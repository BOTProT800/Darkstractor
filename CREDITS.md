# Credits

Darkstractor is original work by **BOTProT800**, released under the MIT License
(see [LICENSE](LICENSE)). This file records everything of external origin that shaped the
project, following the policy written in [AGENTS.md](AGENTS.md).

Each entry states whether the component **is redistributed inside this repository** or is
**only detected on the system or consulted outside it**, and where its license was verified.

## Redistribution status

**This repository redistributes no third-party binaries or code.** Verified on 2026-08-26,
re-checked on 2026-08-27 and again on 2026-11-01, through three separate checks:

- `git ls-files` across the whole tree: every tracked file is original code, documentation or
  configuration. There is no `vendor/` or `tools/` directory, and no binaries.
- [.gitignore](.gitignore): its only inclusion exception is `!tests/.tmp/.gitkeep`. There are no
  rules of the form `!path/something.exe` forcing an executable to be tracked.
- [pyproject.toml](pyproject.toml): `dependencies = []`. Every `import` in the package resolves
  to the Python standard library (`zlib`, `struct`, `tkinter`, `pathlib`, `threading`, `shutil`,
  `argparse`...).

No third-party code is therefore linked or combined with our own, and the choice of the MIT
License conflicts with no external license in the current state of the tree.

## Tools

### QuickBMS

- **Author(s):** **Luigi Auriemma** (`aluigi`). Checked on 2026-11-01: his own site publishes the
  tool and its scripts under that name, and the official manual carries it too. The earlier
  reticence here is lifted because the source itself states the real name; it is not inferred
  from the handle.
- **Source:** http://quickbms.aluigi.org (cited in the header of all three `.bms` scripts);
  manual at http://aluigi.altervista.org/papers/quickbms.txt
- **License:** **GPL-2.0**, checked on 2026-11-01 in the official manual, which calls it "open
  source under the GPL 2.0 license" and adds that the unmodified `quickbms.exe` may be
  distributed freely, while reusing or modifying its source requires the same or a compatible
  open-source license. Corroborated by the Arch Linux AUR package (`license=('GPL2')`).
  **Consequence for this project: its source code can never be absorbed here**, since that would
  force Darkstractor to be relicensed under the GPL. The tool is neither shipped nor invoked, so
  nothing is owed today.
- **Verified in:** nothing verifiable in the repo; the evidence is external — the official manual
  cited above, plus the URL in the headers of `darksiders.bms`, `darksiders2.bms` and
  `darksiders2_pck.bms` (commit `289318a`).
