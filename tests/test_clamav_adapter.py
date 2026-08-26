import asyncio
import struct

import pytest

from app.adapters.scanner import ClamAVScanner, MalwareScanVerdict, ScannerUnavailable


def test_clamav_instream_protocol_streams_chunks_and_parses_clean_and_infected() -> None:
    async def scenario() -> None:
        responses = [b"stream: OK\0", b"stream: Eicar-Test-Signature FOUND\0"]
        received: list[bytes] = []

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            assert await reader.readexactly(len(b"zINSTREAM\0")) == b"zINSTREAM\0"
            payload = bytearray()
            while size := struct.unpack("!I", await reader.readexactly(4))[0]:
                payload.extend(await reader.readexactly(size))
            received.append(bytes(payload))
            writer.write(responses.pop(0))
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        scanner = ClamAVScanner(host="127.0.0.1", port=port, timeout_seconds=2)

        async def chunks():
            yield b"first-"
            yield b"second"

        clean = await scanner.scan(chunks())
        infected = await scanner.scan(chunks())
        server.close()
        await server.wait_closed()

        assert clean.verdict == MalwareScanVerdict.CLEAN
        assert infected.verdict == MalwareScanVerdict.INFECTED
        assert infected.signature == "Eicar-Test-Signature"
        assert received == [b"first-second", b"first-second"]

    asyncio.run(scenario())


def test_clamav_connection_outage_fails_closed() -> None:
    async def scenario() -> None:
        scanner = ClamAVScanner(host="127.0.0.1", port=1, timeout_seconds=1)

        async def chunks():
            yield b"content"

        with pytest.raises(ScannerUnavailable):
            await scanner.scan(chunks())

    asyncio.run(scenario())
