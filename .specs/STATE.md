# Project State — agent-orchestrator-mcp

> Memória do projeto entre fases e sessões. Ver `references/memory.md` da skill `tlc-spec-driven`
> para o protocolo de leitura/escrita deste arquivo.

## Decisions

| ID | Decisão | Status | Contexto |
| --- | --- | --- | --- |
| AD-001 | Transporte MCP no fio interno do compose é **Streamable HTTP**. Cada MCP server oficial (stdio-only na forma distribuída) roda em seu próprio container atrás de um shim FastMCP (`create_proxy`) que traduz stdio→Streamable HTTP. O transporte SSE/HTTP+SSE nunca é usado — está deprecado na spec MCP (revisão 2025-11-25). | active | `.specs/features/mcp-orchestrator/design.md` §1.2 |
| AD-002 | O grafo do orquestrador é um `StateGraph` **customizado** do LangGraph (nós/arestas próprios), não um agente prebuilt (`create_agent`/ReAct pronto). Necessário para controle explícito de `iterations`, `trace.steps` por chamada e bloqueio pré-execução da allowlist. | active | `.specs/features/mcp-orchestrator/design.md` §1.1 |
| AD-003 | Acesso ao LLM via OpenRouter usa o pacote dedicado `langchain-openrouter` (`ChatOpenRouter`), não `ChatOpenAI` com `base_url` sobrescrito — a doc oficial do LangChain desaconselha essa rota para providers não-OpenAI. | active | `.specs/features/mcp-orchestrator/design.md` §1.6 |
| AD-004 | A suíte de avaliação de roteamento (MCPO-10) roda em dois modos: modo CI (default, offline, fixtures de resposta do LLM gravadas uma vez) dentro do gate de PR; modo live (`EVAL_LIVE=1`, chamada real ao OpenRouter) fora do gate. Mudar o prompt de decisão exige regravar as fixtures na mesma task. | active | `.specs/features/mcp-orchestrator/design.md` §1.5 |
| AD-005 | Nenhum nome de MCP server ou de tool pode aparecer hardcoded fora de `config/servers.yaml` + `src/orchestrator/mcp_client/registry.py`. Sustenta MCPO-02 AC4 e o Success Criterion "adicionar um terceiro server não exige alterar o pacote do grafo". | active | `.specs/features/mcp-orchestrator/design.md` §1.3 |
| AD-006 | MCPO-12 (limite de custo/tokens por request) é adiado formalmente para v1.1 e não vira task nesta feature. O AC do requisito exige `error.code = "TOKEN_BUDGET_EXCEEDED"`, código ausente do catálogo fechado de 8 erros já validado na Fase 3 (spec); reabrir esse contrato de API por um requisito P3 não se paga. Os limites já existentes (`MAX_REACT_ITERATIONS=5`, `REQUEST_TIMEOUT_S=120`) já fornecem um teto grosseiro de custo por request. | active | `.specs/features/mcp-orchestrator/spec.md` → Requirement Traceability (MCPO-12, status `Deferred`); `.specs/features/mcp-orchestrator/tasks.md` → Requisitos fora do escopo destas tasks |
| AD-007 | `mcp_client.registry` não conhece `tool_policy.yaml` — `ServerInfo.tools[].write` que ele produz é um placeholder `False`, documentado inline. A classificação real de escrita só existe em `mcp_client.policy` (T10). `GET /servers` (T15) é o único ponto autorizado a sobrescrever esse placeholder com `policy.is_write()` antes de responder ao cliente, conforme MCPO-02 AC3 exige `write: bool` correto. Corrigido em `tasks.md` (T15 ganhou `Depends on: T10`) durante a revisão do Lote 1 do Execute, antes de T15 ser implementada no Lote 2 — nenhum código já commitado precisou mudar. | active | `.specs/features/mcp-orchestrator/tasks.md` → T15; `src/orchestrator/mcp_client/registry.py` (comentário inline) |

## Handoff

**Feature ativa:** `mcp-orchestrator`
**Fase concluída:** Tasks (Fase 4 de 5 do `tlc-spec-driven`)
**Branch:** `docs/tasks-mcp-orchestrator`
**Artefatos desta fase:** `.specs/features/mcp-orchestrator/tasks.md` (novo — 36 tasks em 8 fases, Test Coverage Matrix, Gate Check Commands, diagramas por fase, 3 tabelas de checagem pré-aprovação); `.specs/features/mcp-orchestrator/spec.md` (emendado — tabela de Requirement Traceability ganhou coluna `Tasks`, MCPO-01..MCPO-11 em `In Tasks`, MCPO-12 em `Deferred`); `.specs/STATE.md` (este arquivo — AD-006 registrado).
**Próximo passo:** aguardar validação do usuário sobre `tasks.md`; ao aprovar, seguir para Fase 5 (Execute) com a oferta de sub-agentes em 5 lotes (F1+F2 · F3+F4 · F5 · F6+F7 · F8).
**Pendências levadas à Fase 5:** T1 confirma na prática o caminho exato do binário dentro da imagem `ghcr.io/github/github-mcp-server` antes de T30 depender dele; regravação de fixtures de avaliação (T36) é obrigatória sempre que `graph/prompts.py` mudar (AD-004).
