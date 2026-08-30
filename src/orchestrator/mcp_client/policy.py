"""Tool write/read policy: classification and allowlist decisions (MCPO-08 AC1/AC3).

`ToolPolicy` is pure business logic over an already-loaded mapping -- no I/O, testable with a
synthetic dict. `load_tool_policy()` is the thin loader that reads `config/tool_policy.yaml`.
"""

from pathlib import Path

import yaml

DEFAULT_TOOL_POLICY_PATH = Path("config/tool_policy.yaml")

ServerPolicies = dict[str, dict[str, list[str]]]


class ToolPolicy:
    """Decides whether a tool is a write tool and whether it may be executed."""

    def __init__(self, policies: ServerPolicies) -> None:
        self._policies = policies

    def is_write(self, server: str, tool: str) -> bool:
        """True if `tool` on `server` is classified as a write tool.

        A tool that is not listed under `write_tools` for its server is treated as read.
        """
        write_tools = self._policies.get(server, {}).get("write_tools", [])
        return tool in write_tools

    def is_allowed(self, server: str, tool: str) -> bool:
        """True if `tool` on `server` may be executed.

        A read tool is always allowed. A write tool is allowed only if it is present in that
        server's allowlist.
        """
        if not self.is_write(server, tool):
            return True
        allowlist = self._policies.get(server, {}).get("allowlist", [])
        return tool in allowlist


def load_tool_policy(path: Path = DEFAULT_TOOL_POLICY_PATH) -> ToolPolicy:
    """Parse `config/tool_policy.yaml` into a `ToolPolicy`."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ToolPolicy(raw.get("policies", {}))