- **Redistribution:** **No.** The QuickBMS executable was never included. Only three `.bms`
  scripts written for it were, and they have been removed (see [History](#history)).
- **Added:** 2026-08-22 · **Removed from the tree:** 2026-08-25 (`c93ed7f`)
- **Use:** consulted as a reference. Never invoked at runtime.
- **Modified?:** No.
- **What it gave us:** its scripts described the structure of the game's containers and were the
  starting point for writing our own readers in Python. The project no longer needs it: the
  README says so explicitly and the code confirms it.

### offzip

- **Author(s):** not stated in the repository. Referred to by name only.
- **Source:** no URL cited in the repository.
- **License:** **Unknown — needs verification.**
- **Verified in:** nothing verifiable in the repo. It is named in the README (lines 18 and 28)
  and its behaviour is cited as a reference in the comment at
  [darkstractor/service.py:495](darkstractor/service.py:495).
- **Redistribution:** **No.** It is not invoked as a process either.
- **Added:** 2026-08-22 (mentioned in the first commit)
- **Use:** consulted as a behavioural reference.
- **Modified?:** Not applicable.
- **What it gave us:** its policy of continuing the scan instead of aborting when it hits a
  corrupt zlib stream was mirrored in the `anim_streams.upak` sweep, implemented from scratch in
  [darkstractor/formats/zlib_stream.py](darkstractor/formats/zlib_stream.py) using the standard
  library's `zlib` module.

### wwiser and vgmstream

- **Author(s):** not stated in the repository.
- **Source:** no URL cited in the repository.
- **License:** **Unknown — needs verification.** It does not apply to this project while they
  are merely recommended.
- **Verified in:** nothing verifiable in the repo; only the README recommendation (line 176).
- **Redistribution:** **No.** They are neither bundled nor invoked.
- **Added:** 2026-08-22
- **Use:** cited as tools recommended to the end user.
- **Modified?:** Not applicable.
- **What it gave us:** they are the recommended route for interpreting the `.wem` files that
  Darkstractor extracts, a task this project does not cover.

### GitHub Actions: `actions/checkout`, `actions/setup-python`, `actions/upload-artifact`

- **Author(s):** GitHub, Inc.
- **Source:** https://github.com/actions/checkout, https://github.com/actions/setup-python and
  https://github.com/actions/upload-artifact (pinned at `v4`, `v5` and `v4` in
  [.github/workflows/tests.yml](.github/workflows/tests.yml) and
  [.github/workflows/release.yml](.github/workflows/release.yml)). The release workflow also
  calls the GitHub CLI (`gh`), which comes preinstalled on the runner image.
- **License:** declared as MIT in each upstream repository. **Needs verification** against those
  `LICENSE` files before any of their code is ever copied here.
- **Verified in:** nothing verifiable in the repo. Only the two `uses:` lines of the workflow
  reference them; no copy of their code or license exists in this tree.
- **Redistribution:** **No.** They run on GitHub's infrastructure during CI. Nothing from them is
  tracked here, and they do not ship with Darkstractor.
- **Added:** 2026-08-31
- **Where it is used:** [.github/workflows/tests.yml](.github/workflows/tests.yml) and
  [.github/workflows/release.yml](.github/workflows/release.yml)
- **Use:** invoked as CI steps. Not consulted as a reference and not adapted.
- **Modified?:** No.
- **What it gave us:** they check out the repository and install the Python matrix (3.10 to 3.13)
  on which the test suite runs. They touch none of Darkstractor's code and impose no obligation
  on what it distributes, since the released artifact never contains them.

### PyInstaller

- **Author(s):** the PyInstaller Development Team.
- **Source:** https://github.com/pyinstaller/pyinstaller
- **License:** **GPL-2.0-or-later WITH a bootloader exception — needs verification** against the
  `COPYING.txt` of the exact version the workflow installs. The exception is what allows the
  bootloader to be linked into an application that is not GPL; without it, shipping the
  executable would drag Darkstractor into the GPL. This has to be confirmed, not assumed.
- **Verified in:** nothing verifiable in the repo. PyInstaller is not tracked here; it is
  installed by [.github/workflows/release.yml](.github/workflows/release.yml) at build time.
- **Redistribution:** **Not in the repository.** But the `Darkstractor.exe` the recipe produces
  **embeds PyInstaller's bootloader and the CPython runtime**. Publishing that file is
  redistributing third-party binaries, so before any release is cut, the licenses of those
  components must accompany it and the exact source release of each must be stated. See
  [Open compliance obligations](#open-compliance-obligations), point 5.
- **Added:** 2026-09-02
- **Where it is used:** [darkstractor.spec](darkstractor.spec) and
  [.github/workflows/release.yml](.github/workflows/release.yml)
- **Use:** invoked as a build tool. No line of its code is copied or adapted.
- **Modified?:** No.
- **What it gave us:** a single-file Windows executable, so the tool reaches people who do not
  have Python installed. Nothing in Darkstractor imports it or depends on it at runtime.

## Adapted code

**None in the current tree.** Not a single line in the repository is copied or adapted from a
third party. The format readers are original Python implementations; what was taken from
outside was *knowledge about the formats*, recorded in the two sections below.

## References and documentation

### DS2extract

- **Author(s):** `Sir Kane` (a handle; no real name at the source). Checked on 2026-11-01 in the
  thread below: `zardalu` writes to Sir Kane about updating DS2Extract and relays his reply, and
  `aluigi` states in the same thread that he neither wrote nor supports the tool.
- **Source:** cited in the header of `darksiders2.bms`, alongside the thread
  http://zenhax.com/viewtopic.php?t=1738&p=13332#p13332
- **License:** **Unknown — needs verification.** The thread links the tool but states no license,
  and ZenHAX is offline.
- **Verified in:** `git show 289318a:darksiders2.bms` (header, lines 1-8); authorship in the
  thread mirror https://www.zenhax.com/viewtopic.php@t=1738.html (posts of 2015-11-13 and
  2015-11-16).
- **Redistribution:** **No.** It was never in the repository.
- **Added:** 2026-08-22 (by way of `darksiders2.bms`)
- **Where it is used:** [darkstractor/formats/manifest.py](darkstractor/formats/manifest.py)
- **Use:** consulted as a reference, indirectly.
- **Modified?:** Not applicable.
- **What it gave us:** the header of `darksiders2.bms` credits DS2extract for the information
  about `manifest.bin`. **The manifest reader is our own implementation, but it derives from
  that external description of the format**: version, ten-integer header, path table with 64-bit
  hashes, and the UPAK references.

### ZenHAX thread on the Darksiders II manifests

- **Author(s):** opened by `zardalu` on 2015-11-09. The 64-bit offsets information is his post of
  2015-11-16 relaying `Sir Kane`, and `aluigi` posted the patched tool on 2016-05-13. All three
  are handles, with no real names at the source. Checked on 2026-11-01.
- **Source:** http://zenhax.com/viewtopic.php?t=1738&p=13332#p13332 — ZenHAX is offline; read
  through the mirror https://www.zenhax.com/viewtopic.php@t=1738.html
- **License:** **Unknown — needs verification** (forum terms; the site is no longer up to state
  them).
- **Verified in:** `git show 289318a:darksiders2.bms`, header; thread contents in the mirror
  above.
- **Redistribution:** **No.**
- **Added:** 2026-08-22
- **Use:** consulted as a reference.
- **What it gave us:** it documented the `manifest.bin` variant used by the later releases of the
  game, which is the one Deathinitive Edition ships.

### Audiokinetic Wwise SoundBank (`.bnk`)

- **Author(s):** Audiokinetic (the format). The section layout is publicly documented by the
  Wwise modding community — most visibly by the **wwiser** project — but **no single source was
  consulted for this implementation**, so no individual is credited here.
- **Source:** none consulted; the layout was applied from the format's public description and
  then verified against the game's own banks.
- **License:** **Unknown — needs verification.**
- **Redistribution:** **No — only consulted.**
- **Added:** 2026-08-27
- **Where it is used:** [darkstractor/formats/bnk.py](darkstractor/formats/bnk.py)
- **Use:** original implementation.
- **What it gave us:** the chunked section layout (`BKHD`, `DIDX`, `DATA`, `HIRC`) and the fact
  that `DIDX` holds `{id, offset, size}` triples whose offsets are relative to `DATA`. That is
  what allows splitting the 6813 `.wem` embedded across the game's SoundBanks.

### OBPK container of the Darksiders engine

- **Author(s):** the description used comes from `darksiders.bms`, published by **Luigi
  Auriemma** (`aluigi`) in his own scripts directory; its header only says "Darksiders (script
  0.1.1)" and names nobody, so the attribution rests on where it is published, not on a
  signature (checked 2026-11-01).
