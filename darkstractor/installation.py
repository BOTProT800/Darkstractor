from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable

from .errors import CancelledError, DarkstractorError, FormatError

Log = Callable[[str], None]
Progress = Callable[[int], None]

MANIFEST_SUFFIX = ".darkstractor.json"
STATE_SCHEMA = 1
COPY_BLOCK = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ModManifest:
    schema: int
    tool: str
    tool_version: str
    created_at: str
    source_name: str
    source_size: int
    source_sha256: str
    patched_size: int
    patched_sha256: str
    texture_name: str
    segment_offset: int
    segment_size: int


@dataclass(slots=True)
class InstallState:
    schema: int
    status: str
    game_root: str
    target_name: str
    backup_path: str
    backup_size: int
    backup_sha256: str
    installed_sha256: str
    mod_path: str
    installed_at: str


@dataclass(frozen=True, slots=True)
class InstallationResult:
    action: str
    target: Path
    backup: Path
    previous_sha256: str
    installed_sha256: str
    already_done: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mod_manifest_path(patched: Path) -> Path:
    return patched.with_name(patched.name + MANIFEST_SUFFIX)


def _validate_sha256(value: object, field: str) -> str:
    text = str(value).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise FormatError(f"El campo {field} no contiene un SHA-256 válido")
    return text


