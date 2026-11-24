"""Projeção dos campos de hierarquia documentados pelo Jira Cloud."""


PARENT_FIELDS = {"parent", "parent issue", "parent association", "issueparentassociation"}
TYPE_FIELDS = {"issuetype", "issue type"}


def hierarchy_changes(events: list[dict]) -> dict:
    result = {"parent_changes": [], "issue_type_changes": [], "unrecognized_parent_fields": []}
    seen = set()
    for event in events:
        for item in event["items"]:
            field_id, name = item.get("fieldId"), str(item.get("field", "")).casefold()
            is_parent = field_id in ("parent", "IssueParentAssociation") or (not field_id and name in PARENT_FIELDS)
            is_type = field_id == "issuetype" or (not field_id and name in TYPE_FIELDS)
            if is_parent or is_type:
                identity = (event["id"], "parent" if is_parent else "type", item.get("from"), item.get("to"))
                if identity in seen:
                    continue
                seen.add(identity)
                result["parent_changes" if is_parent else "issue_type_changes"].append({
                    "history_id": event["id"], "at": event["created"],
                    "from": item.get("from"), "to": item.get("to"),
                })
            elif "parent" in name or "parent" in str(field_id).casefold():
                result["unrecognized_parent_fields"].append({
                    "history_id": event["id"], "field_id": field_id, "field_name": item.get("field"),
                    "from": item.get("from"), "to": item.get("to"),
                })
    return result