- **Source:** `git show 289318a:darksiders.bms`; still online at
  http://aluigi.altervista.org/bms/darksiders.bms
- **License:** **None stated at the source.** Checked on 2026-11-01 in the three places where one
  could appear: the script's header, the QuickBMS scripts page and the official manual, which
  licenses only the tool and says nothing about the scripts.
- **Redistribution:** **No** in the current tree; the script was tracked until `c93ed7f`
  (see History).
- **Added:** 2026-08-22
- **Where it is used:** [darkstractor/formats/deathinitive_obp.py](darkstractor/formats/deathinitive_obp.py)
- **Use:** original implementation derived from an external description of the format.
- **What it gave us:** the `OBPK\0` identifier, the hashed name table and the folder tree.
  **The Deathinitive Edition variant with 64-bit offsets and its internal type table is our own
  work**, not covered by that script.
- **Update 2026-08-27:** the header anchors that make the table readable — the absolute end of
  the name table and the size of the metadata block that follows it — were derived here by
  comparing packages against the installed game, with no external source. They are what allows
  reading the map packages that ship only hashes and no name table. The second variant — one
  zlib chunk per member, with the table holding chunk offsets instead of sizes — was worked out
  the same way and is likewise ours.

### Scaleform GFX (`.zgfx`)

- **Author(s):** Scaleform / Autodesk (the format). Nobody is credited in the repository.
- **Source:** not cited in the repository.
- **License:** **Unknown — needs verification.**
- **Redistribution:** **No.**
- **Added:** 2026-08-22
- **Where it is used:** [darkstractor/service.py](darkstractor/service.py)
- **Use:** general knowledge of the format.
- **What it gave us:** knowing that `.zgfx` resources are zlib-compressed GFX files, which lets
  us decompress them to `.gfx` with the standard library.

