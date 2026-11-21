# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .errors import DarkstractorError
from .gui import DEFAULT_GAME
from .i18n import SUPPORTED_LANGUAGES, get_language, resolve_language, set_language, t
from .settings import load_settings
from .service import (
    ensure_free_space,
    estimate_output_bytes,
    extract_entries,
    human_size,
    kind_label,
    list_obp_members,
    scan_game,
)


def initial_language(argv: list[str] | None = None) -> str:
    """Idioma con el que se construye la CLI: ``--lang``, lo guardado o inglés.

    argparse fija los textos de ayuda al construir el parser, así que ``--lang``
    hay que leerlo antes, con un parser mínimo que no valida nada: un valor
    inválido lo rechaza después el parser de verdad, con su mensaje de error.
    """
    early = argparse.ArgumentParser(add_help=False)
    early.add_argument("--lang", nargs="?")
    known, _rest = early.parse_known_args(argv)
    if known.lang in SUPPORTED_LANGUAGES:
        return known.lang
    return resolve_language(load_settings().get("language"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="darkstractor", description=t("cli.description"))
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--lang", choices=tuple(SUPPORTED_LANGUAGES), help=t("cli.lang_help"))
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help=t("cli.scan_help"))
    scan.add_argument("--game", type=Path, default=DEFAULT_GAME)

    members = subparsers.add_parser("members", help=t("cli.members_help"))
    members.add_argument("--game", type=Path, default=DEFAULT_GAME)
    members.add_argument("--archive", default="media.upak")
    members.add_argument("--filter", required=True, help=t("cli.members_filter_help"))

    extract = subparsers.add_parser("extract", help=t("cli.extract_help"))
    extract.add_argument("--game", type=Path, default=DEFAULT_GAME)
    extract.add_argument("--output", type=Path, required=True)
    extract.add_argument("--archive", help=t("cli.archive_help"))
    extract.add_argument("--filter", default="", help=t("cli.filter_help"))
    extract.add_argument("--inner-filter", help=t("cli.inner_filter_help"))
    extract.add_argument("--raw", action="store_true", help=t("cli.raw_help"))
    extract.add_argument("--overwrite", action="store_true")
    extract.add_argument(
        "--skip-space-check",
        action="store_true",
        help=t("cli.skip_space_help"),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    set_language(initial_language(argv))
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        from .gui import main as gui_main

        gui_main(get_language())
        return 0
    try:
        archives = scan_game(args.game)
        if args.command == "scan":
            for archive in archives:
                size = archive.path.stat().st_size if archive.path.is_file() else sum(entry.size for entry in archive.entries)
                print(f"{archive.name:24} {archive.kind:8} {len(archive.entries):7}  {human_size(size):>10}")
            return 0

        if args.command == "members":
            found = False
            for archive in archives:
                if archive.name.casefold() != args.archive.casefold():
                    continue
                for entry in archive.entries:
                    if entry.kind != "upak-segment" or args.filter.casefold() not in entry.name.casefold():
                        continue
                    found = True
                    print(f"[{entry.name}]")
                    for member in list_obp_members(entry):
                        print(f"{kind_label(member.kind):16} {human_size(member.size):>10}  {member.name}")
            if not found:
                parser.error(t("cli.no_package"))
            return 0

        selected = []
        for archive in archives:
            if args.archive and archive.name.casefold() != args.archive.casefold():
                continue
            selected.extend(entry for entry in archive.entries if args.filter.casefold() in entry.name.casefold())
        if not selected:
            parser.error(t("cli.no_entry"))
        if args.inner_filter:
            inner = []
            for entry in selected:
                if entry.kind != "upak-segment":
                    continue
                try:
                    members = list_obp_members(entry)
                except DarkstractorError:
                    continue
                inner.extend(
                    member
                    for member in members
                    if args.inner_filter.casefold() in member.name.casefold()
                )
            selected = inner
            if not selected:
                parser.error(t("cli.no_inner"))
        if not args.skip_space_check:
            try:
                ensure_free_space(
                    args.output, estimate_output_bytes(selected, auto_unpack=not args.raw)
                )
            except DarkstractorError as exc:
                # La reserva multiplica por 3 lo empaquetado porque zlib puede
                # expandirse mucho. Es deliberadamente pesimista, así que tiene
                # que poder ignorarse en vez de bloquear una extracción viable.
                raise DarkstractorError(t("cli.space_hint", error=exc)) from exc
        results = extract_entries(
            selected,
            args.output,
            auto_unpack=not args.raw,
            policy="overwrite" if args.overwrite else "rename",
            log=print,
        )
        print(t("cli.done", count=len(results)))
        return 0
    except DarkstractorError as exc:
        parser.exit(2, f"error: {exc}\n")
