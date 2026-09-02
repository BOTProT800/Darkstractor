# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..binary import BinaryReader
from ..errors import FormatError


@dataclass(frozen=True, slots=True)
class BankMedia:
    """Un `.wem` incrustado dentro de un SoundBank de Wwise."""

    file_id: int
    offset: int
    size: int


def parse_bank_media(path: Path, *, base: int = 0, size: int | None = None) -> list[BankMedia]:
    """Devuelve el audio incrustado en un `.bnk`, o una lista vacía si no lleva.

    Un banco es una sucesión de secciones ``{etiqueta de 4 bytes, tamaño u32}``.
    El índice ``DIDX`` es un array de tripletas ``{id, offset, tamaño}`` cuyos
    offsets son relativos al inicio de la sección ``DATA``. Muchos bancos solo
    traen la jerarquía de eventos (``HIRC``) y ningún audio: eso no es un error.
    """
    with path.open("rb") as file:
        reader = BinaryReader(file, base=base, size=size, label=str(path))
        if reader.size < 8 or reader.read(4) != b"BKHD":
            raise FormatError(f"{path.name} no es un SoundBank de Wwise")
        reader.seek(0)

        index: tuple[int, int] | None = None
        payload_start: int | None = None
        payload_size = 0
        while reader.tell() + 8 <= reader.size:
            tag = reader.read(4)
            section_size = reader.u32()
            start = reader.tell()
            if section_size > reader.size - start:
                raise FormatError(f"La sección {tag!r} desborda el banco {path.name}")
            if tag == b"DIDX":
                index = (start, section_size)
            elif tag == b"DATA":
                payload_start, payload_size = start, section_size
            reader.seek(start + section_size)

        if index is None or payload_start is None:
            return []

        index_start, index_size = index
        media: list[BankMedia] = []
        for position in range(index_start, index_start + index_size - 11, 12):
            reader.seek(position)
            file_id = reader.u32()
            offset = reader.u32()
            length = reader.u32()
            if offset > payload_size or length > payload_size - offset:
                raise FormatError(f"El índice DIDX de {path.name} apunta fuera de DATA")
            media.append(BankMedia(file_id, payload_start + offset, length))
        return media
