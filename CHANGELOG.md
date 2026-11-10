# Changelog

All notable changes to Darkstractor are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

No version has been tagged yet: the entries below are reconstructed from the commit history, not
from releases. `0.4.0` describes the state of the tree at commit `839467e`.

## [Unreleased]

### Added

- The extraction progress bar now measures real progress instead of running an indeterminate
  marquee: the status line reports the percentage and the bytes read out of the total.
- The GUI remembers the installation path, the output folder, the "separar recursos internos"
  option and the duplicate policy between runs, in `%APPDATA%\Darkstractor\config.json`.
- The command line checks the free space before extracting, as the GUI already did, and
  `--skip-space-check` skips that check when the reserve estimate is too pessimistic.
- Tests run on CI over Windows and Python 3.10 to 3.13.
- `manifest.bin` is covered by tests for the first time: 64-bit offsets, the 32-bit branch of
  versions before `0x0D`, resources with no pack, out-of-range indices and packs that are not
  installed.
- Every `.py` and `.pyw` carries the two SPDX header lines required by `AGENTS.md`.
- Packaging metadata in `pyproject.toml` (author, license, URLs, classifiers), a
  `darkstractor-gui` entry point that starts without a console, and this changelog.
- A Windows executable built with PyInstaller, published from a tag. See the licensing note in
  [CREDITS.md](CREDITS.md) before publishing one.
- A preview window for the DDS textures inside a package: double-click one, or select it and
  press **Ver imagen**, and it is drawn without extracting anything. The decoder is pure Python
  and covers DXT1, DXT3, DXT5, BC4, BC5 and the uncompressed 8, 16, 24 and 32-bit layouts, with
  colour, opaque and alpha-only views and power-of-two zoom. It opens on a version of at most
  512 px — a mipmap when the texture has them, one pixel out of every few when it does not —
  and **Detalle completo** decodes it at up to 2048 px on request. Checked against all 15,254
  textures in the game: every header is read, and none uses the DX10 variant.
- `read_member_bytes` reads a single package member into memory without touching the disk: it
  seeks straight to the chunk in the per-member variant, and in the single-stream one it stops
  inflating as soon as the member is complete.

### Changed

- Sweeping zlib streams is 6.6x faster: measured over the real 471 MB `anim_streams.upak`,
  3.62 s down to 0.55 s, finding the same headers. The probe reuses the open file descriptor
  instead of reopening it per candidate, resolves from memory when the window is already read,
  and the scan uses a pattern compiled from the reference rule itself.
- Starting the GUI no longer greets the user with an error dialog when the game is not at the
  default Steam path: it says what to do instead.
- The version now lives only in `darkstractor/__init__.py`; `pyproject.toml` reads it from there
  so the two cannot drift.
- `scripts.obsp` and the world `.bin` files are no longer grouped under an invented `otros`
  container with a `misc/` prefix: each one is listed as its own container with its real name,
  and it is extracted to the root of the output folder, as it sits in the game's `media\`.

### Fixed

- The `progress` callback reported mixed units — uncompressed bytes down some paths, compressed
  bytes down others — which made a total impossible to compute. Every path now reports bytes read
  from the source.
- An extraction request that arrived while a worker was still alive was silently dropped but
  still reset the running operation's progress state.

### Removed

- The unused `ObpMember` import and the `Entry.display_size` property, neither of which was
  referenced anywhere.
- Extraction of the Wwise `.pck` packages in `media\sounds_streamed\PC` (`core.pck`, `en.pck`,
  `es.pck`): they are no longer listed as containers, and the AKPK reader
  (`darkstractor/formats/akpk.py`) and its test are gone. The audio embedded in the SoundBanks
  of the OBP packages (type 9) is still split out to `.wem`.

## [0.4.0] - 2026-08-29

- Reads `manifest.bin`, `media.upak`, `maps.upak`, the Deathinitive OBP tables, Wwise AKPK
  packages and SoundBanks, and recovers the zlib streams of `anim_streams.upak`.
- Graphical interface with search, multiple selection, cancellation and duplicate policies, plus
  a command line with `scan`, `members` and `extract`.
- Uses only the Python standard library: no QuickBMS, no offzip, no packages from PyPI.

## [0.3.0] - 2026-08-27

- The mod pipeline was removed: Darkstractor only extracts. It never writes inside the game
  installation.

## [0.2.0] - 2026-08-26

- MIT license, and `CREDITS.md` recording where the knowledge about the formats came from.

## [0.1.0] - 2026-08-22

- First working version.
