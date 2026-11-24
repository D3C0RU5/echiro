"""Prova manual de leitura; não cadastra projetos nem persiste credenciais."""

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
from getpass import getpass
import json
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv

from app.jira_fields import hierarchy_changes
from app.integrations.client import JiraReader, ProbeError, NoRedirect


ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


SPRINT_SCHEMA = "com.pyxis.greenhopper.jira:gh-sprint"


def selected_values(value: dict, *keys: str) -> dict:
    """Exporta apenas metadados necessários para a conferência."""
    return {key: value.get(key) for key in keys}


def issue_evidence(reader: JiraReader, issue: dict, sprint_fields: list[dict], *,
                   page_size: int = 100, audit: dict | None = None) -> dict:
    fields = issue["fields"]
    history = list(reader.pages(
        f'/rest/api/3/issue/{issue["id"]}/changelog', "values", page_size=page_size, audit=audit))
    status_changes = []
    sprint_changes = []
    sprint_ids = {field["id"] for field in sprint_fields}
    sprint_names = {field["name"] for field in sprint_fields}
    for event in history:
        for item in event["items"]:
            field_id = item.get("fieldId")
            is_status = field_id == "status" or (
                not field_id and item.get("field") == "status")
            is_sprint = field_id in sprint_ids or (
                not field_id and item.get("field") in sprint_names)
            if not is_status and not is_sprint:
                continue
            change = {
                "history_id": event["id"], "at": event["created"],
                "field_id": field_id, "field_name": item.get("field"),
                "from": item.get("from"), "from_name": item.get("fromString"),
                "to": item.get("to"), "to_name": item.get("toString"),
            }
            (status_changes if is_status else sprint_changes).append(change)
    memberships = []
    for field in sprint_fields:
        field_id = field["id"]
        value = fields.get(field_id)
        # Preserva a ausência do campo como indisponível; não herda da tarefa mãe.
        projected = None
        if value is not None:
            if not isinstance(value, list):
                raise ProbeError("Formato inesperado do campo de sprint; conferência incompleta.")
            projected = [
                selected_values(sprint, "id", "name", "state", "startDate", "endDate", "completeDate")
                if isinstance(sprint, dict) else {"legacy_value": sprint}
                for sprint in value
            ]
        memberships.append({
            "field_id": field_id, "available": field_id in fields, "value": projected,
        })
    return {
        "id": issue["id"], "key": issue["key"],
        "created": fields.get("created"), "updated": fields.get("updated"),
        "issue_type": selected_values(fields["issuetype"], "id", "name", "subtask"),
        "status": selected_values(fields["status"], "id", "name"),
        "parent": selected_values(fields["parent"], "id", "key") if fields.get("parent") else None,
        "sprint_memberships": memberships,
        "historical_events": len(history),
        "history_scope": "all_api_pages_for_issue",
        "status_changes": status_changes, "sprint_changes": sprint_changes,
        **hierarchy_changes(history),
    }


