"""Conferência de leitura no Jira; evidências privadas ficam somente no relatório local."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from app.jira_probe import ENV_FILE, JiraReader, ProbeError


from app.jira_fields import hierarchy_changes


def check_live(reader: JiraReader, source: dict, review: dict, *, progress=None, cached: dict | None = None) -> dict:
    reader.get("/rest/api/3/myself")
    project = reader.get(f'/rest/api/3/project/{source["project_key"]}')
    if str(project["id"]) != str(source["project_id"]):
        raise ProbeError("A conexão não corresponde ao projeto da coleta.")
    permission = reader.get("/rest/api/3/mypermissions", projectKey=source["project_key"], permissions="BROWSE_PROJECTS")
    configuration = reader.get(f'/rest/agile/1.0/board/{source["board_id"]}/configuration')
    columns = [{"name": column["name"], "status_ids": [status["id"] for status in column["statuses"]]}
               for column in configuration["columnConfig"]["columns"]]
    issues = {item["key"]: item for item in source["issues"]}
    selected = {example["issue_key"] for case in review["cases"].values() for example in case["examples"]}
    # Todas as subtarefas são verificadas, pois o histórico de vínculo não foi exportado pela coleta inicial.
    selected.update(item["key"] for item in issues.values() if item["issue_type"]["subtask"])
    selected.update(item["parent"]["key"] for item in issues.values()
                    if item["issue_type"]["subtask"] and item.get("parent") and item["parent"].get("key") in issues)
    cached_checks = {item["issue_key"]: item for item in (cached or {}).get("checks", [])}
    by_id = {str(item["id"]): item["key"] for item in issues.values()}
    for item in cached_checks.values():
        if not item["subtask"]:
            continue
        for event in item["parent_changes"]:
            for value in (event["from"], event["to"]):
                if str(value) in by_id:
                    selected.add(by_id[str(value)])
                elif value in issues:
                    selected.add(value)
    ordered = sorted(selected)
    checks = []
    failures = []
    for number, key in enumerate(ordered, 1):
        item = issues[key]
        audit = {}
        try:
            if key in cached_checks:
                checks.append(cached_checks[key])
                if progress:
                    progress(number, len(ordered))
                continue
            events = list(reader.pages(f'/rest/api/3/issue/{item["id"]}/changelog', "values", audit=audit))
            check = {
                "issue_key": key, "issue_id": item["id"],
                "subtask": item["issue_type"]["subtask"], "pagination": audit,
                "history_event_count_matches_source": len(events) == item["historical_events"],
                **hierarchy_changes(events),
            }
            # Confronta os eventos exportados com o endpoint, sem salvar autores ou outros campos.
            event_index = {event["id"]: event for event in events}
            matched = True
            for change in [*item["status_changes"], *item["sprint_changes"]]:
                event = event_index.get(change["history_id"])
                if not event or event["created"] != change["at"]:
                    matched = False
                    break
                if not any(part.get("from") == change["from"] and part.get("to") == change["to"]
                           and (part.get("fieldId") == change["field_id"] if change["field_id"] else part.get("field") == change["field_name"])
                           for part in event["items"]):
                    matched = False
                    break
            check["exported_events_match_live"] = matched
            if key in {example["issue_key"] for case in review["cases"].values() for example in case["examples"]}:
                current = reader.get(f'/rest/api/3/issue/{item["id"]}', fields="project,issuetype,status,parent,updated")
                fields = current["fields"]
                check["current_fields_match_source"] = (
                    str(fields["project"]["id"]) == str(source["project_id"])
                    and fields["issuetype"]["id"] == item["issue_type"]["id"]
                    and fields["status"]["id"] == item["status"]["id"]
                    and (fields.get("parent") or {}).get("id") == (item.get("parent") or {}).get("id")
                )
            checks.append(check)
        except (ProbeError, KeyError, ValueError, TypeError, AttributeError) as error:
            failures.append({"issue_key": key, "error": str(error) if isinstance(error, ProbeError) else "Formato de resposta inesperado."})
            break
        if progress:
            progress(number, len(ordered))
    complete = len(checks) == len(ordered) and not failures
    consistent = all(check["history_event_count_matches_source"] and check["exported_events_match_live"]
                     and check.get("current_fields_match_source", True) for check in checks)
    return {
        "check_version": 2,
        "verified": complete and consistent and columns == source["columns"]
                    and permission["permissions"]["BROWSE_PROJECTS"]["havePermission"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "project_id": source["project_id"], "project_key": source["project_key"],
        "requested": len(ordered), "checks": checks, "failures": failures,
        "complete": complete,
        "browse_projects_allowed": permission["permissions"]["BROWSE_PROJECTS"]["havePermission"],
        "current_columns_match_source": columns == source["columns"],
        "limitation": "Permissão de navegação não comprova acesso a todos os tickets e eventos; configuração atual não reconstrói configurações anteriores.",
    }


def historical_metadata(reader: JiraReader, source: dict) -> dict:
    from app.jira_review import sprint_ids
    known_statuses = {status["id"] for item in source["issue_types"] for status in item["statuses"]}
    known_sprints = {str(item["id"]) for item in source["sprints"]}
    status_ids = {str(event[side]) for issue in source["issues"] for event in issue["status_changes"]
                  for side in ("from", "to") if event[side] is not None} - known_statuses
    sprint_references = set()
    for issue in source["issues"]:
        for event in issue["sprint_changes"]:
            sprint_references.update(sprint_ids(event["from"]) | sprint_ids(event["to"]))
    result = {"statuses": [], "sprints": []}
    for kind, identifiers in (("statuses", status_ids), ("sprints", sprint_references - known_sprints)):
        for identifier in sorted(identifiers):
            path = f"/rest/api/3/status/{identifier}" if kind == "statuses" else f"/rest/agile/1.0/sprint/{identifier}"
            try:
                response = reader.get(path)
                if str(response.get("id")) != identifier:
                    raise ProbeError("Metadado retornado não corresponde ao identificador solicitado.")
                keys = ("id", "name", "statusCategory") if kind == "statuses" else ("id", "name", "state", "startDate", "endDate", "completeDate", "originBoardId")
                result[kind].append({"requested_id": identifier, "available": True,
                                     "metadata": {key: response.get(key) for key in keys}})
            except (ProbeError, KeyError, ValueError, TypeError, AttributeError) as error:
                result[kind].append({"requested_id": identifier, "available": False,
                                     "error": str(error) if isinstance(error, ProbeError) else "Formato de metadados inesperado."})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".local/jira-history-check.json"))
    parser.add_argument("--project", type=int, choices=(1, 2), default=1)
    parser.add_argument("--historical-metadata", action="store_true",
                        help="Verificar metadados de status/sprints referenciados que não estão na configuração atual.")
    parser.add_argument("--resume-from", type=Path,
                        help="Reusar conferências da mesma coleta, preservando sua data de origem.")
    args = parser.parse_args()
    try:
        if args.output.resolve() in (args.input.resolve(), args.review.resolve()):
            raise ProbeError("Use um arquivo de saída separado das evidências de origem.")
        raw = args.input.read_bytes()
        report = json.loads(raw)
        review = json.loads(args.review.read_bytes())
        connection = next(item for item in report["connections"] if item["connection"] == args.project)
        if not connection["collection"]["complete"] or review["source_sha256"] != hashlib.sha256(raw).hexdigest():
            raise ProbeError("A coleta está incompleta ou não corresponde à conferência.")
        if review["project_id"] != connection["project_id"]:
            raise ProbeError("As evidências pertencem a projetos diferentes.")
        load_dotenv(ENV_FILE, override=False, interpolate=False)
        prefix = f"JIRA_PROBE_{args.project}_"
        values = [os.environ.get(prefix + field, "") for field in ("URL", "EMAIL", "TOKEN")]
        if not all(values):
            raise ProbeError("Preencha URL, EMAIL e TOKEN da conexão no ambiente local.")
        cached = None
        if args.resume_from:
            cached = json.loads(args.resume_from.read_bytes())
            if (cached.get("check_version") != 2 or not cached.get("verified")
                    or cached.get("source_sha256") != hashlib.sha256(raw).hexdigest()
                    or cached.get("project_id") != connection["project_id"]):
                raise ProbeError("A conferência anterior não é válida para esta coleta.")
        reader = JiraReader(*values)
        def progress(done, total):
            if done == 1 or done % 20 == 0 or done == total:
                print(f"Históricos conferidos: {done}/{total}.", flush=True)
        result = check_live(reader, connection, review, progress=progress, cached=cached)
        if cached:
            result["reused_checks_checked_at"] = cached["checked_at"]
        if args.historical_metadata:
            result["historical_metadata"] = historical_metadata(reader, connection)
        result["source_sha256"] = hashlib.sha256(raw).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (ProbeError, OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as error:
        print(str(error) if isinstance(error, ProbeError) else "Não foi possível conferir as evidências locais e o acesso ao Jira.", file=sys.stderr)
        return 1
    print(json.dumps({
        "checks_completed": len(result["checks"]), "complete": result["complete"], "verified": result["verified"],
        "failures": len(result["failures"]),
        "exported_event_mismatches": sum(not check["exported_events_match_live"] for check in result["checks"]),
        "parent_change_events": sum(len(check["parent_changes"]) for check in result["checks"]),
        "type_change_events": sum(len(check["issue_type_changes"]) for check in result["checks"]),
        "historical_metadata_summary": {
            kind: {"queried": len(values), "readable": sum(item["available"] for item in values)}
            for kind, values in result.get("historical_metadata", {}).items()
        },
    }, indent=2))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
