/* Portable Prompt-3 controlled-source opener. Local paths are never scientific authority. */
(function () {
    "use strict";

    var IJ = Packages.ij.IJ;
    var File = Packages.java.io.File;
    var FileInputStream = Packages.java.io.FileInputStream;
    var BufferedInputStream = Packages.java.io.BufferedInputStream;
    var MessageDigest = Packages.java.security.MessageDigest;
    var Files = Packages.java.nio.file.Files;
    var StandardCharsets = Packages.java.nio.charset.StandardCharsets;
    var StandardOpenOption = Packages.java.nio.file.StandardOpenOption;
    var StandardCopyOption = Packages.java.nio.file.StandardCopyOption;
    var JFileChooser = Packages.javax.swing.JFileChooser;
    var JOptionPane = Packages.javax.swing.JOptionPane;
    var BF = Packages.loci.plugins.BF;

    var CONFIG_SCHEMA = "CTL_P3_SMOKE_LOCAL_CONFIG_V1";
    var CONFIG_NAME = "P3_SMOKE_LOCAL_CONFIG.json";
    var EXPECTED_SOURCE_SHA256 = "171c6c4e06210a021d046133ee41589609e5414c33c4894e170fd8363a01dd0f";
    var EXPECTED_SOURCE_BYTES = 67353220;
    var EXPECTED_MASTER_PIXEL_SHA256 = "80c65444cfbe42180b0bf32d0649a77149fa533a9ddddc29bc25d02d46245597";

    function fail(code) { throw new Error(String(code)); }

    function hex(bytes) {
        var result = "";
        var i;
        var value;
        for (i = 0; i < bytes.length; i += 1) {
            value = Number(bytes[i]);
            if (value < 0) { value += 256; }
            if (value < 16) { result += "0"; }
            result += value.toString(16);
        }
        return result;
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

    function plainFile(file) {
        return file.isFile() && !Files.isSymbolicLink(file.toPath());
    }

    function readJson(file) {
        var raw = Files.readAllBytes(file.toPath());
        var text = String(new java.lang.String(raw, StandardCharsets.UTF_8));
        var value;
        if (text.indexOf("\u0000") >= 0 || text.indexOf("\r") >= 0 ||
                (raw.length >= 3 && Number(raw[0]) === -17 && Number(raw[1]) === -69 && Number(raw[2]) === -65)) {
            fail("P3_SMOKE_JSON_ENCODING_INVALID");
        }
        value = JSON.parse(text);
        return value;
    }

    function exactKeys(value, expected) {
        return value !== null && typeof value === "object" && !Array.isArray(value) &&
            Object.keys(value).sort().join("|") === expected.slice(0).sort().join("|");
    }

    function chooseFile(title) {
        var chooser = new JFileChooser();
        chooser.setDialogTitle(title);
        chooser.setFileSelectionMode(JFileChooser.FILES_ONLY);
        return chooser.showOpenDialog(null) === JFileChooser.APPROVE_OPTION ?
            chooser.getSelectedFile().getCanonicalFile() : null;
    }

    function chooseDirectory(title) {
        var chooser = new JFileChooser();
        chooser.setDialogTitle(title);
        chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY);
        return chooser.showOpenDialog(null) === JFileChooser.APPROVE_OPTION ?
            chooser.getSelectedFile().getCanonicalFile() : null;
    }

    function validateSource(file) {
        var canonical = file.getCanonicalFile();
        if (!plainFile(canonical)) { fail("P3_SMOKE_SOURCE_NOT_PLAIN_FILE"); }
        if (Number(canonical.length()) !== EXPECTED_SOURCE_BYTES) {
            fail("P3_SMOKE_SOURCE_SIZE_MISMATCH");
        }
        if (sha256File(canonical) !== EXPECTED_SOURCE_SHA256) {
            fail("P3_SMOKE_SOURCE_SHA256_MISMATCH");
        }
        return canonical;
    }

    function validateProject(directory) {
        var root = directory.getCanonicalFile();
        var descriptor = new File(root, "project.json").getCanonicalFile();
        var registry = new File(new File(root, "controls"), "source_registry.json").getCanonicalFile();
        var project;
        var sources;
        var blobMatches = 0;
        var bindingMatches = 0;
        var i;
        if (!root.isDirectory() || Files.isSymbolicLink(root.toPath()) ||
                !plainFile(descriptor) || !plainFile(registry)) {
            fail("P3_SMOKE_PROJECT_LAYOUT_INVALID");
        }
        project = readJson(descriptor);
        sources = readJson(registry);
        if (!exactKeys(project, ["created_at", "project_id", "project_schema_version", "project_uid", "schema"]) ||
                String(project.schema || "") !== "CTL_P2A_PROJECT_JSON_V1" ||
                Number(project.project_schema_version) !== 2) {
            fail("P3_SMOKE_PROJECT_SCHEMA_INVALID");
        }
        if (!exactKeys(sources, ["blobs", "image_bindings", "project_uid", "schema", "updated_at"]) ||
                String(sources.schema || "") !== "CTL_SOURCE_REGISTRY_V1" ||
                String(sources.project_uid || "") !== String(project.project_uid || "") ||
                !Array.isArray(sources.blobs) || !Array.isArray(sources.image_bindings)) {
            fail("P3_SMOKE_SOURCE_REGISTRY_INVALID");
        }
        for (i = 0; i < sources.blobs.length; i += 1) {
            if (String(sources.blobs[i].source_sha256 || "") === EXPECTED_SOURCE_SHA256 &&
                    Number(sources.blobs[i].byte_size) === EXPECTED_SOURCE_BYTES) { blobMatches += 1; }
        }
        for (i = 0; i < sources.image_bindings.length; i += 1) {
            if (String(sources.image_bindings[i].source_sha256 || "") === EXPECTED_SOURCE_SHA256 &&
                    String(sources.image_bindings[i].master_pixel_hash_status || "") === "VERIFIED" &&
                    String(sources.image_bindings[i].master_pixel_sha256 || "") === EXPECTED_MASTER_PIXEL_SHA256) {
                bindingMatches += 1;
            }
        }
        if (blobMatches !== 1 || bindingMatches !== 1) {
            fail("P3_SMOKE_PROJECT_SOURCE_IDENTITY_MISMATCH");
        }
        return root;
    }

    function validateConfig(value) {
        if (!exactKeys(value, [
                "expected_source_bytes", "expected_source_sha256", "project_root", "schema", "source_dm4_path"
            ]) || String(value.schema || "") !== CONFIG_SCHEMA ||
                String(value.expected_source_sha256 || "") !== EXPECTED_SOURCE_SHA256 ||
                Number(value.expected_source_bytes) !== EXPECTED_SOURCE_BYTES) {
            fail("P3_SMOKE_LOCAL_CONFIG_INVALID");
        }
        return value;
    }

    function jsonString(value) {
        return JSON.stringify(String(value));
    }

    function configBytes(source, project) {
        var text = "{\"expected_source_bytes\":" + EXPECTED_SOURCE_BYTES +
            ",\"expected_source_sha256\":\"" + EXPECTED_SOURCE_SHA256 +
            "\",\"project_root\":" + jsonString(String(project.getCanonicalPath())) +
            ",\"schema\":\"" + CONFIG_SCHEMA +
            "\",\"source_dm4_path\":" + jsonString(String(source.getCanonicalPath())) + "}\n";
        return new java.lang.String(text).getBytes(StandardCharsets.UTF_8);
    }

    function writeLocalConfig(configFile, source, project) {
        var temporary = new File(configFile.getParentFile(), CONFIG_NAME + ".partial." +
            String(Packages.java.util.UUID.randomUUID().toString())).getCanonicalFile();
        Files.write(temporary.toPath(), configBytes(source, project),
            StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        try {
            Files.move(temporary.toPath(), configFile.toPath(),
                StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary.toPath());
        }
    }

    function resolveInputs(configFile) {
        var config = null;
        var source = null;
        var project = null;
        if (plainFile(configFile)) {
            config = validateConfig(readJson(configFile));
            source = new File(String(config.source_dm4_path || ""));
            project = new File(String(config.project_root || ""));
            if (source.exists()) { source = validateSource(source); }
            else { source = null; }
            if (project.exists()) { project = validateProject(project); }
            else { project = null; }
        } else if (configFile.exists()) {
            fail("P3_SMOKE_LOCAL_CONFIG_NOT_PLAIN_FILE");
        }
        if (source === null) {
            source = chooseFile("Seleccione el DM4 controlado");
            if (source === null) { fail("P3_SMOKE_SOURCE_SELECTION_CANCELLED"); }
            source = validateSource(source);
        }
        if (project === null) {
            project = chooseDirectory("Seleccione la raiz del proyecto schema 2 controlado");
            if (project === null) { fail("P3_SMOKE_PROJECT_SELECTION_CANCELLED"); }
            project = validateProject(project);
        }
        writeLocalConfig(configFile, source, project);
        return {source: source, project: project};
    }

    try {
        var fijiRoot = new File(String(IJ.getDirectory("imagej") || "")).getCanonicalFile();
        var menuRoot = new File(new File(new File(fijiRoot, "scripts"), "Plugins"),
            "Cavity_TEM_Light").getCanonicalFile();
        var configFile = new File(menuRoot, CONFIG_NAME).getCanonicalFile();
        var selected = resolveInputs(configFile);
        var images = BF.openImagePlus(String(selected.source.getCanonicalPath()));
        var image;
        if (images === null || Number(images.length) !== 1) { fail("P3_SMOKE_SOURCE_SERIES_AMBIGUOUS"); }
        image = images[0];
        image.setProperty("CTL.P1.source_sha256", EXPECTED_SOURCE_SHA256);
        image.setProperty("CTL.P1.source_sha256_actual", EXPECTED_SOURCE_SHA256);
        image.setProperty("CTL.P3.smoke.source_path", String(selected.source.getCanonicalPath()));
        image.show();
        IJ.setProperty("CTL.P3.smoke.project_root", String(selected.project.getCanonicalPath()));
        IJ.setProperty("CTL.P3.smoke.source_path", String(selected.source.getCanonicalPath()));
        IJ.setProperty("CTL.P3.smoke.source_sha256", EXPECTED_SOURCE_SHA256);
        IJ.setProperty("CTL.P3.smoke.source_bytes", String(EXPECTED_SOURCE_BYTES));
        JOptionPane.showMessageDialog(null,
            "Fuente controlada verificada y abierta.\nProyecto: " + selected.project.getCanonicalPath() +
            "\nDM4: " + selected.source.getCanonicalPath() +
            "\nAbra ahora el gestor Prompt 3 y seleccione explicitamente la sesion.",
            "Prompt 3 portable", JOptionPane.INFORMATION_MESSAGE);
    } catch (error) {
        IJ.log("CTL Prompt3 portable open ERROR: " + String(error));
        JOptionPane.showMessageDialog(null, String(error), "Prompt 3 portable",
            JOptionPane.ERROR_MESSAGE);
    }
}());
