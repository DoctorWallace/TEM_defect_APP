"""Create a temporary integration toolset. Only run against an explicit disposable project copy."""
import argparse
import json
from pathlib import Path


def literal(value):
    return json.dumps(str(value).replace('\\', '/'), ensure_ascii=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--allow-save-to-test-copy', action='store_true')
    parser.add_argument('--export', action='store_true', help='Also calculate a real individual-image RUN on the disposable copy.')
    args = parser.parse_args()
    if not args.allow_save_to_test_copy: parser.error('Must explicitly authorize the disposable project copy.')
    source = Path(__file__).with_name('Cavity_TEM_Light_1_2_RC1.ijm').read_text(encoding='utf-8')
    body = '''
macro "Cavity Light: comprobacion integrada RC1" {
    lightAutoRun();
    report=REPORT;
    launchResult=call("java.lang.System.getProperty","cavity.light.library.result");
    opened=0;if(launchResult=="OK")opened=1;
    if(!opened){File.saveString("status\\tOPEN_FAILED\\n",report);exit("Apertura fallida");}
    openedId=getImageID();
    beforeCount=countTypeFast("cavity");beforeX=nmPerPixelX;beforeY=nmPerPixelY;beforeInclude=lightIncludeUncertain;beforeScaleDefined=scaleDefined;beforeResizeStep=lightInteractiveResizeStepNm;
    text="status\\tOPENED\\ninitial_revision\\t"+lightCurrentRevision+"\\ncavities_before\\t"+beforeCount+"\\nscale_x_before\\t"+d2s(beforeX,12)+"\\nscale_y_before\\t"+d2s(beforeY,12)+"\\ninclude_uncertain_before\\t"+beforeInclude+"\\n";
    File.saveString(text,report);
    File.append("scale_defined_before\\t"+beforeScaleDefined+"\\nresize_step_before\\t"+d2s(beforeResizeStep,12)+"\\n",report);
    saved=lightSaveRevisionCore(0);
    if(saved==""){File.append("status\\tSAVE_FAILED\\n",report);exit("Guardado fallido");}
    File.append("saved_revision\\t"+saved+"\\n",report);
    roiManager("reset");call("cavity.light.IndividualEditor.closeImported",d2s(openedId,0));
    reopened=lightOpenLibrarySelection(PROJECT,IMAGE,saved);
    if(!reopened){File.append("status\\tREOPEN_FAILED\\n",report);exit("Reapertura fallida");}
    afterCount=countTypeFast("cavity");
    pass=0;if(afterCount==beforeCount&&nmPerPixelX==beforeX&&nmPerPixelY==beforeY&&lightIncludeUncertain==beforeInclude&&lightCurrentRevision==saved&&scaleDefined==beforeScaleDefined&&lightInteractiveResizeStepNm==beforeResizeStep)pass=1;
    outcome="FAIL";if(pass)outcome="PASS";
    File.append("reopened_revision\\t"+lightCurrentRevision+"\\ncavities_after\\t"+afterCount+"\\nscale_x_after\\t"+d2s(nmPerPixelX,12)+"\\nscale_y_after\\t"+d2s(nmPerPixelY,12)+"\\ninclude_uncertain_after\\t"+lightIncludeUncertain+"\\nstatus\\t"+outcome+"\\n",report);
    File.append("scale_defined_after\\t"+scaleDefined+"\\nresize_step_after\\t"+d2s(lightInteractiveResizeStepNm,12)+"\\n",report);
    EXPORT_BLOCK
}
'''
    export_block = '''
    if(pass){
        File.append("export_status\\tSTARTED\\n",report);
        lightLastExportDir="";
        lightExportCurrentImage();
        exportOutcome="FAILED";if(lightLastExportDir!="")exportOutcome="FINISHED";
        File.append("export_revision\\t"+lightCurrentRevision+"\\nexport_run\\t"+lightCurrentRunId+"\\nexport_directory\\t"+lightLastExportDir+"\\nexport_area_nm2\\t"+d2s(lastValidAreaNm2,12)+"\\nexport_mean_nm\\t"+d2s(lightStatMean,12)+"\\nexport_status\\t"+exportOutcome+"\\n",report);
    }
''' if args.export else ''
    body = body.replace('EXPORT_BLOCK', export_block)
    for key, value in [('REPORT', args.report), ('PROJECT', args.project), ('IMAGE', args.image_id), ('REVISION', args.revision)]:
        body = body.replace(key, literal(value))
    args.output.write_text(source + '\n' + body, encoding='utf-8')
    request = args.output.with_suffix('.request.tsv')
    request.write_text('project_root\t'+str(args.project).replace('\\','/')+'\nimage_id\t'+args.image_id+'\nrevision_id\t'+args.revision+'\n', encoding='utf-8')
    wrapper = args.output.with_suffix('.start.ijm')
    wrapper.write_text('call("java.lang.System.setProperty","cavity.light.library.request",'+literal(request)+');\ncall("cavity.light.IndividualEditor.install",'+literal(args.output)+');\nrun("Cavity Light: comprobacion integrada RC1");\n', encoding='utf-8')
    print(wrapper)
