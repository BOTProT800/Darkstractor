# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import re
import shutil
import zlib
from pathlib import Path, PurePosixPath
from threading import Event
from typing import Callable, Iterable

from .errors import CancelledError, DarkstractorError, FormatError
from .formats.akpk import parse_akpk
from .formats.bnk import parse_bank_media
from .formats.deathinitive_obp import (
    VARIANT_CHUNK_PER_MEMBER,
    DeathinitiveObp,
    ObpMember,
    parse_deathinitive_obp,
)
from .formats.manifest import parse_manifest
from .formats.zlib_stream import (
    declared_size_before,
    extension_for_magic,
    extract_stream,
    find_next_stream,
)
from .models import Archive, Entry

#: Recibe bytes leídos del origen, nunca bytes ya descomprimidos: así el
#: total se puede calcular de antemano con `estimate_source_bytes`.
Progress = Callable[[int], None]
Log = Callable[[str], None]

INVALID_WINDOWS = re.compile(r'[<>:"|?*\x00-\x1f]')
RESERVED_WINDOWS = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))
}

OBP_TYPE_INFO: dict[int, tuple[str, str]] = {
    0: (".bod", "bod"),
    1: (".o3d", "o3d"),
    2: (".2", "modelo"),
    3: (".3", "iluminación"),
    4: (".4", "colisión"),
    5: (".bmat", "bmat"),
    6: (".dds", "dds"),
    7: (".tfnt", "fuente"),
    8: (".anm", "animación"),
    9: (".bnk", "bnk"),
    11: (".smf", "smf"),
    12: (".gfx", "gfx"),
    15: (".sam", "sam"),
    20: (".loc", "localización"),
}


def human_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{value} B"


def safe_relative_path(name: str) -> Path:
    parts: list[str] = []
    for raw in PurePosixPath(name.replace("\\", "/")).parts:
        if raw in ("", "."):
            continue
        if raw == ".." or PurePosixPath(raw).is_absolute():
            raise FormatError(f"Ruta insegura en el archivo: {name}")
        cleaned = INVALID_WINDOWS.sub("_", raw).rstrip(" .") or "sin_nombre"
        if cleaned.upper().split(".", 1)[0] in RESERVED_WINDOWS:
            cleaned = "_" + cleaned
        parts.append(cleaned)
    if not parts:
        raise FormatError("Nombre de salida vacío")
    return Path(*parts)


def destination_for(output: Path, name: str, policy: str = "rename") -> Path | None:
    root = output.resolve()
    destination = (root / safe_relative_path(name)).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise FormatError(f"Ruta de salida insegura: {name}") from exc
    if not destination.exists():
        return destination
    if policy == "overwrite":
        return destination
    if policy == "skip":
        return None
    stem, suffix = destination.stem, destination.suffix
    for index in range(1, 100_000):
        candidate = destination.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise DarkstractorError(f"No se pudo resolver el nombre duplicado: {destination.name}")


def obp_member_extension(type_id: int) -> tuple[str, str]:
    return OBP_TYPE_INFO.get(type_id, (f".{type_id}", f"tipo {type_id}"))


def list_obp_members(entry: Entry) -> list[Entry]:
    if entry.kind != "upak-segment":
        raise DarkstractorError("La entrada seleccionada no es un paquete OBP")
    archive = parse_deathinitive_obp(entry.source, base=entry.offset, size=entry.size)
    base_name = entry.name[:-1] if entry.name.endswith(".") else entry.name
    # En la variante por chunks cada miembro se lee por separado, así que su
    # coste en bytes de origen es el hueco hasta el chunk siguiente.
    spans: list[int | None] = [None] * len(archive.members)
    if archive.variant == VARIANT_CHUNK_PER_MEMBER:
        edges = [member.chunk_offset or 0 for member in archive.members] + [entry.size]
        spans = [edges[position + 1] - edges[position] for position in range(len(archive.members))]
    results: list[Entry] = []
    for index, member in enumerate(archive.members):
        extension, kind = obp_member_extension(member.type_id)
        member_name = member.name
        if not member_name.casefold().endswith(extension.casefold()):
            member_name += extension
        results.append(
            Entry(
                name=str(PurePosixPath(base_name, member_name)),
                offset=member.offset,
                size=member.size,
                source=entry.source,
                kind=f"obp-{kind}",
                metadata={
                    "obp_base": entry.offset,
                    "obp_size": entry.size,
                    "obp_outer_name": entry.name,
                    "member_index": index,
                    "type_id": member.type_id,
                    "stream_offset": archive.stream_offset,
                    "compressed_size": archive.compressed_size,
                    "unpacked_size": archive.unpacked_size,
                    "chunk_span": spans[index],
                },
            )
        )
    return results


