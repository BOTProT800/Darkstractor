from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..binary import BinaryReader
from ..errors import FormatError


@dataclass(slots=True)
class ObpMember:
    name: str
    type_id: int
    offset: int
    size: int


@dataclass(slots=True)
class DeathinitiveObp:
    members: list[ObpMember]
    stream_offset: int
    compressed_size: int
    unpacked_size: int


def parse_deathinitive_obp(path: Path, *, base: int = 0, size: int | None = None) -> DeathinitiveObp:
    """Lee la variante OBPK de Deathinitive sin descomprimir su payload."""
    file_size = path.stat().st_size
    if size is None:
        size = file_size - base
    if base < 0 or size < 0 or base + size > file_size:
        raise FormatError("Segmento OBP fuera del archivo")

    with path.open("rb") as file:
        reader = BinaryReader(file, base=base, size=size, label=f"{path}@0x{base:x}")
        if reader.read(5) != b"OBPK\0":
            raise FormatError("El segmento no comienza con OBPK")

        header = [reader.u32() for _ in range(6)]
        reader.u8()
        table_offset = header[1]
        payload_offset = header[5]
        if not 0 <= table_offset < payload_offset < size:
            raise FormatError("Offsets de cabecera OBP inválidos")
        reader.seek(table_offset)

        group_count = reader.u32()
        file_count = reader.u32()
        opaque_table_size = reader.u32()
        reader.u32()
        if group_count > 100_000 or file_count > 10_000_000:
            raise FormatError("Cantidad inválida de grupos o archivos OBP")
        reader.seek(opaque_table_size, 1)

        for _ in range(4):
            reader.u32()

        groups: list[tuple[int, int]] = []
        for _ in range(group_count):
            type_id = reader.u32()
            member_count = reader.u32()
            reader.u32()
            reader.u32()
            if member_count > file_count:
                raise FormatError("Grupo OBP con demasiados elementos")
            reader.read(member_count)
            groups.append((type_id, member_count))

        reader.u32()
        reader.u8()

        names: list[str] = []
        for index in range(file_count):
            reader.u32()
            reader.u32()
            length = reader.u32()
            if length > 1_000_000:
                raise FormatError(f"Nombre OBP demasiado largo: {length}")
            raw_name = reader.read(length).decode("utf-8", "replace")
            names.append(raw_name or f"archivo_{index:05d}")

        type_ids: list[int] = []
        for type_id, member_count in groups:
            for _ in range(member_count):
                type_ids.append(type_id)
                reader.u32()
                extra_size = reader.u32()
                if extra_size > payload_offset:
                    raise FormatError("Metadatos OBP fuera de rango")
                reader.seek(extra_size, 1)
        if len(type_ids) != file_count:
            raise FormatError(
                f"La tabla OBP declara {file_count} archivos, pero sus grupos contienen {len(type_ids)}"
            )

        sizes = [reader.u32() for _ in range(file_count)]
        if reader.tell() > payload_offset:
            raise FormatError("La tabla OBP invade el payload comprimido")

        reader.seek(payload_offset)
        declared_unpacked_size = reader.u32()
        stream_offset = reader.tell()
        compressed_size = size - stream_offset
        if declared_unpacked_size <= 0 or compressed_size <= 0:
            raise FormatError("Tamaño del payload OBP fuera de rango")

        members: list[ObpMember] = []
        unpacked_offset = 0
        for name, type_id, member_size in zip(names, type_ids, sizes):
            normalized = str(PurePosixPath(name.replace("\\", "/")))
            members.append(ObpMember(normalized, type_id, unpacked_offset, member_size))
            unpacked_offset += member_size

        if declared_unpacked_size != unpacked_offset:
            raise FormatError(
                f"La tabla OBP suma {unpacked_offset} bytes, pero el payload declara {declared_unpacked_size}"
            )
        return DeathinitiveObp(members, stream_offset, compressed_size, unpacked_offset)
