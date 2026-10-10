"""Read-only diagnosis of R9 cached metrics versus an export of decoded ROI geometry.

This does not change the strict integration result or accept approximate equality.
It predicts decoded bounds using ImageJ's float32 endpoint serialization, then
replays the unchanged R9 numerical source to check every affected exported cell.
Only the explicitly requested evidence JSON is written; no Fiji is launched.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile


PROPERTIES = {
    "x_center_px": "Center_x_px", "y_center_px": "Center_y_px",
    "x_center_nm": "Center_x_nm", "y_center_nm": "Center_y_nm",
    "equivalent_diameter_nm": "Equivalent_diameter_nm",
    "major_axis_nm": "Major_axis_nm", "minor_axis_nm": "Minor_axis_nm",
    "aspect_ratio": "Aspect_ratio", "projected_area_nm2": "Cavity_area_nm2",
    "estimated_spherical_volume_nm3": "Estimated_spherical_volume_nm3",
    "signed_depth_nm": "Signed_depth_nm", "absolute_depth_nm": "Depth_absolute_nm",
}


def read_tsv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def roi_dump(path):
    output = {}
    for row in read_tsv(path):
        output.setdefault(row["entry"], {})[row["field"]] = row["value"]
    return output


def bounds(roi):
    return list(map(float, re.search(r"x=([^,]+),y=([^,]+),w=([^,]+),h=([^\]]+)", roi["bounds"]).groups()))


def f32(number):
    return struct.unpack(">f", struct.pack(">f", number))[0]


def formatted(number):
    # R9 writes ROI numeric properties to six decimals, then exports nine.
    return f"{float(f'{number:.6f}'):.9f}"


def source_functions(source):
    masked = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', lambda m: " " * len(m[0]), source, flags=re.S)
    output = {}
    for match in re.finditer(r"\bfunction\s+(\w+)\s*\([^)]*\)\s*\{", masked):
        depth, pos = 1, match.end()
        while depth:
            if masked[pos] == "{": depth += 1
            if masked[pos] == "}": depth -= 1
            pos += 1
        output[match[1]] = source[match.start():pos]
    return output


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sequential_sum(values):
    total = 0.0
    for value in values: total += value
    return total


def summary(rows):
    valid = [r for r in rows if r["size_valid"] == "1"]
    diameters = sorted(float(r["equivalent_diameter_nm"]) for r in valid)
    mean = sequential_sum(diameters) / len(diameters)
    std = math.sqrt(sequential_sum((d - mean) ** 2 for d in diameters) / (len(diameters) - 1))
    return {
        "mean_diameter_nm": f"{mean:.9f}", "std_diameter_nm": f"{std:.9f}",
        "projected_area_size_valid_nm2": f"{sequential_sum(float(r['projected_area_nm2']) for r in valid):.9f}",
        "estimated_spherical_volume_size_valid_nm3": f"{sequential_sum(float(r['estimated_spherical_volume_nm3']) for r in valid):.9f}",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--r9-macro", type=Path, required=True)
    parser.add_argument("--candidate-macro", type=Path, default=Path(__file__).with_name("Cavity_TEM_Light_1_2_RC1.ijm"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    strict_path = args.evidence / "INTEGRATED_VERIFICATION.json"
    strict = json.loads(strict_path.read_text(encoding="utf-8"))
    before_path, after_path = (args.evidence / name for name in ["rois_before.tsv", "rois_final_saved.tsv"])
    before, after = roi_dump(before_path), roi_dump(after_path)
    old_run, new_run = Path(strict["reference_run"]), Path(strict["new_run"])
    old_rows, new_rows = (read_tsv(run / "cavity_objects.tsv") for run in [old_run, new_run])
    old, new = ({r["cavity_id"]: r for r in rows} for rows in [old_rows, new_rows])
    errors, checks = [], {}
    if len(old) != len(old_rows) or len(new) != len(new_rows): errors.append("Duplicate cavity IDs")
    if list(old) != list(new): errors.append("Cavity identity/order differs")
    if before.keys() != after.keys(): errors.append("Saved ROI entries differ")
    geometry_fields = ["bounds", "name", "points", "position", "type"]
    geometry_changes = [(name, key) for name in before for key in geometry_fields if before[name].get(key) != after.get(name, {}).get(key)]
    if geometry_changes: errors.append("Saved protected ROI geometry differs")
    checks["protected_roi_geometry"] = {"rois": len(before), "fields": geometry_fields, "differences": geometry_changes}
    source_old, source_new = (source_functions(p.read_text(encoding="utf-8")) for p in [args.r9_macro, args.candidate_macro])
    unchanged_names = ["syncCavityAtIndex", "lightComputeStats"]
    unchanged = {name: source_old[name] == source_new[name] for name in unchanged_names}
    old_label = "application_version:'1.1.1-R9-HF4.6'"
    new_label = "application_version:'1.2.0-RC1-individual'"
    unchanged["lightHF3Source_except_one_application_version_literal"] = (
        source_old["lightHF3Source"].count(old_label) == 1
        and source_new["lightHF3Source"].count(new_label) == 1
        and source_old["lightHF3Source"] == source_new["lightHF3Source"].replace(new_label, old_label))
    if not all(unchanged.values()): errors.append("Relevant scientific source changed")
    checks["unchanged_r9_scientific_functions"] = unchanged
    checks["explicit_non_scientific_source_difference"] = {"function": "lightHF3Source", "location": "analysis_method.json application_version", "reference_literal": old_label, "candidate_literal": new_label, "allowed_occurrences": 1, "all_other_characters_must_be_identical": True}
    science = "".join(json.loads(m[1]) for m in re.finditer(r'code=code\+("(?:\\.|[^"\\])*");', source_old["lightHF3Source"]))
    metadata = before["CAVITY_SESSION_METADATA.roi"]
    sx, sy = (float(metadata["property:Scale_nm_per_px_" + axis]) for axis in ["x", "y"])
    surface = before["SURFACE_REFERENCE.roi"]
    points = [list(map(float, point.split(","))) for point in surface["points"].strip(";").split(";")]
    sign = float(surface["property:Material_side_sign"])
    # The supplied reference has a single, exactly represented straight surface.
    # This also permits a formal bound for unavailable pre-save double centers.
    if len(points) != 2: errors.append("Old-center rounding bound requires a single straight surface")
    replay_input, float_mismatches, raw_mismatches, cached_mismatches = [], [], [], []
    reference_zip = old_run.parent.parent / "cavity_rois.zip"
    with zipfile.ZipFile(reference_zip) as archive:
        for cavity_id, row in old.items():
            name, roi = cavity_id + ".roi", before[cavity_id + ".roi"]
            x, y, w, h = bounds(roi)
            cx, cy = (float(roi["property:Center_" + axis + "_px"]) for axis in ["x", "y"])
            ow, oh = (float(roi["property:Axis_" + axis + "_nm"]) / scale for axis, scale in [("x", sx), ("y", sy)])
            left, top, right, bottom = f32(cx - ow / 2), f32(cy - oh / 2), f32(cx + ow / 2), f32(cy + oh / 2)
            predicted = [left, top, f32(right - left), f32(bottom - top)]
            if predicted != [x, y, w, h]: float_mismatches.append(cavity_id)
            raw = archive.read(name)
            # ImageJ ROI subpixel rectangle/oval fields: x,y,width,height, float32 BE.
            if list(struct.unpack(">4f", raw[18:34])) != [x, y, w, h]: raw_mismatches.append(cavity_id)
            for field, prop in PROPERTIES.items():
                if f"{float(roi['property:' + prop]):.9f}" != row[field]: cached_mismatches.append([cavity_id, field])
            replay_input.append({"id": cavity_id, "old_x": cx, "old_y": cy, "x": x + w/2, "y": y+h/2, "w": w, "h": h})
    checks["float32_endpoint_serialization"] = {"cavities": len(old), "exact_bounds_components": 4 * (len(old) - len(float_mismatches)), "prediction_mismatches": float_mismatches, "raw_zip_float32_field_mismatches": raw_mismatches,
        "formula": "x=f32(cx-w/2); y=f32(cy-h/2); width=f32(f32(cx+w/2)-x); height=f32(f32(cy+h/2)-y)",
        "scope": "Reconstruction from six-decimal cached centers/axes predicts every stored float32 bound exactly; unavailable original in-memory doubles are not claimed recovered."}
    checks["reference_run_matches_cached_roi_properties"] = {"numeric_cells": len(old)*len(PROPERTIES), "mismatches": cached_mismatches}
    if float_mismatches or raw_mismatches or cached_mismatches: errors.append("Serialization/cached reference reconstruction failed")
    node = shutil.which("node")
    if not node: raise RuntimeError("Node is required to execute the unchanged R9 ES5 source")
    node_script = r'''
const fs=require('fs'), input=JSON.parse(fs.readFileSync(0,'utf8'));
require('vm').runInThisContext(input.science);
const g=CTL3.geometry(input.points,input.sx,input.sy,input.sign);
process.stdout.write(JSON.stringify(input.rows.map(r=>({id:r.id,current:g.metrics(r.x,r.y),previous:g.metrics(r.old_x,r.old_y)}))));
'''
    replay = subprocess.run([node, "-e", node_script], input=json.dumps({"science": science, "points": points, "sx": sx, "sy": sy, "sign": sign, "rows": replay_input}), text=True, capture_output=True, check=True)
    metrics = {r["id"]: r for r in json.loads(replay.stdout)}
    replay_mismatches, unchanged_mismatches, old_depth_outside_rounding_bound = [], [], []
    differences = {field: {"changed_cavities": 0, "max_absolute_change": 0.0} for field in PROPERTIES}
    dx, dy = (points[1][0] - points[0][0])*sx, (points[1][1] - points[0][1])*sy
    length = math.hypot(dx, dy)
    old_depth_rounding_bound = 0.5e-6 * (abs(dy/length)*sx + abs(dx/length)*sy) + 0.5e-6
    predicted_rows = []
    max_old_depth_replay_residual = 0.0
    for item in replay_input:
        cavity_id = item["id"]
        ax, ay = item["w"]*sx, item["h"]*sy
        diameter = math.sqrt(ax*ay)
        values = dict(zip(PROPERTIES, [item["x"], item["y"], item["x"]*sx, item["y"]*sy, diameter, max(ax,ay), min(ax,ay), max(ax,ay)/min(ax,ay), math.pi*ax*ay/4, math.pi*diameter**3/6, metrics[cavity_id]["current"]["depth"], metrics[cavity_id]["current"]["absolute"]]))
        predicted = dict(old[cavity_id])
        for field, value in values.items():
            predicted[field] = formatted(value)
            if predicted[field] != new[cavity_id][field]: replay_mismatches.append([cavity_id, field, predicted[field], new[cavity_id][field]])
            if old[cavity_id][field] != new[cavity_id][field]:
                differences[field]["changed_cavities"] += 1
                differences[field]["max_absolute_change"] = max(differences[field]["max_absolute_change"], abs(float(old[cavity_id][field])-float(new[cavity_id][field])))
        for field in old[cavity_id].keys() - PROPERTIES.keys():
            if old[cavity_id][field] != new[cavity_id][field]: unchanged_mismatches.append([cavity_id, field])
        residual = abs(metrics[cavity_id]["previous"]["depth"] - float(old[cavity_id]["signed_depth_nm"]))
        max_old_depth_replay_residual = max(max_old_depth_replay_residual, residual)
        if residual > old_depth_rounding_bound: old_depth_outside_rounding_bound.append(cavity_id)
        predicted_rows.append(predicted)
    checks["new_run_reproduced_from_accepted_decoded_geometry"] = {"numeric_cells": len(old)*len(PROPERTIES), "exact_decimal_replay_mismatches": replay_mismatches, "science_js_sha256": hashlib.sha256(science.encode()).hexdigest()}
    checks["all_other_cavity_fields_unchanged"] = {"fields": sorted(old_rows[0].keys()-PROPERTIES.keys()), "mismatches": unchanged_mismatches}
    checks["old_depth_consistent_with_cached_center_rounding"] = {"model": "Straight-surface unit-normal projection; six-decimal centers introduce at most0.5e-6*(abs(normal_x)*sx+abs(normal_y)*sy), plus0.5e-6 stored-depth rounding.", "bound_nm": old_depth_rounding_bound, "max_residual_nm": max_old_depth_replay_residual, "outside_bound": old_depth_outside_rounding_bound}
    if replay_mismatches or unchanged_mismatches or old_depth_outside_rounding_bound: errors.append("Numerical replay or categorical comparison failed")
    predicted_summaries = {"reference": summary(old_rows), "new": summary(predicted_rows)}
    summary_mismatches = []
    for label, run in [("reference", old_run), ("new", new_run)]:
        observed = dict(csv.reader((run/"image_summary.tsv").open(encoding="utf-8"), delimiter="\t"))
        for field, value in predicted_summaries[label].items():
            if observed[field] != value: summary_mismatches.append([label,field,value,observed[field]])
    checks["four_changed_summary_fields_replayed"] = {"values": predicted_summaries, "mismatches": summary_mismatches}
    if summary_mismatches: errors.append("Summary replay failed")
    protected_paths = [strict_path, before_path, after_path, reference_zip, args.r9_macro, args.candidate_macro, old_run/"cavity_objects.tsv", new_run/"cavity_objects.tsv", old_run/"image_summary.tsv", new_run/"image_summary.tsv"]
    result = {"status": "PASS_WITH_DOCUMENTED_ROI_PRECISION" if not errors else "FAIL", "strict_integration_status_unchanged": strict["status"], "errors": errors,
        "conclusion": "The historical ZIP already stores float32 geometry different from its cached pre-serialization metrics. Re-export recalculates unchanged R9 science from that stored geometry. No additional protected geometry change occurred in the tested save/reopen.",
        "scientific_validation": False, "scope": "Technical numeric compatibility for the supplied661-cavity revision only; not a claim of bit-identical legacy RUN metrics or general scientific validation.",
        "checks": checks, "observed_numeric_differences": differences, "changed_numeric_cells": sum(d["changed_cavities"] for d in differences.values()),
        "inputs_sha256": {str(p.resolve()): sha(p) for p in protected_paths}, "verifier_sha256": sha(Path(__file__))}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "errors": errors, "output": str(args.output)}))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
