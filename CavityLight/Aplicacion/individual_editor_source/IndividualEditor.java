package cavity.light;

import ij.IJ;
import ij.ImagePlus;
import ij.WindowManager;
import ij.gui.OvalRoi;
import ij.gui.Roi;
import ij.plugin.frame.RoiManager;
import java.awt.geom.Rectangle2D;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.Properties;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Callable;

/** Small compatibility extension to the unchanged R9 HF4.6 runtime. */
public final class IndividualEditor {
    public static final String VERSION = "1.2.0-RC1-individual";
    private static PendingEdit pending;
    private IndividualEditor() {}
    public static String version() { return VERSION; }
    public static String install(String path) {
        if (!Files.isRegularFile(Paths.get(path))) return "ERROR|No se encuentra el editor: " + path;
        new ij.plugin.MacroInstaller().installFile(path);
        return "OK";
    }
    private static String fail(Exception e) { return "ERROR|" + String.valueOf(e.getMessage()).replace('\n', ' '); }

    /** Scale both original axes equally: preserve physical aspect ratio at any X/Y calibration. */
    public static OvalRoi resizedOval(Roi base, double cx, double cy, double diameter, double sx, double sy) throws Exception {
        if (!(base instanceof OvalRoi)) throw new IllegalArgumentException("La edicion numerica requiere una ROI Oval sin rotacion.");
        for (double n : new double[] {cx, cy, diameter, sx, sy})
            if (!Double.isFinite(n)) throw new IllegalArgumentException("Centro, diametro y escala deben ser finitos.");
        Rectangle2D.Double b = base.getFloatBounds();
        if (!(diameter > 0 && sx > 0 && sy > 0 && b.width > 0 && b.height > 0))
            throw new IllegalArgumentException("Diametro, ejes y escala deben ser positivos.");
        double currentDiameter = Math.sqrt((b.width * sx) * (b.height * sy));
        double factor = diameter / currentDiameter, w = b.width * factor, h = b.height * factor;
        if (!(Double.isFinite(w) && Double.isFinite(h) && w > 0 && h > 0))
            throw new IllegalArgumentException("Geometria fuera de rango.");
        OvalRoi result = new OvalRoi(cx - w / 2, cy - h / 2, w, h);
        result.copyAttributes(base);
        result.setName(base.getName());
        result.setGroup(base.getGroup());
        if (base.hasHyperStackPosition()) result.setPosition(base.getCPosition(), base.getZPosition(), base.getTPosition());
        else result.setPosition(base.getPosition());
        // Reader avoids ImageJ setProperties(String)'s UTF-8/Latin-1 conversion.
        Properties properties = new Properties();
        String text = base.getProperties();
        if (text != null) properties.load(new StringReader(text));
        for (String key : properties.stringPropertyNames()) result.setProperty(key, properties.getProperty(key));
        return result;
    }

