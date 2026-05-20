"""HTTP klient pro ÚFAL REST API."""

from __future__ import annotations

from typing import Any

import httpx

MASKIT_URL = "https://quest.ms.mff.cuni.cz/maskit/api/process"
NAMETAG_URL = "https://lindat.mff.cuni.cz/services/nametag/api/recognize"
PONK_URL = "https://quest.ms.mff.cuni.cz/ponk/api/process"
UDPIPE_URL = "https://lindat.mff.cuni.cz/services/udpipe/api/process"

HTTP_TIMEOUT = 60.0
HTTP_TIMEOUT_LONG = 180.0  # Translator doc mode / large inputs


async def post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    """POST x-www-form-urlencoded → JSON response."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.post(url, data=data)
        response.raise_for_status()
        return response.json()


async def post_form_text(url: str, data: dict[str, str], timeout: float = HTTP_TIMEOUT_LONG) -> str:
    """POST x-www-form-urlencoded → plain text response.

    Použito pro Charles Translator, který vrací přeložený text přímo,
    ne JSON. Vyšší default timeout (180s) protože doc mode + velký vstup
    může trvat déle než běžných 60s.
    """
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.post(url, data=data)
        response.raise_for_status()
        return response.text