def scan_game(game_root: Path) -> list[Archive]:
    media = game_root / "media"
    manifest = media / "manifest.bin"
    if not manifest.is_file():
        raise DarkstractorError(f"No se encontró media\\manifest.bin en {game_root}")
    if not (game_root / "Darksiders2.exe").is_file():
        raise DarkstractorError("La carpeta no parece una instalación de Darksiders II Deathinitive Edition")

    archives: list[Archive] = []
    manifest_entries = parse_manifest(manifest, media)
    for pack_path in sorted({entry.source for entry in manifest_entries}, key=lambda item: item.name):
        entries = [entry for entry in manifest_entries if entry.source == pack_path]
        archives.append(Archive(pack_path.name, pack_path, "upak", entries, "Recursos nombrados por manifest.bin"))

    anim = media / "anim_streams.upak"
    if anim.is_file():
        archives.append(
            Archive(
                anim.name,
                anim,
                "zlib",
                [Entry("anim_streams/todos_los_streams_zlib", 0, anim.stat().st_size, anim, "zlib-all")],
                "Sin TOC: recuperación secuencial de streams zlib",
            )
        )

    sound_dir = media / "sounds_streamed" / "PC"
    for pck in sorted(sound_dir.glob("*.pck")) if sound_dir.is_dir() else []:
        archives.append(Archive(pck.name, pck, "akpk", parse_akpk(pck), "Audio Wwise por ID"))

    videos: list[Entry] = []
    video_dir = media / "video"
    for item in sorted(video_dir.iterdir()) if video_dir.is_dir() else []:
        if item.is_file():
            videos.append(Entry(f"video/{item.name}", 0, item.stat().st_size, item, item.suffix.lower().lstrip(".")))
    if videos:
        archives.append(Archive("video", video_dir, "loose", videos, "Vídeos Bink y subtítulos"))

    misc: list[Entry] = []
    for pattern in ("scripts.obsp", "world*.bin"):
        for item in sorted(media.glob(pattern)):
            misc.append(Entry(f"misc/{item.name}", 0, item.stat().st_size, item, item.suffix.lower().lstrip(".")))
    if misc:
        archives.append(Archive("otros", media, "loose", misc, "Scripts y datos auxiliares (copia sin conversión)"))
    return archives


