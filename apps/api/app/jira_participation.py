"""Evidência técnica de participação de subtarefas; não calcula indicadores."""

from dataclasses import dataclass
from datetime import datetime

from app.jira_review import ReviewError, current_sprints, sprint_ids
from app.jira_time import sprint_window, utc_instant


@dataclass(frozen=True)
class Segment:
    start: datetime
    end: datetime
    value: object


def history_segments(changes: list[dict], current, created: str, cutoff: str, decode=lambda value: value) -> list[Segment]:
    start, end = utc_instant(created), utc_instant(cutoff)
    if start >= end:
        raise ReviewError("invalid_issue_lifetime")
    ordered = sorted(changes, key=lambda event: utc_instant(event["at"]))
    value = decode(ordered[0]["from"]) if ordered else current
    result = []
    for event in ordered:
        at = utc_instant(event["at"])
        if at < start or at > end or decode(event["from"]) != value:
            raise ReviewError("discontinuous_or_out_of_bounds_history")
        if at > start:
            result.append(Segment(start, at, value))
        start, value = at, decode(event["to"])
    if value != current:
        raise ReviewError("current_value_differs_from_history")
    if start < end:
        result.append(Segment(start, end, value))
    return result


def subtask_participation(source: dict, checks: dict) -> list[dict]:
    by_id = {str(issue["id"]): issue for issue in source["issues"]}
    by_key = {issue["key"]: issue for issue in source["issues"]}
    types = {item["id"]: item for item in source["issue_types"]}
    cutoff = source["collection"]["finished_at"]
    windows = {str(sprint["id"]): sprint_window(sprint, cutoff) for sprint in source["sprints"]}
    evidence = {item["issue_key"]: item for item in checks["checks"]}

    def parent_id(value):
        if not value:
            return None
        if str(value) in by_id:
            return str(value)
        if value in by_key:
            return str(by_key[value]["id"])
        return str(value)

    result = []
    for child in source["issues"]:
        if not child["issue_type"]["subtask"]:
            continue
        item = {"issue_key": child["key"], "segments": [], "gaps": [], "explicit_no_parent_segments": [],
                "basis": "documented_parent_behavior_and_historical_links",
                "evidence_only": True}
        try:
            check = evidence[child["key"]]
            if not child.get("parent") and not check["parent_changes"]:
                raise ReviewError("current_parent_unavailable")
            if check["unrecognized_parent_fields"]:
                raise ReviewError("unrecognized_parent_fields")
            if len(source["sprint_fields"]) != 1:
                raise ReviewError("ambiguous_sprint_field")
            parents = history_segments(check["parent_changes"], parent_id((child.get("parent") or {}).get("id")),
                                       child["created"], cutoff, parent_id)
            child_types = history_segments(check["issue_type_changes"], child["issue_type"]["id"], child["created"], cutoff)
            for parent_segment in parents:
                for type_segment in child_types:
                    begin, end = max(parent_segment.start, type_segment.start), min(parent_segment.end, type_segment.end)
                    if begin >= end:
                        continue
                    if type_segment.value not in types:
                        item["gaps"].append("historical_issue_type_unavailable")
                        continue
                    if not types[type_segment.value]["subtask"]:
                        continue
                    if parent_segment.value is None:
                        item["explicit_no_parent_segments"].append({"start_utc": begin.isoformat(), "end_utc": end.isoformat(),
                                                                  "basis": "explicit_null_in_parent_history"})
                        continue
                    parent = by_id.get(parent_segment.value)
                    if parent is None:
                        item["gaps"].append("historical_parent_unavailable")
                        continue
                    if begin < utc_instant(parent["created"]):
                        item["gaps"].append("association_precedes_parent_creation")
                        continue
                    parent_check = evidence.get(parent["key"])
                    if not parent_check or parent_check["unrecognized_parent_fields"]:
                        item["gaps"].append("parent_hierarchy_history_unavailable")
                        continue
                    parent_types = history_segments(parent_check["issue_type_changes"], parent["issue_type"]["id"], parent["created"], cutoff)
                    if any(segment.start < end and begin < segment.end and
                           (segment.value not in types or types[segment.value]["subtask"]) for segment in parent_types):
                        item["gaps"].append("parent_requires_recursive_hierarchy")
                        continue
                    current, available = current_sprints(parent)
                    if not available:
                        item["gaps"].append("parent_sprint_field_unavailable")
                        continue
                    memberships = history_segments(parent["sprint_changes"], current, parent["created"], cutoff, sprint_ids)
                    for membership in memberships:
                        left, right = max(begin, membership.start), min(end, membership.end)
                        if left >= right:
                            continue
                        for sprint_id in membership.value:
                            window = windows.get(sprint_id)
                            if window is None:
                                item["gaps"].append("historical_sprint_metadata_unavailable")
                                continue
                            if window.availability == "not_started":
                                continue
                            if window.availability != "available":
                                item["gaps"].append("sprint_interval_unavailable")
                                continue
                            lower, upper = max(left, window.start), min(right, window.end)
                            if lower < upper:
                                item["segments"].append({"sprint_id": sprint_id, "parent_id": parent["id"],
                                                         "start_utc": lower.isoformat(), "end_utc": upper.isoformat()})
        except (ReviewError, KeyError, ValueError, TypeError, AttributeError) as error:
            item["gaps"].append(str(error) if isinstance(error, ReviewError) else "unsupported_history_format")
        item["gaps"] = sorted(set(item["gaps"]))
        item["availability"] = "partial" if item["gaps"] and item["segments"] else "unavailable" if item["gaps"] else "available"
        result.append(item)
    return result
