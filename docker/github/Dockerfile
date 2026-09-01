# Imagem do MCP server "github" (Go, stdio-only) atras do shim (T27/T28, design.md Secao 4).
# Caminho do binario e tag confirmados em T1 (docker inspect + docker create/cp contra a
# imagem oficial): /server/github-mcp-server, tag v1.11.0 -- distroless/scratch, sem shell,
# por isso o COPY --from=bin de um build multi-stage (que nao depende de shell na imagem de
# origem) em vez de qualquer comando de shell.
#
# Multi-stage AUTOCONTIDO: o stage `shim-base` replica docker/shim-base/Dockerfile (T28)
# inline, em vez de depender de uma tag externa `shim-base:latest` pre-construida -- ver
# AD-013 em STATE.md (o bake do Docker Compose nao resolveu de forma confiavel um
# `additional_contexts` apontando para outro servico do compose como base image, mesmo com
# builder docker-container; T33 precisou desta correcao para o stack buildar via
# `docker compose build`). Build a partir da raiz do repo (contexto precisa alcancar shim/):
#   docker build -f docker/github/Dockerfile -t mcp-github:latest .
FROM python:3.13-slim AS shim-base
RUN pip install --no-cache-dir fastmcp==3.4.7
COPY shim/mcp_http_shim.py /app/mcp_http_shim.py
WORKDIR /app
CMD ["python", "mcp_http_shim.py"]

FROM ghcr.io/github/github-mcp-server:v1.11.0 AS bin
FROM shim-base
COPY --from=bin /server/github-mcp-server /usr/local/bin/github-mcp-server
ENV MCP_SERVER_NAME=github
ENV MCP_STDIO_COMMAND=github-mcp-server
ENV MCP_STDIO_ARGS=stdio
