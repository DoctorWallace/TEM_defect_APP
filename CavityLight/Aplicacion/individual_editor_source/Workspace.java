package cavity.light;

import ij.IJ;
import ij.ImagePlus;
import ij.Prefs;
import ij.WindowManager;
import ij.plugin.frame.RoiManager;
import java.awt.BorderLayout;
import java.awt.Container;
import java.awt.Dimension;
import java.awt.Frame;
import java.awt.GraphicsConfiguration;
import java.awt.GraphicsDevice;
import java.awt.GraphicsEnvironment;
import java.awt.GridLayout;
import java.awt.Insets;
import java.awt.Rectangle;
import java.awt.Toolkit;
import java.awt.Window;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JComboBox;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.Timer;

/** Window coordination only. Never replaces a canvas, changes a ROI, or closes an image. */
public final class Workspace {
    public static final String PANEL_MARKER = "CavityLight.Panel";
    private static final String CONTROLS_MARKER = "CavityLight.Workspace.Controls";
    private static final String PREF = "cavity.light.workspace.";
    private static WeakReference<JFrame> panelRef = new WeakReference<JFrame>(null);
    private static Timer preferenceTimer;
    private Workspace() {}

    /** Install once into the marked Cavity JFrame's BorderLayout SOUTH region. */
    public static String install(String unused) {
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                JFrame panel = findPanel();
                if (panel == null) return "ERROR|No se encuentra el panel de Cavity Light.";
                Container content = panel.getContentPane();
                if (!(content.getLayout() instanceof BorderLayout))
                    return "ERROR|El panel no admite los controles de espacio de trabajo.";
                Controls controls = controlsFor(panel);
                if (controls == null) {
                    BorderLayout layout = (BorderLayout) content.getLayout();
                    if (layout.getLayoutComponent(BorderLayout.SOUTH) != null)
                        return "ERROR|La zona inferior del panel ya contiene controles.";
                    controls = new Controls(panel);
                    panel.getRootPane().putClientProperty(CONTROLS_MARKER, controls);
                    content.add(controls, BorderLayout.SOUTH);
                    if (panel.isAlwaysOnTopSupported()) panel.setAlwaysOnTop(Prefs.get(PREF + "panel.top", false));
                    panel.validate();
                }
                panelRef = new WeakReference<JFrame>(panel);
                controls.refresh();
                return "OK|Controles de espacio de trabajo preparados.";
            } catch (Exception e) { return error(e); }
        }});
    }

    /** Macro bridge: show, hide, roi|0/1, toolbar|0/1, top|0/1, arrange|index, save, restore. */
    public static String action(final String request) {
        return HF4.ui(new Callable<String>() { public String call() {
            String result;
            try { result = actionOnEdt(request == null ? "" : request); }
            catch (Exception e) { result = error(e); }
            JFrame panel = findPanel();
            Controls controls = panel == null ? null : controlsFor(panel);
            if (controls != null) { controls.refresh(); controls.status(result); }
            return result;
        }});
    }

    private static String actionOnEdt(String request) throws Exception {
        String[] parts = request.split("\\|", -1);
        String command = parts[0];
        JFrame panel = findPanel();
        if (command.equals("show")) {
            if (panel == null) return "MISSING|Abra el panel principal de Cavity Light.";
            reveal(panel); panel.toFront();
            return "OK|Panel visible.";
        }
        if (panel == null) return "ERROR|Abra primero el panel principal de Cavity Light.";
        if (command.equals("hide")) {
            if (!canHide(usable(panel), usable(IJ.getInstance()), visibleImage(), true))
                return "ERROR|Mantenga visible la barra de Fiji o una imagen para poder recuperar el panel.";
            panel.setVisible(false); return "OK|Panel oculto. F2 recupera los controles desde la imagen.";
        }
        if (command.equals("roi")) {
            boolean visible = flag(parts);
            RoiManager manager = RoiManager.getInstance2();
            if (visible && manager == null) manager = new RoiManager();
            if (manager != null) { if (visible) reveal(manager); else manager.setVisible(false); }
            return "OK|ROI Manager " + (visible ? "visible." : "oculto; sus objetos se conservan.");
        }
        if (command.equals("toolbar")) {
            boolean visible = flag(parts);
            Frame toolbar = IJ.getInstance();
            if (toolbar == null) return "ERROR|No se encuentra la barra de Fiji.";
            if (!visible && !canHide(usable(panel), usable(toolbar), visibleImage(), false))
                return "ERROR|Mantenga visible el panel Cavity o una imagen para poder recuperar la barra.";
            if (visible) reveal(toolbar); else toolbar.setVisible(false);
            return "OK|Barra de Fiji " + (visible ? "visible." : "oculta; recuperable desde este panel.");
        }
        if (command.equals("top")) {
            boolean enabled = flag(parts);
            if (!panel.isAlwaysOnTopSupported()) return "ERROR|El sistema no admite mantener el panel delante.";
            panel.setAlwaysOnTop(enabled);
            Prefs.set(PREF + "panel.top", enabled); schedulePreferences();
            return "OK|Panel " + (enabled ? "delante de todas las aplicaciones." : "con orden normal de ventanas.");
        }
        if (command.equals("save")) return saveLayout(panel);
        if (command.equals("restore")) return restoreLayout(panel);
        if (command.equals("arrange")) {
            int monitor = parts.length == 2 ? Integer.parseInt(parts[1]) : -1;
            return arrange(panel, monitor);
        }
        return "ERROR|Accion de espacio de trabajo desconocida.";
    }

    private static boolean flag(String[] parts) {
        if (parts.length != 2 || !(parts[1].equals("0") || parts[1].equals("1")))
            throw new IllegalArgumentException("Indique 0 o 1 para cambiar la visibilidad o la chincheta.");
        return parts[1].equals("1");
    }

    private static boolean usable(Window window) {
        return window != null && window.isVisible() && (!(window instanceof Frame) ||
            ((((Frame) window).getExtendedState() & Frame.ICONIFIED) == 0));
    }

    private static boolean visibleImage() {
        ImagePlus image = WindowManager.getCurrentImage();
        return image != null && usable(image.getWindow());
    }

    private static void reveal(Window window) {
        if (window instanceof Frame) {
            Frame frame = (Frame) window;
            frame.setExtendedState(frame.getExtendedState() & ~Frame.ICONIFIED);
        }
        window.setVisible(true);
    }

    private static void place(Window window, Rectangle bounds) {
        // Maximized windows may ignore new bounds until their native state is normalized.
        if (window instanceof Frame) ((Frame) window).setExtendedState(Frame.NORMAL);
        window.setBounds(bounds);
    }

    static boolean canHide(boolean panelVisible, boolean toolbarVisible, boolean imageVisible, boolean hidePanel) {
        return imageVisible || (hidePanel ? toolbarVisible : panelVisible);
    }

    private static JFrame findPanel() {
        JFrame panel = panelRef.get();
        if (panel != null && panel.isDisplayable() && marked(panel)) return panel;
        Frame[] frames = Frame.getFrames();
        for (int i = frames.length - 1; i >= 0; i--)
            if (frames[i] instanceof JFrame && frames[i].isDisplayable() && marked((JFrame) frames[i])) {
                panel = (JFrame) frames[i]; panelRef = new WeakReference<JFrame>(panel); return panel;
            }
        return null;
    }

    private static boolean marked(JFrame frame) {
        Object marker = frame.getRootPane().getClientProperty(PANEL_MARKER);
        return Boolean.TRUE.equals(marker) || "true".equals(String.valueOf(marker));
    }

    private static Controls controlsFor(JFrame frame) {
        Object value = frame.getRootPane().getClientProperty(CONTROLS_MARKER);
        return value instanceof Controls ? (Controls) value : null;
    }

    private static Map<String, Window> windows(JFrame panel) {
        Map<String, Window> windows = new LinkedHashMap<String, Window>();
        windows.put("panel", panel);
        ImagePlus image = WindowManager.getCurrentImage();
        if (image != null && image.getWindow() != null) windows.put("image", image.getWindow());
        RoiManager manager = RoiManager.getInstance2();
        if (manager != null) windows.put("roi", manager);
        Frame toolbar = IJ.getInstance();
        if (toolbar != null) windows.put("toolbar", toolbar);
        return windows;
    }

    private static String arrange(JFrame panel, int requestedMonitor) {
        Map<String, Window> current = windows(panel);
        Window image = current.get("image");
        if (image == null) return "ERROR|Abra una imagen antes de organizar las ventanas.";
        List<Screen> screens = screens();
        if (screens.isEmpty()) return "ERROR|No se encuentra una pantalla disponible.";
        List<Rectangle> areas = areas(screens);
        int imageMonitor = monitorFor(image.getBounds(), areas);
        int target = requestedMonitor;
        if (target < 0) target = preferredMonitor(screens, imageMonitor);
        if (target < 0 || target >= screens.size()) return "ERROR|La pantalla seleccionada ya no esta disponible.";
        Window roi = current.get("roi"), toolbar = current.get("toolbar");
        Dimension toolbarSize = toolbar == null ? new Dimension(600, 90) : toolbar.getSize();
        LayoutPlan layout = plan(areas.get(imageMonitor), areas.get(target), toolbarSize,
            roi != null && roi.isVisible(), toolbar != null && toolbar.isVisible(), imageMonitor == target);
        // Only native window bounds change. ImageWindow.setLocationAndSize() is intentionally avoided:
        // it calls fitToWindow()/pack() and can replace the requested bounds or change magnification.
        place(image, layout.image); reveal(image);
        place(panel, layout.panel); reveal(panel);
        if (layout.roi != null) { place(roi, layout.roi); reveal(roi); }
        if (layout.toolbar != null) { place(toolbar, layout.toolbar); reveal(toolbar); }
        Prefs.set(PREF + "monitor.id", screens.get(target).id); schedulePreferences();
        return "OK|Ventanas organizadas " + (imageMonitor == target ? "en una pantalla." : "en dos pantallas.");
    }

    private static String saveLayout(JFrame panel) {
        Map<String, Window> current = windows(panel);
        for (String role : new String[] {"panel", "image", "roi", "toolbar"}) {
            Window window = current.get(role);
            String key = PREF + "saved." + role + ".";
            Prefs.set(key + "exists", window != null);
            if (window == null) continue;
            Rectangle b = window.getBounds();
            Prefs.set(key + "x", b.x); Prefs.set(key + "y", b.y);
            Prefs.set(key + "w", b.width); Prefs.set(key + "h", b.height);
            Prefs.set(key + "visible", window.isVisible());
            Prefs.set(key + "top", window.isAlwaysOnTop());
            Prefs.set(key + "state", window instanceof Frame ? ((Frame) window).getExtendedState() : Frame.NORMAL);
        }
        Prefs.set(PREF + "saved.present", true); Prefs.savePreferences();
        return "OK|Disposicion de ventanas guardada.";
    }

    private static String restoreLayout(JFrame panel) {
        if (!Prefs.get(PREF + "saved.present", false)) return "INFO|Guarde primero una disposicion de ventanas.";
        List<Rectangle> areas = areas(screens());
        if (areas.isEmpty()) return "ERROR|No se encuentra una pantalla disponible.";
        String roiKey = PREF + "saved.roi.";
        if (Prefs.get(roiKey + "exists", false) && Prefs.get(roiKey + "visible", false) && RoiManager.getInstance2() == null)
            new RoiManager();
        for (Map.Entry<String, Window> entry : windows(panel).entrySet()) {
            String key = PREF + "saved." + entry.getKey() + ".";
            if (!Prefs.get(key + "exists", false)) continue;
            Window window = entry.getValue();
            Rectangle current = window.getBounds();
            Rectangle saved = new Rectangle((int) Prefs.get(key + "x", current.x), (int) Prefs.get(key + "y", current.y),
                (int) Prefs.get(key + "w", current.width), (int) Prefs.get(key + "h", current.height));
            place(window, clampToScreens(saved, areas));
            if (window.isAlwaysOnTopSupported()) window.setAlwaysOnTop(Prefs.get(key + "top", false));
            if (window instanceof Frame) ((Frame) window).setExtendedState((int) Prefs.get(key + "state", Frame.NORMAL));
            window.setVisible(Prefs.get(key + "visible", true));
        }
        Prefs.set(PREF + "panel.top", panel.isAlwaysOnTop()); schedulePreferences();
        if (!usable(panel) && !usable(IJ.getInstance()) && !visibleImage()) {
            reveal(panel);
            return "OK|Disposicion restaurada; panel visible para recuperar los controles.";
        }
        return "OK|Disposicion restaurada en las pantallas disponibles.";
    }

    private static void schedulePreferences() {
        if (preferenceTimer == null) {
            preferenceTimer = new Timer(500, new ActionListener() { public void actionPerformed(ActionEvent event) {
                Prefs.savePreferences();
            }});
            preferenceTimer.setRepeats(false);
        }
        preferenceTimer.restart();
    }

    private static final class Screen {
        final String id;
        final Rectangle area;
        Screen(String id, Rectangle area) { this.id = id; this.area = new Rectangle(area); }
    }

    private static List<Screen> screens() {
        List<Screen> screens = new ArrayList<Screen>();
        if (GraphicsEnvironment.isHeadless()) return screens;
        for (GraphicsDevice device : GraphicsEnvironment.getLocalGraphicsEnvironment().getScreenDevices()) {
            GraphicsConfiguration config = device.getDefaultConfiguration();
            Rectangle bounds = config.getBounds();
            Insets insets = Toolkit.getDefaultToolkit().getScreenInsets(config);
            Rectangle usable = new Rectangle(bounds.x + insets.left, bounds.y + insets.top,
                Math.max(1, bounds.width - insets.left - insets.right),
                Math.max(1, bounds.height - insets.top - insets.bottom));
            screens.add(new Screen(device.getIDstring(), usable));
        }
        return screens;
    }

    private static List<Rectangle> areas(List<Screen> screens) {
        List<Rectangle> result = new ArrayList<Rectangle>();
        for (Screen screen : screens) result.add(new Rectangle(screen.area));
        return result;
    }

    private static int preferredMonitor(List<Screen> screens, int fallback) {
        String id = Prefs.get(PREF + "monitor.id", "");
        for (int i = 0; i < screens.size(); i++) if (screens.get(i).id.equals(id)) return i;
        return fallback;
    }

    /** Pure layout data. No ImagePlus, pixel, calibration, ROI or window reference is retained. */
    static final class LayoutPlan {
        final Rectangle image, panel, roi, toolbar;
        LayoutPlan(Rectangle image, Rectangle panel, Rectangle roi, Rectangle toolbar) {
            this.image = new Rectangle(image); this.panel = new Rectangle(panel);
            this.roi = roi == null ? null : new Rectangle(roi);
            this.toolbar = toolbar == null ? null : new Rectangle(toolbar);
        }
    }

    static LayoutPlan plan(Rectangle imageMonitor, Rectangle controlsMonitor, Dimension toolbarSize,
                           boolean roiVisible, boolean toolbarVisible, boolean sameMonitor) {
        requireArea(imageMonitor); requireArea(controlsMonitor);
        int gap = Math.max(1, Math.min(8, Math.min(imageMonitor.width, imageMonitor.height) / 40));
        Rectangle imageArea = inset(imageMonitor, gap), controlsArea = inset(controlsMonitor, gap);
        Rectangle toolbar = null;
        if (toolbarVisible) {
            int toolbarHeight = Math.max(1, Math.min(Math.max(1, toolbarSize.height), imageArea.height / 5));
            int toolbarWidth = Math.max(1, Math.min(imageArea.width, Math.max(1, toolbarSize.width)));
            toolbar = new Rectangle(imageArea.x, imageArea.y, toolbarWidth, toolbarHeight);
            imageArea.y += toolbarHeight + gap; imageArea.height -= toolbarHeight + gap;
        }
        Rectangle image, panel, roi = null;
        if (sameMonitor) {
            int panelWidth = Math.min(660, Math.max(360, (int) (imageArea.width * .38)));
            panelWidth = Math.min(panelWidth, Math.max(1, (imageArea.width - gap) / 2));
            image = new Rectangle(imageArea.x, imageArea.y, imageArea.width - panelWidth - gap, imageArea.height);
            controlsArea = new Rectangle(image.x + image.width + gap, imageArea.y, panelWidth, imageArea.height);
        } else image = new Rectangle(imageArea);
        if (roiVisible && !sameMonitor && controlsArea.width >= 900) {
            int roiWidth = Math.min(320, Math.max(230, controlsArea.width / 4));
            panel = new Rectangle(controlsArea.x, controlsArea.y, controlsArea.width - roiWidth - gap, controlsArea.height);
            roi = new Rectangle(panel.x + panel.width + gap, controlsArea.y, roiWidth, controlsArea.height);
        } else if (roiVisible) {
            int roiHeight = Math.min(240, Math.max(80, controlsArea.height / 3));
            roiHeight = Math.min(roiHeight, Math.max(1, (controlsArea.height - gap) / 2));
            panel = new Rectangle(controlsArea.x, controlsArea.y, controlsArea.width, controlsArea.height - roiHeight - gap);
            roi = new Rectangle(controlsArea.x, panel.y + panel.height + gap, controlsArea.width, roiHeight);
        } else panel = new Rectangle(controlsArea);
        return new LayoutPlan(image, panel, roi, toolbar);
    }

    private static Rectangle inset(Rectangle rectangle, int gap) {
        return new Rectangle(rectangle.x + gap, rectangle.y + gap, rectangle.width - 2 * gap, rectangle.height - 2 * gap);
    }

    private static void requireArea(Rectangle rectangle) {
        if (rectangle == null || rectangle.width < 32 || rectangle.height < 32)
            throw new IllegalArgumentException("La pantalla no tiene un area util suficiente.");
    }

    static int monitorFor(Rectangle window, List<Rectangle> usable) {
        if (usable == null || usable.isEmpty()) throw new IllegalArgumentException("No hay pantallas disponibles.");
        long best = -1;
        int index = 0;
        for (int i = 0; i < usable.size(); i++) {
            Rectangle intersection = window.intersection(usable.get(i));
            long overlap = intersection.width <= 0 || intersection.height <= 0 ? 0 : (long) intersection.width * intersection.height;
            if (overlap > best) { best = overlap; index = i; }
        }
        return index;
    }

    static Rectangle clampToScreens(Rectangle candidate, List<Rectangle> usable) {
        Rectangle screen = usable.get(monitorFor(candidate, usable));
        int width = Math.max(1, Math.min(candidate.width, screen.width));
        int height = Math.max(1, Math.min(candidate.height, screen.height));
        int x = Math.max(screen.x, Math.min(candidate.x, screen.x + screen.width - width));
        int y = Math.max(screen.y, Math.min(candidate.y, screen.y + screen.height - height));
        return new Rectangle(x, y, width, height);
    }

    private static String error(Exception error) {
        String message = error.getMessage();
        return "ERROR|" + (message == null ? error.getClass().getSimpleName() : message.replace('\n', ' '));
    }

    private static final class MonitorChoice {
        final String id;
        final int index;
        MonitorChoice(Screen screen, int index) { this.id = screen.id; this.index = index; }
        public String toString() { return "Controles en pantalla " + (index + 1); }
    }

    private static final class Controls extends JPanel {
        private final JFrame panel;
        private final JCheckBox roi = new JCheckBox("ROI Manager"), toolbar = new JCheckBox("Barra Fiji"), top = new JCheckBox("Siempre delante");
        private final JComboBox<MonitorChoice> monitor = new JComboBox<MonitorChoice>();
        private final JLabel status = new JLabel("Organice las ventanas o guarde su disposicion.");
        private boolean updating;
        private List<Screen> knownScreens = new ArrayList<Screen>();
        Controls(JFrame panel) {
            super(new GridLayout(4, 1, 4, 3)); this.panel = panel;
            setBorder(BorderFactory.createTitledBorder("Espacio de trabajo"));
            JPanel visibility = new JPanel(new GridLayout(1, 3, 3, 0));
            visibility.add(roi); visibility.add(toolbar); visibility.add(top); add(visibility);
            roi.setToolTipText("Ocultar conserva las ROIs. Mostrar recupera el mismo gestor.");
            toolbar.setToolTipText("Mostrar u ocultar la barra principal de Fiji.");
            top.setToolTipText("Mantener solo el panel Cavity delante de todas las aplicaciones.");
            roi.addActionListener(toggle("roi", roi)); toolbar.addActionListener(toggle("toolbar", toolbar)); top.addActionListener(toggle("top", top));
            JPanel arrangement = new JPanel(new BorderLayout(5, 0)); arrangement.add(monitor, BorderLayout.CENTER);
            JButton organize = new JButton("Organizar"); arrangement.add(organize, BorderLayout.EAST); add(arrangement);
            monitor.setToolTipText("La imagen mantiene su pantalla; los controles van a la pantalla elegida.");
            organize.addActionListener(new ActionListener() { public void actionPerformed(ActionEvent event) {
                MonitorChoice choice = (MonitorChoice) monitor.getSelectedItem();
                if (choice == null) { status("ERROR|No hay una pantalla seleccionada."); return; }
                List<Screen> actual = screens();
                int index = -1;
                for (int i = 0; i < actual.size(); i++) if (actual.get(i).id.equals(choice.id)) index = i;
                if (index < 0) { refresh(); status("ERROR|La pantalla cambio. Elija una pantalla disponible."); return; }
                Workspace.action("arrange|" + index);
            }});
            JPanel commands = new JPanel(new GridLayout(1, 3, 3, 0));
            commands.add(button("Guardar disposicion", "save")); commands.add(button("Restaurar", "restore"));
            commands.add(button("Ocultar panel", "hide")); add(commands); add(status);
        }
        private ActionListener toggle(final String command, final JCheckBox checkbox) {
            return new ActionListener() { public void actionPerformed(ActionEvent event) {
                if (!updating) Workspace.action(command + "|" + (checkbox.isSelected() ? "1" : "0"));
            }};
        }
        private JButton button(String text, final String command) {
            JButton button = new JButton(text);
            button.addActionListener(new ActionListener() { public void actionPerformed(ActionEvent event) { Workspace.action(command); }});
            return button;
        }
        void status(String message) {
            int split = message.indexOf('|');
            String text = split < 0 ? message : message.substring(split + 1);
            status.setText(text); status.setToolTipText(text);
        }
        void refresh() {
            updating = true;
            try {
                RoiManager manager = RoiManager.getInstance2();
                roi.setSelected(manager != null && manager.isVisible());
                Frame fiji = IJ.getInstance(); toolbar.setSelected(fiji != null && fiji.isVisible());
                toolbar.setEnabled(fiji != null); top.setSelected(panel.isAlwaysOnTop());
                top.setEnabled(panel.isAlwaysOnTopSupported());
                List<Screen> available = screens();
                boolean changed = available.size() != knownScreens.size();
                for (int i = 0; !changed && i < available.size(); i++)
                    changed = !available.get(i).id.equals(knownScreens.get(i).id) || !available.get(i).area.equals(knownScreens.get(i).area);
                if (changed) {
                    monitor.removeAllItems();
                    for (int i = 0; i < available.size(); i++) monitor.addItem(new MonitorChoice(available.get(i), i));
                    if (!available.isEmpty()) {
                        ImagePlus image = WindowManager.getCurrentImage();
                        Rectangle reference = image != null && image.getWindow() != null ? image.getWindow().getBounds() : panel.getBounds();
                        monitor.setSelectedIndex(preferredMonitor(available, monitorFor(reference, areas(available))));
                    }
                    knownScreens = available;
                }
            } finally { updating = false; }
        }
    }
}
