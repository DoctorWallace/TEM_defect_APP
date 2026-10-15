"""Project study regression tests against real R9 readers and immutable fixtures."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

COMPANION = Path(__file__).resolve().parents[3] / "CavityLight" / "Aplicacion" / "python_companion"
sys.path.insert(0, str(COMPANION))
from cavity_library.project_study import build_study, export_study, load_study_run, study_text


def digest(data):
    return hashlib.sha256(data).hexdigest()


class StudyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cavity-study-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "sample"
        self.project.mkdir()
        self.pairs(self.project / "cavity_light_project.tsv", {"project_id": "P", "project_uid": "UID"})
        self.output = self.root / "exports"
        self.output.mkdir()

    @staticmethod
    def pairs(path, values):
        path.write_text("".join(f"{key}\t{value}\n" for key, value in values.items()), encoding="utf-8")

    def fixture(self, image, *, diameters=(2, 4), area=1000000, count=None, revision="REV_1", source=None, scale=1, **protocol):
        count = len(diameters) if count is None else count
        revision_path = self.project / "images" / image / "roi_sessions" / revision
        run = revision_path / "measurement_runs" / ("RUN_" + revision)
        run.mkdir(parents=True)
        source_hash = source or digest(image.encode())
        summary = {"project_id": "P", "image_id": image, "revision_id": revision, "run_id": run.name,
                   "source_sha256": source_hash, "sample_name": "Fe10Cr", "experimental_condition": "350C",
                   "image_mode": "with_surface", "include_uncertain": "0", "scale_x_nm_px": str(scale),
                   "scale_y_nm_px": str(scale), "valid_area_nm2": str(area), "N_count_valid": str(count),
                   "N_size_valid": str(len(diameters)), "foil_thickness_nm": "60",
                   "mean_diameter_nm": "99", "median_diameter_nm": "99"}
        manifest = {"schema_version": "1", "project": {"id": "P", "uid": "UID"},
                    "image": {"id": image, "sha256": source_hash}, "revision_id": revision,
                    "scientific_context": {"sample": "Fe10Cr", "condition": "350C"}, "analysis_mode": "with_surface",
                    "scale": {"confirmed": 1, "active_nm_per_px_x": scale, "active_nm_per_px_y": scale},
                    "settings": {"include_uncertain": 0, "feature_distance_bin_nm": 10},
                    "bands": {"width_nm": 250, "count": 8}, "thickness": {"nm": 60, "method": "nominal"},
                    "area": {"valid_area_nm2": area}, "objects": {"cavities": count}}
        method = {"version": "1.1.1-R9-HF3", "geometry": "physical_parallel_offsets_miter_joins_tangent_rays",
                  "area_method": "raster_pixel_centres", "size_rule": "centroids count; boundary excluded size",
                  "linear_length_domain": "valid_raster_pixel_cells_v1", "size_classes_nm": [.5, 1, 2, 5],
                  "band_mode": "width", "band_width_nm": 250, "bands_in_image": 8, "foil_thickness_nm": 60}
        method.update(protocol)
        self.pairs(run / "image_summary.tsv", summary)
        (run / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (run / "analysis_method.json").write_text(json.dumps(method), encoding="utf-8")
        with (run / "cavity_objects.tsv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t")
            writer.writerow(["cavity_id", "image_id", "count_valid", "size_valid", "equivalent_diameter_nm"])
            for index in range(count):
                writer.writerow(["CAV_" + str(index), image, "1", "1" if index < len(diameters) else "0", diameters[index] if index < len(diameters) else ""])
        (revision_path / "cavity_rois.zip").write_bytes(b"immutable synthetic ROI evidence")
        self.pairs(revision_path / "revision_manifest.tsv", {
            "project_id": "P", "project_uid": "UID", "image_id": image, "revision_id": revision,
            "source_sha256": source_hash, "roi_zip_sha256": digest((revision_path / "cavity_rois.zip").read_bytes())})
        self.hash_run(run)
        return run

    @staticmethod
    def hash_run(run):
        files = ("run_manifest.json", "analysis_method.json", "image_summary.tsv", "cavity_objects.tsv")
        (run / "RUN_SHA256.txt").write_text("".join(f"{digest((run / name).read_bytes())}  {name}\n" for name in files), encoding="utf-8")

    @staticmethod
    def modify_json(path, key, value):
        data = json.loads(path.read_text(encoding="utf-8"))
        data[key] = value
        path.write_text(json.dumps(data), encoding="utf-8")

    def records(self):
        return [load_study_run(self.fixture("A", diameters=(1, 3), area=1000000, count=3)),
                load_study_run(self.fixture("B", diameters=(10,), area=3000000, count=1, scale=.13))]

    def test_weighted_density_and_pooled_distribution_with_different_scales(self):
        study = build_study(self.records(), non_overlapping_confirmed=True)
        combined = study["combined"]
        self.assertEqual(combined["N_count_valid"], 4)
        self.assertEqual(combined["valid_area_um2"], "4")
        self.assertEqual(combined["density_N_per_um2"], "1")
        self.assertAlmostEqual(combined["diameter"]["mean_nm"], 14 / 3)
        self.assertEqual(combined["diameter"]["median_nm"], 3)
        self.assertEqual(combined["diameter"]["q25_nm"], 2)
        self.assertEqual(combined["diameter"]["q75_nm"], 6.5)
        self.assertNotEqual(combined["diameter"]["mean_nm"], 99)  # Ignore saved means, use objects.

    def test_overlap_confirmation_is_required(self):
        with self.assertRaisesRegex(ValueError, "no se solapan"):
            build_study(self.records())

    def test_same_source_cannot_be_combined(self):
        first = load_study_run(self.fixture("A"))
        second = load_study_run(self.fixture("B", source=first["source_sha256"]))
        with self.assertRaisesRegex(ValueError, "misma fuente"):
            build_study([first, second], non_overlapping_confirmed=True)

    def test_two_revisions_of_one_image_can_only_be_compared(self):
        records = [load_study_run(self.fixture("A", revision="REV_1")),
                   load_study_run(self.fixture("A", revision="REV_2", diameters=(3, 6)))]
        with self.assertRaisesRegex(ValueError, "único RUN"):
            build_study(records, non_overlapping_confirmed=True)
        comparison = build_study(records, mode="compare")
        self.assertIsNone(comparison["combined"])
        self.assertIn("no se suman", study_text(comparison))

    def test_incompatible_size_protocol_blocks_pooling_and_comparison_reports_it(self):
        records = [load_study_run(self.fixture("A")), load_study_run(self.fixture("B", size_classes_nm=[1, 3, 6]))]
        with self.assertRaisesRegex(ValueError, "Límites de tamaño"):
            build_study(records, non_overlapping_confirmed=True)
        comparison = build_study(records, mode="compare")
        self.assertIn("Límites de tamaño (nm)", comparison["protocol_differences"][0]["fields"])

    def test_count_band_settings_must_be_compatible(self):
        records = [load_study_run(self.fixture("A")), load_study_run(self.fixture("B", band_mode="count"))]
        with self.assertRaisesRegex(ValueError, "Modo de bandas"):
            build_study(records, non_overlapping_confirmed=True)

    def test_different_field_extent_band_count_is_preserved(self):
        records = [load_study_run(self.fixture("A")), load_study_run(self.fixture("B", bands_in_image=12))]
        study = build_study(records, non_overlapping_confirmed=True)
        self.assertEqual([r["bands_in_image"] for r in study["records"]], [8, 12])

    def test_incompatible_uncertain_inclusion_is_blocked(self):
        first = load_study_run(self.fixture("A"))
        run = self.fixture("B")
        (run / "image_summary.tsv").write_text((run / "image_summary.tsv").read_text().replace("include_uncertain\t0", "include_uncertain\t1"))
        self.modify_json(run / "run_manifest.json", "settings", {"include_uncertain": 1, "feature_distance_bin_nm": 10})
        self.hash_run(run)
        with self.assertRaisesRegex(ValueError, "Incluir dudosas"):
            build_study([first, load_study_run(run)], non_overlapping_confirmed=True)

    def test_different_sample_condition_cannot_be_combined(self):
        first = load_study_run(self.fixture("A"))
        run = self.fixture("B")
        (run / "image_summary.tsv").write_text((run / "image_summary.tsv").read_text().replace("experimental_condition\t350C", "experimental_condition\t550C"))
        self.modify_json(run / "run_manifest.json", "scientific_context", {"sample": "Fe10Cr", "condition": "550C"})
        self.hash_run(run)
        with self.assertRaisesRegex(ValueError, "Muestra/condición"):
            build_study([first, load_study_run(run)], non_overlapping_confirmed=True)

    def test_missing_frozen_method_evidence_is_rejected(self):
        run = self.fixture("A")
        method = json.loads((run / "analysis_method.json").read_text())
        del method["size_rule"]
        (run / "analysis_method.json").write_text(json.dumps(method))
        self.hash_run(run)
        with self.assertRaisesRegex(ValueError, "Falta evidencia guardada"):
            load_study_run(run)

    def test_unconfirmed_scale_is_rejected(self):
        run = self.fixture("A")
        self.modify_json(run / "run_manifest.json", "scale", {"confirmed": 0, "active_nm_per_px_x": 1, "active_nm_per_px_y": 1})
        self.hash_run(run)
        with self.assertRaisesRegex(ValueError, "no estaba confirmada"):
            load_study_run(run)

    def test_nonfinite_diameter_is_rejected(self):
        run = self.fixture("A", diameters=(float("nan"),))
        with self.assertRaisesRegex(ValueError, "diámetro"):
            load_study_run(run)

    def test_summary_counts_must_match_objects(self):
        run = self.fixture("A")
        data = (run / "image_summary.tsv").read_text().replace("N_count_valid\t2", "N_count_valid\t5")
        (run / "image_summary.tsv").write_text(data)
        self.hash_run(run)
        with self.assertRaisesRegex(ValueError, "recuento guardado"):
            load_study_run(run)

    def test_stale_image_and_run_catalogue_references_are_rejected(self):
        run = self.fixture("A")
        with self.assertRaisesRegex(ValueError, "imagen/fuente"):
            load_study_run(run, image={"image_id": "A", "metadata": {"source_sha256": "0" * 64}})
        with self.assertRaisesRegex(ValueError, "RUN/revisión cambió"):
            load_study_run(run, run={"path": str(run), "run_id": run.name, "revision_id": "REV_old"})

    def test_tampered_run_is_rejected(self):
        run = self.fixture("A")
        (run / "cavity_objects.tsv").write_text((run / "cavity_objects.tsv").read_text() + "corrupt\n")
        with self.assertRaisesRegex(ValueError, "Integridad no confirmada"):
            load_study_run(run)

    def test_zero_count_fields_and_no_size_statistics(self):
        records = [load_study_run(self.fixture("A", diameters=())), load_study_run(self.fixture("B", diameters=()))]
        study = build_study(records, non_overlapping_confirmed=True)
        self.assertEqual(study["combined"]["density_N_per_um2"], "0")
        self.assertIsNone(study["combined"]["diameter"]["mean_nm"])

    def test_export_reverifies_and_keeps_projects_unchanged(self):
        study = build_study(self.records(), non_overlapping_confirmed=True)
        before = {str(path): path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        folder = export_study(study, self.output)
        after = {str(path): path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(set(path.name for path in folder.iterdir()), {"estudio.json", "informe.html", "por_imagen.csv", "diametros.csv", "resumen_combinado.csv"})
        exported = json.loads((folder / "estudio.json").read_text())
        self.assertTrue(exported["non_overlapping_confirmed_by_user"])
        self.assertEqual(exported["records"][0]["fingerprint"], study["records"][0]["fingerprint"])
        with (folder / "diametros.csv").open(encoding="utf-8-sig", newline="") as stream:
            diameters = list(csv.DictReader(stream))
        self.assertEqual(diameters[0]["cavity_id"], "CAV_0")
        self.assertEqual(diameters[0]["image_id"], "A")
        second = export_study(study, self.output)
        self.assertNotEqual(folder, second)

    def test_export_cannot_be_saved_into_project(self):
        study = build_study(self.records(), non_overlapping_confirmed=True)
        with self.assertRaisesRegex(ValueError, "externa"):
            export_study(study, self.project)

    def test_changed_result_after_preview_blocks_export(self):
        study = build_study(self.records(), non_overlapping_confirmed=True)
        run = Path(study["records"][0]["run_path"])
        self.modify_json(run / "analysis_method.json", "size_classes_nm", [1, 2, 4])
        self.hash_run(run)
        with self.assertRaisesRegex(ValueError, "cambió desde"):
            export_study(study, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_modified_preview_data_cannot_be_exported(self):
        study = build_study(self.records(), non_overlapping_confirmed=True)
        study["records"][0]["count"] = 900
        with self.assertRaisesRegex(ValueError, "evidencia seleccionada cambió"):
            export_study(study, self.output)

    def test_export_reconstructs_combined_summary_from_verified_evidence(self):
        study = build_study(self.records(), non_overlapping_confirmed=True)
        study["combined"]["density_N_per_um2"] = "9999"
        folder = export_study(study, self.output)
        exported = json.loads((folder / "estudio.json").read_text())
        self.assertEqual(exported["combined"]["density_N_per_um2"], "1")
        self.assertEqual(exported["records"][0]["saved_manifest"]["scientific_context"]["sample"], "Fe10Cr")

    def test_cancelled_export_creates_no_output(self):
        study = build_study(self.records(), non_overlapping_confirmed=True)
        from cavity_library.readers import ScanCancelled
        with self.assertRaises(ScanCancelled):
            export_study(study, self.output, cancel=lambda: True)
        self.assertEqual(list(self.output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
