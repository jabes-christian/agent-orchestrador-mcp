# PRD — Agente Orquestrador de MCP Servers (meta-agent)

> **Fase 1 de 5** do fluxo `tlc-spec-driven` (PRD → Spec → Design → Tasks → Execute).
> Este arquivo é o entregável da fase de PRD. Após sua validação, ele vira
> `.specs/features/mcp-orchestrator/spec.md` (com critérios EARS e IDs de rastreabilidade) na Fase 2.

---

## Context

O projeto é greenfield: `C:\Users\jmartinsc\Documents\Projetos_Python\agent-orchestrator-mcp` contém apenas `.venv` (Python 3.13.13). Docker 29.6.2 está disponível. Não há `.specs/`, código, nem repositório git inicializado.

**Problema.** Hoje, para uma aplicação consumir capacidades expostas por MCP servers (arquivos, GitHub, APIs externas), alguém precisa saber de antemão qual server e qual tool chamar, e escrever esse acoplamento no código cliente. Cada novo server exige mudança no cliente. O objetivo é inverter isso: o cliente descreve a tarefa em linguagem natural e um agente central decide, em tempo de execução, quais MCP servers e tools usar, executa e devolve o resultado tratado.

**Resultado pretendido.** Um serviço HTTP (FastAPI) que recebe uma tarefa em linguagem natural, roda um grafo LangGraph com loop ReAct limitado sobre o conjunto de MCP servers configurados, e retorna resultado + rastro de decisão auditável — tudo subindo com um `docker compose up`.

---

## Decisões técnicas já fechadas (entrada, não re-discutir)

| Dimensão | Decisão |
| --- | --- |
| Linguagem / ambiente | Python 3.13, `venv` (sem poetry/conda) |
| API Gateway | FastAPI |
| Orquestração | LangGraph (+ LangChain onde fizer sentido para tooling) |
| LLM | Um único modelo via OpenRouter (sem seleção multi-modelo) |
| Estado | Stateless por request — sem checkpointer/persistência na v1 |
| MCP servers | Apenas oficiais/públicos |
| Infra | docker-compose: gateway + MCP servers como containers separados |
| Transporte MCP | **A definir na Fase 3 (Design)** com justificativa |
| Git | Nenhum comando executado pelo agente — orientação apenas |

## Decisões de produto fechadas nesta fase (suas respostas)

| # | Decisão | Escolha |
| --- | --- | --- |
| D1 | Profundidade de orquestração | **Loop ReAct limitado** — até N chamadas de tool (default 5), replanejando a cada passo |
| D2 | MCP servers da v1 | **filesystem** + **github** |
| D3 | Autenticação da API | **API key estática** em header (`X-API-Key`), validada contra env var |
| D4 | Observabilidade | **Logs estruturados JSON + trace de decisão no corpo da resposta** |
| D5 | Operações de escrita | **Permitidas via allowlist** de tools em configuração |
| D6 | Nenhum server adequado | **Responder direto pelo LLM**, HTTP 200, `used_tools: []` e motivo no trace |
| D7 | Avaliação de roteamento | **Dataset fixo (~15 casos) com LLM mockado**, determinístico em CI |

---

## Personas e usuários

| Persona | Necessidade | Como usa |
| --- | --- | --- |
| **Desenvolvedor integrador** (primário) | Consumir capacidades de MCP servers sem acoplar seu código a cada server | `POST /tasks` com a tarefa em linguagem natural; lê `result` + `trace` |
| **Operador / mantenedor** | Adicionar ou remover um MCP server sem tocar no código do agente | Edita `docker-compose.yml` + arquivo de configuração de servers; reinicia o stack |
| **Auditor / debugger** (o próprio dev) | Entender *por que* o agente escolheu determinado server | Lê o `trace` da resposta e os logs JSON correlacionados por `request_id` |

---

## Goals

- [ ] **G1** — Um único endpoint recebe tarefa em linguagem natural e devolve resultado resolvido via MCP, sem o cliente conhecer servers ou tools.
- [ ] **G2** — Adicionar um novo MCP server é uma mudança de **configuração** (compose + config), não de código do grafo.
- [ ] **G3** — Toda resposta carrega um trace auditável: servers consultados, tools chamadas com argumentos, duração, tentativas e motivo da decisão final.
- [ ] **G4** — Falha ou timeout de um MCP server nunca derruba o request: vira erro estruturado ou caminho alternativo, com código de erro estável.
- [ ] **G5** — Acurácia de roteamento ≥ 90% no dataset de avaliação fixo (15 casos rotulados, LLM mockado).
- [ ] **G6** — `docker compose up` sobe gateway + MCP servers e o smoke test end-to-end passa.