### DDS container and block compression (BC1-BC5)

- **Author(s):** Microsoft (public documentation of both the container and the compression)
- **Source:** "Programming Guide for DDS",
  https://learn.microsoft.com/en-us/windows/win32/direct3ddds/dx-graphics-dds-pguide, and
  "Texture Block Compression in Direct3D 11",
  https://learn.microsoft.com/en-us/windows/win32/direct3d11/texture-block-compression-in-direct3d-11
  (both reachable and on topic, checked 2026-11-09).
- **License:** the format is publicly documented; **the license of that documentation belongs to
  Microsoft and has not been verified**. No text or code was copied, so it imposes no conditions
  on our own code.
- **Verified in:** nothing verifiable in the repo — only the specification was read, and the
  implementation is our own.
- **Redistribution:** **No — only consulted.**
- **Added:** 2026-08-22. Retired on 2026-08-27 with the texture-replacement pipeline, and
  reinstated on 2026-11-09 for the preview window, which needs to decode the pixels and not just
  validate the header.
- **Where it is used:** [darkstractor/formats/dds.py](darkstractor/formats/dds.py). The previous,
  header-only version is `git show b132e3e:darkstractor/formats/dds.py`.
- **Use:** original implementation based on a publicly documented format.
- **Modified?:** Not applicable — nothing external was taken to modify.
- **What it gave us:** the 128-byte header layout (the `DDS ` magic, dimensions, mipmap count,
  the pixel-format block with its FourCC and channel masks, and the DX10 block we reject), how
  each mipmap level is laid out one after another, and the rules for decoding the blocks: the
  565 endpoints and their interpolated palette in BC1 together with its three-colour
  punch-through mode, the explicit four-bit alpha of BC2, the eight-step interpolated alpha of
  BC3, and the single- and two-channel variants BC4 and BC5.

### Portable Network Graphics (PNG) specification

- **Author(s):** W3C (PNG Working Group); the Third Edition names its editors on the document
  itself.
- **Source:** "Portable Network Graphics (PNG) Specification (Third Edition)", W3C
  Recommendation of 24 June 2025, https://www.w3.org/TR/png-3/ (checked 2026-11-09).
- **License:** the specification is published under the **W3C Software and Document Notice and
  License**, linked from the document itself (https://www.w3.org/copyright/software-license-2023/,
  checked 2026-11-09). It is a permissive license, compatible with the MIT License of this
  project, and nothing of its text was copied anyway.
- **Verified in:** nothing verifiable in the repo — only the specification was read.
- **Redistribution:** **No — only consulted.**
- **Added:** 2026-11-09
- **Where it is used:** [darkstractor/formats/dds.py](darkstractor/formats/dds.py), in `to_png`.
- **Use:** consulted as a reference.
- **Modified?:** Not applicable.
- **What it gave us:** how to write the minimal PNG that Tk can load from memory: the signature,
  the `IHDR`, `IDAT` and `IEND` chunks with their CRC-32, the colour types for greyscale, RGB and
  RGBA, and the per-row filter byte. It is what lets the preview reach the interface without
  writing any image to disk or depending on an external library.

## History

Third-party components that were once tracked in this repository and no longer are, plus
external resources that shaped code since removed. Nothing is ever deleted from this file: an
entry moves here, dated, when the material it describes stops being used.

### darksiders.bms

