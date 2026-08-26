from __future__ import annotations

import struct
import shutil
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from darkstractor.errors import FormatError
from darkstractor.formats.akpk import parse_akpk
from darkstractor.formats.deathinitive_obp import parse_deathinitive_obp
from darkstractor.formats.dds import validate_replacement
from darkstractor.formats.zlib_stream import declared_size_before, extract_stream, find_next_stream
from darkstractor.models import Entry
from darkstractor.repack import build_patched_segment, create_patched_upak
from darkstractor.installation import (
    active_installations,
    install_mod,
    mod_manifest_path,
    read_mod_manifest,
    restore_backup,
)
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


def make_obp(members: list[tuple[int, bytes, bytes]]) -> bytes:
    payload = b"".join(data for _type_id, _name, data in members)
    groups: list[tuple[int, list[tuple[bytes, bytes]]]] = []
    for type_id, name, data in members:
        if not groups or groups[-1][0] != type_id:
            groups.append((type_id, []))
        groups[-1][1].append((name, data))

    table = bytearray()
    table += struct.pack("<IIII", len(groups), len(members), 0, 0)
    table += struct.pack("<IIII", 0, 0, 0, 0)
    for type_id, group_members in groups:
        table += struct.pack("<IIII", type_id, len(group_members), 0, 0)
        table += bytes(len(group_members))
    table += struct.pack("<I", 0) + b"\0"
    for _type_id, name, _data in members:
        table += struct.pack("<III", 0, 0, len(name)) + name
    for _type_id, group_members in groups:
        for _name, _data in group_members:
            table += struct.pack("<II", 0, 0)
    for _type_id, _name, data in members:
        table += struct.pack("<I", len(data))

    payload_offset = 512
    header = b"OBPK\0" + struct.pack("<IIIIII", 9, 30, 0, 0, 0, payload_offset) + b"\0"
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


class DdsTests(unittest.TestCase):
    def test_rejects_same_size_dds_with_different_dimensions(self) -> None:
        original = make_dds()
        changed = bytearray(original)
        struct.pack_into("<I", changed, 16, 8)
        replacement = SCRATCH / "incompatible.dds"
        try:
            replacement.write_bytes(changed)
            with self.assertRaises(FormatError):
                validate_replacement(original[:148], len(original), replacement)
        finally:
            replacement.unlink(missing_ok=True)

    def test_accepts_equivalent_depth_one_for_2d_texture(self) -> None:
        original = make_dds()
        changed = bytearray(original)
        struct.pack_into("<I", changed, 24, 1)
        replacement = SCRATCH / "depth_one.dds"
        try:
            replacement.write_bytes(changed)
            result = validate_replacement(original[:148], len(original), replacement)
            self.assertEqual(result.depth, 1)
        finally:
            replacement.unlink(missing_ok=True)


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

    def test_rebuilds_fixed_size_segment_and_full_upak_copy(self) -> None:
        original_dds = make_dds(b"ORIGINAL")
        replacement_dds = make_dds(b"MODIFIED")
        data = make_obp([(6, b"texture", original_dds), (0, b"object", b"BOD\xfdobject")])
        source = SCRATCH / "repack_source.upak"
        replacement = SCRATCH / "replacement.dds"
        segment = SCRATCH / "patched.obp"
        full_copy = SCRATCH / "patched.upak"
        try:
            source.write_bytes(data)
            replacement.write_bytes(replacement_dds)
            outer = Entry("fixture.", 0, len(data), source, "upak-segment")
            texture = next(entry for entry in list_obp_members(outer) if entry.kind == "obp-dds")
            segment_result = build_patched_segment(texture, replacement, segment)
            self.assertEqual(segment.stat().st_size, source.stat().st_size)
            self.assertGreaterEqual(segment_result.padding, 0)
            copy_result = create_patched_upak(texture, replacement, full_copy)
            self.assertEqual(full_copy.stat().st_size, source.stat().st_size)
            self.assertEqual(copy_result.dds.width, 4)
            manifest = read_mod_manifest(full_copy)
            self.assertEqual(manifest.source_name, source.name)
            self.assertEqual(manifest.source_sha256, copy_result.source_sha256)
            self.assertEqual(manifest.patched_sha256, copy_result.patched_sha256)
            patched_outer = Entry("fixture.", 0, len(data), full_copy, "upak-segment")
            output = SCRATCH / "verify"
            extract_entries([next(e for e in list_obp_members(patched_outer) if e.kind == "obp-dds")], output)
            self.assertEqual((output / "fixture" / "texture.dds").read_bytes(), replacement_dds)
        finally:
            for path in (source, replacement, segment, full_copy, mod_manifest_path(full_copy)):
                path.unlink(missing_ok=True)
            shutil.rmtree(SCRATCH / "verify", ignore_errors=True)


class InstallationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = SCRATCH / "game"
        self.media = self.root / "media"
        self.mods = SCRATCH / "mods"
        self.backups = SCRATCH / "backups"
        self.media.mkdir(parents=True, exist_ok=True)
        self.mods.mkdir(parents=True, exist_ok=True)
        (self.root / "Darksiders2.exe").write_bytes(b"test executable")
        (self.media / "manifest.bin").write_bytes(b"test manifest")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.mods, ignore_errors=True)
        shutil.rmtree(self.backups, ignore_errors=True)

    def _make_mod(self) -> tuple[Path, bytes, bytes]:
        original_dds = make_dds(b"ORIGINAL")
        replacement_dds = make_dds(b"MODIFIED")
        original = make_obp([(6, b"texture", original_dds), (0, b"object", b"BOD\xfdobject")])
        target = self.media / "media.upak"
        replacement = self.mods / "replacement.dds"
        patched = self.mods / "media_mod.upak"
        target.write_bytes(original)
        replacement.write_bytes(replacement_dds)
        outer = Entry("fixture.", 0, len(original), target, "upak-segment")
        texture = next(entry for entry in list_obp_members(outer) if entry.kind == "obp-dds")
        create_patched_upak(texture, replacement, patched)
        return patched, original, patched.read_bytes()

    @patch("darkstractor.installation.is_game_running", return_value=False)
    def test_installs_with_verified_backup_and_restores(self, _running) -> None:
        patched, original, modified = self._make_mod()
        result = install_mod(self.root, patched, backup_root=self.backups)
        self.assertEqual((self.media / "media.upak").read_bytes(), modified)
        self.assertEqual(result.backup.read_bytes(), original)
        self.assertEqual([state.target_name for state in active_installations(self.root, backup_root=self.backups)], ["media.upak"])

        restored = restore_backup(self.root, "media.upak", backup_root=self.backups)
        self.assertEqual((self.media / "media.upak").read_bytes(), original)
        self.assertEqual(restored.installed_sha256, result.previous_sha256)
        self.assertEqual(active_installations(self.root, backup_root=self.backups), [])

    @patch("darkstractor.installation.is_game_running", return_value=False)
    def test_uses_game_media_backup_directory_by_default(self, _running) -> None:
        patched, original, modified = self._make_mod()
        result = install_mod(self.root, patched)

        expected_archive = (self.media / "backups" / "media.upak").resolve()
        self.assertEqual(result.backup.parent, expected_archive)
        self.assertEqual((self.media / "media.upak").read_bytes(), modified)
        self.assertEqual(result.backup.read_bytes(), original)
        self.assertEqual(
            [state.target_name for state in active_installations(self.root)],
            ["media.upak"],
        )

        restore_backup(self.root, "media.upak")
        self.assertEqual((self.media / "media.upak").read_bytes(), original)

    @patch("darkstractor.installation.is_game_running", return_value=False)
    def test_rejects_tampered_mod(self, _running) -> None:
        patched, original, _modified = self._make_mod()
        changed = bytearray(patched.read_bytes())
        changed[-1] ^= 1
        patched.write_bytes(changed)
        with self.assertRaises(FormatError):
            install_mod(self.root, patched, backup_root=self.backups)
        self.assertEqual((self.media / "media.upak").read_bytes(), original)

    @patch("darkstractor.installation.is_game_running", return_value=False)
    def test_rejects_mod_built_for_another_upak_version(self, _running) -> None:
        patched, original, _modified = self._make_mod()
        changed = bytearray(original)
        changed[-1] ^= 1
        (self.media / "media.upak").write_bytes(changed)
        with self.assertRaises(Exception):
            install_mod(self.root, patched, backup_root=self.backups)
        self.assertEqual((self.media / "media.upak").read_bytes(), changed)

    @patch("darkstractor.installation.is_game_running", return_value=False)
    def test_refuses_to_erase_external_change_during_restore(self, _running) -> None:
        patched, original, _modified = self._make_mod()
        install_mod(self.root, patched, backup_root=self.backups)
        target = self.media / "media.upak"
        externally_changed = bytearray(target.read_bytes())
        externally_changed[-1] ^= 1
        target.write_bytes(externally_changed)
        with self.assertRaises(Exception):
            restore_backup(self.root, "media.upak", backup_root=self.backups)
        self.assertEqual(target.read_bytes(), externally_changed)
        restore_backup(self.root, "media.upak", backup_root=self.backups, force=True)
        self.assertEqual(target.read_bytes(), original)

    @patch("darkstractor.installation.is_game_running", return_value=True)
    def test_rejects_install_while_game_is_running(self, _running) -> None:
        patched, original, _modified = self._make_mod()
        with self.assertRaises(Exception):
            install_mod(self.root, patched, backup_root=self.backups)
        self.assertEqual((self.media / "media.upak").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
