package cavity.light;

import ij.ImagePlus;
import ij.WindowManager;
import ij.gui.OvalRoi;
import ij.gui.Roi;
import ij.process.ByteProcessor;
import ij.process.ImageProcessor;
import java.awt.EventQueue;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** Synthetic pixels only, no Fiji window, real source or historical project writes. */
public final class RevisionWorkspaceTest {
    private static int checks;
    private static void truth(boolean value, String message) { if (!value) throw new AssertionError(message); checks++; }
    private static void ok(String result) { truth(result.equals("OK") || result.startsWith("OK|"), result); }
    private static byte[] pixels(ImageProcessor processor) { return ((byte[]) processor.getPixels()).clone(); }
    private static String json(Map<String, Object> value) { return new com.google.gson.Gson().toJson(value); }
    private static Map<String, Object> settings(String revision) {
        return RevisionWorkspace.map("project", RevisionWorkspace.map("id", "P1", "uid", "project-uid", "name", "Sample"),
            "image", RevisionWorkspace.map("id", "I1", "sha256", String.join("", Collections.nCopies(64, "a")), "width_px", 32, "height_px", 24),
            "scale", RevisionWorkspace.map("active_nm_per_px_x", 0.1, "active_nm_per_px_y", 0.2, "confirmed", 1),
            "bands", RevisionWorkspace.map("width_nm", 5.5, "count", 8), "revision_id", revision);
    }
    private static ImagePlus source(String name) {
        byte[] data = new byte[32 * 24];
        for (int i = 0; i < data.length; i++) data[i] = (byte) (20 + (i * 7) % 180);
        return new ImagePlus(name, new ByteProcessor(32, 24, data));
    }
    private static void writeAuthority(Path stage, String revision, String workspaceDigest) throws Exception {
        String text = "revision_id\t" + revision + "\nproject_id\tP1\nproject_uid\tproject-uid\nimage_id\tI1\nsource_sha256\t" +
            String.join("", Collections.nCopies(64, "a")) + "\nroi_zip_sha256\t" + RevisionWorkspace.sha(stage.resolve("cavity_rois.zip")) + "\n";
        if (workspaceDigest != null) text += "workspace_sha256\t" + workspaceDigest + "\n";
        Files.write(stage.resolve("revision_manifest.tsv"), text.getBytes(StandardCharsets.UTF_8));
        Files.write(stage.resolve("session_metadata.json"), json(settings(revision)).getBytes(StandardCharsets.UTF_8));
    }
    private static void test(Path scratch) throws Exception {
        Map<String, Object> settings = settings("REV_1"); ImagePlus image = source("original");
        byte[] original = pixels(image.getProcessor());
        OvalRoi cavity = new OvalRoi(2.25, 4.5, 6.25, 7.75); cavity.setName("CAV_000001");
        cavity.setProperty("Type", "cavity"); cavity.setProperty("Cavity_id", "CAV_000001"); cavity.setProperty("Cavity_serial", "1");
        image.setRoi(cavity); String properties = cavity.getProperties();
        WindowManager.setTempCurrentImage(image);
        ok(RevisionWorkspace.initialize(json(settings)));
        ImagePreparation.Session session = ImagePreparation.Session.get(image);
        session.apply("brightness_contrast", RevisionWorkspace.map("brightness", 10.0, "contrast", 1.1), new Roi(3, 4, 10, 8));
        byte[] processed = pixels(image.getProcessor());
        session.apply("background_correction", RevisionWorkspace.map("radius", 4.0, "strength", 0.2, "mode", "subtract"), null);
        truth(session.undo(), "undo treatment");
        truth(Arrays.equals(processed, pixels(image.getProcessor())), "undo restores exact pixels");
        truth(cavity.getProperties().equals(properties), "scientific identity is unchanged");
        truth(Arrays.equals(original, pixels(session.originalProcessor())), "source baseline is unchanged");

        Path target = scratch.resolve("REV_1"); String opened = RevisionWorkspace.beginRevision(target.toString()); ok(opened);
        Path stage = Paths.get(opened.substring(3)); HF46.writeZip(stage.resolve("cavity_rois.zip"), Collections.<Roi>singletonList(cavity));
        Roi liveOnly = new Roi(23, 16, 6, 6); liveOnly.setName("LIVE_ONLY");
        image.setRoi(liveOnly); image.setOverlay(new ij.gui.Overlay(liveOnly));
        String digest = RevisionWorkspace.writeWorkspace(stage, "REV_1", "Señal débil α", "Trabajo intermedio: zona corregida", settings,
            image, session.snapshot());
        java.awt.image.BufferedImage annotated = javax.imageio.ImageIO.read(stage.resolve("workspace/annotated_view.png").toFile());
        ImagePlus expectedView = RevisionWorkspace.detached(image, session.snapshot().workingProcessor());
        expectedView.setOverlay(RevisionWorkspace.annotationOverlay(new Roi[] {cavity}, false));
        ImagePlus expectedFlat = expectedView.flatten();
        try {
            truth(Arrays.equals(annotated.getRGB(0, 0, 32, 24, null, 0, 32), expectedFlat.getBufferedImage().getRGB(0, 0, 32, 24, null, 0, 32)),
                "annotated snapshot uses the saved authority ZIP when live annotations differ");
        } finally { expectedFlat.flush(); expectedView.flush(); }
        truth(image.getRoi() == liveOnly && image.getOverlay().get(0) == liveOnly, "saving annotations never changes the live selection or overlay");
        writeAuthority(stage, "REV_1", digest);
        Map<String, Object> saved = RevisionWorkspace.validateWorkspace(stage, "REV_1", RevisionWorkspace.binding(settings), true);
        truth(((java.util.List<?>) saved.get("operations")).size() == 1, "undone background is absent from effective recipe");
        truth("Señal débil α".equals(saved.get("name")), "Unicode name persists");
        truth(Files.exists(stage.resolve("workspace/working_image.tif")), "working TIFF exists");
        truth(Files.exists(stage.resolve("workspace/thumbnail.png")), "thumbnail exists");
        truth(!Files.exists(target), "revision is invisible before publication");
        ok(RevisionWorkspace.publishRevision(stage + "|" + target));
        truth(!Files.exists(stage) && Files.exists(target), "whole folder publishes atomically");
        truth(RevisionWorkspace.beginRevision(target.toString()).startsWith("ERROR|"), "historical revision cannot be overwritten");

        ImagePlus reopened = source("reopened source"); reopened.setRoi(cavity); WindowManager.setTempCurrentImage(reopened);
        ok(RevisionWorkspace.initialize(json(settings)));
        String request = json(RevisionWorkspace.map("revision_directory", target.toString(), "revision_id", "REV_1", "settings", settings));
        String staged = RevisionWorkspace.stageRestore(request); ok(staged);
        truth(Arrays.equals(original, pixels(reopened.getProcessor())), "staging restore changes no pixels");
        ok(RevisionWorkspace.beginSwitch("")); ok(RevisionWorkspace.applyRestore(staged.substring(3))); ok(RevisionWorkspace.endSwitch("commit"));
        truth(Arrays.equals(processed, pixels(reopened.getProcessor())), "reopening restores exact saved image without replay");
        truth(ImagePreparation.Session.get(reopened).operations().size() == 1, "recipe restores");
        truth(!ImagePreparation.Session.get(reopened).canUndo(), "old undo history is explicitly unavailable");

        // Corruption is rejected before either pixels or scientific ROIs change.
        Path working = target.resolve("workspace/working_image.tif"); byte[] valid = Files.readAllBytes(working);
        byte[] changed = valid.clone(); changed[changed.length - 1] ^= 1; Files.write(working, changed);
        String corrupt = RevisionWorkspace.stageRestore(request); truth(corrupt.startsWith("ERROR|"), "corrupt snapshot is rejected");
        truth(Arrays.equals(processed, pixels(reopened.getProcessor())), "failed restore preserves current pixels");
        Files.write(working, valid);

        // Rollback keeps the previous preparation session and its actual undo history.
        ImagePreparation.Session prior = ImagePreparation.Session.get(reopened);
        prior.apply("brightness_contrast", RevisionWorkspace.map("brightness", 3.0, "contrast", 1.0), null);
        byte[] priorPixels = pixels(reopened.getProcessor());
        ok(RevisionWorkspace.beginSwitch("")); staged = RevisionWorkspace.stageRestore(request); ok(staged);
        ok(RevisionWorkspace.applyRestore(staged.substring(3))); ok(RevisionWorkspace.endSwitch("rollback"));
        truth(Arrays.equals(priorPixels, pixels(reopened.getProcessor())), "rollback restores pixels");
        truth(ImagePreparation.Session.get(reopened) == prior && prior.canUndo(), "rollback keeps complete previous undo stack");

        // Nested project/image switches can include an empty outer image and a new inner image.
        ok(RevisionWorkspace.beginSwitch("")); ImagePlus other = source("other"); WindowManager.setTempCurrentImage(other);
        ok(RevisionWorkspace.initialize(json(settings))); ok(RevisionWorkspace.beginSwitch(""));
        ImagePreparation.Session.get(other).apply("brightness_contrast", RevisionWorkspace.map("brightness", 5.0, "contrast", 1.0), null);
        ok(RevisionWorkspace.endSwitch("rollback")); truth(Arrays.equals(original, pixels(other.getProcessor())), "nested inner rollback");
        ok(RevisionWorkspace.endSwitch("rollback")); truth(Arrays.equals(priorPixels, pixels(reopened.getProcessor())), "nested outer rollback");
        WindowManager.setTempCurrentImage(reopened);

        // Legacy revisions explicitly recover the original, never retain processing from another revision.
        Path legacy = Files.createDirectory(scratch.resolve("REV_LEGACY"));
        HF46.writeZip(legacy.resolve("cavity_rois.zip"), Collections.<Roi>singletonList(cavity)); writeAuthority(legacy, "REV_LEGACY", null);
        String legacyRequest = json(RevisionWorkspace.map("revision_directory", legacy.toString(), "settings", settings));
        truth(RevisionWorkspace.stageRestore(legacyRequest).equals("OK|LEGACY"), "legacy is supported");
        ok(RevisionWorkspace.applyRestore("LEGACY")); truth(Arrays.equals(original, pixels(reopened.getProcessor())), "legacy loads original pixels");
        truth(ImagePreparation.Session.get(reopened).operations().isEmpty(), "legacy has no invented recipe");
        writeAuthority(legacy, "REV_LEGACY", String.join("", Collections.nCopies(64, "b")));
        truth(RevisionWorkspace.stageRestore(legacyRequest).startsWith("ERROR|"), "declared missing workspace is rejected");

        String failed = RevisionWorkspace.beginRevision(scratch.resolve("REV_FAILED").toString()); ok(failed);
        Path incomplete = Paths.get(failed.substring(3));
        truth(RevisionWorkspace.publishRevision(incomplete + "|" + scratch.resolve("REV_FAILED")).startsWith("ERROR|"), "incomplete revision cannot publish");
        ok(RevisionWorkspace.abortRevision(incomplete.toString())); truth(!Files.exists(incomplete), "abort removes staged artifacts");
        try { RevisionWorkspace.inside(target, "../outside"); throw new AssertionError("accepted unsafe path"); }
        catch (IllegalArgumentException expected) { checks++; }
        WindowManager.setTempCurrentImage(null);
    }
    public static void main(String[] args) throws Exception {
        try { run(args); }
        finally { ij.util.ThreadUtil.threadPoolExecutor.shutdown(); }
    }
    private static void run(String[] args) throws Exception {
        Path scratchParent = Paths.get(args.length == 0 ? "work/revision_workspace" : args[0]); Files.createDirectories(scratchParent);
        final Path scratch = Files.createTempDirectory(scratchParent, "synthetic-"); final Throwable[] failure = new Throwable[1];
        final boolean keep = args.length > 1 && "--keep".equals(args[1]);
        try { EventQueue.invokeAndWait(new Runnable() { public void run() { try { test(scratch); } catch (Throwable t) { failure[0] = t; } }}); }
        finally { if (!keep) RevisionWorkspace.deleteTree(scratch); }
        if (failure[0] != null) throw new AssertionError("workspace test failed", failure[0]);
        System.out.println("PASS " + checks + " workspace checks: effective recipe, region separation, source immutability, exact snapshot recovery, hashes, rollback, nested switches, legacy original, atomic publication and save failure.");
        if (keep) System.out.println("FIXTURE " + scratch.resolve("REV_1"));
    }
}
