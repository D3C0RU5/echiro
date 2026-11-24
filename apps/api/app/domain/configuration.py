from datetime import date
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class DomainError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    jira_url: str = Field(max_length=250)
    project_key: str = Field(pattern=r'^[A-Z][A-Z0-9_]*$', max_length=60)
    email: SecretStr | None = None
    token: SecretStr | None = None

    @field_validator('name', 'jira_url', 'project_key', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('jira_url')
    @classmethod
    def cloud_url(cls, value):
        try:
            parsed = urlsplit(value)
            valid = (parsed.scheme == 'https' and parsed.hostname
                     and parsed.hostname.endswith('.atlassian.net')
                     and not parsed.username and not parsed.password
                     and parsed.port in (None, 443) and parsed.path in ('', '/')
                     and not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('Use a URL HTTPS do seu site Jira Cloud.')
        return value.rstrip('/').lower()


class MetadataInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    board_id: int | None = Field(default=None, gt=0)


Id = Annotated[str, Field(pattern=r'^\d+$', max_length=30)]


class ConfigurationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    board_id: int = Field(gt=0)
    task_type_ids: list[Id] = Field(default_factory=list)
    subtask_type_ids: list[Id] = Field(default_factory=list)
    bug_type_ids: list[Id] = Field(min_length=1)
    work_column_ids: list[Id] = Field(min_length=1)
    task_final_status_ids: list[Id] = Field(min_length=1)
    bug_final_status_ids: list[Id] = Field(min_length=1)
    sprint_ids: list[Id] = Field(min_length=1)
    ai_adoption_date: date | None = None


def validate_configuration(value: ConfigurationInput, metadata: dict) -> dict:
    if value.board_id != metadata.get('board_id'):
        raise DomainError('Busque as opções do quadro escolhido antes de salvar.')
    data = value.model_dump(mode='json')
    for key, values in data.items():
        if isinstance(values, list):
            if len(values) != len(set(values)):
                raise DomainError('Remova seleções repetidas da configuração.')
            data[key] = sorted(values)
    task, subtask, bug = map(set, (value.task_type_ids, value.subtask_type_ids, value.bug_type_ids))
    if not task | subtask:
        raise DomainError('Selecione pelo menos um tipo de tarefa ou subtarefa.')
    if task & subtask or (task | subtask) & bug:
        raise DomainError('Um tipo não pode representar mais de uma categoria.')
    types = {str(item['id']): item for item in metadata['issue_types']}
    if not (task | subtask | bug) <= types.keys():
        raise DomainError('Há tipos que não pertencem às opções deste projeto.')
    if any(types[item]['subtask'] for item in task | bug) or any(not types[item]['subtask'] for item in subtask):
        raise DomainError('Selecione tipos de subtarefa somente na categoria de subtarefas.')
    statuses = lambda ids: {str(s['id']) for item in ids for s in types[item]['statuses']}
    if not set(value.task_final_status_ids) <= statuses(task | subtask):
        raise DomainError('Os status finais de trabalho devem pertencer aos tipos selecionados.')
    if not set(value.bug_final_status_ids) <= statuses(bug):
        raise DomainError('Os status finais de bugs devem pertencer aos tipos selecionados.')
    columns = {item['id']: item for item in metadata['columns']}
    if not set(value.work_column_ids) <= columns.keys():
        raise DomainError('Há colunas que não pertencem ao quadro escolhido.')
    work = {status for item in value.work_column_ids for status in columns[item]['status_ids']}
    if not work:
        raise DomainError('As colunas de trabalho precisam conter status.')
    if work & set(value.task_final_status_ids):
        raise DomainError('Uma coluna de trabalho não pode conter status finais de tarefas.')
    if not set(value.sprint_ids) <= {str(item['id']) for item in metadata['sprints']}:
        raise DomainError('Há sprints fora das opções do quadro escolhido.')
    data['work_status_ids'] = sorted(work)
    data['metadata_fetched_at'] = metadata['fetched_at']
    return data
