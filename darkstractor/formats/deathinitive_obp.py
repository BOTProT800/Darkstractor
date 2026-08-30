from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..binary import BinaryReader
from ..errors import FormatError


#: Payload único: un solo stream zlib con todos los miembros concatenados.
VARIANT_SINGLE_STREAM = 0
#: Un stream zlib independiente por miembro, cada uno con su tamaño delante.
VARIANT_CHUNK_PER_MEMBER = 1


@dataclass(slots=True)
class ObpMember:
    name: str
    type_id: int
    offset: int
    size: int
    #: Offset del chunk propio del miembro dentro del segmento. Solo lo usa la
    #: variante 1; en la variante 0 los miembros no tienen stream propio.
    chunk_offset: int | None = None


@dataclass(slots=True)
class DeathinitiveObp:
    members: list[ObpMember]
    stream_offset: int
    compressed_size: int
    unpacked_size: int
    variant: int = VARIANT_SINGLE_STREAM


def parse_deathinitive_obp(path: Path, *, base: int = 0, size: int | None = None) -> DeathinitiveObp:
    """Lee la variante OBPK de Deathinitive sin descomprimir su payload.

    La cabecera declara dónde termina la tabla de nombres y cuánto ocupa el
    bloque de metadatos que la sigue. Esos dos valores son las anclas del
    formato: la tabla de nombres puede estar vacía y los metadatos por miembro
    tienen longitud variable, así que recorrerlos a ciegas descarrila. Con las
    anclas basta con leer los nombres que realmente haya y tomar el array de
    tamaños del final del bloque.
    """
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
        variant = reader.u8()
        table_offset = header[1]
        table_size = header[2]
        names_end = header[3]
        metadata_size = header[4]
        payload_offset = header[5]
        if not 0 < table_offset < names_end <= names_end + metadata_size <= payload_offset < size:
            raise FormatError("Offsets de cabecera OBP inválidos")
        if names_end - table_offset != table_size:
            raise FormatError("La cabecera OBP no concuerda con el tamaño de su tabla")
        reader.seek(table_offset)

        group_count = reader.u32()
        file_count = reader.u32()
        hash_table_size = reader.u32()
        reader.u32()
        if group_count > 100_000 or file_count > 10_000_000:
            raise FormatError("Cantidad inválida de grupos o archivos OBP")
        if file_count == 0:
            raise FormatError("La tabla OBP no declara ningún archivo")
        if metadata_size < 4 * file_count:
            raise FormatError("El bloque de metadatos OBP no cabe la tabla de tamaños")
        reader.seek(hash_table_size, 1)

        for _ in range(4):
            reader.u32()

        type_ids: list[int] = []
        for _ in range(group_count):
            type_id = reader.u32()
            member_count = reader.u32()
            reader.u32()
            reader.u32()
            if member_count > file_count or reader.tell() + member_count > names_end:
                raise FormatError("Grupo OBP con demasiados elementos")
            reader.read(member_count)
            type_ids.extend([type_id] * member_count)
        if len(type_ids) != file_count:
            raise FormatError(
                f"La tabla OBP declara {file_count} archivos, pero sus grupos contienen {len(type_ids)}"
            )

        # Muchos paquetes de mapas guardan solo los hashes y omiten los nombres:
        # ahí la región termina en cuanto empiezan los metadatos.
        names: list[str] = []
        if reader.tell() + 5 <= names_end:
            reader.u32()
            reader.u8()
            while reader.tell() < names_end and len(names) < file_count:
                reader.u32()
                reader.u32()
                length = reader.u32()
                if reader.tell() + length > names_end:
                    raise FormatError("Un nombre OBP se sale de su tabla")
                names.append(reader.read(length).decode("utf-8", "replace"))
        while len(names) < file_count:
            names.append(f"archivo_{len(names):05d}")

        reader.seek(names_end + metadata_size - 4 * file_count)
        table = [reader.u32() for _ in range(file_count)]
        labels = [str(PurePosixPath((name or "sin_nombre").replace("\\", "/"))) for name in names]

        if variant == VARIANT_CHUNK_PER_MEMBER:
            return _chunked_members(reader, labels, type_ids, table, payload_offset, size)
        if variant != VARIANT_SINGLE_STREAM:
            raise FormatError(f"Variante OBP no soportada: {variant}")

        reader.seek(payload_offset)
        declared_unpacked_size = reader.u32()
        stream_offset = reader.tell()
        compressed_size = size - stream_offset
        if declared_unpacked_size <= 0 or compressed_size <= 0:
            raise FormatError("Tamaño del payload OBP fuera de rango")

        members: list[ObpMember] = []
        unpacked_offset = 0
        for name, type_id, member_size in zip(labels, type_ids, table):
            members.append(ObpMember(name, type_id, unpacked_offset, member_size))
            unpacked_offset += member_size

        if declared_unpacked_size != unpacked_offset:
            raise FormatError(
                f"La tabla OBP suma {unpacked_offset} bytes, "
                f"pero el payload declara {declared_unpacked_size}"
            )
        return DeathinitiveObp(members, stream_offset, compressed_size, unpacked_offset)


def _chunked_members(
    reader: BinaryReader,
    names: list[str],
    type_ids: list[int],
    offsets: list[int],
    payload_offset: int,
    size: int,
) -> DeathinitiveObp:
    """Resuelve la variante en la que cada miembro trae su propio stream zlib.

    Aquí la tabla no guarda tamaños sino el offset absoluto del chunk de cada
    miembro. El tamaño real va delante de cada stream, así que hay que ir a
    buscarlo chunk por chunk.
    """
    if offsets[0] != payload_offset:
        raise FormatError("El primer chunk OBP no empieza donde dice la cabecera")
    for previous, following in zip(offsets, offsets[1:]):
        if previous >= following:
            raise FormatError("Los offsets de chunk OBP no crecen")
    if offsets[-1] + 4 >= size:
        raise FormatError("El último chunk OBP se sale del segmento")

    members: list[ObpMember] = []
    unpacked_offset = 0
    for index, (name, type_id, chunk_offset) in enumerate(zip(names, type_ids, offsets)):
        reader.seek(chunk_offset)
        member_size = reader.u32()
        if member_size <= 0:
            raise FormatError(f"El chunk OBP {index} declara un tamaño inválido")
        members.append(ObpMember(name, type_id, unpacked_offset, member_size, chunk_offset))
        unpacked_offset += member_size

    return DeathinitiveObp(
        members,
        payload_offset,
        size - payload_offset,
        unpacked_offset,
        VARIANT_CHUNK_PER_MEMBER,
    )
