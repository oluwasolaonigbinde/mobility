from collections.abc import AsyncIterable

from app.adapters.scanner.base import (
    MalwareScanner,
    MalwareScanResult,
    MalwareScanVerdict,
    ScannerError,
    ScannerUnavailable,
)
from app.adapters.scanner.clamav import ClamAVScanner
from app.core.config import Settings


class UnconfiguredMalwareScanner:
    async def scan(self, chunks: AsyncIterable[bytes]) -> MalwareScanResult:
        raise ScannerUnavailable("Mandatory malware scanning is not configured")


def build_malware_scanner(settings: Settings) -> MalwareScanner:
    if not settings.malware_scanner_host.strip():
        return UnconfiguredMalwareScanner()
    return ClamAVScanner(
        host=settings.malware_scanner_host,
        port=settings.malware_scanner_port,
        timeout_seconds=settings.malware_scanner_timeout_seconds,
    )


__all__ = [
    "ClamAVScanner",
    "MalwareScanner",
    "MalwareScanResult",
    "MalwareScanVerdict",
    "ScannerError",
    "ScannerUnavailable",
    "UnconfiguredMalwareScanner",
    "build_malware_scanner",
]
