# Imagem do MCP server "github" (Go, stdio-only) atras do shim (T27/T28, design.md Secao 4).
# Caminho do binario e tag confirmados em T1 (docker inspect + docker create/cp contra a
# imagem oficial): /server/github-mcp-server, tag v1.11.0 -- distroless/scratch, sem shell,
# por isso o COPY --from=bin de um build multi-stage (que nao depende de shell na imagem de
# origem) em vez de qualquer comando de shell. Requer shim-base:latest construida antes (T28).
# Build a partir da raiz do repo:
#   docker build -f docker/github/Dockerfile -t mcp-github:latest .
FROM ghcr.io/github/github-mcp-server:v1.11.0 AS bin
FROM shim-base:latest
COPY --from=bin /server/github-mcp-server /usr/local/bin/github-mcp-server
ENV MCP_SERVER_NAME=github
ENV MCP_STDIO_COMMAND=github-mcp-server
ENV MCP_STDIO_ARGS=stdio
