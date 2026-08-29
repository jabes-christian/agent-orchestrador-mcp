# Agente Orquestrador de MCP Servers Specification

## Problem Statement

Para uma aplicação consumir capacidades expostas por MCP servers (arquivos, GitHub, APIs externas), hoje é preciso saber de antemão qual server e qual tool chamar, acoplando esse conhecimento ao código cliente. Cada novo server exige mudança no cliente. Este feature inverte essa relação: o cliente descreve a tarefa em linguagem natural via API HTTP, e um agente central (grafo LangGraph) decide em tempo de execução quais MCP servers e tools usar, executa e devolve o resultado tratado com um rastro de decisão auditável.

## Goals

- [ ] Um único endpoint recebe tarefa em linguagem natural e devolve resultado resolvido via MCP, sem o cliente conhecer servers ou tools
- [ ] Adicionar um novo MCP server é uma mudança de configuração (compose + arquivo de config), não de código do grafo
- [ ] Toda resposta 200 carrega um trace auditável: servers consultados, tools chamadas com argumentos, duração, tentativas e motivo da decisão final
- [ ] Falha ou timeout de um MCP server nunca derruba o request com erro não tratado — sempre erro estruturado com código estável
- [ ] Acurácia de roteamento ≥ 90% no dataset de avaliação fixo (15 casos rotulados, LLM mockado)
- [ ] `docker compose up` sobe gateway + MCP servers e o smoke test end-to-end passa

## Out of Scope

| Feature | Reason |
| --- | --- |
| Persistência de conversa / checkpointer LangGraph | Stateless por request; cliente reenvia contexto se precisar de continuidade |
| Descoberta dinâmica de MCP servers na rede (mDNS, registry) | v1 descobre apenas o que está declarado em configuração no docker-compose |
| MCP servers próprios/customizados | v1 usa apenas servers oficiais/públicos (filesystem, github) |
| Seleção multi-modelo / roteamento entre LLMs | Um único modelo via OpenRouter |
| Human-in-the-loop para aprovar ações destrutivas | Mitigado por allowlist de tools de escrita; confirmação humana é v2 |
| UI / frontend | v1 é API-only |
| Multi-tenancy, quotas por usuário, billing | API key única de serviço |
| Cache de resultados de tools | Otimização prematura sem dados de uso |
| Autenticação OAuth do protocolo MCP | Servers rodam na rede interna do docker-compose |
| Streaming (SSE) da resposta | Decidido nesta fase: endpoint síncrono na v1 |
| Rate limiting por cliente | Serviço interno com API key única; ver Assumptions |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Streaming vs síncrono | Síncrono — um único JSON por request | Mais simples de testar (inclui suíte de avaliação D7), casa com stateless-por-request; decidido com o usuário na Fase 2 | y |
| Limite de iterações do loop ReAct | 5, configurável via env `MAX_REACT_ITERATIONS` | Cobre tarefas de 2-3 tools com folga; evita loop infinito e custo de tokens | y |
| Timeout por chamada de tool MCP | 30s, configurável via env `MCP_TOOL_TIMEOUT_S` | Cobre chamadas de rede ao GitHub sem travar o request inteiro | y |
| Timeout global do request | 120s, configurável via env `REQUEST_TIMEOUT_S` | Teto para 5 iterações + chamadas ao LLM | y |
| Retry por chamada de tool | 1 retry automático apenas em erro de transporte/timeout (conexão recusada, timeout de rede); nunca em erro de negócio (4xx da tool, validação) | Erro de negócio é determinístico — repetir não muda o resultado e só gasta tempo/tokens | y |
| Formato do envelope de erro | JSON `{ "error": { "code": str, "message": str }, "trace": {...} }` | Código estável permite tratamento programático no cliente; trace sempre presente mesmo em erro, para debug | y |
| Idempotência de request | N/A — serviço stateless, sem escrita transacional própria; cliente é responsável por não duplicar POSTs com efeito colateral | Sem estado persistido entre requests, não há chave de dedup a manter | y |
| Rate limiting | N/A na v1 — serviço interno, uma única API key de serviço | Multi-tenancy e quotas são non-goal explícito da v1 | y |
| Concorrência entre requests | Cada request usa sua própria sessão/conexão MCP (sem estado compartilhado); requests concorrentes são isolados por construção | Grafo é stateless por request — não há necessidade de lock ou fila | y |
| Ciclo de vida de dados | N/A — nada persistido além de logs estruturados (rotação de log é responsabilidade de infra, fora do escopo do código) | Stateless na v1 | y |
| Idioma da resposta | Segue o idioma da tarefa recebida (responsabilidade do prompt do LLM, sem parâmetro explícito) | Sem configuração extra necessária | y |
| Tamanho máximo do campo `task` | 4000 caracteres | Limite generoso para linguagem natural, baixo o suficiente para evitar abuso de payload | y |
| Autenticação | Header `X-API-Key` estático, validado contra env `ORCHESTRATOR_API_KEY` | Fechado no PRD (D3) | y |

