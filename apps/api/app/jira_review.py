"""Conferência local de evidências da fase 1; não calcula indicadores."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from app.jira_time import DISPLAY_TIMEZONE, POLICY_VERSION, sprint_window


class ReviewError(Exception):
    """Erro seguro de configuração ou de formato do relatório local."""


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ReviewError("Datas sem fuso impedem a conferência temporal.")
    return result


def sprint_ids(value) -> set[str]:
    if value is None or value == "":
        return set()
    if not isinstance(value, str) or not re.fullmatch(r"\s*[0-9]+(?:\s*,\s*[0-9]+)*\s*", value):
        raise ReviewError("Formato de IDs de sprint não reconhecido.")
    return {part.strip() for part in value.split(",")}


def current_sprints(issue: dict) -> tuple[set[str], bool]:
    result = set()
    available = False
    for field in issue["sprint_memberships"]:
        if not field["available"]:
            continue
        available = True
        for value in field["value"] or []:
            if not isinstance(value, dict) or not re.fullmatch(r"[0-9]+", str(value.get("id", ""))):
                raise ReviewError("Formato atual de sprint não reconhecido.")
            result.add(str(value["id"]))
    return result, available


def status_evidence(issue: dict, final_ids: set[str]) -> dict:
    changes = sorted(issue["status_changes"], key=lambda event: timestamp(event["at"]))
    gaps = []
    previous = None
    first_final_entry = None
    reopenings = []
    further_final_entries = []
    final_to_final = []
    initial_final = bool(changes and changes[0]["from"] in final_ids)
    for change in changes:
        before, after = change["from"], change["to"]
        if before is None or after is None:
            gaps.append("status_id_unavailable")
            previous = after
            continue
        if previous is not None and before != previous:
            gaps.append("status_history_discontinuous")
        if timestamp(change["at"]) < timestamp(issue["created"]):
            gaps.append("event_before_creation")
        evidence = {key: change[key] for key in ("history_id", "at", "from", "to")}
        if before in final_ids and after in final_ids:
            final_to_final.append(evidence)
        elif after in final_ids:
            if first_final_entry is None:
                first_final_entry = evidence
            else:
                further_final_entries.append(evidence)
        elif before in final_ids:
            reopenings.append(evidence)
        previous = after
    if changes and previous != issue["status"]["id"]:
        gaps.append("current_status_differs_from_history")
    if not changes and issue["status"]["id"] in final_ids:
        gaps.append("final_status_without_transition")
    if initial_final:
        gaps.append("history_starts_in_final_status")
    return {
        "first_observed_final_entry": first_final_entry,
        "first_completion_candidate": first_final_entry if not gaps else None,
        "reopenings": reopenings,
        "further_final_entries": further_final_entries,
        "final_to_final": final_to_final,
        "gaps": sorted(set(gaps)),
    }


def sprint_evidence(issue: dict) -> dict:
    changes = sorted(issue["sprint_changes"], key=lambda event: timestamp(event["at"]))
    current, available = current_sprints(issue)
    seen = set(current)
    movements = []
    removals = []
    gaps = []
    previous_by_field = {}
    for change in changes:
        before, after = sprint_ids(change["from"]), sprint_ids(change["to"])
        field = change["field_id"] or change["field_name"]
        if field in previous_by_field and before != previous_by_field[field]:
            gaps.append("sprint_history_discontinuous")
        previous_by_field[field] = after
        seen.update(before | after)
        entry = {
            "history_id": change["history_id"], "at": change["at"], "field_id": change["field_id"],
            "from_ids": sorted(before), "to_ids": sorted(after),
            "added_ids": sorted(after - before), "removed_ids": sorted(before - after),
        }
        movements.append(entry)
        if entry["removed_ids"]:
            removals.append(entry)
    return {
        "observed_sprint_ids": sorted(seen), "current_sprint_ids": sorted(current),
        "current_field_available": available, "movements": movements, "removals": removals,
        "association_basis": "own_history" if changes else "current_field_only" if current else "unavailable",
        "gaps": sorted(set(gaps)),
    }


def carried_work_evidence(issue: dict, sprints: list[dict], final: set[str], work: set[str],
                          collected_at: str) -> dict | None:
    """Seleciona um exemplo com os intervalos aprovados, sem calcular indicadores."""
    status = status_evidence(issue, final)
    sprint = sprint_evidence(issue)
    if status["gaps"] or sprint["gaps"] or not issue["status_changes"] or not sprint["movements"]:
        return None
    cutoff = timestamp(collected_at)
    windows = [(item, sprint_window(item, collected_at)) for item in sprints]
    ordered_sprints = sorted(
        [(item, window) for item, window in windows if window.availability == "available"],
        key=lambda pair: pair[1].start,
    )
    status_changes = sorted(issue["status_changes"], key=lambda event: timestamp(event["at"]))

    def state_at(reference: datetime, changes: list[dict], decode, *, include_at=False):
        if timestamp(issue["created"]) >= reference or not changes:
            return None
        value = decode(changes[0]["from"])
        for change in changes:
            at = timestamp(change["at"])
            if at > reference or (at == reference and not include_at):
                break
            value = decode(change["to"])
        return value

    for (previous, old_window), (following, new_window) in zip(ordered_sprints, ordered_sprints[1:]):
        end, start = old_window.end, new_window.start
        # A seleção de exemplos usa pares sem sobreposição; as janelas originais não são truncadas.
        if end > start or start >= cutoff:
            continue
        old_status = state_at(end, status_changes, lambda value: value)
        new_status = state_at(start, status_changes, lambda value: value, include_at=True)
        if old_status is None or new_status is None or old_status in final or new_status in final:
            continue
        if any(end <= timestamp(event["at"]) <= start and event["to"] in final for event in status_changes):
            continue
        work_entries = [event for event in status_changes if event["to"] in work and timestamp(event["at"]) < end]
        final_entries = [timestamp(event["at"]) for event in status_changes if event["to"] in final and timestamp(event["at"]) < end]
        if not work_entries:
            continue
        work_event = work_entries[-1]
        if final_entries and timestamp(work_event["at"]) <= max(final_entries):
            continue
        fields = {event["field_id"] or event["field_name"] for event in issue["sprint_changes"]}
        for field in fields:
            changes = sorted([event for event in issue["sprint_changes"]
                              if (event["field_id"] or event["field_name"]) == field],
                             key=lambda event: timestamp(event["at"]))
            old_ids = state_at(end, changes, sprint_ids)
            new_ids = state_at(start, changes, sprint_ids, include_at=True)
            if old_ids is not None and new_ids is not None and str(previous["id"]) in old_ids and str(following["id"]) in new_ids:
                return {
                    "previous_sprint_id": previous["id"], "following_sprint_id": following["id"],
                    "previous_end_utc": end.isoformat(), "following_start_utc": start.isoformat(),
                    "status_at_previous_end": old_status, "status_at_following_start": new_status,
                    "work_entry": {key: work_event[key] for key in ("history_id", "at", "to")},
                    "sprint_movements": sprint["movements"],
                    "basis": "approved_half_open_intervals_nonoverlapping_examples",
                    "requires_interval_review": False,
                }
    return None


def review_connection(connection: dict, *, task_types: set[str], bug_types: set[str],
                      task_final: set[str], bug_final: set[str], work_status: set[str],
                      examples: int = 3) -> dict:
    if not all((task_types, bug_types, task_final, bug_final, work_status)):
        raise ReviewError("Informe os tipos, os status finais e os status de trabalho.")
    if task_types & bug_types:
        raise ReviewError("Um tipo não pode representar tarefa e bug simultaneamente.")
    if work_status & task_final:
        raise ReviewError("Status de trabalho e finais de tarefas não podem se sobrepor.")
    if not 1 <= examples <= 20:
        raise ReviewError("A quantidade de exemplos deve estar entre 1 e 20.")
    known_types = {item["id"]: item for item in connection["issue_types"]}
    if not (task_types | bug_types) <= known_types.keys():
        raise ReviewError("Há tipos selecionados que não constam nos metadados do projeto.")
    for types, final in ((task_types, task_final), (bug_types, bug_final)):
        known_statuses = {status["id"] for type_id in types for status in known_types[type_id]["statuses"]}
        if not final <= known_statuses:
            raise ReviewError("Há status finais selecionados que não constam nos tipos configurados.")
    task_statuses = {status["id"] for type_id in task_types for status in known_types[type_id]["statuses"]}
    if not work_status <= task_statuses:
        raise ReviewError("Há status de trabalho que não constam nos tipos configurados.")
    if connection["status"] != "read_access_verified" or not connection.get("collection", {}).get("complete"):
        raise ReviewError("A conferência exige uma coleta completa dos tickets visíveis.")
    issues = connection["issues"]
    if len({issue["id"] for issue in issues}) != len(issues):
        raise ReviewError("O relatório contém tickets repetidos.")
    if connection["collection"]["histories_read"] != len(issues):
        raise ReviewError("Quantidade de históricos incompatível com os tickets do relatório.")
    audit = connection["pagination"]
    if not audit["search"]["complete"] or audit["search"]["items_read"] != len(issues):
        raise ReviewError("A auditoria de busca não confirma a coleta completa.")
    if any(not audit["changelogs"][issue["key"]]["complete"]
           or audit["changelogs"][issue["key"]]["items_read"] != issue["historical_events"] for issue in issues):
        raise ReviewError("A auditoria não confirma a leitura completa dos changelogs.")
    by_key = {issue["key"]: issue for issue in issues}
    categories = {name: {"candidate_count": 0, "examples": []} for name in (
        "carried_work", "multiple_sprints", "sprint_removals", "subtasks", "first_completions", "reopened_bugs",
        "further_completions", "final_to_final_transitions",
    )}
    limitations = [
        "Evidências para conferência; não são métricas calculadas ou validação manual concluída.",
        "Múltiplas sprints não comprovam trabalho pendente carregado: é necessário conferir os intervalos e as colunas de trabalho.",
        "A primeira entrada observada em status final depende da continuidade e da completude do histórico disponível.",
        "As regras usadas são temporárias e não cadastram nem alteram a configuração de projeto.",
        "Exemplos de trabalho carregado usam as datas aprovadas e pares sem sobreposição; as janelas sobrepostas são preservadas e não entram nessa seleção de exemplos.",
        "A coleta não comprova acesso a tickets ocultos, excluídos ou a todos os eventos do Jira.",
    ]
    counts = Counter()
    gaps = []

    def candidate(category: str, evidence: dict):
        target = categories[category]
        target["candidate_count"] += 1
        if len(target["examples"]) < examples:
            target["examples"].append(evidence)
        elif category == "subtasks" and examples > 1:
            bases = {item["sprint_evidence"]["association_basis"] for item in target["examples"]}
            if evidence["sprint_evidence"]["association_basis"] not in bases:
                target["examples"][-1] = evidence

    for issue in issues:
        type_id = issue["issue_type"]["id"]
        if type_id not in task_types | bug_types:
            continue
        counts["issues_in_scope"] += 1
        try:
            status = status_evidence(issue, task_final if type_id in task_types else bug_final)
            sprint = sprint_evidence(issue)
        except (ReviewError, KeyError, ValueError, TypeError, AttributeError) as error:
            gaps.append({"issue_key": issue["key"], "reason": str(error) if isinstance(error, ReviewError) else "Formato de evidência inesperado."})
            continue
        base = {"issue_key": issue["key"], "issue_id": issue["id"], "type_id": type_id}
        if status["gaps"] or sprint["gaps"]:
            gaps.append({"issue_key": issue["key"], "status_gaps": status["gaps"], "sprint_gaps": sprint["gaps"]})
        if type_id in task_types:
            try:
                carried = carried_work_evidence(issue, connection["sprints"], task_final, work_status,
                                                connection["collection"]["finished_at"])
            except (ReviewError, KeyError, ValueError, TypeError, AttributeError):
                carried = None
                gaps.append({"issue_key": issue["key"], "reason": "carryover_reference_unavailable"})
            if carried:
                candidate("carried_work", {**base, **carried})
            if len(sprint["observed_sprint_ids"]) > 1:
                candidate("multiple_sprints", {**base, "sprint_evidence": sprint,
                                               "status_evidence": status, "requires_interval_review": True})
            if sprint["removals"]:
                candidate("sprint_removals", {**base, "removal_events": sprint["removals"]})
            if status["first_completion_candidate"]:
                candidate("first_completions", {**base, "first_completion": status["first_completion_candidate"],
                                                "reopenings": status["reopenings"],
                                                "further_final_entries": status["further_final_entries"]})
            if status["further_final_entries"]:
                candidate("further_completions", {**base, "status_evidence": status})
            if status["final_to_final"]:
                candidate("final_to_final_transitions", {**base, "events": status["final_to_final"]})
        if type_id in bug_types and status["reopenings"]:
            candidate("reopened_bugs", {**base, "status_evidence": status, "sprint_evidence": sprint})
        if issue["issue_type"]["subtask"]:
            counts["subtasks"] += 1
            counts["subtasks_with_own_sprint_history"] += bool(sprint["movements"])
            counts["subtasks_without_own_sprint_history"] += not sprint["movements"]
            counts["subtasks_with_current_sprint"] += bool(sprint["current_sprint_ids"])
            counts["subtasks_without_current_sprint"] += sprint["current_field_available"] and not sprint["current_sprint_ids"]
            counts["subtasks_current_field_unavailable"] += not sprint["current_field_available"]
            parent_key = issue["parent"]["key"] if issue.get("parent") else None
            parent = by_key.get(parent_key)
            parent_ids = None
            if parent:
                try:
                    parent_ids = sorted(current_sprints(parent)[0])
                except ReviewError:
                    pass
            candidate("subtasks", {**base, "parent_key": parent_key,
                                   "parent_current_sprint_ids_for_comparison_only": parent_ids,
                                   "sprint_evidence": sprint, "inheritance_assumed": False})
    if counts["subtasks_without_own_sprint_history"]:
        limitations.append("Há subtarefas sem mudanças próprias de sprint; o campo atual e a tarefa mãe não comprovam sua participação histórica. Não foi presumida herança.")
    return {
        "connection": connection["connection"], "project_id": connection["project_id"],
        "project_key": connection["project_key"], "phase_1_complete": False,
        "manual_review_complete": False,
        "date_policy": {"version": POLICY_VERSION, "bounds": "[start,end)",
                        "closed_end": "completeDate", "active_end": "collection.finished_at",
                        "start": "startDate", "storage_timezone": "UTC", "display_timezone": DISPLAY_TIMEZONE},
        "sprint_dates_for_review": [
            {"id": sprint["id"], **sprint_window(sprint, connection["collection"]["finished_at"]).as_dict()}
            for sprint in connection["sprints"]
        ],
        "rules": {"task_type_ids": sorted(task_types), "bug_type_ids": sorted(bug_types),
                  "task_final_status_ids": sorted(task_final), "bug_final_status_ids": sorted(bug_final),
                  "work_status_ids": sorted(work_status),
                  "provisional": True},
        "counts": dict(counts), "cases": categories, "gaps": gaps, "limitations": limitations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".local/jira-review-step-4.json"))
    parser.add_argument("--project", type=int, choices=(1, 2), default=1)
    parser.add_argument("--task-type", action="append", required=True)
    parser.add_argument("--bug-type", action="append", required=True)
    parser.add_argument("--task-final-status", action="append", required=True)
    parser.add_argument("--bug-final-status", action="append", required=True)
    parser.add_argument("--work-status", action="append", required=True)
    parser.add_argument("--examples", type=int, choices=range(1, 21), default=3)
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ReviewError("Use arquivos distintos para a coleta e a conferência.")
        raw = args.input.read_bytes()
        source = json.loads(raw)
        connections = [item for item in source["connections"] if item["connection"] == args.project]
        if len(connections) != 1:
            raise ReviewError("A conexão selecionada não foi encontrada de forma única no relatório.")
        report = review_connection(
            connections[0], task_types=set(args.task_type), bug_types=set(args.bug_type),
            task_final=set(args.task_final_status), bug_final=set(args.bug_final_status),
            work_status=set(args.work_status), examples=args.examples,
        )
        report.update({"review_version": 2, "source_sha256": hashlib.sha256(raw).hexdigest(),
                       "source_checked_at": source["checked_at"],
                       "reviewed_at": datetime.now(timezone.utc).isoformat()})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (ReviewError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(str(error) if isinstance(error, ReviewError) else "Não foi possível conferir o relatório local; verifique o arquivo e seu formato.", file=sys.stderr)
        return 1
    # Somente contagens agregadas no terminal; exemplos ficam no arquivo privado.
    print(json.dumps({"case_candidates": {name: case["candidate_count"] for name, case in report["cases"].items()},
                      "counts": report["counts"], "issues_with_gaps": len(report["gaps"])}, ensure_ascii=False, indent=2))
    print("Relatório local de evidências gerado. A conferência manual e a fase 1 continuam pendentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
