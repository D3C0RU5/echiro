import unittest

from app.jira_time import display_instant, sprint_window


class JiraTimeTests(unittest.TestCase):
    def sprint(self, state='closed'):
        return {'state': state, 'startDate': '2026-11-01T09:00:00-03:00',
                'endDate': '2026-11-10T12:00:00Z', 'completeDate': '2026-11-11T12:00:00Z'}

    def test_actual_completion_and_half_open_bounds(self):
        window = sprint_window(self.sprint(), '2026-11-23T12:00:00Z')
        self.assertTrue(window.contains('2026-11-01T12:00:00Z'))
        self.assertTrue(window.contains('2026-11-10T18:00:00Z'))
        self.assertFalse(window.contains('2026-11-11T12:00:00Z'))
        self.assertEqual(window.start.isoformat(), '2026-11-01T12:00:00+00:00')

    def test_overdue_active_sprint_extends_to_fixed_collection_cutoff(self):
        window = sprint_window(self.sprint('active'), '2026-11-23T12:00:00Z')
        self.assertTrue(window.contains('2026-11-22T12:00:00Z'))
        self.assertFalse(window.contains('2026-11-23T12:00:00Z'))
        self.assertTrue(window.as_dict()['partial'])

    def test_missing_actual_completion_does_not_fall_back_to_planned_end(self):
        sprint = self.sprint()
        del sprint['completeDate']
        window = sprint_window(sprint, '2026-11-23T12:00:00Z')
        self.assertEqual(window.reason, 'missing_complete_date')
        self.assertIsNone(window.contains('2026-11-02T12:00:00Z'))

    def test_future_sprint_is_not_zero_activity(self):
        window = sprint_window(self.sprint('future'), '2026-11-23T12:00:00Z')
        self.assertEqual(window.availability, 'not_started')
        self.assertIsNone(window.start)
        self.assertIsNone(window.contains('2026-11-02T12:00:00Z'))

    def test_invalid_dates_and_intervals_are_explicitly_unavailable(self):
        for change in ({'startDate': None}, {'startDate': '2026-11-01T12:00:00'},
                       {'completeDate': '2026-11-24T12:00:00Z'},
                       {'completeDate': '2026-11-01T12:00:00Z'}, {'state': 'unknown'}):
            sprint = self.sprint()
            sprint.update(change)
            with self.subTest(change=change):
                self.assertEqual(sprint_window(sprint, '2026-11-23T12:00:00Z').availability, 'unavailable')

    def test_overlapping_sprints_keep_their_own_intervals(self):
        first = sprint_window(self.sprint(), '2026-11-23T12:00:00Z')
        second = self.sprint()
        second['startDate'] = '2026-11-10T12:00:00Z'
        other = sprint_window(second, '2026-11-23T12:00:00Z')
        self.assertTrue(first.contains('2026-11-10T18:00:00Z'))
        self.assertTrue(other.contains('2026-11-10T18:00:00Z'))

    def test_display_timezone_preserves_the_instant(self):
        self.assertEqual(display_instant('2026-11-23T15:00:00Z'), '2026-11-23T12:00:00-03:00')


if __name__ == '__main__':
    unittest.main()
