from collections.abc import AsyncIterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ScannerError(RuntimeError):
    """Base scanner failure without provider or credential detail."""


class ScannerUnavailable(ScannerError):
    """The mandatory malware scanner is unavailable or unconfigured."""


class MalwareScanVerdict(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"


@dataclass(frozen=True, slots=True)
class MalwareScanResult:
    verdict: MalwareScanVerdict
    signature: str | None = None

    @classmethod
    def clean(cls) -> "MalwareScanResult":
        return cls(MalwareScanVerdict.CLEAN)

    @classmethod
    def infected(cls, signature: str) -> "MalwareScanResult":
        return cls(MalwareScanVerdict.INFECTED, signature=signature[:255])


@runtime_checkable
class MalwareScanner(Protocol):
    async def scan(self, chunks: AsyncIterable[bytes]) -> MalwareScanResult: ...