## Non-goals (Out of Scope da v1)

| Fora de escopo | Motivo |
| --- | --- |
| Persistência de conversa / checkpointer LangGraph | Decisão fechada: stateless por request; cliente reenvia contexto |
| Descoberta dinâmica de servers na rede (mDNS, registry) | v1 descobre apenas o que está declarado na configuração |
| MCP servers próprios/customizados | v1 usa apenas servers oficiais |
| Seleção multi-modelo / roteamento de LLM | Decisão fechada: um único modelo via OpenRouter |
| Human-in-the-loop para aprovar ações destrutivas | Mitigado por allowlist (D5); confirmação humana fica para v2 |
| UI / frontend | v1 é API-only |
| Multi-tenancy, quotas por usuário, billing | API key única de serviço basta para a v1 |
| Cache de resultados de tools | Otimização prematura sem dados de uso |
| Autenticação OAuth do protocolo MCP | Servers da v1 rodam na rede interna do compose |

---

## MCP servers da v1

**Confirmados:**

1. **filesystem** — server de referência oficial (`@modelcontextprotocol/server-filesystem` / imagem `mcp/filesystem`). Opera sobre diretórios explicitamente montados. Cobre leitura e escrita em sandbox.
2. **github** — server oficial mantido pela GitHub (`ghcr.io/github/github-mcp-server`). Requer Personal Access Token. Cobre integração autenticada com API externa e tem suporte nativo a *toolsets* e modo read-only — a verificar na Fase 3.

**Candidatos sugeridos, deferidos para v2** (registrados para não se perderem): `fetch` (URL → markdown, sem credencial, ótimo para E2E barato), `git` (repositório local), `time`, `memory`, `sequential-thinking`. Os três últimos servem bem como *servers de controle* numa suíte de roteamento: o agente precisa aprender a **não** escolhê-los.

---

## User Stories

### P1 — MVP

**P1.1 · Resolver tarefa em linguagem natural via MCP**
Como desenvolvedor integrador, quero enviar uma tarefa em linguagem natural para um endpoint e receber o resultado já resolvido, para não precisar saber qual MCP server ou tool atende àquela tarefa.
*Teste independente:* `POST /tasks` com "liste os arquivos do diretório de trabalho" retorna 200 com a listagem e `trace.used_tools` contendo a tool do server filesystem.

**P1.2 · Descoberta de servers e tools por configuração**
Como operador, quero que o agente descubra na inicialização quais MCP servers estão configurados e quais tools cada um expõe, para adicionar servers sem alterar o código do grafo.
*Teste independente:* subir o stack e consultar `GET /servers` — retorna os dois servers com suas tools e status de saúde.

**P1.3 · Loop ReAct limitado com múltiplas tools**
Como desenvolvedor, quero que o agente encadeie até N chamadas de tool reavaliando o resultado a cada passo, para resolver tarefas que exigem mais de um passo (ex: "leia o README do repositório X e salve um resumo em resumo.md").
*Teste independente:* tarefa que exige github → filesystem conclui em ≤ 5 iterações com as duas tools no trace.

**P1.4 · Trace de decisão auditável**
Como auditor, quero que a resposta inclua o rastro completo da decisão, para entender e depurar a escolha do agente sem ler logs do servidor.
*Teste independente:* toda resposta 200 contém `trace` com `request_id`, iterações, tools chamadas, argumentos, duração por chamada e motivo de encerramento.

**P1.5 · Tratamento de erro e timeout de MCP server**
Como desenvolvedor, quero que falha, indisponibilidade ou lentidão de um MCP server produza um erro estruturado e previsível, para tratar no cliente sem parsear texto livre.
*Teste independente:* com o container do filesystem parado, uma tarefa que o exige retorna erro com código estável e o trace registra a tentativa falha.

**P1.6 · Autenticação por API key**
Como operador, quero que o endpoint exija `X-API-Key`, para não expor o orquestrador sem controle.
*Teste independente:* request sem header retorna 401; com header inválido, 401; com header correto, 200.

