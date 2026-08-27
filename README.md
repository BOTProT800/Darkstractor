# Darkstractor

A graphical Python tool for exploring, extracting and managing modifications for
**Darksiders II Deathinitive Edition** on Windows.

Extraction and repacking happen in separate folders. Installing a mod only happens after an
explicit confirmation, with the game closed, an automatic backup and SHA-256 checks.

## Features

- Reads `manifest.bin` and handles Deathinitive's 64-bit offsets.
- Indexes `media.upak` and `maps.upak`, preserving names and folders.
- Reads the internal table of Deathinitive OBP files and splits their resources out with names
  and types.
- Extracts DDS, O3D, `.2` models, BMAT, ANM, BNK, SMF, LOC, fonts and auxiliary formats directly.
- Automatically decompresses Scaleform `.zgfx` resources to `.gfx`.
- When a variant has no usable table, recovers the whole `.bod` through zlib.
- Recovers the zlib streams of `anim_streams.upak` without depending on offzip.
- Extracts Wwise AKPK packages (`core.pck`, `en.pck`, `es.pck`) to `.wem`, preserving their IDs
  and language.
- Copies `.bik` videos, subtitles and auxiliary files.
- Includes search, multiple selection, cancellation and safe policies for duplicate files.
- Replaces compatible DDS files and generates a complete UPAK copy, verified and with identical
  offsets.
- Generates a safety manifest linking every mod to the exact version of the source UPAK.
- Installs and uninstalls UPAK files with automatic backup, transactional writes and SHA-256
  verification.
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

## Replacing a DDS texture

1. Open the OBP package containing the texture and extract it.
2. Edit the DDS preserving its dimensions, compression format, mipmaps and exact file size.
3. Go back to the open package, select the texture and press **Reemplazar DDS…**.
4. Choose the edited DDS and a location for the new `*_mod.upak` copy.
5. When it finishes, accept **Instalar ahora** or use **Instalar UPAK verificado…** later.

Darkstractor validates the DDS header, rebuilds the zlib stream, checks that the OBP still fits
in its original space, and reads the texture back from the generated UPAK. Next to the UPAK it
creates `*.upak.darkstractor.json`, holding the hashes of both the source and the result. Both
files must stay together for it to be installable.

## Installing and uninstalling safely

1. Close `Darksiders2.exe`.
2. Press **Instalar UPAK verificado…** and select the `*_mod.upak` you generated.
3. Darkstractor checks that the mod has not been altered and that the installed UPAK is exactly
   the version used to create it.
4. Before replacing it, a copy of the previous state is saved and verified in `media\backups`,
   inside the game installation.
5. To uninstall it, press **Restaurar respaldo**. Both the installed file and the backup are
   verified before restoring, too.

The write goes to a temporary file inside the game folder first, and only then replaces the
UPAK. If Windows denies access to `Program Files (x86)`, close Steam and run Darkstractor as
administrator. Backups are kept after restoring, for manual recovery.

If Steam updates or modifies the UPAK, Darkstractor refuses to install an incompatible version.
If another program changes an active mod, the normal restore also stops rather than erasing
those changes; the command line offers `--force` solely for deliberate recovery.

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

Build a modified UPAK from the command line:

```powershell
python -m darkstractor replace-dds `
  --archive media.upak `
  --package ui_buttons_pc `
  --member button_caps.dds `
  --replacement .\editado\button_caps.dds `
  --output .\mods\media_mod.upak
```

Install it with backup and hashes:

```powershell
python -m darkstractor install-upak `
  --input .\mods\media_mod.upak
```

List active modifications and restore the previous state:

```powershell
python -m darkstractor mods
python -m darkstractor restore-upak --archive media.upak
```

You can add `--backup-dir C:\Backups\Darkstractor` to these commands to pick another drive. By
default both the GUI and the command line use `media\backups` inside the game installation.

Use `--raw` to keep UPAK segments as `.obp`, and `--overwrite` to overwrite existing files. By
default, duplicates get a numeric suffix.

## What each container produces

- `media.upak`, `maps.upak` → named internal resources; the whole `.bod` when the variant has no
  table, or the raw `.obp`.
- Type 1 → `.o3d`; type 2 → native `.2` model; type 5 → `.bmat`; type 6 → `.dds`.
- Type 8 → `.anm`; type 9 → `.bnk`; type 12 → `.gfx`; types 11/15/20 → `.smf`, `.sam` and `.loc`.
- `anim_streams.upak` → numbered zlib streams; the extension identifiable from the header is
  preserved.
- `*.pck` → `.wem` and, when the table lists them, `.bnk`.
- `video` → exact `.bik` and `.sub` copies.
- `otros` → exact copies of `scripts.obsp` and the world `.bin` files.

## Known limitations

- Models are kept as `.2` and objects as `.o3d`. They are not converted to FBX/GLB, and skeletons
  or weights are not rebuilt.
- DDS replacement demands the same binary size and the same structure. It does not yet rebuild
  tables or offsets for textures of a different size.
- The UPAK copy is verified structurally, but every modification should still be tested in-game,
  and the original file kept.
- Installing needs free space for a full backup plus another temporary copy of the UPAK;
  `media.upak` takes several GB.
- It does not merge two modified UPAK files automatically. To build a second cumulative change,
  start from the currently installed UPAK or restore the backup first.
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
