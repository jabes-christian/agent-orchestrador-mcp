"""Smoke test E2E: valida `POST /tasks` contra a stack real subida via `docker compose up -d`
(MCPO-07 AC3, spec.md -> P1 "Stack completo via docker-compose" AC3).

Roda DEPOIS da stack estar de pé (`docker compose up -d && python scripts/smoke_test.py`,
Gate Check Commands em tasks.md) -- este script não sobe nem derruba containers, só bate na
porta publicada do gateway (8080, `docker-compose.yml`) com requests reais.

Exige `.env` preenchido com segredos reais (`ORCHESTRATOR_API_KEY`, `OPENROUTER_API_KEY`,
`GITHUB_PERSONAL_ACCESS_TOKEN`) -- spec.md Independent Test: "em máquina limpa, `cp
.env.example .env` (preenchendo os segredos) -> `docker compose up -d` -> script de smoke
test E2E sai com código 0." `Settings()` (T3) lê `ORCHESTRATOR_API_KEY` do mesmo `.env`.

Cada caso pede uma tarefa em linguagem natural que só um MCP server específico consegue
resolver, e confirma que `trace.used_tools` contém uma tool prefixada por aquele server --
`TraceRecorder.used_tools` (T5) só inclui passos com `status: "success"`, então esse critério
prova que o server realmente respondeu, não só que a rota HTTP retornou 200 (spec.md AC3 exige
"HTTP 200 para ao menos um caso de cada MCP server", mas um 200 com `finish_reason:
"no_suitable_server"` não provaria que aquele server funcionou).
"""

import sys

import httpx

from orchestrator.settings import Settings

GATEWAY_URL = "http://localhost:8080"
REQUEST_TIMEOUT_S = 120.0

# (nome do server, tarefa em linguagem natural que só ele resolve)
CASES: list[tuple[str, str]] = [
    ("filesystem", "liste os arquivos do diretorio de trabalho"),
    ("github", "quem e o dono do repositorio octocat/Hello-World no GitHub?"),
]


def _post_task(api_key: str, task: str) -> dict:
    response = httpx.post(
        f"{GATEWAY_URL}/tasks",
        json={"task": task},
        headers={"X-API-Key": api_key},
        timeout=REQUEST_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.json()


def _run_case(api_key: str, server: str, task: str) -> str | None:
    """Roda um caso; retorna `None` se passou, ou uma mensagem de falha."""
    try:
        body = _post_task(api_key, task)
    except httpx.HTTPStatusError as exc:
        return f"{server}: HTTP {exc.response.status_code} -- {exc.response.text}"
    except httpx.HTTPError as exc:
        return f"{server}: falha de conexao -- {exc}"

    used_tools = body.get("trace", {}).get("used_tools", [])
    if not any(tool.startswith(f"{server}.") for tool in used_tools):
        return f"{server}: nenhuma tool de '{server}' em trace.used_tools (obtido: {used_tools})"
    return None


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    failures = [
        message
        for server, task in CASES
        if (message := _run_case(settings.orchestrator_api_key, server, task)) is not None
    ]

    if failures:
        for message in failures:
            print(f"FAIL: {message}", file=sys.stderr)
        return 1

    print(f"smoke test: ok -- {len(CASES)} caso(s) passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
