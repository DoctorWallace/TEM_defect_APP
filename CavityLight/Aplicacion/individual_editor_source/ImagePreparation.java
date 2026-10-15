package cavity.light;

import ij.ImagePlus;
import ij.gui.Roi;
import ij.gui.ShapeRoi;
import ij.io.RoiDecoder;
import ij.io.RoiEncoder;
import ij.plugin.filter.GaussianBlur;
import ij.process.ByteProcessor;
import ij.process.FloatPolygon;
import ij.process.FloatProcessor;
import ij.process.ImageProcessor;
import ij.process.ShortProcessor;
import java.awt.geom.Rectangle2D;
import java.awt.Shape;
import java.awt.geom.AffineTransform;
import java.awt.geom.Ellipse2D;
import java.awt.geom.Path2D;
import java.awt.geom.RoundRectangle2D;
import java.io.IOException;
import java.lang.ref.WeakReference;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.WeakHashMap;

/**
 * Pixel preparation on a detached working processor, never on source files or
 * scientific ROIs. No command invokes ImageJ's global undo, ROI Manager or IJ.run.
 * Call mutations on ImageJ's event thread when the image has a visible window.
 * Float images must contain finite values; colour images and stacks are rejected.
 */
public final class ImagePreparation {
    public static final String ENGINE_VERSION = "1.0";
    public static final String BRIGHTNESS_CONTRAST = "brightness_contrast";
    public static final String LOCAL_CONTRAST = "local_contrast";
    public static final String BACKGROUND_CORRECTION = "background_correction";
    public static final String EXTERNAL_PIXEL_CHANGES = "external_pixel_changes";
    private static final int MAX_HISTORY = 16;
    private static final long MAX_HISTORY_BYTES = 128L * 1024 * 1024;
    private static final Map<ImagePlus, Session> SESSIONS = new WeakHashMap<ImagePlus, Session>();

    private ImagePreparation() {}

    /** Detached worker result. Only its originating, unchanged session may display it. */
    public static final class PreviewTicket {
        private final Session owner;
        private final Frame frame;
        private final int position;
        private final long generation;
        private final Prepared previousPreview;
        private final Prepared prepared;
        private PreviewTicket(Session owner, Frame frame, int position, long generation,
                              Prepared previousPreview, Prepared prepared) {
            this.owner = owner; this.frame = frame; this.position = position; this.generation = generation;
            this.previousPreview = previousPreview; this.prepared = prepared;
        }
        public Map<String, Object> operation() { return prepared.operation; }
        public ImageProcessor processor() { return detached(prepared.pixels); }
    }

    /** An immutable export; processor getters and regionFiles always return copies. */
    public static final class State {
        private final Map<String, Object> binding;
        private final List<Map<String, Object>> operations;
        private final Map<String, byte[]> regions;
        private final ImageProcessor original;
        private final ImageProcessor working;

        private State(Map<String, Object> binding, List<Map<String, Object>> operations,
                      ImageProcessor original, ImageProcessor working, Map<String, byte[]> regions) {
            this.binding = ImagePreparation.sourceBinding(binding, original);
            compatible(original, working);
            this.original = detached(original);
            this.working = detached(working);
            this.operations = immutableOperations(operations);
            this.regions = effectiveRegions(this.operations, regions);
            validateOperations(this.operations, this.regions, original, working);
        }

        public Map<String, Object> sourceBinding() { return binding; }
        public List<Map<String, Object>> operations() { return operations; }
        public ImageProcessor originalProcessor() { return detached(original); }
        public ImageProcessor workingProcessor() { return detached(working); }
        public Map<String, byte[]> regionFiles() { return copyRegions(regions); }

        public Map<String, Object> toMap() {
            Map<String, Object> result = new LinkedHashMap<String, Object>();
            result.put("schema_version", 1);
            result.put("engine_version", ENGINE_VERSION);
            result.put("source_binding", binding);
            result.put("width_px", working.getWidth());
            result.put("height_px", working.getHeight());
            result.put("bit_depth", working.getBitDepth());
            result.put("original_pixel_sha256", pixelHash(original));
            result.put("working_pixel_sha256", pixelHash(working));
            result.put("operations", operations);
            result.put("recipe_complete", recipeComplete(operations));
            // Recovery uses the saved pixels. Historical undo snapshots are not exported.
            result.put("undo_before_reload_available", false);
            return immutableMap(result);
        }

