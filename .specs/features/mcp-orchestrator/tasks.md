# MCP Orchestrator Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its
Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is
the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review,
Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/mcp-orchestrator/design.md`
**Status**: Draft

---

## Test Coverage Matrix

> Gerada a partir da spec e do design - confirmar antes do Execute. Guidelines encontradas:
> nenhuma - defaults fortes aplicados. O repositório é greenfield (só `.gitignore`, `.specs/`, um
> `.venv` vazio): não existem `pyproject.toml`, testes, `AGENTS.md`/`CONTRIBUTING.md` nem config de
> coverage para amostrar. Portanto Coverage Expectation e Run Command abaixo são defaults fortes
> calibrados pelo Design §6 (estratégia de teste em 4 camadas), não inferidos de código existente.

| Camada | Tipo de teste | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Config / schema / infra (`pyproject.toml`, `config/*.yaml`, `.env.example`, Dockerfiles, `docker-compose.yml`, `graph/state.py`, `tests/eval/dataset.json`) | none | build gate apenas | — | build gate |
| Lógica pura (`settings.py`, `policy.py`, `observability/trace.py`, `observability/logging.py`, `api/schemas.py`, `api/auth.py`, `api/errors.py`) | unit | todas as branches; 1:1 com os ACs da spec; todo edge case listado tem teste | `tests/unit/test_*.py` | `python -m pytest tests/unit -q` |
| Nós do grafo e roteamento (`graph/nodes.py`, `graph/builder.py`, `graph/prompts.py`, `llm/provider.py`) | unit | toda branch de roteamento + todo caminho de erro, com dublês de teste (LLM roteirizado, tools falsas) | `tests/unit/test_*.py` | `python -m pytest tests/unit -q` |
| Cliente MCP e transporte (`mcp_client/registry.py`, `shim/mcp_http_shim.py`) | integration | server MCP falso real (`fastmcp.FastMCP` em porta efêmera): sucesso, server fora do ar, timeout | `tests/integration/test_*.py` | `python -m pytest tests/integration -q` |
| Rotas HTTP (`main.py`, `api/routes_*.py`) | integration | toda rota: happy path + cada edge case listado + cada código de erro aplicável | `tests/integration/test_*.py` | `python -m pytest tests/integration -q` |
| Avaliação de roteamento (`tests/eval/`) | eval (pytest, offline) | 15 casos rotulados, acurácia ≥ 90%, exit ≠ 0 abaixo disso | `tests/eval/test_routing.py` | `python -m pytest tests/eval -q` |
| Stack E2E (`scripts/smoke_test.py`, `tests/e2e/`) | e2e | ≥ 1 caso por MCP server, fora do gate padrão | `tests/e2e/test_*.py` | `python -m pytest tests/e2e -q -m e2e` |

## Gate Check Commands

> Gerada a partir da spec e do design - confirmar antes do Execute.

| Gate | Quando | Comando |
| --- | --- | --- |
| Discovery | T1 apenas (spike de infra, sem código) | `docker inspect ghcr.io/github/github-mcp-server:v1.11.0 --format '{{json .Config.Entrypoint}}'` - imprime `["/server/github-mcp-server"]`. **Corrigido em T1**: o comando original (`--entrypoint sh ... -c 'command -v ...'`) falha com exit 127 porque a imagem é distroless/scratch (sem `sh`/`ls`/`busybox`); `docker inspect` no `Entrypoint` é o método que funciona contra esta imagem — ver `design.md` §4 |
| Quick | tasks só com unit tests | `python -m pytest tests/unit -q` |
| Full | tasks com integration/eval | `python -m pytest tests/unit -q && python -m pytest tests/integration -q` (a partir de T36, mais `&& python -m pytest tests/eval -q` como 3ª invocação separada) -- **corrigido no Execute (T27, AD-012)**: `tests/unit` e `tests/integration` combinados num único comando/processo travam de forma reprodutível (hang sem causa raiz identificada, não é bug de nenhum teste específico); rodar como invocações de processo separadas contorna o travamento sem perder cobertura |
| Build | tasks de config/infra e fim de fase | `ruff check . && ruff format --check . && mypy src && python -m pytest tests/unit -q -m "not e2e and not live" && python -m pytest tests/integration -q -m "not e2e and not live"` -- mesma correção do gate Full (AD-012): invocações separadas em vez de `pytest -q` combinado |
| E2E | T34 apenas (fora do gate de PR) | `docker compose up -d && python scripts/smoke_test.py && python -m pytest tests/e2e -q -m e2e` |

---

## Execution Plan

As fases são ordenadas e executam sequencialmente - cada fase se completa antes da próxima começar,
e as tasks dentro de uma fase executam em ordem.

### Phase 1: Fundação e descoberta

Confirma o caminho do binário do github-mcp-server e estabelece a config do projeto, o logging
estruturado e o registro de trace.

```
T1
T2 → T3
T2 → T4
T2 → T5
```

### Phase 2: Configuração e cliente MCP

Registro de servers e política de tools de escrita, construídos sobre a fundação de config da
Fase 1.

```
T6 → T8
T7 → T8
T9 → T10
```

### Phase 3: Camada HTTP e contrato

Schemas de request/response, autenticação, o catálogo de erros, a app factory e a primeira rota.

```
T11 → T13 → T14 → T15
T12
```

### Phase 4: Fundação do grafo

Estado do grafo, o wrapper do provider de LLM e o construtor do system prompt.

```
T16 → T18
T17
```

### Phase 5: Nós e roteamento do grafo

Todo nó do LangGraph e a tabela de roteamento que os conecta, mais o grafo compilado.

```
T19 → T20 → T23 → T24
T19 → T21 → T22 → T24
T20 → T24
```

### Phase 6: Endpoint principal

Conecta autenticação, o grafo compilado e o timeout por request no `POST /tasks`, depois o health
check agregado.

```
T25 → T26
```

### Phase 7: Containers e stack

Shim, imagens por server, a imagem do gateway, defaults de ambiente, topologia do compose e o
smoke test E2E.

```
T27 → T28 → T29 → T33 → T34
T28 → T30 → T33
T31 → T33
T32 → T33
```

### Phase 8: Avaliação de roteamento

Dataset rotulado e a suíte de avaliação offline com gate de acurácia.

```
T35 → T36
```

---

## Task Breakdown

### Phase 1: Fundação e descoberta

#### T1: Confirmar caminho do binário do github-mcp-server

**What**: Executar `docker run --rm --entrypoint sh ghcr.io/github/github-mcp-server:<tag> -c 'command -v github-mcp-server'` para descobrir o caminho real do binário dentro da imagem e a tag pinada a usar; gravar o resultado em `design.md` §4, substituindo a suposição `/server/github-mcp-server`. Se o binário não existir no `PATH` da imagem, documentar o fallback (estágio builder com `go build -o github-mcp-server ./cmd/github-mcp-server`).
**Where**: `.specs/features/mcp-orchestrator/design.md`
**Depends on**: none
**Reuses**: N/A (primeira task do projeto; greenfield)
**Requirement**: MCPO-07

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Comando de discovery executado com sucesso (exit 0) e o caminho do binário impresso
- [x] Tag pinada da imagem registrada
- [x] `design.md` §4 atualizado com o caminho real e a tag, substituindo a suposição anterior
- [x] Gate check passa: comando de discovery listado em Gate Check Commands

**Tests**: none
**Gate**: discovery
**Commit**: `docs(design): confirmar caminho do binario do github-mcp-server`

---

#### T2: Configurar pyproject.toml

**What**: Criar `pyproject.toml` com as dependências pinadas do projeto (FastAPI, LangGraph, langchain-openrouter, pydantic-settings, fastmcp, etc.) e a configuração de ruff (lint + format), mypy e pytest, incluindo os markers customizados `e2e` e `live`.
**Where**: `pyproject.toml`
**Depends on**: none
**Reuses**: N/A (primeira config de toolchain do projeto)
**Requirement**: MCPO-07

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Todas as dependências necessárias ao Design estão listadas com versão pinada
- [x] Seções `[tool.ruff]`, `[tool.mypy]` e `[tool.pytest.ini_options]` configuradas
- [x] Markers `e2e` e `live` registrados em pytest para não gerar warning de marker desconhecido
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(deps): configurar pyproject.toml com pytest, ruff e mypy`

---

#### T3: Implementar settings.py

**What**: Implementar `Settings` (pydantic-settings) cobrindo todos os envs da spec (`REQUEST_TIMEOUT_S`, `MAX_REACT_ITERATIONS`, chaves de API, etc.) com os defaults definidos na spec.
**Where**: `src/orchestrator/settings.py`
**Depends on**: T2
**Reuses**: convenções de dependências/config de `pyproject.toml` (T2)
**Requirement**: MCPO-07 AC2, MCPO-03, MCPO-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Toda variável de ambiente citada na spec está mapeada em `Settings`, com o default correto
- [x] Instanciar `Settings()` sem `.env` não lança erro para as variáveis com default
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo os defaults e overrides por env passam (sem exclusões silenciosas)

**Tests**: unit
**Gate**: quick
**Commit**: `feat(config): adicionar settings com pydantic-settings`

---

#### T4: Implementar logger estruturado

**What**: Implementar logger JSON estruturado que anexa `request_id` a cada linha de log.
**Where**: `src/orchestrator/observability/logging.py`
**Depends on**: T2
**Reuses**: N/A (primeiro módulo de observability)
**Requirement**: MCPO-04 AC3

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Cada linha de log emitida é um JSON válido
- [x] `request_id` está presente em todo log emitido dentro do contexto de uma request
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo o formato JSON e a presença de `request_id` passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(observability): adicionar logger json estruturado`

---

#### T5: Implementar TraceRecorder

**What**: Implementar `TraceRecorder`, que acumula `steps`, deriva `used_tools` no formato `server.tool`, mede `duration_ms` e expõe `to_dict()` para serialização na resposta.
**Where**: `src/orchestrator/observability/trace.py`
**Depends on**: T2
**Reuses**: N/A (primeiro módulo de trace)
**Requirement**: MCPO-04 AC1/AC2

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `steps` acumula cada passo registrado, na ordem em que ocorreram
- [x] `used_tools` deriva corretamente no formato `server.tool`, sem duplicatas indevidas
- [x] `duration_ms` mede o tempo decorrido desde a criação do recorder
- [x] `to_dict()` produz um dicionário serializável em JSON
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo acumulação de steps, `used_tools` e `to_dict()` passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(observability): adicionar trace recorder`

---

### Phase 2: Configuração e cliente MCP

#### T6: Criar config/servers.yaml

**What**: Criar `config/servers.yaml` com a declaração dos servers `filesystem` e `github` (transport, url, timeout, enabled), conforme a topologia do Design.
**Where**: `config/servers.yaml`
**Depends on**: T2
**Reuses**: N/A (primeiro arquivo de config de servers)
**Requirement**: MCPO-02 AC4

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Os dois servers (`filesystem`, `github`) estão declarados com `transport`, `url`, `timeout` e `enabled`
- [x] O arquivo é YAML válido e carrega sem erro de parsing
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(config): adicionar servers.yaml`

---

#### T7: Implementar hierarquia de exceções do cliente MCP

**What**: Implementar a hierarquia de exceções do cliente MCP (ex.: erro de conexão, timeout, server desconhecido) que mapeia depois para os códigos do catálogo de erros.
**Where**: `src/orchestrator/mcp_client/exceptions.py`
**Depends on**: T2
**Reuses**: N/A (primeiro módulo do pacote `mcp_client`)
**Requirement**: MCPO-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Toda condição de erro de cliente MCP prevista no Design tem uma exceção dedicada
- [x] As exceções herdam de uma base comum do pacote `mcp_client`
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `feat(mcp-client): adicionar hierarquia de excecoes`

---

#### T8: Implementar registry do cliente MCP

**What**: Implementar `registry`: parse de `config/servers.yaml`, construção do `MultiServerMCPClient`, `discover()` com falha isolada por server (um server fora do ar não derruba os demais), `servers()` e `get_tools()`.
**Where**: `src/orchestrator/mcp_client/registry.py`
**Depends on**: T3, T6, T7
**Reuses**: `Settings` (T3), `config/servers.yaml` (T6), hierarquia de exceções (T7)
**Requirement**: MCPO-02 AC1/AC2/AC3

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `discover()` popula a lista de tools por server a partir do que está declarado em `servers.yaml`
- [x] Falha de um server individual durante `discover()` não interrompe a descoberta dos demais
- [x] `servers()` e `get_tools()` retornam o estado atual do registry
- [x] Gate check passa: `python -m pytest tests/integration -q`
- [x] Test count: testes de integração contra um server MCP falso real cobrindo sucesso, server fora do ar e timeout passam

**Tests**: integration
**Gate**: full
**Commit**: `feat(mcp-client): adicionar registry de servers mcp`

---

#### T9: Criar config/tool_policy.yaml

**What**: Criar `config/tool_policy.yaml` com a classificação write/read de cada tool e a allowlist de tools de escrita permitidas.
**Where**: `config/tool_policy.yaml`
**Depends on**: T2
**Reuses**: N/A (primeiro arquivo de política de tools)
**Requirement**: MCPO-08 AC1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Toda tool de escrita conhecida no Design está classificada como `write`
- [x] A allowlist reflete exatamente as tools de escrita autorizadas por padrão
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(config): adicionar tool_policy.yaml`

---

#### T10: Implementar policy de allowlist

**What**: Implementar `is_allowed()` e `is_write()`, que consultam `config/tool_policy.yaml` para decidir se uma tool pode ser executada.
**Where**: `src/orchestrator/mcp_client/policy.py`
**Depends on**: T9
**Reuses**: `config/tool_policy.yaml` (T9)
**Requirement**: MCPO-08 AC1/AC3

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `is_write()` classifica corretamente uma tool como escrita ou leitura conforme `tool_policy.yaml`
- [x] `is_allowed()` retorna `False` para toda tool de escrita fora da allowlist
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo `is_allowed()` e `is_write()` para tools dentro e fora da allowlist passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(mcp-client): adicionar policy de allowlist`

---

### Phase 3: Camada HTTP e contrato

#### T11: Implementar schemas pydantic da API

**What**: Implementar `TaskRequest` (campo `task` com tamanho 1-4000), `TaskResponse`, `ErrorResponse` e `Trace`, conforme o contrato fechado da spec.
**Where**: `src/orchestrator/api/schemas.py`
**Depends on**: T5
**Reuses**: formato de `to_dict()` do `TraceRecorder` (T5) como base do schema `Trace`
**Requirement**: MCPO-01, MCPO-04, edge case `INVALID_TASK`

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `TaskRequest` rejeita `task` vazio ou acima de 4000 caracteres
- [x] `TaskResponse`, `ErrorResponse` e `Trace` têm todos os campos exigidos pela spec
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo validação de `TaskRequest` (incluindo o edge case `INVALID_TASK`) e serialização dos demais schemas passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(api): adicionar schemas pydantic de request e response`

---

#### T12: Implementar autenticação por API key

**What**: Implementar a dependency de autenticação que valida o header `X-API-Key` contra o valor configurado.
**Where**: `src/orchestrator/api/auth.py`
**Depends on**: T3
**Reuses**: `Settings` (T3) para ler a API key configurada
**Requirement**: MCPO-06

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Request sem `X-API-Key` ou com valor incorreto é rejeitada
- [x] Request com `X-API-Key` correto passa pela dependency
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo header ausente, incorreto e correto passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(api): adicionar autenticacao por api key`

---

#### T13: Implementar exception handlers do catálogo de erros

**What**: Implementar os exception handlers que traduzem toda exceção prevista para um dos 8 códigos do catálogo fechado da spec, garantindo que `trace` esteja sempre presente na resposta e `finish_reason="error"` quando aplicável.
**Where**: `src/orchestrator/api/errors.py`
**Depends on**: T7, T11
**Reuses**: hierarquia de exceções do cliente MCP (T7), schema `ErrorResponse`/`Trace` (T11)
**Requirement**: MCPO-05 AC6, MCPO-04 AC1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Cada um dos 8 códigos de erro do catálogo tem um handler mapeado
- [x] Toda resposta de erro inclui `trace`, mesmo em falhas antes de qualquer execução de tool
- [x] `finish_reason="error"` está presente quando o AC exige
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo os 8 códigos de erro e a presença de `trace`/`finish_reason` passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(api): adicionar exception handlers do catalogo de erros`

---

#### T14: Implementar app factory e lifespan

**What**: Implementar a app factory do FastAPI com `lifespan` que roda a descoberta de tools na subida; se um server declarado em `servers.yaml` não resolver, a subida falha explicitamente em vez de subir incompleta em silêncio.
**Where**: `src/orchestrator/main.py`
**Depends on**: T8, T13
**Reuses**: `registry` (T8), exception handlers (T13)
**Requirement**: MCPO-02 AC1, edge case de configuração inválida

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `discover()` do registry roda durante o `lifespan` de subida da app
- [x] Server declarado em `servers.yaml` que não resolve faz a subida falhar com log de erro explícito
- [x] Exception handlers de T13 estão registrados na app
- [x] Gate check passa: `python -m pytest tests/integration -q`
- [x] Test count: testes de integração cobrindo subida com sucesso e subida com server inválido passam

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): adicionar app factory com lifespan de discovery`

---

#### T15: Implementar rota GET /servers

**What**: Implementar a rota `GET /servers`, que expõe o estado atual dos MCP servers descobertos pelo registry. Esta rota é o único ponto que combina `registry.servers()` (estrutura: nome, status, tools) com `policy.is_write()` (classificação real de escrita) para produzir o `write: bool` correto por tool — `registry.py` não conhece `tool_policy.yaml` e expõe um placeholder `write: False` documentado in loco (ver `.specs/STATE.md` → AD-007).
**Where**: `src/orchestrator/api/routes_servers.py`
**Depends on**: T14, T10
**Reuses**: app factory (T14), `registry.servers()` (T8), `policy.is_write()` (T10) para sobrescrever o `write:bool` real por tool
**Requirement**: MCPO-02 AC3

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `GET /servers` retorna a lista de servers com seu estado de descoberta
- [x] `tools[].write` reflete a classificação real de `policy.is_write()`, não o placeholder de `registry.py`
- [x] Gate check passa: `python -m pytest tests/integration -q`
- [x] Test count: teste de integração cobrindo o happy path de `GET /servers` (incluindo ao menos uma tool de escrita com `write: true`) passa

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): adicionar rota get /servers`

---

### Phase 4: Fundação do grafo

#### T16: Implementar estado do grafo

**What**: Implementar `OrchestratorState`, `TraceStep` e `ErrorInfo`, as estruturas de estado que o `StateGraph` do LangGraph vai propagar entre nós.
**Where**: `src/orchestrator/graph/state.py`
**Depends on**: T5
**Reuses**: formato de step do `TraceRecorder` (T5) como base de `TraceStep`
**Requirement**: MCPO-03, MCPO-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `OrchestratorState` contém todos os campos que os nós do Design precisam ler/escrever
- [x] `TraceStep` e `ErrorInfo` têm os campos exigidos pelo contrato de trace/erro da spec
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `feat(graph): adicionar estado do grafo`

---

#### T17: Implementar provider ChatOpenRouter

**What**: Implementar o wrapper `ChatOpenRouter` (AD-003) que encapsula o acesso ao LLM via OpenRouter, convertendo qualquer falha do provider em `LLM_PROVIDER_ERROR`.
**Where**: `src/orchestrator/llm/provider.py`
**Depends on**: T3, T7
**Reuses**: `Settings` (T3) para a API key/modelo, hierarquia de exceções (T7) para o mapeamento de erro
**Requirement**: MCPO-05 AC5

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Chamada ao LLM bem-sucedida retorna a resposta esperada pelo grafo
- [x] Falha do provider (timeout, erro HTTP, etc.) é convertida em `LLM_PROVIDER_ERROR`
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo chamada bem-sucedida e cada falha de provider mapeada passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(llm): adicionar provider chatopenrouter`

---

#### T18: Implementar montagem dinâmica do system prompt

**What**: Implementar a montagem do system prompt a partir do catálogo de tools descoberto em runtime, sem nenhum nome de server ou tool hardcoded (AD-005).
**Where**: `src/orchestrator/graph/prompts.py`
**Depends on**: T16
**Reuses**: `OrchestratorState` (T16)
**Requirement**: MCPO-01, MCPO-02 AC4

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] O prompt gerado lista exatamente as tools presentes no catálogo passado, sem nome hardcoded no código
- [x] Adicionar/remover uma tool do catálogo de entrada muda o prompt sem alterar este arquivo
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo a montagem do prompt com catálogos diferentes passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(graph): adicionar system prompt dinamico`

---

### Phase 5: Nós e roteamento do grafo

#### T19: Implementar nós prepare e agent

**What**: Implementar os nós `prepare` (monta o estado inicial a partir do `TaskRequest`) e `agent` (chama o LLM com o system prompt e o histórico para decidir a próxima ação).
**Where**: `src/orchestrator/graph/nodes.py`
**Depends on**: T16, T17, T18
**Reuses**: `OrchestratorState` (T16), `ChatOpenRouter` (T17), montagem do system prompt (T18)
**Requirement**: MCPO-01, MCPO-05 AC5

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `prepare` inicializa `OrchestratorState` a partir da `task` recebida
- [x] `agent` chama o LLM com o prompt montado por T18 e grava a decisão no estado
- [x] Falha do provider propaga como `LLM_PROVIDER_ERROR` (via T17)
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo `prepare` e `agent` (com LLM roteirizado/dublê) passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(graph): adicionar nos prepare e agent`

---

#### T20: Implementar route_after_agent

**What**: Implementar `route_after_agent`, a tabela-verdade dos 4 caminhos de roteamento pós-agente do Design §1.4 (chamar tool, bloquear por policy, finalizar com resultado, finalizar sem server adequado).
**Where**: `src/orchestrator/graph/nodes.py`
**Depends on**: T19
**Reuses**: `OrchestratorState` (T16), decisão do nó `agent` (T19)
**Requirement**: MCPO-03 AC2/AC3, MCPO-09

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Os 4 caminhos da tabela-verdade do Design §1.4 estão implementados e cobertos
- [x] Nenhum quinto caminho implícito é criado (roteamento é exaustivo e determinístico)
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: um teste por caminho da tabela-verdade (4 no mínimo) passa

**Tests**: unit
**Gate**: quick
**Commit**: `feat(graph): adicionar roteamento route_after_agent`

---

#### T21: Implementar nó tools

**What**: Implementar o nó `tools`, que executa a tool decidida pelo agente com timeout, 1 retry restrito a falha de transporte (nunca a falha de aplicação), acumulando em `steps[]` e incrementando `iterations`.
**Where**: `src/orchestrator/graph/nodes.py`
**Depends on**: T19
**Reuses**: `registry.get_tools()` (T8), `TraceStep` (T16)
**Requirement**: MCPO-03 AC1, MCPO-04 AC2, MCPO-05 AC1/AC2/AC3

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Execução de tool respeita o timeout configurado
- [x] Retry acontece exatamente 1 vez, e só para falha de transporte
- [x] Cada execução (sucesso ou falha) vira um item em `steps[]`
- [x] `iterations` incrementa a cada passagem pelo nó
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo sucesso, timeout, falha de transporte com retry e falha de aplicação sem retry passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(graph): adicionar no de execucao de tools`

---

#### T22: Implementar nó guard

**What**: Implementar o nó `guard`, que bloqueia a execução de uma tool de escrita fora da allowlist antes de qualquer chamada externa, registrando um step com `status: "blocked"` e retornando `TOOL_NOT_ALLOWED`.
**Where**: `src/orchestrator/graph/nodes.py`
**Depends on**: T10, T21
**Reuses**: `policy.is_allowed()` (T10), formato de step do nó `tools` (T21)
**Requirement**: MCPO-08 AC2

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Tool de escrita fora da allowlist é bloqueada antes de qualquer chamada ao MCP server
- [x] O step de bloqueio tem `status: "blocked"` e é registrado em `steps[]`
- [x] Erro `TOOL_NOT_ALLOWED` é retornado nesse caminho
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo bloqueio de tool não permitida e passagem de tool permitida passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(graph): adicionar no guard de allowlist`

---

#### T23: Implementar nó finalize

**What**: Implementar o nó `finalize`, único ponto do grafo autorizado a escrever `finish_reason` e `result` no estado; monta o envelope de erro quando o caminho terminou em falha.
**Where**: `src/orchestrator/graph/nodes.py`
**Depends on**: T20
**Reuses**: `ErrorResponse`/`Trace` (T11), `OrchestratorState` (T16)
**Requirement**: MCPO-01, MCPO-03 AC2, MCPO-09

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `finalize` é o único nó que escreve `finish_reason` e `result`
- [x] Caminho de sucesso produz `result` coerente com a decisão do agente
- [x] Caminho de erro produz o envelope de erro completo (com `trace`)
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: testes cobrindo finalize em caminho de sucesso e em caminho de erro passam

**Tests**: unit
**Gate**: quick
**Commit**: `feat(graph): adicionar no finalize`

---

#### T24: Implementar builder do grafo

**What**: Implementar `graph/builder.py`: monta o `StateGraph` com todos os nós e arestas, define `recursion_limit` e expõe `compile()` para produzir o grafo executável.
**Where**: `src/orchestrator/graph/builder.py`
**Depends on**: T20, T22, T23
**Reuses**: nós `prepare`/`agent` (T19), `route_after_agent` (T20), `guard` (T22), `finalize` (T23)
**Requirement**: MCPO-03 AC4

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Todos os nós das tasks T19-T23 estão conectados no `StateGraph` conforme o Design
- [x] `recursion_limit` está configurado de acordo com `MAX_REACT_ITERATIONS`
- [x] `compile()` retorna um grafo executável ponta a ponta
- [x] Gate check passa: `python -m pytest tests/unit -q`
- [x] Test count: teste de integração do grafo completo (happy path + caminho de erro) passa

**Tests**: unit
**Gate**: quick
**Commit**: `feat(graph): adicionar builder do stategraph`

---

### Phase 6: Endpoint principal

#### T25: Implementar rota POST /tasks

**What**: Implementar `POST /tasks`: exige autenticação, envolve a execução do grafo em `asyncio.timeout(REQUEST_TIMEOUT_S)` e retorna `trace` completo na resposta.
**Where**: `src/orchestrator/api/routes_tasks.py`
**Depends on**: T12, T14, T24
**Reuses**: dependency de auth (T12), app factory (T14), grafo compilado (T24)
**Requirement**: MCPO-01, MCPO-04, MCPO-05 AC4, MCPO-06

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Request sem autenticação válida é rejeitada antes de invocar o grafo
- [x] Request que excede `REQUEST_TIMEOUT_S` retorna o erro de timeout do catálogo, não um 500 não tratado
- [x] Toda resposta 200 contém `trace` completo e parseável
- [x] Gate check passa: `python -m pytest tests/integration -q`
- [x] Test count: testes de integração cobrindo happy path, auth inválida e timeout passam

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): adicionar rota post /tasks`

---

#### T26: Implementar rota GET /health agregado

**What**: Implementar `GET /health`, que agrega o próprio estado do gateway com o estado de descoberta de cada MCP server.
**Where**: `src/orchestrator/api/routes_health.py`
**Depends on**: T25
**Reuses**: `registry.servers()` (T8), convenção de rota de T25
**Requirement**: MCPO-11

**Tools**:

- MCP: NONE
- Skill: NONE

> ⚠️ **Lembrete AD-011** (`STATE.md`): no máximo 1 teste por arquivo pode invocar uma tool MCP
> real via `MultiServerMCPClient`/`server_configs`. Se este arquivo de teste também exercitar
> `POST /tasks` de ponta a ponta, use `create_app(tools_by_server={...})` com uma tool falsa
> (`_FakeReadFileTool` em `test_routes_tasks.py`) em qualquer teste adicional — não uma segunda
> conexão MCP real.

**Done when**:

- [x] `GET /health` reporta o estado agregado do gateway e de cada MCP server
- [x] Um MCP server fora do ar aparece refletido no health, sem derrubar a rota
- [x] Gate check passa: `python -m pytest tests/integration -q`
- [x] Test count: testes de integração cobrindo todos-servidores-ok e um-servidor-fora-do-ar passam

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): adicionar rota get /health agregado`

---

### Phase 7: Containers e stack

#### T27: Implementar shim stdio↔Streamable HTTP

**What**: Implementar o shim (`create_proxy` + `StdioTransport`) que traduz stdio para Streamable HTTP (AD-001), incluindo a validação de header `Origin` levantada como hardening no Design.
**Where**: `shim/mcp_http_shim.py`
**Depends on**: T2
**Reuses**: N/A (primeiro módulo do shim); segue o padrão `create_proxy` do Design conforme AD-001
**Requirement**: MCPO-07, AD-001

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `create_proxy` traduz corretamente uma sessão stdio para Streamable HTTP
- [x] Request com `Origin` não permitido é rejeitada
- [x] Gate check passa: `python -m pytest tests/integration -q`
- [x] Test count: testes de integração contra um server MCP falso real cobrindo tradução de protocolo e rejeição por `Origin` passam

**Tests**: integration
**Gate**: full
**Commit**: `feat(shim): adicionar shim stdio para streamable http`

---

#### T28: Criar imagem base do shim

**What**: Criar `docker/shim-base/Dockerfile`, a imagem base reutilizada pelos containers de MCP server que rodam atrás do shim.
**Where**: `docker/shim-base/Dockerfile`
**Depends on**: T27
**Reuses**: shim (T27)
**Requirement**: MCPO-07 AC1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A imagem builda sem erro e contém o shim de T27 pronto para uso
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(docker): adicionar imagem base do shim`

---

#### T29: Criar imagem do server filesystem

**What**: Criar `docker/filesystem/Dockerfile`, baseada na imagem do shim, empacotando o MCP server `filesystem` (Node) com a versão do pacote pinada.
**Where**: `docker/filesystem/Dockerfile`
**Depends on**: T28
**Reuses**: imagem base do shim (T28)
**Requirement**: MCPO-07 AC1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A imagem builda sem erro com o pacote do server `filesystem` na versão pinada
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(docker): adicionar imagem do server filesystem`

---

#### T30: Criar imagem do server github

**What**: Criar `docker/github/Dockerfile`, baseada na imagem do shim, usando o caminho do binário confirmado em T1 (com o fallback de build documentado se necessário).
**Where**: `docker/github/Dockerfile`
**Depends on**: T1, T28
**Reuses**: caminho do binário confirmado (T1), imagem base do shim (T28)
**Requirement**: MCPO-07 AC1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A imagem builda sem erro usando o caminho de binário confirmado em T1
- [x] Se o binário não estiver disponível pronto, o fallback de build documentado em T1 está implementado
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(docker): adicionar imagem do server github`

---

#### T31: Criar imagem do gateway

**What**: Criar o `Dockerfile` do gateway (a aplicação FastAPI/LangGraph deste repositório).
**Where**: `Dockerfile`
**Depends on**: T26
**Reuses**: rotas e app factory do gateway (T14, T25, T26)
**Requirement**: MCPO-07 AC1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A imagem builda sem erro e sobe a aplicação FastAPI completa
- [x] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(docker): adicionar imagem do gateway`

---

#### T32: Criar .env.example

**What**: Criar `.env.example` com todas as variáveis de ambiente do projeto, incluindo a nota de que `GITHUB_READ_ONLY` e a allowlist de `tool_policy.yaml` são portões independentes (um não substitui o outro).
**Where**: `.env.example`
**Depends on**: T3
**Reuses**: `Settings` (T3) como fonte de verdade das variáveis
**Requirement**: MCPO-07 AC2

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Toda variável de `Settings` (T3) está presente em `.env.example` com um valor de exemplo
- [ ] A nota sobre `GITHUB_READ_ONLY` vs. allowlist está documentada no arquivo
- [ ] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(config): adicionar .env.example`

---

#### T33: Criar docker-compose.yml

**What**: Criar `docker-compose.yml` com os 3 serviços (gateway, filesystem, github), healthchecks TCP, rede interna dedicada e apenas a porta do gateway publicada no host.
**Where**: `docker-compose.yml`
**Depends on**: T29, T30, T31, T32
**Reuses**: imagens de T29/T30/T31, variáveis de `.env.example` (T32)
**Requirement**: MCPO-07 AC1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Os 3 serviços estão declarados com healthcheck TCP
- [ ] Os MCP servers estão só na rede interna; apenas a porta do gateway é publicada no host
- [ ] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `chore(docker): adicionar docker-compose da stack completa`

---

#### T34: Implementar smoke test E2E

**What**: Implementar o smoke test E2E (`scripts/smoke_test.py`) com pelo menos 1 caso de sucesso por MCP server, rodado contra a stack subida via compose.
**Where**: `scripts/smoke_test.py`
**Depends on**: T33
**Reuses**: `docker-compose.yml` (T33)
**Requirement**: MCPO-07 AC3

**Tools**:

- MCP: NONE
- Skill: NONE

> ⚠️ **Lembrete AD-011** (`STATE.md`): condicional aqui — o smoke test roda contra containers
> reais via HTTP, fora do processo pytest normal, então o bug (múltiplas conexões MCP reais em
> event loops diferentes do MESMO processo Python) provavelmente não se aplica. Mas se
> `tests/e2e/` acabar instanciando `MultiServerMCPClient` diretamente dentro do mesmo processo
> pytest (em vez de só bater via HTTP no gateway), reavaliar: no máximo 1 teste por arquivo pode
> invocar uma tool MCP real nesse cenário.

**Done when**:

- [ ] Existe pelo menos 1 caso de smoke test por MCP server declarado (`filesystem`, `github`)
- [ ] O script sobe a stack, roda os casos e falha com saída não-zero se algum caso falhar
- [ ] Gate check passa: `docker compose up -d && python scripts/smoke_test.py && python -m pytest tests/e2e -q -m e2e`

**Tests**: e2e
**Gate**: e2e
**Commit**: `test(e2e): adicionar smoke test da stack`

---

### Phase 8: Avaliação de roteamento

#### T35: Criar dataset de avaliação de roteamento

**What**: Criar `tests/eval/dataset.json` com 15 casos rotulados: 5 de roteamento para `filesystem`, 5 para `github`, 2 multi-step (envolvendo os dois servers) e 3 de `no_suitable_server`.
**Where**: `tests/eval/dataset.json`
**Depends on**: T24
**Reuses**: grafo compilado (T24) como sistema sob teste
**Requirement**: MCPO-10 AC1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] O dataset tem exatamente 15 casos, na distribuição especificada (5/5/2/3)
- [ ] Cada caso tem o rótulo esperado de roteamento
- [ ] Gate check passa: `ruff check . && ruff format --check . && mypy src`

**Tests**: none
**Gate**: build
**Commit**: `test(eval): adicionar dataset de avaliacao de roteamento`

---

#### T36: Implementar suíte de avaliação de roteamento

**What**: Implementar `tests/eval/test_routing.py`, rodando o dataset de T35 contra o grafo em modo CI (fixtures de resposta do LLM gravadas, offline) com gate de acurácia ≥ 90%; falha o build se a acurácia cair abaixo disso.
**Where**: `tests/eval/test_routing.py`
**Depends on**: T35
**Reuses**: dataset (T35), modo CI de fixtures gravadas (AD-004)
**Requirement**: MCPO-10 AC2/AC3

**Tools**:

- MCP: NONE
- Skill: NONE

> ⚠️ **Lembrete AD-011** (`STATE.md`): condicional aqui — se as tools do grafo nesta suíte forem
> falsas (esperado, já que o objetivo é testar roteamento/LLM via fixtures do AD-004, não MCP
> real), sem risco. Mas se algum caso do dataset acabar rodando contra um MCP server real dentro
> do mesmo processo pytest, vale a regra: no máximo 1 teste por arquivo pode invocar uma tool MCP
> real via `MultiServerMCPClient`/`server_configs` — use `create_app(tools_by_server={...})` com
> tool falsa nos demais.

**Done when**:

- [ ] A suíte roda os 15 casos do dataset em modo CI (offline, fixtures gravadas), sem chamada real ao OpenRouter
- [ ] Acurácia ≥ 90% passa; um valor abaixo disso derruba a suíte com saída não-zero
- [ ] Checklist do AD-004 confirmado: fixtures regravadas nesta mesma task caso `graph/prompts.py` já tenha mudado até aqui
- [ ] Gate check passa (AD-012 -- invocações separadas, não um comando combinado): `python -m pytest tests/unit -q && python -m pytest tests/integration -q && python -m pytest tests/eval -q`

**Tests**: eval
**Gate**: full
**Commit**: `test(eval): adicionar suite de avaliacao com gate de acuracia`

---

## Phase Execution Map

Representação visual da ordem das tasks. As fases rodam em sequência, e as tasks dentro de uma
fase rodam em ordem:

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8

Phase 1: T1, T2, T3, T4, T5
Phase 2: T6, T7, T8, T9, T10
Phase 3: T11, T12, T13, T14, T15
Phase 4: T16, T17, T18
Phase 5: T19, T20, T21, T22, T23, T24
Phase 6: T25, T26
Phase 7: T27, T28, T29, T30, T31, T32, T33, T34
Phase 8: T35, T36
```

A execução é estritamente sequencial - não há paralelismo intra-fase. Um único agente (ou worker de
lote) trabalha uma task por vez, em ordem.

**Como a execução por fases funciona:**

No Execute, o agente conta o total de tasks e empacota fases em **lotes orçados por task** (~7
tasks por worker, fases inteiras). Um lote nunca corta uma fase ao meio. Quando o empacotamento
resulta em mais de um lote (> ~8 tasks), o agente oferece o despacho de sub-agentes por lote. Lotes
rodam sequencialmente: cada worker executa todas as suas tasks em ordem, depois reporta um resumo
compacto antes do próximo lote começar. Ver `sub-agents.md` da skill `tlc-spec-driven` para o
modelo completo.

Com 36 tasks, o empacotamento em lotes de ~7 tasks por fase inteira dá 5 lotes: F1+F2 (10 tasks) ·
F3+F4 (8 tasks) · F5 (6 tasks) · F6+F7 (10 tasks) · F8 (2 tasks). Essa oferta formal só acontece
depois que o `tasks.md` for aprovado, na Fase 5 (Execute) — nada é despachado sem aceite explícito.

---

## Task Granularity Check

Antes de aprovar as tasks, verificar se são granulares o suficiente:

| Task | Scope | Status |
| --- | --- | --- |
| T1: Confirmar caminho do binário | 1 comando de discovery + 1 atualização em `design.md` | ✅ Granular |
| T2: Configurar pyproject.toml | 1 arquivo de config | ✅ Granular |
| T3: Implementar settings.py | 1 módulo | ✅ Granular |
| T4: Implementar logger estruturado | 1 módulo | ✅ Granular |
| T5: Implementar TraceRecorder | 1 módulo | ✅ Granular |
| T6: Criar config/servers.yaml | 1 arquivo de config | ✅ Granular |
| T7: Implementar hierarquia de exceções | 1 módulo | ✅ Granular |
| T8: Implementar registry do cliente MCP | 1 módulo | ✅ Granular |
| T9: Criar config/tool_policy.yaml | 1 arquivo de config | ✅ Granular |
| T10: Implementar policy de allowlist | 1 módulo | ✅ Granular |
| T11: Implementar schemas pydantic da API | 1 módulo | ✅ Granular |
| T12: Implementar autenticação por API key | 1 módulo | ✅ Granular |
| T13: Implementar exception handlers | 1 módulo | ✅ Granular |
| T14: Implementar app factory e lifespan | 1 módulo | ✅ Granular |
| T15: Implementar rota GET /servers | 1 rota | ✅ Granular |
| T16: Implementar estado do grafo | 1 módulo | ✅ Granular |
| T17: Implementar provider ChatOpenRouter | 1 módulo | ✅ Granular |
| T18: Implementar system prompt dinâmico | 1 módulo | ✅ Granular |
| T19: Implementar nós prepare e agent | 2 nós coesos, 1 arquivo (`nodes.py`) | ✅ Granular |
| T20: Implementar route_after_agent | 1 função de roteamento | ✅ Granular |
| T21: Implementar nó tools | 1 nó | ✅ Granular |
| T22: Implementar nó guard | 1 nó | ✅ Granular |
| T23: Implementar nó finalize | 1 nó | ✅ Granular |
| T24: Implementar builder do grafo | 1 módulo | ✅ Granular |
| T25: Implementar rota POST /tasks | 1 rota | ✅ Granular |
| T26: Implementar rota GET /health | 1 rota | ✅ Granular |
| T27: Implementar shim stdio↔Streamable HTTP | 1 módulo | ✅ Granular |
| T28: Criar imagem base do shim | 1 Dockerfile | ✅ Granular |
| T29: Criar imagem do server filesystem | 1 Dockerfile | ✅ Granular |
| T30: Criar imagem do server github | 1 Dockerfile | ✅ Granular |
| T31: Criar imagem do gateway | 1 Dockerfile | ✅ Granular |
| T32: Criar .env.example | 1 arquivo | ✅ Granular |
| T33: Criar docker-compose.yml | 1 arquivo | ✅ Granular |
| T34: Implementar smoke test E2E | 1 script | ✅ Granular |
| T35: Criar dataset de avaliação | 1 arquivo de dados | ✅ Granular |
| T36: Implementar suíte de avaliação | 1 suíte de teste | ✅ Granular |

**Granularity check**:

- ✅ 1 componente / 1 função / 1 endpoint = Bom
- ⚠️ 2-3 coisas relacionadas no mesmo arquivo = OK se coeso (caso de T19: `prepare` e `agent` são o
  mesmo par de nós de entrada do grafo, sempre editados juntos)
- ❌ Múltiplos componentes ou arquivos = deve ser dividido (nenhum caso neste plano)

---

## Diagram-Definition Cross-Check

Antes de aprovar as tasks, verificar que o diagrama de execução é consistente com as definições de
task. Dependências cross-phase (backward) são validadas pelo forward-phase check do
`validate_tasks.py` e não precisam de seta no diagrama de fase — diagramas são desenhados por fase,
então arestas cross-phase estão fora do escopo de cada diagrama individual.

| Task | Depends On (task body) | Diagram Shows | Status |
| --- | --- | --- | --- |
| T1 | none | (nó isolado, sem seta) | ✅ Match |
| T2 | none | (alimenta T3, T4, T5 via `T2 → T3/T4/T5`) | ✅ Match |
| T3 | T2 | `T2 → T3` | ✅ Match |
| T4 | T2 | `T2 → T4` | ✅ Match |
| T5 | T2 | `T2 → T5` | ✅ Match |
| T6 | T2 (cross-phase) | — (cross-phase, sem seta necessária) | ✅ Match |
| T7 | T2 (cross-phase) | — (cross-phase) | ✅ Match |
| T8 | T3 (cross-phase), T6, T7 | `T6 → T8`, `T7 → T8` | ✅ Match |
| T9 | T2 (cross-phase) | — (cross-phase) | ✅ Match |
| T10 | T9 | `T9 → T10` | ✅ Match |
| T11 | T5 (cross-phase) | — (cross-phase) | ✅ Match |
| T12 | T3 (cross-phase) | — (cross-phase) | ✅ Match |
| T13 | T7 (cross-phase), T11 | `T11 → T13` | ✅ Match |
| T14 | T8 (cross-phase), T13 | `T13 → T14` | ✅ Match |
| T15 | T14, T10 (cross-phase, corrigido no Execute — ver AD-007) | `T14 → T15` | ✅ Match |
| T16 | T5 (cross-phase) | — (cross-phase) | ✅ Match |
| T17 | T3, T7 (ambas cross-phase) | — (cross-phase) | ✅ Match |
| T18 | T16 | `T16 → T18` | ✅ Match |
| T19 | T16, T17, T18 (todas cross-phase) | — (cross-phase) | ✅ Match |
| T20 | T19 | `T19 → T20` | ✅ Match |
| T21 | T19 | `T19 → T21` | ✅ Match |
| T22 | T10 (cross-phase), T21 | `T21 → T22` | ✅ Match |
| T23 | T20 | `T20 → T23` | ✅ Match |
| T24 | T20, T22, T23 | `T20 → T24`, `T22 → T24`, `T23 → T24` | ✅ Match |
| T25 | T12, T14, T24 (todas cross-phase) | — (cross-phase) | ✅ Match |
| T26 | T25 | `T25 → T26` | ✅ Match |
| T27 | T2 (cross-phase) | — (cross-phase) | ✅ Match |
| T28 | T27 | `T27 → T28` | ✅ Match |
| T29 | T28 | `T28 → T29` | ✅ Match |
| T30 | T1 (cross-phase), T28 | `T28 → T30` | ✅ Match |
| T31 | T26 (cross-phase) | — (cross-phase) | ✅ Match |
| T32 | T3 (cross-phase) | — (cross-phase) | ✅ Match |
| T33 | T29, T30, T31, T32 | `T29 → T33`, `T30 → T33`, `T31 → T33`, `T32 → T33` | ✅ Match |
| T34 | T33 | `T33 → T34` | ✅ Match |
| T35 | T24 (cross-phase) | — (cross-phase) | ✅ Match |
| T36 | T35 | `T35 → T36` | ✅ Match |

**Rules:** toda `Depends on` intra-fase tem seta correspondente no diagrama; toda seta do diagrama
corresponde a um `Depends on` da task de destino; nenhuma task depende de uma task de fase
posterior.

---

## Test Co-location Validation

Antes de aprovar as tasks, verificar que o campo `Tests` de CADA task é consistente com a Test
Coverage Matrix gerada acima.

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1: Confirmar binário | Config/schema/infra (`design.md`, discovery) | none | none | ✅ OK |
| T2: pyproject.toml | Config/schema/infra | none | none | ✅ OK |
| T3: settings.py | Lógica pura | unit | unit | ✅ OK |
| T4: logging.py | Lógica pura | unit | unit | ✅ OK |
| T5: trace.py | Lógica pura | unit | unit | ✅ OK |
| T6: servers.yaml | Config/schema/infra | none | none | ✅ OK |
| T7: exceptions.py | Config/schema/infra (classes de exceção, sem branch) | none | none | ✅ OK |
| T8: registry.py | Cliente MCP e transporte | integration | integration | ✅ OK |
| T9: tool_policy.yaml | Config/schema/infra | none | none | ✅ OK |
| T10: policy.py | Lógica pura | unit | unit | ✅ OK |
| T11: schemas.py | Lógica pura | unit | unit | ✅ OK |
| T12: auth.py | Lógica pura | unit | unit | ✅ OK |
| T13: errors.py | Lógica pura | unit | unit | ✅ OK |
| T14: main.py | Rotas HTTP | integration | integration | ✅ OK |
| T15: routes_servers.py | Rotas HTTP | integration | integration | ✅ OK |
| T16: state.py | Config/schema/infra | none | none | ✅ OK |
| T17: provider.py | Nós do grafo e roteamento | unit | unit | ✅ OK |
| T18: prompts.py | Nós do grafo e roteamento | unit | unit | ✅ OK |
| T19: nodes.py (prepare, agent) | Nós do grafo e roteamento | unit | unit | ✅ OK |
| T20: nodes.py (route_after_agent) | Nós do grafo e roteamento | unit | unit | ✅ OK |
| T21: nodes.py (tools) | Nós do grafo e roteamento | unit | unit | ✅ OK |
| T22: nodes.py (guard) | Nós do grafo e roteamento | unit | unit | ✅ OK |
| T23: nodes.py (finalize) | Nós do grafo e roteamento | unit | unit | ✅ OK |
| T24: builder.py | Nós do grafo e roteamento | unit | unit | ✅ OK |
| T25: routes_tasks.py | Rotas HTTP | integration | integration | ✅ OK |
| T26: routes_health.py | Rotas HTTP | integration | integration | ✅ OK |
| T27: mcp_http_shim.py | Cliente MCP e transporte | integration | integration | ✅ OK |
| T28: Dockerfile (shim-base) | Config/schema/infra | none | none | ✅ OK |
| T29: Dockerfile (filesystem) | Config/schema/infra | none | none | ✅ OK |
| T30: Dockerfile (github) | Config/schema/infra | none | none | ✅ OK |
| T31: Dockerfile (gateway) | Config/schema/infra | none | none | ✅ OK |
| T32: .env.example | Config/schema/infra | none | none | ✅ OK |
| T33: docker-compose.yml | Config/schema/infra | none | none | ✅ OK |
| T34: smoke_test.py | Stack E2E | e2e | e2e | ✅ OK |
| T35: dataset.json | Config/schema/infra | none | none | ✅ OK |
| T36: test_routing.py | Avaliação de roteamento | eval | eval | ✅ OK |

**Rules:** "testado em outra task" não é justificativa válida para `Tests: none`; `Tests: none` só é
válido quando a matriz diz `none` para aquela camada; nenhuma ❌ VIOLATION nesta tabela.

---

## Requisitos fora do escopo destas tasks

**MCPO-12** (P3: limite de custo/tokens por request) está **deliberadamente fora** desta quebra em
tasks. Foi formalmente adiado para v1.1 via **AD-006** (`STATE.md` → `## Decisions`): o AC exige
`error.code = "TOKEN_BUDGET_EXCEEDED"`, código ausente do catálogo fechado de 8 erros já validado na
Fase 3; reabrir esse contrato por um requisito P3 não se paga. Os limites já existentes
(`MAX_REACT_ITERATIONS=5`, `REQUEST_TIMEOUT_S=120`, ver T3) já fornecem um teto grosseiro de custo
por request. Ver `spec.md` → `## Requirement Traceability` (status `Deferred`) e `STATE.md` → AD-006
para a decisão completa.

