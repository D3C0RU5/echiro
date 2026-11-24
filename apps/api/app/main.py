from contextlib import asynccontextmanager
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.configuration import ProjectInput, ConfigurationInput, MetadataInput, DomainError
from app.integrations.client import JiraReader, ProbeError
from app.persistence.database import Database
from app.persistence.secrets import CredentialVault, CredentialError
from app.projects import ProjectService
from app.synchronization.service import SyncService
from app.metrics.service import MetricService


LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def create_app(database_path: Path | None = None, key_path: Path | None = None, *, reader_factory=JiraReader):
    @asynccontextmanager
    async def lifespan(app):
        path = database_path or Path(os.environ.get('ECHIRO_DATABASE_PATH', Path(__file__).resolve().parents[1] / '.local' / 'echiro.sqlite3'))
        key = key_path or Path(os.environ.get('ECHIRO_KEY_PATH', Path.home() / '.config' / 'echiro' / 'credentials.key'))
        database = Database(path)
        if key.resolve().is_relative_to(database.path.parent) or key.resolve().is_relative_to(Path(__file__).resolve().parents[3]):
            raise CredentialError('Guarde a chave fora do repositório e da pasta do banco local.')
        database.initialize()
        with database.transaction() as db:
            existing = bool(db.execute('SELECT 1 FROM connections LIMIT 1').fetchone())
        vault = CredentialVault(key, existing_credentials=existing)
        app.state.projects = ProjectService(database, vault, reader_factory)
        app.state.sync = SyncService(app.state.projects)
        app.state.metrics = MetricService(app.state.sync)
        try:
            yield
        finally:
            app.state.sync.close()

    app = FastAPI(title='echiro API', lifespan=lifespan)

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        try:
            host = urlsplit('http://' + request.headers.get('host', '')).hostname
            origin = request.headers.get('origin')
            parsed = urlsplit(origin) if origin else None
            origin_ok = not parsed or (parsed.scheme == 'http' and parsed.hostname in LOCAL_HOSTS
                                       and parsed.port in (5173, 8000))
        except ValueError:
            host, origin_ok = None, False
        if (host not in LOCAL_HOSTS or not origin_ok
                or request.headers.get('sec-fetch-site') == 'cross-site'
                or (request.client and request.client.host not in LOCAL_HOSTS)):
            return JSONResponse({'detail': 'Acesso permitido somente pela aplicação local.'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # O erro padrão inclui o valor recebido, que pode conter o token.
        return JSONResponse({'detail': 'Dados inválidos. Confira os campos obrigatórios, a URL e as seleções.'}, status_code=422)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=exc.status)

    @app.exception_handler(ProbeError)
    async def jira_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=502)

    @app.exception_handler(CredentialError)
    async def credential_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=503)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'service': 'echiro-api'}

    @app.get('/api/projects')
    def list_projects(request: Request):
        return request.app.state.projects.list()

    @app.post('/api/projects', status_code=201)
    def create_project(value: ProjectInput, request: Request):
        return request.app.state.projects.save(value)

    @app.get('/api/projects/{project_id}')
    def get_project(project_id: str, request: Request):
        return request.app.state.projects.get(project_id)

    @app.put('/api/projects/{project_id}')
    def update_project(project_id: str, value: ProjectInput, request: Request):
        return request.app.state.projects.save(value, project_id)

    @app.post('/api/projects/{project_id}/test-connection')
    def test_connection(project_id: str, request: Request):
        return request.app.state.projects.test_connection(project_id)

    @app.get('/api/projects/{project_id}/metadata')
    def metadata(project_id: str, request: Request):
        return request.app.state.projects.metadata(project_id)

    @app.post('/api/projects/{project_id}/metadata')
    def refresh_metadata(project_id: str, value: MetadataInput, request: Request):
        return request.app.state.projects.refresh_metadata(project_id, value.board_id)

    @app.put('/api/projects/{project_id}/configuration')
    def configure(project_id: str, value: ConfigurationInput, request: Request):
        return request.app.state.projects.configure(project_id, value)

    @app.get('/api/projects/{project_id}/sync')
    def sync_status(project_id: str, request: Request):
        return request.app.state.sync.status(project_id)

    @app.post('/api/projects/{project_id}/sync', status_code=202)
    def start_sync(project_id: str, request: Request):
        return request.app.state.sync.start(project_id)

    @app.post('/api/projects/{project_id}/sync/resume', status_code=202)
    def resume_sync(project_id: str, request: Request):
        return request.app.state.sync.start(project_id, resume=True)

    @app.get('/api/projects/{project_id}/dashboard')
    def dashboard(project_id: str, request: Request):
        return request.app.state.metrics.dashboard(project_id)

    @app.post('/api/projects/{project_id}/recalculate')
    def recalculate(project_id: str, request: Request):
        return request.app.state.metrics.dashboard(project_id, force=True)

    return app


app = create_app()
