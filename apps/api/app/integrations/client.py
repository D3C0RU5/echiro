"""Cliente Jira Cloud somente de leitura, compartilhado pela prova e pelo cadastro."""

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ProbeError(Exception):
    """Mensagem segura, sem corpos de respostas ou credenciais."""

    def __init__(self, message, *, status_code=None, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Não encaminhar Authorization para outro destino.
        return None


class JiraReader:
    def __init__(self, url: str, email: str, token: str):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".atlassian.net")
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ProbeError(
                "Use a URL HTTPS do site Jira Cloud: https://empresa.atlassian.net.")
        if not email.strip() or not token.strip():
            raise ProbeError("E-mail e token são obrigatórios.")
        self.url = url.rstrip("/")
        encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
        self._authorization = f"Basic {encoded}"
        self._opener = build_opener(NoRedirect())

    def get(self, path: str, **params):
        if not path.startswith(("/rest/api/3/", "/rest/agile/1.0/")):
            raise ProbeError("Endpoint fora da prova de leitura.")
        request = Request(
            self.url + path + ("?" + urlencode(params) if params else ""),
            headers={"Accept": "application/json",
                     "Authorization": self._authorization},
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            messages = {
                401: "Autenticação recusada; verifique e-mail e token.",
                403: "Permissão insuficiente para esta consulta.",
                404: "Recurso indisponível ou sem permissão de leitura.",
                429: "Limite de requisições atingido; execute novamente mais tarde.",
            }
            raise ProbeError(messages.get(
                error.code, f"Consulta recusada (HTTP {error.code})."),
                status_code=error.code, retry_after=error.headers.get("Retry-After") if error.headers else None) from None
        except (URLError, TimeoutError, OSError):
            raise ProbeError("Falha de comunicação com o Jira.", status_code=0) from None
        except (ValueError, UnicodeError):
            raise ProbeError(
                "O Jira retornou uma resposta JSON inválida.") from None

    def pages(self, path: str, field: str, *, page_size: int = 100,
              audit: dict | None = None, **params):
        audit = audit if audit is not None else {}
        audit.update({"page_count": 0, "items_read": 0, "complete": False, "reported_total": None})
        start = 0
        seen_ids = set()
        expected_total = None
        while True:
            page = self.get(path, startAt=start, maxResults=page_size, **params)
            values = page.get(field)
            total = page.get("total")
            last = page.get("isLast")
            if not isinstance(values, list) or page.get("startAt", start) != start:
                raise ProbeError("Resposta paginada inesperada; leitura incompleta.")
            if total is not None and (type(total) is not int or total < 0):
                raise ProbeError("Total paginado inválido; leitura incompleta.")
            if expected_total is not None and total != expected_total:
                raise ProbeError("Total alterado durante a paginação; refaça a prova.")
            if total is not None:
                expected_total = total
                audit["reported_total"] = total
            end = start + len(values)
            if last is not None and type(last) is not bool:
                raise ProbeError("Indicação de término inválida; leitura incompleta.")
            if total is None and last is None:
                raise ProbeError("Paginação sem indicação de término; leitura incompleta.")
            if total is not None and (end > total or (last is True and end != total)
                                      or (last is False and end >= total)):
                raise ProbeError("Paginação contraditória; leitura incompleta.")
            ids = [str(value["id"]) for value in values if isinstance(value, dict) and "id" in value]
            if len(ids) != len(set(ids)) or seen_ids.intersection(ids):
                raise ProbeError("Registros repetidos entre páginas; leitura incompleta.")
            seen_ids.update(ids)
            audit["page_count"] += 1
            audit["items_read"] = end
            yield from values
            if last is True or (total is not None and end == total):
                audit["complete"] = True
                return
            if not values:
                raise ProbeError("Paginação sem avanço; leitura incompleta.")
            start = end

    def search_issues(self, jql: str, fields: str, *, page_size: int = 100, audit: dict):
        audit.update({"page_count": 0, "items_read": 0, "complete": False})
        token = None
        seen_tokens = set()
        seen_ids = set()
        while True:
            params = {"jql": jql, "fields": fields, "maxResults": page_size}
            if token is not None:
                params["nextPageToken"] = token
            page = self.get("/rest/api/3/search/jql", **params)
            issues = page.get("issues")
            last = page.get("isLast")
            if not isinstance(issues, list) or type(last) is not bool:
                raise ProbeError("Resposta de busca paginada inesperada; leitura incompleta.")
            if page.get("warningMessages") or page.get("warnings"):
                raise ProbeError("O Jira retornou avisos na busca; confira a consulta antes de considerar a leitura completa.")
            next_token = page.get("nextPageToken")
            if not last and (not isinstance(next_token, str) or not next_token or next_token in seen_tokens):
                raise ProbeError("Busca paginada sem avanço do cursor; leitura incompleta.")
            if not issues and not last:
                raise ProbeError("Busca paginada vazia sem término; leitura incompleta.")
            if any(not isinstance(issue, dict) or "id" not in issue for issue in issues):
                raise ProbeError("Ticket sem identificador na busca; leitura incompleta.")
            ids = [str(issue["id"]) for issue in issues]
            if len(ids) != len(set(ids)) or seen_ids.intersection(ids):
                raise ProbeError("Tickets repetidos entre páginas; refaça a prova.")
            seen_ids.update(ids)
            audit["page_count"] += 1
            audit["items_read"] += len(issues)
            yield from issues
            if last:
                audit["complete"] = True
                return
            seen_tokens.add(next_token)
            token = next_token


