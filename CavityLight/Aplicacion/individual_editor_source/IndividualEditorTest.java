package cavity.light;

import ij.gui.OvalRoi;
import ij.gui.Roi;
import ij.ImagePlus;
import ij.WindowManager;
import ij.process.ByteProcessor;
import java.awt.geom.Rectangle2D;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Properties;
import java.io.StringReader;

/** No Fiji process, windows, source images or project writes. */
public class IndividualEditorTest {
    static int checks;
    static void near(double actual, double expected) {
        if (Math.abs(actual-expected)>1e-9*Math.max(1,Math.abs(expected))) throw new AssertionError(actual+" != "+expected);
    }
    static void truth(boolean condition) { if(!condition)throw new AssertionError(); }
    static void rejectsManaged(Roi original) throws Exception {
        String name=original.getName(),properties=original.getProperties();
        Rectangle2D.Double bounds=original.getFloatBounds();
        try{IndividualEditor.newEllipseFromSelection(original);throw new AssertionError("accepted managed ROI");}
        catch(IllegalArgumentException expected){}
        truth(java.util.Objects.equals(name,original.getName()));
        truth(java.util.Objects.equals(properties,original.getProperties()));
        truth(bounds.equals(original.getFloatBounds()));
        checks++;
    }
    static void testNewEllipseIdentity() throws Exception {
        OvalRoi historical=new OvalRoi(15.25,33.5,20.125,10.375);
        historical.setName("CAV_000007");historical.setProperty("Type","cavity");
        historical.setProperty("Cavity_id","CAV_000007");historical.setProperty("Cavity_serial","7");
        historical.setProperty("Notes","revisión α: diámetro µm");
        Roi aliased=(Roi)historical.clone();
        aliased.setName("CAV_000074");aliased.setProperty("Cavity_id","CAV_000074");aliased.setProperty("Cavity_serial","74");
        truth(historical.getName().equals("CAV_000007"));
        truth(historical.getProperty("Cavity_id").equals("CAV_000074"));
        truth(historical.getProperty("Cavity_serial").equals("74"));checks++;
        rejectsManaged(historical);rejectsManaged(aliased);

        for(String key:new String[]{"Type","Object_type","Cavity_id","Cavity_serial"}){
            OvalRoi marked=new OvalRoi(1.5,2.5,8.25,3.75);
            marked.setProperty("Notes","señal débil α");
            marked.setProperty(key,key.equals("Type")||key.equals("Object_type")?"analysis_mask":"corrupted_identity");
            rejectsManaged(marked);
            OvalRoi emptyMarker=new OvalRoi(1.5,2.5,8.25,3.75);
            emptyMarker.setProperties(key+"=\n");rejectsManaged(emptyMarker);
        }
        for(String name:new String[]{"CAV_000001","cav_000001"," CAV_user "}){
            OvalRoi marked=new OvalRoi(1,2,8,3);marked.setName(name);rejectsManaged(marked);
        }

        OvalRoi fresh=new OvalRoi(15.25,33.5,20.125,10.375);
        fresh.setName("selección nueva");fresh.setGroup(3);fresh.setPosition(2,3,4);
        fresh.setProperty("Notes","revisión α: señal débil, diámetro µm");
        fresh.setProperty("User_defined_property","valor propio");
        String before=fresh.getProperties();Rectangle2D.Double bounds=fresh.getFloatBounds();
        OvalRoi prepared=IndividualEditor.newEllipseFromSelection(fresh);
        truth(prepared!=fresh);truth(bounds.equals(prepared.getFloatBounds()));
        truth(prepared.getName().equals(fresh.getName()));truth(prepared.getGroup()==3);
        truth(prepared.getCPosition()==2&&prepared.getZPosition()==3&&prepared.getTPosition()==4);
        truth(prepared.getProperty("Notes").equals(fresh.getProperty("Notes")));
        truth(prepared.getProperty("User_defined_property").equals("valor propio"));
        prepared.setName("CAV_000074");prepared.setProperty("Type","cavity");
        prepared.setProperty("Cavity_id","CAV_000074");prepared.setProperty("Cavity_serial","74");
        prepared.setProperty("Notes","edited on prepared copy only");
        Roi registered=(Roi)prepared.clone();
        truth(registered.getName().equals("CAV_000074"));
        truth(registered.getProperty("Cavity_id").equals("CAV_000074"));
        truth(fresh.getName().equals("selección nueva"));truth(fresh.getProperties().equals(before));
        truth(fresh.getFloatBounds().equals(bounds));checks++;

        String historicalProps=historical.getProperties();
        OvalRoi isolated=IndividualEditor.freshIndependentOval(historical);
        isolated.setProperty("Cavity_id","CAV_009999");isolated.setProperty("Notes","changed copy");
        truth(historical.getProperties().equals(historicalProps));checks++;
        try{IndividualEditor.newEllipseFromSelection(new Roi(1,2,8,3));throw new AssertionError("accepted rectangle");}
        catch(IllegalArgumentException expected){}checks++;
        try{IndividualEditor.newEllipseFromSelection(null);throw new AssertionError("accepted no ROI");}
        catch(IllegalArgumentException expected){}checks++;

        ImagePlus image=new ImagePlus("new ellipse check",new ByteProcessor(256,256));
        image.setProperty("CavityHF4.Serial","73");
        java.awt.EventQueue.invokeAndWait(new Runnable(){public void run(){
            ImagePlus previous=WindowManager.getCurrentImage();
            WindowManager.setTempCurrentImage(image);
            try{
                image.setRoi(historical);String saved=historical.getProperties();
                truth(IndividualEditor.prepareNewEllipse("").startsWith("ERROR|"));
                truth(image.getRoi()==historical);truth(historical.getProperties().equals(saved));
                truth(image.getProperty("CavityHF4.Serial").equals("73"));checks++;
                image.setRoi(fresh);
                truth(IndividualEditor.prepareNewEllipse("").equals("OK"));
                truth(image.getRoi()!=fresh);truth(image.getRoi().getFloatBounds().equals(bounds));
                image.getRoi().setProperty("Cavity_id","CAV_000074");
                truth(fresh.getProperty("Cavity_id")==null);truth(fresh.getProperties().equals(before));
                truth(image.getProperty("CavityHF4.Serial").equals("73"));checks++;
            }finally{WindowManager.setTempCurrentImage(previous);}
        }});
    }
    static void testEllipse(double width, double height, double sx, double sy) throws Exception {
        OvalRoi original=new OvalRoi(15.25,33.5,width,height);
        original.setName("CAV_000661");original.setGroup(3);
        original.setProperty("Type","cavity");original.setProperty("Cavity_id","CAV_000661");
        original.setProperty("Project_id","P1");original.setProperty("Cavity_class","uncertain");
        original.setProperty("Manual_excluded","1");original.setProperty("Notes","revisión α: diámetro µm");
        original.setProperty("User_defined_property","valor propio");
        String properties=original.getProperties();Rectangle2D.Double before=original.getFloatBounds();
        double diameter=Math.sqrt(width*sx*height*sy)*2.5;
        OvalRoi edited=IndividualEditor.resizedOval(original,70,80,diameter,sx,sy);
        Rectangle2D.Double b=edited.getFloatBounds();
        near(b.getCenterX(),70);near(b.getCenterY(),80);near(b.width,width*2.5);near(b.height,height*2.5);
        near(Math.sqrt(b.width*sx*b.height*sy),diameter);near(b.width*sx/(b.height*sy),width*sx/(height*sy));
        truth(edited.getName().equals(original.getName()));truth(edited.getGroup()==3);
        Properties props=new Properties();props.load(new StringReader(properties));
        for(String key:props.stringPropertyNames())truth(props.getProperty(key).equals(edited.getProperty(key)));
        edited.setProperty("Notes","changed only on copy");truth(original.getProperties().equals(properties));
        truth(original.getFloatBounds().equals(before));
        Roi decoded=HF46.decode(ij.io.RoiEncoder.saveAsByteArray(edited),edited.getName());
        near(decoded.getFloatBounds().width,b.width);truth(decoded.getProperty("Cavity_class").equals("uncertain"));
        checks++;
    }
    public static void main(String[] args) throws Exception {
        testNewEllipseIdentity();
        testEllipse(20,10,1,1);testEllipse(20,10,0.1343,0.25);testEllipse(10,20,2,1);testEllipse(20,20,1,1);
        for(double invalid:new double[]{0,-1,Double.NaN,Double.POSITIVE_INFINITY}){
            try{IndividualEditor.resizedOval(new OvalRoi(0,0,20,10),1,2,invalid,1,1);throw new AssertionError("accepted invalid diameter");}
            catch(IllegalArgumentException expected){}
        }
        try{IndividualEditor.resizedOval(new Roi(0,0,20,10),1,2,15,1,1);throw new AssertionError("accepted rectangle");}
        catch(IllegalArgumentException expected){}checks++;
        truth(IndividualEditor.validComponent("REV_20260919_025550_534").equals("1"));
        for(String invalid:new String[]{"", "..", "../REV", "a/b", "a\\b", "C:x", "a|b", "a\tb"})truth(IndividualEditor.validComponent(invalid).equals("0"));checks++;
        System.setProperty("cavity.light.library.request","test.tsv");
        truth(IndividualEditor.takeLaunchRequest("").equals("test.tsv"));truth(IndividualEditor.takeLaunchRequest("").isEmpty());checks++;
        String source=new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8);
        ij.macro.Program program=new ij.macro.Tokenizer().tokenize(source);
        truth(program!=null);checks++;
        System.out.println("PASS "+checks+" headless checks: clone identity alias, managed-ellipse rejection, independent new ellipse, Unicode, axes, anisotropic calibration, geometry, all properties, source immutability, invalid inputs, path components, request consumption and IJM tokenization.");
    }
}