**Open questions:** none — todas resolvidas ou registradas acima.

---

## Contrato da API (fechado nesta fase)

### `POST /tasks`

**Request:**
```json
{
  "task": "string, 1-4000 caracteres, obrigatório"
}
```

**Response 200:**
```json
{
  "result": "string — resposta final para o usuário",
  "trace": {
    "request_id": "uuid",
    "iterations": 2,
    "steps": [
      {
        "step": 1,
        "server": "filesystem",
        "tool": "read_file",
        "arguments": {"path": "README.md"},
        "duration_ms": 120,
        "attempt": 1,
        "status": "success"
      }
    ],
    "used_tools": ["filesystem.read_file"],
    "finish_reason": "completed | no_suitable_server | max_iterations_reached",
    "duration_ms": 1450
  }
}
```

**Response de erro (4xx/5xx):**
```json
{
  "error": {
    "code": "STRING_CONSTANT",
    "message": "human-readable"
  },
  "trace": {
    "...": "mesmo formato acima, sempre presente",
    "finish_reason": "error"
  }
}
```

**Nota (adicionada na Fase 3 — Design):** `trace.finish_reason` aceita um quarto valor, `"error"`, exclusivo de respostas 4xx/5xx — os três valores originais (`completed`, `no_suitable_server`, `max_iterations_reached`) só ocorrem em HTTP 200. Quando `finish_reason = "error"`, o código específico do erro vive em `error.code` (catálogo abaixo), nunca em `finish_reason`. Enum completo: `"completed" | "no_suitable_server" | "max_iterations_reached" | "error"`.

**Códigos de erro estáveis (catálogo mínimo da v1):**

| HTTP | `error.code` | Quando |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | `X-API-Key` ausente ou inválida |
| 422 | `INVALID_TASK` | `task` vazio, ausente, ou > 4000 caracteres |
| 502 | `MCP_SERVER_UNAVAILABLE` | MCP server necessário está indisponível/não responde à conexão |
| 504 | `MCP_TOOL_TIMEOUT` | chamada de tool excedeu `MCP_TOOL_TIMEOUT_S` após retry |
| 504 | `REQUEST_TIMEOUT` | request excedeu `REQUEST_TIMEOUT_S` |
| 403 | `TOOL_NOT_ALLOWED` | tool de escrita fora da allowlist foi requisitada pelo agente |
| 502 | `LLM_PROVIDER_ERROR` | OpenRouter indisponível ou retornou erro |
| 500 | `INTERNAL_ERROR` | qualquer falha não classificada acima |

### `GET /servers`

**Response 200:**
```json
{
  "servers": [
    {
      "name": "filesystem",
      "status": "healthy | unhealthy",
      "tools": [
        {"name": "read_file", "description": "...", "write": false},
        {"name": "write_file", "description": "...", "write": true}
      ]
    }
  ]
}
```

