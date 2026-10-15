package cavity.light;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonParser;
import ij.ImagePlus;
import ij.WindowManager;
import ij.gui.GenericDialog;
import ij.gui.Overlay;
import ij.gui.Roi;
import ij.io.FileSaver;
import ij.io.Opener;
import ij.process.ImageProcessor;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import javax.imageio.ImageIO;

/** Immutable image/recipe snapshots, attached only to newly staged ROI revisions. */
public final class RevisionWorkspace {
    private static final Gson JSON = new GsonBuilder().disableHtmlEscaping().serializeNulls().setPrettyPrinting().create();
    private static final String MARKER = ".revision-workspace-staging";
    private static final int JSON_LIMIT = 1024 * 1024;
    private static final Map<String, Load> LOADS = new LinkedHashMap<String, Load>();
    private static final java.util.Deque<Switch> SWITCHES = new java.util.ArrayDeque<Switch>();
    private static final Map<ImagePlus, String[]> LABELS = new java.util.WeakHashMap<ImagePlus, String[]>();
    private RevisionWorkspace() {}

    static String error(Exception e) { return "ERROR|" + String.valueOf(e.getMessage()).replace('\n', ' '); }
    @SuppressWarnings("unchecked")
    static Map<String, Object> object(Object value) {
        if (!(value instanceof Map)) throw new IllegalArgumentException("Se esperaba un objeto JSON.");
        return (Map<String, Object>) value;
    }
    static Map<String, Object> parse(String text) {
        if (text.getBytes(StandardCharsets.UTF_8).length > JSON_LIMIT) throw new IllegalArgumentException("JSON demasiado grande.");
        JsonElement json = JsonParser.parseString(text);
        if (!json.isJsonObject()) throw new IllegalArgumentException("Se esperaba un objeto JSON.");
        return object(JSON.fromJson(json, Map.class));
    }
    static String string(Map<String, Object> map, String key) {
        Object value = map.get(key);
        if (!(value instanceof String)) throw new IllegalArgumentException("Falta texto: " + key);
        return (String) value;
    }
    static int integer(Map<String, Object> map, String key) {
        Object value = map.get(key);
        if (!(value instanceof Number)) throw new IllegalArgumentException("Falta numero: " + key);
        double n = ((Number) value).doubleValue();
        if (!Double.isFinite(n) || n != Math.floor(n) || n < 0 || n > Integer.MAX_VALUE) throw new IllegalArgumentException("Numero no valido: " + key);
        return (int) n;
    }
    static Map<String, Object> map(Object... pairs) {
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        for (int i = 0; i < pairs.length; i += 2) result.put((String) pairs[i], pairs[i + 1]);
        return result;
    }
    static ImagePlus image() {
        ImagePlus image = WindowManager.getCurrentImage();
        if (image == null) throw new IllegalArgumentException("No hay imagen activa.");
        if (image.getStackSize() != 1 || image.getNChannels() != 1) throw new IllegalArgumentException("Solo se admite una imagen 2D.");
        return image;
    }
    static Path directory(String path) throws Exception {
        Path result = Paths.get(path).toAbsolutePath().normalize();
        rejectSymlinks(result);
        if (!Files.isDirectory(result, LinkOption.NOFOLLOW_LINKS)) throw new IllegalArgumentException("Carpeta no disponible: " + result);
        return result;
    }
    static void rejectSymlinks(Path path) throws Exception {
        for (Path part = path; part != null; part = part.getParent())
            if (Files.isSymbolicLink(part)) throw new IllegalArgumentException("No se admiten enlaces simbolicos: " + part);
    }
    static Path inside(Path root, String relative) throws Exception {
        if (relative == null || relative.isEmpty() || relative.indexOf('\\') >= 0 || relative.indexOf(':') >= 0)
            throw new IllegalArgumentException("Ruta de artefacto no valida.");
        Path value = Paths.get(relative);
        if (value.isAbsolute()) throw new IllegalArgumentException("El artefacto debe ser relativo.");
        for (Path part : value) if (part.toString().equals("..") || part.toString().equals("."))
            throw new IllegalArgumentException("Ruta relativa insegura.");
        Path result = root.resolve(value).normalize();
        if (!result.startsWith(root)) throw new IllegalArgumentException("El artefacto sale de la revision.");
        rejectSymlinks(result);
        return result;
    }
    static void writeNew(Path path, byte[] bytes) throws Exception {
        Files.createDirectories(path.getParent());
        Files.write(path, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
    }
    static String sha(byte[] bytes) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder text = new StringBuilder();
        for (byte b : hash) text.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return text.toString();
    }
    static String sha(Path path) throws Exception {
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) throw new IllegalArgumentException("Falta artefacto: " + path);
        return HF46.sha256(path);
    }
    static Map<String, String> pairs(Path path) throws Exception {
        Map<String, String> map = new LinkedHashMap<String, String>();
        for (String line : new String(Files.readAllBytes(path), StandardCharsets.UTF_8).split("\\r?\\n")) {
            int tab = line.indexOf('\t');
            if (tab > 0) map.put(line.substring(0, tab), line.substring(tab + 1));
        }
        return map;
    }
    static Map<String, Object> binding(Map<String, Object> settings) {
        Map<String, Object> project = object(settings.get("project")), img = object(settings.get("image"));
        return map("project_id", string(project, "id"), "project_uid", string(project, "uid"),
            "image_id", string(img, "id"), "source_sha256", string(img, "sha256"),
            "width_px", integer(img, "width_px"), "height_px", integer(img, "height_px"));
    }
    static void sameBinding(Map<String, Object> a, Map<String, Object> b) {
        for (String key : new String[] {"project_id", "project_uid", "image_id", "source_sha256"})
            if (!string(a, key).equals(string(b, key))) throw new IllegalArgumentException("La identidad de fuente no coincide: " + key);
        for (String key : new String[] {"width_px", "height_px"})
            if (integer(a, key) != integer(b, key)) throw new IllegalArgumentException("Dimensiones de fuente distintas.");
    }

    /** Called after source import, before applying treatments. Captures a detached original. */
    public static String initialize(final String settingsJson) {
        return HF4.ui(new Callable<String>() { public String call() {
            try { ImagePreparation.Session.current(image(), binding(parse(settingsJson))); return "OK"; }
            catch (Exception e) { return error(e); }
        }});
    }

    /** Name and comment are display text; neither is ever used as a filesystem path. */
    public static String askSave(final String unused) {
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                ImagePlus imp = image(); String[] previous = LABELS.get(imp);
                GenericDialog dialog = new GenericDialog("Guardar revision de trabajo");
                dialog.addStringField("Nombre", previous == null ? "Revision de trabajo" : previous[0], 40);
                dialog.addTextAreas(previous == null ? "" : previous[1], null, 5, 60);
                dialog.addMessage("Se guardan la imagen preparada, anotaciones, parametros y receta vigente. No es necesario exportar un RUN.");
                dialog.showDialog(); if (dialog.wasCanceled()) return "CANCEL";
                String name = dialog.getNextString().trim(), comment = dialog.getNextText();
                validateLabel(name, comment); LABELS.put(imp, new String[] {name, comment});
                return JSON.toJson(map("name", name, "comment", comment));
            } catch (Exception e) { return error(e); }
        }});
    }
    static void validateLabel(String name, String comment) {
        if (name.trim().isEmpty() || name.length() > 120 || comment.length() > 4000)
            throw new IllegalArgumentException("Use un nombre de 1 a 120 caracteres y comentario de hasta 4000.");
    }

    /** Creates a hidden sibling owned by this transaction; finalDir is never overwritten. */
    public static String beginRevision(String finalDir) {
        try {
            Path target = Paths.get(finalDir).toAbsolutePath().normalize();
            Path parent = directory(target.getParent().toString());
            String leaf = target.getFileName().toString();
            if (!leaf.matches("REV_[A-Za-z0-9_-]+") || Files.exists(target, LinkOption.NOFOLLOW_LINKS))
                throw new IllegalArgumentException("La revision debe ser nueva y tener un identificador REV valido.");
            Path staging = Files.createDirectory(parent.resolve(".pending_" + leaf + "_" + UUID.randomUUID()));
            writeNew(staging.resolve(MARKER), target.toString().getBytes(StandardCharsets.UTF_8));
            return "OK|" + staging;
        } catch (Exception e) { return error(e); }
    }
    static Path ownedStage(String stage) throws Exception {
        Path path = directory(stage);
        if (!path.getFileName().toString().startsWith(".pending_REV_") || !Files.isRegularFile(path.resolve(MARKER), LinkOption.NOFOLLOW_LINKS))
            throw new IllegalArgumentException("No es una revision temporal propia.");
        return path;
    }
    static void deleteTree(Path path) throws Exception {
        if (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
            try (DirectoryStream<Path> children = Files.newDirectoryStream(path)) {
                for (Path child : children) deleteTree(child);
            }
        }
        Files.deleteIfExists(path);
    }
    public static String abortRevision(String stage) {
        try { deleteTree(ownedStage(stage)); return "OK"; }
        catch (Exception e) { return error(e); }
    }
    public static synchronized String publishRevision(String request) {
        try {
            String[] args = request.split("\\|", -1);
            if (args.length != 2) throw new IllegalArgumentException("Publicacion incompleta.");
            Path staging = ownedStage(args[0]), target = Paths.get(args[1]).toAbsolutePath().normalize();
            if (!staging.getParent().equals(target.getParent()) || !target.toString().equals(new String(Files.readAllBytes(staging.resolve(MARKER)), StandardCharsets.UTF_8)) ||
                Files.exists(target, LinkOption.NOFOLLOW_LINKS)) throw new IllegalArgumentException("Destino de revision distinto u ocupado.");
            Map<String, String> manifest = pairs(staging.resolve("revision_manifest.tsv"));
            if (!target.getFileName().toString().equals(manifest.get("revision_id"))) throw new IllegalArgumentException("El identificador de revision no coincide.");
            validateWorkspace(staging, target.getFileName().toString(), null, true);
            if (!Files.isRegularFile(staging.resolve("session_metadata.json"), LinkOption.NOFOLLOW_LINKS)) throw new IllegalArgumentException("Falta metadata de sesion.");
            // No copy-and-delete fallback: an incomplete published revision must never become visible.
            try { Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException e) { throw new IllegalArgumentException("El disco no permite publicar la carpeta de revision atomicamente."); }
            // The revision is already published. Failure to remove an inert marker is not a failed save.
            try { Files.deleteIfExists(target.resolve(MARKER)); } catch (java.io.IOException ignored) { }
            return "OK";
        } catch (Exception e) { return error(e); }
    }

    static ImagePlus detached(ImagePlus source, ImageProcessor processor) {
        ImagePlus copy = new ImagePlus("Preparacion guardada", processor.duplicate());
        copy.setCalibration(source.getCalibration().copy());
        copy.setDisplayRange(source.getDisplayRangeMin(), source.getDisplayRangeMax());
        return copy;
    }
    static Map<String, Object> artifact(Path root, String relative, ImagePlus image) throws Exception {
        Path file = inside(root, relative);
        Map<String, Object> out = map("relative_path", relative, "sha256", sha(file), "size_bytes", Files.size(file));
        if (image != null) { out.put("width_px", image.getWidth()); out.put("height_px", image.getHeight()); out.put("bit_depth", image.getBitDepth()); }
        return out;
    }
    static void png(BufferedImage image, Path path) throws Exception {
        if (Files.exists(path, LinkOption.NOFOLLOW_LINKS) || !ImageIO.write(image, "png", path.toFile())) throw new IllegalArgumentException("No se pudo guardar PNG.");
    }
    /** No active cursor/proposal previews or metadata are included in the annotation snapshot. */
    static Overlay annotationOverlay(Roi[] scientific, boolean labels) throws Exception {
        Overlay overlay = new Overlay();
        for (Roi roi : scientific) {
            if (roi == null) continue;
            String type = roi.getProperty("Type"), name = roi.getName();
            if ("session_metadata".equals(type) || "CAVITY_SESSION_METADATA".equals(name) || "BUBBLE_SESSION_METADATA".equals(name) ||
                (name != null && (name.startsWith("__CTL_") || name.startsWith("__HF4_")))) continue;
            overlay.add(HF46.independent(roi));
        }
        overlay.drawLabels(labels); overlay.drawNames(labels); overlay.setLabelFontSize(12, "bold background");
        return overlay;
    }
    @SuppressWarnings("unchecked")
    static String writeWorkspace(Path staging, String revisionId, String name, String comment, Map<String, Object> settings,
        ImagePlus image, ImagePreparation.State state) throws Exception {
        ownedStage(staging.toString()); validateLabel(name, comment);
        if (!revisionId.equals(settings.get("revision_id"))) throw new IllegalArgumentException("Los parametros congelados pertenecen a otra revision.");
        Map<String, Object> source = binding(settings); sameBinding(source, state.sourceBinding());
        if (integer(source, "width_px") != image.getWidth() || integer(source, "height_px") != image.getHeight()) throw new IllegalArgumentException("La geometria de la imagen ha cambiado.");
        source.put("roi_zip_sha256", sha(staging.resolve("cavity_rois.zip")));
        Path folder = inside(staging, "workspace");
        Files.createDirectory(folder); Files.createDirectory(folder.resolve("regions"));
        ImagePlus working = detached(image, state.workingProcessor());
        if (!new FileSaver(working).saveAsTiff(folder.resolve("working_image.tif").toString())) throw new IllegalArgumentException("No se pudo guardar imagen de trabajo.");
        Object labels = settings.get("settings") instanceof Map ? object(settings.get("settings")).get("exact_labels_visible") : null;
        boolean drawLabels = labels instanceof Number ? ((Number) labels).intValue() == 1 : Boolean.TRUE.equals(labels);
        // The saved ROI ZIP is the authority for this revision. Live annotations can
        // change while image files are prepared, so never render the manager here.
        List<Roi> scientific = HF46.readZip(staging.resolve("cavity_rois.zip"));
        working.setOverlay(annotationOverlay(scientific.toArray(new Roi[scientific.size()]), drawLabels));
        ImagePlus flat = working.flatten();
        try {
            png(flat.getBufferedImage(), folder.resolve("annotated_view.png"));
            BufferedImage full = flat.getBufferedImage();
            double factor = Math.min(1.0, 1200.0 / Math.max(full.getWidth(), full.getHeight()));
            int width = Math.max(1, (int) Math.round(full.getWidth() * factor)), height = Math.max(1, (int) Math.round(full.getHeight() * factor));
            BufferedImage thumb = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
            Graphics2D graphics = thumb.createGraphics();
            try { graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR); graphics.drawImage(full, 0, 0, width, height, null); }
            finally { graphics.dispose(); }
            png(thumb, folder.resolve("thumbnail.png"));
            List<Map<String, Object>> operations = new ArrayList<Map<String, Object>>();
            if (state.operations().size() > 1000) throw new IllegalArgumentException("La receta excede 1000 operaciones.");
            Map<String, byte[]> regionFiles = state.regionFiles();
            try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(folder.resolve("treatment_regions.zip"), StandardOpenOption.CREATE_NEW))) {
                for (Map.Entry<String, byte[]> entry : regionFiles.entrySet()) {
                    String leaf = entry.getKey();
                    if (leaf.startsWith("regions/")) leaf = leaf.substring("regions/".length());
                    if (!leaf.matches("[A-Za-z0-9_-]+\\.roi")) throw new IllegalArgumentException("Nombre de zona no valido.");
                    writeNew(folder.resolve("regions").resolve(leaf), entry.getValue());
                    zip.putNextEntry(new ZipEntry(leaf)); zip.write(entry.getValue()); zip.closeEntry();
                }
            }
            for (Map<String, Object> original : state.operations()) {
                Map<String, Object> op = object(JSON.fromJson(JSON.toJson(original), Map.class));
                if (op.get("region") instanceof Map && object(op.get("region")).containsKey("roi_file")) {
                    Map<String, Object> region = object(op.get("region"));
                    String internal = string(region, "roi_file");
                    String leaf = internal.startsWith("regions/") ? internal.substring("regions/".length()) : internal;
                    byte[] bytes = regionFiles.get(internal);
                    if (bytes == null) throw new IllegalArgumentException("Falta la zona de una operacion.");
                    region.remove("roi_file"); region.put("roi_relative_path", "workspace/regions/" + leaf); region.put("sha256", sha(bytes));
                } else { op.put("region", null); }
                operations.add(op);
            }
            Map<String, Object> artifacts = map("working_image", artifact(staging, "workspace/working_image.tif", working),
                "annotated_view", artifact(staging, "workspace/annotated_view.png", flat),
                "thumbnail", map("relative_path", "workspace/thumbnail.png", "sha256", sha(folder.resolve("thumbnail.png")), "size_bytes", Files.size(folder.resolve("thumbnail.png")), "width_px", width, "height_px", height),
                "treatment_regions", artifact(staging, "workspace/treatment_regions.zip", null));
            object(artifacts.get("working_image")).put("display_min", image.getDisplayRangeMin());
            object(artifacts.get("working_image")).put("display_max", image.getDisplayRangeMax());
            Map<String, Object> preparation = object(JSON.fromJson(JSON.toJson(state.toMap()), Map.class));
            preparation.remove("operations");
            Map<String, Object> workspace = map("type", "cavity_revision_workspace", "schema_version", 1, "revision_id", revisionId,
                "name", name, "comment", comment, "created_ms", System.currentTimeMillis(), "binding", source,
                "settings_provenance", "saved_session_project_json", "settings", settings, "operations", operations,
                "preparation", preparation, "undo_before_reload_available", false, "artifacts", artifacts);
            byte[] json = (JSON.toJson(workspace) + "\n").getBytes(StandardCharsets.UTF_8);
            if (json.length > JSON_LIMIT) throw new IllegalArgumentException("La receta y parametros exceden 1 MiB.");
            writeNew(staging.resolve("revision_workspace.json"), json);
            String digest = sha(json);
            writeNew(staging.resolve("revision_workspace.sha256"), (digest + "  revision_workspace.json\n").getBytes(StandardCharsets.UTF_8));
            return digest;
        } finally { flat.flush(); working.flush(); }
    }

    private static final class Save { ImagePlus frozen; ImagePreparation.State state; String name, comment; }
    /** Capture on EDT; TIFF/PNG rendering, compression and hashing run on the macro's worker. */
    public static String saveWorkspace(final String request) {
        try {
            final Map<String, Object> args = parse(request), settings = object(args.get("settings"));
            final Save[] captured = new Save[1];
            String capturedStatus = HF4.ui(new Callable<String>() { public String call() {
                try {
                    ImagePlus imp = image(); ImagePreparation.Session session = ImagePreparation.Session.current(imp, binding(settings));
                    Save save = new Save(); save.state = session.snapshot(); save.frozen = detached(imp, save.state.workingProcessor());
                    String[] labels = LABELS.get(imp);
                    save.name = args.get("name") instanceof String ? string(args, "name") : labels == null ? "Revision de trabajo" : labels[0];
                    save.comment = args.get("comment") instanceof String ? string(args, "comment") : labels == null ? "" : labels[1];
                    validateLabel(save.name, save.comment);
                    captured[0] = save; return "OK";
                } catch (Exception e) { return error(e); }
            }});
            if (!"OK".equals(capturedStatus)) return capturedStatus;
            Save save = captured[0];
            try {
                String digest = writeWorkspace(ownedStage(string(args, "revision_directory")), string(args, "revision_id"), save.name, save.comment,
                    settings, save.frozen, save.state);
                return "OK|" + digest;
            } finally { save.frozen.flush(); }
        } catch (Exception e) { return error(e); }
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> validateWorkspace(Path root, String revisionId, Map<String, Object> expected, boolean requireAuthority) throws Exception {
        Path sidecar = inside(root, "revision_workspace.json");
        if (Files.size(sidecar) > JSON_LIMIT) throw new IllegalArgumentException("Workspace demasiado grande.");
        byte[] bytes = Files.readAllBytes(sidecar);
        Map<String, Object> workspace = parse(new String(bytes, StandardCharsets.UTF_8));
        if (!"cavity_revision_workspace".equals(workspace.get("type")) || integer(workspace, "schema_version") != 1 || !revisionId.equals(workspace.get("revision_id")))
            throw new IllegalArgumentException("Workspace de otra version o revision.");
        String digest = sha(bytes);
        if (requireAuthority && !digest.equals(pairs(root.resolve("revision_manifest.tsv")).get("workspace_sha256")))
            throw new IllegalArgumentException("El hash de workspace no coincide con el manifiesto de revision.");
        String sidecarHash = new String(Files.readAllBytes(inside(root, "revision_workspace.sha256")), StandardCharsets.UTF_8);
        if (!sidecarHash.equals(digest + "  revision_workspace.json\n")) throw new IllegalArgumentException("El hash guardado de workspace no coincide.");
        Map<String, Object> source = object(workspace.get("binding"));
        if (expected != null) sameBinding(source, expected);
        Map<String, String> rev = pairs(inside(root, "revision_manifest.tsv"));
        for (String key : new String[] {"project_id", "project_uid", "image_id", "source_sha256", "roi_zip_sha256"})
            if (!string(source, key).equals(rev.get(key))) throw new IllegalArgumentException("Vinculo de revision distinto: " + key);
        if (!string(source, "roi_zip_sha256").equals(sha(inside(root, "cavity_rois.zip")))) throw new IllegalArgumentException("El ZIP cientifico ha cambiado.");
        Map<String, Object> artifacts = object(workspace.get("artifacts"));
        for (String role : new String[] {"working_image", "annotated_view", "thumbnail", "treatment_regions"}) {
            Map<String, Object> artifact = object(artifacts.get(role));
            Path file = inside(root, string(artifact, "relative_path"));
            if (!string(artifact, "sha256").equals(sha(file)) || ((Number) artifact.get("size_bytes")).longValue() != Files.size(file))
                throw new IllegalArgumentException("Artefacto alterado: " + role);
        }
        if (!(workspace.get("operations") instanceof List)) throw new IllegalArgumentException("Receta no valida.");
        for (Object entry : (List<?>) workspace.get("operations")) {
            Map<String, Object> op = object(entry);
            if (op.get("region") instanceof Map && object(op.get("region")).containsKey("roi_relative_path")) {
                Map<String, Object> region = object(op.get("region"));
                if (!string(region, "sha256").equals(sha(inside(root, string(region, "roi_relative_path"))))) throw new IllegalArgumentException("Zona de tratamiento alterada.");
            }
        }
        return workspace;
    }

    private static final class Load { ImagePlus image; ImagePreparation.State state; Map<String, Object> workspace; }
    /** Verify and decode before applying ROI/session switches; failed validation never changes pixels. */
    public static String stageRestore(final String request) {
        ImagePlus stored = null;
        try {
            final Map<String, Object> args = parse(request); final Path root = directory(string(args, "revision_directory"));
            final Map<String, Object> expected = binding(object(args.get("settings")));
            if (!Files.exists(root.resolve("revision_workspace.json"), LinkOption.NOFOLLOW_LINKS)) {
                if (pairs(root.resolve("revision_manifest.tsv")).containsKey("workspace_sha256")) throw new IllegalArgumentException("Falta el workspace declarado por la revision.");
                return "OK|LEGACY";
            }
            final ImagePlus[] capturedImage = new ImagePlus[1]; final ImageProcessor[] original = new ImageProcessor[1];
            String capturedStatus = HF4.ui(new Callable<String>() { public String call() {
                try {
                    ImagePlus imp = image(); ImagePreparation.Session current = ImagePreparation.Session.current(imp, expected);
                    capturedImage[0] = imp; original[0] = current.originalProcessor(); return "OK";
                } catch (Exception e) { return error(e); }
            }});
            if (!"OK".equals(capturedStatus)) return capturedStatus;
            String revisionId = args.get("revision_id") instanceof String ? string(args, "revision_id") : root.getFileName().toString();
            final Map<String, Object> workspace = validateWorkspace(root, revisionId, expected, true);
            Map<String, Object> artifact = object(object(workspace.get("artifacts")).get("working_image"));
            stored = new Opener().openImage(inside(root, string(artifact, "relative_path")).toString());
            if (stored == null || stored.getStackSize() != 1 || stored.getWidth() != integer(expected, "width_px") || stored.getHeight() != integer(expected, "height_px") || stored.getBitDepth() != integer(artifact, "bit_depth"))
                throw new IllegalArgumentException("Snapshot de imagen incompatible.");
            List<Map<String, Object>> operations = new ArrayList<Map<String, Object>>(); Map<String, byte[]> regions = new LinkedHashMap<String, byte[]>();
            for (Object item : (List<?>) workspace.get("operations")) {
                Map<String, Object> op = object(JSON.fromJson(JSON.toJson(item), Map.class));
                if (op.get("region") instanceof Map && object(op.get("region")).containsKey("roi_relative_path")) {
                    Map<String, Object> region = object(op.get("region")); String relative = string(region, "roi_relative_path");
                    String internal = relative.startsWith("workspace/") ? relative.substring("workspace/".length()) : relative;
                    regions.put(internal, Files.readAllBytes(inside(root, relative)));
                    region.remove("roi_relative_path"); region.remove("sha256"); region.put("roi_file", internal);
                } else { op.put("region", map("scope", "whole_image")); }
                operations.add(op);
            }
            Map<String, Object> stateMap = object(JSON.fromJson(JSON.toJson(workspace.get("preparation")), Map.class));
            stateMap.put("source_binding", expected); stateMap.put("operations", operations); stateMap.put("undo_before_reload_available", false);
            final Load load = new Load(); load.image = capturedImage[0]; load.workspace = workspace;
            load.state = ImagePreparation.State.fromMap(stateMap, original[0], stored.getProcessor(), regions);
            final String token = UUID.randomUUID().toString();
            String installStatus = HF4.ui(new Callable<String>() { public String call() {
                try {
                    if (image() != load.image) throw new IllegalArgumentException("La imagen cambio durante la comprobacion.");
                    sameBinding(ImagePreparation.Session.get(load.image).sourceBinding(), expected);
                    LOADS.clear(); LOADS.put(token, load); return "OK";
                } catch (Exception e) { return error(e); }
            }});
            return "OK".equals(installStatus) ? "OK|" + token : installStatus;
        } catch (Exception e) { return error(e); }
        finally { if (stored != null) stored.flush(); }
    }
    public static String applyRestore(final String token) {
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                if ("LEGACY".equals(token)) {
                    ImagePlus imp = image(); ImagePreparation.Session session = ImagePreparation.Session.get(imp);
                    if (session == null) throw new IllegalArgumentException("Falta la copia original para cargar esta revision historica.");
                    ImageProcessor original = session.originalProcessor(); String pixelsHash = ImagePreparation.pixelHash(original);
                    Map<String, Object> clean = map("schema_version", 1, "engine_version", ImagePreparation.ENGINE_VERSION,
                        "source_binding", session.sourceBinding(), "width_px", original.getWidth(), "height_px", original.getHeight(), "bit_depth", original.getBitDepth(),
                        "original_pixel_sha256", pixelsHash, "working_pixel_sha256", pixelsHash, "operations", new ArrayList<Map<String, Object>>(), "recipe_complete", true);
                    ImagePreparation.Session.restore(imp, ImagePreparation.State.fromMap(clean, original, original, new LinkedHashMap<String, byte[]>()));
                    LABELS.remove(imp); return "OK";
                }
                Load load = LOADS.remove(token);
                if (load == null || image() != load.image) throw new IllegalArgumentException("La carga de preparacion ha caducado.");
                ImagePreparation.Session.restore(load.image, load.state);
                Map<String, Object> artifact = object(object(load.workspace.get("artifacts")).get("working_image"));
                load.image.setDisplayRange(((Number) artifact.get("display_min")).doubleValue(), ((Number) artifact.get("display_max")).doubleValue());
                LABELS.put(load.image, new String[] {string(load.workspace, "name"), string(load.workspace, "comment")}); return "OK";
            } catch (Exception e) { return error(e); }
        }});
    }
    public static String discardRestore(final String token) {
        return HF4.ui(new Callable<String>() { public String call() { LOADS.remove(token); return "OK"; }});
    }

    /** Only these three tracked preparation operations can enter the persisted effective recipe. */
    private static final class Treatment { ImagePlus image; ImagePreparation.Session session; Map<String, Object> params; Roi region; }
    public static String treatment(final String kind) {
        final Treatment[] captured = new Treatment[1];
        String captureStatus = HF4.ui(new Callable<String>() { public String call() {
            try {
                ImagePlus imp = image(); ImagePreparation.Session session = ImagePreparation.Session.get(imp);
                if (session == null) throw new IllegalArgumentException("Abra o registre primero la imagen original del proyecto.");
                GenericDialog dialog = new GenericDialog("Preparar imagen: " + kind);
                boolean areaAvailable = imp.getRoi() != null && imp.getRoi().isArea();
                dialog.addChoice("Aplicar en", areaAvailable ? new String[] {"Toda la imagen", "Seleccion actual"} : new String[] {"Toda la imagen"}, "Toda la imagen");
                if (ImagePreparation.BRIGHTNESS_CONTRAST.equals(kind)) {
                    dialog.addNumericField("Brillo", 0, 3); dialog.addNumericField("Contraste (factor)", 1, 3);
                } else if (ImagePreparation.LOCAL_CONTRAST.equals(kind)) {
                    dialog.addNumericField("Radio local (px)", 16, 2); dialog.addNumericField("Intensidad", 1, 3); dialog.addNumericField("Ganancia maxima", 4, 3);
                } else if (ImagePreparation.BACKGROUND_CORRECTION.equals(kind)) {
                    dialog.addNumericField("Radio de fondo (px)", 40, 2); dialog.addNumericField("Intensidad", 1, 3);
                    dialog.addChoice("Correccion", new String[] {"subtract", "divide"}, "subtract");
                } else throw new IllegalArgumentException("Tratamiento no disponible.");
                dialog.addMessage("La seleccion se guarda como zona de tratamiento separada. Las ROIs cientificas mantienen su geometria e identidad.");
                dialog.showDialog(); if (dialog.wasCanceled()) return "CANCEL";
                boolean useArea = "Seleccion actual".equals(dialog.getNextChoice()); Map<String, Object> params = new LinkedHashMap<String, Object>();
                if (ImagePreparation.BRIGHTNESS_CONTRAST.equals(kind)) {
                    params.put("brightness", dialog.getNextNumber()); params.put("contrast", dialog.getNextNumber());
                } else if (ImagePreparation.LOCAL_CONTRAST.equals(kind)) {
                    params.put("radius", dialog.getNextNumber()); params.put("amount", dialog.getNextNumber()); params.put("max_gain", dialog.getNextNumber());
                } else {
                    params.put("radius", dialog.getNextNumber()); params.put("strength", dialog.getNextNumber()); params.put("mode", dialog.getNextChoice());
                }
                Treatment treatment = new Treatment(); treatment.image = imp; treatment.session = session; treatment.params = params;
                treatment.region = useArea ? HF46.independent(imp.getRoi()) : null; captured[0] = treatment; return "OK";
            } catch (Exception e) { return error(e); }
        }});
        if (!"OK".equals(captureStatus)) return captureStatus;
        final Treatment treatment = captured[0]; final ImagePreparation.PreviewTicket ticket;
        try { ticket = treatment.session.computePreview(kind, treatment.params, treatment.region); }
        catch (Exception e) { return error(e); }
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                if (image() != treatment.image) throw new IllegalArgumentException("La imagen cambio mientras se calculaba la vista previa.");
                treatment.session.installPreview(ticket);
                GenericDialog confirm = new GenericDialog("Vista previa de preparacion");
                confirm.addMessage("La imagen muestra la vista previa. Aplicar incorpora este tratamiento a la receta; Cancelar recupera el estado anterior.");
                confirm.setOKLabel("Aplicar"); confirm.showDialog();
                if (confirm.wasCanceled()) { treatment.session.cancelPreview(); return "CANCEL"; }
                treatment.session.commitPreview(); return "OK";
            } catch (Exception e) {
                if (treatment.session.hasPreview()) try { treatment.session.cancelPreview(); } catch (Exception ignored) { }
                return error(e);
            }
        }});
    }
    public static String preparationAction(final String action) {
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                ImagePreparation.Session session = ImagePreparation.Session.get(image());
                if (session == null) throw new IllegalArgumentException("No hay preparacion de una fuente registrada.");
                if ("undo".equals(action)) return session.undo() ? "OK" : "OK|Sin tratamiento que deshacer";
                if ("redo".equals(action)) return session.redo() ? "OK" : "OK|Sin tratamiento que rehacer";
                if ("cancel".equals(action)) { session.cancelPreview(); return "OK"; }
                if ("recipe".equals(action)) return JSON.toJson(session.snapshot().toMap());
                if ("adopt_external".equals(action)) {
                    GenericDialog dialog = new GenericDialog("Conservar cambios externos");
                    dialog.addTextAreas("", null, 5, 60);
                    dialog.addMessage("Describa los cambios que hizo en Fiji. Se conservaran los pixeles y sus hashes, con una marca de receta incompleta; no se inferiran filtros ni parametros.");
                    dialog.showDialog(); if (dialog.wasCanceled()) return "CANCEL";
                    session.adoptExternal(dialog.getNextText()); return "OK";
                }
                if ("reset".equals(action)) {
                    GenericDialog dialog = new GenericDialog("Recuperar imagen original");
                    dialog.addMessage("Se recupera la copia original y se vacia la receta vigente. Puede deshacer esta accion con Deshacer tratamiento.");
                    dialog.showDialog(); if (dialog.wasCanceled()) return "CANCEL";
                    session.reset(); return "OK";
                }
                throw new IllegalArgumentException("Accion de preparacion no disponible.");
            } catch (Exception e) { return error(e); }
        }});
    }
    private static final class Switch { ImagePlus image; ImageProcessor pixels; ImagePreparation.Session session; double min, max; String[] labels; }
    public static String beginSwitch(final String unused) {
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                ImagePlus imp = WindowManager.getCurrentImage(); Switch snapshot = new Switch(); snapshot.image = imp;
                if (imp != null) { snapshot.pixels = imp.getProcessor().duplicate(); snapshot.min = imp.getDisplayRangeMin(); snapshot.max = imp.getDisplayRangeMax(); snapshot.labels = LABELS.get(imp); snapshot.session = ImagePreparation.Session.get(imp); }
                SWITCHES.push(snapshot); return "OK";
            } catch (Exception e) { return error(e); }
        }});
    }
    public static String endSwitch(final String action) {
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                if (SWITCHES.isEmpty()) return "OK"; Switch snapshot = SWITCHES.pop(); ImagePlus imp = snapshot.image;
                if ("rollback".equals(action) && imp != null) {
                    if (snapshot.session != null) ImagePreparation.Session.attach(snapshot.session);
                    imp.setProcessor(snapshot.pixels.duplicate()); imp.setDisplayRange(snapshot.min, snapshot.max);
                    if (snapshot.labels != null) LABELS.put(imp, snapshot.labels); else LABELS.remove(imp);
                    imp.updateAndDraw();
                }
                LOADS.clear(); return "OK";
            } catch (Exception e) { return error(e); }
        }});
    }
}
