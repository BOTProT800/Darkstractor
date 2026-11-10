# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

import struct
import shutil
import unittest
import zlib
from pathlib import Path

from darkstractor.errors import DarkstractorError, FormatError
from darkstractor.formats import dds
from darkstractor.formats.bnk import parse_bank_media
from darkstractor.formats.deathinitive_obp import parse_deathinitive_obp
from darkstractor.formats.manifest import parse_manifest
from darkstractor.formats.zlib_stream import (
    _HEADER_PATTERN,
    _looks_like_header,
    declared_size_before,
    extract_stream,
    find_next_stream,
)
from darkstractor.models import Entry
from darkstractor.settings import load_settings, save_settings
from darkstractor.service import (
    destination_for,
    estimate_source_bytes,
    extract_entries,
    list_obp_members,
    looks_like_game,
    read_member_bytes,
    safe_relative_path,
)

SCRATCH = Path(__file__).parent / ".tmp"


def make_dds_file(
    payload: bytes,
    *,
    width: int = 4,
    height: int = 4,
    mipmaps: int = 1,
    fourcc: bytes | None = b"DXT1",
    bits: int = 0,
    masks: tuple[int, int, int, int] = (0, 0, 0, 0),
    alpha_pixels: bool = False,
    pixel_flags: int | None = None,
) -> bytes:
    """DDS mínimo pero válido: lo que se lee son sus 128 bytes de cabecera."""
    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x000A1007)
    struct.pack_into("<IIIII", header, 12, height, width, len(payload), 0, mipmaps)
    struct.pack_into("<I", header, 76, 32)
    if fourcc is not None:
        struct.pack_into("<I", header, 80, 0x4 | (0x1 if alpha_pixels else 0))
        header[84:88] = fourcc
    else:
        flags = 0x40 | (0x1 if masks[3] else 0) if pixel_flags is None else pixel_flags
        struct.pack_into("<I", header, 80, flags)
        struct.pack_into("<I", header, 88, bits)
        struct.pack_into("<IIII", header, 92, *masks)
    struct.pack_into("<I", header, 108, 0x1000)
    return bytes(header) + payload


def make_dds(payload: bytes = b"12345678") -> bytes:
    return make_dds_file(payload)


#: Rojo y azul puros en 565, los dos extremos de una paleta BC.
RED565 = 0xF800
BLUE565 = 0x001F


def bc1_block(c0: int, c1: int, codes: list[int]) -> bytes:
    bits = 0
    for index, code in enumerate(codes):
        bits |= (code & 3) << (index * 2)
    return struct.pack("<HHI", c0, c1, bits)


def bc3_block(a0: int, a1: int, alpha_codes: list[int], c0: int, c1: int, codes: list[int]) -> bytes:
    packed = 0
    for index, code in enumerate(alpha_codes):
        packed |= (code & 7) << (index * 3)
    return bytes((a0, a1)) + packed.to_bytes(6, "little") + bc1_block(c0, c1, codes)


def solid_bc1(colour: int, blocks: int) -> bytes:
    """Bloques BC1 de un único color, para distinguir niveles mipmap."""
    return bc1_block(colour, colour, [0] * 16) * blocks


def make_bnk(media: list[tuple[int, bytes]]) -> bytes:
    """SoundBank de Wwise con audio incrustado en DIDX/DATA."""
    index = bytearray()
    payload = bytearray()
    for file_id, audio in media:
        index += struct.pack("<III", file_id, len(payload), len(audio))
        payload += audio
    return (
        b"BKHD" + struct.pack("<I", 8) + bytes(8)
        + b"DIDX" + struct.pack("<I", len(index)) + bytes(index)
        + b"DATA" + struct.pack("<I", len(payload)) + bytes(payload)
        + b"HIRC" + struct.pack("<I", 4) + bytes(4)
    )


