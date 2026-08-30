# Credits

Darkstractor is original work by **BOTProT800**, released under the MIT License
(see [LICENSE](LICENSE)). This file records everything of external origin that shaped the
project, following the policy written in [AGENTS.md](AGENTS.md).

Each entry states whether the component **is redistributed inside this repository** or is
**only detected on the system or consulted outside it**, and where its license was verified.

## Redistribution status

**This repository redistributes no third-party binaries or code.** Verified on 2026-08-26 and
re-checked on 2026-08-27 through three separate checks:

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

- **Author(s):** `aluigi` — the author's real name appears in no file of this repository, only
  the project domain. It is not transcribed here so as not to over-attribute.
- **Source:** http://quickbms.aluigi.org (cited in the header of all three `.bms` scripts)
- **License:** **Unknown — needs verification** on the official site or in the `COPYING` of its
  distribution. No copy of its license exists inside this repository.
- **Verified in:** nothing verifiable in the repo; the only evidence is the URL in the headers of
  `darksiders.bms`, `darksiders2.bms` and `darksiders2_pck.bms` (commit `289318a`).
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

## Adapted code

**None in the current tree.** Not a single line in the repository is copied or adapted from a
third party. The format readers are original Python implementations; what was taken from
outside was *knowledge about the formats*, recorded in the two sections below.

## References and documentation

### DS2extract

- **Author(s):** **Unknown — needs verification.** The name appears nowhere in the repository.
- **Source:** cited in the header of `darksiders2.bms`, alongside the thread
  http://zenhax.com/viewtopic.php?t=1738&p=13332#p13332
- **License:** **Unknown — needs verification.**
- **Verified in:** `git show 289318a:darksiders2.bms` (header, lines 1-8).
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

- **Author(s):** **Unknown — needs verification.** The post's author is not stated in the repo.
- **Source:** http://zenhax.com/viewtopic.php?t=1738&p=13332#p13332
- **License:** **Unknown — needs verification** (forum terms).
- **Verified in:** `git show 289318a:darksiders2.bms`, header.
- **Redistribution:** **No.**
- **Added:** 2026-08-22
- **Use:** consulted as a reference.
- **What it gave us:** it documented the `manifest.bin` variant used by the later releases of the
  game, which is the one Deathinitive Edition ships.

### Audiokinetic Wwise AKPK container

- **Author(s):** Audiokinetic (the format); the specific description used comes from
  `darksiders2_pck.bms`, whose author is **unknown — needs verification**.
- **Source:** `git show 289318a:darksiders2_pck.bms`
- **License:** **Unknown — needs verification.**
- **Redistribution:** **No.**
- **Added:** 2026-08-22
- **Where it is used:** [darkstractor/formats/akpk.py](darkstractor/formats/akpk.py)
- **Use:** original implementation derived from an external description of the format.
- **What it gave us:** understanding the `AKPK` header and its entry table (name CRC, alignment
  size, size, and the multiplied offset) in order to extract the `.wem` files from `core.pck`,
  `en.pck` and `es.pck`. Endianness and language detection are our own additions.

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

- **Author(s):** the description used comes from `darksiders.bms`, whose author is **unknown —
  needs verification** (its header only says "Darksiders (script 0.1.1)").
- **Source:** `git show 289318a:darksiders.bms`
- **License:** **Unknown — needs verification.**
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

## History

Third-party components that were once tracked in this repository and no longer are, plus
external resources that shaped code since removed. Nothing is ever deleted from this file: an
entry moves here, dated, when the material it describes stops being used.

### darksiders.bms

- **Author(s):** **Unknown — needs verification.** Header: "Darksiders (script 0.1.1) — script
  for QuickBMS http://quickbms.aluigi.org". It declares neither author nor license.
- **License:** **Unknown — needs verification.**
- **Verified in:** `git show 289318a:darksiders.bms`
- **Redistributed:** **Yes, from 2026-08-22 to 2026-08-25** (95 lines). Removed in `c93ed7f`.
- **Use:** copied verbatim while it was tracked; consulted as a reference afterwards.
- **Modified?:** No.
- **What it gave us:** reading OBPK containers. See the format entry above.

### darksiders2.bms

- **Author(s):** **Unknown — needs verification.** Its header credits DS2extract and the ZenHAX
  thread.
- **License:** **Unknown — needs verification.**
- **Verified in:** `git show 289318a:darksiders2.bms`
- **Redistributed:** **Yes, from 2026-08-22 to 2026-08-25** (131 lines). Removed in `c93ed7f`.
- **Use:** copied verbatim while it was tracked; consulted as a reference afterwards.
- **Modified?:** No.
- **What it gave us:** reading `manifest.bin` and the UPAK references. It also noted that
  `anim_streams` required offzip, a limitation Darkstractor no longer has.

### darksiders2_pck.bms

- **Author(s):** **Unknown — needs verification.** Header: "DarkSiders II core.pck — script for
  QuickBMS http://quickbms.aluigi.org".
- **License:** **Unknown — needs verification.**
- **Verified in:** `git show 289318a:darksiders2_pck.bms`
- **Redistributed:** **Yes, from 2026-08-22 to 2026-08-25** (18 lines). Removed in `c93ed7f`.
- **Use:** copied verbatim while it was tracked; consulted as a reference afterwards.
- **Modified?:** No.
- **What it gave us:** reading the AKPK container. See the format entry above.

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

### DDS format and the DX10/DXGI extension

- **Author(s):** Microsoft (public documentation of the format)
- **Source:** the public DirectDraw Surface specification. **Not verified inside the repo.**
- **License:** the format is publicly documented; **the license of that documentation belongs to
  Microsoft and has not been verified**. No text or code was copied, so it imposes no conditions
  on our own code.
- **Redistribution:** **No.**
- **Added:** 2026-08-22
- **Where it was used:** `darkstractor/formats/dds.py` (deleted on 2026-08-27; the last tracked
  version is `git show b132e3e:darkstractor/formats/dds.py`)
- **Retired:** 2026-08-27. The header reader existed only to validate a replacement texture.
  With the replacement pipeline gone, extraction writes each `.dds` member out byte for byte
  without parsing it, so no knowledge of the format is in use any more.
- **Use:** original implementation based on a publicly documented format.
- **What it gave us:** validating DDS headers (the `DDS ` magic, the 124-byte header, FourCC,
  mipmaps and the DX10 block) before accepting a replacement texture.

## Open compliance obligations

1. **Unverified licenses.** None of the sources above declares a license inside this repository.
   As long as their code is not redistributed this imposes no obligations; **it would if any
   `.bms` came back into the tree.** Under the MIT License the risk runs opposite to copyleft:
   **this project cannot absorb GPL-licensed code or anything similar.** If QuickBMS or its
   scripts turn out to be GPL of any version, bringing them in would force the whole of
   Darkstractor to be relicensed under the GPL. Verify before reinstating any of them.
2. **Unnamed authorship.** Several entries say "Unknown — needs verification" because the source
   file credits nobody. If an author is identified — in the ZenHAX thread, for instance — the
   entry must be completed here, without substituting a real name for a handle without evidence.
3. **No outstanding source-code obligations.** Since no third-party GPL or LGPL binaries are
   redistributed, there are no external license texts to ship and no corresponding source to
   offer. The only obligation in force is MIT's own: anyone redistributing Darkstractor must
   keep the copyright notice and the text of [LICENSE](LICENSE).
4. **No binary bundles to audit.** No executables are tracked, so there is no case of a package
   dragging in components from other projects (FFmpeg DLLs, say) under their own license. If a
   packaged tool is ever tracked, its contents must be reviewed component by component and each
   one given its own notice.