- **Author(s):** **Luigi Auriemma** (`aluigi`), by publication: the script is served from his own
  scripts directory (checked 2026-11-01). Its header — "Darksiders (script 0.1.1) — script for
  QuickBMS http://quickbms.aluigi.org" — declares neither author nor license.
- **License:** **None stated at the source** (see the OBPK entry for the three places checked).
- **Verified in:** `git show 289318a:darksiders.bms`; origin at
  http://aluigi.altervista.org/bms/darksiders.bms
- **Redistributed:** **Yes, from 2026-08-22 to 2026-08-25** (95 lines). Removed in `c93ed7f`.
- **Use:** copied verbatim while it was tracked; consulted as a reference afterwards.
- **Modified?:** No.
- **What it gave us:** reading OBPK containers. See the format entry above.

### darksiders2.bms

- **Author(s):** **Luigi Auriemma** (`aluigi`), stated by himself: in ZenHAX thread t=2332
  (2016-06-13) he links this script and calls it his own. Its header credits DS2extract and the
  ZenHAX thread for the manifest information, but names no author.
- **License:** **None stated at the source** (see the OBPK entry for the three places checked).
- **Verified in:** `git show 289318a:darksiders2.bms`; authorship in the mirror
  http://zenhax.com/viewtopic.php@t=2332&start=20.html, origin at
  http://aluigi.altervista.org/bms/darksiders2.bms
- **Redistributed:** **Yes, from 2026-08-22 to 2026-08-25** (131 lines). Removed in `c93ed7f`.
- **Use:** copied verbatim while it was tracked; consulted as a reference afterwards.
- **Modified?:** No.
- **What it gave us:** reading `manifest.bin` and the UPAK references. It also noted that
  `anim_streams` required offzip, a limitation Darkstractor no longer has.

### darksiders2_pck.bms

- **Author(s):** **Luigi Auriemma** (`aluigi`), by publication — see the AKPK entry below
  for what that attribution rests on and what it does not. Header: "DarkSiders II core.pck —
  script for QuickBMS http://quickbms.aluigi.org", with no author and no license.
- **License:** **None stated at the source** (checked 2026-11-01; see the AKPK entry).
- **Verified in:** `git show 289318a:darksiders2_pck.bms`; still online and byte-identical at
  http://aluigi.altervista.org/bms/darksiders2_pck.bms — md5 `e48ea10fcc071f38b1c83454cbb5d083`
  on both once line endings are normalised (344 bytes with LF here, 362 with CRLF there).
- **Redistributed:** **Yes, from 2026-08-22 to 2026-08-25** (18 lines). Removed in `c93ed7f`.
- **Use:** copied verbatim while it was tracked; consulted as a reference afterwards.
- **Modified?:** No.
- **What it gave us:** reading the AKPK container. See the AKPK format entry below, also retired.

### tasklist (Microsoft Windows)

- **Author(s):** Microsoft
- **Source:** utility shipped with Windows (`System32\tasklist.exe`)
- **License:** the user's operating system license. It does not apply to this project's code.
- **Verified in:** not applicable; it is an operating system component.
- **Redistribution:** **No — only detected on the system.** It runs as a separate process, which
  is mere aggregation and does not affect Darkstractor's license.
- **Added:** 2026-08-22
- **Where it was used:** `darkstractor/installation.py` (deleted on 2026-08-27; the last tracked
  version is `git show b132e3e:darkstractor/installation.py`)
- **Retired:** 2026-08-27. Darkstractor no longer installs or restores UPAK files, so it no
  longer needs to check whether `Darksiders2.exe` is running. `tasklist` is invoked nowhere in
  the tree and no `subprocess` call survives in the package.
- **Use:** invoked as an external process.
- **Modified?:** No.
- **What it gave us:** checking whether `Darksiders2.exe` is still running before touching an
  installed UPAK.

### Audiokinetic Wwise AKPK container

- **Author(s):** Audiokinetic (the format). The specific description used comes from
  `darksiders2_pck.bms`, published by **Luigi Auriemma** (`aluigi`) in his own scripts directory.
  Checked on 2026-11-01: the file is served from `aluigi.altervista.org/bms/`, the directory
  behind the "My scripts" list on his QuickBMS page, where externally contributed scripts are
  instead flagged as not written by him. **The file itself credits nobody** and no post naming
  its author was found, so the attribution rests on where it is published and on that author's
  own `<game>_pck.bms` naming convention, not on a signature.
