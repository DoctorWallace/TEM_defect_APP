package cavity.light;
import ij.gui.OvalRoi;
import ij.gui.Roi;
public final class DetectorAssistantTest {
    static final String SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    static int checks;
    static void truth(boolean value){if(!value)throw new AssertionError();checks++;}
    static Roi cavity(int n,double diameter){
        Roi r=new OvalRoi(3.25,4.5,diameter,diameter);
        r.setName(String.format("CAV_%06d",n));r.setProperty("Type","cavity");
        r.setProperty("Cavity_id",r.getName());r.setProperty("Cavity_serial",""+n);
        r.setProperty("Project_id","P");r.setProperty("Image_id","I");r.setProperty("Source_sha256",SHA);
        r.setProperty("Cavity_class","confirmed");r.setProperty("Manual_excluded","0");return r;
    }
    static void rejected(Roi[] rs,double sx,double sy){
        try{DetectorAssistant.recommend(rs,"P","I",SHA,sx,sy);throw new AssertionError();}
        catch(IllegalArgumentException expected){checks++;}
    }
    public static void main(String[] unused){
        Roi[] rs=new Roi[21];for(int i=0;i<20;i++)rs[i]=cavity(i+1,10+i%3);rs[20]=cavity(21,10000);
        String props=rs[0].getProperties();
        DetectorAssistant.Recommendation a=DetectorAssistant.recommend(rs,"P","I",SHA,1,1);
        truth(a.count==21);truth(a.median==11);truth(a.upper<30);truth(rs[0].getProperties().equals(props));
        DetectorAssistant.Recommendation b=DetectorAssistant.recommend(rs,"P","I",SHA,.1,.4);
        truth(Math.abs(b.median-a.median*.2)<1e-9);truth(b.lower>=.8);
        rejected(new Roi[]{cavity(1,10),cavity(2,11)},1,1);rejected(rs,0,1);rejected(rs,1,Double.NaN);
        rs[1].setProperty("Cavity_id",rs[0].getName());rejected(rs,1,1);rs[1]=cavity(2,11);
        rs[1].setProperty("Source_sha256","wrong");rejected(rs,1,1);rs[1]=cavity(2,11);
        rs[1].setName("different");rejected(rs,1,1);rs[1]=cavity(2,11);
        rs[1].setProperty("Cavity_class","uncertain");rs[2].setProperty("Manual_excluded","1");
        rs[3].setProperty("Edge_intersecting","1");rs[4].setProperty("Duplicate_status","suspect");
        DetectorAssistant.Recommendation c=DetectorAssistant.recommend(rs,"P","I",SHA,1,1);truth(c.count==17);
        System.out.println("PASS "+checks+" detector suggestion checks: robust outlier range, anisotropic scale, identity/binding rejection, exclusions, no source mutation.");
    }
}
