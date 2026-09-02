# Agente Orquestrador de MCP Servers

Serviço HTTP (FastAPI + LangGraph) que recebe uma tarefa em linguagem natural, decide em
tempo de execução quais [MCP servers](https://modelcontextprotocol.io) e tools usar para
resolvê-la, e devolve o resultado junto com um rastro de decisão auditável. O cliente nunca
precisa saber qual server ou tool atende sua tarefa — nem quando um novo server é adicionado.

---

## Funcionalidades

- **Um único endpoint (`POST /tasks`)** resolve a tarefa via MCP sem o cliente conhecer
  servers ou tools.
- **Descoberta automática** de MCP servers e suas tools na subida do gateway
  (`GET /servers`) — adicionar um novo server é mudança de configuração, não de código.
- **Loop ReAct limitado**: encadeia até `MAX_REACT_ITERATIONS` chamadas de tool,
  reavaliando o progresso a cada passo, para tarefas que exigem mais de um server
  (ex.: ler um arquivo no GitHub e cruzar com um arquivo local).
- **Trace de decisão auditável** em toda resposta: `request_id`, servers/tools
  consultados, argumentos, duração, tentativas e motivo do encerramento.
- **Tratamento estruturado de erro e timeout**: falha ou lentidão de um MCP server nunca
  vira 500 opaco — catálogo fechado de 8 códigos de erro estáveis.
- **Allowlist de tools de escrita**: uma tool de escrita fora da allowlist é bloqueada
  *antes* de qualquer chamada externa, com erro dedicado e registro no trace.
- **Resposta direta quando nenhum server é adequado** (ex.: perguntas triviais) —
  o LLM responde sozinho, sem forçar uma chamada de tool artificial.
- **Autenticação por API key** estática via header `X-API-Key`.
- **Health check agregado** (`GET /health`) com o status individual de cada MCP server.
- **Stack completo reproduzível** com `docker compose up -d` — gateway + MCP servers,
  cada um em seu próprio container.

---

## Stack técnica

| Peça | Por que |
| --- | --- |
| **Python 3.13** | Ambiente base do projeto. |
| **FastAPI** | Gateway HTTP stateless por request, com validação de contrato via Pydantic. |
| **LangGraph** (`StateGraph` customizado) | Um agente ReAct pronto não expõe controle explícito sobre `iterations`, trace por passo e bloqueio pré-execução da allowlist — todos exigidos pelo contrato de trace e pela allowlist de escrita. Um grafo próprio dá esse controle sem abrir mão do reducer de mensagens do LangGraph. |
| **LangChain** (`langchain-mcp-adapters`) | `MultiServerMCPClient` mantém o pool de conexões Streamable HTTP com cada MCP server e traduz suas tools para `BaseTool`, sem reescrever esse protocolo à mão. |
| **OpenRouter** via `langchain-openrouter` (`ChatOpenRouter`) | Pacote dedicado recomendado pela documentação oficial do LangChain para providers que não são a OpenAI stricto sensu — evita perder campos específicos do OpenRouter que `ChatOpenAI(base_url=...)` descartaria. |
| **FastMCP** (`create_proxy` + `StdioTransport`) | Os MCP servers oficiais (filesystem, GitHub) são distribuídos como binários **stdio-only**, mas cada um precisa rodar em seu próprio container. O FastMCP fornece o shim stdio↔Streamable HTTP pronto — nenhuma tradução de protocolo escrita à mão. |
| **Docker Compose** | Gateway e MCP servers como containers separados, rede interna dedicada; só a porta do gateway é publicada ao host. |
| **pytest / ruff / mypy** | Gate determinístico de teste, lint e tipagem a cada mudança — não autoavaliação do agente. |

---

## Arquitetura

### O grafo do orquestrador

5 nós, 3 estados terminais de sucesso (mais um estado de erro, exclusivo de respostas
4xx/5xx):

```
        START
          │
          ▼
      ┌─────────┐
      │ prepare │  monta system prompt + catálogo de tools do registry
      └────┬────┘
           ▼
      ┌─────────┐◀────────────────┐
      │  agent  │  LLM decide     │
      └────┬────┘  (bind_tools)   │
           ▼                      │
    tool_calls?          sem tool_calls
    │           │              │
    ▼           ▼              ▼
┌────────┐  max_iter      used_tools == [] ?
│ guard  │  atingido        │           │
└───┬────┘    │             ▼           ▼
 allow│ │deny  │      no_suitable_   completed
     ▼  └──────┼──────►  server         │
┌────────┐     │             │          │
│ tools  │     │             ▼          ▼
└───┬────┘     │        ┌──────────────────┐
    │          └───────►│     finalize     │
    └──(volta a agent,  │ result + trace   │
        iterations+=1)  └────────┬─────────┘
                                  ▼
                                 END
```

`route_after_agent` é a única fonte dos 3 estados terminais de sucesso
(`completed` / `no_suitable_server` / `max_iterations_reached`). O caminho de erro
(`guard` bloqueando uma tool de escrita, ou `tools` falhando após retry) desvia direto
para `finalize`, que monta o envelope de erro em vez do de sucesso.

### Topologia do `docker-compose`

```
Cliente HTTP ──► gateway (única porta publicada: 8080→8000)
                    │
                    ├──streamable_http──► mcp-filesystem (shim + server-filesystem stdio)
                    └──streamable_http──► mcp-github     (shim + github-mcp-server stdio)

                    (mcp-filesystem e mcp-github só na rede interna "mcpnet",
                     sem porta exposta ao host)
```

Cada MCP server oficial roda como binário stdio dentro do seu próprio container, atrás de
um shim (`shim/mcp_http_shim.py`) que traduz stdio↔Streamable HTTP — o gateway só fala
Streamable HTTP com qualquer server, nunca stdio diretamente.

---

## Como rodar

```bash
cp .env.example .env
# edite .env e preencha: ORCHESTRATOR_API_KEY, OPENROUTER_API_KEY, GITHUB_PERSONAL_ACCESS_TOKEN

docker compose up -d
```

Endpoints disponíveis:

| Rota | Auth | Descrição |
| --- | --- | --- |
| `POST /tasks` | `X-API-Key` obrigatório | Recebe `{"task": "..."}` e devolve `result` + `trace` |
| `GET /servers` | — | Lista os MCP servers descobertos, com status e tools |
| `GET /health` | — | Status agregado do gateway e de cada MCP server |

Exemplo:

```bash
curl -X POST http://localhost:8080/tasks \
  -H "X-API-Key: sua-chave" \
  -H "Content-Type: application/json" \
  -d '{"task": "liste os arquivos do diretorio de trabalho"}'
```

---

## Processo de desenvolvimento — Spec-Driven Development (SDD)

Este projeto foi construído com **Spec-Driven Development**, uma técnica que separa
decisão de execução em fases explícitas — `PRD → Spec → Design → Tasks → Execute` —
usando a skill `tlc-spec-driven` com Claude Code. Cada fase produz um artefato versionado em
`.specs/`, revisado e aprovado antes da próxima começar.

**Divisão de responsabilidades:**

- **Eu (arquiteto/produto)** tomei toda decisão de produto e arquitetura — transporte MCP,
  granularidade das tasks, escopo de cada fase, e a resolução de cada ambiguidade ou
  trade-off levantado ao longo do caminho. Revisei e aprovei cada fase antes de avançar
  para a próxima, e todo commit git foi executado manualmente por mim, um por task.
- **O agente (Claude Code)** implementou seguindo a spec aprovada, escreveu os testes,
  investigou problemas técnicos e propôs soluções — mas sempre parando para minha decisão
  em qualquer ponto de ambiguidade ou trade-off, em vez de decidir sozinho.

**Trajetória:** o projeto nasceu greenfield (só um `.venv` vazio) e passou por PRD → Spec
(critérios EARS, IDs rastreáveis `MCPO-NN`) → Design (arquitetura do grafo, transporte MCP
verificado contra documentação oficial) → Tasks (36 tasks atômicas em 8 fases, com matriz de
cobertura de teste e gates determinísticos por task) → Execute, em 5 lotes sequenciais.

Boa parte do valor de engenharia real apareceu na validação manual contra a stack via
Docker, não só nos testes automatizados: múltiplas decisões documentadas em
`.specs/STATE.md` (`## Decisions`) capturam correções descobertas ao validar
`docker compose up -d` de ponta a ponta contra os MCP servers reais — corridas de largada
de inicialização, timeouts que o SDK subjacente não aplicava de fato, mecanismos de build
multi-stage do Compose que não se comportavam como a documentação oficial descrevia. Cada
uma foi isolada por bisseção empírica, corrigida, e coberta por um teste de regressão.

Como parte honesta dessa trajetória: a suíte de avaliação de roteamento (dataset pronto,
15 casos rotulados) está com sua última task pausada — não por falta de trabalho, mas por
um bloqueio de rede corporativa documentado em `.specs/STATE.md` (interceptação TLS que
impede a chamada real ao provedor de LLM necessária para gravar as fixtures de teste).

---

## Estrutura de pastas

```
├─ src/orchestrator/       # gateway: api/, graph/, mcp_client/, llm/, observability/
├─ config/                 # servers.yaml (MCP servers) + tool_policy.yaml (allowlist)
├─ docker/                 # Dockerfile do shim base + de cada MCP server
├─ shim/                   # shim stdio ↔ Streamable HTTP (mcp_http_shim.py)
├─ scripts/                # smoke_test.py (E2E pós docker compose up)
├─ tests/                  # unit/, integration/, eval/, e2e/
└─ .specs/                 # PRD, spec, design, tasks e o log de decisões (STATE.md)
```

---

## Roadmap / próximos passos

- **Suíte de avaliação de roteamento (T36)** — dataset de 15 casos já pronto
  (`tests/eval/dataset.json`); falta gravar as fixtures de resposta do LLM e implementar
  a suíte com gate de acurácia ≥ 90%. Bloqueado por rede corporativa nesta sessão, não por
  decisão de arquitetura — ver `.specs/STATE.md`.
- **Limite de custo/tokens por request** — formalmente adiado para v1.1 (fora do catálogo
  de erros fechado desta versão).
- **Novos MCP servers candidatos** — `fetch`, `git`, `time`, `memory`,
  `sequential-thinking` foram avaliados no PRD e deferidos para v2; a arquitetura atual já
  suporta adicioná-los só por configuração, sem mudar código do grafo.

---

## 👨‍💻 Autor

**Jabes Christian**\

- [LinkedIn](https://www.linkedin.com/in/jabes-christian/)
- [GitHub](https://github.com/jabes-christian)

---

## Licença

[MIT](LICENSE).