def make_obp(members: list[tuple[int, bytes, bytes]], *, named: bool = True, variant: int = 0) -> bytes:
    """Construye un OBPK sintético.

    Con ``named=False`` reproduce la variante que usan la mayoría de los
    paquetes de ``maps.upak``: solo hashes, sin tabla de nombres. Con
    ``variant=1``, la que comprime cada miembro en su propio stream y guarda
    offsets de chunk en lugar de tamaños.
    """
    payload_offset = 512
    if variant == 1:
        chunks = [struct.pack("<I", len(data)) + zlib.compress(data, 9) for _t, _n, data in members]
        table_values = []
        cursor = payload_offset
        for chunk in chunks:
            table_values.append(cursor)
            cursor += len(chunk)
        payload = b"".join(chunks)
    else:
        table_values = [len(data) for _t, _n, data in members]
        raw = b"".join(data for _t, _n, data in members)
        payload = struct.pack("<I", len(raw)) + zlib.compress(raw, 9)

    groups: list[tuple[int, list[tuple[bytes, bytes]]]] = []
    for type_id, name, data in members:
        if not groups or groups[-1][0] != type_id:
            groups.append((type_id, []))
        groups[-1][1].append((name, data))

    table_offset = 30
    table = bytearray()
    table += struct.pack("<IIII", len(groups), len(members), 0, 0)
    table += struct.pack("<IIII", 0, 0, 0, 0)
    for type_id, group_members in groups:
        table += struct.pack("<IIII", type_id, len(group_members), 0, 0)
        table += bytes(len(group_members))
    if named:
        table += struct.pack("<I", 0) + b"\0"
        for _type_id, name, _data in members:
            table += struct.pack("<III", 0, 0, len(name)) + name
    names_end = table_offset + len(table)
    for _type_id, group_members in groups:
        for _name, _data in group_members:
            table += struct.pack("<II", 0, 0)
    for value in table_values:
        table += struct.pack("<I", value)
    metadata_size = table_offset + len(table) - names_end

    header = b"OBPK\0" + struct.pack(
        "<IIIIII",
        9,
        table_offset,
        names_end - table_offset,
        names_end,
        metadata_size,
        payload_offset,
    ) + bytes([variant])
    result = header + table
    result += bytes(payload_offset - len(result))
    return result + payload + bytes(0 if variant == 1 else 128)


def make_manifest(
    paths: list[bytes],
    packs: list[bytes],
    assets: list[tuple[bytes, int, int, int]],
    *,
    version: int = 0x0D,
) -> bytes:
    """`manifest.bin` sintético.

    Cada recurso es ``(nombre, índice de ruta, índice de paquete, offset)``.
    Desde la versión 0x0D los offsets son de 64 bits, que es lo que trae
    Deathinitive; por debajo son de 32.
    """
    data = bytearray(struct.pack("<I", version) + bytes(4 * 10))
    data += struct.pack("<II", len(paths), 0)
    for name in paths:
        data += struct.pack("<QI", 0, len(name)) + name
    data += struct.pack("<I", len(packs))
    for pack in packs:
        data += struct.pack("<BH", 0, len(pack)) + pack
    data += struct.pack("<I", len(assets))
    for filename, path_index, pack_index, offset in assets:
        data += struct.pack("<B", len(filename)) + filename
        data += struct.pack("<QHH", 0, 0, path_index)
        data += struct.pack("<BBBBB", 0, 0, pack_index, 0, 0)
        data += struct.pack("<Q" if version >= 0x0D else "<I", offset)
    return bytes(data)


class PathSafetyTests(unittest.TestCase):
    def test_rejects_parent_traversal(self) -> None:
        with self.assertRaises(Exception):
            safe_relative_path("../../Windows/system.ini")

    def test_sanitizes_windows_names(self) -> None:
        self.assertEqual(safe_relative_path("media/CON/file?.dds"), Path("media/_CON/file_.dds"))

    def test_collision_renaming(self) -> None:
        existing = SCRATCH / "file.bod"
        existing.write_bytes(b"old")
        try:
            self.assertEqual(destination_for(SCRATCH, "file.bod", "rename"), SCRATCH / "file_1.bod")
        finally:
            existing.unlink(missing_ok=True)


class ZlibTests(unittest.TestCase):
    def test_finds_and_extracts_stream_with_declared_size(self) -> None:
        payload = b"BOD" + bytes(range(256)) * 20
        compressed = zlib.compress(payload, 9)
        source = SCRATCH / "sample.upak"
        destination = SCRATCH / "sample.bod"
        try:
            source.write_bytes(b"header" + struct.pack("<I", len(payload)) + compressed + b"tail")
            offset = find_next_stream(source, 0, source.stat().st_size)
            self.assertEqual(offset, 10)
            self.assertEqual(declared_size_before(source, offset), len(payload))
            result = extract_stream(
                source,
                offset,
                source.stat().st_size,
                destination,
                expected_size=len(payload),
            )
            self.assertEqual(result.magic[:3], b"BOD")
            self.assertEqual(destination.read_bytes(), payload)
        finally:
            source.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)


