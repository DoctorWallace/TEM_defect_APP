"""Read-only regression tests for revision browsing and stored RUN comparisons.

Every scientific project is synthetic and lives in TemporaryDirectory. The
fixtures use independently generated SHA-256 sidecars; no Fiji, image decoder,
or third-party Python package is required.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile
import zlib


REPOSITORY = Path(__file__).resolve().parents[3]
COMPANION = REPOSITORY / "CavityLight" / "Aplicacion" / "python_companion"
sys.path.insert(0, str(COMPANION))

from cavity_library.catalog import Catalog
from cavity_library.gui import history_selection_key, revision_history
from cavity_library.readers import (ScanCancelled, compare_runs, read_project,
                                    read_revision_details, read_run)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_pairs(path, values):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerows(values.items())
    Path(path).write_text(stream.getvalue(), encoding="utf-8")


def write_table(path, rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    Path(path).write_text(stream.getvalue(), encoding="utf-8")


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def png_1x1():
    """A complete RGB PNG, including valid CRCs, generated without a decoder."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\0\x81\xa1\xc1")) +
            chunk(b"IEND", b""))


def tiff_1x1():
    """A baseline little-endian, uncompressed, grayscale TIFF."""
    entries = [(256, 4, 1, 1), (257, 4, 1, 1), (258, 3, 1, 8),
               (259, 3, 1, 1), (262, 3, 1, 1), (273, 4, 1, 122),
               (277, 3, 1, 1), (278, 4, 1, 1), (279, 4, 1, 1)]
    return (b"II" + struct.pack("<HI", 42, 8) +
            struct.pack("<H", len(entries)) +
            b"".join(struct.pack("<HHII", *entry) for entry in entries) +
            struct.pack("<I", 0) + b"\x80")


def tree_evidence(root):
    """Capture paths, content, mtimes and permissions, while ignoring read atime."""
    return {str(path.relative_to(root)): (digest(path), path.stat().st_mtime_ns,
                                          path.stat().st_mode)
            for path in sorted(Path(root).rglob("*")) if path.is_file()}


