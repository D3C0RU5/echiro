import json
import unittest

from app.jira_fields import hierarchy_changes
from app.jira_participation import history_segments
from app.jira_review import ReviewError, sprint_ids


class JiraHistoryTests(unittest.TestCase):
    def events(self):
        return [{'id': '1', 'created': '2026-11-01T12:00:00Z', 'author': 'private-author', 'items': [
            {'fieldId': 'parent', 'field': 'Parent', 'from': '8', 'to': '9'},
            {'fieldId': 'issuetype', 'field': 'Issue Type', 'from': 'task', 'to': 'subtask'},
            {'fieldId': 'description', 'field': 'description', 'fromString': 'private-description'},
            {'fieldId': 'customfield_10', 'field': 'Parent Link', 'from': 'a', 'to': 'b'},
        ]}]


    def test_hierarchy_export_excludes_unrelated_content(self):
        result = hierarchy_changes(self.events())
        self.assertEqual(result['parent_changes'][0]['to'], '9')
        self.assertEqual(result['issue_type_changes'][0]['to'], 'subtask')
        self.assertEqual(len(result['unrecognized_parent_fields']), 1)
        self.assertNotIn('private-', json.dumps(result))


    def test_documented_parent_association_and_legacy_duplicate_are_supported(self):
        events = self.events()
        events[0]['items'].append({'field': 'IssueParentAssociation', 'from': '8', 'to': '9'})
        result = hierarchy_changes(events)
        self.assertEqual(len(result['parent_changes']), 1)
        self.assertEqual(len(result['unrecognized_parent_fields']), 1)
        only_modern = [{'id': '2', 'created': '2026-11-01T12:00:00Z',
                        'items': [{'field': 'IssueParentAssociation', 'from': None, 'to': '9'}]}]
        self.assertEqual(hierarchy_changes(only_modern)['parent_changes'][0]['to'], '9')


    def test_history_discontinuity_is_rejected(self):
        with self.assertRaises(ReviewError):
            history_segments([{'at': '2026-11-08T12:00:00Z', 'from': 'a', 'to': 'b'}],
                             'c', '2026-11-01T12:00:00Z', '2026-11-23T12:00:00Z')


    def test_legacy_sprint_names_are_not_guessed_as_identifiers(self):
        self.assertEqual(sprint_ids(None), set())
        self.assertEqual(sprint_ids(' 1, 2 '), {'1', '2'})
        with self.assertRaises(ReviewError):
            sprint_ids('Sprint 1, Sprint 2')