**P1.7 · Stack completo via docker-compose**
Como operador, quero subir gateway e MCP servers com um comando, para reproduzir o ambiente em qualquer máquina.
*Teste independente:* `docker compose up -d` seguido do smoke test E2E passa em máquina limpa.

### P2 — Should have

**P2.1 · Allowlist de tools de escrita**
Como operador, quero declarar em configuração quais tools de escrita são permitidas, para que o agente nunca execute uma ação destrutiva não prevista.
*Teste independente:* tool de escrita fora da allowlist é bloqueada antes da execução, com código de erro próprio e registro no trace.

**P2.2 · Resposta direta quando nenhum server é adequado**
Como desenvolvedor, quero receber uma resposta útil mesmo quando nenhum MCP server cobre a tarefa, para não receber erro em perguntas triviais.
*Teste independente:* "quem escreveu Dom Casmurro?" retorna 200, `used_tools: []` e motivo no trace.

**P2.3 · Suíte de avaliação de roteamento**
Como desenvolvedor, quero medir se o agente escolhe o server certo, para detectar regressão ao mexer no prompt de decisão.
*Teste independente:* `pytest` da suíte de avaliação reporta acurácia ≥ 90% sobre os 15 casos rotulados, com LLM mockado.

### P3 — Nice to have

**P3.1 · Health check com estado dos MCP servers** — `GET /health` reporta status individual de cada server (útil para orquestrador de containers).
**P3.2 · Limite de custo/tokens por request** — teto configurável de tokens por request, com erro estruturado ao estourar.

---

## Requisitos implícitos (varredura de dimensões)

Escopo Large ⇒ todas as dimensões precisam virar requisito ou `N/A justificado`. Resolvidas nesta fase e detalhadas como critérios EARS na Fase 2:

| Dimensão | Tratamento na v1 |
| --- | --- |
| Validação de entrada e limites | Tamanho máximo do campo da tarefa; rejeição de payload vazio; limite de iterações |
| Falhas / falhas parciais | Falha de tool no meio do loop é capturada, registrada no trace e o agente decide seguir ou abortar |
| Idempotência / retry / duplicatas | Retry com limite por chamada de tool; **N/A** para idempotência de request — serviço stateless sem escrita transacional própria |
| Auth e rate limit | `X-API-Key` obrigatória (D3); rate limit **N/A na v1** — serviço interno, API key única |
| Concorrência / ordenação | Requests concorrentes precisam de isolamento de sessão MCP; ordenação **N/A** — sem estado compartilhado entre requests |
| Ciclo de vida de dados | **N/A** — stateless, nada persistido além de logs |
| Observabilidade | Logs JSON com `request_id` + trace na resposta (D4) |
| Falha de dependência externa | Timeout por chamada de tool e por request; erro estruturado para MCP server e para OpenRouter indisponíveis |
| Integridade de transições de estado | Transições válidas do grafo e garantia de terminação do loop (limite de iterações) |

---

## Riscos e itens levados para a Fase de Design

1. **stdio vs SSE/Streamable HTTP em containers separados (item que você pediu para avaliar).** Sinalizo desde já que há tensão real entre duas decisões já fechadas: os servers de referência oficiais são majoritariamente **stdio**, e stdio pressupõe processo filho — o que conflita com "cada server num container separado". As saídas conhecidas (rodar o server como subprocesso dentro do container do gateway, usar um proxy stdio↔HTTP, ou usar o transporte HTTP nativo onde o server oferece) serão avaliadas com documentação verificada via Context7/docs oficiais na Fase 3, com recomendação justificada. Nota adicional: o transporte SSE foi substituído por **Streamable HTTP** nas revisões recentes da spec MCP — confirmarei na Design antes de recomendar.
2. **Custo e latência do loop ReAct.** Cada iteração é uma chamada ao LLM. Limite de iterações e timeout global entram como requisito.
3. **Não determinismo da decisão do LLM.** Mitigado por D7 (dataset fixo com LLM mockado) — testes de CI não dependem de chamada real.
4. **Segredos** (`OPENROUTER_API_KEY`, PAT do GitHub, `X-API-Key`): `.env` fora do git desde o primeiro commit.

---

## Success Criteria