        /** Recover saved pixels without replaying filters or rounding a second time. */
        public static State fromMap(Map<String, Object> data, ImageProcessor original,
                                    ImageProcessor working, Map<String, byte[]> regionFiles) {
            if (data == null) throw new IllegalArgumentException("Falta el estado de preparacion.");
            if (integer(data.get("schema_version"), "schema_version") != 1)
                throw new IllegalArgumentException("Version de preparacion no compatible.");
            if (!ENGINE_VERSION.equals(data.get("engine_version")))
                throw new IllegalArgumentException("Motor de preparacion no compatible.");
            List<Map<String, Object>> operations = asOperations(data.get("operations"));
            if (!Boolean.valueOf(recipeComplete(operations)).equals(data.get("recipe_complete")))
                throw new IllegalArgumentException("El indicador de receta completa no corresponde a los tratamientos.");
            compatible(original, working);
            if (integer(data.get("width_px"), "width_px") != working.getWidth()
                || integer(data.get("height_px"), "height_px") != working.getHeight()
                || integer(data.get("bit_depth"), "bit_depth") != working.getBitDepth())
                throw new IllegalArgumentException("El snapshot tiene dimensiones o tipo distintos.");
            verifyHash(data.get("original_pixel_sha256"), original, "original");
            verifyHash(data.get("working_pixel_sha256"), working, "de trabajo");
            return new State(asMap(data.get("source_binding"), "source_binding"),
                             operations, original, working, regionFiles);
        }
    }

    /** An image has one source binding and one private, bounded pixel history. */
    public static final class Session {
        private final WeakReference<ImagePlus> image;
        private final Map<String, Object> binding;
        private final ImageProcessor original;
        private final List<Frame> history = new ArrayList<Frame>();
        private final Map<String, byte[]> regionStore = new LinkedHashMap<String, byte[]>();
        private int position;
        private long generation;
        private Prepared preview;

        /** Capture the original BEFORE any preparation has been applied. */
        public Session(ImagePlus workingImage, Map<String, Object> sourceBinding) {
            validImage(workingImage);
            this.image = new WeakReference<ImagePlus>(workingImage);
            this.original = detached(workingImage.getProcessor());
            this.binding = ImagePreparation.sourceBinding(sourceBinding, original);
            history.add(new Frame(original, Collections.<Map<String, Object>>emptyList()));
            // Detach from the processor supplied by an importer; do not mutate it later.
            install(original, false);
        }

        private Session(ImagePlus workingImage, State state) {
            validImage(workingImage);
            compatible(workingImage.getProcessor(), state.working);
            this.image = new WeakReference<ImagePlus>(workingImage);
            this.original = state.originalProcessor();
            this.binding = state.sourceBinding();
            this.regionStore.putAll(state.regionFiles());
            history.add(new Frame(state.working, state.operations));
            install(state.working, false);
        }

        public static Session current(ImagePlus image, Map<String, Object> binding) {
            synchronized (SESSIONS) {
                Session session = SESSIONS.get(image);
                if (session == null) {
                    session = new Session(image, binding);
                    SESSIONS.put(image, session);
                } else if (!session.binding.equals(ImagePreparation.sourceBinding(binding, session.original))) {
                    throw new IllegalArgumentException("La imagen ya esta vinculada a otra fuente.");
                }
                return session;
            }
        }

        public static Session get(ImagePlus image) {
            synchronized (SESSIONS) { return SESSIONS.get(image); }
        }

        public static void attach(Session session) {
            if (session == null) throw new IllegalArgumentException("Falta la sesion.");
            synchronized (SESSIONS) { SESSIONS.put(session.workingImage(), session); }
        }

        /** Restores exactly the saved image; undo starts with subsequent edits. */
        public static Session restore(ImagePlus image, State state) {
            if (state == null) throw new IllegalArgumentException("Falta el estado de preparacion.");
            Session result = new Session(image, state);
            attach(result);
            return result;
        }

        public ImagePlus workingImage() {
            ImagePlus result = image.get();
            if (result == null) throw new IllegalStateException("La imagen de trabajo ya no esta disponible.");
            return result;
        }
        public Map<String, Object> sourceBinding() { return binding; }
        public synchronized List<Map<String, Object>> operations() { return frame().operations; }
        public synchronized boolean hasPreview() { return preview != null; }
        public synchronized boolean canUndo() { return preview == null && position > 0; }
        public synchronized boolean canRedo() { return preview == null && position + 1 < history.size(); }
        public ImageProcessor originalProcessor() { return detached(original); }

        /** Replaces any previous preview; each preview starts from committed pixels. */
        public Map<String, Object> preview(String kind, Map<String, Object> params, Roi region) {
            return installPreview(computePreview(kind, params, region));
        }

        /** Capture briefly under the session lock, then compute on the caller's worker thread. */
        public PreviewTicket computePreview(String kind, Map<String, Object> params, Roi region) {
            ImageProcessor base;
            Frame capturedFrame;
            int capturedPosition;
            long capturedGeneration;
            Prepared capturedPreview;
            Roi capturedRegion;
            Map<String, Object> capturedParams;
            synchronized (this) {
                ensureUnchanged();
                capturedFrame = frame(); capturedPosition = position; capturedGeneration = generation;
                capturedPreview = preview;
                base = detached(capturedFrame.pixels);
                copyDisplay(workingImage().getProcessor(), base);
                capturedParams = params == null ? Collections.<String, Object>emptyMap() : immutableMap(params);
                capturedRegion = region == null ? null : decode(RoiEncoder.saveAsByteArray(region), "zona de vista previa");
            }
            Prepared calculated = prepare(base, kind, capturedParams, capturedRegion);
            return new PreviewTicket(this, capturedFrame, capturedPosition, capturedGeneration, capturedPreview, calculated);
        }