def _copy_range(
    entry: Entry,
    destination: Path,
    *,
    cancel: Event | None,
    progress: Progress | None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    remaining = entry.size
    try:
        with entry.source.open("rb") as source, temporary.open("wb") as target:
            source.seek(entry.offset)
            while remaining:
                if cancel and cancel.is_set():
                    raise CancelledError("Extracción cancelada")
                block = source.read(min(1024 * 1024, remaining))
                if not block:
                    raise FormatError(f"Lectura incompleta de {entry.source.name}")
                target.write(block)
                remaining -= len(block)
                if progress:
                    progress(len(block))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _unique_reserved(destination: Path, reserved: set[Path]) -> Path:
    if destination not in reserved:
        reserved.add(destination)
        return destination
    for index in range(1, 100_000):
        candidate = destination.with_name(f"{destination.stem}_{index}{destination.suffix}")
        if candidate not in reserved and not candidate.exists():
            reserved.add(candidate)
            return candidate
    raise DarkstractorError(f"No se pudo resolver el nombre duplicado: {destination.name}")


def _convert_zgfx(raw_path: Path, destination: Path, cancel: Event | None) -> None:
    converted = destination.with_name(destination.name + ".partial")
    try:
        with raw_path.open("rb") as source:
            declared = int.from_bytes(source.read(4), "little")
            decoder = zlib.decompressobj()
            written = 0
            with converted.open("wb") as target:
                while True:
                    if cancel and cancel.is_set():
                        raise CancelledError("Extracción cancelada")
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    output = decoder.decompress(block)
                    target.write(output)
                    written += len(output)
                output = decoder.flush()
                target.write(output)
                written += len(output)
                target.flush()
                os.fsync(target.fileno())
            if not decoder.eof or written != declared:
                raise FormatError(
                    f"ZGFX incompleto: {written} bytes descomprimidos, se esperaban {declared}"
                )
        os.replace(converted, destination)
    except Exception:
        converted.unlink(missing_ok=True)
        raise
    finally:
        raw_path.unlink(missing_ok=True)


def _split_bank(bank: Path, cancel: Event | None, log: Log) -> list[Path]:
    """Separa el audio incrustado de un SoundBank, junto al `.bnk` original.

    El banco se conserva: hace falta para interpretar los eventos con wwiser.
    """
    try:
        media = parse_bank_media(bank)
    except FormatError as error:
        log(f"No se pudo leer el banco {bank.name}: {error}")
        return []
    if not media:
        return []

    folder = bank.with_name(bank.stem + "_wem")
    produced: list[Path] = []
    with bank.open("rb") as source:
        for item in media:
            if cancel and cancel.is_set():
                raise CancelledError("Extracción cancelada")
            destination = folder / f"{item.file_id}.wem"
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".partial")
            source.seek(item.offset)
            remaining = item.size
            try:
                with temporary.open("wb") as target:
                    while remaining:
                        block = source.read(min(1024 * 1024, remaining))
                        if not block:
                            raise FormatError(f"El banco {bank.name} está truncado")
                        target.write(block)
                        remaining -= len(block)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            produced.append(destination)
    log(f"Banco {bank.name}: {len(produced)} .wem separados en {folder.name}")
    return produced


