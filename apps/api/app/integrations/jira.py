"""Metadados para cadastro. Todas as consultas remotas usam GET."""
from datetime import datetime, timezone
from .client import JiraReader, ProbeError


def project_details(reader: JiraReader, project_key: str) -> dict:
    reader.get('/rest/api/3/myself')
    return reader.get(f'/rest/api/3/project/{project_key}', expand='issueTypes')


def _fetch_metadata(reader: JiraReader, project_key: str, board_id: int | None) -> dict:
    project = project_details(reader, project_key)
    boards = list(reader.pages('/rest/agile/1.0/board', 'values', projectKeyOrId=project['id']))
    types = reader.get(f'/rest/api/3/project/{project_key}/statuses')
    details = {str(item['id']): item for item in project['issueTypes']}
    result = {
        'project_id': str(project['id']), 'project_name': project['name'],
        'boards': [{key: item[key] for key in ('id', 'name', 'type')} for item in boards],
        'issue_types': [{'id': str(item['id']), 'name': item['name'],
                         'subtask': bool(details[str(item['id'])].get('subtask')),
                         'statuses': [{'id': str(status['id']), 'name': status['name']} for status in item['statuses']]}
                        for item in types],
        'board_id': board_id, 'columns': [], 'sprints': [],
        'fetched_at': datetime.now(timezone.utc).isoformat(),
    }
    if board_id is not None:
        if board_id not in {int(item['id']) for item in boards}:
            raise ProbeError('O quadro escolhido não pertence às opções acessíveis deste projeto.')
        board = reader.get(f'/rest/agile/1.0/board/{board_id}/configuration')
        if not any(item['type'] == 'scrum' and int(item['id']) == board_id for item in boards):
            raise ProbeError('Escolha um quadro Scrum para analisar sprints.')
        result['columns'] = [
            {'id': str(index), 'name': column['name'],
             'status_ids': [str(status['id']) for status in column['statuses']]}
            for index, column in enumerate(board['columnConfig']['columns'])
        ]
        result['sprints'] = [
            {key: item.get(key) for key in ('id', 'name', 'state', 'startDate', 'endDate', 'completeDate', 'originBoardId')}
            for item in reader.pages(f'/rest/agile/1.0/board/{board_id}/sprint', 'values')
        ]
    return result


def fetch_metadata(reader: JiraReader, project_key: str, board_id: int | None) -> dict:
    try:
        return _fetch_metadata(reader, project_key, board_id)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ProbeError('O Jira retornou metadados inesperados. Tente atualizar as opções novamente.') from None
