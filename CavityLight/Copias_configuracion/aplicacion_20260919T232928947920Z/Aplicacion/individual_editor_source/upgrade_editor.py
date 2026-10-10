"""Reapply the focused, reviewable RC1 changes to the preserved R9 source."""
from pathlib import Path


def replace_function(text, name, replacement):
    start = text.index(f"function {name}(")
    # Functions in this toolset start in column zero; a body may contain embedded JS.
    end = text.find("\nfunction ", start + 1)
    return text[:start] + replacement.rstrip() + "\n\n" + text[end + 1:]


def upgrade(text):
    text = "// 1.2 RC1: individual images, preserved R9 interpretation; see PROVENANCE.json.\n" + text
    text = text.replace('var macroVersion = "Cavity-TEM-Light-v1.1.1-R9-CONSOLIDADA-RC1_derived-from-v5.6.0-R4.1";',
                        'var macroVersion = "Cavity-TEM-Light-v1.2.0-RC1-individual_derived-from-R9-HF4.6";')
    text = text.replace('var lightReleaseVersion = "1.1.1-R9-CONSOLIDADA-RC1";',
                        'var lightReleaseVersion = "1.2.0-RC1-individual";')
    text = text.replace('macro "Cavity Light: analisis combinado" { lightRunCombinedAnalysis(); }\n', '')
    text = text.replace('macro "AutoRun" { lightAutoRun(); }',
                        'macro "AutoRun" { lightAutoRun(); }\nmacro "Cavity Light: iniciar biblioteca" { lightAutoRun(); }')
    text = text.replace("one(p,'Analisis combinado de imagenes','Cavity Light: analisis combinado',true);", '')
    text = text.replace('Cavity TEM Light 1.1.1 R9 - CONSOLIDADA RC1', 'Cavity TEM Light 1.2 RC1 - Imagenes individuales')
    text = text.replace("title.indexOf('Cavity TEM Light 1.1.1 R9')==0", "title.indexOf('Cavity TEM Light 1.2 RC1')==0||title.indexOf('Cavity TEM Light 1.1.1 R9')==0")
    text = text.replace('INTERACCION R9 CONSOLIDADA RC1:', 'IMAGEN INDIVIDUAL 1.2 RC1:')
    # Preserve the HF3 scientific method identifier; label new outputs with their actual application.
    text = text.replace("application_version:'1.1.1-R9-HF4.6'", "application_version:'1.2.0-RC1-individual'")
    text = replace_function(text, 'editSelectedCavityNumerically', '''function editSelectedCavityNumerically() {
    if (!v4PrepareImageForMeasurement(1)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) exit("Selecciona una cavidad.");
    commitOk=commitActiveManagedRoi();if(commitOk<0)return;
    safeRoiSelect(idx);
    if (!currentRoiIsCavity()) exit("La ROI seleccionada no es una cavidad.");
    id = cavityIdCurrent();
    Roi.getFloatBounds(x,y,w,h);
    d=sqrt((w*nmPerPixelX)*(h*nmPerPixelY));
    token=call("cavity.light.IndividualEditor.prepareNumeric","");
    if(startsWith(token,"ERROR|")){showMessage("Edicion no preparada",token);return;}
    Dialog.create("Editar " + id);
    Dialog.addNumber("Centro X (px):",x+w/2,6);
    Dialog.addNumber("Centro Y (px):",y+h/2,6);
    Dialog.addNumber("Diametro equivalente (nm):",d,6);
    Dialog.addMessage("Se conserva la proporcion entre los ejes y las propiedades de la cavidad.");
    Dialog.show();
    newCx=Dialog.getNumber();newCy=Dialog.getNumber();newD=Dialog.getNumber();
    request=token+"|"+d2s(newCx,12)+"|"+d2s(newCy,12)+"|"+d2s(newD,12)+"|"+d2s(nmPerPixelX,12)+"|"+d2s(nmPerPixelY,12);
    applied=call("cavity.light.IndividualEditor.applyNumeric",request);
    if(applied!="OK"){showMessage("Edicion no aplicada",applied);return;}
    activeDiameterNm=newD;
    syncCavityAtIndex(idx);scanAllDuplicates(0);updateSessionMetadataRoi();showAllRois();
    activateMacroToolByPrefix("Cavity select");refreshControlPanelStatus();
    showStatus(id+" actualizada conservando la proporcion de sus ejes.");
}''')
    text = replace_function(text, 'lightPrepareProjectSwitch', '''function lightPrepareProjectSwitch() {
    if(!lightResolvePendingBeforeSwitch())return 0;
    run("ROI Manager...");roiManager("reset");return 1;
}

function lightResolvePendingBeforeSwitch() {
    run("ROI Manager...");if(roiManager("count")==0)return 1;
    canSave=0;if(lightProjectLoaded&&lightImageId!=""&&nImages()>0)canSave=1;
    choice=call("cavity.light.IndividualEditor.switchDecision",d2s(canSave,0));
    if(choice=="cancel")return 0;
    if(choice=="save"){saved=lightSaveRevisionCore(0);if(saved=="")return 0;}
    return 1;
}''')
    text = replace_function(text, 'lightOpenRegisteredImageById', '''function lightOpenRegisteredImageById(id) {
    return lightOpenRegisteredImageCore(id,"__ASK__",1,1);
}

function lightOpenRegisteredImageCore(id,requestedRevision,persistOpening,confirmSwitch) {
    if(call("cavity.light.IndividualEditor.validComponent",id)!="1"){showMessage("Imagen no valida",id);return 0;}
    targetDir=lightNormalizeDir(lightJoin(lightJoin(lightProjectRoot,"images"),id));
    meta=lightJoin(targetDir,lightImageMetadataFileName);
    if(!lightImageMetadataMatches(meta,id,"")){showMessage("Registro no valido",meta);return 0;}
    targetSha=lightKvRead(meta,"source_sha256","");
    sourcePath=normalizeStoredPath(lightKvRead(meta,"source_path",""));
    storedPath=normalizeStoredPath(lightKvRead(meta,"stored_path",""));
    resolvedPath="";
    if(sourcePath!=""&&File.exists(sourcePath))resolvedPath=sourcePath;
    if(storedPath!=""&&File.exists(storedPath))resolvedPath=storedPath;
    sourceName=File.getName(sourcePath);if(sourceName=="")sourceName=File.getName(storedPath);
    candidate=lightJoin(lightJoin(targetDir,"source"),sourceName);
    if(sourceName!=""&&File.exists(candidate)){resolvedPath=candidate;storedPath=candidate;}
    if(resolvedPath==""){
        if(persistOpening==0){showMessage("Fuente no disponible","No se encuentra el DM3/DM4 registrado. Localiza la fuente desde el editor antes de abrirla desde la biblioteca.");return 0;}
        resolvedPath=File.openDialog("Localiza el DM3/DM4 de "+id);if(resolvedPath=="")return 0;sourcePath=resolvedPath;
    }
    actualSha=call("cavity.light.HF46.sourceSha",resolvedPath);
    if(actualSha!=targetSha){showMessage("Fuente incompatible","El archivo no coincide con el SHA-256 de la imagen registrada.");return 0;}
    revisionToLoad=requestedRevision;
    if(revisionToLoad=="__CURRENT__"||revisionToLoad=="__ASK__"){
        revisionToLoad=lightKvRead(meta,"current_revision","");
        if(requestedRevision=="__ASK__"&&revisionToLoad!=""){
            if(!getBoolean("Cargar la revision vigente "+revisionToLoad+"?","Cargar ROIs","Abrir sin ROIs"))revisionToLoad="";
        }
    }
    if(revisionToLoad!=""){
        if(call("cavity.light.IndividualEditor.validComponent",revisionToLoad)!="1")return 0;
        targetRevisionDir=lightNormalizeDir(lightJoin(lightJoin(targetDir,"roi_sessions"),revisionToLoad));
        if(!File.exists(lightJoin(targetRevisionDir,"cavity_rois.zip"))){showMessage("Revision no disponible",revisionToLoad);return 0;}
    }
    if(confirmSwitch&&!lightResolvePendingBeforeSwitch())return 0;
    state=lightHF46CaptureState();switchSnapshotStatus=call("cavity.light.HF46.beginSwitch","");if(switchSnapshotStatus!="OK")return 0;
    imported=call("cavity.light.IndividualEditor.importDm",resolvedPath);
    if(!startsWith(imported,"OK|")){call("cavity.light.HF46.endSwitch","rollback");showMessage("Apertura no realizada",imported);return 0;}
    info=split(imported,"|");importedId=info[1];selectImage(parseFloat(importedId));roiManager("reset");lightHF46ResetImageState();
    lightImageId=id;lightImageDir=targetDir;
    if(!lightReadImageMetadata()){lightRollbackImported(importedId,state);return 0;}
    lightSourcePath=sourcePath;lightSourceStoredPath=storedPath;
    sx=lightKvNumber(meta,"active_scale_x_nm_px",lightOriginalScaleNmX);sy=lightKvNumber(meta,"active_scale_y_nm_px",lightOriginalScaleNmY);
    if(lightHF46Finite(sx)&&lightHF46Finite(sy)&&sx>0&&sy>0){setVoxelSize(sx,sy,1,"nm");updateScaleMaybe();}
    imageFileName=File.getName(resolvedPath);imageDirectory=normalizeStoredPath(File.getDirectory(resolvedPath));imageChecksum=targetSha;montageId=id;
    sourceFirst=imageFileName;sourceLast=imageFileName;sourceImageList=imageFileName;
    projectConfigured=1;lightProjectLoaded=1;v4ProjectLoaded=0;setMetadataImageProperties();
    if(revisionToLoad!=""){
        if(!lightLoadRevisionCore(revisionToLoad,0)){lightRollbackImported(importedId,state);return 0;}
    }else{lightCurrentRevision="";lightCurrentRunId="";updateSessionMetadataRoi();}
    lightSourcePath=sourcePath;lightSourceStoredPath=storedPath;setMetadataImageProperties();
    if(persistOpening&&!lightWriteImageMetadata()){lightRollbackImported(importedId,state);return 0;}
    call("cavity.light.HF46.endSwitch","commit");
    if(persistOpening){lightUpdateRegistry();lightAppendLog("IMAGE_OPENED","revision="+lightCurrentRevision+"; opened_path="+resolvedPath);}
    lightShowPanel();return 1;
}

function lightRollbackImported(importedId,state) {
    call("cavity.light.IndividualEditor.closeImported",importedId);
    call("cavity.light.HF46.endSwitch","rollback");lightHF46RestoreState(state);
}

// Opens existing schema-1 data without changing metadata, pointers, logs or results.
function lightOpenLibrarySelection(projectRoot,imageId,revisionId) {
    descriptor=lightJoin(projectRoot,lightProjectFileName);
    if(lightProjectDescriptorValid(descriptor,"","")==0){showMessage("Proyecto no valido",descriptor);return 0;}
    if(!lightResolvePendingBeforeSwitch())return 0;
    previous=lightHF46CaptureState();snapshot=call("cavity.light.HF46.beginSwitch","");if(snapshot!="OK")return 0;
    loaded=lightLoadProjectFile(descriptor);
    if(loaded&&imageId!="")loaded=lightOpenRegisteredImageCore(imageId,revisionId,0,0);
    if(!loaded){call("cavity.light.HF46.endSwitch","rollback");lightHF46RestoreState(previous);return 0;}
    if(imageId==""){roiManager("reset");lightShowPanel();}
    call("cavity.light.HF46.endSwitch","commit");return 1;
}

function lightOpenLibraryRequest(path) {
    if(!File.exists(path))return 0;
    projectRoot=lightKvRead(path,"project_root","");imageId=lightKvRead(path,"image_id","");revisionId=lightKvRead(path,"revision_id","__CURRENT__");
    if(projectRoot=="")return 0;
    return lightOpenLibrarySelection(projectRoot,imageId,revisionId);
}''')
    text = text.replace('function lightLoadRevisionById(rev) {', 'function lightLoadRevisionById(rev) { return lightLoadRevisionCore(rev,1); }\n\nfunction lightLoadRevisionCore(rev,persistOpening) {')
    # Patch precisely within the core, leaving ordinary explicit load behavior intact.
    start = text.index('function lightLoadRevisionCore(')
    end = text.index('\nfunction ', start + 1)
    core = text[start:end]
    core = core.replace('if(!lightWriteImageMetadata())', 'if(persistOpening&&!lightWriteImageMetadata())')
    core = core.replace('lightUpdateRegistry();lightAppendLog("REVISION_LOADED","revision="+rev);',
                        'if(persistOpening){lightUpdateRegistry();lightAppendLog("REVISION_LOADED","revision="+rev);}')
    text = text[:start] + core + text[end:]
    # Prevent a previous RUN from appearing to belong to an explicitly selected older revision.
    text = text.replace('applied=call("cavity.light.HF46.applyRevision","");loaded=0;',
                        'loadedRun=lightCurrentRunId;if(rev!=lightCurrentRevision)loadedRun="";applied=call("cavity.light.HF46.applyRevision","");loaded=0;')
    text = text.replace('lightSourcePath=expectedSource;lightSourceStoredPath=expectedStored;lightCurrentRevision=rev;',
                        'lightSourcePath=expectedSource;lightSourceStoredPath=expectedStored;lightCurrentRevision=rev;lightCurrentRunId=loadedRun;')
    # Prefer current validated descriptor for relocated copies over old paths embedded in ROI metadata.
    old = 'descriptor=lightFindCanonicalProjectFile(candidateProjectRoot);if(descriptor=="")descriptor=lightFindCanonicalProjectFile(candidateImageDir);if(descriptor==""&&lightProjectFile!=""&&lightProjectDescriptorValid(lightProjectFile,candidateProjectId,candidateProjectUid)==1)descriptor=lightProjectFile;'
    new = 'descriptor="";if(lightProjectFile!=""&&lightProjectDescriptorValid(lightProjectFile,candidateProjectId,candidateProjectUid)==1)descriptor=lightProjectFile;if(descriptor=="")descriptor=lightFindCanonicalProjectFile(candidateProjectRoot);if(descriptor=="")descriptor=lightFindCanonicalProjectFile(candidateImageDir);'
    assert old in text
    text = text.replace(old, new)
    # Library launch is a read-only open. Explicit saves/exports are normal R9 operations.
    start = text.index('function lightAutoRun() {')
    point = text.index('    lightShowPanel();', start)
    text = text[:point] + '''    launchRequest=call("cavity.light.IndividualEditor.takeLaunchRequest","");
    if(launchRequest!=""){
        launchOk=lightOpenLibraryRequest(launchRequest);launchStatus="ERROR";if(launchOk)launchStatus="OK";
        call("cavity.light.IndividualEditor.launchResult",launchStatus);
    }
''' + text[point:]
    # Defer image configuration until import is fully committed: its Dialog Cancel must not strand a snapshot.
    text = text.replace('    lightConfigureCurrentImage();\n    showMessage("Imagen registrada"',
                        '    showMessage("Imagen registrada"')
    text = text.replace('call("cavity.light.HF46.importDm",path)', 'call("cavity.light.IndividualEditor.importDm",path)')
    text = text.replace('if(!lightRegisterActiveImageWithPath(path)){call("cavity.light.HF46.endSwitch","rollback");lightHF46RestoreState(state);return;}\n    call("cavity.light.HF46.endSwitch","commit");\n}\n\nfunction lightRegisterActiveImage()',
                        'if(!lightRegisterActiveImageWithPath(path)){lightRollbackImported(info[1],state);return;}\n    call("cavity.light.HF46.endSwitch","commit");\n    lightConfigureCurrentImage();\n}\n\nfunction lightRegisterActiveImage()')
    # The register-active command has no imported window to close.
    start = text.index('function lightRegisterActiveImage()')
    end = text.index('\nfunction ', start + 1)
    segment = text[start:end].replace('call("cavity.light.HF46.endSwitch","commit");',
                                       'call("cavity.light.HF46.endSwitch","commit");lightConfigureCurrentImage();')
    text = text[:start] + segment + text[end:]
    return text


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('r9_source', type=Path)
    args = parser.parse_args()
    target = Path(__file__).with_name('Cavity_TEM_Light_1_2_RC1.ijm')
    target.write_text(upgrade(args.r9_source.read_text(encoding='utf-8-sig')), encoding='utf-8', newline='\n')
