package cavity.light;

import ij.ImagePlus;
import ij.WindowManager;
import ij.gui.OvalRoi;
import ij.gui.Roi;
import ij.plugin.frame.RoiManager;
import java.awt.geom.Rectangle2D;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;

/** Transparent initial size/separation suggestions; never creates or accepts objects. */
public final class DetectorAssistant {
    private DetectorAssistant() {}
    static final class Recommendation {
        final int count;
        final double median, lower, upper, separation;
        Recommendation(int n, double m, double low, double high, double gap) {
            count=n; median=m; lower=low; upper=high; separation=gap;
        }
    }
    private static String value(Roi r, String key) {
        String v=r.getProperty(key); return v==null?"":v;
    }
    private static String value(ImagePlus image, String key) {
        Object v=image.getProperty(key); return v==null?"":String.valueOf(v);
    }
    static double quantile(List<Double> data, double q) {
        double p=(data.size()-1)*q; int lo=(int)Math.floor(p), hi=(int)Math.ceil(p);
        return data.get(lo)+(data.get(hi)-data.get(lo))*(p-lo);
    }
    static Recommendation recommend(Roi[] rois, String project, String image, String sha, double sx, double sy) {
        if(project.isEmpty()||image.isEmpty()||!sha.matches("[0-9a-fA-F]{64}"))
            throw new IllegalArgumentException("Falta el contexto de la imagen registrada.");
        if(!Double.isFinite(sx)||!Double.isFinite(sy)||sx<=0||sy<=0)
            throw new IllegalArgumentException("Confirme primero una escala fisica valida.");
        Set<String> ids=new HashSet<String>(); List<Double> sizes=new ArrayList<Double>();
        for(Roi r:rois) {
            if(r==null||!(value(r,"Type").equals("cavity")||value(r,"Object_type").equals("cavity")))continue;
            String id=value(r,"Cavity_id"), serial=value(r,"Cavity_serial");
            long number;
            try { number=Long.parseLong(serial); } catch(Exception e) {
                throw new IllegalArgumentException("Hay cavidades sin identidad verificable; revise el aviso de identidad.");
            }
            if(number<=0||!id.equals(String.format(java.util.Locale.ROOT,"CAV_%06d",number))||
               !id.equals(r.getName())||!ids.add(id))
                throw new IllegalArgumentException("Hay identidades inconsistentes o duplicadas; no se usan para ajustar el detector.");
            if(!project.equals(value(r,"Project_id"))||!image.equals(value(r,"Image_id"))||
               !sha.equalsIgnoreCase(value(r,"Source_sha256")))
                throw new IllegalArgumentException("Las cavidades no corresponden a la imagen activa.");
            if(!(r instanceof OvalRoi)||!value(r,"Cavity_class").equals("confirmed")||
               value(r,"Manual_excluded").equals("1")||value(r,"Edge_intersecting").equals("1")||
               (!value(r,"Duplicate_status").isEmpty()&&!value(r,"Duplicate_status").equals("clear")))continue;
            Rectangle2D.Double b=r.getFloatBounds();
            double diameter=Math.sqrt((b.width*sx)*(b.height*sy));
            if(Double.isFinite(diameter)&&diameter>0)sizes.add(diameter);
        }
        if(sizes.size()<5)throw new IllegalArgumentException("Se necesitan al menos cinco cavidades confirmadas, no excluidas ni de borde, con identidad consistente.");
        Collections.sort(sizes); double median=quantile(sizes,.5), pixel=2*Math.max(sx,sy);
        double lower=Math.max(pixel,quantile(sizes,.1)*.5);
        double upper=Math.max(lower*1.5,quantile(sizes,.9)*1.5);
        double separation=Math.max(pixel,median*.35);
        if(!Double.isFinite(upper)||!Double.isFinite(separation))throw new IllegalArgumentException("Escala o geometria fuera de rango.");
        return new Recommendation(sizes.size(),median,lower,upper,separation);
    }
    /** OK|N|median_nm|min_nm|max_nm|separation_nm, read-only on the event thread. */
    public static String suggestions(String unused) {
        return HF4.ui(new Callable<String>() { public String call() {
            try {
                ImagePlus imp=WindowManager.getCurrentImage(); RoiManager rm=RoiManager.getInstance2();
                if(imp==null||rm==null)throw new IllegalArgumentException("Abra una imagen con cavidades confirmadas.");
                Recommendation r=recommend(rm.getRoisAsArray(),value(imp,"CavityTEMLight.ProjectId"),
                    value(imp,"CavityTEMLight.ImageId"),value(imp,"CavityTEMLight.SourceSHA256"),
                    Double.parseDouble(value(imp,"CavityLightScaleXNm")),Double.parseDouble(value(imp,"CavityLightScaleYNm")));
                return "OK|"+r.count+"|"+r.median+"|"+r.lower+"|"+r.upper+"|"+r.separation;
            } catch(Exception e) { return "ERROR|"+String.valueOf(e.getMessage()).replace('\n',' '); }
        }});
    }
}