class DeathinitiveObpTests(unittest.TestCase):
    def test_lists_and_extracts_named_members_and_converts_zgfx(self) -> None:
        dds = make_dds()
        gfx = b"GFX" + b"movie-data"
        zgfx = struct.pack("<I", len(gfx)) + zlib.compress(gfx)
        data = make_obp([(6, b"texture", dds), (12, b"menu", zgfx)])

        source = SCRATCH / "fixture.upak"
        output_dir = SCRATCH / "fixture"
        try:
            source.write_bytes(data)
            parsed = parse_deathinitive_obp(source)
            self.assertEqual([(member.name, member.type_id) for member in parsed.members], [("texture", 6), ("menu", 12)])
            outer = Entry("fixture.", 0, len(data), source, "upak-segment")
            members = list_obp_members(outer)
            self.assertEqual([entry.name for entry in members], ["fixture/texture.dds", "fixture/menu.gfx"])
            results = extract_entries(members, SCRATCH)
            self.assertEqual(len(results), 2)
            self.assertEqual((output_dir / "texture.dds").read_bytes(), dds)
            self.assertEqual((output_dir / "menu.gfx").read_bytes(), gfx)
        finally:
            source.unlink(missing_ok=True)
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_recovers_typed_members_when_the_name_table_is_absent(self) -> None:
        dds = make_dds()
        model = b"MODEL" + bytes(64)
        data = make_obp([(6, b"texture", dds), (2, b"model", model)], named=False)

        source = SCRATCH / "sin_nombres.upak"
        output_dir = SCRATCH / "sin_nombres"
        try:
            source.write_bytes(data)
            parsed = parse_deathinitive_obp(source)
            self.assertEqual([member.type_id for member in parsed.members], [6, 2])
            self.assertEqual([member.size for member in parsed.members], [len(dds), len(model)])
            self.assertEqual(
                [member.name for member in parsed.members], ["archivo_00000", "archivo_00001"]
            )
            outer = Entry("sin_nombres.", 0, len(data), source, "upak-segment")
            members = list_obp_members(outer)
            self.assertEqual(
                [entry.name for entry in members],
                ["sin_nombres/archivo_00000.dds", "sin_nombres/archivo_00001.2"],
            )
            extract_entries(members, SCRATCH)
            self.assertEqual((output_dir / "archivo_00000.dds").read_bytes(), dds)
            self.assertEqual((output_dir / "archivo_00001.2").read_bytes(), model)
        finally:
            source.unlink(missing_ok=True)
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_extracts_the_variant_that_compresses_each_member_apart(self) -> None:
        dds = make_dds()
        model = b"MODEL" + bytes(2048)
        data = make_obp([(6, b"texture", dds), (2, b"model", model)], variant=1)

        source = SCRATCH / "por_chunks.upak"
        output_dir = SCRATCH / "por_chunks"
        try:
            source.write_bytes(data)
            parsed = parse_deathinitive_obp(source)
            self.assertEqual(parsed.variant, 1)
            self.assertEqual([member.size for member in parsed.members], [len(dds), len(model)])
            # Cada miembro apunta a su propio stream, no a una posición del payload común.
            self.assertEqual([member.chunk_offset for member in parsed.members][0], 512)
            self.assertTrue(all(member.chunk_offset for member in parsed.members))

            outer = Entry("por_chunks.", 0, len(data), source, "upak-segment")
            extract_entries(list_obp_members(outer), SCRATCH)
            self.assertEqual((output_dir / "texture.dds").read_bytes(), dds)
            self.assertEqual((output_dir / "model.2").read_bytes(), model)
        finally:
            source.unlink(missing_ok=True)
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_splits_the_audio_embedded_in_a_soundbank(self) -> None:
        first, second = b"RIFF" + bytes(60), b"RIFF" + bytes(28)
        bank = make_bnk([(1234, first), (5678, second)])
        data = make_obp([(9, b"combat", bank)])

        source = SCRATCH / "con_banco.upak"
        output_dir = SCRATCH / "con_banco"
        try:
            source.write_bytes(data)
            outer = Entry("con_banco.", 0, len(data), source, "upak-segment")
            results = extract_entries(list_obp_members(outer), SCRATCH)
            # El banco se conserva y el audio sale aparte.
            self.assertEqual((output_dir / "combat.bnk").read_bytes(), bank)
            self.assertEqual((output_dir / "combat_wem" / "1234.wem").read_bytes(), first)
            self.assertEqual((output_dir / "combat_wem" / "5678.wem").read_bytes(), second)
            self.assertEqual(len(results), 3)
        finally:
            source.unlink(missing_ok=True)
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_reports_no_media_for_a_soundbank_that_only_has_events(self) -> None:
        bank = SCRATCH / "solo_eventos.bnk"
        try:
            bank.write_bytes(
                b"BKHD" + struct.pack("<I", 8) + bytes(8) + b"HIRC" + struct.pack("<I", 4) + bytes(4)
            )
            self.assertEqual(parse_bank_media(bank), [])
        finally:
            bank.unlink(missing_ok=True)

    def test_rejects_a_table_whose_sizes_do_not_match_the_payload(self) -> None:
        data = bytearray(make_obp([(6, b"texture", make_dds())]))
        payload_offset = struct.unpack_from("<I", data, 5 + 20)[0]
        struct.pack_into("<I", data, payload_offset, 12345)

        source = SCRATCH / "descuadrado.upak"
        try:
            source.write_bytes(bytes(data))
            with self.assertRaises(FormatError):
                parse_deathinitive_obp(source)
        finally:
            source.unlink(missing_ok=True)