- [ ] `docker compose up -d` + smoke test E2E passam em máquina limpa (G6)
- [ ] Tarefa multi-step envolvendo os dois servers conclui em ≤ 5 iterações
- [ ] 100% das respostas 200 contêm trace completo e parseável
- [ ] Acurácia de roteamento ≥ 90% no dataset de 15 casos
- [ ] Com um MCP server derrubado, nenhum request retorna 500 não tratado
- [ ] Adicionar um terceiro server (ex: `fetch`) não exige alterar nenhum arquivo do pacote do grafo

---

## Assumptions (a confirmar na Fase 2)

| Assumption | Default proposto | Racional |
| --- | --- | --- |
| Limite de iterações do loop ReAct | 5, configurável por env | Suficiente para tarefas de 2–3 tools com folga; evita loop infinito e custo |
| Timeout por chamada de tool MCP | 30s | Cobre chamadas de rede do GitHub sem travar o request |
| Timeout global do request | 120s | Teto para 5 iterações + chamadas de LLM |
| Retry por chamada de tool | 1 retry apenas em erro de transporte/timeout, nunca em erro de negócio | Erro de negócio é determinístico; repetir só gasta tempo |
| Streaming da resposta | Endpoint síncrono na v1 | **Confirmar na Fase 2** conforme você pediu |
| Formato do erro | Envelope JSON com `error.code`, `error.message`, `trace` | Códigos estáveis permitem tratamento no cliente |
| Idioma da resposta do agente | Segue o idioma da tarefa recebida | Sem configuração extra |

---

## Orientação de Git (execução manual sua)

Nada de git é executado pelo agente. Sugestão para **agora**, antes da Fase 2:

```bash
git init
git branch -M main
# criar .gitignore com: .venv/  .env  __pycache__/  .pytest_cache/  *.pyc
git add .gitignore
git commit -m "chore: initialize repository with gitignore"
```

**Estratégia de branches por fase** (Conventional Commits em todas):

| Fase | Branch sugerida | Commit de fechamento |
| --- | --- | --- |
| PRD + Spec | `docs/spec-mcp-orchestrator` | `docs(spec): add mcp orchestrator specification` |
| Design | `docs/design-mcp-orchestrator` | `docs(design): define graph architecture and mcp transport` |
| Tasks | `docs/tasks-mcp-orchestrator` | `docs(tasks): break mcp orchestrator into atomic tasks` |
| Execute | `feat/mcp-orchestrator` | um commit atômico **por task** |

Escopos de commit sugeridos na fase Execute: `graph`, `mcp`, `api`, `config`, `docker`, `eval`.
Exemplo: `feat(mcp): add stdio client adapter with timeout handling`.
`.env` **nunca** entra em commit — só `.env.example`.

---

## Roteiro das fases seguintes

| Fase | Entregável | Ponto de parada |
| --- | --- | --- |
| **2 · Spec** | `.specs/features/mcp-orchestrator/spec.md` — critérios EARS, IDs `MCPO-NN`, matriz de rastreabilidade; roda `validate_spec.py`. Fecha aqui: streaming vs síncrono, contrato exato de request/response e códigos de erro | Sua validação |
| **3 · Design** | `design.md` — arquitetura do grafo LangGraph, recomendação justificada de transporte MCP (verificada via Context7), estrutura de pacotes, topologia do compose, estratégia de teste | Sua validação |
| **4 · Tasks** | `tasks.md` — tasks atômicas com dependências, `Tests` e `Gate` por task; roda `validate_tasks.py`. Se passar de ~8 tasks, ofereço execução por sub-agentes em lotes | Sua validação |
| **5 · Execute** | Implementação, um commit atômico por task, seguida de verificação independente (`validation.md`) | — |

---

## Verificação desta fase

Como validar o PRD antes de eu seguir para a Spec:

1. Personas, Goals e Non-goals refletem o que você quer construir.
2. As sete decisões D1–D7 estão corretamente registradas.
3. As Assumptions são aceitáveis como default (qualquer uma pode ser trocada agora — é mais barato aqui do que na Fase 2).
4. Nada essencial foi classificado como Non-goal por engano.

**Ao aprovar**, eu crio `.specs/features/mcp-orchestrator/spec.md` a partir deste documento com critérios EARS e rastreabilidade, rodo `validate_spec.py` e paro de novo para sua validação antes do Design.
