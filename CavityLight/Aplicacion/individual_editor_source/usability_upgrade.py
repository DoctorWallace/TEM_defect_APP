"""US1: reproducible UI, preparation and revision transaction hooks, preserving R9 science."""

def replace_function(text, name, replacement):
    start = text.index('function ' + name + '(')
    end = text.find('\nfunction ', start + 1)
    assert end >= 0, name
    return text[:start] + replacement.rstrip() + '\n\n' + text[end + 1:]

SAVE = r'''function lightSaveRevisionCore(verbose) {
    lightHF4Pull();
    labelsJson="{}";
    if(verbose){
        labelsJson=call("cavity.light.RevisionWorkspace.askSave","");
        if(labelsJson=="CANCEL")return "";
        if(startsWith(labelsJson,"ERROR|")){showMessage("Revision no preparada",labelsJson);return "";}
    }
    lightHF4Pause();commitOk=commitActiveManagedRoi();if(commitOk<0)return "";
    preflightOk=quantitativeRevisionPreflight();if(preflightOk==0)return "";
    workspaceInit=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());
    if(workspaceInit!="OK"){showMessage("Revision no preparada",workspaceInit);return "";}
    projectLogsDir=lightJoin(lightProjectRoot,"logs");imageLogsDir=lightJoin(lightImageDir,"logs");
    if(!lightMakeDir(projectLogsDir))return "";
    if(!lightMakeDir(imageLogsDir))return "";
    currentFingerprint=lightAnalysisInputFingerprint();
    lightHF46AnalysisState="pending";
    if(lightPreparedFingerprint!=""&&currentFingerprint==lightPreparedFingerprint)lightHF46AnalysisState="prepared";
    if(lightHF46AnalysisState=="pending")call("cavity.light.HF46.markPending","");
    oldRev=lightCurrentRevision;oldRun=lightCurrentRunId;rev="REV_"+lightTimestamp();
    revisionsDir=lightNormalizeDir(lightJoin(lightImageDir,"roi_sessions"));
    if(!lightMakeDir(revisionsDir))return "";
    finalDir=lightNormalizeDir(lightJoin(revisionsDir,rev));
    if(File.exists(finalDir)){revisionUuid=lightUuid();rev=rev+"_"+substring(revisionUuid,0,8);finalDir=lightNormalizeDir(lightJoin(revisionsDir,rev));}
    stageResult=call("cavity.light.RevisionWorkspace.beginRevision",finalDir);
    if(!startsWith(stageResult,"OK|")){showMessage("Revision no preparada",stageResult);return "";}
    revDir=lightNormalizeDir(substring(stageResult,3));
    lightCurrentRevision=rev;lightCurrentRunId="";
    lightStampRevisionOnAllObjects(rev);updateSessionMetadataRoi();
    pointRoiSaveOk=lightPreparePointRoisForRevisionSave();
    if(pointRoiSaveOk==0)return lightWorkspaceAbortSave(revDir,oldRev,oldRun,"No se pudieron preparar las ROIs de puntos.");
    zip=lightJoin(revDir,"cavity_rois.zip");zipResult=call("cavity.light.HF46.saveZip",zip);
    if(zipResult!="OK")return lightWorkspaceAbortSave(revDir,oldRev,oldRun,"El ZIP de ROIs no supero la verificacion.");
    sha=IJ.checksum("SHA-256 file",zip);
    settingsJson=lightWorkspaceSettings();
    sessionPath=lightJoin(revDir,"session_metadata.json");
    if(!lightHF46WriteText(sessionPath,settingsJson))return lightWorkspaceAbortSave(revDir,oldRev,oldRun,"No se guardaron los parametros de la sesion.");
    workspaceRequest="{\"revision_directory\":\""+jsonEscape(revDir)+"\",\"revision_id\":\""+jsonEscape(rev)+"\",\"settings\":"+settingsJson+"}";
    workspaceRequest=eval("js","(function(){var r=JSON.parse('"+jsEscape(workspaceRequest)+"'),labels=JSON.parse('"+jsEscape(labelsJson)+"');if(labels.name!==undefined){r.name=labels.name;r.comment=labels.comment;}return JSON.stringify(r);})();");
    workspaceSaved=call("cavity.light.RevisionWorkspace.saveWorkspace",workspaceRequest);
    if(!startsWith(workspaceSaved,"OK|"))return lightWorkspaceAbortSave(revDir,oldRev,oldRun,workspaceSaved);
    workspaceSha=substring(workspaceSaved,3);
    manifest="revision_id\t"+rev+"\nimage_id\t"+lightImageId+"\nproject_id\t"+lightProjectId+"\nproject_uid\t"+lightProjectUid+"\nsource_sha256\t"+lightSourceSha256+"\nroi_zip_sha256\t"+sha+"\nroi_count\t"+roiManager("count")+"\ncreated_ms\t"+d2s(getTime(),0)+"\ntool_version\t"+lightReleaseVersion+"\nvalidation_state\t"+lightValidationState+"\nparent_revision\t"+oldRev+"\nprepared_state_reused\t"+lightLastPreparationReused+"\nprepared_state_duration_ms\t"+d2s(lightLastPreparationDurationMs,0)+"\nanalysis_state\t"+lightHF46AnalysisState+"\nworkspace_sha256\t"+workspaceSha+"\n";
    manifestPath=lightJoin(revDir,"revision_manifest.tsv");
    if(!lightHF46WriteText(manifestPath,manifest))return lightWorkspaceAbortSave(revDir,oldRev,oldRun,"No se guardo el manifiesto de revision.");
    published=call("cavity.light.RevisionWorkspace.publishRevision",revDir+"|"+finalDir);
    if(published!="OK")return lightWorkspaceAbortSave(revDir,oldRev,oldRun,published);
    currentRevisionPath=lightJoin(lightImageDir,lightCurrentRevisionFileName);
    if(!lightHF46WriteText(currentRevisionPath,rev+"\n")){
        lightCurrentRevision=oldRev;lightCurrentRunId=oldRun;lightStampRevisionOnAllObjects(oldRev);updateSessionMetadataRoi();
        showMessage("Revision conservada",rev+" se guardo completa, pero no pudo activarse. Puede abrirla desde el historial.");return "";
    }
    if(!lightWriteImageMetadata()){
        lightCurrentRevision=oldRev;lightCurrentRunId=oldRun;lightStampRevisionOnAllObjects(oldRev);updateSessionMetadataRoi();
        lightHF46WriteText(currentRevisionPath,oldRev+"\n");
        showMessage("Revision conservada",rev+" se guardo completa, pero no pudo actualizarse el registro de la imagen.");return "";
    }
    lightUpdateRegistry();lightAppendLog("REVISION_SAVED","revision="+rev+"; parent="+oldRev+"; roi_zip_sha256="+sha+"; workspace_sha256="+workspaceSha);
    if(verbose)showMessage("Revision guardada",rev+"\nImagen preparada, vista anotada, ROIs, receta vigente y parametros conservados.\nEstado del calculo: "+lightHF46AnalysisState+".\n\nPuede guardar avances sin exportar resultados.");
    lightRefreshPanel();return rev;
}'''

