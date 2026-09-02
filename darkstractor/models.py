# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Entry:
    name: str
    offset: int
    size: int
    source: Path
    kind: str
    packed_size: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Archive:
    name: str
    path: Path
    kind: str
    entries: list[Entry] = field(default_factory=list)
    note: str = ""