### `GET /health` (P3)

Reporta status agregado do gateway e por-server.

---

## User Stories

### P1: Resolver tarefa em linguagem natural via MCP ⭐ MVP

**User Story**: Como desenvolvedor integrador, quero enviar uma tarefa em linguagem natural para um endpoint e receber o resultado já resolvido, para não precisar saber qual MCP server ou tool atende àquela tarefa.

**Why P1**: É o objetivo central do produto — sem isso não há meta-agent.

**Acceptance Criteria**:

1. WHEN o cliente envia `POST /tasks` com um `task` válido e `X-API-Key` correta THEN o sistema SHALL retornar HTTP 200 com `result` (string não vazia) e `trace` conforme o contrato definido
2. WHEN a tarefa é resolvível por uma única tool de um MCP server configurado THEN o sistema SHALL incluir exatamente essa tool em `trace.used_tools`
3. The system SHALL responder de forma síncrona — um único corpo JSON por request, sem streaming, dentro do timeout de `REQUEST_TIMEOUT_S`

**Independent Test**: `POST /tasks` com `{"task": "liste os arquivos do diretório de trabalho"}` retorna 200 com listagem no `result` e `trace.used_tools` contendo `filesystem.list_directory` (ou tool equivalente exposta pelo server).

---

### P1: Descoberta de servers e tools por configuração ⭐ MVP

**User Story**: Como operador, quero que o agente descubra na inicialização quais MCP servers estão configurados e quais tools cada um expõe, para adicionar servers sem alterar o código do grafo.

**Why P1**: Sustenta o Goal G2 (extensibilidade por configuração) — sem isso, cada server novo exige releitura e alteração do código do grafo.

**Acceptance Criteria**:

1. WHEN o gateway inicia THEN o sistema SHALL conectar a cada MCP server declarado na configuração e listar suas tools disponíveis
2. IF um MCP server declarado na configuração falha ao conectar na inicialização THEN o sistema SHALL subir mesmo assim, marcar aquele server como `unhealthy` em `GET /servers`, e seguir operando com os servers saudáveis
3. WHEN o cliente chama `GET /servers` THEN o sistema SHALL retornar cada server configurado com `status` e lista de `tools` (nome, descrição, `write: bool`)
4. The system SHALL determinar disponibilidade de servers/tools inteiramente a partir da configuração (docker-compose + arquivo de servers) — nenhuma tool ou server usado pelo grafo pode vir de código hardcoded

**Independent Test**: subir o stack com `docker compose up -d`, chamar `GET /servers` e confirmar que `filesystem` e `github` aparecem com `status: "healthy"` e suas tools reais.

---

### P1: Loop ReAct limitado com múltiplas tools ⭐ MVP

**User Story**: Como desenvolvedor, quero que o agente encadeie até N chamadas de tool reavaliando o resultado a cada passo, para resolver tarefas que exigem mais de um passo.

**Why P1**: Diferencia o produto de um simples roteador de intenção — é o que o torna um "meta-agent" de fato.

**Acceptance Criteria**:

1. WHEN uma tarefa requer mais de uma chamada de tool THEN o sistema SHALL encadear as chamadas necessárias, reavaliando o progresso após cada resultado de tool, até no máximo `MAX_REACT_ITERATIONS` iterações
2. IF o loop atinge `MAX_REACT_ITERATIONS` sem concluir a tarefa THEN o sistema SHALL encerrar o loop, retornar HTTP 200 com o melhor resultado parcial disponível em `result`, e `trace.finish_reason = "max_iterations_reached"`
3. WHEN o loop termina por ter resolvido a tarefa THEN the system SHALL marcar `trace.finish_reason = "completed"`
4. The system SHALL garantir terminação do loop em todos os casos — nunca executar mais de `MAX_REACT_ITERATIONS` chamadas de tool por request

