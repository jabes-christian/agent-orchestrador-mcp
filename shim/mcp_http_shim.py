"""Shim stdio<->Streamable HTTP para os MCP servers oficiais (AD-001, design.md Secao 2).

Cada MCP server oficial (`server-filesystem`, `github-mcp-server`) so fala stdio na forma
distribuida. Este shim -- identico para os dois; o que muda por container e so o env
(`MCP_STDIO_COMMAND`, `MCP_STDIO_ARGS`, `MCP_SERVER_NAME`) -- usa `fastmcp.server.create_proxy`
para expor esse processo stdio como Streamable HTTP na rede interna do compose, sem escrever
nenhum codigo de traducao de protocolo a mao.

Hardening de `Origin` (design.md -> Risks & Concerns, AD-001): a spec MCP exige validacao do
header `Origin` pelo servidor Streamable HTTP como protecao contra DNS rebinding. Passar
`allowed_origins=[]` (lista vazia, mas explicita -- nao `None`) ativa essa validacao
independente do `host_origin_protection`: qualquer request que carregue um header `Origin`
e rejeitado com 403, e requests sem `Origin` (o caso normal do cliente MCP interno, um
`httpx.AsyncClient` que nunca envia esse header por padrao) passam direto -- ver
`fastmcp.server.http.HostOriginGuardMiddleware`, que so valida Origin quando o header esta
presente. `host_origin_protection="auto"` (nao `True`/"strict") mantem esse escopo cirurgico:
com um `allowed_origins` explicito, a validacao de Origin liga em qualquer modo, mas a
validacao de `Host` so seria forcada em modo "strict" -- fora do escopo pedido pelo Design,
que levantou só o gap de `Origin`, e que exigiria o shim conhecer de antemao o hostname que o
compose vai lhe dar.
"""

import os
import shlex

from fastmcp.client.transports import StdioTransport
from fastmcp.server import create_proxy
from fastmcp.server.http import StarletteWithLifespan
from fastmcp.server.providers.proxy import FastMCPProxy


def build_proxy() -> FastMCPProxy:
    """Monta o proxy stdio->MCP a partir das variaveis de ambiente do container."""
    return create_proxy(
        StdioTransport(
            command=os.environ["MCP_STDIO_COMMAND"],
            args=shlex.split(os.environ.get("MCP_STDIO_ARGS", "")),
            env=dict(os.environ),
        ),
        name=os.environ["MCP_SERVER_NAME"],
    )


def build_http_app(proxy: FastMCPProxy) -> StarletteWithLifespan:
    """ASGI app do proxy, servida via Streamable HTTP com a validacao de `Origin` ligada
    (ver docstring do modulo)."""
    return proxy.http_app(host_origin_protection="auto", allowed_origins=[])


def main() -> None:
    proxy = build_proxy()
    proxy.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        host_origin_protection="auto",
        allowed_origins=[],
    )


if __name__ == "__main__":
    main()
