"""Política de leitura/escrita de ferramentas: classificação e decisões de allowlist
(MCPO-08 AC1/AC3).

`ToolPolicy` é lógica de negócio pura sobre um mapeamento já carregado -- sem I/O, testável com um
dict sintético. `load_tool_policy()` é o loader simples que lê `config/tool_policy.yaml`.
"""

from pathlib import Path

import yaml

DEFAULT_TOOL_POLICY_PATH = Path("config/tool_policy.yaml")

ServerPolicies = dict[str, dict[str, list[str]]]


class ToolPolicy:
    """Decide se uma ferramenta é de escrita e se ela pode ser executada."""

    def __init__(self, policies: ServerPolicies) -> None:
        self._policies = policies

    def is_write(self, server: str, tool: str) -> bool:
        """True se `tool` em `server` é classificada como ferramenta de escrita.

        Uma ferramenta que não está listada em `write_tools` para seu servidor é tratada como
        leitura.
        """
        write_tools = self._policies.get(server, {}).get("write_tools", [])
        return tool in write_tools

    def is_allowed(self, server: str, tool: str) -> bool:
        """True se `tool` em `server` pode ser executada.

        Uma ferramenta de leitura é sempre permitida. Uma ferramenta de escrita só é permitida se
        estiver presente na allowlist daquele servidor.
        """
        if not self.is_write(server, tool):
            return True
        allowlist = self._policies.get(server, {}).get("allowlist", [])
        return tool in allowlist


def load_tool_policy(path: Path = DEFAULT_TOOL_POLICY_PATH) -> ToolPolicy:
    """Faz o parse de `config/tool_policy.yaml` para um `ToolPolicy`."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ToolPolicy(raw.get("policies", {}))
