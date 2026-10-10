package cavity.light;

import ij.gui.OvalRoi;
import ij.gui.Roi;
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
        System.out.println("PASS "+checks+" headless checks: axes, anisotropic calibration, geometry, all properties, source immutability, invalid inputs, path components, request consumption and IJM tokenization.");
    }
}