        /** Call on the event thread. A late worker cannot overwrite newer edits or another session. */
        public synchronized Map<String, Object> installPreview(PreviewTicket ticket) {
            Session registered = get(workingImage());
            if (registered != null && registered != this)
                throw new IllegalStateException("La sesion de la vista previa ya no esta activa.");
            if (ticket == null || ticket.owner != this || ticket.frame != frame() || ticket.position != position
                    || ticket.generation != generation || ticket.previousPreview != preview)
                throw new IllegalStateException("La vista previa esta desactualizada; calculela de nuevo.");
            ensureUnchanged();
            install(ticket.prepared.pixels, false);
            preview = ticket.prepared;
            generation++;
            return preview.operation;
        }

        public synchronized void commitPreview() {
            if (preview == null) throw new IllegalStateException("No hay una vista previa que confirmar.");
            ensureUnchanged();
            Prepared selected = preview;
            List<Map<String, Object>> operations = new ArrayList<Map<String, Object>>(frame().operations);
            operations.add(selected.operation);
            if (selected.regionFile != null) regionStore.put(selected.regionFile, selected.regionBytes.clone());
            push(selected.pixels, operations);
            preview = null;
            install(frame().pixels, true);
        }

        public synchronized void cancelPreview() {
            if (preview == null) return;
            ensureUnchanged();
            ImageProcessor committed = detached(frame().pixels);
            copyDisplay(workingImage().getProcessor(), committed);
            install(committed, false);
            preview = null;
            generation++;
        }

        public synchronized Map<String, Object> apply(String kind, Map<String, Object> params, Roi region) {
            if (preview != null) throw new IllegalStateException("Confirme o cancele primero la vista previa.");
            Map<String, Object> operation = preview(kind, params, region);
            commitPreview();
            return operation;
        }

        /** Explicitly acknowledge arbitrary Fiji edits; never invent their algorithm or parameters. */
        public synchronized Map<String, Object> adoptExternal(String description) {
            noPreview();
            if (description == null || description.trim().isEmpty())
                throw new IllegalArgumentException("Describa los cambios externos antes de incorporarlos.");
            ImagePlus image = workingImage();
            validImage(image);
            compatible(original, image.getProcessor());
            if (samePixels(frame().pixels, image.getProcessor()))
                throw new IllegalStateException("No hay cambios externos de pixeles que incorporar.");
            ImageProcessor pixels = detached(image.getProcessor());
            String before = pixelHash(frame().pixels), after = pixelHash(pixels);
            Map<String, Object> params = new LinkedHashMap<String, Object>();
            params.put("description", description.trim());
            params.put("before_pixel_sha256", before); params.put("after_pixel_sha256", after);
            Map<String, Object> region = new LinkedHashMap<String, Object>(); region.put("scope", "whole_image");
            Map<String, Object> operation = new LinkedHashMap<String, Object>();
            operation.put("id", UUID.randomUUID().toString()); operation.put("kind", EXTERNAL_PIXEL_CHANGES);
            operation.put("params", params); operation.put("region", region);
            operation.put("engine_version", ENGINE_VERSION);
            operation.put("input_pixel_sha256", before); operation.put("output_pixel_sha256", after);
            List<Map<String, Object>> effective = new ArrayList<Map<String, Object>>(frame().operations);
            effective.add(operation); push(pixels, effective); install(frame().pixels, true);
            return frame().operations.get(frame().operations.size() - 1);
        }

        public synchronized boolean undo() {
            noPreview();
            ensureUnchanged();
            if (position == 0) return false;
            position--;
            generation++;
            install(frame().pixels, true);
            return true;
        }

        public synchronized boolean redo() {
            noPreview();
            ensureUnchanged();
            if (position + 1 == history.size()) return false;
            position++;
            generation++;
            install(frame().pixels, true);
            return true;
        }

        /** Restoring the immutable original is itself undoable; the effective recipe is empty. */
        public synchronized void reset() {
            noPreview();
            ensureUnchanged();
            push(original, Collections.<Map<String, Object>>emptyList());
            install(frame().pixels, true);
        }

        /** Pending previews and pixel edits outside this helper cannot masquerade as a recipe. */
        public synchronized State snapshot() {
            noPreview();
            ensureUnchanged();
            return new State(binding, frame().operations, original, workingImage().getProcessor(), regionStore);
        }

        private Frame frame() { return history.get(position); }
        private void noPreview() {
            if (preview != null) throw new IllegalStateException("Confirme o cancele primero la vista previa.");
        }
        private void ensureUnchanged() {
            ImagePlus image = workingImage();
            validImage(image);
            ImageProcessor expected = preview == null ? frame().pixels : preview.pixels;
            if (!samePixels(image.getProcessor(), expected))
                throw new IllegalStateException("Cambios externos sin receta; recupere la preparacion guardada o use sus herramientas.");
        }
        private void install(ImageProcessor processor, boolean changed) {
            ImagePlus image = workingImage();
            boolean wasChanged = image.changes;
            // Dimensions and bit depth stay fixed, so ImagePlus preserves the current ROI.
            image.setProcessor(detached(processor));
            image.changes = wasChanged || changed;
            image.updateAndDraw();
        }
        private void push(ImageProcessor processor, List<Map<String, Object>> operations) {
            while (history.size() > position + 1) history.remove(history.size() - 1);
            history.add(new Frame(processor, operations));
            position++;
            generation++;
            long bytesPerFrame = (long) processor.getWidth() * processor.getHeight() * (processor.getBitDepth() / 8);
            // Keep at least one undo even for very large images.
            while (history.size() > 2 && (history.size() > MAX_HISTORY
                    || bytesPerFrame * history.size() > MAX_HISTORY_BYTES)) {
                history.remove(0);
                position--;
            }
            Set<String> retained = new HashSet<String>();
            for (Frame frame : history) retained.addAll(regionNames(frame.operations));
            regionStore.keySet().retainAll(retained);
        }
    }

