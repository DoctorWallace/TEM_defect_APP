"""Transactional Windows updater for Cavity Light usability improvements.

Only application files named by UPDATE_MANIFEST.json are replaced. Scientific
projects, preferences and user images are never scanned or copied.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import uuid


MANIFEST_SCHEMA = "CAVITY_USABILITY_UPDATE_V1"
BACKUP_SCHEMA = "CAVITY_USABILITY_BACKUP_V1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_LAUNCHERS = frozenset({"INICIAR_CAVITY_LIGHT_1_2.bat", "ABRIR_EDITOR_INDIVIDUAL.bat",
                                "ABRIR_MANUAL.bat", "COMPROBAR_APLICACION.bat"})


class UpdateError(ValueError):
    """An incompatible base or failed transaction; safe to show to the user."""


def _absolute(path):
    return Path(os.path.abspath(os.fspath(path)))


def _plain(path):
    path = _absolute(path)
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise UpdateError(f"No se puede consultar la ruta: {item}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise UpdateError(f"No se admiten enlaces ni puntos de reanálisis: {item}")
    return path


def _path(relative, *, application=False):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise UpdateError(f"Ruta relativa no válida: {relative!r}")
    parts = relative.split("/")
    if any(part in ("", ".", "..") or part.rstrip(" .") != part for part in parts):
        raise UpdateError(f"Ruta relativa no válida: {relative!r}")
    if any(any(ord(char) < 32 or char in '<>"|?*' for char in part) for part in parts):
        raise UpdateError(f"Ruta relativa no válida: {relative!r}")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if any(part.split(".")[0].upper() in reserved for part in parts):
        raise UpdateError(f"Nombre reservado de Windows: {relative!r}")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or str(parsed) != relative:
        raise UpdateError(f"Ruta relativa no válida: {relative!r}")
    allowed = (relative == "VERSION_1_2.json" or relative.startswith((
        "Aplicacion/", "Fiji/macros/toolsets/", "Fiji/plugins/", "Documentacion/")))
    if application and not allowed:
        raise UpdateError(f"La actualización solo puede reemplazar archivos de aplicación: {relative}")
    if not application and not (allowed or relative in _REQUIRED_LAUNCHERS or relative.startswith(("Python/", "Fiji/"))):
        raise UpdateError(f"Requisito fuera de los archivos de aplicación/runtime: {relative}")
    return relative


def _digest(value, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise UpdateError("Huella SHA-256 no válida en el manifiesto.")
    return value


def _base_options(entry, *, required=False):
    """An absent file is represented by null; a list also permits null."""
    if "compatible_base_sha256" not in entry:
        if required:
            raise UpdateError(f"Faltan las huellas de las bases compatibles: {entry['path']}")
        return {entry["sha256"]}
    values = entry["compatible_base_sha256"]
    if values is None:
        return {None}
    if not isinstance(values, list) or not values:
        raise UpdateError(f"Lista de bases compatibles no válida: {entry['path']}")
    checked = [_digest(value, optional=True) for value in values]
    if len(set(checked)) != len(checked):
        raise UpdateError(f"Huella de base repetida: {entry['path']}")
    return set(checked)


def _file(root, relative):
    return _plain(root / relative)


def _sha256(path):
    path = _plain(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise UpdateError(f"Se esperaba un archivo regular: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise UpdateError(f"El archivo cambió durante la comprobación: {path}")
    return digest.hexdigest()


def _current(path):
    path = _plain(path)
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    return _sha256(path)


def _read_json(path):
    path = _plain(path)
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            value = json.load(stream)
    except (OSError, ValueError) as exc:
        raise UpdateError(f"No se puede leer {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise UpdateError(f"Formato no válido: {path.name}")
    return value


def _write_json(path, value):
    temporary = _plain(path.with_name(path.name + ".tmp"))
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, _plain(path))


def _target(path):
    root = _plain(path)
    if not root.is_dir():
        raise UpdateError(f"La carpeta CavityLight no está disponible: {root}")
    for relative in ("VERSION_1_2.json", "Python/python.exe"):
        if not _file(root, relative).is_file():
            raise UpdateError(f"Seleccione la carpeta CavityLight: falta {relative}")
    if not _file(root, "Fiji").is_dir():
        raise UpdateError("Seleccione la carpeta CavityLight que contiene Fiji y Python.")
    return root


def _ensure_closed(root):
    if os.name != "nt":
        return
    script = ("$ErrorActionPreference='Stop'; [Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); "
              "@(Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath) "
              "| ConvertTo-Json -Compress")
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, encoding="utf-8", timeout=25, check=True)
        processes = json.loads(result.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise UpdateError("No se pudo comprobar si Fiji y la biblioteca están cerrados. "
                          "Cierre la aplicación y vuelva a ejecutar el actualizador.") from exc
    if isinstance(processes, dict):
        processes = [processes]
    prefix = str(root).rstrip("\\/").casefold() + "\\"
    active = []
    for item in processes:
        if int(item.get("ProcessId", 0)) == os.getpid():
            continue
        executable = str(item.get("ExecutablePath") or "").replace("/", "\\").casefold()
        if executable.startswith(prefix):
            active.append(f"{item.get('Name')} (PID {item.get('ProcessId')})")
    if active:
        raise UpdateError("Cierre Fiji, la biblioteca y otros procesos de esta distribución: " + "; ".join(active))


def _manifest(distribution):
    distribution = _plain(distribution)
    data = _read_json(distribution / "UPDATE_MANIFEST.json")
    if data.get("schema") != MANIFEST_SCHEMA:
        raise UpdateError("No se reconoce el manifiesto de actualización.")
    update_id = data.get("update_id")
    if not isinstance(update_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", update_id):
        raise UpdateError("Identificador de actualización no válido.")
    if not isinstance(data.get("files"), list) or not data["files"]:
        raise UpdateError("El manifiesto no enumera archivos de actualización.")
    if not isinstance(data.get("required_files"), list):
        raise UpdateError("El manifiesto no enumera los requisitos de aplicación.")
    for key in ("files", "required_files"):
        seen = set()
        for entry in data[key]:
            if not isinstance(entry, dict):
                raise UpdateError("Entrada de manifiesto no válida.")
            relative = _path(entry.get("path"), application=key == "files")
            if relative.casefold() in seen:
                raise UpdateError(f"Ruta repetida en el manifiesto: {relative}")
            seen.add(relative.casefold())
            _digest(entry.get("sha256"))
            _base_options(entry, required=key == "files")
            if key == "files":
                if _sha256(_file(distribution / "payload", relative)) != entry["sha256"]:
                    raise UpdateError(f"El archivo de actualización no coincide con su huella: {relative}")
    _base_profiles(data)
    return distribution, data


def _base_profiles(manifest):
    """Keep release correspondence: per-file alternatives alone admit mixtures."""
    paths = {entry["path"].casefold(): entry for entry in manifest["required_files"]}
    replacements = {entry["path"].casefold(): entry for entry in manifest["files"]}
    for key, entry in paths.items():
        if key not in replacements and None in _base_options(entry):
            raise UpdateError(f"Un requisito de aplicación/runtime no puede admitir ausencia: {entry['path']}")
    paths.update(replacements)
    profiles = manifest.get("compatible_bases")
    if not isinstance(profiles, list) or not profiles:
        raise UpdateError("El manifiesto no enumera perfiles completos de bases compatibles.")
    result, seen_ids = [], set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise UpdateError("Perfil de base compatible no válido.")
        base_id = profile.get("base_id")
        if (not isinstance(base_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", base_id)
                or base_id.casefold() in seen_ids):
            raise UpdateError("Identificador de base compatible no válido o repetido.")
        seen_ids.add(base_id.casefold())
        entries = profile.get("files")
        if not isinstance(entries, list):
            raise UpdateError(f"El perfil {base_id} no enumera sus archivos.")
        hashes = {}
        for entry in entries:
            if not isinstance(entry, dict) or "sha256" not in entry:
                raise UpdateError(f"Entrada de perfil no válida: {base_id}")
            relative = _path(entry.get("path"))
            key = relative.casefold()
            if key in hashes or key not in paths or relative != paths[key]["path"]:
                raise UpdateError(f"Ruta de perfil repetida o ajena al manifiesto: {relative}")
            value = _digest(entry["sha256"], optional=True)
            if value not in _base_options(paths[key], required=key in replacements):
                raise UpdateError(f"La huella del perfil {base_id} no está admitida para {relative}")
            hashes[key] = value
        if hashes.keys() != paths.keys():
            raise UpdateError(f"El perfil {base_id} debe cubrir todos los archivos y requisitos.")
        result.append((base_id, hashes))
    return result


def _verify_base(root, manifest):
    profiles = _base_profiles(manifest)
    desired = {entry["path"].casefold(): entry["sha256"] for entry in manifest["files"]}
    actual_hashes = {}
    for entry in manifest["required_files"]:
        actual = _current(_file(root, entry["path"]))
        actual_hashes[entry["path"].casefold()] = actual
        valid = _base_options(entry)
        if entry["path"].casefold() in desired:
            valid.add(desired[entry["path"].casefold()])
        if actual not in valid:
            raise UpdateError(f"Distribución incompatible: no coincide el requisito {entry['path']}")
    changes = []
    for entry in manifest["files"]:
        actual = _current(_file(root, entry["path"]))
        actual_hashes[entry["path"].casefold()] = actual
        if actual == entry["sha256"]:
            continue
        if actual not in _base_options(entry, required=True):
            raise UpdateError(f"Versión anterior incompatible: {entry['path']}. No se ha reemplazado ningún archivo.")
        changes.append(dict(entry, previous_sha256=actual))
    if not any(all((key in desired and actual == desired[key]) or actual == hashes[key]
                   for key, actual in actual_hashes.items()) for _base_id, hashes in profiles):
        raise UpdateError("Los archivos anteriores mezclan bases incompatibles. "
                          "Use una distribución RC1 o ID1 íntegra. No se ha reemplazado ningún archivo.")
    return changes


def _copy_verified(source, destination, expected):
    source, destination = _plain(source), _plain(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _plain(destination.parent)
    shutil.copy2(source, destination)
    if _sha256(destination) != expected:
        raise UpdateError(f"La copia no coincide con la huella comprobada: {destination}")


def _replace_file(source, destination):
    """Single-file atomic replacement; separate helper for failure-injection tests."""
    source, destination = _plain(source), _plain(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _plain(destination.parent)
    os.replace(source, destination)


def _rollback_apply(root, backup, applied):
    errors = []
    for entry in reversed(applied):
        relative = entry["path"]
        target_file = _file(root, relative)
        try:
            if _current(target_file) != entry["sha256"]:
                raise UpdateError("El destino cambió después del reemplazo")
            if entry["previous_sha256"] is None:
                target_file.unlink()
            else:
                staged = _file(backup / "rollback", relative)
                _copy_verified(_file(backup / "originals", relative), staged, entry["previous_sha256"])
                _replace_file(staged, target_file)
                if _sha256(target_file) != entry["previous_sha256"]:
                    raise UpdateError("La restauración de la versión anterior no coincide")
        except Exception as exc:
            errors.append(f"{relative}: {exc}")
    return errors


def apply_update(target, distribution):
    """Apply a verified update, or return without a backup if already installed."""
    root = _target(target)
    distribution, manifest = _manifest(distribution)
    changes = _verify_base(root, manifest)
    _ensure_closed(root)
    if not changes:
        return {"status": "already_applied", "backup": None, "files": []}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = _file(root, "Copias_configuracion") / ("usability_" + stamp + "_" + uuid.uuid4().hex[:8])
    backup = _plain(backup)
    backup.mkdir(parents=True, exist_ok=False)
    metadata = {"schema": BACKUP_SCHEMA, "update_id": manifest["update_id"], "target": str(root),
                "created_at": datetime.now(timezone.utc).isoformat(), "status": "prepared", "files": changes}
    metadata_path = backup / "BACKUP_MANIFEST.json"
    applied = []
    try:
        for entry in changes:
            relative = entry["path"]
            if entry["previous_sha256"] is not None:
                _copy_verified(_file(root, relative), _file(backup / "originals", relative), entry["previous_sha256"])
            _copy_verified(_file(distribution / "payload", relative), _file(backup / "stage", relative), entry["sha256"])
        _write_json(metadata_path, metadata)
        for entry in changes:
            destination = _file(root, entry["path"])
            if _current(destination) != entry["previous_sha256"]:
                raise UpdateError(f"El archivo cambió antes de instalarlo: {entry['path']}")
            _replace_file(_file(backup / "stage", entry["path"]), destination)
            applied.append(entry)
            if _sha256(destination) != entry["sha256"]:
                raise UpdateError(f"La versión instalada no coincide: {entry['path']}")
        metadata["status"] = "applied"
        _write_json(metadata_path, metadata)
    except Exception as exc:
        rollback_errors = _rollback_apply(root, backup, applied)
        metadata["status"] = "rollback_failed" if rollback_errors else "rolled_back"
        try:
            _write_json(metadata_path, metadata)
        except Exception:
            pass
        if rollback_errors:
            raise UpdateError(f"Falló la actualización: {exc}. La recuperación necesita revisión: "
                              + "; ".join(rollback_errors) + f". Copia: {backup}") from exc
        raise UpdateError(f"No se completó la actualización: {exc}. Se conservó la versión anterior. Copia: {backup}") from exc
    return {"status": "applied", "backup": str(backup), "files": [entry["path"] for entry in changes]}


def _backup(root, path):
    backup = _plain(path)
    if backup.parent != _file(root, "Copias_configuracion") or not backup.name.startswith("usability_"):
        raise UpdateError("Seleccione una copia usability_ de Copias_configuracion de esta distribución.")
    data = _read_json(backup / "BACKUP_MANIFEST.json")
    if data.get("schema") != BACKUP_SCHEMA or os.path.normcase(str(root)) != os.path.normcase(str(data.get("target", ""))):
        raise UpdateError("La copia de seguridad no corresponde a esta distribución.")
    if not isinstance(data.get("files"), list) or not data["files"]:
        raise UpdateError("La copia de seguridad no enumera archivos.")
    seen = set()
    for entry in data["files"]:
        if not isinstance(entry, dict):
            raise UpdateError("Entrada de copia de seguridad no válida.")
        relative = _path(entry.get("path"), application=True)
        if relative.casefold() in seen:
            raise UpdateError(f"Ruta repetida en la copia de seguridad: {relative}")
        seen.add(relative.casefold())
        _digest(entry.get("sha256"))
        _digest(entry.get("previous_sha256"), optional=True)
        if "previous_sha256" not in entry:
            raise UpdateError(f"Falta el estado anterior de {relative}")
        if entry["previous_sha256"] is not None:
            if _sha256(_file(backup / "originals", relative)) != entry["previous_sha256"]:
                raise UpdateError(f"La copia anterior no coincide con su huella: {relative}")
    return backup, data


def restore_update(target, backup):
    """Restore only a matching installation, preserving later or unknown edits."""
    root = _target(target)
    backup, metadata = _backup(root, backup)
    entries = metadata["files"]
    restored = metadata.get("status") == "restored"
    if metadata.get("status") not in ("applied", "restored"):
        raise UpdateError("Esta copia no pertenece a una actualización completada. Revise el diagnóstico de la operación.")
    for entry in entries:
        expected = entry["previous_sha256"] if restored else entry["sha256"]
        if _current(_file(root, entry["path"])) != expected:
            raise UpdateError(f"No se restaura {entry['path']}: la versión actual cambió. No se ha reemplazado ningún archivo.")
    _ensure_closed(root)
    if restored:
        return {"status": "already_restored", "files": []}
    staging = _plain(backup / ("restore_" + uuid.uuid4().hex[:8]))
    staging.mkdir(exist_ok=False)
    replaced = []
    try:
        for entry in entries:
            relative = entry["path"]
            _copy_verified(_file(root, relative), _file(staging / "installed", relative), entry["sha256"])
            if entry["previous_sha256"] is not None:
                _copy_verified(_file(backup / "originals", relative), _file(staging / "previous", relative), entry["previous_sha256"])
        for entry in entries:
            destination = _file(root, entry["path"])
            if _current(destination) != entry["sha256"]:
                raise UpdateError(f"El archivo cambió antes de restaurarlo: {entry['path']}")
            if entry["previous_sha256"] is None:
                destination.unlink()
            else:
                _replace_file(_file(staging / "previous", entry["path"]), destination)
            replaced.append(entry)
            if _current(destination) != entry["previous_sha256"]:
                raise UpdateError(f"La versión restaurada no coincide: {entry['path']}")
        metadata["status"] = "restored"
        metadata["restored_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(backup / "BACKUP_MANIFEST.json", metadata)
    except Exception as exc:
        errors = []
        for entry in reversed(replaced):
            try:
                destination = _file(root, entry["path"])
                if _current(destination) != entry["previous_sha256"]:
                    raise UpdateError("El destino cambió después de restaurarlo")
                _replace_file(_file(staging / "installed", entry["path"]), destination)
                if _sha256(destination) != entry["sha256"]:
                    raise UpdateError("La recuperación de la versión instalada no coincide")
            except Exception as rollback_exc:
                errors.append(f"{entry['path']}: {rollback_exc}")
        if errors:
            raise UpdateError(f"Falló la restauración: {exc}. Recuperación incompleta: " + "; ".join(errors)) from exc
        raise UpdateError(f"No se completó la restauración: {exc}. Se conserva la actualización instalada.") from exc
    return {"status": "restored", "files": [entry["path"] for entry in entries]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Actualizar o restaurar las mejoras de usabilidad de Cavity Light")
    commands = parser.add_subparsers(dest="command", required=True)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--target", required=True)
    apply_parser.add_argument("--distribution", default=str(Path(__file__).absolute().parent))
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--target", required=True)
    restore_parser.add_argument("--backup", required=True)
    args = parser.parse_args(argv)
    try:
        result = apply_update(args.target, args.distribution) if args.command == "apply" else restore_update(args.target, args.backup)
    except (UpdateError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    messages = {"applied": "Actualización instalada y comprobada.", "already_applied": "La actualización ya está instalada. No se creó otra copia.",
                "restored": "Versión anterior restaurada y comprobada.", "already_restored": "Esta copia ya está restaurada."}
    print(messages[result["status"]])
    if result.get("backup"):
        print("Copia de seguridad: " + result["backup"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
