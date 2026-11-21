# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

"""Traducción de los textos que ve la persona.

Los catálogos son módulos de Python con un ``dict`` y se importan de forma
estática: PyInstaller los empaqueta sin tocar la receta, y no hacen falta
gettext ni archivos .po/.mo. El idioma activo es un estado del proceso que
fijan la GUI y la CLI al arrancar; los hilos de trabajo solo lo leen.

Las claves van con puntos por zona (``gui.scan``, ``error.manifest_missing``)
y los parámetros, con nombre, se rellenan con ``str.format``.
"""

from __future__ import annotations

from .locales import en, es

#: Cada idioma se nombra en su propia lengua y nunca se traduce: quien no
#: entiende el idioma activo tiene que poder reconocer el suyo.
SUPPORTED_LANGUAGES = {"en": "English", "es": "Español"}
DEFAULT_LANGUAGE = "en"

_CATALOGS: dict[str, dict[str, str]] = {"en": en.MESSAGES, "es": es.MESSAGES}
_current = DEFAULT_LANGUAGE


def resolve_language(value: object) -> str:
    """Normaliza un código de idioma: lo ausente o desconocido pasa a inglés."""
    if isinstance(value, str) and value in SUPPORTED_LANGUAGES:
        return value
    return DEFAULT_LANGUAGE


def set_language(code: object) -> str:
    """Cambia el idioma activo y devuelve el que quedó de verdad."""
    global _current
    _current = resolve_language(code)
    return _current


def get_language() -> str:
    return _current


def t(key: str, **params: object) -> str:
    """Devuelve el texto de ``key`` en el idioma activo.

    Nunca lanza: un texto que falte o no se pueda rellenar no puede tumbar la
    aplicación, ni mucho menos tapar el error que se estaba intentando
    enseñar. Si la clave falta en el idioma activo se usa el inglés, y si
    tampoco está ahí se devuelve la propia clave, que al menos dice qué falta.
    """
    unformatted: str | None = None
    for code in (_current, DEFAULT_LANGUAGE):
        template = _CATALOGS[code].get(key)
        if template is None:
            continue
        try:
            return template.format(**params)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            if unformatted is None:
                unformatted = template
    return unformatted if unformatted is not None else key