    private static final class Frame {
        final ImageProcessor pixels;
        final List<Map<String, Object>> operations;
        Frame(ImageProcessor pixels, List<Map<String, Object>> operations) {
            this.pixels = detached(pixels);
            this.operations = immutableOperations(operations);
        }
    }
    private static final class Prepared {
        final ImageProcessor pixels;
        final Map<String, Object> operation;
        final String regionFile;
        final byte[] regionBytes;
        Prepared(ImageProcessor pixels, Map<String, Object> operation, String file, byte[] bytes) {
            this.pixels = pixels;
            this.operation = immutableMap(operation);
            this.regionFile = file;
            this.regionBytes = bytes;
        }
    }
    private static final class Region {
        final Roi roi;
        final Shape shape;
        final Map<String, Object> description;
        final String file;
        final byte[] bytes;
        Region(Roi source, String id, int width, int height) {
            Map<String, Object> description = new LinkedHashMap<String, Object>();
            if (source == null) {
                roi = null; shape = null; file = null; bytes = null;
                description.put("scope", "whole_image");
            } else {
                if (!source.isArea()) throw new IllegalArgumentException("La zona de tratamiento debe ser una ROI de area.");
                bytes = RoiEncoder.saveAsByteArray(source);
                if (bytes == null) throw new IllegalArgumentException("No se puede conservar la zona de tratamiento.");
                roi = decode(bytes, "zona");
                if (!roi.isArea()) throw new IllegalArgumentException("La zona guardada no es una ROI de area.");
                file = "regions/region_" + id + ".roi";
                Rectangle2D.Double b = roi.getFloatBounds();
                for (double value : new double[] {b.x, b.y, b.width, b.height}) finite(value, "geometria de la zona");
                if (!(b.width > 0 && b.height > 0)) throw new IllegalArgumentException("La zona esta vacia.");
                shape = regionShape(roi);
                description.put("scope", "roi");
                description.put("type", roi.getTypeAsString());
                Map<String, Object> bounds = new LinkedHashMap<String, Object>();
                bounds.put("x", b.x); bounds.put("y", b.y); bounds.put("width", b.width); bounds.put("height", b.height);
                description.put("bounds", bounds);
                FloatPolygon polygon = roi.getFloatPolygon();
                List<Double> xs = new ArrayList<Double>(), ys = new ArrayList<Double>();
                if (polygon != null) for (int i = 0; i < polygon.npoints; i++) {
                    xs.add((double) polygon.xpoints[i]); ys.add((double) polygon.ypoints[i]);
                }
                Map<String, Object> coordinates = new LinkedHashMap<String, Object>();
                coordinates.put("x", xs); coordinates.put("y", ys);
                description.put("coordinates", coordinates);
                description.put("roi_file", file);
                description.put("pixel_membership", "pixel_center");
            }
            this.description = immutableMap(description);
            if (count(width, height) == 0) throw new IllegalArgumentException("La zona no contiene pixeles de la imagen.");
        }
        boolean contains(int x, int y) { return shape == null || shape.contains(x + 0.5, y + 0.5); }
        int count(int width, int height) {
            if (roi == null) return width * height;
            int result = 0;
            for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) if (contains(x, y)) result++;
            return result;
        }
    }

    /** ImageJ 1.54p containsPoint returns false for subpixel bounds; use explicit geometry. */
    private static Shape regionShape(Roi roi) {
        Rectangle2D.Double b = roi.getFloatBounds();
        if (roi.getType() == Roi.OVAL) return new Ellipse2D.Double(b.x, b.y, b.width, b.height);
        if (roi.getType() == Roi.RECTANGLE) return roi.getCornerDiameter() == 0 ? b
                : new RoundRectangle2D.Double(b.x, b.y, b.width, b.height, roi.getCornerDiameter(), roi.getCornerDiameter());
        if (roi instanceof ShapeRoi) return AffineTransform.getTranslateInstance(roi.getBounds().x, roi.getBounds().y)
                .createTransformedShape(((ShapeRoi) roi).getShape());
        FloatPolygon polygon = roi.getFloatPolygon();
        if (polygon == null || polygon.npoints < 3) throw new IllegalArgumentException("La zona no tiene geometria de area.");
        Path2D.Double path = new Path2D.Double(Path2D.WIND_EVEN_ODD);
        path.moveTo(polygon.xpoints[0], polygon.ypoints[0]);
        for (int i = 1; i < polygon.npoints; i++) path.lineTo(polygon.xpoints[i], polygon.ypoints[i]);
        path.closePath(); return path;
    }

    private static Prepared prepare(ImageProcessor input, String kind, Map<String, Object> supplied, Roi selection) {
        validProcessor(input);
        String id = UUID.randomUUID().toString();
        Region region = new Region(selection, id, input.getWidth(), input.getHeight());
        Map<String, Object> params = new LinkedHashMap<String, Object>();
        if (supplied != null) params.putAll(supplied);
        ImageProcessor result = detached(input);
        double[] stats = statistics(input, region);
        if (BRIGHTNESS_CONTRAST.equals(kind)) {
            only(params, "brightness", "contrast", "center");
            double brightness = number(params, "brightness", 0);
            double contrast = bounded(params, "contrast", 1, 0, 32);
            double center = number(params, "center", (stats[0] + stats[1]) * 0.5);
            for (int y = 0; y < input.getHeight(); y++) for (int x = 0; x < input.getWidth(); x++)
                if (region.contains(x, y)) write(result, x, y, (input.getf(x, y) - center) * contrast + center + brightness);
        } else if (LOCAL_CONTRAST.equals(kind)) {
            only(params, "radius", "radius_px", "amount", "max_gain", "noise_floor", "target_stddev");
            double radius = radius(params);
            double amount = bounded(params, "amount", 1, 0, 1);
            double gainLimit = bounded(params, "max_gain", 3, 1, 32);
            double noise = number(params, "noise_floor", Math.max(1e-6, (stats[1] - stats[0]) / 255.0));
            if (!(noise > 0)) throw new IllegalArgumentException("noise_floor debe ser positivo.");
            double target = number(params, "target_stddev", stats[3]);
            if (!(target >= 0)) throw new IllegalArgumentException("target_stddev no puede ser negativo.");
            FloatProcessor mean = blurred(input, radius);
            FloatProcessor variance = rawFloat(input);
            float[] squares = (float[]) variance.getPixels();
            // Centre first to avoid cancellation and float overflow with large offsets.
            double origin = stats[2];
            for (int i = 0; i < squares.length; i++) {
                double centered = squares[i] - origin;
                if (centered * centered > Float.MAX_VALUE) throw new IllegalArgumentException("Rango demasiado amplio para contraste local.");
                squares[i] = (float) (centered * centered);
            }
            new GaussianBlur().blurGaussian(variance, radius, radius, 0.002);
            for (int y = 0; y < input.getHeight(); y++) for (int x = 0; x < input.getWidth(); x++) {
                if (!region.contains(x, y)) continue;
                double m = mean.getf(x, y), centeredMean = m - origin;
                double std = Math.sqrt(Math.max(0, variance.getf(x, y) - centeredMean * centeredMean));
                double gain = 1 + amount * (Math.max(1, Math.min(gainLimit, target / Math.max(noise, std))) - 1);
                write(result, x, y, m + (input.getf(x, y) - m) * gain);
            }
            params.put("algorithm", "gaussian_local_stddev_gain_v1");
        } else if (BACKGROUND_CORRECTION.equals(kind)) {
            only(params, "radius", "radius_px", "strength", "mode", "reference", "epsilon");
            double radius = radius(params);
            double strength = bounded(params, "strength", 1, 0, 1);
            Object modeValue = params.containsKey("mode") ? params.get("mode") : "subtract";
            if (!(modeValue instanceof String)) throw new IllegalArgumentException("mode debe ser subtract o divide.");
            String mode = (String) modeValue;
            if (!mode.equals("subtract") && !mode.equals("divide")) throw new IllegalArgumentException("mode debe ser subtract o divide.");
            params.put("mode", mode);
            FloatProcessor background = blurred(input, radius);
            double reference = number(params, "reference", statistics(background, region)[2]);
            double epsilon = number(params, "epsilon", Math.max(1e-6, Math.abs(reference) * 1e-6));
            if (!(epsilon > 0)) throw new IllegalArgumentException("epsilon debe ser positivo.");
            if (mode.equals("divide") && !(reference > epsilon))
                throw new IllegalArgumentException("La correccion por division necesita un fondo positivo.");
            for (int y = 0; y < input.getHeight(); y++) for (int x = 0; x < input.getWidth(); x++) {
                if (!region.contains(x, y)) continue;
                double value = input.getf(x, y), bg = background.getf(x, y);
                if (mode.equals("divide") && !(bg > epsilon))
                    throw new IllegalArgumentException("La correccion por division necesita un fondo positivo en toda la zona.");
                write(result, x, y, mode.equals("subtract") ? value - strength * (bg - reference)
                        : value * (1 - strength + strength * reference / bg));
            }
            params.put("algorithm", "gaussian_background_v1");
        } else throw new IllegalArgumentException("Tratamiento no reconocido: " + kind);
        Map<String, Object> operation = new LinkedHashMap<String, Object>();
        operation.put("id", id); operation.put("kind", kind); operation.put("params", params);
        operation.put("region", region.description);
        operation.put("engine_version", ENGINE_VERSION);
        operation.put("input_pixel_sha256", pixelHash(input));
        operation.put("output_pixel_sha256", pixelHash(result));
        operation.put("integer_clipping", input instanceof FloatProcessor ? "none" : "type_range_round_nearest");
        return new Prepared(result, operation, region.file, region.bytes);
    }

    private static FloatProcessor blurred(ImageProcessor input, double radius) {
        FloatProcessor result = rawFloat(input);
        result.resetRoi();
        new GaussianBlur().blurGaussian(result, radius, radius, 0.002);
        return result;
    }
    private static FloatProcessor rawFloat(ImageProcessor input) {
        // ImageProcessor.convertToFloat uses an intensity-calibration table when present.
        // Preparation consistently acts on raw digital samples, not calibrated intensities.
        float[] samples = new float[input.getWidth() * input.getHeight()];
        for (int i = 0; i < samples.length; i++) samples[i] = input.getf(i);
        return new FloatProcessor(input.getWidth(), input.getHeight(), samples);
    }
    private static double radius(Map<String, Object> params) {
        if (params.containsKey("radius") && params.containsKey("radius_px"))
            throw new IllegalArgumentException("Use un solo parametro radius_px.");
        if (params.containsKey("radius")) params.put("radius_px", params.remove("radius"));
        double radius = bounded(params, "radius_px", 32, 0.1, 4096);
        return radius; // Gaussian sigma in pixels, explicitly recorded in the recipe.
    }
    private static double[] statistics(ImageProcessor input, Region region) {
        double min = Double.POSITIVE_INFINITY, max = Double.NEGATIVE_INFINITY, mean = 0, m2 = 0;
        int n = 0;
        for (int y = 0; y < input.getHeight(); y++) for (int x = 0; x < input.getWidth(); x++) {
            double v = input.getf(x, y);
            finite(v, "pixel");
            if (!region.contains(x, y)) continue;
            min = Math.min(min, v); max = Math.max(max, v);
            n++; double delta = v - mean; mean += delta / n; m2 += delta * (v - mean);
        }
        return new double[] {min, max, mean, Math.sqrt(Math.max(0, m2 / n))};
    }
    private static void write(ImageProcessor target, int x, int y, double value) {
        finite(value, "resultado del tratamiento");
        if (target instanceof FloatProcessor) {
            if (Math.abs(value) > Float.MAX_VALUE) throw new IllegalArgumentException("Resultado fuera del rango float.");
            target.setf(x, y, (float) value);
        } else target.set(x, y, (int) Math.round(Math.max(0, Math.min(target instanceof ByteProcessor ? 255 : 65535, value))));
    }

    private static void validImage(ImagePlus image) {
        if (image == null) throw new IllegalArgumentException("No hay imagen de trabajo.");
        if (image.getStackSize() != 1) throw new IllegalArgumentException("La preparacion admite una imagen individual, sin pila.");
        validProcessor(image.getProcessor());
    }
    private static void validProcessor(ImageProcessor processor) {
        if (!(processor instanceof ByteProcessor || processor instanceof ShortProcessor || processor instanceof FloatProcessor))
            throw new IllegalArgumentException("La preparacion requiere una imagen gris de 8, 16 o 32 bits.");
        if (processor.getWidth() <= 0 || processor.getHeight() <= 0)
            throw new IllegalArgumentException("La imagen esta vacia.");
    }
    private static void compatible(ImageProcessor first, ImageProcessor second) {
        validProcessor(first); validProcessor(second);
        if (first.getWidth() != second.getWidth() || first.getHeight() != second.getHeight()
                || first.getBitDepth() != second.getBitDepth())
            throw new IllegalArgumentException("No se pueden cambiar dimensiones ni profundidad de bits.");
    }
    private static ImageProcessor detached(ImageProcessor source) {
        ImageProcessor result = source.duplicate();
        result.resetRoi();
        result.setMinAndMax(source.getMin(), source.getMax());
        return result;
    }
    private static void copyDisplay(ImageProcessor source, ImageProcessor target) {
        target.setMinAndMax(source.getMin(), source.getMax());
    }
    private static boolean samePixels(ImageProcessor first, ImageProcessor second) {
        if (first.getWidth() != second.getWidth() || first.getHeight() != second.getHeight()
                || first.getBitDepth() != second.getBitDepth()) return false;
        Object a = first.getPixels(), b = second.getPixels();
        if (a instanceof byte[] && b instanceof byte[]) return Arrays.equals((byte[]) a, (byte[]) b);
        if (a instanceof short[] && b instanceof short[]) return Arrays.equals((short[]) a, (short[]) b);
        if (a instanceof float[] && b instanceof float[]) return Arrays.equals((float[]) a, (float[]) b);
        return false;
    }

    /** Hash raw samples and image geometry, independent of display range and calibration. */
    public static String pixelHash(ImageProcessor processor) {
        validProcessor(processor);
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            hashInt(digest, processor.getWidth()); hashInt(digest, processor.getHeight()); hashInt(digest, processor.getBitDepth());
            Object pixels = processor.getPixels();
            if (pixels instanceof byte[]) digest.update((byte[]) pixels);
            else if (pixels instanceof short[]) for (short v : (short[]) pixels) {
                digest.update((byte) v); digest.update((byte) (v >>> 8));
            } else for (float v : (float[]) pixels) hashInt(digest, Float.floatToIntBits(v));
            return hex(digest.digest());
        } catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    private static void hashInt(MessageDigest digest, int value) {
        for (int shift = 0; shift < 32; shift += 8) digest.update((byte) (value >>> shift));
    }
    private static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) result.append(String.format(Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }
    private static void verifyHash(Object expected, ImageProcessor processor, String name) {
        if (!(expected instanceof String) || !pixelHash(processor).equals(expected))
            throw new IllegalArgumentException("No coincide el hash del snapshot " + name + ".");
    }

    private static Map<String, Object> sourceBinding(Map<String, Object> supplied, ImageProcessor processor) {
        if (supplied == null) throw new IllegalArgumentException("Falta el vinculo con la fuente.");
        Map<String, Object> result = new LinkedHashMap<String, Object>(supplied);
        for (String field : new String[] {"project_uid", "image_id", "source_sha256"}) {
            Object value = result.get(field);
            if (!(value instanceof String) || ((String) value).trim().isEmpty())
                throw new IllegalArgumentException("Falta la identidad de fuente: " + field);
        }
        String sha = ((String) result.get("source_sha256")).toLowerCase(Locale.ROOT);
        if (!sha.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("SHA-256 de fuente no valido.");
        result.put("source_sha256", sha);
        for (String field : new String[] {"width_px", "height_px"}) {
            int expected = field.equals("width_px") ? processor.getWidth() : processor.getHeight();
            if (result.containsKey(field) && integer(result.get(field), field) != expected)
                throw new IllegalArgumentException("Las dimensiones de fuente no coinciden.");
            result.put(field, expected);
        }
        return immutableMap(result);
    }
    private static void validateOperations(List<Map<String, Object>> operations, Map<String, byte[]> regions,
                                           ImageProcessor original, ImageProcessor working) {
        Set<String> ids = new HashSet<String>();
        String previousOutput = pixelHash(original);
        for (Map<String, Object> operation : operations) {
            Object id = operation.get("id");
            if (!(id instanceof String) || !((String) id).matches("[0-9a-fA-F-]{36}") || !ids.add((String) id))
                throw new IllegalArgumentException("Identidad de operacion no valida o repetida.");
            Object kind = operation.get("kind");
            if (!BRIGHTNESS_CONTRAST.equals(kind) && !LOCAL_CONTRAST.equals(kind) && !BACKGROUND_CORRECTION.equals(kind)
                    && !EXTERNAL_PIXEL_CHANGES.equals(kind))
                throw new IllegalArgumentException("Tipo de tratamiento no compatible.");
            if (!ENGINE_VERSION.equals(operation.get("engine_version")))
                throw new IllegalArgumentException("Motor de operacion no compatible.");
            asMap(operation.get("params"), "params");
            Map<String, Object> region = asMap(operation.get("region"), "region");
            if ("roi".equals(region.get("scope"))) {
                String name = regionName(region);
                Roi decoded = decode(regions.get(name), name);
                if (!decoded.isArea()) throw new IllegalArgumentException("La region de tratamiento no es de area.");
            } else if (!"whole_image".equals(region.get("scope"))) throw new IllegalArgumentException("Ambito de tratamiento desconocido.");
            String input = requireHash(operation.get("input_pixel_sha256"));
            String output = requireHash(operation.get("output_pixel_sha256"));
            if (EXTERNAL_PIXEL_CHANGES.equals(kind)) {
                Map<String, Object> params = asMap(operation.get("params"), "params");
                Object description = params.get("description");
                if (!(description instanceof String) || ((String) description).trim().isEmpty()
                        || !input.equals(params.get("before_pixel_sha256")) || !output.equals(params.get("after_pixel_sha256"))
                        || !"whole_image".equals(region.get("scope")))
                    throw new IllegalArgumentException("Los cambios externos necesitan descripcion y hashes coherentes.");
            }
            if (previousOutput != null && !previousOutput.equals(input))
                throw new IllegalArgumentException("La receta no forma una cadena de operaciones coherente.");
            previousOutput = output;
        }
        if (!previousOutput.equals(pixelHash(working)))
            throw new IllegalArgumentException("La receta no corresponde a los pixeles del snapshot.");
    }
    private static boolean recipeComplete(List<Map<String, Object>> operations) {
        for (Map<String, Object> operation : operations)
            if (EXTERNAL_PIXEL_CHANGES.equals(operation.get("kind"))) return false;
        return true;
    }
    private static String requireHash(Object value) {
        if (!(value instanceof String) || !((String) value).matches("[0-9a-f]{64}"))
            throw new IllegalArgumentException("Hash de operacion no valido.");
        return (String) value;
    }
    private static Roi decode(byte[] bytes, String name) {
        if (bytes == null) throw new IllegalArgumentException("Falta la ROI de la zona de tratamiento: " + name);
        try {
            Roi result = new RoiDecoder(bytes.clone(), name).getRoi();
            if (result == null) throw new IllegalArgumentException("ROI de zona no valida.");
            return result;
        } catch (IOException e) { throw new IllegalArgumentException("No se puede leer la ROI de zona.", e); }
    }
    private static String regionName(Map<String, Object> region) {
        Object name = region.get("roi_file");
        if (!(name instanceof String) || !((String) name).matches("regions/region_[0-9a-fA-F-]{36}\\.roi"))
            throw new IllegalArgumentException("Ruta interna de ROI no valida.");
        return (String) name;
    }
    private static Set<String> regionNames(List<Map<String, Object>> operations) {
        Set<String> names = new HashSet<String>();
        for (Map<String, Object> operation : operations) {
            Map<String, Object> region = asMap(operation.get("region"), "region");
            if ("roi".equals(region.get("scope"))) names.add(regionName(region));
        }
        return names;
    }
    private static Map<String, byte[]> effectiveRegions(List<Map<String, Object>> operations, Map<String, byte[]> supplied) {
        Map<String, byte[]> result = new LinkedHashMap<String, byte[]>();
        for (String name : regionNames(operations)) {
            byte[] bytes = supplied == null ? null : supplied.get(name);
            if (bytes == null) throw new IllegalArgumentException("Falta el archivo ROI de tratamiento: " + name);
            result.put(name, bytes.clone());
        }
        return Collections.unmodifiableMap(result);
    }
    private static Map<String, byte[]> copyRegions(Map<String, byte[]> supplied) {
        Map<String, byte[]> result = new LinkedHashMap<String, byte[]>();
        for (Map.Entry<String, byte[]> entry : supplied.entrySet()) result.put(entry.getKey(), entry.getValue().clone());
        return result;
    }

    private static void only(Map<String, Object> params, String... allowed) {
        Set<String> keys = new HashSet<String>(Arrays.asList(allowed));
        for (String key : params.keySet()) if (!keys.contains(key)) throw new IllegalArgumentException("Parametro no reconocido: " + key);
    }
    private static double number(Map<String, Object> params, String key, double fallback) {
        Object value = params.containsKey(key) ? params.get(key) : fallback;
        if (!(value instanceof Number)) throw new IllegalArgumentException(key + " debe ser numerico.");
        double result = ((Number) value).doubleValue(); finite(result, key); params.put(key, result); return result;
    }
    private static double bounded(Map<String, Object> params, String key, double fallback, double min, double max) {
        double value = number(params, key, fallback);
        if (value < min || value > max) throw new IllegalArgumentException(key + " debe estar entre " + min + " y " + max + ".");
        return value;
    }
    private static void finite(double value, String field) {
        if (!Double.isFinite(value)) throw new IllegalArgumentException(field + " debe ser finito.");
    }
    private static int integer(Object value, String field) {
        if (!(value instanceof Number)) throw new IllegalArgumentException("Falta el entero " + field);
        double number = ((Number) value).doubleValue();
        if (!Double.isFinite(number) || number != Math.rint(number) || number < 0 || number > Integer.MAX_VALUE)
            throw new IllegalArgumentException("Entero no valido: " + field);
        return (int) number;
    }
    private static List<Map<String, Object>> immutableOperations(List<Map<String, Object>> supplied) {
        List<Map<String, Object>> result = new ArrayList<Map<String, Object>>();
        for (Map<String, Object> operation : supplied) result.add(immutableMap(operation));
        return Collections.unmodifiableList(result);
    }
    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value, String field) {
        if (!(value instanceof Map)) throw new IllegalArgumentException("Falta el objeto " + field);
        return (Map<String, Object>) value;
    }
    private static List<Map<String, Object>> asOperations(Object value) {
        if (!(value instanceof List)) throw new IllegalArgumentException("Falta la lista de tratamientos.");
        List<Map<String, Object>> result = new ArrayList<Map<String, Object>>();
        for (Object operation : (List<?>) value) result.add(asMap(operation, "operation"));
        return result;
    }
    private static Map<String, Object> immutableMap(Map<String, Object> supplied) {
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        for (Map.Entry<?, ?> entry : supplied.entrySet()) {
            if (!(entry.getKey() instanceof String)) throw new IllegalArgumentException("Las claves de metadatos deben ser texto.");
            result.put((String) entry.getKey(), immutableValue(entry.getValue()));
        }
        return Collections.unmodifiableMap(result);
    }
    private static Object immutableValue(Object value) {
        if (value == null || value instanceof String || value instanceof Boolean) return value;
        if (value instanceof Number) {
            double number = ((Number) value).doubleValue(); finite(number, "metadato numerico");
            return number; // Normalise integers/doubles after JSON recovery for equality.
        }
        if (value instanceof Map) return immutableMap(asMap(value, "metadato"));
        if (value instanceof List) {
            List<Object> result = new ArrayList<Object>();
            for (Object item : (List<?>) value) result.add(immutableValue(item));
            return Collections.unmodifiableList(result);
        }
        throw new IllegalArgumentException("Metadato no serializable: " + value.getClass().getName());
    }
}
