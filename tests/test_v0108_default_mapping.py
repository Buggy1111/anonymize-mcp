"""v0.10.8: MCP tool `anonymize` ve výchozím stavu nevrací originály."""
from __future__ import annotations

import inspect


def test_tool_default_keep_mapping_false() -> None:
    from anonymize_mcp import server
    fn = getattr(server.anonymize, "fn", server.anonymize)
    assert inspect.signature(fn).parameters["keep_mapping"].default is False
