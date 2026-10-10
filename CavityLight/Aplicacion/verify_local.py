"""Verify application bytes against this candidate's local build manifest."""
import hashlib
import json
from pathlib import Path


def verify(root):
    root = Path(root).resolve(strict=True)
    version = json.loads((root / "VERSION_1_2.json").read_text(encoding="utf-8"))
    entries = {**version["application_sha256"], **version["individual_editor_sha256"], **version.get("launcher_sha256", {})}
    errors = []
    for relative, expected in entries.items():
        path = root / relative
        try:
            if not path.resolve().is_relative_to(root) or path.is_symlink():
                raise ValueError("Ruta externa o enlace")
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != expected:
                errors.append(relative + ": hash distinto")
        except (OSError, ValueError) as exc:
            errors.append(relative + ": " + str(exc))
    return {"status": "PASS" if not errors else "FAIL", "checked_application_files": len(entries),
            "errors": errors, "scope": "Application files, not scientific projects or the complete Fiji runtime"}


if __name__ == "__main__":
    result = verify(Path(__file__).resolve().parent.parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
