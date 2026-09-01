# Imagem do MCP server "filesystem" (Node, stdio-only) atras do shim (T27/T28, design.md
# Secao 4). Multi-stage AUTOCONTIDO: o primeiro stage replica docker/shim-base/Dockerfile
# (T28) inline, em vez de depender de uma tag externa `shim-base:latest` pre-construida --
# ver AD-013 em STATE.md (o bake do Docker Compose nao resolveu de forma confiavel um
# `additional_contexts` apontando para outro servico do compose como base image, mesmo com
# builder docker-container; T33 precisou desta correcao para o stack buildar via
# `docker compose build`). Build a partir da raiz do repo (contexto precisa alcancar shim/):
#   docker build -f docker/filesystem/Dockerfile -t mcp-filesystem:latest .
FROM python:3.13-slim AS shim-base
RUN pip install --no-cache-dir fastmcp==3.4.7
COPY shim/mcp_http_shim.py /app/mcp_http_shim.py
WORKDIR /app
CMD ["python", "mcp_http_shim.py"]

FROM shim-base
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g @modelcontextprotocol/server-filesystem@2026.7.10 \
    && apt-get purge -y npm && rm -rf /var/lib/apt/lists/*
ENV MCP_SERVER_NAME=filesystem
ENV MCP_STDIO_COMMAND=mcp-server-filesystem
ENV MCP_STDIO_ARGS=/projects
