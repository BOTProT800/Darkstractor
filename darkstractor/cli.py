# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .errors import DarkstractorError
from .gui import DEFAULT_GAME
from .service import (
    ensure_free_space,
    estimate_output_bytes,
    extract_entries,
    human_size,
    list_obp_members,
    scan_game,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="darkstractor", description="Extractor de Darksiders II Deathinitive Edition")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="mostrar el inventario")
    scan.add_argument("--game", type=Path, default=DEFAULT_GAME)

    members = subparsers.add_parser("members", help="mostrar el contenido interno de paquetes OBP")
    members.add_argument("--game", type=Path, default=DEFAULT_GAME)
    members.add_argument("--archive", default="media.upak")
    members.add_argument("--filter", required=True, help="texto contenido en el nombre del paquete")

    extract = subparsers.add_parser("extract", help="extraer recursos")
    extract.add_argument("--game", type=Path, default=DEFAULT_GAME)
    extract.add_argument("--output", type=Path, required=True)
    extract.add_argument("--archive", help="nombre del contenedor, por ejemplo core.pck")
    extract.add_argument("--filter", default="", help="texto contenido en la ruta")
    extract.add_argument("--inner-filter", help="extraer solo miembros internos que contengan este texto")
    extract.add_argument("--raw", action="store_true", help="no descomprimir los segmentos OBP")
    extract.add_argument("--overwrite", action="store_true")
    extract.add_argument(
        "--skip-space-check",
        action="store_true",
        help="extraer sin comprobar el espacio libre (la reserva es pesimista)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        from .gui import main as gui_main

        gui_main()
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
                        print(f"{member.kind.removeprefix('obp-'):16} {human_size(member.size):>10}  {member.name}")
            if not found:
                parser.error("ningún paquete coincide con los filtros")
            return 0

        selected = []
        for archive in archives:
            if args.archive and archive.name.casefold() != args.archive.casefold():
                continue
            selected.extend(entry for entry in archive.entries if args.filter.casefold() in entry.name.casefold())
        if not selected:
            parser.error("ninguna entrada coincide con los filtros")
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
                parser.error("ningún recurso interno coincide con --inner-filter")
        if not args.skip_space_check:
            try:
                ensure_free_space(
                    args.output, estimate_output_bytes(selected, auto_unpack=not args.raw)
                )
            except DarkstractorError as exc:
                # La reserva multiplica por 3 lo empaquetado porque zlib puede
                # expandirse mucho. Es deliberadamente pesimista, así que tiene
                # que poder ignorarse en vez de bloquear una extracción viable.
                raise DarkstractorError(
                    f"{exc}. Añade --skip-space-check para extraer de todas formas"
                ) from exc
        results = extract_entries(
            selected,
            args.output,
            auto_unpack=not args.raw,
            policy="overwrite" if args.overwrite else "rename",
            log=print,
        )
        print(f"Completado: {len(results)} archivos")
        return 0
    except DarkstractorError as exc:
        parser.exit(2, f"error: {exc}\n")
