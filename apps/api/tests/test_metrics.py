import copy
import unittest

from app.metrics.engine import calculate, compare


def instant(day):
    return f'2026-01-{day:02d}T00:00:00+00:00'


def events(entries):
    return [{'history_id': str(index), 'at': instant(day), 'from': before, 'to': after}
            for index, (day, before, after) in enumerate(entries)]


def ticket(identity, kind='3', *, changes=(), current=None, sprints=('1', '2'), parent=None, created='2025-12-20T00:00:00+00:00'):
    return {'id': str(identity), 'key': f'TEST-{identity}', 'created': created, 'updated': instant(21),
            'issue_type': {'id': kind, 'name': kind, 'subtask': kind == '5'},
            'status': {'id': current or (changes[-1][2] if changes else '0')},
            'status_changes': events(changes), 'sprint_changes': [], 'issue_type_changes': [], 'parent_changes': [],
            'unrecognized_parent_fields': [], 'parent': {'id': str(parent), 'key': f'TEST-{parent}'} if parent else None,
            'sprint_memberships': [{'field_id': 'customfield_1', 'available': True,
                                    'value': [{'id': value} for value in sprints]}]}


def fixture(issues):
    source = {'project_id': '10', 'project_key': 'TEST', 'board_id': 10, 'issues': issues,
              'issue_types': [{'id': identity, 'subtask': identity == '5'} for identity in ('3', '5', '9', '20', '21')],
              'sprint_fields': [{'id': 'customfield_1', 'name': 'Sprint'}],
              'sprints': [{'id': '1', 'name': 'Primeira', 'state': 'closed', 'startDate': instant(1), 'completeDate': instant(10)},
                          {'id': '2', 'name': 'Segunda', 'state': 'closed', 'startDate': instant(10), 'completeDate': instant(20)}],
              'collection': {'finished_at': instant(25), 'complete': True}, 'limitations': []}
    config = {'board_id': 10, 'task_type_ids': ['3'], 'subtask_type_ids': ['5'], 'bug_type_ids': ['9'],
              'work_status_ids': ['1'], 'task_final_status_ids': ['2', '7'], 'bug_final_status_ids': ['4'],
              'sprint_ids': ['1', '2'], 'ai_adoption_date': None}
    return source, config


def value(result, metric, sprint=0):
    return result['sprints'][sprint]['metrics'][metric]['value']


