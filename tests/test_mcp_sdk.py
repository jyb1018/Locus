"""Required in CI; explicitly skipped only in an SDK-less offline developer environment."""
import asyncio
import importlib.util
import os

import pytest

if importlib.util.find_spec("mcp") is None:
    if os.environ.get("LOCUS_REQUIRE_MCP") == "1":
        pytest.fail("CI must install the official MCP SDK; integration tests must not be skipped")
    pytest.skip("Official MCP SDK is not installed (install .[dev]); no host test is claimed", allow_module_level=True)

from locus.demo import run_scenario


@pytest.mark.sdk
def test_two_official_sdk_stdio_sessions_share_state():
    result = asyncio.run(run_scenario("mcp"))
    assert result["result"] == "PASS"
    assert "two_independent_sdk_stdio_sessions" in result["checks"]
    assert "dynamic_read_only_tool_list" in result["checks"]
    assert "crash_restart_and_same_adapter_reconnect" in result["checks"]
