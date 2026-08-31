# Imagem base reutilizada pelos containers de MCP server que rodam atras do shim
# stdio<->Streamable HTTP (T27, design.md Secao 4). Build a partir da raiz do repo:
#   docker build -f docker/shim-base/Dockerfile -t shim-base:latest .
# (o contexto precisa ser a raiz para o COPY abaixo alcancar shim/mcp_http_shim.py).
FROM python:3.13-slim
RUN pip install --no-cache-dir fastmcp==3.4.7
COPY shim/mcp_http_shim.py /app/mcp_http_shim.py
WORKDIR /app
CMD ["python", "mcp_http_shim.py"]
