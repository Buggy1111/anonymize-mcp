"""Wrapper MCP — Czech NLP tools (NameTag, MasKIT, UDPipe, PONK, Korektor, Charles Translator)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("anonymize-mcp")
except PackageNotFoundError:  # spuštěno ze zdrojů bez instalace
    __version__ = "0+unknown"