LOAD = r'''function lightLoadRevisionCore(rev,persistOpening) {
    lightHF4Pause();lightHF4Pull();
    revDir=lightNormalizeDir(lightJoin(lightJoin(lightImageDir,"roi_sessions"),rev));zip=lightJoin(revDir,"cavity_rois.zip");
    if(!File.exists(zip)){showMessage("Revision invalida","No existe el ZIP de la revision:\n"+revDir);return 0;}
    if(!lightVerifyRevisionManifest(revDir,zip)){showMessage("Revision invalida","No se pudo verificar la revision:\n"+revDir);return 0;}
    init=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());
    if(init!="OK"){showMessage("Revision no cargada",init);return 0;}
    restoreRequest="{\"revision_directory\":\""+jsonEscape(revDir)+"\",\"revision_id\":\""+jsonEscape(rev)+"\",\"settings\":"+lightWorkspaceSettings()+"}";
    workspaceStage=call("cavity.light.RevisionWorkspace.stageRestore",restoreRequest);
    if(!startsWith(workspaceStage,"OK|")){showMessage("Revision no cargada",workspaceStage);return 0;}
    workspaceToken=substring(workspaceStage,3);
    args=zip+"|"+lightProjectId+"|"+lightProjectUid+"|"+lightImageId+"|"+lightSourceSha256+"|"+getWidth()+"|"+getHeight();
    staged=call("cavity.light.HF46.stageRevision",args);
    if(!startsWith(staged,"OK|")){call("cavity.light.RevisionWorkspace.discardRestore",workspaceToken);showMessage("Revision no cargada",staged);return 0;}
    state=lightHF46CaptureState();
    workspaceSwitch=call("cavity.light.RevisionWorkspace.beginSwitch","");
    if(workspaceSwitch!="OK"){call("cavity.light.RevisionWorkspace.discardRestore",workspaceToken);showMessage("Revision no cargada",workspaceSwitch);return 0;}
    switchSnapshotStatus=call("cavity.light.HF46.beginSwitch","");
    if(switchSnapshotStatus!="OK"){call("cavity.light.RevisionWorkspace.endSwitch","rollback");call("cavity.light.RevisionWorkspace.discardRestore",workspaceToken);showMessage("Revision no cargada",switchSnapshotStatus);return 0;}
    expectedRoot=lightProjectRoot;expectedFile=lightProjectFile;expectedImageDir=lightImageDir;
    expectedSource=lightSourcePath;expectedStored=lightSourceStoredPath;
    loadedRun=lightCurrentRunId;if(rev!=lightCurrentRevision)loadedRun="";applied=call("cavity.light.HF46.applyRevision","");loaded=0;
    if(applied=="OK"){sessionRoiPath=zip;lightCurrentRevision=rev;loaded=loadSessionFromRois(0);}
    if(loaded){workspaceApplied=call("cavity.light.RevisionWorkspace.applyRestore",workspaceToken);if(workspaceApplied!="OK")loaded=0;}
    if(!loaded){
        call("cavity.light.RevisionWorkspace.discardRestore",workspaceToken);call("cavity.light.HF46.endSwitch","rollback");call("cavity.light.RevisionWorkspace.endSwitch","rollback");lightHF46RestoreState(state);
        showMessage("Revision no cargada","Se conserva la sesion anterior; no se aplico la imagen o sus anotaciones.");return 0;
    }
    lightProjectRoot=expectedRoot;lightProjectFile=expectedFile;lightImageDir=expectedImageDir;
    lightSourcePath=expectedSource;lightSourceStoredPath=expectedStored;lightCurrentRevision=rev;lightCurrentRunId=loadedRun;
    lightInvalidateAnalysisCache();updateSessionMetadataRoi();
    if(persistOpening){if(!lightWriteImageMetadata()){
        call("cavity.light.HF46.endSwitch","rollback");call("cavity.light.RevisionWorkspace.endSwitch","rollback");lightHF46RestoreState(state);return 0;
    }}
    call("cavity.light.HF46.endSwitch","commit");call("cavity.light.RevisionWorkspace.endSwitch","commit");
    if(persistOpening){lightUpdateRegistry();lightAppendLog("REVISION_LOADED","revision="+rev);}
    showStatus("Revision cargada: "+rev+"; ROIs: "+roiManager("count"));lightShowPanel();return 1;
}'''

