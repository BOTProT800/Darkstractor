# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import zlib
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from ..errors import CancelledError, FormatError

Progress = Callable[[int], None]


@dataclass(slots=True)
class ZlibStream:
    offset: int
    compressed_size: int
    unpacked_size: int
    magic: bytes


def _looks_like_header(first: int, second: int) -> bool:
    return (first & 0x0F) == 8 and (first >> 4) <= 7 and ((first << 8) + second) % 31 == 0


def _probe(path: Path, offset: int, end: int) -> tuple[bytes, bool]:
    with path.open("rb") as file:
        file.seek(offset)
        data = file.read(min(128 * 1024, end - offset))
    try:
        decoder = zlib.decompressobj()
        output = decoder.decompress(data, 64)
        return output, bool(output or decoder.eof)
    except zlib.error:
        return b"", False


def find_next_stream(path: Path, start: int, end: int, *, scan_limit: int | None = None) -> int | None:
    if not 0 <= start <= end <= path.stat().st_size:
        raise FormatError("Rango zlib fuera del archivo")
    scan_end = min(end, start + scan_limit) if scan_limit is not None else end
    chunk_size = 1024 * 1024
    cursor = start
    carry = b""
    with path.open("rb") as file:
        while cursor < scan_end:
            file.seek(cursor)
            block = file.read(min(chunk_size, scan_end - cursor))
            if not block:
                break
            data = carry + block
            origin = cursor - len(carry)
            for index in range(max(0, len(carry) - 1), len(data) - 1):
                if _looks_like_header(data[index], data[index + 1]):
                    candidate = origin + index
                    _, valid = _probe(path, candidate, end)
                    if valid:
                        return candidate
            carry = data[-1:]
            cursor += len(block)
    return None


def extract_stream(
    path: Path,
    offset: int,
    end: int,
    destination: Path,
    *,
    expected_size: int | None = None,
    cancel: Event | None = None,
    progress: Progress | None = None,
) -> ZlibStream:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    decoder = zlib.decompressobj()
    compressed_read = 0
    unpacked = 0
    magic = b""
    try:
        with path.open("rb") as source, temporary.open("wb") as target:
            source.seek(offset)
            remaining = end - offset
            while remaining and not decoder.eof:
                if cancel and cancel.is_set():
                    raise CancelledError("Extracción cancelada")
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                output = decoder.decompress(chunk)
                consumed = len(chunk) - len(decoder.unused_data)
                compressed_read += consumed
                if output:
                    if not magic:
                        magic = output[:16]
                    target.write(output)
                    unpacked += len(output)
                    if progress:
                        progress(len(output))
                if decoder.unused_data:
                    break
            if not decoder.eof:
                raise FormatError(f"Stream zlib incompleto en 0x{offset:x}")
            output = decoder.flush()
            if output:
                if not magic:
                    magic = output[:16]
                target.write(output)
                unpacked += len(output)
                if progress:
                    progress(len(output))
            target.flush()
            os.fsync(target.fileno())
        if expected_size is not None and expected_size > 0 and unpacked != expected_size:
            raise FormatError(
                f"Tamaño zlib inesperado en 0x{offset:x}: {unpacked} (esperado {expected_size})"
            )
        os.replace(temporary, destination)
        return ZlibStream(offset, compressed_read, unpacked, magic)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def declared_size_before(path: Path, offset: int, lower_bound: int = 0) -> int | None:
    if offset < lower_bound + 4:
        return None
    with path.open("rb") as file:
        file.seek(offset - 4)
        value = int.from_bytes(file.read(4), "little")
    return value if 0 < value <= 32 * 1024**3 else None


def extension_for_magic(magic: bytes) -> str:
    signatures = {
        b"BOD": ".bod",
        b"DDS ": ".dds",
        b"RIFF": ".wem",
        b"OggS": ".ogg",
        b"BKHD": ".bnk",
        b"OBPK": ".obp",
    }
    for signature, extension in signatures.items():
        if magic.startswith(signature):
            return extension
    return ".bin"

