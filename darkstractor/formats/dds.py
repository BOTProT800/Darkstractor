# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

"""Lectura de DDS y decodificación a píxeles para la vista previa.

Darksiders II guarda sus texturas en cuatro familias: DXT1 y DXT5 para casi
todo, sin comprimir de 32 bits para la interfaz y algún 16 bits suelto. Aquí
se cubren además DXT3, BC4 y BC5, que comparten maquinaria con las anteriores
y evitan que una textura rara deje la vista previa en blanco.

Todo es Python puro a propósito: el proyecto no depende de paquetes externos,
así que el coste se controla eligiendo qué nivel mipmap decodificar y, cuando
no hay mipmaps, quedándose con uno de cada varios píxeles.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from ..errors import FormatError

MAGIC = b"DDS "
HEADER_SIZE = 128
#: Cabecera extra de las variantes DX10, que este juego no usa.
DX10_HEADER_SIZE = 20

_PF_ALPHAPIXELS = 0x1
_PF_ALPHA = 0x2
_PF_FOURCC = 0x4
_PF_RGB = 0x40
_PF_LUMINANCE = 0x20000

#: Bytes por bloque de 4x4 píxeles de cada formato comprimido.
_BLOCK_BYTES = {"BC1": 8, "BC2": 16, "BC3": 16, "BC4": 8, "BC5": 16}

_FOURCC_FORMATS = {
    b"DXT1": "BC1",
    b"DXT2": "BC2",
    b"DXT3": "BC2",
    b"DXT4": "BC3",
    b"DXT5": "BC3",
    b"ATI1": "BC4",
    b"BC4U": "BC4",
    b"ATI2": "BC5",
    b"BC5U": "BC5",
}

#: Nombre que ve el usuario; el interno dice cómo se decodifica, no qué ponía
#: en el archivo.
_DISPLAY_NAMES = {
    b"DXT1": "DXT1",
    b"DXT2": "DXT2",
    b"DXT3": "DXT3",
    b"DXT4": "DXT4",
    b"DXT5": "DXT5",
    b"ATI1": "ATI1 (BC4)",
    b"BC4U": "BC4",
    b"ATI2": "ATI2 (BC5)",
    b"BC5U": "BC5",
}


@dataclass(slots=True)
class DdsHeader:
    width: int
    height: int
    mipmaps: int
    #: Clave interna: BC1..BC5 o ``RAW``.
    kind: str
    #: Etiqueta para la interfaz: DXT5, RGB 32 bits…
    label: str
    bits: int = 0
    masks: tuple[int, int, int, int] = (0, 0, 0, 0)
    has_alpha: bool = False
    luminance: bool = False


@dataclass(slots=True)
class DecodedImage:
    """Resultado ya en píxeles, listo para convertirse en PNG."""

    width: int
    height: int
    #: Tres bytes por píxel, por filas de arriba abajo.
    rgb: bytes
    #: Un byte por píxel, o ``None`` si la textura es opaca.
    alpha: bytes | None
    #: Nivel mipmap decodificado (0 es la resolución completa).
    level: int
    #: Uno de cada cuántos píxeles del nivel se decodificó; 1 si fue entero.
    shrink: int
    header: DdsHeader

    @property
    def reduced(self) -> bool:
        return self.level > 0 or self.shrink > 1


def parse_header(data: bytes) -> DdsHeader:
    """Lee la cabecera DDS y decide cómo hay que decodificar los píxeles."""
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise FormatError("El archivo no empieza por la firma DDS")
    if struct.unpack_from("<I", data, 4)[0] != 124:
        raise FormatError("Cabecera DDS con tamaño inesperado")

    height, width = struct.unpack_from("<II", data, 12)
    mipmaps = struct.unpack_from("<I", data, 28)[0] or 1
    pf_flags, fourcc = struct.unpack_from("<I4s", data, 80)
    bits, red, green, blue, alpha = struct.unpack_from("<IIIII", data, 88)
    if not 0 < width <= 32768 or not 0 < height <= 32768:
        raise FormatError(f"Dimensiones DDS fuera de rango: {width}x{height}")

    if pf_flags & _PF_FOURCC:
        if fourcc == b"DX10":
            dxgi = struct.unpack_from("<I", data, HEADER_SIZE)[0] if len(data) >= 132 else 0
            raise FormatError(f"DDS en variante DX10 (formato DXGI {dxgi}), no soportada")
        kind = _FOURCC_FORMATS.get(fourcc)
        if kind is None:
            readable = fourcc.decode("latin-1").strip() or fourcc.hex()
            raise FormatError(f"Compresión DDS no soportada: {readable}")
        return DdsHeader(
            width,
            height,
            mipmaps,
            kind,
            _DISPLAY_NAMES.get(fourcc, kind),
            has_alpha=kind in ("BC2", "BC3") or bool(pf_flags & _PF_ALPHAPIXELS),
        )

    if bits not in (8, 16, 24, 32):
        raise FormatError(f"DDS sin comprimir con {bits} bits por píxel, no soportado")
    luminance = bool(pf_flags & _PF_LUMINANCE) or not (pf_flags & _PF_RGB)
    alpha_only = bool(pf_flags & _PF_ALPHA) and not (pf_flags & (_PF_RGB | _PF_LUMINANCE))
    if alpha_only:
        # Textura de solo alfa: se enseña como escala de grises opaca, que es
        # lo que transporta de verdad. Devolverla transparente sería enseñar
        # un rectángulo vacío.
        red = green = blue = alpha
        luminance = True
    label = f"{'Luminancia' if luminance else 'RGB'} {bits} bits"
    return DdsHeader(
        width,
        height,
        mipmaps,
        "RAW",
        label,
        bits=bits,
        masks=(red, green, blue, alpha),
        has_alpha=bool(alpha) and bool(pf_flags & (_PF_ALPHAPIXELS | _PF_ALPHA)) and not alpha_only,
        luminance=luminance,
    )


def level_bytes(header: DdsHeader, width: int, height: int) -> int:
    """Bytes que ocupa un nivel mipmap de ese tamaño."""
    if header.kind == "RAW":
        return width * height * (header.bits // 8)
    blocks = max(1, (width + 3) // 4) * max(1, (height + 3) // 4)
    return blocks * _BLOCK_BYTES[header.kind]


def select_level(
    header: DdsHeader, max_side: int | None, available: int | None = None
) -> tuple[int, int, int, int]:
    """Elige el mipmap más pequeño que aún llegue a ``max_side``.

    Devuelve ``(offset, nivel, ancho, alto)``. Sin mipmaps declarados, que es
    casi la mitad de las texturas del juego, se queda en el nivel 0. Con
    ``available``, el tamaño real de los datos, tampoco baja a un nivel que la
    cabecera promete y el archivo no trae.
    """
    offset, width, height = HEADER_SIZE, header.width, header.height
    if max_side is None:
        return offset, 0, width, height
    for level in range(header.mipmaps - 1):
        if max(width, height) <= max_side:
            return offset, level, width, height
        next_offset = offset + level_bytes(header, width, height)
        next_width, next_height = max(1, width // 2), max(1, height // 2)
        if (
            available is not None
            and next_offset + level_bytes(header, next_width, next_height) > available
        ):
            return offset, level, width, height
        offset, width, height = next_offset, next_width, next_height
    return offset, header.mipmaps - 1, width, height


def decode(data: bytes, *, max_side: int | None = None) -> DecodedImage:
    """Decodifica la textura a RGB más alfa, reduciéndola si se pide.

    ``max_side`` es un techo orientativo. Primero se busca un mipmap que lo
    cumpla; si la textura no trae mipmaps, que es casi la mitad del juego, se
    decodifica uno de cada ``step`` píxeles. Las dos vías conservan el alfa, de
    modo que la vista reducida describe la misma textura que la completa.
    """
    header = parse_header(data)
    offset, level, width, height = select_level(header, max_side, len(data))
    needed = offset + level_bytes(header, width, height)
    if len(data) < needed:
        raise FormatError(
            f"El DDS está truncado: hacen falta {needed} bytes y hay {len(data)}"
        )

    step = 1
    if max_side is not None and header.kind not in ("BC4", "BC5"):
        while max(width, height) // step > max_side:
            step *= 2

    if header.kind == "BC1":
        rgb, alpha = _decode_bc1(data, offset, width, height, header.has_alpha, step)
    elif header.kind in ("BC2", "BC3"):
        rgb, alpha = _decode_bc2_bc3(data, offset, width, height, header.kind == "BC3", step)
    elif header.kind in ("BC4", "BC5"):
        rgb, alpha = _decode_bc4_bc5(data, offset, width, height, header.kind == "BC5")
    else:
        rgb, alpha = _decode_raw(data, offset, width, height, header, step)
    return DecodedImage(
        _reduced(width, step), _reduced(height, step), rgb, alpha, level, step, header
    )


def _reduced(size: int, step: int) -> int:
    """Píxeles que quedan al quedarse con uno de cada ``step``."""
    return (size + step - 1) // step


def _channel_scaler(mask: int) -> tuple[int, int]:
    """Desplazamiento y valor máximo para llevar un canal enmascarado a 0..255."""
    if not mask:
        return 0, 0
    shift = (mask & -mask).bit_length() - 1
    return shift, (mask >> shift)


def _decode_raw(
    data: bytes, offset: int, width: int, height: int, header: DdsHeader, step: int = 1
) -> tuple[bytes, bytes | None]:
    red, green, blue, alpha_mask = header.masks
    pixel_bytes = header.bits // 8
    row_bytes = width * pixel_bytes
    out_width, out_height = _reduced(width, step), _reduced(height, step)
    rgb = bytearray(out_width * out_height * 3)
    alpha = bytearray(out_width * out_height) if header.has_alpha else None

    if header.luminance and pixel_bytes == 1:
        # Un solo byte por píxel, como los atlas de fuentes: los tres canales
        # salen del mismo.
        green = blue = red
    direct = {0xFF: 0, 0xFF00: 1, 0xFF0000: 2, 0xFF000000: 3}
    channels = (red, green, blue) if alpha is None else (red, green, blue, alpha_mask)
    if all(direct.get(mask, 4) < pixel_bytes for mask in channels):
        # El caso habitual de la interfaz, B8G8R8A8: cada canal es un byte
        # entero, así que una rebanada por fila hace el trabajo en C en lugar
        # de recorrer los píxeles uno a uno.
        jump = pixel_bytes * step
        for out_y in range(out_height):
            begin = offset + out_y * step * row_bytes
            row = data[begin : begin + row_bytes]
            base = out_y * out_width * 3
            end = base + out_width * 3
            rgb[base:end:3] = row[direct[red] :: jump]
            rgb[base + 1 : end : 3] = row[direct[green] :: jump]
            rgb[base + 2 : end : 3] = row[direct[blue] :: jump]
            if alpha is not None:
                alpha[out_y * out_width : (out_y + 1) * out_width] = row[direct[alpha_mask] :: jump]
        return bytes(rgb), bytes(alpha) if alpha is not None else None

    scalers = [_channel_scaler(mask) for mask in (red, green, blue, alpha_mask)]
    for out_y in range(out_height):
        row_start = offset + out_y * step * row_bytes
        for out_x in range(out_width):
            pixel = row_start + out_x * step * pixel_bytes
            value = int.from_bytes(data[pixel : pixel + pixel_bytes], "little")
            target = (out_y * out_width + out_x) * 3
            for channel, (shift, top) in enumerate(scalers[:3]):
                rgb[target + channel] = ((value >> shift) & top) * 255 // top if top else 0
            if header.luminance:
                # Luminancia: el canal rojo manda y los otros dos lo copian.
                rgb[target + 1] = rgb[target + 2] = rgb[target]
            if alpha is not None:
                shift, top = scalers[3]
                alpha[out_y * out_width + out_x] = (
                    ((value >> shift) & top) * 255 // top if top else 255
                )
    return bytes(rgb), bytes(alpha) if alpha is not None else None


def _rgb565(value: int) -> tuple[int, int, int]:
    return (
        (value >> 11 & 31) * 255 // 31,
        (value >> 5 & 63) * 255 // 63,
        (value & 31) * 255 // 31,
    )


def _colour_palette(c0: int, c1: int, *, four_colours: bool) -> tuple[bytes, bytes, bytes, bytes]:
    r0, g0, b0 = _rgb565(c0)
    r1, g1, b1 = _rgb565(c1)
    first, second = bytes((r0, g0, b0)), bytes((r1, g1, b1))
    if four_colours:
        return (
            first,
            second,
            bytes(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3)),
            bytes(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3)),
        )
    # Modo de tres colores: el cuarto índice es el transparente de BC1.
    return (
        first,
        second,
        bytes(((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2)),
        b"\x00\x00\x00",
    )


def _sampling(step: int) -> tuple[int, range]:
    """Cada cuántos bloques se salta y qué píxeles se toman dentro de cada uno.

    Hasta ``step`` 4 se visitan todos los bloques y se muestrea dentro; a
    partir de ahí ya solo queda un píxel por bloque y se saltan bloques enteros.
    """
    return max(1, step // 4), range(0, 4, min(step, 4))


def _decode_bc1(
    data: bytes, offset: int, width: int, height: int, wants_alpha: bool, step: int = 1
) -> tuple[bytes, bytes | None]:
    blocks_wide = max(1, (width + 3) // 4)
    blocks_high = max(1, (height + 3) // 4)
    out_width, out_height = _reduced(width, step), _reduced(height, step)
    stride = out_width * 3
    rgb = bytearray(stride * out_height)
    alpha = bytearray(b"\xff" * (out_width * out_height)) if wants_alpha else None
    transparent_seen = False
    block_step, samples = _sampling(step)
    for block_y in range(0, blocks_high, block_step):
        row_cursor = offset + block_y * blocks_wide * 8
        for block_x in range(0, blocks_wide, block_step):
            c0, c1, bits = struct.unpack_from("<HHI", data, row_cursor + block_x * 8)
            four_colours = c0 > c1
            palette = _colour_palette(c0, c1, four_colours=four_colours)
            punch_through = alpha is not None and not four_colours
            for row in samples:
                y = block_y * 4 + row
                if y >= height:
                    break
                out_y = y // step
                line = out_y * stride
                shift = row * 8
                for column in samples:
                    x = block_x * 4 + column
                    if x >= width:
                        break
                    code = bits >> (shift + column * 2) & 3
                    target = line + (x // step) * 3
                    rgb[target : target + 3] = palette[code]
                    if punch_through and code == 3:
                        alpha[out_y * out_width + x // step] = 0
                        transparent_seen = True
    if alpha is not None and not transparent_seen:
        return bytes(rgb), None
    return bytes(rgb), bytes(alpha) if alpha is not None else None


def _alpha_table(a0: int, a1: int) -> tuple[int, ...]:
    """Las ocho alfas interpoladas de un bloque BC3/BC4."""
    if a0 > a1:
        return (
            a0, a1,
            (6 * a0 + a1) // 7, (5 * a0 + 2 * a1) // 7, (4 * a0 + 3 * a1) // 7,
            (3 * a0 + 4 * a1) // 7, (2 * a0 + 5 * a1) // 7, (a0 + 6 * a1) // 7,
        )
    return (
        a0, a1,
        (4 * a0 + a1) // 5, (3 * a0 + 2 * a1) // 5,
        (2 * a0 + 3 * a1) // 5, (a0 + 4 * a1) // 5,
        0, 255,
    )


def _decode_bc2_bc3(
    data: bytes, offset: int, width: int, height: int, interpolated: bool, step: int = 1
) -> tuple[bytes, bytes]:
    blocks_wide = max(1, (width + 3) // 4)
    blocks_high = max(1, (height + 3) // 4)
    out_width, out_height = _reduced(width, step), _reduced(height, step)
    stride = out_width * 3
    rgb = bytearray(stride * out_height)
    alpha = bytearray(out_width * out_height)
    block_step, samples = _sampling(step)
    for block_y in range(0, blocks_high, block_step):
        row_cursor = offset + block_y * blocks_wide * 16
        for block_x in range(0, blocks_wide, block_step):
            cursor = row_cursor + block_x * 16
            if interpolated:
                table = _alpha_table(data[cursor], data[cursor + 1])
                codes = int.from_bytes(data[cursor + 2 : cursor + 8], "little")
            else:
                # BC2 guarda cuatro bits de alfa literales por píxel.
                table = None
                codes = int.from_bytes(data[cursor : cursor + 8], "little")
            c0, c1, bits = struct.unpack_from("<HHI", data, cursor + 8)
            # Con alfa aparte, el bloque de color siempre usa los cuatro colores.
            palette = _colour_palette(c0, c1, four_colours=True)
            for row in samples:
                y = block_y * 4 + row
                if y >= height:
                    break
                out_y = y // step
                line = out_y * stride
                shift = row * 8
                for column in samples:
                    x = block_x * 4 + column
                    if x >= width:
                        break
                    out_x = x // step
                    target = line + out_x * 3
                    rgb[target : target + 3] = palette[bits >> (shift + column * 2) & 3]
                    pixel = row * 4 + column
                    if table is None:
                        alpha[out_y * out_width + out_x] = (codes >> (pixel * 4) & 15) * 17
                    else:
                        alpha[out_y * out_width + out_x] = table[codes >> (pixel * 3) & 7]
    return bytes(rgb), bytes(alpha)


def _decode_bc4_bc5(
    data: bytes, offset: int, width: int, height: int, two_channels: bool
) -> tuple[bytes, None]:
    """BC4 como escala de grises y BC5 como mapa de normales en rojo y verde.

    BC5 no guarda el azul: se deja al máximo en lugar de reconstruirlo, que
    costaría una raíz por píxel para una vista previa. El juego no trae
    ninguna de las dos, así que se decodifican siempre enteras.
    """
    stride = width * 3
    rgb = bytearray(stride * height)
    block_bytes = 16 if two_channels else 8
    cursor = offset
    for block_y in range(max(1, (height + 3) // 4)):
        for block_x in range(max(1, (width + 3) // 4)):
            red = _alpha_table(data[cursor], data[cursor + 1])
            red_codes = int.from_bytes(data[cursor + 2 : cursor + 8], "little")
            if two_channels:
                green = _alpha_table(data[cursor + 8], data[cursor + 9])
                green_codes = int.from_bytes(data[cursor + 10 : cursor + 16], "little")
            cursor += block_bytes
            for row in range(4):
                y = block_y * 4 + row
                if y >= height:
                    break
                line = y * stride + block_x * 12
                for column in range(4):
                    if block_x * 4 + column >= width:
                        break
                    pixel = row * 4 + column
                    target = line + column * 3
                    value = red[red_codes >> (pixel * 3) & 7]
                    if two_channels:
                        rgb[target] = value
                        rgb[target + 1] = green[green_codes >> (pixel * 3) & 7]
                        rgb[target + 2] = 255
                    else:
                        rgb[target] = rgb[target + 1] = rgb[target + 2] = value
    return bytes(rgb), None


def to_png(image: DecodedImage, *, mode: str = "color") -> bytes:
    """Convierte la imagen decodificada en un PNG que Tk puede cargar.

    ``mode`` elige qué se mira: ``color`` respeta el alfa, ``opaque`` lo
    ignora y ``alpha`` enseña el canal alfa como escala de grises. La
    compresión va al mínimo porque el PNG solo vive en memoria.
    """
    width, height = image.width, image.height
    if mode == "alpha":
        if image.alpha is None:
            raise FormatError("La textura no tiene canal alfa")
        return _png(image.alpha, width, height, colour_type=0, sample_size=1)
    if mode == "color" and image.alpha is not None:
        pixels = bytearray(width * height * 4)
        pixels[0::4] = image.rgb[0::3]
        pixels[1::4] = image.rgb[1::3]
        pixels[2::4] = image.rgb[2::3]
        pixels[3::4] = image.alpha
        return _png(bytes(pixels), width, height, colour_type=6, sample_size=4)
    return _png(image.rgb, width, height, colour_type=2, sample_size=3)


def _png(pixels: bytes, width: int, height: int, *, colour_type: int, sample_size: int) -> bytes:
    stride = width * sample_size
    # Cada fila va precedida por su byte de filtro, siempre 0: filtrar costaría
    # más tiempo del que ahorra en un buffer que no se guarda.
    raw = b"".join(b"\x00" + pixels[y * stride : (y + 1) * stride] for y in range(height))

    def chunk(tag: bytes, body: bytes) -> bytes:
        block = tag + body
        return struct.pack(">I", len(body)) + block + struct.pack(">I", zlib.crc32(block))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 1))
        + chunk(b"IEND", b"")
    )
