"""Cadastro via API, Jira simulado e armazenamento temporário."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from app.main import create_app
from app.integrations.client import ProbeError
from app.persistence.database import Database
from app.persistence.secrets import CredentialError, CredentialVault


class FakeJira:
    calls = []
    fail = False

    def __init__(self, url, email, token):
        self.url, self.email, self.token = url, email, token
        self.key = 'ALFA' if 'alfa' in url else 'BETA'
        self.project_id = '10' if self.key == 'ALFA' else '20'
        self.board_id = int(self.project_id)

    def get(self, path, **params):
        self.calls.append((self.url, self.email, path))
        if self.fail:
            raise ProbeError('Autenticação recusada; verifique e-mail e token.')
        if path.endswith('/myself'):
            return {'accountId': 'not-exported'}
        if path.endswith('/statuses'):
            return [dict(id=key, name=name, statuses=[{'id': '1', 'name': 'Aberto'}, {'id': '2', 'name': 'Final'}, {'id': '3', 'name': 'Final bug'}])
                    for key, name in [('11', 'Trabalho'), ('12', 'Filha'), ('13', 'Defeito')]]
        if path.endswith('/configuration'):
            return {'columnConfig': {'columns': [
                {'name': 'Construção', 'statuses': [{'id': '1'}]},
                {'name': 'Encerrado', 'statuses': [{'id': '2'}, {'id': '3'}]},
            ]}}
        return {'id': self.project_id, 'key': self.key, 'name': self.key, 'issueTypes': [
            {'id': '11', 'subtask': False}, {'id': '12', 'subtask': True}, {'id': '13', 'subtask': False},
        ]}

    def pages(self, path, field, **params):
        self.calls.append((self.url, self.email, path))
        if path.endswith('/board'):
            return iter([{'id': self.board_id, 'name': 'Quadro', 'type': 'scrum'}])
        return iter([{'id': 100, 'name': 'Sprint', 'state': 'closed', 'originBoardId': self.board_id}])


def project_body(key='ALFA'):
    return dict(name=f'Projeto {key}', jira_url=f'https://{key.lower()}.atlassian.net',
                project_key=key, email=f'{key.lower()}@example.com', token=f'token-private-{key}')


def config_body(board=10):
    return dict(board_id=board, task_type_ids=['11'], subtask_type_ids=['12'], bug_type_ids=['13'],
                work_column_ids=['0'], task_final_status_ids=['2'], bug_final_status_ids=['3'],
                sprint_ids=['100'], ai_adoption_date='2026-10-01')


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        root = Path(self.directory.name)
        self.db_path, self.key_path = root / 'data' / 'test.sqlite3', root / 'secrets' / 'test.key'
        FakeJira.calls, FakeJira.fail = [], False
        self.client = self.start()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def start(self):
        client = TestClient(create_app(self.db_path, self.key_path, reader_factory=FakeJira),
                            base_url='http://localhost', client=('127.0.0.1', 50000))
        client.__enter__()
        return client

    def create(self, key='ALFA'):
        response = self.client.post('/api/projects', json=project_body(key))
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn('token-private', response.text)
        self.assertNotIn('@example.com', response.text)
        return response.json()

    def configure(self, project, board=10):
        path = f"/api/projects/{project['id']}"
        response = self.client.post(path+'/metadata', json={'board_id': board})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.put(path+'/configuration', json=config_body(board))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_two_projects_persist_after_restart_and_keep_independent_connections(self):
        first, second = self.configure(self.create()), self.configure(self.create('BETA'), 20)
        self.assertEqual(first['configuration']['board_id'], 10)
        self.assertEqual(second['configuration']['board_id'], 20)
        self.assertEqual({(url, email) for url, email, _ in FakeJira.calls}, {
            ('https://alfa.atlassian.net', 'alfa@example.com'), ('https://beta.atlassian.net', 'beta@example.com')})
        self.client.__exit__(None, None, None); self.client = self.start()
        records = self.client.get('/api/projects').json()
        self.assertEqual(len(records), 2)
        self.assertTrue(all(item['configured'] for item in records))
        for project in (first, second):
            self.assertEqual(self.client.get(f"/api/projects/{project['id']}").json()['configuration'], project['configuration'])

    def test_credentials_encrypted_and_key_separate(self):
        self.create()
        data = self.db_path.read_bytes()
        for secret in (b'token-private-ALFA', b'alfa@example.com', self.key_path.read_bytes()):
            self.assertNotIn(secret, data)
        for path in (self.db_path, self.key_path):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_edit_preserves_or_rotates_credentials(self):
        project = self.create(); path = f"/api/projects/{project['id']}"
        body = project_body(); body.update(name='Renomeado', email=None, token=None)
        self.assertEqual(self.client.put(path, json=body).status_code, 200)
        self.assertEqual(self.client.post(path+'/test-connection').status_code, 200)
        body.update(email='new@example.com', token='rotated-token')
        self.client.put(path, json=body)
        self.assertIsNone(self.client.get(path).json()['connection']['tested_at'])
        self.client.post(path+'/test-connection')
        self.assertEqual(FakeJira.calls[-1][1], 'new@example.com')

    def test_conflicts_unknown_options_and_incomplete_rules_rejected(self):
        project = self.configure(self.create()); path = f"/api/projects/{project['id']}"
        changes = [dict(bug_type_ids=['11']), dict(subtask_type_ids=['11']), dict(task_type_ids=['999']),
                   dict(task_final_status_ids=['999']), dict(work_column_ids=['1']), dict(sprint_ids=['999']),
                   dict(board_id=999), dict(sprint_ids=[]), dict(bug_type_ids=['13', '13']), dict(ai_adoption_date='bad')]
        for change in changes:
            with self.subTest(change=change):
                body = config_body(); body.update(change)
                self.assertEqual(self.client.put(path+'/configuration', json=body).status_code, 422)
        self.assertEqual(self.client.get(path).json()['config_version'], 1)

    def test_revision_invalidates_only_affected_project_results(self):
        first, second = self.configure(self.create()), self.configure(self.create('BETA'), 20)
        with sqlite3.connect(self.db_path) as db:
            db.execute('INSERT INTO metric_runs VALUES(?,?,?,?,?)', ('run', first['id'], 1, '2026-11-23T00:00:00Z', '{}'))
        path = f"/api/projects/{first['id']}"
        self.assertEqual(self.client.put(path+'/configuration', json=config_body()).json()['config_version'], 1)
        body = config_body(); body['ai_adoption_date'] = '2026-10-02'
        updated = self.client.put(path+'/configuration', json=body).json()
        self.assertEqual(updated['config_version'], 2)
        self.assertEqual(updated['results_state'], 'recalculation_required')
        other = self.client.get(f"/api/projects/{second['id']}").json()
        self.assertEqual(other['config_version'], 1)
        self.assertEqual(other['results_state'], 'not_calculated')

    def test_selection_order_does_not_create_another_revision(self):
        project = self.configure(self.create()); path = f"/api/projects/{project['id']}/configuration"
        body = config_body(); body['task_final_status_ids'] = ['2', '3']
        initial = self.client.put(path, json=body).json()
        body['task_final_status_ids'] = ['3', '2']
        repeated = self.client.put(path, json=body).json()
        self.assertEqual(initial['config_version'], repeated['config_version'])

    def test_invalid_metadata_has_safe_error(self):
        from unittest.mock import patch
        project = self.create()
        with patch.object(FakeJira, 'get', return_value={}):
            response = self.client.post(f"/api/projects/{project['id']}/metadata", json={})
        self.assertEqual(response.status_code, 502)
        self.assertIn('metadados inesperados', response.json()['detail'])

    def test_key_cannot_be_stored_with_database(self):
        with self.assertRaises(CredentialError):
            with TestClient(create_app(self.db_path, self.db_path.parent / 'key'), base_url='http://localhost'):
                pass

    def test_network_only_on_explicit_action(self):
        project = self.create(); path = f"/api/projects/{project['id']}"
        self.client.get('/api/projects'); self.client.get(path+'/metadata')
        self.assertEqual(FakeJira.calls, [])
        result = self.client.post(path+'/metadata', json={})
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json()['board_id'])
        self.assertEqual(result.json()['columns'], [])

    def test_metadata_required_and_other_project_board_rejected(self):
        project = self.create(); path = f"/api/projects/{project['id']}"
        self.assertEqual(self.client.put(path+'/configuration', json=config_body()).status_code, 422)
        self.assertEqual(self.client.post(path+'/metadata', json={'board_id': 20}).status_code, 502)
        self.assertIsNone(self.client.get(path+'/metadata').json())

    def test_errors_do_not_reflect_credentials(self):
        body = project_body(); body['email'] = {'token': 'private-invalid-secret'}
        response = self.client.post('/api/projects', json=body)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('private-invalid-secret', response.text)
        project = self.create(); FakeJira.fail = True
        response = self.client.post(f"/api/projects/{project['id']}/test-connection")
        self.assertEqual(response.status_code, 502)
        self.assertIn('Autenticação', response.json()['detail'])
        self.assertNotIn('token-private', response.text)

    def test_local_host_origin_and_remote_client_restrictions(self):
        for headers in ({'host': 'evil.example'}, {'origin': 'https://evil.example'}, {'sec-fetch-site': 'cross-site'}):
            self.assertEqual(self.client.get('/api/health', headers=headers).status_code, 403)
        self.assertEqual(self.client.get('/api/health', headers={'origin': 'http://localhost:5173'}).status_code, 200)
        remote = TestClient(create_app(), base_url='http://localhost', client=('192.0.2.1', 1000))
        self.assertEqual(remote.get('/api/health').status_code, 403)

    def test_duplicate_missing_credentials_immutable_identity_and_unknown_project(self):
        project = self.create()
        self.assertEqual(self.client.post('/api/projects', json=project_body()).status_code, 409)
        body = project_body('BETA'); body['token'] = None
        self.assertEqual(self.client.post('/api/projects', json=body).status_code, 422)
        self.assertEqual(self.client.put(f"/api/projects/{project['id']}", json=project_body('BETA')).status_code, 422)
        self.assertEqual(self.client.get('/api/projects/missing').status_code, 404)

    def test_lost_or_wrong_key_not_silently_replaced(self):
        self.create(); key = self.key_path.read_bytes(); self.key_path.unlink()
        with self.assertRaises(CredentialError):
            CredentialVault(self.key_path, existing_credentials=True)
        self.key_path.write_bytes(key); self.key_path.chmod(0o600)
        from cryptography.fernet import Fernet
        wrong = self.key_path.parent / 'wrong.key'; wrong.write_bytes(Fernet.generate_key()); wrong.chmod(0o600)
        vault = CredentialVault(wrong, existing_credentials=True)
        with sqlite3.connect(self.db_path) as db:
            encrypted = db.execute('SELECT credentials FROM connections').fetchone()[0]
        with self.assertRaises(CredentialError):
            vault.decrypt(encrypted)

    def test_composite_jira_keys_and_foreign_keys_isolate_projects(self):
        first, second = self.create(), self.create('BETA')
        with sqlite3.connect(self.db_path) as db:
            db.execute('PRAGMA foreign_keys=ON')
            for project in (first, second):
                db.execute('INSERT INTO tickets VALUES(?,?,?,?)', (project['id'], '123', project['project_key']+'-1', '{}'))
                db.execute('INSERT INTO history_events VALUES(?,?,?,?)', (project['id'], '123', 'event1', '{}'))
            self.assertEqual(db.execute('SELECT count(*) FROM history_events').fetchone()[0], 2)
            for ticket, event in [('unrelated', 'event2'), ('123', 'event1')]:
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute('INSERT INTO history_events VALUES(?,?,?,?)', (first['id'], ticket, event, '{}'))

    def test_versioned_migration_idempotent_and_transaction_rolls_back(self):
        database = Database(self.db_path); database.initialize(); database.initialize()
        with database.transaction() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
        with self.assertRaises(RuntimeError):
            with database.transaction() as db:
                db.execute("INSERT INTO projects(id,name,jira_url,project_key,created_at,updated_at) VALUES('rollback','x','x','x','x','x')")
                raise RuntimeError('rollback')
        self.assertEqual(self.client.get('/api/projects').json(), [])


if __name__ == '__main__':
    unittest.main()
