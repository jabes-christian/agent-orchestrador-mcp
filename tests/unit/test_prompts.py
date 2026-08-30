"""Testes unitários de orchestrator.graph.prompts (MCPO-01, MCPO-02 AC4, AD-005)."""

import inspect

from orchestrator.graph import prompts
from orchestrator.graph.prompts import ToolCatalogEntry, build_system_prompt


def test_prompt_lists_every_tool_from_the_catalog() -> None:
    catalog: list[ToolCatalogEntry] = [
        {"server": "filesystem", "name": "read_file", "description": "Le um arquivo."},
        {
            "server": "github",
            "name": "get_file_contents",
            "description": "Le um arquivo do github.",
        },
    ]

    prompt = build_system_prompt(catalog)

    assert "filesystem.read_file: Le um arquivo." in prompt
    assert "github.get_file_contents: Le um arquivo do github." in prompt


def test_prompt_reflects_a_different_catalog_without_touching_the_module() -> None:
    catalog: list[ToolCatalogEntry] = [
        {"server": "fetch", "name": "fetch_url", "description": "Busca uma URL."},
    ]

    prompt = build_system_prompt(catalog)

    assert "fetch.fetch_url: Busca uma URL." in prompt
    assert "filesystem" not in prompt
    assert "github" not in prompt


def test_prompt_notes_when_no_tools_are_available() -> None:
    prompt = build_system_prompt([])

    assert "Nenhuma tool" in prompt


def test_prompt_module_never_hardcodes_a_specific_server_or_tool_name() -> None:
    source = inspect.getsource(prompts)

    for forbidden in ("filesystem", "github", "read_file", "write_file", "fetch_url"):
        assert forbidden not in source