def probe(
    reader: JiraReader, project_key: str, board_id: int, *,
    sample_size: int = 5, issue_keys: list[str] | None = None,
    all_issues: bool = False, page_size: int = 100,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", project_key) or board_id <= 0:
        raise ProbeError("Informe uma chave de projeto válida e um ID de quadro positivo.")
    if not 1 <= sample_size <= 100:
        raise ProbeError("O tamanho da amostra deve estar entre 1 e 100.")
    if not 1 <= page_size <= 100:
        raise ProbeError("O tamanho da página deve estar entre 1 e 100.")
    if all_issues and issue_keys:
        raise ProbeError("Escolha todos os tickets ou chaves específicas, sem combinar as opções.")
    pagination = {"board_projects": {}, "sprints": {}, "search": {}, "changelogs": {}}
    for key in issue_keys or []:
        if not re.fullmatch(rf"{re.escape(project_key)}-[1-9][0-9]*", key):
            raise ProbeError("Os tickets da amostra devem pertencer ao projeto selecionado.")
    reader.get("/rest/api/3/myself")
    project = reader.get(f"/rest/api/3/project/{project_key}", expand="issueTypes")
    board = reader.get(f"/rest/agile/1.0/board/{board_id}")
    members = list(reader.pages(f"/rest/agile/1.0/board/{board_id}/project", "values",
                                page_size=page_size, audit=pagination["board_projects"]))
    if str(project["id"]) not in {str(member["id"]) for member in members}:
        raise ProbeError("O projeto não aparece entre os projetos acessíveis do quadro informado.")
    configuration = reader.get(f"/rest/agile/1.0/board/{board_id}/configuration")
    type_statuses = reader.get(f"/rest/api/3/project/{project_key}/statuses")
    sprints = list(reader.pages(f"/rest/agile/1.0/board/{board_id}/sprint", "values",
                                page_size=page_size, audit=pagination["sprints"]))
    sprint_fields = [selected_values(field, "id", "name")
                     for field in reader.get("/rest/api/3/field")
                     if (field.get("schema") or {}).get("custom") == SPRINT_SCHEMA]
    requested_fields = ",".join([
        "project", "issuetype", "status", "parent", "created", "updated",
        *(field["id"] for field in sprint_fields),
    ])
    collection = {
        "scope": "all_visible_project_issues" if all_issues else "sample",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "search_complete": False, "complete": False, "failures": [],
    }
    if all_issues:
        issues = []
        try:
            for issue in reader.search_issues(
                f'project = "{project_key}" ORDER BY created ASC, key ASC', requested_fields,
                page_size=page_size, audit=pagination["search"],
            ):
                issues.append(issue)
            collection["search_complete"] = True
        except (ProbeError, KeyError, TypeError, ValueError, AttributeError) as error:
            collection["failures"].append({
                "stage": "search",
                "error": str(error) if isinstance(error, ProbeError) else "Formato de busca inesperado.",
            })
    elif issue_keys:
        issues = [reader.get(f"/rest/api/3/issue/{key}", fields=requested_fields)
                  for key in dict.fromkeys(issue_keys)]
    else:
        search = reader.get(
            "/rest/api/3/search/jql", jql=f'project = "{project_key}" ORDER BY created ASC, key ASC',
            maxResults=sample_size, fields=requested_fields,
        )
        issues = search["issues"]
    samples = []
    for issue in issues if not all_issues or collection["search_complete"] else []:
        audit = {}
        pagination["changelogs"][issue["key"]] = audit
        try:
            if str(issue["fields"]["project"]["id"]) != str(project["id"]):
                raise ProbeError("Um ticket retornado não pertence ao projeto selecionado.")
            samples.append(issue_evidence(reader, issue, sprint_fields, page_size=page_size, audit=audit))
        except (ProbeError, KeyError, TypeError, ValueError, AttributeError) as error:
            if not all_issues:
                raise
            collection["failures"].append({
                "stage": "changelog", "issue_key": issue["key"],
                "error": str(error) if isinstance(error, ProbeError) else "Formato de histórico inesperado.",
            })
            break
        if progress:
            progress(len(samples), len(issues))
    collection.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "issues_discovered": len(issues), "histories_read": len(samples),
        "unread_issue_keys": [issue["key"] for issue in issues[len(samples):]],
        "complete": all_issues and collection["search_complete"] and len(samples) == len(issues),
    })
    limitations = [
        "A API não comprova acesso a tickets ocultos, excluídos ou a eventos indisponíveis.",
        "Permissões podem ocultar tickets e eventos sem produzir erro HTTP.",
        "Casos das métricas e configurações históricas ainda exigem conferência manual.",
        "Colunas e status descrevem a configuração atual; não comprovam a configuração histórica.",
        "Datas das sprints são exportadas sem definir ainda as regras de intervalos das métricas.",
        "Ausência de mudança nos dados retornados não comprova ausência de atividade no projeto.",
    ]
    if not all_issues:
        limitations.append("Amostra de tickets; não comprova a completude do histórico do projeto.")
    else:
        limitations.append("Busca sem filtro de quadro, tipo ou sprint; não é um snapshot transacional e alterações durante a coleta podem exigir nova execução.")
        if not collection["complete"]:
            limitations.append("Coleta incompleta; consulte as falhas e os tickets não lidos. Dados indisponíveis não representam zero.")
    if not sprint_fields:
        limitations.append("Campo de sprint não localizado pelo schema; participação em sprints não verificada.")
    if not samples:
        if issues:
            limitations.append("Nenhum histórico pôde ser conferido nesta execução.")
        elif all_issues and not collection["search_complete"]:
            limitations.append("Busca incompleta; quantidade total de tickets indisponível.")
        else:
            limitations.append("Nenhum ticket visível; leitura de changelog não verificada.")
    types = {item["id"]: item for item in project["issueTypes"]}
    return {
        "status": "incomplete" if all_issues and not collection["complete"] else "read_access_verified",
        "project_id": project["id"], "project_key": project["key"], "project_name": project["name"],
        "board_id": board_id, "board": selected_values(board, "id", "name", "type"),
        "columns": [
            {"name": column["name"], "status_ids": [status["id"] for status in column["statuses"]]}
            for column in configuration["columnConfig"]["columns"]
        ],
        "issue_type_ids": [item["id"] for item in type_statuses],
        "issue_types": [
            {**selected_values(types.get(item["id"], item), "id", "name", "subtask"),
             "statuses": [selected_values(status, "id", "name") for status in item["statuses"]]}
            for item in type_statuses
        ],
        "sprint_fields": sprint_fields, "sprints_read": len(sprints),
        "sprints": [selected_values(sprint, "id", "name", "state", "startDate", "endDate", "completeDate", "originBoardId")
                    for sprint in sprints],
        "pagination": pagination,
        "collection": collection if all_issues else None,
        "sample_selection": {"mode": "all_visible_project_issues" if all_issues else "explicit_keys" if issue_keys else "oldest_issues",
                             "requested": "all" if all_issues else list(dict.fromkeys(issue_keys)) if issue_keys else sample_size,
                             "returned": len(samples)},
        ("issues" if all_issues else "sample_issues"): samples, "limitations": limitations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=None)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--project", type=int, choices=(1, 2), default=1,
                           help="Conexão selecionada (padrão: 1).")
    selection.add_argument("--all-projects", action="store_true",
                           help="Testar as duas conexões.")
    parser.add_argument("--sample-size", type=int, choices=range(1, 101), default=5,
                        metavar="1..100", help="Máximo de tickets na amostra (padrão: 5).")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all-issues", action="store_true",
                       help="Percorrer todos os tickets visíveis do projeto e seus changelogs.")
    scope.add_argument("--issue", action="append", dest="issue_keys", metavar="CHAVE",
                        help="Conferir um ticket específico; pode ser repetido e substitui a busca de amostra.")
    parser.add_argument("--page-size", type=int, choices=range(1, 101), default=100,
                        metavar="1..100", help="Máximo de itens solicitado por página (padrão: 100).")
    args = parser.parse_args()
    args.output = args.output or Path(".local/jira-probe-full.json" if args.all_issues else ".local/jira-probe.json")
    load_dotenv(ENV_FILE, override=False, interpolate=False)
    results = []
    for number in ((1, 2) if args.all_projects else (args.project,)):
        prefix = f"JIRA_PROBE_{number}_"
        try:
            def setting(name: str, prompt: str) -> str:
                return os.environ.get(prefix + name) or input(f"Projeto {number} — {prompt}: ").strip()

            url = setting("URL", "URL Jira Cloud")
            key = setting("PROJECT_KEY", "chave do projeto")
            board = int(setting("BOARD_ID", "ID do quadro"))
            email = setting("EMAIL", "e-mail Atlassian")
            token = os.environ.get(
                prefix + "TOKEN") or getpass(f"Projeto {number} — token (oculto): ")
            def progress(done: int, total: int):
                if done == 1 or done % 10 == 0 or done == total:
                    print(f"Conexão {number}: históricos lidos {done}/{total}.", flush=True)

            if args.all_issues:
                print(f"Conexão {number}: buscando todos os tickets visíveis...", flush=True)
            result = probe(JiraReader(url, email, token), key, board,
                           sample_size=args.sample_size, issue_keys=args.issue_keys,
                           all_issues=args.all_issues, page_size=args.page_size,
                           progress=progress if args.all_issues else None)
        except ProbeError as error:
            result = {"status": "failed", "error": str(error)}
        except (ValueError, KeyError, TypeError, AttributeError):
            result = {"status": "failed",
                      "error": "Configuração ou formato de resposta inesperado."}
        except (EOFError, KeyboardInterrupt):
            print(
                "Prova cancelada; nenhum acesso foi considerado validado.", file=sys.stderr)
            return 130
        result["connection"] = number
        results.append(result)
        print(f"Conexão {number}: {result['status']}")
    report = {
        "report_version": 3,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "phase_1_complete": False,
        "connections": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # O relatório contém metadados privados, embora não contenha credenciais.
    descriptor = os.open(args.output, os.O_WRONLY |
                         os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print("Relatório local gerado. A fase 1 ainda requer conferência do histórico.")
    return 0 if all(item["status"] == "read_access_verified" for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
