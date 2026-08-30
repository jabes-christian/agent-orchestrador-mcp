"""Exception hierarchy for the MCP client layer (MCPO-05).

Each exception maps 1:1 to a stable `error.code` from the API error catalog (spec.md -> Contrato
da API). `api/errors.py` turns instances of these into the corresponding HTTP response.
"""


class McpClientError(Exception):
    """Base class for every error condition raised by the MCP client layer."""

    error_code: str = "INTERNAL_ERROR"
    http_status: int = 500


class ServerUnavailableError(McpClientError):
    """The MCP server did not connect (connection refused, DNS failure, closed socket)."""

    error_code = "MCP_SERVER_UNAVAILABLE"
    http_status = 502


class ToolTimeoutError(McpClientError):
    """A tool call exceeded `MCP_TOOL_TIMEOUT_S` after the single automatic transport retry."""

    error_code = "MCP_TOOL_TIMEOUT"
    http_status = 504


class ToolNotAllowedError(McpClientError):
    """A write tool was requested that is not present in the `tool_policy.yaml` allowlist."""

    error_code = "TOOL_NOT_ALLOWED"
    http_status = 403
