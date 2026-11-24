import unittest
import sqlite3
from threading import Event
from unittest.mock import Mock

from app.integrations.client import ProbeError
from app.synchronization.service import RetryingReader
import test_projects as project_fixtures
from test_projects import FakeJira, config_body


class FlowJira(FakeJira):
    histories_read = 0
    fail_issue = None
    updated = '2026-01-20T00:00:00+00:00'
    event_mode = False
    events_removed = False
    hide_second = False

    def raw(self, identity):
        return {'id': str(identity), 'key': f'{self.key}-{identity}', 'fields': {
            'project': {'id': self.project_id}, 'created': '2025-12-20T00:00:00+00:00', 'updated': self.updated,
            'issuetype': {'id': '11' if identity == 1 else '13', 'name': 'Tipo', 'subtask': False},
            'status': {'id': '1', 'name': 'Aberto'}, 'parent': None, 'customfield_1': [{'id': 100}],
        }}

    def get(self, path, **params):
        if path.endswith('/board'):
            return {'values': [{'id': self.board_id, 'name': 'Quadro', 'type': 'scrum'}], 'startAt': 0, 'isLast': True}
        if path.endswith('/sprint'):
            return {'values': [{'id': 100, 'name': 'Sprint', 'state': 'closed', 'originBoardId': self.board_id,
                                'startDate': '2026-01-01T00:00:00Z', 'completeDate': '2026-01-15T00:00:00Z'}],
                    'startAt': 0, 'isLast': True}
        if path.endswith('/field'):

            return [{'id': 'customfield_1', 'name': 'Sprint', 'schema': {'custom': 'com.pyxis.greenhopper.jira:gh-sprint'}}]
        if path.endswith('/search/jql'):
            return {'issues': [self.raw(1)] if self.hide_second else [self.raw(1), self.raw(2)], 'isLast': True}
        if '/issue/' in path:
            identity = int(path.split('/issue/')[1].split('/')[0])
            if path.endswith('/changelog'):
                type(self).histories_read += 1
                if self.fail_issue == identity:
                    raise ProbeError('Falha simulada de comunicação.', status_code=0)
                values = [{'id':'1000','created':'2026-01-01T00:00:00Z','items':[{'fieldId':'status','field':'status','from':'0','to':'1'}]}] if self.event_mode and not self.events_removed else []
                return {'values': values, 'total': len(values), 'isLast': True, 'startAt': 0}
            return self.raw(identity)
        return super().get(path, **params)

    def pages(self, path, field, **params):
        if path.endswith('/sprint'):
            return iter([{'id': 100, 'name': 'Sprint', 'state': 'closed', 'originBoardId': self.board_id,
                          'startDate': '2026-01-01T00:00:00Z', 'completeDate': '2026-01-15T00:00:00Z'}])
        return super().pages(path, field, **params)


