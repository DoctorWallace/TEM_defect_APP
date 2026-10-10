"""Offline Windows entry point for the Cavity TEM Light portable package.

Installed as Aplicacion/portable_launcher.py. Only operational installation JSON
is rebound. Every former configuration is preserved beside a recovery journal;
images, projects, revisions and RUNs are never opened by this launcher.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import runpy
import stat
import subprocess
import sys
import traceback
import uuid

PLUGIN = "Cavity_TEM_Light_Prompt3_Masks"
JAVA_RELATIVE = "Fiji/java/win64/zulu21.42.19-ca-jdk21.0.7-win_x64"
CONFIG_RELATIVE = f"Fiji/lib/{PLUGIN}/runtime_config.json"
RECORD_RELATIVE = f"Fiji/lib/{PLUGIN}/install_record.json"
CONFIG_FILES = (CONFIG_RELATIVE, RECORD_RELATIVE)
JOURNAL_SCHEMA = "CTL_PORTABLE_RELOCATION_V1"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def checked_path(path: Path, *, directory: bool = False) -> Path:
    """Inspect before resolving, so junctions and links cannot hide a target."""
    path = path.absolute()
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        if ancestor.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"La ruta contiene un enlace o una redirección: {ancestor}")
    info = path.stat()
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Se esperaba una carpeta: {path}")
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"Se esperaba un archivo normal sin enlaces: {path}")
    return path.resolve(strict=True)


def plain(path: Path) -> bytes:
    return checked_path(path).read_bytes()


def ensure_directory(path: Path) -> Path:
    checked_path(path.parent, directory=True)
    if not path.exists():
        path.mkdir()
    return checked_path(path, directory=True)


def relative_path(value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Una ruta del paquete está vacía.")
    win = PureWindowsPath(value)
    if win.drive or win.root or ".." in win.parts or ":" in value or "\x00" in value:
        raise ValueError(f"Ruta relativa no válida: {value}")
    return Path(*win.parts)


def replace(path: Path, raw: bytes) -> None:
    checked_path(path.parent, directory=True)
    temporary = path.with_name(path.name + ".portable." + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write_new(path: Path, raw: bytes) -> None:
    checked_path(path.parent, directory=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def preparation_lock(root: Path):
    """Windows releases this byte-range lock even after an interrupted process."""
    logs = ensure_directory(root / "Registro")
    lock_path = logs / "preparacion.lock"
    if not lock_path.exists():
        try:
            write_new(lock_path, b"0")
        except FileExistsError:
            pass
    checked_path(lock_path)
    stream = lock_path.open("r+b")
    try:
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("Otro inicio está preparando este paquete. Espere unos segundos.") from exc
        yield
    finally:
        if os.name == "nt":
            import msvcrt
            try:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        stream.close()


def assert_fiji_closed(root: Path) -> None:
    """Only the destination installation matters; a copied origin may be open."""
    if os.name != "nt":
        return
    command = ("Get-CimInstance Win32_Process | "
               "Where-Object {$_.Name -match '^(javaw?|fiji.*)\\.exe$'} | "
               "Select-Object -ExpandProperty ExecutablePath | ConvertTo-Json -Compress")
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    result = subprocess.run(
        [str(windows / "System32/WindowsPowerShell/v1.0/powershell.exe"),
         "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, check=True, timeout=25,
        creationflags=NO_WINDOW, shell=False,
    )
    paths = json.loads(result.stdout) if result.stdout.strip() else []
    if not isinstance(paths, list):
        paths = [paths]
    fiji = PureWindowsPath(str(root / "Fiji"))
    for value in paths:
        if not value:
            continue
        try:
            PureWindowsPath(value).relative_to(fiji)
        except ValueError:
            continue
        raise ValueError("Cierre el Fiji de esta carpeta antes de actualizar sus rutas portables.")


def recover_interrupted(root: Path) -> list[str]:
    backup_root = root / "Copias_configuracion"
    if not backup_root.exists():
        return []
    checked_path(backup_root, directory=True)
    recovered = []
    for backup in sorted(backup_root.iterdir()):
        checked_path(backup, directory=True)
        journal_path = backup / "reubicacion.json"
        if not journal_path.exists():
            continue  # Interrupted before any publication; original files remain intact.
        journal = json.loads(plain(journal_path))
        if journal.get("schema") != JOURNAL_SCHEMA:
            raise ValueError(f"Registro de recuperación desconocido: {journal_path}")
        if journal.get("state") not in ("PREPARED", "ROLLBACK_REQUIRED"):
            continue
        entries = journal.get("files", [])
        if not entries or len({item.get("path") for item in entries}) != len(entries):
            raise ValueError(f"Registro de recuperación no válido: {journal_path}")
        restorations = {}
        for item in entries:
            relative = item["path"]
            if relative not in CONFIG_FILES:
                raise ValueError("La recuperación intenta acceder fuera de la configuración.")
            before = plain(backup / relative_path(relative))
            if digest(before) != item["before_sha256"]:
                raise ValueError(f"La copia de configuración ha cambiado: {backup}")
            target = root / relative_path(relative)
            current = plain(target)
            if digest(current) not in (item["before_sha256"], item["after_sha256"]):
                raise ValueError(f"La configuración cambió fuera del inicio interrumpido. Conserve {backup}.")
            if current != before:
                restorations[target] = before
        if restorations:
            assert_fiji_closed(root)
        for target, raw in restorations.items():
            replace(target, raw)
        journal["state"] = "ROLLED_BACK_RECOVERED"
        replace(journal_path, encoded(journal))
        recovered.append(str(backup.relative_to(root)))
    return recovered


def preflight(root: Path) -> dict:
    root = checked_path(root, directory=True)
    fiji = checked_path(root / "Fiji", directory=True)
    plugin = checked_path(fiji / "lib" / PLUGIN, directory=True)
    python = checked_path(root / "Python/python.exe")
    checked_path(root / "Python/pythonw.exe")
    checked_path(fiji / "fiji-windows-x64.exe")
    checked_path(root / "Aplicacion/Start_Cavity_Light.ijm")
    checked_path(root / "Aplicacion/python_companion/cavity_stats_app/__main__.py")
    java = checked_path(root / JAVA_RELATIVE, directory=True)
    checked_path(java / "bin/java.exe")
    checked_path(java / "bin/server/jvm.dll")
    pth = [line.strip() for line in plain(root / "Python/python312._pth").decode("utf-8-sig").splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
    if pth != [".", "DLLs", "Lib"]:
        raise ValueError("La configuración del Python portable no está aislada como se esperaba.")
    config_path, record_path = (root / value for value in CONFIG_FILES)
    originals = {config_path: plain(config_path), record_path: plain(record_path)}
    config, record = (json.loads(originals[path]) for path in (config_path, record_path))
    if (config.get("schema") != "CTL_P3_MASKS_RUNTIME_CONFIG_V1"
            or record.get("schema") != "CTL_P3_MASKS_INSTALL_RECORD_V1"
            or record.get("install_state") != "COMMITTED"):
        raise ValueError("El registro de la aplicación no corresponde a una instalación completa.")
    if (record.get("runtime_config_sha256") != digest(originals[config_path])
            or config.get("candidate_id") != record.get("candidate_id")):
        raise ValueError("La configuración de la aplicación no supera su comprobación de integridad.")
    old_fiji = PureWindowsPath(record["fiji_root"])
    if (not old_fiji.is_absolute() or ".." in old_fiji.parts
            or PureWindowsPath(record["plugin_root"]) != old_fiji / "lib" / PLUGIN
            or PureWindowsPath(config["installation_root"]) != old_fiji / "lib" / PLUGIN):
        raise ValueError("Las rutas anteriores del registro no son coherentes.")
    if (config.get("python_runtime_relative_path") != "python_companion"
            or config.get("manager_relative_path") != "python_companion/cavity_tem_light_p3/manager.py"):
        raise ValueError("La vinculación del núcleo Python no es compatible.")
    python_hash = digest(plain(python))
    if python_hash != config.get("python_executable_sha256") or python_hash != record.get("python_executable_sha256"):
        raise ValueError("El Python incluido no coincide con el de la versión verificada.")
    if len(record["runtime_files"]) != 34 or len(record["artifacts"]) != 10:
        raise ValueError("La versión requiere 34 archivos de núcleo y 10 componentes de Fiji.")

    def mapped(value: str, *, directory: bool = False) -> Path:
        win = PureWindowsPath(value)
        if not win.is_absolute() or ".." in win.parts:
            raise ValueError(f"Ruta de componente no válida: {value}")
        rel = relative_path(str(win.relative_to(old_fiji)))
        return checked_path(fiji / rel, directory=directory)

    verified = {}
    artifact_targets = {}
    for item in record["runtime_files"] + record["artifacts"]:
        target = (plugin / "python_companion" / relative_path(item["path"])
                  if item in record["runtime_files"] else mapped(item["path"]))
        if target in verified:
            raise ValueError(f"Componente duplicado: {target}")
        raw = plain(target)
        if len(raw) != item["bytes"] or digest(raw) != item["sha256"]:
            raise ValueError(f"Un componente del paquete está incompleto o modificado: {target}")
        verified[target] = raw
        if item in record["artifacts"]:
            artifact_targets[target] = item
    manager = plugin / config["manager_relative_path"]
    adapter = fiji / "scripts/Plugins/Cavity_TEM_Light/Prompt3_Masks_Manager.js"
    if (manager not in verified or adapter not in verified
            or digest(verified[manager]) != config.get("manager_sha256")
            or config.get("manager_sha256") != record.get("manager_sha256")
            or digest(verified[adapter]) != record.get("adapter_sha256")
            or artifact_targets[adapter].get("kind") != "FIJI_P3_MASKS_MANAGER_SCRIPT"):
        raise ValueError("La vinculación del gestor con su registro de instalación no coincide.")
    updated_config, updated_record = deepcopy(config), deepcopy(record)
    updated_config.update(installation_root=str(plugin), python_executable=str(python))
    updated_record.update(fiji_root=str(fiji), plugin_root=str(plugin))
    for item in updated_record["artifacts"]:
        item["path"] = str(mapped(item["path"]))
    for item in updated_record["menu_parent_directories"] + [updated_record["menu_directory"]]:
        item["path"] = str(mapped(item["path"], directory=True))
    changes = {}
    if updated_config != config:
        changes[config_path] = encoded(updated_config)
    updated_record["runtime_config_sha256"] = digest(changes.get(config_path, originals[config_path]))
    if updated_record != record:
        changes[record_path] = encoded(updated_record)
    return {"root": root, "fiji": fiji, "java": java, "python": python,
            "old_fiji_root": str(old_fiji), "originals": originals, "changes": changes,
            "verified_runtime_files": 34, "verified_artifacts": 10}


def apply_relocation(plan: dict) -> str | None:
    changes = plan["changes"]
    if not changes:
        return None
    root = plan["root"]
    assert_fiji_closed(root)
    for path in changes:
        if plain(path) != plan["originals"][path]:
            raise ValueError("La configuración cambió durante su comprobación. Vuelva a iniciar.")
    backup_root = ensure_directory(root / "Copias_configuracion")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    backup = backup_root / stamp
    backup.mkdir()
    entries = []
    for path, raw in changes.items():
        relative = path.relative_to(root)
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        write_new(saved, plan["originals"][path])
        entries.append({"path": relative.as_posix(),
                        "before_sha256": digest(plan["originals"][path]), "after_sha256": digest(raw)})
    journal = {"schema": JOURNAL_SCHEMA, "state": "PREPARED", "files": entries,
               "old_fiji_root": plan["old_fiji_root"], "new_fiji_root": str(plan["fiji"]),
               "scientific_writes": 0}
    journal_path = backup / "reubicacion.json"
    write_new(journal_path, encoded(journal))
    try:
        for path, raw in changes.items():
            if plain(path) != plan["originals"][path]:
                raise ValueError("La configuración cambió antes de actualizar sus rutas.")
            replace(path, raw)
            if plain(path) != raw:
                raise ValueError("No se pudo verificar la actualización de las rutas.")
        journal["state"] = "COMMITTED"
        replace(journal_path, encoded(journal))
    except Exception:
        rollback_ok = True
        for path, raw in changes.items():
            try:
                current = plain(path)
                if current == raw:
                    replace(path, plan["originals"][path])
                elif current != plan["originals"][path]:
                    rollback_ok = False
            except Exception:
                rollback_ok = False
        journal["state"] = "ROLLED_BACK" if rollback_ok else "ROLLBACK_REQUIRED"
        replace(journal_path, encoded(journal))
        raise
    return str(backup.relative_to(root))


def validate_installation(root: Path) -> dict:
    """Read-only integrity check, also valid before first extraction relocation."""
    plan = preflight(root)
    return {"status": "INSTALLATION_INTEGRITY_PASS", "package_root": str(plan["root"]),
            "python_executable": str(plan["python"]), "java_home": str(plan["java"]),
            "verified_runtime_files": plan["verified_runtime_files"],
            "verified_artifacts": plan["verified_artifacts"],
            "relocation_needed": bool(plan["changes"]), "scientific_writes": 0}


def prepare(root: Path) -> dict:
    root = checked_path(root, directory=True)
    with preparation_lock(root):
        recovered = recover_interrupted(root)
        plan = preflight(root)
        backup = apply_relocation(plan)
        for name in ("Preferencias", "Proyectos", "Resultados"):
            ensure_directory(root / name)
    return {"status": "RELOCATION_PASS" if backup else "ALREADY_CURRENT",
            "package_root": str(root), "python_executable": str(plan["python"]),
            "java_home": str(plan["java"]), "verified_runtime_files": 34,
            "verified_artifacts": 10, "backup": backup,
            "recovered": recovered, "scientific_writes": 0}


def child_environment(root: Path) -> dict:
    env = dict(os.environ)
    remove = {"JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "PYTHONHOME", "PYTHONPATH"}
    for name in list(env):
        if name.upper() in remove:
            del env[name]
    env["JAVA_HOME"] = str(root / JAVA_RELATIVE)
    env["TCL_LIBRARY"] = str(root / "Python/tcl/tcl8.6")
    env["TK_LIBRARY"] = str(root / "Python/tcl/tk8.6")
    return env


def launch_command(root: Path, mode: str) -> tuple[list[str], Path]:
    if mode == "app":
        return ([str(root / "Fiji/fiji-windows-x64.exe"), "--no-splash", "--no-python",
                 "--allow-multiple", "--java-home=" + str(root / JAVA_RELATIVE),
                 "-Duser.home=" + str(root / "Preferencias"), "-macro",
                 str(root / "Aplicacion/Start_Cavity_Light.ijm")], root / "Fiji")
    if mode == "results":
        return ([str(root / "Python/pythonw.exe"), "-I", "-B",
                 str(root / "Aplicacion/portable_launcher.py"), "_results_gui"], root)
    raise ValueError("Modo de inicio desconocido.")


def start_child(root: Path, mode: str, log_path: Path) -> int:
    command, cwd = launch_command(root, mode)
    with log_path.open("ab") as output:
        child = subprocess.Popen(command, cwd=cwd, env=child_environment(root), shell=False,
                                 stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 creationflags=NO_WINDOW)
        try:
            code = child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return child.pid
        if code:
            raise ValueError(f"La aplicación no pudo arrancar (código {code}). Consulte {log_path}.")
        return child.pid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("app", "results", "prepare", "_results_gui"))
    args = parser.parse_args(argv)
    root = Path(__file__).absolute().parent.parent
    log_path = None
    try:
        root = checked_path(root, directory=True)
        if os.name != "nt":
            raise ValueError("Este paquete está preparado para Windows de 64 bits.")
        expected_python = root / "Python" / ("pythonw.exe" if args.mode == "_results_gui" else "python.exe")
        if checked_path(Path(sys.executable)) != checked_path(expected_python):
            raise ValueError("Inicie el programa con sus accesos .bat para utilizar el Python incluido.")
        logs = ensure_directory(root / "Registro")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        log_path = logs / ("inicio_" + args.mode.lstrip("_") + "_" + stamp + ".log")
        write_new(log_path, encoded({"started_utc": stamp, "mode": args.mode, "package_root": str(root)}))
        if args.mode == "_results_gui":
            sys.path.insert(0, str(checked_path(root / "Aplicacion/python_companion", directory=True)))
            sys.argv = ["cavity_stats_app"]
            # Tk callbacks and uncaught startup failures remain in a local log.
            with log_path.open("a", encoding="utf-8") as output:
                sys.stdout = sys.stderr = output
                runpy.run_module("cavity_stats_app", run_name="__main__")
            return 0
        report = prepare(root)
        if args.mode in ("app", "results"):
            report.update(status="STARTED", child_pid=start_child(root, args.mode, log_path))
        with log_path.open("ab") as output:
            output.write(encoded(report))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        detail = traceback.format_exc()
        if log_path is not None:
            with log_path.open("a", encoding="utf-8") as output:
                output.write("\nERROR\n" + detail)
        message = f"No se ha podido iniciar Cavity TEM Light: {exc}"
        if log_path is not None:
            message += f"\nRegistro: {log_path}"
        if sys.stderr is not None and not getattr(sys.stderr, "closed", False):
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
