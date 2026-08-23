from __future__ import annotations

from pathlib import Path, PurePosixPath

from ..binary import BinaryReader
from ..errors import FormatError
from ..models import Entry


def _decode_language(reader: BinaryReader, offset: int) -> str:
    current = reader.tell()
    try:
        reader.seek(offset)
        probe = reader.read(min(128, reader.size - offset))
        if len(probe) >= 2 and (probe[0] == 0 or probe[1] == 0):
            end = 0
            while end + 1 < len(probe) and probe[end : end + 2] != b"\0\0":
                end += 2
            return probe[:end].decode("utf-16-le" if reader.endian == "<" else "utf-16-be", "replace")
        return probe.split(b"\0", 1)[0].decode("utf-8", "replace")
    finally:
        reader.seek(current)


def parse_akpk(path: Path) -> list[Entry]:
    with path.open("rb") as file:
        magic = file.read(4)
        if magic != b"AKPK":
            raise FormatError(f"{path.name} no es un paquete AKPK")
        file.seek(8)
        test = file.read(4)
        if test == b"\x01\0\0\0":
            endian = "<"
        elif test == b"\0\0\0\x01":
            endian = ">"
        else:
            raise FormatError("No se pudo detectar el orden de bytes de AKPK")

        reader = BinaryReader(file, endian=endian, label=str(path))
        reader.seek(4)
        header_size = reader.u32()
        reader.u32()  # bandera/version
        section_sizes = [reader.u32(), reader.u32(), reader.u32()]
        consumed_header = 0x10 + sum(section_sizes)
        if consumed_header < header_size:
            section_sizes.append(reader.u32())
        else:
            section_sizes.append(0)

        languages_start = reader.tell()
        languages: dict[int, str] = {0: "sfx"}
        if section_sizes[0]:
            count = reader.u32()
            if count > 10_000:
                raise FormatError(f"Cantidad inválida de idiomas: {count}")
            language_rows = [(reader.u32(), reader.u32()) for _ in range(count)]
            for string_offset, language_id in language_rows:
                languages[language_id] = _decode_language(reader, languages_start + string_offset)
            reader.seek(languages_start + section_sizes[0])

        entries: list[Entry] = []
        for section_index, (section_size, extension) in enumerate(
            zip(section_sizes[1:], ("bnk", "wem", "wem")), start=1
        ):
            section_start = reader.tell()
            if section_size == 0:
                continue
            file_count = reader.u32()
            if file_count > 10_000_000:
                raise FormatError(f"Cantidad inválida de archivos AKPK: {file_count}")
            if file_count == 0:
                reader.seek(section_start + section_size)
                continue
            payload_size = section_size - 4
            if payload_size <= 0 or payload_size % file_count:
                raise FormatError("Tabla AKPK de tamaño inconsistente")
            entry_size = payload_size // file_count
            if entry_size not in (20, 24):
                raise FormatError(f"Entrada AKPK no soportada: {entry_size} bytes")
            for _ in range(file_count):
                if entry_size == 24 and section_index == 3:
                    file_id = reader.u64()
                else:
                    file_id = reader.u32()
                block_size = reader.u32()
                size = reader.u64() if entry_size == 24 and section_index != 3 else reader.u32()
                start_block = reader.u32()
                language_id = reader.u32()
                offset = start_block * block_size if block_size else start_block
                language = languages.get(language_id, f"idioma_{language_id}")
                prefix = "" if language_id == 0 else f"{language}/"
                if section_index == 3:
                    prefix = "externals/" + prefix
                entries.append(
                    Entry(
                        name=str(PurePosixPath(path.stem, prefix, f"{file_id}.{extension}")),
                        offset=offset,
                        size=size,
                        source=path,
                        kind=extension,
                        metadata={"language_id": language_id, "section": section_index},
                    )
                )
            reader.seek(section_start + section_size)

        for entry in entries:
            if entry.offset < 0 or entry.size < 0 or entry.offset + entry.size > reader.size:
                raise FormatError(f"Entrada AKPK fuera de rango: {entry.name}")
        return entries

