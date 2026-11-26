"""
Check that a Qobuz stream really delivers audio before a renderer is given it.

The CDN occasionally serves a broken file for one quality of a track: it
answers with the right headers, sends a byte, and closes the connection. A
renderer handed such a stream retries it over and over, and some (FiiO K17)
stop answering control commands or hang outright. Reading the start of the
file ourselves first lets the caller fall back to another quality instead.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from aiohttp import ClientError, ClientSession, ClientTimeout

logger = logging.getLogger(__name__)

# Enough to know the CDN is sending the file, small enough to cost little.
PROBE_BYTES = 32 * 1024
PROBE_CONNECT_TIMEOUT_SECONDS = 5.0
PROBE_READ_TIMEOUT_SECONDS = 5.0
PROBE_TOTAL_TIMEOUT_SECONDS = 8.0

# Returns None when the stream delivers audio, else a short reason.
StreamProbe = Callable[[str], Awaitable[Optional[str]]]


async def probe_stream(url: str) -> Optional[str]:
    """Read the start of ``url``. None if it delivers, else why it does not."""
    timeout = ClientTimeout(
        total=PROBE_TOTAL_TIMEOUT_SECONDS,
        connect=PROBE_CONNECT_TIMEOUT_SECONDS,
        sock_read=PROBE_READ_TIMEOUT_SECONDS,
    )
    received = 0
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"Range": "bytes=0-"}) as response:
                if response.status not in (200, 206):
                    return f"HTTP {response.status}"
                length = response.headers.get("Content-Length", "")
                wanted = min(PROBE_BYTES, int(length)) if length.isdigit() else PROBE_BYTES
                async for chunk in response.content.iter_chunked(8192):
                    received += len(chunk)
                    if received >= wanted:
                        return None
                if received >= wanted:
                    return None
                return f"stream ended after {received} bytes"
    except asyncio.TimeoutError:
        return f"timed out after {received} bytes"
    except ClientError as e:
        return f"{type(e).__name__} after {received} bytes"
