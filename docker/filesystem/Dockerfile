# Imagem do MCP server "filesystem" (Node, stdio-only) atras do shim (T27/T28,
# design.md Secao 4). Requer shim-base:latest construida antes (T28). Build a partir da
# raiz do repo:
#   docker build -f docker/filesystem/Dockerfile -t mcp-filesystem:latest .
FROM shim-base:latest
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g @modelcontextprotocol/server-filesystem@2026.7.10 \
    && apt-get purge -y npm && rm -rf /var/lib/apt/lists/*
ENV MCP_SERVER_NAME=filesystem
ENV MCP_STDIO_COMMAND=mcp-server-filesystem
ENV MCP_STDIO_ARGS=/projects
