import aiohttp

from services.logger import logger

_session: aiohttp.ClientSession | None = None


async def get_http_session() -> aiohttp.ClientSession:
    global _session

    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=30, connect=5, sock_read=25)
        _session = aiohttp.ClientSession(timeout=timeout)
        logger.info("HTTP session initialized")

    return _session


async def close_http_session() -> None:
    global _session

    if _session and not _session.closed:
        await _session.close()
        logger.info("HTTP session closed")

    _session = None
