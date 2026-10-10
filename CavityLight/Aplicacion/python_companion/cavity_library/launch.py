"""Launch the matching editor in the isolated local Windows distribution."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

JAVA_RELATIVE = "Fiji/java/win64/zulu21.42.19-ca-jdk21.0.7-win_x64"


def package_root() -> Path:
    configured = os.environ.get("CAVITY_LIGHT_PACKAGE_ROOT")
    root = Path(configured) if configured else Path(__file__).resolve().parents[3]
    if not (root / "VERSION_1_2.json").is_file():
        raise ValueError("No se encuentra la distribución local. Usa INICIAR_CAVITY_LIGHT_1_2.bat.")
    return root.resolve(strict=True)


def _verify_editor(root: Path) -> None:
    manifest = json.loads((root / "VERSION_1_2.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["individual_editor_sha256"].items():
        path = root / relative
        if path.resolve().is_relative_to(root.resolve()) is False:
            raise ValueError("Ruta del editor fuera de la distribución.")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"El editor ha cambiado desde su empaquetado: {relative}")


def _request_text(project_path, image_id, revision_id) -> str:
    fields = {"project_root": str(Path(project_path).resolve(strict=True)),
              "image_id": str(image_id or ""), "revision_id": str(revision_id or "")}
    for name, value in fields.items():
        if any(character in value for character in "\r\n\t\x00"):
            raise ValueError(f"El campo {name} contiene caracteres no admitidos.")
    for name in ("image_id", "revision_id"):
        if any(character in fields[name] for character in "/\\:") or fields[name] in (".", ".."):
            raise ValueError(f"Identificador de selección no válido: {name}")
    return "".join(f"{key}\t{value}\n" for key, value in fields.items())


def editor_command(root: Path, *, schema2=False, request: Path | None = None) -> list[str]:
    command = [str(root / "Fiji/fiji-windows-x64.exe"), "--no-splash", "--no-python",
               "--allow-multiple", "--forbid-single-instance", "--java-home=" + str(root / JAVA_RELATIVE),
               "-Duser.home=" + str(root / "Preferencias")]
    if request:
        command.append("-Dcavity.light.library.request=" + str(request))
    command += ["-macro", str(root / "Aplicacion" / (
        "Start_Cavity_Light.ijm" if schema2 else "Start_Individual_Editor.ijm"))]
    return command


def launch_editor(project_path=None, image_id=None, revision_id=None, project_kind=None) -> dict:
    root = package_root()
    _verify_editor(root)
    # Determine the format from the descriptor; a UI label can never select a
    # different writer for a scientific project.
    schema2 = False
    if project_path:
        from .readers import read_project
        project = read_project(project_path)
        kind = project.get("kind")
        if kind not in ("R9", "P3"):
            raise ValueError("No se reconoce el formato del proyecto para elegir su editor.")
        schema2 = kind == "P3"
    logs = root / "Registro"
    logs.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    request = None
    if project_path and not schema2:
        text = _request_text(project_path, image_id, revision_id)
        request = logs / ("seleccion_" + stamp + ".tsv")
        request.write_text(text, encoding="utf-8")
    if schema2:
        # Reuse the previously verified relocation transaction with its backup.
        import importlib.util
        spec = importlib.util.spec_from_file_location("ctl_portable_launcher", root / "Aplicacion/portable_launcher.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.prepare(root)
    command = editor_command(root, schema2=schema2, request=request)
    env = dict(os.environ)
    for name in list(env):
        if name.upper() in {"JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "PYTHONHOME", "PYTHONPATH"}:
            del env[name]
    env["JAVA_HOME"] = str(root / JAVA_RELATIVE)
    log = logs / ("editor_" + stamp + ".log")
    with log.open("ab") as output:
        child = subprocess.Popen(command, cwd=root / "Fiji", env=env, shell=False,
                                 stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            code = child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            code = None
        if code:
            raise ValueError(f"El editor no pudo arrancar (código {code}). Registro: {log}")
    return {"pid": child.pid, "mode": "P3" if schema2 else "INDIVIDUAL", "log": str(log),
            "message": (f"Gestor P3 abierto; selecciona este proyecto en el gestor: {project_path}"
                        if schema2 else "Editor individual iniciado. La apertura de la imagen puede tardar unos segundos.")}