HELPERS = r'''// US1 preparation and workspace entrypoints.
macro "Cavity Light: contraste por zona" { lightWorkspacePreparation("brightness_contrast"); }
macro "Cavity Light: contraste local" { lightWorkspacePreparation("local_contrast"); }
macro "Cavity Light: correccion de fondo" { lightWorkspacePreparation("background_correction"); }
macro "Cavity Light: deshacer tratamiento" { lightWorkspacePreparation("undo"); }
macro "Cavity Light: rehacer tratamiento" { lightWorkspacePreparation("redo"); }
macro "Cavity Light: restaurar imagen original" { lightWorkspacePreparation("reset"); }
macro "Cavity Light: ver receta vigente" { lightWorkspacePreparation("recipe"); }
macro "Cavity Light: conservar cambios externos" { lightWorkspacePreparation("adopt_external"); }
macro "Cavity Light: recuperar panel [F2]" { lightWorkspaceShowPanel(); }
macro "Cavity Light: ajustar detector con cavidades" { lightWorkspaceDetectorDefaults(); }

function lightWorkspaceSettings() {
    saved=projectJson();
    js="(function(){var v=JSON.parse('"+jsEscape(saved)+"');v.bands.mode='"+jsEscape(lightBandMode)+"';v.settings.size_breaks_nm='"+jsEscape(lightSizeBreaks)+"';v.settings.result_contrast='"+jsEscape(lightResultContrast)+"';v.application_version='"+jsEscape(lightReleaseVersion)+"';v.area.computation_state='"+jsEscape(lightHF46AnalysisState)+"';if(v.area.computation_state!='prepared')v.area.valid_area_nm2=null;return JSON.stringify(v);})();";
    return ""+eval("js",js);
}

function lightWorkspaceAbortSave(stageDir,oldRev,oldRun,reason) {
    aborted=call("cavity.light.RevisionWorkspace.abortRevision",stageDir);
    lightCurrentRevision=oldRev;lightCurrentRunId=oldRun;lightStampRevisionOnAllObjects(oldRev);updateSessionMetadataRoi();
    if(aborted!="OK")reason=reason+"\n"+aborted;
    showMessage("Revision no guardada",reason+"\nLa revision anterior sigue activa.");return "";
}

function lightWorkspacePreparation(action) {
    imageOk=lightEnsureCurrentImage();if(imageOk==0)return;
    lightHF4Pause();commitOk=commitActiveManagedRoi();if(commitOk<0)return;
    init=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());
    if(init!="OK"){showMessage("Preparacion no disponible",init);return;}
    if(action=="brightness_contrast"||action=="local_contrast"||action=="background_correction")
        result=call("cavity.light.RevisionWorkspace.treatment",action);
    else result=call("cavity.light.RevisionWorkspace.preparationAction",action);
    if(startsWith(result,"ERROR|"))showMessage("Preparacion de imagen",result);
    else if(action=="recipe")showText("Receta vigente",lightWorkspaceRecipeText(result));
    else if(result!="CANCEL")showStatus(result);
}

function lightWorkspaceRecipeText(saved) {
    js="(function(){var s=JSON.parse('"+jsEscape(saved)+"'),a=s.operations||[],lines=['Tratamientos vigentes de la copia de trabajo',''];if(s.recipe_complete===false)lines.push('Receta parcial: hay cambios externos descritos, cuyos filtros y parametros no se conocen.','');if(a.length===0)lines.push('Sin tratamientos registrados.');var kinds={brightness_contrast:'Brillo y contraste',local_contrast:'Contraste local',background_correction:'Correccion de fondo',external_pixel_changes:'Cambios hechos con Fiji'};var labels={brightness:'Brillo',contrast:'Contraste (factor)',center:'Centro de intensidades',radius:'Radio (px)',radius_px:'Radio (px)',amount:'Intensidad',max_gain:'Ganancia maxima',noise_floor:'Umbral de ruido',target_stddev:'Variacion objetivo',strength:'Intensidad',mode:'Correccion',reference:'Referencia',epsilon:'Minimo de division',description:'Descripcion'};for(var i=0;i<a.length;i++){var o=a[i],r=o.region,p=o.params||{};lines.push((i+1)+'. '+(kinds[o.kind]||o.kind));lines.push(r&&r.scope!='whole_image'?'Zona: ROI conservada':'Zona: imagen completa');for(var k in p){if(k=='algorithm'||k=='before_pixel_sha256'||k=='after_pixel_sha256')continue;lines.push('  '+(labels[k]||k)+': '+p[k]);}lines.push('');}lines.push('Solo se guardan los pasos vigentes. Las ROIs de tratamiento se conservan separadas de las cavidades.');return lines.join('\\n');})();";
    return ""+eval("js",js);
}

function lightWorkspaceShowPanel() {
    result=call("cavity.light.Workspace.action","show");
    if(startsWith(result,"MISSING|"))lightShowPanel();
}

function lightWorkspaceDetectorDefaults() {
    if(!lightHF4Arm("select"))return;
    suggestion=call("cavity.light.DetectorAssistant.suggestions","");
    if(!startsWith(suggestion,"OK|")){showMessage("Detector sin ajustes",suggestion);return;}
    p=split(suggestion,"|");if(p.length!=6)return;
    Dialog.create("Ajustar detector con cavidades confirmadas");
    Dialog.addMessage("Referencia: "+p[1]+" cavidades; diametro mediano "+d2s(parseFloat(p[2]),3)+" nm.\nSon valores iniciales editables, no un modelo entrenado. Cada propuesta sigue requiriendo revision.");
    Dialog.addNumber("Diametro minimo para estimar (nm):",parseFloat(p[3]),3);
    Dialog.addNumber("Diametro maximo para estimar (nm):",parseFloat(p[4]),3);
    Dialog.addNumber("Separacion minima entre puntos (nm):",parseFloat(p[5]),3);
    Dialog.show();lo=Dialog.getNumber();hi=Dialog.getNumber();gap=Dialog.getNumber();
    if(!lightHF46Finite(lo)||!lightHF46Finite(hi)||!lightHF46Finite(gap)||lo<=0||hi<=lo||gap<=0){showMessage("Ajustes no validos","Use valores positivos y un maximo mayor que el minimo.");return;}
    eval("js","Packages.ij.Prefs.set('cavity.tem.light.hf4.minD',"+d2s(lo,12)+");Packages.ij.Prefs.set('cavity.tem.light.hf4.maxD',"+d2s(hi,12)+");Packages.ij.Prefs.set('cavity.tem.light.hf4.separation',"+d2s(gap,12)+");Packages.ij.Prefs.savePreferences();");
    showStatus("Valores iniciales ajustados. Dibuje una zona nueva y use Detectar puntos / Estimar diametros.");
}
'''