**Independent Test**: tarefa "leia o arquivo `foo.txt` do repositório X no GitHub e salve um resumo em `resumo.md` no filesystem" conclui em ≤ 5 iterações com `github` e `filesystem` presentes em `trace.used_tools`.

---

### P1: Trace de decisão auditável ⭐ MVP

**User Story**: Como auditor, quero que a resposta inclua o rastro completo da decisão, para entender e depurar a escolha do agente sem ler logs do servidor.

**Why P1**: Sustenta o Goal G3 e é pré-condição para debugar roteamento errado em produção.

**Acceptance Criteria**:

1. The system SHALL incluir em toda resposta (200 e erro) um `trace` com `request_id` (UUID), `iterations` (int), `steps` (lista), `used_tools` (lista), `finish_reason` (string) e `duration_ms` (int)
2. WHEN uma tool é chamada THEN o sistema SHALL registrar em `trace.steps` o server, a tool, os argumentos, a duração em ms, o número da tentativa e o status (`success`/`failure`)
3. The system SHALL emitir, para cada request, logs estruturados em JSON contendo no mínimo `request_id`, `timestamp`, `level` e a mensagem — correlacionáveis com o `request_id` retornado na resposta

**Independent Test**: qualquer resposta 200 tem `trace` parseável como JSON válido contendo todos os campos acima; grep dos logs do container do gateway pelo `request_id` retornado encontra ao menos uma linha.

---

### P1: Tratamento de erro e timeout de MCP server ⭐ MVP

**User Story**: Como desenvolvedor, quero que falha, indisponibilidade ou lentidão de um MCP server produza um erro estruturado e previsível, para tratar no cliente sem parsear texto livre.

**Why P1**: Sustenta o Goal G4 — sem isso, uma falha de dependência externa vira 500 opaco.

**Acceptance Criteria**:

1. IF uma chamada a uma tool MCP falha por erro de transporte (conexão recusada, timeout) THEN o sistema SHALL tentar novamente exatamente 1 vez antes de desistir
2. IF a chamada continua falhando após o retry por timeout THEN o sistema SHALL retornar HTTP 504 com `error.code = "MCP_TOOL_TIMEOUT"` e registrar a tentativa falha em `trace.steps`
3. IF o MCP server necessário está indisponível (não conecta) THEN o sistema SHALL retornar HTTP 502 com `error.code = "MCP_SERVER_UNAVAILABLE"`
4. IF o request como um todo excede `REQUEST_TIMEOUT_S` THEN o sistema SHALL retornar HTTP 504 com `error.code = "REQUEST_TIMEOUT"`
5. IF o provider OpenRouter retorna erro ou está indisponível THEN o sistema SHALL retornar HTTP 502 com `error.code = "LLM_PROVIDER_ERROR"`
6. The system SHALL nunca retornar HTTP 500 sem um `error.code` do catálogo — qualquer exceção não classificada é capturada e mapeada para `error.code = "INTERNAL_ERROR"`

**Independent Test**: com o container do MCP server `filesystem` parado, uma tarefa que dependa dele retorna HTTP 502 com `error.code = "MCP_SERVER_UNAVAILABLE"` e o `trace` registra a tentativa.

---

### P1: Autenticação por API key ⭐ MVP

**User Story**: Como operador, quero que o endpoint exija `X-API-Key`, para não expor o orquestrador sem controle.

**Why P1**: Sustenta a dimensão de auth boundary; sem isso o gateway fica aberto no compose.

**Acceptance Criteria**:

1. IF o header `X-API-Key` está ausente THEN o sistema SHALL retornar HTTP 401 com `error.code = "UNAUTHORIZED"`
2. IF o header `X-API-Key` não corresponde ao valor configurado em `ORCHESTRATOR_API_KEY` THEN o sistema SHALL retornar HTTP 401 com `error.code = "UNAUTHORIZED"`
3. WHEN o header `X-API-Key` corresponde ao valor configurado THEN o sistema SHALL processar o request normalmente

