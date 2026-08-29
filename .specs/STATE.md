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

## Handoff

**Feature ativa:** `mcp-orchestrator`
**Fase concluída:** Design (Fase 3 de 5 do `tlc-spec-driven`)
**Branch:** `docs/design-mcp-orchestrator`
**Artefatos desta fase:** `.specs/features/mcp-orchestrator/design.md` (novo), `.specs/STATE.md` (novo, este arquivo), `.specs/features/mcp-orchestrator/spec.md` (emendado — `finish_reason` ganhou o valor `"error"`)
**Próximo passo:** aguardar validação do usuário sobre `design.md`; ao aprovar, seguir para Fase 4 (Tasks) — quebra em tasks atômicas com `Tests`/`Gate` por task, rodando `validate_tasks.py`.
**Pendências levadas à Fase 4:** confirmar na primeira task de Execute o caminho exato do binário dentro da imagem `ghcr.io/github/github-mcp-server` (ver `design.md` → Risks & Concerns); regravação de fixtures de avaliação é obrigatória sempre que `graph/prompts.py` mudar.
