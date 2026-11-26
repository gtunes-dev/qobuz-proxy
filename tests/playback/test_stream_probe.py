"""The stream probe tells a file the CDN serves from one it cannot."""

import socket

from aiohttp import web

from qobuz_proxy.playback.stream_probe import PROBE_BYTES, probe_stream

BODY = b"x" * (PROBE_BYTES * 4)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _serve(handler):
    app = web.Application()
    app.router.add_get("/file", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = _free_port()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    return runner, f"http://127.0.0.1:{port}/file"


async def test_good_stream_passes():
    async def handler(request):
        return web.Response(status=206, body=BODY)

    runner, url = await _serve(handler)
    try:
        assert await probe_stream(url) is None
    finally:
        await runner.cleanup()


async def test_short_file_passes():
    async def handler(request):
        return web.Response(status=200, body=b"short")

    runner, url = await _serve(handler)
    try:
        assert await probe_stream(url) is None
    finally:
        await runner.cleanup()


async def test_one_byte_then_close_fails():
    async def handler(request):
        resp = web.StreamResponse(status=206, headers={"Content-Length": str(len(BODY))})
        await resp.prepare(request)
        await resp.write(BODY[:1])
        request.transport.close()
        return resp

    runner, url = await _serve(handler)
    try:
        reason = await probe_stream(url)
        assert reason is not None and "after 1 bytes" in reason
    finally:
        await runner.cleanup()


async def test_error_status_fails():
    async def handler(request):
        return web.Response(status=403)

    runner, url = await _serve(handler)
    try:
        assert await probe_stream(url) == "HTTP 403"
    finally:
        await runner.cleanup()
