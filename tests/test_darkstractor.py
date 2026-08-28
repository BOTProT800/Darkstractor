from __future__ import annotations

import struct
import shutil
import unittest
import zlib
from pathlib import Path

from darkstractor.errors import FormatError
from darkstractor.formats.akpk import parse_akpk
from darkstractor.formats.deathinitive_obp import parse_deathinitive_obp
from darkstractor.formats.zlib_stream import declared_size_before, extract_stream, find_next_stream
from darkstractor.models import Entry
from darkstractor.service import destination_for, extract_entries, list_obp_members, safe_relative_path

SCRATCH = Path(__file__).parent / ".tmp"


def make_dds(payload: bytes = b"12345678") -> bytes:
    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x000A1007)
    struct.pack_into("<IIIII", header, 12, 4, 4, 8, 0, 1)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 4)
    header[84:88] = b"DXT1"
    struct.pack_into("<I", header, 108, 0x1000)
    return bytes(header) + payload


def make_obp(members: list[tuple[int, bytes, bytes]], *, named: bool = True) -> bytes:
    """Construye un OBPK sintético.

    Con ``named=False`` reproduce la variante que usan la mayoría de los
    paquetes de ``maps.upak``: solo hashes, sin tabla de nombres.
    """
    payload = b"".join(data for _type_id, _name, data in members)
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
    for _type_id, _name, data in members:
        table += struct.pack("<I", len(data))
    metadata_size = table_offset + len(table) - names_end

    payload_offset = 512
    header = b"OBPK\0" + struct.pack(
        "<IIIIII",
        9,
        table_offset,
        names_end - table_offset,
        names_end,
        metadata_size,
        payload_offset,
    ) + b"\0"
    result = header + table
    result += bytes(payload_offset - len(result))
    return result + struct.pack("<I", len(payload)) + zlib.compress(payload, 9) + bytes(128)


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


class AkpkTests(unittest.TestCase):
    def test_parses_little_endian_sound_table(self) -> None:
        language_section = struct.pack("<III", 1, 12, 0) + "sfx\0".encode("utf-16-le")
        bank_section = struct.pack("<I", 0)
        sound_offset = 0x100
        sound = b"RIFF" + b"audio"
        sound_section = struct.pack("<I", 1) + struct.pack("<IIIII", 1234, 1, len(sound), sound_offset, 0)
        header_size = 0x10 + len(language_section) + len(bank_section) + len(sound_section)
        header = b"AKPK" + struct.pack(
            "<IIIII", header_size, 1, len(language_section), len(bank_section), len(sound_section)
        )
        data = header + language_section + bank_section + sound_section
        data += bytes(sound_offset - len(data)) + sound
        path = SCRATCH / "audio.pck"
        try:
            path.write_bytes(data)
            entries = parse_akpk(path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].name, "audio/1234.wem")
            self.assertEqual(entries[0].offset, sound_offset)
            self.assertEqual(entries[0].size, len(sound))
        finally:
            path.unlink(missing_ok=True)


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


if __name__ == "__main__":
    unittest.main()
