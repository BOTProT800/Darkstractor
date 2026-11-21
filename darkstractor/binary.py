# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import BinaryIO

from .errors import FormatError
from .i18n import t


class BinaryReader:
    """Lector binario acotado; evita que un offset corrupto salga de su segmento."""

    def __init__(
        self,
        file: BinaryIO,
        *,
        base: int = 0,
        size: int | None = None,
        endian: str = "<",
        label: str | None = None,
    ) -> None:
        self.file = file
        self.base = base
        self.endian = endian
        self.label = label if label is not None else t("binary.default_label")
        if size is None:
            current = file.tell()
            file.seek(0, os.SEEK_END)
            size = file.tell() - base
            file.seek(current)
        self.size = size
        if base < 0 or size < 0:
            raise FormatError(t("error.binary_range", label=self.label))
        file.seek(base)

    def tell(self) -> int:
        return self.file.tell() - self.base

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            target = offset
        elif whence == os.SEEK_CUR:
            target = self.tell() + offset
        elif whence == os.SEEK_END:
            target = self.size + offset
        else:
            raise ValueError(t("error.binary_whence"))
        if not 0 <= target <= self.size:
            raise FormatError(
                t("error.binary_offset", label=self.label, target=target, size=self.size)
            )
        self.file.seek(self.base + target)
        return target

    def read(self, count: int) -> bytes:
        if count < 0 or self.tell() + count > self.size:
            raise FormatError(t("error.binary_read_range", label=self.label))
        data = self.file.read(count)
        if len(data) != count:
            raise FormatError(t("error.binary_truncated", label=self.label))
        return data

    def unpack(self, code: str) -> int:
        return int(struct.unpack(self.endian + code, self.read(struct.calcsize(code)))[0])

    def u8(self) -> int:
        return self.unpack("B")

    def u16(self) -> int:
        return self.unpack("H")

    def u32(self) -> int:
        return self.unpack("I")

    def u64(self) -> int:
        return self.unpack("Q")

    def sized_string(self, length_bytes: int = 4) -> str:
        if length_bytes == 1:
            length = self.u8()
        elif length_bytes == 2:
            length = self.u16()
        elif length_bytes == 4:
            length = self.u32()
        else:
            raise ValueError(t("error.binary_length_bytes"))
        if length > 1_000_000:
            raise FormatError(t("error.binary_string", label=self.label, length=length))
        return self.read(length).decode("utf-8", errors="replace")


def open_reader(path: Path, *, endian: str = "<") -> tuple[BinaryIO, BinaryReader]:
    file = path.open("rb")
    return file, BinaryReader(file, endian=endian, label=str(path))

