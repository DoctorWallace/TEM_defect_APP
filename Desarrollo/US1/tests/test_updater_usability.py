"""US1 updater regression tests using disposable RC1 and ID1 installations."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


UPDATER_PATH = Path(__file__).resolve().parents[1] / "distribution" / "updater.py"
SPEC = importlib.util.spec_from_file_location("cavity_usability_updater_tests", UPDATER_PATH)
assert SPEC is not None and SPEC.loader is not None
updater = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = updater
SPEC.loader.exec_module(updater)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(root: Path) -> dict[str, tuple[str, object]]:
    result: dict[str, tuple[str, object]] = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[relative] = ("symlink", os.readlink(path))
            elif path.is_dir():
                result[relative] = ("directory", None)
            else:
                result[relative] = ("file", path.read_bytes())
    return result


class UsabilityUpdaterTests(unittest.TestCase):
    RC1 = "1.2-RC1"
    ID1 = "1.2-RC1-ID1"
    EXISTING = "Fiji/macros/toolsets/test.ijm"
    SECOND = "Aplicacion/base-version.json"
    NEW = "Aplicacion/new-tool.py"
    OLD_BYTES = b"macro RC1\n"
    ID1_BYTES = b"macro ID1\n"
    NEW_BYTES = b"macro US1\n"
    SECOND_RC1 = b'{"base":"RC1"}\n'
    SECOND_ID1 = b'{"base":"ID1"}\n'
    SECOND_US1 = b'{"base":"US1"}\n'
    RUNTIME_BYTES = b"portable runtime fixture\n"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cavity-us1-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "CavityLight"
        self.distribution = self.root / "distribution"
        self.target.mkdir()
        self.distribution.mkdir()
        self.write_target("VERSION_1_2.json", b'{"version":"1.2-RC1"}\n')
        self.manifest = {
            "schema": "CAVITY_USABILITY_UPDATE_V1",
            "update_id": "1.2-RC1-US1",
            "files": [],
            "required_files": [],
            "compatible_bases": [
                {"base_id": self.RC1, "files": []},
                {"base_id": self.ID1, "files": []},
            ],
        }
        self.base_bytes = {self.RC1: {}, self.ID1: {}}
        self.add_file(self.EXISTING, self.NEW_BYTES, self.OLD_BYTES, self.ID1_BYTES)
        self.add_file(self.SECOND, self.SECOND_US1, self.SECOND_RC1, self.SECOND_ID1)
        self.add_required("Python/python.exe", self.RUNTIME_BYTES, self.RUNTIME_BYTES)
        self.set_base(self.RC1)
        self.save_manifest()

    def write_target(self, relative: str, data: bytes) -> Path:
        path = self.target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _remember_bases(self, relative: str, rc1: bytes | None, id1: bytes | None) -> None:
        for profile, data in zip(self.manifest["compatible_bases"], (rc1, id1)):
            value = digest(data) if data is not None else None
            existing = next((entry for entry in profile["files"] if entry["path"] == relative), None)
            if existing is None:
                profile["files"].append({"path": relative, "sha256": value})
            else:
                self.assertEqual(existing["sha256"], value)
            self.base_bytes[profile["base_id"]][relative] = data

    def add_file(self, relative: str, new: bytes, rc1: bytes | None, id1: bytes | None) -> dict:
        payload = self.distribution / "payload" / relative
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(new)
        old_hashes = list(dict.fromkeys(digest(data) if data is not None else None for data in (rc1, id1)))
        entry = {"path": relative, "sha256": digest(new), "compatible_base_sha256": old_hashes}
        self.manifest["files"].append(entry)
        self._remember_bases(relative, rc1, id1)
        return entry

    def add_required(self, relative: str, rc1: bytes, id1: bytes) -> None:
        self.manifest["required_files"].append({
            "path": relative,
            "sha256": digest(rc1),
            "compatible_base_sha256": list(dict.fromkeys((digest(rc1), digest(id1)))),
        })
        self._remember_bases(relative, rc1, id1)

    def set_base(self, base_id: str) -> None:
        for relative, data in self.base_bytes[base_id].items():
            if data is not None:
                self.write_target(relative, data)
            elif (self.target / relative).exists():
                (self.target / relative).unlink()

    def save_manifest(self) -> None:
        (self.distribution / "UPDATE_MANIFEST.json").write_text(
            json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8"
        )

    def apply(self) -> dict:
        return updater.apply_update(self.target, self.distribution)

    def assert_rejected_without_mutation(self) -> None:
        before = snapshot(self.target)
        with self.assertRaises(updater.UpdateError):
            self.apply()
        self.assertEqual(snapshot(self.target), before)

    def make_symlink(self, link: Path, destination: Path) -> None:
        try:
            link.symlink_to(destination, target_is_directory=destination.is_dir())
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlink creation is unavailable: {exc}")

    def application_destinations(self) -> set[Path]:
        return {(self.target / entry["path"]).resolve() for entry in self.manifest["files"]}

    def fail_second_replace(self):
        original = updater._replace_file
        destinations = self.application_destinations()
        state = {"count": 0}

        def injected(source, destination, *args, **kwargs):
            if Path(destination).resolve() in destinations:
                state["count"] += 1
                if state["count"] == 2:
                    raise OSError("injected second application replacement failure")
            return original(source, destination, *args, **kwargs)

        return injected, state

    def test_apply_original_rc1_creates_backup_and_reports_files(self) -> None:
        result = self.apply()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(set(result["files"]), {self.EXISTING, self.SECOND})
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.NEW_BYTES)
        self.assertEqual((self.target / self.SECOND).read_bytes(), self.SECOND_US1)
        backup = Path(result["backup"])
        self.assertTrue(backup.is_dir())
        self.assertTrue(backup.name.startswith("usability_"))
        self.assertEqual((backup / "originals" / self.EXISTING).read_bytes(), self.OLD_BYTES)
        metadata = json.loads((backup / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["schema"], "CAVITY_USABILITY_BACKUP_V1")
        self.assertEqual(metadata["status"], "applied")

    def test_apply_id1_and_restore_preserves_id1_originals(self) -> None:
        self.set_base(self.ID1)
        result = self.apply()
        self.assertEqual(result["status"], "applied")
        backup = Path(result["backup"])
        self.assertEqual((backup / "originals" / self.EXISTING).read_bytes(), self.ID1_BYTES)
        updater.restore_update(self.target, backup)
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.ID1_BYTES)
        self.assertEqual((self.target / self.SECOND).read_bytes(), self.SECOND_ID1)

    def test_apply_is_idempotent_without_another_backup(self) -> None:
        first = self.apply()
        before = snapshot(self.target)
        second = self.apply()
        self.assertEqual(second["status"], "already_applied")
        self.assertIsNone(second["backup"])
        self.assertEqual(second["files"], [])
        self.assertEqual(snapshot(self.target), before)
        self.assertTrue(Path(first["backup"]).is_dir())

    def test_restore_recovers_original_and_is_idempotent(self) -> None:
        applied = self.apply()
        restored = updater.restore_update(self.target, applied["backup"])
        self.assertEqual(restored["status"], "restored")
        self.assertEqual(set(restored["files"]), {self.EXISTING, self.SECOND})
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.OLD_BYTES)
        self.assertEqual((self.target / self.SECOND).read_bytes(), self.SECOND_RC1)
        before = snapshot(self.target)
        again = updater.restore_update(self.target, applied["backup"])
        self.assertEqual(again["status"], "already_restored")
        self.assertEqual(snapshot(self.target), before)

    def test_new_file_is_added_and_removed_by_restore(self) -> None:
        self.add_file(self.NEW, b"new tool\n", None, None)
        self.save_manifest()
        self.assertFalse((self.target / self.NEW).exists())
        applied = self.apply()
        self.assertEqual((self.target / self.NEW).read_bytes(), b"new tool\n")
        updater.restore_update(self.target, applied["backup"])
        self.assertFalse((self.target / self.NEW).exists())

    def test_new_file_accepts_direct_null_compatible_hashes(self) -> None:
        entry = self.add_file(self.NEW, b"new tool\n", None, None)
        entry["compatible_base_sha256"] = None
        self.save_manifest()
        applied = self.apply()
        self.assertEqual((self.target / self.NEW).read_bytes(), b"new tool\n")
        updater.restore_update(self.target, applied["backup"])
        self.assertFalse((self.target / self.NEW).exists())

    def test_mixed_rc1_id1_files_are_rejected_without_backup(self) -> None:
        self.write_target(self.SECOND, self.SECOND_ID1)
        self.assert_rejected_without_mutation()
        self.assertFalse((self.target / "Copias_configuracion").exists())

    def test_partial_us1_on_rc1_resumes_and_is_idempotent(self) -> None:
        self.write_target(self.EXISTING, self.NEW_BYTES)
        applied = self.apply()
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["files"], [self.SECOND])
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.NEW_BYTES)
        self.assertEqual((self.target / self.SECOND).read_bytes(), self.SECOND_US1)
        before = snapshot(self.target)
        self.assertEqual(self.apply()["status"], "already_applied")
        self.assertEqual(snapshot(self.target), before)

    def test_partial_us1_on_id1_resumes_with_id1_backup(self) -> None:
        self.set_base(self.ID1)
        self.write_target(self.EXISTING, self.NEW_BYTES)
        applied = self.apply()
        self.assertEqual(applied["files"], [self.SECOND])
        backup = Path(applied["backup"])
        self.assertEqual((backup / "originals" / self.SECOND).read_bytes(), self.SECOND_ID1)
        updater.restore_update(self.target, backup)
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.NEW_BYTES)
        self.assertEqual((self.target / self.SECOND).read_bytes(), self.SECOND_ID1)

    def test_required_runtime_can_differ_between_compatible_bases(self) -> None:
        relative = "Fiji/plugins/base-runtime.jar"
        rc1, id1 = b"runtime RC1\n", b"runtime ID1\n"
        self.add_required(relative, rc1, id1)
        self.save_manifest()
        for base_id, expected in ((self.RC1, rc1), (self.ID1, id1)):
            with self.subTest(base_id=base_id):
                self.set_base(base_id)
                applied = self.apply()
                self.assertEqual(applied["status"], "applied")
                self.assertEqual((self.target / relative).read_bytes(), expected)
                self.assertEqual(self.apply()["status"], "already_applied")
                updater.restore_update(self.target, applied["backup"])

    def test_mixed_required_runtime_and_application_base_are_rejected(self) -> None:
        relative = "Fiji/plugins/base-runtime.jar"
        self.add_required(relative, b"runtime RC1\n", b"runtime ID1\n")
        self.save_manifest()
        self.set_base(self.RC1)
        self.write_target(relative, b"runtime ID1\n")
        self.assert_rejected_without_mutation()

    def test_required_only_file_cannot_use_absence_as_a_compatible_base(self) -> None:
        relative = "Fiji/plugins/required-only.jar"
        self.add_required(relative, b"required runtime\n", b"required runtime\n")
        self.manifest["required_files"][-1]["compatible_base_sha256"] = None
        for profile in self.manifest["compatible_bases"]:
            profile["files"][-1]["sha256"] = None
        self.save_manifest()
        self.assertFalse((self.target / relative).exists())
        self.assert_rejected_without_mutation()

    def test_requirement_overlapping_new_file_accepts_absent_base(self) -> None:
        new_tool = b"new tool\n"
        self.add_file(self.NEW, new_tool, None, None)
        self.manifest["required_files"].append({
            "path": self.NEW, "sha256": digest(new_tool), "compatible_base_sha256": None,
        })
        self.save_manifest()
        applied = self.apply()
        self.assertEqual((self.target / self.NEW).read_bytes(), new_tool)
        self.assertEqual(self.apply()["status"], "already_applied")
        updater.restore_update(self.target, applied["backup"])
        self.assertFalse((self.target / self.NEW).exists())

    def test_overlapping_requirement_accepts_original_and_installed_hashes(self) -> None:
        self.add_required(self.EXISTING, self.OLD_BYTES, self.ID1_BYTES)
        self.save_manifest()
        for base_id in (self.RC1, self.ID1):
            with self.subTest(base_id=base_id):
                self.set_base(base_id)
                first = self.apply()
                self.assertEqual(first["status"], "applied")
                self.assertEqual(self.apply()["status"], "already_applied")
                updater.restore_update(self.target, first["backup"])

    def test_missing_compatible_bases_is_rejected(self) -> None:
        del self.manifest["compatible_bases"]
        self.save_manifest()
        self.assert_rejected_without_mutation()

    def test_incomplete_base_profile_is_rejected(self) -> None:
        self.manifest["compatible_bases"][0]["files"].pop()
        self.save_manifest()
        self.assert_rejected_without_mutation()

    def test_profile_hash_outside_compatible_hash_list_is_rejected(self) -> None:
        self.manifest["compatible_bases"][1]["files"][0]["sha256"] = digest(b"unlisted base macro\n")
        self.save_manifest()
        self.assert_rejected_without_mutation()

    def test_incompatible_current_file_is_rejected_before_writes(self) -> None:
        self.write_target(self.EXISTING, b"user modified macro\n")
        self.assert_rejected_without_mutation()

    def test_new_file_collision_is_rejected_before_writes(self) -> None:
        self.add_file(self.NEW, b"new tool\n", None, None)
        self.save_manifest()
        self.write_target(self.NEW, b"user existing tool\n")
        self.assert_rejected_without_mutation()

    def test_tampered_payload_is_rejected_before_writes(self) -> None:
        (self.distribution / "payload" / self.EXISTING).write_bytes(b"tampered payload\n")
        self.assert_rejected_without_mutation()

    def test_required_runtime_hash_mismatch_is_rejected(self) -> None:
        self.write_target("Python/python.exe", b"unknown runtime\n")
        self.assert_rejected_without_mutation()

    def test_missing_required_runtime_is_rejected(self) -> None:
        (self.target / "Python/python.exe").unlink()
        self.assert_rejected_without_mutation()

    def test_missing_application_marker_is_rejected(self) -> None:
        (self.target / "VERSION_1_2.json").unlink()
        self.assert_rejected_without_mutation()

    def test_unsafe_payload_paths_are_rejected(self) -> None:
        for path in ("../outside.ijm", str(self.root / "outside.ijm"), "C:/outside.ijm",
                     "Fiji\\macros\\toolsets\\test.ijm", "Fiji/macros/toolsets/../../../../outside.ijm"):
            with self.subTest(path=path):
                self.manifest["files"][0]["path"] = path
                for profile in self.manifest["compatible_bases"]:
                    profile["files"][0]["path"] = path
                self.save_manifest()
                self.assert_rejected_without_mutation()

    def test_unsafe_required_paths_are_rejected(self) -> None:
        for path in ("../runtime.exe", str(self.root / "runtime.exe"), "Python\\python.exe"):
            with self.subTest(path=path):
                self.manifest["required_files"][0]["path"] = path
                for profile in self.manifest["compatible_bases"]:
                    profile["files"][2]["path"] = path
                self.save_manifest()
                self.assert_rejected_without_mutation()

    def test_unapproved_scientific_path_is_rejected(self) -> None:
        self.add_file("projects/results.csv", b"result\n", None, None)
        self.save_manifest()
        self.assert_rejected_without_mutation()

    def test_symlinked_target_file_is_rejected_and_external_file_is_untouched(self) -> None:
        external = self.root / "external.ijm"
        external.write_bytes(self.OLD_BYTES)
        link = self.target / self.EXISTING
        link.unlink()
        self.make_symlink(link, external)
        self.assert_rejected_without_mutation()
        self.assertEqual(external.read_bytes(), self.OLD_BYTES)

    def test_symlinked_target_directory_is_rejected(self) -> None:
        parent = self.target / "Fiji/macros/toolsets"
        external = self.root / "external-toolsets"
        parent.rename(external)
        self.make_symlink(parent, external)
        before = snapshot(external)
        self.assert_rejected_without_mutation()
        self.assertEqual(snapshot(external), before)

    def test_symlinked_payload_file_is_rejected(self) -> None:
        external = self.root / "external-payload.ijm"
        external.write_bytes(self.NEW_BYTES)
        link = self.distribution / "payload" / self.EXISTING
        link.unlink()
        self.make_symlink(link, external)
        self.assert_rejected_without_mutation()
        self.assertEqual(external.read_bytes(), self.NEW_BYTES)

    def test_symlinked_payload_directory_is_rejected(self) -> None:
        parent = self.distribution / "payload/Fiji/macros/toolsets"
        external = self.root / "external-payload-toolsets"
        parent.rename(external)
        self.make_symlink(parent, external)
        self.assert_rejected_without_mutation()

    def test_restore_refuses_changes_after_update(self) -> None:
        applied = self.apply()
        self.write_target(self.EXISTING, b"user edited after update\n")
        before = snapshot(self.target)
        with self.assertRaises(updater.UpdateError):
            updater.restore_update(self.target, applied["backup"])
        self.assertEqual(snapshot(self.target), before)

    def test_tampered_backup_is_rejected_before_restore_writes(self) -> None:
        applied = self.apply()
        backup = Path(applied["backup"])
        (backup / "originals" / self.EXISTING).write_bytes(b"tampered backup\n")
        before = snapshot(self.target)
        with self.assertRaises(updater.UpdateError):
            updater.restore_update(self.target, backup)
        self.assertEqual(snapshot(self.target), before)

    def test_apply_and_restore_support_paths_with_spaces(self) -> None:
        new_target, new_distribution = self.root / "Cavity Light portable", self.root / "US1 update package"
        self.target.rename(new_target)
        self.distribution.rename(new_distribution)
        self.target, self.distribution = new_target, new_distribution
        relative = "Documentacion/Usability update notes.txt"
        self.add_file(relative, b"documentation\n", None, None)
        self.save_manifest()
        applied = self.apply()
        self.assertEqual((self.target / relative).read_bytes(), b"documentation\n")
        updater.restore_update(self.target, applied["backup"])
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.OLD_BYTES)
        self.assertFalse((self.target / relative).exists())

    def test_staging_failure_leaves_application_files_unchanged(self) -> None:
        original = updater._copy_verified
        count = 0

        def fail_second_stage(source, destination, *args, **kwargs):
            nonlocal count
            if "stage" in Path(destination).relative_to(self.target).parts:
                count += 1
                if count == 2:
                    raise OSError("injected staging copy failure")
            return original(source, destination, *args, **kwargs)

        with mock.patch.object(updater, "_copy_verified", side_effect=fail_second_stage):
            with self.assertRaises(updater.UpdateError):
                self.apply()
        self.assertEqual(count, 2)
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.OLD_BYTES)
        self.assertEqual((self.target / self.SECOND).read_bytes(), self.SECOND_RC1)
        self.assertEqual((self.target / "Python/python.exe").read_bytes(), self.RUNTIME_BYTES)

    def test_partial_apply_failure_rolls_back_completed_replacements(self) -> None:
        self.add_file(self.NEW, b"new tool\n", None, None)
        self.save_manifest()
        injected, state = self.fail_second_replace()
        with mock.patch.object(updater, "_replace_file", side_effect=injected):
            with self.assertRaises(updater.UpdateError):
                self.apply()
        self.assertGreaterEqual(state["count"], 3)
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.OLD_BYTES)
        self.assertEqual((self.target / self.SECOND).read_bytes(), self.SECOND_RC1)
        self.assertFalse((self.target / self.NEW).exists())

    def test_partial_restore_failure_recovers_installed_files_and_applied_status(self) -> None:
        new_entry = self.add_file(self.NEW, b"new tool\n", None, None)
        self.manifest["files"].remove(new_entry)
        self.manifest["files"].insert(0, new_entry)
        self.save_manifest()
        applied = self.apply()
        backup = Path(applied["backup"])
        metadata_path = backup / "BACKUP_MANIFEST.json"
        metadata_before = metadata_path.read_bytes()
        injected, state = self.fail_second_replace()
        with mock.patch.object(updater, "_replace_file", side_effect=injected):
            with self.assertRaises(updater.UpdateError):
                updater.restore_update(self.target, backup)
        self.assertGreaterEqual(state["count"], 4)
        self.assertEqual((self.target / self.EXISTING).read_bytes(), self.NEW_BYTES)
        self.assertEqual((self.target / self.SECOND).read_bytes(), self.SECOND_US1)
        self.assertEqual((self.target / self.NEW).read_bytes(), b"new tool\n")
        self.assertEqual(metadata_path.read_bytes(), metadata_before)
        self.assertEqual(json.loads(metadata_path.read_text(encoding="utf-8"))["status"], "applied")

    def test_preferences_and_scientific_files_remain_untouched(self) -> None:
        sentinels = {
            "Aplicacion/preferences/user-settings.json": b'{"last_project":"sample"}\n',
            "projects/My project/images/input.dm4": b"raw scientific image\n",
            "projects/My project/roi_sessions/REV_1/cavity_rois.zip": b"scientific ROI archive\n",
            "projects/My project/results/RUN_1/objects.tsv": b"id\tarea\nCAV_1\t42\n",
        }
        for relative, data in sentinels.items():
            self.write_target(relative, data)
        applied = self.apply()
        for relative, data in sentinels.items():
            self.assertEqual((self.target / relative).read_bytes(), data)
            self.assertFalse((Path(applied["backup"]) / "originals" / relative).exists())
        updater.restore_update(self.target, applied["backup"])
        for relative, data in sentinels.items():
            self.assertEqual((self.target / relative).read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
