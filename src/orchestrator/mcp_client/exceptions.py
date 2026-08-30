"""Hierarquia de exceções da camada de cliente MCP (MCPO-05).

Cada exceção mapeia 1:1 para um `error.code` estável do catálogo de erros da API (spec.md ->
Contrato da API). `api/errors.py` converte instâncias dessas exceções na resposta HTTP
correspondente.
"""


class McpClientError(Exception):
    """Classe base para toda condição de erro levantada pela camada de cliente MCP."""

    error_code: str = "INTERNAL_ERROR"
    http_status: int = 500


class ServerUnavailableError(McpClientError):
    """O servidor MCP não conectou (conexão recusada, falha de DNS, socket fechado)."""

    error_code = "MCP_SERVER_UNAVAILABLE"
    http_status = 502


class ToolTimeoutError(McpClientError):
    """Uma chamada de ferramenta excedeu `MCP_TOOL_TIMEOUT_S` após a única retentativa
    automática de transporte."""

    error_code = "MCP_TOOL_TIMEOUT"
    http_status = 504


class ToolNotAllowedError(McpClientError):
    """Foi solicitada uma ferramenta de escrita que não está presente na allowlist de
    `tool_policy.yaml`."""

    error_code = "TOOL_NOT_ALLOWED"
    http_status = 403
