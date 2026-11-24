"""Cálculos puros por sprint. Intervalos desconhecidos nunca viram zero."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.jira_participation import Segment, history_segments
from app.jira_review import ReviewError, current_sprints, sprint_ids
from app.jira_time import DISPLAY_TIMEZONE, sprint_window, utc_instant


ENGINE_VERSION = 2


METRICS = ('worked', 'completed', 'reopened', 'bugs_total', 'bugs_new', 'bugs_existing')
WINDOW_REASONS = {
    'future_sprint': 'Sprint futura; os indicadores ainda não são calculados.',
    'unsupported_state': 'Estado da sprint indisponível.',
    'missing_start_date': 'Data real de início da sprint ausente.',
    'missing_complete_date': 'Data real de encerramento da sprint ausente.',
    'invalid_or_naive_date': 'Data inválida ou sem fuso horário.',
    'nonpositive_interval': 'As datas da sprint não formam um intervalo válido.',
    'completion_after_collection': 'O encerramento informado é posterior ao corte da coleta.',
}



def overlaps(a, b, c, d):
    return max(a, c) < min(b, d)


def intersections(left, right):
    return [Segment(max(a.start, b.start), min(a.end, b.end), a.value)
            for a in left for b in right if overlaps(a.start, a.end, b.start, b.end)]


def at(segments, instant):
    return next((segment.value for segment in segments if segment.start <= instant < segment.end), None)


def _timeline(issue, field, current, cutoff, decode=lambda value: value):
    result = history_segments(issue[field], current, issue['created'], cutoff, decode)
    if any(segment.value is None for segment in result):
        raise ReviewError('missing_historical_value')
    return result


def prepare(source, config):
    cutoff = source['collection']['finished_at']
    by_id = {str(issue['id']): issue for issue in source['issues']}
    by_key = {issue['key']: str(issue['id']) for issue in source['issues']}
    subtypes = {str(item['id']) for item in source['issue_types'] if item['subtask']} | set(config['subtask_type_ids'])
    known_types = {str(item['id']) for item in source['issue_types']}
    tasks = set(config['task_type_ids']) | set(config['subtask_type_ids'])
    finals, work = set(config['task_final_status_ids']), set(config['work_status_ids'])
    prepared = {}

    def identity(value):
        return by_key.get(str(value), str(value)) if value else None

    def memberships(issue, *, current_applicable=True):
        current, available = current_sprints(issue)
        if len(source['sprint_fields']) != 1 or not available:
            raise ReviewError('sprint_field_unavailable_or_ambiguous')
        if not current_applicable:
            # Após conversão para subtarefa, o valor atual é herdado. Ele não
            # valida o antigo campo próprio de uma tarefa padrão. Só usamos
            # a cadeia explícita, e apenas nos períodos de tipo padrão.
            if not issue['sprint_changes']:
                raise ReviewError('standard_sprint_history_before_conversion_unavailable')
            current = sprint_ids(sorted(issue['sprint_changes'], key=lambda event: utc_instant(event['at']))[-1]['to'])
        return _timeline(issue, 'sprint_changes', current, cutoff, sprint_ids)

    for identity_id, issue in by_id.items():
        item = {'issue': issue, 'gaps': {}, 'types': [], 'status': [], 'membership': [], 'working': [],
                'first_completion': None, 'reopenings': []}
        try:
            if issue.get('history_limitations'):
                raise ReviewError('previous_history_events_missing')
            item['types'] = _timeline(issue, 'issue_type_changes', str(issue['issue_type']['id']), cutoff)
            item['status'] = _timeline(issue, 'status_changes', str(issue['status']['id']), cutoff)
        except (ReviewError, ValueError, TypeError, KeyError, AttributeError):
            item['gaps']['state'] = 'Histórico de tipo/status indisponível, descontínuo ou com datas inválidas.'
            prepared[identity_id] = item
            continue
        working = False
        for segment in item['status']:
            if segment.value in finals:
                working = False
            elif segment.value in work:
                working = True
            if working:
                item['working'].append(segment)
        first_known = not (item['status'] and item['status'][0].value in finals)
        if not first_known:
            item['gaps']['completion'] = 'Histórico inicia em status final; a primeira conclusão não é verificável.'
        for event in sorted(issue['status_changes'], key=lambda event: utc_instant(event['at'])):
            instant = utc_instant(event['at'])
            kind = at(item['types'], instant)
            if kind in tasks and event['from'] not in finals and event['to'] in finals and item['first_completion'] is None and first_known:
                item['first_completion'] = event
            applicable_finals = finals if kind in tasks else set(config['bug_final_status_ids'])
            if event['from'] in applicable_finals and event['to'] not in applicable_finals:
                item['reopenings'].append(event)
        relevant = [segment for segment in item['types'] if segment.value in tasks]
        own = [segment for segment in relevant if segment.value not in subtypes]
        child_periods = [segment for segment in relevant if segment.value in subtypes]
        item['membership_gaps'] = []

        def membership_gap(periods, error):
            item['membership_gap_code'] = str(error) if isinstance(error, ReviewError) else 'unsupported_history_format'
            item['gaps']['membership'] = ('Participação em sprint anterior à conversão para subtarefa sem evidência suficiente.'
                                          if item['membership_gap_code'] == 'standard_sprint_history_before_conversion_unavailable'
                                          else 'Participação própria ou derivada indisponível; confira campo de sprint e vínculos históricos.')
            item['membership_gaps'].extend(periods)

        if own:
            try:
                item['membership'].extend(intersections(memberships(issue, current_applicable=str(issue['issue_type']['id']) not in subtypes), own))
            except (ReviewError, KeyError, ValueError, TypeError, AttributeError) as error:
                membership_gap(own, error)
        if child_periods:
            try:
                if issue.get('unrecognized_parent_fields'):
                    raise ReviewError('unrecognized_parent_history')
                if not issue.get('parent') and not issue['parent_changes']:
                    raise ReviewError('parent_unavailable')
                parents = history_segments(issue['parent_changes'], identity((issue.get('parent') or {}).get('id')),
                                           issue['created'], cutoff, identity)
                for period in intersections(parents, child_periods):
                    if period.value is None:
                        continue
                    try:
                        parent = by_id.get(period.value)
                        if parent is None:
                            raise ReviewError('historical_parent_unavailable')
                        if period.start < utc_instant(parent['created']):
                            raise ReviewError('parent_created_after_child_association')
                        parent_types = _timeline(parent, 'issue_type_changes', str(parent['issue_type']['id']), cutoff)
                        if any(segment.value in subtypes or segment.value not in known_types
                               for segment in parent_types if overlaps(period.start, period.end, segment.start, segment.end)):
                            raise ReviewError('parent_type_unavailable_or_recursive')
                        item['membership'].extend(intersections(memberships(parent, current_applicable=str(parent['issue_type']['id']) not in subtypes), [period]))
                    except (ReviewError, KeyError, ValueError, TypeError, AttributeError) as error:
                        membership_gap([period], error)
            except (ReviewError, KeyError, ValueError, TypeError, AttributeError) as error:
                membership_gap(child_periods, error)
        prepared[identity_id] = item
    return prepared


def ai_period(window, adoption_date):
    if not adoption_date:
        return 'not_configured'
    if window.availability != 'available':
        return 'unavailable'
    adoption = datetime.combine(datetime.fromisoformat(adoption_date).date(), time.min, ZoneInfo(DISPLAY_TIMEZONE))
    if window.end <= adoption:
        return 'before'
    if window.start >= adoption:
        return 'after'
    return 'transition'


def calculate(source, config):
    prepared = prepare(source, config)
    tasks = set(config['task_type_ids']) | set(config['subtask_type_ids'])
    bugs, bug_finals = set(config['bug_type_ids']), set(config['bug_final_status_ids'])
    selected = set(config['sprint_ids'])
    sprint_map = {str(item['id']): item for item in source['sprints']}
    rows = []
    for sprint_id in sorted(selected, key=lambda value: (sprint_map.get(value, {}).get('startDate') or '9999', value)):
        sprint = sprint_map.get(sprint_id, {'id': sprint_id, 'name': f'Sprint {sprint_id}', 'state': 'unknown'})
        window = sprint_window(sprint, source['collection']['finished_at'])
        metrics = {name: {'value': None, 'known_count': 0, 'tickets': [], 'limitations': []} for name in METRICS}
        row = {'id': sprint_id, 'name': sprint['name'], 'window': window.as_dict(),
               'ai_period': ai_period(window, config.get('ai_adoption_date')), 'metrics': metrics,
               'ratio': {'value': None, 'status': 'unavailable'}, 'reopening_events': 0}
        rows.append(row)
        if window.availability != 'available':
            for metric in metrics.values():
                metric['limitations'].append({'reason': WINDOW_REASONS.get(window.reason, 'Intervalo da sprint indisponível.')})
            continue
        for metric in metrics.values():
            metric['value'] = 0
        if source.get('missing_previous_tickets'):
            for metric in metrics.values():
                metric['limitations'].append({'reason': 'Tickets da base anterior não estão mais visíveis na busca.'})
        if source.get('metadata_changed'):
            for name in ('worked',):
                metrics[name]['limitations'].append({'reason': 'O mapeamento do quadro mudou; revise as regras e busque novamente os metadados.'})
        for item in prepared.values():
            issue = item['issue']
            try:
                created = utc_instant(issue['created'])
                if created >= window.end:
                    continue
            except (ValueError, TypeError):
                created = None
            type_values = {segment.value for segment in item['types']}
            if not type_values:
                type_values = {str(issue['issue_type']['id'])} | {str(event.get(side)) for event in issue.get('issue_type_changes', []) for side in ('from', 'to')}
            is_task, is_bug = bool(type_values & tasks), bool(type_values & bugs)
            reference = {'id': str(issue['id']), 'key': issue['key'],
                         'kind': 'subtask' if issue['issue_type']['subtask'] else 'bug' if is_bug else 'task'}

            def gap(names, reason):
                for name in names:
                    metrics[name]['limitations'].append({'ticket': issue['key'], 'reason': reason})

            def add(name, events=None):
                detail = dict(reference)
                if events:
                    detail['events'] = [{'at': event['at'], 'history_id': event['history_id'], 'from': event['from'], 'to': event['to'],
                                         'from_name': event.get('from_name'), 'to_name': event.get('to_name')} for event in events]
                metrics[name]['tickets'].append(detail)

            if item['gaps'].get('state') or created is None:
                gap((['worked', 'completed', 'reopened'] if is_task else []) + (['bugs_total', 'bugs_new', 'bugs_existing', 'reopened'] if is_bug else []),
                    item['gaps'].get('state', 'Data de criação indisponível.'))
                continue
            task_periods = [segment for segment in item['types'] if segment.value in tasks]
            membership = [segment for segment in item['membership'] if sprint_id in segment.value]
            unknown_membership = item.get('membership_gaps', [])
            if is_task:
                working_periods = intersections(item['working'], task_periods)
                work = intersections(working_periods, membership)
                work_events = [event for event in issue['status_changes']
                               if event['to'] in set(config['work_status_ids']) and window.contains(event['at'])
                               and at(item['types'], utc_instant(event['at'])) in tasks]
                known_work_events = [event for event in work_events if at(membership, utc_instant(event['at'])) is not None]
                known_work = bool(known_work_events) or any(overlaps(segment.start, segment.end, window.start, window.end) for segment in work)
                if known_work:
                    # Uma evidência positiva já determina a contagem unitária.
                    add('worked', known_work_events)
                elif (any(overlaps(segment.start, segment.end, window.start, window.end)
                          for segment in intersections(working_periods, unknown_membership))
                      or any(period.start <= utc_instant(event['at']) < period.end
                             for event in work_events for period in unknown_membership)):
                    gap(('worked',), item['gaps']['membership'])
                first = item['first_completion']
                if item['gaps'].get('completion'):
                    gap(('completed',), item['gaps']['completion'])
                elif first and window.contains(first['at']):
                    if at(membership, utc_instant(first['at'])) is not None:
                        add('completed', [first])
                    elif any(period.start <= utc_instant(first['at']) < period.end for period in unknown_membership):
                        gap(('completed',), item['gaps']['membership'])
                if any(window.contains(event['at']) and at(item['types'], utc_instant(event['at'])) in tasks
                       and any(period.start <= utc_instant(event['at']) < period.end for period in unknown_membership)
                       for event in item['reopenings']):
                    gap(('reopened',), item['gaps']['membership'])
            if is_bug:
                bug_periods = [segment for segment in item['types'] if segment.value in bugs]
                opened = intersections([segment for segment in item['status'] if segment.value not in bug_finals], bug_periods)
                if any(overlaps(segment.start, segment.end, window.start, window.end) for segment in opened):
                    add('bugs_total')
                    add('bugs_new' if window.start <= created < window.end else 'bugs_existing')
            reopened = [event for event in item['reopenings'] if window.contains(event['at']) and
                        (at(item['types'], utc_instant(event['at'])) in bugs or
                         (at(item['types'], utc_instant(event['at'])) in tasks and
                          not any(period.start <= utc_instant(event['at']) < period.end for period in item.get('membership_gaps', [])) and at(membership, utc_instant(event['at'])) is not None))]
            if reopened:
                add('reopened', reopened)
                row['reopening_events'] += len(reopened)
        for metric in metrics.values():
            metric['tickets'] = list({ticket['id']: ticket for ticket in metric['tickets']}.values())
            metric['known_count'] = len(metric['tickets'])
            metric['value'] = None if metric['limitations'] else metric['known_count']
        total, worked = metrics['bugs_total']['value'], metrics['worked']['value']
        row['ratio'] = {'value': total / worked if total is not None and worked else None,
                        'status': 'unavailable' if total is None or worked is None else 'not_calculable' if worked == 0 else 'available'}
        if metrics['bugs_total']['value'] is not None:
            assert metrics['bugs_total']['value'] == metrics['bugs_new']['value'] + metrics['bugs_existing']['value']
    return {'engine_version': ENGINE_VERSION, 'collected_at': source['collection']['finished_at'],
            'ai_adoption_date': config.get('ai_adoption_date'), 'sprints': rows,
            'limitations': source.get('limitations', []), 'display_timezone': DISPLAY_TIMEZONE}


def compare(rows):
    """Médias apenas de sprints encerradas, completas e fora da transição."""
    result = {}
    for group in ('before', 'after', 'transition', 'not_configured', 'unavailable'):
        selected = [row for row in rows if row['ai_period'] == group]
        included = [row for row in selected if row['window']['state'] == 'closed' and row['window']['availability'] == 'available'
                    and all(row['metrics'][name]['value'] is not None for name in METRICS)]
        if group not in ('before', 'after'):
            included = []
        totals = {name: sum(row['metrics'][name]['value'] for row in included) if included else None for name in METRICS}
        result[group] = {'sprint_count': len(selected), 'included_closed_sprints': len(included),
                         'active_sprints': sum(row['window']['state'] == 'active' for row in selected),
                         'excluded_sprints': len(selected) - len(included), 'totals': totals,
                         'averages': {name: total / len(included) if total is not None else None for name, total in totals.items()},
                         'ratio': totals['bugs_total'] / totals['worked'] if totals['worked'] else None}
    return result
