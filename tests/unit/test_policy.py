"""Unit tests for orchestrator.mcp_client.policy (MCPO-08 AC1/AC3)."""

from pathlib import Path

from orchestrator.mcp_client.policy import ToolPolicy, load_tool_policy

SYNTHETIC_POLICIES = {
    "filesystem": {"write_tools": ["write_file", "edit_file"], "allowlist": ["edit_file"]},
    "github": {"write_tools": ["create_pull_request"], "allowlist": []},
}


def test_is_write_true_for_a_classified_write_tool():
    policy = ToolPolicy(SYNTHETIC_POLICIES)

    assert policy.is_write("filesystem", "write_file") is True


def test_is_write_false_for_an_unclassified_tool():
    policy = ToolPolicy(SYNTHETIC_POLICIES)

    assert policy.is_write("filesystem", "read_file") is False


def test_is_write_false_for_an_unknown_server():
    policy = ToolPolicy(SYNTHETIC_POLICIES)

    assert policy.is_write("unknown-server", "anything") is False


def test_is_allowed_true_for_a_write_tool_in_the_allowlist():
    policy = ToolPolicy(SYNTHETIC_POLICIES)

    assert policy.is_allowed("filesystem", "edit_file") is True


def test_is_allowed_false_for_a_write_tool_outside_the_allowlist():
    policy = ToolPolicy(SYNTHETIC_POLICIES)

    assert policy.is_allowed("filesystem", "write_file") is False
    assert policy.is_allowed("github", "create_pull_request") is False


def test_is_allowed_true_for_a_read_tool_regardless_of_allowlist():
    policy = ToolPolicy(SYNTHETIC_POLICIES)

    assert policy.is_allowed("filesystem", "read_file") is True


def test_load_tool_policy_reads_the_real_config_and_blocks_write_file_by_default():
    # Matches spec.md's own edge case example for the allowlist story.
    policy = load_tool_policy(Path("config/tool_policy.yaml"))

    assert policy.is_write("filesystem", "write_file") is True
    assert policy.is_allowed("filesystem", "write_file") is False