**Independent Test**: request sem header → 401; com header incorreto → 401; com header correto → 200 (ou outro código de negócio, nunca 401).

---

### P1: Stack completo via docker-compose ⭐ MVP

**User Story**: Como operador, quero subir gateway e MCP servers com um comando, para reproduzir o ambiente em qualquer máquina.

**Why P1**: Sustenta o Goal G6 — sem isso o projeto não é demonstrável de forma reprodutível.

**Acceptance Criteria**:

1. WHEN o operador executa `docker compose up -d` com um `.env` válido preenchido a partir de `.env.example` THEN o sistema SHALL subir o gateway FastAPI e os containers dos MCP servers `filesystem` e `github`, todos saudáveis
2. The system SHALL ler toda configuração sensível (API keys, PAT do GitHub) de variáveis de ambiente — nenhum segredo hardcoded no compose ou no código
3. WHEN o smoke test E2E é executado após o stack subir THEN o sistema SHALL responder `POST /tasks` com HTTP 200 para ao menos um caso de cada MCP server

**Independent Test**: em máquina limpa, `cp .env.example .env` (preenchendo os segredos) → `docker compose up -d` → script de smoke test E2E sai com código 0.

---

### P2: Allowlist de tools de escrita

**User Story**: Como operador, quero declarar em configuração quais tools de escrita são permitidas, para que o agente nunca execute uma ação destrutiva não prevista.

**Why P2**: Necessário para uso seguro em escrita, mas a v1 é demonstrável só com leitura — não bloqueia o MVP.

**Acceptance Criteria**:

1. The system SHALL classificar cada tool exposta por um MCP server como leitura ou escrita, a partir de uma allowlist declarada em arquivo de configuração
2. IF o agente decide chamar uma tool marcada como escrita que não está na allowlist THEN o sistema SHALL bloquear a chamada antes de executá-la, retornar HTTP 403 com `error.code = "TOOL_NOT_ALLOWED"`, e registrar a tentativa bloqueada em `trace.steps` com `status: "blocked"`
3. WHERE uma tool de escrita está na allowlist THEN o sistema SHALL permitir sua execução normalmente

**Independent Test**: com `filesystem.write_file` fora da allowlist, uma tarefa que exigiria escrita retorna 403 `TOOL_NOT_ALLOWED` e `trace.steps` mostra a tentativa com `status: "blocked"`.

---

### P2: Resposta direta quando nenhum server é adequado

**User Story**: Como desenvolvedor, quero receber uma resposta útil mesmo quando nenhum MCP server cobre a tarefa, para não receber erro em perguntas triviais.

**Why P2**: Melhora a UX, mas o MVP já é demonstrável sem esse caminho.

**Acceptance Criteria**:

1. IF nenhuma tool de nenhum MCP server configurado cobre a tarefa recebida THEN o sistema SHALL responder usando apenas o LLM, com HTTP 200, `trace.used_tools = []` e `trace.finish_reason = "no_suitable_server"`

**Independent Test**: `POST /tasks` com `{"task": "quem escreveu Dom Casmurro?"}` retorna 200, `result` não vazio, `trace.used_tools = []`, `trace.finish_reason = "no_suitable_server"`.

---

### P2: Suíte de avaliação de roteamento

**User Story**: Como desenvolvedor, quero medir se o agente escolhe o server certo, para detectar regressão ao mexer no prompt de decisão.

**Why P2**: Métrica de qualidade contínua — importante, mas não bloqueia a demonstração do MVP.

**Acceptance Criteria**:

1. The system SHALL manter um dataset fixo de ao menos 15 casos, cada um com `task` e o server/tool esperado (ou `no_suitable_server` esperado)
2. WHEN a suíte de avaliação roda em CI com o LLM mockado (respostas determinísticas fixas por caso) THEN o sistema SHALL reportar acurácia de roteamento ≥ 90% sobre o dataset
3. The system SHALL falhar o build (exit code ≠ 0) se a acurácia cair abaixo de 90%

