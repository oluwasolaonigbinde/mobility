import asyncio
import struct
from collections.abc import AsyncIterable

from app.adapters.scanner.base import MalwareScanResult, ScannerUnavailable

MAX_RESPONSE_BYTES = 4096


class ClamAVScanner:
    """Streaming clamd INSTREAM adapter used by local Compose and provider-neutral builds."""

    def __init__(self, *, host: str, port: int, timeout_seconds: int) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds

    async def scan(self, chunks: AsyncIterable[bytes]) -> MalwareScanResult:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_connection(self._host, self._port)
                try:
                    writer.write(b"zINSTREAM\0")
                    async for chunk in chunks:
                        if chunk:
                            writer.write(struct.pack("!I", len(chunk)))
                            writer.write(chunk)
                            await writer.drain()
                    writer.write(struct.pack("!I", 0))
                    await writer.drain()
                    response = await reader.readuntil(b"\0")
                finally:
                    writer.close()
                    await writer.wait_closed()
        except (
            TimeoutError,
            OSError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ) as exc:
            raise ScannerUnavailable("Mandatory malware scanning is unavailable") from exc

        if len(response) > MAX_RESPONSE_BYTES:
            raise ScannerUnavailable("Mandatory malware scanner returned an invalid response")
        message = response.rstrip(b"\0").decode("utf-8", errors="replace")
        if message.endswith(": OK"):
            return MalwareScanResult.clean()
        marker = " FOUND"
        if message.endswith(marker) and ": " in message:
            return MalwareScanResult.infected(message.rsplit(": ", 1)[1][: -len(marker)])
        raise ScannerUnavailable("Mandatory malware scanner returned an invalid response")
