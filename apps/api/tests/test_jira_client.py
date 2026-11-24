import io
import json
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

from app.integrations.client import JiraReader, NoRedirect, ProbeError


class JiraClientTests(unittest.TestCase):
    def reader(self):
        return JiraReader("https://example.atlassian.net", "user@example.com", "secret-token")

    def test_transport_uses_get_and_does_not_follow_redirects(self):
        reader = self.reader()
        response = Mock()
        response.__enter__ = Mock(return_value=io.StringIO('{"id": "1"}'))
        response.__exit__ = Mock(return_value=False)
        reader._opener.open = Mock(return_value=response)
        self.assertEqual(reader.get("/rest/api/3/myself"), {"id": "1"})
        request = reader._opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.get_header("Authorization").startswith("Basic "))
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))

    def test_invalid_destinations_are_rejected(self):
        for url in ("http://example.atlassian.net", "https://evil.test", "https://a.atlassian.net.evil.test",
                    "https://user:password@example.atlassian.net", "https://example.atlassian.net/path"):
            with self.subTest(url=url), self.assertRaises(ProbeError):
                JiraReader(url, "user", "token")

    def test_http_errors_do_not_expose_remote_body_or_credentials(self):
        for code in (301, 401, 403, 404, 429, 500):
            reader = self.reader()
            reader._opener.open = Mock(side_effect=HTTPError(
                "https://example.atlassian.net", code, "secret-token", {}, io.BytesIO(b"secret-token")
            ))
            with self.subTest(code=code), self.assertRaises(ProbeError) as caught:
                reader.get("/rest/api/3/myself")
            self.assertNotIn("secret-token", str(caught.exception))

    def test_pagination_reads_all_pages_using_actual_page_size(self):
        reader = self.reader()
        reader.get = Mock(side_effect=[
            {"startAt": 0, "total": 3, "values": [1, 2]},
            {"startAt": 2, "total": 3, "values": [3]},
        ])
        self.assertEqual(list(reader.pages("/rest/api/3/sample", "values")), [1, 2, 3])
        self.assertEqual(reader.get.call_args.kwargs["startAt"], 2)

    def test_pagination_rejects_missing_or_nonadvancing_pages(self):
        for page in ({"values": [], "total": 2}, {"values": [1]}, {"values": [1], "startAt": 8}):
            reader = self.reader()
            reader.get = Mock(return_value=page)
            with self.subTest(page=page), self.assertRaises(ProbeError):
                list(reader.pages("/rest/api/3/sample", "values"))

    def test_cursor_pagination_reads_last_page_and_records_evidence_without_cursor(self):
        reader = self.reader()
        reader.get = Mock(side_effect=[
            {"issues": [{"id": "1"}, {"id": "2"}], "isLast": False, "nextPageToken": "private-cursor"},
            {"issues": [{"id": "3"}], "isLast": True},
        ])
        audit = {}
        issues = list(reader.search_issues('project = "ABC"', "status", page_size=2, audit=audit))
        self.assertEqual([issue["id"] for issue in issues], ["1", "2", "3"])
        self.assertEqual(reader.get.call_args.kwargs["nextPageToken"], "private-cursor")
        self.assertNotIn("nextPageToken", reader.get.call_args_list[0].kwargs)
        self.assertEqual(audit, {"page_count": 2, "items_read": 3, "complete": True})
        self.assertNotIn("private-cursor", json.dumps(audit))

    def test_cursor_pagination_rejects_missing_markers_empty_pages_and_warnings(self):
        for page in (
            {"issues": [], "isLast": False, "nextPageToken": "next"},
            {"issues": [{"id": "1"}], "isLast": False},
            {"issues": [{"id": "1"}]},
            {"issues": [{"id": "1"}], "isLast": True, "warningMessages": ["private-warning"]},
        ):
            reader = self.reader()
            reader.get = Mock(return_value=page)
            audit = {}
            with self.subTest(page=page), self.assertRaises(ProbeError):
                list(reader.search_issues("project = ABC", "status", audit=audit))
            self.assertFalse(audit["complete"])

    def test_cursor_pagination_detects_cycles_and_duplicate_issues(self):
        for second in (
            {"issues": [{"id": "2"}], "isLast": False, "nextPageToken": "repeated"},
            {"issues": [{"id": "1"}], "isLast": True},
        ):
            reader = self.reader()
            reader.get = Mock(side_effect=[
                {"issues": [{"id": "1"}], "isLast": False, "nextPageToken": "repeated"}, second,
            ])
            audit = {}
            with self.subTest(second=second), self.assertRaises(ProbeError):
                list(reader.search_issues("project = ABC", "status", audit=audit))
            self.assertFalse(audit["complete"])
            self.assertEqual(audit["items_read"], 1)

    def test_offset_pagination_rejects_changed_totals_duplicates_and_early_last_page(self):
        for second in (
            {"startAt": 1, "total": 3, "values": [{"id": "2"}]},
            {"startAt": 1, "total": 2, "values": [{"id": "1"}]},
            {"startAt": 1, "total": 2, "values": [], "isLast": True},
        ):
            reader = self.reader()
            reader.get = Mock(side_effect=[{"startAt": 0, "total": 2, "values": [{"id": "1"}]}, second])
            audit = {}
            with self.subTest(second=second), self.assertRaises(ProbeError):
                list(reader.pages("/rest/api/3/sample", "values", page_size=1, audit=audit))
            self.assertFalse(audit["complete"])

    def test_empty_final_page_is_a_completed_read(self):
        reader = self.reader()
        reader.get = Mock(return_value={"issues": [], "isLast": True})
        audit = {}
        self.assertEqual(list(reader.search_issues("project = ABC", "status", audit=audit)), [])
        self.assertTrue(audit["complete"])
        reader.get = Mock(return_value={"startAt": 0, "total": 0, "values": []})
        audit = {}
        self.assertEqual(list(reader.pages("/rest/api/3/sample", "values", audit=audit)), [])
        self.assertTrue(audit["complete"])
