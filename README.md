# Darkstractor

A graphical Python tool for exploring and extracting the contents of
**Darksiders II Deathinitive Edition** on Windows.

Darkstractor only reads. It never writes inside the game installation: every resource comes
out into the output folder you pick, and the game files are left exactly as they were.

## Features

- Reads `manifest.bin` and handles Deathinitive's 64-bit offsets.
- Indexes `media.upak` and `maps.upak`, preserving names and folders.
- Reads the internal table of Deathinitive OBP files and splits their resources out with names
  and types.
- Extracts DDS, O3D, `.2` models, BMAT, ANM, BNK, SMF, LOC, fonts and auxiliary formats directly.
- Automatically decompresses Scaleform `.zgfx` resources to `.gfx`.
- Reads the packages that ship only hashes, with no name table: their members still come out
  split, typed and in order, named `archivo_00000` and upwards.
- Handles the variant that compresses every member into its own zlib chunk, used by the large
  packages such as `armor` and `weapons`. Extracting from those seeks straight to the chosen
  member instead of walking the whole payload.
- Splits the `.wem` audio embedded in Wwise SoundBanks into a folder next to each `.bnk`, which
  is kept.
- When a variant has no usable table, recovers the whole `.bod` through zlib.
- Recovers the zlib streams of `anim_streams.upak` without depending on offzip.
- Extracts Wwise AKPK packages (`core.pck`, `en.pck`, `es.pck`) to `.wem`, preserving their IDs
  and language.
- Copies `.bik` videos, subtitles and auxiliary files.
- Includes search, multiple selection, cancellation and safe policies for duplicate files.
- Requires no QuickBMS, no offzip and no external Python packages.

## Quick start

Requires Python 3.10 or later. In this folder run:

```powershell
python run_darkstractor.py
```

On Windows you can also double-click `Darkstractor.pyw` to start without an extra console.

The default path already points to:

```text
C:\Program Files (x86)\Steam\steamapps\common\Darksiders II Deathinitive Edition
```

1. Press **Analizar**.
2. Pick a container on the left.
3. Filter or select resources in the list on the right.
4. Press **Abrir paquete** — or double-click — to view and select its DDS files, models,
   materials and other internal files.
5. Choose the output folder and press **Extraer selección**.

The **Separar recursos internos** option extracts each member under its own name. Turning it off
keeps the secondary segments as `.obp`.

## Command line

Inventory:

```powershell
python -m darkstractor scan
```

Extract one specific track:

```powershell
python -m darkstractor extract --output .\extraction --archive core.pck --filter 454907743.wem
```

Extract resources whose name contains `death`:

```powershell
python -m darkstractor extract --output .\extraction --archive media.upak --filter death
```

Inspect the contents of a package without extracting it:

```powershell
python -m darkstractor members --archive media.upak --filter ui_buttons_pc
```

Extract only one specific internal resource:

```powershell
python -m darkstractor extract --output .\extraccion --archive media.upak --filter ui_buttons_pc --inner-filter button_caps.dds
```

Use `--raw` to keep UPAK segments as `.obp`, and `--overwrite` to overwrite existing files. By
default, duplicates get a numeric suffix.

## What each container produces

- `media.upak`, `maps.upak` → named internal resources; the whole `.bod` when the variant has no
  table, or the raw `.obp`.
- Type 1 → `.o3d`; type 2 → native `.2` model; type 4 → collision data (sometimes a Havok
  tagfile); type 5 → `.bmat`; type 6 → `.dds`.
- Type 8 → `.anm`; type 9 → `.bnk`; type 12 → `.gfx`; types 11/15/20 → `.smf`, `.sam` and `.loc`.
- `anim_streams.upak` → numbered zlib streams; the extension identifiable from the header is
  preserved.
- `*.pck` → `.wem` and, when the table lists them, `.bnk`.
- Type 9 → the `.bnk` itself plus `<name>_wem/<id>.wem` with the audio it carries inside.
- `video` → exact `.bik` and `.sub` copies.
- `otros` → exact copies of `scripts.obsp` and the world `.bin` files.

## Known limitations

- Models are kept as `.2` and objects as `.o3d`. They are not converted to FBX/GLB, and skeletons
  or weights are not rebuilt.
- `.wem` files stay in the original Wwise format. To interpret them by event or to play dynamic
  music, wwiser and vgmstream are recommended.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Credits

This repository distributes no third-party code or binaries: everything tracked here is original
work and uses only the Python standard library. What does come from outside is **knowledge about
the game's formats**, and that has to be acknowledged.

The readers for `manifest.bin`, OBPK and AKPK are original implementations, but they derive from
descriptions published by other people: the QuickBMS scripts for Darksiders and Darksiders II
(http://quickbms.aluigi.org), the information about the manifest that those scripts credit to
DS2extract, and the ZenHAX thread that documented the later versions of the format. The zlib
stream sweep over `anim_streams.upak` was inspired by the behaviour of offzip, though it does
not use it.

Several of those sources credit no author anywhere verifiable; in `CREDITS.md` they are marked
as pending identification rather than attributed to someone by guesswork.

The full list — authors, sources, licenses, where each one was verified, and what it
contributed — lives in [CREDITS.md](CREDITS.md). It is not repeated here so the two cannot drift
apart.

## License

Darkstractor is released under the **MIT License**. The full text is in [LICENSE](LICENSE).

Copyright (c) 2026 BOTProT800

In short: you may use, copy, modify and redistribute this code, including commercially, as long
as you keep the copyright notice and the license text. The software comes with no warranty of
any kind.

This license covers **only Darkstractor's own code**. The third-party tools and sources cited in
[CREDITS.md](CREDITS.md) keep theirs. Darksiders II Deathinitive Edition, its files and its
assets belong to their respective owners: this project distributes no game content.
