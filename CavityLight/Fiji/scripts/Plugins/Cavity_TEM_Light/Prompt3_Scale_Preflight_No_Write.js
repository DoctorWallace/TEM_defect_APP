/* Prompt-3 spatial-scale preflight. It creates only temporary bridge files. */
(function () {
    "use strict";

    var IJ = Packages.ij.IJ;
    var WindowManager = Packages.ij.WindowManager;
    var RoiManager = Packages.ij.plugin.frame.RoiManager;
    var ByteProcessor = Packages.ij.process.ByteProcessor;
    var File = Packages.java.io.File;
    var FileInputStream = Packages.java.io.FileInputStream;
    var BufferedInputStream = Packages.java.io.BufferedInputStream;
    var BufferedReader = Packages.java.io.BufferedReader;
    var InputStreamReader = Packages.java.io.InputStreamReader;
    var MessageDigest = Packages.java.security.MessageDigest;
    var Files = Packages.java.nio.file.Files;
    var StandardCharsets = Packages.java.nio.charset.StandardCharsets;
    var StandardOpenOption = Packages.java.nio.file.StandardOpenOption;
    var UUID = Packages.java.util.UUID;
    var TimeUnit = Packages.java.util.concurrent.TimeUnit;
    var ArrayList = Packages.java.util.ArrayList;
    var JOptionPane = Packages.javax.swing.JOptionPane;
    var JTextArea = Packages.javax.swing.JTextArea;
    var JScrollPane = Packages.javax.swing.JScrollPane;

    var CANDIDATE_ID = "Cavity_TEM_Light_R10_PROMPT3_MASKS_PREVIEW_DEV01";
    var CONFIG_SCHEMA = "CTL_P3_MASKS_RUNTIME_CONFIG_V1";
    var REQUEST_SCHEMA = "CTL_P3_MASKS_BRIDGE_REQUEST_V1";
    var RESPONSE_SCHEMA = "CTL_P3_MASKS_BRIDGE_RESPONSE_V1";
    var PIXEL_METHOD = "CTL_MASTER_PIXEL_SHA256_V1";
    var EXPECTED_SOURCE_SHA256 = "171c6c4e06210a021d046133ee41589609e5414c33c4894e170fd8363a01dd0f";
    var EXPECTED_SOURCE_BYTES = 67353220;
    var BACKEND_TIMEOUT_SECONDS = 300;

    function fail(code) { throw new Error(String(code)); }

    function hex(bytes) {
        var output = "";
        var i;
        var value;
        for (i = 0; i < bytes.length; i += 1) {
            value = Number(bytes[i]);
            if (value < 0) { value += 256; }
            if (value < 16) { output += "0"; }
            output += value.toString(16);
        }
        return output;
    }

    function sha256File(file) {
        var digest = MessageDigest.getInstance("SHA-256");
        var input = null;
        var buffer = java.lang.reflect.Array.newInstance(java.lang.Byte.TYPE, 1048576);
        var count;
        try {
            input = new BufferedInputStream(new FileInputStream(file));
            while ((count = input.read(buffer)) !== -1) { digest.update(buffer, 0, count); }
            return hex(digest.digest());
        } finally {
            if (input !== null) { input.close(); }
        }
    }

    function sha256Text(text) {
        return hex(MessageDigest.getInstance("SHA-256").digest(
            new java.lang.String(String(text)).getBytes(StandardCharsets.UTF_8)));
    }

    function isPlainFile(file) {
        return file.isFile() && !Files.isSymbolicLink(file.toPath());
    }

    function readUtf8(file) {
        return String(new java.lang.String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8));
    }

    function exactKeys(object, names) {
        return object !== null && typeof object === "object" && !Array.isArray(object) &&
            Object.keys(object).sort().join("|") === names.slice(0).sort().join("|");
    }

    function canonicalValue(value) {
        var keys;
        var parts;
        var i;
        if (value === null) { return "null"; }
        if (typeof value === "string") { return JSON.stringify(String(value)); }
        if (typeof value === "boolean") { return value ? "true" : "false"; }
        if (typeof value === "number") {
            if (!isFinite(value) || (value === 0 && 1 / value < 0)) { fail("CANONICAL_NUMBER_INVALID"); }
            return String(new Packages.java.math.BigDecimal(String(value)).stripTrailingZeros().toPlainString());
        }
        if (Array.isArray(value)) {
            parts = [];
            for (i = 0; i < value.length; i += 1) { parts.push(canonicalValue(value[i])); }
            return "[" + parts.join(",") + "]";
        }
        if (typeof value !== "object") { fail("CANONICAL_TYPE_INVALID"); }
        keys = Object.keys(value).sort();
        parts = [];
        for (i = 0; i < keys.length; i += 1) {
            parts.push(JSON.stringify(keys[i]) + ":" + canonicalValue(value[keys[i]]));
        }
        return "{" + parts.join(",") + "}";
    }

    function canonicalJsonText(value) { return canonicalValue(value) + "\n"; }

    function locateRuntime() {
        var fiji = new File(String(IJ.getDirectory("imagej") || "")).getCanonicalFile();
        var root = new File(new File(fiji, "lib"), "Cavity_TEM_Light_Prompt3_Masks").getCanonicalFile();
        var configFile = new File(root, "runtime_config.json").getCanonicalFile();
        var config;
        var python;
        var runtime;
        var manager;
        if (!root.isDirectory() || Files.isSymbolicLink(root.toPath()) || !isPlainFile(configFile)) {
            fail("P3_PREFLIGHT_RUNTIME_ABSENT");
        }
        config = JSON.parse(readUtf8(configFile));
        if (!exactKeys(config, [
                "candidate_id", "created_at", "installation_root", "manager_relative_path",
                "manager_sha256", "python_executable", "python_executable_sha256",
                "python_runtime_relative_path", "schema"
            ]) || String(config.schema || "") !== CONFIG_SCHEMA ||
                String(config.candidate_id || "") !== CANDIDATE_ID ||
                String(config.installation_root || "") !== String(root.getCanonicalPath())) {
            fail("P3_PREFLIGHT_RUNTIME_CONFIG_INVALID");
        }
        python = new File(String(config.python_executable || "")).getCanonicalFile();
        runtime = new File(root, String(config.python_runtime_relative_path || "")).getCanonicalFile();
        manager = new File(root, String(config.manager_relative_path || "")).getCanonicalFile();
        if (!isPlainFile(python) || sha256File(python) !== String(config.python_executable_sha256) ||
                !runtime.isDirectory() || Files.isSymbolicLink(runtime.toPath()) ||
                !isPlainFile(manager) || sha256File(manager) !== String(config.manager_sha256)) {
            fail("P3_PREFLIGHT_RUNTIME_BINDING_FAILED");
        }
        return {python: python, runtime: runtime, manager: manager};
    }

    function readProcessOutput(process) {
        var reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
        var lines = [];
        var line;
        try { while ((line = reader.readLine()) !== null) { lines.push(String(line)); } }
        finally { reader.close(); }
        return lines.join("\n");
    }

    function invokePreflight(argumentsObject) {
        var runtime = locateRuntime();
        var requestId = String(UUID.randomUUID().toString());
        var request = {arguments: argumentsObject, operation: "scale_preflight_no_write",
            request_id: requestId, schema: REQUEST_SCHEMA};
        var requestText = canonicalJsonText(request);
        var temporary = Files.createTempDirectory("ctl-p3-preflight-").toFile().getCanonicalFile();
        var requestFile = new File(temporary, "request.json").getCanonicalFile();
        var responseFile = new File(temporary, "response.json").getCanonicalFile();
        var command = new ArrayList();
        var process;
        var output;
        var response;
        Files.write(requestFile.toPath(), new java.lang.String(requestText).getBytes(StandardCharsets.UTF_8),
            StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        command.add(String(runtime.python.getCanonicalPath()));
        command.add("-I"); command.add("-B"); command.add("-c");
        command.add("import runpy,sys;runtime_root=sys.argv[1];manager_path=sys.argv[2];" +
            "manager_args=sys.argv[3:];sys.path.insert(0,runtime_root);" +
            "sys.argv=[manager_path]+manager_args;runpy.run_module('cavity_tem_light_p3.manager',run_name='__main__')");
        command.add(String(runtime.runtime.getCanonicalPath()));
        command.add(String(runtime.manager.getCanonicalPath()));
        command.add("--request"); command.add(String(requestFile.getCanonicalPath()));
        command.add("--request-sha256"); command.add(sha256Text(requestText));
        command.add("--response"); command.add(String(responseFile.getCanonicalPath()));
        try {
            process = new Packages.java.lang.ProcessBuilder(command).redirectErrorStream(true).start();
            if (!process.waitFor(BACKEND_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                process.destroyForcibly(); fail("P3_PREFLIGHT_BACKEND_TIMEOUT");
            }
            output = readProcessOutput(process);
            if (Number(process.exitValue()) !== 0 || !isPlainFile(responseFile)) {
                fail("P3_PREFLIGHT_BACKEND_FAILED: " + output.replace(/[\r\n]+/g, " "));
            }
            response = JSON.parse(readUtf8(responseFile));
            if (!exactKeys(response, ["errors", "operation", "request_id", "result", "schema", "status", "warnings"]) ||
                    String(response.schema || "") !== RESPONSE_SCHEMA ||
                    String(response.request_id || "") !== requestId ||
                    String(response.operation || "") !== "scale_preflight_no_write" ||
                    String(response.status || "") !== "PASS" || response.errors.length !== 0) {
                fail("P3_PREFLIGHT_REJECTED: " + JSON.stringify(response.errors || []));
            }
            return response.result;
        } finally {
            try { Files.deleteIfExists(requestFile.toPath()); } catch (ignoredRequest) {}
            try { Files.deleteIfExists(responseFile.toPath()); } catch (ignoredResponse) {}
            try { Files.deleteIfExists(temporary.toPath()); } catch (ignoredDirectory) {}
        }
    }

    function updateDigestByte(digest, value) {
        var bytes = java.lang.reflect.Array.newInstance(java.lang.Byte.TYPE, 1);
        bytes[0] = value > 127 ? value - 256 : value;
        digest.update(bytes);
    }

    function updateDigestIntLE(digest, value, count) {
        var index;
        for (index = 0; index < count; index += 1) {
            updateDigestByte(digest, (value >>> (8 * index)) & 255);
        }
    }

    function masterPixelEvidence(imp) {
        var pixels = imp.getProcessor().getPixels();
        var bitDepth = Number(imp.getBitDepth());
        var width = Number(imp.getWidth());
        var height = Number(imp.getHeight());
        var header;
        var digest;
        var i;
        var value;
        if (Number(imp.getStackSize()) !== 1 || Number(imp.getNChannels()) !== 1 ||
                Number(imp.getNSlices()) !== 1 || Number(imp.getNFrames()) !== 1 ||
                [8, 16, 24, 32].indexOf(bitDepth) < 0 || Number(pixels.length) !== width * height) {
            fail("P3_PREFLIGHT_PIXEL_LAYOUT_UNSUPPORTED");
        }
        header = PIXEL_METHOD + "\nwidth=" + width + "\nheight=" + height +
            "\nbit_depth=" + bitDepth + "\nchannels=1\nslices=1\nframes=1\nbyte_order=LITTLE_ENDIAN\n";
        digest = MessageDigest.getInstance("SHA-256");
        digest.update(new java.lang.String(header).getBytes(StandardCharsets.UTF_8));
        for (i = 0; i < pixels.length; i += 1) {
            if (bitDepth === 8) {
                value = Number(pixels[i]); if (value < 0) { value += 256; }
                updateDigestByte(digest, value);
            } else if (bitDepth === 16) {
                value = Number(pixels[i]); if (value < 0) { value += 65536; }
                updateDigestIntLE(digest, value, 2);
            } else if (bitDepth === 24) {
                value = Number(pixels[i]);
                updateDigestByte(digest, (value >>> 16) & 255);
                updateDigestByte(digest, (value >>> 8) & 255);
                updateDigestByte(digest, value & 255);
            } else {
                updateDigestIntLE(digest, Packages.java.lang.Float.floatToRawIntBits(pixels[i]), 4);
            }
        }
        return {bit_depth: bitDepth, channels: 1, evidence_only: true, frames: 1,
            height: height, image_title: String(imp.getTitle() || ""), method: PIXEL_METHOD,
            schema: "CTL_P3_MASKS_MASTER_PIXEL_EVIDENCE_V1", scientific_validation: false,
            scientifically_validated: false, sha256: hex(digest.digest()), slices: 1,
            source_sha256: EXPECTED_SOURCE_SHA256, width: width};
    }

    function unitFactor(raw) {
        var token = String(raw === null || raw === undefined ? "" : raw).replace(/^\s+|\s+$/g, "");
        var folded;
        if (token === "A") { return {factor: 0.1, token: token}; }
        folded = token.toLowerCase();
        if (["nm", "nanometer", "nanometers", "nanometre", "nanometres"].indexOf(folded) >= 0) {
            return {factor: 1, token: token};
        }
        if (["µm", "μm", "um", "micron", "microns", "micrometer", "micrometers",
                "micrometre", "micrometres"].indexOf(folded) >= 0) {
            return {factor: 1000, token: token};
        }
        if (["å", "angstrom", "angstroms", "ångström", "ångströms"].indexOf(folded) >= 0) {
            return {factor: 0.1, token: token};
        }
        if (["pm", "picometer", "picometers", "picometre", "picometres"].indexOf(folded) >= 0) {
            return {factor: 0.001, token: token};
        }
        fail("P3_PREFLIGHT_SPATIAL_UNIT_UNSUPPORTED");
    }

    function roiProperty(roi, name) {
        var direct = roi.getProperty(String(name));
        var lines;
        var i;
        var match;
        if (direct !== null && direct !== undefined && String(direct) !== "") { return String(direct); }
        lines = String(roi.getProperties() || "").split(/\r?\n/);
        for (i = 0; i < lines.length; i += 1) {
            match = /^([^:=]+)[:=](.*)$/.exec(lines[i]);
            if (match !== null && String(match[1]).replace(/^\s+|\s+$/g, "") === name) {
                return String(match[2]).replace(/^\s+|\s+$/g, "");
            }
        }
        return "";
    }

    function roiType(roi) {
        var value = String(roiProperty(roi, "Type") || roiProperty(roi, "Object_type") || "");
        if (value === "analysis_area" || value === "mask") { return "analysis_mask"; }
        if (value === "surface_reference") { return "surface"; }
        return value;
    }

    function validPixelCount(imp) {
        var manager = RoiManager.getInstance2();
        var processor = new ByteProcessor(Number(imp.getWidth()), Number(imp.getHeight()));
        var masks = [];
        var exclusions = [];
        var pixels;
        var i;
        var roi;
        var type;
        var count = 0;
        if (manager === null) { fail("P3_PREFLIGHT_ROI_MANAGER_ABSENT"); }
        for (i = 0; i < Number(manager.getCount()); i += 1) {
            roi = manager.getRoi(i); type = roiType(roi);
            if (type === "analysis_mask") { masks.push(roi); }
            else if (type === "exclusion") { exclusions.push(roi); }
        }
        if (masks.length === 0) { processor.setValue(255); processor.fill(); }
        else {
            processor.setValue(255);
            for (i = 0; i < masks.length; i += 1) { processor.fill(masks[i]); }
        }
        processor.setValue(0);
        for (i = 0; i < exclusions.length; i += 1) { processor.fill(exclusions[i]); }
        pixels = processor.getPixels();
        for (i = 0; i < pixels.length; i += 1) {
            if ((Number(pixels[i]) & 255) !== 0) { count += 1; }
        }
        return count;
    }

    try {
        var imp = WindowManager.getCurrentImage();
        var projectRoot = String(IJ.getProperty("CTL.P3.smoke.project_root") || "");
        var sourcePath = String(IJ.getProperty("CTL.P3.smoke.source_path") || "");
        var source = new File(sourcePath).getCanonicalFile();
        var calibration;
        var x;
        var y;
        var defaultUnit;
        var rawX;
        var rawY;
        var count;
        var imageContext;
        var result;
        var report;
        if (imp === null || projectRoot === "") { fail("P3_PREFLIGHT_PORTABLE_CONTEXT_ABSENT"); }
        if (!isPlainFile(source) || Number(source.length()) !== EXPECTED_SOURCE_BYTES ||
                sha256File(source) !== EXPECTED_SOURCE_SHA256) { fail("P3_PREFLIGHT_SOURCE_IDENTITY_MISMATCH"); }
        calibration = imp.getCalibration();
        rawX = Number(calibration.pixelWidth); rawY = Number(calibration.pixelHeight);
        x = unitFactor(calibration.getXUnit()); y = unitFactor(calibration.getYUnit());
        defaultUnit = unitFactor(calibration.getUnit());
        if (!(rawX > 0) || !(rawY > 0) || defaultUnit.factor !== x.factor) {
            fail("P3_PREFLIGHT_SPATIAL_CALIBRATION_INVALID");
        }
        count = validPixelCount(imp);
        imageContext = {bit_depth: Number(imp.getBitDepth()), decoder_opening_method: "loci.plugins.BF.openImagePlus",
            default_unit: defaultUnit.token, factor_x_to_nm: x.factor, factor_y_to_nm: y.factor,
            fiji_imagej_version: String(IJ.getVersion()), height_px: Number(imp.getHeight()),
            master_pixel_evidence: masterPixelEvidence(imp), normalization_rule_id: "CTL_SPATIAL_UNIT_NORMALIZATION_V1",
            raw_pixel_height: rawY, raw_pixel_width: rawX, raw_x_unit: x.token, raw_y_unit: y.token,
            scale_x_nm_px: rawX * x.factor, scale_y_nm_px: rawY * y.factor, width_px: Number(imp.getWidth())};
        result = invokePreflight({expected_source_bytes: EXPECTED_SOURCE_BYTES,
            expected_source_sha256: EXPECTED_SOURCE_SHA256,
            image_context: imageContext, project_root: projectRoot, valid_pixel_count: count});
        if (String(result.result || "") !== "PASS" || Number(result.writes) !== 0) {
            fail("P3_PREFLIGHT_RESULT_NOT_PASS_NO_WRITE");
        }
        report = [
            "raw_pixel_width=" + String(result.raw_pixel_width),
            "raw_pixel_height=" + String(result.raw_pixel_height),
            "raw_x_unit=" + String(result.raw_x_unit),
            "raw_y_unit=" + String(result.raw_y_unit),
            "factor_x_to_nm=" + String(result.factor_x_to_nm),
            "factor_y_to_nm=" + String(result.factor_y_to_nm),
            "scale_x_nm_px=" + String(result.scale_x_nm_px),
            "scale_y_nm_px=" + String(result.scale_y_nm_px),
            "revision_id=" + String(result.revision_id),
            "revision_scale_x_nm_px=" + String(result.revision_scale_x_nm_px),
            "revision_scale_y_nm_px=" + String(result.revision_scale_y_nm_px),
            "valid_pixels=" + String(result.valid_pixels),
            "predicted_net_area_nm2=" + String(result.predicted_net_area_nm2),
            "result=" + String(result.result),
            "writes=" + String(result.writes)
        ].join("\n");
        var area = new JTextArea(report, 18, 72);
        area.setEditable(false);
        JOptionPane.showMessageDialog(null, new JScrollPane(area),
            "Prompt3 Scale Preflight - No Write", JOptionPane.INFORMATION_MESSAGE);
    } catch (error) {
        IJ.log("CTL Prompt3 scale preflight ERROR: " + String(error));
        JOptionPane.showMessageDialog(null, String(error),
            "Prompt3 Scale Preflight - No Write", JOptionPane.ERROR_MESSAGE);
    }
}());