class ProgressEstimateTests(unittest.TestCase):
    """La barra de progreso mide bytes leídos del origen, no bytes escritos."""

    def test_counts_a_shared_stream_once(self) -> None:
        data = make_obp([(6, b"texture", make_dds()), (2, b"model", b"MODEL" + bytes(64))])
        source = SCRATCH / "estimacion.upak"
        try:
            source.write_bytes(data)
            outer = Entry("estimacion.", 0, len(data), source, "upak-segment")
            members = list_obp_members(outer)
            compressed = int(members[0].metadata["compressed_size"])
            # Los dos miembros salen de la misma pasada: el coste no se duplica,
            # y pedir solo uno no la abarata.
            self.assertEqual(estimate_source_bytes(members), compressed)
            self.assertEqual(estimate_source_bytes(members[:1]), compressed)
        finally:
            source.unlink(missing_ok=True)

    def test_counts_only_the_chunks_selected(self) -> None:
        data = make_obp(
            [(6, b"texture", make_dds()), (2, b"model", b"MODEL" + bytes(2048))], variant=1
        )
        source = SCRATCH / "estimacion_chunks.upak"
        try:
            source.write_bytes(data)
            outer = Entry("estimacion_chunks.", 0, len(data), source, "upak-segment")
            members = list_obp_members(outer)
            spans = [int(member.metadata["chunk_span"]) for member in members]
            self.assertEqual(estimate_source_bytes(members), sum(spans))
            self.assertEqual(estimate_source_bytes(members[1:]), spans[1])
            self.assertLess(spans[1], sum(spans))
        finally:
            source.unlink(missing_ok=True)

    def test_progress_stays_within_the_estimate(self) -> None:
        # El modelo se comprime muchísimo: si el progreso contara bytes ya
        # descomprimidos, aquí se saldría de la barra.
        data = make_obp([(6, b"texture", make_dds()), (2, b"model", b"MODEL" + bytes(4096))])
        source = SCRATCH / "progreso.upak"
        output_dir = SCRATCH / "progreso"
        try:
            source.write_bytes(data)
            outer = Entry("progreso.", 0, len(data), source, "upak-segment")
            members = list_obp_members(outer)
            reported: list[int] = []
            extract_entries(members, SCRATCH, progress=reported.append)
            self.assertTrue(reported)
            self.assertLessEqual(sum(reported), estimate_source_bytes(members))
        finally:
            source.unlink(missing_ok=True)
            shutil.rmtree(output_dir, ignore_errors=True)