def _extract_chunked_members(
    archive: DeathinitiveObp,
    source: Path,
    base: int,
    segment_size: int,
    destinations: dict[int, Path],
    *,
    cancel: Event | None,
    progress: Progress | None,
    log: Log,
) -> list[Path]:
    """Extrae la variante en la que cada miembro tiene su propio stream zlib.

    No hace falta recorrer el payload entero: cada chunk se descomprime por
    separado, así que se salta directamente a los miembros seleccionados.
    """
    bounds = [member.chunk_offset or 0 for member in archive.members] + [segment_size]
    completed: list[Path] = []
    with source.open("rb") as file:
        for index in sorted(destinations):
            member = archive.members[index]
            if member.chunk_offset is None:
                raise FormatError(f"El miembro {member.name} no tiene chunk propio")
            destination = destinations[index]
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(
                destination.name + (".zgfx.partial" if member.type_id == 12 else ".partial")
            )
            file.seek(base + member.chunk_offset + 4)
            remaining = bounds[index + 1] - member.chunk_offset - 4
            decoder = zlib.decompressobj()
            written = 0
            try:
                with temporary.open("wb") as target:
                    while remaining > 0 and not decoder.eof:
                        if cancel and cancel.is_set():
                            raise CancelledError("Extracción cancelada")
                        packed = file.read(min(1024 * 1024, remaining))
                        if not packed:
                            break
                        remaining -= len(packed)
                        block = decoder.decompress(packed)
                        target.write(block)
                        written += len(block)
                        if progress:
                            progress(len(packed))
                    block = decoder.flush()
                    target.write(block)
                    written += len(block)
                    target.flush()
                    os.fsync(target.fileno())
                if written != member.size:
                    raise FormatError(
                        f"El chunk de {member.name} dio {written} bytes y declaraba {member.size}"
                    )
                if member.type_id == 12:
                    _convert_zgfx(temporary, destination, cancel)
                else:
                    os.replace(temporary, destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            completed.append(destination)
            log(f"Extraído: {destination.name} ({human_size(destination.stat().st_size)})")
            if member.type_id == 9:
                completed.extend(_split_bank(destination, cancel, log))
    return completed


def _extract_obp_member_entries(
    entries: list[Entry],
    output: Path,
    *,
    policy: str,
    cancel: Event | None,
    progress: Progress | None,
    log: Log,
) -> list[Path]:
    if not entries:
        return []
    first = entries[0]
    base = int(first.metadata["obp_base"])
    segment_size = int(first.metadata["obp_size"])
    archive = parse_deathinitive_obp(first.source, base=base, size=segment_size)
    selected: dict[int, Entry] = {}
    for entry in entries:
        if entry.source != first.source or int(entry.metadata["obp_base"]) != base:
            raise DarkstractorError("Se mezclaron miembros de paquetes OBP diferentes")
        selected[int(entry.metadata["member_index"])] = entry

    reserved: set[Path] = set()
    destinations: dict[int, Path] = {}
    for index, entry in selected.items():
        destination = destination_for(output, entry.name, policy)
        if destination is None:
            log(f"Omitido (ya existe): {entry.name}")
            continue
        if policy == "rename":
            destination = _unique_reserved(destination, reserved)
        destinations[index] = destination

    if not destinations:
        return []

    if archive.variant == VARIANT_CHUNK_PER_MEMBER:
        return _extract_chunked_members(
            archive,
            first.source,
            base,
            segment_size,
            destinations,
            cancel=cancel,
            progress=progress,
            log=log,
        )

    current_index = 0
    unpacked_position = 0
    current_target = None
    current_temp: Path | None = None
    current_destination: Path | None = None
    completed: list[Path] = []

    def finish_current() -> None:
        nonlocal current_target, current_temp, current_destination
        if current_target is None or current_temp is None or current_destination is None:
            return
        current_target.flush()
        os.fsync(current_target.fileno())
        current_target.close()
        member = archive.members[current_index]
        if member.type_id == 12:
            _convert_zgfx(current_temp, current_destination, cancel)
        else:
            os.replace(current_temp, current_destination)
        completed.append(current_destination)
        log(f"Extraído: {current_destination.name} ({human_size(current_destination.stat().st_size)})")
        if member.type_id == 9:
            completed.extend(_split_bank(current_destination, cancel, log))
        current_target = None
        current_temp = None
        current_destination = None

    try:
        decoder = zlib.decompressobj()
        with first.source.open("rb") as source:
            source.seek(base + archive.stream_offset)
            remaining = archive.compressed_size
            while remaining and not decoder.eof:
                if cancel and cancel.is_set():
                    raise CancelledError("Extracción cancelada")
                packed = source.read(min(1024 * 1024, remaining))
                if not packed:
                    break
                remaining -= len(packed)
                if progress:
                    progress(len(packed))
                data = decoder.decompress(packed)
                data_offset = 0
                while data_offset < len(data):
                    while current_index < len(archive.members) and unpacked_position >= (
                        archive.members[current_index].offset + archive.members[current_index].size
                    ):
                        finish_current()
                        current_index += 1
                    if current_index >= len(archive.members):
                        raise FormatError("El payload OBP contiene más datos que su tabla")
                    member = archive.members[current_index]
                    member_end = member.offset + member.size
                    take = min(len(data) - data_offset, member_end - unpacked_position)
                    if current_index in destinations:
                        if current_target is None:
                            current_destination = destinations[current_index]
                            current_destination.parent.mkdir(parents=True, exist_ok=True)
                            current_temp = current_destination.with_name(
                                current_destination.name + (".zgfx.partial" if member.type_id == 12 else ".partial")
                            )
                            current_target = current_temp.open("wb")
                        current_target.write(data[data_offset : data_offset + take])
                    data_offset += take
                    unpacked_position += take
                    if unpacked_position == member_end:
                        finish_current()
                        current_index += 1
            tail = decoder.flush()
            if tail:
                # El tamaño de bloque de entrada hace que esto normalmente esté vacío.
                data_offset = 0
                while data_offset < len(tail):
                    if current_index >= len(archive.members):
                        raise FormatError("El payload OBP contiene datos adicionales")
                    member = archive.members[current_index]
                    member_end = member.offset + member.size
                    take = min(len(tail) - data_offset, member_end - unpacked_position)
                    if current_index in destinations:
                        if current_target is None:
                            current_destination = destinations[current_index]
                            current_destination.parent.mkdir(parents=True, exist_ok=True)
                            current_temp = current_destination.with_name(
                                current_destination.name + (".zgfx.partial" if member.type_id == 12 else ".partial")
                            )
                            current_target = current_temp.open("wb")
                        current_target.write(tail[data_offset : data_offset + take])
                    data_offset += take
                    unpacked_position += take
                    if unpacked_position == member_end:
                        finish_current()
                        current_index += 1
        if not decoder.eof or unpacked_position != archive.unpacked_size:
            raise FormatError(
                f"Payload OBP incompleto: {unpacked_position} / {archive.unpacked_size} bytes"
            )
        return completed
    except Exception:
        if current_target is not None:
            current_target.close()
        if current_temp is not None:
            current_temp.unlink(missing_ok=True)
        raise


def _extract_upak_segment(
    entry: Entry,
    output: Path,
    *,
    auto_unpack: bool,
    policy: str,
    cancel: Event | None,
    progress: Progress | None,
    log: Log,
) -> list[Path]:
    base_name = entry.name[:-1] if entry.name.endswith(".") else entry.name
    if auto_unpack:
        try:
            members = list_obp_members(entry)
        except FormatError as error:
            log(f"Sin tabla interna utilizable ({error}); recuperando el BOD completo")
        else:
            log(f"Tabla Deathinitive: {len(members)} recursos internos")
            return _extract_obp_member_entries(
                members,
                output,
                policy=policy,
                cancel=cancel,
                progress=progress,
                log=log,
            )
        candidate = find_next_stream(
            entry.source,
            entry.offset,
            entry.offset + entry.size,
            scan_limit=min(entry.size, 8 * 1024 * 1024),
        )
        if candidate is not None:
            with entry.source.open("rb") as file:
                file.seek(candidate)
                decoder = zlib.decompressobj()
                magic = decoder.decompress(file.read(min(128 * 1024, entry.offset + entry.size - candidate)), 16)
            extension = extension_for_magic(magic)
            destination = destination_for(output, base_name + extension, policy)
            if destination is None:
                log(f"Omitido (ya existe): {base_name + extension}")
                return []
            expected = declared_size_before(entry.source, candidate, entry.offset)
            stream = extract_stream(
                entry.source,
                candidate,
                entry.offset + entry.size,
                destination,
                expected_size=expected,
                cancel=cancel,
                progress=progress,
            )
            log(f"Extraído {destination.name}: {human_size(stream.unpacked_size)}")
            return [destination]
    destination = destination_for(output, base_name + ".obp", policy)
    if destination is None:
        log(f"Omitido (ya existe): {base_name}.obp")
        return []
    _copy_range(entry, destination, cancel=cancel, progress=progress)
    log(f"Extraído sin descomprimir: {destination.name}")
    return [destination]


def recover_all_zlib(
    entry: Entry,
    output: Path,
    *,
    policy: str,
    cancel: Event | None,
    progress: Progress | None,
    log: Log,
) -> list[Path]:
    results: list[Path] = []
    cursor = entry.offset
    end = entry.offset + entry.size
    index = 0
    while cursor < end:
        if cancel and cancel.is_set():
            raise CancelledError("Extracción cancelada")
        candidate = find_next_stream(entry.source, cursor, end)
        if candidate is None:
            break
        expected = declared_size_before(entry.source, candidate, entry.offset)
        temporary_name = f"anim_streams/{index:05d}_0x{candidate:08x}.bin"
        destination = destination_for(output, temporary_name, policy)
        if destination is None:
            cursor = candidate + 2
            index += 1
            continue
        try:
            stream = extract_stream(
                entry.source,
                candidate,
                end,
                destination,
                expected_size=expected,
                cancel=cancel,
                progress=progress,
            )
        except FormatError:
            # Los bytes comprimidos pueden contener una cabecera zlib aparente.
            # Continuamos el escaneo como hace offzip en vez de abortar todo.
            destination.unlink(missing_ok=True)
            cursor = candidate + 1
            continue
        extension = extension_for_magic(stream.magic)
        final = destination.with_suffix(extension)
        if final != destination:
            if final.exists():
                final = destination_for(output, str(final.relative_to(output)), policy) or destination
            os.replace(destination, final)
        results.append(final)
        log(f"Stream {index + 1}: 0x{candidate:x}, {human_size(stream.unpacked_size)}")
        cursor = candidate + max(stream.compressed_size, 2)
        index += 1
    if not results:
        raise FormatError("No se encontraron streams zlib válidos")
    return results


def extract_entries(
    entries: Iterable[Entry],
    output: Path,
    *,
    auto_unpack: bool = True,
    policy: str = "rename",
    cancel: Event | None = None,
    progress: Progress | None = None,
    log: Log | None = None,
) -> list[Path]:
    log = log or (lambda _message: None)
    output.mkdir(parents=True, exist_ok=True)
    entries = list(entries)
    results: list[Path] = []
    processed_obp_groups: set[tuple[Path, int]] = set()
    for entry in entries:
        if cancel and cancel.is_set():
            raise CancelledError("Extracción cancelada")
        if entry.kind.startswith("obp-"):
            key = (entry.source, int(entry.metadata["obp_base"]))
            if key in processed_obp_groups:
                continue
            processed_obp_groups.add(key)
            log(f"Procesando recursos internos de {entry.metadata['obp_outer_name']}")
            group = [
                candidate
                for candidate in entries
                if candidate.kind.startswith("obp-")
                and candidate.source == key[0]
                and int(candidate.metadata["obp_base"]) == key[1]
            ]
            results.extend(
                _extract_obp_member_entries(
                    group, output, policy=policy, cancel=cancel, progress=progress, log=log
                )
            )
        elif entry.kind == "upak-segment":
            log(f"Procesando {entry.name}")
            results.extend(
                _extract_upak_segment(
                    entry, output, auto_unpack=auto_unpack, policy=policy,
                    cancel=cancel, progress=progress, log=log
                )
            )
        elif entry.kind == "zlib-all":
            log(f"Procesando {entry.name}")
            results.extend(
                recover_all_zlib(entry, output, policy=policy, cancel=cancel, progress=progress, log=log)
            )
        else:
            log(f"Procesando {entry.name}")
            destination = destination_for(output, entry.name, policy)
            if destination is None:
                log(f"Omitido (ya existe): {entry.name}")
                continue
            _copy_range(entry, destination, cancel=cancel, progress=progress)
            results.append(destination)
            log(f"Extraído: {entry.name}")
    return results


def estimate_source_bytes(entries: Iterable[Entry]) -> int:
    """Bytes que se leerán del disco, la unidad que reporta `Progress`.

    No coincide con lo que se escribe: un segmento comprimido se recorre una
    sola vez aunque produzca decenas de recursos, y de la variante por chunks
    solo se leen los miembros elegidos.
    """
    total = 0
    whole_segments: set[tuple[Path, int]] = set()
    for entry in entries:
        if not entry.kind.startswith("obp-"):
            total += entry.size
            continue
        span = entry.metadata.get("chunk_span")
        if span is not None:
            total += int(span)
            continue
        key = (entry.source, int(entry.metadata["obp_base"]))
        if key in whole_segments:
            continue
        whole_segments.add(key)
        total += int(entry.metadata["compressed_size"])
    return total


def estimate_output_bytes(entries: Iterable[Entry], *, auto_unpack: bool) -> int:
    """Reserva de disco para el resultado, con margen para lo que se expande."""
    entries = list(entries)
    total = sum(entry.size for entry in entries)
    if auto_unpack and any(entry.kind in ("upak-segment", "zlib-all") for entry in entries):
        # zlib puede expandirse mucho; una reserva conservadora evita llenar el
        # disco a mitad de la extracción.
        total *= 3
    return total


def ensure_free_space(output: Path, required: int) -> None:
    probe = output
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free < required:
        raise DarkstractorError(
            f"Espacio insuficiente: se estiman {human_size(required)} y hay {human_size(free)} libres"
        )
