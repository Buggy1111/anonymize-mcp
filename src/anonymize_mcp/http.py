"""HTTP klient pro LINDAT REST API — s retry, logging, exponential backoff."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

MASKIT_URL = "https://quest.ms.mff.cuni.cz/maskit/api/process"
NAMETAG_URL = "https://lindat.mff.cuni.cz/services/nametag/api/recognize"
PONK_URL = "https://quest.ms.mff.cuni.cz/ponk/api/process"
UDPIPE_URL = "https://lindat.mff.cuni.cz/services/udpipe/api/process"

HTTP_TIMEOUT = 120.0  # Zvýšeno z 60s — MasKIT API občas reaguje 60-90s na úřední SK texty
HTTP_TIMEOUT_LONG = 240.0  # Translator doc mode / large inputs

# Retry config — exponential backoff pro transient failures
MAX_RETRIES = 3
INITIAL_BACKOFF_S = 1.0
BACKOFF_MULTIPLIER = 2.0  # 1s → 2s → 4s

# Status codes worth retrying (transient): 429 Too Many Requests, 502/503/504 server errors
_RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})

logger = logging.getLogger(__name__)


async def _post_with_retry(
    url: str,
    data: dict[str, str],
    timeout: float,
) -> httpx.Response:
    """POST s exponential backoff retry pro transient errors.

    Retry pravidla:
    - httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError → retry
    - HTTP status 429/502/503/504 → retry
    - Jiné HTTP errors (4xx) → fail immediately
    - Po MAX_RETRIES pokusech → raise last exception
    """
    backoff = INITIAL_BACKOFF_S
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.post(url, data=data)

            if response.status_code in _RETRYABLE_STATUSES and attempt < MAX_RETRIES:
                logger.warning(
                    "HTTP %s na %s (pokus %d/%d), retry za %.1fs",
                    response.status_code, url, attempt + 1, MAX_RETRIES + 1, backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
                continue

            response.raise_for_status()
            if attempt > 0:
                logger.info("Retry úspěšný na %s po %d pokusech", url, attempt + 1)
            return response

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                logger.warning(
                    "%s na %s (pokus %d/%d), retry za %.1fs",
                    type(e).__name__, url, attempt + 1, MAX_RETRIES + 1, backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
                continue
            logger.error("Vše %d pokusů selhalo na %s: %s", MAX_RETRIES + 1, url, e)
            # Vytvoř exception s explicitní message — httpx.ReadTimeout má prázdné
            # str(), což znesnadňuje debug u uživatele.
            err_type = type(e).__name__
            msg = str(e) or f"{err_type} po {timeout}s na {url} (server pravděpodobně přetížený)"
            raise type(e)(msg) from e
        except httpx.HTTPStatusError as e:
            # 4xx errors except 429 — fail immediately, no point retrying client errors
            logger.error("HTTP %d na %s: %s", e.response.status_code, url, e)
            raise

    if last_exc:
        raise last_exc
    raise RuntimeError(f"Unexpected: vyčerpáno {MAX_RETRIES + 1} pokusů na {url} bez exception")


async def post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    """POST x-www-form-urlencoded → JSON response (s retry + logging).

    Zero-egress: v lokálním módu (ANONYMIZE_MCP_LOCAL) se NameTag NER počítá
    lokálně v procesu místo volání LINDAT API — žádný text neopustí stroj.
    """
    from .local_backend import is_local_mode

    if url == NAMETAG_URL and is_local_mode():
        from .local_backend import local_nametag_conll
        conll = await asyncio.to_thread(local_nametag_conll, data.get("data", ""))
        return {"result": conll, "model": "local:czech-cnec2.0-140304"}

    response = await _post_with_retry(url, data, HTTP_TIMEOUT)
    result: dict[str, Any] = response.json()
    return result


async def post_form_text(
    url: str,
    data: dict[str, str],
    timeout: float = HTTP_TIMEOUT_LONG,
) -> str:
    """POST x-www-form-urlencoded → plain text response (s retry + logging).

    Použito pro Charles Translator, který vrací přeložený text přímo,
    ne JSON. Vyšší default timeout (180s) protože doc mode + velký vstup.
    """
    response = await _post_with_retry(url, data, timeout)
    return response.text