class ManifestTests(unittest.TestCase):
    """`manifest.bin` es la puerta de entrada de todo `scan_game`."""

    def setUp(self) -> None:
        self.media = SCRATCH / "media_manifest"
        self.media.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.media, ignore_errors=True)

    def _write(self, data: bytes, pack_size: int = 4096) -> Path:
        (self.media / "media.upak").write_bytes(bytes(pack_size))
        manifest = self.media / "manifest.bin"
        manifest.write_bytes(data)
        return manifest

    def test_reads_64_bit_offsets_and_derives_sizes(self) -> None:
        manifest = self._write(
            make_manifest(
                [b"textures", b""],
                [b"media"],
                [
                    (b"hero", 0, 0, 0),
                    (b"sky", 0, 0, 1024),
                    (b"suelto", 1, 0, 3072),
                    # 0xFF marca un recurso que no vive en ningún paquete.
                    (b"fantasma", 0, 0xFF, 0),
                ],
            )
        )
        entries = parse_manifest(manifest, self.media)
        self.assertEqual(
            [entry.name for entry in entries],
            ["media/textures/hero.", "media/textures/sky.", "media/suelto."],
        )
        # El tamaño sale del offset siguiente, y el último llega al final del .upak.
        self.assertEqual([entry.size for entry in entries], [1024, 2048, 1024])
        self.assertTrue(all(entry.kind == "upak-segment" for entry in entries))

    def test_reads_32_bit_offsets_on_older_versions(self) -> None:
        manifest = self._write(
            make_manifest([b"ui"], [b"media"], [(b"boton", 0, 0, 512)], version=0x0C)
        )
        entries = parse_manifest(manifest, self.media)
        self.assertEqual([(entry.name, entry.offset) for entry in entries], [("media/ui/boton.", 512)])

    def test_rejects_an_index_outside_the_tables(self) -> None:
        manifest = self._write(make_manifest([b"ui"], [b"media"], [(b"boton", 9, 0, 0)]))
        with self.assertRaises(FormatError):
            parse_manifest(manifest, self.media)

    def test_ignores_packs_that_are_not_installed(self) -> None:
        manifest = self._write(make_manifest([b"ui"], [b"ausente"], [(b"boton", 0, 0, 0)]))
        self.assertEqual(parse_manifest(manifest, self.media), [])