def apply_usability_upgrade(text):
    if '// US1 preparation and workspace entrypoints.' in text:
        return text
    text=text.replace('individual-ID1_derived-from-R9-HF4.6','individual-US1_derived-from-R9-HF4.6')
    text=text.replace('"1.2.0-RC1-individual-ID1"','"1.2.0-RC1-individual-US1"')
    text=text.replace("application_version:'1.2.0-RC1-individual-ID1'","application_version:'1.2.0-RC1-individual-US1'")
    text=replace_function(text,'lightSaveRevisionCore',SAVE)
    text=replace_function(text,'lightLoadRevisionCore',LOAD)
    # A registered source can be saved before marking cavities; the metadata ROI is not a result.
    start=text.index('function quantitativeRevisionPreflight(');end=text.index('\nfunction ',start+1)
    segment=text[start:end]
    segment=segment.replace('run("ROI Manager...");if(roiManager("count")==0)', 'run("ROI Manager...");updateSessionMetadataRoi();if(roiManager("count")==0)')
    text=text[:start]+segment+text[end:]
    # Preserve position, pin and selected tab when project/image switches rebuild the panel.
    text=text.replace('var fs=Frame.getFrames();', 'var previousBounds=null,previousTab=0;var fs=Frame.getFrames();',1)
    text=text.replace("fs[i].dispose();}catch(e){}}", "{previousBounds=fs[i].getBounds();try{var oldTabs=fs[i].getRootPane().getClientProperty('tabs');if(oldTabs!=null)previousTab=oldTabs.getSelectedIndex();}catch(ignoreTabs){}fs[i].dispose();}}catch(e){}}",1)
    text=text.replace('var tabs=new JTabbedPane();', "f.getRootPane().putClientProperty('CavityLight.Panel','true');var tabs=new JTabbedPane();f.getRootPane().putClientProperty('tabs',tabs);",1)
    text=text.replace('f.pack();f.setLocationByPlatform(true);f.setVisible(true);f.toFront();', 'f.pack();if(previousBounds!=null)f.setBounds(previousBounds);else f.setLocationByPlatform(true);tabs.setSelectedIndex(Math.min(previousTab,tabs.getTabCount()-1));f.setVisible(true);f.toFront();',1)
    panel_start=text.index('function lightShowPanel(');panel_end=text.index('\nfunction ',panel_start+1)
    panel=text[panel_start:panel_end].replace('    eval("js", js);','    eval("js", js);\n    call("cavity.light.Workspace.install","");')
    prep="two(p,'Brillo/contraste por zona','Cavity Light: contraste por zona','Contraste local','Cavity Light: contraste local');one(p,'Correccion de fondo','Cavity Light: correccion de fondo',false);two(p,'Deshacer tratamiento','Cavity Light: deshacer tratamiento','Rehacer tratamiento','Cavity Light: rehacer tratamiento');two(p,'Ver receta vigente','Cavity Light: ver receta vigente','Restaurar imagen original','Cavity Light: restaurar imagen original');one(p,'Conservar cambios hechos con Fiji','Cavity Light: conservar cambios externos',false);"
    panel=panel.replace("two(p,'Definir superficie','Cavity Light: definir superficie','Configurar bandas','Cavity Light: configurar bandas');", "two(p,'Definir superficie','Cavity Light: definir superficie','Configurar bandas','Cavity Light: configurar bandas');"+prep)
    panel=panel.replace("two(p,'Revisar propuestas','Cavity Light: revisar propuestas'", "one(p,'Ajustar detector con cavidades confirmadas','Cavity Light: ajustar detector con cavidades',false);two(p,'Revisar propuestas','Cavity Light: revisar propuestas'")
    panel=panel.replace("'Guardar nueva revision'", "'Guardar avance con nombre'")
    text=text[:panel_start]+panel+text[panel_end:]
    # Revisions and full-image switches also restore preparation pixels on rollback.
    start=text.index('function lightOpenRegisteredImageCore(');end=text.index('\nfunction ',start+1)
    segment=text[start:end]
    old='state=lightHF46CaptureState();switchSnapshotStatus=call("cavity.light.HF46.beginSwitch","");if(switchSnapshotStatus!="OK")return 0;'
    new='state=lightHF46CaptureState();workspaceSwitch=call("cavity.light.RevisionWorkspace.beginSwitch","");if(workspaceSwitch!="OK")return 0;switchSnapshotStatus=call("cavity.light.HF46.beginSwitch","");if(switchSnapshotStatus!="OK"){call("cavity.light.RevisionWorkspace.endSwitch","rollback");return 0;}'
    assert old in segment
    segment=segment.replace(old,new)
    segment=segment.replace('call("cavity.light.HF46.endSwitch","rollback");showMessage("Apertura no realizada"', 'call("cavity.light.HF46.endSwitch","rollback");call("cavity.light.RevisionWorkspace.endSwitch","rollback");showMessage("Apertura no realizada"')
    segment=segment.replace('call("cavity.light.HF46.endSwitch","commit");', 'call("cavity.light.HF46.endSwitch","commit");call("cavity.light.RevisionWorkspace.endSwitch","commit");')
    # Capture the imported source before any ordinary Fiji pixel edits can occur.
    needle='projectConfigured=1;lightProjectLoaded=1;v4ProjectLoaded=0;setMetadataImageProperties();'
    assert needle in segment
    segment=segment.replace(needle,needle+'\n    workspaceInit=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());if(workspaceInit!="OK"){lightRollbackImported(importedId,state);showMessage("Apertura no realizada",workspaceInit);return 0;}')
    text=text[:start]+segment+text[end:]
    start=text.index('function lightRegisterActiveImageWithPath(');end=text.index('\nfunction ',start+1)
    segment=text[start:end]
    needle='        setMetadataImageProperties();'
    assert needle in segment
    segment=segment.replace(needle,needle+'\n        workspaceInit=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());if(workspaceInit!="OK"){showMessage("Preparacion no disponible",workspaceInit);return 0;}',1)
    needle='    setMetadataImageProperties();updateSessionMetadataRoi();'
    assert needle in segment
    segment=segment.replace(needle,'    setMetadataImageProperties();\n    workspaceInit=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());if(workspaceInit!="OK"){showMessage("Preparacion no disponible",workspaceInit);return 0;}\n    updateSessionMetadataRoi();',1)
    text=text[:start]+segment+text[end:]
    start=text.index('function lightRollbackImported(');end=text.index('\nfunction ',start+1)
    segment=text[start:end].replace('call("cavity.light.HF46.endSwitch","rollback");', 'call("cavity.light.HF46.endSwitch","rollback");call("cavity.light.RevisionWorkspace.endSwitch","rollback");')
    text=text[:start]+segment+text[end:]
    help_line='    showMessage("Ayuda R9 CONSOLIDADA RC1", msg);'
    text=text.replace(help_line,'    msg=msg+"\\n\\nPreparacion US1: tratamientos sobre copias, previsualizacion antes de aplicar y Deshacer/Rehacer tratamiento independientes de las anotaciones. Guardar avance conserva solo la receta vigente. F2 recupera el panel oculto. Los controles inferiores permiten organizar pantallas, ocultar ventanas y guardar su disposicion.";\n'+help_line)
    return text.rstrip()+'\n\n'+HELPERS