- **Source:** `git show 289318a:darksiders2_pck.bms`; still online and byte-identical at
  http://aluigi.altervista.org/bms/darksiders2_pck.bms (checked 2026-11-01)
- **License:** **None stated at the source.** Checked on 2026-11-01 in the script's own header,
  the QuickBMS scripts page and the official manual, which licenses only the tool. It therefore
  stays **unverifiable**, not permissive by default.
- **Redistribution:** **No.**
- **Added:** 2026-08-22
- **Where it was used:** `darkstractor/formats/akpk.py` (deleted on 2026-11-03; the last tracked
  version is `git show 40b83d1:darkstractor/formats/akpk.py`)
- **Retired:** 2026-11-03. Darkstractor no longer lists or extracts the Wwise `.pck` packages in
  `media\sounds_streamed\PC`, so the AKPK reader was removed along with its test. Nothing in the
  tree reads that format any more. The `.bnk` SoundBanks inside the OBP packages are a different
  format and are still split (see the SoundBank entry above).
- **Use:** original implementation derived from an external description of the format.
- **What it gave us:** understanding the `AKPK` header and its entry table (name CRC, alignment
  size, size, and the multiplied offset) in order to extract the `.wem` files from `core.pck`,
  `en.pck` and `es.pck`. Endianness and language detection were our own additions.

## Open compliance obligations

1. **Licenses: the tool is settled, the scripts are not.** Audited on 2026-11-01. **QuickBMS is
   GPL-2.0** (official manual, corroborated by its AUR package), so what the earlier wording left
   as a hypothesis is now a fact: **its source code can never enter this MIT-licensed tree**,
   since that would force the whole of Darkstractor to be relicensed under the GPL. Its
   unmodified executable may be redistributed, but this project neither ships nor invokes it, so
   nothing is owed. **The three `.bms` scripts state no license anywhere** — not in their headers,
   not on the scripts page, not in the manual, which licenses only the tool. While no `.bms` is
   tracked here that imposes no obligations; **reinstating one would mean asking its author
   first**, because absent a license nothing grants the right to redistribute it, and the GPL of
   the interpreter says nothing about the scripts it reads.
2. **Authorship: identified, with one caveat.** The three scripts are attributed to **Luigi
   Auriemma** (`aluigi`), whose real name his own site publishes; `darksiders2.bms` he states as
   his own in ZenHAX t=2332. **`darksiders2_pck.bms` carries no signature**: it is attributed by
   where it is published, which is weaker than a statement, so if evidence ever turns up that
   someone else wrote it, this file must be corrected. DS2extract is `Sir Kane` and the manifest
   thread is `zardalu`, handles kept as handles because no real name appears at the source. Left
   open, outside the scope of that audit: **offzip**, **wwiser** and **vgmstream**. No code of
   theirs is here — offzip is cited only as a behavioural reference, the other two only as tools
   recommended to the user — so none of them imposes anything today.
3. **No outstanding source-code obligations.** Since no third-party GPL or LGPL binaries are
   redistributed, there are no external license texts to ship and no corresponding source to
   offer. The only obligation in force is MIT's own: anyone redistributing Darkstractor must
   keep the copyright notice and the text of [LICENSE](LICENSE).
4. **No binary bundles to audit.** No executables are tracked, so there is no case of a package
   dragging in components from other projects (FFmpeg DLLs, say) under their own license. If a
   packaged tool is ever tracked, its contents must be reviewed component by component and each
   one given its own notice.
5. **The Windows executable is not cleared yet.** The build recipe exists
   ([darkstractor.spec](darkstractor.spec)) but **no binary has been published**. The `.exe`
   bundles PyInstaller's bootloader and the CPython runtime, which is the exact situation point 4
   describes. Before the first release: confirm PyInstaller's bootloader exception in the
   `COPYING.txt` of the version being used, ship the PSF license for the bundled CPython and
   PyInstaller's own notice alongside the download, and state which release of each was used.
   Adding the recipe imposes nothing; publishing the binary does.
