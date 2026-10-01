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
