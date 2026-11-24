import json
from uuid import uuid4

from app.domain.configuration import DomainError
from app.projects import now
from .engine import ENGINE_VERSION, calculate, compare


class MetricService:
    def __init__(self, sync):
        self.sync, self.db, self.projects = sync, sync.db, sync.projects

    def dashboard(self, project_id, *, force=False):
        project = self.projects.get(project_id)
        source, run_id = self.sync.source(project_id)
        if source is None:
            return {'state': 'no_data', 'project': project, 'sprints': [], 'sync': self.sync.status(project_id)}
        if source.get('board_id') != project['configuration']['board_id']:
            return {'state': 'sync_required', 'project': project, 'sprints': [], 'sync': self.sync.status(project_id)}
        with self.db.transaction() as db:
            latest = db.execute('SELECT * FROM metric_runs WHERE project_id=? ORDER BY computed_at DESC LIMIT 1', (project_id,)).fetchone()
        cached = json.loads(latest['data']) if latest else None
        if not force and cached and cached.get('engine_version') == ENGINE_VERSION and latest['config_version'] == project['config_version'] and cached.get('sync_run_id') == run_id:
            result = cached
        else:
            result = calculate(source, project['configuration'])
            result.update(sync_run_id=run_id, config_version=project['config_version'], computed_at=now())
            with self.db.transaction() as db:
                current = self.projects._row(db, project_id)
                snapshot = db.execute('SELECT run_id FROM snapshots WHERE project_id=?', (project_id,)).fetchone()
                if current['config_version'] != project['config_version'] or snapshot[0] != run_id:
                    raise DomainError('A base ou a configuração mudou durante o cálculo. Atualize a análise.', 409)
                db.execute('INSERT INTO metric_runs VALUES(?,?,?,?,?)',
                           (str(uuid4()), project_id, project['config_version'], result['computed_at'], json.dumps(result)))
        # URLs são construídas da origem validada, sem credenciais.
        for row in result['sprints']:
            for metric in row['metrics'].values():
                for ticket in metric['tickets']:
                    ticket['url'] = project['jira_url'] + '/browse/' + ticket['key']
        project['results_state'] = 'current'
        return {**result, 'state': 'available', 'project': project, 'comparison': compare(result['sprints']),
                'sync': self.sync.status(project_id)}
