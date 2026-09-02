# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import BinaryIO, Callable

from ..errors import CancelledError, FormatError

#: Recibe bytes leídos del archivo de origen, nunca bytes ya
#: descomprimidos: el total se conoce antes de empezar.
Progress = Callable[[int], None]


@dataclass(slots=True)
class ZlibStream:
    offset: int
    compressed_size: int
    unpacked_size: int
    magic: bytes


def _looks_like_header(first: int, second: int) -> bool:
    return (first & 0x0F) == 8 and (first >> 4) <= 7 and ((first << 8) + second) % 31 == 0


def _header_pattern() -> "re.Pattern[bytes]":
    """Compila la regla de `_looks_like_header` para barrer en C, no en Python.

    Comprobar el par byte a byte costaba más que descomprimir: barrer los
    471 MB de `anim_streams.upak` son cientos de millones de iteraciones del
    intérprete. El patrón se deriva de la propia función para que las dos no
    puedan divergir, y es un lookahead de ancho cero porque el bucle original
    sí encontraba cabeceras solapadas y una alternancia normal las perdería.
    """
    alternatives = []
    for first in range(256):
        seconds = bytes(second for second in range(256) if _looks_like_header(first, second))
        if seconds:
            alternatives.append(re.escape(bytes([first])) + b"[" + re.escape(seconds) + b"]")
    return re.compile(b"(?=" + b"|".join(alternatives) + b")", re.DOTALL)


_HEADER_PATTERN = _header_pattern()


#: Bytes que se le dan a zlib para decidir si una cabecera candidata abre un
#: stream de verdad. De sobra: basta con obtener un byte descomprimido.
PROBE_BYTES = 128 * 1024


def _probe_bytes(data: bytes) -> bool:
    """¿Empiezan estos bytes un stream zlib real, y no un falso positivo?"""
    try:
        decoder = zlib.decompressobj()
        output = decoder.decompress(data, 64)
    except zlib.error:
        return False
    return bool(output or decoder.eof)


def _probe(file: BinaryIO, offset: int, end: int) -> bool:
    """Sondea desde el disco reutilizando el descriptor ya abierto.

    Abrir el archivo por candidato costaba una llamada al sistema por cada
    cabecera aparente, y en un barrido completo hay cientos de miles.
    """
    position = file.tell()
    try:
        file.seek(offset)
        return _probe_bytes(file.read(min(PROBE_BYTES, end - offset)))
    finally:
        file.seek(position)


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
            for match in _HEADER_PATTERN.finditer(data, max(0, len(carry) - 1)):
                index = match.start()
                candidate = origin + index
                # `data` nunca pasa de `scan_end`, así que lo que ya está en
                # memoria es exactamente lo que leería el sondeo del disco.
                # Solo los candidatos del final del bloque bajan a leer.
                window = data[index : index + PROBE_BYTES]
                if len(window) >= min(PROBE_BYTES, end - candidate):
                    valid = _probe_bytes(window)
                else:
                    valid = _probe(file, candidate, end)
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
                if progress:
                    progress(consumed)
                if output:
                    if not magic:
                        magic = output[:16]
                    target.write(output)
                    unpacked += len(output)
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