**Independent Test**: `pytest tests/eval/` roda offline (sem chamada real ao OpenRouter) e reporta acurácia ≥ 90% com exit code 0.

---

### P3: Health check com estado dos MCP servers

**User Story**: Como operador, quero um endpoint de health agregado, para uso por orquestradores de container.

**Acceptance Criteria**:

1. WHEN o cliente chama `GET /health` THEN o sistema SHALL retornar HTTP 200 com status agregado (`ok`/`degraded`) e o status individual de cada MCP server configurado

---

### P3: Limite de custo/tokens por request

**User Story**: Como operador, quero um teto de tokens por request, para conter custo de tarefas que geram loops caros.

**Acceptance Criteria**:

1. IF o consumo de tokens do request excede um teto configurável `MAX_TOKENS_PER_REQUEST` THEN o sistema SHALL abortar o loop e retornar erro estruturado com `error.code = "TOKEN_BUDGET_EXCEEDED"`

---

## Edge Cases

- IF `task` é string vazia, ausente, ou apenas espaços em branco THEN o sistema SHALL retornar HTTP 422 com `error.code = "INVALID_TASK"`
- IF `task` excede 4000 caracteres THEN o sistema SHALL retornar HTTP 422 com `error.code = "INVALID_TASK"`
- IF o corpo do request não é um JSON válido ou falta o campo `task` THEN o sistema SHALL retornar HTTP 422 com `error.code = "INVALID_TASK"`
- WHEN dois ou mais MCP servers configurados expõem tools com nomes ambíguos para a mesma tarefa THEN o sistema SHALL escolher com base na descrição/intenção mais próxima e registrar a justificativa no `trace` (campo `steps[].reason`, texto livre curto)
- IF um MCP server declarado na configuração não existe no `docker-compose.yml` (erro de configuração) THEN o sistema SHALL falhar a inicialização do gateway com log de erro explícito, não subir silenciosamente incompleto

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| MCPO-01 | P1: Resolver tarefa em linguagem natural via MCP | Design | Pending |
| MCPO-02 | P1: Descoberta de servers e tools por configuração | Design | Pending |
| MCPO-03 | P1: Loop ReAct limitado com múltiplas tools | Design | Pending |
| MCPO-04 | P1: Trace de decisão auditável | Design | Pending |
| MCPO-05 | P1: Tratamento de erro e timeout de MCP server | Design | Pending |
| MCPO-06 | P1: Autenticação por API key | Design | Pending |
| MCPO-07 | P1: Stack completo via docker-compose | Design | Pending |
| MCPO-08 | P2: Allowlist de tools de escrita | Design | Pending |
| MCPO-09 | P2: Resposta direta quando nenhum server é adequado | Design | Pending |
| MCPO-10 | P2: Suíte de avaliação de roteamento | Design | Pending |
| MCPO-11 | P3: Health check com estado dos MCP servers | Design | Pending |
| MCPO-12 | P3: Limite de custo/tokens por request | Design | Pending |

**ID format:** `MCPO-NN`

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 12 total, 0 mapped to tasks, 12 unmapped ⚠️ (esperado — Tasks ainda não foi executada)

---

## Success Criteria

- [ ] `docker compose up -d` + smoke test E2E passam em máquina limpa
- [ ] Tarefa multi-step envolvendo `github` + `filesystem` conclui em ≤ 5 iterações
- [ ] 100% das respostas 200 contêm `trace` completo e parseável
- [ ] Acurácia de roteamento ≥ 90% no dataset de 15 casos (LLM mockado)
- [ ] Com um MCP server derrubado, nenhum request retorna 500 não tratado (sempre erro do catálogo)
- [ ] Adicionar um terceiro server (ex: `fetch`) não exige alterar nenhum arquivo do pacote do grafo — só configuração