class SyncTests(unittest.TestCase):
    start = project_fixtures.ProjectTests.start
    create = project_fixtures.ProjectTests.create
    configure = project_fixtures.ProjectTests.configure
    tearDown = project_fixtures.ProjectTests.tearDown
    def setUp(self):
        project_fixtures.ProjectTests.setUp(self)
        self.service = self.client.app.state.sync
        self.client.app.state.projects.reader_factory = FlowJira
        FlowJira.histories_read, FlowJira.fail_issue = 0, None
        FlowJira.event_mode, FlowJira.events_removed, FlowJira.hide_second = False, False, False
        FlowJira.updated = '2026-01-20T00:00:00+00:00'

    def run_sync(self, project, resume=False):
        run = self.service.start(project['id'], resume=resume, background=False)
        self.service.run(project['id'], run['run_id'])
        return self.service.status(project['id'])['latest']

    def test_full_then_incremental_is_idempotent_and_keeps_bugs(self):
        project = self.configure(self.create())
        first = self.run_sync(project)
        self.assertEqual(first['status'], 'succeeded', first)
        self.assertEqual(FlowJira.histories_read, 2)
        source, _ = self.service.source(project['id'])
        self.assertEqual(len(source['issues']), 2)
        second = self.run_sync(project)
        self.assertEqual(second['status'], 'succeeded')
        self.assertEqual(FlowJira.histories_read, 2)
        self.assertEqual(second['checkpoint']['reused'], 2)
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tickets').fetchone()[0], 2)
        FlowJira.updated = '2026-01-21T00:00:00Z'
        self.assertEqual(self.run_sync(project)['status'], 'succeeded')
        self.assertEqual(FlowJira.histories_read, 4)

    def test_failure_preserves_snapshot_and_resume_uses_staged_histories(self):
        project = self.configure(self.create())
        self.run_sync(project)
        before, run_id = self.service.source(project['id'])
        FlowJira.updated = '2026-01-21T00:00:00Z'
        FlowJira.fail_issue = 2
        # Não aguarda o backoff real neste teste de falha persistente.
        self.service.stop.wait = Mock(return_value=False)
        failed = self.run_sync(project)
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(self.service.source(project['id']), (before, run_id))
        FlowJira.fail_issue = None
        resumed = self.run_sync(project, resume=True)
        self.assertEqual(resumed['id'], failed['id'])
        self.assertEqual(resumed['status'], 'succeeded')
        self.assertEqual(resumed['checkpoint']['reused'], 1)

    def test_one_running_run_per_project_and_independent_other_project(self):
        first, second = self.configure(self.create()), self.configure(self.create('BETA'), 20)
        run = self.service.start(first['id'], background=False)
        response = self.client.post(f"/api/projects/{first['id']}/sync")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.run_sync(second)['status'], 'succeeded')
        self.service.run(first['id'], run['run_id'])
        self.assertEqual(len(self.service.source(second['id'])[0]['issues']), 2)
        self.assertNotEqual(self.service.source(first['id'])[0]['project_id'], self.service.source(second['id'])[0]['project_id'])

    def test_restart_marks_interrupted_without_automatic_restart(self):
        project = self.configure(self.create())
        self.service.start(project['id'], background=False)
        self.client.__exit__(None, None, None)
        self.client = self.start()
        self.service = self.client.app.state.sync
        self.client.app.state.projects.reader_factory = FlowJira
        status = self.service.status(project['id'])
        self.assertEqual(status['latest']['status'], 'interrupted')
        self.assertIsNone(status['last_success'])
        self.assertEqual(FlowJira.histories_read, 0)
        self.assertEqual(self.run_sync(project, resume=True)['status'], 'succeeded')

    def test_previously_collected_events_are_retained_when_api_history_disappears(self):
        project = self.configure(self.create())
        FlowJira.event_mode = True
        self.assertEqual(self.run_sync(project)['status'], 'succeeded')
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM history_events').fetchone()[0], 2)
        FlowJira.events_removed = True
        FlowJira.updated = '2026-01-21T00:00:00Z'
        self.assertEqual(self.run_sync(project)['status'], 'succeeded')
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM history_events').fetchone()[0], 2)
        result = self.client.get(f"/api/projects/{project['id']}/dashboard").json()
        self.assertIsNone(result['sprints'][0]['metrics']['worked']['value'])
        self.assertIsNone(result['sprints'][0]['metrics']['bugs_total']['value'])

    def test_lost_ticket_visibility_is_not_silently_counted_as_zero(self):
        project = self.configure(self.create())
        self.run_sync(project)
        FlowJira.hide_second = True
        self.assertEqual(self.run_sync(project)['status'], 'succeeded')
        source, _ = self.service.source(project['id'])
        self.assertEqual(source['missing_previous_tickets'], 1)
        self.assertEqual(len(source['issues']), 2)
        result = self.client.get(f"/api/projects/{project['id']}/dashboard").json()
        self.assertIsNone(result['sprints'][0]['metrics']['bugs_total']['value'])

    def test_dashboard_endpoint_and_rule_change_recalculate_from_same_source(self):
        project = self.configure(self.create())
        path = f"/api/projects/{project['id']}"
        self.assertEqual(self.client.get(path+'/dashboard').json()['state'], 'no_data')
        self.run_sync(project)
        dashboard = self.client.get(path+'/dashboard').json()
        self.assertEqual(dashboard['state'], 'available')
        self.assertEqual(dashboard['sprints'][0]['metrics']['worked']['value'], 1)
        self.assertEqual(dashboard['sprints'][0]['metrics']['bugs_total']['value'], 1)
        body = config_body(); body['ai_adoption_date'] = '2026-01-10'
        project = self.client.put(path+'/configuration', json=body).json()
        self.assertEqual(project['results_state'], 'recalculation_required')
        recalculated = self.client.post(path+'/recalculate').json()
        self.assertEqual(recalculated['config_version'], 2)
        self.assertEqual(recalculated['sync_run_id'], dashboard['sync_run_id'])
        self.assertEqual(recalculated['sprints'][0]['ai_period'], 'transition')


class RetryTests(unittest.TestCase):
    def test_retry_after_respected_for_read_requests(self):
        delegate = Mock()
        delegate.get.side_effect = [ProbeError('limit', status_code=429, retry_after='9'), {'ok': True}]
        stop = Event(); stop.wait = Mock(return_value=False)
        reader = RetryingReader(delegate, stop, Mock())
        self.assertEqual(reader.get('/rest/api/3/myself'), {'ok': True})
        stop.wait.assert_called_once_with(9)
        self.assertEqual(delegate.get.call_count, 2)

    def test_auth_errors_never_retry_and_transient_errors_are_bounded(self):
        delegate = Mock(); stop = Event(); stop.wait = Mock(return_value=False)
        reader = RetryingReader(delegate, stop, Mock())
        delegate.get.side_effect = ProbeError('auth', status_code=401)
        with self.assertRaises(ProbeError):
            reader.get('/rest/api/3/myself')
        self.assertEqual(delegate.get.call_count, 1)
        delegate.get.reset_mock(); delegate.get.side_effect = ProbeError('network', status_code=0)
        with self.assertRaises(ProbeError):
            reader.get('/rest/api/3/myself')
        self.assertEqual(delegate.get.call_count, 3)
