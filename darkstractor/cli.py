from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .errors import DarkstractorError
from .gui import DEFAULT_GAME
from .repack import create_patched_upak
from .installation import active_installations, install_mod, restore_backup
from .service import extract_entries, human_size, list_obp_members, scan_game


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

    replace = subparsers.add_parser("replace-dds", help="crear un UPAK con una textura reemplazada")
    replace.add_argument("--game", type=Path, default=DEFAULT_GAME)
    replace.add_argument("--archive", default="media.upak")
    replace.add_argument("--package", required=True, help="texto contenido en el nombre del paquete OBP")
    replace.add_argument("--member", required=True, help="texto contenido en el nombre del DDS interno")
    replace.add_argument("--replacement", type=Path, required=True)
    replace.add_argument("--output", type=Path, required=True)
    replace.add_argument("--overwrite", action="store_true")

    install = subparsers.add_parser("install-upak", help="instalar un UPAK verificado con respaldo automático")
    install.add_argument("--game", type=Path, default=DEFAULT_GAME)
    install.add_argument("--input", type=Path, required=True, help="UPAK generado por Darkstractor")
    install.add_argument("--backup-dir", type=Path)

    restore = subparsers.add_parser("restore-upak", help="restaurar el estado anterior de un UPAK")
    restore.add_argument("--game", type=Path, default=DEFAULT_GAME)
    restore.add_argument("--archive", required=True, help="por ejemplo media.upak")
    restore.add_argument("--backup-dir", type=Path)
    restore.add_argument("--force", action="store_true", help="restaurar aunque el archivo instalado haya cambiado")

    mods = subparsers.add_parser("mods", help="mostrar modificaciones administradas activas")
    mods.add_argument("--game", type=Path, default=DEFAULT_GAME)
    mods.add_argument("--backup-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        from .gui import main as gui_main

        gui_main()
        return 0
    try:
        if args.command == "install-upak":
            result = install_mod(args.game, args.input, backup_root=args.backup_dir, log=print)
            status = "ya estaba instalado" if result.already_done else "instalado y verificado"
            print(f"Completado: {result.target} ({status})")
            print(f"Respaldo: {result.backup}")
            print(f"SHA-256: {result.installed_sha256}")
            return 0

        if args.command == "restore-upak":
            result = restore_backup(
                args.game,
                args.archive,
                backup_root=args.backup_dir,
                force=args.force,
                log=print,
            )
            status = "ya estaba restaurado" if result.already_done else "restaurado y verificado"
            print(f"Completado: {result.target} ({status})")
            print(f"SHA-256: {result.installed_sha256}")
            return 0

        if args.command == "mods":
            states = active_installations(args.game, backup_root=args.backup_dir)
            if not states:
                print("No hay modificaciones activas administradas por Darkstractor.")
            for state in states:
                print(f"{state.target_name}: {state.status} | {state.installed_sha256} | {state.backup_path}")
            return 0

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

        if args.command == "replace-dds":
            matches = []
            for archive in archives:
                if archive.name.casefold() != args.archive.casefold():
                    continue
                for outer in archive.entries:
                    if outer.kind != "upak-segment" or args.package.casefold() not in outer.name.casefold():
                        continue
                    for member in list_obp_members(outer):
                        if member.kind == "obp-dds" and args.member.casefold() in member.name.casefold():
                            matches.append(member)
            if len(matches) != 1:
                parser.error(f"el reemplazo requiere exactamente un DDS coincidente; se encontraron {len(matches)}")
            result = create_patched_upak(
                matches[0],
                args.replacement,
                args.output,
                overwrite=args.overwrite,
                log=print,
            )
            print(
                f"Completado: {result.output} | {result.dds.width}x{result.dds.height} "
                f"{result.dds.format_name} | margen OBP {result.padding} bytes"
            )
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
