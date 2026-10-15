package cavity.light;

import ij.ImagePlus;
import ij.ImageStack;
import ij.gui.Line;
import ij.gui.OvalRoi;
import ij.gui.Overlay;
import ij.gui.Roi;
import ij.gui.ShapeRoi;
import ij.io.RoiEncoder;
import ij.measure.Calibration;
import ij.process.ByteProcessor;
import ij.process.ColorProcessor;
import ij.process.FloatProcessor;
import ij.process.ImageProcessor;
import ij.process.ShortProcessor;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Self-contained, headless checks; no project files, windows or global Fiji state. */
public final class ImagePreparationTest {
    private static int checks;
    private interface Action { void run(); }
    private static void truth(boolean value, String context) {
        if (!value) throw new AssertionError(context);
        checks++;
    }
    private static void near(double actual, double expected, double tolerance, String context) {
        truth(Math.abs(actual - expected) <= tolerance, context + ": " + actual + " != " + expected);
    }
    private static void rejects(Action action, String context) {
        try { action.run(); } catch (IllegalArgumentException expected) { checks++; return; }
        catch (IllegalStateException expected) { checks++; return; }
        throw new AssertionError("Accepted " + context);
    }
    private static Map<String, Object> map(Object... pairs) {
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        for (int i = 0; i < pairs.length; i += 2) result.put((String) pairs[i], pairs[i + 1]);
        return result;
    }
    private static Map<String, Object> binding() {
        return map("project_uid", "project-uid", "project_id", "P1", "image_id", "I1",
                   "source_sha256", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    }
    private static ImagePlus gradient() {
        ByteProcessor pixels = new ByteProcessor(32, 24);
        for (int y = 0; y < 24; y++) for (int x = 0; x < 32; x++) pixels.set(x, y, 35 + x * 3 + y);
        return new ImagePlus("immutable source", pixels);
    }
    private static ImagePreparation.Session session(ImagePlus image) {
        return ImagePreparation.Session.current(image, binding());
    }
    private static void testIsolationAndRegionalBrightness() {
        ImagePlus image = gradient();
        ImageProcessor importedProcessor = image.getProcessor();
        String originalHash = ImagePreparation.pixelHash(importedProcessor);
        Roi cavity = new OvalRoi(3.25, 4.5, 10.25, 7.5);
        cavity.setName("CAV_000007"); cavity.setProperty("Cavity_id", "CAV_000007");
        cavity.setProperty("Notes", "señal débil α / diámetro µm");
        byte[] cavityBefore = RoiEncoder.saveAsByteArray(cavity);
        Overlay overlay = new Overlay(cavity);
        image.setOverlay(overlay); image.setRoi(cavity);
        Calibration calibration = image.getCalibration(); calibration.pixelWidth = 0.2; calibration.pixelHeight = 0.4;
        image.setProperty("Scientific_value", "unchanged");
        Map<String, Object> sourceBinding = binding();
        ImagePreparation.Session s = ImagePreparation.Session.current(image, sourceBinding);
        sourceBinding.put("image_id", "MUTATED");
        truth(s.sourceBinding().get("image_id").equals("I1"), "binding isolated from caller");
        truth(image.getProcessor() != importedProcessor, "working processor detached from importer");
        Roi zone = new Roi(2, 3, 5, 4);
        Map<String, Object> params = map("brightness", 10, "contrast", 1);
        Map<String, Object> op = s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, params, zone);
        params.put("brightness", 999); zone.setLocation(20, 20);
        for (int y = 0; y < 24; y++) for (int x = 0; x < 32; x++) {
            int expected = importedProcessor.get(x, y) + (x >= 2 && x < 7 && y >= 3 && y < 7 ? 10 : 0);
            if (image.getProcessor().get(x, y) != expected) throw new AssertionError("regional brightness pixel");
        }
        checks++;
        truth(ImagePreparation.pixelHash(importedProcessor).equals(originalHash), "import source processor immutable");
        truth(ImagePreparation.pixelHash(s.originalProcessor()).equals(originalHash), "private original immutable");
        truth(image.getRoi() == cavity && image.getOverlay() == overlay, "same scientific ROI and overlay references");
        truth(Arrays.equals(cavityBefore, RoiEncoder.saveAsByteArray(cavity)), "scientific identity and geometry unchanged");
        truth(image.getCalibration() == calibration && calibration.pixelWidth == 0.2 && calibration.pixelHeight == 0.4, "calibration unchanged");
        truth(image.getProperty("Scientific_value").equals("unchanged"), "image properties unchanged");
        ImagePreparation.State state = s.snapshot();
        truth(state.regionFiles().size() == 1, "region bytes exported");
        Map<?, ?> region = (Map<?, ?>) op.get("region");
        truth(region.get("scope").equals("roi") && region.containsKey("coordinates") && region.containsKey("bounds"), "region geometry exported");
        ImageProcessor external = state.originalProcessor(); external.set(0, 0, 200);
        truth(ImagePreparation.pixelHash(state.originalProcessor()).equals(originalHash), "original getter returns independent copy");
        byte[] externalBytes = state.regionFiles().values().iterator().next(); externalBytes[0] = 0;
        truth(state.regionFiles().values().iterator().next()[0] != 0, "region getter returns independent copy");
        try { state.sourceBinding().put("image_id", "x"); throw new AssertionError("mutable binding"); }
        catch (UnsupportedOperationException expected) { checks++; }
        try { state.operations().clear(); throw new AssertionError("mutable operations"); }
        catch (UnsupportedOperationException expected) { checks++; }
    }
    private static void testPreviewAndUndo() {
        ImagePlus image = gradient(); ImagePreparation.Session s = session(image);
        String original = ImagePreparation.pixelHash(image.getProcessor());
        s.preview(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 10), null);
        truth(s.hasPreview() && s.operations().isEmpty(), "preview is not effective recipe");
        near(image.getProcessor().get(0, 0), 45, 0, "first preview");
        rejects(new Action() { public void run() { s.snapshot(); } }, "saving pending preview");
        s.preview(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 20), null);
        near(image.getProcessor().get(0, 0), 55, 0, "second preview starts from committed state");
        s.cancelPreview(); truth(ImagePreparation.pixelHash(image.getProcessor()).equals(original), "cancel exact pixels");
        truth(!s.canUndo() && s.operations().isEmpty(), "cancel does not create history");
        s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 10), new OvalRoi(2.5, 2.5, 12, 8));
        String first = ImagePreparation.pixelHash(image.getProcessor());
        s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 20), null);
        String second = ImagePreparation.pixelHash(image.getProcessor());
        truth(s.operations().size() == 2 && s.canUndo(), "two committed operations");
        truth(s.undo() && ImagePreparation.pixelHash(image.getProcessor()).equals(first), "undo exact pixels");
        truth(s.snapshot().operations().size() == 1, "undo suppresses recipe operation");
        truth(s.undo() && ImagePreparation.pixelHash(image.getProcessor()).equals(original), "second undo to original");
        truth(s.snapshot().regionFiles().isEmpty(), "undone regions absent from export");
        truth(s.redo() && s.redo() && ImagePreparation.pixelHash(image.getProcessor()).equals(second), "redo restores exact pixels");
        s.undo(); s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 3), null);
        truth(!s.canRedo() && s.operations().size() == 2, "new branch discards old redo and recipe");
        s.reset(); truth(ImagePreparation.pixelHash(image.getProcessor()).equals(original) && s.operations().isEmpty(), "reset original and empty recipe");
        truth(s.undo() && s.operations().size() == 2, "reset itself undoable");
    }
    private static void testAlgorithmsAndTypes() {
        FloatProcessor pixels = new FloatProcessor(64, 48);
        for (int y = 0; y < 48; y++) for (int x = 0; x < 64; x++) pixels.setf(x, y, 100 + x * 2 + (x % 2 == 0 ? -2 : 2));
        ImagePlus image = new ImagePlus("background", pixels); ImagePreparation.Session s = session(image);
        float before = pixels.getf(32, 20);
        s.apply(ImagePreparation.LOCAL_CONTRAST, map("radius_px", 5, "max_gain", 3, "target_stddev", 20), new Roi(16, 12, 32, 24));
        truth(image.getProcessor().getf(0, 0) == pixels.getf(0, 0), "local contrast outside zone unchanged");
        truth(Math.abs(image.getProcessor().getf(32, 20) - before) > 0.1, "local contrast enhances weak detail");
        s.undo();
        double slopeBefore = pixels.getf(48, 20) - pixels.getf(16, 20);
        s.apply(ImagePreparation.BACKGROUND_CORRECTION, map("radius", 5, "mode", "subtract"), null);
        double slopeAfter = image.getProcessor().getf(48, 20) - image.getProcessor().getf(16, 20);
        truth(Math.abs(slopeAfter) < Math.abs(slopeBefore) * 0.1, "background subtract removes slow illumination gradient");
        truth(image.getBitDepth() == 32 && image.getWidth() == 64 && image.getHeight() == 48, "float type and geometry preserved");
        s.reset();
        s.apply(ImagePreparation.BACKGROUND_CORRECTION, map("radius_px", 5, "mode", "divide"), null);
        truth(Math.abs(image.getProcessor().getf(48, 20) - image.getProcessor().getf(16, 20)) < 8, "background divide flattens positive gradient");
        ImagePlus byteImage = new ImagePlus("clip8", new ByteProcessor(2, 1, new byte[] {0, (byte) 255}));
        session(byteImage).apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("contrast", 2), null);
        truth(byteImage.getProcessor().get(0) == 0 && byteImage.getProcessor().get(1) == 255, "8-bit clipping");
        ImagePlus shortImage = new ImagePlus("clip16", new ShortProcessor(2, 1, new short[] {0, (short) 65535}, null));
        session(shortImage).apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("contrast", 2), null);
        truth(shortImage.getProcessor().get(0) == 0 && shortImage.getProcessor().get(1) == 65535, "16-bit unsigned clipping");
        ImagePlus floatImage = new ImagePlus("float", new FloatProcessor(2, 1, new float[] {-12, 20}));
        session(floatImage).apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", -30), null);
        near(floatImage.getProcessor().getf(0), -42, 0, "float values are not clipped to integer range");
    }
    private static void testRecoveryAndValidation() {
        ImagePlus image = gradient(); ImagePreparation.Session s = session(image);
        ShapeRoi region = new ShapeRoi(new Roi(2, 3, 8, 10)).or(new ShapeRoi(new OvalRoi(15, 3, 10, 10)));
        s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 4), region);
        s.apply(ImagePreparation.LOCAL_CONTRAST, map("radius", 3, "amount", 0.4), null);
        image.getProcessor().setMinAndMax(20, 180);
        ImagePreparation.State saved = s.snapshot();
        ImagePreparation.State decoded = ImagePreparation.State.fromMap(saved.toMap(), saved.originalProcessor(), saved.workingProcessor(), saved.regionFiles());
        ImagePlus reopened = new ImagePlus("reopen", saved.originalProcessor());
        ImagePreparation.Session restored = ImagePreparation.Session.restore(reopened, decoded);
        truth(ImagePreparation.pixelHash(reopened.getProcessor()).equals(ImagePreparation.pixelHash(image.getProcessor())), "reload uses exact pixels without replay");
        truth(restored.operations().equals(saved.operations()), "reload preserves effective recipe");
        truth(!restored.canUndo(), "historical undo is explicitly unavailable after reload");
        truth(reopened.getProcessor().getMin() == 20 && reopened.getProcessor().getMax() == 180, "reload preserves display range");
        restored.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 1), null);
        truth(restored.undo() && restored.operations().size() == 2, "new undo works after reload");
        truth(ImagePreparation.Session.get(reopened) == restored, "restore attaches registry");
        ImagePreparation.Session.attach(s); truth(ImagePreparation.Session.get(image) == s, "attach preserves prior session reference");
        rejects(new Action() { public void run() { ImagePreparation.Session.current(image, map("project_uid", "other", "image_id", "I1", "source_sha256", binding().get("source_sha256"))); } }, "source rebinding");
        ImageProcessor tampered = saved.workingProcessor(); tampered.set(0, 0, 255);
        rejects(new Action() { public void run() { ImagePreparation.State.fromMap(saved.toMap(), saved.originalProcessor(), tampered, saved.regionFiles()); } }, "tampered working snapshot");
        rejects(new Action() { public void run() { ImagePreparation.State.fromMap(saved.toMap(), saved.originalProcessor(), saved.workingProcessor(), new LinkedHashMap<String, byte[]>()); } }, "missing region ROI");
        Map<String, Object> invalid = new LinkedHashMap<String, Object>(saved.toMap());
        invalid.put("operations", new ArrayList<Map<String, Object>>());
        rejects(new Action() { public void run() { ImagePreparation.State.fromMap(invalid, saved.originalProcessor(), saved.workingProcessor(), saved.regionFiles()); } }, "unrecorded pixels with empty recipe");
        String unchanged = ImagePreparation.pixelHash(image.getProcessor());
        for (final Map<String, Object> params : Arrays.asList(map("brightness", Double.NaN), map("contrast", -1), map("typo", 1))) {
            rejects(new Action() { public void run() { s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, params, null); } }, "invalid brightness params");
            truth(ImagePreparation.pixelHash(image.getProcessor()).equals(unchanged) && !s.hasPreview(), "failed treatment leaves pixels and preview unchanged");
        }
        rejects(new Action() { public void run() { s.preview(ImagePreparation.LOCAL_CONTRAST, map("radius", 0), null); } }, "zero radius");
        rejects(new Action() { public void run() { s.preview(ImagePreparation.BRIGHTNESS_CONTRAST, map(), new Line(1, 2, 3, 4)); } }, "line treatment zone");
        rejects(new Action() { public void run() { s.preview(ImagePreparation.BRIGHTNESS_CONTRAST, map(), new Roi(1000, 1000, 4, 4)); } }, "empty treatment zone");
        rejects(new Action() { public void run() { new ImagePreparation.Session(new ImagePlus("rgb", new ColorProcessor(4, 4)), binding()); } }, "colour image");
        ImageStack stack = new ImageStack(4, 4); stack.addSlice(new ByteProcessor(4, 4)); stack.addSlice(new ByteProcessor(4, 4));
        rejects(new Action() { public void run() { new ImagePreparation.Session(new ImagePlus("stack", stack), binding()); } }, "stack image");
        image.getProcessor().set(0, 0, 250);
        rejects(new Action() { public void run() { s.snapshot(); } }, "external unrecorded processing");
        rejects(new Action() { public void run() { s.undo(); } }, "undo must not silently discard external edits");
    }
    private static void testExplicitExternalEditsAndHistoryLimit() {
        ImagePlus image = gradient(); ImagePreparation.Session s = session(image);
        String original = ImagePreparation.pixelHash(image.getProcessor());
        s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 2), null);
        String tracked = ImagePreparation.pixelHash(image.getProcessor());
        image.getProcessor().set(0, 0, 201);
        String edited = ImagePreparation.pixelHash(image.getProcessor());
        rejects(new Action() { public void run() { s.adoptExternal("  "); } }, "external edits without description");
        Map<String, Object> operation = s.adoptExternal("Filtro externo de Fiji, parámetros no registrados");
        truth(operation.get("kind").equals(ImagePreparation.EXTERNAL_PIXEL_CHANGES), "external operation explicitly identified");
        ImagePreparation.State external = s.snapshot();
        truth(external.toMap().get("recipe_complete").equals(false), "external edits are marked incomplete recipe");
        truth(ImagePreparation.pixelHash(external.workingProcessor()).equals(edited), "external exact pixels are saved");
        ImagePreparation.State decoded = ImagePreparation.State.fromMap(external.toMap(), external.originalProcessor(), external.workingProcessor(), external.regionFiles());
        truth(decoded.operations().size() == 2 && decoded.toMap().get("recipe_complete").equals(false), "external snapshot can be recovered with honest provenance");
        Map<String, Object> falselyComplete = new LinkedHashMap<String, Object>(external.toMap()); falselyComplete.put("recipe_complete", true);
        rejects(new Action() { public void run() { ImagePreparation.State.fromMap(falselyComplete, external.originalProcessor(), external.workingProcessor(), external.regionFiles()); } }, "false completeness claim");
        truth(s.undo() && ImagePreparation.pixelHash(image.getProcessor()).equals(tracked), "external adoption undo restores prior pixels");
        truth(s.snapshot().toMap().get("recipe_complete").equals(true), "undo removes incomplete operation");
        truth(s.redo() && ImagePreparation.pixelHash(image.getProcessor()).equals(edited), "external adoption redo restores exact pixels");
        s.reset(); truth(s.snapshot().toMap().get("recipe_complete").equals(true), "reset clears incomplete recipe");
        truth(ImagePreparation.pixelHash(image.getProcessor()).equals(original), "reset after external edits restores immutable original");
        s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 1), null);
        rejects(new Action() { public void run() { s.adoptExternal("nothing changed"); } }, "false external adoption when pixels match");
        // The bounded pixel history must preserve the whole effective recipe, including earlier operations.
        for (int i = 0; i < 24; i++) s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 1), null);
        truth(s.snapshot().operations().size() == 25, "bounded history keeps full effective recipe");
        int undone = 0; while (s.undo()) undone++;
        truth(undone == 15 && s.snapshot().operations().size() == 10, "bounded history stops at its declared baseline");
    }
    private static void testIntensityCalibrationAndSubpixelRegion() {
        ImagePlus calibrated = gradient(), plain = gradient();
        calibrated.getCalibration().setFunction(Calibration.STRAIGHT_LINE, new double[] {17, 3}, "intensity");
        Roi region = new OvalRoi(2.25, 3.25, 10.5, 8.5);
        ImagePreparation.Session a = session(calibrated), b = session(plain);
        a.apply(ImagePreparation.LOCAL_CONTRAST, map("radius", 3), region);
        b.apply(ImagePreparation.LOCAL_CONTRAST, map("radius", 3), region);
        truth(ImagePreparation.pixelHash(calibrated.getProcessor()).equals(ImagePreparation.pixelHash(plain.getProcessor())), "filters use raw samples independently of intensity calibration");
        truth(calibrated.getCalibration().getCoefficients()[0] == 17 && calibrated.getCalibration().getCoefficients()[1] == 3, "intensity calibration preserved");
        ByteProcessor pixels = new ByteProcessor(4, 4); pixels.setValue(10); pixels.fill();
        ImagePlus fractional = new ImagePlus("fractional", pixels); ImagePreparation.Session s = session(fractional);
        s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 1), new Roi(0.75, 0.75, 1.5, 1.5));
        truth(fractional.getProcessor().get(1, 1) == 11 && fractional.getProcessor().get(0, 0) == 10
              && fractional.getProcessor().get(2, 2) == 10, "subpixel rectangle uses centres in floating geometry");
    }
    private static void testDetachedPreviewTickets() {
        ImagePlus image = gradient(); ImagePreparation.Session s = session(image);
        String original = ImagePreparation.pixelHash(image.getProcessor());
        Map<String, Object> parameters = map("brightness", 7);
        Roi region = new Roi(2, 3, 4, 5);
        ImagePreparation.PreviewTicket ticket = s.computePreview(ImagePreparation.BRIGHTNESS_CONTRAST, parameters, region);
        truth(ImagePreparation.pixelHash(image.getProcessor()).equals(original) && !s.hasPreview(), "worker computation leaves displayed image and session unchanged");
        parameters.put("brightness", 100); region.setLocation(20, 20);
        ImageProcessor exposed = ticket.processor(); exposed.set(0, 0, 0);
        s.installPreview(ticket);
        truth(image.getProcessor().get(2, 3) == 51 && image.getProcessor().get(0, 0) == 35, "ticket owns detached pixels, region and parameters");
        rejects(new Action() { public void run() { s.installPreview(ticket); } }, "same preview ticket installed twice");
        s.cancelPreview();
        ImagePreparation.PreviewTicket stale = s.computePreview(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 7), null);
        s.apply(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 1), null);
        String changed = ImagePreparation.pixelHash(image.getProcessor());
        rejects(new Action() { public void run() { s.installPreview(stale); } }, "late preview overwriting new operation");
        truth(ImagePreparation.pixelHash(image.getProcessor()).equals(changed), "stale result leaves current pixels unchanged");
        s.undo();
        rejects(new Action() { public void run() { s.installPreview(stale); } }, "late preview after undo returns to same old frame");
        ImagePlus otherImage = gradient(); ImagePreparation.Session other = session(otherImage);
        ImagePreparation.PreviewTicket current = s.computePreview(ImagePreparation.BRIGHTNESS_CONTRAST, map("brightness", 7), null);
        rejects(new Action() { public void run() { other.installPreview(current); } }, "ticket from another session");
        ImagePreparation.Session replacement = ImagePreparation.Session.restore(image, s.snapshot());
        rejects(new Action() { public void run() { s.installPreview(current); } }, "late preview after session replacement");
        truth(ImagePreparation.Session.get(image) == replacement, "replacement remains attached");
    }
    public static void main(String[] args) {
        try {
            testIsolationAndRegionalBrightness(); testPreviewAndUndo(); testAlgorithmsAndTypes(); testRecoveryAndValidation();
            testExplicitExternalEditsAndHistoryLimit(); testIntensityCalibrationAndSubpixelRegion();
            testDetachedPreviewTickets();
            System.out.println("PASS " + checks + " checks: source isolation, region geometry, scientific ROIs, previews, effective recipe, undo/redo, reset, background/local contrast, types, snapshot reload, hashes and drift.");
        } finally {
            // GaussianBlur uses ImageJ's non-daemon executor; this standalone JVM owns it.
            ij.util.ThreadUtil.threadPoolExecutor.shutdown();
        }
    }
}
