"""Local catalogue; all linked projects are read-only evidence.

Refresh is transactional and cancellable. Inaccessible projects retain their
last dated snapshot. The cache is not an integrity or scientific acceptance
claim; only an explicit verified RUN can become a local accepted reference.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time

from .readers import (ScanCancelled, check_cancel, directories, path_key,
                      plain_path, read_project, read_run, utc_now)


def default_state_path():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "CavityTEMLight" / "library.json"


def _within(path, root):
    try:
        Path(path_key(path)).relative_to(Path(path_key(root)))
        return True
    except ValueError:
        return False


def _validate_state(data):
    if (not isinstance(data, dict) or data.get("schema") != "CTL_LOCAL_LIBRARY_V1" or
            any(not isinstance(data.get(key), list) for key in ("locations", "projects", "references"))):
        raise ValueError("Formato del catálogo local no reconocido.")
    for location in data["locations"]:
        if not isinstance(location, dict) or not isinstance(location.get("path"), str):
            raise ValueError("Ubicación de catálogo no válida.")
    for project in data["projects"]:
        if not isinstance(project, dict) or not isinstance(project.get("path"), str) or not isinstance(project.get("images", []), list):
            raise ValueError("Proyecto de catálogo no válido.")
    for reference in data["references"]:
        if not isinstance(reference, dict) or not reference.get("run_path") or not reference.get("fingerprint"):
            raise ValueError("Referencia local no válida.")
    return data


class Catalog:
    def __init__(self, state_path=None):
        self.state_path = Path(state_path) if state_path else default_state_path()
        self.backup_path = self.state_path.with_suffix(self.state_path.suffix + ".bak")
        self._lock = threading.RLock()
        self.load_warning = ""
        self.data = {"schema": "CTL_LOCAL_LIBRARY_V1", "locations": [], "projects": [], "references": [],
                     "updated_at": None}
        if self.state_path.exists():
            try:
                self.data = self._load(self.state_path)
            except (OSError, ValueError, TypeError) as exc:
                if not self.backup_path.exists():
                    raise ValueError(f"Catálogo local ilegible; se conserva para recuperación: {self.state_path}: {exc}") from exc
                self.data = self._load(self.backup_path)
                self.load_warning = f"Se recuperó la copia anterior del catálogo: {exc}"

    @staticmethod
    def _load(path):
        return _validate_state(json.loads(plain_path(path).read_text(encoding="utf-8")))

    def _ensure_local_state(self, data):
        state = plain_path(self.state_path)
        for parent in state.parents:
            if (parent / "cavity_light_project.tsv").is_file() or (parent / "project.json").is_file():
                raise ValueError("El catálogo local no puede guardarse dentro de un proyecto científico.")
        if any(_within(state, p["path"]) for p in data["projects"]):
            raise ValueError("El catálogo local no puede guardarse dentro de un proyecto científico.")

    def _save(self, data):
        self._ensure_local_state(data)
        data["updated_at"] = utc_now()
        encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        plain_path(self.state_path.parent)
        fd, temporary = tempfile.mkstemp(prefix=self.state_path.name + ".", suffix=".tmp", dir=self.state_path.parent)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if self.state_path.exists():
                # Never replace the recoverable backup with a corrupt primary.
                try:
                    self._load(self.state_path)
                except (OSError, ValueError, TypeError):
                    corrupt = self.state_path.with_name(self.state_path.name + ".corrupt." + utc_now().replace(":", "-") + ".json")
                    shutil.copy2(self.state_path, corrupt)
                else:
                    backup_tmp = self.backup_path.with_suffix(self.backup_path.suffix + ".tmp")
                    plain_path(backup_tmp)
                    shutil.copy2(self.state_path, backup_tmp)
                    os.replace(backup_tmp, self.backup_path)
            os.replace(temporary, self.state_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        self.data = data

    def list_projects(self):
        with self._lock:
            return copy.deepcopy(self.data["projects"])

    def add_location(self, path, cancel=None, on_progress=None):
        path = str(plain_path(path))
        if not Path(path).is_dir():
            raise ValueError(f"La carpeta no está disponible: {path}")
        with self._lock:
            data = copy.deepcopy(self.data)
            if not any(path_key(loc["path"]) == path_key(path) for loc in data["locations"]):
                data["locations"].append({"path": path, "available": True, "added_at": utc_now()})
            self._refresh(data, cancel, on_progress)
            return self.list_projects()

    def remove_location(self, path):
        """Unlink a search location; never remove its project directories."""
        with self._lock:
            data = copy.deepcopy(self.data)
            data["locations"] = [loc for loc in data["locations"] if path_key(loc["path"]) != path_key(path)]
            data["projects"] = [p for p in data["projects"]
                                if any(_within(p["path"], loc["path"]) for loc in data["locations"])]
            self._mark_copies(data)
            self._save(data)
            return self.list_projects()

    def refresh(self, cancel=None, on_progress=None):
        with self._lock:
            self._refresh(copy.deepcopy(self.data), cancel, on_progress)
            return self.list_projects()

    @staticmethod
    def _discover(root, cancel, on_progress, errors):
        pending, visited = [Path(root)], set()
        last_progress = 0.0
        while pending:
            check_cancel(cancel)
            path = pending.pop()
            key = path_key(path)
            if key in visited:
                continue
            visited.add(key)
            if len(visited) > 200000:
                raise ValueError("La ubicación supera 200 000 carpetas; seleccione una carpeta más específica.")
            now = time.monotonic()
            if on_progress and (not last_progress or now - last_progress >= 0.1):
                on_progress(f"Leyendo carpetas: {path}")
                last_progress = now
            try:
                plain_path(path)
                if (path / "cavity_light_project.tsv").is_file() or (path / "project.json").is_file():
                    yield path
                    continue
                pending.extend(reversed([p for p in directories(path)
                                         if not p.name.startswith(".") and p.name not in ("$RECYCLE.BIN", "System Volume Information")]))
            except (OSError, ValueError) as exc:
                errors.append(f"{path}: {exc}")

    def _refresh(self, data, cancel, on_progress):
        old = {path_key(p["path"]): p for p in data["projects"]}
        found, scanned, now = {}, set(), utc_now()
        for location in data["locations"]:
            check_cancel(cancel)
            root = Path(location["path"])
            location.update(last_attempt=now, errors=[])
            try:
                location["available"] = plain_path(root).is_dir()
            except (OSError, ValueError) as exc:
                location["available"] = False
                location["errors"].append(str(exc))
            if not location["available"]:
                location["errors"].append("Ubicación no disponible; se conserva el último resumen.")
                continue
            location["last_seen"] = now
            for path in self._discover(root, cancel, on_progress, location["errors"]):
                key = path_key(path)
                if key in scanned:
                    continue
                scanned.add(key)
                try:
                    found[key] = read_project(path, cancel=cancel)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    previous = copy.deepcopy(old.get(key, {"path": str(path), "name": path.name, "images": []}))
                    previous.update(available=False, last_scanned=now, errors=[str(exc)])
                    found[key] = previous
        for key, previous in old.items():
            if key not in found and any(_within(previous["path"], loc["path"]) for loc in data["locations"]):
                previous.update(available=False, last_scanned=now,
                                errors=["Proyecto no disponible o no localizado; resumen conservado de " + str(previous.get("last_seen", "fecha desconocida"))])
                found[key] = previous
        check_cancel(cancel)
        data["projects"] = sorted(found.values(), key=lambda p: (p.get("name", "").casefold(), path_key(p["path"])))
        self._mark_copies(data)
        self._save(data)

    @staticmethod
    def _mark_copies(data):
        groups = {}
        for project in data["projects"]:
            uid = project.get("project_uid")
            if uid:
                groups.setdefault(uid, []).append(project["path"])
        for project in data["projects"]:
            paths = groups.get(project.get("project_uid"), [])
            project["is_copy"] = len(paths) > 1
            project["copy_locations"] = paths if len(paths) > 1 else []

    def accept_reference(self, run_report):
        """Accept only the exact report reviewed, after checking it again."""
        if not run_report.get("verification", {}).get("ok"):
            raise ValueError("No puede aceptarse un resultado con integridad no confirmada.")
        current = read_run(run_report.get("path") or run_report["run_path"])
        if not current.get("verification", {}).get("ok") or current["fingerprint"] != run_report.get("fingerprint"):
            raise ValueError("El resultado ha cambiado desde su lectura; vuelva a revisarlo.")
        reference = {field: current.get(field, "") for field in
                     ("project_path", "project_uid", "project_id", "image_id", "image_uid", "session_id", "session_uid",
                      "revision_id", "run_id", "fingerprint")}
        reference.update(run_path=current["path"], accepted_at=utc_now())
        with self._lock:
            data = copy.deepcopy(self.data)
            data["references"] = [r for r in data["references"] if path_key(r["run_path"]) != path_key(reference["run_path"])]
            data["references"].append(reference)
            self._save(data)
        return copy.deepcopy(reference)

    def select_reference(self, project, image, run):
        """Convenience for a selected catalogue row, checked against its parent."""
        report = read_run(run["path"] if isinstance(run, dict) else run)
        if isinstance(project, dict):
            if (project.get("project_uid") != report.get("project_uid") or
                    (report.get("project_path") and path_key(project["path"]) != path_key(report["project_path"]))):
                raise ValueError("El resultado no corresponde al proyecto seleccionado.")
        if isinstance(image, dict) and image.get("image_id") != report.get("image_id"):
            raise ValueError("El resultado no corresponde a la imagen seleccionada.")
        return self.accept_reference(report)
