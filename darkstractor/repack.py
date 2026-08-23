from __future__ import annotations

import os
import shutil
import zlib
import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import BinaryIO, Callable

from . import __version__
from .errors import CancelledError, DarkstractorError, FormatError
from .formats.dds import DdsInfo, validate_replacement
from .formats.deathinitive_obp import DeathinitiveObp, ObpMember, parse_deathinitive_obp
from .models import Entry
from .installation import ModManifest, mod_manifest_path, utc_now, write_mod_manifest

Progress = Callable[[int], None]
Log = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class RepackResult:
    output: Path
    texture_name: str
    dds: DdsInfo
    compressed_size: int
    available_size: int
    padding: int
    source_sha256: str = ""
    patched_sha256: str = ""
    manifest: Path | None = None


def _metadata(entry: Entry) -> tuple[int, int, int]:
    if entry.kind != "obp-dds":
        raise DarkstractorError("Solo se pueden reemplazar miembros DDS de un paquete OBP")
    try:
        return (
            int(entry.metadata["obp_base"]),
            int(entry.metadata["obp_size"]),
            int(entry.metadata["member_index"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DarkstractorError("La entrada DDS no contiene metadatos de repaquetado") from exc


def _read_member_prefix(
    source_path: Path,
    base: int,
    archive: DeathinitiveObp,
    member: ObpMember,
    count: int,
) -> bytes:
    wanted = min(count, member.size)
    result = bytearray()
    position = 0
    decoder = zlib.decompressobj()
    with source_path.open("rb") as source:
        source.seek(base + archive.stream_offset)
        remaining = archive.compressed_size
        while remaining and len(result) < wanted and not decoder.eof:
            packed = source.read(min(1024 * 1024, remaining))
            if not packed:
                break
            remaining -= len(packed)
            data = decoder.decompress(packed)
            start = position
            end = position + len(data)
            overlap_start = max(start, member.offset)
            overlap_end = min(end, member.offset + wanted)
            if overlap_start < overlap_end:
                result.extend(data[overlap_start - start : overlap_end - start])
            position = end
    if len(result) != wanted:
        raise FormatError(f"No se pudo leer la cabecera de {member.name}")
    return bytes(result)


def _write_patched_segment(
    target: BinaryIO,
    entry: Entry,
    replacement: Path,
    *,
    cancel: Event | None,
    progress: Progress | None,
) -> tuple[DdsInfo, int, int, int]:
    base, segment_size, member_index = _metadata(entry)
    archive = parse_deathinitive_obp(entry.source, base=base, size=segment_size)
    if not 0 <= member_index < len(archive.members):
        raise FormatError("Índice de textura fuera del paquete OBP")
    member = archive.members[member_index]
    if member.type_id != 6:
        raise FormatError("El miembro seleccionado no es una textura DDS")

    original_header = _read_member_prefix(entry.source, base, archive, member, 148)
    dds = validate_replacement(original_header, member.size, replacement)
    segment_start = target.tell()

    with entry.source.open("rb") as source:
        source.seek(base)
        remaining_prefix = archive.stream_offset
        while remaining_prefix:
            if cancel and cancel.is_set():
                raise CancelledError("Reempaquetado cancelado")
            block = source.read(min(1024 * 1024, remaining_prefix))
            if not block:
                raise FormatError("Cabecera OBP truncada")
            target.write(block)
            remaining_prefix -= len(block)

    decoder = zlib.decompressobj()
    encoder = zlib.compressobj(level=9)
    unpacked_position = 0
    replacement_written = 0

    def process(data: bytes, replacement_file: BinaryIO) -> None:
        nonlocal unpacked_position, replacement_written
        if not data:
            return
        chunk_start = unpacked_position
        chunk_end = chunk_start + len(data)
        overlap_start = max(chunk_start, member.offset)
        overlap_end = min(chunk_end, member.offset + member.size)
        if overlap_start < overlap_end:
            mutable = bytearray(data)
            replacement_file.seek(overlap_start - member.offset)
            replacement_data = replacement_file.read(overlap_end - overlap_start)
            if len(replacement_data) != overlap_end - overlap_start:
                raise FormatError("El DDS de reemplazo se truncó durante la lectura")
            mutable[overlap_start - chunk_start : overlap_end - chunk_start] = replacement_data
            data = bytes(mutable)
            replacement_written += len(replacement_data)
        packed_output = encoder.compress(data)
        if packed_output:
            target.write(packed_output)
        unpacked_position = chunk_end
        if progress:
            progress(len(data))

    with entry.source.open("rb") as source, replacement.open("rb") as replacement_file:
        source.seek(base + archive.stream_offset)
        remaining = archive.compressed_size
        while remaining and not decoder.eof:
            if cancel and cancel.is_set():
                raise CancelledError("Reempaquetado cancelado")
            packed = source.read(min(1024 * 1024, remaining))
            if not packed:
                break
            remaining -= len(packed)
            process(decoder.decompress(packed), replacement_file)
        process(decoder.flush(), replacement_file)

    if not decoder.eof or unpacked_position != archive.unpacked_size:
        raise FormatError(
            f"Payload OBP incompleto: {unpacked_position} / {archive.unpacked_size} bytes"
        )
    if replacement_written != member.size:
        raise FormatError(
            f"Solo se reemplazaron {replacement_written} de {member.size} bytes de la textura"
        )
    compressed = encoder.flush()
    target.write(compressed)

    used = target.tell() - segment_start
    if used > segment_size:
        raise FormatError(
            "El OBP recomprimido no cabe en su espacio original: "
            f"excede la capacidad por {used - segment_size} bytes"
        )
    padding = segment_size - used
    zero_block = bytes(1024 * 1024)
    while padding:
        block_size = min(len(zero_block), padding)
        target.write(zero_block[:block_size])
        padding -= block_size
    return dds, used - archive.stream_offset, segment_size - archive.stream_offset, segment_size - used


def build_patched_segment(
    entry: Entry,
    replacement: Path,
    destination: Path,
    *,
    cancel: Event | None = None,
    progress: Progress | None = None,
) -> RepackResult:
    _base, segment_size, _index = _metadata(entry)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    try:
        with temporary.open("wb") as target:
            dds, compressed, available, padding = _write_patched_segment(
                target, entry, replacement, cancel=cancel, progress=progress
            )
            target.flush()
            os.fsync(target.fileno())
        if temporary.stat().st_size != segment_size:
            raise FormatError("El segmento reconstruido no conservó su tamaño")
        os.replace(temporary, destination)
        return RepackResult(destination, entry.name, dds, compressed, available, padding)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _copy_bytes(
    source: BinaryIO,
    target: BinaryIO,
    count: int,
    *,
    cancel: Event | None,
    progress: Progress | None,
    digests: tuple[object, ...] = (),
) -> None:
    remaining = count
    while remaining:
        if cancel and cancel.is_set():
            raise CancelledError("Reempaquetado cancelado")
        block = source.read(min(8 * 1024 * 1024, remaining))
        if not block:
            raise FormatError("UPAK truncado durante la copia")
        target.write(block)
        for digest in digests:
            digest.update(block)
        remaining -= len(block)
        if progress:
            progress(len(block))


def create_patched_upak(
    entry: Entry,
    replacement: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    cancel: Event | None = None,
    progress: Progress | None = None,
    log: Log | None = None,
) -> RepackResult:
    log = log or (lambda _message: None)
    base, segment_size, member_index = _metadata(entry)
    source_path = entry.source.resolve()
    destination = destination.resolve()
    if destination == source_path:
        raise DarkstractorError("Por seguridad, el UPAK original no puede sobrescribirse directamente")
    if destination.exists() and not overwrite:
        raise DarkstractorError(f"El archivo de salida ya existe: {destination}")
    replacement = replacement.resolve()
    if not replacement.is_file():
        raise DarkstractorError(f"No se encontró el DDS de reemplazo: {replacement}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    source_size = source_path.stat().st_size
    temporary = destination.with_name(destination.name + ".partial")
    segment_temporary = destination.with_name(destination.name + ".segment.tmp")
    manifest_path = mod_manifest_path(destination)
    try:
        log("Validando DDS y reconstruyendo primero el segmento OBP…")
        segment_result = build_patched_segment(
            entry, replacement, segment_temporary, cancel=cancel, progress=progress
        )
        free = shutil.disk_usage(destination.parent).free
        if free < source_size:
            raise DarkstractorError(
                f"Se necesitan al menos {source_size} bytes libres para crear la copia UPAK"
            )
        log(f"Creando copia de {source_path.name} ({source_size} bytes)…")
        source_digest = hashlib.sha256()
        patched_digest = hashlib.sha256()
        with source_path.open("rb") as source, temporary.open("wb") as target:
            _copy_bytes(
                source, target, base, cancel=cancel, progress=progress,
                digests=(source_digest, patched_digest),
            )
            # El segmento original también forma parte del hash fuente, aunque no se copie al destino.
            remaining_original_segment = segment_size
            while remaining_original_segment:
                if cancel and cancel.is_set():
                    raise CancelledError("Reempaquetado cancelado")
                block = source.read(min(8 * 1024 * 1024, remaining_original_segment))
                if not block:
                    raise FormatError("UPAK truncado durante el cálculo SHA-256")
                source_digest.update(block)
                remaining_original_segment -= len(block)
            with segment_temporary.open("rb") as patched_segment:
                _copy_bytes(
                    patched_segment,
                    target,
                    segment_size,
                    cancel=cancel,
                    progress=progress,
                    digests=(patched_digest,),
                )
            _copy_bytes(
                source,
                target,
                source_size - base - segment_size,
                cancel=cancel,
                progress=progress,
                digests=(source_digest, patched_digest),
            )
            target.flush()
            os.fsync(target.fileno())
        if temporary.stat().st_size != source_size:
            raise FormatError("El UPAK reconstruido no conservó su tamaño original")

        patched_archive = parse_deathinitive_obp(temporary, base=base, size=segment_size)
        patched_member = patched_archive.members[member_index]
        patched_header = _read_member_prefix(temporary, base, patched_archive, patched_member, 148)
        with replacement.open("rb") as candidate:
            if patched_header != candidate.read(len(patched_header)):
                raise FormatError("La verificación del DDS reempaquetado no coincide")

        source_sha256 = source_digest.hexdigest()
        patched_sha256 = patched_digest.hexdigest()
        os.replace(temporary, destination)
        write_mod_manifest(
            manifest_path,
            ModManifest(
                schema=1,
                tool="Darkstractor",
                tool_version=__version__,
                created_at=utc_now(),
                source_name=source_path.name,
                source_size=source_size,
                source_sha256=source_sha256,
                patched_size=source_size,
                patched_sha256=patched_sha256,
                texture_name=entry.name,
                segment_offset=base,
                segment_size=segment_size,
            ),
        )
        log(f"UPAK parcheado creado: {destination}")
        return RepackResult(
            destination,
            entry.name,
            segment_result.dds,
            segment_result.compressed_size,
            segment_result.available_size,
            segment_result.padding,
            source_sha256,
            patched_sha256,
            manifest_path,
        )
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        segment_temporary.unlink(missing_ok=True)
