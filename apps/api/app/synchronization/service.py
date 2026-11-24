"""Sincronização manual com preparação isolada e publicação atômica."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import sqlite3
from threading import Event
from uuid import uuid4

from app.domain.configuration import DomainError
from app.integrations.client import JiraReader, ProbeError
from app.integrations.jira import fetch_metadata
from app.jira_probe import issue_evidence, SPRINT_SCHEMA
from app.projects import now


class RetryingReader(JiraReader):
    """Reutiliza paginação, interceptando somente o GET para tentativas limitadas."""
    def __init__(self, reader, stop: Event, progress):
        self.reader, self.stop, self.progress = reader, stop, progress

    def get(self, path, **params):
        for attempt in range(3):
            if self.stop.is_set():
                raise ProbeError('Coleta interrompida; use Retomar para continuar.')
            try:
                return self.reader.get(path, **params)
            except ProbeError as error:
                if getattr(error, 'status_code', None) not in (0, 429, 500, 502, 503, 504) or attempt == 2:
                    raise
                delay = 2 ** attempt
                if error.retry_after:
                    try:
                        delay = max(delay, float(error.retry_after))
                    except ValueError:
                        try:
                            delay = max(delay, (parsedate_to_datetime(error.retry_after) - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError):
                            raise ProbeError('O Jira informou um prazo de nova tentativa inválido.') from None
                self.progress('waiting_retry', retry_in_seconds=delay)
                if self.stop.wait(delay):
                    raise ProbeError('Coleta interrompida; use Retomar para continuar.')


class SyncService:
    def __init__(self, projects):
        self.projects, self.db = projects, projects.db
        self.stop = Event()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='jira-sync')
        # A aplicação local é executada em um único processo, sem workers extras.
        with self.db.transaction() as db:
            db.execute("UPDATE sync_runs SET status='interrupted',finished_at=?,error_code=? WHERE status='running'",
                       (now(), 'Aplicação reiniciada durante a coleta. Use Retomar.',))

    def close(self):
        self.stop.set()
        self.executor.shutdown(wait=True)

    def status(self, project_id):
        with self.db.transaction() as db:
            self.projects._row(db, project_id)
            rows = db.execute('SELECT * FROM sync_runs WHERE project_id=? ORDER BY started_at DESC LIMIT 10', (project_id,)).fetchall()
            snapshot = db.execute('SELECT collected_at,run_id FROM snapshots WHERE project_id=?', (project_id,)).fetchone()
        return {'latest': self._public(rows[0]) if rows else None,
                'last_success': dict(snapshot) if snapshot else None,
                'runs': [self._public(row) for row in rows]}

    @staticmethod
    def _public(row):
        return {key: json.loads(row[key]) if key == 'checkpoint' and row[key] else row[key]
                for key in ('id', 'status', 'started_at', 'finished_at', 'checkpoint', 'error_code', 'config_version')}

    def start(self, project_id, *, resume=False, background=True):
        with self.db.transaction() as db:
            project = self.projects._row(db, project_id)
            if not project['config_version']:
                raise DomainError('Configure o projeto antes de sincronizar.')
            if db.execute("SELECT 1 FROM sync_runs WHERE project_id=? AND status='running'", (project_id,)).fetchone():
                raise DomainError('Já existe uma sincronização em andamento neste projeto.', 409)
            previous = db.execute('SELECT * FROM sync_runs WHERE project_id=? ORDER BY started_at DESC LIMIT 1', (project_id,)).fetchone()
            run_id = str(uuid4())
            if resume:
                if not previous or previous['status'] not in ('failed', 'interrupted'):
                    raise DomainError('Não há coleta interrompida para retomar.')
                if previous['config_version'] != project['config_version']:
                    raise DomainError('A configuração mudou. Inicie uma nova sincronização.')
                run_id = previous['id']
                db.execute("UPDATE sync_runs SET status='running',finished_at=NULL,error_code=NULL WHERE id=?", (run_id,))
            else:
                try:
                    db.execute('INSERT INTO sync_runs(id,project_id,status,started_at,config_version,checkpoint) VALUES(?,?,?,?,?,?)',
                               (run_id, project_id, 'running', now(), project['config_version'], json.dumps({'stage': 'starting', 'read': 0})))
                except sqlite3.IntegrityError:
                    raise DomainError('Já existe uma sincronização em andamento.', 409) from None
        if background:
            self.executor.submit(self.run, project_id, run_id)
        return {'run_id': run_id, 'status': 'running'}

    def _progress(self, run_id, stage, **values):
        with self.db.transaction() as db:
            row = db.execute('SELECT checkpoint FROM sync_runs WHERE id=?', (run_id,)).fetchone()
            checkpoint = json.loads(row[0] or '{}')
            checkpoint.update(stage=stage, **values)
            db.execute('UPDATE sync_runs SET checkpoint=? WHERE id=?', (json.dumps(checkpoint), run_id))

    def run(self, project_id, run_id):
        try:
            project, delegate = self.projects._reader(project_id)
            reader = RetryingReader(delegate, self.stop, lambda stage, **values: self._progress(run_id, stage, **values))
            with self.db.transaction() as db:
                version = db.execute('SELECT config_version FROM sync_runs WHERE id=?', (run_id,)).fetchone()[0]
                config = json.loads(db.execute('SELECT data FROM configurations WHERE project_id=? AND version=?', (project_id, version)).fetchone()[0])
                baseline = {row['jira_id']: json.loads(row['data']) for row in db.execute('SELECT jira_id,data FROM tickets WHERE project_id=?', (project_id,))}
                staged = {row['ticket_id']: json.loads(row['data']) for row in db.execute('SELECT ticket_id,data FROM sync_staging WHERE run_id=?', (run_id,))}
            self._progress(run_id, 'metadata')
            metadata = fetch_metadata(reader, project['project_key'], config['board_id'])
            if project['jira_project_id'] and metadata['project_id'] != project['jira_project_id']:
                raise ProbeError('A identidade do projeto Jira mudou. Confira o cadastro.')
            fields = [{'id': item['id'], 'name': item['name']} for item in reader.get('/rest/api/3/field')
                      if (item.get('schema') or {}).get('custom') == SPRINT_SCHEMA]
            requested = ','.join(['project', 'issuetype', 'status', 'parent', 'created', 'updated', *(field['id'] for field in fields)])
            search_audit = {}
            self._progress(run_id, 'search')
            manifest = list(reader.search_issues(f'project = "{project["project_key"]}" ORDER BY created ASC, key ASC', requested,
                                               audit=search_audit))
            self._progress(run_id, 'histories', total=len(manifest), read=0, reused=0)
            collected, reused = [], 0

            def read_one(raw):
                if self.stop.is_set():
                    raise ProbeError('Coleta interrompida; use Retomar para continuar.')
                if str(raw['fields']['project']['id']) != metadata['project_id']:
                    raise ProbeError('A busca retornou um ticket de outro projeto.')
                previous = staged.get(str(raw['id'])) or baseline.get(str(raw['id']))
                if previous and raw['fields'].get('updated') and previous['updated'] == raw['fields']['updated']:
                    return previous, True
                for attempt in range(2):
                    evidence = issue_evidence(reader, raw, fields)
                    fresh = reader.get(f'/rest/api/3/issue/{raw["id"]}', fields=requested)
                    if str(fresh['fields']['project']['id']) != metadata['project_id']:
                        raise ProbeError('Um ticket mudou de projeto durante a coleta. Execute novamente.')
                    if fresh['fields'].get('updated') == raw['fields'].get('updated'):
                        break
                    raw = fresh
                else:
                    raise ProbeError('Um ticket mudou durante a coleta. Retome para atualizar sua evidência.')
                if previous:
                    def identities(value):
                        return {(category, str(event['history_id']), event.get('from'), event.get('to'))
                                for category in ('status_changes', 'sprint_changes', 'parent_changes', 'issue_type_changes')
                                for event in value.get(category, [])}
                    if identities(previous) - identities(evidence) or previous.get('history_limitations'):
                        evidence['history_limitations'] = ['Eventos anteriormente coletados não retornaram; histórico requer conferência.']
                with self.db.transaction() as db:
                    db.execute('INSERT INTO sync_staging VALUES(?,?,?,?) ON CONFLICT(run_id,ticket_id) DO UPDATE SET updated_at=excluded.updated_at,data=excluded.data',
                               (run_id, str(evidence['id']), evidence['updated'], json.dumps(evidence)))
                return evidence, False

            # Três leituras independentes limitam a latência sem uma rajada de tickets.
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix='jira-history') as pool:
                futures = [pool.submit(read_one, raw) for raw in manifest]
                try:
                    for future in as_completed(futures):
                        evidence, was_reused = future.result()
                        collected.append(evidence)
                        reused += was_reused
                        self._progress(run_id, 'histories', read=len(collected), reused=reused)
                except Exception:
                    for future in futures:
                        future.cancel()
                    raise
            cutoff = now()
            observed = {str(item['id']) for item in collected}
            missing = set(baseline) - observed
            limitations = [
                'A API não comprova acesso a tickets ocultos, excluídos ou movidos para fora do projeto.',
                'A coleta não é um snapshot transacional do Jira.',
                'Configuração histórica de colunas não reconstruída; IDs configurados são aplicados a todo o histórico.',
            ]
            if missing:
                limitations.append('Tickets da base anterior não retornaram na busca; a visibilidade da base está incompleta.')
            if len(fields) != 1:
                limitations.append('O campo de sprint está ausente ou ambíguo; participação indisponível.')
            previous_metadata = self.projects.metadata(project_id)
            if previous_metadata and previous_metadata['columns'] != metadata['columns']:
                limitations.append('As colunas ou seus status mudaram desde a última configuração; revise as regras de trabalho.')
            source = {'connection': project_id, 'project_id': metadata['project_id'], 'project_key': project['project_key'],
                      'issue_types': metadata['issue_types'], 'columns': metadata['columns'], 'board_id': config['board_id'],
                      'sprint_fields': fields, 'sprints': metadata['sprints'],
                      'collection': {'finished_at': cutoff, 'complete': True}, 'issues': collected,
                      'limitations': limitations, 'missing_previous_tickets': len(missing),
                      'metadata_changed': bool(previous_metadata and previous_metadata['columns'] != metadata['columns'])}
            self._progress(run_id, 'publishing')
            with self.db.transaction() as db:
                for evidence in collected:
                    identity = str(evidence['id'])
                    db.execute('INSERT INTO tickets VALUES(?,?,?,?) ON CONFLICT(project_id,jira_id) DO UPDATE SET issue_key=excluded.issue_key,data=excluded.data',
                               (project_id, identity, evidence['key'], json.dumps(evidence)))
                    grouped = {}
                    for category in ('status_changes', 'sprint_changes', 'parent_changes', 'issue_type_changes'):
                        for event in evidence[category]:
                            grouped.setdefault(str(event['history_id']), []).append({'kind': category, **event})
                    for history_id, events in grouped.items():
                        db.execute('INSERT INTO history_events VALUES(?,?,?,?) ON CONFLICT(project_id,ticket_id,jira_id) DO UPDATE SET data=excluded.data', (project_id, identity, history_id, json.dumps(events)))
                for sprint in metadata['sprints']:
                    db.execute('INSERT INTO sprints VALUES(?,?,?) ON CONFLICT(project_id,jira_id) DO UPDATE SET data=excluded.data',
                               (project_id, str(sprint['id']), json.dumps(sprint)))
                # Metadados e fontes ficam na mesma transação da publicação.
                source_without_issues = {key: value for key, value in source.items() if key != 'issues'}
                db.execute('INSERT INTO snapshots VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET run_id=excluded.run_id,collected_at=excluded.collected_at,data=excluded.data',
                           (project_id, run_id, cutoff, json.dumps(source_without_issues)))
                db.execute("UPDATE sync_runs SET status='succeeded',finished_at=?,error_code=NULL,checkpoint=? WHERE id=?",
                           (cutoff, json.dumps({'stage': 'completed', 'read': len(collected), 'total': len(manifest), 'reused': reused}), run_id))
                db.execute('DELETE FROM sync_staging WHERE run_id=?', (run_id,))
        except Exception as error:
            safe = str(error) if isinstance(error, (ProbeError, DomainError)) else 'Falha ao ler ou persistir a coleta. A última base válida foi preservada.'
            with self.db.transaction() as db:
                db.execute('UPDATE sync_runs SET status=?,finished_at=?,error_code=? WHERE id=?',
                           ('interrupted' if self.stop.is_set() else 'failed', now(), safe, run_id))

    def source(self, project_id):
        with self.db.transaction() as db:
            self.projects._row(db, project_id)
            row = db.execute('SELECT * FROM snapshots WHERE project_id=?', (project_id,)).fetchone()
            if row is None:
                return None, None
            source = json.loads(row['data'])
            source['issues'] = [json.loads(item[0]) for item in db.execute('SELECT data FROM tickets WHERE project_id=?', (project_id,))]
            return source, row['run_id']
