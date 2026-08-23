from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..binary import BinaryReader
from ..errors import FormatError
from ..models import Entry


@dataclass(slots=True)
class ManifestAsset:
    pack_name: str
    relative_name: str
    offset: int
    size: int = 0


def _safe_count(value: int, label: str, maximum: int = 2_000_000) -> int:
    if value > maximum:
        raise FormatError(f"Cantidad inválida de {label}: {value}")
    return value


def parse_manifest(manifest_path: Path, media_dir: Path | None = None) -> list[Entry]:
    media_dir = media_dir or manifest_path.parent
    with manifest_path.open("rb") as file:
        reader = BinaryReader(file, label=str(manifest_path))
        version = reader.u32()
        if not 1 <= version <= 0x100:
            raise FormatError(f"Versión de manifiesto no reconocida: {version}")

        for _ in range(10):
            reader.u32()

        paths: list[str] = []
        path_count = _safe_count(reader.u32(), "rutas")
        reader.u32()  # contador auxiliar
        for _ in range(path_count):
            reader.u64()  # hash
            paths.append(reader.sized_string(4))

        packs: list[str] = []
        pack_count = _safe_count(reader.u32(), "paquetes", 256)
        for _ in range(pack_count):
            reader.u8()  # bandera
            packs.append(reader.sized_string(2))

        asset_count = _safe_count(reader.u32(), "recursos")
        assets: list[ManifestAsset] = []
        for _ in range(asset_count):
            filename = reader.sized_string(1)
            reader.u64()  # hash
            reader.u16()  # campo desconocido
            path_index = reader.u16()
            alias_count = reader.u8()
            for _ in range(alias_count):
                reader.u16()
            reader.u8()  # campo desconocido
            pack_index = reader.u8()
            reader.u8()
            reader.u8()
            offset = reader.u64() if version >= 0x0D else reader.u32()

            if pack_index == 0xFF:
                continue
            if pack_index >= len(packs) or path_index >= len(paths):
                raise FormatError("El manifiesto contiene un índice fuera de rango")
            pack = packs[pack_index]
            parts = [pack, paths[path_index].replace("\\", "/"), filename]
            relative = str(PurePosixPath(*(part for part in parts if part))) + "."
            assets.append(ManifestAsset(pack, relative, offset))

    by_pack: dict[str, list[ManifestAsset]] = defaultdict(list)
    for asset in assets:
        by_pack[asset.pack_name].append(asset)

    entries: list[Entry] = []
    for pack_name, pack_assets in by_pack.items():
        pack_path = media_dir / f"{pack_name}.upak"
        if not pack_path.is_file():
            continue
        pack_size = pack_path.stat().st_size
        ordered = sorted(pack_assets, key=lambda item: item.offset)
        for index, asset in enumerate(ordered):
            next_offset = ordered[index + 1].offset if index + 1 < len(ordered) else pack_size
            if not 0 <= asset.offset <= next_offset <= pack_size:
                raise FormatError(f"Offsets inválidos para {pack_path.name}")
            asset.size = next_offset - asset.offset
            entries.append(
                Entry(
                    name=asset.relative_name,
                    offset=asset.offset,
                    size=asset.size,
                    source=pack_path,
                    kind="upak-segment",
                    metadata={"pack": pack_name, "manifest": str(manifest_path)},
                )
            )
    return sorted(entries, key=lambda item: (item.source.name.lower(), item.offset))

