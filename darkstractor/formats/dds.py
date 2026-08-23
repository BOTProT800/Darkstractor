from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from ..errors import FormatError


@dataclass(frozen=True, slots=True)
class DdsInfo:
    width: int
    height: int
    depth: int
    mipmaps: int
    pixel_flags: int
    fourcc: bytes
    rgb_bits: int
    red_mask: int
    green_mask: int
    blue_mask: int
    alpha_mask: int
    dxgi_format: int | None
    resource_dimension: int | None
    array_size: int | None

    @property
    def format_name(self) -> str:
        if self.fourcc == b"DX10" and self.dxgi_format is not None:
            return f"DXGI {self.dxgi_format}"
        if self.fourcc.strip(b"\0"):
            return self.fourcc.decode("ascii", "replace")
        return f"RGB {self.rgb_bits} bits"


def parse_dds_header(data: bytes, *, label: str = "DDS") -> DdsInfo:
    if len(data) < 128 or data[:4] != b"DDS ":
        raise FormatError(f"{label} no tiene una cabecera DDS válida")
    if struct.unpack_from("<I", data, 4)[0] != 124:
        raise FormatError(f"{label} usa una cabecera DDS no reconocida")
    pixel_size = struct.unpack_from("<I", data, 76)[0]
    if pixel_size != 32:
        raise FormatError(f"{label} tiene una descripción de píxel inválida")
    height, width, _pitch, depth, mipmaps = struct.unpack_from("<IIIII", data, 12)
    pixel_flags = struct.unpack_from("<I", data, 80)[0]
    fourcc = data[84:88]
    rgb_bits, red, green, blue, alpha = struct.unpack_from("<IIIII", data, 88)
    dxgi = dimension = array_size = None
    if fourcc == b"DX10":
        if len(data) < 148:
            raise FormatError(f"{label} está truncado en su cabecera DX10")
        dxgi, dimension, _misc, array_size, _misc2 = struct.unpack_from("<IIIII", data, 128)
    return DdsInfo(
        width, height, depth, max(mipmaps, 1), pixel_flags, fourcc, rgb_bits,
        red, green, blue, alpha, dxgi, dimension, array_size,
    )


def read_dds_info(path: Path) -> DdsInfo:
    with path.open("rb") as file:
        return parse_dds_header(file.read(148), label=path.name)


def validate_replacement(original_header: bytes, original_size: int, replacement: Path) -> DdsInfo:
    original = parse_dds_header(original_header, label="textura original")
    candidate = read_dds_info(replacement)
    replacement_size = replacement.stat().st_size
    if replacement_size != original_size:
        raise FormatError(
            f"El DDS de reemplazo mide {replacement_size} bytes; debe medir exactamente {original_size}"
        )
    if candidate != original:
        differences: list[str] = []
        for field in DdsInfo.__dataclass_fields__:
            before = getattr(original, field)
            after = getattr(candidate, field)
            if before != after:
                differences.append(f"{field}: {before!r} → {after!r}")
        raise FormatError("El DDS no es estructuralmente compatible: " + "; ".join(differences))
    return candidate