class HeaderScanTests(unittest.TestCase):
    def test_the_compiled_pattern_matches_the_reference_rule(self) -> None:
        """El barrido rápido debe encontrar exactamente lo mismo que la regla."""
        # Tres bytes que abren dos cabeceras solapadas: una alternancia sin
        # lookahead consumiría la primera y se comería la segunda.
        overlapping = next(
            bytes([first, middle, third])
            for first in range(256)
            for middle in range(256)
            if _looks_like_header(first, middle)
            for third in range(256)
            if _looks_like_header(middle, third)
        )
        data = bytes((index * 37 + index // 251) % 256 for index in range(60_000))
        data += overlapping + zlib.compress(b"carga" * 500, 9) + bytes(64)
        expected = [
            index
            for index in range(len(data) - 1)
            if _looks_like_header(data[index], data[index + 1])
        ]
        self.assertEqual([match.start() for match in _HEADER_PATTERN.finditer(data)], expected)
        self.assertTrue(any(b - a == 1 for a, b in zip(expected, expected[1:])))


class SettingsTests(unittest.TestCase):
    """Las preferencias nunca pueden impedir que la aplicación arranque."""

    def setUp(self) -> None:
        self.config = SCRATCH / "config.json"

    def tearDown(self) -> None:
        self.config.unlink(missing_ok=True)

    def test_round_trip_drops_unknown_keys(self) -> None:
        save_settings(
            {"game": "C:/juego", "collision": "Omitir", "inyectado": "no deberia sobrevivir"},
            self.config,
        )
        self.assertEqual(load_settings(self.config), {"game": "C:/juego", "collision": "Omitir"})

    def test_a_missing_file_is_not_an_error(self) -> None:
        self.assertEqual(load_settings(SCRATCH / "no_existe.json"), {})

    def test_a_corrupt_file_is_not_an_error(self) -> None:
        self.config.write_text("{esto no es json", encoding="utf-8")
        self.assertEqual(load_settings(self.config), {})

    def test_a_json_that_is_not_an_object_is_ignored(self) -> None:
        self.config.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(load_settings(self.config), {})


class GameDetectionTests(unittest.TestCase):
    def test_requires_both_the_manifest_and_the_executable(self) -> None:
        root = SCRATCH / "instalacion"
        try:
            (root / "media").mkdir(parents=True, exist_ok=True)
            self.assertFalse(looks_like_game(root))
            (root / "media" / "manifest.bin").write_bytes(b"x")
            # Solo con el manifiesto todavía no basta: podría ser otro juego.
            self.assertFalse(looks_like_game(root))
            (root / "Darksiders2.exe").write_bytes(b"x")
            self.assertTrue(looks_like_game(root))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_path_that_does_not_exist_is_not_the_game(self) -> None:
        self.assertFalse(looks_like_game(SCRATCH / "ni_existe"))


def png_contents(blob: bytes) -> tuple[int, int, int, bytes]:
    """Devuelve ancho, alto, tipo de color y los bytes ya descomprimidos."""
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("No empieza por la firma PNG")
    position, width, height, colour, payload = 8, 0, 0, 0, b""
    while position < len(blob):
        length = struct.unpack_from(">I", blob, position)[0]
        tag = blob[position + 4 : position + 8]
        body = blob[position + 8 : position + 8 + length]
        if tag == b"IHDR":
            width, height, _depth, colour = struct.unpack_from(">IIBB", body)
        elif tag == b"IDAT":
            payload += body
        position += 12 + length
    return width, height, colour, zlib.decompress(payload)


class DdsDecodingTests(unittest.TestCase):
    def test_decodes_a_bc1_block_into_its_four_colours(self) -> None:
        block = bc1_block(RED565, BLUE565, [0, 1, 2, 3] * 4)
        image = dds.decode(make_dds_file(block))
        self.assertEqual(image.width, 4)
        self.assertEqual(image.header.label, "DXT1")
        self.assertEqual(
            [tuple(image.rgb[index * 3 : index * 3 + 3]) for index in range(4)],
            [(255, 0, 0), (0, 0, 255), (170, 0, 85), (85, 0, 170)],
        )
        self.assertIsNone(image.alpha)

    def test_the_three_colour_mode_turns_the_last_index_transparent(self) -> None:
        # Con c0 <= c1, BC1 cambia a tres colores y un índice transparente.
        block = bc1_block(BLUE565, RED565, [0, 1, 2, 3] * 4)
        image = dds.decode(make_dds_file(block, alpha_pixels=True))
        self.assertIsNotNone(image.alpha)
        self.assertEqual(list(image.alpha[:4]), [255, 255, 255, 0])
        self.assertEqual(tuple(image.rgb[9:12]), (0, 0, 0))

    def test_an_opaque_bc1_does_not_invent_an_alpha_channel(self) -> None:
        block = bc1_block(RED565, BLUE565, [0] * 16)
        image = dds.decode(make_dds_file(block, alpha_pixels=True))
        self.assertIsNone(image.alpha)

    def test_decodes_the_interpolated_alpha_of_bc3(self) -> None:
        block = bc3_block(255, 0, [0, 1, 2, 3] * 4, RED565, BLUE565, [0] * 16)
        image = dds.decode(make_dds_file(block, fourcc=b"DXT5"))
        self.assertEqual(image.header.label, "DXT5")
        self.assertEqual(list(image.alpha[:2]), [255, 0])
        # Los índices intermedios reparten el tramo en siete pasos.
        self.assertEqual(list(image.alpha[2:4]), [(6 * 255) // 7, (5 * 255) // 7])
        self.assertEqual(tuple(image.rgb[:3]), (255, 0, 0))

    def test_decodes_uncompressed_pixels_through_their_masks(self) -> None:
        # B8G8R8A8, el orden que usa la interfaz del juego.
        payload = bytes((0x10, 0x20, 0x30, 0x40)) * 16
        data = make_dds_file(
            payload,
            fourcc=None,
            bits=32,
            masks=(0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000),
        )
        image = dds.decode(data)
        self.assertEqual(image.header.label, "RGB 32 bits")
        self.assertEqual(tuple(image.rgb[:3]), (0x30, 0x20, 0x10))
        self.assertEqual(image.alpha[0], 0x40)

    def test_picks_a_smaller_mipmap_for_the_preview(self) -> None:
        green = 0x07E0
        payload = (
            solid_bc1(RED565, 256)
            + solid_bc1(green, 64)
            + solid_bc1(BLUE565, 16)
            + solid_bc1(0xFFFF, 4)
        )
        data = make_dds_file(payload, width=64, height=64, mipmaps=4)
        self.assertEqual(tuple(dds.decode(data).rgb[:3]), (255, 0, 0))
        preview = dds.decode(data, max_side=16)
        self.assertEqual((preview.width, preview.height, preview.level), (16, 16, 2))
        self.assertEqual(tuple(preview.rgb[:3]), (0, 0, 255))
        self.assertTrue(preview.reduced)

    def test_does_not_trust_mipmaps_the_file_does_not_carry(self) -> None:
        # La cabecera promete cinco niveles y solo viene el primero.
        data = make_dds_file(solid_bc1(RED565, 256), width=64, height=64, mipmaps=5)
        preview = dds.decode(data, max_side=16)
        self.assertEqual((preview.width, preview.height), (16, 16))
        self.assertEqual((preview.level, preview.shrink), (0, 4))
        self.assertEqual(tuple(preview.rgb[:3]), (255, 0, 0))

    def test_samples_pixels_when_there_are_no_mipmaps(self) -> None:
        data = make_dds_file(solid_bc1(RED565, 256), width=64, height=64)
        preview = dds.decode(data, max_side=16)
        self.assertEqual((preview.width, preview.height), (16, 16))
        self.assertEqual((preview.level, preview.shrink), (0, 4))
        self.assertTrue(preview.reduced)
        self.assertEqual(tuple(preview.rgb[:3]), (255, 0, 0))

    def test_a_sampled_preview_keeps_the_alpha_channel(self) -> None:
        # Columnas 0-1 opacas y rojas, columnas 2-3 transparentes y azules.
        block = bc3_block(255, 0, [0, 0, 1, 1] * 4, RED565, BLUE565, [0, 0, 1, 1] * 4)
        data = make_dds_file(block * 4, width=8, height=8, fourcc=b"DXT5")
        preview = dds.decode(data, max_side=4)
        self.assertEqual((preview.width, preview.height, preview.shrink), (4, 4, 2))
        # Uno de cada dos píxeles: se alternan las dos mitades de cada bloque.
        self.assertEqual(list(preview.alpha[:4]), [255, 0, 255, 0])
        self.assertEqual(tuple(preview.rgb[:6]), (255, 0, 0, 0, 0, 255))

    def test_skips_whole_blocks_past_one_pixel_per_block(self) -> None:
        # Solo los bloques de fila y columna pares son rojos: con paso 8 se
        # visita uno de cada dos en cada eje, así que no debe verse el azul.
        payload = b"".join(
            solid_bc1(RED565 if block_x % 2 == 0 and block_y % 2 == 0 else BLUE565, 1)
            for block_y in range(8)
            for block_x in range(8)
        )
        preview = dds.decode(make_dds_file(payload, width=32, height=32), max_side=4)
        self.assertEqual((preview.width, preview.height, preview.shrink), (4, 4, 8))
        self.assertEqual(preview.rgb, bytes((255, 0, 0)) * 16)

    def test_samples_uncompressed_rows(self) -> None:
        # Cuatro píxeles BGRA por fila; el azul lleva el número de columna.
        row = b"".join(bytes((column, 0x20, 0x30, 0xFF)) for column in range(4))
        data = make_dds_file(
            row * 2,
            width=4,
            height=2,
            fourcc=None,
            bits=32,
            masks=(0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000),
        )
        preview = dds.decode(data, max_side=2)
        self.assertEqual((preview.width, preview.height, preview.shrink), (2, 1, 2))
        self.assertEqual(tuple(preview.rgb), (0x30, 0x20, 0, 0x30, 0x20, 2))
        self.assertEqual(tuple(preview.alpha), (0xFF, 0xFF))

    def test_reads_single_byte_luminance(self) -> None:
        # El formato de los atlas de fuentes: un byte de gris por píxel.
        data = make_dds_file(
            bytes(range(16)),
            fourcc=None,
            bits=8,
            masks=(0xFF, 0, 0, 0),
            pixel_flags=0x20000,
        )
        image = dds.decode(data)
        self.assertEqual(image.header.label, "Luminancia 8 bits")
        self.assertEqual(tuple(image.rgb[9:15]), (3, 3, 3, 4, 4, 4))
        self.assertIsNone(image.alpha)

    def test_scales_channels_narrower_than_a_byte(self) -> None:
        # A4R4G4B4: alfa 8, rojo 15, verde 4 y azul 0, cada uno en cuatro bits.
        data = make_dds_file(
            struct.pack("<H", 0x8F40) * 16,
            fourcc=None,
            bits=16,
            masks=(0x0F00, 0x00F0, 0x000F, 0xF000),
        )
        image = dds.decode(data)
        self.assertEqual(image.header.label, "RGB 16 bits")
        self.assertEqual(tuple(image.rgb[:3]), (255, 68, 0))
        self.assertEqual(image.alpha[0], 136)

    def test_refuses_formats_it_cannot_draw(self) -> None:
        block = bc1_block(RED565, BLUE565, [0] * 16)
        with self.assertRaises(FormatError):
            dds.decode(make_dds_file(block * 2, fourcc=b"DX10"))
        with self.assertRaises(FormatError):
            dds.decode(make_dds_file(block, fourcc=b"XYZW"))
        with self.assertRaises(FormatError):
            dds.decode(b"no es un dds" + bytes(200))

    def test_refuses_a_truncated_texture(self) -> None:
        # La cabecera promete 64x64 y el payload solo trae un bloque.
        data = make_dds_file(bc1_block(RED565, BLUE565, [0] * 16), width=64, height=64)
        with self.assertRaises(FormatError):
            dds.decode(data)

    def test_writes_a_png_that_keeps_the_pixels(self) -> None:
        block = bc3_block(255, 1, [0, 1] * 8, RED565, BLUE565, [0, 1] * 8)
        image = dds.decode(make_dds_file(block, fourcc=b"DXT5"))

        width, height, colour, raw = png_contents(dds.to_png(image))
        self.assertEqual((width, height, colour), (4, 4, 6))
        # Cada fila empieza por su byte de filtro, siempre 0.
        self.assertEqual(raw[0], 0)
        self.assertEqual(tuple(raw[1:9]), (255, 0, 0, 255, 0, 0, 255, 1))

        width, height, colour, raw = png_contents(dds.to_png(image, mode="opaque"))
        self.assertEqual(colour, 2)
        self.assertEqual(tuple(raw[1:7]), (255, 0, 0, 0, 0, 255))

        width, height, colour, raw = png_contents(dds.to_png(image, mode="alpha"))
        self.assertEqual((width, colour), (4, 0))
        self.assertEqual(tuple(raw[1:3]), (255, 1))

    def test_the_alpha_view_needs_an_alpha_channel(self) -> None:
        image = dds.decode(make_dds_file(bc1_block(RED565, BLUE565, [0] * 16)))
        with self.assertRaises(FormatError):
            dds.to_png(image, mode="alpha")


class MemberReadingTests(unittest.TestCase):
    """Lectura en memoria de un recurso suelto, sin escribir nada."""

    def _members(self, source: Path, variant: int) -> list[Entry]:
        texture = make_dds_file(bc1_block(RED565, BLUE565, [0, 1, 2, 3] * 4))
        model = b"MODEL" + bytes(2048)
        source.write_bytes(
            make_obp([(2, b"model", model), (6, b"texture", texture)], variant=variant)
        )
        self.texture = texture
        return list_obp_members(Entry(f"{source.stem}.", 0, source.stat().st_size, source, "upak-segment"))

    def test_reads_a_member_of_each_variant_without_touching_the_disk(self) -> None:
        for variant in (0, 1):
            with self.subTest(variant=variant):
                source = SCRATCH / f"memoria_{variant}.upak"
                try:
                    members = self._members(source, variant)
                    before = sorted(item.name for item in SCRATCH.iterdir())
                    data = read_member_bytes(members[1])
                    self.assertEqual(data, self.texture)
                    self.assertEqual(dds.decode(data).width, 4)
                    # Nada nuevo en el directorio: la lectura es solo memoria.
                    self.assertEqual(sorted(item.name for item in SCRATCH.iterdir()), before)
                finally:
                    source.unlink(missing_ok=True)

    def test_refuses_a_member_larger_than_the_memory_limit(self) -> None:
        source = SCRATCH / "memoria_limite.upak"
        try:
            members = self._members(source, 0)
            with self.assertRaises(DarkstractorError):
                read_member_bytes(members[1], limit=16)
        finally:
            source.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
