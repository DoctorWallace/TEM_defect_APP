package cavity.light;

import java.awt.Dimension;
import java.awt.Rectangle;
import java.util.Arrays;
import java.util.List;

/** Pure window-layout checks: no Fiji windows, preferences, image source or project writes. */
public final class WorkspaceTest {
    private static int checks;
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
        checks++;
    }
    private static void inside(Rectangle window, Rectangle screen) {
        check(window != null && window.width > 0 && window.height > 0 && screen.contains(window),
            "Window outside usable screen: " + window + " / " + screen);
    }
    private static void apart(Rectangle a, Rectangle b) {
        check(a == null || b == null || !a.intersects(b), "Windows overlap: " + a + " / " + b);
    }
    private static void singleMonitor(int width, int height, boolean roi, boolean toolbar) {
        Rectangle screen = new Rectangle(27, 45, width, height), before = new Rectangle(screen);
        Dimension bar = new Dimension(700, 90), barBefore = new Dimension(bar);
        Workspace.LayoutPlan layout = Workspace.plan(screen, screen, bar, roi, toolbar, true);
        inside(layout.image, screen); inside(layout.panel, screen);
        if (roi) inside(layout.roi, screen); else check(layout.roi == null, "Hidden ROI should not occupy space");
        if (toolbar) inside(layout.toolbar, screen); else check(layout.toolbar == null, "Hidden toolbar should not occupy space");
        apart(layout.image, layout.panel); apart(layout.image, layout.roi); apart(layout.image, layout.toolbar);
        apart(layout.panel, layout.roi); apart(layout.panel, layout.toolbar); apart(layout.roi, layout.toolbar);
        check(screen.equals(before) && bar.equals(barBefore), "Layout changed input geometry");
        check(layout.image.x < layout.panel.x, "Panel should sit alongside image");
        layout.panel.x = -9999;
        check(screen.equals(before), "Layout rectangle aliases monitor bounds");
    }
    private static void twoMonitors(Rectangle imageScreen, Rectangle controlsScreen, boolean roi, boolean toolbar) {
        Rectangle imageBefore = new Rectangle(imageScreen), controlsBefore = new Rectangle(controlsScreen);
        Workspace.LayoutPlan layout = Workspace.plan(imageScreen, controlsScreen, new Dimension(900, 110), roi, toolbar, false);
        inside(layout.image, imageScreen); inside(layout.panel, controlsScreen);
        if (roi) inside(layout.roi, controlsScreen); else check(layout.roi == null, "Hidden ROI should not occupy controls monitor");
        if (toolbar) inside(layout.toolbar, imageScreen); else check(layout.toolbar == null, "Hidden toolbar should not occupy image monitor");
        apart(layout.image, layout.toolbar); apart(layout.panel, layout.roi);
        check(imageScreen.equals(imageBefore) && controlsScreen.equals(controlsBefore), "Two-monitor layout changed its source bounds");
    }
    private static void monitorRecovery() {
        Rectangle main = new Rectangle(0, 0, 1920, 1040), left = new Rectangle(-1600, -100, 1600, 900);
        List<Rectangle> both = Arrays.asList(main, left);
        Rectangle old = new Rectangle(-1550, -80, 600, 700), before = new Rectangle(old);
        check(Workspace.monitorFor(old, both) == 1, "Negative-coordinate monitor not recognized");
        check(Workspace.clampToScreens(old, both).equals(old), "Valid negative bounds should be preserved");
        Rectangle recovered = Workspace.clampToScreens(old, Arrays.asList(main));
        inside(recovered, main);
        check(recovered.width == old.width && recovered.height == old.height, "Recovery needlessly resizes fitting window");
        check(old.equals(before), "Recovery changed saved bounds");
        Rectangle oversized = new Rectangle(100, 20, 3000, 2000);
        inside(Workspace.clampToScreens(oversized, both), main);
        Rectangle cross = new Rectangle(-200, 10, 700, 600);
        check(Workspace.monitorFor(cross, both) == 0, "Largest intersection should select current monitor");
        Rectangle unreachable = new Rectangle(9999, 9999, 500, 500);
        check(Workspace.monitorFor(unreachable, both) == 0, "Unavailable screen should recover to primary");
        inside(Workspace.clampToScreens(unreachable, both), main);
        check(Workspace.clampToScreens(new Rectangle(10, 10, 0, -2), both).width == 1, "Invalid size should still produce usable bounds");
        try { Workspace.monitorFor(old, java.util.Collections.<Rectangle>emptyList()); throw new AssertionError("Accepted no screens"); }
        catch (IllegalArgumentException expected) { checks++; }
    }
    private static void noDataDependencies() {
        for (java.lang.reflect.Field field : Workspace.LayoutPlan.class.getDeclaredFields())
            check(field.getType() == Rectangle.class, "Layout retained non-window state: " + field);
        check(Workspace.action("show").startsWith("MISSING|"), "Missing panel must allow macro fallback");
        check(Workspace.action("save").startsWith("ERROR|"), "Headless save should require an existing panel");
        check(Workspace.install("").startsWith("ERROR|"), "Headless install should report missing panel");
        check(!Workspace.canHide(true,false,false,true), "Panel must remain when it is the last usable window");
        check(!Workspace.canHide(false,true,false,false), "Toolbar must remain when it is the last usable window");
        check(Workspace.canHide(true,true,false,true), "Visible toolbar can recover hidden panel");
        check(Workspace.canHide(true,true,false,false), "Visible panel can recover hidden toolbar");
        check(Workspace.canHide(false,false,true,true), "Visible image can recover panel with F2");
        check(Workspace.canHide(false,false,true,false), "Visible image can recover controls with F2");
    }
    public static void main(String[] args) {
        for (int[] size : new int[][] {{1920,1040},{1366,728},{1024,728},{640,440},{320,240}})
            for (boolean roi : new boolean[] {false,true})
                for (boolean toolbar : new boolean[] {false,true}) singleMonitor(size[0],size[1],roi,toolbar);
        for (boolean roi : new boolean[] {false,true}) for (boolean toolbar : new boolean[] {false,true}) {
            twoMonitors(new Rectangle(0,0,1920,1040),new Rectangle(-1600,-100,1600,900),roi,toolbar);
            twoMonitors(new Rectangle(-1600,-100,1600,900),new Rectangle(0,0,1920,1040),roi,toolbar);
            twoMonitors(new Rectangle(0,0,1920,1040),new Rectangle(1920,200,640,440),roi,toolbar);
        }
        monitorRecovery(); noDataDependencies();
        System.out.println("PASS " + checks + " workspace checks: one/two monitors, hidden windows, negative coordinates, monitor removal, immutable geometry, no image/ROI state and headless fallbacks.");
    }
}
