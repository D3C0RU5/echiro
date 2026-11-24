"""Consolida as evidências da fase 1 para a conexão explicitamente selecionada."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from app.jira_participation import subtask_participation
from app.jira_review import ReviewError, sprint_ids
from app.jira_time import DISPLAY_TIMEZONE, POLICY_VERSION, sprint_window


SOURCES = {
    "subtask_inheritance": "https://support.atlassian.com/jira-software-cloud/docs/create-a-work-item-and-a-subtask/",
    "parent_history": "https://developer.atlassian.com/cloud/jira/platform/deprecation-notice-issue-reparenting-changelogs/",
    "sprint_dates": "https://developer.atlassian.com/cloud/jira/platform/jira-expressions-type-reference/#sprint",
    "board_configuration": "https://developer.atlassian.com/cloud/jira/software/rest/api-group-board/#api-rest-agile-1-0-board-boardid-configuration-get",
}


def evaluate(source: dict, review: dict, checks: dict, *,
             use_confirmed_rules: bool = False) -> dict:
    if source["project_id"] != review["project_id"] or source["project_id"] != checks["project_id"]:
        raise ReviewError("As evidências pertencem a projetos diferentes.")
    if review.get("review_version") != 2 or review.get("date_policy", {}).get("version") != POLICY_VERSION:
        raise ReviewError("Gere a conferência com a política de datas aprovada.")
    if not checks.get("verified") or checks.get("check_version") != 2:
        raise ReviewError("A conferência direta no Jira ainda não foi verificada.")
    by_key = {item["issue_key"]: item for item in checks["checks"]}
    examples = {}
    required_cases = ("carried_work", "sprint_removals", "subtasks", "first_completions", "reopened_bugs")
    for name in required_cases:
        entries = review["cases"][name]["examples"]
        matched = bool(entries) and all(
            entry["issue_key"] in by_key and by_key[entry["issue_key"]]["exported_events_match_live"]
            and by_key[entry["issue_key"]]["history_event_count_matches_source"]
            and by_key[entry["issue_key"]].get("current_fields_match_source", False)
            for entry in entries
        )
        examples[name] = {"example_count": len(entries), "verified_against_jira": matched,
                          "issue_keys": [entry["issue_key"] for entry in entries]}
    cutoff = source["collection"]["finished_at"]
    window_pairs = [(sprint, sprint_window(sprint, cutoff)) for sprint in source["sprints"]]
    available = [window for _, window in window_pairs if window.availability == "available"]
    overlaps = sum(first.start < second.end and second.start < first.end
                   for index, first in enumerate(available) for second in available[index + 1:])
    participation = subtask_participation(source, checks)
    participation_summary = {
        "subtasks": len(participation),
        "availability": dict(Counter(item["availability"] for item in participation)),
        "gap_reasons": dict(Counter(reason for item in participation for reason in item["gaps"])),
        "confirmed_interval_segments": sum(len(item["segments"]) for item in participation),
    }
    column_statuses = {status for column in source["columns"] for status in column["status_ids"]}
    mapped_statuses = {status["id"] for item in source["issue_types"] for status in item["statuses"]}
    observed_statuses = {str(event[side]) for item in source["issues"] for event in item["status_changes"]
                         for side in ("from", "to") if event[side] is not None}
    known_sprints = {str(sprint["id"]) for sprint in source["sprints"]}
    observed_sprints = set()
    unsupported_sprint_values = 0
    for item in source["issues"]:
        for event in item["sprint_changes"]:
            for side in ("from", "to"):
                try:
                    observed_sprints.update(sprint_ids(event[side]))
                except ReviewError:
                    unsupported_sprint_values += 1
    limitations = [
        "Validação restrita à conexão selecionada por orientação do usuário; o segundo projeto segue pendente para a primeira versão.",
        "Não há prova de acesso a tickets ocultos, excluídos ou a eventos que o Jira não disponibiliza.",
        "A coleta usa o projeto atual e não descobre automaticamente tickets movidos para fora dele.",
        "A coleta não é um snapshot transacional; divergências exigem atualização das evidências.",
        "A configuração histórica de colunas/status não foi reconstruída; aplica-se apenas a política de IDs expressamente aprovada.",
        "Participação derivada respeita existência, tipo e vínculo histórico da subtarefa; períodos desconhecidos são indisponíveis, não zero.",
        "Histórico ou metadados ausentes devem tornar os resultados afetados incompletos; não é permitido exibir ausência de atividade como substituição.",
        "Esta fase não implementa persistência, sincronização do produto nem o motor de métricas.",
    ]
    dates_ok = all(window.availability in ("available", "not_started") for _, window in window_pairs)
    inheritance_verified = bool(participation) and all(item["availability"] == "available" for item in participation)
    criteria = {
        "read_only_connection": bool(checks["verified"] and checks["browse_projects_allowed"]),
        "metadata_obtained": bool(source["columns"] and source["issue_types"] and source["sprints"]),
        "visible_history_pagination": bool(source["collection"]["complete"] and source["pagination"]["search"]["complete"]
                                           and all(item["complete"] for item in source["pagination"]["changelogs"].values())),
        "technical_examples_checked": all(item["verified_against_jira"] for item in examples.values()),
        "documented_subtask_method_verified": inheritance_verified,
        "date_policy_verified": dates_ok,
        "confirmed_rules_and_metadata_limitations_recorded": use_confirmed_rules and checks["current_columns_match_source"],
    }
    return {
        "phase_1_complete_for_selected_project": all(criteria.values()),
        "validation_scope": {"connection": source["connection"], "project_id": source["project_id"],
                             "project_key": source["project_key"], "second_project_deferred": True},
        "criteria": criteria, "technical_examples": examples,
        "verification_method": "selected_source_events_and_current_fields_compared_to_jira_read_api",
        "manual_ui_review_performed": False,
        "decisions": {"documented_inheritance_verified": inheritance_verified,
                      "configured_status_ids_applied_retroactively": use_confirmed_rules,
                      "status_rule_authority": "ids_previously_confirmed_by_user_for_phase1_analysis",
                      "method_basis": "official_jira_documentation_and_verified_historical_parent_type_links",
                      "production_configuration_saved": False,
                      "unknown_periods_remain_unavailable": True},
        "rules": review["rules"],
        "date_policy": review["date_policy"],
        "sprint_windows": [{"sprint_id": sprint["id"], **window.as_dict()} for sprint, window in window_pairs],
        "date_summary": {"availability": dict(Counter(window.availability for _, window in window_pairs)),
                         "overlapping_interval_pairs": overlaps, "display_timezone": DISPLAY_TIMEZONE},
        "subtask_summary": participation_summary, "subtask_participation": participation,
        "historical_metadata": checks.get("historical_metadata"),
        "metadata": {"current_columns_match_source": checks["current_columns_match_source"],
                     "observed_status_ids_outside_current_columns": sorted(observed_statuses - column_statuses),
                     "observed_status_ids_missing_from_type_metadata": sorted(observed_statuses - mapped_statuses),
                     "referenced_sprint_ids_not_returned_for_board": sorted(observed_sprints - known_sprints),
                     "unsupported_sprint_values": unsupported_sprint_values,
                     "historical_configuration_reconstructed": False},
        "limitations": limitations, "official_sources": SOURCES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".local/jira-phase1.json"))
    parser.add_argument("--project", type=int, choices=(1, 2), default=1)
    parser.add_argument("--use-confirmed-status-rules", action="store_true",
                        help="Usar na conferência os IDs já confirmados pelo usuário; não cadastra regras do produto.")
    args = parser.parse_args()
    try:
        if args.output.resolve() in {path.resolve() for path in (args.input, args.review, args.checks)}:
            raise ReviewError("A consolidação deve usar um arquivo de saída separado.")
        raw = args.input.read_bytes()
        source = json.loads(raw)
        review = json.loads(args.review.read_bytes())
        checks = json.loads(args.checks.read_bytes())
        fingerprint = hashlib.sha256(raw).hexdigest()
        if review["source_sha256"] != fingerprint or checks["source_sha256"] != fingerprint:
            raise ReviewError("As evidências não correspondem à mesma coleta.")
        selected = next(item for item in source["connections"] if item["connection"] == args.project)
        result = evaluate(selected, review, checks, use_confirmed_rules=args.use_confirmed_status_rules)
        result.update({"report_version": 1, "source_sha256": fingerprint,
                       "completed_at": datetime.now(timezone.utc).isoformat()})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (ReviewError, OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as error:
        print(str(error) if isinstance(error, ReviewError) else "Não foi possível consolidar as evidências da fase 1.", file=sys.stderr)
        return 1
    print(json.dumps({
        "phase_1_complete_for_selected_project": result["phase_1_complete_for_selected_project"],
        "criteria": result["criteria"], "date_summary": result["date_summary"],
        "subtask_summary": result["subtask_summary"],
        "metadata_summary": {key: len(result["metadata"][key]) for key in (
            "observed_status_ids_outside_current_columns", "observed_status_ids_missing_from_type_metadata", "referenced_sprint_ids_not_returned_for_board")},
        "historical_metadata_summary": {kind: {"queried": len(values), "readable": sum(item["available"] for item in values)}
                                        for kind, values in (result["historical_metadata"] or {}).items()},
    }, indent=2))
    return 0 if result["phase_1_complete_for_selected_project"] else 2


if __name__ == "__main__":
    sys.exit(main())
