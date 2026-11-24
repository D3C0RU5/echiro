"""Serviço de cadastro: isola projetos e versiona configurações."""
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

from app.domain.configuration import DomainError, ProjectInput, ConfigurationInput, validate_configuration
from app.integrations.client import JiraReader
from app.integrations.jira import project_details, fetch_metadata
from app.persistence.database import Database
from app.persistence.secrets import CredentialVault


def now():
    return datetime.now(timezone.utc).isoformat()


class ProjectService:
    def __init__(self, db: Database, vault: CredentialVault, reader_factory=JiraReader):
        self.db, self.vault, self.reader_factory = db, vault, reader_factory

    def _row(self, db, project_id):
        row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if row is None:
            raise DomainError('Projeto não encontrado.', 404)
        return row

    def _public(self, db, row):
        result = dict(row)
        config = db.execute('SELECT data FROM configurations WHERE project_id=? AND version=?',
                            (row['id'], row['config_version'])).fetchone()
        result['configuration'] = json.loads(config['data']) if config else None
        latest = db.execute('SELECT config_version,data FROM metric_runs WHERE project_id=? ORDER BY computed_at DESC LIMIT 1',
                            (row['id'],)).fetchone()
        result['results_state'] = ('not_calculated' if latest is None else
                                   'current' if latest[0] == row['config_version'] else 'recalculation_required')
        snapshot = db.execute('SELECT run_id FROM snapshots WHERE project_id=?', (row['id'],)).fetchone()
        if latest and snapshot and json.loads(latest['data']).get('sync_run_id') != snapshot[0]:
            result['results_state'] = 'recalculation_required'
        result['configured'] = config is not None
        connection = db.execute('SELECT tested_at, test_status FROM connections WHERE project_id=?', (row['id'],)).fetchone()
        result['connection'] = {'credentials_saved': connection is not None,
                                'tested_at': connection['tested_at'] if connection else None,
                                'status': connection['test_status'] if connection else None}
        return result

    def list(self):
        with self.db.transaction() as db:
            return [self._public(db, row) for row in db.execute('SELECT * FROM projects ORDER BY created_at')]

    def get(self, project_id):
        with self.db.transaction() as db:
            return self._public(db, self._row(db, project_id))

    def save(self, value: ProjectInput, project_id=None):
        with self.db.transaction() as db:
            old = self._row(db, project_id) if project_id else None
            credentials = None
            if old:
                encrypted = db.execute('SELECT credentials FROM connections WHERE project_id=?', (project_id,)).fetchone()
                credentials = self.vault.decrypt(encrypted[0])
                if old['jira_url'] != value.jira_url or old['project_key'] != value.project_key:
                    raise DomainError('URL e chave identificam o projeto. Cadastre outra conexão para trocar sua origem.')
            email = value.email.get_secret_value().strip() if value.email else (credentials or {}).get('email', '')
            token = value.token.get_secret_value().strip() if value.token else (credentials or {}).get('token', '')
            if not email or '@' not in email or not token:
                raise DomainError('Informe um e-mail Atlassian válido e o token de API.')
            project_id = project_id or str(uuid4())
            timestamp = now()
            try:
                if old:
                    db.execute('UPDATE projects SET name=?, updated_at=? WHERE id=?', (value.name, timestamp, project_id))
                else:
                    db.execute('INSERT INTO projects(id,name,jira_url,project_key,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                               (project_id, value.name, value.jira_url, value.project_key, timestamp, timestamp))
                if not old or credentials != {'email': email, 'token': token}:
                    db.execute('INSERT INTO connections(project_id,credentials) VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET credentials=excluded.credentials,tested_at=NULL,test_status=NULL',
                               (project_id, self.vault.encrypt(email, token)))
            except sqlite3.IntegrityError:
                raise DomainError('Este projeto já está cadastrado neste site Jira.', 409) from None
            return self._public(db, self._row(db, project_id))

    def _reader(self, project_id):
        with self.db.transaction() as db:
            project = dict(self._row(db, project_id))
            encrypted = db.execute('SELECT credentials FROM connections WHERE project_id=?', (project_id,)).fetchone()[0]
        credentials = self.vault.decrypt(encrypted)
        return project, self.reader_factory(project['jira_url'], credentials['email'], credentials['token'])

    def test_connection(self, project_id):
        project, reader = self._reader(project_id)
        details = project_details(reader, project['project_key'])
        with self.db.transaction() as db:
            db.execute('UPDATE connections SET tested_at=?, test_status=? WHERE project_id=?',
                       (now(), 'verified', project_id))
            db.execute('UPDATE projects SET jira_project_id=? WHERE id=?', (str(details['id']), project_id))
        return {'status': 'verified', 'message': 'Conexão de leitura verificada com o projeto Jira.'}

    def metadata(self, project_id):
        with self.db.transaction() as db:
            self._row(db, project_id)
            row = db.execute('SELECT data FROM metadata WHERE project_id=?', (project_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def refresh_metadata(self, project_id, board_id):
        project, reader = self._reader(project_id)
        result = fetch_metadata(reader, project['project_key'], board_id)
        with self.db.transaction() as db:
            db.execute('INSERT INTO metadata(project_id,data,fetched_at) VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET data=excluded.data,fetched_at=excluded.fetched_at',
                       (project_id, json.dumps(result), result['fetched_at']))
            db.execute('UPDATE projects SET jira_project_id=? WHERE id=?', (result['project_id'], project_id))
        return result

    def configure(self, project_id, value: ConfigurationInput):
        with self.db.transaction() as db:
            project = self._row(db, project_id)
            metadata = db.execute('SELECT data FROM metadata WHERE project_id=?', (project_id,)).fetchone()
            if metadata is None:
                raise DomainError('Busque as opções do Jira antes de configurar o projeto.')
            data = validate_configuration(value, json.loads(metadata[0]))
            previous = db.execute('SELECT data FROM configurations WHERE project_id=? AND version=?',
                                  (project_id, project['config_version'])).fetchone()
            old = json.loads(previous[0]) if previous else None
            # Atualizar apenas a data de busca não invalida resultados calculados.
            if old and {k: sorted(v) if isinstance(v, list) else v for k, v in old.items() if k != 'metadata_fetched_at'} == {k: v for k, v in data.items() if k != 'metadata_fetched_at'}:
                return self._public(db, project)
            version, timestamp = project['config_version'] + 1, now()
            db.execute('INSERT INTO configurations(project_id,version,data,created_at) VALUES(?,?,?,?)',
                       (project_id, version, json.dumps(data), timestamp))
            db.execute('UPDATE projects SET config_version=?,updated_at=? WHERE id=?', (version, timestamp, project_id))
            return self._public(db, self._row(db, project_id))