def read_mod_manifest(patched: Path) -> ModManifest:
    manifest_path = mod_manifest_path(patched)
    if not manifest_path.is_file():
        raise DarkstractorError(
            f"Falta el manifiesto de seguridad {manifest_path.name}. "
            "Genera de nuevo el UPAK con esta versión de Darkstractor."
        )
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ModManifest(
            schema=int(raw["schema"]),
            tool=str(raw["tool"]),
            tool_version=str(raw["tool_version"]),
            created_at=str(raw["created_at"]),
            source_name=str(raw["source_name"]),
            source_size=int(raw["source_size"]),
            source_sha256=_validate_sha256(raw["source_sha256"], "source_sha256"),
            patched_size=int(raw["patched_size"]),
            patched_sha256=_validate_sha256(raw["patched_sha256"], "patched_sha256"),
            texture_name=str(raw["texture_name"]),
            segment_offset=int(raw["segment_offset"]),
            segment_size=int(raw["segment_size"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FormatError(f"Manifiesto de mod inválido: {manifest_path}") from exc
    if manifest.schema != STATE_SCHEMA or manifest.tool != "Darkstractor":
        raise FormatError("El manifiesto pertenece a una versión no compatible")
    if Path(manifest.source_name).name != manifest.source_name or not manifest.source_name.lower().endswith(".upak"):
        raise FormatError("El manifiesto contiene un nombre de destino inseguro")
    if manifest.source_size <= 0 or manifest.patched_size != manifest.source_size:
        raise FormatError("El manifiesto no conserva el tamaño del UPAK original")
    return manifest


def write_mod_manifest(path: Path, manifest: ModManifest) -> None:
    temporary = path.with_name(path.name + ".partial")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(asdict(manifest), output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def hash_file(
    path: Path,
    *,
    cancel: Event | None = None,
    progress: Progress | None = None,
) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(COPY_BLOCK):
            if cancel and cancel.is_set():
                raise CancelledError("Operación cancelada")
            digest.update(block)
            if progress:
                progress(len(block))
    return digest.hexdigest()


def _copy_and_hash(
    source: Path,
    destination: Path,
    *,
    cancel: Event | None,
    progress: Progress | None,
) -> str:
    temporary = destination.with_name(destination.name + ".partial")
    digest = hashlib.sha256()
    try:
        with source.open("rb") as input_file, temporary.open("wb") as output:
            while block := input_file.read(COPY_BLOCK):
                if cancel and cancel.is_set():
                    raise CancelledError("Operación cancelada")
                output.write(block)
                digest.update(block)
                if progress:
                    progress(len(block))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        return digest.hexdigest()
    except PermissionError as exc:
        temporary.unlink(missing_ok=True)
        raise DarkstractorError(
            "Windows no permitió escribir en la instalación. "
            "Cierra Steam y ejecuta Darkstractor como administrador."
        ) from exc
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _validate_game_root(game_root: Path) -> Path:
    root = game_root.resolve()
    if not (root / "Darksiders2.exe").is_file() or not (root / "media" / "manifest.bin").is_file():
        raise DarkstractorError("La carpeta no parece una instalación de Darksiders II Deathinitive Edition")
    return root


def is_game_running() -> bool:
    if os.name != "nt":
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Darksiders2.exe", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
    except OSError:
        return False
    if result.returncode != 0:
        return False
    return any(row and row[0].casefold() == "darksiders2.exe" for row in csv.reader(result.stdout.splitlines()))


def _ensure_game_closed() -> None:
    if is_game_running():
        raise DarkstractorError("Darksiders2.exe está abierto. Cierra el juego antes de instalar o restaurar archivos.")


def default_backup_root(game_root: Path) -> Path:
    """Return the backup store that belongs to this game installation."""
    return game_root.expanduser().resolve() / "media" / "backups"


def _game_id(game_root: Path) -> str:
    normalized = str(game_root.resolve()).rstrip("\\/").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _game_backup_root(game_root: Path, backup_root: Path | None) -> Path:
    if backup_root is None:
        return default_backup_root(game_root)
    return backup_root.expanduser().resolve() / _game_id(game_root)


def _archive_directory(game_root: Path, target_name: str, backup_root: Path | None) -> Path:
    return _game_backup_root(game_root, backup_root) / target_name.casefold()


def _state_path(game_root: Path, target_name: str, backup_root: Path | None) -> Path:
    return _archive_directory(game_root, target_name, backup_root) / "state.json"


def _read_state(path: Path) -> InstallState | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return InstallState(
            schema=int(raw["schema"]),
            status=str(raw["status"]),
            game_root=str(raw["game_root"]),
            target_name=str(raw["target_name"]),
            backup_path=str(raw["backup_path"]),
            backup_size=int(raw["backup_size"]),
            backup_sha256=_validate_sha256(raw["backup_sha256"], "backup_sha256"),
            installed_sha256=_validate_sha256(raw["installed_sha256"], "installed_sha256"),
            mod_path=str(raw["mod_path"]),
            installed_at=str(raw["installed_at"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FormatError(f"Estado de instalación inválido: {path}") from exc


def _validate_state(
    state: InstallState,
    *,
    state_path: Path,
    game_root: Path,
    target_name: str,
) -> Path:
    if state.schema != STATE_SCHEMA or state.status not in {"active", "pending", "restored"}:
        raise FormatError(f"Estado de instalación no compatible: {state_path}")
    if Path(state.game_root).resolve() != game_root.resolve() or state.target_name.casefold() != target_name.casefold():
        raise FormatError(f"El estado de instalación no corresponde a {target_name}")
    backup = Path(state.backup_path).resolve()
    try:
        backup.relative_to(state_path.parent.resolve())
    except ValueError as exc:
        raise FormatError("La ruta del respaldo registrado está fuera del almacén seguro") from exc
    return backup


def _write_state(path: Path, state: InstallState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(asdict(state), output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _ensure_space(directory: Path, required: int, purpose: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(directory).free
    if free < required:
        raise DarkstractorError(f"No hay espacio suficiente para {purpose}: se necesitan {required} bytes libres")


def _target_for(game_root: Path, target_name: str) -> Path:
    media = (game_root / "media").resolve()
    target = (media / target_name).resolve()
    try:
        target.relative_to(media)
    except ValueError as exc:
        raise FormatError("Ruta de destino insegura") from exc
    if not target.is_file():
        raise DarkstractorError(f"No se encontró el UPAK de destino: {target}")
    return target


def active_installations(game_root: Path, *, backup_root: Path | None = None) -> list[InstallState]:
    root = _validate_game_root(game_root)
    game_backups = _game_backup_root(root, backup_root)
    if not game_backups.is_dir():
        return []
    states: list[InstallState] = []
    for state_path in game_backups.glob("*/state.json"):
        state = _read_state(state_path)
        if state and state.status in {"active", "pending"}:
            _validate_state(
                state,
                state_path=state_path,
                game_root=root,
                target_name=state_path.parent.name,
            )
            states.append(state)
    return sorted(states, key=lambda item: item.target_name.casefold())


def install_mod(
    game_root: Path,
    patched: Path,
    *,
    backup_root: Path | None = None,
    cancel: Event | None = None,
    progress: Progress | None = None,
    log: Log | None = None,
) -> InstallationResult:
    log = log or (lambda _message: None)
    root = _validate_game_root(game_root)
    _ensure_game_closed()
    patched = patched.resolve()
    if not patched.is_file():
        raise DarkstractorError(f"No se encontró el UPAK modificado: {patched}")
    manifest = read_mod_manifest(patched)
    target = _target_for(root, manifest.source_name)
    if patched == target:
        raise DarkstractorError("El archivo seleccionado ya es el UPAK instalado")
    if patched.stat().st_size != manifest.patched_size or target.stat().st_size != manifest.source_size:
        raise DarkstractorError("El tamaño del mod o de la instalación no coincide con su manifiesto")

    log("Verificando SHA-256 del UPAK modificado…")
    patched_hash = hash_file(patched, cancel=cancel, progress=progress)
    if patched_hash != manifest.patched_sha256:
        raise FormatError("El UPAK modificado cambió después de ser generado")
    log(f"Mod verificado: {patched_hash}")

    log(f"Verificando la versión instalada de {target.name}…")
    current_hash = hash_file(target, cancel=cancel, progress=progress)
    if current_hash == patched_hash:
        state_path = _state_path(root, target.name, backup_root)
        state = _read_state(state_path)
        if state and state.status in {"active", "pending"}:
            backup = _validate_state(
                state,
                state_path=state_path,
                game_root=root,
                target_name=target.name,
            )
            return InstallationResult("install", target, backup, state.backup_sha256, patched_hash, True)
        raise DarkstractorError("Ese UPAK modificado ya está instalado, pero no existe un respaldo administrado")
    if current_hash != manifest.source_sha256:
        raise DarkstractorError(
            "El UPAK instalado no es la versión desde la que se creó este mod. "
            "Restaura el respaldo, regenera el mod o verifica los archivos con Steam."
        )

    archive_dir = _archive_directory(root, target.name, backup_root)
    state_path = archive_dir / "state.json"
    state = _read_state(state_path)
    if state and state.status in {"active", "pending"}:
        backup = _validate_state(
            state,
            state_path=state_path,
            game_root=root,
            target_name=target.name,
        )
        if state.installed_sha256 != current_hash:
            raise DarkstractorError(
                "El archivo instalado cambió fuera de Darkstractor. No se reemplazará para proteger esos cambios."
            )
        if not backup.is_file() or hash_file(backup, cancel=cancel) != state.backup_sha256:
            raise FormatError("El respaldo registrado falta o no supera la verificación SHA-256")
        previous_hash = state.backup_sha256
    else:
        archive_dir.mkdir(parents=True, exist_ok=True)
        _ensure_space(archive_dir, target.stat().st_size, "crear el respaldo")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = archive_dir / f"{target.stem}-{stamp}-{current_hash[:12]}{target.suffix}.backup"
        log(f"Creando respaldo del estado previo: {backup}")
        backup_hash = _copy_and_hash(target, backup, cancel=cancel, progress=progress)
        if backup_hash != current_hash:
            backup.unlink(missing_ok=True)
            raise FormatError("La copia de seguridad no coincide con el archivo original")
        previous_hash = current_hash

    _ensure_space(target.parent, patched.stat().st_size, "instalar temporalmente el UPAK")
    state = InstallState(
        schema=STATE_SCHEMA,
        status="pending",
        game_root=str(root),
        target_name=target.name,
        backup_path=str(backup),
        backup_size=backup.stat().st_size,
        backup_sha256=previous_hash,
        installed_sha256=patched_hash,
        mod_path=str(patched),
        installed_at=utc_now(),
    )
    _write_state(state_path, state)
    log(f"Instalando {patched.name} como {target.name}…")
    installed_hash = _copy_and_hash(patched, target, cancel=cancel, progress=progress)
    if installed_hash != patched_hash:
        raise FormatError("El archivo instalado no coincide con el mod verificado")
    state.status = "active"
    _write_state(state_path, state)
    log(f"Instalación verificada: {installed_hash}")
    return InstallationResult("install", target, backup, previous_hash, installed_hash)


def restore_backup(
    game_root: Path,
    target_name: str,
    *,
    backup_root: Path | None = None,
    force: bool = False,
    cancel: Event | None = None,
    progress: Progress | None = None,
    log: Log | None = None,
) -> InstallationResult:
    log = log or (lambda _message: None)
    root = _validate_game_root(game_root)
    _ensure_game_closed()
    if Path(target_name).name != target_name:
        raise FormatError("Nombre de UPAK inseguro")
    target = _target_for(root, target_name)
    state_path = _state_path(root, target.name, backup_root)
    state = _read_state(state_path)
    if not state or state.status not in {"active", "pending"}:
        raise DarkstractorError(f"No hay una modificación activa administrada para {target.name}")
    backup = _validate_state(
        state,
        state_path=state_path,
        game_root=root,
        target_name=target.name,
    )
    if not backup.is_file() or backup.stat().st_size != state.backup_size:
        raise DarkstractorError(f"No se encontró el respaldo registrado: {backup}")
    log("Verificando el UPAK instalado y su respaldo…")
    current_hash = hash_file(target, cancel=cancel, progress=progress)
    backup_hash = hash_file(backup, cancel=cancel, progress=progress)
    if backup_hash != state.backup_sha256:
        raise FormatError("El respaldo fue alterado y no se utilizará")
    if current_hash == backup_hash:
        state.status = "restored"
        _write_state(state_path, state)
        return InstallationResult("restore", target, backup, current_hash, backup_hash, True)
    if current_hash != state.installed_sha256 and not force:
        raise DarkstractorError(
            "El UPAK instalado cambió fuera de Darkstractor. "
            "La restauración se canceló para no borrar esos cambios."
        )
    _ensure_space(target.parent, backup.stat().st_size, "restaurar temporalmente el UPAK")
    log(f"Restaurando el respaldo de {target.name}…")
    restored_hash = _copy_and_hash(backup, target, cancel=cancel, progress=progress)
    if restored_hash != backup_hash:
        raise FormatError("El UPAK restaurado no coincide con el respaldo verificado")
    state.status = "restored"
    _write_state(state_path, state)
    log(f"Restauración verificada: {restored_hash}")
    return InstallationResult("restore", target, backup, current_hash, restored_hash)