class R9Project:
    """The saved format consumed by read_run, built without calling a writer."""
    def __init__(self, root, *, project_id="PROJECT_A", project_uid="uid-project-a"):
        self.root = Path(root)
        self.root.mkdir(parents=True)
        self.project_id = project_id
        self.project_uid = project_uid
        self.images = {}
        self.revisions = {}
        write_pairs(self.root / "cavity_light_project.tsv", {
            "schema_version": "1", "descriptor_type": "cavity_tem_light_project",
            "project_id": project_id, "project_uid": project_uid,
            "project_name": "Proyecto sintético de usabilidad",
        })
        self.add_image("IMAGE_A")

    def add_image(self, image_id, *, source_sha256=None):
        image_root = self.root / "images" / image_id
        (image_root / "source").mkdir(parents=True)
        source = image_root / "source" / (image_id + ".dm3")
        source.write_bytes(b"Synthetic source pixels are never decoded. " + image_id.encode())
        self.images[image_id] = {
            "image_id": image_id, "display_name": "Imagen " + image_id,
            "source_path": str(source), "stored_path": str(source),
            "source_sha256": source_sha256 or digest(source),
            "current_revision": "", "current_run": "",
        }
        self._registry()
        return image_root

    def _registry(self):
        write_table(self.root / "images.tsv", list(self.images.values()),
                    ["image_id", "display_name", "source_path", "stored_path",
                     "source_sha256", "current_revision", "current_run"])

    def revision(self, revision_id, *, image_id="IMAGE_A", parent="",
                 created_ms=1780000000000, source_sha256=None,
                 analysis_state="pending", session=True):
        image = self.images[image_id]
        path = self.root / "images" / image_id / "roi_sessions" / revision_id
        path.mkdir(parents=True)
        roi_header = bytearray(64)
        roi_header[:4] = b"Iout"
        roi_header[4:6] = struct.pack(">H", 228)
        roi_header[6] = 1  # rectangular ROI
        with zipfile.ZipFile(path / "cavity_rois.zip", "w") as archive:
            archive.writestr("CAV_000001.roi", bytes(roi_header))
        source_sha = source_sha256 or image["source_sha256"]
        manifest = {
            "revision_id": revision_id, "image_id": image_id,
            "project_id": self.project_id, "project_uid": self.project_uid,
            "source_sha256": source_sha, "roi_zip_sha256": digest(path / "cavity_rois.zip"),
            "roi_count": "1", "created_ms": str(created_ms),
            "tool_version": "1.2.0-RC1", "validation_state": "reviewed",
            "parent_revision": parent, "analysis_state": analysis_state,
        }
        write_pairs(path / "revision_manifest.tsv", manifest)
        settings = {
            "format": "Cavity TEM Light image session", "schema_version": "1",
            "project": {"id": self.project_id, "uid": self.project_uid},
            "image": {"id": image_id, "sha256": source_sha, "width_px": 1, "height_px": 1},
            "revision_id": revision_id,
            "scientific_context": {"sample": "Fe10Cr", "condition": "350 C", "operator": "MRB"},
            "analysis_mode": "with_surface",
            "scale": {"confirmed": 1, "active_nm_per_px_x": 0.5, "active_nm_per_px_y": 0.5},
            "thickness": {"nm": 60, "uncertainty_nm": 5, "method": "EELS", "notes": "guardado"},
            "bands": {"width_nm": 250, "count": 8},
            "settings": {"include_uncertain": 1, "histogram_bin_nm": 1,
                         "feature_distance_bin_nm": 10},
            "area": {"whole_image_confirmed": 1, "valid_area_nm2": 100},
            "objects": {"cavities": 1, "analysis_masks": 0, "exclusions": 0},
        }
        if session:
            write_json(path / "session_metadata.json", settings)
        (path / "roi_overlay_preview.png").write_bytes(png_1x1())
        self.revisions[revision_id] = {"path": path, "manifest": manifest,
                                       "settings": settings, "image_id": image_id}
        image["current_revision"] = revision_id
        self._registry()
        return path

    def run(self, revision_id, run_id, *, summary_changes=None,
            manifest_changes=None, method_changes=None, omit=()):
        revision = self.revisions[revision_id]
        rev_manifest = revision["manifest"]
        image_id = revision["image_id"]
        path = revision["path"] / "measurement_runs" / run_id
        path.mkdir(parents=True)
        summary = {
            "project_id": self.project_id, "image_id": image_id,
            "revision_id": revision_id, "run_id": run_id,
            "source_sha256": rev_manifest["source_sha256"],
            "scale_x_nm_px": "0.5", "scale_y_nm_px": "0.5",
            "include_uncertain": "1", "valid_area_nm2": "100",
            "band_width_nm": "250", "band_count": "8",
            "N_count_valid": "1", "mean_diameter_nm": "4.5",
        }
        summary.update(summary_changes or {})
        for field in omit:
            summary.pop(field, None)
        manifest = {
            "schema_version": "1", "revision_id": revision_id,
            "project": {"id": self.project_id, "uid": self.project_uid},
            "image": {"id": image_id, "sha256": rev_manifest["source_sha256"]},
            "scale": {"active_nm_per_px_x": 0.5, "active_nm_per_px_y": 0.5},
            "settings": {"include_uncertain": 1},
            "area": {"valid_area_nm2": 100}, "objects": {"cavities": 1},
        }
        for group, value in (manifest_changes or {}).items():
            if isinstance(value, dict) and isinstance(manifest.get(group), dict):
                manifest[group].update(value)
            else:
                manifest[group] = value
        for field, group, nested in (
                ("scale_x_nm_px", "scale", "active_nm_per_px_x"),
                ("scale_y_nm_px", "scale", "active_nm_per_px_y"),
                ("include_uncertain", "settings", "include_uncertain"),
                ("valid_area_nm2", "area", "valid_area_nm2")):
            if field in omit:
                manifest[group].pop(nested, None)
        method = {"version": "test-r9", "area_method": "raster_pixel_centres",
                  "size_rule": "valid centroids", "band_width_nm": 250,
                  "bands_in_image": 8}
        method.update(method_changes or {})
        write_pairs(path / "image_summary.tsv", summary)
        write_json(path / "run_manifest.json", manifest)
        write_json(path / "analysis_method.json", method)
        write_table(path / "cavity_objects.tsv", [{"image_id": image_id,
                    "cavity_id": "CAV_000001", "diameter_nm": "4.5"}],
                    ["image_id", "cavity_id", "diameter_nm"])
        self.seal_run(path)
        self.images[image_id]["current_run"] = run_id
        self._registry()
        return path

    @staticmethod
    def seal_run(path):
        names = ["run_manifest.json", "image_summary.tsv", "cavity_objects.tsv",
                 "analysis_method.json"]
        (path / "RUN_SHA256.txt").write_text(
            "".join(digest(path / name) + "  " + name + "\n" for name in names),
            encoding="utf-8")

    def workspace(self, revision_id, *, name="Primer tratamiento", comment="Revisar borde izquierdo"):
        revision = self.revisions[revision_id]
        path = revision["path"]
        workspace = path / "workspace"
        workspace.mkdir()
        (workspace / "working_image.tif").write_bytes(tiff_1x1())
        for filename in ("annotated_view.png", "thumbnail.png"):
            (workspace / filename).write_bytes(png_1x1())
        with zipfile.ZipFile(workspace / "treatment_regions.zip", "w"):
            pass
        artifacts = {}
        for key, filename in (("working_image", "working_image.tif"),
                              ("annotated_view", "annotated_view.png"),
                              ("thumbnail", "thumbnail.png"),
                              ("treatment_regions", "treatment_regions.zip")):
            file_path = workspace / filename
            entry = {"relative_path": "workspace/" + filename,
                     "sha256": digest(file_path), "size_bytes": file_path.stat().st_size}
            if key != "treatment_regions":
                entry.update(width_px=1, height_px=1)
            if key == "working_image":
                entry["bit_depth"] = 8
            artifacts[key] = entry
        manifest = revision["manifest"]
        value = {
            "type": "cavity_revision_workspace", "schema_version": 1,
            "revision_id": revision_id, "name": name, "comment": comment,
            "created_ms": int(manifest["created_ms"]),
            "binding": {key: manifest[key] for key in
                        ("project_id", "project_uid", "image_id", "source_sha256", "roi_zip_sha256")},
            "settings_provenance": "saved_session_project_json",
            "settings": copy.deepcopy(revision["settings"]),
            "operations": [], "artifacts": artifacts,
        }
        value["binding"].update(width_px=1, height_px=1)
        self.seal_workspace(revision_id, value)
        return value

    def seal_workspace(self, revision_id, value):
        revision = self.revisions[revision_id]
        path = revision["path"]
        write_json(path / "revision_workspace.json", value)
        sha256 = digest(path / "revision_workspace.json")
        revision["manifest"]["workspace_sha256"] = sha256
        write_pairs(path / "revision_manifest.tsv", revision["manifest"])
        (path / "revision_workspace.sha256").write_text(
            sha256 + "  revision_workspace.json\n", encoding="utf-8")

    def selection(self, revision_id):
        project = read_project(self.root)
        image_id = self.revisions[revision_id]["image_id"]
        image = next(image for image in project["images"] if image["image_id"] == image_id)
        revision = next(rev for rev in image["revisions"] if rev["revision_id"] == revision_id)
        return project, image, revision


class LibraryUsabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cavity-library-usability-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = R9Project(self.root / "project")
        self.rev_a = "REV_20261011_090000_001"
        self.rev_b = "REV_20261011_100000_002"
        self.fixture.revision(self.rev_a, created_ms=1791709200000)

    def details(self, revision_id=None):
        return read_revision_details(*self.fixture.selection(revision_id or self.rev_a))

    def pair(self, **right_options):
        left = self.fixture.run(self.rev_a, "RUN_20261011_090010_001")
        self.fixture.revision(self.rev_b, parent=self.rev_a, created_ms=1791712800000)
        right = self.fixture.run(self.rev_b, "RUN_20261011_100010_002", **right_options)
        self.assertTrue(read_run(left)["verification"]["ok"], "fixture A must have valid evidence")
        self.assertTrue(read_run(right)["verification"]["ok"], "fixture B must have valid evidence")
        return left, right

    @staticmethod
    def comparison_row(report, field):
        return next(row for row in report["rows"] if row["field"] == field)

    def test_same_image_comparison_preserves_stored_values_and_project_files(self):
        left, right = self.pair(summary_changes={"N_count_valid": "7", "mean_diameter_nm": "8.125"})
        before = tree_evidence(self.fixture.root)
        result = compare_runs(left, right)
        self.assertEqual(tree_evidence(self.fixture.root), before)
        self.assertTrue(result["left"]["verification"]["ok"])
        self.assertTrue(result["right"]["verification"]["ok"])
        row = self.comparison_row(result, "mean_diameter_nm")
        self.assertEqual((row["left"], row["right"]), ("4.5", "8.125"))
        self.assertNotEqual(row["state"], "equal")
        self.assertIn(self.rev_a, result["text"])
        self.assertIn(self.rev_b, result["text"])

    def test_different_saved_inclusion_and_methods_are_visible(self):
        left, right = self.pair(summary_changes={"include_uncertain": "0"},
                                manifest_changes={"settings": {"include_uncertain": 0}},
                                method_changes={"size_rule": "boundary-aware alternative"})
        result = compare_runs(left, right)
        inclusion = self.comparison_row(result, "include_uncertain")
        self.assertEqual((inclusion["left"], inclusion["right"]), ("1", "0"))
        self.assertNotEqual(inclusion["state"], "equal")
        method = self.comparison_row(result, "method_parameters")
        self.assertNotEqual(method["left"], method["right"])
        self.assertNotEqual(method["state"], "equal")

    def test_comparison_shows_revision_context_and_treatments_without_pixel_io(self):
        left, right = self.pair()
        first = self.fixture.workspace(self.rev_a, name="Contraste inicial",
                                       comment="Primera prueba.\nConservar para comparar.")
        second = self.fixture.workspace(self.rev_b, name="Suavizado adicional",
                                        comment="Gaussian blur antes de revisar ROIs.")
        first["operations"] = [{"id": "op-001", "kind": "brightness_contrast",
                                "params": {"brightness": 3, "contrast": 1.1}, "region": None}]
        second["operations"] = [{"id": "op-002", "kind": "gaussian_blur",
                                 "params": {"sigma_px": 0.7}, "region": None}]
        working = self.fixture.revisions[self.rev_b]["path"] / "workspace" / "working_image.tif"
        working.write_bytes(tiff_1x1()[:-1] + b"\x90")
        second["artifacts"]["working_image"]["sha256"] = digest(working)
        self.fixture.seal_workspace(self.rev_a, first)
        self.fixture.seal_workspace(self.rev_b, second)
        before = tree_evidence(self.fixture.root)
        original_open = Path.open

        def no_full_pixel_io(path, *args, **kwargs):
            if path.suffix.lower() in (".dm3", ".dm4", ".tif", ".tiff"):
                raise AssertionError("Comparison attempted full pixel IO: " + str(path))
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", new=no_full_pixel_io):
            result = compare_runs(left, right)
        self.assertEqual(tree_evidence(self.fixture.root), before)
        for field, key in (("revision_name", "name"), ("revision_comment", "comment")):
            with self.subTest(field=field):
                row = self.comparison_row(result, field)
                self.assertEqual((row["left"], row["right"]), (first[key], second[key]))
                self.assertEqual(row["state"], "different")
        treatments = self.comparison_row(result, "treatment_operations")
        self.assertEqual(json.loads(treatments["left"]), first["operations"])
        self.assertEqual(json.loads(treatments["right"]), second["operations"])
        self.assertEqual(treatments["state"], "different")
        working_row = self.comparison_row(result, "working_image_sha256")
        self.assertEqual(working_row["left"], first["artifacts"]["working_image"]["sha256"])
        self.assertEqual(working_row["right"], second["artifacts"]["working_image"]["sha256"])
        self.assertEqual(working_row["state"], "different")
        self.assertIn(first["name"], result["text"])
        self.assertIn(second["name"], result["text"])

    def test_legacy_comparison_does_not_invent_revision_context_or_treatments(self):
        left, right = self.pair()
        result = compare_runs(left, right)
        for field in ("revision_name", "revision_comment", "treatment_operations",
                      "working_image_sha256"):
            with self.subTest(field=field):
                row = self.comparison_row(result, field)
                self.assertEqual(row["state"], "unknown")
                self.assertEqual((row["left"], row["right"]), ("No registrado", "No registrado"))

    def test_workspace_edit_blocks_comparison_even_if_run_files_are_intact(self):
        left, right = self.pair()
        self.fixture.workspace(self.rev_a)
        second = self.fixture.workspace(self.rev_b)
        second["comment"] = "Alteración después del guardado sellado"
        path = self.fixture.revisions[self.rev_b]["path"]
        write_json(path / "revision_workspace.json", second)
        self.assertTrue(read_run(right)["verification"]["ok"], "RUN evidence remains intact")
        with self.assertRaises(ValueError):
            compare_runs(left, right)

    def test_two_runs_from_the_same_revision_are_not_a_revision_comparison(self):
        left = self.fixture.run(self.rev_a, "RUN_A")
        right = self.fixture.run(self.rev_a, "RUN_B")
        self.assertTrue(read_run(left)["verification"]["ok"])
        self.assertTrue(read_run(right)["verification"]["ok"])
        with self.assertRaises(ValueError):
            compare_runs(left, right)

    def test_missing_on_both_sides_is_unknown_not_equal(self):
        left = self.fixture.run(self.rev_a, "RUN_A", omit=("scale_x_nm_px", "N_count_valid"))
        self.fixture.revision(self.rev_b, parent=self.rev_a)
        right = self.fixture.run(self.rev_b, "RUN_B", omit=("scale_x_nm_px", "N_count_valid"))
        result = compare_runs(left, right)
        for field in ("scale_x_nm_px", "N_count_valid"):
            with self.subTest(field=field):
                row = self.comparison_row(result, field)
                self.assertEqual(row["state"], "unknown")
                self.assertEqual((row["left"], row["right"]), ("No registrado", "No registrado"))

    def test_missing_on_one_side_stays_unknown(self):
        left, right = self.pair(omit=("mean_diameter_nm",))
        row = self.comparison_row(compare_runs(left, right), "mean_diameter_nm")
        self.assertEqual(row["state"], "unknown")
        self.assertEqual(row["right"], "No registrado")

    def test_hash_failure_blocks_comparison_before_results_are_displayed(self):
        left, right = self.pair()
        (right / "analysis_method.json").write_text('{"version":"changed"}\n', encoding="utf-8")
        self.assertFalse(read_run(right)["verification"]["ok"])
        with self.assertRaises(ValueError):
            compare_runs(left, right)

    def test_other_image_is_rejected_even_with_the_same_source_identity(self):
        left = self.fixture.run(self.rev_a, "RUN_A")
        self.fixture.add_image("IMAGE_B", source_sha256=self.fixture.images["IMAGE_A"]["source_sha256"])
        self.fixture.revision(self.rev_b, image_id="IMAGE_B")
        right = self.fixture.run(self.rev_b, "RUN_B")
        self.assertTrue(read_run(right)["verification"]["ok"])
        with self.assertRaises(ValueError):
            compare_runs(left, right)

    def test_other_project_is_rejected(self):
        left = self.fixture.run(self.rev_a, "RUN_A")
        other = R9Project(self.root / "other", project_uid="uid-project-b")
        other.revision(self.rev_b)
        right = other.run(self.rev_b, "RUN_B")
        self.assertTrue(read_run(right)["verification"]["ok"])
        with self.assertRaises(ValueError):
            compare_runs(left, right)

    def test_other_source_is_rejected_even_when_image_and_project_ids_match(self):
        left = self.fixture.run(self.rev_a, "RUN_A")
        self.fixture.revision(self.rev_b, parent=self.rev_a, source_sha256="a" * 64)
        right = self.fixture.run(self.rev_b, "RUN_B")
        self.assertTrue(read_run(right)["verification"]["ok"])
        with self.assertRaises(ValueError):
            compare_runs(left, right)

    def test_comparison_cancel_is_not_reported_as_valid(self):
        left, right = self.pair()
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(ScanCancelled):
            compare_runs(left, right, cancel=cancelled)

    def test_legacy_revision_has_no_verified_workspace_preview(self):
        before = tree_evidence(self.fixture.root)
        result = self.details()
        self.assertEqual(result["workspace"]["status"], "legacy")
        self.assertIsNone(result["preview"])
        self.assertIn("No registrado", result["text"])
        self.assertEqual(result["analysis_state"], "pending")
        self.assertIn("Pendiente", result["text"])
        self.assertEqual(tree_evidence(self.fixture.root), before)

    def test_foreign_project_id_in_unsigned_legacy_session_is_not_used(self):
        revision = self.fixture.revisions[self.rev_a]
        settings = copy.deepcopy(revision["settings"])
        settings["project"]["id"] = "FOREIGN_PROJECT"
        write_json(revision["path"] / "session_metadata.json", settings)
        result = self.details()
        self.assertTrue(result["verification"]["ok"], result["verification"].get("errors"))
        self.assertEqual(result["workspace"]["status"], "legacy")
        inclusion = next(row for row in result["configuration"] if row["field"] == "include_uncertain")
        self.assertEqual(inclusion["state"], "unknown")
        self.assertEqual(inclusion["value"], "No registrado")
        self.assertIsNone(result["preview"])

    def test_named_intermediate_revision_has_verified_snapshot_without_a_run(self):
        name = "Borde izquierdo — tratamiento 1"
        comment = "Contraste ajustado.\nTodavía falta revisar las ROIs pequeñas."
        self.fixture.workspace(self.rev_a, name=name, comment=comment)
        before = tree_evidence(self.fixture.root)
        result = self.details()
        self.assertTrue(result["verification"]["ok"], result["verification"].get("errors"))
        self.assertEqual(result["workspace"]["status"], "verified")
        self.assertEqual(result["name"], name)
        self.assertEqual(result["comment"], comment)
        self.assertIsNotNone(result["preview"])
        self.assertEqual((result["preview"]["width"], result["preview"]["height"]), (1, 1))
        self.assertEqual(digest(result["preview"]["path"]), result["preview"]["sha256"])
        self.assertEqual(tree_evidence(self.fixture.root), before)

    def test_external_pixel_changes_are_described_as_a_partial_recipe(self):
        value = self.fixture.workspace(self.rev_a)
        description = "Contraste manual ajustado en una herramienta externa"
        before_sha, after_sha = "b" * 64, "c" * 64
        value["preparation"] = {"recipe_complete": False}
        value["operations"] = [{
            "id": "external-001", "kind": "external_pixel_changes", "region": None,
            "params": {"description": description, "before_pixel_sha256": before_sha,
                       "after_pixel_sha256": after_sha},
        }]
        self.fixture.seal_workspace(self.rev_a, value)
        result = self.details()
        self.assertTrue(result["verification"]["ok"], result["verification"].get("errors"))
        self.assertEqual(result["workspace"]["status"], "verified")
        self.assertIsNotNone(result["preview"])
        self.assertIn("Receta parcial", result["text"])
        treatments = result["text"].split("Tratamientos de la copia de trabajo", 1)[1]
        self.assertIn(description, treatments)
        self.assertNotIn(before_sha, treatments)
        self.assertNotIn(after_sha, treatments)
        self.assertNotIn("before_pixel_sha256", treatments)
        self.assertNotIn("after_pixel_sha256", treatments)
        self.assertEqual(result["workspace"]["operations"], value["operations"],
                         "Readable formatting must preserve the sealed operation evidence")

    def test_complete_internal_recipe_has_no_partial_warning(self):
        value = self.fixture.workspace(self.rev_a)
        value["preparation"] = {"recipe_complete": True}
        value["operations"] = [{"id": "internal-001", "kind": "brightness_contrast",
                                "params": {"brightness": 3, "contrast": 1.1}, "region": None}]
        self.fixture.seal_workspace(self.rev_a, value)
        result = self.details()
        self.assertTrue(result["verification"]["ok"], result["verification"].get("errors"))
        self.assertEqual(result["workspace"]["status"], "verified")
        self.assertNotIn("Receta parcial", result["text"])
        self.assertEqual(result["workspace"]["operations"], value["operations"])

    def test_saved_configuration_comes_from_the_bound_workspace_snapshot(self):
        value = self.fixture.workspace(self.rev_a)
        value["settings"]["settings"]["include_uncertain"] = 0
        self.fixture.seal_workspace(self.rev_a, value)
        result = self.details()
        self.assertTrue(result["verification"]["ok"], result["verification"].get("errors"))
        row = next(row for row in result["configuration"] if row["field"] == "include_uncertain")
        self.assertEqual(str(row["value"]), "0")
        self.assertIn("revision_workspace", str(row["source"]))

    def test_revision_selection_does_not_load_tem_or_working_tiff_pixels(self):
        self.fixture.workspace(self.rev_a)
        original_open = Path.open

        def metadata_or_thumbnail_only(path, *args, **kwargs):
            if path.suffix.lower() in (".dm3", ".dm4", ".tif", ".tiff"):
                raise AssertionError("Revision selection attempted full source/image IO: " + str(path))
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", new=metadata_or_thumbnail_only):
            result = self.details()
        self.assertTrue(result["verification"]["ok"], result["verification"].get("errors"))
        self.assertIsNotNone(result["preview"])

    def test_workspace_edit_without_updating_revision_seal_is_blocked(self):
        value = self.fixture.workspace(self.rev_a)
        value["name"] = "Cambio posterior sin sello"
        path = self.fixture.revisions[self.rev_a]["path"]
        write_json(path / "revision_workspace.json", value)
        result = self.details()
        self.assertFalse(result["verification"]["ok"])
        self.assertEqual(result["workspace"]["status"], "invalid")
        self.assertIsNone(result["preview"])

    def test_workspace_without_revision_manifest_seal_is_not_trusted(self):
        self.fixture.workspace(self.rev_a)
        revision = self.fixture.revisions[self.rev_a]
        revision["manifest"].pop("workspace_sha256")
        write_pairs(revision["path"] / "revision_manifest.tsv", revision["manifest"])
        result = self.details()
        self.assertFalse(result["verification"]["ok"])
        self.assertEqual(result["workspace"]["status"], "invalid")
        self.assertIsNone(result["preview"])

    def test_roi_zip_edit_blocks_workspace_preview(self):
        self.fixture.workspace(self.rev_a)
        path = self.fixture.revisions[self.rev_a]["path"]
        with (path / "cavity_rois.zip").open("ab") as stream:
            stream.write(b"tampered")
        result = self.details()
        self.assertFalse(result["verification"]["ok"])
        self.assertIsNone(result["preview"])

    def test_previously_verified_run_does_not_hide_a_later_roi_zip_edit(self):
        self.fixture.workspace(self.rev_a)
        run_path = self.fixture.run(self.rev_a, "RUN_A")
        verified_run = read_run(run_path)
        self.assertTrue(verified_run["verification"]["ok"])
        path = self.fixture.revisions[self.rev_a]["path"]
        with (path / "cavity_rois.zip").open("ab") as stream:
            stream.write(b"changed after RUN verification")
        result = read_revision_details(*self.fixture.selection(self.rev_a), verified_run=verified_run)
        self.assertFalse(result["verification"]["ok"])
        self.assertEqual(result["workspace"]["status"], "invalid")
        self.assertIsNone(result["preview"])

    def test_thumbnail_edit_blocks_workspace_preview(self):
        self.fixture.workspace(self.rev_a)
        path = self.fixture.revisions[self.rev_a]["path"]
        with (path / "workspace" / "thumbnail.png").open("ab") as stream:
            stream.write(b"tampered")
        result = self.details()
        self.assertFalse(result["verification"]["ok"])
        self.assertEqual(result["workspace"]["status"], "invalid")
        self.assertIsNone(result["preview"])

    def test_resealed_thumbnail_dimension_claim_is_checked_against_png(self):
        value = self.fixture.workspace(self.rev_a)
        value["artifacts"]["thumbnail"]["width_px"] = 2
        self.fixture.seal_workspace(self.rev_a, value)
        result = self.details()
        self.assertFalse(result["verification"]["ok"])
        self.assertEqual(result["workspace"]["status"], "invalid")
        self.assertIsNone(result["preview"])

    def test_resealed_foreign_binding_is_rejected(self):
        value = self.fixture.workspace(self.rev_a)
        value["binding"]["image_id"] = "IMAGE_B"
        self.fixture.seal_workspace(self.rev_a, value)
        result = self.details()
        self.assertFalse(result["verification"]["ok"])
        self.assertEqual(result["workspace"]["status"], "invalid")
        self.assertIsNone(result["preview"])

    def test_resealed_artifact_path_cannot_escape_revision(self):
        value = self.fixture.workspace(self.rev_a)
        outside = self.fixture.revisions[self.rev_a]["path"].parent / "outside.png"
        outside.write_bytes(png_1x1())
        value["artifacts"]["thumbnail"].update(relative_path="../outside.png", sha256=digest(outside))
        self.fixture.seal_workspace(self.rev_a, value)
        result = self.details()
        self.assertFalse(result["verification"]["ok"])
        self.assertEqual(result["workspace"]["status"], "invalid")
        self.assertIsNone(result["preview"])

    def test_artifact_link_is_not_followed(self):
        self.fixture.workspace(self.rev_a)
        path = self.fixture.revisions[self.rev_a]["path"] / "workspace" / "thumbnail.png"
        outside = self.root / "linked.png"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symbolic links unavailable: " + str(exc))
        result = self.details()
        self.assertFalse(result["verification"]["ok"])
        self.assertIsNone(result["preview"])

    def test_detached_revision_selection_is_rejected(self):
        project, image, revision = self.fixture.selection(self.rev_a)
        foreign = copy.deepcopy(revision)
        foreign["path"] = str(self.root / "unregistered-revision")
        result = read_revision_details(project, image, foreign)
        self.assertFalse(result["verification"]["ok"])
        self.assertEqual(result["workspace"]["status"], "invalid")
        self.assertIsNone(result["preview"])

    def test_history_interleaves_saved_revision_and_runs_in_one_chronology(self):
        self.fixture.run(self.rev_a, "RUN_20261011_090010_001")
        self.fixture.revision(self.rev_b, parent=self.rev_a, created_ms=1791712800000)
        self.fixture.workspace(self.rev_b, name="Revisión sin cálculo")
        catalog = Catalog(self.root / "local" / "library.json")
        before = tree_evidence(self.fixture.root)
        catalog.add_location(self.fixture.root)
        project = catalog.list_projects()[0]
        image = project["images"][0]
        history = revision_history(project, image)
        self.assertEqual(tree_evidence(self.fixture.root), before)
        self.assertEqual(history[0]["revision_id"], self.rev_b)
        self.assertEqual(history[0]["entry_kind"], "revision")
        self.assertIn("Revisión sin cálculo", history[0]["label"])
        self.assertIn("Actual", history[0]["state"])
        self.assertIn("Sin resultado", history[0]["state"])
        self.assertTrue(any(entry["entry_kind"] == "run" and entry["revision_id"] == self.rev_a
                            for entry in history))
        self.assertEqual(sum(entry["entry_kind"] == "revision" and entry["revision_id"] == self.rev_b
                             for entry in history), 1)

    def test_history_keeps_immutable_revision_name_in_offline_catalog_snapshot(self):
        name = "Borrador con contexto guardado"
        self.fixture.workspace(self.rev_a, name=name)
        state_path = self.root / "local" / "library.json"
        catalog = Catalog(state_path)
        before = tree_evidence(self.fixture.root)
        catalog.add_location(self.fixture.root)
        moved = self.fixture.root.with_name("temporarily-offline")
        self.fixture.root.rename(moved)
        catalog.refresh()
        catalog = Catalog(state_path)
        project = catalog.list_projects()[0]
        self.assertFalse(project["available"])
        history = revision_history(project, project["images"][0])
        self.assertEqual(history[0]["revision_id"], self.rev_a)
        self.assertEqual(history[0]["label"], name)
        self.assertEqual(tree_evidence(moved), before)

    def test_p3_history_keeps_repeated_ids_from_distinct_sessions(self):
        revision_id, run_id = "REV_REPEAT", "RUN_REPEAT"
        project = {"kind": "P3", "project_uid": "project-p3"}
        image = {
            "kind": "P3", "image_id": "IMAGE_A", "image_uid": "image-p3",
            "revision_id": revision_id, "run_id": run_id, "session_uid": "session-2",
            "revisions": [
                {"revision_id": revision_id, "session_id": "SESSION_A", "session_uid": "session-1"},
                {"revision_id": revision_id, "session_id": "SESSION_B", "session_uid": "session-2"},
            ],
            "runs": [
                {"kind": "P3", "revision_id": revision_id, "run_id": run_id,
                 "session_id": "SESSION_A", "session_uid": "session-1", "path": "session-1/runs/RUN_REPEAT"},
                {"kind": "P3", "revision_id": revision_id, "run_id": run_id,
                 "session_id": "SESSION_B", "session_uid": "session-2", "path": "session-2/runs/RUN_REPEAT"},
            ],
        }
        entries = revision_history(project, image)
        self.assertEqual(len(entries), 2)
        self.assertEqual({entry["session_uid"] for entry in entries}, {"session-1", "session-2"})
        self.assertEqual(len({history_selection_key(entry) for entry in entries}), 2)
        self.assertEqual([entry["session_uid"] for entry in entries if "Actual" in entry["state"]],
                         ["session-2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