class MetricTests(unittest.TestCase):
    def calculate(self, issues):
        return calculate(*fixture(issues))

    def test_carried_work_counts_once_per_sprint_until_final(self):
        result = self.calculate([ticket(1, changes=[(2, '0', '1'), (15, '1', '2')])])
        self.assertEqual([value(result, 'worked', n) for n in (0, 1)], [1, 1])
        self.assertEqual([value(result, 'completed', n) for n in (0, 1)], [0, 1])

    def test_removal_counts_prior_work_and_no_automatic_next_sprint(self):
        issue = ticket(1, changes=[(2, '0', '1')], sprints=())
        issue['sprint_changes'] = events([(5, '1', None)])
        result = self.calculate([issue])
        self.assertEqual([value(result, 'worked', n) for n in (0, 1)], [1, 0])

    def test_reopen_and_final_to_final_never_duplicate_first_completion(self):
        result = self.calculate([ticket(1, changes=[(2, '0', '1'), (4, '1', '2'), (5, '2', '7'), (11, '7', '1'), (15, '1', '2')])])
        self.assertEqual([value(result, 'completed', n) for n in (0, 1)], [1, 0])
        self.assertEqual([value(result, 'worked', n) for n in (0, 1)], [1, 1])
        self.assertEqual(value(result, 'reopened', 1), 1)
        self.assertEqual(result['sprints'][1]['reopening_events'], 1)

    def test_reopening_to_backlog_does_not_inherit_previous_work(self):
        result = self.calculate([ticket(1, changes=[(2, '0', '1'), (4, '1', '2'), (11, '2', '0')])])
        self.assertEqual(value(result, 'worked', 1), 0)
        self.assertEqual(value(result, 'reopened', 1), 1)

    def test_work_moved_to_another_nonfinal_status_remains_started(self):
        result = self.calculate([ticket(1, changes=[(2, '0', '1'), (4, '1', '6')])])
        self.assertEqual(value(result, 'worked', 1), 1)

    def test_parent_and_subtask_each_count_one_with_own_status(self):
        parent = ticket(1, changes=[(2, '0', '1')])
        child = ticket(2, '5', parent=1, changes=[(3, '0', '1')], sprints=(), created=instant(3))
        ignored_child = ticket(3, '5', parent=1, sprints=(), created=instant(3))
        result = self.calculate([parent, child, ignored_child])
        self.assertEqual(value(result, 'worked'), 2)
        self.assertEqual(value(result, 'worked', 1), 2)

    def test_subtask_creation_prevents_backdating_and_historical_parent_is_used(self):
        first_parent = ticket(1, sprints=('1',))
        second_parent = ticket(2, sprints=('2',))
        child = ticket(3, '5', parent=2, changes=[(12, '0', '1')], created=instant(11), sprints=())
        child['parent_changes'] = events([(13, '1', '2')])
        result = self.calculate([first_parent, second_parent, child])
        self.assertEqual(value(result, 'worked'), 0)
        self.assertEqual(value(result, 'worked', 1), 1)

    def test_converted_former_subtask_uses_historical_membership(self):
        parent = ticket(1, sprints=('1',))
        child = ticket(2, '3', changes=[(2, '0', '1')], sprints=('2',))
        child['issue_type_changes'] = events([(11, '5', '3')])
        child['parent_changes'] = events([(11, '1', None)])
        result = self.calculate([parent, child])
        self.assertEqual([value(result, 'worked', n) for n in (0, 1)], [1, 1])

    def test_conversion_to_subtask_does_not_validate_old_own_sprint_against_inherited_current_value(self):
        parent = ticket(1, sprints=('2',))
        child = ticket(2, '5', parent=1, changes=[(2, '0', '1')], sprints=('2',))
        child['issue_type_changes'] = events([(11, '3', '5')])
        child['parent_changes'] = events([(11, None, '1')])
        child['sprint_changes'] = events([(1, None, '1')])
        result = self.calculate([parent, child])
        self.assertEqual([value(result, 'worked', n) for n in (0, 1)], [1, 1])

    def test_conversion_without_own_sprint_history_preserves_unknown_past(self):
        parent = ticket(1, sprints=('2',))
        child = ticket(2, '5', parent=1, changes=[(2, '0', '1')], sprints=('2',))
        child['issue_type_changes'] = events([(11, '3', '5')])
        child['parent_changes'] = events([(11, None, '1')])
        self.assertIsNone(value(self.calculate([parent, child]), 'worked'))

    def test_unknown_membership_before_sprints_does_not_hide_later_verified_participation(self):
        parent = ticket(1, sprints=('2',))
        child = ticket(2, '5', parent=1, changes=[(2, '0', '1')], sprints=('2',))
        child['issue_type_changes'] = [{'history_id': 'type', 'at': '2025-12-21T00:00:00Z', 'from': '3', 'to': '5'}]
        child['parent_changes'] = [{'history_id': 'parent', 'at': '2025-12-21T00:00:00Z', 'from': None, 'to': '1'}]
        result = self.calculate([parent, child])
        self.assertEqual(value(result, 'worked'), 0)
        self.assertEqual(value(result, 'worked', 1), 1)

    def test_membership_gap_without_eligible_activity_does_not_invalidate_metrics(self):
        parent = ticket(1, sprints=('1', '2'))
        child = ticket(2, '5', parent=1, sprints=('1', '2'))
        child['issue_type_changes'] = events([(6, '3', '5')])
        child['parent_changes'] = events([(6, None, '1')])
        result = self.calculate([parent, child])
        self.assertEqual(value(result, 'worked'), 0)
        self.assertEqual(value(result, 'completed'), 0)
        self.assertEqual(value(result, 'reopened'), 0)

    def test_activity_after_conversion_is_known_even_when_same_sprint_has_membership_gap(self):
        parent = ticket(1, sprints=('1', '2'))
        child = ticket(2, '5', parent=1, sprints=('1', '2'), changes=[(7, '0', '1'), (8, '1', '2')])
        child['issue_type_changes'] = events([(6, '3', '5')])
        child['parent_changes'] = events([(6, None, '1')])
        result = self.calculate([parent, child])
        self.assertEqual(value(result, 'worked'), 1)
        self.assertEqual(value(result, 'completed'), 1)
        self.assertEqual(value(result, 'reopened'), 0)

    def test_eligible_activity_inside_membership_gap_remains_unavailable(self):
        parent = ticket(1, sprints=('1', '2'))
        child = ticket(2, '5', parent=1, sprints=('1', '2'), changes=[(2, '0', '1'), (4, '1', '2'), (5, '2', '0')])
        child['issue_type_changes'] = events([(6, '3', '5')])
        child['parent_changes'] = events([(6, None, '1')])
        result = self.calculate([parent, child])
        self.assertIsNone(value(result, 'worked'))
        self.assertIsNone(value(result, 'completed'))
        self.assertIsNone(value(result, 'reopened'))
        self.assertEqual(value(result, 'worked', 1), 0)

    def test_project_bugs_without_membership_created_resolved_or_reopened(self):
        old = ticket(1, '9', changes=[(2, '0', '4')], sprints=())
        new = ticket(2, '9', changes=[(4, '0', '4')], created=instant(3), sprints=())
        reopened = ticket(3, '9', changes=[(1, '0', '4'), (12, '4', '0'), (13, '0', '4')], sprints=())
        result = self.calculate([old, new, reopened])
        self.assertEqual(value(result, 'bugs_total'), 2)
        self.assertEqual(value(result, 'bugs_new'), 1)
        self.assertEqual(value(result, 'bugs_existing'), 1)
        self.assertEqual(value(result, 'bugs_total', 1), 1)
        self.assertEqual(value(result, 'bugs_existing', 1), 1)
        self.assertEqual(value(result, 'reopened', 1), 1)

    def test_half_open_boundaries_include_start_exclude_end(self):
        task = ticket(1, changes=[(1, '0', '1'), (10, '1', '2')])
        bug = ticket(2, '9', created=instant(10), sprints=())
        result = self.calculate([task, bug])
        self.assertEqual(value(result, 'completed'), 0)
        self.assertEqual(value(result, 'completed', 1), 1)
        self.assertEqual(value(result, 'bugs_total'), 0)
        self.assertEqual(value(result, 'bugs_new', 1), 1)

    def test_zero_duration_work_transition_is_still_observed_work(self):
        result = self.calculate([ticket(1, changes=[(2, '0', '1'), (2, '1', '2')])])
        self.assertEqual(value(result, 'worked'), 1)
        self.assertEqual(value(result, 'completed'), 1)

    def test_zero_denominator_and_empty_project(self):
        result = self.calculate([])
        self.assertEqual(value(result, 'worked'), 0)
        self.assertEqual(result['sprints'][0]['ratio']['status'], 'not_calculable')
        self.assertIsNone(result['sprints'][0]['ratio']['value'])

    def test_stories_epics_excluded_and_ratio_is_bugs_divided_by_work(self):
        result = self.calculate([ticket(1, '20', changes=[(2, '0', '1')]), ticket(2, '21', changes=[(2, '0', '1')]),
                                 ticket(3, changes=[(2, '0', '1')]), ticket(4, '9')])
        self.assertEqual(value(result, 'worked'), 1)
        self.assertEqual(result['sprints'][0]['ratio']['value'], 1)

    def test_missing_history_is_unavailable_and_exposes_known_evidence(self):
        valid = ticket(1, changes=[(2, '0', '1')])
        invalid = ticket(2, changes=[(2, '0', '1'), (3, '6', '2')])
        result = self.calculate([valid, invalid])
        self.assertIsNone(value(result, 'worked'))
        self.assertEqual(result['sprints'][0]['metrics']['worked']['known_count'], 1)
        self.assertTrue(result['sprints'][0]['metrics']['worked']['limitations'])
        self.assertEqual(result['sprints'][0]['ratio']['status'], 'unavailable')

    def test_absent_parent_does_not_become_zero(self):
        result = self.calculate([ticket(1, '5', parent=999, changes=[(2, '0', '1')])])
        self.assertIsNone(value(result, 'worked'))

    def test_initial_final_status_has_unknown_first_completion(self):
        result = self.calculate([ticket(1, current='2')])
        self.assertIsNone(value(result, 'completed'))
        self.assertEqual(value(result, 'worked'), 0)

    def test_future_missing_dates_active_and_overlapping_sprints(self):
        source, config = fixture([ticket(1, changes=[(2, '0', '1')])])
        source['sprints'][1].update(state='active', startDate=instant(5))
        result = calculate(source, config)
        self.assertTrue(result['sprints'][1]['window']['partial'])
        self.assertEqual(value(result, 'worked', 1), 1)
        source['sprints'][1]['state'] = 'future'
        result = calculate(source, config)
        self.assertIsNone(value(result, 'worked', 1))
        source['sprints'][0]['completeDate'] = None
        self.assertIsNone(value(calculate(source, config), 'worked'))

    def test_ai_groups_use_sao_paulo_midnight_and_exclude_transition_active_from_averages(self):
        source, config = fixture([])
        config['ai_adoption_date'] = '2026-01-10'
        result = calculate(source, config)
        self.assertEqual([row['ai_period'] for row in result['sprints']], ['before', 'transition'])
        comparison = compare(result['sprints'])
        self.assertEqual(comparison['before']['included_closed_sprints'], 1)
        self.assertIsNone(comparison['after']['averages']['worked'])
        self.assertEqual(comparison['transition']['included_closed_sprints'], 0)
        config['ai_adoption_date'] = '2026-01-01'
        source['sprints'][1]['state'] = 'active'
        comparison = compare(calculate(source, config)['sprints'])
        self.assertEqual(comparison['after']['active_sprints'], 1)
        self.assertEqual(comparison['after']['included_closed_sprints'], 0)

    def test_visibility_and_metadata_gaps_are_explicit(self):
        source, config = fixture([])
        source['missing_previous_tickets'] = 1
        self.assertIsNone(value(calculate(source, config), 'bugs_total'))
        source['missing_previous_tickets'] = 0
        source['metadata_changed'] = True
        self.assertIsNone(value(calculate(source, config), 'worked'))


if __name__ == '__main__':
    unittest.main()
