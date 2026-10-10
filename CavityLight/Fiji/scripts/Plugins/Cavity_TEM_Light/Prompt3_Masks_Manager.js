/*
 * Cavity TEM Light - Prompt 3 functional masks manager (technical preview DEV01).
 *
 * This is a separate Fiji/SciJava JavaScript adapter.  It does not alter or
 * replace the Prompt 1 macro/runtime.  Pixel hashes produced here are explicit
 * provenance evidence only; they are not a scientific-validation claim.
 */
(function () {
    "use strict";

    var IJ = Packages.ij.IJ;
    var ImagePlus = Packages.ij.ImagePlus;
    var GaussianBlur = Packages.ij.plugin.filter.GaussianBlur;
    var BF = Packages.loci.plugins.BF;
    var ImporterOptions = Packages.loci.plugins.in.ImporterOptions;
    var WindowManager = Packages.ij.WindowManager;
    var RoiManager = Packages.ij.plugin.frame.RoiManager;
    var RoiEncoder = Packages.ij.io.RoiEncoder;
    var RoiDecoder = Packages.ij.io.RoiDecoder;
    var OvalRoi = Packages.ij.gui.OvalRoi;
    var Rectangle2DDouble = Packages.java.awt.geom.Rectangle2D.Double;
    var Overlay = Packages.ij.gui.Overlay;
    var Toolbar = Packages.ij.gui.Toolbar;
    var ByteProcessor = Packages.ij.process.ByteProcessor;
    var File = Packages.java.io.File;
    var FileInputStream = Packages.java.io.FileInputStream;
    var BufferedInputStream = Packages.java.io.BufferedInputStream;
    var BufferedReader = Packages.java.io.BufferedReader;
    var InputStreamReader = Packages.java.io.InputStreamReader;
    var MessageDigest = Packages.java.security.MessageDigest;
    var ByteArrayOutputStream = Packages.java.io.ByteArrayOutputStream;
    var ZipOutputStream = Packages.java.util.zip.ZipOutputStream;
    var ZipEntry = Packages.java.util.zip.ZipEntry;
    var ArrayList = Packages.java.util.ArrayList;
    var Files = Packages.java.nio.file.Files;
    var StandardCharsets = Packages.java.nio.charset.StandardCharsets;
    var StandardOpenOption = Packages.java.nio.file.StandardOpenOption;
    var Base64 = Packages.java.util.Base64;
    var UUID = Packages.java.util.UUID;
    var TimeUnit = Packages.java.util.concurrent.TimeUnit;
    var SwingUtilities = Packages.javax.swing.SwingUtilities;
    var Timer = Packages.javax.swing.Timer;
    var JFrame = Packages.javax.swing.JFrame;
    var JPanel = Packages.javax.swing.JPanel;
    var JLabel = Packages.javax.swing.JLabel;
    var JButton = Packages.javax.swing.JButton;
    var JCheckBox = Packages.javax.swing.JCheckBox;
    var JTable = Packages.javax.swing.JTable;
    var DefaultTableModel = Packages.javax.swing.table.DefaultTableModel;
    var JScrollPane = Packages.javax.swing.JScrollPane;
    var JTextArea = Packages.javax.swing.JTextArea;
    var JTextField = Packages.javax.swing.JTextField;
    var JFileChooser = Packages.javax.swing.JFileChooser;
    var JOptionPane = Packages.javax.swing.JOptionPane;
    var ListSelectionModel = Packages.javax.swing.ListSelectionModel;
    var BorderLayout = Packages.java.awt.BorderLayout;
    var FlowLayout = Packages.java.awt.FlowLayout;
    var GridLayout = Packages.java.awt.GridLayout;
    var Dimension = Packages.java.awt.Dimension;
    var Color = Packages.java.awt.Color;
    var Frame = Packages.java.awt.Frame;
    var ActionListener = Packages.java.awt.event.ActionListener;
    var WindowAdapter = Packages.java.awt.event.WindowAdapter;
    var MouseAdapter = Packages.java.awt.event.MouseAdapter;
    var MouseEvent = Packages.java.awt.event.MouseEvent;
    var Runnable = Packages.java.lang.Runnable;
    var Thread = Packages.java.lang.Thread;
    var System = Packages.java.lang.System;
    var Character = Packages.java.lang.Character;
    var Normalizer = Packages.java.text.Normalizer;
    var NormalizerForm = Packages.java.text.Normalizer.Form;

    var CANDIDATE_ID = "Cavity_TEM_Light_R10_PROMPT3_MASKS_PREVIEW_DEV01";
    var CONFIG_SCHEMA = "CTL_P3_MASKS_RUNTIME_CONFIG_V1";
    var REQUEST_SCHEMA = "CTL_P3_MASKS_BRIDGE_REQUEST_V1";
    var RESPONSE_SCHEMA = "CTL_P3_MASKS_BRIDGE_RESPONSE_V1";
    var ROI_SCHEMA = "CTL_P3_MASKS_FIJI_ROI_SNAPSHOT_V1";
    var PIXEL_METHOD = "CTL_MASTER_PIXEL_SHA256_V1";
    var WINDOW_TITLE = "Cavity TEM Light - Prompt 3 Masks DEV01";
    var DISPLAY_MODES = ["HIDDEN", "OUTLINE"];
    var GEOMETRY_TYPES = ["analysis_mask", "exclusion", "surface"];
    var DEFAULT_DISPLAY_MODES = {
        analysis_mask: "OUTLINE", exclusion: "OUTLINE", surface: "OUTLINE"
    };
    var TEMPORARY_REVEAL_MS = 3000;
    var BACKEND_TIMEOUT_SECONDS = 300;
    var GEOMETRY_SCHEMA = "CTL_P3_IMAGEJ_ROI_GEOMETRY_V1";
    var SPATIAL_NORMALIZATION_RULE_ID = "CTL_SPATIAL_UNIT_NORMALIZATION_V1";
    var SPATIAL_SCALE_ABSOLUTE_TOLERANCE = 1e-12;
    var SPATIAL_SCALE_RELATIVE_TOLERANCE = 1e-6;
    var IMAGE_DECODER_OPENING_METHOD = "loci.plugins.BF.openImagePlus";
    var GEOMETRY_COLORS = {
        // cyan apto para daltonismo, magenta y ámbar: solo clones del overlay.
        analysis_mask: new Color(0, 210, 255),
        exclusion: new Color(255, 0, 190),
        surface: new Color(255, 190, 0)
    };
    var OPERATIONS = [
        "inspect_project", "create_session", "select_session", "set_canonical",
        "mark_superseded", "save_revision", "clone_revision", "publish_run",
        "inspect_run_scientific_scale", "publish_scale_disposition",
        "publish_run_disposition",
        "get_geometry_state", "set_display_mode", "commit_analysis_area_cache",
        "migrate_legacy", "inspect_legacy_quarantine", "archive_session",
        "restore_session", "verify_project", "save_draft", "load_draft", "discard_draft",
        "p3_create_project", "p3_register_source_image", "p3_source_image_context"
    ];
    var OPERATION_LABELS = {
        inspect_project: "Leyendo y verificando el proyecto",
        p3_create_project: "Creando el proyecto",
        p3_register_source_image: "Incorporando y verificando la imagen",
        p3_source_image_context: "Recuperando la fuente de la imagen",
        decode_source_image: "Leyendo píxeles y escala de la imagen TEM",
        create_session: "Creando la sesión",
        select_session: "Abriendo y verificando la sesión",
        set_canonical: "Marcando la sesión de referencia",
        mark_superseded: "Actualizando el estado de la sesión",
        save_revision: "Guardando y verificando la revisión",
        clone_revision: "Copiando la revisión a una sesión nueva",
        publish_run: "Calculando y verificando los resultados",
        inspect_run_scientific_scale: "Verificando la escala de los resultados",
        publish_scale_disposition: "Registrando la corrección de escala",
        publish_run_disposition: "Registrando el estado de los resultados",
        get_geometry_state: "Cargando y verificando las geometrías",
        set_display_mode: "Guardando la preferencia de visualización",
        commit_analysis_area_cache: "Verificando y guardando el área de análisis",
        migrate_legacy: "Migrando el proyecto por copia",
        inspect_legacy_quarantine: "Consultando el historial conservado",
        archive_session: "Archivando la sesión",
        restore_session: "Restaurando y verificando la sesión",
        verify_project: "Verificando el proyecto",
        save_draft: "Guardando el borrador recuperable",
        load_draft: "Comprobando el borrador de esta sesión",
        discard_draft: "Descartando el borrador seleccionado",
        create_inspection_view: "Creando y verificando la vista de inspección",
        replay_inspection_recipe: "Reaplicando y verificando la receta guardada",
        prepare_manual_candidate: "Verificando la propuesta manual y su imagen",
        review_manual_candidate: "Verificando la revisión sobre el original",
        export_inspection_recipe: "Verificando y guardando la receta de la vista"
    };
    var TABLE_COLUMNS = [
        "project_id", "image_id", "source_sha256", "analysis_session_id", "state",
        "current_revision", "current_run", "revision_count", "run_count",
        "migration_status", "editable_baseline_revision", "quarantined_revision_count",
        "logical_bytes", "physical_bytes", "origin", "session_uid", "generation",
        "object_count", "_state_label"
    ];
    // Keep the original model indices stable. Only the visible TableColumn objects move.
    var SESSION_SUMMARY_COLUMNS = [3, 1, 18, 5, 6, 17];
    var SESSION_COLUMN_LABELS = [
        "Proyecto", "Imagen", "SHA-256 de la fuente", "Sesión", "Estado técnico",
        "Revisión", "Resultado", "Revisiones guardadas", "Resultados guardados",
        "Estado de migración", "Revisión editable inicial", "Revisiones en cuarentena",
        "Bytes lógicos", "Bytes físicos", "Origen", "UID de sesión", "Generación",
        "Cavidades", "Estado"
    ];
    var SESSION_COLUMN_WIDTHS = [
        180, 190, 470, 260, 245, 145, 145, 155, 155, 240, 185, 195,
        150, 150, 220, 340, 110, 110, 235
    ];

    var HISTORY_MAX_STEPS = 20;
    var HISTORY_MAX_BYTES = 32 * 1024 * 1024;
    var INSPECTION_MAX_VIEWS = 2;
    var INSPECTION_MAX_BYTES = 128 * 1024 * 1024;
    var INSPECTION_RECIPE_MAX_BYTES = 64 * 1024;
    var state = {
        projectPath: null,
        projectUid: null,
        projectKind: null,
        sessions: [],
        activeSessionUid: null,
        activeGeneration: null,
        activeSession: null,
        activeObjects: [],
        workingObjects: [],
        activeCandidates: [],
        candidateReview: null,
        candidateOperator: "",
        cloneRoiIdentityBridge: null,
        activeGeometries: [],
        geometryState: null,
        images: [],
        migrationLimitations: [],
        baselineRoiSha256: null,
        boundImage: null,
        displayModes: jsonClone(DEFAULT_DISPLAY_MODES),
        displayPreferencesSha256: "NOT_APPLICABLE",
        displayEpoch: 0,
        editFillAlpha: 72,
        temporaryReveal: false,
        temporaryRevealToken: 0,
        temporaryRevealTimer: null,
        editState: null,
        cavityClickBinding: null,
        geometryDirty: false,
        callbackEpoch: 0,
        busy: false,
        operationProgressTimer: null,
        sessionDetailsVisible: false,
        draftTimer: null,
        draftReady: false,
        draftImageContext: null,
        draftLastSnapshotSha256: null,
        draftAutosave: true,
        draftPaused: false,
        editHistory: null,
        historyNotice: "",
        inspectionViews: [],
        disposed: false
    };
    var frame;
    var projectField;
    var statusLabel;
    var operationTimingLabel;
    var migrationWarningLabel;
    var table;
    var tableModel;
    var sessionTableColumns = [];
    var activeSessionLabel;
    var draftStatusLabel;
    var saveDraftButton;
    var recoverDraftButton;
    var discardDraftButton;
    var undoButton;
    var redoButton;
    var recordHistoryButton;
    var historyStatusLabel;
    var candidateStatusLabel;
    var refreshButton;
    var actionButtons = [];
    var maskModeButton;
    var exclusionModeButton;
    var surfaceModeButton;
    var editButton;
    var confirmEditButton;
    var cancelEditButton;
    var temporaryRevealButton;
    var restoreOutlineButton;

    function fail(code) {
        throw new Error(String(code));
    }

    function spatialUnitToken(rawUnit) {
        var normalized;
        var start;
        var end;
        var codePoint;
        if (rawUnit === null || rawUnit === undefined) {
            fail("SPATIAL_SCALE_UNIT_MISSING");
        }
        normalized = Normalizer.normalize(
            new java.lang.String(String(rawUnit)), NormalizerForm.NFC
        );
        start = 0;
        end = Number(normalized.length());
        while (start < end) {
            codePoint = Number(normalized.codePointAt(start));
            if (!Character.isWhitespace(codePoint) && !Character.isSpaceChar(codePoint)) { break; }
            start += Number(Character.charCount(codePoint));
        }
        while (end > start) {
            codePoint = Number(normalized.codePointBefore(end));
            if (!Character.isWhitespace(codePoint) && !Character.isSpaceChar(codePoint)) { break; }
            end -= Number(Character.charCount(codePoint));
        }
        normalized = String(normalized.substring(start, end));
        if (normalized === "") { fail("SPATIAL_SCALE_UNIT_MISSING"); }
        return normalized;
    }

    function spatialUnitFactorToNm(rawUnit) {
        var token = spatialUnitToken(rawUnit);
        var folded;
        // ImageJ's exact upper-case A spatial alias is accepted before case
        // folding.  Lower-case a is deliberately not an Angstrom alias.
        if (token === "A") { return {factor: 0.1, token: token}; }
        folded = token.toLowerCase();
        if (folded === "nm" || folded === "nanometer" || folded === "nanometers" ||
                folded === "nanometre" || folded === "nanometres") {
            return {factor: 1, token: token};
        }
        if (folded === "µm" || folded === "μm" || folded === "um" ||
                folded === "micron" || folded === "microns" ||
                folded === "micrometer" || folded === "micrometers" ||
                folded === "micrometre" || folded === "micrometres") {
            return {factor: 1000, token: token};
        }
        if (folded === "å" || folded === "angstrom" || folded === "angstroms" ||
                folded === "ångström" || folded === "ångströms") {
            return {factor: 0.1, token: token};
        }
        if (folded === "pm" || folded === "picometer" || folded === "picometers" ||
                folded === "picometre" || folded === "picometres") {
            return {factor: 0.001, token: token};
        }
        fail("SPATIAL_SCALE_UNIT_UNSUPPORTED");
    }

    function positiveSpatialScale(value) {
        var converted = Number(value);
        if (!isFinite(converted) || converted <= 0) {
            fail("SPATIAL_SCALE_VALUE_INVALID");
        }
        return converted;
    }

    function spatialScalesAgree(left, right) {
        var a = positiveSpatialScale(left);
        var b = positiveSpatialScale(right);
        var tolerance = Math.max(
            SPATIAL_SCALE_ABSOLUTE_TOLERANCE,
            SPATIAL_SCALE_RELATIVE_TOLERANCE * Math.max(Math.abs(a), Math.abs(b))
        );
        return Math.abs(a - b) <= tolerance;
    }

    function normalizedSpatialCalibration(imp) {
        var calibration;
        var rawWidth;
        var rawHeight;
        var xUnit;
        var yUnit;
        var defaultUnit;
        if (imp === null || imp === undefined) { fail("NO_BOUND_ACTIVE_IMAGE"); }
        calibration = imp.getCalibration();
        if (calibration === null || calibration === undefined) {
            fail("SPATIAL_SCALE_UNIT_MISSING");
        }
        rawWidth = positiveSpatialScale(calibration.pixelWidth);
        rawHeight = positiveSpatialScale(calibration.pixelHeight);
        xUnit = spatialUnitFactorToNm(calibration.getXUnit());
        yUnit = spatialUnitFactorToNm(calibration.getYUnit());
        defaultUnit = spatialUnitFactorToNm(calibration.getUnit());
        if (defaultUnit.factor !== xUnit.factor) {
            fail("SPATIAL_SCALE_AXIS_UNIT_CONTRADICTION");
        }
        return {
            default_unit: defaultUnit.token,
            factor_x_to_nm: xUnit.factor,
            factor_y_to_nm: yUnit.factor,
            normalization_rule_id: SPATIAL_NORMALIZATION_RULE_ID,
            raw_pixel_width: rawWidth,
            raw_pixel_height: rawHeight,
            raw_x_unit: xUnit.token,
            raw_y_unit: yUnit.token,
            scale_x_nm_px: positiveSpatialScale(rawWidth * xUnit.factor),
            scale_y_nm_px: positiveSpatialScale(rawHeight * yUnit.factor)
        };
    }

    function closedProtocolValue(objects, names) {
        var sources = [];
        var values = {};
        var i;
        var j;
        var k;
        var object;
        var source;
        var value;
        for (k = 0; k < objects.length; k += 1) {
            object = objects[k];
            if (object !== null && object !== undefined && typeof object === "object") {
                sources.push(object);
                if (object.geometry && typeof object.geometry === "object") {
                    sources.push(object.geometry);
                }
                if (object.legacy_properties && typeof object.legacy_properties === "object") {
                    sources.push(object.legacy_properties);
                }
            }
        }
        for (i = 0; i < sources.length; i += 1) {
            source = sources[i];
            for (j = 0; j < names.length; j += 1) {
                value = source[names[j]];
                if (value !== null && value !== undefined && String(value) !== "") {
                    values[String(value)] = true;
                }
            }
        }
        value = Object.keys(values).sort();
        if (value.length !== 1) { fail("SCALE_ANISOTROPY_REQUIRES_PROTOCOL"); }
        return String(value[0]);
    }

    function priorScientificObject(cavityId, objectUuid) {
        var objects = (Array.isArray(state.activeObjects) ? state.activeObjects : []).concat(state.workingObjects || []);
        var i;
        for (i = 0; i < objects.length; i += 1) {
            if ((objectUuid !== "" && String(objects[i].object_uuid || "").toLowerCase() ===
                    String(objectUuid).toLowerCase()) ||
                    (objectUuid === "" && String(objects[i].cavity_id || "") === cavityId)) {
                return objects[i];
            }
        }
        return null;
    }

    function requireCircleAnisotropyProtocol(object, propertyMap) {
        var sources = [object, propertyMap];
        var primary = closedProtocolValue(sources, [
            "measurement_protocol", "Measurement_protocol",
            "primary_measurement_protocol", "Primary_measurement_protocol"
        ]);
        var method = closedProtocolValue(sources, [
            "sampling_axis_method", "Sampling_axis_method"
        ]);
        var version = closedProtocolValue(sources, [
            "sampling_axis_method_version", "Sampling_axis_method_version"
        ]);
        if (primary !== "CAVITY_CIRCLE" || method !== "CIRCLE_CONSERVATIVE_MAX_SCALE" ||
                version !== "ANISOTROPIC_AXIS_V1") {
            fail("SCALE_ANISOTROPY_REQUIRES_PROTOCOL");
        }
    }

    function diameterNmFromBounds(bounds, spatial, object, propertyMap) {
        var widthNm = positiveSpatialScale(Number(bounds.width) * spatial.scale_x_nm_px);
        var heightNm = positiveSpatialScale(Number(bounds.height) * spatial.scale_y_nm_px);
        if (spatialScalesAgree(spatial.scale_x_nm_px, spatial.scale_y_nm_px)) {
            return (widthNm + heightNm) / 2;
        }
        requireCircleAnisotropyProtocol(object, propertyMap);
        return Math.max(widthNm, heightNm);
    }

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

    function sha256Bytes(bytes) {
        var digest = MessageDigest.getInstance("SHA-256");
        digest.update(bytes);
        return hex(digest.digest());
    }

    function sha256Text(text) {
        return sha256Bytes(new java.lang.String(String(text)).getBytes(StandardCharsets.UTF_8));
    }

    function sha256File(file) {
        var digest = MessageDigest.getInstance("SHA-256");
        var input = null;
        var buffer = java.lang.reflect.Array.newInstance(java.lang.Byte.TYPE, 1048576);
        var count;
        try {
            input = new BufferedInputStream(new FileInputStream(file));
            while ((count = input.read(buffer)) !== -1) {
                digest.update(buffer, 0, count);
            }
            return hex(digest.digest());
        } finally {
            if (input !== null) { input.close(); }
        }
    }

    function readUtf8(file) {
        return String(new java.lang.String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8));
    }

    function isPlainFile(file) {
        return file.isFile() && !Files.isSymbolicLink(file.toPath());
    }

    function exactChild(file, parent, relativePath) {
        var expected = new File(parent, String(relativePath)).getCanonicalFile();
        return file.getCanonicalFile().equals(expected) &&
            String(expected.getPath()).indexOf(String(parent.getCanonicalPath()) + File.separator) === 0;
    }

    function exactKeys(object, names) {
        var actual = [];
        var key;
        var expected = names.slice(0).sort().join("|");
        for (key in object) {
            if (Object.prototype.hasOwnProperty.call(object, key)) { actual.push(String(key)); }
        }
        return actual.sort().join("|") === expected;
    }

    function locateRuntime() {
        var fijiText = String(IJ.getDirectory("imagej") || "");
        var fiji;
        var root;
        var configFile;
        var config;
        var pythonLexical;
        var pythonRuntimeLexical;
        var managerLexical;
        var python;
        var pythonRuntime;
        var manager;
        if (fijiText === "") { fail("FIJI_ROOT_NOT_AVAILABLE"); }
        fiji = new File(fijiText).getCanonicalFile();
        root = new File(new File(fiji, "lib"), "Cavity_TEM_Light_Prompt3_Masks").getCanonicalFile();
        configFile = new File(root, "runtime_config.json").getCanonicalFile();
        if (!root.isDirectory() || Files.isSymbolicLink(root.toPath()) ||
                !exactChild(configFile, root, "runtime_config.json") || !isPlainFile(configFile)) {
            fail("RUNTIME_CONFIG_PATH_UNSAFE");
        }
        config = JSON.parse(readUtf8(configFile));
        if (!exactKeys(config, [
                "candidate_id", "created_at", "installation_root", "manager_relative_path",
                "manager_sha256", "python_executable", "python_executable_sha256",
                "python_runtime_relative_path", "schema"
            ]) || String(config.schema || "") !== CONFIG_SCHEMA ||
                String(config.candidate_id || "") !== CANDIDATE_ID ||
                String(config.installation_root || "") !== String(root.getCanonicalPath()) ||
                !/^[0-9a-f]{64}$/.test(String(config.python_executable_sha256 || "")) ||
                !/^[0-9a-f]{64}$/.test(String(config.manager_sha256 || ""))) {
            fail("RUNTIME_CONFIG_INVALID");
        }
        if (String(config.manager_relative_path || "") !==
                "python_companion/cavity_tem_light_p3/manager.py" ||
                String(config.python_runtime_relative_path || "") !== "python_companion") {
            fail("RUNTIME_CONFIG_PATHS_NOT_CLOSED");
        }
        pythonLexical = new File(String(config.python_executable || ""));
        pythonRuntimeLexical = new File(root, String(config.python_runtime_relative_path));
        managerLexical = new File(root, String(config.manager_relative_path));
        python = pythonLexical.getCanonicalFile();
        pythonRuntime = pythonRuntimeLexical.getCanonicalFile();
        manager = managerLexical.getCanonicalFile();
        if (!pythonLexical.isAbsolute() || !isPlainFile(pythonLexical) ||
                sha256File(python) !== String(config.python_executable_sha256) ||
                Files.isSymbolicLink(pythonRuntimeLexical.toPath()) ||
                !exactChild(pythonRuntime, root, String(config.python_runtime_relative_path)) ||
                !pythonRuntime.isDirectory() ||
                Files.isSymbolicLink(managerLexical.toPath()) ||
                !exactChild(manager, root, String(config.manager_relative_path)) || !isPlainFile(manager) ||
                sha256File(manager) !== String(config.manager_sha256)) {
            fail("RUNTIME_EXECUTABLE_BINDING_FAILED");
        }
        return {
            root: root,
            configFile: configFile,
            config: config,
            python: python,
            pythonRuntime: pythonRuntime,
            manager: manager
        };
    }

    function readProcessOutput(process) {
        var reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
        var lines = [];
        var line;
        try {
            while ((line = reader.readLine()) !== null) { lines.push(String(line)); }
        } finally {
            reader.close();
        }
        return lines.join("\n");
    }

    function canonicalUnicode(value) {
        var text = String(value);
        var i;
        var first;
        var second;
        for (i = 0; i < text.length; i += 1) {
            first = text.charCodeAt(i);
            if (first >= 0xD800 && first <= 0xDBFF) {
                if (i + 1 >= text.length) { fail("CANONICAL_JSON_ISOLATED_SURROGATE"); }
                second = text.charCodeAt(i + 1);
                if (second < 0xDC00 || second > 0xDFFF) {
                    fail("CANONICAL_JSON_ISOLATED_SURROGATE");
                }
                i += 1;
            } else if (first >= 0xDC00 && first <= 0xDFFF) {
                fail("CANONICAL_JSON_ISOLATED_SURROGATE");
            }
        }
        return String(Packages.java.text.Normalizer.normalize(
            new java.lang.String(text), Packages.java.text.Normalizer.Form.NFC));
    }

    function canonicalCodePoint(text, index) {
        var first = text.charCodeAt(index);
        var second;
        if (first >= 0xD800 && first <= 0xDBFF) {
            second = text.charCodeAt(index + 1);
            return {value: ((first - 0xD800) * 0x400) + (second - 0xDC00) + 0x10000, width: 2};
        }
        return {value: first, width: 1};
    }

    function compareCanonicalKeys(left, right) {
        var li = 0;
        var ri = 0;
        var lp;
        var rp;
        while (li < left.length && ri < right.length) {
            lp = canonicalCodePoint(left, li);
            rp = canonicalCodePoint(right, ri);
            if (lp.value < rp.value) { return -1; }
            if (lp.value > rp.value) { return 1; }
            li += lp.width;
            ri += rp.width;
        }
        if (li < left.length) { return 1; }
        if (ri < right.length) { return -1; }
        return 0;
    }

    function canonicalJsonString(value) {
        var text = canonicalUnicode(value);
        var parts = ['"'];
        var i;
        var character;
        var code;
        var escaped;
        for (i = 0; i < text.length; i += 1) {
            character = text.charAt(i);
            code = text.charCodeAt(i);
            if (character === '"') { parts.push('\\"'); }
            else if (character === "\\") { parts.push("\\\\"); }
            else if (character === "\b") { parts.push("\\b"); }
            else if (character === "\t") { parts.push("\\t"); }
            else if (character === "\n") { parts.push("\\n"); }
            else if (character === "\f") { parts.push("\\f"); }
            else if (character === "\r") { parts.push("\\r"); }
            else if (code < 0x20) {
                escaped = code.toString(16);
                parts.push("\\u" + ("0000" + escaped).slice(-4));
            } else { parts.push(character); }
        }
        parts.push('"');
        return parts.join("");
    }

    function canonicalNumber(value) {
        var rendered;
        if (typeof value !== "number" || value !== value || !isFinite(value) ||
                (value === 0 && (1 / value) < 0)) {
            fail("CANONICAL_JSON_NUMBER_INVALID");
        }
        rendered = String(new Packages.java.math.BigDecimal(String(value))
            .stripTrailingZeros().toPlainString());
        if (rendered === "-0") { fail("CANONICAL_JSON_NEGATIVE_ZERO"); }
        return rendered;
    }

    function canonicalJsonValue(value) {
        var kind;
        var keys;
        var normalizedKeys;
        var parts;
        var i;
        var j;
        var normalized;
        if (value === null) { return "null"; }
        kind = typeof value;
        if (kind === "string") { return canonicalJsonString(value); }
        if (kind === "number") { return canonicalNumber(value); }
        if (kind === "boolean") { return value ? "true" : "false"; }
        if (kind !== "object") { fail("CANONICAL_JSON_TYPE_UNSUPPORTED"); }
        if (Array.isArray(value)) {
            keys = Object.keys(value);
            if (keys.length !== value.length) { fail("CANONICAL_JSON_ARRAY_NOT_DENSE"); }
            parts = [];
            for (i = 0; i < value.length; i += 1) {
                if (!Object.prototype.hasOwnProperty.call(value, String(i))) {
                    fail("CANONICAL_JSON_ARRAY_NOT_DENSE");
                }
                parts.push(canonicalJsonValue(value[i]));
            }
            return "[" + parts.join(",") + "]";
        }
        keys = Object.keys(value);
        normalizedKeys = [];
        for (i = 0; i < keys.length; i += 1) {
            normalized = canonicalUnicode(keys[i]);
            for (j = 0; j < normalizedKeys.length; j += 1) {
                if (normalizedKeys[j].normalized === normalized) {
                    fail("CANONICAL_JSON_KEY_COLLISION");
                }
            }
            normalizedKeys.push({original: keys[i], normalized: normalized});
        }
        normalizedKeys.sort(function (left, right) {
            return compareCanonicalKeys(left.normalized, right.normalized);
        });
        parts = [];
        for (i = 0; i < normalizedKeys.length; i += 1) {
            parts.push(canonicalJsonString(normalizedKeys[i].normalized) + ":" +
                canonicalJsonValue(value[normalizedKeys[i].original]));
        }
        return "{" + parts.join(",") + "}";
    }

    function canonicalJsonText(value) {
        if (value === null || typeof value !== "object" || Array.isArray(value)) {
            fail("CANONICAL_JSON_ROOT_NOT_OBJECT");
        }
        return canonicalJsonValue(value) + "\n";
    }

    function invokeCli(operation, argumentsObject) {
        var runtime;
        var requestId;
        var request;
        var requestText;
        var requestSha;
        var temp;
        var requestFile;
        var responseFile;
        var process;
        var command;
        var completed;
        var output;
        var exitCode;
        var responseText;
        var response;
        var responseStatus;
        var coherentExit;
        var rejection;
        if (OPERATIONS.indexOf(String(operation)) < 0) { fail("OPERATION_NOT_ALLOWED"); }
        runtime = locateRuntime();
        requestId = String(UUID.randomUUID().toString());
        request = {
            schema: REQUEST_SCHEMA,
            request_id: requestId,
            operation: String(operation),
            arguments: argumentsObject || {}
        };
        requestText = canonicalJsonText(request);
        requestSha = sha256Text(requestText);
        temp = Files.createTempDirectory("ctl-p3-masks-").toFile().getCanonicalFile();
        requestFile = new File(temp, "request.json").getCanonicalFile();
        responseFile = new File(temp, "response.json").getCanonicalFile();
        Files.write(requestFile.toPath(), new java.lang.String(requestText).getBytes(StandardCharsets.UTF_8),
            StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        try {
            command = new ArrayList();
            command.add(String(runtime.python.getCanonicalPath()));
            command.add("-I");
            command.add("-B");
            command.add("-c");
            command.add("import runpy,sys;runtime_root=sys.argv[1];manager_path=sys.argv[2];" +
                "manager_args=sys.argv[3:];sys.path.insert(0,runtime_root);" +
                "sys.argv=[manager_path]+manager_args;runpy.run_module('cavity_tem_light_p3.manager',run_name='__main__')");
            command.add(String(runtime.pythonRuntime.getCanonicalPath()));
            command.add(String(runtime.manager.getCanonicalPath()));
            command.add("--request");
            command.add(String(requestFile.getCanonicalPath()));
            command.add("--request-sha256");
            command.add(requestSha);
            command.add("--response");
            command.add(String(responseFile.getCanonicalPath()));
            process = new Packages.java.lang.ProcessBuilder(command).redirectErrorStream(true).start();
            completed = process.waitFor(BACKEND_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            if (!completed) {
                process.destroyForcibly();
                fail("P3_MASKS_MANAGER_TIMEOUT");
            }
            output = readProcessOutput(process);
            exitCode = Number(process.exitValue());
            if (!isPlainFile(responseFile)) {
                fail("P3_MASKS_MANAGER_FAILED: " + output.replace(/[\r\n]+/g, " "));
            }
            responseText = readUtf8(responseFile);
            response = JSON.parse(responseText);
            if (canonicalJsonText(response) !== responseText) {
                fail("P3_MASKS_MANAGER_RESPONSE_NOT_CANONICAL");
            }
            if (!exactKeys(response, ["errors", "operation", "request_id", "result", "schema", "status", "warnings"]) ||
                    String(response.schema || "") !== RESPONSE_SCHEMA ||
                    String(response.request_id || "") !== requestId ||
                    String(response.operation || "") !== String(operation) ||
                    ["PASS", "ERROR", "CANCELLED"].indexOf(String(response.status || "")) < 0 ||
                    !Array.isArray(response.errors) || !Array.isArray(response.warnings)) {
                fail("P3_MASKS_MANAGER_RESPONSE_INVALID");
            }
            responseStatus = String(response.status);
            coherentExit = (exitCode === 0 &&
                (responseStatus === "PASS" || responseStatus === "CANCELLED")) ||
                ((exitCode === 2 || exitCode === 3) && responseStatus === "ERROR");
            if (!coherentExit ||
                    ((responseStatus === "PASS" || responseStatus === "CANCELLED") &&
                    response.errors.length !== 0) ||
                    (responseStatus === "ERROR" && response.errors.length === 0)) {
                fail("P3_MASKS_MANAGER_EXIT_STATUS_MISMATCH: exit=" + exitCode +
                    " status=" + responseStatus + " output=" + output.replace(/[\r\n]+/g, " "));
            }
            if (responseStatus === "ERROR") {
                rejection = new Error("P3_MASKS_MANAGER_REJECTED: " + JSON.stringify(response.errors));
                rejection.verticalErrors = response.errors;
                rejection.verticalResponse = response;
                throw rejection;
            }
            try { Files.deleteIfExists(requestFile.toPath()); } catch (ignoredRequest) {}
            try { Files.deleteIfExists(responseFile.toPath()); } catch (ignoredResponse) {}
            try { Files.deleteIfExists(temp.toPath()); } catch (ignoredDirectory) {}
            return response;
        } catch (error) {
            IJ.log("CTL Prompt3 Masks: evidencia temporal conservada en " + temp.getCanonicalPath());
            throw error;
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

    function computeMasterPixelEvidence(imp) {
        var processor;
        var pixels;
        var bitDepth;
        var width;
        var height;
        var header;
        var digest;
        var i;
        var value;
        if (imp === null || Number(imp.getStackSize()) !== 1 || Number(imp.getNChannels()) !== 1 ||
                Number(imp.getNSlices()) !== 1 || Number(imp.getNFrames()) !== 1) {
            fail("PIXEL_HASH_UNSUPPORTED_DIMENSIONS");
        }
        processor = imp.getProcessor();
        pixels = processor.getPixels();
        bitDepth = Number(imp.getBitDepth());
        width = Number(imp.getWidth());
        height = Number(imp.getHeight());
        if ([8, 16, 24, 32].indexOf(bitDepth) < 0 || Number(pixels.length) !== width * height) {
            fail("PIXEL_HASH_UNSUPPORTED_LAYOUT");
        }
        header = PIXEL_METHOD + "\nwidth=" + width + "\nheight=" + height +
            "\nbit_depth=" + bitDepth + "\nchannels=1\nslices=1\nframes=1\nbyte_order=LITTLE_ENDIAN\n";
        digest = MessageDigest.getInstance("SHA-256");
        digest.update(new java.lang.String(header).getBytes(StandardCharsets.UTF_8));
        for (i = 0; i < pixels.length; i += 1) {
            if (bitDepth === 8) {
                value = Number(pixels[i]);
                if (value < 0) { value += 256; }
                updateDigestByte(digest, value);
            } else if (bitDepth === 16) {
                value = Number(pixels[i]);
                if (value < 0) { value += 65536; }
                updateDigestIntLE(digest, value, 2);
            } else if (bitDepth === 24) {
                value = Number(pixels[i]);
                updateDigestByte(digest, (value >>> 16) & 255);
                updateDigestByte(digest, (value >>> 8) & 255);
                updateDigestByte(digest, value & 255);
            } else {
                value = java.lang.Float.floatToRawIntBits(pixels[i]);
                updateDigestIntLE(digest, value, 4);
            }
        }
        return {
            schema: "CTL_P3_MASKS_MASTER_PIXEL_EVIDENCE_V1",
            method: PIXEL_METHOD,
            sha256: hex(digest.digest()),
            width: width,
            height: height,
            bit_depth: bitDepth,
            channels: 1,
            slices: 1,
            frames: 1,
            image_title: String(imp.getTitle() || ""),
            source_sha256: String(imp.getProperty("CTL.P1.source_sha256") || ""),
            evidence_only: true,
            scientific_validation: false,
            scientifically_validated: false
        };
    }

    function geometrySnapshotFromRoi(roi, type, bytes, encoded) {
        var bounds = roi.getFloatBounds();
        var polygon = roi.getFloatPolygon();
        var coordinates = [];
        var labels;
        var i;
        var uuid = geometryUuidForRoi(roi);
        var digest = sha256Bytes(bytes);
        var geometryId;
        var prior = null;
        geometryId = geometryIdForRoi(roi, type);
        for (i = 0; i < state.activeGeometries.length; i += 1) {
            if (String(state.activeGeometries[i].geometry_uid || "").toLowerCase() === uuid &&
                    String(state.activeGeometries[i].geometry_id || "") === geometryId) {
                prior = state.activeGeometries[i];
                break;
            }
        }
        if (prior !== null && String(prior.roi_bytes_sha256 || "") === digest) {
            return jsonClone(prior);
        }
        if (polygon !== null) {
            for (i = 0; i < Number(polygon.npoints); i += 1) {
                coordinates.push({x_px: Number(polygon.xpoints[i]), y_px: Number(polygon.ypoints[i])});
            }
        }
        if (coordinates.length === 0) {
            coordinates.push({x_px: Number(bounds.x), y_px: Number(bounds.y)});
            coordinates.push({x_px: Number(bounds.x) + Number(bounds.width),
                y_px: Number(bounds.y) + Number(bounds.height)});
        }
        labels = prior !== null ? jsonClone(prior.labels) : {
            name: String(roi.getName() || ""),
            scientific_role: type,
            mask_label: String(roiProperty(roi, "Mask_label") || ""),
            exclusion_reason: String(roiProperty(roi, "Exclusion_reason") || ""),
            material_side_sign: String(roiProperty(roi, "Material_side_sign") || "")
        };
        return {
            bounds: {
                x_px: Number(bounds.x), y_px: Number(bounds.y),
                width_px: Number(bounds.width), height_px: Number(bounds.height)
            },
            coordinates: coordinates,
            geometry_id: geometryId,
            geometry_schema: prior === null ? GEOMETRY_SCHEMA : String(prior.geometry_schema),
            geometry_type: type,
            geometry_uid: uuid,
            labels: labels,
            roi_bytes_base64: encoded,
            roi_bytes_sha256: digest,
            source_roi_sha256: digest
        };
    }

    function exportAllFijiRois() {
        requireOriginalImage(state.boundImage);
        var manager = RoiManager.getInstance2();
        var rois = [];
        var geometries = [];
        var cavityZipEntries = [];
        var geometryZipEntries = [];
        var unmanagedZipEntries = [];
        var canonicalZipEntries;
        var zipBuffer = new ByteArrayOutputStream();
        var zip;
        var i;
        var roi;
        var type;
        var bytes;
        var bounds;
        var encoded;
        var entry;
        var spatial = normalizedSpatialCalibration(state.boundImage);
        var scaleX = spatial.scale_x_nm_px;
        var scaleY = spatial.scale_y_nm_px;
        var propertyMap;
        var cavityId;
        var objectUuid;
        var priorObject;
        var objects;
        if (manager !== null) {
            for (i = 0; i < Number(manager.getCount()); i += 1) {
                roi = manager.getRoi(i);
                if (roi === null) { continue; }
                type = normalizeRoiType(roi);
                bytes = RoiEncoder.saveAsByteArray(roi);
                bounds = roi.getFloatBounds();
                encoded = String(Base64.getEncoder().encodeToString(bytes));
                propertyMap = parseRoiProperties(String(roi.getProperties() || ""));
                if (type === "cavity") {
                    cavityId = String(propertyMap.Cavity_id || propertyMap.cavity_id || "");
                    if (!/^CAV_[0-9]{6}$/.test(cavityId)) { fail("LIVE_ROI_CAVITY_ID_INVALID"); }
                    objectUuid = String(propertyMap.Object_uuid || propertyMap.object_uuid || "");
                    priorObject = priorScientificObject(cavityId, objectUuid);
                    rois.push({
                        index: rois.length,
                        cavity_id: cavityId,
                        name: String(manager.getName(i) || roi.getName() || ""),
                        properties: String(roi.getProperties() || ""),
                        geometry: {
                            center_x_px: Number(bounds.x) + Number(bounds.width) / 2,
                            center_y_px: Number(bounds.y) + Number(bounds.height) / 2,
                            center_x_nm: (Number(bounds.x) + Number(bounds.width) / 2) * scaleX,
                            center_y_nm: (Number(bounds.y) + Number(bounds.height) / 2) * scaleY,
                            diameter_nm: diameterNmFromBounds(
                                bounds, spatial, priorObject, propertyMap
                            ),
                            review_status: String(propertyMap.Review_status || "reviewed")
                        },
                        bounds: {
                            x: Number(bounds.x), y: Number(bounds.y),
                            width: Number(bounds.width), height: Number(bounds.height)
                        },
                        roi_bytes_base64: encoded,
                        roi_bytes_sha256: sha256Bytes(bytes),
                        roi_bytes: Number(bytes.length)
                    });
                    cavityZipEntries.push({bytes: bytes});
                    if (/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(objectUuid)) {
                        rois[rois.length - 1].object_uuid = objectUuid.toLowerCase();
                        rois[rois.length - 1].identity_provenance = {
                            generation_method: "PRESERVED",
                            source: "FIJI_ACTIVE_SESSION_ROI_SNAPSHOT"
                        };
                    }
                } else if (isGeometryType(type)) {
                    geometryZipEntries.push({
                        bytes: bytes,
                        geometry: geometrySnapshotFromRoi(roi, type, bytes, encoded)
                    });
                } else {
                    unmanagedZipEntries.push({bytes: bytes});
                }
            }
        }
        geometryZipEntries.sort(function (left, right) {
            return String(left.geometry.geometry_uid) < String(right.geometry.geometry_uid) ? -1 :
                (String(left.geometry.geometry_uid) > String(right.geometry.geometry_uid) ? 1 : 0);
        });
        for (i = 0; i < geometryZipEntries.length; i += 1) {
            geometries.push(geometryZipEntries[i].geometry);
        }
        canonicalZipEntries = cavityZipEntries.concat(geometryZipEntries).concat(unmanagedZipEntries);
        zip = new ZipOutputStream(zipBuffer);
        try {
            for (i = 0; i < canonicalZipEntries.length; i += 1) {
                bytes = canonicalZipEntries[i].bytes;
                entry = new ZipEntry(("00000" + i).slice(-5) + ".roi");
                entry.setTime(0);
                zip.putNextEntry(entry);
                zip.write(bytes, 0, bytes.length);
                zip.closeEntry();
            }
        } finally {
            zip.finish();
            zip.close();
        }
        objects = reconcileActiveObjects(rois);
        encoded = JSON.stringify({geometries: geometries, rois: rois, candidates: state.activeCandidates});
        return {
            schema: ROI_SCHEMA,
            roi_count: rois.length + geometries.length,
            rois: rois,
            geometries: geometries,
            objects: objects,
            snapshot_sha256: sha256Text(encoded),
            roi_zip_sha256: sha256Bytes(zipBuffer.toByteArray()),
            roi_zip_bytes: Number(zipBuffer.size())
        };
    }

    function jsonClone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function reconcileActiveObjects(liveRois) {
        var priorObjects = (Array.isArray(state.activeObjects) ? state.activeObjects : []).concat(state.workingObjects || []);
        var byCavity = {};
        var byUuid = {};
        var seenPrior = {};
        var seenCavity = {};
        var seenUuid = {};
        var merged = [];
        var i;
        var prior;
        var live;
        var cavityId;
        var objectUuid;
        var fromCavity;
        var fromUuid;
        var object;
        var geometry;
        var key;
        if (!Array.isArray(liveRois)) { fail("LIVE_ROI_SNAPSHOT_NOT_ARRAY"); }
        for (i = 0; i < priorObjects.length; i += 1) {
            prior = priorObjects[i] || {};
            cavityId = String(prior.cavity_id || "");
            objectUuid = String(prior.object_uuid || "").toLowerCase();
            if (!/^CAV_[0-9]{6}$/.test(cavityId) ||
                    !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(objectUuid) ||
                    byCavity[cavityId] !== undefined || byUuid[objectUuid] !== undefined) {
                fail("ACTIVE_OBJECT_IDENTITY_INVENTORY_INVALID");
            }
            byCavity[cavityId] = prior;
            byUuid[objectUuid] = prior;
        }
        for (i = 0; i < liveRois.length; i += 1) {
            live = liveRois[i] || {};
            cavityId = String(live.cavity_id || "");
            objectUuid = String(live.object_uuid || "").toLowerCase();
            if (!/^CAV_[0-9]{6}$/.test(cavityId) || seenCavity[cavityId] === true) {
                fail("LIVE_ROI_CAVITY_ID_INVALID_OR_DUPLICATE");
            }
            seenCavity[cavityId] = true;
            if (objectUuid !== "") {
                if (seenUuid[objectUuid] === true) { fail("LIVE_ROI_OBJECT_UUID_DUPLICATE"); }
                seenUuid[objectUuid] = true;
                fromUuid = byUuid[objectUuid];
                fromCavity = byCavity[cavityId];
                if (fromUuid === undefined || fromCavity === undefined || fromUuid !== fromCavity) {
                    fail("LIVE_ROI_OBJECT_IDENTITY_MISMATCH");
                }
                prior = fromUuid;
                seenPrior[objectUuid] = true;
                object = jsonClone(prior);
                delete object.object_sha256;
            } else {
                if (byCavity[cavityId] !== undefined) {
                    fail("EXISTING_ROI_LOST_OBJECT_UUID");
                }
                object = {
                    candidate_uuid: null,
                    cavity_id: cavityId,
                    identity_provenance: {
                        generation_method: "UUIDV4_RANDOM",
                        source: "FIJI_ACTIVE_SESSION_NEW_ROI"
                    }
                };
            }
            geometry = object.geometry && typeof object.geometry === "object" ?
                jsonClone(object.geometry) : {};
            for (key in live.geometry) {
                if (Object.prototype.hasOwnProperty.call(live.geometry, key)) {
                    geometry[key] = live.geometry[key];
                }
            }
            object.cavity_id = cavityId;
            object.name = String(live.name || cavityId);
            object.properties = String(live.properties || "");
            object.geometry = geometry;
            object.bounds = jsonClone(live.bounds);
            object.center = {
                x: Number(live.geometry.center_x_px),
                y: Number(live.geometry.center_y_px)
            };
            object.diameter_nm = Number(live.geometry.diameter_nm);
            object.roi_bytes_base64 = String(live.roi_bytes_base64);
            object.roi_bytes_sha256 = String(live.roi_bytes_sha256);
            object.roi_bytes = Number(live.roi_bytes);
            merged.push(object);
        }
        for (i = 0; i < priorObjects.length; i += 1) {
            objectUuid = String(priorObjects[i].object_uuid || "").toLowerCase();
            if (seenPrior[objectUuid] !== true) {
                fail("ACTIVE_OBJECT_MISSING_FROM_LIVE_ROI_SNAPSHOT");
            }
        }
        return merged;
    }

    function parseRoiProperties(text) {
        var result = {};
        var lines = String(text || "").split(/\r?\n/);
        var i;
        var match;
        for (i = 0; i < lines.length; i += 1) {
            match = /^([^:=]+)[:=](.*)$/.exec(lines[i]);
            if (match !== null) { result[String(match[1]).replace(/^\s+|\s+$/g, "")] = String(match[2]).replace(/^\s+|\s+$/g, ""); }
        }
        return result;
    }

    function roiProperty(roi, name) {
        var direct;
        var parsed;
        if (roi === null || roi === undefined) { return ""; }
        direct = roi.getProperty(String(name));
        if (direct !== null && direct !== undefined && String(direct) !== "") {
            return String(direct);
        }
        parsed = parseRoiProperties(String(roi.getProperties() || ""));
        return parsed[name] === undefined ? "" : String(parsed[name]);
    }

    function normalizeRoiType(roi) {
        var primary = String(roiProperty(roi, "Type") || "");
        var alias = String(roiProperty(roi, "Object_type") || "");
        function normalized(value) {
            if (value === "analysis_area" || value === "mask") { return "analysis_mask"; }
            if (value === "surface_reference") { return "surface"; }
            return value;
        }
        primary = normalized(primary);
        alias = normalized(alias);
        if (primary !== "" && alias !== "" && primary !== alias) { fail("ROI_TYPE_CONFLICT"); }
        return primary !== "" ? primary : alias;
    }

    function isGeometryType(type) {
        return GEOMETRY_TYPES.indexOf(String(type)) >= 0;
    }

    function geometryIdForRoi(roi, type) {
        var id = "";
        var alias = String(roiProperty(roi, "Object_id") || "");
        if (type === "analysis_mask") { id = roiProperty(roi, "Mask_id"); }
        else if (type === "exclusion") { id = roiProperty(roi, "Exclusion_id"); }
        else if (type === "surface") {
            id = roiProperty(roi, "Surface_id") || roiProperty(roi, "Feature_id") ||
                alias || String(roi.getName() || "SURFACE_REFERENCE");
        }
        if (id !== "" && alias !== "" && id !== alias) { fail("GEOMETRY_ID_ALIAS_CONFLICT"); }
        if (id === "") { id = alias || String(roi.getName() || ""); }
        if (!/^[A-Za-z0-9][A-Za-z0-9._~-]{0,199}$/.test(String(id))) {
            fail("GEOMETRY_ID_INVALID");
        }
        return String(id);
    }

    function geometryUuidForRoi(roi) {
        var primary = String(roiProperty(roi, "Object_uuid") || "").toLowerCase();
        var alias = String(roiProperty(roi, "object_uuid") || "").toLowerCase();
        var uuid;
        if (primary !== "" && alias !== "" && primary !== alias) { fail("GEOMETRY_UUID_ALIAS_CONFLICT"); }
        uuid = primary !== "" ? primary : alias;
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(uuid)) {
            fail("GEOMETRY_UUID_INVALID");
        }
        return uuid;
    }

    function stableRoiIdentity(roi, index) {
        var type = normalizeRoiType(roi);
        var uuid = isGeometryType(type) ? geometryUuidForRoi(roi) :
            String(roiProperty(roi, "Object_uuid") || roiProperty(roi, "object_uuid") || "").toLowerCase();
        var id;
        if (isGeometryType(type)) {
            id = geometryIdForRoi(roi, type);
            return "GEOMETRY|" + type + "|" + uuid + "|" + id;
        }
        if (type === "cavity") {
            id = String(roiProperty(roi, "Cavity_id") || roiProperty(roi, "cavity_id") || "");
            if (id === "") { fail("CAVITY_ID_MISSING"); }
            return "CAVITY|" + uuid + "|" + id;
        }
        return "OTHER|" + String(index) + "|" + type + "|" + String(roi.getName() || "");
    }

    function captureDisplayScope() {
        var imp = state.boundImage;
        var window;
        if (imp === null || imp === undefined || isInspectionView(imp) || imp !== WindowManager.getCurrentImage() ||
                state.activeSessionUid === null ||
                state.activeSession === null || state.projectUid === null) { return null; }
        window = imp.getWindow();
        return {
            project_uid: String(state.projectUid),
            image_uid: String(state.activeSession._image_uid || ""),
            analysis_session_uid: String(state.activeSessionUid),
            generation: Number(state.activeGeneration),
            imageplus_id: Number(imp.getID()),
            window_identity: window === null ? 0 : Number(System.identityHashCode(window)),
            display_epoch: Number(state.displayEpoch)
        };
    }

    function sameDisplayScope(scope) {
        var current = captureDisplayScope();
        return scope !== null && current !== null && state.boundImage === WindowManager.getCurrentImage() &&
            scope.project_uid === current.project_uid && scope.image_uid === current.image_uid &&
            scope.analysis_session_uid === current.analysis_session_uid &&
            scope.generation === current.generation && scope.imageplus_id === current.imageplus_id &&
            scope.window_identity === current.window_identity && scope.display_epoch === current.display_epoch;
    }

    function displayModeFor(type) {
        var mode = String(state.displayModes[type] || DEFAULT_DISPLAY_MODES[type] || "OUTLINE");
        if (DISPLAY_MODES.indexOf(mode) < 0) { fail("DISPLAY_MODE_INVALID"); }
        return mode;
    }

    function styleOverlayClone(roi, type) {
        if (isGeometryType(type)) {
            roi.setFillColor(null);
            roi.setStrokeColor(GEOMETRY_COLORS[type]);
            roi.setStrokeWidth(type === "surface" ? 1.5 : 1.0);
        }
        return roi;
    }

    function clearFilteredOverlay(imp) {
        var canvas;
        if (imp === null || imp === undefined || imp.getWindow() === null) { return; }
        canvas = imp.getCanvas();
        if (canvas === null) { return; }
        canvas.setShowAllList(new Overlay());
        imp.updateAndDraw();
    }

    function rebuildFilteredOverlay(expectedScope) {
        var scope = expectedScope || captureDisplayScope();
        var imp = state.boundImage;
        var manager = RoiManager.getInstance2();
        var overlay = new Overlay();
        var geometry = [];
        var ordinary = [];
        var cavities = [];
        var seen = {};
        var seenGeometryUid = {};
        var seenGeometryId = {};
        var i;
        var roi;
        var activeRoi;
        var activeCavityIdentity = null;
        var clone;
        var type;
        var identity;
        var editIdentity = state.editState === null ? null : state.editState.identity;
        var labels;
        if (!sameDisplayScope(scope) || imp === null || manager === null || imp.getCanvas() === null) { return false; }
        activeRoi = imp.getRoi();
        if (activeRoi !== null && state.editState === null) {
            type = normalizeRoiType(activeRoi);
            if (isGeometryType(type)) {
                imp.killRoi();
                activeRoi = null;
            } else if (type === "cavity") {
                activeCavityIdentity = stableRoiIdentity(activeRoi, -1);
            }
        }
        for (i = 0; i < Number(manager.getCount()); i += 1) {
            roi = manager.getRoi(i);
            if (roi === null) { continue; }
            type = normalizeRoiType(roi);
            if (type === "session_metadata") { continue; }
            identity = stableRoiIdentity(roi, i);
            if (seen[identity] === true) { fail("FILTERED_OVERLAY_IDENTITY_DUPLICATE"); }
            seen[identity] = true;
            if (isGeometryType(type)) {
                if (seenGeometryUid[geometryUuidForRoi(roi)] ||
                        seenGeometryId[geometryIdForRoi(roi, type)]) {
                    fail("FILTERED_OVERLAY_GEOMETRY_IDENTITY_COLLISION");
                }
                seenGeometryUid[geometryUuidForRoi(roi)] = true;
                seenGeometryId[geometryIdForRoi(roi, type)] = true;
            }
            if (identity === editIdentity) { continue; }
            if (isGeometryType(type)) {
                if (!state.temporaryReveal && displayModeFor(type) === "HIDDEN") { continue; }
                clone = styleOverlayClone(roi.clone(), type);
                geometry.push(clone);
            } else if (type === "cavity") {
                if (identity === activeCavityIdentity) { continue; }
                cavities.push(roi.clone());
            } else {
                ordinary.push(roi.clone());
            }
        }
        for (i = 0; i < geometry.length; i += 1) { overlay.add(geometry[i]); }
        for (i = 0; i < ordinary.length; i += 1) { overlay.add(ordinary[i]); }
        for (i = 0; i < cavities.length; i += 1) { overlay.add(cavities[i]); }
        labels = String(imp.getProperty("CavityLightExactLabelsEnabled") || "1") !== "0";
        try { overlay.drawLabels(labels); } catch (ignoredLabels) {}
        try { overlay.drawNames(labels); } catch (ignoredNames) {}
        try { overlay.setSelectable(false); } catch (ignoredSelectable) {}
        try { overlay.setDraggable(false); } catch (ignoredDraggable) {}
        if (!sameDisplayScope(scope)) { return false; }
        imp.getCanvas().setShowAllList(overlay);
        imp.updateAndDraw();
        return true;
    }

    function stopTemporaryReveal(rebuild) {
        var wasVisible = state.temporaryReveal;
        state.temporaryRevealToken += 1;
        if (state.temporaryRevealTimer !== null) {
            state.temporaryRevealTimer.stop();
            state.temporaryRevealTimer = null;
        }
        state.temporaryReveal = false;
        if (rebuild && wasVisible) { rebuildFilteredOverlay(); }
    }

    function showEverythingTemporarily() {
        var scope = captureDisplayScope();
        var token;
        if (scope === null || state.editState !== null) {
            statusLabel.setText("Active una sesión editable y salga de EDIT antes de la vista temporal.");
            return;
        }
        stopTemporaryReveal(false);
        token = state.temporaryRevealToken;
        state.temporaryReveal = true;
        rebuildFilteredOverlay(scope);
        // El timer restaura el overlay con rebuildFilteredOverlay solo si conserva exactamente el scope.
        state.temporaryRevealTimer = new Timer(TEMPORARY_REVEAL_MS,
            new JavaAdapter(ActionListener, {actionPerformed: function () {
                if (token !== state.temporaryRevealToken) { return; }
                state.temporaryRevealTimer = null;
                if (!sameDisplayScope(scope)) {
                    state.temporaryReveal = false;
                    refreshDisplayControls();
                    return;
                }
                state.temporaryReveal = false;
                rebuildFilteredOverlay(scope);
                refreshDisplayControls();
            }}));
        state.temporaryRevealTimer.setRepeats(false);
        state.temporaryRevealTimer.start();
        statusLabel.setText("Todas las geometrías visibles durante 3 segundos (sin cambiar preferencias).");
        refreshDisplayControls();
    }

    function removeCavityClickListener() {
        var binding = state.cavityClickBinding;
        if (binding !== null) {
            try { binding.canvas.removeMouseListener(binding.listener); } catch (ignoredRemove) {}
        }
        state.cavityClickBinding = null;
    }

    function installCavityClickListener() {
        var scope = captureDisplayScope();
        var imp = state.boundImage;
        var canvas;
        var listener;
        removeCavityClickListener();
        if (scope === null || imp === null || imp.getWindow() === null) { return; }
        canvas = imp.getCanvas();
        if (canvas === null) { return; }
        listener = new JavaAdapter(MouseAdapter, {mouseClicked: function (event) {
            var manager;
            var x;
            var y;
            var i;
            var roi;
            var bounds;
            var dx;
            var dy;
            var distance;
            var bestDistance = Number.POSITIVE_INFINITY;
            var best = -1;
            var toolName = String(Toolbar.getToolName() || "").toLowerCase();
            if (event.getButton() !== MouseEvent.BUTTON1 || state.editState !== null ||
                    !sameDisplayScope(scope)) { return; }
            if (toolName.indexOf("cavity") < 0 && toolName.indexOf("select") < 0 &&
                    toolName.indexOf("hand") < 0) { return; }
            manager = RoiManager.getInstance2();
            if (manager === null) { return; }
            x = Number(canvas.offScreenX(event.getX()));
            y = Number(canvas.offScreenY(event.getY()));
            for (i = 0; i < Number(manager.getCount()); i += 1) {
                roi = manager.getRoi(i);
                if (roi === null || normalizeRoiType(roi) !== "cavity" ||
                        !roi.contains(Math.round(x), Math.round(y))) { continue; }
                bounds = roi.getFloatBounds();
                dx = x - (Number(bounds.x) + Number(bounds.width) / 2);
                dy = y - (Number(bounds.y) + Number(bounds.height) / 2);
                distance = dx * dx + dy * dy;
                if (distance < bestDistance) { bestDistance = distance; best = i; }
            }
            if (best >= 0 && sameDisplayScope(scope)) {
                try { manager.select(imp, best); } catch (selectError) { manager.select(best); }
                imp.setRoi(manager.getRoi(best));
                statusLabel.setText("Cavidad seleccionada: " + String(manager.getName(best) || (best + 1)));
            }
            // Reclaims the working canvas if a legacy macro issued ROI Manager Show All.
            if (sameDisplayScope(scope)) { rebuildFilteredOverlay(scope); }
        }});
        canvas.addMouseListener(listener);
        state.cavityClickBinding = {canvas: canvas, listener: listener, scope: scope};
    }

    function verifiedActiveSourceSha(imp) {
        requireOriginalImage(imp);
        var expected = state.activeSession === null ? "" :
            String(state.activeSession.source_sha256 || "");
        var declared = [
            String(imp.getProperty("CTL.P1.source_sha256_actual") || ""),
            String(imp.getProperty("CTL.P1.source_sha256") || "")
        ];
        var i;
        var nonempty = [];
        var info;
        var sourceFile;
        var fileBound = false;
        if (!/^[0-9a-f]{64}$/.test(expected)) { fail("ACTIVE_SESSION_SOURCE_SHA256_INVALID"); }
        for (i = 0; i < declared.length; i += 1) {
            if (declared[i] !== "") {
                if (declared[i] !== expected) { fail("ACTIVE_IMAGE_SOURCE_PROPERTY_MISMATCH"); }
                nonempty.push(declared[i]);
            }
        }
        info = imp.getOriginalFileInfo();
        if (info !== null && info.directory !== null && info.fileName !== null) {
            sourceFile = new File(String(info.directory), String(info.fileName)).getCanonicalFile();
            if (isPlainFile(sourceFile)) {
                if (sha256File(sourceFile) !== expected) { fail("ACTIVE_IMAGE_SOURCE_FILE_MISMATCH"); }
                fileBound = true;
            }
        }
        if (nonempty.length === 0 && !fileBound) { fail("ACTIVE_IMAGE_SOURCE_NOT_VERIFIABLE"); }
        imp.setProperty("CTL.P1.source_sha256", expected);
        imp.setProperty("CTL.P1.source_sha256_actual", expected);
        return expected;
    }

    function currentImageContext(operatorId, featureBinNm) {
        var imp = state.boundImage;
        var spatial;
        if (imp === null || imp !== WindowManager.getCurrentImage()) { fail("NO_BOUND_ACTIVE_IMAGE"); }
        requireOriginalImage(imp);
        verifiedActiveSourceSha(imp);
        spatial = normalizedSpatialCalibration(imp);
        return {
            width_px: Number(imp.getWidth()),
            height_px: Number(imp.getHeight()),
            bit_depth: Number(imp.getBitDepth()),
            raw_pixel_width: spatial.raw_pixel_width,
            raw_pixel_height: spatial.raw_pixel_height,
            raw_x_unit: spatial.raw_x_unit,
            raw_y_unit: spatial.raw_y_unit,
            default_unit: spatial.default_unit,
            factor_x_to_nm: spatial.factor_x_to_nm,
            factor_y_to_nm: spatial.factor_y_to_nm,
            scale_x_nm_px: spatial.scale_x_nm_px,
            scale_y_nm_px: spatial.scale_y_nm_px,
            normalization_rule_id: spatial.normalization_rule_id,
            fiji_imagej_version: String(IJ.getVersion()),
            decoder_opening_method: IMAGE_DECODER_OPENING_METHOD,
            operator_id: String(operatorId),
            feature_distance_bin_nm: String(featureBinNm),
            histogram_bin_nm: String(featureBinNm),
            use_whole_image: 1,
            image_mode: "without_surface",
            thickness_status: "NOT_APPLICABLE",
            depth_policy: {
                exclude_negative_depth: false,
                material_side: "NOT_APPLICABLE",
                mode: "NONE"
            },
            scale_method: "FIJI_CALIBRATION_UNIT_NORMALIZED_CLOSED_V1",
            master_pixel_evidence: computeMasterPixelEvidence(imp)
        };
    }

    function verifiedObjectIdentity(object, index) {
        var legacy = object.legacy_properties;
        var keys;
        var i;
        var key;
        var value;
        var cavityId = String(object.cavity_id || "");
        var objectUuid = String(object.object_uuid || "");
        if (legacy !== undefined && (legacy === null || typeof legacy !== "object" || Array.isArray(legacy))) {
            fail("LEGACY_PROPERTIES_NOT_OBJECT");
        }
        if (legacy !== undefined) {
            keys = Object.keys(legacy).sort();
            for (i = 0; i < keys.length; i += 1) {
                key = String(keys[i]);
                value = legacy[key];
                if (key === "" || /[\r\n\u0000:=]/.test(key) || value === null ||
                        (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean")) {
                    fail("LEGACY_PROPERTY_NOT_ROI_SCALAR");
                }
            }
        }
        if (!/^CAV_[0-9]{6}$/.test(cavityId)) { fail("MIGRATED_CAVITY_ID_INVALID"); }
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(objectUuid)) {
            fail("MIGRATED_OBJECT_UUID_INVALID");
        }
        return {
            cavityId: cavityId,
            legacy: legacy,
            name: String(object.name || cavityId || ("CAV_" + ("000000" + (index + 1)).slice(-6))),
            objectUuid: objectUuid.toLowerCase()
        };
    }

    function validateVerifiedObjectProperties(roi, object, index, acceptedObjectUuid) {
        var identity = verifiedObjectIdentity(object, index);
        var observedType = normalizeRoiType(roi);
        var observedCavityId = String(roiProperty(roi, "Cavity_id") ||
            roiProperty(roi, "cavity_id") || "");
        var observedObjectUuid = String(roiProperty(roi, "Object_uuid") ||
            roiProperty(roi, "object_uuid") || "").toLowerCase();
        var observedName = String(roi.getName() || "");
        var protectedKeys = {
            Type: true, Object_type: true,
            Cavity_id: true, cavity_id: true,
            Object_uuid: true, object_uuid: true
        };
        var keys;
        var i;
        var key;
        var requiredObjectUuid = acceptedObjectUuid === undefined ? identity.objectUuid :
            String(acceptedObjectUuid || "").toLowerCase();
        if (observedType !== "cavity" || observedCavityId !== identity.cavityId ||
                observedObjectUuid !== requiredObjectUuid || observedName !== identity.name) {
            fail("IMMUTABLE_ROI_OBJECT_IDENTITY_MISMATCH");
        }
        if (identity.legacy !== undefined) {
            keys = Object.keys(identity.legacy).sort();
            for (i = 0; i < keys.length; i += 1) {
                key = String(keys[i]);
                if (protectedKeys[key] !== true &&
                        String(roiProperty(roi, key) || "") !== String(identity.legacy[key])) {
                    fail("IMMUTABLE_ROI_LEGACY_PROPERTY_MISMATCH");
                }
            }
        }
    }

    function normalizedCloneRoiIdentityBridge(value, sessionUid) {
        var mappings;
        var seenSource = {};
        var seenDestination = {};
        var i;
        var mapping;
        var source;
        var destination;
        var cavityId;
        var roiSha;
        if (value === null || value === undefined) { return null; }
        if (String(value.schema || "") !== "CTL_P3_CLONE_ROI_IDENTITY_BRIDGE_V1" ||
                String(value.analysis_session_uid || "").toLowerCase() !== String(sessionUid || "").toLowerCase() ||
                !Array.isArray(value.mappings) ||
                !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value.source_revision_uid || "")) ||
                !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value.destination_genesis_revision_uid || ""))) {
            fail("CLONE_ROI_IDENTITY_BRIDGE_INVALID");
        }
        mappings = [];
        for (i = 0; i < value.mappings.length; i += 1) {
            mapping = value.mappings[i] || {};
            source = String(mapping.source_object_uuid || "").toLowerCase();
            destination = String(mapping.destination_object_uuid || "").toLowerCase();
            cavityId = String(mapping.cavity_id || "");
            roiSha = String(mapping.source_roi_bytes_sha256 || "");
            if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(source) ||
                    !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(destination) ||
                    source === destination || !/^CAV_[0-9]{6}$/.test(cavityId) ||
                    !/^[0-9a-f]{64}$/.test(roiSha) || seenSource[source] || seenDestination[destination]) {
                fail("CLONE_ROI_IDENTITY_BRIDGE_MAPPING_INVALID");
            }
            seenSource[source] = true;
            seenDestination[destination] = true;
            mappings.push({
                cavity_id: cavityId,
                destination_object_uuid: destination,
                source_object_uuid: source,
                source_roi_bytes_sha256: roiSha
            });
        }
        return {
            analysis_session_uid: String(value.analysis_session_uid).toLowerCase(),
            destination_genesis_revision_uid: String(value.destination_genesis_revision_uid).toLowerCase(),
            mappings: mappings,
            schema: "CTL_P3_CLONE_ROI_IDENTITY_BRIDGE_V1",
            source_revision_uid: String(value.source_revision_uid).toLowerCase()
        };
    }

    function cloneRoiIdentityMapping(bridge, object, index, observedObjectUuid, expectedSha) {
        var identity = verifiedObjectIdentity(object, index);
        var mappings;
        var i;
        var mapping;
        if (bridge === null) { fail("IMMUTABLE_ROI_OBJECT_IDENTITY_MISMATCH"); }
        mappings = bridge.mappings;
        for (i = 0; i < mappings.length; i += 1) {
            mapping = mappings[i];
            if (mapping.destination_object_uuid === identity.objectUuid) {
                if (mapping.cavity_id !== identity.cavityId ||
                        mapping.source_object_uuid !== String(observedObjectUuid || "").toLowerCase() ||
                        mapping.source_roi_bytes_sha256 !== expectedSha) {
                    fail("CLONE_ROI_IDENTITY_BRIDGE_SCOPE_MISMATCH");
                }
                return mapping;
            }
        }
        fail("IMMUTABLE_ROI_OBJECT_IDENTITY_MISMATCH");
    }

    function applyVerifiedObjectProperties(roi, object, index) {
        var identity = verifiedObjectIdentity(object, index);
        var legacy = identity.legacy;
        var keys;
        var i;
        var key;
        var value;
        var observedType;
        if (legacy !== undefined) {
            keys = Object.keys(legacy).sort();
            for (i = 0; i < keys.length; i += 1) {
                key = String(keys[i]);
                value = legacy[key];
                roi.setProperty(key, String(value));
            }
        }
        observedType = String(roi.getProperty("Type") || roi.getProperty("Object_type") || "");
        if (observedType !== "" && observedType !== "cavity") { fail("MIGRATED_OBJECT_TYPE_INVALID"); }
        roi.setProperty("Type", "cavity");
        roi.setProperty("Cavity_id", identity.cavityId);
        roi.setProperty("Object_uuid", identity.objectUuid);
        roi.setName(identity.name);
    }

    function loadObjectsIntoRoiManager(objects, cloneIdentityBridge) {
        var manager = RoiManager.getInstance2();
        var i;
        var object;
        var encoded;
        var expectedSha;
        var bytes;
        var roi;
        var geometry;
        var spatial;
        var scaleX;
        var scaleY;
        var width;
        var height;
        var centerX;
        var centerY;
        var loadedRoi;
        var immutablePayload;
        var immutableLoadedSha;
        var observedObjectUuid;
        var identity;
        var cloneMapping;
        if (!Array.isArray(objects)) { fail("ROI_OBJECTS_NOT_ARRAY"); }
        if (manager === null) { manager = new RoiManager(); }
        manager.reset();
        for (i = 0; i < objects.length; i += 1) {
            object = objects[i] || {};
            immutablePayload = false;
            immutableLoadedSha = null;
            encoded = String(object.roi_bytes_base64 || object.serialized_roi_base64 ||
                (object.fiji_roi && object.fiji_roi.roi_bytes_base64) || "");
            expectedSha = String(object.roi_bytes_sha256 ||
                (object.fiji_roi && object.fiji_roi.roi_bytes_sha256) || "");
            if (encoded !== "") {
                if (!/^[0-9a-f]{64}$/.test(expectedSha)) { fail("ROI_PAYLOAD_INVALID"); }
                bytes = Base64.getDecoder().decode(encoded);
                if (sha256Bytes(bytes) !== expectedSha) { fail("ROI_PAYLOAD_HASH_MISMATCH"); }
                roi = new RoiDecoder(bytes, String(object.name || "roi-" + i)).getRoi();
                if (roi === null) { fail("ROI_DECODE_FAILED"); }
                identity = verifiedObjectIdentity(object, i);
                observedObjectUuid = String(roiProperty(roi, "Object_uuid") ||
                    roiProperty(roi, "object_uuid") || "").toLowerCase();
                cloneMapping = null;
                if (observedObjectUuid === identity.objectUuid) {
                    validateVerifiedObjectProperties(roi, object, i);
                } else {
                    cloneMapping = cloneRoiIdentityMapping(
                        cloneIdentityBridge, object, i, observedObjectUuid, expectedSha
                    );
                    validateVerifiedObjectProperties(
                        roi, object, i, cloneMapping.source_object_uuid
                    );
                }
                if (sha256Bytes(RoiEncoder.saveAsByteArray(roi)) !== expectedSha) {
                    fail("IMMUTABLE_ROI_PAYLOAD_NOT_ROUNDTRIP_STABLE");
                }
                if (cloneMapping !== null) {
                    applyVerifiedObjectProperties(roi, object, i);
                    validateVerifiedObjectProperties(roi, object, i);
                    immutableLoadedSha = sha256Bytes(RoiEncoder.saveAsByteArray(roi));
                } else {
                    immutableLoadedSha = expectedSha;
                }
                immutablePayload = true;
            } else {
                geometry = object.geometry || object;
                spatial = normalizedSpatialCalibration(WindowManager.getCurrentImage());
                scaleX = spatial.scale_x_nm_px;
                scaleY = spatial.scale_y_nm_px;
                centerX = Number(geometry.center_x_px);
                centerY = Number(geometry.center_y_px);
                if ((geometry.width_px === undefined || geometry.height_px === undefined) &&
                        !spatialScalesAgree(scaleX, scaleY)) {
                    requireCircleAnisotropyProtocol(object, null);
                }
                width = geometry.width_px === undefined ? Number(geometry.diameter_nm) / scaleX : Number(geometry.width_px);
                height = geometry.height_px === undefined ? Number(geometry.diameter_nm) / scaleY : Number(geometry.height_px);
                if (!isFinite(centerX) || !isFinite(centerY) || !isFinite(width) || !isFinite(height) ||
                        width <= 0 || height <= 0) { fail("ROI_GEOMETRY_INVALID"); }
                roi = new OvalRoi(centerX - width / 2, centerY - height / 2, width, height);
                applyVerifiedObjectProperties(roi, object, i);
            }
            manager.addRoi(roi);
            if (immutablePayload) {
                loadedRoi = manager.getRoi(Number(manager.getCount()) - 1);
                if (loadedRoi === null) { fail("IMMUTABLE_ROI_PAYLOAD_MISSING_AFTER_LOAD"); }
                validateVerifiedObjectProperties(loadedRoi, object, i);
                if (sha256Bytes(RoiEncoder.saveAsByteArray(loadedRoi)) !== immutableLoadedSha) {
                    fail("IMMUTABLE_ROI_PAYLOAD_MUTATED_ON_MANAGER_LOAD");
                }
            }
        }
        try { manager.runCommand("Show None"); } catch (ignoredShowNone) {}
    }

    function loadGeometriesIntoRoiManager(geometries) {
        var manager = RoiManager.getInstance2();
        var seenUid = {};
        var seenId = {};
        var i;
        var geometry;
        var encoded;
        var bytes;
        var expectedSha;
        var roi;
        var type;
        var observedUid;
        var observedId;
        var loadedRoi;
        if (!Array.isArray(geometries)) { fail("GEOMETRY_STATE_NOT_ARRAY"); }
        if (manager === null) { manager = new RoiManager(); }
        for (i = 0; i < geometries.length; i += 1) {
            geometry = geometries[i] || {};
            type = String(geometry.geometry_type || "");
            if (!isGeometryType(type)) { fail("GEOMETRY_STATE_TYPE_INVALID"); }
            encoded = String(geometry.roi_bytes_base64 || "");
            expectedSha = String(geometry.roi_bytes_sha256 || "");
            if (encoded === "" || !/^[0-9a-f]{64}$/.test(expectedSha)) { fail("GEOMETRY_ROI_PAYLOAD_INVALID"); }
            bytes = Base64.getDecoder().decode(encoded);
            if (sha256Bytes(bytes) !== expectedSha || String(geometry.source_roi_sha256 || "") !== expectedSha) {
                fail("GEOMETRY_ROI_PAYLOAD_HASH_MISMATCH");
            }
            roi = new RoiDecoder(bytes, String((geometry.labels || {}).name || geometry.geometry_id || "geometry")).getRoi();
            if (roi === null || normalizeRoiType(roi) !== type) { fail("GEOMETRY_ROI_TYPE_MISMATCH"); }
            if (sha256Bytes(RoiEncoder.saveAsByteArray(roi)) !== expectedSha) {
                fail("IMMUTABLE_GEOMETRY_ROI_PAYLOAD_NOT_ROUNDTRIP_STABLE");
            }
            observedUid = geometryUuidForRoi(roi);
            observedId = geometryIdForRoi(roi, type);
            if (observedUid !== String(geometry.geometry_uid || "").toLowerCase() ||
                    observedId !== String(geometry.geometry_id || "") || seenUid[observedUid] || seenId[observedId]) {
                fail("GEOMETRY_ROI_IDENTITY_MISMATCH_OR_DUPLICATE");
            }
            seenUid[observedUid] = true;
            seenId[observedId] = true;
            manager.addRoi(roi);
            loadedRoi = manager.getRoi(Number(manager.getCount()) - 1);
            if (loadedRoi === null) { fail("IMMUTABLE_GEOMETRY_ROI_PAYLOAD_MISSING_AFTER_LOAD"); }
            if (sha256Bytes(RoiEncoder.saveAsByteArray(loadedRoi)) !== expectedSha) {
                fail("IMMUTABLE_GEOMETRY_ROI_PAYLOAD_MUTATED_ON_MANAGER_LOAD");
            }
        }
        try { manager.runCommand("Show None"); } catch (ignoredShowNone) {}
    }

    function applyGeometryState(geometryState) {
        var preferences;
        var modes;
        var binding;
        if (geometryState === null || geometryState === undefined) {
            state.activeGeometries = [];
            state.geometryState = null;
            state.displayModes = jsonClone(DEFAULT_DISPLAY_MODES);
            state.displayPreferencesSha256 = "NOT_APPLICABLE";
            state.editFillAlpha = 72;
            return;
        }
        if (!Array.isArray(geometryState.geometries)) { fail("GEOMETRY_STATE_INVENTORY_INVALID"); }
        binding = geometryState.revision_binding || {};
        if (state.activeSession !== null && String(binding.revision_pointer_sha256 || "") !==
                String(state.activeSession.current_revision_pointer_sha256 || "")) {
            fail("GEOMETRY_STATE_REVISION_SCOPE_MISMATCH");
        }
        preferences = geometryState.preferences || {};
        modes = preferences.modes || {};
        if (GEOMETRY_TYPES.some(function (type) {
                return DISPLAY_MODES.indexOf(String(modes[type] || "")) < 0;
            })) { fail("GEOMETRY_DISPLAY_PREFERENCES_INVALID"); }
        state.activeGeometries = jsonClone(geometryState.geometries);
        state.geometryState = jsonClone(geometryState);
        state.displayModes = {
            analysis_mask: String(modes.analysis_mask),
            exclusion: String(modes.exclusion),
            surface: String(modes.surface)
        };
        state.displayPreferencesSha256 = String(geometryState.preferences_sha256 || "NOT_APPLICABLE");
        state.editFillAlpha = Number(preferences.edit_fill_alpha === undefined ? 72 : preferences.edit_fill_alpha);
        if (!isFinite(state.editFillAlpha) || state.editFillAlpha < 0 || state.editFillAlpha > 160) {
            fail("GEOMETRY_EDIT_ALPHA_INVALID");
        }
        loadGeometriesIntoRoiManager(state.activeGeometries);
    }

    function roiBytesSha256(roi) {
        return sha256Bytes(RoiEncoder.saveAsByteArray(roi));
    }

    function suspendPrompt1ForEdit(imp) {
        var runtime = IJ.getProperty("CTL.P1.Runtime");
        if (runtime === null || runtime === undefined) { return null; }
        try {
            if (runtime.teardown(imp) !== true) { fail("P1_RUNTIME_TEARDOWN_REFUSED_EDIT"); }
        } catch (error) {
            fail("P1_RUNTIME_TEARDOWN_FAILED: " + error);
        }
        return runtime;
    }

    function restorePrompt1AfterEdit(edit) {
        if (edit === null || edit.p1Runtime === null || edit.p1Runtime === undefined) { return; }
        try {
            if (edit.p1Runtime.install(edit.imp) === false) {
                IJ.log("CTL Prompt3 Masks: P1 runtime no pudo reinstalarse tras EDIT.");
            }
        } catch (error) {
            IJ.log("CTL Prompt3 Masks: error al reinstalar P1 tras EDIT: " + error);
        }
    }

    function beginGeometryEdit() {
        var scope = captureDisplayScope();
        var imp = state.boundImage;
        var manager = RoiManager.getInstance2();
        var index;
        var original;
        var type;
        var identity;
        var active;
        var color;
        var editAlpha;
        var editRgba;
        var runtime;
        if (scope === null || manager === null || imp === null || state.editState !== null) {
            statusLabel.setText("Active una sesión y seleccione una geometría del ROI Manager.");
            return;
        }
        index = Number(manager.getSelectedIndex());
        if (index < 0 || index >= Number(manager.getCount())) {
            statusLabel.setText("Seleccione explícitamente una máscara, exclusión o superficie en ROI Manager.");
            return;
        }
        original = manager.getRoi(index);
        type = normalizeRoiType(original);
        if (!isGeometryType(type)) {
            statusLabel.setText("La ROI seleccionada no es una geometría científica editable de Prompt 3.");
            return;
        }
        identity = stableRoiIdentity(original, index);
        stopTemporaryReveal(false);
        try { runtime = suspendPrompt1ForEdit(imp); } catch (error) { showError(error); return; }
        active = original.clone();
        color = GEOMETRY_COLORS[type];
        active.setStrokeColor(color);
        active.setStrokeWidth(type === "surface" ? 2.0 : 1.5);
        editAlpha = Math.round(Number(state.editFillAlpha));
        editRgba = ((editAlpha & 0xff) << 24) |
            ((color.getRed() & 0xff) << 16) |
            ((color.getGreen() & 0xff) << 8) |
            (color.getBlue() & 0xff);
        // Color(int, boolean) tiene aridad inequívoca en Nashorn; la variante
        // de cuatro números es ambigua entre sus sobrecargas int y float.
        active.setFillColor(new Color(editRgba, true));
        state.editState = {
            scope: scope,
            imp: imp,
            manager: manager,
            index: index,
            type: type,
            identity: identity,
            original: original.clone(),
            original_sha256: roiBytesSha256(original),
            prior_mode: displayModeFor(type),
            p1Runtime: runtime
        };
        imp.setRoi(active);
        rebuildFilteredOverlay(scope);
        statusLabel.setText("EDIT: ajuste los manejadores y confirme o cancele. La revisión aún no cambia.");
        refreshDisplayControls();
    }

    function finishGeometryEdit(commit, silent) {
        var edit = state.editState;
        var active;
        var committed;
        var current;
        if (edit === null) { return true; }
        if (!sameDisplayScope(edit.scope) || edit.manager !== RoiManager.getInstance2() ||
                edit.imp !== state.boundImage) {
            state.editState = null;
            try { edit.imp.killRoi(); } catch (ignoredStaleRoi) {}
            restorePrompt1AfterEdit(edit);
            if (!silent) { showError("EDIT_SCOPE_STALE: la sesión o imagen cambió; no se aplicó la geometría."); }
            refreshDisplayControls();
            return false;
        }
        current = edit.manager.getRoi(edit.index);
        if (current === null || stableRoiIdentity(current, edit.index) !== edit.identity ||
                roiBytesSha256(current) !== edit.original_sha256) {
            state.editState = null;
            edit.imp.killRoi();
            restorePrompt1AfterEdit(edit);
            rebuildFilteredOverlay(edit.scope);
            if (!silent) { showError("EDIT_AUTHORITY_CHANGED: ROI Manager cambió durante EDIT."); }
            refreshDisplayControls();
            return false;
        }
        if (commit) {
            active = edit.imp.getRoi();
            if (active === null || normalizeRoiType(active) !== edit.type ||
                    stableRoiIdentity(active, edit.index) !== edit.identity) {
                if (!silent) { showError("EDIT_ACTIVE_ROI_IDENTITY_MISMATCH"); }
                return false;
            }
            try { recordEditHistory("Cambios en ROI Manager", true); }
            catch (historyError) { if (!silent) { showError(historyError); } return false; }
            committed = active.clone();
            try { committed.copyAttributes(edit.original); } catch (ignoredAttributes) {}
            // setStrokeWidth(0) no limpia scaleStrokeWidth en ImageJ. Restaure
            // ambas partes del atributo para impedir que el resaltado EDIT
            // transitorio entre en los bytes científicos de la revisión.
            if (Boolean(edit.original.getScaleStrokeWidth())) {
                committed.setStrokeWidth(edit.original.getStrokeWidth());
            } else {
                committed.setUnscalableStrokeWidth(edit.original.getStrokeWidth());
            }
            try { committed.setProperties(String(edit.original.getProperties() || "")); } catch (ignoredProperties) {}
            committed.setName(String(edit.original.getName() || ""));
            if (stableRoiIdentity(committed, edit.index) !== edit.identity) { fail("EDIT_COMMIT_IDENTITY_CHANGED"); }
            try {
                edit.manager.setRoi(committed, edit.index);
            } catch (setRoiError) {
                try {
                    edit.manager.select(edit.imp, edit.index);
                    edit.imp.setRoi(committed);
                    if (edit.manager.runCommand(edit.imp, "Update") === false) {
                        fail("EDIT_ROI_MANAGER_UPDATE_REFUSED");
                    }
                } catch (updateError) {
                    if (!silent) { showError("EDIT_ROI_MANAGER_UPDATE_FAILED: " + updateError); }
                    return false;
                }
            }
            state.geometryDirty = state.geometryDirty || roiBytesSha256(committed) !== edit.original_sha256;
        }
        state.editState = null;
        if (commit) {
            try { recordEditHistory("Geometría confirmada", false); }
            catch (historyCaptureError) {
                resetEditHistory();
                state.historyNotice = "Geometría confirmada; historial no disponible. Guarde un borrador. " + historyCaptureError;
            }
        }
        edit.imp.killRoi();
        try { edit.manager.deselect(); } catch (ignoredDeselect) {}
        restorePrompt1AfterEdit(edit);
        rebuildFilteredOverlay(edit.scope);
        if (!silent) {
            statusLabel.setText(commit ?
                "Geometría confirmada localmente; guarde una revisión para hacerla autoridad." :
                "Edición cancelada; ROI Manager y autoridad científica permanecen intactos.");
        }
        refreshDisplayControls();
        return true;
    }

    function persistDisplayMode(type, mode) {
        var scope = captureDisplayScope();
        var active = state.activeSession;
        if (scope === null || active === null || state.editState !== null) {
            statusLabel.setText("Active una sesión y cierre EDIT antes de cambiar la visibilidad.");
            return;
        }
        if ((type !== "all" && !isGeometryType(type)) || DISPLAY_MODES.indexOf(mode) < 0) {
            showError("DISPLAY_MODE_REQUEST_INVALID");
            return;
        }
        stopTemporaryReveal(false);
        invokeOperation("set_display_mode", {
            project_root: state.projectPath,
            image_uid: String(active._image_uid),
            analysis_session_uid: state.activeSessionUid,
            geometry_type: type,
            mode: mode,
            edit_fill_alpha: Number(state.editFillAlpha),
            expected_preferences_sha256: String(state.displayPreferencesSha256)
        }, function (result) {
            var preferences = result.preferences || {};
            var modes = preferences.modes || {};
            if (GEOMETRY_TYPES.some(function (geometryType) {
                    return DISPLAY_MODES.indexOf(String(modes[geometryType] || "")) < 0;
                })) { showError("set_display_mode devolvió preferencias inválidas."); return; }
            state.displayModes = {
                analysis_mask: String(modes.analysis_mask),
                exclusion: String(modes.exclusion),
                surface: String(modes.surface)
            };
            state.displayPreferencesSha256 = String(result.preferences_sha256 || "");
            state.editFillAlpha = Number(preferences.edit_fill_alpha);
            state.displayEpoch += 1;
            rebuildFilteredOverlay();
            installCavityClickListener();
            refreshDisplayControls();
            statusLabel.setText("Preferencia visual guardada; geometría, revisión, RUN y área no cambiaron.");
        });
    }

    function toggleDisplayMode(type) {
        persistDisplayMode(type, displayModeFor(type) === "HIDDEN" ? "OUTLINE" : "HIDDEN");
    }

    function refreshDisplayControls() {
        var active = state.activeSessionUid !== null && state.boundImage !== null;
        var editing = state.editState !== null;
        refreshActiveSessionLabel();
        refreshHistoryControls();
        if (saveDraftButton) {
            saveDraftButton.setEnabled(active && state.draftReady && !editing && !state.busy);
            recoverDraftButton.setEnabled(active && state.draftReady && !editing && !state.busy);
            discardDraftButton.setEnabled(active && state.draftReady && !editing && !state.busy);
        }
        if (maskModeButton) { maskModeButton.setText("Áreas válidas: " + displayModeFor("analysis_mask")); }
        if (exclusionModeButton) { exclusionModeButton.setText("Exclusiones: " + displayModeFor("exclusion")); }
        if (surfaceModeButton) { surfaceModeButton.setText("Superficie: " + displayModeFor("surface")); }
        if (maskModeButton) { maskModeButton.setEnabled(active && !state.busy && !editing); }
        if (exclusionModeButton) { exclusionModeButton.setEnabled(active && !state.busy && !editing); }
        if (surfaceModeButton) { surfaceModeButton.setEnabled(active && !state.busy && !editing); }
        if (editButton) { editButton.setEnabled(active && !state.busy && !editing); }
        if (confirmEditButton) { confirmEditButton.setEnabled(active && !state.busy && editing); }
        if (cancelEditButton) { cancelEditButton.setEnabled(active && !state.busy && editing); }
        if (temporaryRevealButton) { temporaryRevealButton.setEnabled(active && !state.busy && !editing); }
        if (restoreOutlineButton) { restoreOutlineButton.setEnabled(active && !state.busy && !editing); }
    }

    function onEdt(callback) {
        SwingUtilities.invokeLater(new JavaAdapter(Runnable, {run: callback}));
    }

    function setBusy(busy, text) {
        var i;
        state.busy = busy;
        refreshButton.setEnabled(!busy);
        for (i = 0; i < actionButtons.length; i += 1) { actionButtons[i].setEnabled(!busy); }
        statusLabel.setText(String(text || (busy ? "Procesando..." : "Listo")));
        refreshDisplayControls();
    }

    function showError(error) {
        var text = String(error && error.message ? error.message : error);
        IJ.log("CTL Prompt3 Masks ERROR: " + text);
        JOptionPane.showMessageDialog(frame, text, "Prompt 3 Masks", JOptionPane.ERROR_MESSAGE);
    }

    function operationDurationText(milliseconds) {
        var seconds = Math.max(0, Math.floor(Number(milliseconds) / 1000));
        if (seconds < 60) { return seconds + " s"; }
        return Math.floor(seconds / 60) + " min " + (seconds % 60) + " s";
    }

    function stopOperationProgress() {
        if (state.operationProgressTimer !== null) {
            state.operationProgressTimer.stop();
            state.operationProgressTimer = null;
        }
    }

    function startOperationProgress(operation, startedAt) {
        var label = OPERATION_LABELS[operation] || "Procesando la solicitud";
        var update = function () {
            if (state.disposed || !state.busy) { stopOperationProgress(); return; }
            statusLabel.setText(label + " · " +
                operationDurationText((Number(System.nanoTime()) - startedAt) / 1000000) +
                " transcurridos. Espere a que termine la verificación.");
        };
        stopOperationProgress();
        // Swing Timer only updates labels on the EDT; all bridge I/O stays in the worker.
        state.operationProgressTimer = new Timer(1000,
            new JavaAdapter(ActionListener, {actionPerformed: update}));
        update();
        state.operationProgressTimer.start();
    }

    function finishOperationProgress(operation, startedAt, outcome) {
        var elapsedMs = Math.max(0,
            Math.round((Number(System.nanoTime()) - startedAt) / 1000000));
        var label = OPERATION_LABELS[operation] || "Operación";
        stopOperationProgress();
        operationTimingLabel.setText("Última operación: " + label + " · " +
            operationDurationText(elapsedMs) +
            (outcome === "PASS" ? "" : outcome === "STALE" ? " · respuesta descartada" :
                outcome === "CANCELLED" ? " · cancelada" : " · con error"));
        // Operational timing only: excludes the callback's ROI rendering or any chained operation.
        if (IJ.debugMode) {
            IJ.log("CTL_P4_OPERATION_TIMING " + JSON.stringify({
                schema: "CTL_P4_OPERATION_TIMING_V1", operation: String(operation),
                elapsed_ms: elapsedMs, outcome: String(outcome),
                scope: "BRIDGE_ROUND_TRIP_BEFORE_UI_CALLBACK"
            }));
        }
    }

    function invokeOperation(operation, argumentsObject, callback, binding, failure) {
        var captured = binding || {
            session_uid: state.activeSessionUid,
            generation: state.activeGeneration,
            epoch: state.callbackEpoch
        };
        var startedAt;
        if (state.busy) { return; }
        if (isInspectionView(WindowManager.getCurrentImage())) {
            showError("Vista de inspección activa. Use Volver al original antes de operar sobre el proyecto o la sesión.");
            return;
        }
        startedAt = Number(System.nanoTime());
        setBusy(true, OPERATION_LABELS[operation] || "Procesando la solicitud...");
        startOperationProgress(operation, startedAt);
        new Thread(new JavaAdapter(Runnable, {
            run: function () {
                var response;
                var error;
                try { response = invokeCli(operation, argumentsObject); } catch (caught) { error = caught; }
                onEdt(function () {
                    if (state.disposed) { return; }
                    setBusy(false, "Listo");
                    if (error) {
                        finishOperationProgress(operation, startedAt, "ERROR");
                        statusLabel.setText("La operación no se completó. Revise el mensaje de error.");
                        if (failure) { failure(error); return; }
                        showError(error);
                        return;
                    }
                    if (captured.epoch !== state.callbackEpoch ||
                            captured.session_uid !== state.activeSessionUid ||
                            captured.generation !== state.activeGeneration) {
                        finishOperationProgress(operation, startedAt, "STALE");
                        IJ.log("CTL Prompt3 Masks: respuesta obsoleta descartada para " + operation);
                        return;
                    }
                    finishOperationProgress(operation, startedAt, String(response.status));
                    callback(response.result || {}, response);
                });
            }
        }), "CTL-P3-Masks-CLI").start();
    }

    function selectedSession() {
        var viewRow = Number(table.getSelectedRow());
        var modelRow;
        if (viewRow < 0) {
            JOptionPane.showMessageDialog(frame, "Seleccione explícitamente una sesión.",
                "Prompt 3 Masks", JOptionPane.WARNING_MESSAGE);
            return null;
        }
        modelRow = Number(table.convertRowIndexToModel(viewRow));
        if (modelRow < 0 || modelRow >= state.sessions.length) { fail("SESSION_SELECTION_INVALID"); }
        return state.sessions[modelRow];
    }

    function promptText(label, initial) {
        var value = JOptionPane.showInputDialog(frame, label, String(initial || ""));
        if (value === null) { return null; }
        value = String(value).replace(/^\s+|\s+$/g, "");
        return value === "" ? null : value;
    }

    function chooseDirectory(title) {
        var chooser = new JFileChooser();
        chooser.setDialogTitle(title);
        chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY);
        chooser.setMultiSelectionEnabled(false);
        if (chooser.showOpenDialog(frame) !== JFileChooser.APPROVE_OPTION) { return null; }
        return String(chooser.getSelectedFile().getCanonicalPath());
    }

    function chooseOpenFile(title) {
        var chooser = new JFileChooser();
        chooser.setDialogTitle(title);
        chooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
        if (chooser.showOpenDialog(frame) !== JFileChooser.APPROVE_OPTION) { return null; }
        return String(chooser.getSelectedFile().getCanonicalPath());
    }

    function chooseNewDirectory(title, suggestedLeaf, requireExactLeaf) {
        var parent = chooseDirectory(title + " - seleccione la carpeta padre");
        var leaf;
        var target;
        if (parent === null) { return null; }
        leaf = promptText("Nombre de la carpeta nueva:", suggestedLeaf);
        if (leaf === null) { return null; }
        if (requireExactLeaf && String(leaf) !== String(suggestedLeaf)) {
            showError("La carpeta de restauración debe conservar el nombre de sesión contractual.");
            return null;
        }
        if (!/^[A-Za-z0-9][A-Za-z0-9._~-]{0,199}$/.test(leaf)) {
            showError("Nombre de carpeta destino no portable.");
            return null;
        }
        target = new File(new File(parent).getCanonicalFile(), leaf).getCanonicalFile();
        if (!target.getParentFile().equals(new File(parent).getCanonicalFile()) || target.exists()) {
            showError("El destino debe ser un hijo directo nuevo y ausente.");
            return null;
        }
        return String(target.getCanonicalPath());
    }

    function onboardingId(value, label) {
        var text = String(value || "").replace(/^\s+|\s+$/g, "");
        if (!/^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/.test(text)) {
            fail(label + ": use de 1 a 128 letras sin acentos, números, puntos, guiones o guiones bajos.");
        }
        return text;
    }

    function onboardingGuard() {
        return {epoch: state.callbackEpoch, project: state.projectPath,
            roi: state.activeSessionUid === null ? null : exportAllFijiRois().snapshot_sha256};
    }

    function checkOnboardingGuard(guard) {
        if (state.disposed || guard.epoch !== state.callbackEpoch || guard.project !== state.projectPath ||
                (guard.roi !== null && guard.roi !== exportAllFijiRois().snapshot_sha256)) {
            fail("La sesión o sus anotaciones cambiaron durante la operación. Se conserva el trabajo abierto; actualice el proyecto para continuar.");
        }
    }

    function createProjectFromUi() {
        if (state.busy || state.disposed) { return; }
        if (WindowManager.getCurrentImage() !== null) { requireOriginalImage(WindowManager.getCurrentImage()); }
        resolvePendingChanges(function () {
            var guard = onboardingGuard();
            var destination = chooseNewDirectory("Nuevo proyecto", "Cavity_Proyecto", false);
            var projectId;
            if (destination === null) { return; }
            try { projectId = onboardingId(new File(destination).getName(), "Nombre del proyecto"); }
            catch (error) { showError(error); return; }
            checkOnboardingGuard(guard);
            invokeOperation("p3_create_project", {project_root: destination, project_id: projectId}, function (result) {
                try { checkOnboardingGuard(guard); }
                catch (changed) { showError("El proyecto se creó en " + destination + ". " + changed); return; }
                inspectProject(String(result.project_root), guard);
            });
        });
    }

    function decodeOnboardingSource(path, expected) {
        var source = new File(String(path)).getCanonicalFile();
        var before;
        var images = null;
        var imp;
        var options;
        var spatial;
        var context;
        var evidence;
        var i;
        if (!/\.dm[34]$/i.test(String(source.getName())) || !isPlainFile(source)) {
            fail("Seleccione un archivo TEM DM3 o DM4 existente.");
        }
        before = sha256File(source);
        if (expected && before !== String(expected.source_sha256)) { fail("La copia de la fuente no coincide con el proyecto."); }
        try {
            options = new ImporterOptions();
            options.setId(String(source.getCanonicalPath()));
            options.setQuiet(true); options.setWindowless(true); options.setUpgradeCheck(false);
            options.setVirtual(false); options.setOpenAllSeries(true); options.setGroupFiles(false);
            options.setShowMetadata(false); options.setShowOMEXML(false); options.setShowROIs(false);
            options.setAutoscale(true);
            images = BF.openImagePlus(options);
            if (images === null || Number(images.length) !== 1) {
                fail("Esta versión necesita una imagen única. El archivo contiene varias series; no se ha incorporado.");
            }
            imp = images[0];
            // A global ImageJ calibration belongs to another workflow, not this source.
            imp.setIgnoreGlobalCalibration(true);
            imp.setProperty("CTL.P1.source_sha256", before);
            imp.setProperty("CTL.P1.source_sha256_actual", before);
            evidence = computeMasterPixelEvidence(imp);
            spatial = normalizedSpatialCalibration(imp);
            if (sha256File(source) !== before) { fail("El archivo cambió durante la lectura. No se ha incorporado."); }
            if (expected && (String(expected.master_pixel_hash_status) !== "VERIFIED" ||
                    evidence.sha256 !== String(expected.master_pixel_sha256))) {
                fail("Los píxeles leídos no coinciden con la identidad guardada. La sesión no se abrirá sobre esta imagen.");
            }
            context = jsonClone(spatial);
            context.width_px = Number(imp.getWidth()); context.height_px = Number(imp.getHeight());
            context.bit_depth = Number(imp.getBitDepth()); context.master_pixel_evidence = evidence;
            context.fiji_imagej_version = String(IJ.getVersion());
            context.decoder_opening_method = IMAGE_DECODER_OPENING_METHOD;
            context.scale_method = "OTHER";
            if (expected && expected.initial_image_context) {
                var original = expected.initial_image_context;
                if (Number(original.width_px) !== context.width_px || Number(original.height_px) !== context.height_px ||
                        Number(original.bit_depth) !== context.bit_depth ||
                        !spatialScalesAgree(original.scale_x_nm_px, context.scale_x_nm_px) ||
                        !spatialScalesAgree(original.scale_y_nm_px, context.scale_y_nm_px)) {
                    fail("La escala o las dimensiones actuales difieren de las guardadas al incorporar la imagen.");
                }
            }
            return {image: imp, source_path: String(source.getCanonicalPath()), source_sha256: before,
                source_file_name: String(source.getName()), image_context: context};
        } catch (error) {
            if (images !== null) {
                for (i = 0; i < Number(images.length); i += 1) { images[i].changes = false; images[i].close(); }
            }
            throw error;
        }
    }

    function runSourceDecode(path, expected, callback, originalGuard) {
        var guard = originalGuard || onboardingGuard();
        var startedAt = Number(System.nanoTime());
        if (state.busy || state.disposed) { return; }
        checkOnboardingGuard(guard);
        setBusy(true, OPERATION_LABELS.decode_source_image);
        startOperationProgress("decode_source_image", startedAt);
        new Thread(new JavaAdapter(Runnable, {run: function () {
            var decoded = null;
            var problem = null;
            try { decoded = decodeOnboardingSource(path, expected); } catch (error) { problem = error; }
            onEdt(function () {
                try {
                    checkOnboardingGuard(guard);
                    setBusy(false, "Lectura terminada");
                    if (problem !== null) { throw problem; }
                    finishOperationProgress("decode_source_image", startedAt, "PASS");
                    callback(decoded);
                } catch (error) {
                    if (decoded !== null) { decoded.image.changes = false; decoded.image.close(); }
                    if (!state.disposed) {
                        setBusy(false, "No se completó la apertura de la imagen.");
                        finishOperationProgress("decode_source_image", startedAt, "ERROR"); showError(error);
                    }
                }
            });
        }}), "CTL-P3-Source-Read").start();
    }

    function promptSourceMetadata(decoded) {
        var names = ["study_id", "condition_id", "specimen_id", "lamella_id", "image_id", "analysis_session_id", "operator_id"];
        var labels = ["Estudio", "Condición", "Muestra", "Lamela", "Imagen", "Sesión inicial", "Operador"];
        var stem = decoded.source_file_name.replace(/\.dm[34]$/i, "").replace(/[^A-Za-z0-9._~-]+/g, "_").replace(/^[^A-Za-z0-9]+/, "");
        var defaults = ["SIN_ESPECIFICAR", "SIN_ESPECIFICAR", "SIN_ESPECIFICAR", "SIN_ESPECIFICAR",
            (stem || "IMAGEN").substring(0, 80), "SESION_1", "SIN_ESPECIFICAR"];
        var panel = new JPanel(new BorderLayout(6, 6));
        var fieldsPanel = new JPanel(new GridLayout(0, 2, 6, 5));
        var fields = [];
        var context = decoded.image_context;
        var details = new JTextArea("Fuente: " + decoded.source_file_name + "\n" + context.width_px + " × " + context.height_px +
            " píxeles · " + context.bit_depth + " bits\nEscala: X = " + Number(context.scale_x_nm_px).toPrecision(10) +
            " · Y = " + Number(context.scale_y_nm_px).toPrecision(10) + " nm/píxel\n" +
            "Revise la escala y los identificadores. SIN_ESPECIFICAR indica un dato todavía desconocido.");
        var result = {};
        var i;
        details.setEditable(false); details.setBackground(panel.getBackground());
        panel.add(details, BorderLayout.NORTH);
        for (i = 0; i < names.length; i += 1) {
            fieldsPanel.add(new JLabel(labels[i] + ":"));
            fields[i] = new JTextField(defaults[i], 32); fieldsPanel.add(fields[i]);
        }
        panel.add(fieldsPanel, BorderLayout.CENTER);
        panel.add(new JLabel("Se conservará una copia de la fuente y se creará una sesión sin anotaciones."), BorderLayout.SOUTH);
        while (true) {
            if (JOptionPane.showConfirmDialog(frame, panel, "Incorporar imagen TEM", JOptionPane.OK_CANCEL_OPTION,
                    JOptionPane.PLAIN_MESSAGE) !== JOptionPane.OK_OPTION) { return null; }
            try {
                for (i = 0; i < names.length; i += 1) { result[names[i]] = onboardingId(fields[i].getText(), labels[i]); }
                return result;
            } catch (error) { showError(error); }
        }
    }

    function addSourceImageFromUi() {
        if (state.busy || state.disposed) { return; }
        if (WindowManager.getCurrentImage() !== null) { requireOriginalImage(WindowManager.getCurrentImage()); }
        if (!state.projectPath || state.projectKind !== "SCHEMA2") {
            showError("Cree o abra primero un proyecto editable."); return;
        }
        resolvePendingChanges(function () {
            var guard = onboardingGuard();
            var path = chooseOpenFile("Seleccione la imagen TEM DM3 o DM4");
            if (path === null) { return; }
            runSourceDecode(path, null, function (decoded) {
                var metadata = promptSourceMetadata(decoded);
                if (metadata === null) { decoded.image.close(); return; }
                checkOnboardingGuard(guard);
                metadata.project_root = state.projectPath; metadata.expected_project_uid = state.projectUid;
                metadata.source_path = decoded.source_path; metadata.source_sha256 = decoded.source_sha256;
                metadata.image_context = decoded.image_context;
                invokeOperation("p3_register_source_image", metadata, function (result) {
                    decoded.image.close();
                    try { checkOnboardingGuard(guard); }
                    catch (error) { showError("La imagen se incorporó, pero no se cambió la sesión abierta. " + error); return; }
                    inspectProject(state.projectPath, guard);
                    JOptionPane.showMessageDialog(frame,
                        (result.registration_status === "ALREADY_REGISTERED" ? "La imagen ya estaba incorporada: " : "Imagen incorporada: ") +
                        result.image_id + "\nSesión: " + result.analysis_session_id +
                        "\nSeleccione su fila y pulse Abrir imagen y sesión para empezar.", "Imagen incorporada", JOptionPane.INFORMATION_MESSAGE);
                }, null, function (error) {
                    decoded.image.close();
                    showError(String(error) + "\nActualice el proyecto para consultar cualquier registro conservado antes de reintentar.");
                });
            }, guard);
        });
    }

    function sourceCacheDirectory() {
        var root = new File(String(System.getProperty("java.io.tmpdir")), "CavityTEM_SourceCache");
        if (!root.exists()) { Files.createDirectory(root.toPath()); }
        if (!root.isDirectory() || Files.isSymbolicLink(root.toPath())) { fail("No se puede utilizar la carpeta temporal de fuentes."); }
        return String(root.getCanonicalPath());
    }

    function openSourceAndSession() {
        if (WindowManager.getCurrentImage() !== null) { requireOriginalImage(WindowManager.getCurrentImage()); }
        var session = selectedSession();
        if (session === null || state.busy || state.disposed) { return; }
        if (session._legacy_image) { showError("Migre el proyecto histórico por copia antes de abrir una sesión editable."); return; }
        resolvePendingChanges(function () {
            session = sessionByUid(String(session.analysis_session_uid));
            if (session === null) { showError("La sesión seleccionada ya no está disponible. Actualice el proyecto."); return; }
            var guard = onboardingGuard();
            invokeOperation("p3_source_image_context", {project_root: state.projectPath,
                expected_project_uid: state.projectUid, image_uid: String(session._image_uid),
                cache_directory: sourceCacheDirectory()}, function (source) {
                try { checkOnboardingGuard(guard); }
                catch (changed) { showError(changed); return; }
                runSourceDecode(String(source.source_path), source, function (decoded) {
                    checkOnboardingGuard(guard);
                    invokeOperation("select_session", {project_root: state.projectPath,
                        image_uid: String(session._image_uid), analysis_session_uid: String(session.analysis_session_uid),
                        expected_current_generation: Number(session.generation),
                        expected_registry_sha256: String(session._session_registry_sha256), cancel: false}, function (result) {
                        try { checkOnboardingGuard(guard); }
                        catch (changed) { decoded.image.close(); showError(changed); return; }
                        decoded.image.setTitle(String(source.source_file_name));
                        decoded.image.show();
                        WindowManager.setCurrentWindow(decoded.image.getWindow());
                        bindActivePayload(result, result.selection && result.selection.selected_session_uid, "Imagen y sesión abiertas");
                    }, null, function (error) { decoded.image.close(); showError(error); });
                }, guard);
            });
        });
    }

    function restoreLeafFromArchive(archivePath) {
        var name = String(new File(archivePath).getName());
        var match = /^CTL_SESSION_(.+)_([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\.zip$/i.exec(name);
        if (match === null || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(match[1])) {
            fail("SESSION_ARCHIVE_FILENAME_INVALID");
        }
        return "SESSION_" + match[1];
    }

    function sessionStateLabel(session) {
        var raw = String(session.state || "");
        var labels = {
            CURRENT: "Actual en el proyecto",
            HISTORICAL: "Histórica",
            HISTORICAL_NON_CANONICAL: "Histórica (no canónica)",
            ARCHIVED: "Archivada",
            QUARANTINED: "En cuarentena",
            VERIFIED_READ_ONLY: "Histórica · solo lectura",
            BLOCKED_REVIEW_READ_ONLY: "Requiere revisión · solo lectura"
        };
        return labels[raw] || (raw === "" ? "No disponible" : raw);
    }

    function sessionTableValue(session, columnName) {
        var value = session[columnName];
        if (columnName === "_state_label") { return sessionStateLabel(session); }
        if (value === null || value === undefined || String(value) === "") {
            if (columnName === "current_revision") { return "Sin revisión"; }
            if (columnName === "current_run") { return "Sin resultado"; }
            if (columnName === "object_count") { return "No disponible"; }
            return "";
        }
        return String(value);
    }

    function refreshActiveSessionLabel() {
        var session = state.activeSession;
        if (!activeSessionLabel) { return; }
        if (session === null || state.activeSessionUid === null || state.boundImage === null) {
            activeSessionLabel.setText("Sesión activa: ninguna. Seleccione una fila y pulse Abrir sesión.");
            activeSessionLabel.setToolTipText("Seleccionar una fila no abre ni activa una sesión.");
            return;
        }
        activeSessionLabel.setText("Sesión activa: " + String(session.analysis_session_id) +
            "   ·   Imagen: " + String(session.image_id) +
            "   ·   Revisión: " + sessionTableValue(session, "current_revision"));
        activeSessionLabel.setToolTipText("UID: " + String(state.activeSessionUid) +
            " · generación " + String(state.activeGeneration));
    }

    function applySessionTableColumns() {
        var model = table.getColumnModel();
        var order = SESSION_SUMMARY_COLUMNS.slice(0);
        var i;
        var column;
        if (state.sessionDetailsVisible) {
            for (i = 0; i < TABLE_COLUMNS.length; i += 1) {
                if (order.indexOf(i) < 0) { order.push(i); }
            }
        }
        // The row model and sorter remain intact when toggling details.
        while (model.getColumnCount() > 0) { model.removeColumn(model.getColumn(0)); }
        for (i = 0; i < order.length; i += 1) {
            column = sessionTableColumns[order[i]];
            model.addColumn(column);
        }
        table.setAutoResizeMode(state.sessionDetailsVisible ?
            JTable.AUTO_RESIZE_OFF : JTable.AUTO_RESIZE_SUBSEQUENT_COLUMNS);
    }

    function rebuildSessionTableColumns() {
        var model = table.getColumnModel();
        var i;
        var column;
        var modelIndex;
        // setDataVector recreates JTable columns; discard references to the old ones.
        sessionTableColumns = [];
        for (i = 0; i < model.getColumnCount(); i += 1) {
            column = model.getColumn(i);
            modelIndex = Number(column.getModelIndex());
            column.setHeaderValue(SESSION_COLUMN_LABELS[modelIndex]);
            column.setPreferredWidth(SESSION_COLUMN_WIDTHS[modelIndex]);
            column.setMinWidth(modelIndex === 17 ? 100 : 120);
            sessionTableColumns[modelIndex] = column;
        }
        applySessionTableColumns();
    }

    function fillSessions(result) {
        var images = Array.isArray(result.images) ? result.images : [];
        var sessions = [];
        var data;
        var i;
        var j;
        var k;
        var image;
        var session;
        var row;
        var revisions;
        var verifiedRevisions;
        var limitation;
        state.images = images;
        state.projectUid = result.project_uid === undefined || result.project_uid === null ?
            null : String(result.project_uid);
        state.projectKind = String(result.project_kind || "UNKNOWN");
        if (state.projectKind === "LEGACY_SCHEMA1_READ_ONLY") {
            for (i = 0; i < images.length; i += 1) {
                image = images[i] || {};
                revisions = Array.isArray(image.revisions) ? image.revisions : [];
                verifiedRevisions = revisions.filter(function (item) {
                    return String((item || {}).status || "") === "VERIFIED";
                });
                sessions.push({
                    project_id: result.project_id,
                    image_id: image.image_id,
                    source_sha256: image.source_sha256,
                    analysis_session_id: "LEGACY_SESSION",
                    state: String(image.status || "BLOCKED_REVIEW") + "_READ_ONLY",
                    current_revision: image.current_revision_observed_non_authoritative || "",
                    current_run: image.legacy_run_observed_non_authoritative || "",
                    revision_count: verifiedRevisions.length,
                    run_count: 0,
                    logical_bytes: "READ_ONLY",
                    physical_bytes: "READ_ONLY",
                    origin: "LEGACY_SCHEMA1_READ_ONLY",
                    session_uid: "LEGACY:" + String(image.image_id || ""),
                    generation: 0,
                    active: false,
                    _legacy_image: image,
                    _image_uid: null,
                    _session_registry_sha256: null
                });
            }
        }
        for (i = 0; i < images.length; i += 1) {
            image = images[i] || {};
            if (state.projectKind === "LEGACY_SCHEMA1_READ_ONLY") { continue; }
            for (j = 0; j < (Array.isArray(image.sessions) ? image.sessions.length : 0); j += 1) {
                session = image.sessions[j] || {};
                row = {};
                for (k in session) {
                    if (Object.prototype.hasOwnProperty.call(session, k)) { row[k] = session[k]; }
                }
                row.project_id = result.project_id;
                row.image_id = image.image_id;
                row.source_sha256 = image.source_sha256;
                row.current_revision = session.current_revision_id;
                row.current_run = session.current_run_id;
                row.session_uid = session.analysis_session_uid;
                row.generation = image.current_session_generation;
                row._image_uid = image.image_uid;
                row._session_registry_sha256 = image.session_registry_sha256;
                row._master_pixel_hash_status = image.master_pixel_hash_status;
                sessions.push(row);
            }
        }
        state.migrationLimitations = [];
        for (i = 0; i < sessions.length; i += 1) {
            limitation = sessions[i].migration_limitation;
            if (limitation !== null && limitation !== undefined) {
                state.migrationLimitations.push(limitation);
            }
        }
        if (state.migrationLimitations.length > 0) {
            limitation = state.migrationLimitations[0];
            migrationWarningLabel.setText(
                "Migración parcial segura. La revisión legacy más reciente contiene conflictos " +
                "de identidad y se conserva íntegra en cuarentena. La sesión editable parte de " +
                String(limitation.editable_baseline_revision) + "."
            );
            migrationWarningLabel.setVisible(true);
        } else {
            migrationWarningLabel.setText("");
            migrationWarningLabel.setVisible(false);
        }
        data = java.lang.reflect.Array.newInstance(java.lang.Object.class, sessions.length, TABLE_COLUMNS.length);
        state.sessions = sessions;
        for (i = 0; i < sessions.length; i += 1) {
            session = sessions[i] || {};
            for (j = 0; j < TABLE_COLUMNS.length; j += 1) {
                data[i][j] = sessionTableValue(session, TABLE_COLUMNS[j]);
            }
        }
        tableModel.setDataVector(data, TABLE_COLUMNS);
        rebuildSessionTableColumns();
        table.clearSelection();
        projectField.setText(String(state.projectPath || ""));
    }

    function sessionByUid(uid) {
        var i;
        for (i = 0; i < state.sessions.length; i += 1) {
            if (String(state.sessions[i].analysis_session_uid) === String(uid)) { return state.sessions[i]; }
        }
        return null;
    }

    function clearActiveContext(clearRois) {
        var oldImage = state.boundImage;
        if (state.editState !== null) { finishGeometryEdit(false, true); }
        stopTemporaryReveal(false);
        removeCavityClickListener();
        if (oldImage !== null) { clearFilteredOverlay(oldImage); }
        state.activeSessionUid = null;
        state.activeGeneration = null;
        state.activeSession = null;
        state.activeObjects = [];
        state.workingObjects = [];
        state.activeCandidates = [];
        state.candidateReview = null;
        state.cloneRoiIdentityBridge = null;
        state.activeGeometries = [];
        state.geometryState = null;
        state.baselineRoiSha256 = null;
        state.boundImage = null;
        state.displayModes = jsonClone(DEFAULT_DISPLAY_MODES);
        state.displayPreferencesSha256 = "NOT_APPLICABLE";
        state.displayEpoch += 1;
        state.geometryDirty = false;
        state.callbackEpoch += 1;
        resetDraftState();
        if (clearRois) { loadObjectsIntoRoiManager([]); }
        refreshDisplayControls();
    }

    function requestGeometryState(message, continuation) {
        var active = state.activeSession;
        var imageContext;
        if (active === null || state.activeSessionUid === null) { return; }
        if (active.current_revision_uid === null || active.current_revision_uid === undefined ||
                String(active.current_revision_uid) === "") {
            state.activeGeometries = [];
            state.geometryState = null;
            state.baselineRoiSha256 = exportAllFijiRois().snapshot_sha256;
            rebuildFilteredOverlay();
            installCavityClickListener();
            refreshDisplayControls();
            initializeDraftState(null);
            if (continuation) { continuation(); }
            return;
        }
        imageContext = currentImageContext("PROMPT3_MASKS_GEOMETRY_STATE", "1");
        invokeOperation("get_geometry_state", {
            project_root: state.projectPath,
            image_uid: String(active._image_uid),
            analysis_session_uid: state.activeSessionUid,
            expected_revision_pointer_sha256: String(active.current_revision_pointer_sha256),
            image_context: imageContext
        }, function (result) {
            try {
                loadObjectsIntoRoiManager(state.activeObjects, state.cloneRoiIdentityBridge);
                applyGeometryState(result);
                state.baselineRoiSha256 = exportAllFijiRois().snapshot_sha256;
                state.geometryDirty = false;
                state.displayEpoch += 1;
                rebuildFilteredOverlay();
                installCavityClickListener();
                refreshDisplayControls();
                statusLabel.setText(String(message || "Geometrías y preferencias de la sesión cargadas."));
                initializeDraftState(imageContext);
                if (continuation) { continuation(result); }
            } catch (geometryError) {
                clearActiveContext(true);
                showError("No se pudo ligar la geometría científica a la revisión: " + geometryError);
            }
        });
    }

    function bindActivePayload(result, sessionUid, message) {
        // Check before replacing the active session, table or ROI Manager contents.
        try { requireOriginalImage(WindowManager.getCurrentImage()); }
        catch (viewError) { showError(viewError); return; }
        var uid = String(sessionUid || "");
        var selected;
        var baseline;
        var imp;
        var suppliedGeometryState;
        if (!result.project || !Array.isArray(result.objects) ||
                !Array.isArray(result.candidates) || uid === "") {
            clearActiveContext(true);
            showError("La operación no devolvió el working state activo verificado.");
            return;
        }
        fillSessions(result.project);
        selected = sessionByUid(uid);
        if (selected === null || !(selected.active === true ||
                String(selected.active) === "true")) {
            clearActiveContext(true);
            showError("La autoridad current_session no coincide con la sesión devuelta.");
            return;
        }
        if (state.editState !== null) { finishGeometryEdit(false, true); }
        stopTemporaryReveal(false);
        removeCavityClickListener();
        if (state.boundImage !== null) { clearFilteredOverlay(state.boundImage); }
        state.activeSessionUid = uid;
        state.activeSession = selected;
        state.activeGeneration = Number(selected.generation);
        resetDraftState();
        state.callbackEpoch += 1;
        state.displayEpoch += 1;
        imp = WindowManager.getCurrentImage();
        suppliedGeometryState = result.geometry_state;
        try {
            if (imp === null) { fail("NO_ACTIVE_IMAGE_FOR_SESSION_BIND"); }
            state.boundImage = imp;
            verifiedActiveSourceSha(imp);
            imp.setProperty("CTL.P3.project_uid", String(state.projectUid || ""));
            imp.setProperty("CTL.P3.image_uid", String(selected._image_uid || ""));
            imp.setProperty("CTL.P3.analysis_session_uid", uid);
            imp.setProperty("CTL.P3.session_generation", String(state.activeGeneration));
            state.activeObjects = jsonClone(result.objects);
            state.workingObjects = [];
            state.activeCandidates = jsonClone(result.candidates);
            state.candidateReview = null;
            state.cloneRoiIdentityBridge = normalizedCloneRoiIdentityBridge(
                result.clone_roi_identity_bridge, uid
            );
            loadObjectsIntoRoiManager(result.objects, state.cloneRoiIdentityBridge);
            if (suppliedGeometryState !== null && suppliedGeometryState !== undefined) {
                applyGeometryState(suppliedGeometryState);
            } else {
                state.activeGeometries = [];
                state.geometryState = null;
                state.displayModes = jsonClone(DEFAULT_DISPLAY_MODES);
                state.displayPreferencesSha256 = "NOT_APPLICABLE";
            }
            baseline = exportAllFijiRois().snapshot_sha256;
        } catch (loaderError) {
            clearActiveContext(true);
            showError("No se pudo cargar de forma íntegra el working state activo: " + loaderError);
            return;
        }
        state.baselineRoiSha256 = baseline;
        rebuildFilteredOverlay();
        installCavityClickListener();
        refreshDisplayControls();
        if (suppliedGeometryState !== null && suppliedGeometryState !== undefined) {
            statusLabel.setText(String(message) + ": " + uid +
                " / generación " + state.activeGeneration);
            initializeDraftState(null);
        } else {
            requestGeometryState(String(message) + ": geometría y preferencias ligadas a " + uid);
        }
    }

    function explicitImage() {
        var selected = Number(table.getSelectedRow());
        var labels = [];
        var i;
        var choice;
        if (selected >= 0) { return state.sessions[Number(table.convertRowIndexToModel(selected))]; }
        if (state.images.length === 1) {
            return {
                image_id: state.images[0].image_id,
                _image_uid: state.images[0].image_uid,
                generation: state.images[0].current_session_generation,
                _session_registry_sha256: state.images[0].session_registry_sha256
            };
        }
        for (i = 0; i < state.images.length; i += 1) {
            labels.push(String(state.images[i].image_id) + " | " + String(state.images[i].image_uid));
        }
        if (labels.length === 0) { showError("El proyecto no contiene imágenes registradas."); return null; }
        choice = JOptionPane.showInputDialog(frame, "Seleccione explícitamente una imagen:",
            "Imagen", JOptionPane.QUESTION_MESSAGE, null, labels, null);
        if (choice === null) { return null; }
        i = labels.indexOf(String(choice));
        if (i < 0) { fail("IMAGE_SELECTION_INVALID"); }
        return {
            image_id: state.images[i].image_id,
            _image_uid: state.images[i].image_uid,
            generation: state.images[i].current_session_generation,
            _session_registry_sha256: state.images[i].session_registry_sha256
        };
    }

    function inspectProject(projectPath, pendingGuard) {
        var binding = {session_uid: state.activeSessionUid, generation: state.activeGeneration, epoch: state.callbackEpoch};
        var sameProject = state.projectPath !== null &&
            String(new File(state.projectPath).getCanonicalPath()) ===
            String(new File(projectPath).getCanonicalPath());
        var preservedUid = sameProject ? state.activeSessionUid : null;
        invokeOperation("inspect_project", {project_root: projectPath}, function (result) {
            if (pendingGuard) {
                try { checkOnboardingGuard(pendingGuard); }
                catch (changed) { showError("El proyecto está disponible en " + projectPath + ". " + changed); return; }
            }
            state.projectPath = String(projectPath);
            fillSessions(result);
            if (preservedUid !== null && sessionByUid(preservedUid) !== null &&
                    (sessionByUid(preservedUid).active === true ||
                    String(sessionByUid(preservedUid).active) === "true")) {
                state.activeSessionUid = preservedUid;
                state.activeSession = sessionByUid(preservedUid);
                state.activeGeneration = Number(state.activeSession.generation);
                statusLabel.setText("Proyecto actualizado; se conserva la sesión elegida explícitamente.");
                refreshActiveSessionLabel();
            } else {
                clearActiveContext(true);
                statusLabel.setText(state.projectKind === "LEGACY_SCHEMA1_READ_ONLY" ?
                    "Proyecto legacy abierto como LEGACY_SESSION read-only." :
                    "Proyecto inspeccionado; seleccione una sesión explícitamente.");
            }
        }, binding);
    }

    function computeValidAnalysisPixelCount() {
        var imp = state.boundImage;
        var manager = RoiManager.getInstance2();
        var processor;
        var masks = [];
        var exclusions = [];
        var pixels;
        var i;
        var roi;
        var type;
        var count = 0;
        if (imp === null || imp !== WindowManager.getCurrentImage() || manager === null) {
            fail("AREA_RASTER_SCOPE_INVALID");
        }
        processor = new ByteProcessor(Number(imp.getWidth()), Number(imp.getHeight()));
        for (i = 0; i < Number(manager.getCount()); i += 1) {
            roi = manager.getRoi(i);
            if (roi === null) { continue; }
            type = normalizeRoiType(roi);
            if (type === "analysis_mask") { masks.push(roi); }
            else if (type === "exclusion") { exclusions.push(roi); }
        }
        if (masks.length === 0) {
            processor.setValue(255);
            processor.fill();
        } else {
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

    function geometryStateMatchesSnapshot(geometryState, snapshot) {
        var stateGeometries = Array.isArray(geometryState.geometries) ? geometryState.geometries : [];
        var live = Array.isArray(snapshot.geometries) ? snapshot.geometries : [];
        var expected = [];
        var observed = [];
        var i;
        for (i = 0; i < live.length; i += 1) {
            expected.push(String(live[i].geometry_uid) + "|" + String(live[i].roi_bytes_sha256));
        }
        for (i = 0; i < stateGeometries.length; i += 1) {
            observed.push(String(stateGeometries[i].geometry_uid) + "|" + String(stateGeometries[i].roi_bytes_sha256));
        }
        expected.sort();
        observed.sort();
        return expected.join("\n") === observed.join("\n");
    }

    function ensureAnalysisAreaCache(imageContext, continuation) {
        var active = state.activeSession;
        var snapshot = exportAllFijiRois();
        if (active === null || state.editState !== null) { fail("AREA_CACHE_SESSION_NOT_READY"); }
        invokeOperation("get_geometry_state", {
            project_root: state.projectPath,
            image_uid: String(active._image_uid),
            analysis_session_uid: state.activeSessionUid,
            expected_revision_pointer_sha256: String(active.current_revision_pointer_sha256),
            image_context: imageContext
        }, function (geometryState) {
            var status = String(geometryState.analysis_area_cache_status || "");
            var cache = geometryState.analysis_area_cache;
            var validPixelCount;
            if (!geometryStateMatchesSnapshot(geometryState, snapshot) ||
                    !geometryStateMatchesSnapshot(geometryState, exportAllFijiRois())) {
                showError("AREA_CACHE_GEOMETRY_SCOPE_MISMATCH");
                return;
            }
            state.geometryState = jsonClone(geometryState);
            state.activeGeometries = jsonClone(geometryState.geometries || []);
            if ((status === "HIT" || status === "REBOUND_WITHOUT_RASTER_RECALCULATION") &&
                    cache !== null && cache !== undefined && Number(cache.valid_pixel_count) > 0) {
                continuation(geometryState);
                return;
            }
            validPixelCount = computeValidAnalysisPixelCount();
            if (validPixelCount <= 0) {
                showError("El área científica válida es cero; RUN bloqueado.");
                return;
            }
            invokeOperation("commit_analysis_area_cache", {
                project_root: state.projectPath,
                image_uid: String(active._image_uid),
                analysis_session_uid: state.activeSessionUid,
                expected_revision_pointer_sha256: String(active.current_revision_pointer_sha256),
                expected_area_cache_sha256: String(geometryState.analysis_area_cache_sha256 || "NOT_APPLICABLE"),
                input_fingerprint_sha256: String((geometryState.area_input || {}).input_fingerprint_sha256 || ""),
                valid_pixel_count: validPixelCount,
                image_context: imageContext
            }, function (result) {
                geometryState.analysis_area_cache = result.analysis_area_cache;
                geometryState.analysis_area_cache_sha256 = result.analysis_area_cache_sha256;
                geometryState.analysis_area_cache_status = result.analysis_area_cache_status;
                state.geometryState = jsonClone(geometryState);
                continuation(geometryState);
            });
        });
    }

    function isInspectionView(imp) {
        var role;
        if (!imp) { return false; }
        role = String(imp.getProperty("CTL.P1.image_role") || "");
        return String(imp.getProperty("CTL.P3.inspection_view_id") || "") !== "" ||
            (role !== "" && role !== "MASTER_READ_ONLY") ||
            String(imp.getTitle()).indexOf("[Inspección CTL]") === 0;
    }

    function requireOriginalImage(imp) {
        if (!imp) { fail("Active la imagen original de la sesión."); }
        if (isInspectionView(imp)) {
            fail("Esta ventana es una vista de inspección. Use Volver al original para editar, abrir sesiones o guardar resultados.");
        }
    }

    function inspectionGeometry(imp) {
        var spatial = normalizedSpatialCalibration(imp);
        var calibration = imp.getCalibration();
        return {width_px: Number(imp.getWidth()), height_px: Number(imp.getHeight()),
            bit_depth: Number(imp.getBitDepth()), scale_x_nm_px: spatial.scale_x_nm_px,
            scale_y_nm_px: spatial.scale_y_nm_px,
            x_origin_px: Number(calibration.xOrigin), y_origin_px: Number(calibration.yOrigin)};
    }

    function inspectionVisualState(imp) {
        var colors = imp.getProcessor().getColorModel();
        var lut = [];
        var i;
        for (i = 0; i < Number(colors.getMapSize()); i += 1) {
            lut.push([Number(colors.getRed(i)), Number(colors.getGreen(i)), Number(colors.getBlue(i))]);
        }
        return {min: Number(imp.getDisplayRangeMin()), max: Number(imp.getDisplayRangeMax()),
            unit: "raw_pixel_value", lut_sha256: sha256Text(canonicalJsonText({rgb: lut})),
            inverted_lut: Boolean(imp.getProcessor().isInvertedLut())};
    }

    function inspectionVersions() {
        var fiji = "UNKNOWN";
        var bioFormats = "UNKNOWN";
        try { fiji = String(Packages.net.imagej.ImageJ.class.getPackage().getImplementationVersion() || "UNKNOWN"); }
        catch (ignoredFijiVersion) {}
        try { bioFormats = String(Packages.loci.formats.FormatTools.VERSION); }
        catch (ignoredBioFormatsVersion) {}
        return {Fiji_version: fiji, ImageJ_version: String(IJ.getVersion()),
            Java_version: String(System.getProperty("java.version")), Bio_Formats_version: bioFormats,
            plugin_versions: {ImageJ_core: String(IJ.getVersion())}};
    }

    function inspectionRecipe(mode, sigma, versions) {
        var steps = [{operation: "COPY_FULL_PROCESSOR_V1", crop: false, resample: false}];
        if (["CONTRAST", "GAUSSIAN"].indexOf(mode) < 0) { fail("Ajuste de inspección desconocido."); }
        if (mode === "GAUSSIAN") {
            if (!isFinite(sigma) || sigma < 0.1 || sigma > 5) { fail("Sigma debe estar entre 0,1 y 5 píxeles."); }
            steps.push({operation: "ij.plugin.filter.GaussianBlur", sigma_x: sigma, sigma_y: sigma,
                sigma_unit: "px", accuracy: 0.01});
        }
        steps.push({operation: "DISPLAY_MEAN_PLUS_MINUS_STD_V1", standard_deviations: 2,
            clamp_to_data_range: true, materialize_pixels: false});
        return {schema: "CTL_P7_INSPECTION_RECIPE_V1", versions: jsonClone(versions), steps: steps};
    }

    function buildInspectionView(master, settings, binding) {
        var before;
        var after;
        var viewEvidence;
        var geometry;
        var originalVisual;
        var processor;
        var copy;
        var stats;
        var low;
        var high;
        var visual;
        var recipe = inspectionRecipe(settings.mode, settings.sigma, binding.versions);
        var viewId = "VIEW_" + String(UUID.randomUUID());
        var record;
        requireOriginalImage(master);
        if ([8, 16, 32].indexOf(Number(master.getBitDepth())) < 0 ||
                Number(master.getWidth()) * Number(master.getHeight()) * (Number(master.getBitDepth()) / 8) > INSPECTION_MAX_BYTES) {
            fail("Esta vista admite imágenes TEM grises de 8, 16 o 32 bits dentro del límite de memoria.");
        }
        if (!master.lock()) { fail("La imagen original está ocupada. Espere a que termine su operación."); }
        try {
            geometry = inspectionGeometry(master);
            originalVisual = inspectionVisualState(master);
            before = computeMasterPixelEvidence(master);
            if (binding.expected_master_sha256 && before.sha256 !== binding.expected_master_sha256) {
                fail("Los píxeles originales cambiaron desde la carga de la sesión. Reabra la imagen verificada.");
            }
            processor = master.getProcessor().duplicate();
            if (processor === master.getProcessor() || processor.getPixels() === master.getProcessor().getPixels()) {
                fail("No se obtuvo una copia independiente de los píxeles.");
            }
            processor.resetRoi();
            processor.resetThreshold();
            // A fresh ImagePlus inherits no FileInfo, source authority, session or listeners.
            copy = new ImagePlus("[Inspección CTL] " + (settings.mode === "GAUSSIAN" ? "Suavizado" : "Contraste") +
                " · " + viewId.substring(5, 13) + " · " + String(master.getTitle()), processor);
            copy.setCalibration(master.getCalibration().copy());
            if (settings.mode === "GAUSSIAN") {
                new GaussianBlur().blurGaussian(processor, settings.sigma, settings.sigma, 0.01);
            }
            stats = processor.getStatistics();
            low = Math.max(Number(stats.min), Number(stats.mean) - 2 * Number(stats.stdDev));
            high = Math.min(Number(stats.max), Number(stats.mean) + 2 * Number(stats.stdDev));
            if (!isFinite(low) || !isFinite(high) || low > high) { fail("No se pudo calcular un rango de inspección finito."); }
            copy.setDisplayRange(low, high);
            viewEvidence = computeMasterPixelEvidence(copy);
            after = computeMasterPixelEvidence(master);
            if (before.sha256 !== after.sha256 ||
                    canonicalJsonText(geometry) !== canonicalJsonText(inspectionGeometry(master)) ||
                    canonicalJsonText(originalVisual) !== canonicalJsonText(inspectionVisualState(master))) {
                fail("La imagen original cambió durante la creación. No se publicó la vista.");
            }
            if (canonicalJsonText(geometry) !== canonicalJsonText(inspectionGeometry(copy)) ||
                    (settings.mode === "CONTRAST" && viewEvidence.sha256 !== before.sha256)) {
                fail("La copia no conserva los píxeles o la correspondencia espacial esperados.");
            }
            visual = inspectionVisualState(copy);
            record = {view_id: viewId, image_role: settings.mode === "CONTRAST" ? "DISPLAY_ONLY" : "DERIVED_VIEW_CANDIDATE",
                source_sha256: binding.source_sha256, master_pixel_sha256: before.sha256,
                master_pixel_sha256_after: after.sha256, view_pixel_sha256: viewEvidence.sha256,
                pixel_hash_method: PIXEL_METHOD, recipe_sha256: sha256Text(canonicalJsonText(recipe)),
                filter_recipe: recipe, geometry_preserved: true, width_px: geometry.width_px,
                height_px: geometry.height_px, bit_depth: geometry.bit_depth,
                scale_x_nm_px: geometry.scale_x_nm_px, scale_y_nm_px: geometry.scale_y_nm_px,
                coordinate_origin: {x_px: geometry.x_origin_px, y_px: geometry.y_origin_px},
                display_range: {min: visual.min, max: visual.max, unit: visual.unit},
                display_lut_sha256: visual.lut_sha256, inverted_lut: visual.inverted_lut, polarity: "UNKNOWN",
                purpose: "TEM_VISUAL_INSPECTION_V1", measurement_role: "visualization_only",
                measurement_validation_status: "NOT_VALIDATED", Fiji_version: binding.versions.Fiji_version,
                ImageJ_version: binding.versions.ImageJ_version, Java_version: binding.versions.Java_version,
                Bio_Formats_version: binding.versions.Bio_Formats_version,
                plugin_versions: binding.versions.plugin_versions, operator_id: "UNKNOWN",
                created_at: String(Packages.java.time.Instant.now()), project_uid: binding.project_uid,
                image_uid: binding.image_uid, analysis_session_uid: binding.analysis_session_uid,
                revision_uid: binding.revision_uid};
            copy.setProperty("CTL.P1.image_role", record.image_role);
            copy.setProperty("CTL.P3.inspection_view_id", viewId);
            copy.setProperty("Info", canonicalJsonText({schema: "CTL_P7_INSPECTION_VIEW_RECORD_V1", record: record,
                record_sha256: sha256Text(canonicalJsonText(record))}));
            return {image: copy, original: master, record: record, projectPath: binding.projectPath,
                geometry: geometry, visual: visual, bytes: geometry.width_px * geometry.height_px * (geometry.bit_depth / 8)};
        } finally { master.unlock(); }
    }

    function parseInspectionReplay(text, versions) {
        var envelope;
        var record;
        var steps;
        var settings;
        var recordedVersions;
        var numberFields;
        text = String(text);
        if (text.length === 0 || text.length > INSPECTION_RECIPE_MAX_BYTES) {
            fail("La receta está vacía o supera el límite de 64 KiB.");
        }
        try { envelope = JSON.parse(text); }
        catch (invalidJson) { fail("El archivo no contiene una receta JSON válida."); }
        if (!envelope || Array.isArray(envelope) || typeof envelope !== "object" ||
                envelope.schema !== "CTL_P7_INSPECTION_VIEW_RECORD_V1" ||
                Object.keys(envelope).sort().join("|") !== "record|record_sha256|schema" ||
                canonicalJsonText(envelope) !== text) {
            fail("La receta no tiene el formato canónico exportado por Cavity. Seleccione el JSON original sin modificar.");
        }
        record = envelope.record;
        if (!record || Array.isArray(record) || typeof record !== "object" ||
                sha256Text(canonicalJsonText(record)) !== envelope.record_sha256) {
            fail("El checksum del registro no coincide. La receta está dañada o fue modificada.");
        }
        ["source_sha256", "master_pixel_sha256", "master_pixel_sha256_after", "view_pixel_sha256",
            "recipe_sha256", "display_lut_sha256"].forEach(function (field) {
            if (typeof record[field] !== "string" || !/^[0-9a-f]{64}$/.test(record[field])) {
                fail("La receta no contiene un hash válido: " + field + ".");
            }
        });
        if (!record.filter_recipe || !Array.isArray(record.filter_recipe.steps) ||
                sha256Text(canonicalJsonText(record.filter_recipe)) !== record.recipe_sha256) {
            fail("El checksum o la estructura de los ajustes no coincide.");
        }
        steps = record.filter_recipe.steps;
        if ((steps.length !== 2 && steps.length !== 3) || !steps[1]) {
            fail("La receta contiene operaciones no admitidas.");
        }
        settings = {mode: steps.length === 3 ? "GAUSSIAN" : "CONTRAST",
            sigma: steps.length === 3 ? steps[1].sigma_x : 1};
        if (typeof settings.sigma !== "number" ||
                canonicalJsonText(record.filter_recipe) !==
                canonicalJsonText(inspectionRecipe(settings.mode, settings.sigma, versions))) {
            fail("La receta usa operaciones, parámetros o versiones diferentes de los admitidos en este entorno.");
        }
        recordedVersions = {Fiji_version: record.Fiji_version, ImageJ_version: record.ImageJ_version,
            Java_version: record.Java_version, Bio_Formats_version: record.Bio_Formats_version,
            plugin_versions: record.plugin_versions};
        if (canonicalJsonText(recordedVersions) !== canonicalJsonText(versions)) {
            fail("Las versiones del registro no coinciden con las del entorno actual.");
        }
        ["Fiji_version", "ImageJ_version", "Java_version", "Bio_Formats_version"].forEach(function (field) {
            if (typeof versions[field] !== "string" || !versions[field] || versions[field] === "UNKNOWN") {
                fail("No se puede verificar la versión del entorno: " + field + ". Cree una vista nueva.");
            }
        });
        numberFields = ["width_px", "height_px", "bit_depth", "scale_x_nm_px", "scale_y_nm_px"];
        numberFields.forEach(function (field) {
            if (typeof record[field] !== "number" || !isFinite(record[field]) || record[field] <= 0) {
                fail("La geometría guardada no es válida: " + field + ".");
            }
        });
        if (Math.floor(record.width_px) !== record.width_px || Math.floor(record.height_px) !== record.height_px ||
                [8, 16, 32].indexOf(record.bit_depth) < 0 ||
                !record.coordinate_origin || typeof record.coordinate_origin.x_px !== "number" ||
                typeof record.coordinate_origin.y_px !== "number" || !isFinite(record.coordinate_origin.x_px) ||
                !isFinite(record.coordinate_origin.y_px) || !record.display_range ||
                typeof record.display_range.min !== "number" || typeof record.display_range.max !== "number" ||
                !isFinite(record.display_range.min) || !isFinite(record.display_range.max) ||
                record.display_range.min > record.display_range.max || record.display_range.unit !== "raw_pixel_value" ||
                typeof record.inverted_lut !== "boolean") {
            fail("La receta contiene dimensiones, origen o visualización no válidos.");
        }
        ["project_uid", "image_uid", "analysis_session_uid", "revision_uid", "created_at"].forEach(function (field) {
            if (typeof record[field] !== "string" || !record[field]) { fail("Falta la procedencia de la receta: " + field + "."); }
        });
        if (typeof record.view_id !== "string" || !/^VIEW_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(record.view_id) ||
                record.pixel_hash_method !== PIXEL_METHOD || record.geometry_preserved !== true ||
                record.master_pixel_sha256 !== record.master_pixel_sha256_after ||
                (settings.mode === "CONTRAST" && record.view_pixel_sha256 !== record.master_pixel_sha256) ||
                record.image_role !== (settings.mode === "GAUSSIAN" ? "DERIVED_VIEW_CANDIDATE" : "DISPLAY_ONLY") ||
                record.measurement_role !== "visualization_only" || record.measurement_validation_status !== "NOT_VALIDATED" ||
                record.purpose !== "TEM_VISUAL_INSPECTION_V1" || record.polarity !== "UNKNOWN") {
            fail("La receta no corresponde a una vista de inspección compatible y sin autoridad de medición.");
        }
        return {record: record, record_sha256: envelope.record_sha256,
            recipe_file_sha256: sha256Text(text), settings: settings};
    }

    function readInspectionReplayFile(path, versions) {
        var file = new File(path).getCanonicalFile();
        var input;
        var output = new ByteArrayOutputStream();
        var buffer = java.lang.reflect.Array.newInstance(java.lang.Byte.TYPE, 8192);
        var count;
        var bytes;
        var text;
        if (!file.isFile() || file.length() <= 0 || file.length() > INSPECTION_RECIPE_MAX_BYTES) {
            fail("Seleccione un archivo de receta de hasta 64 KiB.");
        }
        input = new BufferedInputStream(new FileInputStream(file));
        try {
            while ((count = input.read(buffer)) !== -1) {
                if (output.size() + count > INSPECTION_RECIPE_MAX_BYTES) { fail("La receta supera el límite de 64 KiB."); }
                output.write(buffer, 0, count);
            }
        } finally { input.close(); }
        bytes = output.toByteArray();
        text = String(new java.lang.String(bytes, StandardCharsets.UTF_8));
        if (sha256Bytes(bytes) !== sha256Text(text)) { fail("La receta no usa una codificación UTF-8 válida."); }
        return parseInspectionReplay(text, versions);
    }

    function validateInspectionReplayContext(replay, master, binding) {
        var record = replay.record;
        var geometry = inspectionGeometry(master);
        var visual = inspectionVisualState(master);
        requireOriginalImage(master);
        if (record.project_uid !== binding.project_uid || record.image_uid !== binding.image_uid ||
                record.source_sha256 !== binding.source_sha256 ||
                (binding.expected_master_sha256 && record.master_pixel_sha256 !== binding.expected_master_sha256)) {
            fail("La receta pertenece a otra imagen o proyecto, o no coincide con los píxeles verificados de esta sesión.");
        }
        if (canonicalJsonText(geometry) !== canonicalJsonText({width_px: record.width_px, height_px: record.height_px,
                bit_depth: record.bit_depth, scale_x_nm_px: record.scale_x_nm_px, scale_y_nm_px: record.scale_y_nm_px,
                x_origin_px: record.coordinate_origin.x_px, y_origin_px: record.coordinate_origin.y_px})) {
            fail("El tamaño, la escala o el origen del original no coincide con la receta.");
        }
        if (visual.lut_sha256 !== record.display_lut_sha256 || visual.inverted_lut !== record.inverted_lut) {
            fail("La LUT del original no coincide con la receta. Restaure su visualización o cree una receta nueva.");
        }
    }

    function inspectionReplayResult(record) {
        var result = {};
        ["source_sha256", "master_pixel_sha256", "master_pixel_sha256_after", "view_pixel_sha256",
            "pixel_hash_method", "recipe_sha256", "geometry_preserved", "width_px", "height_px", "bit_depth",
            "scale_x_nm_px", "scale_y_nm_px", "coordinate_origin", "display_range", "display_lut_sha256",
            "inverted_lut", "image_role", "purpose", "measurement_role", "measurement_validation_status"].forEach(function (field) {
            result[field] = record[field];
        });
        return result;
    }

    function buildReplayedInspectionView(master, replay, binding) {
        var replayBinding = jsonClone(binding);
        var entry;
        validateInspectionReplayContext(replay, master, binding);
        replayBinding.expected_master_sha256 = replay.record.master_pixel_sha256;
        entry = buildInspectionView(master, replay.settings, replayBinding);
        if (canonicalJsonText(inspectionReplayResult(entry.record)) !==
                canonicalJsonText(inspectionReplayResult(replay.record))) {
            fail("La vista reconstruida no coincide con los píxeles o la visualización guardados. No se ha abierto.");
        }
        entry.record.replay_provenance = {schema: "CTL_P7_INSPECTION_REPLAY_V1",
            parent_view_id: replay.record.view_id, parent_record_sha256: replay.record_sha256,
            recipe_file_sha256: replay.recipe_file_sha256,
            parent_analysis_session_uid: replay.record.analysis_session_uid,
            parent_revision_uid: replay.record.revision_uid,
            verification: "EXACT_PIXELS_GEOMETRY_DISPLAY_AND_VERSIONS"};
        entry.image.setProperty("Info", canonicalJsonText({schema: "CTL_P7_INSPECTION_VIEW_RECORD_V1", record: entry.record,
            record_sha256: sha256Text(canonicalJsonText(entry.record))}));
        return entry;
    }

    function reapplyInspectionRecipe() {
        createInspectionView(true);
    }

    function pruneInspectionViews() {
        state.inspectionViews = state.inspectionViews.filter(function (entry) { return entry.image.getWindow() !== null; });
    }

    function createInspectionView(reapply) {
        var master = state.boundImage;
        var choice;
        var recipePath = null;
        var operation = reapply === true ? "replay_inspection_recipe" : "create_inspection_view";
        var binding;
        var key;
        var epoch;
        var startedAt;
        var retainedBytes = 0;
        if (state.busy || state.disposed || state.editState !== null) { return; }
        try {
            requireOriginalImage(WindowManager.getCurrentImage());
            if (!state.draftReady || !master || master !== WindowManager.getCurrentImage()) { fail("Abra y active la imagen original de esta sesión."); }
            if (state.draftImageContext !== null &&
                    draftImageSignature(inspectionGeometry(master)) !== draftImageSignature(state.draftImageContext)) {
                fail("La calibración o el tamaño cambió. Reabra la sesión antes de crear la vista.");
            }
            pruneInspectionViews();
            state.inspectionViews.forEach(function (entry) { retainedBytes += entry.bytes; });
            if (state.inspectionViews.length >= INSPECTION_MAX_VIEWS || retainedBytes +
                    Number(master.getWidth()) * Number(master.getHeight()) * Number(master.getBitDepth()) / 8 > INSPECTION_MAX_BYTES) {
                fail("Cierre una vista de inspección antes de crear otra. Se conservan hasta dos vistas dentro del límite de memoria.");
            }
            if (reapply === true) {
                recipePath = chooseOpenFile("Reaplicar una receta de vista guardada por Cavity (*.json)");
                if (recipePath === null) { return; }
            } else {
                choice = JOptionPane.showOptionDialog(frame, "Crear una copia a tamaño completo. Las mediciones se realizan en el original.",
                    "Vista de inspección", JOptionPane.DEFAULT_OPTION, JOptionPane.INFORMATION_MESSAGE, null,
                    ["Contraste", "Suavizado gaussiano (1 px)", "Cancelar"], "Contraste");
                if (choice !== 0 && choice !== 1) { return; }
            }
            verifiedActiveSourceSha(master);
            key = historyContextKey(); epoch = state.callbackEpoch;
            binding = {project_uid: state.projectUid, projectPath: state.projectPath,
                image_uid: String(state.activeSession._image_uid), analysis_session_uid: state.activeSessionUid,
                revision_uid: String(state.activeSession.current_revision_uid || "NOT_APPLICABLE"),
                source_sha256: String(state.activeSession.source_sha256), versions: inspectionVersions(),
                expected_master_sha256: state.draftImageContext === null ? null : state.draftImageContext.master_pixel_evidence.sha256};
        } catch (error) { showError(error); return; }
        startedAt = Number(System.nanoTime());
        setBusy(true, OPERATION_LABELS[operation]);
        startOperationProgress(operation, startedAt);
        new Thread(new JavaAdapter(Runnable, {run: function () {
            var entry;
            var error;
            try {
                entry = recipePath !== null ?
                    buildReplayedInspectionView(master, readInspectionReplayFile(recipePath, binding.versions), binding) :
                    buildInspectionView(master, {mode: choice === 0 ? "CONTRAST" : "GAUSSIAN", sigma: 1}, binding);
            }
            catch (caught) { error = caught; }
            onEdt(function () {
                if (state.disposed) { return; }
                setBusy(false, "Listo");
                try {
                    if (error) { throw error; }
                    if (state.boundImage !== master || master.getWindow() === null || state.callbackEpoch !== epoch || historyContextKey() !== key) {
                        fail("Cambió la sesión o la imagen; la vista preparada no se ha abierto.");
                    }
                    entry.image.show();
                    state.inspectionViews.push(entry);
                    finishOperationProgress(operation, startedAt, "PASS");
                    statusLabel.setText(recipePath !== null ?
                        "Receta reaplicada: píxeles, escala y visualización coinciden. Original intacto; use Volver al original para medir." :
                        "Vista de inspección creada; original intacto. Use Volver al original para editar y medir.");
                } catch (viewError) {
                    finishOperationProgress(operation, startedAt, "ERROR"); showError(viewError);
                }
            });
        }}), "CTL-P7-Inspection").start();
    }

    function returnToOriginal() {
        var master = state.boundImage;
        if (state.busy || !master || master.getWindow() === null) { statusLabel.setText("No hay una imagen original abierta disponible."); return; }
        master.getWindow().toFront();
        WindowManager.setCurrentWindow(master.getWindow());
        statusLabel.setText("Imagen original activa. La sesión y sus ROI se conservan.");
    }

    function validateInspectionView(entry) {
        var image = entry.image;
        var evidence;
        if (!image || image.getWindow() === null || !image.lock()) { fail("La vista no está disponible o está ocupada."); }
        try {
            evidence = computeMasterPixelEvidence(image);
            if (evidence.sha256 !== entry.record.view_pixel_sha256 ||
                    canonicalJsonText(inspectionGeometry(image)) !== canonicalJsonText(entry.geometry) ||
                    canonicalJsonText(inspectionVisualState(image)) !== canonicalJsonText(entry.visual)) {
                fail("La vista cambió después de crearla. Cree otra vista para guardar una receta que reproduzca su contenido.");
            }
        } finally { image.unlock(); }
    }

    function saveInspectionRecipe() {
        var current = WindowManager.getCurrentImage();
        var matches;
        var entry;
        var directory;
        var target;
        var parent;
        var text;
        var startedAt;
        if (state.busy || state.disposed) { return; }
        pruneInspectionViews();
        matches = state.inspectionViews.filter(function (item) { return item.image === current; });
        if (matches.length !== 1) { showError("Active la ventana de inspección cuya receta desea guardar."); return; }
        entry = matches[0];
        directory = chooseDirectory("Guardar receta de inspección fuera del proyecto científico");
        if (directory === null) { return; }
        try {
            parent = new File(directory).getCanonicalFile();
            [entry.projectPath, state.projectPath].forEach(function (project) {
                if (project && parent.toPath().startsWith(new File(project).getCanonicalFile().toPath())) {
                    fail("Guarde la receta fuera del proyecto científico.");
                }
            });
            target = new File(parent, entry.record.view_id + ".json");
            if (target.exists()) { fail("Esta carpeta ya contiene la receta de la vista. Elija otra carpeta para conservar ambas copias."); }
            text = canonicalJsonText({schema: "CTL_P7_INSPECTION_VIEW_RECORD_V1", record: entry.record,
                record_sha256: sha256Text(canonicalJsonText(entry.record))});
        } catch (error) { showError(error); return; }
        startedAt = Number(System.nanoTime());
        setBusy(true, OPERATION_LABELS.export_inspection_recipe);
        startOperationProgress("export_inspection_recipe", startedAt);
        new Thread(new JavaAdapter(Runnable, {run: function () {
            var temp;
            var error;
            try {
                validateInspectionView(entry);
                temp = Files.createTempFile(parent.toPath(), "ctl-view-", ".partial");
                Files.write(temp, new java.lang.String(text).getBytes(StandardCharsets.UTF_8),
                    Java.to([StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING], "java.nio.file.OpenOption[]"));
                // Same-directory publication; default move refuses to replace an existing file.
                Files.move(temp, target.toPath(), Java.to([], "java.nio.file.CopyOption[]"));
            } catch (caught) { error = caught; }
            onEdt(function () {
                if (state.disposed) { return; }
                setBusy(false, "Listo");
                finishOperationProgress("export_inspection_recipe", startedAt, error ? "ERROR" : "PASS");
                if (error) { showError(error); return; }
                statusLabel.setText("Receta guardada: " + target.getCanonicalPath());
            });
        }}), "CTL-P7-Recipe").start();
    }

    function candidateCircleGeometry(roi, imp) {
        var bounds;
        var spatial = normalizedSpatialCalibration(imp);
        if (!roi || Number(roi.getType()) !== 1) { fail("Dibuje una selección circular con la herramienta Oval de Fiji; mantenga Mayús para hacer un círculo."); }
        if (!spatialScalesAgree(spatial.scale_x_nm_px, spatial.scale_y_nm_px)) {
            fail("Las propuestas circulares manuales requieren píxeles con escala X/Y equivalente en esta entrega.");
        }
        bounds = roi.getFloatBounds();
        ["x", "y", "width", "height"].forEach(function (field) {
            if (!isFinite(Number(bounds[field]))) { fail("La selección contiene coordenadas no válidas."); }
        });
        if (Number(bounds.width) < 1 || Math.abs(Number(bounds.width) - Number(bounds.height)) > 1e-6 ||
                Number(bounds.x) < 0 || Number(bounds.y) < 0 ||
                Number(bounds.x) + Number(bounds.width) > Number(imp.getWidth()) ||
                Number(bounds.y) + Number(bounds.height) > Number(imp.getHeight())) {
            fail("La propuesta debe ser un círculo de al menos un píxel, completamente dentro de la imagen.");
        }
        return {schema: "CTL_P7_CIRCLE_PROPOSAL_V1",
            center_x_px: Number(bounds.x) + Number(bounds.width) / 2,
            center_y_px: Number(bounds.y) + Number(bounds.height) / 2,
            diameter_px: Number(bounds.width)};
    }

    function candidateDecisionClass(decision) {
        var classes = {accept: "confirmed", adjust_and_accept: "confirmed",
            mark_uncertain: "uncertain", mark_possible_artifact: "possible_artifact"};
        if (decision === "reject") { return null; }
        if (!Object.prototype.hasOwnProperty.call(classes, decision)) { fail("Decisión de revisión no válida."); }
        return classes[decision];
    }

    function candidateRoi(geometry) {
        // Avoid ambiguous int/double constructor dispatch in Fiji's script
        // engine when JSON coordinates combine integer and fractional values.
        var roi = new OvalRoi(0, 0, 1, 1);
        roi.setBounds(new Rectangle2DDouble(geometry.center_x_px - geometry.diameter_px / 2,
            geometry.center_y_px - geometry.diameter_px / 2, geometry.diameter_px, geometry.diameter_px));
        return roi;
    }

    function makeManualCandidate(geometry, entry, operator) {
        var uid = String(UUID.randomUUID());
        var record = entry.record;
        var candidate = {candidate_schema: "CTL_P7_MANUAL_CANDIDATE_V1", candidate_id: "CAND_" + uid,
            candidate_uuid: uid, identity_provenance: {generation_method: "UUIDV4_RANDOM", source: "CTL_P7_MANUAL_PROPOSAL"},
            object_uuid: null, cavity_id: null, review_status: "pending", review_decision: "pending",
            accepted_cavity_class: null, measurement_source: "manual_proposal",
            proposed_geometry: jsonClone(geometry), proposed_geometry_sha256: sha256Text(canonicalJsonText(geometry)),
            final_geometry: null, final_geometry_sha256: null,
            view_id: record.view_id, recipe_sha256: record.recipe_sha256,
            source_sha256: record.source_sha256, master_pixel_sha256: record.master_pixel_sha256,
            source_view: {record: jsonClone(record), record_sha256: sha256Text(canonicalJsonText(record))},
            proposal_operator_id: operator, created_at: candidateTimestamp(),
            reviewed_by: null, reviewed_at: null};
        ["count_valid", "size_valid", "position_valid", "primary_count_included", "primary_size_included",
            "primary_position_included", "sensitivity_count_included", "sensitivity_size_included",
            "sensitivity_position_included"].forEach(function (field) { candidate[field] = 0; });
        return candidate;
    }

    function reviewedCandidate(candidate, geometry, decision, operator, objectUuid, cavityId) {
        var reviewed = jsonClone(candidate);
        var cavityClass = candidateDecisionClass(decision);
        if (candidate.candidate_schema !== "CTL_P7_MANUAL_CANDIDATE_V1" || candidate.review_status !== "pending" ||
                candidate.review_decision !== "pending" || candidate.object_uuid !== null) { fail("El candidato ya fue resuelto o pertenece a otro flujo."); }
        if (decision === "accept" && canonicalJsonText(geometry) !== canonicalJsonText(candidate.proposed_geometry)) {
            decision = "adjust_and_accept";
        }
        delete reviewed.candidate_sha256;
        reviewed.review_status = "reviewed"; reviewed.review_decision = decision;
        reviewed.reviewed_by = operator; reviewed.reviewed_at = candidateTimestamp();
        reviewed.accepted_cavity_class = cavityClass;
        reviewed.object_uuid = cavityClass === null ? null : objectUuid;
        reviewed.cavity_id = cavityClass === null ? null : cavityId;
        reviewed.final_geometry = cavityClass === null ? null : jsonClone(geometry);
        reviewed.final_geometry_sha256 = cavityClass === null ? null : sha256Text(canonicalJsonText(geometry));
        return reviewed;
    }

    function candidateObject(roi, candidate) {
        var imp = state.boundImage;
        var spatial = normalizedSpatialCalibration(imp);
        var geometry = candidateCircleGeometry(roi, imp);
        var bounds = roi.getFloatBounds();
        var properties = {Type: "cavity", Cavity_id: candidate.cavity_id, Object_uuid: candidate.object_uuid,
            Candidate_uuid: candidate.candidate_uuid, Candidate_id: candidate.candidate_id,
            Cavity_class: candidate.accepted_cavity_class, Review_status: "reviewed", Measurement_source: "manual",
            Last_edit_method: "manual", Geometry_kind: "circle", Count_valid: "1", Size_valid: "1", Position_valid: "1"};
        var bytes;
        var object;
        roi.setName(candidate.cavity_id);
        roi.setProperties(Object.keys(properties).sort().map(function (key) { return key + ": " + properties[key]; }).join("\n") + "\n");
        bytes = RoiEncoder.saveAsByteArray(roi);
        object = {object_uuid: candidate.object_uuid, cavity_id: candidate.cavity_id,
            candidate_uuid: candidate.candidate_uuid, candidate_id: candidate.candidate_id,
            identity_provenance: {generation_method: "UUIDV4_RANDOM", source: "CTL_P7_MASTER_REVIEW"},
            view_id: candidate.view_id, recipe_sha256: candidate.recipe_sha256,
            proposed_geometry_sha256: candidate.proposed_geometry_sha256,
            final_geometry_sha256: candidate.final_geometry_sha256,
            name: candidate.cavity_id, properties: String(roi.getProperties()),
            bounds: {x: Number(bounds.x), y: Number(bounds.y), width: Number(bounds.width), height: Number(bounds.height)},
            center: {x: geometry.center_x_px, y: geometry.center_y_px},
            diameter_nm: geometry.diameter_px * spatial.scale_x_nm_px,
            geometry: {kind: "circle", center_x_px: geometry.center_x_px, center_y_px: geometry.center_y_px,
                center_x_nm: geometry.center_x_px * spatial.scale_x_nm_px,
                center_y_nm: geometry.center_y_px * spatial.scale_y_nm_px,
                width_px: geometry.diameter_px, height_px: geometry.diameter_px,
                diameter_nm: geometry.diameter_px * spatial.scale_x_nm_px,
                cavity_class: candidate.accepted_cavity_class, review_status: "reviewed",
                measurement_source: "manual", last_edit_method: "manual", count_valid: 1, size_valid: 1, position_valid: 1},
            roi_bytes_base64: String(Base64.getEncoder().encodeToString(bytes)),
            roi_bytes_sha256: sha256Bytes(bytes), roi_bytes: Number(bytes.length)};
        return object;
    }

    function refreshCandidateSummary() {
        var candidates = (state.activeCandidates || []).filter(function (item) { return item.candidate_schema === "CTL_P7_MANUAL_CANDIDATE_V1"; });
        var pending = candidates.filter(function (item) { return item.review_status === "pending"; }).length;
        if (typeof candidateStatusLabel !== "undefined" && candidateStatusLabel) {
            candidateStatusLabel.setText("Propuestas manuales: " + pending + " pendientes · " +
                (candidates.length - pending) + " revisadas. Guardar borrador/revisión para conservar.");
        }
    }

    function requireCandidateContext(allowView) {
        var history = state.editHistory;
        if (state.busy || state.disposed || state.editState !== null || !state.draftReady || !history ||
                state.boundImage !== history.image || state.boundImage.getWindow() !== history.window ||
                history.window === null || RoiManager.getInstance2() !== history.manager || history.contextKey !== historyContextKey()) {
            fail("Abra la sesión y termine EDIT antes de registrar o revisar candidatos.");
        }
        if (!allowView) { assertHistoryContext(false); }
    }

    function applyCandidateMutation(label, change) {
        var before = createHistoryEntry(exportAllFijiRois(), "Antes de revisar candidato");
        var history = state.editHistory;
        if (!history || history.index < 0 || before.signature !== history.entries[history.index].signature) {
            fail("Hay cambios ROI sin registrar. Use Registrar cambios ROI antes de modificar candidatos.");
        }
        try {
            change();
            appendHistoryEntry(createHistoryEntry(exportAllFijiRois(), label));
        } catch (error) {
            restoreMemorySnapshot(before.snapshot, before.dirty);
            throw error;
        }
        state.candidateReview = null;
        state.callbackEpoch += 1;
        rebuildFilteredOverlay();
        refreshCandidateSummary();
    }

    function verifyCandidateMaster(record) {
        var imp = state.boundImage;
        var spatial = inspectionGeometry(imp);
        requireOriginalImage(imp);
        if (record.project_uid !== state.projectUid || record.image_uid !== String(state.activeSession._image_uid) ||
                record.source_sha256 !== String(state.activeSession.source_sha256) ||
                record.width_px !== spatial.width_px || record.height_px !== spatial.height_px || record.bit_depth !== spatial.bit_depth ||
                record.scale_x_nm_px !== spatial.scale_x_nm_px || record.scale_y_nm_px !== spatial.scale_y_nm_px ||
                record.coordinate_origin.x_px !== spatial.x_origin_px || record.coordinate_origin.y_px !== spatial.y_origin_px) {
            fail("La propuesta no corresponde al original, su escala o su proyecto actuales.");
        }
        if (!imp.lock()) { fail("El original está ocupado; espere a que termine su operación."); }
        try {
            verifiedActiveSourceSha(imp);
            if (computeMasterPixelEvidence(imp).sha256 !== record.master_pixel_sha256) { fail("Los píxeles originales no coinciden con la propuesta."); }
        } finally { imp.unlock(); }
    }

    function runCandidateJob(operation, work, publish) {
        var master = state.boundImage;
        var key = historyContextKey();
        var epoch = state.callbackEpoch;
        var fingerprint = createHistoryEntry(exportAllFijiRois(), "Verificación de candidato").signature;
        var startedAt = Number(System.nanoTime());
        setBusy(true, OPERATION_LABELS[operation]);
        startOperationProgress(operation, startedAt);
        new Thread(new JavaAdapter(Runnable, {run: function () {
            var result;
            var error;
            try { result = work(); } catch (caught) { error = caught; }
            onEdt(function () {
                if (state.disposed) { return; }
                setBusy(false, "Listo");
                try {
                    if (error) { throw error; }
                    requireCandidateContext(true);
                    if (state.boundImage !== master || state.callbackEpoch !== epoch || historyContextKey() !== key ||
                            createHistoryEntry(exportAllFijiRois(), "Verificación de candidato").signature !== fingerprint) {
                        fail("Cambió la sesión o su trabajo durante la verificación; repita la acción.");
                    }
                    publish(result);
                    finishOperationProgress(operation, startedAt, "PASS");
                } catch (publishError) { finishOperationProgress(operation, startedAt, "ERROR"); showError(publishError); }
            });
        }}), "CTL-P7-Candidate").start();
    }

    function candidateTimestamp() {
        // The persisted UTC contract admits at most microseconds; Java can
        // provide nanoseconds. Preserve its canonical precision before hashing.
        return String(Packages.java.time.Instant.now()).replace(/(\.\d{6})\d+Z$/, "$1Z")
            .replace(/(\.\d*?[1-9])0+Z$/, "$1Z").replace(/\.0+Z$/, "Z");
    }

    function candidateOperator() {
        var operator = promptText("Identificador de operador (letras sin acentos, números, punto, guion o guion bajo; hasta 64 caracteres):", state.candidateOperator || "");
        if (operator === null) { return null; }
        operator = String(operator).trim();
        if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(operator)) { fail("El identificador debe empezar por letra o número y usar hasta 64 caracteres: letras sin acentos, números, punto, guion o guion bajo."); }
        if (operator.indexOf("..") >= 0 || /\.$/.test(operator) || /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i.test(operator.split(".")[0]) ||
                operator === "NOT_APPLICABLE" || operator === "NA") { fail("Elija un identificador de operador sin nombres reservados, puntos consecutivos ni punto final."); }
        state.candidateOperator = operator;
        return operator;
    }

    function addManualCandidate() {
        var current = WindowManager.getCurrentImage();
        var entries;
        var entry;
        var geometry;
        var operator;
        try {
            requireCandidateContext(true);
            pruneInspectionViews();
            entries = state.inspectionViews.filter(function (view) { return view.image === current && view.original === state.boundImage; });
            if (entries.length !== 1 || entries[0].record.image_role !== "DERIVED_VIEW_CANDIDATE" ||
                    entries[0].record.analysis_session_uid !== state.activeSessionUid) {
                fail("Active la vista de suavizado de esta sesión y dibuje allí una selección circular.");
            }
            if (state.activeCandidates.length >= 500) { fail("Se admiten hasta 500 propuestas por sesión en esta entrega."); }
            entry = entries[0];
            geometry = candidateCircleGeometry(current.getRoi(), current);
            operator = candidateOperator();
            if (operator === null) { return; }
            runCandidateJob("prepare_manual_candidate", function () {
                validateInspectionView(entry);
                verifyCandidateMaster(entry.record);
                return makeManualCandidate(geometry, entry, operator);
            }, function (candidate) {
                if (WindowManager.getCurrentImage() !== current ||
                        canonicalJsonText(candidateCircleGeometry(current.getRoi(), current)) !== canonicalJsonText(geometry)) {
                    fail("Cambió la selección de la vista durante la verificación. Dibuje o seleccione de nuevo la propuesta.");
                }
                applyCandidateMutation("Propuesta manual añadida", function () { state.activeCandidates.push(candidate); });
                statusLabel.setText("Propuesta pendiente añadida; no es una cavidad ni entra en resultados. Use Revisar propuestas sobre el original.");
            });
        } catch (error) { showError(error); }
    }

    function prepareCandidateReview() {
        var candidates;
        var labels;
        var choice;
        var candidate;
        try {
            requireCandidateContext(true);
            candidates = state.activeCandidates.filter(function (item) { return item.candidate_schema === "CTL_P7_MANUAL_CANDIDATE_V1"; });
            if (!candidates.length) { fail("No hay propuestas manuales. Dibuje un círculo en la vista de suavizado y use Añadir propuesta desde vista."); }
            labels = candidates.map(function (item, index) { return (index + 1) + ". " +
                (item.review_status === "pending" ? "Pendiente" : item.review_decision) + " · " +
                item.candidate_id.substring(0, 13) + " · vista " + item.view_id.substring(5, 13); });
            choice = JOptionPane.showInputDialog(frame, "Seleccione una propuesta. Las pendientes se muestran sobre el original para ajustar y resolver.",
                "Revisar propuestas", JOptionPane.QUESTION_MESSAGE, null, labels, labels[0]);
            if (choice === null) { return; }
            candidate = candidates[labels.indexOf(String(choice))];
            if (!candidate) { fail("Seleccione una propuesta de la lista."); }
            if (candidate.review_status !== "pending") {
                JOptionPane.showMessageDialog(frame, "Decisión: " + candidate.review_decision + "\nOperador: " + candidate.reviewed_by +
                    "\nFecha: " + candidate.reviewed_at + "\nCavidad: " + (candidate.cavity_id || "Ninguna") +
                    "\nVista de origen: " + candidate.view_id, "Propuesta revisada", JOptionPane.INFORMATION_MESSAGE);
                return;
            }
            if (sha256Text(canonicalJsonText(candidate.source_view.record)) !== candidate.source_view.record_sha256 ||
                    sha256Text(canonicalJsonText(candidate.proposed_geometry)) !== candidate.proposed_geometry_sha256) {
                fail("La propuesta no supera su comprobación de integridad.");
            }
            runCandidateJob("review_manual_candidate", function () { verifyCandidateMaster(candidate.source_view.record); }, function () {
                var geometry = candidate.proposed_geometry;
                var roi = candidateRoi(geometry);
                candidateCircleGeometry(roi, state.boundImage);
                state.boundImage.setRoi(roi);
                state.candidateReview = {candidate_uuid: candidate.candidate_uuid, contextKey: historyContextKey(),
                    epoch: state.callbackEpoch};
                returnToOriginal();
                statusLabel.setText("Propuesta sobre el ORIGINAL. Ajuste el círculo si procede y pulse Resolver propuesta. La selección aún no es una cavidad.");
            });
        } catch (error) { showError(error); }
    }

    function resolveCandidateReview() {
        var review = state.candidateReview;
        var candidate;
        var choice;
        var decision;
        var geometry;
        var operator;
        var nextId = 0;
        try {
            requireCandidateContext(false);
            if (!review || review.contextKey !== historyContextKey() || review.epoch !== state.callbackEpoch) {
                fail("Use Revisar propuestas para mostrar una propuesta pendiente sobre el original.");
            }
            candidate = state.activeCandidates.filter(function (item) { return item.candidate_uuid === review.candidate_uuid; })[0];
            if (!candidate || candidate.review_status !== "pending") { fail("Esta propuesta ya no está pendiente."); }
            choice = JOptionPane.showOptionDialog(frame,
                "Revise la selección circular sobre el original. Aceptar crea una cavidad con la clase elegida; rechazar conserva solo la propuesta.",
                "Resolver propuesta", JOptionPane.DEFAULT_OPTION, JOptionPane.QUESTION_MESSAGE, null,
                ["Aceptar confirmada", "Marcar incierta", "Posible artefacto", "Rechazar", "Cancelar"], "Cancelar");
            if (choice < 0 || choice > 3) { return; }
            decision = ["accept", "mark_uncertain", "mark_possible_artifact", "reject"][choice];
            geometry = choice === 3 ? null : candidateCircleGeometry(state.boundImage.getRoi(), state.boundImage);
            operator = candidateOperator();
            if (operator === null) { return; }
            runCandidateJob("review_manual_candidate", function () { verifyCandidateMaster(candidate.source_view.record); }, function () {
                var roi;
                var reviewed;
                var object;
                if (WindowManager.getCurrentImage() !== state.boundImage || state.candidateReview !== review ||
                        (geometry !== null && canonicalJsonText(candidateCircleGeometry(state.boundImage.getRoi(), state.boundImage)) !== canonicalJsonText(geometry))) {
                    fail("La selección original cambió durante la verificación. Revísela antes de resolver.");
                }
                if (geometry !== null) {
                    exportAllFijiRois().objects.forEach(function (item) { nextId = Math.max(nextId, Number(String(item.cavity_id).substring(4))); });
                    if (nextId >= 999999) { fail("Se agotaron los identificadores de cavidades de esta sesión."); }
                    roi = candidateRoi(geometry);
                }
                reviewed = reviewedCandidate(candidate, geometry, decision, operator,
                    geometry === null ? null : String(UUID.randomUUID()),
                    geometry === null ? null : "CAV_" + ("000000" + (nextId + 1)).slice(-6));
                if (roi) { object = candidateObject(roi, reviewed); }
                applyCandidateMutation("Propuesta " + reviewed.review_decision, function () {
                    state.activeCandidates = state.activeCandidates.map(function (item) { return item.candidate_uuid === candidate.candidate_uuid ? reviewed : item; });
                    if (roi) { state.workingObjects.push(object); RoiManager.getInstance2().addRoi(roi); }
                });
                state.boundImage.killRoi();
                statusLabel.setText(roi ? "Cavidad " + reviewed.cavity_id + " creada sobre el original (" + reviewed.accepted_cavity_class +
                    "). Guarde borrador o revisión para conservarla." : "Propuesta rechazada sin crear cavidad. La decisión se conserva al guardar borrador o revisión.");
            });
        } catch (error) { showError(error); }
    }

    function resetEditHistory() {
        state.editHistory = null;
        state.historyNotice = "Historial: abra una sesión para registrar cambios.";
        refreshHistoryControls();
    }

    function historyContextKey() {
        var active = state.activeSession;
        var imp = state.boundImage;
        var spatial;
        if (!active || !imp || state.activeSessionUid === null) { fail("No hay una sesión preparada para el historial."); }
        spatial = normalizedSpatialCalibration(imp);
        // Epochs and display preferences do not change the scientific working base.
        // Undo affects ROI only; pixel evidence is still checked by publication/recovery.
        return JSON.stringify([state.projectPath, state.projectUid, state.activeSessionUid,
            state.activeGeneration, active._image_uid, active.working_state_sha256,
            active.current_revision_pointer_sha256, active.source_sha256,
            Number(imp.getWidth()), Number(imp.getHeight()), Number(imp.getBitDepth()),
            spatial.scale_x_nm_px, spatial.scale_y_nm_px,
            String(imp.getProperty("CTL.P1.source_sha256") || ""),
            String(imp.getProperty("CTL.P1.source_sha256_actual") || "")]);
    }

    function assertHistoryContext(allowEdit) {
        var history = state.editHistory;
        if (state.busy || state.disposed || (!allowEdit && state.editState !== null)) {
            fail("Termine la operación o confirme/cancele EDIT antes de usar el historial.");
        }
        if (!history || !state.draftReady || state.boundImage !== WindowManager.getCurrentImage() ||
                state.boundImage !== history.image || RoiManager.getInstance2() !== history.manager ||
                state.boundImage.getWindow() !== history.window || history.window === null ||
                history.contextKey !== historyContextKey()) {
            fail("El contexto del historial cambió. Active la imagen original o reabra la sesión antes de continuar.");
        }
    }

    function createHistoryEntry(snapshot, label) {
        var manager = RoiManager.getInstance2();
        var payload;
        if (!manager || Number(manager.getCount()) !== Number(snapshot.roi_count)) {
            fail("Hay ROI sin clasificar. Clasifíquelas antes de registrar o restaurar un paso completo.");
        }
        payload = jsonClone({objects: snapshot.objects, geometries: snapshot.geometries,
            candidates: state.activeCandidates, roi_zip_sha256: snapshot.roi_zip_sha256,
            snapshot_sha256: snapshot.snapshot_sha256});
        return {snapshot: payload, label: String(label),
            signature: sha256Text(canonicalJsonText({objects: payload.objects,
                geometries: payload.geometries, candidates: payload.candidates,
                roi_zip_sha256: payload.roi_zip_sha256})),
            bytes: JSON.stringify(payload).length * 2,
            dirty: state.geometryDirty || canonicalJsonText({geometries: payload.geometries}) !==
                canonicalJsonText({geometries: state.activeGeometries})};
    }

    function initializeEditHistory() {
        resetEditHistory();
        try {
            state.editHistory = {entries: [], index: -1, bytes: 0,
                contextKey: historyContextKey(), image: state.boundImage,
                window: state.boundImage.getWindow(),
                manager: RoiManager.getInstance2()};
            appendHistoryEntry(createHistoryEntry(exportAllFijiRois(), "Estado de partida"));
        } catch (error) {
            state.editHistory = null;
            state.historyNotice = "Historial no disponible: " + error;
        }
        refreshHistoryControls();
    }

    function appendHistoryEntry(entry) {
        var history = state.editHistory;
        var removed = false;
        if (history.index >= 0 && history.entries[history.index].signature === entry.signature) { return false; }
        if (entry.bytes > HISTORY_MAX_BYTES) {
            history.entries = []; history.index = -1; history.bytes = 0;
            state.historyNotice = "La edición supera el límite del historial. Use Guardar borrador; las ROI se conservan.";
            refreshHistoryControls();
            return false;
        }
        while (history.entries.length > history.index + 1) {
            history.bytes -= history.entries.pop().bytes;
        }
        history.entries.push(entry);
        history.bytes += entry.bytes;
        while (history.entries.length > HISTORY_MAX_STEPS + 1 || history.bytes > HISTORY_MAX_BYTES) {
            history.bytes -= history.entries.shift().bytes;
            removed = true;
        }
        history.index = history.entries.length - 1;
        state.historyNotice = removed ? "Límite de historial: se conserva el trabajo y los pasos más recientes." : "";
        refreshHistoryControls();
        return true;
    }

    function recordEditHistory(label, allowEdit) {
        assertHistoryContext(allowEdit);
        return appendHistoryEntry(createHistoryEntry(exportAllFijiRois(), label));
    }

    function refreshHistoryControls() {
        var history = state.editHistory;
        var ready = Boolean(history) && state.draftReady && !state.busy && !state.disposed && state.editState === null;
        if (undoButton) { undoButton.setEnabled(ready && history.index > 0); }
        if (redoButton) { redoButton.setEnabled(ready && history.index >= 0 && history.index < history.entries.length - 1); }
        if (recordHistoryButton) { recordHistoryButton.setEnabled(ready); }
        if (historyStatusLabel) {
            historyStatusLabel.setText(state.historyNotice || (history ?
                "Historial: " + Math.max(0, history.index) + " para deshacer · " +
                Math.max(0, history.entries.length - history.index - 1) + " para rehacer. Solo en esta sesión abierta." :
                "Historial: abra una sesión para registrar cambios."));
        }
        refreshCandidateSummary();
    }

    function travelEditHistory(direction) {
        var history;
        var current;
        var targetIndex;
        var target;
        var label;
        try {
            assertHistoryContext(false);
            if (direction !== -1 && direction !== 1) { fail("Dirección de historial inválida."); }
            history = state.editHistory;
            current = createHistoryEntry(exportAllFijiRois(), "Cambios en ROI Manager");
            if (history.index < 0 || current.signature !== history.entries[history.index].signature) {
                statusLabel.setText("Hay cambios nuevos en ROI Manager. Pulse Registrar cambios ROI antes de deshacer o rehacer.");
                return false;
            }
            targetIndex = history.index + direction;
            if (targetIndex < 0 || targetIndex >= history.entries.length) { return false; }
            target = history.entries[targetIndex];
            label = direction < 0 ? history.entries[history.index].label : target.label;
            restoreMemorySnapshot(target.snapshot, target.dirty);
            // Advance only after exact restoration succeeds. No draft was saved here.
            history.index = targetIndex;
            state.historyNotice = "";
            refreshHistoryControls();
            statusLabel.setText((direction < 0 ? "Deshecho: " : "Rehecho: ") + label + ". La revisión publicada no cambia.");
            return true;
        } catch (error) { showError(error); return false; }
    }

    function resetDraftState() {
        resetEditHistory();
        state.candidateReview = null;
        state.draftReady = false;
        state.draftImageContext = null;
        state.draftLastSnapshotSha256 = null;
        state.draftPaused = false;
        if (draftStatusLabel) { draftStatusLabel.setText("Borradores: abra una sesión para recuperar o guardar su trabajo."); }
    }

    function draftImageSignature(context) {
        return JSON.stringify([Number(context.width_px), Number(context.height_px),
            Number(context.bit_depth), Number(context.scale_x_nm_px), Number(context.scale_y_nm_px)]);
    }

    function draftContextArguments(refreshImage) {
        var active = state.activeSession;
        var imp = state.boundImage;
        var spatial;
        var live;
        if (!state.draftReady || active === null || imp === null ||
                imp !== WindowManager.getCurrentImage() || state.editState !== null) {
            fail("Borrador no disponible: termine EDIT y active la imagen de esta sesión.");
        }
        spatial = normalizedSpatialCalibration(imp);
        live = {width_px: Number(imp.getWidth()), height_px: Number(imp.getHeight()),
            bit_depth: Number(imp.getBitDepth()), scale_x_nm_px: spatial.scale_x_nm_px,
            scale_y_nm_px: spatial.scale_y_nm_px};
        if (state.draftImageContext !== null &&
                draftImageSignature(live) !== draftImageSignature(state.draftImageContext)) {
            fail("La imagen o su escala cambió. Reabra la sesión antes de guardar un borrador.");
        }
        if (refreshImage || state.draftImageContext === null) {
            state.draftImageContext = currentImageContext("PROMPT6_DRAFT", "1");
        }
        return {project_root: state.projectPath, image_uid: String(active._image_uid),
            analysis_session_uid: state.activeSessionUid,
            expected_working_sha256: String(active.working_state_sha256),
            expected_revision_pointer_sha256: String(active.current_revision_pointer_sha256),
            image_context: jsonClone(state.draftImageContext)};
    }

    function draftFailure(error, automatic) {
        state.draftPaused = true;
        draftStatusLabel.setText("Borrador no guardado/verificado. Autoguardado pausado; use Guardar borrador para reintentar.");
        draftStatusLabel.setToolTipText(String(error));
        if (!automatic) { showError(error); }
    }

    function describeDraft(result) {
        var status = String(result.draft_status || "");
        var message;
        if (status === "AVAILABLE") {
            message = "Hay un borrador del " + String(result.draft.saved_at) + ". Pulse Recuperar borrador para revisarlo.";
        } else if (status === "MISSING" || status === "DISCARDED") {
            message = "Sin borrador pendiente. Puede usar Guardar borrador o activar el autoguardado.";
        } else {
            message = status === "STALE" ?
                "Borrador conservado: la revisión, imagen o escala de partida ha cambiado. No se restaura automáticamente." :
                "Borrador conservado: no supera la comprobación de integridad. Se requiere revisar la copia antes de recuperarla.";
            state.draftPaused = true; // Do not hide a stale/corrupt draft behind a new automatic snapshot.
        }
        draftStatusLabel.setText(message);
        draftStatusLabel.setToolTipText(message + (result.reason ? " Detalle: " + String(result.reason) : ""));
    }

    function initializeDraftState(imageContext) {
        state.draftReady = true;
        state.draftImageContext = imageContext === null ? null : jsonClone(imageContext);
        state.draftLastSnapshotSha256 = state.baselineRoiSha256;
        state.draftPaused = false;
        initializeEditHistory();
        draftStatusLabel.setText("Borradores separados de revisiones. Use Recuperar borrador para buscar una copia anterior.");
        refreshDisplayControls();
        if (imageContext !== null) {
            invokeOperation("load_draft", draftContextArguments(false), describeDraft, null,
                function (error) { draftFailure(error, true); });
        }
    }

    function saveCurrentDraft(automatic, continuation) {
        var args;
        var snapshot;
        if (state.busy || !state.draftReady || state.editState !== null ||
                state.disposed || (automatic && (!state.draftAutosave || state.draftPaused))) { return; }
        try {
            // The expensive pixel evidence is reused only for auxiliary autosaves.
            // Explicit save/recovery recomputes it; publication keeps its own checks.
            args = draftContextArguments(!automatic);
            snapshot = exportAllFijiRois();
            if (RoiManager.getInstance2() !== null &&
                    Number(RoiManager.getInstance2().getCount()) !== Number(snapshot.roi_count)) {
                fail("Hay ROI sin clasificar en ROI Manager. Clasifíquelas antes de guardar un borrador completo.");
            }
            // Undo may return to the published baseline after a different draft
            // was saved. Save that return too, so recovery cannot revive undone work.
            if (automatic && snapshot.snapshot_sha256 === state.draftLastSnapshotSha256) { return; }
            args.objects = snapshot.objects;
            args.candidates = jsonClone(state.activeCandidates);
            args.geometries = snapshot.geometries;
            args.roi_zip_sha256 = snapshot.roi_zip_sha256;
            args.snapshot_sha256 = snapshot.snapshot_sha256;
        } catch (error) { draftFailure(error, automatic); return; }
        invokeOperation("save_draft", args, function (result) {
            if (result.draft_status !== "SAVED" && result.draft_status !== "UNCHANGED") {
                draftFailure("El borrador no devolvió confirmación de guardado.", automatic); return;
            }
            state.draftLastSnapshotSha256 = snapshot.snapshot_sha256;
            state.draftPaused = false;
            draftStatusLabel.setText("Borrador guardado: " + String(result.saved_at) +
                ". La revisión publicada sigue intacta.");
            draftStatusLabel.setToolTipText("Copia recuperable en autosave/prompt6 de esta sesión. EDIT debe confirmarse primero.");
            if (continuation) {
                try {
                    draftContextArguments(false);
                    if (exportAllFijiRois().snapshot_sha256 !== snapshot.snapshot_sha256) {
                        fail("Hay cambios posteriores al borrador; guárdelos antes de salir o cambiar de sesión.");
                    }
                } catch (changedDuringSave) {
                    statusLabel.setText("El borrador se guardó, pero el contexto o las ROI cambiaron después. Se mantiene la sesión abierta.");
                    return;
                }
                continuation();
            }
        }, null, function (error) { draftFailure(error, automatic); });
    }

    function decodeDraftCavities(objects) {
        var decoded = [];
        var i;
        var object;
        var roi;
        var bytes;
        var uid;
        if (!Array.isArray(objects)) { fail("Inventario de cavidades del borrador inválido."); }
        for (i = 0; i < objects.length; i += 1) {
            object = objects[i];
            bytes = Base64.getDecoder().decode(String(object.roi_bytes_base64 || ""));
            if (sha256Bytes(bytes) !== String(object.roi_bytes_sha256 || "")) { fail("Hash ROI del borrador incorrecto."); }
            roi = new RoiDecoder(bytes, String(object.name || "")).getRoi();
            if (roi === null || normalizeRoiType(roi) !== "cavity" ||
                    String(roiProperty(roi, "Cavity_id") || roiProperty(roi, "cavity_id")) !== String(object.cavity_id) ||
                    roiBytesSha256(roi) !== String(object.roi_bytes_sha256)) { fail("Identidad ROI del borrador incorrecta."); }
            uid = String(roiProperty(roi, "Object_uuid") || roiProperty(roi, "object_uuid") || "").toLowerCase();
            if (uid !== String(object.object_uuid || "").toLowerCase()) { fail("UUID ROI del borrador incorrecto."); }
            // New cavities intentionally retain an empty UUID until normal revision publication.
            decoded.push(roi);
        }
        return decoded;
    }

    function restoreMemorySnapshot(snapshot, dirty) {
        var manager = RoiManager.getInstance2();
        var oldRois = [];
        var oldGeometries = state.activeGeometries;
        var oldCandidates = state.activeCandidates;
        var oldWorkingObjects = state.workingObjects;
        var oldDirty = state.geometryDirty;
        var decoded;
        var restored;
        var i;
        if (!snapshot || !manager) { fail("Instantánea auxiliar inválida."); }
        decoded = decodeDraftCavities(snapshot.objects); // Decode before touching the working canvas.
        for (i = 0; i < Number(manager.getCount()); i += 1) { oldRois.push(manager.getRoi(i).clone()); }
        try {
            manager.reset();
            for (i = 0; i < decoded.length; i += 1) { manager.addRoi(decoded[i]); }
            loadGeometriesIntoRoiManager(snapshot.geometries);
            state.activeGeometries = jsonClone(snapshot.geometries);
            state.activeCandidates = jsonClone(snapshot.candidates);
            state.workingObjects = jsonClone(snapshot.objects.filter(function (object) {
                return object.object_uuid && !state.activeObjects.some(function (base) {
                    return String(base.object_uuid) === String(object.object_uuid);
                });
            }));
            // Keep the verified base separate from newly accepted objects with UUIDs.
            restored = exportAllFijiRois();
            // The UI dirty fingerprint uses JSON.stringify and is sensitive to
            // property insertion order. Storage uses canonical JSON, which sorts
            // keys. Compare the exact ROI ZIP bytes and canonical field values
            // instead: key order must not make an intact draft unrecoverable.
            if (restored.roi_zip_sha256 !== String(snapshot.roi_zip_sha256) ||
                    canonicalJsonText({objects: restored.objects, geometries: restored.geometries,
                        candidates: state.activeCandidates}) !==
                    canonicalJsonText({objects: snapshot.objects, geometries: snapshot.geometries,
                        candidates: snapshot.candidates})) {
                fail("La copia recuperada no reproduce exactamente las ROI y los datos guardados.");
            }
            state.geometryDirty = dirty;
        } catch (error) {
            manager.reset();
            for (i = 0; i < oldRois.length; i += 1) { manager.addRoi(oldRois[i]); }
            state.activeGeometries = oldGeometries;
            state.activeCandidates = oldCandidates;
            state.workingObjects = oldWorkingObjects;
            state.geometryDirty = oldDirty;
            rebuildFilteredOverlay();
            throw error;
        }
        state.boundImage.killRoi();
        state.candidateReview = null;
        state.displayEpoch += 1;
        state.callbackEpoch += 1;
        rebuildFilteredOverlay();
        installCavityClickListener();
        refreshDisplayControls();
        return restored;
    }

    function restoreDraftToMemory(draft) {
        var restored;
        if (draft.authority !== false) { fail("Borrador auxiliar inválido."); }
        restored = restoreMemorySnapshot(draft.snapshot, true);
        state.draftLastSnapshotSha256 = restored.snapshot_sha256;
        initializeEditHistory();
        draftStatusLabel.setText("Borrador recuperado en memoria. Revise los cambios y use Guardar revisión para publicarlos.");
    }

    function recoverCurrentDraft(discard) {
        var args;
        var liveSnapshot;
        if (state.busy || state.editState !== null) { return; }
        try { args = draftContextArguments(false); liveSnapshot = exportAllFijiRois().snapshot_sha256; }
        catch (error) { draftFailure(error, false); return; }
        invokeOperation("load_draft", args, function (result) {
            var choice;
            var confirmedImage;
            if (result.draft_status !== "AVAILABLE") { describeDraft(result); return; }
            choice = JOptionPane.showConfirmDialog(frame, discard ?
                "¿Descartar este borrador? Su historial se conserva y las ROI actuales no cambian." :
                "Recuperar el borrador del " + String(result.draft.saved_at) +
                " reemplazará las ROI actuales en memoria. La revisión publicada no cambia. ¿Continuar?",
                discard ? "Descartar borrador" : "Recuperar borrador", JOptionPane.YES_NO_OPTION,
                JOptionPane.WARNING_MESSAGE);
            if (choice !== JOptionPane.YES_OPTION) { return; }
            if (discard) {
                invokeOperation("discard_draft", {project_root: state.projectPath,
                    image_uid: String(state.activeSession._image_uid), analysis_session_uid: state.activeSessionUid,
                    draft_id: result.draft_id, expected_draft_sha256: result.draft_sha256}, function () {
                    state.draftPaused = true; // Resume via an explicit save or re-enabling the checkbox.
                    draftStatusLabel.setText("Borrador descartado. Autoguardado pausado hasta que vuelva a activarlo o guarde otro borrador.");
                });
                return;
            }
            try {
                confirmedImage = currentImageContext("PROMPT6_DRAFT_RECOVERY", "1");
                if (draftImageSignature(confirmedImage) !== draftImageSignature(args.image_context) ||
                        String(confirmedImage.master_pixel_evidence.sha256) !==
                        String(args.image_context.master_pixel_evidence.sha256)) {
                    fail("La imagen o sus píxeles cambiaron durante la recuperación. No se aplicó el borrador.");
                }
                if (exportAllFijiRois().snapshot_sha256 !== liveSnapshot) { fail("Las ROI cambiaron durante la consulta; vuelva a recuperar el borrador."); }
                restoreDraftToMemory(result.draft);
            } catch (error) { draftFailure(error, false); }
        });
    }

    function requestManagerClose() {
        if (state.busy) { statusLabel.setText("Espere a que termine la operación antes de cerrar."); return; }
        resolvePendingChanges(function () { frame.dispose(); });
    }

    function saveCurrentRevision(continuation) {
        var snapshot;
        var active = state.activeSession;
        if (active === null) { showError("No hay una sesión activa ligada al último inspect."); return; }
        if (state.editState !== null) {
            statusLabel.setText("Confirme o cancele EDIT antes de guardar una revisión.");
            return;
        }
        snapshot = exportAllFijiRois();
        var args = {
            project_root: state.projectPath,
            image_uid: String(active._image_uid),
            analysis_session_uid: state.activeSessionUid,
            objects: snapshot.objects,
            candidates: jsonClone(state.activeCandidates),
            geometries: snapshot.geometries,
            roi_zip_sha256: snapshot.roi_zip_sha256,
            expected_working_sha256: String(active.working_state_sha256),
            expected_revision_pointer_sha256: String(active.current_revision_pointer_sha256),
            image_context: currentImageContext("PROMPT3_MASKS_SAVE_REVISION", "1")
        };
        invokeOperation("save_revision", args, function (result) {
            var uid = state.activeSessionUid;
            if (!result.project) { showError("save_revision no devolvió el proyecto verificado."); return; }
            fillSessions(result.project);
            state.activeSession = sessionByUid(uid);
            if (state.activeSession === null) { showError("La sesión guardada desapareció del modelo verificado."); return; }
            state.activeObjects = jsonClone(snapshot.objects);
            state.workingObjects = [];
            state.candidateReview = null;
            state.activeGeneration = Number(state.activeSession.generation);
            try {
                loadObjectsIntoRoiManager(state.activeObjects, state.cloneRoiIdentityBridge);
                applyGeometryState(result.geometry_state);
                state.baselineRoiSha256 = exportAllFijiRois().snapshot_sha256;
            } catch (geometrySaveError) {
                clearActiveContext(true);
                showError("La revisión se guardó, pero su geometría devuelta no pudo ligarse: " + geometrySaveError);
                return;
            }
            state.geometryDirty = false;
            state.displayEpoch += 1;
            state.callbackEpoch += 1;
            rebuildFilteredOverlay();
            installCavityClickListener();
            refreshDisplayControls();
            state.draftLastSnapshotSha256 = state.baselineRoiSha256;
            initializeEditHistory();
            draftStatusLabel.setText("Revisión guardada. Los borradores anteriores se conservan como historial de su base anterior.");
            if (continuation) { continuation(); }
        });
    }

    function resolvePendingChanges(continuation) {
        var snapshot;
        var options;
        var choice;
        if (state.editState !== null) {
            statusLabel.setText("Confirme o cancele EDIT antes de cambiar de proyecto o sesión.");
            refreshDisplayControls();
            return;
        }
        if (state.activeSessionUid === null || state.baselineRoiSha256 === null) {
            continuation();
            return;
        }
        snapshot = exportAllFijiRois();
        if (snapshot.snapshot_sha256 === state.baselineRoiSha256) {
            continuation();
            return;
        }
        options = ["Guardar revisión", "Guardar borrador", "Continuar sin guardar", "Cancelar"];
        choice = JOptionPane.showOptionDialog(frame,
            "Hay cambios de ROI o candidatos sin guardar. Puede guardar una revisión o un borrador recuperable. Los borradores existentes se conservan.",
            "Cambios pendientes", JOptionPane.DEFAULT_OPTION, JOptionPane.WARNING_MESSAGE,
            null, options, options[3]);
        if (choice === 0) {
            saveCurrentRevision(continuation);
        } else if (choice === 1) {
            saveCurrentDraft(false, continuation);
        } else if (choice === 2) {
            continuation();
        } else {
            statusLabel.setText("Operación cancelada; no se llamó al companion.");
            return; // Cancelar termina localmente y no produce I/O externo.
        }
    }

    function selectExplicitSession() {
        try { requireOriginalImage(WindowManager.getCurrentImage()); }
        catch (viewError) { showError(viewError); return; }
        var session = selectedSession();
        if (session === null) { return; }
        if (session._legacy_image) {
            JOptionPane.showMessageDialog(frame,
                JSON.stringify(session._legacy_image, null, 2),
                "LEGACY_SESSION read-only", JOptionPane.INFORMATION_MESSAGE);
            return;
        }
        resolvePendingChanges(function () {
            var args = {
                project_root: state.projectPath,
                image_uid: String(session._image_uid),
                analysis_session_uid: String(session.analysis_session_uid),
                expected_current_generation: Number(session.generation),
                expected_registry_sha256: String(session._session_registry_sha256),
                cancel: false
            };
            invokeOperation("select_session", args, function (result) {
                var selectedUid = result.selection && result.selection.selected_session_uid;
                bindActivePayload(result, selectedUid, "Sesión activa");
            });
        });
    }

    function sessionOperation(operation, extra, refreshAfter) {
        var session = selectedSession();
        var args;
        if (session === null) { return; }
        if (session._legacy_image) {
            showError("LEGACY_SESSION es estrictamente read-only; migre por copia para editar.");
            return;
        }
        args = extra || {};
        args.project_root = state.projectPath;
        args.image_uid = String(session._image_uid);
        args.analysis_session_uid = String(session.analysis_session_uid);
        args.expected_current_generation = Number(session.generation);
        args.expected_registry_sha256 = String(session._session_registry_sha256);
        invokeOperation(operation, args, function () {
            if (refreshAfter) { inspectProject(state.projectPath); }
        });
    }

    function addButton(panel, label, handler) {
        var button = new JButton(label);
        button.addActionListener(new JavaAdapter(ActionListener, {actionPerformed: handler}));
        panel.add(button);
        actionButtons.push(button);
        return button;
    }

    function buildUi() {
        var oldFrames = Frame.getFrames();
        var i;
        var top = new JPanel(new BorderLayout(6, 6));
        var projectButtons = new JPanel(new FlowLayout(FlowLayout.LEFT));
        var geometryButtons = new JPanel(new GridLayout(0, 4, 4, 4));
        var sessionButtons = new JPanel(new GridLayout(0, 4, 4, 4));
        var draftControls = new JPanel(new FlowLayout(FlowLayout.LEFT));
        var viewControls = new JPanel(new FlowLayout(FlowLayout.LEFT));
        var candidateControls = new JPanel(new FlowLayout(FlowLayout.LEFT));
        var auxiliaryControls = new JPanel(new GridLayout(0, 1));
        var autosaveCheckBox;
        var controls = new JPanel(new BorderLayout(4, 4));
        var sessionNavigation = new JPanel(new BorderLayout(6, 6));
        var sessionHeading = new JPanel(new BorderLayout(6, 6));
        var detailsCheckBox;
        var bottom = new JPanel(new BorderLayout(6, 6));
        var statusPanel = new JPanel(new GridLayout(0, 1, 0, 3));
        for (i = 0; i < oldFrames.length; i += 1) {
            if (String(oldFrames[i].getTitle()) === WINDOW_TITLE) { oldFrames[i].dispose(); }
        }
        frame = new JFrame(WINDOW_TITLE);
        frame.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE);
        projectField = new JTextField(70);
        projectField.setEditable(false);
        projectField.setToolTipText("Ruta informativa. Use Crear proyecto o Abrir / actualizar proyecto.");
        top.add(new JLabel("Proyecto:"), BorderLayout.WEST);
        top.add(projectField, BorderLayout.CENTER);
        refreshButton = new JButton("Abrir / actualizar proyecto");
        refreshButton.addActionListener(new JavaAdapter(ActionListener, {actionPerformed: function () {
            var path = chooseDirectory("Seleccione el proyecto Cavity TEM Light");
            if (path !== null) {
                resolvePendingChanges(function () { inspectProject(path); });
            }
        }}));
        top.add(refreshButton, BorderLayout.EAST);
        addButton(projectButtons, "Crear proyecto", function () {
            try { createProjectFromUi(); } catch (error) { showError(error); }
        });
        addButton(projectButtons, "Incorporar imagen TEM", function () {
            try { addSourceImageFromUi(); } catch (error) { showError(error); }
        });
        addButton(projectButtons, "Abrir imagen y sesión", function () {
            try { openSourceAndSession(); } catch (error) { showError(error); }
        });
        projectButtons.add(new JLabel("1. Proyecto  ·  2. Imagen  ·  3. Seleccione una sesión para abrirla"));
        top.add(projectButtons, BorderLayout.SOUTH);

        tableModel = new JavaAdapter(DefaultTableModel, {
            isCellEditable: function () { return false; }
        });
        tableModel.setColumnIdentifiers(Java.to(TABLE_COLUMNS, "java.lang.Object[]"));
        table = new JTable(tableModel);
        table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        table.setAutoCreateRowSorter(true);
        table.setRowHeight(24);
        table.setToolTipText("Cavidades: total de objetos guardados en la sesión, sin filtrar por " +
            "confirmación. Resultado identifica el RUN actual; no indica su validez científica. " +
            "Seleccione una fila y pulse Abrir sesión para activarla.");
        table.setPreferredScrollableViewportSize(new Dimension(1250, 260));
        rebuildSessionTableColumns();
        activeSessionLabel = new JLabel("");
        activeSessionLabel.setForeground(new Color(20, 70, 120));
        detailsCheckBox = new JCheckBox("Detalles", state.sessionDetailsVisible);
        detailsCheckBox.setToolTipText("Mostrar identificadores, estados técnicos y datos de trazabilidad. " +
            "Desplace la tabla horizontalmente para verlos.");
        detailsCheckBox.addActionListener(new JavaAdapter(ActionListener, {actionPerformed: function () {
            state.sessionDetailsVisible = detailsCheckBox.isSelected();
            applySessionTableColumns();
        }}));
        sessionHeading.add(activeSessionLabel, BorderLayout.CENTER);
        sessionHeading.add(detailsCheckBox, BorderLayout.EAST);
        sessionNavigation.add(sessionHeading, BorderLayout.NORTH);
        sessionNavigation.add(new JScrollPane(table), BorderLayout.CENTER);

        saveDraftButton = addButton(draftControls, "Guardar borrador", function () { saveCurrentDraft(false); });
        recoverDraftButton = addButton(draftControls, "Recuperar borrador", function () { recoverCurrentDraft(false); });
        discardDraftButton = addButton(draftControls, "Descartar borrador", function () { recoverCurrentDraft(true); });
        autosaveCheckBox = new JCheckBox("Autoguardar cambios cada 60 s", state.draftAutosave);
        autosaveCheckBox.setToolTipText("Solo cambios confirmados en ROI Manager. Durante EDIT, confirme primero. Nunca publica una revisión.");
        autosaveCheckBox.addActionListener(new JavaAdapter(ActionListener, {actionPerformed: function () {
            state.draftAutosave = autosaveCheckBox.isSelected();
            state.draftPaused = false;
            draftStatusLabel.setText(state.draftAutosave ?
                "Autoguardado activado: se copiarán los cambios confirmados cada 60 s." :
                "Autoguardado desactivado. Puede usar Guardar borrador manualmente.");
        }}));
        draftControls.add(autosaveCheckBox);
        addButton(viewControls, "Crear vista de inspección", createInspectionView);
        addButton(viewControls, "Volver al original", returnToOriginal);
        addButton(viewControls, "Guardar receta de vista", saveInspectionRecipe);
        addButton(viewControls, "Reaplicar receta guardada", reapplyInspectionRecipe);
        viewControls.add(new JLabel("Inspección visual; mida y edite en el original."));
        addButton(candidateControls, "Añadir propuesta desde vista", addManualCandidate);
        addButton(candidateControls, "Revisar propuestas", prepareCandidateReview);
        addButton(candidateControls, "Resolver propuesta", resolveCandidateReview);
        candidateStatusLabel = new JLabel("Propuestas manuales: abra una sesión.");
        candidateControls.add(candidateStatusLabel);

        maskModeButton = addButton(geometryButtons, "Áreas válidas: OUTLINE", function () {
            toggleDisplayMode("analysis_mask");
        });
        exclusionModeButton = addButton(geometryButtons, "Exclusiones: OUTLINE", function () {
            toggleDisplayMode("exclusion");
        });
        surfaceModeButton = addButton(geometryButtons, "Superficie: OUTLINE", function () {
            toggleDisplayMode("surface");
        });
        editButton = addButton(geometryButtons, "Editar geometría de análisis", beginGeometryEdit);
        confirmEditButton = addButton(geometryButtons, "Confirmar EDIT", function () {
            finishGeometryEdit(true, false);
        });
        cancelEditButton = addButton(geometryButtons, "Cancelar EDIT", function () {
            finishGeometryEdit(false, false);
        });
        restoreOutlineButton = addButton(geometryButtons, "Restaurar visualización recomendada", function () {
            persistDisplayMode("all", "OUTLINE");
        });
        temporaryRevealButton = addButton(geometryButtons, "Mostrar todo 3 s", showEverythingTemporarily);
        undoButton = addButton(geometryButtons, "Deshacer", function () { travelEditHistory(-1); });
        redoButton = addButton(geometryButtons, "Rehacer", function () { travelEditHistory(1); });
        recordHistoryButton = addButton(geometryButtons, "Registrar cambios ROI", function () {
            try {
                statusLabel.setText(recordEditHistory("Cambios en ROI Manager", false) ?
                    "Cambios registrados como un paso. Puede deshacerlos; aún no se han guardado en disco." :
                    "No se añadió un paso. Consulte el estado del historial.");
            } catch (historyError) { showError(historyError); }
        });
        undoButton.setMnemonic(68);
        redoButton.setMnemonic(82);
        recordHistoryButton.setMnemonic(84);
        undoButton.setToolTipText("Alt+D en este gestor. Deshace un paso confirmado; no cambia píxeles ni revisiones publicadas.");
        redoButton.setToolTipText("Alt+R en este gestor. Una edición nueva registrada sustituye la rama de rehacer.");
        recordHistoryButton.setToolTipText("Alt+T. Agrupa los cambios ya aplicados en ROI Manager como un paso. EDIT de geometrías se registra al confirmar.");
        geometryButtons.add(new JLabel("Hasta 20 pasos; memoria acotada"));

        addButton(sessionButtons, "Crear sesión vacía", function () {
            var name;
            var image;
            if (!state.projectPath) { showError("Abra primero un proyecto."); return; }
            if (state.projectKind !== "SCHEMA2") {
                showError("Crear sesión requiere una copia schema 2 editable."); return;
            }
            image = explicitImage();
            if (image === null) { return; }
            name = promptText("ID de la nueva sesión:", "SESSION_NEW");
            if (name === null) { return; }
            resolvePendingChanges(function () {
                invokeOperation("create_session", {
                    project_root: state.projectPath,
                    image_uid: String(image._image_uid),
                    analysis_session_id: name,
                    expected_current_generation: Number(image.generation),
                    expected_registry_sha256: String(image._session_registry_sha256)
                }, function (result) {
                    bindActivePayload(result,
                        result.session && result.session.analysis_session_uid,
                        "Sesión vacía activa");
                });
            });
        });
        addButton(sessionButtons, "Abrir sesión / Marcar activa", selectExplicitSession);
        addButton(sessionButtons, "Guardar revisión", function () {
            if (state.activeSessionUid === null) { showError("No hay sesión activa."); return; }
            saveCurrentRevision(function () { inspectProject(state.projectPath); });
        });
        addButton(sessionButtons, "Clonar revisión seleccionada", function () {
            var revision;
            var name;
            var session = selectedSession();
            if (session === null) { return; }
            if (session._legacy_image) {
                showError("Una revisión legacy debe migrarse por copia antes de clonarse."); return;
            }
            revision = promptText("UID de revisión explícita a clonar:", session.current_revision_uid || "");
            if (revision === null) { return; }
            name = promptText("Nombre de la sesión clonada:", "Clon de revisión");
            if (name === null) { return; }
            resolvePendingChanges(function () {
                invokeOperation("clone_revision", {
                    project_root: state.projectPath,
                    image_uid: String(session._image_uid),
                    source_session_uid: String(session.analysis_session_uid),
                    source_revision_uid: revision,
                    source_revision_manifest_sha256: String(session.current_revision_manifest_sha256),
                    destination_session_id: name
                }, function (result) {
                    bindActivePayload(result,
                        result.session && result.session.analysis_session_uid,
                        "Sesión clonada activa");
                });
            });
        });
        addButton(sessionButtons, "Marcar canónica", function () {
            sessionOperation("set_canonical", {}, true);
        });
        addButton(sessionButtons, "Marcar superada", function () {
            sessionOperation("mark_superseded", {reason: "USER_SELECTED_IN_PROMPT3_MASKS_PREVIEW"}, true);
        });
        addButton(sessionButtons, "Publicar RUN", function () {
            var operatorId;
            var featureBin;
            var snapshot;
            var imageContext;
            if (state.activeSessionUid === null) { showError("Active una sesión explícitamente."); return; }
            operatorId = promptText("Identificador del operador:", "");
            if (operatorId === null) { return; }
            featureBin = promptText("Bin de distancia (nm, positivo):", "1");
            if (featureBin === null) { return; }
            resolvePendingChanges(function () {
                imageContext = currentImageContext(operatorId, featureBin);
                ensureAnalysisAreaCache(imageContext, function () {
                    snapshot = exportAllFijiRois();
                    invokeOperation("publish_run", {
                        project_root: state.projectPath,
                        image_uid: String(state.activeSession._image_uid),
                        analysis_session_uid: state.activeSessionUid,
                        expected_revision_pointer_sha256: String(state.activeSession.current_revision_pointer_sha256),
                        roi_zip_sha256: snapshot.roi_zip_sha256,
                        geometries: snapshot.geometries,
                        image_context: imageContext
                    }, function () { inspectProject(state.projectPath); });
                });
            });
        });
        addButton(sessionButtons, "Verificar escala científica de RUN", function () {
            var runId;
            var imageContext;
            if (state.activeSessionUid === null || state.activeSession === null) {
                showError("Active una sesión explícitamente."); return;
            }
            runId = promptText(
                "RUN exacto a verificar (integridad física y validez científica separadas):",
                String(state.activeSession.current_run || "RUN_000002")
            );
            if (runId === null) { return; }
            imageContext = currentImageContext("PROMPT3_SCALE_INSPECTION", "1");
            invokeOperation("inspect_run_scientific_scale", {
                project_root: state.projectPath,
                image_uid: String(state.activeSession._image_uid),
                analysis_session_uid: state.activeSessionUid,
                run_id: runId,
                image_context: imageContext
            }, function (result) {
                var scientific = String(result.scientific_scale_validity || "UNKNOWN");
                var disposition = result.scientific_disposition;
                statusLabel.setText(
                    "RUN " + runId + ": cadena física PASS; escala científica " + scientific +
                    (disposition ? "; disposición=" + String(disposition.disposition) : "")
                );
                JOptionPane.showMessageDialog(
                    frame,
                    new JScrollPane(new JTextArea(JSON.stringify(result, null, 2), 24, 100)),
                    "Verificación científica de RUN",
                    scientific === "PASS" ? JOptionPane.INFORMATION_MESSAGE : JOptionPane.WARNING_MESSAGE
                );
            });
        });
        addButton(sessionButtons, "Registrar RUN inválido y sucesor", function () {
            var invalidatedId;
            var replacementId;
            var imageContext;
            if (state.activeSessionUid === null || state.activeSession === null) {
                showError("Active una sesión explícitamente."); return;
            }
            invalidatedId = promptText("RUN físicamente íntegro que se invalida:", "RUN_000002");
            if (invalidatedId === null) { return; }
            replacementId = promptText(
                "RUN sucesor corregido y actual:",
                String(state.activeSession.current_run || "RUN_000003")
            );
            if (replacementId === null) { return; }
            imageContext = currentImageContext("PROMPT3_SCALE_DISPOSITION", "1");
            invokeOperation("publish_scale_disposition", {
                project_root: state.projectPath,
                image_uid: String(state.activeSession._image_uid),
                analysis_session_uid: state.activeSessionUid,
                invalidated_run_id: invalidatedId,
                replacement_run_id: replacementId,
                image_context: imageContext
            }, function (result) {
                statusLabel.setText(
                    "Disposición científica publicada: " + invalidatedId + " → " + replacementId +
                    "; RUN históricos preservados."
                );
                JOptionPane.showMessageDialog(
                    frame,
                    "Registro externo verificado.\n" + String(result.disposition_path || "") +
                    "\nSHA-256: " + String(result.disposition_sha256 || ""),
                    "RUN invalidado y superado",
                    JOptionPane.INFORMATION_MESSAGE
                );
                inspectProject(state.projectPath);
            });
        });
        addButton(sessionButtons, "Archivar", function () {
            var session = selectedSession();
            var directory;
            var archiveName;
            var path;
            if (session === null) { return; }
            if (session.active === true || String(session.active) === "true") {
                JOptionPane.showMessageDialog(frame,
                    "La sesión seleccionada es la actual. Active explícitamente otra sesión antes de archivarla.",
                    "Archivo bloqueado", JOptionPane.WARNING_MESSAGE);
                return;
            }
            directory = chooseDirectory("Seleccione la carpeta donde crear el archivo de sesión");
            if (directory === null) { return; }
            archiveName = "CTL_SESSION_" + String(session.analysis_session_id) + "_" +
                String(session.analysis_session_uid) + ".zip";
            path = String(new File(new File(directory).getCanonicalFile(), archiveName).getCanonicalPath());
            if (new File(path).exists()) { showError("El archivo contractual ya existe; no se reemplaza."); return; }
            sessionOperation("archive_session", {archive_path: path}, true);
        });
        addButton(sessionButtons, "Restaurar", function () {
            var archive = chooseOpenFile("Seleccione el archivo de sesión");
            var destination;
            if (archive === null) { return; }
            try {
                destination = chooseNewDirectory("Destino de restauración", restoreLeafFromArchive(archive), true);
            } catch (restoreNameError) {
                showError(restoreNameError);
                return;
            }
            if (destination === null) { return; }
            invokeOperation("restore_session", {
                project_root: state.projectPath,
                archive_path: archive,
                destination_root: destination
            }, function (result) {
                statusLabel.setText("Restauración verificada: " + String(result.status || "PASS"));
            });
        });
        addButton(sessionButtons, "Inspeccionar cuarentena (solo lectura)", function () {
            var session = selectedSession();
            if (session === null) { return; }
            if (session._legacy_image) {
                showError("La cuarentena pertenece a la sesión schema 2 migrada, no al original legacy.");
                return;
            }
            if (session.migration_limitation === null || session.migration_limitation === undefined) {
                showError("La sesión seleccionada no declara una cuarentena legacy verificada.");
                return;
            }
            invokeOperation("inspect_legacy_quarantine", {
                project_root: state.projectPath,
                image_uid: String(session._image_uid),
                analysis_session_uid: String(session.analysis_session_uid)
            }, function (result) {
                var reportPath = String(result.conflict_report_path || "");
                var reportText;
                var area;
                if (reportPath === "") { showError("La inspección no devolvió el informe físico."); return; }
                try { reportText = readUtf8(new File(reportPath)); }
                catch (reportError) { showError("No se pudo leer el informe verificado: " + reportError); return; }
                area = new JTextArea(reportText, 30, 120);
                area.setEditable(false);
                area.setCaretPosition(0);
                JOptionPane.showMessageDialog(frame, new JScrollPane(area),
                    "Cuarentena legacy verificada - solo lectura", JOptionPane.INFORMATION_MESSAGE);
            });
        });
        addButton(sessionButtons, "Migrar proyecto legacy por copia", function () {
            var source = chooseDirectory("Seleccione el proyecto legacy (solo lectura)");
            var destination;
            var imageId;
            var migrationEvidencePath;
            var pixelEvidencePath;
            var migrationEvidence;
            var pixelEvidence;
            if (source === null) { return; }
            destination = chooseNewDirectory("Destino nuevo de migración", "Cavity_TEM_Light_P2_Migrated", false);
            if (destination === null) { return; }
            migrationEvidencePath = chooseOpenFile("Seleccione r9_migration_evidence.json exportado por Fiji");
            if (migrationEvidencePath === null) { return; }
            pixelEvidencePath = chooseOpenFile("Seleccione master_pixel_evidence JSON independiente");
            if (pixelEvidencePath === null) { return; }
            try {
                migrationEvidence = JSON.parse(readUtf8(new File(migrationEvidencePath)));
                pixelEvidence = JSON.parse(readUtf8(new File(pixelEvidencePath)));
            } catch (migrationEvidenceError) {
                showError("Evidencia de migración JSON inválida: " + migrationEvidenceError);
                return;
            }
            if (!exactKeys(pixelEvidence, ["hash", "method", "status"]) ||
                    String(pixelEvidence.status || "") !== "VERIFIED" ||
                    !/^[0-9a-f]{64}$/.test(String(pixelEvidence.hash || "")) ||
                    !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(String(pixelEvidence.method || ""))) {
                showError("master_pixel_evidence debe tener exactamente hash/method/status y status VERIFIED.");
                return;
            }
            if (!exactKeys(migrationEvidence, [
                    "automatic_identity_repair", "image_id", "legacy_file_inventory",
                    "legacy_snapshot_sha256", "policy_id", "revision_chain",
                    "revision_manifests", "revision_observations", "schema",
                    "scientific_validation", "source_binding", "text_decodings"
                ]) || String(migrationEvidence.schema || "") !== "CTL_R9_MIGRATION_EVIDENCE_V1" ||
                    String(migrationEvidence.policy_id || "") !==
                        "CTL_R9_MIGRATION_CONSISTENT_PREFIX_WITH_LEGACY_QUARANTINE_V1" ||
                    migrationEvidence.automatic_identity_repair !== false ||
                    migrationEvidence.scientific_validation !== false ||
                    !Array.isArray(migrationEvidence.revision_chain) ||
                    migrationEvidence.revision_chain.length === 0) {
                showError("r9_migration_evidence no cumple el inventario cerrado de cuarentena V1.");
                return;
            }
            imageId = String(migrationEvidence.image_id || "");
            if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(imageId)) {
                showError("La evidencia no contiene un image_id portable explícito.");
                return;
            }
            invokeOperation("migrate_legacy", {
                legacy_root: source,
                destination_root: destination,
                image_id: imageId,
                migration_evidence: migrationEvidence,
                master_pixel_evidence: pixelEvidence
            }, function (result) {
                statusLabel.setText("Migración por copia: " + String(result.status || "PASS"));
                inspectProject(destination);
            });
        });
        addButton(sessionButtons, "Verificar proyecto", function () {
            if (!state.projectPath) { showError("Abra primero un proyecto."); return; }
            invokeOperation("verify_project", {project_root: state.projectPath}, function (result) {
                statusLabel.setText("Verificación: " + String(result.status || "PASS") +
                    " (no implica validación científica)");
            });
        });
        addButton(sessionButtons, "Calcular evidencia pixel", function () {
            var evidence = computeMasterPixelEvidence(WindowManager.getCurrentImage());
            JOptionPane.showMessageDialog(frame, JSON.stringify(evidence, null, 2),
                "Evidencia CTL_MASTER_PIXEL_SHA256_V1 (no validación científica)",
                JOptionPane.INFORMATION_MESSAGE);
        });
        addButton(sessionButtons, "Cancelar", function () {
            if (state.editState !== null) { finishGeometryEdit(false, true); }
            stopTemporaryReveal(false);
            removeCavityClickListener();
            if (state.boundImage !== null) { clearFilteredOverlay(state.boundImage); }
            state.disposed = true;
            resetEditHistory();
            stopOperationProgress();
            if (state.draftTimer !== null) { state.draftTimer.stop(); }
            state.callbackEpoch += 1;
            frame.dispose(); // no llama al CLI
        });

        migrationWarningLabel = new JLabel("");
        migrationWarningLabel.setForeground(new Color(160, 60, 0));
        migrationWarningLabel.setVisible(false);
        statusLabel = new JLabel("Cree o abra un proyecto. Incorpore una imagen o seleccione una sesión existente.");
        operationTimingLabel = new JLabel("Los tiempos de las operaciones aparecerán aquí.");
        draftStatusLabel = new JLabel("Borradores: abra una sesión para recuperar o guardar su trabajo.");
        historyStatusLabel = new JLabel("Historial: abra una sesión para registrar cambios.");
        bottom.add(migrationWarningLabel, BorderLayout.NORTH);
        controls.add(geometryButtons, BorderLayout.NORTH);
        controls.add(sessionButtons, BorderLayout.CENTER);
        auxiliaryControls.add(draftControls);
        auxiliaryControls.add(viewControls);
        auxiliaryControls.add(candidateControls);
        controls.add(auxiliaryControls, BorderLayout.SOUTH);
        bottom.add(controls, BorderLayout.CENTER);
        statusPanel.add(statusLabel);
        statusPanel.add(operationTimingLabel);
        statusPanel.add(draftStatusLabel);
        statusPanel.add(historyStatusLabel);
        bottom.add(statusPanel, BorderLayout.SOUTH);
        frame.getContentPane().setLayout(new BorderLayout(8, 8));
        frame.getContentPane().add(top, BorderLayout.NORTH);
        frame.getContentPane().add(sessionNavigation, BorderLayout.CENTER);
        frame.getContentPane().add(bottom, BorderLayout.SOUTH);
        frame.addWindowListener(new JavaAdapter(WindowAdapter, {windowClosing: function () {
            requestManagerClose();
        }, windowClosed: function () {
            if (state.editState !== null) { finishGeometryEdit(false, true); }
            stopTemporaryReveal(false);
            removeCavityClickListener();
            if (state.boundImage !== null) { clearFilteredOverlay(state.boundImage); }
            state.disposed = true;
            resetEditHistory();
            stopOperationProgress();
            if (state.draftTimer !== null) { state.draftTimer.stop(); }
            state.callbackEpoch += 1;
        }}));
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
        state.draftTimer = new Timer(60000, new JavaAdapter(ActionListener, {actionPerformed: function () {
            saveCurrentDraft(true);
        }}));
        state.draftTimer.start();
        refreshDisplayControls();
    }

    onEdt(buildUi);
}());