    private static final class PendingEdit {
        ImagePlus image; Roi stored; int index; String token; Rectangle2D.Double bounds;
    }
    public static String prepareNumeric(String unused) {
        return HF4.ui(new Callable<String>() { public String call() throws Exception {
            pending = null;
            ImagePlus imp = WindowManager.getCurrentImage();
            RoiManager rm = RoiManager.getInstance2();
            if (!Identity.selectedMatches(imp, rm)) return "ERROR|La imagen y la seleccion no coinciden.";
            Roi roi = rm.getRoi(rm.getSelectedIndex());
            if (!(roi instanceof OvalRoi)) return "ERROR|Solo se admite una ROI Oval sin rotacion.";
            PendingEdit p = new PendingEdit();
            p.image = imp; p.stored = roi; p.index = rm.getSelectedIndex();
            p.bounds = roi.getFloatBounds(); p.token = UUID.randomUUID().toString(); pending = p;
            return p.token;
        }});
    }
    /** Reject a stale dialog if image, selected object or geometry changed while it was open. */
    public static String applyNumeric(final String request) {
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                String[] args = request.split("\\|", -1);
                PendingEdit p = pending; pending = null;
                RoiManager rm = RoiManager.getInstance2();
                if (args.length != 6 || p == null || !p.token.equals(args[0]))
                    throw new IllegalArgumentException("La edicion numerica ha caducado.");
                if (WindowManager.getCurrentImage() != p.image || rm == null || rm.getSelectedIndex() != p.index ||
                    p.index >= rm.getCount() || rm.getRoi(p.index) != p.stored ||
                    !Identity.selectedMatches(p.image, rm) || !p.bounds.equals(p.stored.getFloatBounds()) ||
                    !p.bounds.equals(p.image.getRoi().getFloatBounds()))
                    throw new IllegalArgumentException("La seleccion cambio; no se ha modificado ninguna ROI.");
                OvalRoi roi = resizedOval(p.stored, Double.parseDouble(args[1]), Double.parseDouble(args[2]),
                    Double.parseDouble(args[3]), Double.parseDouble(args[4]), Double.parseDouble(args[5]));
                String source = roi.getProperty("Measurement_source");
                roi.setProperty("Measurement_source", (source == null ? "" : source) + ";numeric_edit");
                roi.setProperty("Last_edit_method", "numeric_preserve_axes");
                roi.setProperty("Last_edit_ms", Long.toString(System.currentTimeMillis()));
                Identity.pending(roi);
                rm.setRoi(roi, p.index); rm.select(p.image, p.index); p.image.setRoi(roi);
                p.image.setProperty("CavityHF4.Dirty", "1");
                return "OK";
            } catch (Exception e) { return fail(e); }
        }});
    }

    /** Only windows opened by this import are ever closed on an import error. */
    public static String importDm(String path) {
        Set<Integer> before = new HashSet<Integer>();
        int[] ids = WindowManager.getIDList(); if (ids != null) for (int id : ids) before.add(id);
        String result = HF46.importDm(path);
        if (!result.startsWith("OK|")) {
            ids = WindowManager.getIDList();
            if (ids != null) for (int id : ids) if (!before.contains(id)) closeImported(Integer.toString(id));
        }
        return result;
    }
    public static String closeImported(final String id) {
        return HF4.ui(new Callable<String>() { public String call() {
            ImagePlus imp = WindowManager.getImage(Integer.parseInt(id));
            if (imp != null) { imp.changes = false; imp.close(); }
            return "OK";
        }});
    }
    /** Launch request is external to projects and consumed once, without changing preferences. */
    public static String takeLaunchRequest(String unused) {
        String path = System.getProperty("cavity.light.library.request", "");
        System.clearProperty("cavity.light.library.request");
        return path;
    }
    public static String launchResult(String result) {
        System.setProperty("cavity.light.library.result", result);
        return result;
    }
    public static String validComponent(String value) {
        if (value == null || value.isEmpty() || value.equals(".") || value.equals("..") ||
            value.indexOf('/') >= 0 || value.indexOf('\\') >= 0 || value.indexOf(':') >= 0 ||
            value.indexOf('|') >= 0 || value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0 || value.indexOf('\t') >= 0)
            return "0";
        return "1";
    }
    public static String switchDecision(final String canSave) {
        return HF4.ui(new Callable<String>() { public String call() {
            boolean save = "1".equals(canSave);
            String[] options = save ? new String[] {"Guardar revision y cambiar", "Descartar y cambiar", "Cancelar"} :
                new String[] {"Descartar y cambiar", "Cancelar"};
            int choice = javax.swing.JOptionPane.showOptionDialog(IJ.getInstance(),
                "Hay anotaciones en la sesion actual. Resuelve los cambios antes de cambiar de imagen o proyecto.",
                "Cambiar de sesion", javax.swing.JOptionPane.DEFAULT_OPTION, javax.swing.JOptionPane.QUESTION_MESSAGE,
                null, options, options[options.length - 1]);
            if (choice < 0 || choice == options.length - 1) return "cancel";
            return save && choice == 0 ? "save" : "discard";
        }});
    }
}
