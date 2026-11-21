# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

"""Preferencias del usuario, guardadas fuera del repositorio y del juego."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .i18n import resolve_language

#: Solo se conserva lo que el usuario elige a mano. Cualquier otra clave del
#: archivo se descarta al leer, para que una versión anterior o un fichero
#: manipulado no inyecten estado en la aplicación.
KNOWN_KEYS = frozenset({"game", "output", "auto_unpack", "collision", "language"})

#: Políticas de duplicados, en el orden en que las ofrece la interfaz.
COLLISION_POLICIES = ("rename", "skip", "overwrite")
DEFAULT_COLLISION = "rename"

#: Lo que guardaban las versiones anteriores: la etiqueta española del
#: desplegable en lugar de la política. Se acepta al leer y se convierte.
LEGACY_COLLISION_LABELS = {"Renombrar": "rename", "Omitir": "skip", "Sobrescribir": "overwrite"}


def resolve_collision(value: object) -> str:
    """Normaliza la política de duplicados guardada; lo desconocido pasa a renombrar."""
    if isinstance(value, str):
        if value in COLLISION_POLICIES:
            return value
        if value in LEGACY_COLLISION_LABELS:
            return LEGACY_COLLISION_LABELS[value]
    return DEFAULT_COLLISION


def config_path() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / "Darkstractor" / "config.json"


def load_settings(path: Path | None = None) -> dict[str, object]:
    """Lee las preferencias; si no hay o están corruptas, devuelve un dict vacío.

    Nunca lanza: que la configuración falle no puede impedir que la aplicación
    arranque.
    """
    try:
        data = json.loads((path or config_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    values = {key: value for key, value in data.items() if key in KNOWN_KEYS}
    # Los valores con vocabulario cerrado salen ya normalizados: quien los lee
    # no tiene que conocer los formatos antiguos ni defenderse de uno inválido.
    if "collision" in values:
        values["collision"] = resolve_collision(values["collision"])
    if "language" in values:
        values["language"] = resolve_language(values["language"])
    return values


def save_settings(values: dict[str, object], path: Path | None = None) -> None:
    """Guarda las preferencias. Un fallo de escritura se ignora en silencio."""
    destination = path or config_path()
    temporary = destination.with_name(destination.name + ".partial")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: value for key, value in values.items() if key in KNOWN_KEYS}
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, destination)
    except OSError:
        temporary.unlink(missing_ok=True)
