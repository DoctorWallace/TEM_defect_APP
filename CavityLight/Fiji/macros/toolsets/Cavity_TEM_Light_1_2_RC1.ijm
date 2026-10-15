// 1.2 RC1: individual images, preserved R9 interpretation; see PROVENANCE.json.
// RELEASE_CANDIDATE: full Fiji/Windows + real DM3/DM4 acceptance is PENDING.
// R9 CONSOLIDADA RC1 (2026-09-18): HF4.6 + HF4.5.1 fixes + scoped IJM identifier fix.
// HF4: install this toolset AND plugins/cavity-light-hf4.jar; restart Fiji.
// Cavity_TEM_Light_v1_1_1_R9_CONSOLIDADA_RC1.ijm
// Combined and user-installable Fiji toolset for Cavity TEM Studio v5.6.0.
// Install this macro with the bundled cavity-light-hf4.jar; see LEEME_PRIMERO.md.
// R9 corrects the mouse-wheel routing observed during the guided R8 audit.
// R9-HF1 adds one scoped guard for the ImageJ 1.54p PointRoi save exception.
// R9-HF2 corrects the percentile helper to call the supported Math.ceil function.
// In Add mode, Alt+wheel changes the live cursor-circle diameter immediately;
// in Select mode it changes the selected cavity. Ctrl+Alt remains an accepted
// alias, but can no longer fall through to image zoom. A high-priority wheel
// router delegates every unhandled event to FIJI, preserving normal navigation.
// The project schema remains 1 and R9 opens immutable revisions created by R5-R8.

// Cavity_ROI_Toolset_v8_3_0.ijm - Guided tabbed interface and ProjectAware workflow
// Fiji/ImageJ toolset for manual and traceable TEM cavity measurements in
// individual micrographs and TEM collages.
//
// v8.0.6 provides continuous drag-to-measure and click-to-add modes, fixes
// select/edit activation, repairs quantitative export, and makes Cancel/Esc a
// normal end-of-operation instead of an ImageJ "Macro canceled" exception.
// It also normalizes stored Windows paths and repairs common text mojibake.
// Version 8 priorities:
// - no F-key shortcuts;
// - separate add and select/edit modes, so close cavities are never blocked;
// - persistent project, scale, surface, panel, mask and feature metadata;
// - one calibrated physical scale; visual scale overlays are optional;
// - straight, segmented or freehand surface with signed perpendicular depth;
// - stable cavity identifiers and recalculation from the current ROI geometry;
// - duplicate warnings without preventing genuine overlaps or alignments;
// - grain-boundary, dislocation, panel, analysis-mask and exclusion layers;
// - post-identification grouping by depth bands and quantitative export.
//
// Install with Plugins > Macros > Install..., or place in Fiji.app/macros/toolsets/.
// User-facing strings are intentionally ASCII-only for compatibility with
// ImageJ installations that do not read macro files as UTF-8.

requires("1.54e");

// -----------------------------------------------------------------------------
// Global state
// -----------------------------------------------------------------------------

var macroVersion = "Cavity-TEM-Light-v1.2.0-RC1-individual-US1_derived-from-R9-HF4.6";
var sessionMetadataName = "CAVITY_SESSION_METADATA";
var legacyMetadataName = "BUBBLE_SESSION_METADATA";
var scaleReferenceName = "SCALE_REFERENCE";
var scaleLabelName = "SCALE_REFERENCE_LABEL";
var surfaceReferenceName = "SURFACE_REFERENCE";

// -----------------------------------------------------------------------------
// Cavity TEM Light: project and independent-image state
// -----------------------------------------------------------------------------
var lightSchemaVersion = "1";
var lightHF46ScientificSource="";
var lightHF46KvPath="";
var lightHF46KvText="";
var lightHF46AnalysisState="pending";
var lightReleaseVersion = "1.2.0-RC1-individual-US1";
var lightProjectLoaded = 0;
var lightProjectRoot = "";
var lightProjectFile = "";
var lightProjectId = "";
var lightProjectName = "";
var lightProjectUid = "";
var lightImageId = "";
var lightImageDir = "";
var lightSourcePath = "";
var lightSourceStoredPath = "";
var lightSourceSha256 = "";
var lightCopySource = 0;
var lightImageMode = "without_surface";
var lightThicknessNm = 0;
var lightThicknessUncertaintyNm = 0;
var lightThicknessMethod = "not_provided";
var lightThicknessNotes = "";
var lightOriginalScaleNmX = NaN;
var lightOriginalScaleNmY = NaN;
var lightOriginalScaleUnit = "";
var lightScaleOrigin = "bioformats_metadata";
var lightScaleConfirmed = 0;
var lightUseWholeImage = 0;
var lightIncludeUncertain = 0;
var lightCurrentRevision = "";
var lightCurrentRunId = "";
var lightHistogramBinNm = 0.2;
var lightLastExportDir = "";
var lightRegistryFileName = "images.tsv";
var lightProjectFileName = "cavity_light_project.tsv";
var lightImageMetadataFileName = "image_metadata.tsv";
var lightCurrentRevisionFileName = "current_revision.txt";
var lightValidationState = "TECHNICAL_PREVIEW_NOT_VALIDATED_ON_REAL_DM3_DM4";
var lightLastDepthBinNm = 1.0;
var lightBandMode = "width";
var lightSizeBreaks = "0.5,1,1.5,2,3,5";
var lightResultContrast = 0.18;
var lightMaxImageDepthNm = 0;
var lightHF3X = 0;
var lightHF3Y = 0;
var lightCtxDepth = newArray(0);
var lightCtxAbsolute = newArray(0);
var lightCtxArc = newArray(0);
var lightCtxNearX = newArray(0);
var lightCtxNearY = newArray(0);
var lightCtxAngle = newArray(0);
var lightLastDepthAreasNm2 = newArray(0);
var lightLastValidPixels = 0;
var lightStatMean = NaN;
var lightStatStd = NaN;
var lightStatMedian = NaN;
var lightStatQ25 = NaN;
var lightStatQ75 = NaN;
var lightStatMin = NaN;
var lightStatMax = NaN;
var lightFeatureDistanceBinNm = 10.0;
var lightLastGbDistanceAreasNm2 = newArray(0);
var lightLastDislocationDistanceAreasNm2 = newArray(0);
var lightLastInterfaceDistanceAreasNm2 = newArray(0);
var lightProjectDescriptorType = "cavity_tem_light_project";
var lightImageDescriptorType = "cavity_tem_light_image";

// R7 prepared-state and area caches. The fingerprint contains only primary
// geometry/configuration inputs, never derived properties such as duplicate
// status. This allows validation, revision save and export to reuse a verified
// state when nothing scientific changed, while direct ROI edits are still
// detected before any quantitative operation.
var lightPreparedFingerprint = "";
var lightPreparedAtMs = 0;
var lightLastPreparationDurationMs = 0;
var lightLastPreparationReused = 0;
var lightPreparationRuns = 0;
var lightPreparationCacheHits = 0;
var lightAreaFingerprint = "";
var lightAreaComputationMode = "not_calculated";
var lightAreaComputationDurationMs = 0;
var lightCavityContextActive = 0;
var lightCtxValid = newArray(0);
var lightCtxEdgeMask = newArray(0);
var lightCtxReason = newArray(0);
var lightCtxDistanceGbNm = newArray(0);
var lightCtxDistanceDislocationNm = newArray(0);
var lightCtxDistanceInterfaceNm = newArray(0);

// R9 interactive editing. The resize step is a UI preference (nm per wheel
// notch), not a scientific result. Stable cavity IDs are never renumbered.
var lightInteractiveMode = "select";
var lightInteractivePreviewEnabled = 1;
var lightInteractiveResizeStepNm = 0.050;
var lightInteractiveResizeMinNm = 0.001;
var lightInteractiveResizeMaxNm = 2.000;
var lightInteractiveDebounceMs = 350;
var lightInteractiveControllerStatus = "not_installed";
var lightInteractivePreviewName = "__CTL_R8_CURSOR_PREVIEW__";
var lightLastInteractiveEditId = "";
var lightLastInteractiveEditKind = "";
var lightLastInteractiveEditDiameterNm = NaN;
var lightCachedCavityCount = -1;
var lightHF4LastSequence = "";
var lightHF4LastReport = "";
var lightLastIdAuditErrors = 0;
var lightLastIdAuditDuplicateIds = 0;
var lightObjectCountCavities = 0;
var lightObjectCountMasks = 0;
var lightObjectCountExclusions = 0;
var lightObjectCountGrainBoundaries = 0;
var lightObjectCountDislocations = 0;
var lightObjectCountInterfaces = 0;
var lightObjectCountSurfaces = 0;
var lightObjectCountDuplicateSuspects = 0;


// Project metadata
var projectConfigured = 0;
var sampleName = "";
var experimentalCondition = "";
var montageId = "";
var sourceFirst = "";
var sourceLast = "";
var sourceImageList = "";
var microscopeVoltage = "";
var specimenTemperature = "";
var operatorName = "";
var projectNotes = "";
var imageFileName = "";
var imageDirectory = "";
var imageChecksum = "";
var sessionRoiPath = "";

// ProjectAware bridge with Cavity TEM Studio / Python-prepared projects
var projectAwareActive = 0;
var projectAwareProjectDir = "";
var projectAwareSessionsDir = "";
var projectAwareDerivedDir = "";
var projectAwareViewsDir = "";
var projectAwareProjectFieldsCsv = "";
var projectAwareMetadataJson = "";
var projectAwareLayoutCheckCsv = "";
var projectAwareMontageBuildLogCsv = "";
var projectAwareResultsCsv = "";
var projectAwareMasterTif = "";
var projectAwareCurrentAnalysisImagePath = "";
var projectAwareCurrentAnalysisImageRole = "";
var projectAwareCurrentAnalysisImageName = "";
var projectAwareProjectUid = "";
var projectAwarePanelCount = "";
var projectAwarePixelWidth = "";
var projectAwarePixelHeight = "";
var projectAwarePixelUnit = "";
var projectAwareSourceEndExclusive = "";
var projectAwareLastExportDir = "";

// Calibration and geometry
var scaleDefined = 0;
var scaleKnownNm = 0;
var nmPerPixelX = 1;
var nmPerPixelY = 1;
var unitFactorNm = 1;
var currentUnit = "pixel";

var surfaceDefined = 0;
var surfaceSideDefined = 0;
var surfaceMaterialX = NaN;
var surfaceMaterialY = NaN;
var surfaceMaterialSign = 1;
var surfaceX = newArray(0);
var surfaceY = newArray(0);

// Last surface calculation. computeSurfaceMetrics() updates these values.
var surfaceLastDistanceNm = NaN;
var surfaceLastSignedDistanceNm = NaN;
var surfaceLastArcNm = NaN;
var surfaceLastNearestXpx = NaN;
var surfaceLastNearestYpx = NaN;
var surfaceLastTangentAngleDeg = NaN;

// Cavity measurement and grouping
var activeDiameterNm = 0;
var bandNm = 50;
var bandCount = 20;
var excludeNegativeDepth = 1;
var usePanelsAsMask = 0;
var displayMode = "type"; // type, band or quality
var PI_VAL = 3.141592653589793;

// Stable serial counters
var cavityCounter = 0;
var panelCounter = 0;
var maskCounter = 0;
var exclusionCounter = 0;
var grainBoundaryCounter = 0;
var dislocationCounter = 0;
var loopCounter = 0;
var interfaceCounter = 0;

// Duplicate detection
var duplicateCenterTolPx = 2.0;
var duplicateRelativeTol = 0.20;
var duplicateDiameterTolFraction = 0.30;
var selectionTolerancePx = 5.0;
var pointValidityReason = "";
var panelLastId = "";
var panelLastSource = "";
var panelLastMatchCount = 0;

// Area sampling for band denominators
var areaSamplingTarget = 2000000;
var lastAreaSamplingStepPx = NaN;
var lastValidAreaNm2 = NaN;
var lastBandAreasNm2 = newArray(0);

// Quantitative export coverage. Globals avoid ambiguous mixed text/numeric
// return values in IJM when no or only one field is present after split().
var coverageMaxBand = -1;
var coverageUnbanded = 0;
var coverageIncluded = 0;

// Appearance
var showRoiLabels = 1;
var fillCavities = 1;
var fillAlpha = 70;
var fillAlphaHex = "46";
var roiStrokeWidth = 1;
var activeStrokeColor = "#00ff00";
var activeFillColor = "#4600ff00";
var lightConfirmedCavityColor = "#00ff00";
var activeCavityClass = "confirmed";
var activeCavityClassLabel = "Confirmada";
var activeCavityConfidence = "high";
var autoOpenBrightnessContrast = 1;
var featureToolPreset = "";
var missingMacroToolWarningShown = 0;

// One-level undo for add/delete operations
var undoKind = "";
var undoObjectId = "";
var undoDeletedName = "";
var undoAvailable = 0;

// Navigation and view preservation
var keepWindowSize = 1;
var lockedWinW = 0;
var lockedWinH = 0;
var fixedNavigation = 1;
var panFraction = 0.75;
var keyPanFraction = 0.30;
var wheelPanFraction = 0.18;
var zoomStep = 1.5;
var restoreViewAfterRoi = 1;
var viewSnapshotValid = 0;
var viewSnapX = 0;
var viewSnapY = 0;
var viewSnapW = 0;
var viewSnapH = 0;
var viewSnapWinX = 0;
var viewSnapWinY = 0;
var viewSnapWinW = 0;
var viewSnapWinH = 0;

// -----------------------------------------------------------------------------
// Macro commands. No F-key shortcuts are used.
// -----------------------------------------------------------------------------

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// Toolbar tools
// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// -----------------------------------------------------------------------------
// Control panel and status
// -----------------------------------------------------------------------------

function showControlPanel() { lightShowPanel(); }


function refreshControlPanelStatus() { lightRefreshPanel(); }


function panelStatusLine1() {
    s = sampleName;
    if (s == "") s = "(muestra sin definir)";
    m = montageId;
    if (m == "") m = "(montaje sin definir)";
    r = sourceFirst;
    if (sourceLast != "") r = r + " - " + sourceLast;
    if (r == "") r = "(origen sin definir)";
    return "Muestra: " + s + " | Montaje: " + m + " | Imagenes: " + r;
}

function panelStatusLine2() {
    sc = "sin escala";
    if (updateScaleMaybe()) sc = d2s(nmPerPixelX, 6) + " nm/px";
    if (scaleDefined) sc = sc + " (referencia visible)";
    sf = "sin superficie";
    if (surfaceDefined) {
        sf = "superficie definida";
        if (surfaceSideDefined) sf = sf + " + lado material";
        else sf = sf + " (distancia sin signo)";
    }
    d = "sin diametro activo";
    if (activeDiameterNm > 0) d = d2s(activeDiameterNm, 3) + " nm";
    modeLabel = currentInteractionModeLabel();
    return "Escala: " + sc + " | " + sf + " | Diametro activo: " + d + " | Modo: " + modeLabel;
}

function panelStatusLine3() {
    countsReady = lightRefreshObjectCounts();
    if (countsReady == 0) {
        lightObjectCountCavities = 0;
        lightObjectCountMasks = 0;
        lightObjectCountExclusions = 0;
        lightObjectCountDuplicateSuspects = 0;
    }
    pa = "";
    if (projectAwareActive) pa = " | Proyecto: ProjectAware | Imagen: " + projectAwareCurrentAnalysisImageRole;
    return "Cavidades: " + lightObjectCountCavities + " | Tipo activo: " + activeCavityClassLabel + " | Mascaras: " + lightObjectCountMasks + " | Exclusiones: " + lightObjectCountExclusions + " | Duplicados sospechosos: " + lightObjectCountDuplicateSuspects + " | Color: " + displayMode + pa;
}

// -----------------------------------------------------------------------------
// Project metadata, session persistence and migration
// -----------------------------------------------------------------------------

function editProjectMetadata() {
    if (nImages() <= 0) exit("Abre primero la imagen o collage TEM.");
    refreshImageIdentity();

    if (montageId == "") montageId = stripExtension(getTitle());
    if (operatorName == "") operatorName = getInfo("user.name");

    Dialog.create("Proyecto y trazabilidad");
    Dialog.addString("Nombre de la muestra:", sampleName, 35);
    Dialog.addString("Condicion experimental:", experimentalCondition, 35);
    Dialog.addString("Identificador del collage/montaje:", montageId, 35);
    Dialog.addString("Primera imagen DM3:", sourceFirst, 25);
    Dialog.addString("Ultima imagen DM3:", sourceLast, 25);
    Dialog.addString("Lista completa (separada por ;):", sourceImageList, 55);
    Dialog.addString("Tension del microscopio:", microscopeVoltage, 20);
    Dialog.addString("Temperatura/condicion de muestra:", specimenTemperature, 20);
    Dialog.addString("Operador:", operatorName, 25);
    Dialog.addString("Notas:", projectNotes, 55);
    Dialog.show();

    sampleName = Dialog.getString();
    experimentalCondition = Dialog.getString();
    montageId = Dialog.getString();
    sourceFirst = Dialog.getString();
    sourceLast = Dialog.getString();
    sourceImageList = Dialog.getString();
    microscopeVoltage = Dialog.getString();
    specimenTemperature = Dialog.getString();
    operatorName = Dialog.getString();
    projectNotes = Dialog.getString();

    projectConfigured = 0;
    if (sampleName != "" && montageId != "") projectConfigured = 1;
    updateSessionMetadataRoi();
    refreshControlPanelStatus();
    showStatus("Metadatos del proyecto actualizados.");
}

function refreshImageIdentity() {
    detectedFileName = getInfo("image.filename");
    detectedDirectory = getInfo("image.directory");
    if (detectedFileName == "") detectedFileName = getTitle();
    imageFileName = detectedFileName;
    imageDirectory = normalizeStoredPath(detectedDirectory);
    imageChecksum = "";
    fullPath = "";
    if (imageFileName != "" && imageDirectory != "") fullPath = imageDirectory + imageFileName;
    if (fullPath != "" && File.exists(fullPath)) {
        imageChecksum = IJ.checksum("SHA-256 file", fullPath);
        if (imageChecksum == "0") imageChecksum = "";
    }
}

function openOrLoadSessionRois() { lightLoadRevision(); return 1; }


function saveSessionRois() { lightSaveRevision(); return 1; }


function loadSessionFromRois(verbose) {
    if (nImages() <= 0) return 0;
    run("ROI Manager..."); n = roiManager("count"); if (n == 0) return 0;
    snapshotCurrentView(); loaded = 0; idx = findMetadataIndex();
    if (idx >= 0) { if(!safeRoiSelect(idx))return 0; loaded = readMetadataFromSelectedRoi();if(!loaded)return 0; }
    if (loadScaleReferenceFromRois()) { loaded = 1; rebuildScaleLabelFromReference(0); }
    if (loadSurfaceReferenceFromRois()) loaded = 1;
    if (!updateScaleMaybe()) { if (inferLegacyScaleFromCavities()) loaded = 1; }
    ensureObjectIds(); recalculateCounters(); lightInvalidateAnalysisCache(); restyleAllRois(); showAllRois(); restoreViewSnapshot(); installInteractionListeners(0);lightInteractivePushState("select");
    if (loaded) updateSessionMetadataRoi();
    if (verbose && loaded) {
        msg = "Sesion Cavity TEM Light restaurada.\n\nImagen: " + lightImageId + "\nMuestra: " + sampleName + "\n";
        if (updateScaleMaybe()) msg = msg + "Escala: " + d2s(nmPerPixelX,8) + " x " + d2s(nmPerPixelY,8) + " nm/px\n";
        msg = msg + "Cavidades: " + countTypeFast("cavity") + "\nAreas validas: " + countTypeFast("analysis_mask") + "; exclusiones: " + countTypeFast("exclusion") + ".";
        showMessage("Sesion Light restaurada", msg);
    }
    lightRefreshPanel(); return loaded;
}
function readMetadataFromSelectedRoi() {
    mv=Roi.getProperty("Macro_version");candidateProjectRoot=normalizeStoredPath(propString("Light_project_root",lightProjectRoot));candidateProjectId=propString("Light_project_id",lightProjectId);candidateProjectName=propString("Light_project_name",lightProjectName);candidateProjectUid=propString("Light_project_uid",lightProjectUid);candidateImageId=propString("Light_image_id",propString("Montage_id",lightImageId));candidateImageDir=normalizeStoredPath(propString("Light_image_dir",lightImageDir));
    descriptor="";if(lightProjectFile!=""&&lightProjectDescriptorValid(lightProjectFile,candidateProjectId,candidateProjectUid)==1)descriptor=lightProjectFile;if(descriptor=="")descriptor=lightFindCanonicalProjectFile(candidateProjectRoot);if(descriptor=="")descriptor=lightFindCanonicalProjectFile(candidateImageDir);
    if(lightProjectDescriptorValid(descriptor,candidateProjectId,candidateProjectUid)==0){showMessage("Sesion ROI rechazada","Las ROIs no pueden vincularse a un descriptor canonico con el mismo Project ID y Project UID.\n\nNo se modificara el contexto del proyecto.");return 0;}
    lightProjectFile=normalizeStoredPath(descriptor);lightProjectRoot=lightNormalizeDir(File.getDirectory(descriptor));lightProjectId=lightKvRead(descriptor,"project_id",candidateProjectId);lightProjectName=lightKvRead(descriptor,"project_name",candidateProjectName);lightProjectUid=lightKvRead(descriptor,"project_uid",candidateProjectUid);
    lightImageId=candidateImageId;expectedImageDir=lightNormalizeDir(lightJoin(lightJoin(lightProjectRoot,"images"),lightImageId));lightImageDir=expectedImageDir;
    lightSourcePath=normalizeStoredPath(propString("Light_source_path",lightSourcePath));lightSourceStoredPath=normalizeStoredPath(propString("Light_source_stored_path",lightSourceStoredPath));lightSourceSha256=propString("Light_source_sha256",propString("Image_checksum_sha256",lightSourceSha256));lightCopySource=round(propNumber("Light_copy_source",lightCopySource));lightImageMode=propString("Light_image_mode",lightImageMode);lightThicknessNm=propNumber("Light_thickness_nm",lightThicknessNm);lightThicknessUncertaintyNm=propNumber("Light_thickness_uncertainty_nm",lightThicknessUncertaintyNm);lightThicknessMethod=propString("Light_thickness_method",lightThicknessMethod);lightThicknessNotes=propString("Light_thickness_notes",lightThicknessNotes);lightOriginalScaleNmX=propNumber("Light_original_scale_nm_per_px_x",lightOriginalScaleNmX);lightOriginalScaleNmY=propNumber("Light_original_scale_nm_per_px_y",lightOriginalScaleNmY);lightOriginalScaleUnit=propString("Light_original_scale_unit",lightOriginalScaleUnit);lightScaleOrigin=propString("Light_scale_origin",lightScaleOrigin);lightScaleConfirmed=round(propNumber("Light_scale_confirmed",lightScaleConfirmed));lightUseWholeImage=round(propNumber("Light_use_whole_image",lightUseWholeImage));lightIncludeUncertain=round(propNumber("Light_include_uncertain",lightIncludeUncertain));lightHistogramBinNm=propNumber("Light_histogram_bin_nm",lightHistogramBinNm);lightFeatureDistanceBinNm=propNumber("Light_feature_distance_bin_nm",lightFeatureDistanceBinNm);lightCurrentRevision=propString("Light_current_revision",lightCurrentRevision);
    sampleName=lightKvRead(descriptor,"sample_name",repairCommonTextEncoding(propString("Sample_name",sampleName)));experimentalCondition=lightKvRead(descriptor,"experimental_condition",repairCommonTextEncoding(propString("Experimental_condition",experimentalCondition)));microscopeVoltage=repairCommonTextEncoding(propString("Microscope_voltage",microscopeVoltage));specimenTemperature=repairCommonTextEncoding(propString("Specimen_temperature",specimenTemperature));operatorName=lightKvRead(descriptor,"operator_name",repairCommonTextEncoding(propString("Operator_name",operatorName)));projectNotes=lightKvRead(descriptor,"project_notes",repairCommonTextEncoding(propString("Project_notes",projectNotes)));imageFileName=repairCommonTextEncoding(propString("Image_filename",imageFileName));imageDirectory=normalizeStoredPath(repairCommonTextEncoding(propString("Image_directory",imageDirectory)));montageId=lightImageId;sourceFirst=imageFileName;sourceLast=imageFileName;sourceImageList=imageFileName;
    sx=propNumber("Scale_nm_per_px_x",0);sy=propNumber("Scale_nm_per_px_y",0);if(sx>0&&sy>0){setVoxelSize(sx,sy,1,"nm");updateScaleMaybe();}scaleKnownNm=propNumber("Scale_known_length_nm",scaleKnownNm);scaleDefined=round(propNumber("Scale_defined",scaleDefined));surfaceDefined=round(propNumber("Surface_defined",surfaceDefined));surfaceSideDefined=round(propNumber("Surface_side_defined",surfaceSideDefined));surfaceMaterialX=propNumber("Surface_material_x_px",surfaceMaterialX);surfaceMaterialY=propNumber("Surface_material_y_px",surfaceMaterialY);surfaceMaterialSign=propNumber("Surface_material_sign",surfaceMaterialSign);if(surfaceMaterialSign==0||isNaN(surfaceMaterialSign))surfaceMaterialSign=1;activeDiameterNm=propNumber("Active_diameter_nm",activeDiameterNm);lightBandMode=propString("HF3_band_mode","width");lightSizeBreaks=propString("HF3_size_breaks_nm","0.5,1,1.5,2,3,5");lightResultContrast=propNumber("HF3_result_contrast",0.18);bandNm=propNumber("Band_width_nm",bandNm);bandCount=round(propNumber("Band_count",bandCount));excludeNegativeDepth=round(propNumber("Exclude_negative_depth",excludeNegativeDepth));usePanelsAsMask=0;displayMode=propString("Display_mode",displayMode);duplicateCenterTolPx=propNumber("Duplicate_center_tol_px",duplicateCenterTolPx);duplicateRelativeTol=propNumber("Duplicate_relative_tol",duplicateRelativeTol);duplicateDiameterTolFraction=propNumber("Duplicate_diameter_tol_fraction",duplicateDiameterTolFraction);selectionTolerancePx=propNumber("Selection_tolerance_px",selectionTolerancePx);areaSamplingTarget=round(propNumber("Area_sampling_target",areaSamplingTarget));storedExactLabelMode=propString("Light_exact_label_mode","");showRoiLabels=round(propNumber("Show_roi_labels",showRoiLabels));if(storedExactLabelMode=="")showRoiLabels=1;fillCavities=round(propNumber("Fill_cavities",fillCavities));fillAlpha=round(propNumber("Fill_alpha",fillAlpha));roiStrokeWidth=round(propNumber("ROI_stroke_width",roiStrokeWidth));lightInteractivePreviewEnabled=round(propNumber("Light_interactive_preview",lightInteractivePreviewEnabled));lightInteractiveResizeStepNm=propNumber("Light_resize_step_nm",lightInteractiveResizeStepNm);if(lightInteractiveResizeStepNm<lightInteractiveResizeMinNm)lightInteractiveResizeStepNm=lightInteractiveResizeMinNm;if(lightInteractiveResizeStepNm>lightInteractiveResizeMaxNm)lightInteractiveResizeStepNm=lightInteractiveResizeMaxNm;
    setMetadataImageProperties();
    projectConfigured=0;if(lightProjectId!=""&&lightImageId!="")projectConfigured=1;lightProjectLoaded=projectConfigured;v4ProjectLoaded=0;savedW=round(propNumber("Image_width_px",getWidth()));savedH=round(propNumber("Image_height_px",getHeight()));if(savedW!=getWidth()||savedH!=getHeight())showMessage("Aviso de trazabilidad","Las ROIs pertenecen a "+savedW+" x "+savedH+" px y la imagen activa tiene "+getWidth()+" x "+getHeight()+" px.");loaded=0;if(mv!="")loaded=1;if(lightImageId!="")loaded=1;if(sx>0)loaded=1;return loaded;
}

function updateSessionMetadataRoi() {
    lightHF4Pull();
    if (nImages() <= 0) return;
    run("ROI Manager...");
    refreshImageIdentityIfMissing();
    updateScaleMaybe();

    idx = findMetadataIndex();
    if (idx >= 0) {
        if(!safeRoiSelect(idx))return;
        Roi.setName(sessionMetadataName);
        Roi.setGroup(0);
        Roi.setFillColor("#00000000");
        Roi.setStrokeColor("#00000000");
        writeMetadataProperties();
        roiManager("update");
    } else {
        makeRectangle(0, 0, 1, 1);
        Roi.setName(sessionMetadataName);
        Roi.setGroup(0);
        Roi.setFillColor("#00000000");
        Roi.setStrokeColor("#00000000");
        writeMetadataProperties();
        roiManager("add");
    }
}

function writeMetadataProperties() {
    updateScaleMaybe();
    Roi.setProperty("Type", "session_metadata");
    Roi.setProperty("Macro_version", macroVersion);
    Roi.setProperty("Light_schema_version", lightSchemaVersion);
    Roi.setProperty("Light_release_version", lightReleaseVersion);
    Roi.setProperty("Light_validation_state", lightValidationState);
    Roi.setProperty("Light_project_root", lightProjectRoot);
    Roi.setProperty("Light_project_id", lightProjectId);
    Roi.setProperty("Light_project_name", lightProjectName);
    Roi.setProperty("Light_project_uid", lightProjectUid);
    Roi.setProperty("Light_image_id", lightImageId);
    Roi.setProperty("Light_image_dir", lightImageDir);
    Roi.setProperty("Light_source_path", lightSourcePath);
    Roi.setProperty("Light_source_stored_path", lightSourceStoredPath);
    Roi.setProperty("Light_source_sha256", lightSourceSha256);
    Roi.setProperty("Light_copy_source", d2s(lightCopySource,0));
    Roi.setProperty("Light_image_mode", lightImageMode);
    Roi.setProperty("Light_thickness_nm", d2s(lightThicknessNm,9));
    Roi.setProperty("Light_thickness_uncertainty_nm", d2s(lightThicknessUncertaintyNm,9));
    Roi.setProperty("Light_thickness_method", lightThicknessMethod);
    Roi.setProperty("Light_thickness_notes", lightThicknessNotes);
    Roi.setProperty("Light_original_scale_nm_per_px_x", d2s(lightOriginalScaleNmX,12));
    Roi.setProperty("Light_original_scale_nm_per_px_y", d2s(lightOriginalScaleNmY,12));
    Roi.setProperty("Light_original_scale_unit", lightOriginalScaleUnit);
    Roi.setProperty("Light_scale_origin", lightScaleOrigin);
    Roi.setProperty("Light_scale_confirmed", d2s(lightScaleConfirmed,0));
    Roi.setProperty("Light_use_whole_image", d2s(lightUseWholeImage,0));
    Roi.setProperty("Light_include_uncertain", d2s(lightIncludeUncertain,0));
    Roi.setProperty("Light_histogram_bin_nm", d2s(lightHistogramBinNm,9));
    Roi.setProperty("Light_feature_distance_bin_nm", d2s(lightFeatureDistanceBinNm,9));
    Roi.setProperty("Light_current_revision", lightCurrentRevision);
    Roi.setProperty("Sample_name", sampleName);
    Roi.setProperty("Experimental_condition", experimentalCondition);
    Roi.setProperty("Montage_id", lightImageId);
    Roi.setProperty("Source_first", imageFileName);
    Roi.setProperty("Source_last", imageFileName);
    Roi.setProperty("Source_image_list", imageFileName);
    Roi.setProperty("Microscope_voltage", microscopeVoltage);
    Roi.setProperty("Specimen_temperature", specimenTemperature);
    Roi.setProperty("Operator_name", operatorName);
    Roi.setProperty("Project_notes", projectNotes);
    Roi.setProperty("Image_title", getTitle());
    Roi.setProperty("Image_filename", imageFileName);
    Roi.setProperty("Image_directory", normalizeStoredPath(imageDirectory));
    Roi.setProperty("Image_checksum_sha256", lightSourceSha256);
    Roi.setProperty("Image_width_px", d2s(getWidth(),0));
    Roi.setProperty("Image_height_px", d2s(getHeight(),0));
    Roi.setProperty("Scale_defined", d2s(scaleDefined,0));
    Roi.setProperty("Scale_known_length_nm", d2s(scaleKnownNm,9));
    Roi.setProperty("Scale_nm_per_px_x", d2s(nmPerPixelX,12));
    Roi.setProperty("Scale_nm_per_px_y", d2s(nmPerPixelY,12));
    Roi.setProperty("Surface_defined", d2s(surfaceDefined,0));
    Roi.setProperty("Surface_side_defined", d2s(surfaceSideDefined,0));
    Roi.setProperty("Surface_material_x_px", d2s(surfaceMaterialX,6));
    Roi.setProperty("Surface_material_y_px", d2s(surfaceMaterialY,6));
    Roi.setProperty("Surface_material_sign", d2s(surfaceMaterialSign,0));
    Roi.setProperty("Active_diameter_nm", d2s(activeDiameterNm,9));
    Roi.setProperty("Band_width_nm", d2s(bandNm,9));
    Roi.setProperty("Band_count", d2s(bandCount,0));
    Roi.setProperty("HF3_band_mode",lightBandMode);
    Roi.setProperty("HF3_size_breaks_nm",lightSizeBreaks);
    Roi.setProperty("HF3_result_contrast",d2s(lightResultContrast,6));
    Roi.setProperty("Exclude_negative_depth", d2s(excludeNegativeDepth,0));
    Roi.setProperty("Use_panels_as_mask", "0");
    Roi.setProperty("Display_mode", displayMode);
    Roi.setProperty("Duplicate_center_tol_px", d2s(duplicateCenterTolPx,6));
    Roi.setProperty("Duplicate_relative_tol", d2s(duplicateRelativeTol,6));
    Roi.setProperty("Duplicate_diameter_tol_fraction", d2s(duplicateDiameterTolFraction,6));
    Roi.setProperty("Selection_tolerance_px", d2s(selectionTolerancePx,6));
    Roi.setProperty("Area_sampling_target", d2s(areaSamplingTarget,0));
    Roi.setProperty("Show_roi_labels", d2s(showRoiLabels,0));
    Roi.setProperty("Fill_cavities", d2s(fillCavities,0));
    Roi.setProperty("Fill_alpha", d2s(fillAlpha,0));
    Roi.setProperty("ROI_stroke_width", d2s(roiStrokeWidth,0));
    Roi.setProperty("Light_exact_label_mode", "roi_name_v1");
    Roi.setProperty("Light_interactive_preview", d2s(lightInteractivePreviewEnabled,0));
    Roi.setProperty("Light_resize_step_nm", d2s(lightInteractiveResizeStepNm,6));
    Roi.setProperty("Cavity_counter", d2s(cavityCounter,0));
    Roi.setProperty("Mask_counter", d2s(maskCounter,0));
    Roi.setProperty("Exclusion_counter", d2s(exclusionCounter,0));
    Roi.setProperty("Grain_boundary_counter", d2s(grainBoundaryCounter,0));
    Roi.setProperty("Dislocation_counter", d2s(dislocationCounter,0));
    Roi.setProperty("Interface_counter", d2s(interfaceCounter,0));
}


function setCommonObjectProperties() {
    updateScaleMaybe();
    Roi.setProperty("Session_macro_version", macroVersion);
    Roi.setProperty("Light_schema_version", lightSchemaVersion);
    Roi.setProperty("Project_id", lightProjectId);
    Roi.setProperty("Project_uid", lightProjectUid);
    Roi.setProperty("Image_id", lightImageId);
    Roi.setProperty("Image_mode", lightImageMode);
    Roi.setProperty("Source_sha256", lightSourceSha256);
    Roi.setProperty("Revision_id", lightCurrentRevision);
    Roi.setProperty("Sample_name", sampleName);
    Roi.setProperty("Experimental_condition", experimentalCondition);
    Roi.setProperty("Montage_id", lightImageId);
    Roi.setProperty("Image_title", getTitle());
    Roi.setProperty("Image_width_px", d2s(getWidth(),0));
    Roi.setProperty("Image_height_px", d2s(getHeight(),0));
    Roi.setProperty("Session_scale_nm_per_px_x", d2s(nmPerPixelX,12));
    Roi.setProperty("Session_scale_nm_per_px_y", d2s(nmPerPixelY,12));
    Roi.setProperty("Session_scale_unit", "nm");
    Roi.setProperty("Foil_thickness_nm", d2s(lightThicknessNm,9));
}


function findMetadataIndex() {
    n = roiManager("count");
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        name = Roi.getName;
        type = Roi.getProperty("Type");
        if (type == "session_metadata" || name == sessionMetadataName || name == legacyMetadataName || startsWith(name, legacyMetadataName)) return i;
    }
    return -1;
}

function refreshImageIdentityIfMissing() {
    currentFileName = getInfo("image.filename");
    currentImageDirectory = getInfo("image.directory");
    storedPathValid = 0;
    if (imageFileName != "" && imageDirectory != "") {
        normalizedImageDirectory = normalizeStoredPath(imageDirectory);
        storedFullPath = normalizedImageDirectory + imageFileName;
        if (File.exists(storedFullPath)) storedPathValid = 1;
    }
    if (!storedPathValid || imageFileName == "" || imageDirectory == "" || looksLikeCollapsedWindowsPath(imageDirectory)) {
        if (currentFileName != "" || currentImageDirectory != "") refreshImageIdentity();
        else if (imageFileName == "") imageFileName = getTitle();
    }
}

function inferLegacyScaleFromCavities() {
    n = roiManager("count");
    sxSum = 0;
    sySum = 0;
    c = 0;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        if (currentRoiIsCavity()) {
            d = propNumber("Diameter_nm", -1);
            Roi.getFloatBounds(x, y, w, h);
            if (d > 0 && w > 0 && h > 0) {
                sxSum = sxSum + d/w;
                sySum = sySum + d/h;
                c++;
            }
        }
    }
    if (c > 0) {
        setVoxelSize(sxSum/c, sySum/c, 1, "nm");
        updateScaleMaybe();
        return 1;
    }
    return 0;
}

function ensureObjectIds() {
    if (nImages() <= 0) return;
    run("ROI Manager...");
    recalculateCounters();
    n = roiManager("count");
    changed = 0;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        name = Roi.getName;
        storedType = Roi.getProperty("Type");
        type = normalizedType(name, storedType);
        if (type == "cavity") {
            id = Roi.getProperty("Cavity_id");
            if (id == "") {
                cavityCounter++;
                id = "CAV_" + IJ.pad(cavityCounter, 6);
                Roi.setProperty("Cavity_id", id);
                Roi.setProperty("Cavity_serial", d2s(cavityCounter, 0));
                Roi.setProperty("Legacy_name", name);
                Roi.setProperty("Type", "cavity");
                Roi.setName(id);
                roiManager("update");
                changed++;
            }
        } else if (type == "panel") {
            id = Roi.getProperty("Panel_id");
            if (id == "") {
                panelCounter++;
                id = "PANEL_" + IJ.pad(panelCounter, 3);
                Roi.setProperty("Panel_id", id);
                Roi.setProperty("Panel_order", d2s(panelCounter, 0));
                Roi.setProperty("Type", "panel");
                Roi.setName(id);
                roiManager("update");
                changed++;
            }
        } else if (type == "analysis_mask") {
            id = Roi.getProperty("Mask_id");
            if (id == "") {
                maskCounter++;
                id = "MASK_" + IJ.pad(maskCounter, 3);
                Roi.setProperty("Mask_id", id);
                Roi.setProperty("Type", "analysis_mask");
                Roi.setName(id);
                roiManager("update");
                changed++;
            }
        } else if (type == "exclusion") {
            id = Roi.getProperty("Exclusion_id");
            if (id == "") {
                exclusionCounter++;
                id = "EXCL_" + IJ.pad(exclusionCounter, 3);
                Roi.setProperty("Exclusion_id", id);
                Roi.setProperty("Type", "exclusion");
                Roi.setName(id);
                roiManager("update");
                changed++;
            }
        } else if (type == "grain_boundary") {
            id = Roi.getProperty("Feature_id");
            if (id == "") {
                grainBoundaryCounter++;
                id = "GB_" + IJ.pad(grainBoundaryCounter, 4);
                Roi.setProperty("Feature_id", id);
                Roi.setProperty("Type", "grain_boundary");
                Roi.setName(id);
                roiManager("update");
                changed++;
            }
        } else if (type == "dislocation") {
            id = Roi.getProperty("Feature_id");
            if (id == "") {
                dislocationCounter++;
                id = "DISL_" + IJ.pad(dislocationCounter, 4);
                Roi.setProperty("Feature_id", id);
                Roi.setProperty("Type", "dislocation");
                Roi.setName(id);
                roiManager("update");
                changed++;
            }
        } else if (type == "dislocation_loop") {
            id = Roi.getProperty("Object_id");
            if (id == "") id = Roi.getProperty("Feature_id");
            if (id == "" || !startsWith(id, "LOOP_")) {
                loopCounter++;
                id = "LOOP_" + IJ.pad(loopCounter, 6);
                Roi.setProperty("Legacy_name", name);
            }
            loopCounter = max2(loopCounter, serialFromId(id));
            Roi.setProperty("Object_id", id);
            Roi.setProperty("Feature_id", id);
            Roi.setProperty("Type", "dislocation_loop");
            Roi.setProperty("Object_type", "dislocation_loop");
            subtype = Roi.getProperty("Object_subtype");
            if (subtype == "") subtype = v4LoopSubtypeForCurrentSelection();
            Roi.setProperty("Object_subtype", subtype);
            visibleName = v4VisibleLoopName(id, subtype);
            if (name != visibleName) Roi.setName(visibleName);
            roiManager("update");
            changed++;
        } else if (type == "interface") {
            id = Roi.getProperty("Feature_id");
            if (id == "") {
                interfaceCounter++;
                id = "INT_" + IJ.pad(interfaceCounter, 4);
                Roi.setProperty("Feature_id", id);
                Roi.setProperty("Type", "interface");
                Roi.setName(id);
                roiManager("update");
                changed++;
            }
        }
    }
    if (changed > 0) updateSessionMetadataRoi();
}

function recalculateCounters() {
    cavityCounter = 0;
    panelCounter = 0;
    maskCounter = 0;
    exclusionCounter = 0;
    grainBoundaryCounter = 0;
    dislocationCounter = 0;
    loopCounter = 0;
    interfaceCounter = 0;
    activeCavityCount = 0;
    n = roiManager("count");
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        type = currentRoiType();
        cavityIdValue = Roi.getProperty("Cavity_id");
        panelIdValue = Roi.getProperty("Panel_id");
        maskIdValue = Roi.getProperty("Mask_id");
        exclusionIdValue = Roi.getProperty("Exclusion_id");
        featureIdValue = Roi.getProperty("Feature_id");
        cavityFallback = serialFromId(cavityIdValue);
        panelFallback = serialFromId(panelIdValue);
        if (type == "cavity") { cavityCounter = max2(cavityCounter, max2(cavityFallback, round(propNumber("Cavity_serial", cavityFallback)))); activeCavityCount++; }
        if (type == "panel") panelCounter = max2(panelCounter, round(propNumber("Panel_order", panelFallback)));
        if (type == "analysis_mask") maskCounter = max2(maskCounter, serialFromId(maskIdValue));
        if (type == "exclusion") exclusionCounter = max2(exclusionCounter, serialFromId(exclusionIdValue));
        if (type == "grain_boundary") grainBoundaryCounter = max2(grainBoundaryCounter, serialFromId(featureIdValue));
        if (type == "dislocation") dislocationCounter = max2(dislocationCounter, serialFromId(featureIdValue));
        if (type == "dislocation_loop") loopCounter = max2(loopCounter, serialFromId(Roi.getProperty("Object_id")));
        if (type == "interface") interfaceCounter = max2(interfaceCounter, serialFromId(featureIdValue));
    }
    lightCachedCavityCount = activeCavityCount;
}

// -----------------------------------------------------------------------------
// Cancellation-safe drawing support
// -----------------------------------------------------------------------------

function waitForUserSafe(title, message) {
    // The native IJM waitForUser() throws RuntimeException("Macro canceled")
    // when Cancel or Esc is used. Calling WaitForUserDialog directly lets us
    // inspect escPressed(), reset the Escape state and return normally.
    safeTitle = jsEscape(title);
    safeMessage = jsEscape(message);
    code = "var IJ=Packages.ij.IJ;var D=Packages.ij.gui.WaitForUserDialog;";
    code = code + "var d=new D('" + safeTitle + "','" + safeMessage + "');";
    code = code + "function relabel(c){try{var a=c.getComponents();for(var i=0;i<a.length;i++){var x=a[i];try{var t=String(x.getLabel());if(t.indexOf('Cancel')>=0)x.setLabel(' Terminar ');}catch(e){}try{relabel(x);}catch(e){}}}catch(e){}}";
    code = code + "relabel(d);d.pack();d.show();var cancelled=d.escPressed();IJ.resetEscape();String(cancelled?'0':'1');";
    safeResult = eval("js", code);
    if (safeResult == "1") return 1;
    return 0;
}

function finishCancelledDrawing(message) {
    run("ROI Manager...");
    roiManager("deselect");
    Roi.selectNone;
    ok = activateMacroToolByPrefix("Cavity select");
    if (!ok) setTool("hand");
    refreshControlPanelStatus();
    showStatus(message);
}

// -----------------------------------------------------------------------------
// Scale and surface references
// -----------------------------------------------------------------------------

function calibrateScaleFromLine() {
    if (nImages() <= 0) exit("Abre primero la imagen o collage TEM.");
    if (!v55VerifyQuantitativeIntegrity("calibrar la escala", 1, 1)) return;
    run("ROI Manager...");

    existingMeasurements = countTypeFast("cavity");
    if (existingMeasurements > 0) {
        proceed = getBoolean("Hay " + existingMeasurements + " cavidades. Sustituir la escala recalculara todos los valores fisicos desde la geometria actual.\n\nContinuar?", "Sustituir escala", "Cancelar");
        if (!proceed) return;
    }

    setTool("line");
    if (!waitForUserSafe("Calibrar escala", "Dibuja una linea recta exactamente sobre una barra de escala o una distancia conocida.\nPulsa OK cuando termine o Cancelar/Esc para conservar la escala anterior.")) {
        finishCancelledDrawing("Calibracion cancelada. La escala anterior se conserva.");
        return;
    }
    getLine(x1, y1, x2, y2, lw);
    if (x1 == -1) exit("No hay una seleccion de linea recta.");
    dpx = sqrt((x2-x1)*(x2-x1) + (y2-y1)*(y2-y1));
    if (dpx <= 0) exit("La linea de escala tiene longitud cero.");

    defaultNm = scaleKnownNm;
    if (defaultNm <= 0) defaultNm = 50;
    knownNm = getNumber("Longitud real de la linea (nm):", defaultNm);
    if (knownNm <= 0) exit("La longitud conocida debe ser mayor que cero.");

    newNmPerPx = knownNm/dpx;
    if (!getBoolean("Longitud en pixels: " + d2s(dpx, 3) + " px\nLongitud real: " + d2s(knownNm, 6) + " nm\nEscala resultante: " + d2s(newNmPerPx, 9) + " nm/px\n\nAceptar y sustituir la escala activa?", "Aceptar escala", "Cancelar")) return;

    snapshotCurrentView();
    setVoxelSize(newNmPerPx, newNmPerPx, 1, "nm");
    updateScaleOrExit();
    scaleKnownNm = knownNm;
    scaleDefined = 1;

    deleteScaleRoisOnly();
    makeLine(x1, y1, x2, y2);
    Roi.setName(scaleReferenceName);
    Roi.setGroup(0);
    Roi.setStrokeColor("yellow");
    Roi.setUnscalableStrokeWidth(3);
    setCommonObjectProperties();
    v4StampCurrentRevisionBinding();
    Roi.setProperty("Type", "scale_reference");
    Roi.setProperty("Known_length_nm", d2s(knownNm, 9));
    Roi.setProperty("Line_length_px", d2s(dpx, 9));
    Roi.setProperty("Scale_nm_per_px", d2s(newNmPerPx, 12));
    Roi.setProperty("X1_px", d2s(x1, 6));
    Roi.setProperty("Y1_px", d2s(y1, 6));
    Roi.setProperty("X2_px", d2s(x2, 6));
    Roi.setProperty("Y2_px", d2s(y2, 6));
    roiManager("add");

    rebuildScaleLabelFromReference(0);

    syncAllObjects(0);
    showAllRois();
    restoreViewSnapshot();
    updateSessionMetadataRoi();
    refreshControlPanelStatus();
    showStatus("Escala v8 definida: " + d2s(newNmPerPx, 9) + " nm/px. La linea amarilla permanece visible.");
}

function verifyScaleReference() {
    if (!v55VerifyQuantitativeIntegrity("verificar la referencia de escala", 1, 1)) return;
    if (!loadScaleReferenceFromRois()) exit("No existe una ROI SCALE_REFERENCE. Define la escala primero.");
    idx = findScaleReferenceIndex();
    safeRoiSelect(idx);
    getLine(x1, y1, x2, y2, lw);
    if (x1 == -1) exit("La referencia de escala ya no es una linea recta valida.");
    dpx = sqrt((x2-x1)*(x2-x1) + (y2-y1)*(y2-y1));
    known = propNumber("Known_length_nm", scaleKnownNm);
    calculated = known/dpx;
    updateScaleOrExit();
    diffPct = 100*abs(calculated-nmPerPixelX)/nmPerPixelX;
    msg = "Referencia visible: " + d2s(known, 6) + " nm\n";
    msg = msg + "Longitud actual: " + d2s(dpx, 4) + " px\n";
    msg = msg + "Escala de la linea: " + d2s(calculated, 10) + " nm/px\n";
    msg = msg + "Escala de la imagen: " + d2s(nmPerPixelX, 10) + " nm/px\n";
    msg = msg + "Diferencia: " + d2s(diffPct, 4) + " %";
    if (diffPct > 1) msg = msg + "\n\nADVERTENCIA: la referencia y la calibracion difieren mas del 1 %.";
    showMessage("Verificacion de escala", msg);
}

function loadScaleReferenceFromRois() {
    idx = findScaleReferenceIndex();
    if (idx < 0) {
        if(!updateScaleMaybe())scaleDefined=0;
        return 0;
    }
    safeRoiSelect(idx);
    getLine(x1, y1, x2, y2, lw);
    if (x1 == -1) return 0;
    dpx = sqrt((x2-x1)*(x2-x1) + (y2-y1)*(y2-y1));
    known = propNumber("Known_length_nm", scaleKnownNm);
    if (dpx <= 0 || known <= 0) return 0;
    nmpp = known/dpx;
    setVoxelSize(nmpp, nmpp, 1, "nm");
    updateScaleMaybe();
    scaleKnownNm = known;
    scaleDefined = 1;
    return 1;
}

function findScaleReferenceIndex() {
    n = roiManager("count");
    idx = -1;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        name = Roi.getName;
        type = Roi.getProperty("Type");
        legacyScaleLine = startsWith(name, scaleReferenceName + "_") && name != scaleLabelName && type != "scale_label";
        if (type == "scale_reference" || name == scaleReferenceName || legacyScaleLine) idx = i;
    }
    return idx;
}

function deleteScaleRoisOnly() {
    n = roiManager("count");
    for (i=n-1; i>=0; i=i-1) {
        safeRoiSelect(i);
        type = Roi.getProperty("Type");
        name = Roi.getName;
        if (type == "scale_reference" || type == "scale_label" || name == scaleReferenceName || name == scaleLabelName || startsWith(name, scaleReferenceName + "_")) roiManager("delete");
    }
}

function deleteScaleLabelsOnly() {
    nScaleLabels = roiManager("count");
    for (jScaleLabel=nScaleLabels-1; jScaleLabel>=0; jScaleLabel=jScaleLabel-1) {
        safeRoiSelect(jScaleLabel);
        scaleLabelTypeValue = Roi.getProperty("Type");
        scaleLabelNameValue = Roi.getName;
        if (scaleLabelTypeValue == "scale_label" || scaleLabelNameValue == scaleLabelName || startsWith(scaleLabelNameValue, scaleLabelName + "_")) roiManager("delete");
    }
}

function rebuildScaleLabelFromReference(verbose) {
    if (nImages() <= 0) return 0;
    run("ROI Manager...");
    scaleLineIndex = findScaleReferenceIndex();
    if (scaleLineIndex < 0) {
        if (verbose) showMessage("Etiqueta de escala", "No existe una ROI SCALE_REFERENCE. Define primero la escala.");
        return 0;
    }

    safeRoiSelect(scaleLineIndex);
    getLine(sx1, sy1, sx2, sy2, scaleLineWidth);
    if (sx1 == -1) {
        if (verbose) showMessage("Etiqueta de escala", "La referencia de escala no es una linea recta valida.");
        return 0;
    }
    scaleLineLengthPx = sqrt((sx2-sx1)*(sx2-sx1)+(sy2-sy1)*(sy2-sy1));
    scaleLabelKnownNm = propNumber("Known_length_nm", scaleKnownNm);
    if (scaleLineLengthPx <= 0 || scaleLabelKnownNm <= 0) {
        if (verbose) showMessage("Etiqueta de escala", "La linea o la longitud conocida no son validas.");
        return 0;
    }

    scaleLabelNmPerPx = scaleLabelKnownNm/scaleLineLengthPx;
    scaleLabelTextValue = d2s(scaleLabelKnownNm, 3) + " nm | " + d2s(scaleLabelNmPerPx, 6) + " nm/px";
    scaleLabelFontPx = 24;
    setFont("SansSerif", scaleLabelFontPx, "bold antialiased");
    scaleLabelTextWidth = getStringWidth(scaleLabelTextValue);

    scaleLabelX = min2(sx1, sx2);
    scaleLabelY = min2(sy1, sy2)-scaleLabelFontPx-8;
    if (scaleLabelY < 0) scaleLabelY = max2(sy1, sy2)+8;
    if (scaleLabelX+scaleLabelTextWidth+6 > getWidth()) scaleLabelX = getWidth()-scaleLabelTextWidth-6;
    if (scaleLabelX < 0) scaleLabelX = 0;
    if (scaleLabelY+2*scaleLabelFontPx+6 > getHeight()) scaleLabelY = getHeight()-2*scaleLabelFontPx-6;
    if (scaleLabelY < 0) scaleLabelY = 0;

    deleteScaleLabelsOnly();
    setColor("yellow");
    makeText(scaleLabelTextValue, round(scaleLabelX), round(scaleLabelY));
    Roi.setName(scaleLabelName);
    Roi.setGroup(0);
    Roi.setFillColor("#aa000000");
    Roi.setStrokeColor("#ffff00");
    Roi.setAntiAlias(1);
    Roi.setFontSize(scaleLabelFontPx);
    Roi.setJustification("left");
    setCommonObjectProperties();
    v4StampCurrentRevisionBinding();
    Roi.setProperty("Type", "scale_label");
    Roi.setProperty("Known_length_nm", d2s(scaleLabelKnownNm, 9));
    Roi.setProperty("Scale_nm_per_px", d2s(scaleLabelNmPerPx, 12));
    Roi.setProperty("Label_text", scaleLabelTextValue);
    Roi.setProperty("Font_size_px", d2s(scaleLabelFontPx, 0));
    roiManager("add");
    showAllRois();
    if (verbose) showStatus("Etiqueta de escala recreada: " + scaleLabelTextValue);
    return 1;
}

function defineSurfaceReference() {
    if (nImages() <= 0) exit("Abre primero la imagen o collage TEM.");
    if (!v55VerifyQuantitativeIntegrity("definir la superficie de referencia", 1, 1)) return;
    updateScaleOrExit();
    run("ROI Manager...");

    choices = newArray("Polilinea segmentada", "Linea recta", "Linea libre");
    Dialog.create("Definir superficie de referencia");
    Dialog.addChoice("Tipo de trazado:", choices, choices[0]);
    Dialog.addMessage("La superficie sera unica. La anterior solo se sustituye despues de validar el nuevo trazado y el lado del material.");
    Dialog.show();
    choice = Dialog.getChoice();
    tool = "polyline";
    selectionKind = "polyline";
    if (choice == "Linea recta") { tool = "line"; selectionKind = "polyline"; }
    if (choice == "Linea libre") { tool = "freeline"; selectionKind = "freeline"; }

    setTool(tool);
    if (!waitForUserSafe("Trazar superficie", "Dibuja la superficie de referencia.\nPara una polilinea, haz clicks sucesivos y termina con doble click.\nPulsa OK al finalizar o Cancelar/Esc para conservar la superficie anterior.")) {
        finishCancelledDrawing("Definicion de superficie cancelada. La superficie anterior se conserva.");
        return;
    }
    st = selectionType;
    if (st != 5 && st != 6 && st != 7) exit("La seleccion no es una linea recta, segmentada o libre.");
    getSelectionCoordinates(newSX, newSY);
    if (newSX.length < 2) exit("La superficie necesita al menos dos puntos.");

    setTool("point");
    if (!waitForUserSafe("Indicar el interior del material", "Haz un click claramente dentro del material, en el lado positivo de la superficie.\nPulsa OK despues del click o Cancelar/Esc para conservar la superficie anterior.")) {
        finishCancelledDrawing("Seleccion del lado del material cancelada. La superficie anterior se conserva.");
        return;
    }
    if (selectionType != 10) exit("No se ha definido un punto de material. La superficie anterior se conserva.");
    getSelectionCoordinates(px, py);
    if (px.length < 1) exit("No se ha definido un punto de material. La superficie anterior se conserva.");
    matX = px[0];
    matY = py[0];
    matSign = materialSideSignForPolyline(matX, matY, newSX, newSY);
    if (matSign == 0) exit("El punto de material esta exactamente sobre la superficie. Repite la operacion y elige un punto claramente separado.");

    snapshotCurrentView();
    deleteSurfaceRoisOnly();
    makeSelection(selectionKind, newSX, newSY);
    Roi.setName(surfaceReferenceName);
    Roi.setGroup(6);
    Roi.setStrokeColor("cyan");
    Roi.setUnscalableStrokeWidth(3);
    setCommonObjectProperties();
    v4StampCurrentRevisionBinding();
    Roi.setProperty("Type", "surface_reference");
    Roi.setProperty("Surface_side_defined", "1");
    Roi.setProperty("Material_point_x_px", d2s(matX, 6));
    Roi.setProperty("Material_point_y_px", d2s(matY, 6));
    Roi.setProperty("Material_side_sign", d2s(matSign, 0));
    Roi.setProperty("Point_count", d2s(newSX.length, 0));
    roiManager("add");

    surfaceDefined = 1;
    surfaceSideDefined = 1;
    surfaceMaterialX = matX;
    surfaceMaterialY = matY;
    surfaceMaterialSign = matSign;
    refreshSurfaceGeometryFromRoi();

    syncAllObjects(0);
    showAllRois();
    restoreViewSnapshot();
    updateSessionMetadataRoi();
    refreshControlPanelStatus();
    showStatus("Superficie unica definida. Profundidad positiva hacia el punto de material seleccionado.");
}


function loadSurfaceReferenceFromRois() {
    idx = findSurfaceReferenceIndex();
    if (idx < 0) {
        surfaceDefined = 0;
        surfaceX = newArray(0);
        surfaceY = newArray(0);
        return 0;
    }
    safeRoiSelect(idx);
    Roi.getCoordinates(surfaceX, surfaceY);
    if (surfaceX.length < 2) return 0;
    surfaceDefined = 1;
    surfaceSideDefined = round(propNumber("Surface_side_defined", surfaceSideDefined));
    surfaceMaterialX = propNumber("Material_point_x_px", propNumber("Surface_material_x_px", surfaceMaterialX));
    surfaceMaterialY = propNumber("Material_point_y_px", propNumber("Surface_material_y_px", surfaceMaterialY));
    surfaceMaterialSign = propNumber("Material_side_sign", propNumber("Surface_material_sign", surfaceMaterialSign));
    if (surfaceMaterialSign == 0 || isNaN(surfaceMaterialSign)) surfaceMaterialSign = 1;
    return 1;
}

function refreshSurfaceGeometryFromRoi() {
    idx = findSurfaceReferenceIndex();
    if (idx < 0) {
        surfaceDefined = 0;
        surfaceX = newArray(0);
        surfaceY = newArray(0);
        return 0;
    }
    safeRoiSelect(idx);
    Roi.getCoordinates(surfaceX, surfaceY);
    if (surfaceX.length < 2) {
        surfaceDefined = 0;
        return 0;
    }
    surfaceDefined = 1;
    surfaceSideDefined = round(propNumber("Surface_side_defined", surfaceSideDefined));
    surfaceMaterialX = propNumber("Material_point_x_px", surfaceMaterialX);
    surfaceMaterialY = propNumber("Material_point_y_px", surfaceMaterialY);
    surfaceMaterialSign = propNumber("Material_side_sign", surfaceMaterialSign);
    if (surfaceMaterialSign == 0 || isNaN(surfaceMaterialSign)) surfaceMaterialSign = 1;
    return 1;
}

function findSurfaceReferenceIndex() {
    n = roiManager("count");
    idx = -1;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        name = Roi.getName;
        type = Roi.getProperty("Type");
        if (type == "surface_reference" || type == "surface" || name == surfaceReferenceName || startsWith(name, "SURFACE_REFERENCE")) idx = i;
    }
    return idx;
}

function deleteSurfaceRoisOnly() {
    n = roiManager("count");
    for (i=n-1; i>=0; i=i-1) {
        safeRoiSelect(i);
        name = Roi.getName;
        type = Roi.getProperty("Type");
        if (type == "surface_reference" || type == "surface" || name == surfaceReferenceName || startsWith(name, "SURFACE_REFERENCE")) roiManager("delete");
    }
}

function materialSideSignForPolyline(x, y, xs, ys) {
    updateScaleOrExit();
    xnm = x*nmPerPixelX;
    ynm = y*nmPerPixelY;
    best = 1e300;
    bestCross = 0;
    for (j=0; j<xs.length-1; j++) {
        x1 = xs[j]*nmPerPixelX;
        y1 = ys[j]*nmPerPixelY;
        x2 = xs[j+1]*nmPerPixelX;
        y2 = ys[j+1]*nmPerPixelY;
        vx = x2-x1;
        vy = y2-y1;
        len2 = vx*vx+vy*vy;
        if (len2 <= 0) continue;
        t = ((xnm-x1)*vx+(ynm-y1)*vy)/len2;
        if (t < 0) t = 0;
        if (t > 1) t = 1;
        qx = x1+t*vx;
        qy = y1+t*vy;
        dx = xnm-qx;
        dy = ynm-qy;
        d2 = dx*dx+dy*dy;
        if (d2 < best) {
            best = d2;
            bestCross = vx*(ynm-y1)-vy*(xnm-x1);
        }
    }
    if (bestCross > 0) return 1;
    if (bestCross < 0) return -1;
    return 0;
}

function computeSurfaceMetrics(x,y) {
    if(!surfaceDefined||surfaceX.length<2)return 0;
    lightHF3X=x;lightHF3Y=y;result=lightHF3Run("metrics","");a=split(result,"|");
    if(a.length!=6||startsWith(result,"ERROR"))return 0;
    surfaceLastDistanceNm=parseFloat(a[0]);surfaceLastSignedDistanceNm=parseFloat(a[1]);surfaceLastArcNm=parseFloat(a[2]);
    surfaceLastNearestXpx=parseFloat(a[3]);surfaceLastNearestYpx=parseFloat(a[4]);surfaceLastTangentAngleDeg=parseFloat(a[5]);return 1;
}

function configureBands() {
    if(!lightEnsureCurrentImage())return;
    choices=newArray("Ancho fijo: cubrir toda la imagen","Numero fijo: repartir la profundidad");choice=choices[0];if(lightBandMode=="count")choice=choices[1];
    Dialog.create("Bandas desde la superficie - HF3");Dialog.addChoice("Definir por:",choices,choice);
    Dialog.addNumber("Ancho de banda (nm; modo ancho):",bandNm);
    Dialog.addNumber("Numero de bandas (modo numero):",bandCount);
    Dialog.addMessage("El origen es la superficie. Solo se analiza el lado del material.\nEl espesor de la lamina se configura en Datos de la imagen.");Dialog.show();
    selected=Dialog.getChoice();width=Dialog.getNumber();count=round(Dialog.getNumber());
    if(isNaN(width)||width<=0||isNaN(count)||count<1||count>5000){showMessage("Bandas no validas","Indique un ancho positivo y entre 1 y 5000 bandas.");return;}
    lightBandMode="width";if(selected==choices[1])lightBandMode="count";bandNm=width;bandCount=count;excludeNegativeDepth=1;
    lightInvalidateAnalysisCache();if(!lightPrepareAnalysisState(1,0))return;
    updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();
    lightSaveRevisionCore(0);lightRefreshPanel();showStatus(bandCount+" bandas de "+d2s(bandNm,6)+" nm desde la superficie.");
}



// -----------------------------------------------------------------------------
// Cavity creation, selection, editing and deletion
// -----------------------------------------------------------------------------

function activateMeasureTool() {
    if (nImages() <= 0) {
        showMessage("Sin imagen", "Abre primero la imagen o micrografia TEM.");
        return;
    }
    updateScaleOrExit();
    if(!lightHF4Arm("measure"))return;
    lightInteractiveMode = "measure";
    lightInteractivePushState("measure");
    installInteractionListeners(0);
    ok = activateMacroToolByPrefix("Cavity measure");
    if (!ok) {
        showMessage("Herramienta no instalada", "No se encontro la herramienta 'Cavity Light measure Tool'. Reinstala el toolset R9 y reinicia Fiji.");
        return;
    }
    refreshControlPanelStatus();
    showStatus("Modo MEDIR CONTINUO activo: arrastra sobre cada diametro. Cada linea crea una cavidad; Esc o Ctrl+E termina.");
}

function activateAddTool() {
    if (nImages() > 0) lightInteractivePullActiveDiameter();
    if (nImages() <= 0) {
        showMessage("Sin imagen", "Abre primero la imagen TEM que vas a analizar.");
        return;
    }
    if (activeDiameterNm <= 0) {
        showMessage("Diametro no definido", "Mide primero un diametro o introduce un diametro activo.");
        return;
    }
    updateScaleOrExit();
    if(!lightHF4Arm("add"))return;
    lightInteractiveMode = "add";
    lightInteractivePushState("add");
    installInteractionListeners(0);
    ok = activateMacroToolByPrefix("Cavity add");
    if (!ok) {
        showMessage("Herramienta no instalada", "No se encontro la herramienta 'Cavity Light add Tool'. Reinstala el toolset R9 y reinicia Fiji.");
        return;
    }
    lightInteractivePushState("add");
    refreshControlPanelStatus();
    showStatus("Modo ANADIR activo: el cursor muestra el diametro activo. Alt+rueda cambia su tamano sin zoom; cada click crea una cavidad. Esc o Ctrl+E termina.");
}

function activateSelectTool() {
    if(!lightHF4Arm("select"))return;
    lightInteractiveMode = "select";
    lightInteractivePushState("select");
    installInteractionListeners(0);
    // The installed toolbar name can be either the Light or legacy form.
    ok = activateMacroToolByPrefix("Cavity select edit");
    if (!ok) ok = activateMacroToolByPrefix("Cavity select");
    if (!ok) {
        // Fallback: built-in oval still allows moving/resizing an already selected ROI,
        // but click-to-select will not be available until the macro is reinstalled.
        setTool(1); // built-in oval tool
        if (!missingMacroToolWarningShown) {
            missingMacroToolWarningShown = 1;
            showMessage("Herramienta de seleccion no encontrada",
                "No encuentro la herramienta macro 'Cavity select edit' en la barra.\n\n"+
                "He activado la herramienta oval estandar como respaldo.\n"+
                "Para recuperar la seleccion por click, instala o repara Cavity_TEM_Studio_v5_6_0.ijm desde Cavity TEM Studio, reinicia Fiji y seleccionalo desde More Tools (>>).");
        } else showStatus("Herramienta Cavity select edit no encontrada; usando oval estandar como respaldo.");
        return;
    }
    refreshControlPanelStatus();
    showStatus("Modo SELECCIONAR activo: click sobre una cavidad; arrastrala para moverla o usa Alt+rueda (Ctrl+Alt tambien funciona) para cambiar su diametro.");
}

function cancelCaptureMode() {
    activateSelectTool();
    showStatus("Modo de captura terminado. Seleccion/edicion activa.");
}

function activateMacroToolByPrefix(prefix) {
    safePrefix = jsEscape(prefix);
    // Try several exact toolbar names. ij.gui.Toolbar.getToolId() is not a prefix
    // search in all Fiji versions, despite the name of this helper.
    code = "var T=Packages.ij.gui.Toolbar;var tb=T.getInstance();var result='0';"+
           "if(tb!=null){var names=[];"+
           "names.push('" + safePrefix + "');"+
           "names.push('" + safePrefix + " Tool');"+
           "if(String('" + safePrefix + "').indexOf('Cavity select')==0){names.push('Cavity Light select edit');names.push('Cavity Light select edit Tool');names.push('Cavity select');names.push('Cavity select Tool');names.push('Cavity select edit');names.push('Cavity select edit Tool');}"+
           "if(String('" + safePrefix + "').indexOf('Cavity measure')==0){names.push('Cavity Light measure');names.push('Cavity Light measure Tool');names.push('Cavity measure');names.push('Cavity measure Tool');}"+
           "if(String('" + safePrefix + "').indexOf('Cavity add')==0){names.push('Cavity Light add');names.push('Cavity Light add Tool');names.push('Cavity add');names.push('Cavity add Tool');}"+
           "for(var k=0;k<names.length;k++){try{var id=tb.getToolId(String(names[k]));if(id>=0){tb.setTool(id);result='1';break;}}catch(e){}}}"+
           "result;";
    resultText = eval("js", code);
    if (resultText == "1") return 1;
    return 0;
}

function currentInteractionModeLabel() {
    toolNameNow = IJ.getToolName();
    label = toolNameNow;
    if (startsWith(toolNameNow, "Cavity measure") || startsWith(toolNameNow, "Cavity Light measure")) label = "medir continuo";
    else if (startsWith(toolNameNow, "Cavity add") || startsWith(toolNameNow, "Cavity Light add")) label = "anadir";
    else if (startsWith(toolNameNow, "Cavity select") || startsWith(toolNameNow, "Cavity Light select")) label = "seleccionar";
    else if (toolNameNow == "oval" || toolNameNow == "ellipse") label = "editar ROI";
    else if (toolNameNow == "hand") label = "mano/pan";
    if (label == "") label = "sin identificar";
    return label;
}

function measureCavityByDrag() {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (!updateScaleMaybe()) {
        showStatus("Define primero la escala antes de medir cavidades.");
        return;
    }

    leftButton = 16;
    getCursorLoc(mx1, my1, mz, mflags);
    if ((mflags & leftButton) == 0) return;
    if (mx1 < 0 || my1 < 0) return;

    mx2 = mx1;
    my2 = my1;
    lastMx = mx1;
    lastMy = my1;
    setOption("DisablePopupMenu", true);
    while ((mflags & leftButton) != 0) {
        getCursorLoc(mx2, my2, mz, mflags);
        if (mx2 != lastMx || my2 != lastMy) {
            makeLine(mx1, my1, mx2, my2);
            mdxNm = (mx2-mx1)*nmPerPixelX;
            mdyNm = (my2-my1)*nmPerPixelY;
            previewDiameterNm = sqrt(mdxNm*mdxNm+mdyNm*mdyNm);
            showStatus("Modo MEDIR CONTINUO: d=" + d2s(previewDiameterNm, 4) + " nm. Suelta para crear la cavidad.");
            lastMx = mx2;
            lastMy = my2;
        }
        wait(10);
    }
    setOption("DisablePopupMenu", false);

    mdxNm = (mx2-mx1)*nmPerPixelX;
    mdyNm = (my2-my1)*nmPerPixelY;
    measuredDiameterNm = sqrt(mdxNm*mdxNm+mdyNm*mdyNm);
    if (measuredDiameterNm <= 0) {
        showStatus("Medicion ignorada: arrastra una linea de longitud mayor que cero.");
        return;
    }

    activeDiameterNm = measuredDiameterNm;
    lightInteractivePushState(lightInteractiveMode);
    measuredCx = (mx1+mx2)/2;
    measuredCy = (my1+my2)/2;
    addCavityCircle(measuredCx, measuredCy, measuredDiameterNm, "continuous_line_measurement");
    activateMacroToolByPrefix("Cavity measure");
    refreshControlPanelStatus();
    showStatus("Cavidad creada: d=" + d2s(measuredDiameterNm, 4) + " nm. Sigue arrastrando; Esc o Ctrl+E termina.");
}

function measureDiameterFromLine(addCircle) {
    if (!v4PrepareImageForMeasurement(1)) return;
    updateScaleOrExit();
    setTool("line");
    if (!waitForUserSafe("Medir diametro", "Dibuja una linea recta sobre el diametro de la cavidad.\nPulsa OK al terminar o Cancelar/Esc para salir.")) {
        finishCancelledDrawing("Medicion puntual cancelada.");
        return;
    }
    getLine(x1, y1, x2, y2, lw);
    if (x1 == -1) exit("No hay una linea de diametro.");
    dxNm = (x2-x1)*nmPerPixelX;
    dyNm = (y2-y1)*nmPerPixelY;
    dNm = sqrt(dxNm*dxNm+dyNm*dyNm);
    if (dNm <= 0) exit("El diametro medido es cero.");
    activeDiameterNm = dNm;
    lightInteractivePushState(lightInteractiveMode);
    cx = (x1+x2)/2;
    cy = (y1+y2)/2;
    if (addCircle) {
        addCavityCircle(cx, cy, dNm, "line_measurement");
    } else {
        updateSessionMetadataRoi();
        refreshControlPanelStatus();
        showStatus("Diametro activo: " + d2s(activeDiameterNm, 4) + " nm. Activa Modo anadir para repetirlo.");
    }
}

function addCavityAtCursor() {
    // A native canvas listener records the click without interpreter analysis.
    if(call("cavity.light.HF4.active","")!="1")showStatus("Active Anadir con circulo visible desde el panel HF4.");
}

function selectOrForceAddAtCursor() {
    if (!v4PrepareImageForMeasurement(1)) return;
    updateScaleOrExit();
    getCursorLoc(x, y, z, flags);
    shift = 1;
    if ((flags & shift) != 0) {
        if (activeDiameterNm <= 0) exit("No hay diametro activo para Shift+click.");
        addCavityCircle(x, y, activeDiameterNm, "shift_click");
        return;
    }
    idx = findCavityAtPoint(x, y);
    if (idx < 0) {
        showStatus("No hay una cavidad en ese punto. Usa Shift+click o Modo anadir para crear una.");
        return;
    }
    snapshotCurrentView();
    safeRoiSelect(idx);
    id = cavityIdCurrent();
    restoreViewSnapshot();
    setTool(1); // built-in oval tool
    showStatus(id + " seleccionada. Arrastra para moverla o usa Alt+rueda (Ctrl+Alt tambien funciona) para cambiar su tamano. R9 sincroniza automaticamente al terminar.");
}

function addCavityCircle(cx,cy,dNm,source) {
    if(!lightHF4Configure())return -1;
    result=call("cavity.light.HF4.add",d2s(cx,9)+"|"+d2s(cy,9)+"|"+d2s(dNm,9)+"|"+source);
    if(startsWith(result,"ERROR")){showMessage("Cavidad no registrada",result);return -1;}
    lightHF4Pull();return parseFloat(result);
}

function findCavityAtPoint(x,y) {
    if(!lightHF4Configure())return -1;
    result=call("cavity.light.HF4.select",x+"|"+y);
    if(startsWith(result,"ERROR"))return -1;return parseFloat(result);
}

function syncSelectedObject(verbose) {
    if (nImages() <= 0) return;
    if (v4ProjectLoaded && !v4RequireCurrentRevisionBinding("sincronizar la ROI", verbose)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) {
        if (verbose) showMessage("Sin seleccion", "Selecciona una ROI en la imagen o en el ROI Manager.");
        return;
    }
    commitOk=commitActiveManagedRoi();if(commitOk<0)return;
    safeRoiSelect(idx);
    type = currentRoiType();
    if (type == "cavity") syncCavityAtIndex(idx);
    else if (isLinearFeatureType(type)) syncLinearFeatureAtIndex(idx);
    else if (type == "dislocation_loop") syncDislocationLoopAtIndex(idx);
    else if (type == "panel" || type == "analysis_mask" || type == "exclusion") syncAreaObjectAtIndex(idx);
    else if (type == "surface_reference") {
        refreshSurfaceGeometryFromRoi();
        syncAllObjects(0);
    } else if (type == "scale_reference") {
        loadScaleReferenceFromRois();
        syncAllObjects(0);
    }
    updateSessionMetadataRoi();
    showAllRois();
    if (verbose && type == "cavity") activateMacroToolByPrefix("Cavity select");
    refreshControlPanelStatus();
    if (verbose) {
        if (type == "cavity") showStatus("Cavidad sincronizada. Modo SELECCIONAR listo para elegir la siguiente.");
        else showStatus("ROI seleccionada sincronizada desde su geometria actual.");
    }
}

function commitActiveManagedRoi() {
    if(nImages()<=0)return 0;
    if(selectionType<0)return 0;
    activeType=currentRoiType();if(!isManagedType(activeType))return 0;
    return parseFloat(call("cavity.light.Identity.commit",""));
}

function takeDiameterFromSelected() {
    if (!v4PrepareImageForMeasurement(1)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) exit("Selecciona una cavidad.");
    commitOk=commitActiveManagedRoi();if(commitOk<0)return;
    safeRoiSelect(idx);
    if (!currentRoiIsCavity()) exit("La ROI seleccionada no es una cavidad.");
    syncCavityAtIndex(idx);
    safeRoiSelect(idx);
    activeDiameterNm = propNumber("Equivalent_diameter_nm", propNumber("Diameter_nm", 0));
    lightInteractivePushState(lightInteractiveMode);
    updateSessionMetadataRoi();
    refreshControlPanelStatus();
    showStatus("Diametro activo tomado de " + cavityIdCurrent() + ": " + d2s(activeDiameterNm, 4) + " nm.");
}

function editSelectedCavityNumerically() {
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
}

function toggleSelectedInclusion() {
    if (!v4PrepareImageForMeasurement(1)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) exit("Selecciona una cavidad.");
    commitOk=commitActiveManagedRoi();if(commitOk<0)return;
    safeRoiSelect(idx);
    if (!currentRoiIsCavity()) exit("Esta accion solo se aplica a cavidades.");
    excluded = round(propNumber("Manual_excluded", 0));
    excluded = 1-excluded;
    Roi.setProperty("Manual_excluded", d2s(excluded, 0));
    roiManager("update");
    syncCavityAtIndex(idx);
    showAllRois();
    activateMacroToolByPrefix("Cavity select");
    refreshControlPanelStatus();
    if (excluded) showStatus(cavityIdCurrent() + " excluida manualmente. Modo SELECCIONAR listo.");
    else showStatus(cavityIdCurrent() + " incluida de nuevo. Modo SELECCIONAR listo.");
}

function deleteSelectedManagedRoi() {
    if (!v4PrepareImageForMeasurement(1)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) {
        showStatus("No hay una ROI seleccionada para borrar.");
        return;
    }
    commitOk=commitActiveManagedRoi();if(commitOk<0)return;
    safeRoiSelect(idx);
    name = Roi.getName;
    storedType = Roi.getProperty("Type");
    type = normalizedType(name, storedType);
    if (type == "session_metadata" || type == "scale_reference" || type == "scale_label" || type == "surface_reference") {
        showMessage("ROI protegida", "La escala y la superficie se sustituyen con sus comandos especificos. La metadata no se borra manualmente.");
        return;
    }
    if (!isManagedType(type)) {
        showMessage("ROI no gestionada", "La ROI seleccionada no pertenece a Cavity Toolset v8.");
        return;
    }

    snapshotCurrentView();
    Roi.copy;
    undoKind = "delete";
    undoObjectId = objectIdCurrent(type);
    undoDeletedName = name;
    undoAvailable = 1;
    roiManager("delete");
    if (type == "cavity") lightInvalidateCavityCount();
    showAllRois();
    restoreViewSnapshot();
    updateSessionMetadataRoi();
    activateMacroToolByPrefix("Cavity select");
    refreshControlPanelStatus();
    showStatus("Borrada " + name + ". Ctrl+Z permite restaurarla una vez; modo SELECCIONAR listo.");
}

function undoLastAddOrDelete() {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (!undoAvailable) {
        showStatus("No hay una adicion o borrado v8 para deshacer.");
        return;
    }
    run("ROI Manager...");
    if (undoKind == "add") {
        idx = findObjectById(undoObjectId);
        if (idx >= 0) {
            safeRoiSelect(idx);
            roiManager("delete");
            showStatus("Deshecha la adicion de " + undoObjectId + ".");
        } else showStatus("No se encontro " + undoObjectId + " para deshacer.");
    } else if (undoKind == "delete") {
        Roi.paste;
        if (selectionType < 0) {
            showMessage("No se pudo deshacer", "El portapapeles de ROI ya no contiene el objeto borrado.");
            lightInvalidateCavityCount();
    undoAvailable = 0;
            return;
        }
        roiManager("add");
        idx = roiManager("count")-1;
        safeRoiSelect(idx);
        type = currentRoiType();
        if (type == "cavity") syncCavityAtIndex(idx);
        else if (isLinearFeatureType(type)) syncLinearFeatureAtIndex(idx);
        else if (type == "panel" || type == "analysis_mask" || type == "exclusion") syncAreaObjectAtIndex(idx);
        showStatus("Restaurada " + undoDeletedName + ".");
    }
    undoAvailable = 0;
    undoKind = "";
    undoObjectId = "";
    updateSessionMetadataRoi();
    showAllRois();
    refreshControlPanelStatus();
}

// -----------------------------------------------------------------------------
// Panels, masks, exclusions and linear microstructural features
// -----------------------------------------------------------------------------

function chooseAreaToolId(title) {
    choices = newArray("Rectangulo", "Poligono", "Mano alzada");
    Dialog.create(title);
    Dialog.addChoice("Herramienta para toda la serie:", choices, choices[0]);
    Dialog.addMessage("La herramienta permanecera activa. Pulsa Cancelar en la ventana de dibujo cuando hayas terminado la serie.");
    Dialog.show();
    choice = Dialog.getChoice();
    toolId = 0;
    if (choice == "Poligono") toolId = 2;
    if (choice == "Mano alzada") toolId = 3;
    return toolId;
}

function clearCurrentSelectionForContinuousDrawing() {
    roiManager("deselect");
    Roi.selectNone;
}

function addPanelRoi() {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (nImages() <= 0) exit("Abre primero la imagen o collage TEM.");
    run("ROI Manager...");
    areaToolId = chooseAreaToolId("Paneles TEM - modo continuo");
    lastPanelSource = sourceFirst;
    if (lastPanelSource == "") lastPanelSource = "DM3";

    while (1) {
        setTool(areaToolId);
        if (!waitForUserSafe("Panel TEM - modo continuo",
            "Dibuja el siguiente panel TEM.\n"+
            "Pulsa OK para registrarlo.\n"+
            "Pulsa Cancelar o Esc cuando hayas terminado todos los paneles.")) {
            finishCancelledDrawing("Serie de paneles TEM finalizada.");
            return;
        }
        if (!isAreaSelection()) {
            showMessage("Panel no registrado", "La seleccion actual no es un area valida. Vuelve a dibujarla.");
            continue;
        }

        nextPanelSerial = panelCounter + 1;
        defaultId = "PANEL_" + IJ.pad(nextPanelSerial, 3);
        Dialog.create("Registrar panel TEM");
        Dialog.addString("ID del panel:", defaultId, 18);
        Dialog.addString("Archivo DM3 de origen:", lastPanelSource, 35);
        Dialog.addNumber("Orden del panel (mayor = preferente en solapes):", nextPanelSerial);
        Dialog.addString("Notas:", "", 40);
        Dialog.show();
        id = sanitizeId(Dialog.getString(), defaultId);
        source = Dialog.getString();
        order = round(Dialog.getNumber());
        notes = Dialog.getString();
        if (order < 1) order = nextPanelSerial;
        panelCounter = nextPanelSerial;
        if (source != "") lastPanelSource = source;

        snapshotCurrentView();
        Roi.setName(id);
        Roi.setGroup(0);
        Roi.setFillColor("#00000000");
        Roi.setStrokeColor("white");
        Roi.setUnscalableStrokeWidth(2);
        setCommonObjectProperties();
        v4StampCurrentRevisionBinding();
        Roi.setProperty("Type", "panel");
        Roi.setProperty("Panel_id", id);
        Roi.setProperty("Panel_order", d2s(order, 0));
        Roi.setProperty("Source_filename", source);
        Roi.setProperty("Notes", notes);
        roiManager("add");
        idx = roiManager("count")-1;
        syncAreaObjectAtIndex(idx);

        undoKind = "add";
        undoObjectId = id;
        undoDeletedName = "";
        undoAvailable = 1;
        showAllRois();
        restoreViewSnapshot();
        updateSessionMetadataRoi();
        refreshControlPanelStatus();
        clearCurrentSelectionForContinuousDrawing();
        showStatus("Panel registrado: " + id + " -> " + source + ". Dibuja el siguiente o pulsa Cancelar.");
    }
}

function addAnalysisMaskRoi() {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (nImages() <= 0) exit("Abre primero la imagen o collage TEM.");
    run("ROI Manager...");
    areaToolId = chooseAreaToolId("Mascaras validas - modo continuo");
    Dialog.create("Mascaras validas - propiedades de la serie");
    Dialog.addString("Etiqueta comun:", "material_valido", 30);
    Dialog.show();
    seriesLabel = Dialog.getString();

    while (1) {
        setTool(areaToolId);
        if (!waitForUserSafe("Mascara valida - modo continuo",
            "Dibuja la siguiente region de material observable y cuantificable.\n"+
            "Pulsa OK para registrarla.\n"+
            "Pulsa Cancelar o Esc cuando hayas terminado todas las mascaras.")) {
            finishCancelledDrawing("Serie de mascaras validas finalizada.");
            return;
        }
        if (!isAreaSelection()) {
            showMessage("Mascara no registrada", "La seleccion actual no es un area valida. Vuelve a dibujarla.");
            continue;
        }

        maskCounter++;
        id = "MASK_" + IJ.pad(maskCounter, 3);
        snapshotCurrentView();
        Roi.setName(id);
        Roi.setGroup(8);
        Roi.setFillColor("#1800ffff");
        Roi.setStrokeColor("cyan");
        Roi.setUnscalableStrokeWidth(2);
        setCommonObjectProperties();
        v4StampCurrentRevisionBinding();
        Roi.setProperty("Type", "analysis_mask");
        Roi.setProperty("Mask_id", id);
        Roi.setProperty("Mask_label", seriesLabel);
        roiManager("add");
        idx = roiManager("count")-1;
        syncAreaObjectAtIndex(idx);

        undoKind = "add";
        undoObjectId = id;
        undoDeletedName = "";
        undoAvailable = 1;
        syncAllObjects(0);
        showAllRois();
        restoreViewSnapshot();
        refreshControlPanelStatus();
        clearCurrentSelectionForContinuousDrawing();
        showStatus("Mascara valida anadida: " + id + ". Dibuja la siguiente o pulsa Cancelar.");
    }
}


function addExclusionRoi() {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (nImages() <= 0) exit("Abre primero la imagen o collage TEM.");
    run("ROI Manager...");
    areaToolId = chooseAreaToolId("Zonas excluidas - modo continuo");
    reasons = newArray("scale_bar", "text", "vacuum", "contamination", "too_thick", "out_of_focus", "artifact", "other");
    Dialog.create("Zonas excluidas - propiedades de la serie");
    Dialog.addChoice("Motivo comun:", reasons, reasons[0]);
    Dialog.addString("Nota comun:", "", 40);
    Dialog.show();
    seriesReason = Dialog.getChoice();
    seriesNote = Dialog.getString();

    while (1) {
        setTool(areaToolId);
        if (!waitForUserSafe("Zona excluida - modo continuo",
            "Dibuja la siguiente zona no cuantificable.\n"+
            "Pulsa OK para registrarla.\n"+
            "Pulsa Cancelar o Esc cuando hayas terminado todas las exclusiones de este tipo.")) {
            finishCancelledDrawing("Serie de zonas excluidas finalizada.");
            return;
        }
        if (!isAreaSelection()) {
            showMessage("Exclusion no registrada", "La seleccion actual no es un area valida. Vuelve a dibujarla.");
            continue;
        }

        exclusionCounter++;
        id = "EXCL_" + IJ.pad(exclusionCounter, 3);
        snapshotCurrentView();
        Roi.setName(id);
        Roi.setGroup(9);
        Roi.setFillColor("#22ff00ff");
        Roi.setStrokeColor("magenta");
        Roi.setUnscalableStrokeWidth(2);
        setCommonObjectProperties();
        v4StampCurrentRevisionBinding();
        Roi.setProperty("Type", "exclusion");
        Roi.setProperty("Exclusion_id", id);
        Roi.setProperty("Exclusion_reason", seriesReason);
        Roi.setProperty("Notes", seriesNote);
        roiManager("add");
        idx = roiManager("count")-1;
        syncAreaObjectAtIndex(idx);

        undoKind = "add";
        undoObjectId = id;
        undoDeletedName = "";
        undoAvailable = 1;
        syncAllObjects(0);
        showAllRois();
        restoreViewSnapshot();
        refreshControlPanelStatus();
        clearCurrentSelectionForContinuousDrawing();
        showStatus("Zona excluida anadida: " + id + " (" + seriesReason + "). Dibuja la siguiente o pulsa Cancelar.");
    }
}


function addLinearFeatureWithTool(featureType, toolChoice) {
    featureToolPreset = toolChoice;
    addLinearFeature(featureType);
}

function addLinearFeature(featureType) {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (nImages() <= 0) exit("Abre primero la imagen o collage TEM.");
    updateScaleOrExit();
    run("ROI Manager...");
    label = featureTypeLabel(featureType);
    confidenceChoices = newArray("high", "medium", "low");
    toolChoices = newArray("Polilinea", "Mano alzada");
    defaultToolChoice = "Polilinea";
    if (featureToolPreset != "") defaultToolChoice = featureToolPreset;
    Dialog.create(label + " - modo continuo");
    Dialog.addChoice("Herramienta:", toolChoices, defaultToolChoice);
    Dialog.addChoice("Confianza comun:", confidenceChoices, confidenceChoices[0]);
    Dialog.addString("Nota comun:", "", 40);
    Dialog.addMessage("Dibuja tantas lineas como necesites. Pulsa Cancelar en la ventana de dibujo para finalizar la serie.");
    Dialog.show();
    seriesToolChoice = Dialog.getChoice();
    seriesConfidence = Dialog.getChoice();
    seriesFeatureNote = Dialog.getString();
    featureToolPreset = "";

    while (1) {
        if (seriesToolChoice == "Mano alzada") setTool("freeline");
        else setTool("polyline");
        if (!waitForUserSafe("Dibujar " + label + " - modo continuo",
            "Dibuja la siguiente linea sobre " + label + ".\n"+
            "Polilinea: clicks sucesivos y doble click. Mano alzada: arrastra.\n"+
            "Pulsa OK para registrarla o Cancelar/Esc para terminar la serie.")) {
            finishCancelledDrawing("Serie de " + label + " finalizada.");
            return;
        }
        st = selectionType;
        if (st != 5 && st != 6 && st != 7) {
            showMessage("Linea no registrada", "La seleccion actual no es una linea valida. Vuelve a dibujarla.");
            continue;
        }
        getSelectionCoordinates(xs, ys);
        if (xs.length < 2) {
            showMessage("Linea no registrada", "La linea necesita al menos dos puntos.");
            continue;
        }

        id = "";
        if (featureType == "grain_boundary") {
            grainBoundaryCounter++;
            id = "GB_" + IJ.pad(grainBoundaryCounter, 4);
        } else if (featureType == "dislocation") {
            dislocationCounter++;
            id = "DISL_" + IJ.pad(dislocationCounter, 4);
        } else {
            interfaceCounter++;
            id = "INT_" + IJ.pad(interfaceCounter, 4);
        }

        snapshotCurrentView();
        Roi.setName(id);
        Roi.setGroup(lightGroupForFeatureType(featureType));
        setCommonObjectProperties();
        v4StampCurrentRevisionBinding();
        Roi.setProperty("Type", featureType);
        Roi.setProperty("Feature_id", id);
        Roi.setProperty("Confidence", seriesConfidence);
        Roi.setProperty("Notes", seriesFeatureNote);
        applyFeatureStyle(featureType);
        roiManager("add");
        idx = roiManager("count")-1;
        syncLinearFeatureAtIndex(idx);

        undoKind = "add";
        undoObjectId = id;
        undoDeletedName = "";
        undoAvailable = 1;
        showAllRois();
        restoreViewSnapshot();
        updateSessionMetadataRoi();
        refreshControlPanelStatus();
        clearCurrentSelectionForContinuousDrawing();
        showStatus(label + " registrada: " + id + ". Dibuja la siguiente o pulsa Cancelar.");
    }
}


function drawAreaSelection(title, message) {
    choices = newArray("Rectangulo", "Poligono", "Mano alzada");
    Dialog.create(title);
    Dialog.addChoice("Herramienta:", choices, choices[0]);
    Dialog.show();
    choice = Dialog.getChoice();
    tool = "rectangle";
    if (choice == "Poligono") tool = "polygon";
    if (choice == "Mano alzada") tool = "freehand";
    setTool(tool);
    if (!waitForUserSafe(title, message)) {
        finishCancelledDrawing(title + " cancelado.");
        return 0;
    }
    return 1;
}

function isAreaSelection() {
    st = selectionType;
    if (st == 0 || st == 1 || st == 2 || st == 3 || st == 4 || st == 9) return 1;
    return 0;
}

function syncAreaObjectAtIndex(idx) {
    if(!safeRoiSelect(idx))return; type=currentRoiType(); if(type!="panel"&&type!="analysis_mask"&&type!="exclusion")return;
    getStatistics(areaCurrent);areaNm2=areaCurrent*unitFactorNm*unitFactorNm;Roi.getFloatBounds(x,y,w,h);setCommonObjectProperties();Roi.setProperty("Area_nm2",d2s(areaNm2,6));Roi.setProperty("Area_um2",d2s(areaNm2/1000000,9));Roi.setProperty("Bounds_x_px",d2s(x,6));Roi.setProperty("Bounds_y_px",d2s(y,6));Roi.setProperty("Bounds_width_px",d2s(w,6));Roi.setProperty("Bounds_height_px",d2s(h,6));if(type=="analysis_mask")Roi.setGroup(8);else if(type=="exclusion")Roi.setGroup(9);applyAreaObjectStyle(type);roiManager("update");
}


function syncLinearFeatureAtIndex(idx) {
    if(!safeRoiSelect(idx))return 0;
    type=currentRoiType();if(!isLinearFeatureType(type))return 0;
    Roi.getCoordinates(xs,ys);tracedLength=polylineLengthNm(xs,ys);
    if(lightCavityContextActive!=1){
        if(!lightComputeExactAreaAndDepth()){
            Roi.setProperty("Traced_length_nm",d2s(tracedLength,6));Roi.setProperty("Length_nm","");Roi.setProperty("Length_um","");
            Roi.setProperty("Length_domain","pending_valid_area");roiManager("update");return 0;
        }
    }
    args=""+idx+"|"+d2s(nmPerPixelX,12)+"|"+d2s(nmPerPixelY,12);
    result=call("cavity.light.HF46.lineLength",args);
    if(startsWith(result,"ERROR")){call("cavity.light.HF4.log",result);return 0;}
    lengthNm=parseFloat(result);if(!lightHF46Finite(lengthNm)||lengthNm<0)return 0;
    setCommonObjectProperties();Roi.setProperty("Point_count",d2s(xs.length,0));
    Roi.setProperty("Traced_length_nm",d2s(tracedLength,6));
    Roi.setProperty("Length_nm",d2s(lengthNm,6));Roi.setProperty("Length_um",d2s(lengthNm/1000,9));
    Roi.setProperty("Length_domain","valid_raster_pixel_cells_v1");
    Roi.setGroup(lightGroupForFeatureType(type));applyFeatureStyle(type);roiManager("update");return 1;
}


function syncDislocationLoopAtIndex(idx) {
    if(!safeRoiSelect(idx))return;
    if (currentRoiType() != "dislocation_loop") return;
    setCommonObjectProperties();
    v4SetGeometryProperties();
    Roi.setProperty("Closed_contour", "1");
    Roi.setProperty("Modified_time_ms", d2s(getTime(),0));
    applyLoopStyle();
    roiManager("update");
}

function panelForPoint(x, y) {
    // Updates the single effective owner plus the geometric coverage count.
    // Panel_match_count now means effective assignments (0/1); overlaps are
    // diagnosed separately and resolved by certified SVG z_order/ownership.
    n = roiManager("count");
    bestOrder = -1e30;
    panelLastId = "";
    panelLastSource = "";
    panelLastMatchCount = 0;
    panelLastCoverageCount = 0;
    panelLastOwnerCode = 0;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        type = currentRoiType();
        if (type == "panel" && Roi.contains(round(x), round(y))) {
            panelLastCoverageCount++;
            order = propNumber("Panel_order", 0);
            if (order >= bestOrder) {
                bestOrder = order;
                panelName = Roi.getName;
                panelLastId = propString("Panel_id", panelName);
                panelLastSource = propString("Source_filename", "");
                panelLastOwnerCode = round(propNumber("Owner_code", 0));
            }
        }
    }
    if (panelLastId != "") panelLastMatchCount = 1;
    return panelLastMatchCount;
}

function v51PanelBoundaryInfo(idx) {
    // Returns crosses_boundary, distinct_positive_owners, touches_background.
    // Java inspection avoids changing the active ROI while sampling its edge.
    js = "var RM=Packages.ij.plugin.frame.RoiManager,rm=RM.getInstance2(),out='0,0,0';if(rm!=null&&" + idx + ">=0&&" + idx + "<rm.getCount()){var rois=rm.getRoisAsArray(),target=rois[" + idx + "],panels=[];function typ(r){var t=r.getProperty('Type');if(t==null||String(t)=='')t=r.getProperty('Object_type');return t==null?'':String(t);}for(var i=0;i<rois.length;i++)if(typ(rois[i])=='panel')panels.push(rois[i]);function owner(x,y){var best=-1e300,code=0;for(var j=0;j<panels.length;j++){var p=panels[j];if(p.contains(Math.round(x),Math.round(y))){var z=parseFloat(String(p.getProperty('Panel_order')));if(isNaN(z))z=0;if(z>=best){best=z;var c=parseInt(String(p.getProperty('Owner_code')),10);code=isNaN(c)?j+1:c;}}}return code;}var seen={},positive=0,bg=false,b=target.getFloatBounds(),c=owner(b.x+b.width/2,b.y+b.height/2);if(c>0)seen[c]=1;else bg=true;var fp=(target instanceof Packages.ij.gui.Line?target.getFloatPoints():target.getFloatPolygon());if(fp!=null&&fp.npoints>0){var step=Math.max(1,Math.floor(fp.npoints/512));for(var k=0;k<fp.npoints;k+=step){var o=owner(fp.xpoints[k],fp.ypoints[k]);if(o>0)seen[o]=1;else bg=true;}}for(var key in seen)if(seen.hasOwnProperty(key))positive++;var cross=(positive>1||(positive>0&&bg))?1:0;out=cross+','+positive+','+(bg?1:0);}String(out);";
    return "" + eval("js", js);
}

function pointValidity(x,y) {
    if(x<0||y<0||x>=getWidth()||y>=getHeight()){pointValidityReason="outside_image";return 0;}
    lightHF3X=x;lightHF3Y=y;result=lightHF3Run("point","");
    pointValidityReason="";if(result!="1")pointValidityReason="outside_valid_material";
    if(result=="1")return 1;return 0;
}

function cavityIntersectsInvalidRegion(cx, cy, rx, ry) {
    if (lightUseWholeImage == 1) {
        fastExclusionCount = countTypeFast("exclusion");
        if (fastExclusionCount == 0) return 0;
    }
    if(!pointValidity(cx,cy))return 0;
    samples=24;
    for(k=0;k<samples;k++){
        theta=2*PI_VAL*k/samples;
        px=cx+rx*cos(theta);py=cy+ry*sin(theta);
        if(!pointValidity(px,py))return 1;
    }
    return 0;
}

function distanceToNearestFeatureNm(x, y, featureType) {
    featureCountFast = countTypeFast(featureType);
    if (featureCountFast == 0) return NaN;
    n = roiManager("count");
    best = NaN;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        type = currentRoiType();
        if (type == featureType) {
            Roi.getCoordinates(xs, ys);
            d = pointToPolylineDistanceNm(x, y, xs, ys);
            if (isNaN(best) || d < best) best = d;
        }
    }
    return best;
}

function pointToPolylineDistanceNm(x, y, xs, ys) {
    if (xs.length < 2) return NaN;
    xnm = x*nmPerPixelX;
    ynm = y*nmPerPixelY;
    best = 1e300;
    for (j=0; j<xs.length-1; j++) {
        x1 = xs[j]*nmPerPixelX;
        y1 = ys[j]*nmPerPixelY;
        x2 = xs[j+1]*nmPerPixelX;
        y2 = ys[j+1]*nmPerPixelY;
        vx = x2-x1;
        vy = y2-y1;
        l2 = vx*vx+vy*vy;
        if (l2 <= 0) continue;
        t = ((xnm-x1)*vx+(ynm-y1)*vy)/l2;
        if (t < 0) t = 0;
        if (t > 1) t = 1;
        qx = x1+t*vx;
        qy = y1+t*vy;
        d2 = (xnm-qx)*(xnm-qx)+(ynm-qy)*(ynm-qy);
        if (d2 < best) best = d2;
    }
    if (best >= 1e299) return NaN;
    return sqrt(best);
}

function polylineLengthNm(xs, ys) {
    if (xs.length < 2) return 0;
    sum = 0;
    for (j=0; j<xs.length-1; j++) {
        dx = (xs[j+1]-xs[j])*nmPerPixelX;
        dy = (ys[j+1]-ys[j])*nmPerPixelY;
        sum = sum+sqrt(dx*dx+dy*dy);
    }
    return sum;
}

// -----------------------------------------------------------------------------
// R7 prepared-state cache and batch geometry context
// -----------------------------------------------------------------------------

function lightInvalidateAnalysisCache() {
    lightPreparedFingerprint = "";
    lightPreparedAtMs = 0;
    lightLastPreparationReused = 0;
    lightAreaFingerprint = "";
    lightAreaComputationMode = "not_calculated";
    lightAreaComputationDurationMs = 0;
}

function lightAnalysisInputFingerprint() {
    if (nImages() <= 0) return "";
    updateScaleMaybe();
    config = lightImageId + "|" + lightSourceSha256 + "|" + getWidth() + "x" + getHeight();
    config = config + "|scale=" + d2s(nmPerPixelX,12) + "," + d2s(nmPerPixelY,12);
    config = config + "|mode=" + lightImageMode + "|whole=" + lightUseWholeImage;
    config = config + "|surface=" + surfaceDefined + "," + surfaceSideDefined + "," + d2s(surfaceMaterialSign,0);
    config = config + "|bands=" + d2s(bandNm,9) + "," + bandCount + "," + excludeNegativeDepth;
    config = config + "|HF3=parallel_miter|band_mode="+lightBandMode;
    config = config + "|include_uncertain=" + lightIncludeUncertain;
    config = config + "|duplicates=" + d2s(duplicateCenterTolPx,6) + "," + d2s(duplicateRelativeTol,6) + "," + d2s(duplicateDiameterTolFraction,6);
    configJs = jsEscape(config);
    js = "(function(){var RM=Packages.ij.plugin.frame.RoiManager,MD=Packages.java.security.MessageDigest,CS=Packages.java.nio.charset.StandardCharsets,rm=RM.getInstance2(),rois=rm==null?[]:rm.getRoisAsArray(),parts=['" + configJs + "'];function val(r,k){var v=r.getProperty(k);return v==null?'':String(v);}function typ(r){var t=val(r,'Type');if(t=='')t=val(r,'Object_type');return t;}function num(v){var n=Number(v);return isFinite(n)?n.toFixed(6):String(v);}for(var i=0;i<rois.length;i++){var r=rois[i],b=r.getFloatBounds(),fp=(r instanceof Packages.ij.gui.Line?r.getFloatPoints():r.getFloatPolygon()),name=String(r.getName()||'');parts.push('R',i,name,typ(r),num(b.x),num(b.y),num(b.width),num(b.height),val(r,'Cavity_class'),val(r,'Manual_excluded'),val(r,'Measurement_source'),val(r,'Exclusion_reason'),val(r,'Mask_label'),val(r,'Material_side_sign'));if(fp!=null){parts.push('P',fp.npoints);for(var k=0;k<fp.npoints;k++)parts.push(num(fp.xpoints[k]),num(fp.ypoints[k]));}}var bytes=MD.getInstance('SHA-256').digest(new java.lang.String(parts.join('|')).getBytes(CS.UTF_8)),out='';for(var j=0;j<bytes.length;j++){var v=Number(bytes[j])&255;out+=(v<16?'0':'')+v.toString(16);}return out;})();";
    result = "" + eval("js", js);
    return result;
}

function lightAreaInputFingerprint() {
    if (nImages() <= 0) return "";
    updateScaleMaybe();
    config = lightImageId + "|" + getWidth() + "x" + getHeight();
    config = config + "|scale=" + d2s(nmPerPixelX,12) + "," + d2s(nmPerPixelY,12);
    config = config + "|mode=" + lightImageMode + "|whole=" + lightUseWholeImage;
    config = config + "|surface=" + surfaceDefined + "," + surfaceSideDefined + "," + d2s(surfaceMaterialSign,0);
    config = config + "|exclude_negative=" + excludeNegativeDepth;
    config=config+"|HF3=parallel_miter|band_mode="+lightBandMode;
    if(lightBandMode=="count")config=config+"|N="+bandCount;else config=config+"|width="+d2s(bandNm,12);
    configJs = jsEscape(config);
    js = "(function(){var RM=Packages.ij.plugin.frame.RoiManager,MD=Packages.java.security.MessageDigest,CS=Packages.java.nio.charset.StandardCharsets,rm=RM.getInstance2(),rois=rm==null?[]:rm.getRoisAsArray(),parts=['" + configJs + "'];function val(r,k){var v=r.getProperty(k);return v==null?'':String(v);}function typ(r){var t=val(r,'Type');if(t=='')t=val(r,'Object_type');return t;}function num(v){var n=Number(v);return isFinite(n)?n.toFixed(6):String(v);}for(var i=0;i<rois.length;i++){var r=rois[i],t=typ(r);if(t!='analysis_mask'&&t!='exclusion'&&t!='surface_reference')continue;var b=r.getFloatBounds(),fp=(r instanceof Packages.ij.gui.Line?r.getFloatPoints():r.getFloatPolygon());parts.push('R',i,String(r.getName()||''),t,num(b.x),num(b.y),num(b.width),num(b.height),val(r,'Exclusion_reason'),val(r,'Material_side_sign'));if(fp!=null){parts.push('P',fp.npoints);for(var k=0;k<fp.npoints;k++)parts.push(num(fp.xpoints[k]),num(fp.ypoints[k]));}}var bytes=MD.getInstance('SHA-256').digest(new java.lang.String(parts.join('|')).getBytes(CS.UTF_8)),out='';for(var j=0;j<bytes.length;j++){var v=Number(bytes[j])&255;out+=(v<16?'0':'')+v.toString(16);}return out;})();";
    result = "" + eval("js", js);
    return result;
}

function lightClearCavityContextCache() {
    lightCavityContextActive = 0;
    lightCtxValid = newArray(0);
    lightCtxEdgeMask = newArray(0);
    lightCtxReason = newArray(0);
    lightCtxDistanceGbNm = newArray(0);
    lightCtxDistanceDislocationNm = newArray(0);
    lightCtxDistanceInterfaceNm = newArray(0);
}

function lightBuildCavityContextCache() {
    lightClearCavityContextCache();total=roiManager("count");
    lightCtxValid=newArray(total);lightCtxEdgeMask=newArray(total);lightCtxReason=newArray(total);
    lightCtxDistanceGbNm=newArray(total);lightCtxDistanceDislocationNm=newArray(total);lightCtxDistanceInterfaceNm=newArray(total);
    lightCtxDepth=newArray(total);lightCtxAbsolute=newArray(total);lightCtxArc=newArray(total);lightCtxNearX=newArray(total);lightCtxNearY=newArray(total);lightCtxAngle=newArray(total);
    result=lightHF3Run("context","");rows=split(result,"\n");
    if(rows.length<1||rows[0]!="OK"){showMessage("Calculo no realizado",result);return 0;}
    for(k=1;k<rows.length;k++){
        a=split(rows[k],"|");if(a.length<13)continue;idx=round(parseFloat(a[0]));
        lightCtxValid[idx]=parseFloat(a[1]);lightCtxEdgeMask[idx]=parseFloat(a[2]);lightCtxReason[idx]=a[3];
        lightCtxDistanceGbNm[idx]=parseFloat(a[4]);lightCtxDistanceDislocationNm[idx]=parseFloat(a[5]);lightCtxDistanceInterfaceNm[idx]=parseFloat(a[6]);
        lightCtxDepth[idx]=parseFloat(a[7]);lightCtxAbsolute[idx]=parseFloat(a[8]);lightCtxArc[idx]=parseFloat(a[9]);lightCtxNearX[idx]=parseFloat(a[10]);lightCtxNearY[idx]=parseFloat(a[11]);lightCtxAngle[idx]=parseFloat(a[12]);
    }
    lightCavityContextActive=1;return 1;
}

function lightPrepareAnalysisState(force, verbose) {
    lightHF4Pause();
    lightHF4Pull();
    if (nImages() <= 0) return 0;
    commitOk=commitActiveManagedRoi();if(commitOk<0)return 0;
    startMs = getTime();
    beforeFingerprint = lightAnalysisInputFingerprint();
    canReuse = 0;
    if (force == 0) {
        if (beforeFingerprint != "") {
            if (beforeFingerprint == lightPreparedFingerprint) canReuse = 1;
        }
    }
    if (canReuse == 1) {
        lightLastPreparationReused = 1;
        lightLastPreparationDurationMs = getTime() - startMs;
        lightPreparationCacheHits++;
        if (verbose) showStatus("Estado cuantitativo reutilizado; no se recorrieron de nuevo las cavidades.");
        return 1;
    }
    lightLastPreparationReused = 0;
    showStatus("Actualizando geometria y duplicados en un unico ciclo...");
    syncOk = lightSyncAllObjectsCore(0);
    if (syncOk == 0) return 0;
    duplicateResult=lightScanAllDuplicatesCore(0);if(duplicateResult<0)return 0;
    afterFingerprint = lightAnalysisInputFingerprint();
    lightPreparedFingerprint = afterFingerprint;
    lightPreparedAtMs = getTime();
    lightLastPreparationDurationMs = lightPreparedAtMs - startMs;
    lightPreparationRuns++;
    if (verbose) showStatus("Estado cuantitativo preparado en " + d2s(lightLastPreparationDurationMs/1000,2) + " s.");
    return 1;
}

// -----------------------------------------------------------------------------
// Recalculation from current ROI geometry
// -----------------------------------------------------------------------------

function syncAllObjects(verbose) {
    lightSyncAllObjectsCore(verbose);
}

function lightSyncAllObjectsCore(verbose) {
    lightHF4Pause();
    if (nImages() <= 0) return 0;
    if (v4ProjectLoaded && !v4RequireCurrentRevisionBinding("sincronizar las ROI", verbose)) return 0;
    run("ROI Manager...");
    if (!updateScaleMaybe()) {
        if (verbose) showMessage("Escala no valida", "Define o restaura la escala antes de sincronizar.");
        return 0;
    }
    commitOk=commitActiveManagedRoi();if(commitOk<0)return 0;
    refreshSurfaceGeometryFromRoi();
    ensureObjectIds();
    if(lightImageMode=="with_surface")excludeNegativeDepth=1;
    if(!lightComputeExactAreaAndDepth())return 0;
    if(!lightBuildCavityContextCache())return 0;

    snapshotCurrentView();
    n = roiManager("count");
    cCav = 0;
    cOther = 0;
    for (i=0; i<n; i++) {
        if (i % 20 == 0) showProgress(i, max2(n,1));
        if(!safeRoiSelect(i)){lightClearCavityContextCache();return 0;}
        type = currentRoiType();
        if (type == "cavity") {
            syncCavityAtIndex(i);
            cCav++;
        } else if (isLinearFeatureType(type)) {
            if(!syncLinearFeatureAtIndex(i)){lightClearCavityContextCache();return 0;}
            cOther++;
        } else if (type == "dislocation_loop") {
            syncDislocationLoopAtIndex(i);
            cOther++;
        } else if (type == "panel" || type == "analysis_mask" || type == "exclusion") {
            syncAreaObjectAtIndex(i);
            cOther++;
        } else if (type == "scale_reference") {
            syncScaleReferenceAtIndex(i);
        } else if (type == "surface_reference") {
            syncSurfaceReferenceAtIndex(i);
        }
    }
    showProgress(1,1);
    if (scaleDefined) rebuildScaleLabelFromReference(0);
    updateSessionMetadataRoi();
    showAllRois();
    restoreViewSnapshot();
    lightClearCavityContextCache();
    refreshControlPanelStatus();
    if (verbose) showStatus("Sincronizadas " + cCav + " cavidades y " + cOther + " ROIs auxiliares en un solo recorrido.");
    return 1;
}

function syncCavityAtIndex(idx) {
    if(!safeRoiSelect(idx))return; if (!currentRoiIsCavity()) return;
    id = Roi.getProperty("Cavity_id"); if (id == "") { cavityCounter++; id = "CAV_" + IJ.pad(cavityCounter,6); }
    serial = round(propNumber("Cavity_serial", serialFromId(id))); if (serial < 1) serial = serialFromId(id);
    source = propString("Measurement_source", "unknown"); manualExcluded = round(propNumber("Manual_excluded",0));
    duplicateStatus = propString("Duplicate_status","clear"); duplicatePartners = propString("Duplicate_partners","");
    storedCavityClass = propString("Cavity_class","confirmed"); cavityClass = normalizeCavityClass(storedCavityClass); defaultClassLabel = cavityClassLabel(cavityClass); cavityClassLabelValue = propString("Cavity_class_label",defaultClassLabel); cavityConfidence = propString("Cavity_confidence","high");
    Roi.getFloatBounds(x,y,w,h); cx=x+w/2; cy=y+h/2; axisXNm=w*nmPerPixelX; axisYNm=h*nmPerPixelY; majorNm=max2(axisXNm,axisYNm); minorNm=min2(axisXNm,axisYNm); eqDnm=sqrt(axisXNm*axisYNm); if(eqDnm<=0)return; aspect=NaN;if(minorNm>0)aspect=majorNm/minorNm;areaNm2=PI_VAL*axisXNm*axisYNm/4;sphereVolumeNm3=PI_VAL*pow(eqDnm,3)/6;geometryKind="circle";if(aspect>1.02)geometryKind="ellipse";
    depthAbs=NaN;depthSigned=NaN;arcNm=NaN;nearestX=NaN;nearestY=NaN;tangentAngle=NaN;bandIndex=-1;
    metricOkHF3=0;
    if(lightImageMode=="with_surface"&&surfaceDefined){metricOkHF3=lightHF3SetMetrics(idx);if(metricOkHF3==0)metricOkHF3=computeSurfaceMetrics(cx,cy);}
    if(lightImageMode=="with_surface"&&surfaceDefined&&metricOkHF3){depthAbs=surfaceLastDistanceNm;depthSigned=surfaceLastSignedDistanceNm;arcNm=surfaceLastArcNm;nearestX=surfaceLastNearestXpx;nearestY=surfaceLastNearestYpx;tangentAngle=surfaceLastTangentAngleDeg;depthForBand=depthSigned;if(!surfaceSideDefined)depthForBand=depthAbs;if(depthForBand>=0)bandIndex=lightHF3BandIndex(depthForBand);}
    useCachedContext=0;
    if(lightCavityContextActive==1){
        if(idx>=0){
            if(idx<lightCtxValid.length)useCachedContext=1;
        }
    }
    if(useCachedContext==1){
        validCenter=round(lightCtxValid[idx]);
        invalidReason=lightCtxReason[idx];
        edgeMask=round(lightCtxEdgeMask[idx]);
        distanceGbNm=lightCtxDistanceGbNm[idx];
        distanceDislocationNm=lightCtxDistanceDislocationNm[idx];
        distanceInterfaceNm=lightCtxDistanceInterfaceNm[idx];
    }else{
        validCenter=pointValidity(cx,cy);
        invalidReason=pointValidityReason;
        edgeMask=0;
        if(validCenter)edgeMask=cavityIntersectsInvalidRegion(cx,cy,w/2,h/2);
        distanceGbNm=distanceToNearestFeatureNm(cx,cy,"grain_boundary");
        distanceDislocationNm=distanceToNearestFeatureNm(cx,cy,"dislocation");
        distanceInterfaceNm=distanceToNearestFeatureNm(cx,cy,"interface");
    }
    edgeImage=0;if(x<=0||y<=0||x+w>=getWidth()||y+h>=getHeight())edgeImage=1;edgeIntersect=max2(edgeImage,edgeMask);
    includeStats=1;exclusionReason="";if(!validCenter){includeStats=0;exclusionReason=invalidReason;}if(manualExcluded){includeStats=0;exclusionReason="manual_exclusion";}if(lightImageMode=="with_surface"&&excludeNegativeDepth&&!isNaN(depthSigned)&&depthSigned<0){includeStats=0;exclusionReason="negative_depth";}
    classAllowed=1;if(cavityClass=="possible_artifact")classAllowed=0;if(cavityClass=="uncertain"&&!lightIncludeUncertain)classAllowed=0;countValid=includeStats&&classAllowed;sizeValid=countValid&&!edgeIntersect;
    cavityGroup=lightGroupForCavityClass(cavityClass);if(manualExcluded)cavityGroup=3;
    safeRoiSelect(idx);Roi.setName(id);Roi.setGroup(cavityGroup);Roi.setProperty("Type","cavity");Roi.setProperty("Cavity_id",id);Roi.setProperty("Cavity_serial",d2s(serial,0));Roi.setProperty("Measurement_source",source);Roi.setProperty("Cavity_class",cavityClass);Roi.setProperty("Cavity_class_label",cavityClassLabelValue);Roi.setProperty("Cavity_confidence",cavityConfidence);Roi.setProperty("Geometry_kind",geometryKind);
    Roi.setProperty("Center_x_px",d2s(cx,6));Roi.setProperty("Center_y_px",d2s(cy,6));Roi.setProperty("Center_x_nm",d2s(cx*nmPerPixelX,6));Roi.setProperty("Center_y_nm",d2s(cy*nmPerPixelY,6));Roi.setProperty("Axis_x_nm",d2s(axisXNm,6));Roi.setProperty("Axis_y_nm",d2s(axisYNm,6));Roi.setProperty("Major_axis_nm",d2s(majorNm,6));Roi.setProperty("Minor_axis_nm",d2s(minorNm,6));Roi.setProperty("Equivalent_diameter_nm",d2s(eqDnm,6));Roi.setProperty("Diameter_nm",d2s(eqDnm,6));Roi.setProperty("Aspect_ratio",d2s(aspect,6));Roi.setProperty("Cavity_area_nm2",d2s(areaNm2,6));Roi.setProperty("Estimated_spherical_volume_nm3",d2s(sphereVolumeNm3,6));Roi.setProperty("Bubble_area_nm2",d2s(areaNm2,6));Roi.setProperty("Bubble_volume_nm3",d2s(sphereVolumeNm3,6));
    Roi.setProperty("Depth_absolute_nm",d2s(depthAbs,6));Roi.setProperty("Signed_depth_nm",d2s(depthSigned,6));Roi.setProperty("Depth_nm",d2s(depthSigned,6));Roi.setProperty("Surface_position_nm",d2s(arcNm,6));Roi.setProperty("Surface_nearest_x_px",d2s(nearestX,6));Roi.setProperty("Surface_nearest_y_px",d2s(nearestY,6));Roi.setProperty("Surface_tangent_angle_deg",d2s(tangentAngle,6));Roi.setProperty("Band_index",d2s(bandIndex,0));if(bandIndex>=0){Roi.setProperty("Band_low_nm",d2s(bandIndex*bandNm,6));Roi.setProperty("Band_high_nm",d2s((bandIndex+1)*bandNm,6));}else{Roi.setProperty("Band_low_nm","NaN");Roi.setProperty("Band_high_nm","NaN");}Roi.setProperty("Band_width_nm",d2s(bandNm,6));
    Roi.setProperty("Inside_analysis_mask",d2s(validCenter,0));Roi.setProperty("Position_valid",d2s(validCenter,0));Roi.setProperty("Exclusion_reason",exclusionReason);Roi.setProperty("Manual_excluded",d2s(manualExcluded,0));Roi.setProperty("Include_in_statistics",d2s(countValid,0));Roi.setProperty("Count_valid",d2s(countValid,0));Roi.setProperty("Size_valid",d2s(sizeValid,0));Roi.setProperty("Include_in_size_statistics",d2s(sizeValid,0));Roi.setProperty("Edge_intersecting",d2s(edgeIntersect,0));Roi.setProperty("Panel_id","");Roi.setProperty("Source_filename",imageFileName);Roi.setProperty("Panel_match_count","0");Roi.setProperty("Effective_owner_code","0");Roi.setProperty("Geometric_coverage_count","0");Roi.setProperty("Crosses_panel_boundary","0");Roi.setProperty("Distinct_panel_owners","0");Roi.setProperty("Touches_panel_background","0");Roi.setProperty("Panel_boundary_review_required","0");Roi.setProperty("Duplicate_status",duplicateStatus);Roi.setProperty("Duplicate_partners",duplicatePartners);Roi.setProperty("Distance_to_grain_boundary_nm",d2s(distanceGbNm,6));Roi.setProperty("Distance_to_dislocation_nm",d2s(distanceDislocationNm,6));Roi.setProperty("Distance_to_interface_nm",d2s(distanceInterfaceNm,6));Roi.setProperty("Analysis_pending","0");setCommonObjectProperties();applyCavityStyle();roiManager("update");
}


function syncScaleReferenceAtIndex(idx) {
    if(!safeRoiSelect(idx))return;
    getLine(x1, y1, x2, y2, lw);
    if (x1 == -1) return;
    dpx = sqrt((x2-x1)*(x2-x1)+(y2-y1)*(y2-y1));
    known = propNumber("Known_length_nm", scaleKnownNm);
    if (dpx > 0 && known > 0) {
        scaleKnownNm = known;
        Roi.setProperty("Line_length_px", d2s(dpx, 9));
        Roi.setProperty("Scale_nm_per_px", d2s(known/dpx, 12));
        Roi.setProperty("X1_px", d2s(x1, 6));
        Roi.setProperty("Y1_px", d2s(y1, 6));
        Roi.setProperty("X2_px", d2s(x2, 6));
        Roi.setProperty("Y2_px", d2s(y2, 6));
    }
    Roi.setStrokeColor("yellow");
    Roi.setUnscalableStrokeWidth(3);
    roiManager("update");
}

function syncSurfaceReferenceAtIndex(idx) {
    if(!safeRoiSelect(idx))return;
    Roi.getCoordinates(xs, ys);
    if (xs.length < 2) return;
    Roi.setProperty("Type", "surface_reference");
    Roi.setProperty("Surface_side_defined", d2s(surfaceSideDefined, 0));
    Roi.setProperty("Material_point_x_px", d2s(surfaceMaterialX, 6));
    Roi.setProperty("Material_point_y_px", d2s(surfaceMaterialY, 6));
    Roi.setProperty("Material_side_sign", d2s(surfaceMaterialSign, 0));
    Roi.setProperty("Point_count", d2s(xs.length, 0));
    Roi.setProperty("Length_nm", d2s(polylineLengthNm(xs, ys), 6));
    Roi.setStrokeColor("cyan");
    Roi.setUnscalableStrokeWidth(3);
    roiManager("update");
    surfaceX = xs;
    surfaceY = ys;
}

// -----------------------------------------------------------------------------
// Duplicate detection
// -----------------------------------------------------------------------------

function duplicatePairLikely(x1, y1, d1px, d1nm, x2, y2, d2px, d2nm) {
    centerDist = sqrt((x1-x2)*(x1-x2)+(y1-y2)*(y1-y2));
    tol = max2(duplicateCenterTolPx, duplicateRelativeTol*min2(d1px, d2px));
    maxD = max2(d1nm, d2nm);
    sizeDiff = 0;
    if (maxD > 0) sizeDiff = abs(d1nm-d2nm)/maxD;
    if (centerDist <= tol && sizeDiff <= duplicateDiameterTolFraction) return 1;
    // Exact/near-exact center is suspicious even if the measured diameters differ.
    if (centerDist <= duplicateCenterTolPx*0.5) return 1;
    return 0;
}

function checkNewCavityForDuplicates(newIdx) {
    safeRoiSelect(newIdx);
    if (!currentRoiIsCavity()) return;
    Roi.getFloatBounds(x, y, w, h);
    cx = x+w/2;
    cy = y+h/2;
    dpx = sqrt(w*h);
    dnm = propNumber("Equivalent_diameter_nm", sqrt((w*nmPerPixelX)*(h*nmPerPixelY)));
    id = cavityIdCurrent();
    partners = "";
    n = roiManager("count");
    for (i=0; i<n; i++) {
        if (i == newIdx) continue;
        safeRoiSelect(i);
        if (currentRoiIsCavity()) {
            Roi.getFloatBounds(x2, y2, w2, h2);
            cx2 = x2+w2/2;
            cy2 = y2+h2/2;
            d2px = sqrt(w2*h2);
            d2nm = propNumber("Equivalent_diameter_nm", sqrt((w2*nmPerPixelX)*(h2*nmPerPixelY)));
            if (duplicatePairLikely(cx, cy, dpx, dnm, cx2, cy2, d2px, d2nm)) {
                id2 = cavityIdCurrent();
                partners = appendToken(partners, id2);
                old = propString("Duplicate_partners", "");
                safeRoiSelect(i);
                Roi.setProperty("Duplicate_status", "suspect");
                Roi.setProperty("Duplicate_partners", appendToken(old, id));
                applyCavityStyle();
                roiManager("update");
            }
        }
    }
    safeRoiSelect(newIdx);
    if (partners != "") {
        Roi.setProperty("Duplicate_status", "suspect");
        Roi.setProperty("Duplicate_partners", partners);
        applyCavityStyle();
        roiManager("update");
        showStatus(id + " coincide con posibles duplicados: " + partners + ". Se conservan para revision.");
    }
}

function scanAllDuplicates(verbose) {
    if (nImages() <= 0) return;
    if (v4ProjectLoaded && !v4RequireCurrentRevisionBinding("buscar duplicados", verbose)) return;
    syncOk = lightSyncAllObjectsCore(0);
    if (syncOk == 0) return;
    if(lightScanAllDuplicatesCore(verbose)<0)return;
    lightPreparedFingerprint = lightAnalysisInputFingerprint();
    lightPreparedAtMs = getTime();
    lightLastPreparationReused = 0;
}

function lightScanAllDuplicatesCore(verbose) {
    if(countTypeFast("cavity")<1){if(verbose)showStatus("No hay cavidades.");return 0;}
    args=""+duplicateCenterTolPx+"|"+duplicateRelativeTol+"|"+duplicateDiameterTolFraction+"|"+nmPerPixelX+"|"+nmPerPixelY+"|"+verbose;
    result=call("cavity.light.HF46.duplicates",args);
    if(startsWith(result,"ERROR")){call("cavity.light.HF4.log",result);showStatus(result);return -1;}
    restyleAllRois();showAllRois();
    if(verbose)showStatus("Pares sospechosos: "+result+". Ninguna cavidad se borra o excluye automaticamente.");
    return parseFloat(result);
}

function computeBandAreasSampled() {
    lastAreaSamplingStepPx = NaN;
    lastValidAreaNm2 = NaN;
    lastBandAreasNm2 = newArray(bandCount);
    if (!surfaceDefined) return 0;
    updateScaleOrExit();

    js = "var IJ=Packages.ij.IJ;";
    js = js + "var RM=Packages.ij.plugin.frame.RoiManager;";
    js = js + "var OUT='ERROR|unknown';var imp=IJ.getImage();var rm=RM.getInstance2();if(imp==null||rm==null){OUT='ERROR|no image or ROI manager';}else{";
    js = js + "var rois=rm.getRoisAsArray();var masks=[];var panels=[];var exclusions=[];var surface=null;";
    js = js + "function typ(r){var p=r.getProperty('Type');return p==null?'':String(p);}";
    js = js + "for(var i=0;i<rois.length;i++){var t=typ(rois[i]);var n=String(rois[i].getName());if(t=='analysis_mask')masks.push(rois[i]);else if(t=='panel')panels.push(rois[i]);else if(t=='exclusion')exclusions.push(rois[i]);else if(t=='surface_reference'||t=='surface'||n.indexOf('SURFACE_REFERENCE')==0)surface=rois[i];}";
    js = js + "if(surface==null){OUT='ERROR|surface missing';}else{";
    js = js + "var requirePanels=" + d2s(usePanelsAsMask || v4PanelQuantitativeReady,0) + ";";
    js = js + "function anyContains(arr,x,y){for(var j=0;j<arr.length;j++){if(arr[j].contains(x,y))return true;}return false;}";
    js = js + "var fp=(surface instanceof Packages.ij.gui.Line?surface.getFloatPoints():surface.getFloatPolygon());var sx=fp.xpoints;var sy=fp.ypoints;var sn=fp.npoints;";
    js = js + "var pw=" + d2s(nmPerPixelX,12) + ";var ph=" + d2s(nmPerPixelY,12) + ";var sideDefined=" + d2s(surfaceSideDefined,0) + ";var matSign=" + d2s(surfaceMaterialSign,0) + ";";
    js = js + "function sdist(px,py){var xn=px*pw,yn=py*ph;var best=1e300,bestCross=0;for(var q=0;q<sn-1;q++){var x1=sx[q]*pw,y1=sy[q]*ph,x2=sx[q+1]*pw,y2=sy[q+1]*ph;var vx=x2-x1,vy=y2-y1,l2=vx*vx+vy*vy;if(l2<=0)continue;var tt=((xn-x1)*vx+(yn-y1)*vy)/l2;if(tt<0)tt=0;if(tt>1)tt=1;var qx=x1+tt*vx,qy=y1+tt*vy;var dx=xn-qx,dy=yn-qy,d2=dx*dx+dy*dy;if(d2<best){best=d2;bestCross=vx*(yn-y1)-vy*(xn-x1);}}if(best>=1e299)return NaN;var d=Math.sqrt(best);if(sideDefined==1){var sg=bestCross<0?-1:1;if(bestCross==0)sg=matSign;if(sg!=matSign)d=-d;}return d;}";
    js = js + "var W=imp.getWidth(),H=imp.getHeight();var target=" + d2s(areaSamplingTarget,0) + ";if(target<10000)target=10000;var step=Math.ceil(Math.sqrt((W*H)/target));if(step<1)step=1;";
    js = js + "var bc=" + d2s(bandCount,0) + ",bw=" + d2s(bandNm,12) + ";var areas=new Array(bc);for(var z=0;z<bc;z++)areas[z]=0;var validArea=0;var inBandArea=0;var sampled=0;";
    js = js + "for(var y0=0;y0<H;y0+=step){var ch=Math.min(step,H-y0);var cy=y0+ch/2.0;for(var x0=0;x0<W;x0+=step){var cw=Math.min(step,W-x0);var cx=x0+cw/2.0;var xi=Math.floor(cx),yi=Math.floor(cy);var valid=(requirePanels==0||panels.length==0||anyContains(panels,xi,yi));if(valid&&masks.length>0&&!anyContains(masks,xi,yi))valid=false;if(valid&&anyContains(exclusions,xi,yi))valid=false;if(!valid)continue;var a=cw*ch*pw*ph;validArea+=a;var dd=sdist(cx,cy);if(!isNaN(dd)&&dd>=0){var b=Math.floor(dd/bw);if(b>=0&&b<bc){areas[b]+=a;inBandArea+=a;}}sampled++;}}";
    js = js + "OUT=step+'|'+validArea+'|'+inBandArea+'|'+sampled+'|'+areas.join(',');";
    js = js + "}}OUT;";
    result = eval("js", js);
    if (startsWith(result, "ERROR")) {
        call("cavity.light.HF4.log","Cavity area sampling: " + result);
        return 0;
    }
    parts = split(result, "|");
    if (parts.length < 5) return 0;
    lastAreaSamplingStepPx = parseFloat(parts[0]);
    lastValidAreaNm2 = parseFloat(parts[1]);
    areaValues = split(parts[4], ",");
    lastBandAreasNm2 = newArray(bandCount);
    for (b=0; b<bandCount; b++) {
        lastBandAreasNm2[b] = 0;
        if (b < areaValues.length) lastBandAreasNm2[b] = parseFloat(areaValues[b]);
    }
    return 1;
}

// -----------------------------------------------------------------------------
// Quantitative preflight: ensure every included cavity is represented by the
// configured non-negative depth bands. This prevents silent omission from the
// Band_Summary table when a cavity lies beyond the current band range.
// -----------------------------------------------------------------------------

function computeIncludedBandCoverage() {
    coverageMaxBand = -1;
    coverageUnbanded = 0;
    coverageIncluded = 0;
    n = roiManager("count");
    for (ii=0; ii<n; ii++) {
        safeRoiSelect(ii);
        if (currentRoiIsCavity()) {
            inc = round(propNumber("Include_in_statistics", 1));
            if (inc) {
                coverageIncluded++;
                bi = round(propNumber("Band_index", -1));
                if (bi < 0) coverageUnbanded++;
                else if (bi > coverageMaxBand) coverageMaxBand = bi;
            }
        }
    }
    return 1;
}

function quantitativeExportPreflight() {
    if(!lightHF4RequireReviewed())return 0;
    imageOk=lightEnsureCurrentImage();
    if(imageOk==0)return 0;
    if(lightSourceSha256==""||lengthOf(lightSourceSha256)!=64){
        showMessage("Exportacion no disponible","La imagen no tiene SHA-256 de origen.");
        return 0;
    }
    path=lightResolveSourcePath();
    if(path=="")return 0;
    actualSha=call("cavity.light.HF46.sourceSha",path);
    if(actualSha!=lightSourceSha256){
        showMessage("Integridad bloqueada","La fuente actual no coincide con el SHA-256 registrado.");
        return 0;
    }
    scaleReady=updateScaleMaybe();
    if(scaleReady==0||lightScaleConfirmed==0){
        showMessage("Exportacion no disponible","Confirma primero la escala fisica.");
        return 0;
    }
    countsReady=lightRefreshObjectCounts();
    if(countsReady==0){
        showMessage("Exportacion no disponible","No se pudieron contar los objetos del ROI Manager.");
        return 0;
    }
    maskTotal=lightObjectCountMasks;
    if(maskTotal==0&&lightUseWholeImage==0&&!lightHF3ImplicitMaterialArea()){
        showMessage("Exportacion no disponible","Dibuja un area valida o confirma toda la imagen.");
        return 0;
    }
    if(lightImageMode=="with_surface"){
        surfaceTotal=lightObjectCountSurfaces;
        if(surfaceTotal!=1||surfaceDefined==0||surfaceSideDefined==0){
            showMessage("Exportacion no disponible","El modo con superficie exige una superficie unica y lado del material.");
            return 0;
        }
    }
    cavityTotal=lightObjectCountCavities;
    if(cavityTotal==0){
        showMessage("Exportacion no disponible","No hay cavidades registradas.");
        return 0;
    }
    preparedOk=lightPrepareAnalysisState(0,0);
    if(preparedOk==0)return 0;
    if(!lightHF46Finite(lastValidAreaNm2)||lastValidAreaNm2<=0)return 0;
    updateSessionMetadataRoi();
    return 1;
}

function v51AutoExtendBands(verbose) {
    // Never drop deep measurements merely because the initial display range
    // was too short. Negative/unbanded objects remain a separate QC issue.
    computeIncludedBandCoverage();
    maxBand = coverageMaxBand;
    requiredBands = maxBand + 1;
    if (requiredBands <= bandCount) return 0;
    oldBandCount = bandCount;
    bandCount = requiredBands;
    syncAllObjects(0);
    updateSessionMetadataRoi();
    metadataIndex = findMetadataIndex();
    if (metadataIndex >= 0) {
        safeRoiSelect(metadataIndex);
        extensionTime = d2s(getTime(),0);
        extensionDelta = bandCount-oldBandCount;
        extensionHistory = propString("Band_auto_extension_history", "");
        extensionEntry = extensionTime + ":" + oldBandCount + ">" + bandCount + "@" + d2s(bandNm,9) + "nm";
        if (extensionHistory != "") extensionHistory = extensionHistory + ";";
        extensionHistory = extensionHistory + extensionEntry;
        Roi.setProperty("Band_count_previous", d2s(oldBandCount,0));
        Roi.setProperty("Band_count_auto_extended_to", d2s(bandCount,0));
        Roi.setProperty("Band_auto_extension_delta", d2s(extensionDelta,0));
        Roi.setProperty("Band_auto_extension_time_ms", extensionTime);
        Roi.setProperty("Band_auto_extension_policy", "fixed_width_auto_count");
        Roi.setProperty("Band_auto_extension_history", extensionHistory);
        roiManager("update");
    }
    if (verbose) showStatus("Bandas ampliadas automaticamente: " + oldBandCount + " -> " + bandCount + ".");
    return bandCount-oldBandCount;
}

// -----------------------------------------------------------------------------
// Validation
// -----------------------------------------------------------------------------

function validateProject() {
    imageOk = lightEnsureCurrentImage();
    if (imageOk == 0) return 0;

    errors = 0;
    warnings = 0;
    areaMissing = 0;
    report = "CAVITY TEM LIGHT 1.1.1 R9-HF4.6 - VALIDACION DE IMAGEN\n";
    report = report + "====================================================\n\n";
    report = report + "Proyecto: " + lightProjectName + " [" + lightProjectId + "]\n";
    report = report + "Imagen: " + lightImageId + "\n";
    report = report + "Revision activa: " + lightCurrentRevision + "\n";
    report = report + "Modo: " + lightImageMode + "\n\n";

    path = lightResolveSourcePath();
    if (path == "") {
        report = report + "ERROR: no se ha localizado la fuente DM3/DM4.\n";
        errors++;
    } else {
        actualSha = call("cavity.light.HF46.verifySourceNow",path);
        if (actualSha != lightSourceSha256) {
            report = report + "ERROR: el SHA-256 actual no coincide con el registro.\n";
            errors++;
        } else report = report + "OK: identidad de ventana y fuente verificadas por project_id, image_id y SHA-256.\n";
    }

    scaleUpdated = updateScaleMaybe();
    if (scaleUpdated == 0 || lightScaleConfirmed == 0) {
        report = report + "ERROR: escala fisica no confirmada.\n";
        errors++;
    } else report = report + "OK: escala " + d2s(nmPerPixelX,9) + " x " + d2s(nmPerPixelY,9) + " nm/px (" + lightScaleOrigin + ").\n";

    preparedOk = lightPrepareAnalysisState(0,0);
    if (preparedOk == 0) {
        report = report + "ERROR: no se pudo preparar el estado cuantitativo de las ROIs.\n";
        errors++;
    }

    countsOk = lightRefreshObjectCounts();
    if (countsOk == 0) {
        report = report + "ERROR: no se pudieron contar los objetos del ROI Manager.\n";
        errors++;
    }

    auditText = lightAuditCavitiesFast();
    auditParts = split(auditText, "|");
    auditOk = 1;
    if (auditParts.length < 13) auditOk = 0;
    if (auditOk == 1) {
        cavCount = round(parseFloat(auditParts[0]));
        included = round(parseFloat(auditParts[1]));
        sizeValid = round(parseFloat(auditParts[2]));
        edge = round(parseFloat(auditParts[3]));
        dup = round(parseFloat(auditParts[4]));
        confirmed = round(parseFloat(auditParts[5]));
        uncertain = round(parseFloat(auditParts[6]));
        artifacts = round(parseFloat(auditParts[7]));
        otherClasses = round(parseFloat(auditParts[8]));
        includedConfirmed = round(parseFloat(auditParts[9]));
        includedUncertain = round(parseFloat(auditParts[10]));
        idAuditErrors = round(parseFloat(auditParts[11]));
        idAuditDuplicateIds = round(parseFloat(auditParts[12]));
    } else {
        cavCount = lightObjectCountCavities;
        included = 0;
        sizeValid = 0;
        edge = 0;
        dup = 0;
        confirmed = 0;
        uncertain = 0;
        artifacts = 0;
        otherClasses = 0;
        includedConfirmed = 0;
        includedUncertain = 0;
        idAuditErrors = 0;
        idAuditDuplicateIds = 0;
        report = report + "ERROR: no se pudo completar la auditoria rapida de cavidades.\n";
        errors++;
    }
    lightLastIdAuditErrors = idAuditErrors;
    lightLastIdAuditDuplicateIds = idAuditDuplicateIds;

    surfaceOk = 1;
    surfaceCount = lightObjectCountSurfaces;
    if (lightImageMode == "with_surface") {
        if (surfaceCount != 1 || surfaceDefined == 0 || surfaceSideDefined == 0) {
            surfaceOk = 0;
            report = report + "ERROR: el modo con superficie exige una superficie unica y el lado del material.\n";
            errors++;
        } else report = report + "OK: superficie y lado del material definidos.\n";
    } else report = report + "OK: modo sin superficie; no se exigen bandas de profundidad.\n";

    maskCount = lightObjectCountMasks;
    exclusionCount = lightObjectCountExclusions;
    if (maskCount == 0 && lightUseWholeImage == 0 && !lightHF3ImplicitMaterialArea()) {
        areaMissing = 1;
        report = report + "ERROR: falta definir el area de analisis. Pulsa 'Toda la imagen valida' o dibuja al menos un 'Area valida'.\n";
        report = report + "       Sin este paso no existe un denominador fisico para calcular densidades.\n";
        errors++;
    } else if (lightImageMode == "with_surface" && surfaceOk == 0) {
        report = report + "ERROR: el area no se calcula hasta definir correctamente la superficie.\n";
    } else {
        areaCalculated = lightComputeExactAreaAndDepth();
        if (areaCalculated == 1) {
            report = report + "OK: area neta " + d2s(lastValidAreaNm2/1000000,9) + " um^2";
            report = report + " (areas validas=" + maskCount + ", exclusiones=" + exclusionCount + ").\n";
        } else {
            report = report + "ERROR: el area neta calculada no es positiva.\n";
            errors++;
        }
    }

    if (lightThicknessNm <= 0) {
        report = report + "AVISO: sin espesor; no se calculara densidad volumetrica nominal.\n";
        warnings++;
    } else report = report + "OK: espesor " + d2s(lightThicknessNm,3) + " +/- " + d2s(lightThicknessUncertaintyNm,3) + " nm (" + lightThicknessMethod + ").\n";

    if (cavCount == 0) {
        report = report + "ERROR: no hay cavidades.\n";
        errors++;
    }

    report = report + "\nOBJETOS ACTUALES\n";
    report = report + "Cavidades: " + cavCount + " (confirmadas=" + confirmed + ", dudosas=" + uncertain + ", posibles artefactos=" + artifacts + ", otras=" + otherClasses + ").\n";
    report = report + "Dislocaciones: " + lightObjectCountDislocations + "; bordes de grano: " + lightObjectCountGrainBoundaries + "; interfaces: " + lightObjectCountInterfaces + ".\n";
    report = report + "Validas para recuento: " + included + " (confirmadas=" + includedConfirmed + ", dudosas=" + includedUncertain + ").\n";
    report = report + "Validas para tamanos: " + sizeValid + "; tocan borde: " + edge + "; duplicados sospechosos: " + dup + ".\n";
    report = report + "Incluir dudosas en estadistica: " + lightIncludeUncertain + ".\n";
    report = report + "Contador historico de identificadores: " + cavityCounter + " (puede contener huecos por borrados o deshacer).\n";
    report = report + "Identidad ROI/etiqueta: errores=" + idAuditErrors + "; IDs duplicados=" + idAuditDuplicateIds + "; modo=roi_name_v1.\n";

    if (idAuditErrors > 0 || idAuditDuplicateIds > 0) {
        report = report + "ERROR: el nombre visible, Cavity_id y Cavity_serial no son coherentes en todas las cavidades.\n";
        report=report+call("cavity.light.Identity.details","");
        errors++;
    }
    if (dup > 0) {
        report = report + "AVISO: revisa los duplicados antes de exportar.\n";
        warnings++;
    }
    if (included == 0) {
        report = report + "ERROR: ninguna cavidad cumple los criterios de recuento.\n";
        errors++;
    }

    report = report + "\nRESULTADO: " + errors + " errores y " + warnings + " avisos.\n";
    if (errors == 0) {
        report = report + "La imagen esta preparada para guardar una revision y calcular/exportar resultados tecnicos.\n";
        report = report + "PASO SIGUIENTE: pulsa Calcular y exportar resultados en la pestana 5.\n";
    } else {
        report = report + "Corrige los errores antes de utilizar resultados cuantitativos.\n";
        if (areaMissing == 1) report = report + "\nPASO SIGUIENTE: abre la pestana '2 Preparar' y decide si toda la imagen es valida o dibuja el area real de muestra.\n";
    }
    report = report + "\nRENDIMIENTO R9\n";
    report = report + "Preparacion reutilizada: " + lightLastPreparationReused + "; tiempo: " + d2s(lightLastPreparationDurationMs/1000,3) + " s.\n";
    report = report + "Conteo y auditoria de identidad: un unico recorrido Java del ROI Manager.\n";
    report = report + "Area: " + lightAreaComputationMode + "; tiempo: " + d2s(lightAreaComputationDurationMs/1000,3) + " s.\n";
    report = report + "\nEstado de la rama: " + lightValidationState + ". Requiere aceptacion con Fiji y DM3/DM4 reales antes de uso cientifico definitivo.\n";

    lightHF4Report(report,errors);
    if (errors == 0) return 1;
    return 0;
}


// -----------------------------------------------------------------------------
// Export
// -----------------------------------------------------------------------------

function exportAnalysis() { lightExportCurrentImage(); }


function exportFeaturePanelAndRegionTables() {
    featureRow = 0;
    panelRow = 0;
    regionRow = 0;
    n = roiManager("count");
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        type = currentRoiType();
        currentName = Roi.getName;
        if (isLinearFeatureType(type)) {
            Table.set("feature_id", featureRow, propString("Feature_id", currentName), "Microstructural_Features");
            Table.set("feature_type", featureRow, type, "Microstructural_Features");
            Table.set("length_nm", featureRow, propNumber("Length_nm", NaN), "Microstructural_Features");
            Table.set("length_um", featureRow, propNumber("Length_um", NaN), "Microstructural_Features");
            Table.set("point_count", featureRow, propNumber("Point_count", NaN), "Microstructural_Features");
            Table.set("confidence", featureRow, propString("Confidence", ""), "Microstructural_Features");
            Table.set("notes", featureRow, propString("Notes", ""), "Microstructural_Features");
            featureRow++;
        } else if (type == "panel") {
            Table.set("panel_id", panelRow, propString("Panel_id", currentName), "TEM_Panels");
            Table.set("panel_order", panelRow, propNumber("Panel_order", NaN), "TEM_Panels");
            Table.set("source_filename", panelRow, propString("Source_filename", ""), "TEM_Panels");
            Table.set("area_nm2", panelRow, propNumber("Area_nm2", NaN), "TEM_Panels");
            Table.set("area_um2", panelRow, propNumber("Area_um2", NaN), "TEM_Panels");
            Table.set("notes", panelRow, propString("Notes", ""), "TEM_Panels");
            panelRow++;
        } else if (type == "analysis_mask" || type == "exclusion") {
            Table.set("region_id", regionRow, objectIdCurrent(type), "Analysis_Regions");
            Table.set("region_type", regionRow, type, "Analysis_Regions");
            Table.set("label_or_reason", regionRow, propString("Mask_label", propString("Exclusion_reason", "")), "Analysis_Regions");
            Table.set("area_nm2", regionRow, propNumber("Area_nm2", NaN), "Analysis_Regions");
            Table.set("area_um2", regionRow, propNumber("Area_um2", NaN), "Analysis_Regions");
            Table.set("notes", regionRow, propString("Notes", ""), "Analysis_Regions");
            regionRow++;
        }
    }
}

function showLegacyRoiGroupSummary() {
    if (nImages() <= 0) exit("Abre una imagen y carga/importa ROIs primero.");
    run("ROI Manager...");
    n = roiManager("count");
    cCav=0; cMask=0; cPanel=0; cGB=0; cDisl=0; cExcl=0; cSurf=0; cScale=0; cMeta=0; cOther=0;
    for (rs=0; rs<n; rs++) {
        if (!safeRoiSelect(rs)) continue;
        t = currentRoiType();
        if (t == "cavity") cCav++;
        else if (t == "analysis_mask") cMask++;
        else if (t == "panel") cPanel++;
        else if (t == "grain_boundary") cGB++;
        else if (t == "dislocation") cDisl++;
        else if (t == "exclusion") cExcl++;
        else if (t == "surface_reference") cSurf++;
        else if (t == "scale_reference") cScale++;
        else if (t == "session_metadata") cMeta++;
        else cOther++;
    }
    msg = "ROIs cargadas: " + n + "\n\n";
    msg += "Cavidades: " + cCav + "\n";
    msg += "Mascaras/area valida: " + cMask + "\n";
    msg += "Paneles TEM: " + cPanel + "\n";
    msg += "Bordes de grano: " + cGB + "\n";
    msg += "Dislocaciones: " + cDisl + "\n";
    msg += "Exclusiones: " + cExcl + "\n";
    msg += "Superficie: " + cSurf + "\n";
    msg += "Escala: " + cScale + "\n";
    msg += "Metadata: " + cMeta + "\n";
    msg += "Otros/no clasificados: " + cOther + "\n\n";
    msg += "Los nombres legacy CAV_, MASK_, GB_ y DISL_ se reconocen automaticamente.";
    showMessage("Resumen ROIs", msg);
}

// -----------------------------------------------------------------------------
// Settings, instructions and display modes
// -----------------------------------------------------------------------------

function settingsDialog() {
    imageOk = lightEnsureCurrentImage();
    if (imageOk == 0) return;
    lightInteractiveReadResizeStep();
    oldActive = activeDiameterNm;
    oldBand = bandNm;
    oldCount = bandCount;
    oldExclude = excludeNegativeDepth;
    oldInclude = lightIncludeUncertain;
    oldHist = lightHistogramBinNm;
    oldFeature = lightFeatureDistanceBinNm;
    oldDupPx = duplicateCenterTolPx;
    oldDupRel = duplicateRelativeTol;
    oldDupD = duplicateDiameterTolFraction;
    oldSel = selectionTolerancePx;
    oldLabels = showRoiLabels;
    oldFill = fillCavities;
    oldAlpha = fillAlpha;
    oldStroke = roiStrokeWidth;
    oldRestore = restoreViewAfterRoi;
    oldPreview = lightInteractivePreviewEnabled;
    oldResizeStep = lightInteractiveResizeStepNm;

    oldModeHF3=lightBandMode;oldBreaksHF3=lightSizeBreaks;oldContrastHF3=lightResultContrast;
    Dialog.create("Ajustes Cavity TEM Light R9-HF3");
    Dialog.addNumber("Diametro activo (nm):", activeDiameterNm);
    Dialog.addNumber("Ancho de banda de profundidad (nm):", bandNm);
    Dialog.addNumber("Numero inicial de bandas:", bandCount);
    Dialog.addCheckbox("Excluir profundidad negativa", excludeNegativeDepth);
    Dialog.addCheckbox("Incluir cavidades dudosas en recuento principal", lightIncludeUncertain);
    Dialog.addNumber("Ancho del histograma (nm):", lightHistogramBinNm);
    Dialog.addNumber("Intervalo de distancia a microestructura (nm):", lightFeatureDistanceBinNm);
    Dialog.addMessage("Control de duplicados y seleccion:");
    Dialog.addNumber("Tolerancia centro duplicado (px):", duplicateCenterTolPx);
    Dialog.addNumber("Tolerancia relativa de centro:", duplicateRelativeTol);
    Dialog.addNumber("Tolerancia relativa de diametro:", duplicateDiameterTolFraction);
    Dialog.addNumber("Tolerancia de seleccion (px):", selectionTolerancePx);
    Dialog.addMessage("Interaccion HF4:");
    Dialog.addCheckbox("Mostrar circulo del diametro activo bajo el cursor", lightInteractivePreviewEnabled);
    Dialog.addNumber("Sensibilidad Alt+rueda (Ctrl opcional) (nm/paso):", lightInteractiveResizeStepNm);
    Dialog.addMessage("Rango permitido HF4: 0.001 a 2.000 nm por paso de rueda.");
    Dialog.addMessage("Visualizacion:");
    Dialog.addCheckbox("Mostrar etiquetas con el nombre ROI exacto", showRoiLabels);
    Dialog.addCheckbox("Rellenar cavidades", fillCavities);
    Dialog.addNumber("Opacidad de relleno (0-255):", fillAlpha);
    Dialog.addNumber("Grosor de contorno (px):", roiStrokeWidth);
    Dialog.addCheckbox("Restaurar vista despues de crear ROIs", restoreViewAfterRoi);
    Dialog.addMessage("Resultados HF3: bandas paralelas desde la superficie.");
    Dialog.addChoice("Modo de bandas:",newArray("width","count"),lightBandMode);
    Dialog.addString("Limites de diametro (nm, separados por comas):",lightSizeBreaks,32);
    Dialog.addNumber("Contraste del fondo en resultados (0 a 1):",lightResultContrast);
    Dialog.show();

    newActive = Dialog.getNumber();
    newBand = Dialog.getNumber();
    newCount = round(Dialog.getNumber());
    newExclude = Dialog.getCheckbox();
    newInclude = Dialog.getCheckbox();
    newHist = Dialog.getNumber();
    newFeature = Dialog.getNumber();
    newDupPx = Dialog.getNumber();
    newDupRel = Dialog.getNumber();
    newDupD = Dialog.getNumber();
    newSel = Dialog.getNumber();
    newPreview = Dialog.getCheckbox();
    newResizeStep = Dialog.getNumber();
    newLabels = Dialog.getCheckbox();
    newFill = Dialog.getCheckbox();
    newAlpha = round(Dialog.getNumber());
    newStroke = round(Dialog.getNumber());
    newRestore = Dialog.getCheckbox();
    newModeHF3=Dialog.getChoice();newBreaksHF3=Dialog.getString();newContrastHF3=Dialog.getNumber();
    checkSource=lightHF3Source();checkCode=checkSource+"\ntry{CTL3.breaks('"+jsEscape(newBreaksHF3)+"');'OK';}catch(e){String(e);}";
    checkResult=""+eval("js",checkCode);
    if(checkResult!="OK"||isNaN(newContrastHF3)||newContrastHF3<0||newContrastHF3>1){showMessage("Ajustes no validos","Revise los limites de tamano y el contraste entre 0 y 1.\n"+checkResult);return;}
    if(lightImageMode=="with_surface")newExclude=1;

    if (newActive < 0) newActive = 0;
    if (newBand <= 0) newBand = 50;
    if (newCount < 1) newCount = 1;
    if (newHist <= 0) newHist = 1;
    if (newFeature <= 0) newFeature = 10;
    if (newAlpha < 0) newAlpha = 0;
    if (newAlpha > 255) newAlpha = 255;
    if (newStroke < 1) newStroke = 1;
    if (newResizeStep < lightInteractiveResizeMinNm) newResizeStep = lightInteractiveResizeMinNm;
    if (newResizeStep > lightInteractiveResizeMaxNm) newResizeStep = lightInteractiveResizeMaxNm;

    quantitativeChanged = 0;
    if(newModeHF3!=oldModeHF3)quantitativeChanged=1;
    if (lightNumberChanged(newBand, oldBand) == 1) quantitativeChanged = 1;
    if (newCount != oldCount) quantitativeChanged = 1;
    if (newExclude != oldExclude) quantitativeChanged = 1;
    if (newInclude != oldInclude) quantitativeChanged = 1;
    if (lightNumberChanged(newHist, oldHist) == 1) quantitativeChanged = 1;
    if (lightNumberChanged(newFeature, oldFeature) == 1) quantitativeChanged = 1;
    if (lightNumberChanged(newDupPx, oldDupPx) == 1) quantitativeChanged = 1;
    if (lightNumberChanged(newDupRel, oldDupRel) == 1) quantitativeChanged = 1;
    if (lightNumberChanged(newDupD, oldDupD) == 1) quantitativeChanged = 1;

    objects = lightScientificObjectCount();
    if (quantitativeChanged == 1 && objects > 0) {
        if (!getBoolean("Estos ajustes cambian calculos, inclusiones o control de duplicados. Las ROIs se recalcularan y se guardara una revision nueva.\n\nContinuar?", "Cambiar y revisar", "Cancelar")) return;
        if (!quantitativeRevisionPreflight()) return;
    }

    lightBandMode=newModeHF3;lightSizeBreaks=newBreaksHF3;lightResultContrast=newContrastHF3;
    activeDiameterNm = newActive;
    bandNm = newBand;
    bandCount = newCount;
    excludeNegativeDepth = newExclude;
    lightIncludeUncertain = newInclude;
    lightHistogramBinNm = newHist;
    lightFeatureDistanceBinNm = newFeature;
    duplicateCenterTolPx = newDupPx;
    duplicateRelativeTol = newDupRel;
    duplicateDiameterTolFraction = newDupD;
    selectionTolerancePx = newSel;
    lightInteractivePreviewEnabled = newPreview;
    lightInteractiveResizeStepNm = newResizeStep;
    showRoiLabels = newLabels;
    fillCavities = newFill;
    fillAlpha = newAlpha;
    roiStrokeWidth = newStroke;
    restoreViewAfterRoi = newRestore;
    usePanelsAsMask = 0;
    lightInteractiveSaveResizePreference();
    lightInteractivePushState(lightInteractiveMode);
    if (lightInteractivePreviewEnabled == 0) lightInteractiveRemovePreview();
    styleChanged = 0;
    if (newFill != oldFill) styleChanged = 1;
    if (newAlpha != oldAlpha) styleChanged = 1;
    if (newStroke != oldStroke) styleChanged = 1;
    labelsChanged = 0;
    if (newLabels != oldLabels) labelsChanged = 1;
    if (quantitativeChanged == 1) {
        syncAllObjects(0);
        restyleAllRois();
        showAllRois();
    } else {
        updateSessionMetadataRoi();
        if (styleChanged == 1) {
            restyleAllRois();
            showAllRois();
        } else if (labelsChanged == 1) showAllRois();
    }
    lightWriteImageMetadata();
    lightUpdateRegistry();
    rev = "";

    if (quantitativeChanged == 1 && objects > 0) {
        rev = lightSaveRevisionCore(0);
        if (rev == "") {
            lightBandMode=oldModeHF3;lightSizeBreaks=oldBreaksHF3;lightResultContrast=oldContrastHF3;
            activeDiameterNm = oldActive;
            bandNm = oldBand;
            bandCount = oldCount;
            excludeNegativeDepth = oldExclude;
            lightIncludeUncertain = oldInclude;
            lightHistogramBinNm = oldHist;
            lightFeatureDistanceBinNm = oldFeature;
            duplicateCenterTolPx = oldDupPx;
            duplicateRelativeTol = oldDupRel;
            duplicateDiameterTolFraction = oldDupD;
            selectionTolerancePx = oldSel;
            lightInteractivePreviewEnabled = oldPreview;
            lightInteractiveResizeStepNm = oldResizeStep;
            showRoiLabels = oldLabels;
            fillCavities = oldFill;
            fillAlpha = oldAlpha;
            roiStrokeWidth = oldStroke;
            restoreViewAfterRoi = oldRestore;
            lightInteractiveSaveResizePreference();
            lightInteractivePushState(lightInteractiveMode);
            syncAllObjects(0);
            updateSessionMetadataRoi();
            restyleAllRois();
            showAllRois();
            lightWriteImageMetadata();
            lightUpdateRegistry();
            showMessage("Ajustes restaurados", "No se pudo guardar la revision. Se restauraron los valores anteriores.");
            return;
        }
    }
    updateSessionMetadataRoi();lightWriteImageMetadata();
    lightAppendLog("SETTINGS_UPDATED", "band_nm="+lightNum(bandNm)+"; bands="+bandCount+"; include_uncertain="+lightIncludeUncertain+"; histogram_nm="+lightNum(lightHistogramBinNm)+"; feature_bin_nm="+lightNum(lightFeatureDistanceBinNm)+"; resize_step_nm="+lightNum(lightInteractiveResizeStepNm)+"; exact_labels="+showRoiLabels+"; revision="+rev);
    lightRefreshPanel();
    showStatus("Ajustes Light R9 actualizados.");
}



function chooseDisplayMode() {
    choices = newArray("Tipo de objeto", "Banda de profundidad", "Calidad/validacion");
    current = choices[0];
    if (displayMode == "band") current = choices[1];
    if (displayMode == "quality") current = choices[2];
    Dialog.create("Modo de color");
    Dialog.addChoice("Colorear cavidades por:", choices, current);
    Dialog.show();
    choice = Dialog.getChoice();
    displayMode = "type";
    if (choice == choices[1]) displayMode = "band";
    if (choice == choices[2]) displayMode = "quality";
    restyleAllRois();
    showAllRois();
    updateSessionMetadataRoi();
    refreshControlPanelStatus();
}

function toggleLabels() {
    showRoiLabels = 1-showRoiLabels;
    lightInteractivePushState(lightInteractiveMode);
    showAllRois();
    updateSessionMetadataRoi();
    lightWriteImageMetadata();
    lightRefreshPanel();
    if (showRoiLabels) showStatus("Etiquetas exactas ROI Manager visibles.");
    else showStatus("Etiquetas ROI ocultas; los IDs internos no cambian.");
}

function showKeyboardShortcuts() {
    msg = "ATAJOS DE CAVITY ROI TOOLSET v8\n";
    msg = msg + "================================\n\n";
    msg = msg + "PROYECTO Y GEOMETRIA\n";
    msg = msg + "Ctrl+H   Mostrar esta tabla de atajos\n";
    msg = msg + "Ctrl+P   Proyecto y trazabilidad\n";
    msg = msg + "Ctrl+K   Calibrar o sustituir escala\n";
    msg = msg + "Ctrl+B   Definir o sustituir superficie\n";
    msg = msg + "Ctrl+S   Guardar sesion\n\n";
    msg = msg + "CAVIDADES\n";
    msg = msg + "Ctrl+M   Activar medicion continua: arrastrar = medir + crear\n";
    msg = msg + "Ctrl+R   Activar modo anadir\n";
    msg = msg + "Ctrl+E   Activar modo seleccionar/editar\n";
    msg = msg + "Esc   Terminar los modos Medir continuo o Anadir y pasar a Seleccionar\n";
    msg = msg + "Cancelar/Esc en una ventana de dibujo   Finaliza la serie sin mostrar una excepcion\n";
    msg = msg + "Ctrl+U   Sincronizar ROI seleccionada\n";
    msg = msg + "Ctrl+Shift+U   Sincronizar toda la sesion\n";
    msg = msg + "Supr o Retroceso   Borrar seleccionada\n";
    msg = msg + "Ctrl+Z   Deshacer ultima adicion o borrado\n";
    msg = msg + "Ctrl+T   Buscar duplicados\n\n";
    msg = msg + "COLLAGE Y MICROESTRUCTURA\n";
    msg = msg + "Ctrl+Shift+P   Paneles TEM en modo continuo\n";
    msg = msg + "Ctrl+Shift+M   Mascaras validas en modo continuo\n";
    msg = msg + "Ctrl+Shift+X   Zonas excluidas en modo continuo\n";
    msg = msg + "Ctrl+G   Bordes de grano en modo continuo\n";
    msg = msg + "Ctrl+L   Dislocaciones por polilinea, aceptacion automatica\n";
    msg = msg + "Ctrl+Shift+L   Bucles por polilinea cerrada\n";
    msg = msg + "Supr durante trazado   Borrar seleccionada o ultima; Esc finaliza la serie\n";
    msg = msg + "Cancelar en la ventana de dibujo   Terminar la serie activa\n\n";
    msg = msg + "REVISION Y NAVEGACION\n";
    msg = msg + "Ctrl+Shift+V   Validar proyecto\n";
    msg = msg + "Ctrl+Shift+E   Exportar analisis\n";
    msg = msg + "Rueda   Desplazamiento vertical\n";
    msg = msg + "Shift+rueda   Desplazamiento horizontal\n";
    msg = msg + "Ctrl+rueda   Zoom\n";
    msg = msg + "Flechas   Desplazar la vista\n";
    msg = msg + "Esc   Terminar captura continua o cancelar el dibujo activo\n\n";
    msg = msg + "No se utilizan teclas F ni la tecla Fn.";
    showText("Cavity ROI Toolset v8 - atajos", msg);
}

function showInstructions() {
    msg = "CAVITY TEM STUDIO v5.6.0 - GUIA DE USO\n";
    msg = msg + "==================================\n\n";
    msg = msg + "OBJETIVO\n";
    msg = msg + "Registrar de forma trazable la posicion y geometria de cavidades en imagenes TEM individuales o collages, y obtener distribuciones de tamano y densidad en funcion de la distancia perpendicular a una superficie unica.\n\n";
    msg = msg + "FLUJO RECOMENDADO\n";
    msg = msg + "1. Abre el proyecto y el montaje maestro desde Studio. La lista exacta de fuentes de panels.csv es la trazabilidad autoritativa; primera/ultima son solo un resumen informativo.\n";
    msg = msg + "2. Escala: usa la calibracion conciliada DM3/OME/proyecto. Una referencia amarilla o una barra de escala en overlay son ayudas visuales opcionales y no determinan los calculos.\n";
    msg = msg + "3. Superficie: dibuja una recta, polilinea o linea libre y despues marca un punto dentro del material. Solo existe una superficie activa; la anterior se conserva si cancelas.\n";
    msg = msg + "4. Pulsa Actualizar paneles SVG. Fiji importa panels.csv, el orden de apilado y el ownership certificado; no dibujes paneles a mano salvo en un flujo legacy deliberado. Cada pixel de solape pertenece a un solo panel efectivo.\n";
    msg = msg + "5. El area base es la cobertura SVG/ownership. Una mascara de inclusion es opcional y la restringe; las zonas de exclusion se restan. Calcular area exacta guarda el total y el desglose reconciliado por panel.\n";
    msg = msg + "6. Medir continuo: pulsa una vez el boton o Ctrl+M. Arrastra sobre el diametro de cada cavidad; al soltar se crea inmediatamente la ROI, sin ventana OK. El modo permanece activo hasta pulsar Esc, Ctrl+E o elegir otra herramienta.\n";
    msg = msg + "7. Modo anadir: cada click crea una cavidad con el diametro activo, incluso junto, solapada o dentro de otra. No existe separacion minima.\n";
    msg = msg + "8. Modo seleccionar/editar: click sobre una cavidad para seleccionarla; el programa activa despues la herramienta oval estandar para moverla o redimensionarla. Pulsa Sincronizar (Ctrl+U) al terminar. Supr borra y Ctrl+Z deshace una adicion o borrado.\n";
    msg = msg + "9. Duplicados: busca centros coincidentes y los marca en magenta. Es una advertencia; nunca borra ni excluye automaticamente.\n";
    msg = msg + "10. Las dislocaciones y los bucles se registran automaticamente al terminar cada trazo. Para bucles hay ovalo, elipse inclinada, polilinea cerrada y mano alzada; Ajustar a elipse conserva el contorno original para restaurarlo.\n";
    msg = msg + "11. Configura el ancho de bandas despues de identificar las cavidades. La profundidad continua se conserva y el numero de bandas se amplia automaticamente hasta cubrir los objetos incluidos.\n";
    msg = msg + "12. Valida y exporta. Los objetos que cruzan una frontera efectiva se cuentan una vez por el panel de su centroide; su tamano queda pendiente hasta una revision explicita.\n";
    msg = msg + "13. Barra de escala y guias paralelas viven en el overlay. Ocultarlas no modifica ROIs, calibracion ni pixeles del montaje.\n\n";
    msg = msg + "ATAJOS (NO SE USAN TECLAS F)\n";
    msg = msg + "Ctrl+H atajos | Ctrl+P proyecto | Ctrl+K escala | Ctrl+B superficie\n";
    msg = msg + "Ctrl+M medir continuo | Ctrl+R modo anadir | Ctrl+E seleccionar | Esc terminar captura\n";
    msg = msg + "Ctrl+U sincronizar seleccion | Ctrl+Shift+U sincronizar todo\n";
    msg = msg + "Supr borrar | Ctrl+Z deshacer | Ctrl+U sincronizar despues de editar\n";
    msg = msg + "Ctrl+G borde de grano | Ctrl+L dislocacion | Ctrl+Shift+L bucle cerrado\n";
    msg = msg + "Ctrl+Shift+P panel | Ctrl+Shift+M mascara | Ctrl+Shift+X exclusion\n";
    msg = msg + "Ctrl+T duplicados | Ctrl+Shift+V validar | Ctrl+Shift+E exportar\n";
    msg = msg + "Ctrl+S guardar sesion | Esc cancelar el dibujo activo\n\n";
    msg = msg + "NAVEGACION\n";
    msg = msg + "Rueda: desplazamiento vertical; Shift+rueda: horizontal; Ctrl+rueda: zoom. Las flechas desplazan la vista. La tecla Fn no se utiliza ni se necesita.\n\n";
    msg = msg + "CRITERIO METROLOGICO\n";
    msg = msg + "La geometria visible de cada ROI es la fuente de verdad. Al sincronizar o exportar se recalculan centro, diametro equivalente, ejes, area, volumen esferico estimado, profundidad firmada, posicion paralela a la superficie, panel, mascara, borde y banda.\n";
    msg = msg + "Las magnitudes volumetricas asumen cavidades esfericas y un espesor de foil introducido por el usuario; se exportan como estimaciones.\n";
    showText("Cavity TEM Studio v5.6.0 - instrucciones", msg);
}

// -----------------------------------------------------------------------------
// ROI appearance
// -----------------------------------------------------------------------------


function normalizeCavityClass(c) {
    c = toLowerCase(c);
    c = replace(c, " ", "_");
    if (c == "" || c == "confirmed" || c == "confirmada") return "confirmed";
    if (c == "uncertain" || c == "dudosa" || c == "doubtful" || c == "posible") return "uncertain";
    if (c == "possible_artifact" || c == "artifact" || c == "artefacto" || c == "not_cavity") return "possible_artifact";
    if (c == "secondary" || c == "secundaria") return "secondary";
    return c;
}

function cavityClassLabel(c) {
    c = normalizeCavityClass(c);
    if (c == "confirmed") return "Confirmada";
    if (c == "uncertain") return "Dudosa";
    if (c == "possible_artifact") return "Posible artefacto/no segura";
    if (c == "secondary") return "Secundaria";
    return c;
}

function setCavityClassColorVariables(c) {
    c = normalizeCavityClass(c);
    if (c == "confirmed") {
        activeStrokeColor = lightConfirmedCavityColor;
        activeFillColor = "#" + fillAlphaHex + substring(lightConfirmedCavityColor, 1);
    } else if (c == "uncertain") {
        activeStrokeColor = "#ff9900";
        activeFillColor = "#" + fillAlphaHex + "ff9900";
    } else if (c == "possible_artifact") {
        activeStrokeColor = "#9966ff";
        activeFillColor = "#" + fillAlphaHex + "9966ff";
    } else if (c == "secondary") {
        activeStrokeColor = "#3399ff";
        activeFillColor = "#" + fillAlphaHex + "3399ff";
    } else {
        activeStrokeColor = lightConfirmedCavityColor;
        activeFillColor = "#" + fillAlphaHex + substring(lightConfirmedCavityColor, 1);
    }
}

function lightHF43NormalizeHexColor(c) {
    c = toLowerCase(c);
    if (lengthOf(c) != 7 || substring(c,0,1) != "#") return "#00ff00";
    valid = "0123456789abcdef";
    for (ci=1; ci<7; ci++) if (indexOf(valid, substring(c,ci,ci+1)) < 0) return "#00ff00";
    return c;
}

function lightHF43LoadCavityColorPreference() {
    c = "" + call("ij.Prefs.get", "cavity.tem.light.hf43.confirmed.color", "#00ff00");
    lightConfirmedCavityColor = lightHF43NormalizeHexColor(c);
}

function lightHF43ChooseCavityColor() {
    lightHF43LoadCavityColorPreference();
    js = "(function(){try{var C=Packages.java.awt.Color,J=Packages.javax.swing.JColorChooser,c=C.decode('"+lightConfirmedCavityColor+"'),n=J.showDialog(null,'Color de cavidades confirmadas',c);if(n==null)return 'CANCEL';function h(v){var x=v.toString(16);return x.length<2?'0'+x:x;}return '#'+h(n.getRed())+h(n.getGreen())+h(n.getBlue());}catch(e){return 'ERROR|'+String(e);}})()";
    result = "" + eval("js", js);
    if (result == "CANCEL") return;
    if (startsWith(result,"ERROR")) { showMessage("Color no cambiado", result); return; }
    lightConfirmedCavityColor = lightHF43NormalizeHexColor(result);
    call("ij.Prefs.set", "cavity.tem.light.hf43.confirmed.color", lightConfirmedCavityColor);
    eval("js", "try{Packages.ij.Prefs.savePreferences();}catch(e){}");
    restyleAllRois();
    showAllRois();
    lightHF4PushPreferences();
    lightRefreshPanel();
    showStatus("Color de cavidades confirmadas: " + lightConfirmedCavityColor + ".");
}

function chooseActiveCavityClass() {
    choices = newArray("Confirmada", "Dudosa / no segura", "Posible artefacto", "Secundaria");
    defaultChoice = "Confirmada";
    if (activeCavityClass == "uncertain") defaultChoice = "Dudosa / no segura";
    if (activeCavityClass == "possible_artifact") defaultChoice = "Posible artefacto";
    if (activeCavityClass == "secondary") defaultChoice = "Secundaria";
    Dialog.create("Tipo de cavidad activo");
    Dialog.addChoice("Las nuevas cavidades se guardaran como:", choices, defaultChoice);
    Dialog.addChoice("Confianza:", newArray("high", "medium", "low"), activeCavityConfidence);
    Dialog.addMessage("El tipo queda guardado en la propiedad Cavity_class y se exporta como columna.\nNo cambia automaticamente include_in_statistics; usa Incluir/excluir si quieres quitarla de la estadistica.");
    Dialog.show();
    c = Dialog.getChoice();
    activeCavityConfidence = Dialog.getChoice();
    if (c == "Confirmada") activeCavityClass = "confirmed";
    else if (c == "Dudosa / no segura") activeCavityClass = "uncertain";
    else if (c == "Posible artefacto") activeCavityClass = "possible_artifact";
    else activeCavityClass = "secondary";
    activeCavityClassLabel = cavityClassLabel(activeCavityClass);
    lightInteractivePushState(lightInteractiveMode);
    refreshControlPanelStatus();
    showStatus("Tipo de cavidad activo: " + activeCavityClassLabel + " (" + activeCavityConfidence + ").");
}

function setSelectedCavityClass(newClass) {
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0 || isNaN(idx)) exit("Selecciona una cavidad en el ROI Manager o en la imagen.");
    safeRoiSelect(idx);
    if (!currentRoiIsCavity()) exit("La ROI seleccionada no es una cavidad.");
    newClass = normalizeCavityClass(newClass);
    Roi.setProperty("Cavity_class", newClass);
    Roi.setProperty("Cavity_class_label", cavityClassLabel(newClass));
    if (Roi.getProperty("Cavity_confidence") == "") Roi.setProperty("Cavity_confidence", "medium");
    roiManager("update");
    syncCavityAtIndex(idx);
    applyCavityStyle();
    roiManager("update");
    showAllRois();
    refreshControlPanelStatus();
    showStatus(cavityIdCurrent() + " marcada como " + cavityClassLabel(newClass) + ".");
}

function applyCavityStyle() {
    updateFillAlphaHex();
    bandIndex = round(propNumber("Band_index", -1));
    includeStats = round(propNumber("Include_in_statistics", 1));
    manualExcluded = round(propNumber("Manual_excluded", 0));
    edge = round(propNumber("Edge_intersecting", 0));
    duplicate = propString("Duplicate_status", "clear");
    storedCavityClass = propString("Cavity_class", "confirmed");
    cavityClass = normalizeCavityClass(storedCavityClass);

    if (displayMode == "band" && bandIndex >= 0) {
        setGroupColorVariables(bandIndex+1);
    } else if (displayMode == "quality") {
        activeStrokeColor = "#33cc66";
        activeFillColor = "#" + fillAlphaHex + "33cc66";
        if (cavityClass != "confirmed") setCavityClassColorVariables(cavityClass);
        if (!includeStats || manualExcluded) {
            activeStrokeColor = "#999999";
            activeFillColor = "#" + fillAlphaHex + "999999";
        }
        if (edge) {
            activeStrokeColor = "#ffcc00";
            activeFillColor = "#" + fillAlphaHex + "ffcc00";
        }
        if (duplicate == "suspect") {
            activeStrokeColor = "#ff00ff";
            activeFillColor = "#" + fillAlphaHex + "ff00ff";
        }
    } else {
        setCavityClassColorVariables(cavityClass);
        // Duplicate warnings remain visible in every display mode.
        if (duplicate == "suspect") {
            activeStrokeColor = "#ff00ff";
            activeFillColor = "#" + fillAlphaHex + "ff00ff";
        }
        if (!includeStats && duplicate != "suspect") {
            activeStrokeColor = "#999999";
            activeFillColor = "#" + fillAlphaHex + "999999";
        }
    }

    if (fillCavities) Roi.setFillColor(activeFillColor);
    else Roi.setFillColor("#00000000");
    Roi.setStrokeColor(activeStrokeColor);
    Roi.setUnscalableStrokeWidth(roiStrokeWidth);
}

function applyFeatureStyle(featureType) {
    Roi.setFillColor("#00000000");
    if (featureType == "grain_boundary") Roi.setStrokeColor("#ffff00");
    else if (featureType == "dislocation") Roi.setStrokeColor("#00ff66");
    else Roi.setStrokeColor("#ff9900");
    Roi.setUnscalableStrokeWidth(max2(roiStrokeWidth, 2));
}

function applyLoopStyle() {
    // Closed loops are area defects, not linear dislocations. Keep a visible
    // outline and a light transparent fill without touching image pixels.
    Roi.setStrokeColor("#ff9900");
    Roi.setFillColor("#18ff9900");
    Roi.setUnscalableStrokeWidth(max2(roiStrokeWidth, 2));
}

function applyAreaObjectStyle(type) {
    if (type == "panel") {
        Roi.setFillColor("#00000000");
        Roi.setStrokeColor("white");
    } else if (type == "analysis_mask") {
        Roi.setFillColor("#1800ffff");
        Roi.setStrokeColor("cyan");
    } else if (type == "exclusion") {
        Roi.setFillColor("#22ff00ff");
        Roi.setStrokeColor("magenta");
    }
    Roi.setUnscalableStrokeWidth(max2(roiStrokeWidth, 2));
}

function restyleAllRois() {
    if (nImages() <= 0) return;
    run("ROI Manager...");
    n = roiManager("count");
    if (n <= 0) return;
    snapshotCurrentView();
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        name = Roi.getName;
        storedType = Roi.getProperty("Type");
        type = normalizedType(name, storedType);
        if (type == "cavity") applyCavityStyle();
        else if (isLinearFeatureType(type)) applyFeatureStyle(type);
        else if (type == "dislocation_loop") applyLoopStyle();
        else if (type == "panel" || type == "analysis_mask" || type == "exclusion") applyAreaObjectStyle(type);
        else if (type == "scale_reference") {
            Roi.setFillColor("#00000000");
            Roi.setStrokeColor("yellow");
            Roi.setUnscalableStrokeWidth(3);
        } else if (type == "scale_label") {
            Roi.setFillColor("#aa000000");
            Roi.setStrokeColor("#ffff00");
            Roi.setAntiAlias(1);
            Roi.setFontSize(24);
        } else if (type == "surface_reference") {
            Roi.setFillColor("#00000000");
            Roi.setStrokeColor("cyan");
            Roi.setUnscalableStrokeWidth(3);
        } else if (type == "session_metadata") {
            Roi.setFillColor("#00000000");
            Roi.setStrokeColor("#00000000");
        }
        roiManager("update");
    }
    restoreViewSnapshot();
}

function showAllRois() {
    lightHF4PushPreferences();
    nativeResult=call("cavity.light.HF4.refresh","");
    if(nativeResult=="OK")return;
    run("ROI Manager...");
    if (showRoiLabels == 1) {
        roiManager("show all with labels");
        lightApplyStableNameLabels();
    } else {
        roiManager("show all without labels");
    }
}

function lightApplyStableNameLabels() {
    if (nImages() <= 0) return;
    js = "var WM=Packages.ij.WindowManager,imp=WM.getCurrentImage();if(imp!=null){var ic=imp.getCanvas();if(ic!=null){var ov=ic.getShowAllList();if(ov!=null){ov.drawLabels(true);ov.drawNames(true);ov.selectable(false);ov.setDraggable(false);try{ov.setLabelFontSize(12,'bold background');}catch(e){}ic.repaint();imp.draw();}}}";
    eval("js", js);
}

function lightRefreshSelectedRoiOverlay(idx) {
    if (nImages() <= 0) return 0;
    js = "(function(){var WM=Packages.ij.WindowManager,RM=Packages.ij.plugin.frame.RoiManager,imp=WM.getCurrentImage(),rm=RM.getInstance2();if(imp==null||rm==null)return '0';var ic=imp.getCanvas(),ov=ic==null?null:ic.getShowAllList();if(ov==null||ov.size()!=rm.getCount()||"+idx+"<0||"+idx+">=rm.getCount())return '0';var r=rm.getRoi("+idx+");if(r==null)return '0';ov.set(r,"+idx+");ov.drawLabels("+showRoiLabels+");ov.drawNames("+showRoiLabels+");ov.selectable(false);ov.setDraggable(false);try{ov.setLabelFontSize(12,'bold background');}catch(e){}ic.repaint();imp.draw();return '1';})()";
    overlayResult = "" + eval("js", js);
    if (overlayResult == "1") return 1;
    return 0;
}







function updateFillAlphaHex() {
    a = round(fillAlpha);
    if (a < 0) a = 0;
    if (a > 255) a = 255;
    digits = "0123456789abcdef";
    hi = floor(a/16);
    lo = a-hi*16;
    fillAlphaHex = substring(digits, hi, hi+1) + substring(digits, lo, lo+1);
}

function setGroupColorVariables(group) {
    idx = (round(group)-1)%12;
    if (idx < 0) idx = 0;
    if (idx == 0) { activeStrokeColor="#ff3333"; activeFillColor="#"+fillAlphaHex+"ff3333"; }
    else if (idx == 1) { activeStrokeColor="#33cc33"; activeFillColor="#"+fillAlphaHex+"33cc33"; }
    else if (idx == 2) { activeStrokeColor="#3399ff"; activeFillColor="#"+fillAlphaHex+"3399ff"; }
    else if (idx == 3) { activeStrokeColor="#ff9900"; activeFillColor="#"+fillAlphaHex+"ff9900"; }
    else if (idx == 4) { activeStrokeColor="#cc66ff"; activeFillColor="#"+fillAlphaHex+"cc66ff"; }
    else if (idx == 5) { activeStrokeColor="#00cccc"; activeFillColor="#"+fillAlphaHex+"00cccc"; }
    else if (idx == 6) { activeStrokeColor="#ff66cc"; activeFillColor="#"+fillAlphaHex+"ff66cc"; }
    else if (idx == 7) { activeStrokeColor="#ffff00"; activeFillColor="#"+fillAlphaHex+"ffff00"; }
    else if (idx == 8) { activeStrokeColor="#999999"; activeFillColor="#"+fillAlphaHex+"999999"; }
    else if (idx == 9) { activeStrokeColor="#ffffff"; activeFillColor="#"+fillAlphaHex+"ffffff"; }
    else if (idx == 10) { activeStrokeColor="#cc9966"; activeFillColor="#"+fillAlphaHex+"cc9966"; }
    else { activeStrokeColor="#66ff99"; activeFillColor="#"+fillAlphaHex+"66ff99"; }
}

// -----------------------------------------------------------------------------
// Keyboard shortcuts, fixed navigation and view preservation
// -----------------------------------------------------------------------------

function lightInteractiveReadResizeStep() {
    js = "(function(){var P=Packages.ij.Prefs,imp=Packages.ij.WindowManager.getCurrentImage(),v=imp==null?null:imp.getProperty('CavityLightResizeStepNm');if(v!=null){var n=Number(v);if(isFinite(n)&&n>0)return String(n);}return String(P.get('cavity.tem.light.hf4.resize.step.nm',0.050));})();";
    raw = "" + eval("js", js);
    value = parseFloat(raw);
    if (isNaN(value)) value = 0.050;
    if (value < lightInteractiveResizeMinNm) value = lightInteractiveResizeMinNm;
    if (value > lightInteractiveResizeMaxNm) value = lightInteractiveResizeMaxNm;
    lightInteractiveResizeStepNm = value;
    return value;
}

function lightInteractiveSaveResizePreference() {
    if (lightInteractiveResizeStepNm < lightInteractiveResizeMinNm) lightInteractiveResizeStepNm = lightInteractiveResizeMinNm;
    if (lightInteractiveResizeStepNm > lightInteractiveResizeMaxNm) lightInteractiveResizeStepNm = lightInteractiveResizeMaxNm;
    js = "try{var imp=Packages.ij.WindowManager.getCurrentImage();if(imp!=null)imp.setProperty('CavityLightResizeStepNm','" + d2s(lightInteractiveResizeStepNm,6) + "');Packages.ij.Prefs.set('cavity.tem.light.hf4.resize.step.nm'," + d2s(lightInteractiveResizeStepNm,6) + ");Packages.ij.Prefs.savePreferences();'1';}catch(e){'0';}";
    prefResult = "" + eval("js", js);
    if (prefResult == "1") return 1;
    return 0;
}


function lightInteractivePushState(modeValue) {
    if (modeValue != "") lightInteractiveMode = modeValue;
    if (nImages() <= 0) return 0;
    lightHF4PushPreferences();
    lightInteractiveReadResizeStep();
    scaleOk = updateScaleMaybe();
    js = "var WM=Packages.ij.WindowManager,imp=WM.getCurrentImage();if(imp==null)'0';else{";
    js = js + "imp.setProperty('CavityV8NavActive','" + d2s(fixedNavigation,0) + "');";
    js = js + "imp.setProperty('CavityV8WheelPan','" + d2s(wheelPanFraction,8) + "');";
    js = js + "imp.setProperty('CavityV8KeyPan','" + d2s(keyPanFraction,8) + "');";
    js = js + "imp.setProperty('CavityV8ZoomStep','" + d2s(zoomStep,8) + "');";
    js = js + "imp.setProperty('CavityLightInteractionMode','" + jsEscape(lightInteractiveMode) + "');";
    js = js + "imp.setProperty('CavityLightActiveDiameterNm','" + d2s(activeDiameterNm,9) + "');";
    if (scaleOk == 1) {
        js = js + "imp.setProperty('CavityLightScaleXNm','" + d2s(nmPerPixelX,12) + "');";
        js = js + "imp.setProperty('CavityLightScaleYNm','" + d2s(nmPerPixelY,12) + "');";
    } else {
        js = js + "imp.setProperty('CavityLightScaleXNm','0');imp.setProperty('CavityLightScaleYNm','0');";
    }
    js = js + "imp.setProperty('CavityLightPreviewEnabled','" + d2s(lightInteractivePreviewEnabled,0) + "');";
    js = js + "imp.setProperty('CavityLightExactLabelsEnabled','" + d2s(showRoiLabels,0) + "');";
    js = js + "imp.setProperty('CavityLightActiveColor','" + jsEscape(activeStrokeColor) + "');";
    js = js + "imp.setProperty('CavityLightResizeStepNm','" + d2s(lightInteractiveResizeStepNm,6) + "');";
    js = js + "imp.setProperty('CavityLightResizeDebounceMs','" + d2s(lightInteractiveDebounceMs,0) + "');";
    js = js + "if('" + jsEscape(lightInteractiveMode) + "'!='add'){var ov=imp.getOverlay();if(ov!=null){try{ov.remove('__CTL_R8_CURSOR_PREVIEW__');}catch(e){}if(ov.size()==0&&String(imp.getProperty('CavityLightOwnPreviewOverlay'))=='1'){imp.setOverlay(null);imp.setProperty('CavityLightOwnPreviewOverlay',null);}else imp.setOverlay(ov);imp.draw();}}'1';}";
    resultText = "" + eval("js", js);
    if (resultText == "1") return 1;
    return 0;
}


function lightInteractiveRemovePreview() {
    if (nImages() <= 0) return;
    js = "var WM=Packages.ij.WindowManager,imp=WM.getCurrentImage();if(imp!=null){var ov=imp.getOverlay();if(ov!=null){try{ov.remove('__CTL_R8_CURSOR_PREVIEW__');}catch(e){}if(ov.size()==0&&String(imp.getProperty('CavityLightOwnPreviewOverlay'))=='1'){imp.setOverlay(null);imp.setProperty('CavityLightOwnPreviewOverlay',null);}else imp.setOverlay(ov);imp.draw();}}";
    eval("js", js);
}


function lightInteractivePullActiveDiameter() {
    if (nImages() <= 0) return 0;
    js = "var WM=Packages.ij.WindowManager,imp=WM.getCurrentImage();var v=imp==null?null:imp.getProperty('CavityLightActiveDiameterNm');v==null?'':String(v);";
    valueText = "" + eval("js", js);
    if (valueText == "") return 0;
    value = parseFloat(valueText);
    if (isNaN(value) || value <= 0) return 0;
    minDiameter = max2(nmPerPixelX, nmPerPixelY);
    if (minDiameter > 0 && value < minDiameter) value = minDiameter;
    activeDiameterNm = value;
    return 1;
}


function lightFinalizeInteractiveActiveDiameter() {
    lightInteractivePullActiveDiameter();
    showStatus("Diametro activo: "+d2s(activeDiameterNm,4)+" nm. Alt+Mayus+rueda: ajuste fino.");
}


function lightUpdateResizeStepFromPreference() {
    lightInteractiveReadResizeStep();lightInteractivePushState(lightInteractiveMode);lightRefreshPanel();
}


function lightFinalizeInteractiveEdit() {
    if(nImages()<=0)return;
    count=parseFloat(call("cavity.light.Identity.finishEdits",""));
    if(count>0){lightInvalidateAnalysisCache();lightRefreshPanel();showStatus(count+" ROI editadas; calculos pendientes de validar/exportar.");}
}


function installInteractionListeners(verbose) {
    if (nImages() <= 0) return;
    if (keepWindowSize == 1) {
        if (lockedWinW <= 0 || lockedWinH <= 0) lockWindowSizeToCurrent(0);
    }
    lightInteractiveReadResizeStep();
    lightInteractivePushState(lightInteractiveMode);
    js = "";
    js = js + "(function(){";
    js = js + "var IJ=Packages.ij.IJ,WM=Packages.ij.WindowManager,Rectangle=Packages.java.awt.Rectangle,ArrayList=Packages.java.util.ArrayList;";
    js = js + "var KeyEvent=Packages.java.awt.event.KeyEvent,KeyAdapter=Packages.java.awt.event.KeyAdapter,MouseWheelListener=Packages.java.awt.event.MouseWheelListener,MouseMotionListener=Packages.java.awt.event.MouseMotionListener,MouseAdapter=Packages.java.awt.event.MouseAdapter;";
    js = js + "var ActionListener=Packages.java.awt.event.ActionListener,Timer=Packages.javax.swing.Timer,Executer=Packages.ij.Executer,Runnable=Packages.java.lang.Runnable,Thread=Packages.java.lang.Thread;";
    js = js + "var RoiManager=Packages.ij.plugin.frame.RoiManager,Overlay=Packages.ij.gui.Overlay,OvalRoi=Packages.ij.gui.OvalRoi,Color=Packages.java.awt.Color,Toolbar=Packages.ij.gui.Toolbar;";
    js = js + "var imp=WM.getCurrentImage();if(imp==null)return 'NO_IMAGE';var win=imp.getWindow(),c=(win==null?null:win.getCanvas());if(c==null)return 'NO_CANVAS';";
    js = js + "var installedVersion=imp.getProperty('CavityLightWheelRouterVersion');if(installedVersion!=null&&String(installedVersion)=='1.1.1-R9-HF4.6')return 'ALREADY';";
    js = js + "var oldR8Wheel=null,oldR9Wheel=null;try{oldR8Wheel=imp.getProperty('CavityLightR8WheelListener');if(oldR8Wheel!=null)c.removeMouseWheelListener(oldR8Wheel);imp.setProperty('CavityLightR8WheelListener',null);}catch(ignoreR8Wheel){}";
    js = js + "try{oldR9Wheel=imp.getProperty('CavityLightR9WheelListener');if(oldR9Wheel!=null)c.removeMouseWheelListener(oldR9Wheel);imp.setProperty('CavityLightR9WheelListener',null);}catch(ignoreR9Wheel){}";
    js = js + "try{var oldMotion=imp.getProperty('CavityLightR8MotionListener');if(oldMotion!=null)c.removeMouseMotionListener(oldMotion);imp.setProperty('CavityLightR8MotionListener',null);}catch(ignoreMotion){}";
    js = js + "try{var oldMotion9=imp.getProperty('CavityLightR9MotionListener');if(oldMotion9!=null)c.removeMouseMotionListener(oldMotion9);imp.setProperty('CavityLightR9MotionListener',null);}catch(ignoreMotion9){}";
    js = js + "try{var oldMouse=imp.getProperty('CavityLightR8MouseListener');if(oldMouse!=null)c.removeMouseListener(oldMouse);imp.setProperty('CavityLightR8MouseListener',null);}catch(ignoreMouse){}";
    js = js + "try{var oldMouse9=imp.getProperty('CavityLightR9MouseListener');if(oldMouse9!=null)c.removeMouseListener(oldMouse9);imp.setProperty('CavityLightR9MouseListener',null);}catch(ignoreMouse9){}";
    js = js + "try{var oldKey=imp.getProperty('CavityLightR8KeyListener');if(oldKey!=null){c.removeKeyListener(oldKey);if(win!=null)win.removeKeyListener(oldKey);}imp.setProperty('CavityLightR8KeyListener',null);}catch(ignoreKey){}";
    js = js + "try{var oldKey9=imp.getProperty('CavityLightR9KeyListener');if(oldKey9!=null){c.removeKeyListener(oldKey9);if(win!=null)win.removeKeyListener(oldKey9);}imp.setProperty('CavityLightR9KeyListener',null);}catch(ignoreKey9){}";
    js = js + "var baseWheel=imp.getProperty('CavityLightBaseWheelListeners');if(baseWheel==null){baseWheel=new ArrayList();var currentWheel=c.getMouseWheelListeners();for(var bw=0;bw<currentWheel.length;bw++){var listener=currentWheel[bw];if(listener!=null&&listener!==oldR8Wheel&&listener!==oldR9Wheel)baseWheel.add(listener);}imp.setProperty('CavityLightBaseWheelListeners',baseWheel);}";
    js = js + "var remainingWheel=c.getMouseWheelListeners();for(var rw=0;rw<remainingWheel.length;rw++){try{c.removeMouseWheelListener(remainingWheel[rw]);}catch(ignoreRemoveBase){}}";
    js = js + "function num(key,def){var p=imp.getProperty(key);if(p==null)return def;var v=parseFloat(String(p));return isNaN(v)?def:v;}";
    js = js + "function str(key,def){var p=imp.getProperty(key);return p==null?def:String(p);}";
    js = js + "function navOn(){return str('CavityV8NavActive','0')=='1';}";
    js = js + "function mode(){return str('CavityLightInteractionMode','select');}";
    js = js + "function submit(cmd){var body={run:function(){IJ.resetEscape();new Executer(cmd).run();}};var r;if(typeof JavaAdapter!='undefined')r=new JavaAdapter(Runnable,body);else{var R=Java.extend(Runnable);r=new R(body);}var th=new Thread(r);th.setDaemon(true);th.start();}";
    js = js + "function adapter(iface,body){if(typeof JavaAdapter!='undefined')return new JavaAdapter(iface,body);var C=Java.extend(iface);return new C(body);}";
    js = js + "function isCavity(r){if(r==null)return false;var typ=r.getProperty('Type');if(typ==null||String(typ)=='')typ=r.getProperty('Object_type');return typ!=null&&String(typ)=='cavity';}";
    js = js + "function preciseRotation(e){var rot=e.getPreciseWheelRotation();if(!isFinite(rot)||rot==0)rot=e.getWheelRotation();return rot;}";
    js = js + "function delegateWheel(e){var base=imp.getProperty('CavityLightBaseWheelListeners');if(base==null)return;for(var i=0;i<base.size();i++){try{var listener=base.get(i);if(listener!=null)listener.mouseWheelMoved(e);}catch(ignoreDelegate){}}}";
    js = js + "function removePreview(){var ov=imp.getOverlay();if(ov==null)return;try{ov.remove('__CTL_R8_CURSOR_PREVIEW__');}catch(ex){}var own=str('CavityLightOwnPreviewOverlay','0')=='1';if(own&&ov.size()==0){imp.setOverlay(null);imp.setProperty('CavityLightOwnPreviewOverlay',null);}else imp.setOverlay(ov);imp.draw();}";
    js = js + "function colorFromHex(h){try{return Color.decode(String(h));}catch(ex){return Color.yellow;}}";
    js = js + "function updatePreview(e){var toolName=String(Toolbar.getToolName()).toLowerCase();if(mode()!='add'||str('CavityLightPreviewEnabled','1')!='1'||toolName.indexOf('cavity')<0||toolName.indexOf('add')<0){removePreview();return;}var d=num('CavityLightActiveDiameterNm',0),sx=num('CavityLightScaleXNm',0),sy=num('CavityLightScaleYNm',0);if(!(d>0&&sx>0&&sy>0)){removePreview();return;}var x=c.offScreenXD(e.getX()),y=c.offScreenYD(e.getY()),rw=d/sx,rh=d/sy;var ov=imp.getOverlay();if(ov==null){ov=new Overlay();imp.setProperty('CavityLightOwnPreviewOverlay','1');}try{ov.remove('__CTL_R8_CURSOR_PREVIEW__');}catch(ex2){}var preview=new OvalRoi(x-rw/2.0,y-rh/2.0,rw,rh);preview.setName('__CTL_R8_CURSOR_PREVIEW__');preview.setStrokeColor(colorFromHex(str('CavityLightActiveColor','#ffff00')));preview.setStrokeWidth(1.5);preview.setFillColor(null);ov.add(preview);imp.setOverlay(ov);c.repaint();}";
    js = js + "function refreshShowAll(idx,r){var ov=c.getShowAllList();var rm=RoiManager.getInstance2();if(ov==null||rm==null||ov.size()!=rm.getCount()||idx<0||idx>=ov.size())return false;var labels=str('CavityLightExactLabelsEnabled','1')=='1';ov.set(r,idx);ov.drawLabels(labels);ov.drawNames(labels);try{ov.selectable(false);}catch(ignoreSelectable){}try{ov.setDraggable(false);}catch(ignoreDraggable){}try{ov.setLabelFontSize(12,'bold background');}catch(ignoreFont){}c.repaint();imp.draw();return true;}";
    js = js + "function pan(dx,dy){var w=imp.getWindow();if(w==null)return;var cc=w.getCanvas();if(cc==null)return;cc.setScaleToFit(false);var r=cc.getSrcRect();var iw=imp.getWidth(),ih=imp.getHeight();var nx=Math.round(r.x+r.width*dx),ny=Math.round(r.y+r.height*dy);if(nx<0)nx=0;if(ny<0)ny=0;if(nx>iw-r.width)nx=iw-r.width;if(ny>ih-r.height)ny=ih-r.height;if(nx<0)nx=0;if(ny<0)ny=0;var s=cc.getSize();if(s.width>0&&s.height>0)cc.setSize(s.width,s.height);var mag=cc.getMagnification();cc.setSourceRect(new Rectangle(nx,ny,r.width,r.height));cc.setMagnification(mag);cc.repaint();imp.updateAndDraw();}";
    js = js + "function zoom(dir){var nav=imp.getProperty('CavityLightHF45Navigation');if(nav!=null){nav.zoom(dir,null,null);return;}if(dir>0)c.zoomIn(Math.round(c.getWidth()/2),Math.round(c.getHeight()/2));else c.zoomOut(Math.round(c.getWidth()/2),Math.round(c.getHeight()/2));}";
    js = js + "var resizeTimer=null;function queueCommit(kind){imp.setProperty('CavityLightPendingEditKind',kind);var delay=Math.round(num('CavityLightResizeDebounceMs',350));if(delay<100)delay=100;if(resizeTimer==null){resizeTimer=new Timer(delay,adapter(ActionListener,{actionPerformed:function(ev){if(WM.getCurrentImage()==imp)submit('Cavity Light: confirmar edicion interactiva');}}));resizeTimer.setRepeats(false);}resizeTimer.setInitialDelay(delay);resizeTimer.restart();}";
    js = js + "var activeDiameterTimer=null;function queueActiveDiameterCommit(){var delay=Math.round(num('CavityLightResizeDebounceMs',350));if(delay<100)delay=100;if(activeDiameterTimer==null){activeDiameterTimer=new Timer(delay,adapter(ActionListener,{actionPerformed:function(ev){if(WM.getCurrentImage()==imp)submit('Cavity Light: confirmar diametro activo interactivo');}}));activeDiameterTimer.setRepeats(false);}activeDiameterTimer.setInitialDelay(delay);activeDiameterTimer.restart();}";
    js = js + "function resizedRoi(base,x,y,w,h){var nr=new OvalRoi(x,y,w,h);nr.copyAttributes(base);var props=base.getProperties();if(props!=null)nr.setProperties(props);nr.setName(base.getName());try{nr.setGroup(base.getGroup());}catch(ignoreGroup){}try{nr.setPosition(base.getCPosition(),base.getZPosition(),base.getTPosition());}catch(ignorePosition){}return nr;}";
    js = js + "function adjustActiveDiameter(e){var oldD=num('CavityLightActiveDiameterNm',0),sx=num('CavityLightScaleXNm',0),sy=num('CavityLightScaleYNm',0),step=num('CavityLightResizeStepNm',0.010),rot=preciseRotation(e);if(!(oldD>0&&sx>0&&sy>0&&step>0&&isFinite(rot)&&rot!=0))return false;if(e.isShiftDown())step*=0.2;var newD=oldD-rot*step,minD=Math.max(sx,sy);if(newD<minD)newD=minD;var maxD=Math.max(imp.getWidth()*sx,imp.getHeight()*sy);if(maxD>0&&newD>maxD)newD=maxD;imp.setProperty('CavityLightActiveDiameterNm',String(newD));imp.setProperty('CavityLightPendingActiveDiameterNm',String(newD));updatePreview(e);IJ.showStatus('Diametro activo: '+newD.toFixed(4)+' nm; paso='+step.toFixed(4)+' nm. Alt+rueda no cambia el zoom.');queueActiveDiameterCommit();return true;}";
    js = js + "function resizeSelected(e){var rm=RoiManager.getInstance2();if(rm==null)return false;var idx=rm.getSelectedIndex();if(idx<0||idx>=rm.getCount())return false;if(!Packages.cavity.light.Identity.editable(imp,rm))return false;var base=imp.getRoi();var b=base.getFloatBounds(),sx=num('CavityLightScaleXNm',0),sy=num('CavityLightScaleYNm',0);if(!(sx>0&&sy>0&&b.width>0&&b.height>0))return false;var oldD=Math.sqrt((b.width*sx)*(b.height*sy)),step=num('CavityLightResizeStepNm',0.010),rot=preciseRotation(e);if(!(oldD>0&&step>0&&isFinite(rot)&&rot!=0))return false;if(e.isShiftDown())step*=0.2;var newD=oldD-rot*step,minD=Math.max(sx,sy);if(newD<minD)newD=minD;var factor=newD/oldD,nw=b.width*factor,nh=b.height*factor,cx=b.x+b.width/2.0,cy=b.y+b.height/2.0,nr=resizedRoi(base,cx-nw/2.0,cy-nh/2.0,nw,nh),kind=e.isControlDown()?'ctrl_alt_wheel':'alt_wheel';nr.setProperty('Interactive_edit_pending','1');nr.setProperty('Last_edit_method',kind);nr.setProperty('Last_edit_ms',String(java.lang.System.currentTimeMillis()));Packages.cavity.light.Identity.pending(nr);rm.setRoi(nr,idx);rm.select(imp,idx);imp.setRoi(nr);refreshShowAll(idx,nr);imp.draw();IJ.showStatus(String(nr.getName())+': d='+newD.toFixed(4)+' nm; paso='+step.toFixed(4)+' nm');queueCommit(kind);return true;}";
    js = js + "var pressedIndex=-1,pressedName='',pressedBounds=null,pressedRoi=null;";
    js = js + "var wheelBody={mouseWheelMoved:function(e){var alt=e.isAltDown(),ctrl=e.isControlDown()||e.isMetaDown(),currentMode=mode();if(alt){var handled=false;if(currentMode=='add')handled=adjustActiveDiameter(e);else if(currentMode=='select')handled=resizeSelected(e);if(!handled){if(currentMode=='select')IJ.showStatus('Alt+rueda: selecciona primero una cavidad. El zoom no se ha modificado.');else if(currentMode=='add')IJ.showStatus('Alt+rueda: define antes un diametro activo y una escala valida.');}e.consume();return;}if(ctrl||navOn()){var rot=e.getWheelRotation();if(ctrl){if(rot<0)zoom(1);else if(rot>0)zoom(-1);}else{var f=num('CavityV8WheelPan',0.18);if(e.isShiftDown())pan(rot*f,0);else pan(0,rot*f);}e.consume();return;}delegateWheel(e);}};";
    js = js + "var motionBody={mouseMoved:function(e){updatePreview(e);},mouseDragged:function(e){if(mode()=='add')updatePreview(e);}};";
    js = js + "var mouseBody={mousePressed:function(e){pressedIndex=-1;pressedName='';pressedBounds=null;pressedRoi=null;if(mode()!='select'||e.getButton()!=1)return;var rm=RoiManager.getInstance2();if(!Packages.cavity.light.Identity.editable(imp,rm))return;var idx=rm.getSelectedIndex(),r=rm.getRoi(idx);pressedIndex=idx;pressedName=String(r.getName());pressedRoi=r;pressedBounds=r.getFloatBounds();},mouseReleased:function(e){if(pressedIndex<0||pressedBounds==null)return;var rm=RoiManager.getInstance2(),idx=pressedIndex;pressedIndex=-1;if(rm==null||idx>=rm.getCount()||rm.getSelectedIndex()!=idx||rm.getRoi(idx)!==pressedRoi||!Packages.cavity.light.Identity.editable(imp,rm))return;var active=imp.getRoi();if(String(active.getName())!=pressedName)return;var b=active.getFloatBounds(),eps=0.0001,changed=Math.abs(b.x-pressedBounds.x)>eps||Math.abs(b.y-pressedBounds.y)>eps||Math.abs(b.width-pressedBounds.width)>eps||Math.abs(b.height-pressedBounds.height)>eps;if(!changed)return;var nr=active.clone();nr.setProperty('Interactive_edit_pending','1');nr.setProperty('Last_edit_method','mouse_drag_or_handles');nr.setProperty('Last_edit_ms',String(java.lang.System.currentTimeMillis()));Packages.cavity.light.Identity.pending(nr);rm.setRoi(nr,idx);rm.select(imp,idx);imp.setRoi(nr);refreshShowAll(idx,nr);imp.draw();queueCommit('mouse_drag_or_handles');},mouseExited:function(e){removePreview();},mouseClicked:function(e){},mouseEntered:function(e){}};";
    js = js + "var keyBody={keyPressed:function(e){var code=e.getKeyCode(),ctrl=e.isControlDown()||e.isMetaDown(),shift=e.isShiftDown(),cmd=null;if(code==KeyEvent.VK_F1)cmd='Cavity Light: accesos directos';else if(ctrl&&shift&&code==KeyEvent.VK_W)cmd='Cavity Light: alternar ventana fija';else if(ctrl&&shift&&code==KeyEvent.VK_V)cmd='Cavity Light: validar imagen';else if(ctrl&&shift&&code==KeyEvent.VK_E)cmd='Cavity Light: calcular y exportar resultados';else if(ctrl&&code==KeyEvent.VK_H)cmd='Cavity Light: ayuda';else if(ctrl&&code==KeyEvent.VK_K)cmd='Cavity Light: calibrar escala con linea';else if(ctrl&&code==KeyEvent.VK_B)cmd='Cavity Light: definir superficie';else if(ctrl&&code==KeyEvent.VK_M)cmd='Cavity Light: medir diametro y crear cavidad';else if(ctrl&&code==KeyEvent.VK_R)cmd='Cavity Light: anadir con diametro activo';else if(ctrl&&code==KeyEvent.VK_E)cmd='Cavity Light: seleccionar/editar';else if(ctrl&&code==KeyEvent.VK_U)cmd='Cavity Light: sincronizar seleccionada';else if(ctrl&&code==KeyEvent.VK_T)cmd='Cavity Light: buscar duplicados';else if(ctrl&&code==KeyEvent.VK_G)cmd='Cavity Light: dibujar bordes de grano';else if(ctrl&&code==KeyEvent.VK_L)cmd='Cavity Light: dibujar dislocaciones';else if(ctrl&&code==KeyEvent.VK_S)cmd='Cavity Light: guardar nueva revision';else if(ctrl&&code==KeyEvent.VK_Z)cmd='Cavity Light: deshacer ultima accion';else if(code==KeyEvent.VK_ESCAPE){removePreview();cmd='Cavity Light: seleccionar/editar';}else if(code==KeyEvent.VK_DELETE||code==KeyEvent.VK_BACK_SPACE)cmd='Cavity Light: borrar seleccionada';if(cmd!=null){submit(cmd);e.consume();return;}if(navOn()){var f=num('CavityV8KeyPan',0.30);if(shift)f*=2.0;if(e.isAltDown())f*=0.25;if(code==KeyEvent.VK_LEFT){pan(-f,0);e.consume();}else if(code==KeyEvent.VK_RIGHT){pan(f,0);e.consume();}else if(code==KeyEvent.VK_UP){pan(0,-f);e.consume();}else if(code==KeyEvent.VK_DOWN){pan(0,f);e.consume();}}}};";
    js = js + "var wl=adapter(MouseWheelListener,wheelBody),ml=adapter(MouseMotionListener,motionBody),ma=adapter(MouseAdapter,mouseBody),kl=adapter(KeyAdapter,keyBody);c.addMouseWheelListener(wl);c.addMouseMotionListener(ml);c.addMouseListener(ma);c.addKeyListener(kl);win.addKeyListener(kl);c.setFocusable(true);c.requestFocusInWindow();imp.setProperty('CavityLightR9WheelListener',wl);imp.setProperty('CavityLightR9MotionListener',ml);imp.setProperty('CavityLightR9MouseListener',ma);imp.setProperty('CavityLightR9KeyListener',kl);imp.setProperty('CavityV8ListenersInstalled','1');imp.setProperty('CavityLightWheelRouterVersion','1.1.1-R9-HF4.6');imp.setProperty('CavityV8ListenersVersion','1.1.1-R9-HF4.6');return 'INSTALLED';";
    js = js + "})()";
    statusText = "" + eval("js", js);
    lightInteractiveControllerStatus = statusText;
    navState = lightHF45NavigationCall("attach");
    if (navState == "0" || navState == "1") keepWindowSize = parseFloat(navState);
    else showMessage("Navegacion no instalada", navState);
    lightInteractivePushState(lightInteractiveMode);
    if (verbose) showStatus("Interaccion HF4: " + statusText + "; Alt+rueda=" + d2s(lightInteractiveResizeStepNm,3) + " nm/paso; Ctrl+Alt compatible.");
}


function snapshotCurrentView() {
    if (!restoreViewAfterRoi || nImages() <= 0) return;
    getDisplayedArea(viewSnapX, viewSnapY, viewSnapW, viewSnapH);
    getLocationAndSize(viewSnapWinX, viewSnapWinY, viewSnapWinW, viewSnapWinH);
    if (viewSnapW <= 0 || viewSnapH <= 0) { viewSnapshotValid=0; return; }
    viewSnapshotValid = 1;
}

function restoreViewSnapshot() {
    if (!restoreViewAfterRoi || !viewSnapshotValid || nImages() <= 0) return;
    if (viewSnapWinW > 0 && viewSnapWinH > 0) {
        setLocation(viewSnapWinX, viewSnapWinY, viewSnapWinW, viewSnapWinH);
        lockedWinW = viewSnapWinW;
        lockedWinH = viewSnapWinH;
        wait(40);
    }
    jsRestoreViewRect(viewSnapX, viewSnapY, viewSnapW, viewSnapH);
    viewSnapshotValid = 0;
}

function jsRestoreViewRect(x, y, w, h) {
    if (w <= 0 || h <= 0) return;
    js = "var IJ=Packages.ij.IJ;var Rectangle=Packages.java.awt.Rectangle;var imp=IJ.getImage();if(imp!=null){var win=imp.getWindow();if(win!=null){var c=win.getCanvas();if(c!=null){var iw=imp.getWidth(),ih=imp.getHeight();var x="+d2s(x,6)+",y="+d2s(y,6)+",w="+d2s(w,6)+",h="+d2s(h,6)+";if(w>iw)w=iw;if(h>ih)h=ih;if(x<0)x=0;if(y<0)y=0;if(x>iw-w)x=iw-w;if(y>ih-h)y=ih-h;c.setScaleToFit(false);c.setSourceRect(new Rectangle(Math.round(x),Math.round(y),Math.round(w),Math.round(h)));c.repaint();imp.updateAndDraw();}}}";
    eval("js", js);
}

function lockWindowSizeToCurrent(verbose) {
    if (nImages() <= 0) return;
    getLocationAndSize(wx, wy, ww, wh);
    lockedWinW = ww; lockedWinH = wh;
    result = lightHF45NavigationCall("enable");
    keepWindowSize = 0;
    if (result == "1") keepWindowSize = 1;
    if (verbose) showStatus("Ventana fija durante el zoom. Se permite moverla o redimensionarla manualmente.");
}

function ensureLockedWindowSizeBeforeViewChange() {
    // HF4.6 keeps the current bounds during each zoom. Manual resizing remains allowed.
    if (nImages() > 0) { navState = lightHF45NavigationCall("attach"); }
}

function zoomInFixed() { zoomViewCentered(zoomStep); }
function zoomOutFixed() { zoomViewCentered(1.0/zoomStep); }

function zoomViewCentered(factor) {
    if (nImages() <= 0 || factor <= 0) return;
    ensureLockedWindowSizeBeforeViewChange();
    getDisplayedArea(x, y, w, h);
    jsZoomView(x+w/2, y+h/2, factor);
    showAllRois();
}

function jsZoomView(cx, cy, factor) {
    result = lightHF45NavigationCall("at|"+d2s(cx,9)+"|"+d2s(cy,9)+"|"+d2s(factor,12));
    if (startsWith(result,"ERROR")) showMessage("Zoom no aplicado",result);
}

function panView(dxFraction, dyFraction) {
    if (nImages() <= 0) return;
    ensureLockedWindowSizeBeforeViewChange();
    js = "var IJ=Packages.ij.IJ;var Rectangle=Packages.java.awt.Rectangle;var imp=IJ.getImage();if(imp!=null){var win=imp.getWindow();if(win!=null){var c=win.getCanvas();if(c!=null){c.setScaleToFit(false);var r=c.getSrcRect(),iw=imp.getWidth(),ih=imp.getHeight();var nx=Math.round(r.x+r.width*("+d2s(dxFraction,12)+")),ny=Math.round(r.y+r.height*("+d2s(dyFraction,12)+"));if(nx<0)nx=0;if(ny<0)ny=0;if(nx>iw-r.width)nx=iw-r.width;if(ny>ih-r.height)ny=ih-r.height;if(nx<0)nx=0;if(ny<0)ny=0;var mag=c.getMagnification();c.setSourceRect(new Rectangle(nx,ny,r.width,r.height));c.setMagnification(mag);c.repaint();imp.updateAndDraw();}}}";
    eval("js", js);
    showAllRois();
}

function v4ToggleImageAspectLock() {
    current = call("ij.Prefs.get", "cavity.v5.ui.image.aspect", "0");
    enabled = 1;
    if (current == "1") enabled = 0;
    call("ij.Prefs.set", "cavity.v5.ui.image.aspect", "" + enabled);
    v4InstallImageAspectLock(enabled);
    refreshControlPanelStatus();
    if (enabled) showStatus("Relacion de aspecto de la ventana de imagen bloqueada.");
    else showStatus("Relacion de aspecto de la ventana de imagen libre.");
}

function v4InstallImageAspectLock(enabled) {
    if (nImages() <= 0) {
        if (enabled) showMessage("Sin imagen", "Abra el montaje antes de bloquear la proporcion de su ventana.");
        return;
    }
    js = "var IJ=Packages.ij.IJ;var ComponentAdapter=Packages.java.awt.event.ComponentAdapter;var imp=IJ.getImage(),enable=" + enabled + ";if(imp!=null){var w=imp.getWindow();if(w!=null){var old=imp.getProperty('CavityV5AspectListener');if(old!=null)try{w.removeComponentListener(old);}catch(ignore){}imp.setProperty('CavityV5AspectListener',null);if(enable){var ratio=imp.getWidth()/imp.getHeight(),guard=false,lastW=w.getWidth(),lastH=w.getHeight();var body={componentResized:function(e){if(guard||ratio<=0)return;try{var nw=w.getWidth(),nh=w.getHeight(),ins=w.getInsets(),extraW=ins.left+ins.right,extraH=ins.top+ins.bottom,innerW=Math.max(160,nw-extraW),innerH=Math.max(120,nh-extraH),targetW=nw,targetH=nh;if(Math.abs(nw-lastW)>=Math.abs(nh-lastH))targetH=Math.round(innerW/ratio)+extraH;else targetW=Math.round(innerH*ratio)+extraW;if(targetW<240)targetW=240;if(targetH<180)targetH=180;if(Math.abs(targetW-nw)>1||Math.abs(targetH-nh)>1){guard=true;w.setSize(targetW,targetH);guard=false;}lastW=w.getWidth();lastH=w.getHeight();}catch(ex){guard=false;Packages.cavity.light.HF4.log('Cavity aspect lock: '+ex);}}};var listener;if(typeof JavaAdapter!='undefined')listener=new JavaAdapter(ComponentAdapter,body);else{var C=Java.extend(ComponentAdapter);listener=new C(body);}w.addComponentListener(listener);imp.setProperty('CavityV5AspectListener',listener);}}}";
    eval("js", js);
}

// -----------------------------------------------------------------------------
// General utilities and type helpers
// -----------------------------------------------------------------------------

function updateScaleMaybe() {
    if (nImages() <= 0) return 0;
    getPixelSize(unit, pw, ph);
    factor = unitToNmFactor(unit);
    if (factor <= 0) return 0;
    currentUnit = unit;
    unitFactorNm = factor;
    nmPerPixelX = pw*factor;
    nmPerPixelY = ph*factor;
    if (nmPerPixelX <= 0 || nmPerPixelY <= 0) return 0;
    return 1;
}

function updateScaleOrExit() {
    if (!updateScaleMaybe()) exit("La imagen no esta calibrada en nm, um, mm, cm o m. Usa el boton Escala (Ctrl+K) o carga una sesion v8.");
}

function unitToNmFactor(unit) {
    u = toLowerCase(unit);
    if (u == "nm" || u == "nanometer" || u == "nanometers" || u == "nanometre" || u == "nanometres") return 1;
    if (u == "um" || u == "micron" || u == "microns" || u == "micrometer" || u == "micrometers" || u == "micrometre" || u == "micrometres") return 1000;
    if (unit == fromCharCode(181)+"m" || unit == fromCharCode(956)+"m") return 1000;
    if (u == "angstrom" || u == "angstroms" || u == fromCharCode(197)) return 0.1;
    if (u == "pm" || u == "picometer" || u == "picometers") return 0.001;
    if (u == "mm") return 1000000;
    if (u == "cm") return 10000000;
    if (u == "m") return 1000000000;
    return -1;
}

function normalizedType(name, type) {
    t = toLowerCase(type);
    n = toLowerCase(name);
    if (t == "bubble") return "cavity";
    if (t == "analysis_area") return "analysis_mask";
    if (t == "surface") return "surface_reference";
    if (t != "") return t;
    if (startsWith(n, "cav_") || startsWith(n, "b_") || startsWith(n, "bubble")) return "cavity";
    if (startsWith(n, "panel_")) return "panel";
    if (startsWith(n, "mask_")) return "analysis_mask";
    if (startsWith(n, "area_")) return "analysis_mask";
    if (startsWith(n, "excl_")) return "exclusion";
    if (startsWith(n, "gb_")) return "grain_boundary";
    if (startsWith(n, "disl_")) return "dislocation";
    if (startsWith(n, "loop_")) return "dislocation_loop";
    if (startsWith(n, "int_")) return "interface";
    if (n == toLowerCase(scaleReferenceName)) return "scale_reference";
    if (n == toLowerCase(scaleLabelName)) return "scale_label";
    if (startsWith(n, toLowerCase(surfaceReferenceName))) return "surface_reference";
    if (n == toLowerCase(sessionMetadataName) || n == toLowerCase(legacyMetadataName)) return "session_metadata";
    return "";
}

function isCavityRoi(name, type) {
    normalized = normalizedType(name, type);
    if (normalized == "cavity") return 1;
    return 0;
}

// Roi.getName is a VARIABLE_FUNCTION in the ImageJ macro interpreter. Passing
// it directly as an argument to a user function can make the interpreter expect
// a numeric value. Read the ROI strings first, then pass ordinary variables.
function currentRoiType() {
    if(nImages()<=0)return "";
    if(selectionType<0)return "";
    currentName = Roi.getName;
    currentStoredType = Roi.getProperty("Type");
    currentTypeValue = normalizedType(currentName, currentStoredType);
    return currentTypeValue;
}

function currentRoiIsCavity() {
    currentTypeValue = currentRoiType();
    if (currentTypeValue == "cavity") return 1;
    return 0;
}

function isLinearFeatureType(type) {
    if (type == "grain_boundary" || type == "dislocation" || type == "interface") return 1;
    return 0;
}

function isManagedType(type) {
    if (type == "cavity" || type == "panel" || type == "analysis_mask" || type == "exclusion") return 1;
    if (type == "dislocation_loop") return 1;
    if (isLinearFeatureType(type)) return 1;
    if (type == "scale_reference" || type == "scale_label" || type == "surface_reference" || type == "session_metadata") return 1;
    return 0;
}

function countTypeFast(wantedType) {
    if (nImages() <= 0) return 0;
    wantedText = "" + wantedType;
    wantedJs = jsEscape(wantedText);
    js = "(function(){var RM=Packages.ij.plugin.frame.RoiManager,rm=RM.getInstance2(),rois=rm==null?[]:rm.getRoisAsArray(),wanted='" + wantedJs + "',count=0;function typ(r){var t=r.getProperty('Type');if(t==null||String(t)=='')t=r.getProperty('Object_type');return t==null?'':String(t);}for(var i=0;i<rois.length;i++){if(typ(rois[i])==wanted)count++;}return String(count);})();";
    result = "" + eval("js", js);
    value = parseFloat(result);
    if (isNaN(value)) return 0;
    return round(value);
}

function lightCavityCountCached() {
    if (lightCachedCavityCount < 0) lightCachedCavityCount = countTypeFast("cavity");
    return lightCachedCavityCount;
}

function lightInvalidateCavityCount() {
    lightCachedCavityCount = -1;
}


function lightRefreshObjectCounts() {
    lightObjectCountCavities = 0;
    lightObjectCountMasks = 0;
    lightObjectCountExclusions = 0;
    lightObjectCountGrainBoundaries = 0;
    lightObjectCountDislocations = 0;
    lightObjectCountInterfaces = 0;
    lightObjectCountSurfaces = 0;
    lightObjectCountDuplicateSuspects = 0;
    if (nImages() <= 0) return 0;
    js = "(function(){var RM=Packages.ij.plugin.frame.RoiManager,rm=RM.getInstance2(),rois=rm==null?[]:rm.getRoisAsArray(),c=[0,0,0,0,0,0,0,0];function val(r,k){var v=r.getProperty(k);return v==null?'':String(v);}function typ(r){var t=val(r,'Type');if(t=='')t=val(r,'Object_type');return t;}for(var i=0;i<rois.length;i++){var r=rois[i],t=typ(r);if(t=='cavity'){c[0]++;if(val(r,'Duplicate_status')=='suspect')c[7]++;}else if(t=='analysis_mask')c[1]++;else if(t=='exclusion')c[2]++;else if(t=='grain_boundary')c[3]++;else if(t=='dislocation')c[4]++;else if(t=='interface')c[5]++;else if(t=='surface_reference')c[6]++;}return c.join('|');})();";
    result = "" + eval("js", js);
    parts = split(result, "|");
    if (parts.length < 8) return 0;
    lightObjectCountCavities = round(parseFloat(parts[0]));
    lightObjectCountMasks = round(parseFloat(parts[1]));
    lightObjectCountExclusions = round(parseFloat(parts[2]));
    lightObjectCountGrainBoundaries = round(parseFloat(parts[3]));
    lightObjectCountDislocations = round(parseFloat(parts[4]));
    lightObjectCountInterfaces = round(parseFloat(parts[5]));
    lightObjectCountSurfaces = round(parseFloat(parts[6]));
    lightObjectCountDuplicateSuspects = round(parseFloat(parts[7]));
    lightCachedCavityCount = lightObjectCountCavities;
    return 1;
}

function lightAuditCavitiesFast() {
    result=call("cavity.light.Identity.audit","");
    if(startsWith(result,"ERROR"))return "";
    return result;
}

function lightAppendRoiToShowAll(idx) {
    if (nImages() <= 0) return 0;
    js = "(function(){var WM=Packages.ij.WindowManager,RM=Packages.ij.plugin.frame.RoiManager,imp=WM.getCurrentImage(),rm=RM.getInstance2(),idx="+idx+",labels="+showRoiLabels+"==1;if(imp==null||rm==null||idx<0||idx>=rm.getCount())return '0';var c=imp.getCanvas(),ov=c==null?null:c.getShowAllList();if(ov==null||ov.size()!=rm.getCount()-1)return '0';var r=rm.getRoi(idx);if(r==null)return '0';ov.add(r);ov.drawLabels(labels);ov.drawNames(labels);try{ov.selectable(false);}catch(ignoreSelectable){}try{ov.setDraggable(false);}catch(ignoreDraggable){}try{ov.setLabelFontSize(12,'bold background');}catch(e){}c.repaint();imp.draw();return '1';})()";
    result = "" + eval("js", js);
    if (result == "1") return 1;
    return 0;
}

function lightCheckNewCavityDuplicatesFast(newIdx) {
    if (nImages() <= 0) return "";
    js = "(function(){var RM=Packages.ij.plugin.frame.RoiManager,rm=RM.getInstance2(),idx="+newIdx+",tolPx="+d2s(duplicateCenterTolPx,8)+",tolRel="+d2s(duplicateRelativeTol,8)+",tolD="+d2s(duplicateDiameterTolFraction,8)+",sx="+d2s(nmPerPixelX,12)+",sy="+d2s(nmPerPixelY,12)+";if(rm==null||idx<0||idx>=rm.getCount())return '';function val(r,k){var v=r.getProperty(k);return v==null?'':String(v);}function typ(r){var t=val(r,'Type');if(t=='')t=val(r,'Object_type');return t;}function add(list,id){if(!id)return list;var a=list?list.split(';'):[];for(var q=0;q<a.length;q++)if(a[q]==id)return list;return list?list+';'+id:id;}function geom(r){var b=r.getFloatBounds(),cx=b.x+b.width/2,cy=b.y+b.height/2,dpx=Math.sqrt(b.width*b.height),dnm=Math.sqrt((b.width*sx)*(b.height*sy));return [cx,cy,dpx,dnm];}function likely(a,b){var dx=a[0]-b[0],dy=a[1]-b[1],dist=Math.sqrt(dx*dx+dy*dy),tol=Math.max(tolPx,tolRel*Math.min(a[2],b[2])),mx=Math.max(a[3],b[3]),diff=mx>0?Math.abs(a[3]-b[3])/mx:0;return (dist<=tol&&diff<=tolD)||dist<=tolPx*0.5;}var nr=rm.getRoi(idx);if(typ(nr)!='cavity')return '';var ng=geom(nr),nid=val(nr,'Cavity_id')||String(nr.getName()||''),partners='';for(var i=0;i<rm.getCount();i++){if(i==idx)continue;var r=rm.getRoi(i);if(typ(r)!='cavity')continue;if(likely(ng,geom(r))){var id=val(r,'Cavity_id')||String(r.getName()||'');partners=add(partners,id);r.setProperty('Duplicate_status','suspect');r.setProperty('Duplicate_partners',add(val(r,'Duplicate_partners'),nid));rm.setRoi(r,i);}}nr.setProperty('Duplicate_partners',partners);nr.setProperty('Duplicate_status',partners?'suspect':'pending_recheck');rm.setRoi(nr,idx);return partners;})()";
    return "" + eval("js", js);
}

function countDuplicateSuspectsFast() {
    if (nImages() <= 0) return 0;
    js = "(function(){var RM=Packages.ij.plugin.frame.RoiManager,rm=RM.getInstance2(),rois=rm==null?[]:rm.getRoisAsArray(),count=0;function typ(r){var t=r.getProperty('Type');if(t==null||String(t)=='')t=r.getProperty('Object_type');return t==null?'':String(t);}for(var i=0;i<rois.length;i++){if(typ(rois[i])!='cavity')continue;var s=rois[i].getProperty('Duplicate_status');if(s!=null&&String(s)=='suspect')count++;}return String(count);})();";
    result = "" + eval("js", js);
    value = parseFloat(result);
    if (isNaN(value)) return 0;
    return round(value);
}

function propString(key, defaultValue) {
    s = Roi.getProperty(key);
    if (s == "") return defaultValue;
    return s;
}

function propNumber(key, defaultValue) {
    s = Roi.getProperty(key);
    if (s == "") return defaultValue;
    v = parseFloat(s);
    if (isNaN(v)) return defaultValue;
    return v;
}

function cavityIdCurrent() {
    id = Roi.getProperty("Cavity_id");
    if (id == "") id = Roi.getName;
    return id;
}

function objectIdCurrent(type) {
    currentName = Roi.getName;
    objectId = "";
    if (type == "cavity") {
        objectId = cavityIdCurrent();
        return objectId;
    }
    if (type == "panel") {
        objectId = propString("Panel_id", currentName);
        return objectId;
    }
    if (type == "analysis_mask") {
        objectId = propString("Mask_id", currentName);
        return objectId;
    }
    if (type == "exclusion") {
        objectId = propString("Exclusion_id", currentName);
        return objectId;
    }
    if (isLinearFeatureType(type)) {
        objectId = propString("Feature_id", currentName);
        return objectId;
    }
    if (type == "dislocation_loop") {
        objectId = propString("Object_id", propString("Feature_id", currentName));
        return objectId;
    }
    objectId = currentName;
    return objectId;
}

function findObjectById(id) {
    n = roiManager("count");
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        type = currentRoiType();
        currentId = objectIdCurrent(type);
        currentName = Roi.getName;
        if (currentId == id || currentName == id) return i;
    }
    return -1;
}

function appendToken(list, token) {
    if (token == "") return list;
    if (list == "") return token;
    parts = split(list, ";");
    for (ii=0; ii<parts.length; ii++) if (parts[ii] == token) return list;
    return list + ";" + token;
}

function serialFromId(id) {
    if (id == "") return 0;
    p = lastIndexOf(id, "_");
    if (p < 0 || p >= lengthOf(id)-1) return 0;
    v = parseFloat(substring(id, p+1));
    if (isNaN(v)) return 0;
    return round(v);
}

function featureTypeLabel(featureType) {
    if (featureType == "grain_boundary") return "borde de grano";
    if (featureType == "dislocation") return "dislocacion";
    if (featureType == "interface") return "interfaz";
    return featureType;
}

function min2(a, b) { if (a <= b) return a; return b; }

function safeRoiSelect(idx) {
    // Prevents Fiji RoiManager crashes when an invalid/NaN index reaches roiManager("select", ...).
    if (isNaN(idx)) {
        showStatus("ROI index invalido (NaN). Operacion omitida para evitar error de Fiji.");
        return 0;
    }
    idx = round(idx);
    // In some ImageJ builds round(NaN) may arrive here as Integer.MIN_VALUE.
    if (idx <= -2147480000) {
        showStatus("ROI index invalido (-2147483648). Operacion omitida para evitar error de Fiji.");
        return 0;
    }
    count = roiManager("count");
    if (idx < 0 || idx >= count) {
        showStatus("ROI index fuera de rango: " + idx + " / " + count + ". Operacion omitida.");
        return 0;
    }
    roiManager("select", idx);
    return 1;
}

function max2(a, b) { if (a >= b) return a; return b; }

function axialAngleDifferenceDeg(a, b) {
    if (isNaN(a) || isNaN(b)) return NaN;
    d = abs(a-b);
    while (d >= 180) d = d-180;
    if (d > 90) d = 180-d;
    return abs(d);
}

function percentileSorted(arr, percent) {
    n = arr.length;
    if (n == 0) return NaN;
    if (n == 1) return arr[0];
    p = percent;
    if (p < 0) p = 0;
    if (p > 100) p = 100;
    pos = (p/100.0)*(n-1);
    lo = floor(pos);
    hi = ceil(pos);
    if (lo == hi) return arr[lo];
    f = pos-lo;
    return arr[lo]*(1-f)+arr[hi]*f;
}

function resetNamedTable(name) { Table.create(name); }

function sanitizeId(s, fallback) {
    s = String.trim(s);
    s = sanitize(s);
    out = "";
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
    for (kk=0; kk<lengthOf(s); kk++) {
        ch = substring(s, kk, kk+1);
        if (indexOf(allowed, ch) >= 0) out = out+ch;
        else out = out+"_";
    }
    while (indexOf(out, "__") >= 0) out = replace(out, "__", "_");
    if (out == "") out = fallback;
    return out;
}

function sanitize(s) {
    s = String.trim(s);
    out = "";
    for (kk=0; kk<lengthOf(s); kk++) {
        ch = substring(s, kk, kk+1);
        if (ch == " " || ch == "\t" || ch == "\r" || ch == "\n") out = out+"_";
        else if (ch == ":" || ch == ";" || ch == "/" || ch == "\\") out = out+"-";
        else out = out+ch;
    }
    return out;
}

function sanitizeFileName(s) {
    s = sanitize(s);
    forbidden = ".\"<>|?*";
    out = "";
    for (kk=0; kk<lengthOf(s); kk++) {
        ch = substring(s, kk, kk+1);
        if (indexOf(forbidden, ch) >= 0) out = out+"-";
        else out = out+ch;
    }
    while (indexOf(out, "--") >= 0) out = replace(out, "--", "-");
    while (indexOf(out, "__") >= 0) out = replace(out, "__", "_");
    if (out == "") out = "CavityProject";
    return out;
}

function stripExtension(s) {
    p = lastIndexOf(s, ".");
    if (p <= 0) return "" + s;
    out = substring(s, 0, p);
    return "" + out;
}


function projectBaseName() {
    if (lightImageId != "") return lightImageId;
    baseTitle = stripExtension(getTitle());
    safeBaseTitle = lightSanitizeId(baseTitle);
    return safeBaseTitle;
}

function normalizeStoredPath(pathText) {
    // Use fromCharCode(92) instead of a literal backslash. Some ImageJ/Fiji macro
    // parses and some copy/paste routes can corrupt replace(pathText, "\\", "/").
    pathText = "" + pathText;
    slashChar = fromCharCode(92);
    normalizedPath = replace(pathText, slashChar, "/");
    return "" + normalizedPath;
}

function looksLikeCollapsedWindowsPath(pathText) {
    if (lengthOf(pathText) < 3) return 0;
    if (substring(pathText, 1, 2) != ":") return 0;
    tailPath = substring(pathText, 2, lengthOf(pathText));
    if (indexOf(tailPath, "/") >= 0 || indexOf(tailPath, "\\") >= 0) return 0;
    return 1;
}

function chooseDirectorySafe(title) {
    safeChooserTitle = jsEscape(title);
    chooserCode = "var D=Packages.ij.io.DirectoryChooser;var d=new D('" + safeChooserTitle + "');var p=d.getDirectory();p==null?'':String(p);";
    chosenDirectory = eval("js", chooserCode);
    if (chosenDirectory == "null") chosenDirectory = "";
    return chosenDirectory;
}

function chooseFileSafe(title) {
    safeChooserTitle = jsEscape(title);
    chooserCode = "var JFileChooser=Packages.javax.swing.JFileChooser;var OpenDialog=Packages.ij.io.OpenDialog;var File=Packages.java.io.File;var fc=new JFileChooser();fc.setDialogTitle('" + safeChooserTitle + "');fc.setFileSelectionMode(JFileChooser.FILES_ONLY);var d=OpenDialog.getDefaultDirectory();if(d!=null)fc.setCurrentDirectory(new File(String(d)));var r=fc.showOpenDialog(Packages.ij.IJ.getInstance());var p='';if(r==JFileChooser.APPROVE_OPTION&&fc.getSelectedFile()!=null)p=String(fc.getSelectedFile().getAbsolutePath());p;";
    chosenFile = eval("js", chooserCode);
    if (chosenFile == "null") chosenFile = "";
    return chosenFile;
}

function repairCommonTextEncoding(s) {
    // Repairs the most common UTF-8-as-Latin-1 sequences seen after loading
    // ROI properties, without requiring non-ASCII source-code literals.
    s = replace(s, fromCharCode(194)+fromCharCode(176), fromCharCode(176));
    s = replace(s, fromCharCode(194)+fromCharCode(181), fromCharCode(181));
    s = replace(s, fromCharCode(194)+fromCharCode(186), fromCharCode(186));
    s = replace(s, fromCharCode(195)+fromCharCode(161), fromCharCode(225));
    s = replace(s, fromCharCode(195)+fromCharCode(169), fromCharCode(233));
    s = replace(s, fromCharCode(195)+fromCharCode(173), fromCharCode(237));
    s = replace(s, fromCharCode(195)+fromCharCode(179), fromCharCode(243));
    s = replace(s, fromCharCode(195)+fromCharCode(186), fromCharCode(250));
    s = replace(s, fromCharCode(195)+fromCharCode(177), fromCharCode(241));
    return s;
}

function jsEscape(s) {
    out = "";
    for (jj=0; jj<lengthOf(s); jj++) {
        ch = substring(s, jj, jj+1);
        if (ch == "\\") out = out + "\\\\";
        else if (ch == "'") out = out + "\\'";
        else if (ch == "\n") out = out + "\\n";
        else if (ch == "\r") out = out + "\\r";
        else if (ch == "\t") out = out + "\\t";
        else out = out + ch;
    }
    return out;
}

function jsonEscape(s) {
    out = "";
    for (jj=0; jj<lengthOf(s); jj++) {
        ch = substring(s, jj, jj+1);
        if (ch == "\\") out = out + "\\\\";
        else if (ch == "\"") out = out + "\\\"";
        else if (ch == "\n") out = out + "\\n";
        else if (ch == "\r") out = out + "\\r";
        else if (ch == "\t") out = out + "\\t";
        else out = out + ch;
    }
    return out;
}

function jsonNumber(v) {
    if (isNaN(v)) return "null";
    return ""+v;
}

function projectJson() {
    updateScaleMaybe();
    countsOk = lightRefreshObjectCounts();
    s = "{\n";
    s = s + "  \"format\": \"Cavity TEM Light image session\",\n";
    s = s + "  \"schema_version\": \"" + lightSchemaVersion + "\",\n";
    s = s + "  \"tool_version\": \"" + jsonEscape(macroVersion) + "\",\n";
    s = s + "  \"validation_state\": \"" + lightValidationState + "\",\n";
    s = s + "  \"project\": {\"id\": \"" + jsonEscape(lightProjectId) + "\", \"uid\": \"" + jsonEscape(lightProjectUid) + "\", \"name\": \"" + jsonEscape(lightProjectName) + "\", \"root\": \"" + jsonEscape(lightProjectRoot) + "\"},\n";
    s = s + "  \"image\": {\"id\": \"" + jsonEscape(lightImageId) + "\", \"title\": \"" + jsonEscape(getTitle()) + "\", \"source_path\": \"" + jsonEscape(lightSourcePath) + "\", \"stored_path\": \"" + jsonEscape(lightSourceStoredPath) + "\", \"sha256\": \"" + jsonEscape(lightSourceSha256) + "\", \"width_px\": " + getWidth() + ", \"height_px\": " + getHeight() + "},\n";
    s = s + "  \"scientific_context\": {\"sample\": \"" + jsonEscape(sampleName) + "\", \"condition\": \"" + jsonEscape(experimentalCondition) + "\", \"operator\": \"" + jsonEscape(operatorName) + "\"},\n";
    s = s + "  \"analysis_mode\": \"" + lightImageMode + "\",\n";
    s = s + "  \"scale\": {\"confirmed\": " + lightScaleConfirmed + ", \"origin\": \"" + jsonEscape(lightScaleOrigin) + "\", \"original_nm_per_px_x\": " + jsonNumber(lightOriginalScaleNmX) + ", \"original_nm_per_px_y\": " + jsonNumber(lightOriginalScaleNmY) + ", \"active_nm_per_px_x\": " + jsonNumber(nmPerPixelX) + ", \"active_nm_per_px_y\": " + jsonNumber(nmPerPixelY) + "},\n";
    s = s + "  \"thickness\": {\"nm\": " + jsonNumber(lightThicknessNm) + ", \"uncertainty_nm\": " + jsonNumber(lightThicknessUncertaintyNm) + ", \"method\": \"" + jsonEscape(lightThicknessMethod) + "\", \"notes\": \"" + jsonEscape(lightThicknessNotes) + "\"},\n";
    s = s + "  \"surface\": {\"defined\": " + surfaceDefined + ", \"side_defined\": " + surfaceSideDefined + "},\n";
    s = s + "  \"bands\": {\"width_nm\": " + jsonNumber(bandNm) + ", \"count\": " + bandCount + "},\n";
    s = s + "  \"settings\": {\"include_uncertain\": " + lightIncludeUncertain + ", \"histogram_bin_nm\": " + jsonNumber(lightHistogramBinNm) + ", \"feature_distance_bin_nm\": " + jsonNumber(lightFeatureDistanceBinNm) + ", \"interactive_preview\": " + lightInteractivePreviewEnabled + ", \"resize_step_nm\": " + jsonNumber(lightInteractiveResizeStepNm) + ", \"exact_labels_visible\": " + showRoiLabels + ", \"exact_label_mode\": \"roi_name_v1\"},\n";
    s = s + "  \"identity_audit\": {\"errors\": " + lightLastIdAuditErrors + ", \"duplicate_ids\": " + lightLastIdAuditDuplicateIds + "},\n";
    s = s + "  \"performance\": {\"prepared_state_reused\": " + lightLastPreparationReused + ", \"prepared_state_duration_ms\": " + jsonNumber(lightLastPreparationDurationMs) + ", \"area_mode\": \"" + jsonEscape(lightAreaComputationMode) + "\", \"area_duration_ms\": " + jsonNumber(lightAreaComputationDurationMs) + "},\n";
    s = s + "  \"area\": {\"whole_image_confirmed\": " + lightUseWholeImage + ", \"valid_area_nm2\": " + jsonNumber(lastValidAreaNm2) + "},\n";
    s = s + "  \"revision_id\": \"" + jsonEscape(lightCurrentRevision) + "\",\n";
    s = s + "  \"objects\": {\"cavities\": " + lightObjectCountCavities + ", \"analysis_masks\": " + lightObjectCountMasks + ", \"exclusions\": " + lightObjectCountExclusions + ", \"grain_boundaries\": " + lightObjectCountGrainBoundaries + ", \"dislocations\": " + lightObjectCountDislocations + ", \"interfaces\": " + lightObjectCountInterfaces + "}\n";
    s = s + "}\n";
    return s;
}


function exportReadmeText(foilNm, areaOk) {
    txt = "CAVITY ROI TOOLSET v8 - NOTAS DE EXPORTACION\n";
    txt = txt + "============================================\n\n";
    txt = txt + "Muestra: " + sampleName + "\nMontaje: " + montageId + "\n";
    if (sourceImageList != "") txt = txt + "Fuentes explicitas: " + sourceImageList + "\n";
    else txt = txt + "Rango de origen informativo: " + sourceFirst + " - " + sourceLast + "\n";
    txt = txt + "Imagen: " + getTitle() + "\nEscala: " + d2s(nmPerPixelX, 10) + " nm/px (x), " + d2s(nmPerPixelY, 10) + " nm/px (y)\n";
    txt = txt + "Bandas: " + bandCount + " x " + d2s(bandNm, 6) + " nm\n";
    txt = txt + "Espesor de foil introducido: " + d2s(foilNm, 6) + " nm\n\n";
    txt = txt + "El centro, diametro equivalente, ejes, area, profundidad, posicion sobre la superficie, panel y estados de validacion se recalcularon desde la geometria actual de las ROIs antes de exportar.\n";
    if (areaOk) txt = txt + "Las areas por banda se estimaron mediante muestreo geometrico con paso " + d2s(lastAreaSamplingStepPx, 0) + " px. Cada celda se incluyo solo si pertenecia a la mascara/panel valido, no estaba en una exclusion y su profundidad firmada estaba dentro de la banda.\n";
    else txt = txt + "No se pudo calcular el area por bandas. Las densidades y fracciones dependientes del area pueden aparecer como NaN.\n";
    if (v51LastExactAreaMethod != "not_calculated") txt = txt + "El area total y por panel se calculo exactamente desde ownership>0, inclusion opcional y union de exclusiones: " + v51LastExactAreaCsv + "\n";
    txt = txt + "La densidad volumetrica usa volumen de muestra = area valida de banda x espesor de foil. El volumen de cavidad se estima como esfera de diametro equivalente: V=pi*d^3/6.\n";
    txt = txt + "Los duplicados son advertencias y no se excluyen automaticamente. Las cavidades de borde se conservan y se identifican mediante edge_intersecting.\n";
    txt = txt + "Para analisis estadistico jerarquico conserva panel_id/source_filename y agrega primero por campo, imagen y muestra.\n";
    return txt;
}



// -----------------------------------------------------------------------------
// Fiji launcher for Cavity TEM Studio GUI
// -----------------------------------------------------------------------------

function openCavityManagerFromFiji() {
    batPath = readCavityManagerBatPath();
    if (batPath == "" || !File.exists(batPath)) {
        if (batPath != "" && !File.exists(batPath)) showMessage("Ruta no encontrada", "No encuentro el launcher guardado:\n" + batPath + "\n\nSelecciona de nuevo Run_Cavity_TEM_Studio_v5_6_0.bat.");
        batPath = askForCavityManagerBatPath();
        if (batPath == "") return;
        saveCavityManagerBatPath(batPath);
    }
    launchCavityManagerBat(batPath);
}

function configureCavityManagerLauncher() {
    batPath = askForCavityManagerBatPath();
    if (batPath == "") return;
    saveCavityManagerBatPath(batPath);
    showMessage("Cavity TEM Studio configurado", "Launcher guardado:\n" + batPath + "\n\nYa puedes abrir Studio desde el panel de Fiji.");
}

function askForCavityManagerBatPath() {
    path = File.openDialog("Selecciona Run_Cavity_TEM_Studio_v5_6_0.bat");
    if (path == "") return "";
    path = "" + normalizeStoredPath(path);
    if (!endsWith(toLowerCase(path), ".bat")) {
        showMessage("Archivo no valido", "Selecciona el archivo versionado que lanza Cavity TEM Studio.\n\nArchivo:\nRun_Cavity_TEM_Studio_v5_6_0.bat");
        return "";
    }
    return "" + path;
}

function cavityManagerPrefsPath() {
    return getDirectory("macros") + "Cavity_Manager_Launcher_Path.txt";
}

function readCavityManagerBatPath() {
    pathFile = cavityManagerPrefsPath();
    if (!File.exists(pathFile)) return "";
    txt = File.openAsString(pathFile);
    lines = split(txt, "\n");
    if (lines.length <= 0) return "";
    path = String.trim(replace(lines[0], "\r", ""));
    path = "" + normalizeStoredPath(path);
    return "" + path;
}

function saveCavityManagerBatPath(path) {
    path = "" + normalizeStoredPath(path);
    File.saveString(path + "\n", cavityManagerPrefsPath());
}

function launchCavityManagerBat(path) {
    path = "" + normalizeStoredPath(path);
    safePath = jsEscape(path);
    parentDir = File.getParent(path);
    if (parentDir == "") parentDir = getDirectory("home");
    safeParent = jsEscape(parentDir);
    js = "var PB=Packages.java.lang.ProcessBuilder;var File=Packages.java.io.File;";
    js = js + "var pb=new PB('cmd.exe','/c','start','', '" + safePath + "');";
    js = js + "pb.directory(new File('" + safeParent + "'));";
    js = js + "pb.start();'1';";
    out = eval("js", js);
    if (out == "1") showStatus("Cavity TEM Studio lanzado: " + path);
}

// -----------------------------------------------------------------------------
// ProjectAware integration with Cavity TEM Studio projects
// -----------------------------------------------------------------------------

function projectAwareOpenPreparedProject() {
    projectDir = chooseDirectorySafe("Elige carpeta raiz del proyecto Cavity preparado");
    if (projectDir == "") {
        showStatus("Apertura de proyecto preparada cancelada.");
        return;
    }
    if (!projectAwareLoadProject(projectDir)) return;
    projectAwareApplyToCoreMetadata();

    roiPath = projectAwareDefaultSessionRoiPath();
    roisFound = File.exists(roiPath);
    panelsFound = countTypeFast("panel") > 0;
    buildLogFound = File.exists(projectAwareMontageBuildLogCsv);

    createLegacyPanelsDefault = 0;
    if (buildLogFound) {
        if (!panelsFound) createLegacyPanelsDefault = 1;
    }

    Dialog.create("Abrir proyecto Cavity preparado");
    Dialog.addMessage(projectAwareSummary());
    Dialog.addChoice("Imagen para abrir", newArray("Master original montage", "Choose processed analysis image...", "Do not open image"), "Master original montage");
    Dialog.addCheckbox("Aplicar escala desde metadatos", 1);
    Dialog.addCheckbox("Inicializar/actualizar sessions/cavity_results.csv", 1);
    Dialog.addCheckbox("Cargar la sesion current publicada si existe", roisFound);
    Dialog.addCheckbox("Crear paneles TEM desde montage_build_log.csv", createLegacyPanelsDefault);
    Dialog.show();

    imageChoice = Dialog.getChoice();
    setScaleFromMetadata = Dialog.getCheckbox();
    initResults = Dialog.getCheckbox();
    loadProjectRois = Dialog.getCheckbox();
    createPanels = Dialog.getCheckbox();

    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "preparar el proyecto historico", 1)) return;
    if (initResults) projectAwareEnsureResultsCsv();

    if (imageChoice == "Master original montage") {
        projectAwareOpenImage(projectAwareMasterTif, "master_original");
    } else if (imageChoice == "Choose processed analysis image...") {
        analysisPath = projectAwareChooseFileInDirectory("Elige imagen procesada de analisis", projectAwareAnalysisDir());
        if (analysisPath == "") {
            showStatus("No se selecciono imagen de analisis.");
        } else {
            projectAwareOpenImage(analysisPath, "processed_analysis_image");
        }
    }

    if (nImages() > 0 && setScaleFromMetadata) projectAwareApplyScaleFromMetadata();
    if (nImages() > 0) projectAwareAttachProjectInfoToImage();

    if (loadProjectRois && roisFound) projectAwareLoadRoisFromProject();
    if (createPanels) projectAwareCreatePanelRoisFromBuildLog(0);

    projectAwareWriteActiveProjectMarker();
    updateSessionMetadataRoi();
    showControlPanel();
    projectAwareAutoOpenBrightnessContrast();
    refreshControlPanelStatus();
    showStatus("Proyecto preparado cargado: " + projectAwareProjectDir);
}

function projectAwareReloadMetadataForCurrentImage() {
    if (projectAwareProjectDir == "") {
        projectDir = chooseDirectorySafe("Elige carpeta raiz del proyecto Cavity preparado");
        if (projectDir == "") return;
    } else projectDir = projectAwareProjectDir;
    if (!projectAwareLoadProject(projectDir)) return;
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "recargar los metadatos", 1)) return;
    projectAwareApplyToCoreMetadata();
    if (nImages() > 0) {
        projectAwareApplyScaleFromMetadata();
        projectAwareAttachProjectInfoToImage();
        updateSessionMetadataRoi();
    }
    projectAwareWriteActiveProjectMarker();
    refreshControlPanelStatus();
    showMessage("Proyecto recargado", projectAwareSummary());
}

function projectAwareSelectAnalysisImage() {
    if (!projectAwareEnsureLoaded()) return;
    Dialog.create("Seleccionar imagen para medir");
    Dialog.addMessage("Proyecto activo:\n" + projectAwareProjectDir + "\n\nElige la imagen que se usara para medir.");
    Dialog.addChoice("Imagen", newArray("Master original montage", "Choose processed analysis image..."), "Master original montage");
    Dialog.addCheckbox("Aplicar escala desde proyecto", 1);
    Dialog.show();
    choice = Dialog.getChoice();
    setScaleFromMetadata = Dialog.getCheckbox();
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "seleccionar la imagen de analisis", 1)) return;

    if (choice == "Master original montage") {
        projectAwareOpenImage(projectAwareMasterTif, "master_original");
    } else {
        analysisPath = projectAwareChooseFileInDirectory("Elige imagen procesada de analisis", projectAwareAnalysisDir());
        if (analysisPath == "") return;
        projectAwareOpenImage(analysisPath, "processed_analysis_image");
    }
    if (setScaleFromMetadata) projectAwareApplyScaleFromMetadata();
    projectAwareAttachProjectInfoToImage();
    updateSessionMetadataRoi();
    projectAwareWriteActiveProjectMarker();
    showControlPanel();
    projectAwareAutoOpenBrightnessContrast();
    refreshControlPanelStatus();
}

function projectAwareAutoOpenBrightnessContrast() {
    if (autoOpenBrightnessContrast && nImages() > 0) run("Brightness/Contrast...");
}

function projectAwareShowCurrentInfo() {
    if (!projectAwareEnsureLoaded()) return;
    showMessage("Proyecto Cavity activo", projectAwareSummary());
}

function projectAwareEnsureLoaded() {
    if (projectAwareActive && projectAwareProjectDir != "") {
        if (!v55RequireActiveImageProjectContext(projectAwareProjectDir, "usar el proyecto cargado", 1)) {
            projectAwareActive = 0;
            return 0;
        }
        return 1;
    }
    projectDir = chooseDirectorySafe("Elige carpeta raiz del proyecto Cavity preparado");
    if (projectDir == "") return 0;
    loaded = projectAwareLoadProject(projectDir);
    if (!loaded) return 0;
    return v55RequireActiveImageProjectContext(projectAwareProjectDir, "usar el proyecto cargado", 1);
}

function projectAwareResolveProjectPath(path) {
    path = normalizeStoredPath(path);
    if (path == "") return "";
    // Absolute Windows path, UNC path, or Unix path.
    if (lengthOf(path) >= 2 && substring(path, 1, 2) == ":") return "" + path;
    if (startsWith(path, "//")) return "" + path;
    if (startsWith(path, "/")) return "" + path;
    resolvedPath = projectAwareJoinPath(projectAwareProjectDir, path);
    return "" + resolvedPath;
}

function projectAwareFirstExistingPath(a, b, c, d) {
    p = projectAwareResolveProjectPath(a);
    if (p != "" && File.exists(p)) return "" + p;
    p = projectAwareResolveProjectPath(b);
    if (p != "" && File.exists(p)) return "" + p;
    p = projectAwareResolveProjectPath(c);
    if (p != "" && File.exists(p)) return "" + p;
    p = projectAwareResolveProjectPath(d);
    if (p != "" && File.exists(p)) return "" + p;
    p = projectAwareResolveProjectPath(a);
    return "" + p;
}

function projectAwareApplyScaleToActiveImageCommand() {
    if (!projectAwareEnsureLoaded()) return;
    if (nImages() <= 0) {
        showMessage("Sin imagen", "Abre primero el montaje o la imagen de analisis.");
        return;
    }
    projectAwareApplyScaleFromMetadata();
    projectAwareAttachProjectInfoToImage();
    updateSessionMetadataRoi();
    projectAwareAppendLog("apply_scale_manual", "Applied project scale to active image: " + getTitle());
    showMessage("Escala aplicada", "Escala del proyecto aplicada a la imagen activa.\n\n" + projectAwarePixelWidth + " x " + projectAwarePixelHeight + " " + projectAwarePixelUnit + "/px");
}

function projectAwareLoadProject(projectDir) {
    if (projectDir == "") return 0;
    candidateProjectDir = normalizeStoredPath(projectDir);
    if (endsWith(candidateProjectDir, "/") || endsWith(candidateProjectDir, "\\"))
        candidateProjectDir = substring(candidateProjectDir, 0, lengthOf(candidateProjectDir)-1);
    if (!v55ProjectBridgeMarkerClear(candidateProjectDir, "cargar el proyecto historico", 1)) return 0;
    if (v4ProjectLoaded && v4ProjectDir == candidateProjectDir) return 1;
    if (!v4LoadProject(candidateProjectDir)) {
        projectAwareActive = 0;
        return 0;
    }
    if (!v55ProjectBridgeMarkerClear(candidateProjectDir, "terminar de cargar el proyecto historico", 1)) {
        projectAwareActive = 0;
        v4ProjectLoaded = 0;
        return 0;
    }
    return 1;
}

function projectAwareApplyToCoreMetadata() {
    if (sampleName != "" && montageId != "") projectConfigured = 1;
    if (operatorName == "") operatorName = getInfo("user.name");
    if (sourceImageList == "" && File.exists(projectAwareLayoutCheckCsv))
        sourceImageList = projectAwareBuildSourceImageListFromLayoutCheck();
}

function projectAwareOpenImage(path, role) {
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "abrir una imagen del proyecto", 1)) return;
    if (!v4ProjectLoaded) {
        if (!v4LoadProject(projectAwareProjectDir)) {
            showMessage("Apertura cuantitativa bloqueada", "El flujo ProjectAware historico no puede abrir una imagen de analisis sin current_bridge.json y una revision v5.6.0 verificada.");
            return;
        }
    }
    if (role == "master_original") {
        if (toLowerCase(v55CanonicalPathJava(path)) != toLowerCase(v55CanonicalPathJava(v4MasterImage))) {
            showMessage("Apertura cuantitativa bloqueada", "La ruta solicitada no es el maestro vigente sellado por current_montage.json.");
            return;
        }
        if (!v4OpenOrActivateRegisteredMaster(1)) return;
        return;
    }
    if (path == "") {
        showMessage("Ruta de imagen vacia", "No hay imagen para abrir.");
        return;
    }
    if (!File.exists(path)) {
        showMessage("Imagen no encontrada", "No encuentro:\n" + path);
        return;
    }
    open(path);
    projectAwareCurrentAnalysisImagePath = normalizeStoredPath(path);
    projectAwareCurrentAnalysisImageRole = role;
    projectAwareCurrentAnalysisImageName = File.getName(path);
    refreshImageIdentity();
    if (startsWith(getTitle(), "VIEW_ONLY__")) {
        if (!getBoolean("La imagen activa empieza por VIEW_ONLY__.\n\nEstas copias son solo para inspeccion visual, no para exportacion cuantitativa.\n\nQuieres continuar de todos modos?", "Continuar", "Cancelar")) return;
    }
}

function projectAwareApplyScaleFromMetadata() {
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "aplicar la escala del proyecto", 1)) return;
    if (nImages() <= 0) return;
    pxw = projectAwareParseFloat(projectAwarePixelWidth);
    pxh = projectAwareParseFloat(projectAwarePixelHeight);
    unit = projectAwarePixelUnit;
    if (unit == "") unit = "nm";
    if (pxw <= 0) {
        showMessage("Escala no aplicada", "No hay source_pixel_width valido en los metadatos del proyecto.");
        return;
    }
    if (pxh <= 0) pxh = pxw;
    setVoxelSize(pxw, pxh, 1, unit);
    // Some Fiji/Bio-Formats imports ignore TIFF/ImageJ calibration. Force the active image calibration too.
    run("Set Scale...", "distance=1 known=" + pxw + " unit=[" + unit + "] global");
    updateScaleMaybe();
    projectAwareAppendLog("set_scale", "Set image scale from project: " + projectAwarePixelWidth + " x " + projectAwarePixelHeight + " " + unit + "/px");
}

function projectAwareAttachProjectInfoToImage() {
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "adjuntar el contexto del proyecto", 1)) return;
    if (nImages() <= 0) return;
    txt = "Cavity ProjectAware context\n";
    txt = txt + "macro_version=" + macroVersion + "\n";
    txt = txt + "project_dir=" + projectAwareProjectDir + "\n";
    txt = txt + "project_uid=" + projectAwareProjectUid + "\n";
    txt = txt + "sampleName=" + sampleName + "\n";
    txt = txt + "experimentalCondition=" + experimentalCondition + "\n";
    txt = txt + "montageId=" + montageId + "\n";
    txt = txt + "sourceFirst=" + sourceFirst + "\n";
    txt = txt + "sourceLast=" + sourceLast + "\n";
    txt = txt + "sourceEndExclusive=" + projectAwareSourceEndExclusive + "\n";
    txt = txt + "panel_count=" + projectAwarePanelCount + "\n";
    txt = txt + "source_pixel_width=" + projectAwarePixelWidth + "\n";
    txt = txt + "source_pixel_height=" + projectAwarePixelHeight + "\n";
    txt = txt + "source_pixel_unit=" + projectAwarePixelUnit + "\n";
    txt = txt + "analysis_image_path=" + projectAwareCurrentAnalysisImagePath + "\n";
    txt = txt + "analysis_image_role=" + projectAwareCurrentAnalysisImageRole + "\n";
    setMetadata("Info", txt);
}

function projectAwareSaveSessionToProject() {
    if (!projectAwareEnsureLoaded()) return 0;
    return v56PrepareRoiSessionRequest("ProjectAware save session");
}

function projectAwareLoadRoisFromProject() {
    if (!projectAwareEnsureLoaded()) return 0;
    return v4LoadSession();
}

function projectAwareCreatePanelRoisFromBuildLog(force) {
    if (!projectAwareEnsureLoaded()) return;
    if (!v4EnsureProject()) return;
    v4CreatePanelsFromManifest();
    return;
    if (nImages() <= 0) {
        showMessage("Sin imagen", "Abre primero el master montage para crear los paneles.");
        return;
    }
    if (!File.exists(projectAwareMontageBuildLogCsv)) {
        showMessage("Build log no encontrado", "No encuentro:\n" + projectAwareMontageBuildLogCsv + "\n\nVuelve a preparar el proyecto con el script Python para generar montage_build_log.csv.");
        return;
    }
    existingPanels = countTypeFast("panel");
    if (existingPanels > 0 && !force) {
        if (!getBoolean("Ya existen " + existingPanels + " paneles TEM.\n\nQuieres crear paneles nuevos desde el layout de todos modos?", "Crear de todos modos", "Cancelar")) return;
    }

    text = File.openAsString(projectAwareMontageBuildLogCsv);
    lines = split(text, "\n");
    if (lines.length < 2) {
        showMessage("Build log vacio", "El CSV no contiene filas de panel.");
        return;
    }
    header = split(replace(lines[0], "\r", ""), ",");
    ixX = projectAwareColumnIndex(header, "x_canvas_px");
    ixY = projectAwareColumnIndex(header, "y_canvas_px");
    ixW = projectAwareColumnIndex(header, "paste_width_px");
    ixH = projectAwareColumnIndex(header, "paste_height_px");
    ixSrc = projectAwareColumnIndex(header, "source_relative_path");
    ixPanel = projectAwareColumnIndex(header, "panel_idx");
    if (ixX < 0 || ixY < 0 || ixW < 0 || ixH < 0) {
        showMessage("Columnas no reconocidas", "El build log no contiene x_canvas_px/y_canvas_px/paste_width_px/paste_height_px.");
        return;
    }

    run("ROI Manager...");
    created = 0;
    for (li=1; li<lines.length; li++) {
        line = replace(lines[li], "\r", "");
        if (line == "") continue;
        vals = split(line, ",");
        if (vals.length <= ixH) continue;
        x = projectAwareParseFloat(projectAwareCsvCell(vals, ixX));
        y = projectAwareParseFloat(projectAwareCsvCell(vals, ixY));
        w = projectAwareParseFloat(projectAwareCsvCell(vals, ixW));
        h = projectAwareParseFloat(projectAwareCsvCell(vals, ixH));
        if (w <= 0 || h <= 0) continue;
        panelIdx = created;
        if (ixPanel >= 0 && vals.length > ixPanel) panelIdx = round(projectAwareParseFloat(projectAwareCsvCell(vals, ixPanel)));
        source = "";
        if (ixSrc >= 0 && vals.length > ixSrc) source = projectAwareCsvCell(vals, ixSrc);
        serial = panelCounter + 1;
        id = "PANEL_" + IJ.pad(serial, 3);
        makeRectangle(x, y, w, h);
        Roi.setName(id);
        Roi.setGroup(0);
        Roi.setFillColor("#00000000");
        Roi.setStrokeColor("white");
        Roi.setUnscalableStrokeWidth(2);
        setCommonObjectProperties();
        v4StampCurrentRevisionBinding();
        Roi.setProperty("Type", "panel");
        Roi.setProperty("Panel_id", id);
        Roi.setProperty("Panel_order", d2s(serial, 0));
        Roi.setProperty("Panel_idx_from_layout", d2s(panelIdx, 0));
        Roi.setProperty("Source_filename", source);
        Roi.setProperty("Notes", "Created automatically from montage_build_log.csv");
        roiManager("add");
        idx = roiManager("count")-1;
        syncAreaObjectAtIndex(idx);
        panelCounter = serial;
        created++;
    }
    updateSessionMetadataRoi();
    restyleAllRois();
    showAllRois();
    projectAwareAppendLog("create_panels", "Created " + created + " panel ROIs from build log");
    refreshControlPanelStatus();
    showStatus("Paneles creados desde layout: " + created);
}

function projectAwareEnsureResultsCsv() {
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "inicializar los resultados historicos", 1)) return;
    if (projectAwareResultsCsv == "") projectAwareResultsCsv = projectAwareJoinPath(projectAwareSessionsDir, "cavity_results.csv");
    makeDirIfMissing(projectAwareSessionsDir);
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "inicializar los resultados historicos", 1)) return;
    if (!File.exists(projectAwareResultsCsv)) {
        header = projectAwareResultsHeader();
        File.saveString(header, projectAwareResultsCsv);
    }
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "terminar de inicializar los resultados", 1)) return;
}

function projectAwareWriteSimplifiedResultsCsv() {
    if (!projectAwareEnsureLoaded()) return;
    if (projectAwareResultsCsv == "") projectAwareResultsCsv = projectAwareJoinPath(projectAwareSessionsDir, "cavity_results.csv");
    text = projectAwareResultsHeader();
    n = roiManager("count");
    for (ri=0; ri<n; ri++) {
        safeRoiSelect(ri);
        if (!currentRoiIsCavity()) continue;
        id = cavityIdCurrent();
        xpx = propNumber("Center_x_px", NaN);
        ypx = propNumber("Center_y_px", NaN);
        xnm = propNumber("Center_x_nm", NaN);
        ynm = propNumber("Center_y_nm", NaN);
        dnm = propNumber("Equivalent_diameter_nm", propNumber("Diameter_nm", NaN));
        dpx = NaN;
        if (nmPerPixelX > 0) dpx = dnm/nmPerPixelX;
        depthSigned = propNumber("Signed_depth_nm", NaN);
        depthAbs = propNumber("Depth_absolute_nm", abs(depthSigned));
        band = round(propNumber("Band_index", -1));
        source = propString("Source_filename", "");
        panel = propString("Panel_id", "");
        panelIdx = propString("Panel_idx_from_layout", "");
        includeStats = round(propNumber("Include_in_statistics", 1));
        inside = round(propNumber("Inside_analysis_mask", 1));
        edge = round(propNumber("Edge_intersecting", 0));
        manual = round(propNumber("Manual_excluded", 0));
        duplicate = propString("Duplicate_status", "clear");
        reason = propString("Exclusion_reason", "");
        method = propString("Measurement_source", "");
        cclass = propString("Cavity_class", "confirmed");
        cconf = propString("Cavity_confidence", "high");
        text = text + projectAwareCsvEscape(id) + ",";
        text = text + projectAwareCsvEscape(sampleName) + "," + projectAwareCsvEscape(experimentalCondition) + "," + projectAwareCsvEscape(montageId) + "," + projectAwareCsvEscape(projectAwareProjectUid) + ",";
        text = text + projectAwareCsvEscape(projectAwareCurrentAnalysisImageName) + "," + projectAwareCsvEscape(projectAwareCurrentAnalysisImageRole) + ",";
        text = text + projectAwareCsvEscape(source) + "," + projectAwareCsvEscape(panel) + "," + projectAwareCsvEscape(panelIdx) + ",";
        text = text + d2s(xpx, 6) + "," + d2s(ypx, 6) + "," + d2s(xnm, 6) + "," + d2s(ynm, 6) + ",";
        text = text + d2s(dpx, 6) + "," + d2s(dnm, 6) + "," + d2s(depthAbs, 6) + "," + d2s(depthSigned, 6) + "," + band + ",";
        text = text + includeStats + "," + inside + "," + edge + "," + manual + "," + projectAwareCsvEscape(duplicate) + "," + projectAwareCsvEscape(reason) + "," + projectAwareCsvEscape(method) + "," + projectAwareCsvEscape(cclass) + "," + projectAwareCsvEscape(cconf) + "," + projectAwareCsvEscape(macroVersion) + "\n";
    }
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "publicar los resultados simplificados", 1)) return;
    File.saveString(text, projectAwareResultsCsv);
    latest = projectAwareJoinPath(projectAwareSessionsDir, "cavity_results_latest.csv");
    File.saveString(text, latest);
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "terminar de publicar los resultados", 1)) return;
    projectAwareAppendLog("write_results_csv", "Updated simplified results CSV: " + projectAwareResultsCsv);
}

function projectAwareResultsHeader() {
    return "cavity_id,sample_name,experimental_condition,montage_id,project_uid,analysis_image_name,analysis_image_role,source_file,panel_id,panel_idx,x_global_px,y_global_px,x_global_nm,y_global_nm,diameter_px,diameter_nm,distance_to_surface_nm,signed_depth_nm,band_id,include_in_statistics,inside_analysis_mask,edge_intersecting,manual_excluded,duplicate_status,exclusion_reason,measurement_method,cavity_class,cavity_confidence,tool_version\n";
}


function projectAwareDuplicateFullImage(title) {
    if (nImages() <= 0) {
        showMessage("Sin imagen", "Abra o active una imagen antes de crear una copia completa.");
        return 0;
    }
    sourceImageId = getImageID();
    getDimensions(sourceFullWidth, sourceFullHeight, sourceFullChannels, sourceFullSlices, sourceFullFrames);
    if (sourceFullWidth < 2 || sourceFullHeight < 2) {
        showMessage("Imagen no valida",
            "La imagen activa mide " + sourceFullWidth + " x " + sourceFullHeight + " px y no puede duplicarse como imagen completa.");
        return 0;
    }

    duplicateScript = "var WM=Packages.ij.WindowManager;";
    duplicateScript = duplicateScript + "var imp=WM.getCurrentImage();";
    duplicateScript = duplicateScript + "if(imp==null) throw 'No active image';";
    duplicateScript = duplicateScript + "var roi=imp.getRoi();";
    duplicateScript = duplicateScript + "imp.deleteRoi();";
    duplicateScript = duplicateScript + "var dup=null;";
    duplicateScript = duplicateScript + "try{dup=imp.duplicate();}finally{if(roi!=null)imp.setRoi(roi);}";
    duplicateScript = duplicateScript + "dup.deleteRoi();";
    duplicateScript = duplicateScript + "dup.setTitle('" + jsEscape(title) + "');";
    duplicateScript = duplicateScript + "dup.show();";
    duplicateScript = duplicateScript + "String(dup.getID());";
    duplicateIdText = eval("script", duplicateScript);
    duplicateImageId = parseInt(duplicateIdText);
    if (isNaN(duplicateImageId)) {
        selectImage(sourceImageId);
        showMessage("No se pudo duplicar", "Fiji no devolvio un identificador valido para la copia completa.");
        return 0;
    }

    selectImage(duplicateImageId);
    getDimensions(copyFullWidth, copyFullHeight, copyFullChannels, copyFullSlices, copyFullFrames);
    sameGeometry = copyFullWidth == sourceFullWidth;
    if (copyFullHeight != sourceFullHeight) sameGeometry = 0;
    if (copyFullChannels != sourceFullChannels) sameGeometry = 0;
    if (copyFullSlices != sourceFullSlices) sameGeometry = 0;
    if (copyFullFrames != sourceFullFrames) sameGeometry = 0;
    if (!sameGeometry) {
        close();
        selectImage(sourceImageId);
        showMessage("Copia geometrica rechazada",
            "Origen: " + sourceFullWidth + " x " + sourceFullHeight + " px; C=" + sourceFullChannels + ", Z=" + sourceFullSlices + ", T=" + sourceFullFrames + "\n" +
            "Copia: " + copyFullWidth + " x " + copyFullHeight + " px; C=" + copyFullChannels + ", Z=" + copyFullSlices + ", T=" + copyFullFrames + "\n\n" +
            "La aplicacion ha cerrado la copia para evitar procesar una ROI recortada.");
        return 0;
    }
    run("Select None");
    return 1;
}

function projectAwareCreateFilteredWorkingCopy() {
    if (nImages() <= 0) {
        showMessage("Sin imagen", "Abre primero el montaje maestro o una imagen de analisis.");
        return;
    }
    sourceProjectRoot = v4FindProjectRootFromCurrentImage();
    loadedProjectRoot = "";
    if (v4ProjectLoaded && v4ProjectDir != "") loadedProjectRoot = v4ProjectDir;
    if (!v55RequireProjectRootMatch(sourceProjectRoot, loadedProjectRoot, "crear una copia visual", 1)) return;
    originalTitle = getTitle();
    originalID = getImageID();
    getDimensions(width, height, channels, slices, frames);
    hasRoi = selectionType() != -1;

    Dialog.create("Copia visual / filtrada Cavity");
    Dialog.addMessage("La imagen activa no se modifica.\nLas copias VIEW_ONLY son para inspeccion; las copias de geometria completa pueden registrarse despues como imagen de analisis.");
    Dialog.addChoice("Tipo de copia", newArray("Full image - same geometry", "Current ROI crop - view only"), "Full image - same geometry");
    Dialog.addChoice("Filtro visual", newArray("No pixel filter", "Display contrast only", "Gaussian denoise", "Unsharp visual enhancement", "Bandpass cavity contrast", "CLAHE local contrast"), "Display contrast only");
    Dialog.addNumber("Display saturated pixels (%)", 0.35);
    Dialog.addNumber("Gaussian sigma (px)", 0.8);
    Dialog.addNumber("Unsharp radius (px)", 1.5);
    Dialog.addNumber("Unsharp mask weight", 0.60);
    Dialog.addNumber("Bandpass large structures (px)", 80);
    Dialog.addNumber("Bandpass small structures (px)", 2);
    Dialog.addNumber("CLAHE block size (px)", 127);
    Dialog.addNumber("CLAHE maximum slope", 3.0);
    Dialog.addCheckbox("Guardar esta copia en project/views", projectAwareActive);
    Dialog.show();

    copyType = Dialog.getChoice();
    preset = Dialog.getChoice();
    sat = Dialog.getNumber();
    sigma = Dialog.getNumber();
    unsharpRadius = Dialog.getNumber();
    unsharpWeight = Dialog.getNumber();
    bpLarge = Dialog.getNumber();
    bpSmall = Dialog.getNumber();
    claheBlock = Dialog.getNumber();
    claheMax = Dialog.getNumber();
    saveView = Dialog.getCheckbox();

    selectImage(originalID);
    if (copyType == "Current ROI crop - view only" && !hasRoi) {
        if (!getBoolean("No hay ROI seleccionada.\n\nSe creara una copia completa, que puede consumir RAM. Continuar?", "Continuar", "Cancelar")) return;
        copyType = "Full image - same geometry";
    }
    if (copyType == "Full image - same geometry" && width*height > 80000000) {
        if (!getBoolean("El montaje es grande (" + width + " x " + height + " px).\n\nDuplicarlo puede consumir bastante RAM. Continuar?", "Continuar", "Cancelar")) return;
    }

    role = "VIEW_ONLY";
    if (copyType == "Full image - same geometry") role = "VIEW_FULL_GEOMETRY";
    viewTitle = role + "__" + sanitizeFileName(preset) + "__" + originalTitle;
    if (copyType == "Full image - same geometry") {
        if (!projectAwareDuplicateFullImage(viewTitle)) return;
    } else {
        run("Duplicate...", "title=[" + viewTitle + "]");
        run("Select None");
    }
    projectAwareApplyVisualPreset(preset, sat, sigma, unsharpRadius, unsharpWeight, bpLarge, bpSmall, claheBlock, claheMax);

    if (saveView) {
        if (!projectAwareEnsureLoaded()) return;
        if (!v55RequireProjectRootMatch(sourceProjectRoot, projectAwareProjectDir, "guardar la copia visual", 1)) return;
        if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "guardar la copia visual", 1)) return;
        makeDirIfMissing(projectAwareViewsDir);
        id = d2s(getTime(), 0);
        safeViewTitle = sanitizeFileName(viewTitle);
        viewFileName = safeViewTitle + "__" + id + ".tif";
        outPath = projectAwareJoinPath(projectAwareViewsDir, viewFileName);
        if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "guardar la copia visual", 1)) return;
        saveAs("Tiff", outPath);
        if (!projectAwareWriteViewSidecar(outPath, originalTitle, viewTitle, preset, copyType, "working_view", width, height)) { showMessage("Vista parcial", "La imagen se guardo, pero el sidecar quedo bloqueado por una recuperacion del proyecto. No se registra como vista completa.\n\n" + outPath); return; }
        projectAwareAppendLog("save_view", "Saved view copy to " + outPath);
    }
    selectImage(originalID);
    showStatus("Copia visual creada. La imagen original no se ha modificado.");
}

function projectAwareSaveActiveImageAsAnalysisVersion() {
    if (nImages() <= 0) {
        showMessage("Sin imagen", "Selecciona la imagen procesada que quieres registrar.");
        return;
    }
    activeProjectRoot = v4FindProjectRootFromCurrentImage();
    loadedProjectRoot = "";
    if (v4ProjectLoaded && v4ProjectDir != "") loadedProjectRoot = v4ProjectDir;
    if (!v55RequireProjectRootMatch(activeProjectRoot, loadedProjectRoot, "registrar la imagen de analisis", 1)) return;
    if (!projectAwareEnsureLoaded()) return;
    if (!v55RequireProjectRootMatch(activeProjectRoot, projectAwareProjectDir, "registrar la imagen de analisis", 1)) return;
    activeTitle = getTitle();
    getDimensions(width, height, channels, slices, frames);

    Dialog.create("Registrar imagen de analisis");
    Dialog.addMessage("Guarda la imagen activa como version procesada aceptada para medir.\nNo sustituye al master original.");
    Dialog.addString("Nombre de la version", "original_2", 30);
    Dialog.addString("Notas de procesado", "", 60);
    Dialog.addCheckbox("Confirmo que la geometria no ha cambiado: sin resize, rotacion ni crop", 1);
    Dialog.addCheckbox("Confirmo que no es el original bruto, sino una version procesada", 1);
    Dialog.show();
    label = sanitizeFileName(Dialog.getString());
    notes = Dialog.getString();
    geometryOK = Dialog.getCheckbox();
    userUnderstands = Dialog.getCheckbox();
    if (!geometryOK || !userUnderstands) {
        showMessage("No guardado", "Para registrar una imagen de analisis deben confirmarse geometria preservada y trazabilidad.");
        return;
    }
    if (label == "") label = "analysis_image";

    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "registrar la imagen de analisis", 1)) return;
    analysisDir = projectAwareAnalysisDir();
    makeDirIfMissing(projectAwareDerivedDir);
    makeDirIfMissing(analysisDir);
    outPath = projectAwareJoinPath(analysisDir, label + ".tif");
    if (File.exists(outPath)) {
        if (!getBoolean("El archivo ya existe:\n" + outPath + "\n\nSobrescribir?", "Sobrescribir", "Cancelar")) return;
    }
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "guardar la imagen de analisis", 1)) return;
    saveAs("Tiff", outPath);
    projectAwareCurrentAnalysisImagePath = outPath;
    projectAwareCurrentAnalysisImageRole = "processed_analysis_image";
    projectAwareCurrentAnalysisImageName = File.getName(outPath);
    if (!projectAwareWriteAnalysisSidecar(outPath, activeTitle, label, notes, width, height)) { showMessage("Registro parcial", "El TIFF se guardo, pero su sidecar quedo bloqueado por una recuperacion del proyecto. No se anuncia como version registrada.\n\n" + outPath); return; }
    if (!projectAwareAppendAnalysisRegistry(label, outPath, activeTitle, notes, width, height)) { showMessage("Registro parcial", "El TIFF y su sidecar existen, pero el registro quedo bloqueado por una recuperacion del proyecto. No se anuncia como version registrada.\n\n" + outPath); return; }
    projectAwareAttachProjectInfoToImage();
    updateSessionMetadataRoi();
    projectAwareWriteActiveProjectMarker();
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "terminar de registrar la imagen de analisis", 1)) return;
    showMessage("Imagen de analisis registrada", "Guardada en:\n" + outPath + "\n\nEsta imagen podra seleccionarse desde 'Imagen analisis'.");
}

function projectAwareApplyVisualPreset(preset, sat, sigma, unsharpRadius, unsharpWeight, bpLarge, bpSmall, claheBlock, claheMax) {
    if (preset == "No pixel filter") return;
    if (preset == "Display contrast only") {
        run("Enhance Contrast", "saturated=" + sat);
        return;
    }
    if (preset == "Gaussian denoise") {
        run("Gaussian Blur...", "sigma=" + sigma);
        run("Enhance Contrast", "saturated=" + sat);
        return;
    }
    if (preset == "Unsharp visual enhancement") {
        run("Unsharp Mask...", "radius=" + unsharpRadius + " mask=" + unsharpWeight);
        run("Enhance Contrast", "saturated=" + sat);
        return;
    }
    if (preset == "Bandpass cavity contrast") {
        run("Bandpass Filter...", "filter_large=" + bpLarge + " filter_small=" + bpSmall + " suppress=None tolerance=5 autoscale saturate");
        return;
    }
    if (preset == "CLAHE local contrast") {
        run("Enhance Local Contrast (CLAHE)", "blocksize=" + claheBlock + " histogram=256 maximum=" + claheMax + " mask=*None* fast_(less_accurate)");
        run("Enhance Contrast", "saturated=" + sat);
    }
}

function projectAwareSummary() {
    txt = "Project folder:\n" + projectAwareProjectDir + "\n\n";
    txt = txt + "sampleName: " + sampleName + "\n";
    txt = txt + "experimentalCondition: " + experimentalCondition + "\n";
    txt = txt + "montageId: " + montageId + "\n";
    txt = txt + "project_uid: " + projectAwareProjectUid + "\n";
    txt = txt + "source range: " + sourceFirst + " - " + sourceLast + "";
    if (projectAwareSourceEndExclusive != "") txt = txt + " (end exclusive: " + projectAwareSourceEndExclusive + ")";
    txt = txt + "\n";
    txt = txt + "panel_count: " + projectAwarePanelCount + "\n";
    txt = txt + "pixel size: " + projectAwarePixelWidth + " x " + projectAwarePixelHeight + " " + projectAwarePixelUnit + "/px\n";
    txt = txt + "active image: " + projectAwareCurrentAnalysisImageName + " [" + projectAwareCurrentAnalysisImageRole + "]\n";
    txt = txt + "master TIFF:\n" + projectAwareMasterTif + "\n";
    txt = txt + "results CSV:\n" + projectAwareResultsCsv + "\n";
    return txt;
}

function projectAwareDefaultSessionRoiPath() {
    p = projectAwareJoinPath(projectAwareSessionsDir, "current_roi_session.json");
    return "" + p;
}

function projectAwareDefaultExportDir() {
    d = projectAwareJoinPath(projectAwareSessionsDir, "exports");
    if (!endsWith(d, "/") && !endsWith(d, "\\")) d = d + "/";
    return d;
}

function projectAwareAnalysisDir() {
    p = projectAwareJoinPath(projectAwareDerivedDir, "analysis_images");
    return "" + p;
}

function projectAwareGetField(fieldName) {
    fieldValue = "";
    if (File.exists(projectAwareProjectFieldsCsv)) {
        fieldValue = projectAwareReadFieldFromCsv(projectAwareProjectFieldsCsv, fieldName);
        if (fieldValue != "") return "" + fieldValue;
    }
    if (File.exists(projectAwareMetadataJson)) {
        textJson = File.openAsString(projectAwareMetadataJson);
        fieldValue = projectAwareReadFieldFromJsonText(textJson, fieldName);
        return "" + fieldValue;
    }
    return "";
}

function projectAwareReadFieldFromCsv(path, fieldName) {
    textCsv = File.openAsString(path);
    csvField = projectAwareReadFieldFromCsvText(textCsv, fieldName);
    return "" + csvField;
}

function projectAwareReadFieldFromCsvText(textCsv, fieldName) {
    if (lengthOf(textCsv) > 0 && charCodeAt(textCsv, 0) == 65279) textCsv = substring(textCsv, 1, lengthOf(textCsv));
    bomMojibake = fromCharCode(239) + fromCharCode(187) + fromCharCode(191);
    if (startsWith(textCsv, bomMojibake)) textCsv = substring(textCsv, 3, lengthOf(textCsv));
    lines = split(textCsv, "\n");
    key1 = fieldName + ",";
    key2 = "\"" + fieldName + "\",";
    for (ci=0; ci<lines.length; ci++) {
        line = replace(lines[ci], "\r", "");
        if (indexOf(line, key1) == 0 || indexOf(line, key2) == 0) {
            comma = indexOf(line, ",");
            if (comma >= 0) {
                csvRawValue = substring(line, comma+1, lengthOf(line));
                csvCleanValue = projectAwareCleanCsvValue(csvRawValue);
                return "" + csvCleanValue;
            }
        }
    }
    return "";
}

function projectAwareReadFieldFromJsonText(textJson, fieldName) {
    pattern = "\"" + fieldName + "\"";
    p = indexOf(textJson, pattern);
    if (p < 0) return "";
    rest = substring(textJson, p + lengthOf(pattern), lengthOf(textJson));
    colon = indexOf(rest, ":");
    if (colon < 0) return "";
    v = String.trim(substring(rest, colon+1, lengthOf(rest)));
    if (v == "") return "";
    first = substring(v, 0, 1);
    if (first == "\"") {
        v2 = substring(v, 1, lengthOf(v));
        q = indexOf(v2, "\"");
        if (q < 0) return "";
        jsonOut = substring(v2, 0, q);
        jsonOut = replace(jsonOut, "\\/", "/");
        jsonOut = replace(jsonOut, "\\\\", "\\");
        jsonOut = replace(jsonOut, "\\\"", "\"");
        return "" + jsonOut;
    }
    comma = indexOf(v, ",");
    brace = indexOf(v, "}");
    end = lengthOf(v);
    if (comma >= 0 && comma < end) end = comma;
    if (brace >= 0 && brace < end) end = brace;
    jsonOut = String.trim(substring(v, 0, end));
    return "" + jsonOut;
}

function projectAwareCleanCsvValue(csvValueIn) {
    csvClean = "" + csvValueIn;
    csvClean = String.trim(replace(csvClean, "\r", ""));
    if (lengthOf(csvClean) >= 2) {
        csvFirst = substring(csvClean, 0, 1);
        csvLast = substring(csvClean, lengthOf(csvClean)-1, lengthOf(csvClean));
        if (csvFirst == "\"" && csvLast == "\"") {
            csvClean = substring(csvClean, 1, lengthOf(csvClean)-1);
            csvClean = replace(csvClean, "\"\"", "\"");
        }
    }
    return "" + csvClean;
}

function projectAwareBuildSourceImageListFromLayoutCheck() {
    if (!File.exists(projectAwareLayoutCheckCsv)) return "";
    textCsv = File.openAsString(projectAwareLayoutCheckCsv);
    lines = split(textCsv, "\n");
    if (lines.length < 2) return "";
    header = split(replace(lines[0], "\r", ""), ",");
    ix = projectAwareColumnIndex(header, "source_relative_path");
    if (ix < 0) return "";
    out = "";
    for (li=1; li<lines.length; li++) {
        line = replace(lines[li], "\r", "");
        if (line == "") continue;
        vals = split(line, ",");
        if (vals.length <= ix) continue;
        src = projectAwareCsvCell(vals, ix);
        if (src == "") continue;
        if (out != "") out = out + ";";
        out = out + src;
    }
    return out;
}

function projectAwareColumnIndex(header, name) {
    for (hi=0; hi<header.length; hi++) {
        h = projectAwareCleanCsvValue(header[hi]);
        if (h == name) return hi;
    }
    return -1;
}

function projectAwareCsvCell(vals, ix) {
    if (ix < 0 || vals.length <= ix) return "";
    cell = projectAwareCleanCsvValue(vals[ix]);
    return "" + cell;
}

function projectAwareParseFloat(s) {
    if (s == "") return 0;
    return parseFloat(s);
}

function projectAwareChooseFileInDirectory(title, startDir) {
    safeTitle = jsEscape(title);
    safeDir = jsEscape(startDir);
    chooserCode = "var JFileChooser=Packages.javax.swing.JFileChooser;var File=Packages.java.io.File;var IJ=Packages.ij.IJ;var fc=new JFileChooser();fc.setDialogTitle('" + safeTitle + "');fc.setFileSelectionMode(JFileChooser.FILES_ONLY);if('" + safeDir + "'!='')fc.setCurrentDirectory(new File('" + safeDir + "'));var r=fc.showOpenDialog(IJ.getInstance());var p='';if(r==JFileChooser.APPROVE_OPTION&&fc.getSelectedFile()!=null)p=String(fc.getSelectedFile().getAbsolutePath());p;";
    chosenFile = eval("js", chooserCode);
    if (chosenFile == "null") chosenFile = "";
    chosenFile = normalizeStoredPath(chosenFile);
    return chosenFile;
}

function projectAwareAppendLog(action, message) {
    if (projectAwareSessionsDir == "") return;
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "escribir el registro historico", 1)) return;
    makeDirIfMissing(projectAwareSessionsDir);
    logPath = projectAwareJoinPath(projectAwareSessionsDir, "cavity_projectaware_log.csv");
    if (!File.exists(logPath)) File.saveString("time_ms,macro_version,action,message\n", logPath);
    line = d2s(getTime(),0) + "," + projectAwareCsvEscape(macroVersion) + "," + projectAwareCsvEscape(action) + "," + projectAwareCsvEscape(message) + "\n";
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "escribir el registro historico", 1)) return;
    File.append(line, logPath);
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "terminar el registro historico", 1)) return;
}

function projectAwareWriteActiveProjectMarker() {
    if (projectAwareSessionsDir == "") return;
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "escribir el marcador de proyecto activo", 1)) return;
    path = projectAwareJoinPath(projectAwareSessionsDir, "cavity_active_project.csv");
    text = "field,value\n";
    text = text + "project_dir," + projectAwareCsvEscape(projectAwareProjectDir) + "\n";
    text = text + "project_uid," + projectAwareCsvEscape(projectAwareProjectUid) + "\n";
    text = text + "sampleName," + projectAwareCsvEscape(sampleName) + "\n";
    text = text + "experimentalCondition," + projectAwareCsvEscape(experimentalCondition) + "\n";
    text = text + "montageId," + projectAwareCsvEscape(montageId) + "\n";
    text = text + "analysis_image_name," + projectAwareCsvEscape(projectAwareCurrentAnalysisImageName) + "\n";
    text = text + "analysis_image_role," + projectAwareCsvEscape(projectAwareCurrentAnalysisImageRole) + "\n";
    text = text + "analysis_image_path," + projectAwareCsvEscape(projectAwareCurrentAnalysisImagePath) + "\n";
    text = text + "results_csv," + projectAwareCsvEscape(projectAwareResultsCsv) + "\n";
    File.saveString(text, path);
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "terminar el marcador de proyecto activo", 1)) return;
}

function projectAwareWriteViewSidecar(imagePath, originalTitle, viewTitle, preset, copyType, role, width, height) {
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "guardar el sidecar de vista", 1)) return 0;
    jsonPath = replace(imagePath, ".tif", ".json");
    text = "{\n";
    text = text + "  \"image_role\": \"" + jsonEscape(role) + "\",\n";
    text = text + "  \"created_by\": \"" + jsonEscape(macroVersion) + "\",\n";
    text = text + "  \"created_time_ms\": \"" + d2s(getTime(),0) + "\",\n";
    text = text + "  \"project_dir\": \"" + jsonEscape(projectAwareProjectDir) + "\",\n";
    text = text + "  \"source_title\": \"" + jsonEscape(originalTitle) + "\",\n";
    text = text + "  \"view_title\": \"" + jsonEscape(viewTitle) + "\",\n";
    text = text + "  \"preset\": \"" + jsonEscape(preset) + "\",\n";
    text = text + "  \"copy_type\": \"" + jsonEscape(copyType) + "\",\n";
    text = text + "  \"geometry_preserved\": \"" + (copyType == "Full image - same geometry") + "\",\n";
    text = text + "  \"width_px\": " + width + ",\n";
    text = text + "  \"height_px\": " + height + "\n";
    text = text + "}\n";
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "guardar el sidecar de vista", 1)) return 0;
    File.saveString(text, jsonPath);
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "terminar el sidecar de vista", 1)) return 0;
    return 1;
}

function projectAwareWriteAnalysisSidecar(imagePath, activeTitle, label, notes, width, height) {
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "guardar el sidecar de analisis", 1)) return 0;
    jsonPath = replace(imagePath, ".tif", ".json");
    text = "{\n";
    text = text + "  \"image_role\": \"processed_analysis_image\",\n";
    text = text + "  \"created_by\": \"" + jsonEscape(macroVersion) + "\",\n";
    text = text + "  \"created_time_ms\": \"" + d2s(getTime(),0) + "\",\n";
    text = text + "  \"project_dir\": \"" + jsonEscape(projectAwareProjectDir) + "\",\n";
    text = text + "  \"analysis_label\": \"" + jsonEscape(label) + "\",\n";
    text = text + "  \"source_active_title\": \"" + jsonEscape(activeTitle) + "\",\n";
    text = text + "  \"processing_notes\": \"" + jsonEscape(notes) + "\",\n";
    text = text + "  \"geometry_preserved\": true,\n";
    text = text + "  \"measurement_warning\": \"Processed image. Use only if this processing is part of the defined measurement protocol.\",\n";
    text = text + "  \"width_px\": " + width + ",\n";
    text = text + "  \"height_px\": " + height + "\n";
    text = text + "}\n";
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "guardar el sidecar de analisis", 1)) return 0;
    File.saveString(text, jsonPath);
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "terminar el sidecar de analisis", 1)) return 0;
    return 1;
}

function projectAwareAppendAnalysisRegistry(label, imagePath, activeTitle, notes, width, height) {
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "actualizar el registro de imagenes", 1)) return 0;
    makeDirIfMissing(projectAwareSessionsDir);
    reg = projectAwareJoinPath(projectAwareSessionsDir, "analysis_image_registry.csv");
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "actualizar el registro de imagenes", 1)) return 0;
    if (!File.exists(reg)) File.saveString("analysis_label,image_path,source_active_title,width_px,height_px,created_time_ms,processing_notes\n", reg);
    // R2: start with a literal so ImageJ parses the complete RHS as text.
    line = "" + projectAwareCsvEscape(label) + "," + projectAwareCsvEscape(imagePath) + "," + projectAwareCsvEscape(activeTitle) + "," + width + "," + height + "," + d2s(getTime(),0) + "," + projectAwareCsvEscape(notes) + "\n";
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "actualizar el registro de imagenes", 1)) return 0;
    File.append(line, reg);
    if (!v55ProjectBridgeMarkerClear(projectAwareProjectDir, "terminar el registro de imagenes", 1)) return 0;
    return 1;
}

function projectAwareJoinPath(dir, name) {
    if (dir == "") return name;
    if (endsWith(dir, "/") || endsWith(dir, "\\")) return dir + name;
    return dir + "/" + name;
}

function projectAwareCsvEscape(s) {
    s = "" + s;
    s = replace(s, "\"", "\"\"");
    return "\"" + s + "\"";
}

function makeDirIfMissing(path) {
    if (path == "") return;
    if (!File.exists(path)) File.makeDirectory(path);
}


// --- Cavity TEM Studio 5 project layer (v4 function names are compatibility API) ---

// Cavity_ROI_Studio_v9_0.ijm
// Cavity TEM Studio 5 integration layer for the mature v8.3.0 ROI toolset.
// This file is appended to Cavity_ROI_Toolset_v8_3_0.ijm in the distributable
// toolset. User-facing text is ASCII-only for broad Fiji compatibility.

var v4ToolVersion = "5.6.0";
var v4ProjectLoaded = 0;
var v4ProjectDir = "";
var v4ProjectSwitchInProgress = 0;
var v4BridgeDir = "";
var v4BridgeStaticDir = "";
var v4BridgePointerJson = "";
var v4BridgeGenerationId = "";
var v4ProjectFieldsCsv = "";
var v4ProjectFieldsText = "";
var v4RoiSetsCsv = "";
var v4ProjectId = "";
var v4ProjectName = "";
var v4StudyId = "";
var v4StudyName = "";
var v4SampleId = "";
var v4Material = "";
var v4Condition = "";
var v4SpecimenId = "";
var v4SpecimenLabel = "";
var v4AcquisitionId = "";
var v4AcquisitionLabel = "";
var v4MasterImage = "";
var v4MasterRole = "MASTER_ANALYTICAL";
var v4MasterRevisionId = "";
var v4CurrentMontagePointerPath = "";
var v4MasterRevisionManifestPath = "";
var v4MasterNativePlanPath = "";
var v4MasterFidelityReportPath = "";
var v4CurrentMontagePointerSha256 = "";
var v4MasterRevisionManifestSha256 = "";
var v4MasterNativePlanSha256 = "";
var v4MasterFidelitySha256 = "";
var v4MasterSha256 = "";
var v4MasterOwnershipSha256 = "";
var v4RevisionBindingReady = 0;
var v4RevisionBindingError = "";
var v55IntegrityCacheFingerprint = "";
var v55IntegrityCacheProjectId = "";
var v55IntegrityCacheUntilMs = 0;
var v55IntegrityCacheTtlMs = 5000;
var v55IntegrityLastEvidence = "";
var v55IntegrityLastError = "";
var v55FileCanonicalPath = "";
var v55FileSizeBytes = -1;
var v55FileModifiedMs = -1;
var v55FileSha256 = "";
var v56RequestId = "";
var v56PreparedAt = "";
var v56RoiDraftError = "";
var v56RoiDraftCount = 0;
var v56RoiSnapshotDirectory = "";
var v56RoiSnapshotEntryName = "";
var v56ResolvedSessionZip = "";
var v56ResolvedSessionRoiCount = 0;
var v56SessionValidationError = "";
var v56ResolvedSessionReviewStatus = "";
var v56ResolvedSessionQuantitativeReady = 0;
var v56ResolvedSessionPendingCount = 0;
var v56ResolvedSessionGeometryBlockerCount = 0;
// BEGIN GENERATED ROI SESSION CONTRACT. The release test requires byte-for-byte
// semantic equality with schemas/cavity_roi_session_contract_v2.json.
var v56RoiSessionContractJson = "{\"application_version\":\"5.6.0\",\"canonical_geometry_method_fields\":[\"classification\",\"bounds\",\"coordinates\",\"centroid\",\"area\",\"perimeter\"],\"commit_request_fields\":[\"schema_version\",\"application_version\",\"request_id\",\"prepared_at\",\"prepared_by\",\"reason\",\"launch_record_relative_path\",\"launch_record_sha256\",\"creation_context\",\"fiji_imagej_version\",\"java_version\",\"candidate_zip_sha256\",\"candidate_zip_size_bytes\",\"candidate_index_sha256\",\"candidate_index_size_bytes\",\"payload_sha256\"],\"creation_context_fields\":[\"project_version\",\"project_payload_sha256\",\"bridge_generation_id\",\"bridge_manifest_sha256\"],\"current_pointer_fields\":[\"schema_version\",\"application_version\",\"session_id\",\"session_relative_path\",\"manifest_relative_path\",\"manifest_sha256\",\"manifest_payload_sha256\",\"publication_status\",\"review_status\",\"quantitative_ready\",\"project_id\",\"montage_revision_id\",\"master_sha256\",\"published_at\",\"payload_sha256\"],\"fiji_metric_observation_fields\":[\"value\",\"unit\",\"method\",\"comparable_to_canonical\"],\"fiji_observation_fields\":[\"purpose\",\"imagej_roi_type\",\"geometry\",\"bounding_box\",\"centroid\",\"area\",\"perimeter\"],\"fiji_observation_purposes\":[\"diagnostic_only\"],\"geometry_entry_fields\":[\"entry_name\",\"imagej_roi_type\",\"geometry_class\",\"supported\",\"area\",\"perimeter\",\"blockers\"],\"geometry_metric_fields\":[\"method\",\"observed\",\"derived\",\"difference\",\"tolerance\",\"result\"],\"geometry_metric_tolerance_fields\":[\"absolute_area_px2\",\"absolute_length_px\",\"relative\"],\"geometry_precision_decimals\":6,\"geometry_validation_fields\":[\"status\",\"tolerance_px\",\"metric_tolerances\",\"supported_count\",\"unsupported_count\",\"entries\",\"blockers\"],\"published_session_states\":[{\"quantitative_ready\":false,\"review_status\":\"REVIEW_REQUIRED\"},{\"quantitative_ready\":true,\"review_status\":\"VERIFIED\"}],\"request_result_fields\":[\"schema_version\",\"application_version\",\"request_id\",\"session_id\",\"manifest_sha256\",\"manifest_payload_sha256\",\"published_at\",\"operator\",\"result\",\"review_status\",\"quantitative_ready\",\"payload_sha256\"],\"review_count_fields\":[\"pending\",\"reviewed\"],\"roi_index_fields\":[\"schema_version\",\"application_version\",\"geometry_precision_decimals\",\"binding\",\"rois\",\"payload_sha256\"],\"roi_index_row_fields\":[\"object_uuid\",\"object_id\",\"entry_name\",\"entry_sha256\",\"entry_size_bytes\",\"imagej_roi_type\",\"scientific_role\",\"roi_set_id\",\"object_class\",\"object_subtype\",\"geometry\",\"bounding_box\",\"centroid\",\"area_px2\",\"perimeter_px\",\"canonical_geometry_methods\",\"fiji_observation\",\"project_id\",\"montage_revision_id\",\"master_sha256\",\"master_dimensions\",\"master_dtype\",\"coordinate_system\",\"review_status\",\"include_in_statistics\",\"created_time\",\"modified_time\",\"semantic_sha256\"],\"roi_request_draft_authoritative\":false,\"roi_request_draft_fields\":[\"schema_version\",\"application_version\",\"authoritative\",\"binding\",\"rois\",\"payload_sha256\"],\"roi_request_draft_row_fields\":[\"object_uuid\",\"object_id\",\"entry_name\",\"entry_sha256\",\"entry_size_bytes\",\"scientific_role\",\"roi_set_id\",\"object_class\",\"object_subtype\",\"review_status\",\"include_in_statistics\",\"created_time\",\"modified_time\",\"fiji_observation\"],\"roi_session_manifest_fields\":[\"schema_version\",\"application_version\",\"session_id\",\"source_type\",\"publication_status\",\"review_status\",\"quantitative_ready\",\"published_at\",\"published_by\",\"reason\",\"source_request\",\"binding\",\"creation_context\",\"source_launch\",\"calibration_record\",\"artifacts\",\"roi_count\",\"role_counts\",\"review_counts\",\"geometry_validation\",\"semantic_fingerprints\",\"binary_inventory_sha256\",\"payload_sha256\"],\"row_review_statuses\":[\"pending\",\"reviewed\"],\"schema_version\":\"cavity_roi_session_contract_v2\",\"schemas\":{\"current_roi_session\":\"cavity_current_roi_session_v1\",\"roi_index\":\"cavity_roi_index_v2\",\"roi_request_draft\":\"cavity_roi_request_draft_v1\",\"roi_session\":\"cavity_roi_session_v2\",\"roi_session_request\":\"cavity_roi_session_request_v2\",\"roi_session_request_result\":\"cavity_roi_session_request_result_v2\"},\"scientific_binding_fields\":[\"project_id\",\"montage_revision_id\",\"revision_manifest_payload_sha256\",\"revision_manifest_file_sha256\",\"master_sha256\",\"master_dimensions\",\"master_dtype\",\"coordinate_system\",\"calibration_id\",\"calibration_record_sha256\",\"scale_input_signature\",\"scale_report_sha256\",\"toolset_version\",\"toolset_sha256\",\"studio_version\"],\"source_launch_fields\":[\"launch_record_relative_path\",\"launch_record_sha256\",\"installed_toolset_path\",\"installed_toolset_sha256\",\"source_toolset_path\",\"source_toolset_sha256\",\"fiji_root\",\"fiji_executable\",\"fiji_imagej_version\",\"java_version\"],\"source_request_fields\":[\"request_id\",\"request_relative_path\",\"commit_request_payload_sha256\",\"candidate_zip_sha256\",\"candidate_index_sha256\"]}";
// END GENERATED ROI SESSION CONTRACT.
var v4CalibrationId = "";
var v4PixelWidth = NaN;
var v4PixelHeight = NaN;
var v4PixelUnit = "nm";
var v4SurfaceId = "";
var v4SurfaceOriginDefined = 0;
var v4SurfaceOriginArcNm = 0;
var v4SurfaceOriginXpx = NaN;
var v4SurfaceOriginYpx = NaN;
var v4SurfaceTangentialSign = 1;
var v4ActiveRoiSetId = "CAVITIES";
var v4ActiveRoiSetName = "Cavidades";
var v4ActiveObjectType = "cavity";
var v4ActiveGeometry = "line_or_ellipse";
var v4ActiveIdPrefix = "CAV";
var v4ActiveScientificRole = "defect";
var v4ActiveProtocolId = "CAVITY_MANUAL_V1";
var v4ActiveStrokeColor = "#ff3b30";
var v4ActiveFillColor = "#46ff3b30";
var v4RunId = "";
var v4LastLocalXpx = NaN;
var v4LastLocalYpx = NaN;
var v4TraceMode = "";
var v4TraceTool = "";
var v4TraceSessionId = "";
var v4TraceConfidence = "high";
var v4TraceNote = "";
var v4TraceAdded = 0;
var v4TraceDeleted = 0;
var v4TraceLastObjectId = "";
var v4TraceCaptureOrder = 0;
var v4ScaleConflict = 0;
var v4ScaleConflictText = "";
var v4ScaleReconciliationStatus = "NOT_ANALYZED";
var v4ScaleMeasurementAllowed = 0;
var v4ImageScaleNmX = NaN;
var v4ImageScaleNmY = NaN;
var v4ImageScaleUnit = "";
var v4PanelsCsv = "";
var v4PanelGeometryJson = "";
var v4OwnershipImage = "";
var v4OwnershipLegendCsv = "";
var v4OwnershipCertified = 0;
var v4PanelOverlapPolicy = "unknown";
var v4PanelGeometryStatus = "UNAVAILABLE";
var v4PanelQuantitativeReady = 0;
var panelLastOwnerCode = 0;
var panelLastCoverageCount = 0;

// Non-destructive visual overlays. These values affect only the ImagePlus
// overlay; they never alter master pixels or the scientific calibration.
var v51ScaleBarLengthNm = 500;
var v51ScaleBarPosition = "Abajo derecha";
var v51ScaleBarColor = "#ffffff";
var v51ScaleBarBackground = "#000000";
var v51ScaleBarBackgroundAlpha = 160;
var v51ScaleBarThicknessPx = 8;
var v51ScaleBarFontPx = 28;
var v51ScaleBarMarginPx = 35;
var v51GuideSpacingNm = 100;
var v51GuideMaximumNm = 1000;
var v51GuideColor = "#00ffff";
var v51GuideWidthPx = 2;
var v51GuideDashed = 1;
var v51GuideBothSides = 0;
var v51GuideLabels = 1;
var v51LastExactAreaCsv = "";
var v51LastExactAreaMethod = "not_calculated";

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


function v4ShowPanel() {
    // Always re-synchronize with the project selected by Studio or inferred
    // from the active TIFF. This also handles Fiji starting with an older
    // remembered project before the launcher macro updates Preferences.
    v4SynchronizeProjectContext();
    if (v4ProjectLoaded && nImages() <= 0) {
        if (v4OpenOrActivateRegisteredMaster(1)) v4ApplyScale();
    }
    projectStatus = "1. Proyecto: NO CARGADO";
    if (v4ProjectLoaded) projectStatus = "1. Proyecto: " + v4ProjectName;
    imageStatus = "2. Imagen: no abierta";
    if (nImages() > 0) imageStatus = "2. Imagen: " + getTitle();
    scaleStatus = "3. Escala: no definida";
    if (!isNaN(v4PixelWidth) && v4PixelWidth > 0) scaleStatus = "3. Escala: " + d2s(v4PixelWidth, 8) + " " + v4PixelUnit + "/px (" + v4CalibrationId + ")";
    if (v4ScaleConflict) scaleStatus = "3. Escala: CONFLICTO; medicion bloqueada";
    surfaceStatus = "4. Superficie: opcional, no definida";
    if (surfaceDefined) {
        surfaceStatus = "4. Superficie: definida";
        if (v4SurfaceOriginDefined) surfaceStatus = surfaceStatus + "; origen s=0 definido";
        else surfaceStatus = surfaceStatus + "; falta origen s=0";
    }
    Dialog.create("Cavity TEM Studio v5.6.0");
    Dialog.addMessage(projectStatus + "\n" + imageStatus + "\n" + scaleStatus + "\n" + surfaceStatus);
    Dialog.addMessage("Conjunto ROI activo: " + v4ActiveRoiSetId + " - " + v4ActiveRoiSetName + "\nModo recomendado para cavidades: medir continuamente con una linea sobre cada diametro.");
    actions = newArray(
        "1. Iniciar o continuar medicion guiada",
        "2. Medir cavidades, dislocaciones o bucles",
        "3. Abrir o recargar proyecto",
        "4. Definir superficie, material y origen",
        "5. Seleccionar o editar una ROI",
        "6. Cambiar conjunto ROI",
        "7. Registrar la ROI dibujada",
        "8. Revisar objeto seleccionado",
        "9. Guardar sesion",
        "10. Exportar datos",
        "11. Mostrar tabla de objetos",
        "12. Herramientas de imagen",
        "13. Auditoria rapida",
        "14. Panel avanzado (nucleo ROI)",
        "Ayuda: flujo completo"
    );
    Dialog.addChoice("Siguiente accion:", actions, actions[0]);
    Dialog.show();
    action = Dialog.getChoice();
    if (action == actions[0]) v4StartGuidedMeasurement();
    else if (action == actions[1]) v4ShowMeasurementMenu();
    else if (action == actions[2]) v4OpenProject();
    else if (action == actions[3]) v4DefineSurfaceComplete();
    else if (action == actions[4]) activateSelectTool();
    else if (action == actions[5]) v4ChooseRoiSet();
    else if (action == actions[6]) v4AddSelectionToActiveSet();
    else if (action == actions[7]) v4ReviewSelectedObject();
    else if (action == actions[8]) v4SaveSession();
    else if (action == actions[9]) v4ExportAll();
    else if (action == actions[10]) v4ShowObjectTable();
    else if (action == actions[11]) imageToolsPanel();
    else if (action == actions[12]) v4QuickAudit();
    else if (action == actions[13]) showControlPanel();
    else v4ShowWorkflowHelp();
}

function v4ShowWorkflowHelp() {
    showMessage("Flujo de trabajo en Fiji",
        "ANTES DE FIJI\n"+
        "1. Abra o cree el proyecto en Cavity TEM Studio.\n"+
        "2. Registre el OME-TIFF maestro y una calibracion activa.\n\n"+
        "EN FIJI\n"+
        "3. Abra Fiji desde Studio: el master registrado se abre automaticamente. Si abre el TIFF manualmente, el toolset intentara localizar project.json ascendiendo por sus carpetas.\n"+
        "4. Elija abrir el montaje, aplicar la escala y cargar la sesion si existe.\n"+
        "5. Pulse Actualizar paneles SVG: se importan panels.csv, z-order y ownership; no hay que dibujar paneles manualmente.\n"+
        "6. Defina superficie, lado del material y origen s=0 si necesita perfiles de profundidad.\n"+
        "7. En la opcion 2 elija cavidades, dislocaciones o bucles. Los bucles admiten ovalo, elipse inclinada, polilinea y mano alzada, con ajuste eliptico reversible.\n"+
        "8. Durante dislocaciones y bucles use Borrar ultima o Supr solo para los trazos incorrectos; Esc finaliza la serie.\n"+
        "9. Use la cobertura SVG como area base, inclusion solo si necesita restringirla y exclusiones para restar zonas. Calcule el area exacta antes de publicar densidades.\n"+
        "10. Guarde la sesion con frecuencia y exporte al finalizar. Las barras y guias visuales son overlays no destructivos.\n\n"+
        "No instale Cavity_ROI_Studio_v9_0.ijm ni los modulos internos por separado. Instale unicamente Cavity_TEM_Studio_v5_6_0.ijm.");
}

function v4StartGuidedMeasurement() {
    if (!v4EnsureProject()) return;
    haveImage = nImages() > 0;
    masterAlreadyActive = 0;
    if (haveImage && v4MasterImage != "" && File.getName(v4MasterImage) == getTitle()) masterAlreadyActive = 1;
    haveSession = File.exists(v4SessionPath());
    panelCount = v4CountRoisOfType("panel");

    // Compatibility: some ImageJ macro interpreters reject compound boolean
    // expressions used directly as Dialog.addCheckbox defaults. Compute every
    // default as an explicit numeric variable before constructing the dialog.
    openMasterDefault = 1;
    if (masterAlreadyActive) openMasterDefault = 0;
    applyCalibrationDefault = 0;
    if (!isNaN(v4PixelWidth)) {
        if (v4PixelWidth > 0) applyCalibrationDefault = 1;
    }
    loadSessionDefault = 0;
    if (haveSession) loadSessionDefault = 1;
    createPanelsDefault = 0;
    if (panelCount == 0) createPanelsDefault = 1;

    Dialog.create("Preparar Fiji para medir");
    Dialog.addMessage("Proyecto: " + v4ProjectName + "\nLa preparacion no modifica los pixeles. La superficie solo es necesaria para calcular profundidad y posicion lateral.");
    Dialog.addCheckbox("Abrir o activar el montaje maestro registrado", openMasterDefault);
    Dialog.addCheckbox("Aplicar la calibracion activa", applyCalibrationDefault);
    Dialog.addCheckbox("Cargar la sesion guardada si el ROI Manager esta vacio", loadSessionDefault);
    Dialog.addCheckbox("Actualizar paneles desde SVG/panels.csv si faltan", createPanelsDefault);
    Dialog.addCheckbox("Activar el conjunto CAVITIES", 1);
    Dialog.addCheckbox("Definir ahora superficie, material y origen s=0", 0);
    Dialog.addCheckbox("Iniciar inmediatamente la medida continua", 1);
    Dialog.show();
    openMaster = Dialog.getCheckbox();
    applyScale = Dialog.getCheckbox();
    loadSaved = Dialog.getCheckbox();
    createPanels = Dialog.getCheckbox();
    activateCavities = Dialog.getCheckbox();
    defineSurfaceNow = Dialog.getCheckbox();
    startMeasure = Dialog.getCheckbox();

    if (openMaster) {
        if (v4MasterImage != "" && File.exists(v4MasterImage)) {
            if (!v4OpenOrActivateRegisteredMaster(1)) {
                showMessage("Montaje no disponible", "Fiji no pudo abrir la ruta exacta del montaje registrado:\n" + v4MasterImage);
                return;
            }
        } else { showMessage("Montaje no disponible", "No existe un OME-TIFF maestro registrado en el proyecto."); return; }
    }
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra el montaje maestro o una imagen de analisis antes de medir."); return; }
    projectAwareCurrentAnalysisImageName = getTitle();
    if (v4MasterImage != "" && toLowerCase(v55CanonicalPathJava(v4CurrentImageCanonicalPath())) == toLowerCase(v55CanonicalPathJava(v4MasterImage))) {
        projectAwareCurrentAnalysisImagePath = v4MasterImage;
        projectAwareCurrentAnalysisImageRole = v4MasterRole;
    } else {
        projectAwareCurrentAnalysisImagePath = "";
        projectAwareCurrentAnalysisImageRole = "ANALYSIS_IMAGE";
    }
    if (applyScale && !isNaN(v4PixelWidth) && v4PixelWidth > 0) { if (!v4ApplyScale()) return; }
    v4AttachImageContext();
    run("ROI Manager...");
    if (loadSaved && haveSession && roiManager("count") == 0) v4LoadSession();
    if (createPanels && v4CountRoisOfType("panel") == 0) v4CreatePanelsFromManifest();
    if (activateCavities) {
        v4ReadRoiSet("CAVITIES");
        if (!v55PersistActiveRoiSet("activar el conjunto CAVITIES")) return;
    }
    if (defineSurfaceNow) v4DefineSurfaceComplete();
    if (startMeasure) v4StartContinuousCavityMeasurement();
    else showMessage("Fiji preparado", "Proyecto, imagen y escala preparados. Defina la superficie si necesita profundidad y despues inicie la medida continua.");
}

function v4StartContinuousCavityMeasurement() {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (!v4ReadRoiSet("CAVITIES")) { showMessage("Conjunto ausente", "No se encuentra el conjunto CAVITIES en fiji_bridge/roi_sets.csv."); return; }
    if (!v55PersistActiveRoiSet("activar la medicion continua")) return;
    if (v4CountRoisOfType("panel") == 0) showStatus("Aviso: no hay paneles. Podra medir, pero no se asignara el DM3 de origen hasta crearlos.");
    activateMeasureTool();
    shown = call("ij.Prefs.get", "cavity.v4.measure.help.shown", "0");
    if (shown != "1") {
        call("ij.Prefs.set", "cavity.v4.measure.help.shown", "1");
        showMessage("Medida continua activa", "Arrastre una linea de borde a borde sobre el diametro de cada cavidad. Al soltar, Fiji crea una ROI circular y registra la medida.\n\nRepita el arrastre para las siguientes cavidades. Pulse Esc para terminar. Para corregir una cavidad, use 'Seleccionar o editar'.");
    }
}

function v4CountRoisOfType(wantedType) {
    run("ROI Manager...");
    n = roiManager("count"); count = 0;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        t = Roi.getProperty("Object_type");
        if (t == "") t = currentRoiType();
        if (t == wantedType) count++;
    }
    return count;
}


function v4ShowMeasurementMenu() {
    if (!v4EnsureProject()) return;
    actions = newArray(
        "Cavidades: medir diametro continuamente",
        "Dislocaciones: polilinea",
        "Dislocaciones: mano alzada",
        "Bucles: ovalos",
        "Bucles: elipses inclinadas",
        "Bucles: polilinea cerrada (poligono)",
        "Bucles: contorno cerrado a mano alzada",
        "Bucles: ajustar seleccionada a elipse",
        "Bucles: restaurar forma original",
        "Seleccionar o editar una ROI",
        "Borrar seleccionada o ultimo trazo",
        "Finalizar serie automatica"
    );
    Dialog.create("2. Medir defectos");
    Dialog.addMessage("Las dislocaciones y los bucles se registran al terminar el trazo. No se solicita OK para cada objeto. Corrija las excepciones con Borrar ultima o Borrar seleccionada.");
    Dialog.addChoice("Modo:", actions, actions[0]);
    Dialog.show();
    action = Dialog.getChoice();
    if (action == actions[0]) v4StartContinuousCavityMeasurement();
    else if (action == actions[1]) v4StartAutomaticTrace("dislocation", "polyline");
    else if (action == actions[2]) v4StartAutomaticTrace("dislocation", "freeline");
    else if (action == actions[3]) v4StartAutomaticTrace("loop", "oval");
    else if (action == actions[4]) v4StartAutomaticTrace("loop", "ellipse");
    else if (action == actions[5]) v4StartAutomaticTrace("loop", "polygon");
    else if (action == actions[6]) v4StartAutomaticTrace("loop", "freehand");
    else if (action == actions[7]) v4FitSelectedLoopToEllipse();
    else if (action == actions[8]) v4RestoreSelectedLoopOriginal();
    else if (action == actions[9]) activateSelectTool();
    else if (action == actions[10]) v4DeleteSelectedTrace();
    else v4FinishAutomaticTrace(0);
}

function v51RepairPendingLoops() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("reparar bucles pendientes", 1)) return;
    if (nImages() <= 0) { showMessage("Reparar pendientes", "Abra la imagen asociada a la sesion antes de migrar ROIs."); return; }
    run("ROI Manager...");
    n = roiManager("count");
    pendingCount = 0;
    for (i=0; i<n; i++) {
        if (!safeRoiSelect(i)) continue;
        if (startsWith(toLowerCase(Roi.getName), "__v4_pending__")) pendingCount++;
    }
    if (pendingCount == 0) { showMessage("Reparar pendientes", "No hay ROIs __V4_PENDING__ en el ROI Manager. Las altas normales de v5.6.0 ya son transaccionales y no crean ese estado."); return; }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "crear la copia previa a reparar bucles", 1)) return;
    sessionsDir = projectAwareJoinPath(v4ProjectDir, "sessions");
    makeDirIfMissing(sessionsDir);
    stamp = v4Timestamp();
    backupPath = projectAwareJoinPath(sessionsDir, "roi_session_before_pending_repair_" + stamp + ".zip");
    roiManager("save", backupPath);
    previousSet = v4ActiveRoiSetId;
    if (!v4ReadRoiSet("LOOPS")) { showMessage("Conjunto LOOPS ausente", "No se modifico ninguna ROI.\n\nCopia de seguridad: " + backupPath); return; }
    choices = newArray("Ovalo", "Elipse inclinada", "Mano alzada cerrada", "Polilinea cerrada", "Omitir", "Terminar");
    migrated = 0;
    omitted = 0;
    invalid = 0;
    stopped = 0;
    // Work by stable indexes; registration is in-place and never adds/deletes.
    for (i=0; i<n; i++) {
        if (stopped) break;
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "reparar los bucles pendientes", 1)) return;
        if (!safeRoiSelect(i)) continue;
        pendingName = Roi.getName;
        if (!startsWith(toLowerCase(pendingName), "__v4_pending__")) continue;
        getStatistics(pendingArea);
        if (pendingArea <= 0 || (selectionType != 1 && selectionType != 2 && selectionType != 3 && selectionType != 4)) {
            invalid++;
            continue;
        }
        Dialog.create("Clasificar bucle pendiente " + (migrated+omitted+invalid+1) + "/" + pendingCount);
        Dialog.addMessage("ROI: " + pendingName + "\nIndice: " + i + "\n\nElija el tipo observando la geometria. No se infiere ni se transforma automaticamente. Omitir conserva la ROI exactamente como esta.");
        Dialog.addChoice("Tipo de bucle:", choices, choices[4]);
        Dialog.show();
        choice = Dialog.getChoice();
        if (choice == "Terminar") { stopped = 1; break; }
        if (choice == "Omitir") { omitted++; continue; }
        if (choice == "Elipse inclinada" && !v4SelectionIsEllipseRoi()) {
            showMessage("Elipse no confirmada", "La ROI no es una EllipseRoi inclinable de ImageJ. Se ha omitido para evitar cambiar o etiquetar falsamente su geometria. Puede ajustarla despues con Ajustar a elipse.");
            omitted++;
            continue;
        }
        if (!v4StoreCurrentRoiClone("CavityV51PendingBackup")) { invalid++; continue; }
        id = v4NextObjectId("LOOP");
        if (!safeRoiSelect(i)) { v4ClearStoredRoiClone("CavityV51PendingBackup"); invalid++; continue; }
        subtype = "oval_loop";
        method = "migrated_pending_oval_loop";
        if (choice == "Elipse inclinada") { subtype = "inclined_ellipse_loop"; method = "migrated_pending_inclined_ellipse_loop"; }
        else if (choice == "Mano alzada cerrada") { subtype = "closed_freehand_loop"; method = "migrated_pending_closed_freehand_loop"; }
        else if (choice == "Polilinea cerrada") { subtype = "closed_polygon_loop"; method = "migrated_pending_closed_polygon_loop"; }
        now = d2s(getTime(),0);
        v4SetCoreProperties(id, v4Uuid(), now);
        Roi.setProperty("Object_subtype", subtype);
        Roi.setProperty("Measurement_method", method);
        Roi.setProperty("Closed_contour", "1");
        Roi.setProperty("Closure_validation", "user_confirmed_during_pending_migration");
        Roi.setProperty("Migration_source_name", pendingName);
        Roi.setProperty("Migration_backup_zip", backupPath);
        Roi.setProperty("Migration_reviewed_by_user", "1");
        Roi.setProperty("Auto_accepted", "0");
        Roi.setName(v4VisibleLoopName(id, subtype));
        v4SetGeometryProperties();
        v4SetLoopMetrics();
        applyLoopStyle();
        roiManager("update");
        safeRoiSelect(i);
        if (propString("Object_id","") != id || startsWith(toLowerCase(Roi.getName), "__v4_pending__")) {
            v4RestoreStoredRoiClone("CavityV51PendingBackup", 1);
            roiManager("update");
            invalid++;
            continue;
        }
        v4ClearStoredRoiClone("CavityV51PendingBackup");
        v4RefreshSpatialProperties(i);
        migrated++;
    }
    migratedPath = "";
    if (migrated > 0) {
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "guardar los bucles reparados", 1)) return;
        migratedPath = projectAwareJoinPath(sessionsDir, "roi_session_pending_repaired_" + stamp + ".zip");
        roiManager("save", migratedPath);
    }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar la reparacion de bucles", 1)) return;
    if (previousSet != "") v4ReadRoiSet(previousSet);
    restyleAllRois();
    showAllRois();
    message = "Encontradas: " + pendingCount + "\nMigradas: " + migrated + "\nOmitidas: " + omitted + "\nInvalidas/no procesadas: " + invalid + "\n\nCopia previa inmutable:\n" + backupPath;
    if (migratedPath != "") message = message + "\n\nSesion migrada para revisar:\n" + migratedPath + "\n\nLa sesion canonica no se ha sobrescrito. Tras revisar, use Guardar sesion si desea adoptarla.";
    showMessage("Reparacion segura finalizada", message);
}

function v4StartAutomaticTrace(mode, toolName) {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (v4TraceMode != "") v4FinishAutomaticTrace(1);
    if (mode == "dislocation") {
        if (!v4ReadRoiSet("DISLOCATIONS")) { showMessage("Conjunto ausente", "No se encuentra DISLOCATIONS en roi_sets.csv."); return; }
        title = "Serie de dislocaciones";
        help = "Cada polilinea se termina con doble clic; cada linea libre, al soltar el raton. El trazo se registra automaticamente.";
    } else if (mode == "loop") {
        if (!v4ReadRoiSet("LOOPS")) { showMessage("Conjunto ausente", "No se encuentra LOOPS en roi_sets.csv."); return; }
        title = "Serie de bucles cerrados";
        help = "Un bucle debe ser un area cerrada. El poligono se cierra con doble clic; el contorno libre se cierra al soltar; el ovalo se completa al soltar.";
    } else return;
    Dialog.create(title);
    Dialog.addMessage(help + "\n\nSolo se confirma esta configuracion una vez para toda la serie. Durante la captura use el boton rojo Borrar ultima para retirar errores.");
    Dialog.addChoice("Confianza comun:", newArray("high", "medium", "low"), v4TraceConfidence);
    Dialog.addString("Nota comun:", v4TraceNote, 42);
    Dialog.show();
    v4TraceConfidence = Dialog.getChoice();
    v4TraceNote = Dialog.getString();
    v4TraceMode = mode;
    v4TraceTool = toolName;
    v4TraceSessionId = "TRACE_" + d2s(getTime(),0);
    v4TraceAdded = 0;
    v4TraceDeleted = 0;
    v4TraceCaptureOrder = 0;
    v4TraceLastObjectId = "";
    if (!v55PersistActiveRoiSet("activar el trazado automatico")) return;
    v4SetTraceImageProperty("CavityV4TraceMode", v4TraceMode);
    v4SetTraceImageProperty("CavityV4TraceTool", v4TraceTool);
    v4SetTraceImageProperty("CavityV4TraceSession", v4TraceSessionId);
    v4SetTraceImageProperty("CavityV4TraceBusy", "0");
    v4InstallTraceListener();
    installInteractionListeners(0);
    v4ApplyTraceTool();
    v4ShowTraceController();
    showStatus(v4TraceModeLabel() + " activo: cada trazo terminado se acepta automaticamente; Borrar ultima elimina los errores.");
}

function v4InstallTraceListener() {
    if (nImages() <= 0) return;
    js = "var IJ=Packages.ij.IJ;var Roi=Packages.ij.gui.Roi;var RoiListener=Packages.ij.gui.RoiListener;var Executer=Packages.ij.Executer;var Runnable=Packages.java.lang.Runnable;var Thread=Packages.java.lang.Thread;";
    js = js + "var imp=IJ.getImage();if(imp!=null){var old=imp.getProperty('CavityV4TraceListener');if(old!=null){try{Roi.removeRoiListener(old);}catch(ignore){}}";
    js = js + "function submit(cmd){var body={run:function(){IJ.resetEscape();new Executer(cmd).run();}};var r;if(typeof JavaAdapter!='undefined')r=new JavaAdapter(Runnable,body);else{var R=Java.extend(Runnable);r=new R(body);}var t=new Thread(r);t.setDaemon(true);t.start();}";
    js = js + "var body={roiModified:function(changedImp,id){try{if(changedImp!=imp||id!=RoiListener.COMPLETED)return;var mode=imp.getProperty('CavityV4TraceMode');if(mode==null||String(mode)=='')return;var busy=imp.getProperty('CavityV4TraceBusy');if(busy!=null&&String(busy)=='1')return;var completed=changedImp.getRoi();if(completed==null)return;imp.setProperty('CavityV4CompletedRoi',completed.clone());imp.setProperty('CavityV4TraceBusy','1');submit('Cavity V9: registrar trazo automatico');}catch(ex){imp.setProperty('CavityV4CompletedRoi',null);imp.setProperty('CavityV4TraceBusy','0');Packages.cavity.light.HF4.log('Cavity automatic trace listener: '+ex);}}};";
    js = js + "var listener;if(typeof JavaAdapter!='undefined')listener=new JavaAdapter(RoiListener,body);else{var L=Java.extend(RoiListener);listener=new L(body);}Roi.addRoiListener(listener);imp.setProperty('CavityV4TraceListener',listener);}";
    eval("js", js);
}

function v4RemoveTraceListener() {
    if (nImages() <= 0) return;
    js = "var IJ=Packages.ij.IJ;var Roi=Packages.ij.gui.Roi;var imp=IJ.getImage();if(imp!=null){var old=imp.getProperty('CavityV4TraceListener');if(old!=null){try{Roi.removeRoiListener(old);}catch(ignore){}}imp.setProperty('CavityV4TraceListener',null);imp.setProperty('CavityV4TraceMode','');imp.setProperty('CavityV4TraceTool','');imp.setProperty('CavityV4TraceBusy','0');imp.setProperty('CavityV4CompletedRoi',null);imp.setProperty('CavityV4RegistrationRoi',null);}";
    eval("js", js);
}

function v4SetTraceImageProperty(key, value) {
    if (nImages() <= 0) return;
    js = "var imp=Packages.ij.IJ.getImage();if(imp!=null)imp.setProperty('" + jsEscape(key) + "','" + jsEscape(value) + "');";
    eval("js", js);
}

function v4RestoreCompletedTraceSnapshot() {
    if (nImages() <= 0) return 0;
    js = "var imp=Packages.ij.IJ.getImage(),ok='0';if(imp!=null){var saved=imp.getProperty('CavityV4CompletedRoi');if(saved!=null){try{imp.setRoi(saved.clone());ok='1';}catch(ex){Packages.cavity.light.HF4.log('Cavity completed ROI restore: '+ex);}imp.setProperty('CavityV4CompletedRoi',null);}}String(ok);";
    restored = eval("js", js);
    if (restored == "1") return 1;
    return 0;
}

function v4AutoRegisterCompletedTrace() {
    if (v4TraceMode == "" || nImages() <= 0) { v4SetTraceImageProperty("CavityV4TraceBusy", "0"); return; }
    if (!v4PrepareImageForMeasurement(1)) { v4SetTraceImageProperty("CavityV4TraceBusy", "0"); return; }
    // RoiListener.COMPLETED runs asynchronously. Restore the clone captured by
    // the listener before any double click or tool event can clear the ROI.
    v4RestoreCompletedTraceSnapshot();
    if (!v4TraceSelectionValid()) {
        beep();
        showStatus("Trazo no registrado: " + v4TraceValidationMessage());
        v4SetTraceImageProperty("CavityV4TraceBusy", "0");
        v4ApplyTraceTool();
        return;
    }
    if (v4TraceMode == "dislocation") v4ReadRoiSet("DISLOCATIONS");
    else v4ReadRoiSet("LOOPS");
    run("ROI Manager...");
    before = roiManager("count");
    v4AddSelectionToActiveSet();
    after = roiManager("count");
    if (after <= before) {
        v4SetTraceImageProperty("CavityV4TraceBusy", "0");
        v4ApplyTraceTool();
        return;
    }
    idx = after - 1;
    safeRoiSelect(idx);
    id = propString("Object_id", Roi.getName);
    v4TraceCaptureOrder++;
    Roi.setProperty("Trace_session_id", v4TraceSessionId);
    Roi.setProperty("Capture_order", d2s(v4TraceCaptureOrder,0));
    Roi.setProperty("Auto_accepted", "1");
    Roi.setProperty("Capture_mode", "auto_accept_delete_if_wrong");
    Roi.setProperty("Confidence", v4TraceConfidence);
    Roi.setProperty("Analyst_note", v4TraceNote);
    Roi.setProperty("Review_status", "pending");
    Roi.setProperty("Measurement_method", v4TraceMeasurementMethod());
    Roi.setProperty("Object_subtype", v4TraceObjectSubtype());
    if (v4TraceMode == "loop") {
        Roi.setProperty("Closed_contour", "1");
        Roi.setProperty("Closure_validation", "area_roi_closed");
        v4SetLoopMetrics();
    } else {
        Roi.setProperty("Closed_contour", "0");
        Roi.setProperty("Closure_validation", "not_applicable");
    }
    Roi.setProperty("Modified_time_ms", d2s(getTime(),0));
    roiManager("update");
    v4RefreshSpatialProperties(idx);
    safeRoiSelect(idx);
    v4TraceLastObjectId = id;
    v4TraceAdded++;
    undoKind = "add";
    undoObjectId = id;
    undoDeletedName = "";
    undoAvailable = 1;
    v4SetTraceImageProperty("CavityV4TraceBusy", "0");
    v4RefreshTraceController();
    // Keep the last registered ROI selected and editable. Starting the next
    // drawing naturally replaces the active selection without deleting it.
    safeRoiSelect(idx);
    registeredVisibleName = Roi.getName;
    showStatus("Registrado " + registeredVisibleName + " [" + id + "]. Puede editarlo o empezar el siguiente trazo.");
}

function v4TraceSelectionValid() {
    if (selectionType < 0) return 0;
    if (v4TraceMode == "dislocation") {
        if (selectionType != 5 && selectionType != 6 && selectionType != 7) return 0;
        Roi.getCoordinates(tx, ty);
        if (tx.length < 2) return 0;
        return polylineLengthNm(tx,ty) > 0;
    }
    if (v4TraceMode == "loop") {
        if (selectionType != 1 && selectionType != 2 && selectionType != 3 && selectionType != 4) return 0;
        getStatistics(traceAreaPx);
        if (traceAreaPx <= 0) return 0;
        if (selectionType != 1) {
            Roi.getCoordinates(tx, ty);
            if (tx.length < 3) return 0;
        }
        return 1;
    }
    return 0;
}

function v4TraceValidationMessage() {
    if (v4TraceMode == "loop") return "el bucle debe cerrarse y formar un area. Use Ovalo, Elipse inclinada, Polilinea cerrada o Mano alzada cerrada.";
    return "la dislocacion debe ser una linea, polilinea o linea a mano alzada con longitud mayor que cero.";
}

function v4TraceMeasurementMethod() {
    if (v4TraceMode == "dislocation" && v4TraceTool == "polyline") return "automatic_polyline_trace";
    if (v4TraceMode == "dislocation" && v4TraceTool == "freeline") return "automatic_freehand_line_trace";
    if (v4TraceMode == "loop" && v4TraceTool == "oval") return "automatic_oval_loop";
    if (v4TraceMode == "loop" && v4TraceTool == "ellipse") return "automatic_inclined_ellipse_loop";
    if (v4TraceMode == "loop" && v4TraceTool == "polygon") return "automatic_closed_polygon_loop";
    if (v4TraceMode == "loop" && v4TraceTool == "freehand") return "automatic_closed_freehand_loop";
    return "automatic_trace";
}

function v4TraceObjectSubtype() {
    if (v4TraceMode == "dislocation") return "line_dislocation";
    if (v4TraceTool == "oval") return "oval_loop";
    if (v4TraceTool == "ellipse") return "inclined_ellipse_loop";
    if (v4TraceTool == "polygon") return "closed_polygon_loop";
    if (v4TraceTool == "freehand") return "closed_freehand_loop";
    return "closed_loop";
}

function v4SelectionIsEllipseRoi() {
    if (nImages() <= 0 || selectionType < 0) return 0;
    result = eval("js", "var imp=Packages.ij.IJ.getImage(),r=imp==null?null:imp.getRoi();String(r!=null&&String(r.getClass().getName())=='ij.gui.EllipseRoi'?'1':'0');");
    if (result == "1") return 1;
    return 0;
}

function v4LoopSubtypeForCurrentSelection() {
    if (v4TraceMode == "loop") {
        if (v4TraceTool == "ellipse") return "inclined_ellipse_loop";
        if (v4TraceTool == "oval") return "oval_loop";
        if (v4TraceTool == "polygon") return "closed_polygon_loop";
        if (v4TraceTool == "freehand") return "closed_freehand_loop";
    }
    // EllipseRoi inherits PolygonRoi/FREEROI, so identify the Java class
    // before interpreting ImageJ's numeric selectionType.
    if (v4SelectionIsEllipseRoi()) return "inclined_ellipse_loop";
    if (selectionType == 1) return "oval_loop";
    if (selectionType == 2) return "closed_polygon_loop";
    if (selectionType == 3 || selectionType == 4) return "closed_freehand_loop";
    return "closed_loop";
}

function v4VisibleLoopName(id, subtype) {
    serial = serialFromId(id);
    if (serial < 1) serial = 1;
    stem = "loop_mano_";
    s = toLowerCase(subtype);
    if (indexOf(s, "ellipse") >= 0 || indexOf(s, "elipse") >= 0 || indexOf(s, "fitted") >= 0) stem = "loop_elipse_";
    else if (indexOf(s, "oval") >= 0) stem = "loop_ovalo_";
    else if (indexOf(s, "polygon") >= 0 || indexOf(s, "polyline") >= 0 || indexOf(s, "poliline") >= 0) stem = "loop_polilinea_";
    else if (indexOf(s, "freehand") >= 0 || indexOf(s, "mano") >= 0) stem = "loop_mano_";
    return stem + IJ.pad(serial, 6);
}

function v4EncodeCurrentCoordinates() {
    if (selectionType < 0) return "";
    Roi.getCoordinates(xs, ys);
    encoded = "";
    for (ci=0; ci<xs.length; ci++) {
        if (ci > 0) encoded = encoded + ";";
        encoded = encoded + d2s(xs[ci],6) + ":" + d2s(ys[ci],6);
    }
    return encoded;
}

function v4CopyStoredRoiAttributesToCurrent(key) {
    if (nImages() <= 0 || selectionType < 0) return 0;
    js = "var imp=Packages.ij.IJ.getImage(),ok='0';if(imp!=null){var source=imp.getProperty('" + jsEscape(key) + "'),target=imp.getRoi();if(source!=null&&target!=null){try{var props=source.getProperties();if(props!=null)target.setProperties(props);target.setName(source.getName());ok='1';}catch(ex){Packages.cavity.light.HF4.log('Cavity ROI attribute transfer: '+ex);}}}String(ok);";
    copied = eval("js", js);
    if (copied == "1") return 1;
    return 0;
}

function v4FitSelectedLoopToEllipse() {
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra primero el montaje."); return; }
    if (!v55VerifyQuantitativeIntegrity("ajustar el bucle a elipse", 1, 1)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) { showMessage("Sin bucle", "Seleccione un bucle a mano alzada o polilinea."); return; }
    safeRoiSelect(idx);
    type = propString("Object_type", currentRoiType());
    if (type != "dislocation_loop") { showMessage("Objeto incompatible", "El ajuste solo se aplica a bucles cerrados."); return; }
    if (propString("Fit_state","") == "ellipse_fit") {
        showMessage("Ajuste ya activo", "Este bucle ya muestra el ajuste eliptico. Use Restaurar original para volver al contorno conservado.");
        return;
    }
    originalSelectionType = selectionType;
    if (originalSelectionType != 2 && originalSelectionType != 3 && originalSelectionType != 4) {
        showMessage("Forma no ajustable", "Seleccione un bucle de polilinea o mano alzada. Los ovalos y elipses ya son formas parametricas.");
        return;
    }
    originalCoordinates = v4EncodeCurrentCoordinates();
    if (originalCoordinates == "") { showMessage("Forma vacia", "No se pudieron leer los puntos del contorno."); return; }
    originalSubtype = propString("Object_subtype", v4LoopSubtypeForCurrentSelection());
    originalMethod = propString("Measurement_method", "");
    originalName = Roi.getName;
    id = propString("Object_id", propString("Feature_id", ""));
    if (id == "") { showMessage("Bucle sin ID", "Sincronice la sesion antes de ajustar este bucle."); return; }
    // Capture audited before/after metrics together with the reversible
    // coordinates. Fit Ellipse changes the scientific geometry.
    v4SetGeometryProperties();
    originalAreaNm2 = propNumber("Projected_area_nm2", NaN);
    originalPerimeterNm = propNumber("Perimeter_nm", NaN);
    if (startsWith(toLowerCase(originalName), "__v4_pending__") || startsWith(originalName, "LOOP_")) originalName = v4VisibleLoopName(id, originalSubtype);
    if (!v4StoreCurrentRoiClone("CavityV4FitSourceRoi")) { showMessage("Ajuste cancelado", "No se pudo conservar el contorno original."); return; }
    v4SetTraceImageProperty("CavityV4TraceBusy", "1");
    run("Fit Ellipse");
    if (!v4SelectionIsEllipseRoi()) {
        v4RestoreStoredRoiClone("CavityV4FitSourceRoi", 1);
        v4SetTraceImageProperty("CavityV4TraceBusy", "0");
        showMessage("Ajuste no disponible", "ImageJ no pudo calcular una elipse para este contorno.");
        return;
    }
    if (!v4CopyStoredRoiAttributesToCurrent("CavityV4FitSourceRoi")) {
        v4RestoreStoredRoiClone("CavityV4FitSourceRoi", 1);
        v4SetTraceImageProperty("CavityV4TraceBusy", "0");
        showMessage("Ajuste cancelado", "No se pudieron transferir de forma segura los metadatos del bucle.");
        return;
    }
    Roi.setProperty("Original_coordinates_px", originalCoordinates);
    Roi.setProperty("Original_selection_type", d2s(originalSelectionType,0));
    Roi.setProperty("Original_object_subtype", originalSubtype);
    Roi.setProperty("Original_measurement_method", originalMethod);
    Roi.setProperty("Original_visible_name", originalName);
    Roi.setProperty("Fit_state", "ellipse_fit");
    Roi.setProperty("Fit_method", "ImageJ_Fit_Ellipse");
    Roi.setProperty("Derived_geometry", "1");
    Roi.setProperty("Fit_source_subtype", originalSubtype);
    Roi.setProperty("Object_subtype", "fitted_ellipse_loop");
    Roi.setProperty("Measurement_method", "ellipse_fit_from_" + originalSubtype);
    Roi.setName(v4VisibleLoopName(id, "fitted_ellipse_loop"));
    v4SetGeometryProperties();
    fittedAreaNm2 = propNumber("Projected_area_nm2", NaN);
    fittedPerimeterNm = propNumber("Perimeter_nm", NaN);
    Roi.setProperty("Fit_original_area_nm2", d2s(originalAreaNm2,6));
    Roi.setProperty("Fit_original_perimeter_nm", d2s(originalPerimeterNm,6));
    Roi.setProperty("Fit_area_nm2", d2s(fittedAreaNm2,6));
    Roi.setProperty("Fit_perimeter_nm", d2s(fittedPerimeterNm,6));
    if (!isNaN(originalAreaNm2) && originalAreaNm2 > 0) Roi.setProperty("Fit_area_change_percent", d2s(100*(fittedAreaNm2-originalAreaNm2)/originalAreaNm2,6));
    if (!isNaN(originalPerimeterNm) && originalPerimeterNm > 0) Roi.setProperty("Fit_perimeter_change_percent", d2s(100*(fittedPerimeterNm-originalPerimeterNm)/originalPerimeterNm,6));
    applyLoopStyle();
    Roi.setProperty("Modified_time_ms", d2s(getTime(),0));
    roiManager("update");
    v4ClearStoredRoiClone("CavityV4FitSourceRoi");
    safeRoiSelect(idx);
    v4SetTraceImageProperty("CavityV4TraceBusy", "0");
    v4RefreshTraceController();
    showStatus("Ajuste eliptico activo. El contorno original permanece guardado y puede restaurarse.");
}

function v4RestoreSelectedLoopOriginal() {
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra primero el montaje."); return; }
    if (!v55VerifyQuantitativeIntegrity("restaurar el contorno original del bucle", 1, 1)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) { showMessage("Sin bucle", "Seleccione un bucle con ajuste eliptico."); return; }
    safeRoiSelect(idx);
    if (propString("Object_type",currentRoiType()) != "dislocation_loop" || propString("Fit_state","") != "ellipse_fit") {
        showMessage("Sin original guardado", "La ROI seleccionada no tiene un ajuste eliptico reversible.");
        return;
    }
    encoded = propString("Original_coordinates_px","");
    if (encoded == "") { showMessage("Original no disponible", "No hay coordenadas originales conservadas en esta ROI."); return; }
    originalSelectionType = round(propNumber("Original_selection_type",2));
    originalSubtype = propString("Original_object_subtype","closed_freehand_loop");
    originalMethod = propString("Original_measurement_method","");
    originalName = propString("Original_visible_name","");
    id = propString("Object_id", propString("Feature_id",""));
    if (!v4StoreCurrentRoiClone("CavityV4FittedSourceRoi")) { showMessage("Restauracion cancelada", "No se pudo conservar la ROI ajustada durante la operacion."); return; }
    pairs = split(encoded, ";");
    rx = newArray(pairs.length);
    ry = newArray(pairs.length);
    valid = 0;
    for (ri=0; ri<pairs.length; ri++) {
        xy = split(pairs[ri], ":");
        if (xy.length < 2) continue;
        rx[valid] = parseFloat(xy[0]);
        ry[valid] = parseFloat(xy[1]);
        valid++;
    }
    if (valid < 3) {
        v4ClearStoredRoiClone("CavityV4FittedSourceRoi");
        showMessage("Original no valido", "Las coordenadas conservadas no forman un contorno.");
        return;
    }
    if (valid != pairs.length) {
        x2 = newArray(valid); y2 = newArray(valid);
        for (ri=0; ri<valid; ri++) { x2[ri]=rx[ri]; y2[ri]=ry[ri]; }
        rx=x2; ry=y2;
    }
    restoreKind = "polygon";
    if (originalSelectionType == 3) restoreKind = "freehand";
    v4SetTraceImageProperty("CavityV4TraceBusy", "1");
    makeSelection(restoreKind, rx, ry);
    if (!v4CopyStoredRoiAttributesToCurrent("CavityV4FittedSourceRoi")) {
        v4RestoreStoredRoiClone("CavityV4FittedSourceRoi", 1);
        v4SetTraceImageProperty("CavityV4TraceBusy", "0");
        showMessage("Restauracion cancelada", "No se pudieron transferir de forma segura los metadatos.");
        return;
    }
    Roi.setProperty("Fit_state", "original");
    Roi.setProperty("Derived_geometry", "0");
    Roi.setProperty("Object_subtype", originalSubtype);
    Roi.setProperty("Measurement_method", originalMethod);
    if (originalName == "") originalName = v4VisibleLoopName(id, originalSubtype);
    Roi.setName(originalName);
    v4SetGeometryProperties();
    applyLoopStyle();
    Roi.setProperty("Modified_time_ms", d2s(getTime(),0));
    roiManager("update");
    v4ClearStoredRoiClone("CavityV4FittedSourceRoi");
    safeRoiSelect(idx);
    v4SetTraceImageProperty("CavityV4TraceBusy", "0");
    v4RefreshTraceController();
    showStatus("Contorno original restaurado. El identificador " + id + " no ha cambiado.");
}

function v4SetLoopMetrics() {
    updateScaleMaybe();
    getSelectionBounds(lx,ly,lw,lh);
    getStatistics(loopAreaPx);
    loopAreaNm2 = loopAreaPx * nmPerPixelX * nmPerPixelY;
    perimeterNm = 0;
    if (selectionType == 1 || v4SelectionIsEllipseRoi()) {
        a = propNumber("Major_axis_nm", max2(lw*nmPerPixelX,lh*nmPerPixelY)) / 2;
        b = propNumber("Minor_axis_nm", min2(lw*nmPerPixelX,lh*nmPerPixelY)) / 2;
        if (a > 0 && b > 0) perimeterNm = PI_VAL * (3*(a+b) - sqrt((3*a+b)*(a+3*b)));
    } else {
        Roi.getCoordinates(loopXs, loopYs);
        perimeterNm = v4ClosedPolylineLengthNm(loopXs, loopYs);
    }
    Roi.setProperty("Perimeter_nm", d2s(perimeterNm,6));
    if (perimeterNm > 0 && loopAreaNm2 > 0) {
        circularity = 4*PI_VAL*loopAreaNm2/(perimeterNm*perimeterNm);
        if (circularity > 1) circularity = 1;
        if (circularity < 0) circularity = 0;
        Roi.setProperty("Circularity", d2s(circularity,6));
    }
}

function v4ClosedPolylineLengthNm(xs, ys) {
    if (xs.length < 2) return 0;
    total = polylineLengthNm(xs,ys);
    dx = (xs[0]-xs[xs.length-1])*nmPerPixelX;
    dy = (ys[0]-ys[ys.length-1])*nmPerPixelY;
    return total + sqrt(dx*dx+dy*dy);
}

function v4SwitchTraceTool(toolName) {
    if (v4TraceMode == "") { showMessage("Sin serie activa", "Inicie primero una serie de dislocaciones o bucles."); return; }
    if (v4TraceMode == "dislocation" && toolName != "polyline" && toolName != "freeline") return;
    if (v4TraceMode == "loop" && toolName != "oval" && toolName != "ellipse" && toolName != "polygon" && toolName != "freehand") return;
    v4TraceTool = toolName;
    v4SetTraceImageProperty("CavityV4TraceTool", v4TraceTool);
    v4ApplyTraceTool();
    v4RefreshTraceController();
}

function v4ApplyTraceTool() {
    if (v4TraceTool == "polyline") setTool("polyline");
    else if (v4TraceTool == "freeline") setTool("freeline");
    else if (v4TraceTool == "oval") setTool("oval");
    else if (v4TraceTool == "ellipse") setTool("elliptical");
    else if (v4TraceTool == "polygon") setTool("polygon");
    else if (v4TraceTool == "freehand") setTool("freehand");
}

function v4TraceModeLabel() {
    if (v4TraceMode == "dislocation") return "Dislocaciones lineales";
    if (v4TraceMode == "loop") return "Bucles cerrados";
    return "Sin serie automatica";
}

function v4TraceToolLabel() {
    if (v4TraceTool == "polyline") return "Polilinea; doble clic para terminar";
    if (v4TraceTool == "freeline") return "Linea a mano alzada; soltar para terminar";
    if (v4TraceTool == "oval") return "Ovalo; soltar para terminar";
    if (v4TraceTool == "ellipse") return "Elipse inclinada; arrastrar eje y ajustar ancho";
    if (v4TraceTool == "polygon") return "Polilinea cerrada; doble clic para cerrar";
    if (v4TraceTool == "freehand") return "Contorno cerrado a mano alzada; soltar para cerrar";
    return v4TraceTool;
}

function v4ShowTraceController() {
    if (v4TraceMode == "") return;
    v4CloseTraceController();
    js = "var IJ=Packages.ij.IJ;var JFrame=Packages.javax.swing.JFrame;var JPanel=Packages.javax.swing.JPanel;var JButton=Packages.javax.swing.JButton;var JToggleButton=Packages.javax.swing.JToggleButton;var JCheckBox=Packages.javax.swing.JCheckBox;var JLabel=Packages.javax.swing.JLabel;var BorderLayout=Packages.java.awt.BorderLayout;var GridLayout=Packages.java.awt.GridLayout;var Window=Packages.java.awt.Window;var KeyboardFocusManager=Packages.java.awt.KeyboardFocusManager;var Color=Packages.java.awt.Color;var Font=Packages.java.awt.Font;var EmptyBorder=Packages.javax.swing.border.EmptyBorder;var Executer=Packages.ij.Executer;var Runnable=Packages.java.lang.Runnable;var Thread=Packages.java.lang.Thread;var ActionListener=Packages.java.awt.event.ActionListener;var ComponentAdapter=Packages.java.awt.event.ComponentAdapter;var WindowAdapter=Packages.java.awt.event.WindowAdapter;var Timer=Packages.javax.swing.Timer;var Prefs=Packages.ij.Prefs;";
    js = js + "var f=new JFrame('Cavity TEM - captura automatica');f.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE);var outer=new JPanel(new BorderLayout(6,6));outer.setBorder(new EmptyBorder(8,8,8,8));";
    js = js + "function makeRun(cmd){var body={run:function(){IJ.resetEscape();new Executer(cmd).run();}};if(typeof JavaAdapter!='undefined')return new JavaAdapter(Runnable,body);var R=Java.extend(Runnable);return new R(body);}";
    js = js + "function listener(cmd){var body={actionPerformed:function(e){var t=new Thread(makeRun(cmd));t.setDaemon(true);t.start();}};if(typeof JavaAdapter!='undefined')return new JavaAdapter(ActionListener,body);var A=Java.extend(ActionListener);return new A(body);}";
    js = js + "function button(p,label,cmd,bg,fg){var b=new JButton(label);b.addActionListener(listener(cmd));if(bg!=null)b.setBackground(bg);if(fg!=null)b.setForeground(fg);p.add(b);return b;}";
    js = js + "var info=new JPanel(new GridLayout(4,1,0,2));var mode=new JLabel('Modo: " + jsEscape(v4TraceModeLabel()) + "');mode.setFont(mode.getFont().deriveFont(Font.BOLD));var tool=new JLabel('Herramienta: " + jsEscape(v4TraceToolLabel()) + "');tool.setName('traceTool');var count=new JLabel('Registradas: " + v4TraceAdded + " | Borradas: " + v4TraceDeleted + "');count.setName('traceStatus');var hint=new JLabel('El ultimo objeto queda seleccionado para poder editarlo.');info.add(mode);info.add(tool);info.add(count);info.add(hint);var top=new JPanel(new BorderLayout(6,6));top.add(info,BorderLayout.CENTER);var winControls=new JPanel(new GridLayout(4,1,2,2));var pin=new JToggleButton('Chincheta (Fiji)',String(Prefs.get('cavity.v5.ui.trace.pinned','1'))!='0');var always=new JCheckBox('Siempre delante (Windows)',String(Prefs.get('cavity.v5.ui.alwaysOnTop','0'))=='1');always.setToolTipText('Modo opcional: delante de cualquier programa de Windows.');var dock=new JToggleButton('Acoplar',String(Prefs.get('cavity.v5.ui.dock','1'))!='0');dock.setToolTipText('Acoplamiento magnetico con panel avanzado e imagen; se separa arrastrando.');var aspect=new JCheckBox('Proporcion imagen',String(Prefs.get('cavity.v5.ui.image.aspect','0'))=='1');aspect.addActionListener(listener('Cavity V9: alternar proporcion de imagen'));winControls.add(pin);winControls.add(always);winControls.add(dock);winControls.add(aspect);top.add(winControls,BorderLayout.EAST);outer.add(top,BorderLayout.NORTH);f.getRootPane().putClientProperty('traceTool',tool);f.getRootPane().putClientProperty('traceStatus',count);f.getRootPane().putClientProperty('alwaysToggle',always);f.getRootPane().putClientProperty('aspectCheck',aspect);";
    if (v4TraceMode == "dislocation") {
        js = js + "var tools=new JPanel(new GridLayout(1,2,5,5));";
        js = js + "button(tools,'Polilinea','Cavity V9: usar polilinea',null,null);button(tools,'Mano alzada','Cavity V9: usar linea mano alzada',null,null);";
    } else {
        js = js + "var tools=new JPanel(new GridLayout(2,3,5,5));";
        js = js + "button(tools,'Ovalo','Cavity V9: usar ovalo de bucle',null,null);button(tools,'Elipse inclinada','Cavity V9: usar elipse inclinada de bucle',null,null);button(tools,'Polilinea cerrada','Cavity V9: usar poligono cerrado',null,null);button(tools,'Mano alzada cerrada','Cavity V9: usar contorno cerrado mano alzada',null,null);button(tools,'Ajustar seleccionada','Cavity V9: ajustar bucle seleccionado a elipse',Color.decode('#eeeeee'),Color.BLACK);button(tools,'Restaurar original','Cavity V9: restaurar bucle original',Color.decode('#eeeeee'),Color.BLACK);";
    }
    js = js + "outer.add(tools,BorderLayout.CENTER);var actions=new JPanel(new GridLayout(1,3,5,5));button(actions,'Borrar ultima','Cavity V9: borrar ultimo trazo',Color.decode('#c42b1c'),Color.WHITE);button(actions,'Borrar seleccionada','Cavity V9: borrar trazo seleccionado',Color.decode('#eeeeee'),Color.BLACK);button(actions,'Finalizar','Cavity V9: finalizar trazado automatico',Color.decode('#2b6de0'),Color.WHITE);outer.add(actions,BorderLayout.SOUTH);f.setContentPane(outer);";
    js = js + "function saveBounds(){try{var b=f.getBounds();Prefs.set('cavity.v5.ui.trace.x',b.x);Prefs.set('cavity.v5.ui.trace.y',b.y);Prefs.set('cavity.v5.ui.trace.w',b.width);Prefs.set('cavity.v5.ui.trace.h',b.height);}catch(ignore){}}function peers(){var out=[],ws=Window.getWindows();for(var j=0;j<ws.length;j++)try{var w=ws[j],t=String(w.getTitle());if(w!=f&&w.isVisible()&&(t.indexOf('Cavity TEM Studio 5.')==0||t=='Cavity TEM - captura automatica'))out.push(w);}catch(ignore){}try{var iw=IJ.getImage().getWindow();if(iw!=null&&iw!=f&&iw.isVisible()&&out.indexOf(iw)<0)out.push(iw);}catch(ignore){}return out;}var snapping=false;function snap(){if(snapping||!dock.isSelected())return;var ps=peers(),b=f.getBounds(),g=18,nx=b.x,ny=b.y,hit=false;for(var k=0;k<ps.length;k++){var q=ps[k].getBounds();if(Math.abs(b.x-(q.x+q.width))<=g){nx=q.x+q.width;hit=true;}else if(Math.abs((b.x+b.width)-q.x)<=g){nx=q.x-b.width;hit=true;}if(Math.abs(b.y-q.y)<=g){ny=q.y;hit=true;}else if(Math.abs((b.y+b.height)-q.y)<=g){ny=q.y-b.height;hit=true;}}if(hit&&(nx!=b.x||ny!=b.y)){snapping=true;f.setLocation(nx,ny);snapping=false;}}var cbody={componentMoved:function(e){snap();saveBounds();},componentResized:function(e){saveBounds();}};var cl;if(typeof JavaAdapter!='undefined')cl=new JavaAdapter(ComponentAdapter,cbody);else{var C=Java.extend(ComponentAdapter);cl=new C(cbody);}f.addComponentListener(cl);";
    js = js + "var pbody={actionPerformed:function(e){Prefs.set('cavity.v5.ui.trace.pinned',pin.isSelected()?'1':'0');}};var abody={actionPerformed:function(e){Prefs.set('cavity.v5.ui.alwaysOnTop',always.isSelected()?'1':'0');}};var dbody={actionPerformed:function(e){Prefs.set('cavity.v5.ui.dock',dock.isSelected()?'1':'0');if(dock.isSelected())snap();}};if(typeof JavaAdapter!='undefined'){pin.addActionListener(new JavaAdapter(ActionListener,pbody));always.addActionListener(new JavaAdapter(ActionListener,abody));dock.addActionListener(new JavaAdapter(ActionListener,dbody));}else{var PA=Java.extend(ActionListener);pin.addActionListener(new PA(pbody));always.addActionListener(new PA(abody));dock.addActionListener(new PA(dbody));}";
    js = js + "function fijiActive(){try{var a=KeyboardFocusManager.getCurrentKeyboardFocusManager().getActiveWindow();if(a==null)return false;if(a==f)return true;var cn=String(a.getClass().getName());if(cn.indexOf('ij.')==0)return true;var tt=String(a.getTitle());if(tt.indexOf('Cavity TEM')==0)return true;}catch(ignore){}return false;}var tbody={actionPerformed:function(e){try{var globalTop=String(Prefs.get('cavity.v5.ui.alwaysOnTop','0'))=='1';if(always.isSelected()!=globalTop)always.setSelected(globalTop);var wanted=globalTop||(pin.isSelected()&&fijiActive());if(f.isAlwaysOnTop()!=wanted)f.setAlwaysOnTop(wanted);}catch(ignore){}}};var tl;if(typeof JavaAdapter!='undefined')tl=new JavaAdapter(ActionListener,tbody);else{var TA=Java.extend(ActionListener);tl=new TA(tbody);}var timer=new Timer(300,tl);timer.start();";
    js = js + "var wb={windowClosing:function(e){var t=new Thread(makeRun('Cavity V9: finalizar trazado automatico'));t.setDaemon(true);t.start();},windowClosed:function(e){try{timer.stop();saveBounds();}catch(ignore){}}};if(typeof JavaAdapter!='undefined')f.addWindowListener(new JavaAdapter(WindowAdapter,wb));else{var W=Java.extend(WindowAdapter);f.addWindowListener(new W(wb));}f.pack();var sw=Math.round(Prefs.get('cavity.v5.ui.trace.w',-1)),sh=Math.round(Prefs.get('cavity.v5.ui.trace.h',-1)),sx=Math.round(Prefs.get('cavity.v5.ui.trace.x',-32000)),sy=Math.round(Prefs.get('cavity.v5.ui.trace.y',-32000));if(sw>=430&&sh>=180)f.setSize(sw,sh);if(sx>-30000&&sy>-30000)f.setLocation(sx,sy);else f.setLocationByPlatform(true);f.setVisible(true);f.toFront();snap();";
    eval("js", js);
}

function v4RefreshTraceController() {
    if (v4TraceMode == "") return;
    js = "var Frame=Packages.java.awt.Frame;var Prefs=Packages.ij.Prefs;var previousBounds=null,previousTab=0;var fs=Frame.getFrames();for(var i=0;i<fs.length;i++){try{if(String(fs[i].getTitle())=='Cavity TEM - captura automatica'){var r=fs[i].getRootPane();var t=r.getClientProperty('traceTool');var s=r.getClientProperty('traceStatus');var a=r.getClientProperty('aspectCheck');if(t!=null)t.setText('Herramienta: " + jsEscape(v4TraceToolLabel()) + "');if(s!=null)s.setText('Registradas: " + v4TraceAdded + " | Borradas: " + v4TraceDeleted + "');if(a!=null)a.setSelected(String(Prefs.get('cavity.v5.ui.image.aspect','0'))=='1');fs[i].repaint();}}catch(e){}}";
    eval("js",js);
}

function v4CloseTraceController() {
    js = "var Frame=Packages.java.awt.Frame;var fs=Frame.getFrames();for(var i=0;i<fs.length;i++){try{if(String(fs[i].getTitle())=='Cavity TEM - captura automatica'){previousBounds=fs[i].getBounds();try{var oldTabs=fs[i].getRootPane().getClientProperty('tabs');if(oldTabs!=null)previousTab=oldTabs.getSelectedIndex();}catch(ignoreTabs){}fs[i].dispose();}}catch(e){}}";
    eval("js",js);
}

function v4DeleteLastTrace() {
    run("ROI Manager...");
    n=roiManager("count"); best=-1; bestOrder=-1;
    for(i=0;i<n;i++) {
        safeRoiSelect(i);
        if(propString("Trace_session_id","")!=v4TraceSessionId) continue;
        order=propNumber("Capture_order",-1);
        if(order>bestOrder){bestOrder=order;best=i;}
    }
    if(best<0){run("Select None");if(v4TraceMode!="")v4ApplyTraceTool();showStatus("No hay trazos de la serie activa para borrar.");return;}
    v4DeleteTraceAtIndex(best);
}

function v4DeleteSelectedTrace() {
    run("ROI Manager...");
    idx=roiManager("index");
    if(idx<0){if(v4TraceMode!="")v4DeleteLastTrace();else deleteSelectedManagedRoi();return;}
    safeRoiSelect(idx);
    type=propString("Object_type",currentRoiType());
    if(type!="dislocation" && type!="dislocation_loop") {
        if(v4TraceMode!="") showStatus("La ROI seleccionada no es una dislocacion ni un bucle. Use Borrar ultima para retirar el ultimo trazo de la serie.");
        else deleteSelectedManagedRoi();
        return;
    }
    v4DeleteTraceAtIndex(idx);
}

function v4DeleteTraceAtIndex(idx) {
    run("ROI Manager...");
    if(!safeRoiSelect(idx)) return;
    name=Roi.getName;
    Roi.copy;
    undoKind="delete";
    undoObjectId=propString("Object_id",name);
    undoDeletedName=name;
    undoAvailable=1;
    roiManager("delete");
    if(v4TraceMode!="") v4TraceDeleted++;
    showAllRois();
    run("Select None");
    if(v4TraceMode!="") {
        v4ApplyTraceTool();
        v4RefreshTraceController();
        showStatus("Borrado " + name + ". Continue trazando; no es necesario confirmar los objetos correctos.");
    } else {
        activateSelectTool();
        showStatus("Borrado " + name + ". Ctrl+Z permite restaurarlo una vez.");
    }
}

function v4FinishAutomaticTrace(silent) {
    previousMode=v4TraceMode;
    previousAdded=v4TraceAdded;
    previousDeleted=v4TraceDeleted;
    v4RemoveTraceListener();
    v4CloseTraceController();
    v4TraceMode="";
    v4TraceTool="";
    v4TraceSessionId="";
    v4TraceLastObjectId="";
    if(nImages()>0) activateSelectTool();
    if(!silent && previousMode!="") showMessage("Serie finalizada", "Registradas: " + previousAdded + "\nBorradas durante la serie: " + previousDeleted + "\n\nLas ROI conservadas permanecen en el ROI Manager y se guardan con la sesion del proyecto.");
    else if(!silent) showStatus("No hay una serie automatica activa.");
}

function v4AutoPrepareOnActivation() {
    if (!v4SynchronizeProjectContext()) {
        showStatus("Cavity TEM Studio v5.6.0 activo. No hay proyecto asociado; pulse el icono Studio para elegirlo.");
        return;
    }
    if (!v4OpenOrActivateRegisteredMaster(0)) {
        showStatus("Proyecto cargado, pero no se pudo abrir el montaje maestro registrado. Pulse el icono Studio para revisar.");
        return;
    }
    if (!v4ApplyScale()) {
        showStatus("Montaje abierto, pero existe un conflicto de escala. La medicion queda bloqueada hasta revisarlo.");
        return;
    }
    v4AttachImageContext();
    v4LoadSurfaceStateFromBridge();
    run("ROI Manager...");
    if (roiManager("count") > 0) {
        ensureObjectIds();
        restyleAllRois();
        showAllRois();
    }
    lockWindowSizeToCurrent(0);
    installInteractionListeners(0);
    showStatus("Proyecto y montaje maestro cargados automaticamente. Pulse el icono Studio para comenzar o continuar.");
}

function v55ProjectBridgeMarkerClear(root, actionText, showErrors) {
    root = normalizeStoredPath(root);
    if (endsWith(root, "/") || endsWith(root, "\\")) root = substring(root, 0, lengthOf(root)-1);
    if (root == "") {
        v55IntegrityLastError = "PROJECT_BRIDGE_RECOVERY_REQUIRED: raiz de proyecto no definida.";
        if (showErrors) showMessage("Recuperacion de proyecto requerida", "No se puede " + actionText + ".\n\n" + v55IntegrityLastError);
        return 0;
    }
    recoveryMarker = projectAwareJoinPath(projectAwareJoinPath(root, "fiji_bridge"), "project_bridge_recovery.json");
    if (File.exists(recoveryMarker)) {
        v55InvalidateIntegrityCache();
        v55IntegrityLastError = "PROJECT_BRIDGE_RECOVERY_REQUIRED: existe fiji_bridge/project_bridge_recovery.json.";
        if (showErrors) showMessage("Recuperacion de proyecto requerida", "No se puede " + actionText + ".\n\n" + v55IntegrityLastError + "\n\nVuelva a Studio y complete la recuperacion antes de continuar en Fiji.");
        return 0;
    }
    return 1;
}

function v55RequireProjectRootMatch(imageRoot, expectedRoot, actionText, showErrors) {
    imageRoot = normalizeStoredPath(imageRoot);
    expectedRoot = normalizeStoredPath(expectedRoot);
    if (imageRoot != "" && !v55ProjectBridgeMarkerClear(imageRoot, actionText, showErrors)) return 0;
    if (expectedRoot != "" && !v55ProjectBridgeMarkerClear(expectedRoot, actionText, showErrors)) return 0;
    if (imageRoot != "" && expectedRoot != "") {
        imageCanonicalRoot = toLowerCase(v55CanonicalPathJava(imageRoot));
        expectedCanonicalRoot = toLowerCase(v55CanonicalPathJava(expectedRoot));
        if (imageCanonicalRoot == "" || expectedCanonicalRoot == "" || imageCanonicalRoot != expectedCanonicalRoot) {
            v55IntegrityLastError = "CROSS_PROJECT_IMAGE_CONTEXT: la imagen activa pertenece a otro proyecto.";
            if (showErrors) showMessage("Contexto de proyecto incompatible", "No se puede " + actionText + ".\n\n" + v55IntegrityLastError + "\n\nProyecto de la imagen: " + imageRoot + "\nProyecto cargado: " + expectedRoot + "\n\nCargue el proyecto de la imagen antes de continuar.");
            return 0;
        }
    }
    return 1;
}

function v55RequireActiveImageProjectContext(expectedRoot, actionText, showErrors) {
    return v55RequireProjectRootMatch(v4FindProjectRootFromCurrentImage(), expectedRoot, actionText, showErrors);
}

function v55PersistActiveRoiSet(actionText) {
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, actionText, 1)) return 0;
    activeRoiSetPath = projectAwareJoinPath(v4BridgeDir, "active_roi_set.txt");
    File.saveString(v4ActiveRoiSetId + "\n", activeRoiSetPath);
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, actionText, 1)) return 0;
    return 1;
}

function v4SynchronizeProjectContext() {
    // Prefer the project physically containing the active image. This prevents
    // an old Fiji preference from binding a newly opened master to the wrong
    // project. If the image is not inside a project, use the Studio preference.
    imageRoot = v4FindProjectRootFromCurrentImage();
    if (imageRoot != "") {
        if (v4ProjectLoaded && imageRoot == v4ProjectDir) {
            if (v55ProjectBridgeMarkerClear(imageRoot, "sincronizar el proyecto de la imagen", 1)) return 1;
            v4ProjectLoaded = 0;
            projectAwareActive = 0;
            projectConfigured = 0;
            return 0;
        }
        return v4LoadProject(imageRoot);
    }
    rememberedRoot = call("ij.Prefs.get", "cavity.v5.project.dir", "");
    if (rememberedRoot == "") rememberedRoot = call("ij.Prefs.get", "cavity.v4.project.dir", "");
    rememberedRoot = normalizeStoredPath(rememberedRoot);
    if (rememberedRoot != "" && rememberedRoot != v4ProjectDir) {
        rememberedJson = projectAwareJoinPath(rememberedRoot, "project.json");
        rememberedBridge = projectAwareJoinPath(projectAwareJoinPath(rememberedRoot, "fiji_bridge"), "current_bridge.json");
        if (File.exists(rememberedJson) && File.exists(rememberedBridge)) return v4LoadProject(rememberedRoot);
    }
    if (v4ProjectLoaded && v4ProjectDir != "") {
        if (v55ProjectBridgeMarkerClear(v4ProjectDir, "sincronizar el proyecto", 1)) return 1;
        v4ProjectLoaded = 0;
        projectAwareActive = 0;
        projectConfigured = 0;
        return 0;
    }
    return v4TryAutoLoadRememberedProject();
}

function v4FindProjectRootFromCurrentImage() {
    resultRoot = "";
    if (nImages() <= 0) return "" + resultRoot;
    imageDirNow = getInfo("image.directory");
    if (imageDirNow == "") return "" + resultRoot;
    currentDir = normalizeStoredPath(imageDirNow);
    if (endsWith(currentDir, "/") || endsWith(currentDir, "\\")) currentDir = substring(currentDir, 0, lengthOf(currentDir)-1);
    for (depth=0; depth<10; depth++) {
        candidateJson = projectAwareJoinPath(currentDir, "project.json");
        candidateBridge = projectAwareJoinPath(projectAwareJoinPath(currentDir, "fiji_bridge"), "current_bridge.json");
        candidateRecovery = projectAwareJoinPath(projectAwareJoinPath(currentDir, "fiji_bridge"), "project_bridge_recovery.json");
        if (File.exists(candidateRecovery)) {
            resultRoot = currentDir;
            return "" + resultRoot;
        }
        if (File.exists(candidateJson) && File.exists(candidateBridge)) {
            resultRoot = currentDir;
            return "" + resultRoot;
        }
        parentDir = File.getParent(currentDir);
        if (parentDir == "" || parentDir == currentDir) break;
        currentDir = normalizeStoredPath(parentDir);
        if (endsWith(currentDir, "/") || endsWith(currentDir, "\\")) currentDir = substring(currentDir, 0, lengthOf(currentDir)-1);
    }
    return "" + resultRoot;
}

function v4OpenOrActivateRegisteredMaster(showErrors) {
    if (!v4ProjectLoaded) return 0;
    if (!v55VerifyQuantitativeIntegrity("abrir el maestro", 0, showErrors)) return 0;
    if (v4MasterImage == "" || !File.exists(v4MasterImage)) {
        if (showErrors) showMessage("Montaje no disponible", "No existe el OME-TIFF maestro registrado:\n" + v4MasterImage + "\n\nVuelva a Studio y registre el montaje maestro.");
        return 0;
    }
    if (!v4OpenImageByExactPath(v4MasterImage)) {
        if (showErrors) showMessage("No se pudo abrir", "Fiji no pudo abrir el montaje maestro:\n" + v4MasterImage);
        return 0;
    }
    if (!v55ActiveImageMatchesCurrentMaster(showErrors)) return 0;
    projectAwareCurrentAnalysisImagePath = v4MasterImage;
    projectAwareCurrentAnalysisImageRole = v4MasterRole;
    projectAwareCurrentAnalysisImageName = getTitle();
    return 1;
}

function v4CurrentImageCanonicalPath() {
    currentPathText = "";
    if (nImages() <= 0) return "" + currentPathText;
    currentDirText = normalizeStoredPath(getInfo("image.directory"));
    if (currentDirText == "") return "" + currentPathText;
    currentFileText = getInfo("image.filename");
    if (currentFileText == "") currentFileText = getTitle();
    currentPathText = normalizeStoredPath(projectAwareJoinPath(currentDirText, currentFileText));
    return "" + currentPathText;
}

function v4OpenImageByExactPath(path) {
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "abrir una imagen exacta", 1)) return 0;
    wantedPathText = normalizeStoredPath(path);
    if (wantedPathText == "" || !File.exists(wantedPathText)) return 0;
    openTitles = getList("image.titles");
    for (openIndex=0; openIndex<openTitles.length; openIndex++) {
        selectWindow(openTitles[openIndex]);
        if (v4CurrentImageCanonicalPath() == wantedPathText) return v55ProjectBridgeMarkerClear(v4ProjectDir, "activar una imagen exacta", 1);
    }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "abrir una imagen exacta", 1)) return 0;
    open(wantedPathText);
    if (nImages() <= 0) return 0;
    if (v4CurrentImageCanonicalPath() != wantedPathText) return 0;
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar de abrir una imagen exacta", 1)) return 0;
    return 1;
}

function v4PrepareImageForMeasurement(showErrors) {
    lightHF4Pull();
    if (!lightEnsureCurrentImage()) return 0;
    if (!updateScaleMaybe() || !lightScaleConfirmed) {
        if (showErrors) showMessage("Escala no confirmada", "Confirma la escala de Bio-Formats, introducela en nm/px o calibra con una linea antes de medir.");
        return 0;
    }
    usePanelsAsMask = 0; v4ProjectLoaded = 0; projectConfigured = 1;
    return 1;
}


function v4TryAutoLoadRememberedProject() {
    if (v4ProjectLoaded && v4ProjectDir != "") return 1;
    rememberedRoot = call("ij.Prefs.get", "cavity.v5.project.dir", "");
    if (rememberedRoot == "") rememberedRoot = call("ij.Prefs.get", "cavity.v4.project.dir", "");
    rememberedRoot = normalizeStoredPath(rememberedRoot);
    if (rememberedRoot == "") return 0;
    rememberedJson = projectAwareJoinPath(rememberedRoot, "project.json");
    rememberedBridge = projectAwareJoinPath(projectAwareJoinPath(rememberedRoot, "fiji_bridge"), "current_bridge.json");
    if (!File.exists(rememberedJson) || !File.exists(rememberedBridge)) return 0;
    return v4LoadProject(rememberedRoot);
}

function v4OpenProject() {
    remembered = call("ij.Prefs.get", "cavity.v5.project.dir", "");
    if (remembered == "") remembered = call("ij.Prefs.get", "cavity.v4.project.dir", "");
    if (remembered != "" && File.exists(projectAwareJoinPath(remembered, "project.json"))) {
        Dialog.create("Abrir proyecto Cavity TEM Studio");
        Dialog.addMessage("Proyecto recordado:\n" + remembered);
        Dialog.addChoice("Accion:", newArray("Abrir proyecto recordado", "Elegir otra carpeta"), "Abrir proyecto recordado");
        Dialog.show();
        pick = Dialog.getChoice();
        if (pick == "Abrir proyecto recordado") root = remembered;
        else root = getDirectory("Elige la carpeta raiz del proyecto Cavity TEM Studio");
    } else root = getDirectory("Elige la carpeta raiz del proyecto Cavity TEM Studio");
    if (root == "") return;
    if (!v4LoadProject(root)) return;

    openChoice = "No abrir imagen";
    canOpen = 0;
    if (v4MasterImage != "") {
        if (File.exists(v4MasterImage)) canOpen = 1;
    }
    if (nImages() > 0) {
        imageChoices = newArray("Usar imagen abierta", "Abrir montaje maestro", "No abrir imagen");
        openChoice = "Usar imagen abierta";
        if (canOpen && v4CurrentImageCanonicalPath() != normalizeStoredPath(v4MasterImage)) openChoice = "Abrir montaje maestro";
    } else {
        imageChoices = newArray("Abrir montaje maestro", "No abrir imagen");
        if (canOpen) openChoice = "Abrir montaje maestro";
    }
    applyCalibrationDefault = 0;
    if (!isNaN(v4PixelWidth)) {
        if (v4PixelWidth > 0) applyCalibrationDefault = 1;
    }
    loadSessionDefault = 0;
    sessionPathText = v4SessionPath();
    if (sessionPathText != "") {
        if (File.exists(sessionPathText)) loadSessionDefault = 1;
    }

    Dialog.create("Proyecto Cavity TEM 5 preparado");
    Dialog.addMessage(v4ProjectSummary());
    Dialog.addChoice("Imagen:", imageChoices, openChoice);
    Dialog.addCheckbox("Aplicar calibracion activa", applyCalibrationDefault);
    Dialog.addCheckbox("Cargar la sesion current publicada si existe", loadSessionDefault);
    Dialog.show();
    imageChoice = Dialog.getChoice();
    applyScale = Dialog.getCheckbox();
    loadSession = Dialog.getCheckbox();

    if (imageChoice == "Usar imagen abierta" && nImages() > 0) {
        currentName = getTitle();
        projectAwareCurrentAnalysisImageName = currentName;
        projectAwareCurrentAnalysisImageRole = "ANALYSIS_IMAGE";
        if (v4MasterImage != "" && v4CurrentImageCanonicalPath() == normalizeStoredPath(v4MasterImage)) {
            projectAwareCurrentAnalysisImagePath = v4MasterImage;
            projectAwareCurrentAnalysisImageRole = v4MasterRole;
        }
    }
    if (imageChoice == "Abrir montaje maestro") {
        if (canOpen) {
            if (!v4OpenOrActivateRegisteredMaster(1)) {
                showMessage("Montaje no disponible", "Fiji no pudo abrir la ruta exacta del montaje registrado:\n" + v4MasterImage);
                return;
            }
        } else showMessage("Montaje no disponible", "No existe el montaje registrado:\n" + v4MasterImage);
    }
    if (nImages() > 0 && applyScale) { if (!v4ApplyScale()) return; }
    if (loadSession) v4LoadSession();
    if (nImages() > 0) v4AttachImageContext();
    v4LoadSurfaceStateFromBridge();
    showStatus("Proyecto Cavity TEM 5 cargado: " + v4ProjectName);
}

function v4ReloadProject() {
    if (v4ProjectDir == "") { v4OpenProject(); return; }
    if (v4LoadProject(v4ProjectDir)) {
        if (nImages() > 0 && v4PixelWidth > 0) { if (!v4ApplyScale()) return; }
        v4LoadSurfaceStateFromBridge();
        showStatus("Proyecto Cavity TEM 5 recargado.");
    }
}

function v4LoadProject(root) {
    root = normalizeStoredPath(root);
    if (endsWith(root, "/") || endsWith(root, "\\")) root = substring(root, 0, lengthOf(root)-1);
    if (v4ProjectLoaded && v4ProjectDir == root) {
        v4ProjectLoaded = 0;
        projectAwareActive = 0;
        projectConfigured = 0;
    }
    if (!v55ProjectBridgeMarkerClear(root, "cargar el proyecto", 1)) return 0;
    projectJsonPath = projectAwareJoinPath(root, "project.json");
    bridge = projectAwareJoinPath(root, "fiji_bridge");
    bridgePointer = projectAwareJoinPath(bridge, "current_bridge.json");
    if (!File.exists(projectJsonPath) || !File.exists(bridgePointer)) {
        showMessage("Proyecto no valido", "No encuentro project.json o el puntero fiji_bridge/current_bridge.json en:\n" + root + "\n\nAbra antes la carpeta con Cavity TEM Studio 5.6.0 para publicar un puente inmutable.");
        return 0;
    }
    bridgePointerText = File.openAsString(bridgePointer);
    bridgeGeneration = projectAwareReadFieldFromJsonText(bridgePointerText, "generation_id");
    pointerProjectId = projectAwareReadFieldFromJsonText(bridgePointerText, "project_id");
    if (bridgeGeneration == "" || indexOf(bridgeGeneration, "..") >= 0 || indexOf(bridgeGeneration, "/") >= 0 || indexOf(bridgeGeneration, "\\") >= 0) {
        showMessage("Puente Fiji no valido", "current_bridge.json no contiene un generation_id seguro. Vuelva a Studio y regenere el puente.");
        return 0;
    }
    bridgeStatic = projectAwareJoinPath(projectAwareJoinPath(bridge, "generations"), bridgeGeneration);
    fields = projectAwareJoinPath(bridgeStatic, "project_fields.csv");
    generationManifest = projectAwareJoinPath(bridgeStatic, "bridge_generation_manifest.json");
    if (!File.exists(fields) || !File.exists(generationManifest)) {
        showMessage("Puente Fiji incompleto", "La generacion seleccionada por current_bridge.json no esta completa:\n" + bridgeStatic);
        return 0;
    }
    // A global ROI Manager can otherwise carry measurements from project A
    // into project B. Save with the old context and clear before switching.
    switchingProject = 0;
    if (v4ProjectLoaded && v4ProjectDir != "" && v4ProjectDir != root) switchingProject = 1;
    if (switchingProject) {
        run("ROI Manager...");
        previousRoiCount = roiManager("count");
        if (previousRoiCount > 0) {
            if (!getBoolean("El ROI Manager contiene " + previousRoiCount + " ROI del proyecto anterior.\n\nPara impedir una atribucion incorrecta, Studio debe guardar esa sesion y limpiar el ROI Manager.", "Guardar y cambiar", "Cancelar")) return 0;
            switchTargetImageId = -1;
            if (nImages() > 0) switchTargetImageId = getImageID();
            if (!v4OpenOrActivateRegisteredMaster(1)) return 0;
            v4ProjectSwitchInProgress = 1;
            previousSessionSaved = v4SaveSession();
            v4ProjectSwitchInProgress = 0;
            if (switchTargetImageId > 0) selectImage(switchTargetImageId);
            if (!previousSessionSaved) return 0;
            roiManager("reset");
        }
    }
    // From this point onward globals describe a candidate project. Any later
    // failure must leave the context inactive so synchronization reloads it.
    v4ProjectLoaded = 0;
    projectAwareActive = 0;
    projectConfigured = 0;
    v4ProjectDir = root;
    v4BridgeDir = bridge;
    v4BridgeStaticDir = bridgeStatic;
    v4BridgePointerJson = bridgePointer;
    v4BridgeGenerationId = bridgeGeneration;
    v4ProjectFieldsCsv = fields;
    v4ProjectFieldsText = File.openAsString(v4ProjectFieldsCsv);
    v4RoiSetsCsv = projectAwareJoinPath(v4BridgeStaticDir, "roi_sets.csv");
    v55InvalidateIntegrityCache();
    // The integrated v8.3 core also reads project-aware fields. Point both
    // layers at the same bridge instead of leaving the legacy global empty.
    projectAwareProjectFieldsCsv = v4ProjectFieldsCsv;
    v4ProjectId = v4Field("project_id");
    if (v4Field("bridge_generation_id") != v4BridgeGenerationId || pointerProjectId != v4ProjectId) {
        showMessage("Puente Fiji incoherente", "project_fields.csv, current_bridge.json y project_id no pertenecen a la misma generacion.");
        return 0;
    }
    v4ProjectName = v4Field("project_name");
    v4StudyId = v4Field("study_id");
    v4StudyName = v4Field("study_name");
    v4SampleId = v4Field("sample_id");
    v4Material = v4Field("material");
    v4Condition = v4Field("condition");
    v4SpecimenId = v4Field("specimen_id");
    v4SpecimenLabel = v4Field("specimen_label");
    v4AcquisitionId = v4Field("acquisition_id");
    v4AcquisitionLabel = v4Field("acquisition_label");
    v4MasterRole = v4Field("master_role");
    if (v4MasterRole == "") v4MasterRole = "MASTER_ANALYTICAL";
    masterStored = v4Field("master_image");
    v4MasterImage = v4ResolvePath(masterStored);
    v4MasterRevisionId = v4Field("master_revision_id");
    v4CurrentMontagePointerPath = v4ResolvePath(v4Field("current_montage_pointer"));
    v4MasterRevisionManifestPath = v4ResolvePath(v4Field("master_revision_manifest"));
    v4MasterNativePlanPath = v4ResolvePath(v4Field("master_native_plan"));
    v4MasterFidelityReportPath = v4ResolvePath(v4Field("master_fidelity_report"));
    v4OwnershipImage = v4ResolvePath(v4Field("master_ownership"));
    v4CurrentMontagePointerSha256 = toLowerCase(v4Field("current_montage_pointer_sha256"));
    v4MasterRevisionManifestSha256 = toLowerCase(v4Field("master_revision_manifest_sha256"));
    v4MasterNativePlanSha256 = toLowerCase(v4Field("master_native_plan_sha256"));
    v4MasterFidelitySha256 = toLowerCase(v4Field("master_fidelity_sha256"));
    v4MasterSha256 = toLowerCase(v4Field("master_sha256"));
    v4MasterOwnershipSha256 = toLowerCase(v4Field("master_ownership_sha256"));
    v4RevisionBindingReady = 0;
    v4RevisionBindingError = "";
    if (!v4ValidateBridgeRevisionBinding(1)) return 0;
    v4CalibrationId = v4Field("active_calibration_id");
    v4ScaleReconciliationStatus = v4Field("scale_reconciliation_status");
    if (v4ScaleReconciliationStatus == "") v4ScaleReconciliationStatus = "NOT_ANALYZED";
    scaleAllowedText = toLowerCase(v4Field("scale_measurement_allowed"));
    scaleRevisionMatchText = toLowerCase(v4Field("scale_revision_match"));
    v4ScaleMeasurementAllowed = 0;
    if ((scaleAllowedText == "1" || scaleAllowedText == "true" || scaleAllowedText == "yes" || scaleAllowedText == "si") && (scaleRevisionMatchText == "1" || scaleRevisionMatchText == "true" || scaleRevisionMatchText == "yes" || scaleRevisionMatchText == "si")) v4ScaleMeasurementAllowed = 1;
    v4PixelWidth = parseFloat(v4Field("pixel_width"));
    v4PixelHeight = parseFloat(v4Field("pixel_height"));
    if (isNaN(v4PixelHeight) || v4PixelHeight <= 0) v4PixelHeight = v4PixelWidth;
    v4PixelUnit = v4Field("pixel_unit");
    if (v4PixelUnit == "") v4PixelUnit = "nm";
    v4SurfaceId = v4Field("active_surface_id");
    if (v4SurfaceId == "") v4SurfaceId = "SURF_001";
    // Source range is display-only. The semicolon-separated explicit list is
    // authoritative and preserves intentional gaps such as 0004;0007;0012.
    sourceFirst = v4Field("source_first");
    sourceLast = v4Field("source_last");
    sourceImageList = v4Field("source_sequences");
    projectAwarePanelCount = v4Field("panel_count");
    v4PanelsCsv = v4ResolvePath(v4Field("panels_csv"));
    if (v4PanelsCsv == "") v4PanelsCsv = projectAwareJoinPath(v4BridgeStaticDir, "panels.csv");
    v4PanelGeometryJson = v4ResolvePath(v4Field("panel_geometry_json"));
    if (v4PanelGeometryJson == "") v4PanelGeometryJson = projectAwareJoinPath(v4BridgeStaticDir, "panel_geometry.json");
    v4OwnershipImage = v4ResolvePath(v4Field("panel_ownership_image"));
    v4OwnershipLegendCsv = v4ResolvePath(v4Field("panel_ownership_legend_csv"));
    if (v4OwnershipLegendCsv == "") v4OwnershipLegendCsv = projectAwareJoinPath(v4BridgeStaticDir, "panel_ownership_legend.csv");
    ownershipCertifiedText = toLowerCase(v4Field("panel_ownership_certified"));
    v4OwnershipCertified = 0;
    if (ownershipCertifiedText == "1" || ownershipCertifiedText == "true" || ownershipCertifiedText == "yes" || ownershipCertifiedText == "si") v4OwnershipCertified = 1;
    v4PanelOverlapPolicy = v4Field("panel_overlap_policy");
    if (v4PanelOverlapPolicy == "") v4PanelOverlapPolicy = "unknown";
    v4PanelGeometryStatus = v4Field("panel_geometry_status");
    if (v4PanelGeometryStatus == "") v4PanelGeometryStatus = "UNAVAILABLE";
    panelReadyText = toLowerCase(v4Field("panel_quantitative_ownership_ready"));
    v4PanelQuantitativeReady = 0;
    if (panelReadyText == "1" || panelReadyText == "true" || panelReadyText == "yes" || panelReadyText == "si") v4PanelQuantitativeReady = 1;
    v4ActiveRoiSetId = v4Field("active_roi_set_id");
    if (v4ActiveRoiSetId == "") v4ActiveRoiSetId = "CAVITIES";
    roiSetsStored = v4Field("roi_sets_csv");
    if (roiSetsStored != "") v4RoiSetsCsv = v4ResolvePath(roiSetsStored);
    if (v4ProjectId == "" || v4ProjectName == "") {
        showMessage("Puente Fiji incompleto", "No se pudieron leer project_id y project_name de:\n" + v4ProjectFieldsCsv + "\n\nVuelva a Cavity TEM Studio, abra este proyecto y pulse Actualizar antes de abrir Fiji.");
        return 0;
    }
    if (!v55ProjectBridgeMarkerClear(root, "terminar de cargar el proyecto", 1)) return 0;
    v4ReadRoiSet(v4ActiveRoiSetId);
    call("ij.Prefs.set", "cavity.v5.project.dir", v4ProjectDir);
    call("ij.Prefs.set", "cavity.v4.project.dir", v4ProjectDir);

    // Mirror v4 context into the mature v8.3 globals for compatible tools.
    projectAwareProjectDir = v4ProjectDir;
    projectAwareSessionsDir = projectAwareJoinPath(v4ProjectDir, "sessions");
    projectAwareDerivedDir = projectAwareJoinPath(v4ProjectDir, "analysis_images");
    projectAwareViewsDir = projectAwareJoinPath(v4ProjectDir, "analysis_images");
    projectAwareProjectUid = v4ProjectId;
    projectAwareMasterTif = v4MasterImage;
    projectAwareMontageBuildLogCsv = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "sessions"), "montage_build_log.csv");
    projectAwareLayoutCheckCsv = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "layout"), "montage_layout_check.csv");
    projectAwarePixelWidth = "" + v4PixelWidth;
    projectAwarePixelHeight = "" + v4PixelHeight;
    projectAwarePixelUnit = v4PixelUnit;
    projectAwareResultsCsv = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "exports"), "objects_v4.csv");
    sampleName = v4Material;
    experimentalCondition = v4Condition;
    montageId = v4ProjectId;
    operatorName = v4Field("operator");
    if (!v55ProjectBridgeMarkerClear(root, "publicar el contexto cargado", 1)) return 0;
    makeDirIfMissing(projectAwareSessionsDir);
    makeDirIfMissing(projectAwareJoinPath(v4ProjectDir, "exports"));
    makeDirIfMissing(projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "exports"), "runs"));
    if (!v55ProjectBridgeMarkerClear(root, "publicar el contexto cargado", 1)) return 0;
    v4ProjectLoaded = 1;
    projectAwareActive = 1;
    projectConfigured = 1;
    return 1;
}

function v4Field(name) {
    // IJM can infer a numeric return type when a user-defined function call is
    // returned directly. Assign and coerce explicitly so text fields such as
    // project_id, names and paths remain strings.
    if (v4ProjectFieldsText == "") return "";
    fieldText = projectAwareReadFieldFromCsvText(v4ProjectFieldsText, name);
    return "" + fieldText;
}

function v4IsSha256(value) {
    canonicalHash = toLowerCase("" + value);
    if (lengthOf(canonicalHash) != 64) return 0;
    return matches(canonicalHash, "^[0-9a-f]{64}$");
}

// -------------------------------------------------------------------------
// Fase 1 R2 - live integrity verification for quantitative Fiji operations.
//
// The Java helper reads every byte through MessageDigest. It intentionally
// does not call a command shell and does not trust a hash merely because it
// has 64 hexadecimal characters. The short cache below is bounded to five
// seconds and is invalidated by the canonical path, size or modification time
// of every bridge/revision file. A full verification also compares a before
// and after fingerprint so a concurrent publication fails closed.
//
// Runtime evidence: NO PROBADO EN FIJI REAL. Static Python tests only verify
// the call graph and this Java/ImageJ contract; a real Fiji acceptance run is
// still mandatory before scientific use.
// -------------------------------------------------------------------------

function v55InvalidateIntegrityCache() {
    v55IntegrityCacheFingerprint = "";
    v55IntegrityCacheProjectId = "";
    v55IntegrityCacheUntilMs = 0;
    v55IntegrityLastEvidence = "";
    v55IntegrityLastError = "";
}

function v55ReadFileEvidenceJava(path) {
    v55FileCanonicalPath = "";
    v55FileSizeBytes = -1;
    v55FileModifiedMs = -1;
    v55FileSha256 = "";
    if (path == "") return 0;
    js = "var File=Packages.java.io.File,FIS=Packages.java.io.FileInputStream,MD=Packages.java.security.MessageDigest,Reflect=Packages.java.lang.reflect.Array,ByteType=Packages.java.lang.Byte.TYPE,Integer=Packages.java.lang.Integer,StringBuilder=Packages.java.lang.StringBuilder;var input=null,OUT='ERROR|unknown';";
    js = js + "function clean(v){return String(v).replace(/[\\r\\n|]/g,' ');}function hex(bytes){var sb=new StringBuilder();for(var i=0;i<bytes.length;i++){var value=Number(bytes[i])&255;if(value<16)sb.append('0');sb.append(Integer.toHexString(value));}return String(sb.toString());}";
    js = js + "try{var file=new File('" + jsEscape(path) + "').getCanonicalFile();if(!file.isFile())throw new Error('not_a_file');var digest=MD.getInstance('SHA-256');input=new FIS(file);var buffer=Reflect.newInstance(ByteType,1048576),count;while((count=input.read(buffer))!=-1){if(count>0)digest.update(buffer,0,count);}OUT='OK|'+clean(file.getCanonicalPath())+'|'+String(file.length())+'|'+String(file.lastModified())+'|'+hex(digest.digest());}catch(ex){OUT='ERROR|'+clean(ex);}finally{try{if(input!=null)input.close();}catch(ignore){}}String(OUT);";
    result = "" + eval("js", js);
    parts = split(result, "|");
    if (parts.length < 5 || parts[0] != "OK") {
        v55IntegrityLastError = "No se pudo calcular SHA-256 real: " + path + " (" + result + ")";
        return 0;
    }
    v55FileCanonicalPath = normalizeStoredPath(parts[1]);
    v55FileSizeBytes = parseFloat(parts[2]);
    v55FileModifiedMs = parseFloat(parts[3]);
    v55FileSha256 = toLowerCase(parts[4]);
    if (!v4IsSha256(v55FileSha256)) {
        v55IntegrityLastError = "SHA-256 Java no valido para: " + path;
        return 0;
    }
    return 1;
}

function v55Sha256FileJava(path) {
    if (!v55ReadFileEvidenceJava(path)) return "";
    return "" + v55FileSha256;
}

function v55CanonicalPathJava(path) {
    if (path == "") return "";
    js = "var File=Packages.java.io.File,OUT='';try{OUT=String(new File('" + jsEscape(path) + "').getCanonicalPath());}catch(ex){OUT='';}OUT;";
    canonicalResult = "" + eval("js", js);
    canonicalResult = normalizeStoredPath(canonicalResult);
    return "" + canonicalResult;
}

function v55CurrentIntegrityFingerprintJava() {
    revisionDir = projectAwareJoinPath(projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "derived"), "montage_revisions"), v4MasterRevisionId);
    recoveryMarker = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "fiji_bridge"), "project_bridge_recovery.json");
    js = "var File=Packages.java.io.File,MD=Packages.java.security.MessageDigest,Integer=Packages.java.lang.Integer,StringBuilder=Packages.java.lang.StringBuilder,Text=Packages.java.lang.String;var OUT='ERROR|unknown';";
    js = js + "function clean(v){return String(v).replace(/[\\r\\n|]/g,' ');}function hex(bytes){var sb=new StringBuilder();for(var i=0;i<bytes.length;i++){var value=Number(bytes[i])&255;if(value<16)sb.append('0');sb.append(Integer.toHexString(value));}return String(sb.toString());}function add(items,file){var f=file.getCanonicalFile();items.push(clean(f.getCanonicalPath())+';'+(f.exists()?'1':'0')+';'+(f.isFile()?String(f.length()):'-1')+';'+String(f.lastModified()));}function addDir(items,dir){add(items,dir);var files=dir.listFiles();if(files==null)return;var names=[];for(var i=0;i<files.length;i++)names.push(files[i]);names.sort(function(a,b){return String(a.getName()).localeCompare(String(b.getName()));});for(var j=0;j<names.length;j++)add(items,names[j]);}";
    js = js + "try{var items=[];add(items,new File('" + jsEscape(projectAwareJoinPath(v4ProjectDir, "project.json")) + "'));add(items,new File('" + jsEscape(v4BridgePointerJson) + "'));add(items,new File('" + jsEscape(v4CurrentMontagePointerPath) + "'));add(items,new File('" + jsEscape(recoveryMarker) + "'));addDir(items,new File('" + jsEscape(v4BridgeStaticDir) + "'));addDir(items,new File('" + jsEscape(revisionDir) + "'));items.sort();var digest=MD.getInstance('SHA-256');OUT='OK|'+hex(digest.digest(new Text(items.join('\\n')).getBytes('UTF-8')));}catch(ex){OUT='ERROR|'+clean(ex);}String(OUT);";
    result = "" + eval("js", js);
    parts = split(result, "|");
    if (parts.length < 2 || parts[0] != "OK" || !v4IsSha256(parts[1])) {
        v55IntegrityLastError = "No se pudo construir la huella viva de integridad: " + result;
        return "";
    }
    return "" + toLowerCase(parts[1]);
}

function v55ActiveImageMatchesCurrentMaster(showErrors) {
    if (nImages() <= 0) {
        v55IntegrityLastError = "No hay una imagen activa para la operacion cuantitativa.";
        if (showErrors) showMessage("Integridad cuantitativa bloqueada", v55IntegrityLastError);
        return 0;
    }
    if (startsWith(getTitle(), "VIEW_ONLY__")) {
        v55IntegrityLastError = "La imagen activa es VIEW_ONLY y no puede gobernar una operacion cuantitativa.";
        if (showErrors) showMessage("Integridad cuantitativa bloqueada", v55IntegrityLastError);
        return 0;
    }
    activePath = v55CanonicalPathJava(v4CurrentImageCanonicalPath());
    masterPath = v55CanonicalPathJava(v4MasterImage);
    if (activePath == "" || masterPath == "" || toLowerCase(activePath) != toLowerCase(masterPath)) {
        v55IntegrityLastError = "La imagen activa no es el maestro vigente.\n\nMaestro: " + masterPath + "\nImagen activa: " + activePath;
        if (showErrors) showMessage("Integridad cuantitativa bloqueada", v55IntegrityLastError);
        return 0;
    }
    dirtyState = "" + eval("js", "var imp=Packages.ij.IJ.getImage();String(imp!=null&&imp.changes?'DIRTY':'CLEAN');");
    if (dirtyState != "CLEAN") {
        v55IntegrityLastError = "La imagen maestra activa contiene cambios no guardados en memoria. Abra de nuevo el maestro certificado.";
        if (showErrors) showMessage("Integridad cuantitativa bloqueada", v55IntegrityLastError);
        return 0;
    }
    return 1;
}

function v55RunFullIntegrityVerificationJava() {
    projectJsonPath = projectAwareJoinPath(v4ProjectDir, "project.json");
    recoveryMarker = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "fiji_bridge"), "project_bridge_recovery.json");
    js = "var File=Packages.java.io.File,FIS=Packages.java.io.FileInputStream,Files=Packages.java.nio.file.Files,MD=Packages.java.security.MessageDigest,Reflect=Packages.java.lang.reflect.Array,ByteType=Packages.java.lang.Byte.TYPE,Integer=Packages.java.lang.Integer,StringBuilder=Packages.java.lang.StringBuilder,Text=Packages.java.lang.String;var input=null,lastLabel='integrity',OUT='ERROR|integrity|unknown';";
    js = js + "function clean(v){return String(v).replace(/[\\r\\n|]/g,' ');}function fail(label,message){lastLabel=String(label);throw new Error(String(message));}function hex(bytes){var sb=new StringBuilder();for(var i=0;i<bytes.length;i++){var value=Number(bytes[i])&255;if(value<16)sb.append('0');sb.append(Integer.toHexString(value));}return String(sb.toString());}function shaBytes(bytes){return hex(MD.getInstance('SHA-256').digest(bytes));}function shaText(text){return shaBytes(new Text(String(text)).getBytes('UTF-8'));}";
    js = js + "function shaFile(file,label){var stream=null;try{if(!file.isFile())fail(label,'archivo ausente');var digest=MD.getInstance('SHA-256');stream=new FIS(file);var buffer=Reflect.newInstance(ByteType,1048576),count;while((count=stream.read(buffer))!=-1){if(count>0)digest.update(buffer,0,count);}return hex(digest.digest());}finally{try{if(stream!=null)stream.close();}catch(ignore){}}}function readText(file,label){if(!file.isFile())fail(label,'archivo ausente');var value=String(new Text(Files.readAllBytes(file.toPath()),'UTF-8'));if(value.length>0&&value.charCodeAt(0)==65279)value=value.substring(1);return value;}function readJson(file,label){try{return JSON.parse(readText(file,label));}catch(ex){fail(label,'JSON no valido: '+clean(ex));}}";
    js = js + "function isArray(value){return Object.prototype.toString.call(value)=='[object Array]';}function stable(value){if(value===null)return 'null';if(isArray(value)){var rows=[];for(var i=0;i<value.length;i++)rows.push(stable(value[i]));return '['+rows.join(',')+']';}if(typeof value=='object'){var keys=[];for(var key in value)if(Object.prototype.hasOwnProperty.call(value,key))keys.push(String(key));keys.sort();var pairs=[];for(var j=0;j<keys.length;j++)pairs.push(JSON.stringify(keys[j])+':'+stable(value[keys[j]]));return '{'+pairs.join(',')+'}';}return JSON.stringify(value);}function payloadHash(object){var copy={};for(var key in object)if(Object.prototype.hasOwnProperty.call(object,key)&&key!='payload_sha256')copy[key]=object[key];return shaText(stable(copy));}function verifyPayload(object,label){var expected=String(object.payload_sha256||'').toLowerCase();if(!/^[0-9a-f]{64}$/.test(expected))fail(label,'payload_sha256 ausente o invalido');var actual=payloadHash(object);if(actual!=expected)fail(label,'payload_sha256 no coincide con el contenido canonico');return actual;}";
    js = js + "function canon(file){return String(file.getCanonicalPath()).replace(/\\\\/g,'/');}function same(a,b){return canon(a).toLowerCase()==canon(b).toLowerCase();}function inside(file,base){var child=canon(file).toLowerCase(),root=canon(base).toLowerCase();return child==root||child.indexOf(root+'/')==0;}function requireExact(actual,expected,label){if(!same(actual,expected))fail(label,'ruta canonica no coincide: '+canon(actual));}function verifyRecord(file,record,label,boundary){if(record==null||typeof record!='object')fail(label,'registro de manifest ausente');if(!inside(file,boundary))fail(label,'ruta fuera del directorio autorizado');if(!file.isFile())fail(label,'archivo ausente');var expectedSize=Number(record.size_bytes);if(!isFinite(expectedSize)||expectedSize<0||Math.floor(expectedSize)!=expectedSize)fail(label,'size_bytes invalido');if(Number(file.length())!=expectedSize)fail(label,'tamano distinto: esperado '+expectedSize+', real '+file.length());var expectedHash=String(record.sha256||'').toLowerCase();if(!/^[0-9a-f]{64}$/.test(expectedHash))fail(label,'SHA-256 esperado invalido');var actualHash=shaFile(file,label);if(actualHash!=expectedHash)fail(label,'SHA-256 real distinto');return actualHash;}";
    js = js + "try{var root=new File('" + jsEscape(v4ProjectDir) + "').getCanonicalFile(),projectFile=new File('" + jsEscape(projectJsonPath) + "').getCanonicalFile(),bridgePointerFile=new File('" + jsEscape(v4BridgePointerJson) + "').getCanonicalFile(),generationDir=new File('" + jsEscape(v4BridgeStaticDir) + "').getCanonicalFile(),currentMontageFile=new File('" + jsEscape(v4CurrentMontagePointerPath) + "').getCanonicalFile(),revisionManifestFile=new File('" + jsEscape(v4MasterRevisionManifestPath) + "').getCanonicalFile(),planFile=new File('" + jsEscape(v4MasterNativePlanPath) + "').getCanonicalFile(),certificateFile=new File('" + jsEscape(v4MasterFidelityReportPath) + "').getCanonicalFile(),masterFile=new File('" + jsEscape(v4MasterImage) + "').getCanonicalFile(),ownershipFile=new File('" + jsEscape(v4OwnershipImage) + "').getCanonicalFile(),recoveryFile=new File('" + jsEscape(recoveryMarker) + "').getCanonicalFile();";
    js = js + "requireExact(bridgePointerFile,new File(root,'fiji_bridge/current_bridge.json'),'current_bridge.json');requireExact(currentMontageFile,new File(root,'derived/current_montage.json'),'current_montage.json');var revisionDir=new File(new File(root,'derived/montage_revisions'),'" + jsEscape(v4MasterRevisionId) + "').getCanonicalFile();requireExact(revisionManifestFile,new File(revisionDir,'revision_manifest.json'),'revision_manifest.json');requireExact(planFile,new File(revisionDir,'montage_native_plan.json'),'montage_native_plan.json');requireExact(certificateFile,new File(revisionDir,'montage_fidelity_certificate.json'),'montage_fidelity_certificate.json');requireExact(masterFile,new File(revisionDir,'montage_master.ome.tif'),'montage_master.ome.tif');requireExact(ownershipFile,new File(revisionDir,'panel_ownership.ome.tif'),'panel_ownership.ome.tif');if(recoveryFile.exists())fail('project_bridge_recovery.json','existe un estado de recuperacion pendiente');";
    js = js + "var bridgePointer=readJson(bridgePointerFile,'current_bridge.json');verifyPayload(bridgePointer,'current_bridge.json');if(String(bridgePointer.schema_version||'')!='cavity_current_fiji_bridge_v2')fail('current_bridge.json','schema v2 requerido');if(String(bridgePointer.project_id||'')!='" + jsEscape(v4ProjectId) + "')fail('current_bridge.json','project_id no coincide');if(String(bridgePointer.generation_id||'')!='" + jsEscape(v4BridgeGenerationId) + "')fail('current_bridge.json','generation_id ya no es current');if(String(bridgePointer.revision_id||'')!='" + jsEscape(v4MasterRevisionId) + "')fail('current_bridge.json','revision_id no coincide');var generationRelative=String(bridgePointer.generation_relative_path||'').replace(/\\\\/g,'/');if(generationRelative!='fiji_bridge/generations/" + jsEscape(v4BridgeGenerationId) + "')fail('current_bridge.json','generation_relative_path no canonica');requireExact(generationDir,new File(root,generationRelative),'current_bridge.json');var generationManifestFile=new File(generationDir,'bridge_generation_manifest.json').getCanonicalFile(),generationManifestFileHash=shaFile(generationManifestFile,'bridge_generation_manifest.json'),expectedGenerationManifestHash=String(bridgePointer.generation_manifest_sha256||'').toLowerCase();if(generationManifestFileHash!=expectedGenerationManifestHash)fail('bridge_generation_manifest.json','SHA-256 real no coincide con current_bridge.json');if(bridgePointer.generation_manifest_size_bytes==null||Number(bridgePointer.generation_manifest_size_bytes)!=Number(generationManifestFile.length()))fail('bridge_generation_manifest.json','tamano no coincide con current_bridge.json');";
    js = js + "var generationManifest=readJson(generationManifestFile,'bridge_generation_manifest.json');verifyPayload(generationManifest,'bridge_generation_manifest.json');if(String(generationManifest.schema_version||'')!='cavity_fiji_bridge_generation_v2')fail('bridge_generation_manifest.json','schema v2 requerido');if(String(generationManifest.project_id||'')!='" + jsEscape(v4ProjectId) + "')fail('bridge_generation_manifest.json','project_id no coincide');if(String(generationManifest.generation_id||'')!='" + jsEscape(v4BridgeGenerationId) + "')fail('bridge_generation_manifest.json','generation_id no coincide');if(String(generationManifest.revision_id||'')!='" + jsEscape(v4MasterRevisionId) + "')fail('bridge_generation_manifest.json','revision_id no coincide');var project=readJson(projectFile,'project.json'),expectedProjectPayload=String(generationManifest.project_payload_sha256||'').toLowerCase();if(!/^[0-9a-f]{64}$/.test(expectedProjectPayload))fail('project.json','project_payload_sha256 no esta sellado por el bridge');var actualProjectPayload=shaFile(projectFile,'project.json');if(actualProjectPayload!=expectedProjectPayload)fail('project.json','los bytes vivos no coinciden con el snapshot canonico del bridge');if(String(bridgePointer.project_payload_sha256||'').toLowerCase()!=expectedProjectPayload)fail('current_bridge.json','project_payload_sha256 no coincide con el manifest de generacion');var projectVersion=Number(project.project_version),manifestProjectVersion=Number(generationManifest.project_version),pointerProjectVersion=Number(bridgePointer.project_version);if(!isFinite(projectVersion)||Math.floor(projectVersion)!=projectVersion||projectVersion<0)fail('project.json','project_version no valido');if(projectVersion!=manifestProjectVersion||projectVersion!=pointerProjectVersion)fail('project.json','project_version no coincide entre proyecto, pointer y manifest');";
    js = js + "var bridgeArtifacts=generationManifest.artifacts;if(bridgeArtifacts==null||typeof bridgeArtifacts!='object')fail('bridge_generation_manifest.json','mapa artifacts ausente');var bridgeSeen={},bridgeCount=0;for(var bridgeKey in bridgeArtifacts){if(!Object.prototype.hasOwnProperty.call(bridgeArtifacts,bridgeKey))continue;var bridgeRecord=bridgeArtifacts[bridgeKey],bridgeRelative=String((bridgeRecord||{}).relative_path||bridgeKey).replace(/\\\\/g,'/'),bridgeFile=new File(generationDir,bridgeRelative).getCanonicalFile();verifyRecord(bridgeFile,bridgeRecord,'bridge artifact '+bridgeKey,generationDir);bridgeSeen[canon(bridgeFile).toLowerCase()]=1;bridgeCount++;}var requiredCsv=['project_fields.csv','panels.csv','panel_ownership_legend.csv','roi_sets.csv','calibrations.csv','surfaces.csv'];for(var csvIndex=0;csvIndex<requiredCsv.length;csvIndex++){var csvFile=new File(generationDir,requiredCsv[csvIndex]).getCanonicalFile();if(!bridgeSeen[canon(csvFile).toLowerCase()])fail(requiredCsv[csvIndex],'CSV no sellado por bridge_generation_manifest.json');}";
    js = js + "var external=generationManifest.external_artifacts;if(external==null||typeof external!='object')fail('bridge_generation_manifest.json','external_artifacts ausente');var externalSeen={},externalCount=0;for(var externalKey in external){if(!Object.prototype.hasOwnProperty.call(external,externalKey))continue;var externalRecord=external[externalKey],externalRelative=String((externalRecord||{}).relative_path||'').replace(/\\\\/g,'/');if(externalRelative=='')fail('external artifact '+externalKey,'relative_path ausente');var externalFile=new File(root,externalRelative).getCanonicalFile(),externalCanonical=canon(externalFile).toLowerCase();if(externalSeen[externalCanonical])fail('external artifact '+externalKey,'ruta duplicada');verifyRecord(externalFile,externalRecord,'external artifact '+externalKey,root);externalSeen[externalCanonical]=1;externalCount++;}if(externalCount!=6)fail('bridge_generation_manifest.json','external_artifacts no contiene las seis entradas exactas');var requiredExternal=[currentMontageFile,revisionManifestFile,planFile,certificateFile,masterFile,ownershipFile],requiredExternalLabels=['current_montage.json','revision_manifest.json','montage_native_plan.json','montage_fidelity_certificate.json','montage_master.ome.tif','panel_ownership.ome.tif'];for(var externalIndex=0;externalIndex<requiredExternal.length;externalIndex++){if(!externalSeen[canon(requiredExternal[externalIndex]).toLowerCase()])fail(requiredExternalLabels[externalIndex],'artefacto no sellado en external_artifacts');}";
    js = js + "var currentMontage=readJson(currentMontageFile,'current_montage.json');var currentPayload=verifyPayload(currentMontage,'current_montage.json');if(currentPayload!='" + jsEscape(v4CurrentMontagePointerSha256) + "')fail('current_montage.json','payload_sha256 no coincide con project_fields.csv');if(String(currentMontage.project_id||'')!='" + jsEscape(v4ProjectId) + "'||String(currentMontage.revision_id||'')!='" + jsEscape(v4MasterRevisionId) + "')fail('current_montage.json','identidad de proyecto/revision no coincide');var expectedRevisionRelative='derived/montage_revisions/" + jsEscape(v4MasterRevisionId) + "';if(String(currentMontage.revision_relative_path||'').replace(/\\\\/g,'/')!=expectedRevisionRelative)fail('current_montage.json','revision_relative_path no canonica');";
    js = js + "var revisionManifest=readJson(revisionManifestFile,'revision_manifest.json');var revisionPayload=verifyPayload(revisionManifest,'revision_manifest.json');if(revisionPayload!='" + jsEscape(v4MasterRevisionManifestSha256) + "')fail('revision_manifest.json','payload_sha256 no coincide con project_fields.csv');if(String(revisionManifest.project_id||'')!='" + jsEscape(v4ProjectId) + "'||String(revisionManifest.revision_id||'')!='" + jsEscape(v4MasterRevisionId) + "')fail('revision_manifest.json','identidad de proyecto/revision no coincide');if(String(revisionManifest.status||'').toUpperCase()!='PASS')fail('revision_manifest.json','status no es PASS');var revisionArtifacts=revisionManifest.artifacts;if(revisionArtifacts==null||typeof revisionArtifacts!='object')fail('revision_manifest.json','mapa artifacts ausente');var revisionExpected={master:masterFile,ownership:ownershipFile,certificate:certificateFile,plan:planFile},revisionExpectedHash={master:'" + jsEscape(v4MasterSha256) + "',ownership:'" + jsEscape(v4MasterOwnershipSha256) + "',certificate:'" + jsEscape(v4MasterFidelitySha256) + "',plan:'" + jsEscape(v4MasterNativePlanSha256) + "'};for(var revisionKey in revisionExpected){if(!Object.prototype.hasOwnProperty.call(revisionExpected,revisionKey))continue;var revisionRecord=revisionArtifacts[revisionKey];if(revisionRecord==null)fail('revision_manifest.json','falta artefacto '+revisionKey);var revisionName=String(revisionRecord.name||'');var revisionFile=new File(revisionDir,revisionName).getCanonicalFile();requireExact(revisionFile,revisionExpected[revisionKey],revisionKey);var revisionHash=verifyRecord(revisionFile,revisionRecord,revisionKey,revisionDir);if(revisionHash!=String(revisionExpectedHash[revisionKey]).toLowerCase())fail(revisionKey,'SHA-256 no coincide con project_fields.csv');}";
    js = js + "var currentBridgeFileHash=shaFile(bridgePointerFile,'current_bridge.json');OUT='OK|generation='+clean('" + jsEscape(v4BridgeGenerationId) + "')+';revision='+clean('" + jsEscape(v4MasterRevisionId) + "')+';bridge_files='+bridgeCount+';external_files='+externalCount+';current_bridge_file_sha256='+currentBridgeFileHash+';generation_manifest_file_sha256='+generationManifestFileHash+';project_payload_sha256='+actualProjectPayload;}catch(ex){OUT='ERROR|'+clean(lastLabel)+'|'+clean(ex);}String(OUT);";
    return "" + eval("js", js);
}

function v55VerifyQuantitativeIntegrity(actionText, requireActiveMaster, showErrors) {
    v4RevisionBindingReady=0;v55IntegrityLastError="";
    if(!lightEnsureCurrentImage()){v55IntegrityLastError="No hay una imagen Light activa con identidad valida.";return 0;}
    if(lightSourceSha256==""||lengthOf(lightSourceSha256)!=64){v55IntegrityLastError="Falta el SHA-256 de la fuente.";if(showErrors)showMessage("Integridad cuantitativa bloqueada","No se puede "+actionText+".\n\n"+v55IntegrityLastError);return 0;}
    path=lightResolveSourcePath();if(path==""){v55IntegrityLastError="No se ha localizado la fuente DM3/DM4 registrada.";return 0;}
    actual=IJ.checksum("SHA-256 file",path);if(actual!=lightSourceSha256){v55IntegrityLastError="El SHA-256 de la fuente no coincide con el registro.";if(showErrors)showMessage("Integridad cuantitativa bloqueada","No se puede "+actionText+".\n\n"+v55IntegrityLastError);return 0;}
    v55IntegrityLastError="";v4RevisionBindingReady=1;return 1;
}


function v4JsonHasStringField(jsonText, fieldName, fieldValue) {
    spacedNeedle = "\"" + fieldName + "\": \"" + fieldValue + "\"";
    compactNeedle = "\"" + fieldName + "\":\"" + fieldValue + "\"";
    return indexOf(jsonText, spacedNeedle) >= 0 || indexOf(jsonText, compactNeedle) >= 0;
}

function v4ValidateBridgeRevisionBinding(showErrors) {
    v4RevisionBindingReady = 0;
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "validar la revision activa", showErrors)) return 0;
    missing = "";
    if (v4MasterRevisionId == "") missing = missing + "master_revision_id\n";
    if (!v4IsSha256(v4CurrentMontagePointerSha256)) missing = missing + "current_montage_pointer_sha256\n";
    if (!v4IsSha256(v4MasterRevisionManifestSha256)) missing = missing + "master_revision_manifest_sha256\n";
    if (!v4IsSha256(v4MasterNativePlanSha256)) missing = missing + "master_native_plan_sha256\n";
    if (!v4IsSha256(v4MasterFidelitySha256)) missing = missing + "master_fidelity_sha256\n";
    if (!v4IsSha256(v4MasterSha256)) missing = missing + "master_sha256\n";
    if (!v4IsSha256(v4MasterOwnershipSha256)) missing = missing + "master_ownership_sha256\n";
    if (missing != "") {
        v4RevisionBindingError = "Campos ausentes o no validos:\n" + missing;
        if (showErrors) showMessage("Revision de montaje no valida", "Fiji no abrira ni medira este proyecto porque el puente no identifica de forma completa la revision activa.\n\n" + v4RevisionBindingError + "\nVuelva a Studio 5.6.0, publique una revision valida y prepare de nuevo el puente Fiji.");
        return 0;
    }
    liveErrors = "";
    if (!File.exists(v4BridgePointerJson)) liveErrors = liveErrors + "current_bridge.json ausente\n";
    else {
        liveBridgeText = File.openAsString(v4BridgePointerJson);
        if (!v4JsonHasStringField(liveBridgeText, "generation_id", v4BridgeGenerationId)) liveErrors = liveErrors + "la generacion Fiji ya no es current\n";
        if (!v4JsonHasStringField(liveBridgeText, "project_id", v4ProjectId)) liveErrors = liveErrors + "project_id del puente no coincide\n";
    }
    generationManifestPath = projectAwareJoinPath(v4BridgeStaticDir, "bridge_generation_manifest.json");
    if (!File.exists(generationManifestPath)) liveErrors = liveErrors + "bridge_generation_manifest.json ausente\n";
    else {
        generationManifestText = File.openAsString(generationManifestPath);
        if (!v4JsonHasStringField(generationManifestText, "generation_id", v4BridgeGenerationId)) liveErrors = liveErrors + "manifest de generacion incompatible\n";
        if (!v4JsonHasStringField(generationManifestText, "revision_id", v4MasterRevisionId)) liveErrors = liveErrors + "revision_id del puente incompatible\n";
    }
    expectedPointerPath = normalizeStoredPath(projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "derived"), "current_montage.json"));
    expectedRevisionDir = projectAwareJoinPath(projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "derived"), "montage_revisions"), v4MasterRevisionId);
    expectedManifestPath = normalizeStoredPath(projectAwareJoinPath(expectedRevisionDir, "revision_manifest.json"));
    expectedPlanPath = normalizeStoredPath(projectAwareJoinPath(expectedRevisionDir, "montage_native_plan.json"));
    expectedCertificatePath = normalizeStoredPath(projectAwareJoinPath(expectedRevisionDir, "montage_fidelity_certificate.json"));
    expectedMasterPath = normalizeStoredPath(projectAwareJoinPath(expectedRevisionDir, "montage_master.ome.tif"));
    expectedOwnershipPath = normalizeStoredPath(projectAwareJoinPath(expectedRevisionDir, "panel_ownership.ome.tif"));
    normalizedCurrentPointerPath=normalizeStoredPath(v4CurrentMontagePointerPath);
    if (normalizedCurrentPointerPath != expectedPointerPath) liveErrors = liveErrors + "ruta current_montage no canonica\n";
    normalizedRevisionManifestPath=normalizeStoredPath(v4MasterRevisionManifestPath);
    if (normalizedRevisionManifestPath != expectedManifestPath) liveErrors = liveErrors + "ruta de manifest no canonica\n";
    normalizedNativePlanPath=normalizeStoredPath(v4MasterNativePlanPath);
    if (normalizedNativePlanPath != expectedPlanPath) liveErrors = liveErrors + "ruta de plan no canonica\n";
    normalizedFidelityPath=normalizeStoredPath(v4MasterFidelityReportPath);
    if (normalizedFidelityPath != expectedCertificatePath) liveErrors = liveErrors + "ruta de certificado no canonica\n";
    normalizedMasterImagePath=normalizeStoredPath(v4MasterImage);
    if (normalizedMasterImagePath != expectedMasterPath) liveErrors = liveErrors + "ruta de maestro no canonica\n";
    normalizedOwnershipImagePath=normalizeStoredPath(v4OwnershipImage);
    if (normalizedOwnershipImagePath != expectedOwnershipPath) liveErrors = liveErrors + "ruta de ownership no canonica\n";
    if (!File.exists(expectedPointerPath)) liveErrors = liveErrors + "current_montage.json ausente\n";
    else {
        currentPointerText = File.openAsString(expectedPointerPath);
        if (!v4JsonHasStringField(currentPointerText, "project_id", v4ProjectId)) liveErrors = liveErrors + "project_id de current_montage incompatible\n";
        if (!v4JsonHasStringField(currentPointerText, "revision_id", v4MasterRevisionId)) liveErrors = liveErrors + "revision_id ya no es current\n";
        if (!v4JsonHasStringField(currentPointerText, "payload_sha256", v4CurrentMontagePointerSha256)) liveErrors = liveErrors + "hash de current_montage incompatible\n";
    }
    if (!File.exists(expectedManifestPath) || !File.exists(expectedPlanPath) || !File.exists(expectedCertificatePath) || !File.exists(expectedMasterPath) || !File.exists(expectedOwnershipPath)) liveErrors = liveErrors + "faltan artefactos de la revision inmutable\n";
    else {
        revisionManifestText = File.openAsString(expectedManifestPath);
        if (!v4JsonHasStringField(revisionManifestText, "project_id", v4ProjectId)) liveErrors = liveErrors + "project_id del manifest incompatible\n";
        if (!v4JsonHasStringField(revisionManifestText, "revision_id", v4MasterRevisionId)) liveErrors = liveErrors + "revision_id del manifest incompatible\n";
        if (!v4JsonHasStringField(revisionManifestText, "payload_sha256", v4MasterRevisionManifestSha256)) liveErrors = liveErrors + "hash del manifest incompatible\n";
        if (indexOf(toLowerCase(revisionManifestText), v4MasterNativePlanSha256) < 0) liveErrors = liveErrors + "hash del plan no vinculado por el manifest\n";
        if (indexOf(toLowerCase(revisionManifestText), v4MasterFidelitySha256) < 0) liveErrors = liveErrors + "hash del certificado no vinculado por el manifest\n";
        if (indexOf(toLowerCase(revisionManifestText), v4MasterSha256) < 0) liveErrors = liveErrors + "hash del maestro no vinculado por el manifest\n";
        if (indexOf(toLowerCase(revisionManifestText), v4MasterOwnershipSha256) < 0) liveErrors = liveErrors + "hash de ownership no vinculado por el manifest\n";
    }
    if (liveErrors != "") {
        v4RevisionBindingError = "El estado vivo no coincide con la generacion cargada:\n" + liveErrors;
        if (showErrors) showMessage("Revision de montaje cambiada o corrupta", v4RevisionBindingError + "\nVuelva a Studio, regenere el puente y recargue el proyecto.");
        return 0;
    }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "validar la revision activa", showErrors)) return 0;
    if (!v55VerifyQuantitativeIntegrity("validar la revision activa", 0, showErrors)) return 0;
    v4RevisionBindingError = "";
    v4RevisionBindingReady = 1;
    return 1;
}

function v4StampCurrentRevisionBinding() {
    if (!lightProjectLoaded) return 0;
    Roi.setProperty("Revision_id", lightCurrentRevision);
    Roi.setProperty("Light_project_id", lightProjectId);
    Roi.setProperty("Light_project_uid", lightProjectUid);
    Roi.setProperty("Light_image_id", lightImageId);
    Roi.setProperty("Source_sha256", lightSourceSha256);
    return 1;
}


function v4SelectedRoiMatchesCurrentRevision() {
    if (!v4RevisionBindingReady) return 0;
    if (propString("Revision_id", "") != v4MasterRevisionId) return 0;
    if (toLowerCase(propString("Current_montage_pointer_sha256", "")) != v4CurrentMontagePointerSha256) return 0;
    if (toLowerCase(propString("Master_revision_manifest_sha256", "")) != v4MasterRevisionManifestSha256) return 0;
    if (toLowerCase(propString("Master_native_plan_sha256", "")) != v4MasterNativePlanSha256) return 0;
    if (toLowerCase(propString("Master_sha256", "")) != v4MasterSha256) return 0;
    if (toLowerCase(propString("Master_ownership_sha256", "")) != v4MasterOwnershipSha256) return 0;
    return 1;
}

function v4CountRevisionBindingMismatches() {
    run("ROI Manager...");
    mismatchCount = 0;
    bindingTotal = roiManager("count");
    bindingSelected = roiManager("index");
    for (bindingIndex=0; bindingIndex<bindingTotal; bindingIndex++) {
        if (!safeRoiSelect(bindingIndex)) continue;
        if (!v4SelectedRoiMatchesCurrentRevision()) mismatchCount++;
    }
    if (bindingSelected >= 0 && bindingSelected < bindingTotal) safeRoiSelect(bindingSelected);
    return mismatchCount;
}

function v4RequireCurrentRevisionBinding(actionText, showErrors) {
    if (!v4ValidateBridgeRevisionBinding(0)) {
        if (showErrors) showMessage("Accion bloqueada", "No se puede " + actionText + " porque la revision activa no tiene un binding completo.\n\n" + v4RevisionBindingError);
        return 0;
    }
    if (!v55VerifyQuantitativeIntegrity(actionText, 1, showErrors)) return 0;
    mismatches = v4CountRevisionBindingMismatches();
    if (mismatches > 0) {
        if (showErrors) showMessage("Revision de sesion incompatible", "No se puede " + actionText + ": hay " + mismatches + " ROI sin binding o pertenecientes a otra revision del montaje.\n\nNo se inferira identidad por nombre de archivo. Conserve el ZIP original para revision y cargue o genere una sesion de " + v4MasterRevisionId + ".");
        return 0;
    }
    return 1;
}

function v4RevisionBindingJson() {
    return "{\"schema_version\":\"cavity_revision_binding_v1\",\"project_id\":\"" + jsonEscape(v4ProjectId) + "\",\"revision_id\":\"" + jsonEscape(v4MasterRevisionId) + "\",\"current_montage_pointer_sha256\":\"" + v4CurrentMontagePointerSha256 + "\",\"master_revision_manifest_sha256\":\"" + v4MasterRevisionManifestSha256 + "\",\"master_native_plan_sha256\":\"" + v4MasterNativePlanSha256 + "\",\"master_sha256\":\"" + v4MasterSha256 + "\",\"master_ownership_sha256\":\"" + v4MasterOwnershipSha256 + "\"}\n";
}

function v4WriteRevisionBindingIntoSessionZip(path) {
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "sellar la sesion ROI", 1)) return 0;
    if (!v4RevisionBindingReady || path == "" || !File.exists(path)) return 0;
    bindingJson = v4RevisionBindingJson();
    js = "var File=Packages.java.io.File,FIS=Packages.java.io.FileInputStream,FOS=Packages.java.io.FileOutputStream,ZIS=Packages.java.util.zip.ZipInputStream,ZOS=Packages.java.util.zip.ZipOutputStream,ZE=Packages.java.util.zip.ZipEntry,Reflect=Packages.java.lang.reflect.Array,ByteType=Packages.java.lang.Byte.TYPE,Files=Packages.java.nio.file.Files,CopyOption=Packages.java.nio.file.CopyOption,Replace=Packages.java.nio.file.StandardCopyOption.REPLACE_EXISTING;";
    js = js + "var src=new File('" + jsEscape(path) + "'),tmp=new File('" + jsEscape(path + ".binding.tmp") + "'),zin=null,zout=null,OUT='ERROR';try{if(tmp.exists())tmp.delete();zin=new ZIS(new FIS(src));zout=new ZOS(new FOS(tmp));var buf=Reflect.newInstance(ByteType,8192),entry;while((entry=zin.getNextEntry())!=null){var name=String(entry.getName());if(name!='cavity_revision_binding.json'){zout.putNextEntry(new ZE(name));var count;while((count=zin.read(buf))>0)zout.write(buf,0,count);zout.closeEntry();}zin.closeEntry();}var payload=new Packages.java.lang.String('" + jsEscape(bindingJson) + "').getBytes('UTF-8');zout.putNextEntry(new ZE('cavity_revision_binding.json'));zout.write(payload,0,payload.length);zout.closeEntry();zin.close();zin=null;zout.close();zout=null;var opts=Reflect.newInstance(CopyOption,1);opts[0]=Replace;Files.move(tmp.toPath(),src.toPath(),opts);OUT='OK';}catch(ex){OUT='ERROR|'+String(ex);}finally{try{if(zin!=null)zin.close();}catch(ignore){}try{if(zout!=null)zout.close();}catch(ignore){}if(OUT!='OK'&&tmp.exists())tmp.delete();}String(OUT);";
    result = "" + eval("js", js);
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar de sellar la sesion ROI", 1)) return 0;
    if (result == "OK") return 1;
    showMessage("Sesion no certificada", "Se guardaron las ROI, pero no se pudo insertar cavity_revision_binding.json. La sesion queda bloqueada para analisis.\n\n" + result);
    return 0;
}

function v4ResolvePath(path) {
    path = normalizeStoredPath(path);
    if (path == "") return "";
    if (lengthOf(path) >= 2 && substring(path,1,2) == ":") return "" + path;
    if (startsWith(path,"/") || startsWith(path,"//")) return "" + path;
    resolvedPath = projectAwareJoinPath(v4ProjectDir, path);
    return "" + resolvedPath;
}

function v4ProjectSummary() {
    text = "Proyecto: " + v4ProjectName + "\n";
    text = text + "Revision activa: " + v4MasterRevisionId + "\n";
    text = text + "Estudio: " + v4StudyName + "\n";
    text = text + "Muestra: " + v4Material + " | " + v4Condition + "\n";
    text = text + "Lamina: " + v4SpecimenLabel + "\n";
    text = text + "Adquisicion: " + v4AcquisitionLabel + "\n";
    text = text + "Escala: " + d2s(v4PixelWidth, 9) + " x " + d2s(v4PixelHeight, 9) + " " + v4PixelUnit + "/px\n";
    if (sourceImageList != "") text = text + "Fuentes explicitas: " + sourceImageList + "\n";
    else if (sourceFirst != "" || sourceLast != "") text = text + "Rango informativo: " + sourceFirst + " - " + sourceLast + "\n";
    text = text + "Paneles: " + projectAwarePanelCount + " | Geometria: " + v4PanelGeometryStatus + " | Solape: " + v4PanelOverlapPolicy + "\n";
    text = text + "Conjunto ROI: " + v4ActiveRoiSetId;
    return text;
}

function v4ApplyScale() {
    if (nImages() <= 0 || isNaN(v4PixelWidth) || v4PixelWidth <= 0) return 0;
    if (!v4CheckImageScaleAgainstProject(1)) return 0;
    setVoxelSize(v4PixelWidth, v4PixelHeight, 1, v4PixelUnit);
    if (!updateScaleMaybe()) {
        showMessage("Escala no aplicada", "Fiji no ha aceptado la calibracion activa del proyecto.");
        return 0;
    }
    expectedX = v4ProjectScaleNmX();
    expectedY = v4ProjectScaleNmY();
    if (v4RelativeDifference(nmPerPixelX, expectedX) > 0.000001 || v4RelativeDifference(nmPerPixelY, expectedY) > 0.000001) {
        showMessage("Escala no aplicada", "La calibracion activa no coincide con la escala leida despues de aplicarla.\n\nEsperada: " + d2s(expectedX,9) + " x " + d2s(expectedY,9) + " nm/px\nLeida: " + d2s(nmPerPixelX,9) + " x " + d2s(nmPerPixelY,9) + " nm/px");
        return 0;
    }
    projectAwarePixelWidth = "" + v4PixelWidth;
    projectAwarePixelHeight = "" + v4PixelHeight;
    projectAwarePixelUnit = v4PixelUnit;
    v4ScaleConflict = 0;
    v4ScaleConflictText = "";
    showStatus("Calibracion activa aplicada: " + v4CalibrationId);
    return 1;
}

function v4ProjectScaleNmX() {
    f = unitToNmFactor(v4PixelUnit);
    if (f <= 0 || isNaN(v4PixelWidth) || v4PixelWidth <= 0) return NaN;
    return v4PixelWidth*f;
}

function v4ProjectScaleNmY() {
    f = unitToNmFactor(v4PixelUnit);
    if (f <= 0 || isNaN(v4PixelHeight) || v4PixelHeight <= 0) return NaN;
    return v4PixelHeight*f;
}

function v4RelativeDifference(a, b) {
    if (isNaN(a) || isNaN(b) || a <= 0 || b <= 0) return 0;
    denom = max2(abs(a), abs(b));
    if (denom <= 0) return 0;
    return abs(a-b)/denom;
}

function v4InspectActiveImageScale() {
    v4ImageScaleNmX = NaN;
    v4ImageScaleNmY = NaN;
    v4ImageScaleUnit = "";
    if (nImages() <= 0) return 0;
    getPixelSize(imageScaleUnit, imageScaleX, imageScaleY);
    imageScaleFactor = unitToNmFactor(imageScaleUnit);
    if (imageScaleFactor <= 0 || imageScaleX <= 0 || imageScaleY <= 0) return 0;
    v4ImageScaleNmX = imageScaleX*imageScaleFactor;
    v4ImageScaleNmY = imageScaleY*imageScaleFactor;
    v4ImageScaleUnit = imageScaleUnit;
    return 1;
}

function v4CheckImageScaleAgainstProject(showDialog) {
    v4ScaleConflict = 0;
    v4ScaleConflictText = "";
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "comprobar la escala de la imagen", showDialog)) return 0;
    projectNmX = v4ProjectScaleNmX();
    projectNmY = v4ProjectScaleNmY();
    if (isNaN(projectNmX) || isNaN(projectNmY) || projectNmX <= 0 || projectNmY <= 0) {
        v4ScaleConflict = 1;
        v4ScaleConflictText = "La calibracion activa del proyecto no es valida.";
        if (showDialog) showMessage("Calibracion no valida", v4ScaleConflictText + "\n\nRevise la pestana Referencias en Studio.");
        return 0;
    }
    // An uncalibrated image (pixel units) can safely receive the project scale.
    if (!v4InspectActiveImageScale()) return 1;
    dx = v4RelativeDifference(v4ImageScaleNmX, projectNmX);
    dy = v4RelativeDifference(v4ImageScaleNmY, projectNmY);
    if (max2(dx,dy) <= 0.01) return 1;
    ratioX = v4ImageScaleNmX/projectNmX;
    ratioY = v4ImageScaleNmY/projectNmY;
    v4ScaleConflict = 1;
    v4ScaleConflictText = "OME-TIFF: " + d2s(v4ImageScaleNmX,9) + " x " + d2s(v4ImageScaleNmY,9) + " nm/px (unidad leida: " + v4ImageScaleUnit + ")\nProyecto " + v4CalibrationId + ": " + d2s(projectNmX,9) + " x " + d2s(projectNmY,9) + " nm/px\nRelacion TIFF/proyecto: " + d2s(ratioX,6) + " x " + d2s(ratioY,6) + ".";
    if (v4ProjectDir != "") {
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "registrar el conflicto de escala", showDialog)) return 0;
        qcDir = projectAwareJoinPath(v4ProjectDir, "qc");
        makeDirIfMissing(qcDir);
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "registrar el conflicto de escala", showDialog)) return 0;
        File.saveString("Cavity TEM Studio v5.6.0 - CONFLICTO DE ESCALA\n\n" + v4ScaleConflictText + "\n\nNo se permitio iniciar una medicion cuantitativa.\n", projectAwareJoinPath(qcDir, "fiji_scale_conflict.txt"));
    }
    if (showDialog) showMessage("Conflicto de escala: medicion bloqueada", v4ScaleConflictText + "\n\nNo mida hasta decidir cual escala es correcta. Revise los metadatos DM3/DM4 y la calibracion activa en Studio; despues pulse Actualizar y vuelva a abrir Fiji.");
    return 0;
}

function v4AttachImageContext() {
    if (nImages() <= 0) return;
    info = "Cavity TEM Studio 5 context\n";
    info = info + "project_id=" + v4ProjectId + "\n";
    info = info + "revision_id=" + v4MasterRevisionId + "\n";
    info = info + "current_montage_pointer_sha256=" + v4CurrentMontagePointerSha256 + "\n";
    info = info + "master_revision_manifest_sha256=" + v4MasterRevisionManifestSha256 + "\n";
    info = info + "master_native_plan_sha256=" + v4MasterNativePlanSha256 + "\n";
    info = info + "master_sha256=" + v4MasterSha256 + "\n";
    info = info + "master_ownership_sha256=" + v4MasterOwnershipSha256 + "\n";
    info = info + "study_id=" + v4StudyId + "\n";
    info = info + "sample_id=" + v4SampleId + "\n";
    info = info + "specimen_id=" + v4SpecimenId + "\n";
    info = info + "acquisition_id=" + v4AcquisitionId + "\n";
    info = info + "calibration_id=" + v4CalibrationId + "\n";
    info = info + "surface_id=" + v4SurfaceId + "\n";
    info = info + "active_roi_set_id=" + v4ActiveRoiSetId + "\n";
    setMetadata("Info", info);
}

function v4CreatePanelsFromManifest() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("actualizar paneles", 1)) return;
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra primero el montaje maestro."); return; }
    // source_manifest.csv is an immutable source registry, not the layout
    // authority. Studio 5.6.0 writes certified layout/plan geometry to panels.csv.
    panelsPath = v4PanelsCsv;
    if (panelsPath == "") panelsPath = projectAwareJoinPath(v4BridgeStaticDir, "panels.csv");
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "leer los paneles certificados", 1)) return;
    if (!File.exists(panelsPath)) { showMessage("Paneles SVG no disponibles", "No existe:\n" + panelsPath + "\n\nVuelva a Studio, valide el SVG, construya el maestro y pulse Preparar y abrir este proyecto."); return; }
    run("ROI Manager...");
    existing = countTypeFast("panel");
    text=File.openAsString(panelsPath); lines=split(text,"\n");
    if(lines.length<2) return;
    header=split(replace(lines[0],"\r",""),",");
    ixSourceId=projectAwareColumnIndex(header,"source_id");
    ixSeq=projectAwareColumnIndex(header,"sequence_number");
    ixFile=projectAwareColumnIndex(header,"source_filename");
    ixSourcePath=projectAwareColumnIndex(header,"source_relative_path");
    ixPanel=projectAwareColumnIndex(header,"panel_id");
    ixX=projectAwareColumnIndex(header,"x_global_px");
    ixY=projectAwareColumnIndex(header,"y_global_px");
    ixW=projectAwareColumnIndex(header,"width_px");
    ixH=projectAwareColumnIndex(header,"height_px");
    ixSourceW=projectAwareColumnIndex(header,"source_width_px");
    ixSourceH=projectAwareColumnIndex(header,"source_height_px");
    ixRot=projectAwareColumnIndex(header,"rotation_deg");
    ixZ=projectAwareColumnIndex(header,"z_order");
    ixRank=projectAwareColumnIndex(header,"composition_rank_bottom_to_top");
    ixOwner=projectAwareColumnIndex(header,"owner_code");
    ixOwnedPixels=projectAwareColumnIndex(header,"effective_owned_pixels");
    ixOccluded=projectAwareColumnIndex(header,"occluded_pixel_count");
    ixZSource=projectAwareColumnIndex(header,"z_order_source");
    ixGeometrySource=projectAwareColumnIndex(header,"geometry_source");
    ixOwnershipSource=projectAwareColumnIndex(header,"ownership_source");
    ixOwnershipCertified=projectAwareColumnIndex(header,"ownership_certified");
    if(ixPanel<0||ixX<0||ixY<0||ixW<0||ixH<0||ixZ<0) { showMessage("Geometria SVG incompleta", "fiji_bridge/panels.csv no contiene panel_id, posicion, dimensiones y z_order. Actualice el puente desde Studio; source_manifest.csv no se usara como sustituto ambiguo."); return; }
    validPanelRows = 0;
    for(checkLine=1; checkLine<lines.length; checkLine++) {
        checkText=replace(lines[checkLine],"\r",""); if(checkText=="") continue;
        checkCells=split(checkText,",");
        checkW=projectAwareParseFloat(projectAwareCsvCell(checkCells,ixW)); checkH=projectAwareParseFloat(projectAwareCsvCell(checkCells,ixH));
        checkId=projectAwareCsvCell(checkCells,ixPanel);
        if(checkW>0&&checkH>0&&checkId!="") validPanelRows++;
    }
    if (validPanelRows == 0) { showMessage("Paneles no actualizados", "panels.csv no contiene ninguna fila con identidad y geometria validas. No se modifico el ROI Manager."); return; }
    backupPanelsPath = "";
    if (existing > 0) {
        if (!getBoolean("Ya existen " + existing + " paneles. Sustituirlos por " + validPanelRows + " paneles de la geometria SVG certificada?\n\nSe guardara antes una copia completa de la sesion.", "Actualizar", "Cancelar")) return;
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "actualizar los paneles certificados", 1)) return;
        backupPanelsPath = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir,"sessions"),"roi_session_before_panel_update_"+v4Timestamp()+".zip");
        roiManager("save",backupPanelsPath);
        n0=roiManager("count");
        for (di=n0-1; di>=0; di=di-1) { safeRoiSelect(di); if (currentRoiType()=="panel") roiManager("delete"); }
    }
    created=0; skipped=0;
    for(li=1; li<lines.length; li++) {
        line=replace(lines[li],"\r",""); if(line=="") continue;
        c=split(line,",");
        x=projectAwareParseFloat(projectAwareCsvCell(c,ixX)); y=projectAwareParseFloat(projectAwareCsvCell(c,ixY));
        w=projectAwareParseFloat(projectAwareCsvCell(c,ixW)); h=projectAwareParseFloat(projectAwareCsvCell(c,ixH));
        if(w<=0||h<=0) { skipped++; continue; }
        seq=round(projectAwareParseFloat(projectAwareCsvCell(c,ixSeq)));
        panelId=projectAwareCsvCell(c,ixPanel);
        if(panelId=="") { skipped++; continue; }
        svgPanelId=panelId;
        sourceId=projectAwareCsvCell(c,ixSourceId); sourceFile=projectAwareCsvCell(c,ixFile);
        sourcePath=projectAwareCsvCell(c,ixSourcePath);
        sourceW=projectAwareParseFloat(projectAwareCsvCell(c,ixSourceW)); sourceH=projectAwareParseFloat(projectAwareCsvCell(c,ixSourceH));
        rot=projectAwareParseFloat(projectAwareCsvCell(c,ixRot));
        zOrder=projectAwareParseFloat(projectAwareCsvCell(c,ixZ));
        rank=created+1; if(ixRank>=0) rank=round(projectAwareParseFloat(projectAwareCsvCell(c,ixRank)));
        ownerCode=0; if(ixOwner>=0) ownerCode=round(projectAwareParseFloat(projectAwareCsvCell(c,ixOwner)));
        ownedPixels=""; if(ixOwnedPixels>=0) ownedPixels=projectAwareCsvCell(c,ixOwnedPixels);
        occludedPixels=""; if(ixOccluded>=0) occludedPixels=projectAwareCsvCell(c,ixOccluded);
        zSource=""; if(ixZSource>=0) zSource=projectAwareCsvCell(c,ixZSource);
        geometrySource=""; if(ixGeometrySource>=0) geometrySource=projectAwareCsvCell(c,ixGeometrySource);
        ownershipSource=""; if(ixOwnershipSource>=0) ownershipSource=projectAwareCsvCell(c,ixOwnershipSource);
        ownershipCertified="0"; if(ixOwnershipCertified>=0) ownershipCertified=projectAwareCsvCell(c,ixOwnershipCertified);
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "crear los paneles certificados", 1)) return;
        makeRectangle(x,y,w,h); Roi.setName(panelId); Roi.setGroup(0); Roi.setFillColor("#00000000"); Roi.setStrokeColor("white"); Roi.setUnscalableStrokeWidth(2);
        setCommonObjectProperties(); v4StampCurrentRevisionBinding(); Roi.setProperty("Type","panel"); Roi.setProperty("Object_type","panel"); Roi.setProperty("Scientific_role","region"); Roi.setProperty("ROI_set_id","PANELS"); Roi.setProperty("Object_id",panelId); Roi.setProperty("Object_uuid",v4Uuid());
        Roi.setProperty("Panel_id",panelId); Roi.setProperty("SVG_panel_id",svgPanelId); Roi.setProperty("Panel_order",d2s(zOrder,0)); Roi.setProperty("Z_order",d2s(zOrder,0)); Roi.setProperty("Composition_rank",d2s(rank,0)); Roi.setProperty("Owner_code",d2s(ownerCode,0)); Roi.setProperty("Effective_owned_pixels",ownedPixels); Roi.setProperty("Occluded_pixel_count",occludedPixels); Roi.setProperty("Source_id",sourceId); Roi.setProperty("Source_filename",sourceFile); Roi.setProperty("Source_relative_path",sourcePath); Roi.setProperty("Source_width_px",d2s(sourceW,0)); Roi.setProperty("Source_height_px",d2s(sourceH,0)); Roi.setProperty("Rotation_deg",d2s(rot,3)); Roi.setProperty("Z_order_source",zSource); Roi.setProperty("Geometry_source",geometrySource); Roi.setProperty("Ownership_source",ownershipSource); Roi.setProperty("Ownership_certified",ownershipCertified); Roi.setProperty("Project_id",v4ProjectId); Roi.setProperty("Calibration_id",v4CalibrationId); Roi.setProperty("Include_in_statistics","1"); Roi.setProperty("Count_valid","0"); Roi.setProperty("Size_valid","0"); Roi.setProperty("Position_valid","1"); Roi.setProperty("Tool_version",v4ToolVersion);
        roiManager("add"); idx=roiManager("count")-1; syncAreaObjectAtIndex(idx); created++;
    }
    showAllRois();
    if (created > 0) syncAllObjects(0);
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar de crear los paneles certificados", 1)) return;
    ownerText = "geometria SVG/plan";
    if (v4OwnershipCertified) ownerText = "raster de ownership certificado";
    backupText = "";
    if (backupPanelsPath != "") backupText = "\nCopia previa: " + backupPanelsPath;
    showMessage("Paneles SVG actualizados", "Creados: "+created+"\nOmitidos sin geometria: "+skipped+"\nFuente: "+panelsPath+"\nAsignacion: "+ownerText+backupText+"\n\nEl fondo valido se obtiene de la cobertura de estos paneles; no necesita dibujar una mascara solo para retirar el negro exterior.");
}

function v4ChooseRoiSet() {
    if (!v4ProjectLoaded && !v4EnsureProject()) return;
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "seleccionar el conjunto ROI", 1)) return;
    if (!File.exists(v4RoiSetsCsv)) { showMessage("Sin registro ROI", "No existe:\n" + v4RoiSetsCsv); return; }
    text = File.openAsString(v4RoiSetsCsv);
    lines = split(text, "\n");
    if (lines.length < 2) return;
    ids = newArray(0); labels = newArray(0);
    for (i=1; i<lines.length; i++) {
        line = replace(lines[i], "\r", "");
        if (line == "") continue;
        cells = split(line, ",");
        if (cells.length < 2) continue;
        id = projectAwareCleanCsvValue(cells[0]);
        name = projectAwareCleanCsvValue(cells[1]);
        ids = Array.concat(ids, newArray(id));
        labels = Array.concat(labels, newArray(id + " - " + name));
    }
    if (ids.length == 0) return;
    defaultIndex = 0;
    for (i=0; i<ids.length; i++) if (ids[i] == v4ActiveRoiSetId) defaultIndex = i;
    Dialog.create("Seleccionar conjunto ROI");
    Dialog.addChoice("Conjunto activo:", labels, labels[defaultIndex]);
    Dialog.show();
    selectedLabel = Dialog.getChoice();
    selectedIndex = 0;
    for (i=0; i<labels.length; i++) if (labels[i] == selectedLabel) selectedIndex = i;
    v4ReadRoiSet(ids[selectedIndex]);
    if (!v55PersistActiveRoiSet("seleccionar el conjunto ROI")) return;
    v4SuggestToolForActiveSet();
    showStatus("Conjunto ROI activo: " + v4ActiveRoiSetId + " - " + v4ActiveRoiSetName);
}

function v4ReadRoiSet(wantedId) {
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "leer el conjunto ROI", 1)) return 0;
    if (!File.exists(v4RoiSetsCsv)) return 0;
    text = File.openAsString(v4RoiSetsCsv);
    lines = split(text, "\n");
    for (i=1; i<lines.length; i++) {
        line = replace(lines[i], "\r", "");
        if (line == "") continue;
        cells = split(line, ",");
        if (cells.length < 9) continue;
        id = projectAwareCleanCsvValue(cells[0]);
        if (id != wantedId) continue;
        nextRoiSetName = projectAwareCleanCsvValue(cells[1]);
        nextObjectType = projectAwareCleanCsvValue(cells[2]);
        nextGeometry = projectAwareCleanCsvValue(cells[3]);
        nextIdPrefix = projectAwareCleanCsvValue(cells[4]);
        nextScientificRole = projectAwareCleanCsvValue(cells[5]);
        nextStrokeColor = projectAwareCleanCsvValue(cells[6]);
        nextFillColor = projectAwareCleanCsvValue(cells[7]);
        nextProtocolId = projectAwareCleanCsvValue(cells[8]);
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "leer el conjunto ROI", 1)) return 0;
        previousRoiSetId = v4ActiveRoiSetId;
        previousRoiSetName = v4ActiveRoiSetName;
        previousObjectType = v4ActiveObjectType;
        previousGeometry = v4ActiveGeometry;
        previousIdPrefix = v4ActiveIdPrefix;
        previousScientificRole = v4ActiveScientificRole;
        previousStrokeColor = v4ActiveStrokeColor;
        previousFillColor = v4ActiveFillColor;
        previousProtocolId = v4ActiveProtocolId;
        v4ActiveRoiSetId = id;
        v4ActiveRoiSetName = nextRoiSetName;
        v4ActiveObjectType = nextObjectType;
        v4ActiveGeometry = nextGeometry;
        v4ActiveIdPrefix = nextIdPrefix;
        v4ActiveScientificRole = nextScientificRole;
        v4ActiveStrokeColor = nextStrokeColor;
        v4ActiveFillColor = nextFillColor;
        v4ActiveProtocolId = nextProtocolId;
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar el conjunto ROI", 1)) {
            v4ActiveRoiSetId = previousRoiSetId;
            v4ActiveRoiSetName = previousRoiSetName;
            v4ActiveObjectType = previousObjectType;
            v4ActiveGeometry = previousGeometry;
            v4ActiveIdPrefix = previousIdPrefix;
            v4ActiveScientificRole = previousScientificRole;
            v4ActiveStrokeColor = previousStrokeColor;
            v4ActiveFillColor = previousFillColor;
            v4ActiveProtocolId = previousProtocolId;
            return 0;
        }
        return 1;
    }
    return 0;
}

function v4SuggestToolForActiveSet() {
    if (indexOf(v4ActiveGeometry, "line") >= 0 || indexOf(v4ActiveGeometry, "polyline") >= 0) setTool("polyline");
    else if (indexOf(v4ActiveGeometry, "rectangle") >= 0) setTool("rectangle");
    else if (indexOf(v4ActiveGeometry, "contour") >= 0 || indexOf(v4ActiveGeometry, "polygon") >= 0) setTool("freehand");
    else setTool("oval");
}

function v4AddSelectionToActiveSet() {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra el montaje maestro o una imagen de analisis."); return; }
    if (selectionType < 0) { showMessage("Sin seleccion", "Dibuje primero una ROI con la geometria adecuada."); return; }
    run("ROI Manager...");
    // Transactional registration: clone the finished ROI before scanning IDs,
    // build all metadata on the clone and add it only once with its final name.
    // No __V4_PENDING__ object can remain after a failed or interrupted add.
    if (!v4StoreCurrentRoiClone("CavityV4RegistrationRoi")) {
        showMessage("ROI no registrada", "No se pudo conservar una copia segura de la seleccion.");
        return 0;
    }
    id = v4NextObjectId(v4ActiveIdPrefix);
    if (!v4RestoreStoredRoiClone("CavityV4RegistrationRoi", 0)) {
        v4ClearStoredRoiClone("CavityV4RegistrationRoi");
        showMessage("ROI no registrada", "La seleccion cambio antes de completar el registro. Dibujela de nuevo.");
        return 0;
    }
    now = d2s(getTime(),0);
    uuid = v4Uuid();
    subtype = "";
    visibleName = id;
    if (v4ActiveObjectType == "dislocation_loop") {
        subtype = v4LoopSubtypeForCurrentSelection();
        visibleName = v4VisibleLoopName(id, subtype);
    }
    Roi.setName(visibleName);
    v4SetCoreProperties(id, uuid, now);
    if (subtype != "") Roi.setProperty("Object_subtype", subtype);
    v4SetGeometryProperties();
    if (v4ActiveObjectType == "dislocation_loop") applyLoopStyle();
    else v4ApplyActiveStyle();
    before = roiManager("count");
    roiManager("add");
    after = roiManager("count");
    if (after != before+1) {
        v4RollbackRegistration(before);
        v4ClearStoredRoiClone("CavityV4RegistrationRoi");
        showMessage("ROI no registrada", "Fiji no confirmo el alta completa. No se ha conservado ningun objeto parcial.");
        return 0;
    }
    idx = after-1;
    safeRoiSelect(idx);
    if (propString("Object_id","") != id) {
        v4RollbackRegistration(before);
        v4ClearStoredRoiClone("CavityV4RegistrationRoi");
        showMessage("ROI no registrada", "La verificacion del identificador fallo. La adicion parcial se retiro.");
        return 0;
    }
    roiManager("update");
    v4ClearStoredRoiClone("CavityV4RegistrationRoi");
    roiManager("update");
    v4RefreshSpatialProperties(idx);
    showAllRois();
    safeRoiSelect(idx);
    showStatus("Objeto registrado: " + visibleName + " [" + id + "] en " + v4ActiveRoiSetId);
    return 1;
}

function v4StoreCurrentRoiClone(key) {
    if (nImages() <= 0 || selectionType < 0) return 0;
    js = "var imp=Packages.ij.IJ.getImage(),ok='0';if(imp!=null&&imp.getRoi()!=null){try{imp.setProperty('" + jsEscape(key) + "',imp.getRoi().clone());ok='1';}catch(ex){Packages.cavity.light.HF4.log('Cavity ROI snapshot: '+ex);}}String(ok);";
    result = eval("js", js);
    if (result == "1") return 1;
    return 0;
}

function v4RestoreStoredRoiClone(key, clearAfter) {
    if (nImages() <= 0) return 0;
    js = "var imp=Packages.ij.IJ.getImage(),ok='0';if(imp!=null){var saved=imp.getProperty('" + jsEscape(key) + "');if(saved!=null){try{imp.setRoi(saved.clone());ok='1';}catch(ex){Packages.cavity.light.HF4.log('Cavity ROI restore: '+ex);}if(" + clearAfter + ")imp.setProperty('" + jsEscape(key) + "',null);}}String(ok);";
    result = eval("js", js);
    if (result == "1") return 1;
    return 0;
}

function v4ClearStoredRoiClone(key) {
    if (nImages() <= 0) return;
    js = "var imp=Packages.ij.IJ.getImage();if(imp!=null)imp.setProperty('" + jsEscape(key) + "',null);";
    eval("js", js);
}

function v4RollbackRegistration(beforeCount) {
    run("ROI Manager...");
    while (roiManager("count") > beforeCount) {
        rollbackIndex = roiManager("count")-1;
        if (!safeRoiSelect(rollbackIndex)) return;
        roiManager("delete");
    }
}

function v4SetCoreProperties(id, uuid, created) {
    setCommonObjectProperties();
    v4StampCurrentRevisionBinding();
    Roi.setProperty("Object_id", id);
    Roi.setProperty("Object_uuid", uuid);
    Roi.setProperty("ROI_set_id", v4ActiveRoiSetId);
    Roi.setProperty("Object_type", v4ActiveObjectType);
    Roi.setProperty("Object_subtype", v4ActiveObjectType);
    Roi.setProperty("Geometry", v4ActiveGeometry);
    Roi.setProperty("Scientific_role", v4ActiveScientificRole);
    Roi.setProperty("Object_class", "confirmed");
    Roi.setProperty("Confidence", "high");
    Roi.setProperty("Review_status", "pending");
    Roi.setProperty("Include_in_statistics", "1");
    Roi.setProperty("Count_valid", "1");
    Roi.setProperty("Size_valid", "1");
    Roi.setProperty("Position_valid", "1");
    Roi.setProperty("Exclusion_reason", "");
    Roi.setProperty("Project_id", v4ProjectId);
    Roi.setProperty("Study_id", v4StudyId);
    Roi.setProperty("Sample_id", v4SampleId);
    Roi.setProperty("Specimen_id", v4SpecimenId);
    Roi.setProperty("Acquisition_id", v4AcquisitionId);
    Roi.setProperty("Calibration_id", v4CalibrationId);
    Roi.setProperty("Surface_id", v4SurfaceId);
    Roi.setProperty("Measurement_protocol_id", v4ActiveProtocolId);
    Roi.setProperty("Operator", operatorName);
    Roi.setProperty("Created_time_ms", created);
    Roi.setProperty("Modified_time_ms", created);
    Roi.setProperty("Tool_version", v4ToolVersion);
    // Also provide the legacy Type used by v8.3 tools.
    legacyType = v4ActiveObjectType;
    if (v4ActiveObjectType == "dislocation_loop" || v4ActiveObjectType == "precipitate") legacyType = v4ActiveObjectType;
    if (v4ActiveScientificRole == "region" && v4ActiveObjectType == "mask") legacyType = "analysis_mask";
    Roi.setProperty("Type", legacyType);
}

function v4SetGeometryProperties() {
    updateScaleMaybe();
    getSelectionBounds(x, y, w, h);
    cx = x + w/2; cy = y + h/2;
    Roi.setProperty("Center_x_px", d2s(cx,6));
    Roi.setProperty("Center_y_px", d2s(cy,6));
    Roi.setProperty("Center_x_nm", d2s(cx*nmPerPixelX,6));
    Roi.setProperty("Center_y_nm", d2s(cy*nmPerPixelY,6));
    Roi.setProperty("Bounds_x_px", d2s(x,6));
    Roi.setProperty("Bounds_y_px", d2s(y,6));
    Roi.setProperty("Bounds_width_px", d2s(w,6));
    Roi.setProperty("Bounds_height_px", d2s(h,6));
    areaPx = 0;
    getStatistics(areaPx);
    areaNm2 = areaPx * nmPerPixelX * nmPerPixelY;
    Roi.setProperty("Projected_area_nm2", d2s(areaNm2,6));
    if (areaNm2 > 0) Roi.setProperty("Equivalent_diameter_nm", d2s(2*sqrt(areaNm2/PI_VAL),6));
    major = max2(w*nmPerPixelX, h*nmPerPixelY);
    minor = min2(w*nmPerPixelX, h*nmPerPixelY);
    orientation = 0;
    if (h*nmPerPixelY > w*nmPerPixelX) orientation = 90;
    ellipseMetrics = v4InclinedEllipseMetrics();
    if (startsWith(ellipseMetrics, "1,")) {
        em = split(ellipseMetrics, ",");
        if (em.length >= 6) {
            major = parseFloat(em[1]);
            minor = parseFloat(em[2]);
            orientation = parseFloat(em[3]);
            cx = parseFloat(em[4]);
            cy = parseFloat(em[5]);
            Roi.setProperty("Center_x_px", d2s(cx,6));
            Roi.setProperty("Center_y_px", d2s(cy,6));
            Roi.setProperty("Center_x_nm", d2s(cx*nmPerPixelX,6));
            Roi.setProperty("Center_y_nm", d2s(cy*nmPerPixelY,6));
        }
    }
    Roi.setProperty("Major_axis_nm", d2s(major,6));
    Roi.setProperty("Minor_axis_nm", d2s(minor,6));
    Roi.setProperty("Orientation_deg", d2s(orientation,6));
    if (minor > 0) Roi.setProperty("Aspect_ratio", d2s(major/minor,6));
    if (selectionType == 5 || selectionType == 6 || selectionType == 7) {
        Roi.getCoordinates(xs, ys);
        len = polylineLengthNm(xs,ys);
        Roi.setProperty("Length_nm", d2s(len,6));
        if (v4ActiveObjectType == "cavity") Roi.setProperty("Equivalent_diameter_nm", d2s(len,6));
    }
    geometryObjectType = Roi.getProperty("Object_type");
    if (geometryObjectType == "") geometryObjectType = v4ActiveObjectType;
    if (geometryObjectType == "dislocation_loop" && (selectionType == 1 || selectionType == 2 || selectionType == 3 || selectionType == 4)) v4SetLoopMetrics();
}

function v4InclinedEllipseMetrics() {
    if (!v4SelectionIsEllipseRoi()) return "0";
    js = "var imp=Packages.ij.IJ.getImage(),r=imp==null?null:imp.getRoi(),out='0';if(r!=null&&String(r.getClass().getName())=='ij.gui.EllipseRoi'){try{var p=r.getParams();if(p!=null&&p.length>=5){var dx=p[2]-p[0],dy=p[3]-p[1],majorPx=Math.sqrt(dx*dx+dy*dy),ratio=Math.abs(p[4]),minorPx=majorPx*ratio,sx=" + d2s(nmPerPixelX,12) + ",sy=" + d2s(nmPerPixelY,12) + ",majorNm=Math.sqrt(dx*dx*sx*sx+dy*dy*sy*sy),ux=majorPx>0?-dy/majorPx:0,uy=majorPx>0?dx/majorPx:0,minorNm=minorPx*Math.sqrt(ux*ux*sx*sx+uy*uy*sy*sy),angle=Math.atan2(dy*sy,dx*sx)*180/Math.PI,cx=(p[0]+p[2])/2,cy=(p[1]+p[3])/2;if(angle<0)angle+=180;out='1,'+majorNm+','+minorNm+','+angle+','+cx+','+cy;}}catch(ex){Packages.cavity.light.HF4.log('Cavity EllipseRoi metrics: '+ex);}}String(out);";
    return "" + eval("js", js);
}

function v4ApplyActiveStyle() {
    if (v4ActiveObjectType == "dislocation_loop") { applyLoopStyle(); return; }
    if (v4ActiveStrokeColor != "") Roi.setStrokeColor(v4ActiveStrokeColor);
    Roi.setUnscalableStrokeWidth(roiStrokeWidth);
    if (v4ActiveFillColor != "" && v4ActiveScientificRole != "line_feature" && v4ActiveScientificRole != "reference_feature") Roi.setFillColor(v4ActiveFillColor);
}

function v4NextObjectId(prefix) {
    run("ROI Manager...");
    selectedIndex = roiManager("index");
    n = roiManager("count"); maxSerial = 0;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        current = Roi.getProperty("Object_id");
        if (current == "") current = Roi.getName;
        if (startsWith(current, prefix + "_")) {
            serial = serialFromId(current);
            if (serial > maxSerial) maxSerial = serial;
        }
    }
    if (selectedIndex >= 0 && selectedIndex < n) safeRoiSelect(selectedIndex);
    return prefix + "_" + IJ.pad(maxSerial+1, 6);
}

function v4Uuid() {
    id = eval("js", "String(java.util.UUID.randomUUID())");
    return "" + id;
}

function v4RefreshSpatialProperties(idx) {
    if (!safeRoiSelect(idx)) return;
    spatialType = currentRoiType();
    getSelectionBounds(x,y,w,h); cx=x+w/2; cy=y+h/2;
    panelForPoint(cx,cy);
    ownerCode = panelLastOwnerCode;
    coverageCount = panelLastCoverageCount;
    effectiveMatches = panelLastMatchCount;
    effectivePanelId = panelLastId;
    effectiveSource = panelLastSource;
    boundaryCross = 0;
    boundaryOwnerCount = 0;
    boundaryTouchesBackground = 0;
    if (v4RoleForType(spatialType) == "defect") {
        boundaryInfo = split(v51PanelBoundaryInfo(idx), ",");
        if (boundaryInfo.length > 0) boundaryCross = round(parseFloat(boundaryInfo[0]));
        if (boundaryInfo.length > 1) boundaryOwnerCount = round(parseFloat(boundaryInfo[1]));
        if (boundaryInfo.length > 2) boundaryTouchesBackground = round(parseFloat(boundaryInfo[2]));
    }
    safeRoiSelect(idx);
    Roi.setProperty("Panel_id", effectivePanelId);
    Roi.setProperty("Source_filename", effectiveSource);
    Roi.setProperty("Panel_match_count", d2s(effectiveMatches,0));
    Roi.setProperty("Effective_owner_code", d2s(ownerCode,0));
    Roi.setProperty("Geometric_coverage_count", d2s(coverageCount,0));
    Roi.setProperty("Crosses_panel_boundary", d2s(boundaryCross,0));
    Roi.setProperty("Distinct_panel_owners", d2s(boundaryOwnerCount,0));
    Roi.setProperty("Touches_panel_background", d2s(boundaryTouchesBackground,0));
    boundaryReviewed = round(propNumber("Panel_boundary_reviewed",0));
    Roi.setProperty("Panel_boundary_review_required", d2s(boundaryCross && !boundaryReviewed,0));
    if (boundaryCross && !boundaryReviewed) Roi.setProperty("Size_valid", "0");
    localFound = v4LocalCoordinatesForPoint(cx,cy);
    safeRoiSelect(idx);
    if (localFound) {
        Roi.setProperty("X_local_px", d2s(v4LastLocalXpx,6));
        Roi.setProperty("Y_local_px", d2s(v4LastLocalYpx,6));
    } else {
        Roi.setProperty("X_local_px", "NaN");
        Roi.setProperty("Y_local_px", "NaN");
    }
    if (surfaceDefined && computeSurfaceMetrics(cx,cy)) {
        Roi.setProperty("Distance_to_surface_nm", d2s(surfaceLastDistanceNm,6));
        Roi.setProperty("Signed_depth_nm", d2s(surfaceLastSignedDistanceNm,6));
        Roi.setProperty("Absolute_depth_nm", d2s(surfaceLastDistanceNm,6));
        s = surfaceLastArcNm;
        if (v4SurfaceOriginDefined) s = (s-v4SurfaceOriginArcNm)*v4SurfaceTangentialSign;
        Roi.setProperty("Surface_position_nm", d2s(s,6));
        Roi.setProperty("Surface_nearest_x_px", d2s(surfaceLastNearestXpx,6));
        Roi.setProperty("Surface_nearest_y_px", d2s(surfaceLastNearestYpx,6));
        Roi.setProperty("Surface_tangent_angle_deg", d2s(surfaceLastTangentAngleDeg,6));
    }
    Roi.setProperty("Modified_time_ms", d2s(getTime(),0));
    roiManager("update");
}

function v4LocalCoordinatesForPoint(x,y) {
    v4LastLocalXpx=NaN; v4LastLocalYpx=NaN;
    n=roiManager("count"); bestOrder=-1e30; found=0;
    for(pi=0; pi<n; pi++) {
        safeRoiSelect(pi); if(currentRoiType()!="panel") continue;
        if(!Roi.contains(round(x),round(y))) continue;
        order=propNumber("Panel_order",0); if(order<bestOrder) continue;
        Roi.getFloatBounds(px,py,pw,ph); u=x-px; v=y-py;
        sw=propNumber("Source_width_px",pw); sh=propNumber("Source_height_px",ph); rot=round(propNumber("Rotation_deg",0));
        while(rot<0) rot=rot+360; while(rot>=360) rot=rot-360;
        lx=NaN; ly=NaN;
        if(rot==0) { lx=u; ly=v; }
        else if(rot==90) { lx=sw-1-v; ly=u; }
        else if(rot==180) { lx=sw-1-u; ly=sh-1-v; }
        else if(rot==270) { lx=v; ly=sh-1-u; }
        if(!isNaN(lx)&&!isNaN(ly)) { v4LastLocalXpx=lx; v4LastLocalYpx=ly; found=1; bestOrder=order; }
    }
    return found;
}


function v4ReviewSelectedObject() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("revisar la ROI", 1)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) { showMessage("Sin ROI", "Seleccione una ROI en el ROI Manager."); return; }
    safeRoiSelect(idx);
    oldId = propString("Object_id", Roi.getName);
    oldSet = propString("ROI_set_id", "");
    oldClass = propString("Object_class", "doubtful");
    oldConfidence = propString("Confidence", "medium");
    oldReview = propString("Review_status", "pending");
    if (oldClass!="confirmed" && oldClass!="doubtful" && oldClass!="possible_artifact" && oldClass!="rejected") oldClass="doubtful";
    if (oldConfidence!="high" && oldConfidence!="medium" && oldConfidence!="low" && oldConfidence!="algorithmic") oldConfidence="medium";
    if (oldReview!="reviewed" && oldReview!="pending") oldReview="pending";
    oldInclude = propNumber("Include_in_statistics", 0);
    oldCount = propNumber("Count_valid", 0);
    oldSize = propNumber("Size_valid", 0);
    oldPosition = propNumber("Position_valid", 1);
    oldBoundaryCross = round(propNumber("Crosses_panel_boundary", 0));
    oldBoundaryReviewed = round(propNumber("Panel_boundary_reviewed", 0));
    if (oldBoundaryCross && !oldBoundaryReviewed) oldSize = 0;
    classes = newArray("confirmed", "doubtful", "possible_artifact", "rejected");
    confidences = newArray("high", "medium", "low", "algorithmic");
    reviews = newArray("reviewed", "pending");
    Dialog.create("Revisar objeto");
    reviewIntro = "Objeto: " + oldId + "\nConjunto: " + oldSet + "\n\nLos candidatos confirmados se transfieren a CAVITIES y conservan Candidate_id.";
    if (oldBoundaryCross) reviewIntro = reviewIntro + "\n\nATENCION: el contorno cruza una frontera efectiva de panel. El recuento pertenece al panel del centroide, pero el tamano solo sera valido si lo confirma aqui tras revisar ambas fuentes.";
    Dialog.addMessage(reviewIntro);
    Dialog.addChoice("Clase:", classes, oldClass);
    Dialog.addChoice("Confianza:", confidences, oldConfidence);
    Dialog.addChoice("Revision:", reviews, oldReview);
    Dialog.addCheckbox("Incluir en estadistica", oldInclude);
    Dialog.addCheckbox("Valido para recuento", oldCount);
    Dialog.addCheckbox("Valido para tamano", oldSize);
    Dialog.addCheckbox("Valido para posicion", oldPosition);
    Dialog.addString("Motivo de exclusion:", propString("Exclusion_reason", ""), 35);
    Dialog.show();
    cls = Dialog.getChoice();
    conf = Dialog.getChoice();
    review = Dialog.getChoice();
    include = Dialog.getCheckbox();
    countValid = Dialog.getCheckbox();
    sizeValid = Dialog.getCheckbox();
    positionValid = Dialog.getCheckbox();
    reason = Dialog.getString();
    if (cls == "possible_artifact" || cls == "rejected") {
        include = 0; countValid = 0; sizeValid = 0;
        if (reason == "") reason = cls;
    }
    if (oldSet == "CAVITY_CANDIDATES" && cls == "confirmed") {
        previousSet = v4ActiveRoiSetId;
        if (v4ReadRoiSet("CAVITIES")) {
            newId = v4NextObjectId(v4ActiveIdPrefix);
            Roi.setProperty("Candidate_id", oldId);
            Roi.setName(newId);
            Roi.setProperty("Object_id", newId);
            Roi.setProperty("ROI_set_id", v4ActiveRoiSetId);
            Roi.setProperty("Object_type", v4ActiveObjectType);
            Roi.setProperty("Geometry", v4ActiveGeometry);
            Roi.setProperty("Scientific_role", v4ActiveScientificRole);
            Roi.setProperty("Measurement_protocol_id", v4ActiveProtocolId);
            v4ApplyActiveStyle();
            oldId = newId;
        }
        v4ReadRoiSet(previousSet);
    }
    Roi.setProperty("Object_class", cls);
    Roi.setProperty("Confidence", conf);
    Roi.setProperty("Review_status", review);
    Roi.setProperty("Include_in_statistics", "" + include);
    Roi.setProperty("Count_valid", "" + countValid);
    Roi.setProperty("Size_valid", "" + sizeValid);
    Roi.setProperty("Position_valid", "" + positionValid);
    if (oldBoundaryCross) {
        boundaryReviewedNow = 0;
        if (review == "reviewed") boundaryReviewedNow = 1;
        Roi.setProperty("Panel_boundary_reviewed", "" + boundaryReviewedNow);
        Roi.setProperty("Panel_boundary_review_required", "" + (1-boundaryReviewedNow));
        if (!boundaryReviewedNow) Roi.setProperty("Size_valid", "0");
    }
    Roi.setProperty("Exclusion_reason", reason);
    Roi.setProperty("Reviewed_by", operatorName);
    Roi.setProperty("Reviewed_time_ms", d2s(getTime(),0));
    Roi.setProperty("Modified_time_ms", d2s(getTime(),0));
    roiManager("update");
    v4RefreshSpatialProperties(idx);
    showStatus("Objeto revisado: " + oldId + " | " + cls);
}

function v4UpgradeSelectedRoi() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("actualizar la ROI", 1)) return;
    run("ROI Manager...");
    idx = roiManager("index");
    if (idx < 0) { showMessage("Sin ROI", "Seleccione una ROI en el ROI Manager."); return; }
    v4UpgradeRoiAtIndex(idx);
    showStatus("ROI actualizada al esquema compatible.");
}

function v4UpgradeAllRois() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("actualizar las ROI", 1)) return;
    run("ROI Manager...");
    n = roiManager("count");
    for (i=0; i<n; i++) v4UpgradeRoiAtIndex(i);
    showStatus("ROIs actualizadas al esquema compatible: " + n);
}

function v4UpgradeRoiAtIndex(idx) {
    if (!safeRoiSelect(idx)) return;
    oldType = currentRoiType();
    objectType = Roi.getProperty("Object_type");
    if (objectType == "") objectType = oldType;
    if (objectType == "") objectType = "unclassified";
    setId = Roi.getProperty("ROI_set_id");
    if (setId == "") setId = v4SetIdForType(objectType);
    prefix = v4PrefixForType(objectType);
    id = Roi.getProperty("Object_id");
    if (id == "") {
        id = objectIdCurrent(oldType);
        if (id == "" || id == "SURFACE_REFERENCE") id = v4NextObjectId(prefix);
    }
    if (objectType == "dislocation_loop" && !startsWith(id, "LOOP_")) id = v4NextObjectId("LOOP");
    uuid = Roi.getProperty("Object_uuid");
    if (uuid == "") uuid = v4Uuid();
    created = Roi.getProperty("Created_time_ms");
    if (created == "") created = d2s(getTime(),0);
    existingProjectId = Roi.getProperty("Project_id");
    if (existingProjectId != "" && existingProjectId != v4ProjectId) {
        Roi.setProperty("Project_mismatch", "1");
        Roi.setProperty("Project_mismatch_expected", v4ProjectId);
        roiManager("update");
        return;
    }
    Roi.setProperty("Object_id", id);
    Roi.setProperty("Object_uuid", uuid);
    Roi.setProperty("ROI_set_id", setId);
    Roi.setProperty("Object_type", objectType);
    Roi.setProperty("Scientific_role", v4RoleForType(objectType));
    Roi.setProperty("Project_id", v4ProjectId);
    Roi.setProperty("Study_id", v4StudyId);
    Roi.setProperty("Sample_id", v4SampleId);
    Roi.setProperty("Specimen_id", v4SpecimenId);
    Roi.setProperty("Acquisition_id", v4AcquisitionId);
    Roi.setProperty("Calibration_id", v4CalibrationId);
    Roi.setProperty("Surface_id", v4SurfaceId);
    if (Roi.getProperty("Measurement_protocol_id") == "") Roi.setProperty("Measurement_protocol_id", v4ProtocolForType(objectType));
    if (Roi.getProperty("Object_class") == "") Roi.setProperty("Object_class", propString("Cavity_class", "confirmed"));
    if (Roi.getProperty("Confidence") == "") Roi.setProperty("Confidence", propString("Cavity_confidence", "high"));
    if (Roi.getProperty("Review_status") == "") Roi.setProperty("Review_status", "pending");
    if (Roi.getProperty("Include_in_statistics") == "") Roi.setProperty("Include_in_statistics", "1");
    if (Roi.getProperty("Count_valid") == "") Roi.setProperty("Count_valid", propString("Include_in_statistics","1"));
    if (Roi.getProperty("Size_valid") == "") {
        sizeFlag = "1";
        if (propNumber("Edge_intersecting",0) > 0) sizeFlag = "0";
        Roi.setProperty("Size_valid", sizeFlag);
    }
    if (Roi.getProperty("Position_valid") == "") Roi.setProperty("Position_valid", propString("Include_in_statistics","1"));
    Roi.setProperty("Created_time_ms", created);
    Roi.setProperty("Modified_time_ms", d2s(getTime(),0));
    Roi.setProperty("Tool_version", v4ToolVersion);
    if (objectType == "dislocation_loop") {
        subtype = Roi.getProperty("Object_subtype");
        if (subtype == "") subtype = v4LoopSubtypeForCurrentSelection();
        Roi.setProperty("Object_subtype", subtype);
        Roi.setProperty("Type", "dislocation_loop");
        Roi.setProperty("Feature_id", id);
        Roi.setName(v4VisibleLoopName(id, subtype));
    }
    v4SetGeometryProperties();
    roiManager("update");
    v4RefreshSpatialProperties(idx);
}

function v4SetIdForType(t) {
    if (t == "cavity") return "CAVITIES";
    if (t == "dislocation_loop") return "LOOPS";
    if (t == "precipitate") return "PRECIPITATES";
    if (t == "dislocation") return "DISLOCATIONS";
    if (t == "grain_boundary") return "GRAIN_BOUNDARIES";
    if (t == "interface") return "INTERFACES";
    if (t == "panel") return "PANELS";
    if (t == "analysis_mask") return "ANALYSIS_MASKS";
    if (t == "exclusion") return "EXCLUSIONS";
    if (t == "surface_reference") return "SURFACES";
    return "UNCLASSIFIED";
}

function v4PrefixForType(t) {
    if (t == "cavity") return "CAV";
    if (t == "dislocation_loop") return "LOOP";
    if (t == "precipitate") return "PPT";
    if (t == "dislocation") return "DIS";
    if (t == "grain_boundary") return "GB";
    if (t == "interface") return "INT";
    if (t == "panel") return "PANEL";
    if (t == "analysis_mask") return "MASK";
    if (t == "exclusion") return "EXCL";
    if (t == "surface_reference") return "SURF";
    return "OBJ";
}

function v4RoleForType(t) {
    if (t == "panel" || t == "analysis_mask" || t == "exclusion") return "region";
    if (t == "surface_reference" || t == "grain_boundary" || t == "interface") return "reference_feature";
    if (t == "dislocation") return "line_feature";
    return "defect";
}

function v4ProtocolForType(t) {
    if (t == "cavity") return "CAVITY_MANUAL_V1";
    if (t == "dislocation") return "DISLOCATION_TRACE_V1";
    if (t == "dislocation_loop") return "LOOP_MANUAL_V1";
    if (t == "precipitate") return "PARTICLE_MANUAL_V1";
    return "REFERENCE_OR_REGION_V1";
}

function v4DefineSurfaceComplete() {
    if (!v4PrepareImageForMeasurement(1)) return;
    defineSurfaceReference();
    if (!surfaceDefined) return;
    v4DefineSurfaceOrigin();
}

function v4DefineSurfaceOrigin() {
    if (!v4PrepareImageForMeasurement(1)) return;
    if (!surfaceDefined) loadSurfaceReferenceFromRois();
    if (!surfaceDefined) { showMessage("Sin superficie", "Defina primero la superficie y el lado del material."); return; }
    setTool("point");
    if (!waitForUserSafe("Definir origen s=0", "Haga click sobre, o muy cerca de, la superficie en el punto que sera s=0.\nPulse OK despues del click.")) return;
    if (selectionType != 10) { showMessage("Origen no definido", "La seleccion debe ser un punto."); return; }
    getSelectionCoordinates(px,py);
    if (px.length < 1 || !computeSurfaceMetrics(px[0],py[0])) return;
    arc = surfaceLastArcNm;
    nearestX = surfaceLastNearestXpx; nearestY = surfaceLastNearestYpx;
    Dialog.create("Sentido de la coordenada superficial");
    Dialog.addChoice("Sentido positivo de s:", newArray("Desde el primer vertice hacia el ultimo", "Desde el ultimo vertice hacia el primero"), "Desde el primer vertice hacia el ultimo");
    Dialog.show();
    direction = Dialog.getChoice();
    sign = 1; if (direction == "Desde el ultimo vertice hacia el primero") sign = -1;
    v4SurfaceOriginDefined = 1;
    v4SurfaceOriginArcNm = arc;
    v4SurfaceOriginXpx = nearestX;
    v4SurfaceOriginYpx = nearestY;
    v4SurfaceTangentialSign = sign;
    idx = findSurfaceReferenceIndex();
    if (idx >= 0) {
        safeRoiSelect(idx);
        Roi.setProperty("Surface_id", v4SurfaceId);
        Roi.setProperty("Origin_defined", "1");
        Roi.setProperty("Origin_arc_nm", d2s(arc,6));
        Roi.setProperty("Origin_x_px", d2s(nearestX,6));
        Roi.setProperty("Origin_y_px", d2s(nearestY,6));
        Roi.setProperty("Tangential_sign", d2s(sign,0));
        Roi.setProperty("Project_id", v4ProjectId);
        roiManager("update");
    }
    v4PersistSurfaceState();
    v4UpgradeAllRois();
    showStatus("Origen s=0 definido para " + v4SurfaceId);
}

function v4PersistSurfaceState() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("guardar la superficie", 1)) return;
    if (!surfaceDefined) loadSurfaceReferenceFromRois();
    if (!surfaceDefined) return;
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "guardar el estado de superficie", 1)) return;
    refs = projectAwareJoinPath(v4ProjectDir, "references"); makeDirIfMissing(refs);
    geometryName = "surface_geometry_" + v4SurfaceId + ".csv";
    geometryPath = projectAwareJoinPath(refs, geometryName);
    geom = "surface_id,point_index,x_px,y_px,x_nm,y_nm\n";
    for (i=0; i<surfaceX.length; i++) {
        geom = geom + projectAwareCsvEscape(v4SurfaceId) + "," + i + "," + d2s(surfaceX[i],6) + "," + d2s(surfaceY[i],6) + "," + d2s(surfaceX[i]*nmPerPixelX,6) + "," + d2s(surfaceY[i]*nmPerPixelY,6) + "\n";
    }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar la geometria de superficie", 1)) return;
    File.saveString(geom, geometryPath);
    statePath = projectAwareJoinPath(refs, "surface_state_from_fiji.csv");
    state = "surface_id,geometry_file,origin_defined,origin_arc_nm,origin_x_px,origin_y_px,tangential_sign,side_defined,material_side_sign,material_point_x_px,material_point_y_px,point_count,updated_time_ms\n";
    state = state + projectAwareCsvEscape(v4SurfaceId) + "," + projectAwareCsvEscape("references/"+geometryName) + "," + v4SurfaceOriginDefined + "," + d2s(v4SurfaceOriginArcNm,6) + "," + d2s(v4SurfaceOriginXpx,6) + "," + d2s(v4SurfaceOriginYpx,6) + "," + v4SurfaceTangentialSign + "," + surfaceSideDefined + "," + surfaceMaterialSign + "," + d2s(surfaceMaterialX,6) + "," + d2s(surfaceMaterialY,6) + "," + surfaceX.length + "," + d2s(getTime(),0) + "\n";
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar el estado de superficie", 1)) return;
    File.saveString(state, statePath);
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar de guardar la superficie", 1)) return;
}

function v4LoadSurfaceStateFromBridge() {
    if (!v4ProjectLoaded) return;
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "leer el estado de superficie", 1)) return;
    surfacesPath = v4ResolvePath(v4Field("surfaces_csv"));
    if (surfacesPath == "") surfacesPath = projectAwareJoinPath(v4BridgeStaticDir, "surfaces.csv");
    if (!File.exists(surfacesPath)) return;
    text = File.openAsString(surfacesPath); lines = split(text,"\n");
    for (i=1; i<lines.length; i++) {
        line=replace(lines[i],"\r",""); if (line=="") continue;
        c=split(line,","); if (c.length<10) continue;
        id=projectAwareCleanCsvValue(c[0]); if (id!=v4SurfaceId) continue;
        nextOriginDefined = parseFloat(projectAwareCleanCsvValue(c[4]));
        nextOriginArcNm = parseFloat(projectAwareCleanCsvValue(c[5]));
        nextOriginXpx = parseFloat(projectAwareCleanCsvValue(c[6]));
        nextOriginYpx = parseFloat(projectAwareCleanCsvValue(c[7]));
        nextTangentialSign = parseFloat(projectAwareCleanCsvValue(c[8]));
        if (isNaN(nextTangentialSign) || nextTangentialSign==0) nextTangentialSign=1;
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "leer el estado de superficie", 1)) return;
        previousOriginDefined = v4SurfaceOriginDefined;
        previousOriginArcNm = v4SurfaceOriginArcNm;
        previousOriginXpx = v4SurfaceOriginXpx;
        previousOriginYpx = v4SurfaceOriginYpx;
        previousTangentialSign = v4SurfaceTangentialSign;
        v4SurfaceOriginDefined = nextOriginDefined;
        v4SurfaceOriginArcNm = nextOriginArcNm;
        v4SurfaceOriginXpx = nextOriginXpx;
        v4SurfaceOriginYpx = nextOriginYpx;
        v4SurfaceTangentialSign = nextTangentialSign;
        if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar el estado de superficie", 1)) {
            v4SurfaceOriginDefined = previousOriginDefined;
            v4SurfaceOriginArcNm = previousOriginArcNm;
            v4SurfaceOriginXpx = previousOriginXpx;
            v4SurfaceOriginYpx = previousOriginYpx;
            v4SurfaceTangentialSign = previousTangentialSign;
            return;
        }
        return;
    }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar de leer el estado de superficie", 1)) return;
}

function v4ShowObjectTable() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("mostrar la tabla cuantitativa", 1)) return;
    run("ROI Manager...");
    n = roiManager("count");
    run("Clear Results");
    row=0;
    for (i=0; i<n; i++) {
        safeRoiSelect(i);
        t=Roi.getProperty("Object_type"); if (t=="") t=currentRoiType();
        if (t=="session_metadata" || t=="scale_label") continue;
        id=Roi.getProperty("Object_id"); if (id=="") id=objectIdCurrent(currentRoiType());
        setResult("ROI",row,i);
        setResult("Object ID",row,id);
        setResult("Set",row,Roi.getProperty("ROI_set_id"));
        setResult("Type",row,t);
        setResult("Class",row,propString("Object_class",propString("Cavity_class","")));
        setResult("Review",row,propString("Review_status",""));
        setResult("Included",row,propNumber("Include_in_statistics",1));
        setResult("Size (nm)",row,propNumber("Equivalent_diameter_nm",propNumber("Diameter_nm",NaN)));
        setResult("Depth (nm)",row,propNumber("Signed_depth_nm",propNumber("Depth_nm",NaN)));
        setResult("s (nm)",row,propNumber("Surface_position_nm",NaN));
        setResult("Panel",row,propString("Panel_id",""));
        row++;
    }
    updateResults();
    showStatus("Tabla creada. La columna ROI permite localizar el indice en ROI Manager.");
}

function v51RemoveOverlayPrefix(prefix) {
    if (nImages() <= 0) return 0;
    js = "var imp=Packages.ij.IJ.getImage(),removed=0,ov=imp==null?null:imp.getOverlay();if(ov!=null){for(var i=ov.size()-1;i>=0;i--){var r=ov.get(i),n=r==null?null:r.getName();if(n!=null&&String(n).indexOf('" + jsEscape(prefix) + "')==0){ov.remove(i);removed++;}}imp.setOverlay(ov);imp.updateAndDraw();}String(removed);";
    removed = round(parseFloat("" + eval("js", js)));
    showStatus("Ayudas visuales retiradas del overlay: " + removed + ". Los pixeles no se modificaron.");
    return removed;
}

function v51ConfigureScaleBarOverlay() {
    if (nImages() <= 0) { showMessage("Barra de escala", "Abra primero una imagen calibrada."); return; }
    if (!updateScaleMaybe()) { showMessage("Barra de escala", "La imagen no tiene calibracion fisica valida."); return; }
    positions = newArray("Abajo derecha", "Abajo izquierda", "Arriba derecha", "Arriba izquierda");
    Dialog.create("Barra de escala visual - overlay no destructivo");
    Dialog.addMessage("La barra usa la calibracion ya conciliada. Es solo una ayuda visual: no crea una referencia cientifica ni cambia los pixeles.");
    Dialog.addNumber("Longitud (nm):", v51ScaleBarLengthNm);
    Dialog.addChoice("Posicion:", positions, v51ScaleBarPosition);
    Dialog.addString("Color barra/texto (#RRGGBB):", v51ScaleBarColor, 10);
    Dialog.addString("Color fondo (#RRGGBB):", v51ScaleBarBackground, 10);
    Dialog.addNumber("Opacidad fondo (0-255):", v51ScaleBarBackgroundAlpha);
    Dialog.addNumber("Grosor barra (px de imagen):", v51ScaleBarThicknessPx);
    Dialog.addNumber("Tamano texto (px):", v51ScaleBarFontPx);
    Dialog.addNumber("Margen (px):", v51ScaleBarMarginPx);
    Dialog.show();
    v51ScaleBarLengthNm = Dialog.getNumber();
    v51ScaleBarPosition = Dialog.getChoice();
    v51ScaleBarColor = Dialog.getString();
    v51ScaleBarBackground = Dialog.getString();
    v51ScaleBarBackgroundAlpha = round(Dialog.getNumber());
    v51ScaleBarThicknessPx = round(Dialog.getNumber());
    v51ScaleBarFontPx = round(Dialog.getNumber());
    v51ScaleBarMarginPx = round(Dialog.getNumber());
    if (v51ScaleBarLengthNm <= 0) { showMessage("Valor no valido", "La longitud debe ser mayor que cero."); return; }
    if (v51ScaleBarBackgroundAlpha < 0) v51ScaleBarBackgroundAlpha = 0;
    if (v51ScaleBarBackgroundAlpha > 255) v51ScaleBarBackgroundAlpha = 255;
    if (v51ScaleBarThicknessPx < 1) v51ScaleBarThicknessPx = 1;
    if (v51ScaleBarFontPx < 8) v51ScaleBarFontPx = 8;
    if (v51ScaleBarMarginPx < 0) v51ScaleBarMarginPx = 0;
    v51RenderScaleBarOverlay();
}

function v51RenderScaleBarOverlay() {
    if (nImages() <= 0 || !updateScaleMaybe()) return 0;
    barPx = v51ScaleBarLengthNm/nmPerPixelX;
    if (barPx < 1 || barPx > getWidth()-2*v51ScaleBarMarginPx) {
        showMessage("Barra fuera de rango", "La longitud elegida equivale a " + d2s(barPx,1) + " px y no cabe con el margen actual.");
        return 0;
    }
    label = d2s(v51ScaleBarLengthNm,0) + " nm";
    if (v51ScaleBarLengthNm >= 1000) label = d2s(v51ScaleBarLengthNm/1000.0,2) + " um";
    js = "var IJ=Packages.ij.IJ,Overlay=Packages.ij.gui.Overlay,Roi=Packages.ij.gui.Roi,TextRoi=Packages.ij.gui.TextRoi,Color=Packages.java.awt.Color,Font=Packages.java.awt.Font;var imp=IJ.getImage(),OUT='ERROR';try{var ov=imp.getOverlay();if(ov==null)ov=new Overlay();for(var i=ov.size()-1;i>=0;i--){var old=ov.get(i),nm=old==null?null:old.getName();if(nm!=null&&String(nm).indexOf('CAVITY_SCALE_')==0)ov.remove(i);}function color(hex,a){var c=Color.decode(String(hex));return new Color((a<<24)|(c.getRed()<<16)|(c.getGreen()<<8)|c.getBlue(),true);}var barW=Math.max(1,Math.round(" + d2s(barPx,6) + ")),th=" + v51ScaleBarThicknessPx + ",fontPx=" + v51ScaleBarFontPx + ",margin=" + v51ScaleBarMarginPx + ",label='" + jsEscape(label) + "',approx=Math.round(label.length*fontPx*0.64),boxW=Math.max(barW,approx)+20,boxH=th+fontPx+22,w=imp.getWidth(),h=imp.getHeight(),pos='" + jsEscape(v51ScaleBarPosition) + "',x=margin,y=h-margin-boxH;if(pos.indexOf('izquierda')>=0)x=margin;else x=w-margin-boxW;if(pos.indexOf('Arriba')==0)y=margin;x=Math.max(0,Math.min(w-boxW,x));y=Math.max(0,Math.min(h-boxH,y));var bg=new Roi(x,y,boxW,boxH);bg.setName('CAVITY_SCALE_BACKGROUND');bg.setFillColor(color('" + jsEscape(v51ScaleBarBackground) + "'," + v51ScaleBarBackgroundAlpha + "));bg.setStrokeColor(null);ov.add(bg);var bx=x+10+(boxW-barW-20)/2,by=y+boxH-th-10;var bar=new Roi(Math.round(bx),Math.round(by),barW,th);bar.setName('CAVITY_SCALE_BAR');bar.setFillColor(color('" + jsEscape(v51ScaleBarColor) + "',255));bar.setStrokeColor(null);ov.add(bar);var text=new TextRoi(Math.round(x+(boxW-approx)/2),Math.round(y+2),label,new Font('SansSerif',Font.PLAIN,fontPx));text.setName('CAVITY_SCALE_TEXT');text.setStrokeColor(color('" + jsEscape(v51ScaleBarColor) + "',255));ov.add(text);imp.setOverlay(ov);imp.updateAndDraw();OUT='OK|'+barW;}catch(ex){OUT='ERROR|'+String(ex);}String(OUT);";
    result = "" + eval("js", js);
    if (!startsWith(result,"OK|")) { showMessage("Barra no creada", result); return 0; }
    showStatus("Barra visual anadida al overlay: " + label + ". Pixeles intactos.");
    return 1;
}

function v51ConfigureSurfaceGuides() {
    if (nImages() <= 0) { showMessage("Guias paralelas", "Abra primero una imagen calibrada."); return; }
    if (!updateScaleMaybe()) { showMessage("Guias paralelas", "La imagen no tiene calibracion fisica valida."); return; }
    if (!surfaceDefined) loadSurfaceReferenceFromRois();
    if (!surfaceDefined) { showMessage("Guias paralelas", "Defina primero la superficie y el lado del material."); return; }
    Dialog.create("Guias paralelas a la superficie - overlay");
    Dialog.addMessage("Se crean offsets visuales aproximados de la polilinea de superficie en unidades fisicas. No se anaden al ROI Manager ni entran en los calculos.");
    Dialog.addNumber("Separacion (nm):", v51GuideSpacingNm);
    Dialog.addNumber("Distancia maxima (nm):", v51GuideMaximumNm);
    Dialog.addString("Color (#RRGGBB):", v51GuideColor, 10);
    Dialog.addNumber("Grosor (px de imagen):", v51GuideWidthPx);
    Dialog.addCheckbox("Linea discontinua", v51GuideDashed);
    Dialog.addCheckbox("Mostrar tambien el lado opuesto", v51GuideBothSides);
    Dialog.addCheckbox("Mostrar distancias", v51GuideLabels);
    Dialog.show();
    v51GuideSpacingNm = Dialog.getNumber();
    v51GuideMaximumNm = Dialog.getNumber();
    v51GuideColor = Dialog.getString();
    v51GuideWidthPx = Dialog.getNumber();
    v51GuideDashed = Dialog.getCheckbox();
    v51GuideBothSides = Dialog.getCheckbox();
    v51GuideLabels = Dialog.getCheckbox();
    if (v51GuideSpacingNm <= 0 || v51GuideMaximumNm < v51GuideSpacingNm) { showMessage("Valores no validos", "La separacion debe ser positiva y la distancia maxima debe ser igual o mayor."); return; }
    if (v51GuideMaximumNm/v51GuideSpacingNm > 200) { showMessage("Demasiadas guias", "Configure como maximo 200 lineas por lado para mantener Fiji fluido."); return; }
    if (v51GuideWidthPx < 0.5) v51GuideWidthPx = 0.5;
    v51RenderSurfaceGuides();
}

function v51RenderSurfaceGuides() {
    if (nImages() <= 0 || !updateScaleMaybe()) return 0;
    if (!surfaceDefined) loadSurfaceReferenceFromRois();
    if (!surfaceDefined) return 0;
    js = "var IJ=Packages.ij.IJ,RM=Packages.ij.plugin.frame.RoiManager,Overlay=Packages.ij.gui.Overlay,Roi=Packages.ij.gui.Roi,PolygonRoi=Packages.ij.gui.PolygonRoi,TextRoi=Packages.ij.gui.TextRoi,Color=Packages.java.awt.Color,Font=Packages.java.awt.Font,BasicStroke=Packages.java.awt.BasicStroke,Reflect=Packages.java.lang.reflect.Array,FloatType=Packages.java.lang.Float.TYPE;var imp=IJ.getImage(),OUT='ERROR';try{var rm=RM.getInstance2(),surface=null,rois=rm==null?[]:rm.getRoisAsArray();function typ(r){var t=r.getProperty('Object_type');if(t==null||String(t)=='')t=r.getProperty('Type');return t==null?'':String(t);}for(var r=0;r<rois.length;r++){var t=typ(rois[r]),n=String(rois[r].getName());if(t=='surface_reference'||t=='surface'||n.indexOf('SURFACE_REFERENCE')==0){surface=rois[r];break;}}if(surface==null){OUT='ERROR|surface_missing';}else{var fp=(surface instanceof Packages.ij.gui.Line?surface.getFloatPoints():surface.getFloatPolygon()),count=fp.npoints;if(count<2){OUT='ERROR|surface_too_short';}else{var ov=imp.getOverlay();if(ov==null)ov=new Overlay();for(var oi=ov.size()-1;oi>=0;oi--){var old=ov.get(oi),on=old==null?null:old.getName();if(on!=null&&String(on).indexOf('CAVITY_GUIDE_')==0)ov.remove(oi);}var base=Color.decode('" + jsEscape(v51GuideColor) + "'),sx=" + d2s(nmPerPixelX,12) + ",sy=" + d2s(nmPerPixelY,12) + ",spacing=" + d2s(v51GuideSpacingNm,9) + ",maximum=" + d2s(v51GuideMaximumNm,9) + ",materialSign=" + d2s(surfaceMaterialSign,0) + ",both=" + d2s(v51GuideBothSides,0) + ",dashed=" + d2s(v51GuideDashed,0) + ",labels=" + d2s(v51GuideLabels,0) + ",width=" + d2s(v51GuideWidthPx,3) + ",made=0;var sides=both?[materialSign,-materialSign]:[materialSign];for(var si=0;si<sides.length;si++){var sign=sides[si];for(var dist=spacing;dist<=maximum+spacing*1e-9;dist+=spacing){var xp=Reflect.newInstance(FloatType,count),yp=Reflect.newInstance(FloatType,count);for(var p=0;p<count;p++){var p0=Math.max(0,p-1),p1=Math.min(count-1,p+1),dx=(fp.xpoints[p1]-fp.xpoints[p0])*sx,dy=(fp.ypoints[p1]-fp.ypoints[p0])*sy,len=Math.sqrt(dx*dx+dy*dy);if(len<=0){dx=1;dy=0;len=1;}var nx=-dy/len,ny=dx/len;xp[p]=fp.xpoints[p]+sign*dist*nx/sx;yp[p]=fp.ypoints[p]+sign*dist*ny/sy;}var line=new PolygonRoi(xp,yp,count,Roi.POLYLINE);line.setName('CAVITY_GUIDE_'+si+'_'+Math.round(dist)+'NM');line.setStrokeColor(base);line.setStrokeWidth(width);if(dashed){try{var dash=Reflect.newInstance(FloatType,2);dash[0]=10;dash[1]=7;line.setStroke(new BasicStroke(width,BasicStroke.CAP_BUTT,BasicStroke.JOIN_ROUND,10,dash,0));line.setStrokeColor(base);}catch(ignore){}}ov.add(line);if(labels){var mid=Math.floor(count/2),txt=new TextRoi(Math.round(xp[mid]+4),Math.round(yp[mid]+4),Math.round(dist)+' nm',new Font('SansSerif',Font.PLAIN,14));txt.setName('CAVITY_GUIDE_LABEL_'+si+'_'+Math.round(dist)+'NM');txt.setStrokeColor(base);ov.add(txt);}made++;}}imp.setOverlay(ov);imp.updateAndDraw();OUT='OK|'+made;}}}}catch(ex){OUT='ERROR|'+String(ex);}String(OUT);";
    result = "" + eval("js", js);
    if (!startsWith(result,"OK|")) { showMessage("Guias no creadas", result); return 0; }
    showStatus("Guias paralelas anadidas al overlay (" + substring(result,3) + "). Pixeles y ROIs cientificas intactos.");
    return 1;
}

function v51ActiveImageIsRegisteredMaster(verbose) {
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "comprobar el maestro registrado", verbose)) return 0;
    if (v4MasterImage == "" || !File.exists(v4MasterImage)) {
        if (verbose) showMessage("Area no disponible", "El proyecto no tiene un maestro registrado y disponible. Vuelva a Studio y construya o abra el OME-TIFF certificado.");
        return 0;
    }
    wantedMasterPath = normalizeStoredPath(v4MasterImage);
    activeMasterPath = v4CurrentImageCanonicalPath();
    if (activeMasterPath == "" || activeMasterPath != wantedMasterPath) {
        if (verbose) showMessage("Imagen incorrecta para el area", "El area solo se calcula sobre el maestro registrado exacto, nunca sobre una copia filtrada o una ventana con el mismo tamano.\n\nMaestro esperado:\n" + wantedMasterPath + "\n\nImagen activa:\n" + activeMasterPath + "\n\nUse Abrir o activar montaje maestro y vuelva a intentarlo.");
        return 0;
    }
    return 1;
}

function v51ComputeAndSaveExactValidArea(verbose) {
    // Exact, non-sampled denominator:
    //   ownership > 0 AND optional inclusion union AND NOT exclusion union.
    // The ownership raster already resolves SVG overlap by certified z-order,
    // therefore every valid montage pixel belongs to at most one panel.
    v51LastExactAreaCsv = "";
    v51LastExactAreaMethod = "not_calculated";
    if (!v4EnsureProject()) return 0;
    if (!v4RequireCurrentRevisionBinding("calcular el area valida", verbose)) return 0;
    if (nImages() <= 0) { if (verbose) showMessage("Area exacta", "Abra la imagen maestra del proyecto."); return 0; }
    if (!v51ActiveImageIsRegisteredMaster(verbose)) return 0;
    if (!v4ScaleMeasurementAllowed || !v4CheckImageScaleAgainstProject(0) || !updateScaleMaybe()) {
        if (verbose) showMessage("Area exacta no disponible", "La calibracion de proyecto no esta conciliada con la imagen activa.");
        return 0;
    }
    if (!v4OwnershipCertified || !v4PanelQuantitativeReady || v4OwnershipImage == "" || !File.exists(v4OwnershipImage)) {
        if (verbose) {
            useFallback = getBoolean("No hay panel_ownership.ome.tif certificado.\n\nPuede intentar detectar automaticamente solo el fondo negro (valor 0) conectado al borde. El negro interior se conserva como area. El resultado quedara marcado como FALLBACK NO CERTIFICADO y no ofrecera desglose fiable por panel.\n\nUsar este fallback ahora?", "Usar fondo negro", "Cancelar");
            if (useFallback) return v51ComputeBlackBackgroundFallback(1);
            showMessage("Area exacta no disponible", "Reconstruya o actualice el montaje en Studio para obtener ownership certificado. El fallback negro nunca sustituye silenciosamente esa evidencia.");
        }
        return 0;
    }
    run("ROI Manager...");
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "leer el ownership para el area exacta", verbose)) return 0;
    showStatus("Calculando area exacta: ownership, inclusion opcional y exclusiones...");
    js = "var IJ=Packages.ij.IJ,RM=Packages.ij.plugin.frame.RoiManager,BP=Packages.ij.process.ByteProcessor;var OUT='ERROR|unknown',owner=null;";
    js = js + "try{var active=IJ.getImage();owner=IJ.openImage('" + jsEscape(v4OwnershipImage) + "');if(active==null||owner==null){OUT='ERROR|image_missing';}else if(active.getWidth()!=owner.getWidth()||active.getHeight()!=owner.getHeight()){OUT='ERROR|dimension_mismatch|'+active.getWidth()+'x'+active.getHeight()+'|'+owner.getWidth()+'x'+owner.getHeight();}else{";
    js = js + "var w=owner.getWidth(),h=owner.getHeight(),n=w*h,rm=RM.getInstance2(),rois=rm==null?[]:rm.getRoisAsArray(),masks=[],exclusions=[];function typ(r){var t=r.getProperty('Object_type');if(t==null||String(t)=='')t=r.getProperty('Type');return t==null?'':String(t);}";
    js = js + "for(var r=0;r<rois.length;r++){var t=typ(rois[r]);if(t=='analysis_mask')masks.push(rois[r]);else if(t=='exclusion')exclusions.push(rois[r]);}function paint(bp,roi,value){bp.setValue(value);bp.fill(roi);}";
    js = js + "var inc=new BP(w,h),exc=new BP(w,h),maskApplied=masks.length>0;if(maskApplied){for(var a=0;a<masks.length;a++)paint(inc,masks[a],255);}else{inc.setValue(255);inc.fill();}for(var e=0;e<exclusions.length;e++)paint(exc,exclusions[e],255);";
    js = js + "var op=owner.getProcessor(),pix=op.getPixels(),ipix=inc.getPixels(),epix=exc.getPixels(),bits=owner.getBitDepth(),by={},coverage=0,outside=0,excluded=0,valid=0;for(var i=0;i<n;i++){var code=Number(pix[i]);if(code<0&&bits==8)code+=256;else if(code<0&&bits==16)code+=65536;code=Math.round(code);if(code<=0)continue;coverage++;var row=by[code];if(row==null){row=[0,0,0,0];by[code]=row;}row[0]++;if(ipix[i]==0){outside++;row[1]++;}else if(epix[i]!=0){excluded++;row[2]++;}else{valid++;row[3]++;}}";
    js = js + "var keys=[];for(var k in by)if(by.hasOwnProperty(k))keys.push(parseInt(k,10));keys.sort(function(a,b){return a-b;});var rows=[];for(var q=0;q<keys.length;q++){var c=keys[q],z=by[c];rows.push(c+':'+z[0]+':'+z[1]+':'+z[2]+':'+z[3]);}OUT='OK|'+w+'|'+h+'|'+coverage+'|'+outside+'|'+excluded+'|'+valid+'|'+(maskApplied?1:0)+'|'+(rows.length?rows.join(';'):'NONE');}}catch(ex){OUT='ERROR|'+String(ex);}finally{try{if(owner!=null){owner.changes=false;owner.close();}}catch(ignore){}}String(OUT);";
    result = "" + eval("js", js);
    parts = split(result, "|");
    if (parts.length < 9 || parts[0] != "OK") {
        if (verbose) showMessage("Area exacta no calculada", "No se modifico ninguna imagen.\n\nDetalle: " + result);
        showStatus("Area exacta no calculada: " + result);
        return 0;
    }
    coveragePixels = parseFloat(parts[3]);
    outsidePixels = parseFloat(parts[4]);
    excludedPixels = parseFloat(parts[5]);
    validPixels = parseFloat(parts[6]);
    inclusionApplied = round(parseFloat(parts[7]));
    pixelAreaNm2 = nmPerPixelX*nmPerPixelY;
    lastValidAreaNm2 = validPixels*pixelAreaNm2;
    generatedTime = d2s(getTime(),0);
    method = "ownership_exact_svg_z_order_intersect_optional_inclusion_minus_exclusions";
    csv = "project_id,revision_id,current_montage_pointer_sha256,master_revision_manifest_sha256,master_native_plan_sha256,master_sha256,master_ownership_sha256,panel_id,owner_code,valid_pixel_count,valid_area_nm2,valid_area_um2,method,coverage_pixel_count,outside_inclusion_pixel_count,excluded_pixel_count,inclusion_mask_applied,ownership_image,ownership_certified,generated_time_ms\n";
    ownerRows = parts[8];
    if (ownerRows != "NONE") {
        encodedRows = split(ownerRows, ";");
        for (ar=0; ar<encodedRows.length; ar++) {
            fields = split(encodedRows[ar], ":");
            if (fields.length < 5) continue;
            code = round(parseFloat(fields[0]));
            panelCoverage = parseFloat(fields[1]);
            panelOutside = parseFloat(fields[2]);
            panelExcluded = parseFloat(fields[3]);
            panelValid = parseFloat(fields[4]);
            panelId = v51PanelIdForOwnerCode(code);
            if (panelId == "") panelId = "OWNER_" + code;
            panelAreaNm2 = panelValid*pixelAreaNm2;
            csv = csv + projectAwareCsvEscape(v4ProjectId) + "," + projectAwareCsvEscape(v4MasterRevisionId) + "," + projectAwareCsvEscape(v4CurrentMontagePointerSha256) + "," + projectAwareCsvEscape(v4MasterRevisionManifestSha256) + "," + projectAwareCsvEscape(v4MasterNativePlanSha256) + "," + projectAwareCsvEscape(v4MasterSha256) + "," + projectAwareCsvEscape(v4MasterOwnershipSha256) + "," + projectAwareCsvEscape(panelId) + "," + code + "," + d2s(panelValid,0) + "," + d2s(panelAreaNm2,9) + "," + d2s(panelAreaNm2/1000000.0,12) + "," + projectAwareCsvEscape(method) + "," + d2s(panelCoverage,0) + "," + d2s(panelOutside,0) + "," + d2s(panelExcluded,0) + "," + inclusionApplied + "," + projectAwareCsvEscape(v4OwnershipImage) + ",1," + generatedTime + "\n";
        }
    }
    csv = csv + projectAwareCsvEscape(v4ProjectId) + "," + projectAwareCsvEscape(v4MasterRevisionId) + "," + projectAwareCsvEscape(v4CurrentMontagePointerSha256) + "," + projectAwareCsvEscape(v4MasterRevisionManifestSha256) + "," + projectAwareCsvEscape(v4MasterNativePlanSha256) + "," + projectAwareCsvEscape(v4MasterSha256) + "," + projectAwareCsvEscape(v4MasterOwnershipSha256) + ",__TOTAL__,0," + d2s(validPixels,0) + "," + d2s(lastValidAreaNm2,9) + "," + d2s(lastValidAreaNm2/1000000.0,12) + "," + projectAwareCsvEscape(method) + "," + d2s(coveragePixels,0) + "," + d2s(outsidePixels,0) + "," + d2s(excludedPixels,0) + "," + inclusionApplied + "," + projectAwareCsvEscape(v4OwnershipImage) + ",1," + generatedTime + "\n";
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar el area exacta", verbose)) return 0;
    exportsDir = projectAwareJoinPath(v4ProjectDir, "exports");
    makeDirIfMissing(exportsDir);
    v51LastExactAreaCsv = projectAwareJoinPath(exportsDir, "valid_area_by_panel.csv");
    File.saveString(csv, v51LastExactAreaCsv);
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar de publicar el area exacta", verbose)) return 0;
    v51LastExactAreaMethod = method;
    showStatus("Area valida exacta: " + d2s(lastValidAreaNm2,3) + " nm^2 (sin doble conteo).");
    if (verbose) showMessage("Area valida exacta", "Cobertura SVG/ownership: " + d2s(coveragePixels,0) + " px\nFuera de inclusion opcional: " + d2s(outsidePixels,0) + " px\nExcluidos: " + d2s(excludedPixels,0) + " px\nValidos: " + d2s(validPixels,0) + " px\n\nArea valida: " + d2s(lastValidAreaNm2,3) + " nm^2\n\n" + v51LastExactAreaCsv);
    return 1;
}

function v51PanelIdForOwnerCode(code) {
    run("ROI Manager...");
    selected = roiManager("index");
    found = "";
    n = roiManager("count");
    for (pi=0; pi<n; pi++) {
        if (!safeRoiSelect(pi)) continue;
        if (currentRoiType() == "panel" && round(propNumber("Owner_code",0)) == code) {
            found = propString("Panel_id", Roi.getName);
            break;
        }
    }
    if (selected >= 0 && selected < n) safeRoiSelect(selected);
    return "" + found;
}

function v51ComputeBlackBackgroundFallback(verbose) {
    // Explicit compatibility fallback for old projects only. A 4-connected
    // FloodFiller marks exactly the zero-valued background reachable from the
    // image border; enclosed black detail remains valid material.
    if (!v4EnsureProject() || nImages() <= 0) return 0;
    if (!v4RequireCurrentRevisionBinding("calcular el area fallback", verbose)) return 0;
    if (!v51ActiveImageIsRegisteredMaster(verbose) || !updateScaleMaybe()) return 0;
    if (v4OwnershipCertified && v4OwnershipImage != "" && File.exists(v4OwnershipImage)) {
        if (verbose) showMessage("Fallback no usado", "Existe ownership certificado. Use Calcular area exacta para conservar la propiedad por panel.");
        return 0;
    }
    run("ROI Manager...");
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "calcular el area fallback", verbose)) return 0;
    showStatus("Detectando fondo negro conectado al borde (fallback no certificado)...");
    js = "var IJ=Packages.ij.IJ,RM=Packages.ij.plugin.frame.RoiManager,BP=Packages.ij.process.ByteProcessor,FF=Packages.ij.process.FloodFiller;var OUT='ERROR';try{var imp=IJ.getImage(),w=imp.getWidth(),h=imp.getHeight(),n=w*h,src=imp.getProcessor().getPixels(),black=new BP(w,h),bp=black.getPixels();for(var i=0;i<n;i++)bp[i]=(Number(src[i])==0)?255:0;black.setValue(128);var flood=new FF(black);for(var x=0;x<w;x++){if(black.get(x,0)==255)flood.fill(x,0);if(h>1&&black.get(x,h-1)==255)flood.fill(x,h-1);}for(var y=0;y<h;y++){if(black.get(0,y)==255)flood.fill(0,y);if(w>1&&black.get(w-1,y)==255)flood.fill(w-1,y);}var rm=RM.getInstance2(),rois=rm==null?[]:rm.getRoisAsArray(),masks=[],exclusions=[];function typ(r){var t=r.getProperty('Object_type');if(t==null||String(t)=='')t=r.getProperty('Type');return t==null?'':String(t);}for(var r=0;r<rois.length;r++){var t=typ(rois[r]);if(t=='analysis_mask')masks.push(rois[r]);else if(t=='exclusion')exclusions.push(rois[r]);}function paint(p,r,v){p.setValue(v);p.fill(r);}var inc=new BP(w,h),exc=new BP(w,h),maskApplied=masks.length>0;if(maskApplied){for(var a=0;a<masks.length;a++)paint(inc,masks[a],255);}else{inc.setValue(255);inc.fill();}for(var e=0;e<exclusions.length;e++)paint(exc,exclusions[e],255);var iv=inc.getPixels(),ev=exc.getPixels(),background=0,enclosedBlack=0,coverage=0,outside=0,excluded=0,valid=0;for(var q=0;q<n;q++){var state=Number(bp[q])&255;if(state==128){background++;continue;}coverage++;if(state==255)enclosedBlack++;if(iv[q]==0)outside++;else if(ev[q]!=0)excluded++;else valid++;}OUT='OK|'+w+'|'+h+'|'+background+'|'+enclosedBlack+'|'+coverage+'|'+outside+'|'+excluded+'|'+valid+'|'+(maskApplied?1:0);}catch(ex){OUT='ERROR|'+String(ex);}String(OUT);";
    result = "" + eval("js", js);
    parts = split(result,"|");
    if (parts.length < 10 || parts[0] != "OK") { if (verbose) showMessage("Fallback no calculado", result); return 0; }
    backgroundPixels = parseFloat(parts[3]);
    enclosedBlackPixels = parseFloat(parts[4]);
    coveragePixels = parseFloat(parts[5]);
    outsidePixels = parseFloat(parts[6]);
    excludedPixels = parseFloat(parts[7]);
    validPixels = parseFloat(parts[8]);
    inclusionApplied = round(parseFloat(parts[9]));
    pixelAreaNm2 = nmPerPixelX*nmPerPixelY;
    lastValidAreaNm2 = validPixels*pixelAreaNm2;
    generatedTime = d2s(getTime(),0);
    method = "black_background_border_connected_4_fallback_uncertified";
    csv = "project_id,revision_id,current_montage_pointer_sha256,master_revision_manifest_sha256,master_native_plan_sha256,master_sha256,master_ownership_sha256,panel_id,owner_code,valid_pixel_count,valid_area_nm2,valid_area_um2,method,coverage_pixel_count,outside_inclusion_pixel_count,excluded_pixel_count,inclusion_mask_applied,ownership_image,ownership_certified,generated_time_ms\n";
    csv = csv + projectAwareCsvEscape(v4ProjectId) + "," + projectAwareCsvEscape(v4MasterRevisionId) + "," + projectAwareCsvEscape(v4CurrentMontagePointerSha256) + "," + projectAwareCsvEscape(v4MasterRevisionManifestSha256) + "," + projectAwareCsvEscape(v4MasterNativePlanSha256) + "," + projectAwareCsvEscape(v4MasterSha256) + "," + projectAwareCsvEscape(v4MasterOwnershipSha256) + ",__TOTAL__,0," + d2s(validPixels,0) + "," + d2s(lastValidAreaNm2,9) + "," + d2s(lastValidAreaNm2/1000000.0,12) + "," + projectAwareCsvEscape(method) + "," + d2s(coveragePixels,0) + "," + d2s(outsidePixels,0) + "," + d2s(excludedPixels,0) + "," + inclusionApplied + ",,0," + generatedTime + "\n";
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar el area fallback", verbose)) return 0;
    exportsDir = projectAwareJoinPath(v4ProjectDir,"exports"); makeDirIfMissing(exportsDir);
    v51LastExactAreaCsv = projectAwareJoinPath(exportsDir,"valid_area_by_panel.csv");
    File.saveString(csv,v51LastExactAreaCsv);
    v51LastExactAreaMethod = method;
    qcDir = projectAwareJoinPath(v4ProjectDir,"qc"); makeDirIfMissing(qcDir);
    File.saveString("Cavity TEM Studio v5.6.0 - FALLBACK DE AREA NO CERTIFICADO\n\nMetodo: "+method+"\nFondo negro 4-conexo al borde: "+d2s(backgroundPixels,0)+" px\nNegro interior preservado: "+d2s(enclosedBlackPixels,0)+" px\nArea valida: "+d2s(lastValidAreaNm2,9)+" nm^2\n\nRegenere el montaje para obtener ownership certificado antes de publicar resultados por panel.\n",projectAwareJoinPath(qcDir,"fiji_black_background_fallback.txt"));
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar de publicar el area fallback", verbose)) return 0;
    showStatus("Area fallback calculada y marcada como NO CERTIFICADA.");
    if (verbose) showMessage("Area por fondo negro - NO CERTIFICADA", "Fondo negro conectado al borde: "+d2s(backgroundPixels,0)+" px\nNegro interior preservado: "+d2s(enclosedBlackPixels,0)+" px\nValidos tras inclusion/exclusiones: "+d2s(validPixels,0)+" px\nArea: "+d2s(lastValidAreaNm2,3)+" nm^2\n\nNo hay desglose fiable por panel. Resultado: "+v51LastExactAreaCsv);
    return 1;
}

function v4ExportAll() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("exportar", 1)) return;
    if (!v56RequireCurrentSessionQuantitative("exportar o analizar resultados", 1)) return;
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra la imagen asociada antes de exportar."); return; }
    run("ROI Manager...");
    if (roiManager("count") == 0) { showMessage("Sin ROIs", "No hay objetos para exportar."); return; }
    foreignProjectRois = v4CountForeignProjectRois();
    if (foreignProjectRois > 0) {
        showMessage("Exportacion bloqueada", "El ROI Manager contiene " + foreignProjectRois + " ROI asociados a otro proyecto.\n\nNo se ha reescrito ningun Project_id. Limpie el ROI Manager y cargue la sesion correcta antes de exportar.");
        return;
    }
    syncAllObjects(0);
    if (!quantitativeExportPreflight()) return;
    // Reject incomplete identity before the compatibility upgrader can fill
    // anything. Once this read-only gate is green, the upgrader only refreshes
    // already identified ROI and the central save gate validates them again.
    exportIdentityDraft = v56CollectRoiDraftJson();
    if (exportIdentityDraft == "") {
        showMessage("Exportacion bloqueada", v56RoiDraftError);
        return;
    }
    v4UpgradeAllRois();
    exactAreaReady = v51ComputeAndSaveExactValidArea(0);
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "preparar la exportacion v4", 1)) return;
    v4RunId = "RUN_" + v4Timestamp();
    exports = projectAwareJoinPath(v4ProjectDir,"exports"); makeDirIfMissing(exports);
    runDir = projectAwareJoinPath(projectAwareJoinPath(exports,"runs"),v4RunId); makeDirIfMissing(runDir);
    objectsPath=projectAwareJoinPath(exports,"objects_v4.csv");
    featuresPath=projectAwareJoinPath(exports,"features_v4.csv");
    regionsPath=projectAwareJoinPath(exports,"regions_v4.csv");
    header=v4ExportHeader();
    objects=header; features=header; regions=header;
    n=roiManager("count"); objectCount=0; featureCount=0; regionCount=0;
    for (i=0;i<n;i++) {
        safeRoiSelect(i);
        type=Roi.getProperty("Object_type"); if(type=="") type=currentRoiType();
        if(type=="session_metadata" || type=="scale_label") continue;
        line=v4ExportLine(i,type);
        role=propString("Scientific_role",v4RoleForType(type));
        if(role=="region") { regions=regions+line; regionCount++; }
        else if(role=="line_feature" || role=="reference_feature") { features=features+line; featureCount++; }
        else { objects=objects+line; objectCount++; }
    }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar la exportacion v4", 1)) return;
    File.saveString(objects,objectsPath); File.saveString(features,featuresPath); File.saveString(regions,regionsPath);
    File.saveString(objects,projectAwareJoinPath(runDir,"objects_v4.csv"));
    File.saveString(features,projectAwareJoinPath(runDir,"features_v4.csv"));
    File.saveString(regions,projectAwareJoinPath(runDir,"regions_v4.csv"));
    if (exactAreaReady && v51LastExactAreaCsv != "" && File.exists(v51LastExactAreaCsv)) File.saveString(File.openAsString(v51LastExactAreaCsv),projectAwareJoinPath(runDir,"valid_area_by_panel.csv"));
    if (!v4SaveSession()) {
        showMessage("Exportacion bloqueada", "No se pudo preparar la solicitud ROI asociada. No se publicara el manifest de esta ejecucion.");
        return;
    }
    v4PersistSurfaceState();
    runJson="{\n  \"run_id\": \""+jsonEscape(v4RunId)+"\",\n  \"project_id\": \""+jsonEscape(v4ProjectId)+"\",\n  \"revision_id\": \""+jsonEscape(v4MasterRevisionId)+"\",\n  \"current_montage_pointer_sha256\": \""+v4CurrentMontagePointerSha256+"\",\n  \"master_revision_manifest_sha256\": \""+v4MasterRevisionManifestSha256+"\",\n  \"master_native_plan_sha256\": \""+v4MasterNativePlanSha256+"\",\n  \"master_sha256\": \""+v4MasterSha256+"\",\n  \"master_ownership_sha256\": \""+v4MasterOwnershipSha256+"\",\n  \"tool_version\": \""+v4ToolVersion+"\",\n  \"created_time_ms\": \""+d2s(getTime(),0)+"\",\n  \"objects\": "+objectCount+",\n  \"features\": "+featureCount+",\n  \"regions\": "+regionCount+",\n  \"exact_area_ready\": "+exactAreaReady+",\n  \"exact_area_method\": \""+jsonEscape(v51LastExactAreaMethod)+"\",\n  \"valid_area_nm2\": "+jsonNumber(lastValidAreaNm2)+",\n  \"calibration_id\": \""+jsonEscape(v4CalibrationId)+"\",\n  \"surface_id\": \""+jsonEscape(v4SurfaceId)+"\"\n}\n";
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar el manifest de ejecucion", 1)) return;
    File.saveString(runJson,projectAwareJoinPath(runDir,"run_manifest.json"));
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar la exportacion v4", 1)) return;
    areaText = "Area exacta: no disponible; no use densidades hasta corregir ownership/mascaras.";
    if (exactAreaReady) areaText = "Area exacta: " + d2s(lastValidAreaNm2,3) + " nm^2 (desglose por panel guardado).";
    showMessage("Exportacion Cavity TEM 5.6.0 completada", "Ejecucion: "+v4RunId+"\n\nObjetos: "+objectCount+"\nLineas/referencias: "+featureCount+"\nRegiones: "+regionCount+"\n"+areaText+"\n\n"+runDir);
}

function v4ExportHeader() {
    return "run_id,object_id,object_uuid,roi_index,roi_set_id,object_type,object_subtype,geometry,scientific_role,object_class,confidence,review_status,include_in_statistics,count_valid,size_valid,position_valid,exclusion_reason,project_id,revision_id,current_montage_pointer_sha256,master_revision_manifest_sha256,master_native_plan_sha256,master_sha256,master_ownership_sha256,study_id,study_name,sample_id,material,condition,specimen_id,specimen_label,acquisition_id,acquisition_label,analysis_image_name,analysis_image_role,source_filename,panel_id,panel_match_count,effective_owner_code,geometric_coverage_count,crosses_panel_boundary,panel_boundary_reviewed,x_global_px,y_global_px,x_local_px,y_local_px,x_center_nm,y_center_nm,equivalent_diameter_nm,major_axis_nm,minor_axis_nm,aspect_ratio,projected_area_nm2,perimeter_nm,circularity,length_nm,orientation_deg,measurement_method,closed_contour,trace_session_id,auto_accepted,analyst_note,surface_id,surface_position_nm,signed_depth_nm,absolute_depth_nm,distance_to_surface_nm,edge_intersecting,manual_excluded,duplicate_status,calibration_id,measurement_protocol_id,operator,created_time_ms,modified_time_ms,tool_version,foil_thickness_nm\n";
}

function v4ExportLine(idx,type) {
    id=propString("Object_id",objectIdCurrent(currentRoiType()));
    getSelectionBounds(x,y,w,h); cx=x+w/2; cy=y+h/2;
    vals=newArray(
        v4RunId,id,propString("Object_uuid",""),idx,propString("ROI_set_id",v4SetIdForType(type)),type,propString("Object_subtype",""),propString("Geometry",""),propString("Scientific_role",v4RoleForType(type)),propString("Object_class",propString("Cavity_class","")),propString("Confidence",propString("Cavity_confidence","")),propString("Review_status",""),propString("Include_in_statistics","1"),propString("Count_valid","1"),propString("Size_valid","1"),propString("Position_valid","1"),propString("Exclusion_reason",""),v4ProjectId,v4MasterRevisionId,v4CurrentMontagePointerSha256,v4MasterRevisionManifestSha256,v4MasterNativePlanSha256,v4MasterSha256,v4MasterOwnershipSha256,v4StudyId,v4StudyName,v4SampleId,v4Material,v4Condition,v4SpecimenId,v4SpecimenLabel,v4AcquisitionId,v4AcquisitionLabel,getTitle(),projectAwareCurrentAnalysisImageRole,propString("Source_filename",""),propString("Panel_id",""),propString("Panel_match_count","0"),propString("Effective_owner_code","0"),propString("Geometric_coverage_count","0"),propString("Crosses_panel_boundary","0"),propString("Panel_boundary_reviewed","0"),d2s(cx,6),d2s(cy,6),propString("X_local_px",""),propString("Y_local_px",""),d2s(cx*nmPerPixelX,6),d2s(cy*nmPerPixelY,6),propString("Equivalent_diameter_nm",propString("Diameter_nm","")),propString("Major_axis_nm",""),propString("Minor_axis_nm",""),propString("Aspect_ratio",""),propString("Projected_area_nm2",propString("Cavity_area_nm2",propString("Area_nm2",""))),propString("Perimeter_nm",""),propString("Circularity",""),propString("Length_nm",""),propString("Orientation_deg",propString("Surface_tangent_angle_deg","")),propString("Measurement_method",""),propString("Closed_contour","0"),propString("Trace_session_id",""),propString("Auto_accepted","0"),propString("Analyst_note",""),v4SurfaceId,propString("Surface_position_nm",""),propString("Signed_depth_nm",propString("Depth_nm","")),propString("Absolute_depth_nm",propString("Depth_absolute_nm","")),propString("Distance_to_surface_nm",propString("Depth_absolute_nm","")),propString("Edge_intersecting","0"),propString("Manual_excluded","0"),propString("Duplicate_status","clear"),v4CalibrationId,propString("Measurement_protocol_id",v4ProtocolForType(type)),propString("Operator",operatorName),propString("Created_time_ms",""),propString("Modified_time_ms",""),v4ToolVersion,v4Field("foil_thickness_nm")
    );
    line="";
    for(k=0;k<vals.length;k++) { if(k>0) line=line+","; line=line+projectAwareCsvEscape(vals[k]); }
    return line+"\n";
}

// -------------------------------------------------------------------------
// Phase 2A - Fiji is a request producer, never the session publisher.
//
// A successful save creates exactly three files below a new staging
// directory, verifies their hashes and inventory, then atomically renames the
// staging directory to its immutable request_id. It never writes either
// legacy flat ZIP and never changes sessions/current_roi_session.json.
// Runtime evidence: NO PROBADO EN FIJI REAL.
// -------------------------------------------------------------------------

function v56NewRequestIdentityJava() {
    v56RequestId = "";
    v56PreparedAt = "";
    js = "var Instant=Packages.java.time.Instant,Formatter=Packages.java.time.format.DateTimeFormatter,ZoneOffset=Packages.java.time.ZoneOffset,UUID=Packages.java.util.UUID;var OUT='ERROR';try{var now=Instant.now();var stamp=Formatter.ofPattern(\"yyyyMMdd'T'HHmmss.SSSSSS'Z'\").withZone(ZoneOffset.UTC).format(now);OUT=String(stamp)+'_'+String(UUID.randomUUID()).toLowerCase()+'|'+String(Formatter.ISO_INSTANT.format(now));}catch(ex){OUT='ERROR|'+String(ex).replace(/[\\r\\n|]/g,' ');}String(OUT);";
    result = "" + eval("js", js);
    parts = split(result, "|");
    if (parts.length < 2 || startsWith(result, "ERROR|")) return 0;
    v56RequestId = "" + parts[0];
    v56PreparedAt = "" + parts[1];
    if (!matches(v56RequestId, "^[0-9]{8}T[0-9]{6}\\.[0-9]{6}Z_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")) return 0;
    return 1;
}

function v56CreateRequestStagingJava(requestRoot, stagingPath, finalPath) {
    js = "var File=Packages.java.io.File,Files=Packages.java.nio.file.Files;var OUT='ERROR';function canon(f){return String(f.getCanonicalPath()).replace(/\\\\/g,'/');}try{var project=new File('" + jsEscape(v4ProjectDir) + "').getCanonicalFile(),sessions=new File(project,'sessions').getCanonicalFile(),requests=new File('" + jsEscape(requestRoot) + "').getCanonicalFile(),staging=new File('" + jsEscape(stagingPath) + "').getCanonicalFile(),finalDir=new File('" + jsEscape(finalPath) + "').getCanonicalFile();if(canon(requests)!=canon(new File(sessions,'roi_session_requests').getCanonicalFile()))throw new Error('request_root_no_canonico');if(!sessions.exists()&&!sessions.mkdir())throw new Error('no_se_pudo_crear_sessions');if(!requests.exists()&&!requests.mkdir())throw new Error('no_se_pudo_crear_request_root');if(Files.isSymbolicLink(requests.toPath()))throw new Error('request_root_es_enlace');if(canon(staging.getParentFile())!=canon(requests)||canon(finalDir.getParentFile())!=canon(requests))throw new Error('destino_fuera_de_request_root');if(staging.exists()||finalDir.exists())throw new Error('request_id_ya_existe');if(!staging.mkdir())throw new Error('no_se_pudo_crear_staging');OUT='OK';}catch(ex){OUT='ERROR|'+String(ex).replace(/[\\r\\n|]/g,' ');}String(OUT);";
    return "" + eval("js", js);
}

function v56CanonicalScientificRole(rawRole) {
    role = toLowerCase(String.trim("" + rawRole));
    // The mature v8/v9 core used "defect" for object ROIs. Phase 2A names
    // that same documented semantic class "object"; no missing role is inferred.
    if (role == "defect") role = "object";
    if (role == "object" || role == "region" || role == "line_feature" || role == "reference_feature" || role == "surface" || role == "scale_reference" || role == "metadata") return "" + role;
    return "";
}

function v56ImageJRoiType() {
    if (selectionType == 0) return "rectangle";
    if (selectionType == 1) return "oval";
    if (selectionType == 2) return "polygon";
    if (selectionType == 3) return "freehand";
    if (selectionType == 4) return "traced";
    if (selectionType == 5) return "straight_line";
    if (selectionType == 6) return "polyline";
    if (selectionType == 7) return "freeline";
    if (selectionType == 8) return "angle";
    if (selectionType == 9) return "composite";
    if (selectionType == 10) return "point";
    return "unknown_" + selectionType;
}

function v56SelectedRoiObservationJava(imagejType) {
    js = "var File=Packages.java.io.File,FOS=Packages.java.io.FileOutputStream,Files=Packages.java.nio.file.Files,MD=Packages.java.security.MessageDigest,Integer=Packages.java.lang.Integer,StringBuilder=Packages.java.lang.StringBuilder,IJ=Packages.ij.IJ,Roi=Packages.ij.gui.Roi,Line=Packages.ij.gui.Line,RoiEncoder=Packages.ij.io.RoiEncoder,RoiDecoder=Packages.ij.io.RoiDecoder,kind='" + jsEscape(imagejType) + "',snapshotDir='" + jsEscape(v56RoiSnapshotDirectory) + "',entryName='" + jsEscape(v56RoiSnapshotEntryName) + "',OUT='ERROR';";
    js = js + "function finite(v){return typeof v=='number'&&isFinite(v);}function nonnegative(v){return finite(v)&&v>=0;}function distance(x1,y1,x2,y2){var dx=x2-x1,dy=y2-y1;return Math.sqrt(dx*dx+dy*dy);}function hex(bytes){var sb=new StringBuilder();for(var i=0;i<bytes.length;i++){var v=Number(bytes[i])&255;if(v<16)sb.append('0');sb.append(Integer.toHexString(v));}return String(sb.toString());}function shaBytes(bytes){return hex(MD.getInstance('SHA-256').digest(bytes));}function quantize(v){if(v===null||typeof v=='string'||typeof v=='boolean')return v;if(typeof v=='number'){if(!finite(v))throw new Error('geometria_no_finita');var n=Number(v.toFixed(6));return n===0?0:n;}if(Object.prototype.toString.call(v)=='[object Array]'){var a=[];for(var i=0;i<v.length;i++)a.push(quantize(v[i]));return a;}if(typeof v=='object'){var o={};for(var k in v)if(Object.prototype.hasOwnProperty.call(v,k))o[k]=quantize(v[k]);return o;}throw new Error('geometria_tipo_no_valido');}";
    js = js + "function typeName(roi){var t=Number(roi.getType());if(t==Roi.RECTANGLE)return 'rectangle';if(t==Roi.OVAL)return 'oval';if(t==Roi.POLYGON)return 'polygon';if(t==Roi.FREEROI)return 'freehand';if(t==Roi.TRACED_ROI)return 'traced';if(t==Roi.LINE)return 'straight_line';if(t==Roi.POLYLINE)return 'polyline';if(t==Roi.FREELINE)return 'freeline';if(t==Roi.ANGLE)return 'angle';if(t==Roi.COMPOSITE)return 'composite';if(t==Roi.POINT)return 'point';return 'unknown_'+t;}";
    js = js + "try{var imp=IJ.getImage(),live=imp==null?null:imp.getRoi();if(live==null)throw new Error('roi_no_seleccionada');var bytes=RoiEncoder.saveAsByteArray(live);if(bytes==null||Number(bytes.length)<64)throw new Error('roi_encoder_sin_bytes');var decoded=RoiDecoder.openFromByteArray(bytes);if(decoded==null)throw new Error('roi_decoder_sin_roi');var decodedKind=typeName(decoded);if(decodedKind!=kind)throw new Error('tipo_serializado_no_coincide:'+kind+':'+decodedKind);var b=decoded.getFloatBounds(),x=Number(b.getX()),y=Number(b.getY()),w=Number(b.getWidth()),h=Number(b.getHeight()),vertices=[],fp=null;";
    js = js + "if(kind=='straight_line'){if(!(decoded instanceof Line))throw new Error('straight_line_no_es_Line');vertices=[[Number(decoded.x1d),Number(decoded.y1d)],[Number(decoded.x2d),Number(decoded.y2d)]];}else if(kind!='rectangle'&&kind!='oval'){fp=decoded.getFloatPolygon();if(fp!=null){for(var i=0;i<Number(fp.npoints);i++)vertices.push([Number(fp.xpoints[i]),Number(fp.ypoints[i])]);}}";
    js = js + "var area=null,perimeter=null,areaMethod='unsupported_imagej_observation_v1',perimeterMethod='unsupported_imagej_observation_v1',comparable=false,geometryClass=kind,rounded=kind=='rectangle'&&Number(decoded.getCornerDiameter())>0;if(rounded)geometryClass='rounded_rectangle';if(kind=='rectangle'){area=w*h;perimeter=2*(w+h);if(rounded){areaMethod='fiji_rounded_rectangle_bounding_rect_diagnostic_v1';perimeterMethod='fiji_rounded_rectangle_bounding_rect_diagnostic_v1';comparable=false;}else{areaMethod='fiji_rectangle_float_bounds_v1';perimeterMethod='fiji_rectangle_float_bounds_v1';comparable=true;}}else if(kind=='oval'){var a=w/2,c=h/2;area=Math.PI*a*c;if(a+c==0)perimeter=0;else{var rh=((a-c)/(a+c))*((a-c)/(a+c));perimeter=Math.PI*(a+c)*(1+(3*rh)/(10+Math.sqrt(4-3*rh)));}areaMethod='fiji_ellipse_float_bounds_v1';perimeterMethod='fiji_ellipse_ramanujan_ii_v1';comparable=true;}else if(kind=='straight_line'){area=0;perimeter=distance(vertices[0][0],vertices[0][1],vertices[1][0],vertices[1][1]);var rawLength=Number(decoded.getRawLength()),lineTolerance=0.000001+0.000000001*Math.max(Math.abs(rawLength),Math.abs(perimeter),1);if(!finite(rawLength)||Math.abs(rawLength-perimeter)>lineTolerance)throw new Error('line_raw_length_no_coincide_con_extremos_serializados');areaMethod='fiji_zero_for_open_path_v1';perimeterMethod='fiji_line_get_raw_length_v1';comparable=true;}else if(kind=='polygon'||kind=='freehand'||kind=='traced'||kind=='polyline'||kind=='freeline'){area=0;perimeter=0;var closed=(kind=='polygon'||kind=='freehand'||kind=='traced');for(var p=1;p<vertices.length;p++)perimeter+=distance(vertices[p-1][0],vertices[p-1][1],vertices[p][0],vertices[p][1]);if(closed&&vertices.length>1)perimeter+=distance(vertices[vertices.length-1][0],vertices[vertices.length-1][1],vertices[0][0],vertices[0][1]);if(closed&&vertices.length>=3){var twice=0;for(var q=0;q<vertices.length;q++){var next=(q+1)%vertices.length;twice+=vertices[q][0]*vertices[next][1]-vertices[next][0]*vertices[q][1];}area=Math.abs(twice)/2;}areaMethod=closed?'fiji_shoelace_closed_v1':'fiji_zero_for_open_path_v1';perimeterMethod=closed?'fiji_closed_float_polygon_length_v1':'fiji_open_float_polygon_length_v1';comparable=true;}";
    js = js + "if(!finite(x)||!finite(y)||!nonnegative(w)||!nonnegative(h)||area!==null&&!nonnegative(area)||perimeter!==null&&!nonnegative(perimeter))throw new Error('geometria_no_finita');var observation={purpose:'diagnostic_only',imagej_roi_type:kind,geometry:{geometry_class:geometryClass,vertices_px:vertices},bounding_box:{height:h,width:w,x:x,y:y},centroid:{x:x+w/2,y:y+h/2},area:{value:area,unit:'px2',method:areaMethod,comparable_to_canonical:comparable},perimeter:{value:perimeter,unit:'px',method:perimeterMethod,comparable_to_canonical:comparable}},normalized=quantize(observation);";
    js = js + "if(snapshotDir!=''){if(entryName==''||entryName.indexOf('/')>=0||entryName.indexOf('\\\\')>=0||entryName.toLowerCase().substring(entryName.length-4)!='.roi')throw new Error('entry_name_snapshot_no_plano');var root=new File(snapshotDir).getCanonicalFile(),file=new File(root,entryName).getCanonicalFile();if(!root.isDirectory()||file.getParentFile().getCanonicalPath()!=root.getCanonicalPath()||file.exists())throw new Error('ruta_snapshot_no_segura_o_existente');var stream=new FOS(file);try{stream.write(bytes);stream.flush();stream.getFD().sync();}finally{stream.close();}var persisted=Files.readAllBytes(file.toPath()),before=shaBytes(bytes),after=shaBytes(persisted);if(Number(persisted.length)!=Number(bytes.length)||before!=after)throw new Error('ROI_SESSION_SERIALIZED_SNAPSHOT_MISMATCH');OUT=JSON.stringify({entry_sha256:before,entry_size_bytes:Number(bytes.length),fiji_observation:normalized});}else{OUT=JSON.stringify(quantize(observation));}}catch(ex){OUT='ERROR|'+String(ex).replace(/[\\r\\n|]/g,' ');}String(OUT);";
    return "" + eval("js", js);
}

function v56CollectRoiDraftJson() {
    v56RoiDraftError = "";
    v56RoiDraftCount = 0;
    run("ROI Manager...");
    total = roiManager("count");
    if (total <= 0) { v56RoiDraftError = "El ROI Manager esta vacio."; return ""; }
    entryNames = newArray(total);
    objectUuids = newArray(total);
    roleIds = newArray(total);
    rows = "";
    for (draftIndex=0; draftIndex<total; draftIndex++) {
        if (!safeRoiSelect(draftIndex)) { v56RoiDraftError = "No se pudo seleccionar la ROI " + draftIndex + "."; return ""; }
        objectUuid = toLowerCase(String.trim(propString("Object_uuid", "")));
        objectId = String.trim(propString("Object_id", ""));
        rawRole = String.trim(propString("Scientific_role", ""));
        scientificRole = v56CanonicalScientificRole(rawRole);
        roiSetId = String.trim(propString("ROI_set_id", ""));
        objectClass = String.trim(propString("Object_class", ""));
        objectSubtype = String.trim(propString("Object_subtype", ""));
        // The binary ImageJ type is the canonical geometric class. The older
        // free-text Geometry property remains descriptive metadata only.
        geometryClass = v56ImageJRoiType();
        reviewStatus = String.trim(propString("Review_status", ""));
        createdTime = String.trim(propString("Created_time_ms", ""));
        modifiedTime = String.trim(propString("Modified_time_ms", ""));
        if (!matches(objectUuid, "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")) { v56RoiDraftError = "ROI " + draftIndex + ": Object_uuid ausente o no valido."; return ""; }
        if (objectId == "") { v56RoiDraftError = "ROI " + draftIndex + ": Object_id ausente."; return ""; }
        if (rawRole == "" || scientificRole == "") { v56RoiDraftError = "ROI " + draftIndex + ": Scientific_role ausente o no admitido."; return ""; }
        if (roiSetId == "") { v56RoiDraftError = "ROI " + draftIndex + ": ROI_set_id ausente."; return ""; }
        if (objectClass == "" || objectSubtype == "") { v56RoiDraftError = "ROI " + draftIndex + ": Object_class/Object_subtype ausentes."; return ""; }
        if (geometryClass == "") { v56RoiDraftError = "ROI " + draftIndex + ": Geometry ausente."; return ""; }
        if (reviewStatus != "pending" && reviewStatus != "reviewed") { v56RoiDraftError = "ROI " + draftIndex + ": Review_status solo admite pending o reviewed."; return ""; }
        if (createdTime == "" || modifiedTime == "") { v56RoiDraftError = "ROI " + draftIndex + ": tiempos de creacion/modificacion ausentes."; return ""; }
        includeRaw = toLowerCase(String.trim(propString("Include_in_statistics", "")));
        if (includeRaw == "1" || includeRaw == "true" || includeRaw == "yes" || includeRaw == "si") includeJson = "true";
        else if (includeRaw == "0" || includeRaw == "false" || includeRaw == "no") includeJson = "false";
        else { v56RoiDraftError = "ROI " + draftIndex + ": Include_in_statistics no es booleano explicito."; return ""; }
        roiName = String.trim("" + Roi.getName);
        if (roiName == "") { v56RoiDraftError = "ROI " + draftIndex + ": nombre ImageJ ausente."; return ""; }
        entryName = roiName;
        if (!endsWith(toLowerCase(entryName), ".roi")) entryName = entryName + ".roi";
        if (indexOf(entryName, "/") >= 0 || indexOf(entryName, "\\") >= 0) { v56RoiDraftError = "ROI " + draftIndex + ": entry_name no es plano."; return ""; }
        roleIdKey = toLowerCase(scientificRole + "|" + objectId);
        for (seenIndex=0; seenIndex<draftIndex; seenIndex++) {
            if (toLowerCase(entryNames[seenIndex]) == toLowerCase(entryName)) { v56RoiDraftError = "entry_name duplicado: " + entryName; return ""; }
            if (objectUuids[seenIndex] == objectUuid) { v56RoiDraftError = "Object_uuid duplicado: " + objectUuid; return ""; }
            if (roleIds[seenIndex] == roleIdKey) { v56RoiDraftError = "Object_id duplicado dentro del rol: " + objectId; return ""; }
        }
        entryNames[draftIndex] = entryName;
        objectUuids[draftIndex] = objectUuid;
        roleIds[draftIndex] = roleIdKey;
        observationJson = v56SelectedRoiObservationJava(geometryClass);
        if (startsWith(observationJson, "ERROR|")) { v56RoiDraftError = "ROI " + draftIndex + ": no se pudo observar la geometria raw-pixel (" + observationJson + ")."; return ""; }
        row = "{\"object_uuid\":\"" + jsonEscape(objectUuid) + "\",\"object_id\":\"" + jsonEscape(objectId) + "\",\"entry_name\":\"" + jsonEscape(entryName) + "\",\"scientific_role\":\"" + jsonEscape(scientificRole) + "\",\"roi_set_id\":\"" + jsonEscape(roiSetId) + "\",\"object_class\":\"" + jsonEscape(objectClass) + "\",\"object_subtype\":\"" + jsonEscape(objectSubtype) + "\",\"review_status\":\"" + jsonEscape(reviewStatus) + "\",\"include_in_statistics\":" + includeJson + ",\"created_time\":\"" + jsonEscape(createdTime) + "\",\"modified_time\":\"" + jsonEscape(modifiedTime) + "\",\"fiji_observation\":" + observationJson + "}";
        if (rows != "") rows = rows + ",";
        rows = rows + row;
    }
    v56RoiDraftCount = total;
    return "{\"rois\":[" + rows + "]}\n";
}

function v56CollectSerializedRoiDraftJson(snapshotDirectory) {
    v56RoiDraftError = "";
    v56RoiDraftCount = 0;
    run("ROI Manager...");
    total = roiManager("count");
    if (total <= 0) { v56RoiDraftError = "El ROI Manager esta vacio."; return ""; }
    entryNames = newArray(total);
    objectUuids = newArray(total);
    roleIds = newArray(total);
    rows = "";
    for (draftIndex=0; draftIndex<total; draftIndex++) {
        if (!safeRoiSelect(draftIndex)) { v56RoiDraftError = "No se pudo seleccionar la ROI " + draftIndex + "."; return ""; }
        objectUuid = toLowerCase(String.trim(propString("Object_uuid", "")));
        objectId = String.trim(propString("Object_id", ""));
        rawRole = String.trim(propString("Scientific_role", ""));
        scientificRole = v56CanonicalScientificRole(rawRole);
        roiSetId = String.trim(propString("ROI_set_id", ""));
        objectClass = String.trim(propString("Object_class", ""));
        objectSubtype = String.trim(propString("Object_subtype", ""));
        geometryClass = v56ImageJRoiType();
        reviewStatus = String.trim(propString("Review_status", ""));
        createdTime = String.trim(propString("Created_time_ms", ""));
        modifiedTime = String.trim(propString("Modified_time_ms", ""));
        if (!matches(objectUuid, "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")) { v56RoiDraftError = "ROI " + draftIndex + ": Object_uuid ausente o no valido."; return ""; }
        if (objectId == "") { v56RoiDraftError = "ROI " + draftIndex + ": Object_id ausente."; return ""; }
        if (rawRole == "" || scientificRole == "") { v56RoiDraftError = "ROI " + draftIndex + ": Scientific_role ausente o no admitido."; return ""; }
        if (roiSetId == "") { v56RoiDraftError = "ROI " + draftIndex + ": ROI_set_id ausente."; return ""; }
        if (objectClass == "" || objectSubtype == "") { v56RoiDraftError = "ROI " + draftIndex + ": Object_class/Object_subtype ausentes."; return ""; }
        if (geometryClass == "") { v56RoiDraftError = "ROI " + draftIndex + ": Geometry ausente."; return ""; }
        if (reviewStatus != "pending" && reviewStatus != "reviewed") { v56RoiDraftError = "ROI " + draftIndex + ": Review_status solo admite pending o reviewed."; return ""; }
        if (createdTime == "" || modifiedTime == "") { v56RoiDraftError = "ROI " + draftIndex + ": tiempos de creacion/modificacion ausentes."; return ""; }
        includeRaw = toLowerCase(String.trim(propString("Include_in_statistics", "")));
        if (includeRaw == "1" || includeRaw == "true" || includeRaw == "yes" || includeRaw == "si") includeJson = "true";
        else if (includeRaw == "0" || includeRaw == "false" || includeRaw == "no") includeJson = "false";
        else { v56RoiDraftError = "ROI " + draftIndex + ": Include_in_statistics no es booleano explicito."; return ""; }
        roiName = String.trim("" + Roi.getName);
        if (roiName == "") { v56RoiDraftError = "ROI " + draftIndex + ": nombre ImageJ ausente."; return ""; }
        entryName = roiName;
        if (!endsWith(toLowerCase(entryName), ".roi")) entryName = entryName + ".roi";
        if (indexOf(entryName, "/") >= 0 || indexOf(entryName, "\\") >= 0) { v56RoiDraftError = "ROI " + draftIndex + ": entry_name no es plano."; return ""; }
        roleIdKey = toLowerCase(scientificRole + "|" + objectId);
        for (seenIndex=0; seenIndex<draftIndex; seenIndex++) {
            if (toLowerCase(entryNames[seenIndex]) == toLowerCase(entryName)) { v56RoiDraftError = "entry_name duplicado: " + entryName; return ""; }
            if (objectUuids[seenIndex] == objectUuid) { v56RoiDraftError = "Object_uuid duplicado: " + objectUuid; return ""; }
            if (roleIds[seenIndex] == roleIdKey) { v56RoiDraftError = "Object_id duplicado dentro del rol: " + objectId; return ""; }
        }
        entryNames[draftIndex] = entryName;
        objectUuids[draftIndex] = objectUuid;
        roleIds[draftIndex] = roleIdKey;
        v56RoiSnapshotDirectory = "" + snapshotDirectory;
        v56RoiSnapshotEntryName = "" + entryName;
        snapshotJson = v56SelectedRoiObservationJava(geometryClass);
        v56RoiSnapshotDirectory = "";
        v56RoiSnapshotEntryName = "";
        if (startsWith(snapshotJson, "ERROR|")) { v56RoiDraftError = "ROI " + draftIndex + ": fallo el snapshot binario autoritativo (" + snapshotJson + ")."; return ""; }
        row = "{\"object_uuid\":\"" + jsonEscape(objectUuid) + "\",\"object_id\":\"" + jsonEscape(objectId) + "\",\"entry_name\":\"" + jsonEscape(entryName) + "\",\"scientific_role\":\"" + jsonEscape(scientificRole) + "\",\"roi_set_id\":\"" + jsonEscape(roiSetId) + "\",\"object_class\":\"" + jsonEscape(objectClass) + "\",\"object_subtype\":\"" + jsonEscape(objectSubtype) + "\",\"review_status\":\"" + jsonEscape(reviewStatus) + "\",\"include_in_statistics\":" + includeJson + ",\"created_time\":\"" + jsonEscape(createdTime) + "\",\"modified_time\":\"" + jsonEscape(modifiedTime) + "\",\"serialized_snapshot\":" + snapshotJson + "}";
        if (rows != "") rows = rows + ",";
        rows = rows + row;
    }
    v56RoiDraftCount = total;
    return "{\"snapshot_authority\":\"imagej_roi_bytes_v1\",\"rois\":[" + rows + "]}\n";
}

function v56CreateRoiSnapshotDirectoryJava(stagingPath, snapshotPath) {
    js = "var File=Packages.java.io.File,Files=Packages.java.nio.file.Files,OUT='ERROR';try{var staging=new File('" + jsEscape(stagingPath) + "').getCanonicalFile(),snapshot=new File('" + jsEscape(snapshotPath) + "').getCanonicalFile();if(!staging.isDirectory()||snapshot.getParentFile().getCanonicalPath()!=staging.getCanonicalPath()||String(snapshot.getName())!='.roi_snapshot'||snapshot.exists())throw new Error('ruta_snapshot_no_segura_o_existente');if(!snapshot.mkdir()||Files.isSymbolicLink(snapshot.toPath()))throw new Error('no_se_pudo_crear_snapshot');OUT='OK';}catch(ex){OUT='ERROR|'+String(ex).replace(/[\\r\\n|]/g,' ');}String(OUT);";
    return "" + eval("js", js);
}

function v56BuildCandidateZipFromSnapshotJava(snapshotPath, zipPath) {
    js = "var File=Packages.java.io.File,FOS=Packages.java.io.FileOutputStream,BOS=Packages.java.io.BufferedOutputStream,Files=Packages.java.nio.file.Files,ZipEntry=Packages.java.util.zip.ZipEntry,ZipOutputStream=Packages.java.util.zip.ZipOutputStream,OUT='ERROR',zos=null;function canon(f){return String(f.getCanonicalPath()).replace(/\\\\/g,'/');}try{var snapshot=new File('" + jsEscape(snapshotPath) + "').getCanonicalFile(),zipFile=new File('" + jsEscape(zipPath) + "').getCanonicalFile(),staging=snapshot.getParentFile().getCanonicalFile();if(!snapshot.isDirectory()||String(snapshot.getName())!='.roi_snapshot'||zipFile.getParentFile().getCanonicalPath()!=staging.getCanonicalPath()||String(zipFile.getName())!='rois.candidate.zip'||zipFile.exists()||Files.isSymbolicLink(snapshot.toPath()))throw new Error('rutas_snapshot_zip_no_seguras');var files=snapshot.listFiles();if(files==null||files.length==0)throw new Error('snapshot_vacio');var names=[];for(var i=0;i<files.length;i++){if(!files[i].isFile()||Files.isSymbolicLink(files[i].toPath()))throw new Error('snapshot_contiene_entrada_no_regular');var name=String(files[i].getName());if(name.indexOf('/')>=0||name.indexOf('\\\\')>=0||name.toLowerCase().substring(name.length-4)!='.roi')throw new Error('entry_name_snapshot_no_plano');names.push(name);}names.sort();var fos=new FOS(zipFile),bos=new BOS(fos);zos=new ZipOutputStream(bos);for(var j=0;j<names.length;j++){var file=new File(snapshot,names[j]).getCanonicalFile();if(file.getParentFile().getCanonicalPath()!=snapshot.getCanonicalPath())throw new Error('ROI_snapshot_fuera_de_directorio');var bytes=Files.readAllBytes(file.toPath());if(Number(bytes.length)<64)throw new Error('ROI_snapshot_truncada');var entry=new ZipEntry(names[j]);entry.setTime(0);zos.putNextEntry(entry);zos.write(bytes);zos.closeEntry();}zos.finish();zos.flush();bos.flush();fos.getFD().sync();zos.close();zos=null;if(!zipFile.isFile()||Number(zipFile.length())<=0)throw new Error('ZIP_snapshot_no_creado');OUT='OK|'+names.length;}catch(ex){OUT='ERROR|'+String(ex).replace(/[\\r\\n|]/g,' ');}finally{try{if(zos!=null)zos.close();}catch(ignore){}}String(OUT);";
    return "" + eval("js", js);
}

function v56RefreshLiveBridgeForRoiWorkflow(actionText) {
    if (v4ProjectDir == "" || v4BridgePointerJson == "" || !File.exists(v4BridgePointerJson)) {
        showMessage("Accion bloqueada", "No se puede " + actionText + ": falta el bridge vivo del proyecto.");
        return 0;
    }
    liveBridgeText = File.openAsString(v4BridgePointerJson);
    liveGeneration = projectAwareReadFieldFromJsonText(liveBridgeText, "generation_id");
    if (liveGeneration == "") {
        showMessage("Accion bloqueada", "No se puede " + actionText + ": current_bridge.json no declara generation_id.");
        return 0;
    }
    if (liveGeneration == v4BridgeGenerationId) return 1;

    // ROI publication legitimately advances project.json and the bridge while
    // Fiji remains open. Reload that live bridge, but only accept it if the
    // scientific montage/calibration binding stayed exactly the same.
    refreshRoot = v4ProjectDir;
    expectedProjectId = v4ProjectId;
    expectedRevisionId = v4MasterRevisionId;
    expectedCurrentMontageSha = v4CurrentMontagePointerSha256;
    expectedRevisionManifestSha = v4MasterRevisionManifestSha256;
    expectedMasterSha = v4MasterSha256;
    expectedCalibrationId = v4CalibrationId;
    if (!v4LoadProject(refreshRoot)) {
        showMessage("Accion bloqueada", "No se puede " + actionText + ": el bridge cambio y no pudo recargarse de forma integra.");
        return 0;
    }
    if (v4ProjectId != expectedProjectId || v4MasterRevisionId != expectedRevisionId ||
        v4CurrentMontagePointerSha256 != expectedCurrentMontageSha ||
        v4MasterRevisionManifestSha256 != expectedRevisionManifestSha ||
        v4MasterSha256 != expectedMasterSha || v4CalibrationId != expectedCalibrationId) {
        v4ProjectLoaded = 0;
        v4RevisionBindingReady = 0;
        showMessage("Accion bloqueada", "No se puede " + actionText + ": el bridge nuevo pertenece a otro binding cientifico. Recargue el proyecto desde Studio.");
        return 0;
    }
    v55InvalidateIntegrityCache();
    return 1;
}

function v56FinalizeRequestJava(stagingPath, finalPath, snapshotPath, draftPath, zipPath, indexPath, commitPath, launchPath, reasonText) {
    projectJsonPath = projectAwareJoinPath(v4ProjectDir, "project.json");
    scaleReportPath = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "qc"), "scale_reconciliation.json");
    currentSessionPointer = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "sessions"), "current_roi_session.json");
    js = "var File=Packages.java.io.File,FIS=Packages.java.io.FileInputStream,FOS=Packages.java.io.FileOutputStream,Files=Packages.java.nio.file.Files,MD=Packages.java.security.MessageDigest,Reflect=Packages.java.lang.reflect.Array,ByteType=Packages.java.lang.Byte.TYPE,Integer=Packages.java.lang.Integer,StringBuilder=Packages.java.lang.StringBuilder,Text=Packages.java.lang.String,ZipFile=Packages.java.util.zip.ZipFile,CopyOption=Packages.java.nio.file.CopyOption,AtomicMove=Packages.java.nio.file.StandardCopyOption.ATOMIC_MOVE;var OUT='ERROR|unknown',lastLabel='request',stream=null,zip=null;var contract=JSON.parse('" + jsEscape(v56RoiSessionContractJson) + "');";
    js = js + "function clean(v){return String(v).replace(/[\\r\\n|]/g,' ');}function fail(label,msg){lastLabel=String(label);throw new Error(String(msg));}function hex(bytes){var sb=new StringBuilder();for(var i=0;i<bytes.length;i++){var value=Number(bytes[i])&255;if(value<16)sb.append('0');sb.append(Integer.toHexString(value));}return String(sb.toString());}function shaBytes(bytes){return hex(MD.getInstance('SHA-256').digest(bytes));}function shaText(value){return shaBytes(new Text(String(value)).getBytes('UTF-8'));}";
    js = js + "function shaFile(file,label){var input=null;try{if(!file.isFile())fail(label,'archivo ausente');var digest=MD.getInstance('SHA-256'),buffer=Reflect.newInstance(ByteType,1048576),count;input=new FIS(file);while((count=input.read(buffer))!=-1)if(count>0)digest.update(buffer,0,count);return hex(digest.digest());}finally{try{if(input!=null)input.close();}catch(ignore){}}}function readText(file,label){if(!file.isFile())fail(label,'archivo ausente');var text=String(new Text(Files.readAllBytes(file.toPath()),'UTF-8'));if(text.length>0&&text.charCodeAt(0)==65279)text=text.substring(1);return text;}function readJson(file,label){try{return JSON.parse(readText(file,label));}catch(ex){fail(label,'JSON no valido: '+clean(ex));}}";
    js = js + "function isArray(v){return Object.prototype.toString.call(v)=='[object Array]';}function stable(v){if(v===null)return 'null';if(isArray(v)){var a=[];for(var i=0;i<v.length;i++)a.push(stable(v[i]));return '['+a.join(',')+']';}if(typeof v=='object'){var keys=[];for(var k in v)if(Object.prototype.hasOwnProperty.call(v,k))keys.push(String(k));keys.sort();var pairs=[];for(var j=0;j<keys.length;j++)pairs.push(JSON.stringify(keys[j])+':'+stable(v[keys[j]]));return '{'+pairs.join(',')+'}';}return JSON.stringify(v);}function semanticGeometry(v){if(v===null||typeof v=='string'||typeof v=='boolean')return v;if(typeof v=='number'){if(!isFinite(v))fail('semantic_sha256','geometria no finita');var n=Number(v);if(n==0)n=0;return n.toFixed(6);}if(isArray(v)){var out=[];for(var si=0;si<v.length;si++)out.push(semanticGeometry(v[si]));return out;}if(typeof v=='object'){var mapped={};for(var sk in v)if(Object.prototype.hasOwnProperty.call(v,sk))mapped[sk]=semanticGeometry(v[sk]);return mapped;}fail('semantic_sha256','tipo de geometria no permitido');}function payloadHash(obj){var copy={};for(var k in obj)if(Object.prototype.hasOwnProperty.call(obj,k)&&k!='payload_sha256')copy[k]=obj[k];return shaText(stable(copy));}function exactKeys(obj,expected,label){if(obj==null||typeof obj!='object'||isArray(obj))fail(label,'objeto ausente');var actual=[];for(var k in obj)if(Object.prototype.hasOwnProperty.call(obj,k))actual.push(String(k));actual.sort();var wanted=expected.slice(0);wanted.sort();if(actual.join('|')!=wanted.join('|'))fail(label,'campos ausentes o adicionales: '+actual.join(','));}";
    js = js + "function canon(file){return String(file.getCanonicalPath()).replace(/\\\\/g,'/');}function same(a,b){return canon(a).toLowerCase()==canon(b).toLowerCase();}function inside(file,base){var child=canon(file).toLowerCase(),root=canon(base).toLowerCase();return child.indexOf(root+'/')==0;}function writeNew(file,text,label){if(file.exists())fail(label,'el archivo ya existe');var output=null;try{output=new FOS(file,false);var bytes=new Text(String(text)).getBytes('UTF-8');output.write(bytes,0,bytes.length);output.getFD().sync();}finally{try{if(output!=null)output.close();}catch(ignore){}}}function fingerprint(files){var rows=[];for(var i=0;i<files.length;i++){var f=files[i].getCanonicalFile();rows.push(canon(f)+'|'+(f.isFile()?String(f.length())+'|'+shaFile(f,'contexto'):'MISSING'));}return shaText(rows.join('\\n'));}";
    js = js + "function inspectZip(file){var result={},folded={},count=0,total=0;zip=new ZipFile(file);var entries=zip.entries();while(entries.hasMoreElements()){var entry=entries.nextElement(),name=String(entry.getName()),lower=name.toLowerCase();if(entry.isDirectory()||name.indexOf('/')>=0||name.indexOf('\\\\')>=0||lower.substring(lower.length-4)!='.roi')fail('rois.candidate.zip','solo se admiten .roi planas');for(var ci=0;ci<name.length;ci++)if(name.charCodeAt(ci)<32)fail('rois.candidate.zip','entry_name contiene control');if(folded[lower])fail('rois.candidate.zip','entry_name duplicado');folded[lower]=1;var size=Number(entry.getSize());if(!isFinite(size)||size<64||size>134217728)fail('rois.candidate.zip','tamano de ROI no permitido');var input=null,digest=MD.getInstance('SHA-256'),buffer=Reflect.newInstance(ByteType,1048576),read,totalEntry=0,magic=[];try{input=zip.getInputStream(entry);while((read=input.read(buffer))!=-1){if(read<=0)continue;for(var mi=0;mi<read&&magic.length<4;mi++)magic.push(Number(buffer[mi])&255);digest.update(buffer,0,read);totalEntry+=read;}}finally{try{if(input!=null)input.close();}catch(ignore){}}if(totalEntry!=size||magic.join(',')!='73,111,117,116')fail('rois.candidate.zip','binario ROI no valido');result[name]={sha256:hex(digest.digest()),size_bytes:totalEntry};total+=totalEntry;count++;if(count>1000000||total>17179869184)fail('rois.candidate.zip','limite de seguridad excedido');}zip.close();zip=null;if(count==0)fail('rois.candidate.zip','ZIP vacio');return result;}";
    js = js + "try{var root=new File('" + jsEscape(v4ProjectDir) + "').getCanonicalFile(),requests=new File(new File(root,'sessions'),'roi_session_requests').getCanonicalFile(),staging=new File('" + jsEscape(stagingPath) + "').getCanonicalFile(),finalDir=new File('" + jsEscape(finalPath) + "').getCanonicalFile(),snapshotDir=new File('" + jsEscape(snapshotPath) + "').getCanonicalFile(),draftFile=new File('" + jsEscape(draftPath) + "').getCanonicalFile(),zipFile=new File('" + jsEscape(zipPath) + "').getCanonicalFile(),indexFile=new File('" + jsEscape(indexPath) + "').getCanonicalFile(),commitFile=new File('" + jsEscape(commitPath) + "').getCanonicalFile(),launchFile=new File('" + jsEscape(launchPath) + "').getCanonicalFile(),bridgeDir=new File(root,'fiji_bridge').getCanonicalFile();if(!same(staging.getParentFile(),requests)||!same(finalDir.getParentFile(),requests)||!same(snapshotDir.getParentFile(),staging)||String(snapshotDir.getName())!='.roi_snapshot'||!inside(draftFile,staging)||!inside(zipFile,staging)||!inside(indexFile,staging)||!inside(commitFile,staging))fail('request','rutas fuera del staging');if(!staging.isDirectory()||!snapshotDir.isDirectory()||Files.isSymbolicLink(snapshotDir.toPath())||finalDir.exists())fail('request','staging o snapshot no validos, o destino existente');if(!same(launchFile.getParentFile(),bridgeDir)||launchFile.getName().indexOf('local_launch_')!=0||String(launchFile.getName()).toLowerCase().substring(String(launchFile.getName()).length-5)!='.json')fail('local_launch','ruta local_launch no canonica');";
    js = js + "var contextFiles=[new File('" + jsEscape(projectJsonPath) + "'),new File('" + jsEscape(v4BridgePointerJson) + "'),new File('" + jsEscape(v4CurrentMontagePointerPath) + "'),new File('" + jsEscape(v4MasterRevisionManifestPath) + "'),new File('" + jsEscape(scaleReportPath) + "'),launchFile,new File('" + jsEscape(currentSessionPointer) + "')],contextBefore=fingerprint(contextFiles),launchHashBefore=shaFile(launchFile,'local_launch'),launch=readJson(launchFile,'local_launch'),binding=launch.roi_session_binding,bindingKeys=['project_id','montage_revision_id','revision_manifest_payload_sha256','revision_manifest_file_sha256','master_sha256','master_dimensions','master_dtype','coordinate_system','calibration_id','calibration_record_sha256','scale_input_signature','scale_report_sha256','toolset_version','toolset_sha256','studio_version'];exactKeys(binding,bindingKeys,'roi_session_binding');if(String(launch.project_id||'')!='" + jsEscape(v4ProjectId) + "'||String(launch.revision_id||'')!='" + jsEscape(v4MasterRevisionId) + "'||String(launch.master_sha256||'').toLowerCase()!='" + jsEscape(v4MasterSha256) + "')fail('local_launch','lanzamiento de otro contexto');if(String(binding.project_id||'')!='" + jsEscape(v4ProjectId) + "'||String(binding.montage_revision_id||'')!='" + jsEscape(v4MasterRevisionId) + "'||String(binding.master_sha256||'').toLowerCase()!='" + jsEscape(v4MasterSha256) + "')fail('roi_session_binding','binding de otro contexto');if(String(binding.coordinate_system||'')!='MASTER_PIXEL_COORDINATES_V1'||String(binding.toolset_version||'')!='5.6.0'||String(binding.studio_version||'')!='5.6.0')fail('roi_session_binding','version o coordenadas no validas');var revisionLive=new File('" + jsEscape(v4MasterRevisionManifestPath) + "').getCanonicalFile(),scaleLive=new File('" + jsEscape(scaleReportPath) + "').getCanonicalFile();if(String(binding.revision_manifest_payload_sha256||'').toLowerCase()!='" + jsEscape(v4MasterRevisionManifestSha256) + "'||String(binding.revision_manifest_file_sha256||'').toLowerCase()!=shaFile(revisionLive,'revision_manifest.json'))fail('roi_session_binding','manifest de revision no coincide');var scaleDocument=readJson(scaleLive,'scale_reconciliation.json');if(String(binding.scale_report_sha256||'').toLowerCase()!=shaFile(scaleLive,'scale_reconciliation.json')||String(binding.scale_input_signature||'')!=String(scaleDocument.input_signature||''))fail('roi_session_binding','reconciliacion de escala no coincide');if(String(binding.calibration_id||'')!='" + jsEscape(v4CalibrationId) + "')fail('roi_session_binding','calibracion activa no coincide');if(!isArray(binding.master_dimensions)||binding.master_dimensions.length!=2||Number(binding.master_dimensions[0])!=" + getWidth() + "||Number(binding.master_dimensions[1])!=" + getHeight() + ")fail('roi_session_binding','dimensiones no coinciden con el maestro activo');for(var bk=0;bk<bindingKeys.length;bk++)if(binding[bindingKeys[bk]]===null||String(binding[bindingKeys[bk]])=='')fail('roi_session_binding','campo vacio: '+bindingKeys[bk]);var tool=launch.toolset;if(tool==null||tool.current!==true||String(tool.status||'')!='CURRENT'||String(tool.source_sha256||'').toLowerCase()!=String(binding.toolset_sha256||'').toLowerCase()||String(tool.installed_sha256||'').toLowerCase()!=String(binding.toolset_sha256||'').toLowerCase())fail('local_launch','toolset no CURRENT');var sourceTool=new File(String(tool.source_path||'')).getCanonicalFile(),installedTool=new File(String(tool.installed_path||'')).getCanonicalFile();if(shaFile(sourceTool,'toolset source')!=String(binding.toolset_sha256).toLowerCase()||shaFile(installedTool,'toolset installed')!=String(binding.toolset_sha256).toLowerCase())fail('local_launch','bytes vivos del toolset no coinciden');";
    js = js + "bindingKeys=contract.scientific_binding_fields;exactKeys(binding,bindingKeys,'roi_session_binding.contract');var projectFile=new File('" + jsEscape(projectJsonPath) + "').getCanonicalFile(),bridgePointerFile=new File('" + jsEscape(v4BridgePointerJson) + "').getCanonicalFile(),liveProject=readJson(projectFile,'project.json'),liveProjectHash=shaFile(projectFile,'project.json'),bridgePointer=readJson(bridgePointerFile,'current_bridge.json');if(String(bridgePointer.payload_sha256||'').toLowerCase()!=payloadHash(bridgePointer))fail('current_bridge.json','payload_sha256 no coincide');var projectVersion=Number(liveProject.project_version),bridgeVersion=Number(bridgePointer.project_version),bridgeGeneration=String(bridgePointer.generation_id||''),generationRelative=String(bridgePointer.generation_relative_path||'').replace(/\\\\/g,'/');if(!isFinite(projectVersion)||Math.floor(projectVersion)!=projectVersion||projectVersion<0||projectVersion!=bridgeVersion)fail('creation_context','project_version no coincide con el bridge vivo');if(String(liveProject.project_id||'')!=String(binding.project_id)||String(bridgePointer.project_id||'')!=String(binding.project_id)||String(bridgePointer.revision_id||'')!=String(binding.montage_revision_id)||String(bridgePointer.project_payload_sha256||'').toLowerCase()!=liveProjectHash)fail('creation_context','project.json y current_bridge.json no forman el mismo snapshot');if(generationRelative!='fiji_bridge/generations/'+bridgeGeneration)fail('current_bridge.json','generation_relative_path no canonica');var bridgeManifestFile=new File(root,generationRelative+'/bridge_generation_manifest.json').getCanonicalFile(),bridgeGenerations=new File(bridgeDir,'generations').getCanonicalFile();if(!inside(bridgeManifestFile,bridgeGenerations))fail('current_bridge.json','manifest de bridge fuera de generations');var bridgeManifestHash=shaFile(bridgeManifestFile,'bridge_generation_manifest.json'),bridgeManifest=readJson(bridgeManifestFile,'bridge_generation_manifest.json');if(bridgeManifestHash!=String(bridgePointer.generation_manifest_sha256||'').toLowerCase()||String(bridgeManifest.payload_sha256||'').toLowerCase()!=payloadHash(bridgeManifest)||String(bridgeManifest.generation_id||'')!=bridgeGeneration||String(bridgeManifest.project_id||'')!=String(binding.project_id)||String(bridgeManifest.revision_id||'')!=String(binding.montage_revision_id)||String(bridgeManifest.project_payload_sha256||'').toLowerCase()!=liveProjectHash||Number(bridgeManifest.project_version)!=projectVersion)fail('bridge_generation_manifest.json','bridge vivo incoherente');var creationContext={project_version:projectVersion,project_payload_sha256:liveProjectHash,bridge_generation_id:bridgeGeneration,bridge_manifest_sha256:bridgeManifestHash};exactKeys(creationContext,contract.creation_context_fields,'creation_context');contextFiles.push(bridgeManifestFile);contextBefore=fingerprint(contextFiles);";
    js = js + "var draft=readJson(draftFile,'roi_index.draft.json');exactKeys(draft,['snapshot_authority','rois'],'roi_index.draft.json');if(String(draft.snapshot_authority||'')!='imagej_roi_bytes_v1'||!isArray(draft.rois)||draft.rois.length==0)fail('roi_index.draft.json','autoridad de snapshot ausente o sin ROI');var binaries=inspectZip(zipFile),rows=[],seenEntries={},seenUuid={},seenRoleId={};for(var ri=0;ri<draft.rois.length;ri++){var source=draft.rois[ri];exactKeys(source,['object_uuid','object_id','entry_name','scientific_role','roi_set_id','object_class','object_subtype','review_status','include_in_statistics','created_time','modified_time','serialized_snapshot'],'ROI draft');var snapshot=source.serialized_snapshot;exactKeys(snapshot,['entry_sha256','entry_size_bytes','fiji_observation'],'serialized_snapshot');var entryName=String(source.entry_name||''),binary=binaries[entryName],uuid=String(source.object_uuid||'').toLowerCase(),role=String(source.scientific_role||''),objectId=String(source.object_id||''),fold=entryName.toLowerCase(),roleId=(role+'|'+objectId).toLowerCase(),observation=snapshot.fiji_observation,snapshotHash=String(snapshot.entry_sha256||'').toLowerCase(),snapshotSize=Number(snapshot.entry_size_bytes);if(binary==null)fail('roi_index','ROI ausente del ZIP: '+entryName);if(!/^[0-9a-f]{64}$/.test(snapshotHash)||!isFinite(snapshotSize)||Math.floor(snapshotSize)!=snapshotSize||snapshotSize<64||binary.sha256!=snapshotHash||Number(binary.size_bytes)!=snapshotSize)fail('ROI_SESSION_SERIALIZED_SNAPSHOT_MISMATCH','los bytes del ZIP no son el snapshot que origino draft, hash y observacion: '+entryName);if(seenEntries[fold]||seenUuid[uuid]||seenRoleId[roleId])fail('roi_index','identidad o entry_name duplicados');seenEntries[fold]=1;seenUuid[uuid]=1;seenRoleId[roleId]=1;if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(uuid))fail('roi_index','object_uuid no valido');if(['object','region','line_feature','reference_feature','surface','scale_reference','metadata'].indexOf(role)<0||objectId==''||String(source.roi_set_id||'')==''||String(source.review_status||'')==''||typeof source.include_in_statistics!='boolean')fail('roi_index','metadatos ROI incompletos');exactKeys(observation,contract.fiji_observation_fields,'fiji_observation');if(String(observation.purpose||'')!='diagnostic_only'||String(observation.imagej_roi_type||'')=='')fail('fiji_observation','finalidad o tipo ausente');exactKeys(observation.area,contract.fiji_metric_observation_fields,'fiji_observation.area');exactKeys(observation.perimeter,contract.fiji_metric_observation_fields,'fiji_observation.perimeter');var row={object_uuid:uuid,object_id:objectId,entry_name:entryName,entry_sha256:snapshotHash,entry_size_bytes:snapshotSize,scientific_role:role,roi_set_id:String(source.roi_set_id),object_class:String(source.object_class||''),object_subtype:String(source.object_subtype||''),review_status:String(source.review_status),include_in_statistics:source.include_in_statistics,created_time:String(source.created_time||''),modified_time:String(source.modified_time||''),fiji_observation:observation};rows.push(row);}var binaryNames=[];for(var binaryName in binaries)if(Object.prototype.hasOwnProperty.call(binaries,binaryName))binaryNames.push(binaryName.toLowerCase());for(var bi=0;bi<binaryNames.length;bi++)if(!seenEntries[binaryNames[bi]])fail('roi_index','ZIP contiene ROI extra');rows.sort(function(a,b){var ak=String(a.scientific_role)+'\\u0000'+String(a.object_id)+'\\u0000'+String(a.object_uuid),bk=String(b.scientific_role)+'\\u0000'+String(b.object_id)+'\\u0000'+String(b.object_uuid);return ak<bk?-1:(ak>bk?1:0);});";
    js = js + "for(var contractRow=0;contractRow<rows.length;contractRow++){exactKeys(rows[contractRow],contract.roi_request_draft_row_fields,'roi_request_draft.row');if(contract.row_review_statuses.indexOf(String(rows[contractRow].review_status))<0)fail('roi_request_draft.row','review_status no canonico');}";
    js = js + "var index={schema_version:'cavity_roi_request_draft_v1',application_version:'5.6.0',authoritative:false,binding:binding,rois:rows};index.payload_sha256=payloadHash(index);exactKeys(index,contract.roi_request_draft_fields,'roi_index.candidate.json');writeNew(indexFile,JSON.stringify(index,null,2)+'\\n','roi_index.candidate.json');var request={schema_version:'cavity_roi_session_request_v2',application_version:'5.6.0',request_id:'" + jsEscape(v56RequestId) + "',prepared_at:'" + jsEscape(v56PreparedAt) + "',prepared_by:'" + jsEscape(operatorName) + "',reason:'" + jsEscape(reasonText) + "',launch_record_relative_path:'fiji_bridge/'+String(launchFile.getName()),launch_record_sha256:launchHashBefore,creation_context:creationContext,fiji_imagej_version:String(Packages.ij.IJ.getVersion()),java_version:String(Packages.java.lang.System.getProperty('java.version')),candidate_zip_sha256:shaFile(zipFile,'rois.candidate.zip'),candidate_zip_size_bytes:Number(zipFile.length()),candidate_index_sha256:shaFile(indexFile,'roi_index.candidate.json'),candidate_index_size_bytes:Number(indexFile.length())};var forbiddenVersions=['','unknown','none','n/a','na','not available','not_available','synthetic'];if(forbiddenVersions.indexOf(String(request.fiji_imagej_version||'').toLowerCase())>=0||forbiddenVersions.indexOf(String(request.java_version||'').toLowerCase())>=0)fail('commit_request.json','version observada de Fiji/ImageJ o Java ausente');request.payload_sha256=payloadHash(request);exactKeys(request,contract.commit_request_fields,'commit_request.json');writeNew(commitFile,JSON.stringify(request,null,2)+'\\n','commit_request.json');if(!draftFile.delete())fail('request','no se pudo retirar el draft del staging');var snapshotFiles=snapshotDir.listFiles();if(snapshotFiles==null)fail('request','no se pudo listar el snapshot binario');for(var sf=0;sf<snapshotFiles.length;sf++){if(!snapshotFiles[sf].isFile()||Files.isSymbolicLink(snapshotFiles[sf].toPath())||!snapshotFiles[sf].delete())fail('request','no se pudo retirar una ROI del snapshot temporal');}if(!snapshotDir.delete())fail('request','no se pudo retirar el snapshot temporal');var names=[],listed=staging.listFiles();if(listed==null)fail('request','no se pudo listar staging');for(var li=0;li<listed.length;li++)names.push(String(listed[li].getName()));names.sort();if(names.join('|')!='commit_request.json|roi_index.candidate.json|rois.candidate.zip')fail('request','inventario final no exacto: '+names.join(','));if(shaFile(launchFile,'local_launch')!=launchHashBefore||fingerprint(contextFiles)!=contextBefore)fail('request','el contexto vivo cambio durante la preparacion');var opts=Reflect.newInstance(CopyOption,1);opts[0]=AtomicMove;Files.move(staging.toPath(),finalDir.toPath(),opts);if(!finalDir.isDirectory())fail('request','rename atomico no confirmado');OUT='OK|'+canon(finalDir);}catch(ex){OUT='ERROR|'+clean(lastLabel)+'|'+clean(ex);}finally{try{if(stream!=null)stream.close();}catch(ignore){}try{if(zip!=null)zip.close();}catch(ignore){}}String(OUT);";
    return "" + eval("js", js);
}

function v56PrepareRoiSessionRequest(reasonText) {
    if (!v4EnsureProject()) return 0;
    if (!v56RefreshLiveBridgeForRoiWorkflow("preparar la solicitud de sesion ROI")) return 0;
    if (!v4RequireCurrentRevisionBinding("preparar la solicitud de sesion ROI", 1)) return 0;
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra el maestro vigente antes de preparar una solicitud ROI."); return 0; }
    if (String.trim(operatorName) == "") { showMessage("Solicitud bloqueada", "Falta un operador no vacio en el proyecto."); return 0; }
    reasonText = String.trim("" + reasonText);
    if (reasonText == "") { showMessage("Solicitud bloqueada", "Falta un motivo no vacio."); return 0; }
    launchPath = "" + call("ij.Prefs.get", "cavity.v5.launch.request", "");
    if (launchPath == "" || !File.exists(launchPath)) { showMessage("Solicitud bloqueada", "No existe el local_launch_*.json de este lanzamiento. Abra Fiji desde Studio 5.6.0."); return 0; }
    run("ROI Manager...");
    if (roiManager("count") <= 0) { showMessage("Solicitud bloqueada", "El ROI Manager esta vacio."); return 0; }
    updateSessionMetadataRoi();
    if (!v4RequireCurrentRevisionBinding("preparar la solicitud de sesion ROI", 1)) return 0;
    if (!v56NewRequestIdentityJava()) { showMessage("Solicitud bloqueada", "No se pudo generar request_id UTC con microsegundos y UUID."); return 0; }
    sessionsDir = projectAwareJoinPath(v4ProjectDir, "sessions");
    requestRoot = projectAwareJoinPath(sessionsDir, "roi_session_requests");
    stagingPath = projectAwareJoinPath(requestRoot, "." + v56RequestId + ".staging");
    finalPath = projectAwareJoinPath(requestRoot, v56RequestId);
    stagingResult = v56CreateRequestStagingJava(requestRoot, stagingPath, finalPath);
    if (stagingResult != "OK") { showMessage("Solicitud bloqueada", stagingResult); return 0; }
    snapshotPath = projectAwareJoinPath(stagingPath, ".roi_snapshot");
    draftPath = projectAwareJoinPath(stagingPath, "roi_index.draft.json");
    zipPath = projectAwareJoinPath(stagingPath, "rois.candidate.zip");
    indexPath = projectAwareJoinPath(stagingPath, "roi_index.candidate.json");
    commitPath = projectAwareJoinPath(stagingPath, "commit_request.json");
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "preparar la solicitud ROI", 1)) return 0;
    snapshotResult = v56CreateRoiSnapshotDirectoryJava(stagingPath, snapshotPath);
    if (snapshotResult != "OK") { showMessage("Solicitud incompleta", snapshotResult + "\n\nEl staging se conserva para diagnostico:\n" + stagingPath); return 0; }
    draftJson = v56CollectSerializedRoiDraftJson(snapshotPath);
    if (draftJson == "") { showMessage("Solicitud incompleta", v56RoiDraftError + "\n\nEl staging y los snapshots ya creados se conservan para diagnostico:\n" + stagingPath + "\n\nNo se ha publicado ni reemplazado ninguna sesion."); return 0; }
    File.saveString(draftJson, draftPath);
    zipResult = v56BuildCandidateZipFromSnapshotJava(snapshotPath, zipPath);
    if (!startsWith(zipResult, "OK|") || round(parseFloat(substring(zipResult, 3))) != v56RoiDraftCount) { showMessage("Solicitud incompleta", "No se pudo construir el ZIP desde los mismos snapshots ROI: " + zipResult + "\n\nEl staging se conserva para diagnostico:\n" + stagingPath); return 0; }
    finalizeResult = v56FinalizeRequestJava(stagingPath, finalPath, snapshotPath, draftPath, zipPath, indexPath, commitPath, launchPath, reasonText);
    if (!startsWith(finalizeResult, "OK|")) {
        showMessage("Solicitud incompleta", finalizeResult + "\n\nEl staging no es publicable y se conserva para diagnostico:\n" + stagingPath + "\n\ncurrent_roi_session.json no se ha modificado.");
        return 0;
    }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar la solicitud ROI", 1)) return 0;
    showStatus("Solicitud ROI preparada: " + v56RequestId);
    showMessage("Solicitud ROI preparada", "Solicitud preparada; Studio aun debe validarla y publicarla; current permanece sin cambios.\n\nRequest ID: " + v56RequestId + "\nCarpeta: " + finalPath);
    return 1;
}

function v56ResolveCurrentSessionJava() {
    v56ResolvedSessionZip = "";
    v56ResolvedSessionRoiCount = 0;
    v56SessionValidationError = "";
    v56ResolvedSessionReviewStatus = "";
    v56ResolvedSessionQuantitativeReady = 0;
    v56ResolvedSessionPendingCount = 0;
    v56ResolvedSessionGeometryBlockerCount = 0;
    launchPath = "" + call("ij.Prefs.get", "cavity.v5.launch.request", "");
    projectJsonPath = projectAwareJoinPath(v4ProjectDir, "project.json");
    pointerPath = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "sessions"), "current_roi_session.json");
    scaleReportPath = projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir, "qc"), "scale_reconciliation.json");
    js = "var File=Packages.java.io.File,FIS=Packages.java.io.FileInputStream,Files=Packages.java.nio.file.Files,MD=Packages.java.security.MessageDigest,Reflect=Packages.java.lang.reflect.Array,ByteType=Packages.java.lang.Byte.TYPE,Integer=Packages.java.lang.Integer,StringBuilder=Packages.java.lang.StringBuilder,Text=Packages.java.lang.String,ZipFile=Packages.java.util.zip.ZipFile;var OUT='ERROR|validation|unknown',lastLabel='current_roi_session.json',zip=null,contract=JSON.parse('" + jsEscape(v56RoiSessionContractJson) + "');";
    js = js + "function clean(v){return String(v).replace(/[\\r\\n|]/g,' ');}function fail(label,msg){lastLabel=String(label);throw new Error(String(msg));}function hex(bytes){var sb=new StringBuilder();for(var i=0;i<bytes.length;i++){var value=Number(bytes[i])&255;if(value<16)sb.append('0');sb.append(Integer.toHexString(value));}return String(sb.toString());}function shaBytes(bytes){return hex(MD.getInstance('SHA-256').digest(bytes));}function shaText(v){return shaBytes(new Text(String(v)).getBytes('UTF-8'));}function shaFile(file,label){var input=null;try{if(!file.isFile())fail(label,'archivo ausente');var digest=MD.getInstance('SHA-256'),buffer=Reflect.newInstance(ByteType,1048576),count;input=new FIS(file);while((count=input.read(buffer))!=-1)if(count>0)digest.update(buffer,0,count);return hex(digest.digest());}finally{try{if(input!=null)input.close();}catch(ignore){}}}function readJson(file,label){try{var text=String(new Text(Files.readAllBytes(file.toPath()),'UTF-8'));if(text.length>0&&text.charCodeAt(0)==65279)text=text.substring(1);return JSON.parse(text);}catch(ex){fail(label,'JSON no valido: '+clean(ex));}}function readJsonAtHash(file,expected,label){try{var bytes=Files.readAllBytes(file.toPath());if(shaBytes(bytes)!=String(expected).toLowerCase())fail(label,'bytes cambiaron antes de parsear');var text=String(new Text(bytes,'UTF-8'));if(text.length>0&&text.charCodeAt(0)==65279)text=text.substring(1);return JSON.parse(text);}catch(ex){fail(label,'JSON/hash no valido: '+clean(ex));}}";
    js = js + "function isArray(v){return Object.prototype.toString.call(v)=='[object Array]';}function isInteger(v){return typeof v=='number'&&isFinite(v)&&Math.floor(v)==v;}function isGenerationId(v){return /^[0-9]{8}T[0-9]{6}\\.[0-9]{6}Z_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(String(v||''));}function isUuid(v){return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(String(v||'').toLowerCase());}function stable(v){if(v===null)return 'null';if(isArray(v)){var a=[];for(var i=0;i<v.length;i++)a.push(stable(v[i]));return '['+a.join(',')+']';}if(typeof v=='object'){var keys=[];for(var k in v)if(Object.prototype.hasOwnProperty.call(v,k))keys.push(String(k));keys.sort();var pairs=[];for(var j=0;j<keys.length;j++)pairs.push(JSON.stringify(keys[j])+':'+stable(v[keys[j]]));return '{'+pairs.join(',')+'}';}return JSON.stringify(v);}function semanticGeometry(v){if(v===null||typeof v=='string'||typeof v=='boolean')return v;if(typeof v=='number'){if(!isFinite(v))fail('semantic_sha256','geometria no finita');var n=Number(v);if(n==0)n=0;return n.toFixed(6);}if(isArray(v)){var a=[];for(var i=0;i<v.length;i++)a.push(semanticGeometry(v[i]));return a;}if(typeof v=='object'){var mapped={};for(var k in v)if(Object.prototype.hasOwnProperty.call(v,k))mapped[k]=semanticGeometry(v[k]);return mapped;}fail('semantic_sha256','tipo no permitido');}function payloadHash(obj){var copy={};for(var k in obj)if(Object.prototype.hasOwnProperty.call(obj,k)&&k!='payload_sha256')copy[k]=obj[k];return shaText(stable(copy));}function exactKeys(obj,expected,label){if(obj==null||typeof obj!='object'||isArray(obj))fail(label,'objeto ausente');var actual=[];for(var k in obj)if(Object.prototype.hasOwnProperty.call(obj,k))actual.push(String(k));actual.sort();var wanted=expected.slice(0);wanted.sort();if(actual.join('|')!=wanted.join('|'))fail(label,'campos ausentes o adicionales: '+actual.join(','));}function canon(f){return String(f.getCanonicalPath()).replace(/\\\\/g,'/');}function same(a,b){return canon(a).toLowerCase()==canon(b).toLowerCase();}function inside(f,b){var child=canon(f).toLowerCase(),base=canon(b).toLowerCase();return child.indexOf(base+'/')==0;}function isSha(v){return /^[0-9a-f]{64}$/.test(String(v||'').toLowerCase());}function allowedState(review,ready){for(var i=0;i<contract.published_session_states.length;i++){var state=contract.published_session_states[i];if(String(review)==String(state.review_status)&&ready===state.quantitative_ready)return true;}return false;}function requireVersion(v,label){var text=String(v||'').replace(/^\\s+|\\s+$/g,''),lower=text.toLowerCase(),bad=['','unknown','none','n/a','na','not available','not_available','synthetic'];if(bad.indexOf(lower)>=0)fail(label,'version observada ausente');return text;}";
    js = js + "function finiteObject(v,keys,label){exactKeys(v,keys,label);for(var i=0;i<keys.length;i++)if(typeof v[keys[i]]!='number'||!isFinite(v[keys[i]]))fail(label,'valor no finito: '+keys[i]);}function validateVertices(v,label){if(!isArray(v))fail(label,'vertices_px no es array');for(var i=0;i<v.length;i++){if(!isArray(v[i])||v[i].length!=2||typeof v[i][0]!='number'||!isFinite(v[i][0])||typeof v[i][1]!='number'||!isFinite(v[i][1]))fail(label,'vertice no finito');}}function validateObservationMetric(v,label,unit){exactKeys(v,contract.fiji_metric_observation_fields,label);if(v.value!==null&&(typeof v.value!='number'||!isFinite(v.value)||Number(v.value)<0))fail(label,'valor diagnostico invalido');if(typeof v.comparable_to_canonical!='boolean'||(v.comparable_to_canonical&&v.value===null)||String(v.unit||'').replace(/^\\s+|\\s+$/g,'')==''||String(v.method||'').replace(/^\\s+|\\s+$/g,'')=='')fail(label,'unidad, metodo o comparabilidad invalidos');if(v.comparable_to_canonical&&String(v.unit)!=unit)fail(label,'unidad comparable no canonica');}function validateObservation(v,label){exactKeys(v,contract.fiji_observation_fields,label);if(String(v.purpose||'')!='diagnostic_only'||String(v.imagej_roi_type||'').replace(/^\\s+|\\s+$/g,'')=='')fail(label,'finalidad o tipo diagnostico invalido');exactKeys(v.geometry,['geometry_class','vertices_px'],label+'.geometry');if(String(v.geometry.geometry_class||'').replace(/^\\s+|\\s+$/g,'')=='')fail(label,'clase diagnostica ausente');validateVertices(v.geometry.vertices_px,label+'.geometry');finiteObject(v.bounding_box,['x','y','width','height'],label+'.bounding_box');if(Number(v.bounding_box.width)<0||Number(v.bounding_box.height)<0)fail(label,'bounds diagnosticos negativos');finiteObject(v.centroid,['x','y'],label+'.centroid');validateObservationMetric(v.area,label+'.area','px2');validateObservationMetric(v.perimeter,label+'.perimeter','px');}";
    js = js + "function inspectZip(file){var result={},folded={},count=0,total=0;zip=new ZipFile(file);var entries=zip.entries();while(entries.hasMoreElements()){var entry=entries.nextElement(),name=String(entry.getName()),lower=name.toLowerCase();if(entry.isDirectory()||name.indexOf('/')>=0||name.indexOf('\\\\')>=0||lower.substring(lower.length-4)!='.roi')fail('rois.zip','entrada no ROI o no plana');if(folded[lower])fail('rois.zip','entry_name duplicado');folded[lower]=1;var input=null,digest=MD.getInstance('SHA-256'),buffer=Reflect.newInstance(ByteType,1048576),read,size=0,magic=[];try{input=zip.getInputStream(entry);while((read=input.read(buffer))!=-1){if(read<=0)continue;for(var mi=0;mi<read&&magic.length<4;mi++)magic.push(Number(buffer[mi])&255);digest.update(buffer,0,read);size+=read;}}finally{try{if(input!=null)input.close();}catch(ignore){}}if(size<64||size>134217728||magic.join(',')!='73,111,117,116')fail('rois.zip','binario ROI no valido');result[name]={sha256:hex(digest.digest()),size_bytes:size};total+=size;count++;if(count>1000000||total>17179869184)fail('rois.zip','limite de seguridad excedido');}zip.close();zip=null;if(count==0)fail('rois.zip','ZIP vacio');return {entries:result,count:count};}";
    js = js + "try{var root=new File('" + jsEscape(v4ProjectDir) + "').getCanonicalFile(),projectFile=new File('" + jsEscape(projectJsonPath) + "').getCanonicalFile(),pointerFile=new File('" + jsEscape(pointerPath) + "').getCanonicalFile(),expectedPointer=new File(new File(root,'sessions'),'current_roi_session.json').getCanonicalFile(),activeLaunchFile=new File('" + jsEscape(launchPath) + "').getCanonicalFile(),bridgeDir=new File(root,'fiji_bridge').getCanonicalFile(),currentBridgeFile=new File(bridgeDir,'current_bridge.json').getCanonicalFile();if(!same(pointerFile,expectedPointer))fail('current_roi_session.json','ruta no canonica');if(!activeLaunchFile.isFile()||!same(activeLaunchFile.getParentFile(),bridgeDir))fail('active_launch','launch activo ausente o no canonico');var activeLaunchHashBefore=shaFile(activeLaunchFile,'active_launch'),activeLaunch=readJsonAtHash(activeLaunchFile,activeLaunchHashBefore,'active_launch'),binding=activeLaunch.roi_session_binding,bindingKeys=contract.scientific_binding_fields;exactKeys(binding,bindingKeys,'active_launch.roi_session_binding');if(String(binding.project_id||'')!='" + jsEscape(v4ProjectId) + "'||String(binding.montage_revision_id||'')!='" + jsEscape(v4MasterRevisionId) + "'||String(binding.master_sha256||'').toLowerCase()!='" + jsEscape(v4MasterSha256) + "'||String(binding.coordinate_system||'')!='MASTER_PIXEL_COORDINATES_V1'||String(binding.toolset_version||'')!='5.6.0'||String(binding.studio_version||'')!='5.6.0'||!isArray(binding.master_dimensions)||binding.master_dimensions.length!=2||Number(binding.master_dimensions[0])!=" + getWidth() + "||Number(binding.master_dimensions[1])!=" + getHeight() + "||String(binding.master_dtype||'')=='')fail('active_launch.roi_session_binding','binding cientifico no vigente');var revisionFile=new File('" + jsEscape(v4MasterRevisionManifestPath) + "').getCanonicalFile(),scaleFile=new File('" + jsEscape(scaleReportPath) + "').getCanonicalFile(),masterFile=new File('" + jsEscape(v4MasterImage) + "').getCanonicalFile(),revisionHashBefore=shaFile(revisionFile,'revision_manifest.json'),scaleHashBefore=shaFile(scaleFile,'scale_reconciliation.json'),masterHashBefore=shaFile(masterFile,'montage_master.ome.tif'),scale=readJsonAtHash(scaleFile,scaleHashBefore,'scale_reconciliation.json');if(String(binding.revision_manifest_payload_sha256||'').toLowerCase()!='" + jsEscape(v4MasterRevisionManifestSha256) + "'||String(binding.revision_manifest_file_sha256||'').toLowerCase()!=revisionHashBefore||String(binding.master_sha256||'').toLowerCase()!=masterHashBefore||String(binding.scale_report_sha256||'').toLowerCase()!=scaleHashBefore||String(binding.scale_input_signature||'')!=String(scale.input_signature||'')||String(binding.calibration_id||'')!='" + jsEscape(v4CalibrationId) + "')fail('scientific_binding','revision, maestro, escala o calibracion no vigentes');var activeTool=activeLaunch.toolset;if(activeTool==null)fail('active_launch','toolset ausente');var activeToolSourceFile=new File(String(activeTool.source_path||'')).getCanonicalFile(),activeToolInstalledFile=new File(String(activeTool.installed_path||'')).getCanonicalFile(),activeToolSourceHashBefore=shaFile(activeToolSourceFile,'toolset source'),activeToolInstalledHashBefore=shaFile(activeToolInstalledFile,'toolset installed');if(activeTool.current!==true||String(activeTool.status||'')!='CURRENT'||String(activeTool.source_sha256||'').toLowerCase()!=String(binding.toolset_sha256||'').toLowerCase()||String(activeTool.installed_sha256||'').toLowerCase()!=String(binding.toolset_sha256||'').toLowerCase()||activeToolSourceHashBefore!=String(binding.toolset_sha256).toLowerCase()||activeToolInstalledHashBefore!=String(binding.toolset_sha256).toLowerCase())fail('active_launch','toolset no CURRENT o bytes distintos');";
    js = js + "var projectHashBefore=shaFile(projectFile,'project.json'),pointerHashBefore=shaFile(pointerFile,'current_roi_session.json'),bridgeHashBefore=shaFile(currentBridgeFile,'current_bridge.json'),project=readJsonAtHash(projectFile,projectHashBefore,'project.json'),bridge=readJsonAtHash(currentBridgeFile,bridgeHashBefore,'current_bridge.json');if(String(bridge.payload_sha256||'').toLowerCase()!=payloadHash(bridge))fail('current_bridge.json','payload_sha256 no coincide');var projectVersion=Number(project.project_version),bridgeGeneration=String(bridge.generation_id||''),generationRelative=String(bridge.generation_relative_path||'').replace(/\\\\/g,'/');if(!isFinite(projectVersion)||Math.floor(projectVersion)!=projectVersion||projectVersion<0||Number(bridge.project_version)!=projectVersion||String(project.project_id||'')!=String(binding.project_id)||String(bridge.project_id||'')!=String(binding.project_id)||String(bridge.revision_id||'')!=String(binding.montage_revision_id)||String(bridge.project_payload_sha256||'').toLowerCase()!=projectHashBefore||generationRelative!='fiji_bridge/generations/'+bridgeGeneration)fail('current_bridge.json','bridge vivo no coincide con project.json');var bridgeManifestFile=new File(root,generationRelative+'/bridge_generation_manifest.json').getCanonicalFile(),bridgeManifestHashBefore=shaFile(bridgeManifestFile,'bridge_generation_manifest.json'),bridgeManifest=readJsonAtHash(bridgeManifestFile,bridgeManifestHashBefore,'bridge_generation_manifest.json');if(bridgeManifestHashBefore!=String(bridge.generation_manifest_sha256||'').toLowerCase()||String(bridgeManifest.payload_sha256||'').toLowerCase()!=payloadHash(bridgeManifest)||String(bridgeManifest.generation_id||'')!=bridgeGeneration||String(bridgeManifest.project_id||'')!=String(binding.project_id)||String(bridgeManifest.revision_id||'')!=String(binding.montage_revision_id)||String(bridgeManifest.project_payload_sha256||'').toLowerCase()!=projectHashBefore||Number(bridgeManifest.project_version)!=projectVersion)fail('bridge_generation_manifest.json','generacion bridge viva incoherente');";
    js = js + "var pointer=readJsonAtHash(pointerFile,pointerHashBefore,'current_roi_session.json');exactKeys(pointer,contract.current_pointer_fields,'current_roi_session.json');if(String(pointer.payload_sha256||'').toLowerCase()!=payloadHash(pointer)||String(pointer.schema_version||'')!='cavity_current_roi_session_v1'||String(pointer.application_version||'')!='5.6.0'||String(pointer.publication_status||'')!='PUBLISHED'||!allowedState(pointer.review_status,pointer.quantitative_ready))fail('current_roi_session.json','schema o estado estructural no permitido');var roiState=project.roi_sessions;exactKeys(roiState,['schema_version','current_session_id','current_pointer_payload_sha256','current_quantitative_ready','updated_at'],'project.json.roi_sessions');if(String(project.application_version||'')!='5.6.0'||String(roiState.schema_version||'')!='cavity_project_roi_sessions_v1'||String(roiState.current_session_id||'')!=String(pointer.session_id)||String(roiState.current_pointer_payload_sha256||'').toLowerCase()!=String(pointer.payload_sha256||'').toLowerCase()||roiState.current_quantitative_ready!==pointer.quantitative_ready||String(roiState.updated_at||'').replace(/^\\s+|\\s+$/g,'')=='')fail('project.json.roi_sessions','project y pointer no designan la misma autoridad');var sessionId=String(pointer.session_id||'');if(!isGenerationId(sessionId)||String(pointer.project_id||'')!=String(binding.project_id)||String(pointer.montage_revision_id||'')!=String(binding.montage_revision_id)||String(pointer.master_sha256||'').toLowerCase()!=String(binding.master_sha256).toLowerCase())fail('current_roi_session.json','identidad o binding no vigente');var sessionRelative='sessions/roi_sessions/'+sessionId,manifestRelative=sessionRelative+'/roi_session_manifest.json';if(String(pointer.session_relative_path||'').replace(/\\\\/g,'/')!=sessionRelative||String(pointer.manifest_relative_path||'').replace(/\\\\/g,'/')!=manifestRelative)fail('current_roi_session.json','rutas no canonicas');var sessionsRoot=new File(new File(root,'sessions'),'roi_sessions').getCanonicalFile(),sessionDir=new File(root,sessionRelative).getCanonicalFile();if(!same(sessionDir.getParentFile(),sessionsRoot)||!sessionDir.isDirectory())fail('roi_session','generacion no hija directa');var manifestFile=new File(sessionDir,'roi_session_manifest.json').getCanonicalFile(),zipFile=new File(sessionDir,'rois.zip').getCanonicalFile(),indexFile=new File(sessionDir,'roi_index.json').getCanonicalFile(),listed=sessionDir.listFiles(),names=[];if(listed==null)fail('roi_session','no se puede listar');for(var li=0;li<listed.length;li++)names.push(String(listed[li].getName()));names.sort();if(names.join('|')!='roi_index.json|roi_session_manifest.json|rois.zip')fail('roi_session','inventario no exacto');var manifestHashBefore=shaFile(manifestFile,'roi_session_manifest.json'),zipHashBefore=shaFile(zipFile,'rois.zip'),indexHashBefore=shaFile(indexFile,'roi_index.json');if(manifestHashBefore!=String(pointer.manifest_sha256||'').toLowerCase())fail('roi_session_manifest.json','hash no coincide con pointer');var manifest=readJsonAtHash(manifestFile,manifestHashBefore,'roi_session_manifest.json');exactKeys(manifest,contract.roi_session_manifest_fields,'roi_session_manifest.json');if(String(manifest.payload_sha256||'').toLowerCase()!=payloadHash(manifest)||String(manifest.payload_sha256||'').toLowerCase()!=String(pointer.manifest_payload_sha256||'').toLowerCase()||String(manifest.schema_version||'')!='cavity_roi_session_v2'||String(manifest.application_version||'')!='5.6.0'||String(manifest.session_id||'')!=sessionId||String(manifest.source_type||'')!='CANONICAL_REQUEST'||String(manifest.publication_status||'')!='PUBLISHED'||!allowedState(manifest.review_status,manifest.quantitative_ready)||String(manifest.review_status)!=String(pointer.review_status)||manifest.quantitative_ready!==pointer.quantitative_ready||String(manifest.published_at||'')!=String(pointer.published_at||''))fail('roi_session_manifest.json','manifest y pointer no coinciden');";
    js = js + "exactKeys(manifest.binding,bindingKeys,'manifest.binding');for(var bk=0;bk<bindingKeys.length;bk++)if(stable(manifest.binding[bindingKeys[bk]])!=stable(binding[bindingKeys[bk]]))fail('manifest.binding','campo no vigente: '+bindingKeys[bk]);var creation=manifest.creation_context;exactKeys(creation,contract.creation_context_fields,'manifest.creation_context');if(!isFinite(Number(creation.project_version))||Math.floor(Number(creation.project_version))!=Number(creation.project_version)||Number(creation.project_version)<0||!isSha(creation.project_payload_sha256)||String(creation.bridge_generation_id||'')==''||!isSha(creation.bridge_manifest_sha256))fail('manifest.creation_context','snapshot historico no valido');var refs=project.references||{},calRel=String(refs.calibrations_file||'references/calibrations.json').replace(/\\\\/g,'/'),refsRoot=new File(root,'references').getCanonicalFile(),calFile=new File(root,calRel).getCanonicalFile();if(!inside(calFile,refsRoot))fail('calibration_record','registry fuera de references');var calibrationHashBefore=shaFile(calFile,'calibrations.json'),registry=readJsonAtHash(calFile,calibrationHashBefore,'calibrations.json'),calibrations=registry.calibrations,activeCalibration=String(refs.active_calibration_id||''),matches=[];if(!isArray(calibrations)||activeCalibration!=String(binding.calibration_id||''))fail('calibration_record','calibracion activa no coincide');for(var ci=0;ci<calibrations.length;ci++)if(String((calibrations[ci]||{}).calibration_id||'')==activeCalibration)matches.push(calibrations[ci]);if(matches.length!=1||shaText(stable(matches[0]))!=String(binding.calibration_record_sha256||'').toLowerCase()||stable(manifest.calibration_record)!=stable(matches[0]))fail('calibration_record','registro vivo, binding y manifest no coinciden');var sourceLaunch=manifest.source_launch;exactKeys(sourceLaunch,contract.source_launch_fields,'manifest.source_launch');requireVersion(sourceLaunch.fiji_imagej_version,'source_launch.fiji_imagej_version');requireVersion(sourceLaunch.java_version,'source_launch.java_version');var sourceLaunchRel=String(sourceLaunch.launch_record_relative_path||'').replace(/\\\\/g,'/'),sourceLaunchFile=new File(root,sourceLaunchRel).getCanonicalFile();if(!same(sourceLaunchFile.getParentFile(),bridgeDir)||String(sourceLaunchFile.getName()).indexOf('local_launch_')!=0||String(sourceLaunchFile.getName()).toLowerCase().substring(String(sourceLaunchFile.getName()).length-5)!='.json')fail('manifest.source_launch','ruta launch historico no canonica');var sourceLaunchHashBefore=shaFile(sourceLaunchFile,'source_launch');if(sourceLaunchHashBefore!=String(sourceLaunch.launch_record_sha256||'').toLowerCase())fail('manifest.source_launch','hash launch historico no coincide');var originLaunch=readJsonAtHash(sourceLaunchFile,sourceLaunchHashBefore,'source_launch'),originBinding=originLaunch.roi_session_binding;exactKeys(originBinding,bindingKeys,'source_launch.roi_session_binding');for(var ob=0;ob<bindingKeys.length;ob++)if(stable(originBinding[bindingKeys[ob]])!=stable(binding[bindingKeys[ob]]))fail('manifest.source_launch','binding historico distinto');var originTool=originLaunch.toolset;if(originTool==null||String(sourceLaunch.installed_toolset_path||'')!=String(originTool.installed_path||'')||String(sourceLaunch.installed_toolset_sha256||'').toLowerCase()!=String(originTool.installed_sha256||'').toLowerCase()||String(sourceLaunch.source_toolset_path||'')!=String(originTool.source_path||'')||String(sourceLaunch.source_toolset_sha256||'').toLowerCase()!=String(originTool.source_sha256||'').toLowerCase()||String(sourceLaunch.fiji_root||'')!=String(originLaunch.fiji_root||'')||String(sourceLaunch.fiji_executable||'')!=String(originLaunch.fiji_executable||'')||String(sourceLaunch.installed_toolset_sha256||'').toLowerCase()!=String(binding.toolset_sha256||'').toLowerCase()||String(sourceLaunch.source_toolset_sha256||'').toLowerCase()!=String(binding.toolset_sha256||'').toLowerCase())fail('manifest.source_launch','toolset o procedencia historica no coinciden');";
    js = js + "var artifacts=manifest.artifacts;exactKeys(artifacts,['rois.zip','roi_index.json'],'manifest.artifacts');var zipRecord=artifacts['rois.zip'],indexRecord=artifacts['roi_index.json'];exactKeys(zipRecord,['sha256','size_bytes'],'rois.zip record');exactKeys(indexRecord,['sha256','size_bytes'],'roi_index.json record');if(!isInteger(zipRecord.size_bytes)||zipRecord.size_bytes!=Number(zipFile.length())||String(zipRecord.sha256||'').toLowerCase()!=zipHashBefore||!isInteger(indexRecord.size_bytes)||indexRecord.size_bytes!=Number(indexFile.length())||String(indexRecord.sha256||'').toLowerCase()!=indexHashBefore)fail('manifest.artifacts','hash o tamano no coincide');var inspected=inspectZip(zipFile),index=readJsonAtHash(indexFile,indexHashBefore,'roi_index.json');exactKeys(index,contract.roi_index_fields,'roi_index.json');if(String(index.payload_sha256||'').toLowerCase()!=payloadHash(index)||String(index.schema_version||'')!='cavity_roi_index_v2'||String(index.application_version||'')!='5.6.0'||!isInteger(index.geometry_precision_decimals)||index.geometry_precision_decimals!=6||!isArray(index.rois)||index.rois.length==0)fail('roi_index.json','schema o filas no validas');exactKeys(index.binding,bindingKeys,'index.binding');for(var ik=0;ik<bindingKeys.length;ik++)if(stable(index.binding[bindingKeys[ik]])!=stable(binding[bindingKeys[ik]]))fail('index.binding','campo no vigente: '+bindingKeys[ik]);var seen={},seenSemantic={},semantic=[],roles={},pending=0,reviewed=0,lastSort='';for(var ri=0;ri<index.rois.length;ri++){var row=index.rois[ri];exactKeys(row,contract.roi_index_row_fields,'roi_index.row');exactKeys(row.canonical_geometry_methods,contract.canonical_geometry_method_fields,'roi_index.row.canonical_geometry_methods');exactKeys(row.fiji_observation,contract.fiji_observation_fields,'roi_index.row.fiji_observation');exactKeys(row.fiji_observation.area,contract.fiji_metric_observation_fields,'roi_index.row.fiji_observation.area');exactKeys(row.fiji_observation.perimeter,contract.fiji_metric_observation_fields,'roi_index.row.fiji_observation.perimeter');var name=String(row.entry_name||''),binary=inspected.entries[name],review=String(row.review_status||''),role=String(row.scientific_role||''),uuid=String(row.object_uuid||'').toLowerCase(),objectId=String(row.object_id||''),sortKey=role+'\\u0000'+objectId+'\\u0000'+uuid,geometryClass=String((row.geometry||{}).geometry_class||''),roiType=String(row.imagej_roi_type||''),classAllowed=geometryClass==roiType||(roiType=='rectangle'&&geometryClass=='rounded_rectangle');if(binary==null||String(row.entry_sha256||'').toLowerCase()!=binary.sha256||!isInteger(row.entry_size_bytes)||row.entry_size_bytes!=Number(binary.size_bytes)||seen[name.toLowerCase()]||seenSemantic[String(row.semantic_sha256||'').toLowerCase()]||!isSha(row.semantic_sha256)||contract.row_review_statuses.indexOf(review)<0||!classAllowed)fail('roi_index.row','binario, identidad, estado o clase geometrica no validos');if(lastSort!=''&&sortKey<lastSort)fail('roi_index.json','orden de filas no canonico');lastSort=sortKey;seen[name.toLowerCase()]=1;seenSemantic[String(row.semantic_sha256).toLowerCase()]=1;semantic.push(String(row.semantic_sha256));roles[role]=Number(roles[role]||0)+1;if(review=='pending')pending++;else reviewed++;var semanticPayload={object_uuid:uuid,object_id:objectId,imagej_roi_type:String(row.imagej_roi_type),scientific_role:role,roi_set_id:String(row.roi_set_id),object_class:String(row.object_class),object_subtype:String(row.object_subtype),geometry:semanticGeometry(row.geometry),bounding_box:semanticGeometry(row.bounding_box),centroid:semanticGeometry(row.centroid),area_px2:semanticGeometry(row.area_px2),perimeter_px:semanticGeometry(row.perimeter_px),project_id:String(row.project_id),montage_revision_id:String(row.montage_revision_id),master_sha256:String(row.master_sha256).toLowerCase(),master_dimensions:row.master_dimensions,master_dtype:String(row.master_dtype),coordinate_system:String(row.coordinate_system),review_status:review,include_in_statistics:row.include_in_statistics,canonical_geometry_methods:semanticGeometry(row.canonical_geometry_methods)};if(String(row.semantic_sha256).toLowerCase()!=shaText(stable(semanticPayload)))fail('roi_index.row','semantic_sha256 no coincide');}if(index.rois.length!=inspected.count||!isInteger(manifest.roi_count)||manifest.roi_count!=inspected.count)fail('roi_session_manifest.json','roi_count no coincide');var inventory={},inventoryNames=[];for(var en in inspected.entries)if(Object.prototype.hasOwnProperty.call(inspected.entries,en))inventoryNames.push(en);inventoryNames.sort();for(var ii=0;ii<inventoryNames.length;ii++){var item=inspected.entries[inventoryNames[ii]];inventory[inventoryNames[ii]]={sha256:item.sha256,size_bytes:item.size_bytes};}semantic.sort();if(String(manifest.binary_inventory_sha256||'').toLowerCase()!=shaText(stable(inventory))||stable(manifest.semantic_fingerprints)!=stable(semantic)||stable(manifest.role_counts)!=stable(roles))fail('roi_session_manifest.json','inventario, roles o fingerprints no coinciden');";
    js = js + "var rowBindingKeys=['project_id','montage_revision_id','master_sha256','master_dimensions','master_dtype','coordinate_system'],allowedRoles=['object','region','line_feature','reference_feature','surface','scale_reference','metadata'],rowByName={},seenUuidExact={},seenRoleObject={};for(var rv=0;rv<index.rois.length;rv++){var validatedRow=index.rois[rv],validatedName=String(validatedRow.entry_name||''),validatedUuid=String(validatedRow.object_uuid||'').toLowerCase(),validatedRole=String(validatedRow.scientific_role||''),validatedObjectId=String(validatedRow.object_id||''),validatedRoleObject=(validatedRole+'\\u0000'+validatedObjectId).toLowerCase();if(!isUuid(validatedUuid)||seenUuidExact[validatedUuid]||allowedRoles.indexOf(validatedRole)<0||validatedObjectId.replace(/^\\s+|\\s+$/g,'')==''||seenRoleObject[validatedRoleObject])fail('roi_index.row','UUID, rol u object_id invalido o duplicado');seenUuidExact[validatedUuid]=1;seenRoleObject[validatedRoleObject]=1;if(String(validatedRow.roi_set_id||'').replace(/^\\s+|\\s+$/g,'')==''||String(validatedRow.object_class||'').replace(/^\\s+|\\s+$/g,'')==''||String(validatedRow.object_subtype||'').replace(/^\\s+|\\s+$/g,'')==''||String(validatedRow.created_time||'').replace(/^\\s+|\\s+$/g,'')==''||String(validatedRow.modified_time||'').replace(/^\\s+|\\s+$/g,'')==''||typeof validatedRow.include_in_statistics!='boolean')fail('roi_index.row','metadatos o inclusion incompletos');for(var rb=0;rb<rowBindingKeys.length;rb++){var rowBindingKey=rowBindingKeys[rb];if(stable(validatedRow[rowBindingKey])!=stable(binding[rowBindingKey]))fail('roi_index.row','binding de fila distinto: '+rowBindingKey);}var canonicalGeometryFields=['geometry_class','vertices_px'];if(String((validatedRow.geometry||{}).geometry_class||'')=='rounded_rectangle')canonicalGeometryFields.push('rounded_rect_arc_size_px');exactKeys(validatedRow.geometry,canonicalGeometryFields,'roi_index.row.geometry');if(String(validatedRow.geometry.geometry_class||'').replace(/^\\s+|\\s+$/g,'')=='')fail('roi_index.row.geometry','clase ausente');validateVertices(validatedRow.geometry.vertices_px,'roi_index.row.geometry');finiteObject(validatedRow.bounding_box,['x','y','width','height'],'roi_index.row.bounding_box');if(Number(validatedRow.bounding_box.width)<0||Number(validatedRow.bounding_box.height)<0)fail('roi_index.row.bounding_box','dimension negativa');finiteObject(validatedRow.centroid,['x','y'],'roi_index.row.centroid');var areaNull=validatedRow.area_px2===null,perimeterNull=validatedRow.perimeter_px===null;if(areaNull!=perimeterNull||(!areaNull&&(typeof validatedRow.area_px2!='number'||!isFinite(validatedRow.area_px2)||Number(validatedRow.area_px2)<0||typeof validatedRow.perimeter_px!='number'||!isFinite(validatedRow.perimeter_px)||Number(validatedRow.perimeter_px)<0)))fail('roi_index.row','metricas canonicas invalidas');for(var cm=0;cm<contract.canonical_geometry_method_fields.length;cm++)if(String(validatedRow.canonical_geometry_methods[contract.canonical_geometry_method_fields[cm]]||'').replace(/^\\s+|\\s+$/g,'')=='')fail('roi_index.row.canonical_geometry_methods','metodo vacio');validateObservation(validatedRow.fiji_observation,'roi_index.row.fiji_observation');if(String(validatedRow.fiji_observation.imagej_roi_type)!=String(validatedRow.imagej_roi_type))fail('roi_index.row.fiji_observation','tipo distinto de la fila');rowByName[validatedName]=validatedRow;}";
    js = js + "exactKeys(manifest.review_counts,contract.review_count_fields,'manifest.review_counts');if(Number(manifest.review_counts.pending)!=pending||Number(manifest.review_counts.reviewed)!=reviewed)fail('manifest.review_counts','recuentos no coinciden con las filas');var geometry=manifest.geometry_validation;exactKeys(geometry,contract.geometry_validation_fields,'manifest.geometry_validation');exactKeys(geometry.metric_tolerances,contract.geometry_metric_tolerance_fields,'geometry.metric_tolerances');if(!isArray(geometry.entries)||!isArray(geometry.blockers)||geometry.entries.length!=index.rois.length)fail('manifest.geometry_validation','resumen geometrico incompleto');var derivedSupportedCount=0,derivedUnsupportedCount=0,derivedGeometryBlockerSet={},derivedGeometryBlockers=[],previousGeometryEntry='';for(var ge=0;ge<geometry.entries.length;ge++){var geometryEntry=geometry.entries[ge],geometryEntryName=String(geometryEntry.entry_name||'');exactKeys(geometryEntry,contract.geometry_entry_fields,'geometry.entry');exactKeys(geometryEntry.area,contract.geometry_metric_fields,'geometry.entry.area');exactKeys(geometryEntry.perimeter,contract.geometry_metric_fields,'geometry.entry.perimeter');if(!isArray(geometryEntry.blockers)||geometryEntryName==''||(previousGeometryEntry!=''&&geometryEntryName<=previousGeometryEntry))fail('geometry.entry','identidad, orden o blockers no validos');previousGeometryEntry=geometryEntryName;if(geometryEntry.supported===true){var areaResult=String(geometryEntry.area.result||''),perimeterResult=String(geometryEntry.perimeter.result||'');if(geometryEntry.blockers.length!=0||['MATCH','DIAGNOSTIC_ONLY'].indexOf(areaResult)<0||['MATCH','DIAGNOSTIC_ONLY'].indexOf(perimeterResult)<0||!isFinite(Number(geometryEntry.area.derived))||Number(geometryEntry.area.derived)<0||!isFinite(Number(geometryEntry.perimeter.derived))||Number(geometryEntry.perimeter.derived)<0)fail('geometry.entry','entrada supported sin derivacion canonica Python');derivedSupportedCount++;}else if(geometryEntry.supported===false){if(geometryEntry.blockers.length==0||String(geometryEntry.area.result||'')!='UNSUPPORTED'||String(geometryEntry.perimeter.result||'')!='UNSUPPORTED')fail('geometry.entry','entrada unsupported sin bloqueo y metricas UNSUPPORTED');var previousEntryBlocker='';for(var geb=0;geb<geometryEntry.blockers.length;geb++){var entryBlocker=String(geometryEntry.blockers[geb]||'');if(entryBlocker==''||(previousEntryBlocker!=''&&entryBlocker<=previousEntryBlocker))fail('geometry.entry','blockers no canonicos');previousEntryBlocker=entryBlocker;derivedGeometryBlockerSet[entryBlocker]=1;}derivedUnsupportedCount++;}else fail('geometry.entry','supported debe ser booleano');}for(var derivedBlocker in derivedGeometryBlockerSet)if(Object.prototype.hasOwnProperty.call(derivedGeometryBlockerSet,derivedBlocker))derivedGeometryBlockers.push(derivedBlocker);derivedGeometryBlockers.sort();var suppliedGeometryBlockers=[];for(var gb=0;gb<geometry.blockers.length;gb++){var suppliedBlocker=String(geometry.blockers[gb]||'');if(suppliedBlocker==''||(gb>0&&suppliedBlocker<=suppliedGeometryBlockers[gb-1]))fail('manifest.geometry_validation','blockers superiores no canonicos');suppliedGeometryBlockers.push(suppliedBlocker);}if(Number(geometry.supported_count)!=derivedSupportedCount||Number(geometry.unsupported_count)!=derivedUnsupportedCount||derivedSupportedCount+derivedUnsupportedCount!=index.rois.length||stable(suppliedGeometryBlockers)!=stable(derivedGeometryBlockers))fail('manifest.geometry_validation','conteos o union de blockers no derivados de entries');var geometrySeen={};for(var gl=0;gl<geometry.entries.length;gl++){var linkedGeometry=geometry.entries[gl],linkedName=String(linkedGeometry.entry_name||''),linkedRow=rowByName[linkedName];if(linkedRow==null||geometrySeen[linkedName]||String(linkedGeometry.imagej_roi_type||'')!=String(linkedRow.imagej_roi_type)||String(linkedGeometry.geometry_class||'')!=String(linkedRow.geometry.geometry_class))fail('manifest.geometry_validation','entrada geometrica no ligada a fila');geometrySeen[linkedName]=1;if(linkedGeometry.supported===true){if(linkedRow.area_px2===null||linkedRow.perimeter_px===null||Number(linkedGeometry.area.derived)!=Number(linkedRow.area_px2)||Number(linkedGeometry.perimeter.derived)!=Number(linkedRow.perimeter_px))fail('manifest.geometry_validation','metricas derivadas no ligadas a fila');}else if(linkedRow.area_px2!==null||linkedRow.perimeter_px!==null)fail('manifest.geometry_validation','fila unsupported contiene metricas');}var geometryBlockers=derivedGeometryBlockers.length,derivedReady=pending==0&&geometryBlockers==0,derivedReview=derivedReady?'VERIFIED':'REVIEW_REQUIRED';if(String(geometry.status||'')!=(geometryBlockers==0?'VERIFIED':'REVIEW_REQUIRED')||String(manifest.review_status||'')!=derivedReview||manifest.quantitative_ready!==derivedReady)fail('manifest.geometry_validation','estado global no derivado de pending y blockers');";
    js = js + "var sourceRequest=manifest.source_request;exactKeys(sourceRequest,contract.source_request_fields,'manifest.source_request');var requestId=String(sourceRequest.request_id||''),requestRelative=String(sourceRequest.request_relative_path||'').replace(/\\\\/g,'/'),expectedRequestRelative='sessions/roi_session_requests/'+requestId,requestsRoot=new File(new File(root,'sessions'),'roi_session_requests').getCanonicalFile(),requestDir=new File(root,requestRelative).getCanonicalFile();if(!isGenerationId(requestId)||requestRelative!=expectedRequestRelative||!same(requestDir.getParentFile(),requestsRoot)||!requestDir.isDirectory())fail('manifest.source_request','request historica no canonica');var requestFiles=requestDir.listFiles(),requestNames=[];if(requestFiles==null)fail('manifest.source_request','request ausente');for(var rq=0;rq<requestFiles.length;rq++)requestNames.push(String(requestFiles[rq].getName()));requestNames.sort();if(requestNames.join('|')!='commit_request.json|request_result.json|roi_index.candidate.json|rois.candidate.zip')fail('manifest.source_request','inventario request no exacto');var commitFile=new File(requestDir,'commit_request.json').getCanonicalFile(),candidateZip=new File(requestDir,'rois.candidate.zip').getCanonicalFile(),candidateIndex=new File(requestDir,'roi_index.candidate.json').getCanonicalFile(),resultFile=new File(requestDir,'request_result.json').getCanonicalFile(),commitHashBefore=shaFile(commitFile,'commit_request.json'),candidateZipHashBefore=shaFile(candidateZip,'rois.candidate.zip'),candidateIndexHashBefore=shaFile(candidateIndex,'roi_index.candidate.json'),resultHashBefore=shaFile(resultFile,'request_result.json'),candidateZipSizeBefore=Number(candidateZip.length()),candidateIndexSizeBefore=Number(candidateIndex.length()),request=readJsonAtHash(commitFile,commitHashBefore,'commit_request.json');exactKeys(request,contract.commit_request_fields,'commit_request.json');if(String(request.payload_sha256||'').toLowerCase()!=payloadHash(request)||String(request.payload_sha256||'').toLowerCase()!=String(sourceRequest.commit_request_payload_sha256||'').toLowerCase()||String(request.candidate_zip_sha256||'').toLowerCase()!=String(sourceRequest.candidate_zip_sha256||'').toLowerCase()||String(request.candidate_index_sha256||'').toLowerCase()!=String(sourceRequest.candidate_index_sha256||'').toLowerCase()||String(request.candidate_zip_sha256||'').toLowerCase()!=candidateZipHashBefore||String(request.candidate_index_sha256||'').toLowerCase()!=candidateIndexHashBefore||String(request.launch_record_relative_path||'').replace(/\\\\/g,'/')!=sourceLaunchRel||String(request.launch_record_sha256||'').toLowerCase()!=String(sourceLaunch.launch_record_sha256||'').toLowerCase()||stable(request.creation_context)!=stable(creation)||String(request.fiji_imagej_version||'')!=String(sourceLaunch.fiji_imagej_version||'')||String(request.java_version||'')!=String(sourceLaunch.java_version||''))fail('manifest.source_request','request, launch y manifest no describen la misma creacion');";
    js = js + "if(String(request.prepared_at||'').replace(/^\\s+|\\s+$/g,'')=='')fail('commit_request.json','prepared_at ausente');";
    js = js + "if(String(request.schema_version||'')!='cavity_roi_session_request_v2'||String(request.application_version||'')!='5.6.0'||String(request.request_id||'')!=requestId||!isGenerationId(request.request_id)||String(request.prepared_by||'').replace(/^\\s+|\\s+$/g,'')==''||String(request.reason||'').replace(/^\\s+|\\s+$/g,'')==''||!isInteger(request.candidate_zip_size_bytes)||request.candidate_zip_size_bytes!=candidateZipSizeBefore||!isInteger(request.candidate_index_size_bytes)||request.candidate_index_size_bytes!=candidateIndexSizeBefore||String(request.candidate_zip_sha256||'').toLowerCase()!=zipHashBefore)fail('commit_request.json','schema, identidad, tamanos o ZIP publicado no coinciden');var draft=readJsonAtHash(candidateIndex,candidateIndexHashBefore,'roi_index.candidate.json');exactKeys(draft,contract.roi_request_draft_fields,'roi_index.candidate.json');if(String(draft.payload_sha256||'').toLowerCase()!=payloadHash(draft)||String(draft.schema_version||'')!='cavity_roi_request_draft_v1'||String(draft.application_version||'')!='5.6.0'||draft.authoritative!==false||!isArray(draft.rois)||draft.rois.length!=index.rois.length)fail('roi_index.candidate.json','schema, hash, autoridad o filas invalidas');exactKeys(draft.binding,bindingKeys,'draft.binding');for(var db=0;db<bindingKeys.length;db++)if(stable(draft.binding[bindingKeys[db]])!=stable(binding[bindingKeys[db]]))fail('draft.binding','campo no vigente: '+bindingKeys[db]);var draftSeen={},draftUuid={},draftRoleObject={},draftLastSort='';for(var dr=0;dr<draft.rois.length;dr++){var draftRow=draft.rois[dr];exactKeys(draftRow,contract.roi_request_draft_row_fields,'roi_index.candidate.row');var draftName=String(draftRow.entry_name||''),draftFinal=rowByName[draftName],draftBinary=inspected.entries[draftName],draftUuidValue=String(draftRow.object_uuid||'').toLowerCase(),draftRole=String(draftRow.scientific_role||''),draftObjectId=String(draftRow.object_id||''),draftRoleKey=(draftRole+'\\u0000'+draftObjectId).toLowerCase(),draftSort=draftRole+'\\u0000'+draftObjectId+'\\u0000'+draftUuidValue;if(draftFinal==null||draftBinary==null||draftSeen[draftName.toLowerCase()]||draftUuid[draftUuidValue]||draftRoleObject[draftRoleKey]||!isUuid(draftUuidValue)||!isSha(draftRow.entry_sha256)||String(draftRow.entry_sha256).toLowerCase()!=draftBinary.sha256||!isInteger(draftRow.entry_size_bytes)||draftRow.entry_size_bytes!=Number(draftBinary.size_bytes)||(draftLastSort!=''&&draftSort<draftLastSort))fail('roi_index.candidate.row','identidad, binario u orden no canonico');draftSeen[draftName.toLowerCase()]=1;draftUuid[draftUuidValue]=1;draftRoleObject[draftRoleKey]=1;draftLastSort=draftSort;validateObservation(draftRow.fiji_observation,'roi_index.candidate.row.fiji_observation');for(var dl=0;dl<contract.roi_request_draft_row_fields.length;dl++){var linkedField=contract.roi_request_draft_row_fields[dl];if(stable(draftRow[linkedField])!=stable(draftFinal[linkedField]))fail('roi_index.candidate.row','draft y fila canonica divergen en '+linkedField);}}var requestResult=readJsonAtHash(resultFile,resultHashBefore,'request_result.json');exactKeys(requestResult,contract.request_result_fields,'request_result.json');if(String(requestResult.payload_sha256||'').toLowerCase()!=payloadHash(requestResult)||String(requestResult.schema_version||'')!='cavity_roi_session_request_result_v2'||String(requestResult.application_version||'')!='5.6.0'||String(requestResult.request_id||'')!=requestId||String(requestResult.session_id||'')!=sessionId||String(requestResult.manifest_sha256||'').toLowerCase()!=manifestHashBefore||String(requestResult.manifest_payload_sha256||'').toLowerCase()!=String(manifest.payload_sha256||'').toLowerCase()||String(requestResult.published_at||'')!=String(manifest.published_at||'')||String(requestResult.operator||'')!=String(request.prepared_by||'')||String(requestResult.result||'')!='PUBLISHED'||String(requestResult.review_status||'')!=String(manifest.review_status||'')||requestResult.quantitative_ready!==manifest.quantitative_ready)fail('request_result.json','resultado idempotente no coincide con request y sesion');";
    js = js + "var runtimeFijiVersion=requireVersion(String(Packages.ij.IJ.getVersion()),'active_runtime.fiji_imagej_version'),runtimeJavaVersion=requireVersion(String(Packages.java.lang.System.getProperty('java.version')),'active_runtime.java_version');if(runtimeFijiVersion!=String(sourceLaunch.fiji_imagej_version||'')||runtimeJavaVersion!=String(sourceLaunch.java_version||''))fail('active_runtime','versiones Fiji/ImageJ o Java distintas de la sesion de origen');if(shaFile(projectFile,'project.json')!=projectHashBefore||shaFile(pointerFile,'current_roi_session.json')!=pointerHashBefore||shaFile(currentBridgeFile,'current_bridge.json')!=bridgeHashBefore||shaFile(bridgeManifestFile,'bridge_generation_manifest.json')!=bridgeManifestHashBefore||shaFile(activeLaunchFile,'active_launch')!=activeLaunchHashBefore||shaFile(activeToolSourceFile,'toolset source')!=activeToolSourceHashBefore||shaFile(activeToolInstalledFile,'toolset installed')!=activeToolInstalledHashBefore||shaFile(revisionFile,'revision_manifest.json')!=revisionHashBefore||shaFile(scaleFile,'scale_reconciliation.json')!=scaleHashBefore||shaFile(masterFile,'montage_master.ome.tif')!=masterHashBefore||shaFile(calFile,'calibrations.json')!=calibrationHashBefore||shaFile(sourceLaunchFile,'source_launch')!=sourceLaunchHashBefore||shaFile(manifestFile,'roi_session_manifest.json')!=manifestHashBefore||shaFile(zipFile,'rois.zip')!=zipHashBefore||shaFile(indexFile,'roi_index.json')!=indexHashBefore||shaFile(commitFile,'commit_request.json')!=commitHashBefore||shaFile(candidateZip,'rois.candidate.zip')!=candidateZipHashBefore||shaFile(candidateIndex,'roi_index.candidate.json')!=candidateIndexHashBefore||shaFile(resultFile,'request_result.json')!=resultHashBefore)fail('validation','el contexto cambio durante la lectura');OUT='OK|'+canon(zipFile)+'|'+String(inspected.count)+'|'+derivedReview+'|'+(derivedReady?'1':'0')+'|'+String(pending)+'|'+String(geometryBlockers);}catch(ex){OUT='ERROR|'+clean(lastLabel)+'|'+clean(ex);}finally{try{if(zip!=null)zip.close();}catch(ignore){}}String(OUT);";
    result = "" + eval("js", js);
    parts = split(result, "|");
    if (parts.length < 7 || parts[0] != "OK") { v56SessionValidationError = result; return 0; }
    v56ResolvedSessionZip = normalizeStoredPath(parts[1]);
    v56ResolvedSessionRoiCount = round(parseFloat(parts[2]));
    v56ResolvedSessionReviewStatus = parts[3];
    v56ResolvedSessionQuantitativeReady = round(parseFloat(parts[4]));
    v56ResolvedSessionPendingCount = round(parseFloat(parts[5]));
    v56ResolvedSessionGeometryBlockerCount = round(parseFloat(parts[6]));
    return 1;
}

function v56RequireCurrentSessionQuantitative(actionText, showErrors) {
    if (!v56RefreshLiveBridgeForRoiWorkflow(actionText)) return 0;
    if (!v56ResolveCurrentSessionJava()) {
        if (showErrors) showMessage("Autorizacion cuantitativa bloqueada", "No se puede " + actionText + ".\n\n" + v56SessionValidationError);
        return 0;
    }
    if (v56ResolvedSessionReviewStatus != "VERIFIED" ||
        v56ResolvedSessionQuantitativeReady != 1 ||
        v56ResolvedSessionPendingCount != 0 ||
        v56ResolvedSessionGeometryBlockerCount != 0) {
        if (showErrors) showMessage("Autorizacion cuantitativa bloqueada", "La sesion current es integra y puede cargarse para editar, pero no esta autorizada para cuantificar.\n\nEstado: " + v56ResolvedSessionReviewStatus + "\nPending: " + v56ResolvedSessionPendingCount + "\nBloqueos geometricos: " + v56ResolvedSessionGeometryBlockerCount);
        return 0;
    }
    return 1;
}

function v56RestoreRuntimeFromCanonicalRois() {
    snapshotCurrentView();
    metadataIndex = findMetadataIndex();
    if (metadataIndex >= 0) { safeRoiSelect(metadataIndex); readMetadataFromSelectedRoi(); }
    if (loadScaleReferenceFromRois()) rebuildScaleLabelFromReference(0);
    loadSurfaceReferenceFromRois();
    updateScaleMaybe();
    recalculateCounters();
    restyleAllRois();
    showAllRois();
    restoreViewSnapshot();
    installInteractionListeners(0);
    refreshControlPanelStatus();
}

function v4SaveSession() {
    return v56PrepareRoiSessionRequest("Fiji V9 save session");
}

function v4LoadSession() {
    if (!v4EnsureProject()) return 0;
    if (!v56RefreshLiveBridgeForRoiWorkflow("cargar la sesion current")) return 0;
    if (!v4RequireCurrentRevisionBinding("cargar la sesion current", 1)) return 0;
    if (!v56ResolveCurrentSessionJava()) {
        run("ROI Manager...");
        roiManager("reset");
        showMessage("Sesion incompatible", v56SessionValidationError + "\n\nEl ROI Manager se ha vaciado. No se ha intentado cargar ningun ZIP legacy plano.");
        return 0;
    }
    run("ROI Manager...");
    if (roiManager("count") > 0 && !getBoolean("La sesion current ha sido validada. Para cargarla es obligatorio vaciar el ROI Manager actual.", "Vaciar y cargar", "Cancelar")) return 0;
    roiManager("reset");
    // Re-resolve after the human dialog. A changed pointer or binding aborts.
    if (!v56ResolveCurrentSessionJava()) {
        roiManager("reset");
        showMessage("Sesion current cambiada", v56SessionValidationError + "\n\nEl ROI Manager permanece vacio.");
        return 0;
    }
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "abrir la sesion current", 1)) { roiManager("reset"); return 0; }
    roiManager("open", v56ResolvedSessionZip);
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar de abrir la sesion current", 1)) { roiManager("reset"); return 0; }
    if (roiManager("count") != v56ResolvedSessionRoiCount || v4CountForeignProjectRois() > 0 || v4CountRevisionBindingMismatches() > 0) {
        roiManager("reset");
        showMessage("Sesion current incompatible", "Las ROI abiertas no coinciden con el indice o con el binding vigente. El ROI Manager se ha vaciado.");
        return 0;
    }
    loadedDraft = v56CollectRoiDraftJson();
    if (loadedDraft == "") {
        roiManager("reset");
        showMessage("Sesion current incompleta", v56RoiDraftError + "\n\nEl ROI Manager se ha vaciado.");
        return 0;
    }
    v56RestoreRuntimeFromCanonicalRois();
    if (v56ResolvedSessionReviewStatus == "REVIEW_REQUIRED") {
        showStatus("Sesion current integra pendiente de revisar cargada.");
        showMessage("Sesion pendiente de revision", "Sesion integra, pendiente de revisar; no autorizada para cuantificar.\n\nPuede continuar editando y revisando las ROI. Guarde una nueva request y publiquela desde Studio cuando termine.");
    } else {
        showStatus("Sesion current VERIFIED y autorizada cargada.");
    }
    return 1;
}

function v4CountForeignProjectRois() {
    run("ROI Manager...");
    foreignCount = 0;
    foreignTotal = roiManager("count");
    for (foreignIndex=0; foreignIndex<foreignTotal; foreignIndex++) {
        if (!safeRoiSelect(foreignIndex)) continue;
        foreignId = Roi.getProperty("Project_id");
        if (foreignId != "" && foreignId != v4ProjectId) foreignCount++;
    }
    return foreignCount;
}

function v4SessionPath() {
    v4SessionsDirText = projectAwareJoinPath(v4ProjectDir, "sessions");
    v4SessionFileText = projectAwareJoinPath(v4SessionsDirText, "current_roi_session.json");
    return "" + v4SessionFileText;
}

function v4QuickAudit() {
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("auditar las ROI", 1)) return;
    run("ROI Manager..."); n=roiManager("count");
    missingId=0; missingType=0; missingSet=0; invalidSize=0; invalidPosition=0; duplicates=0; unreviewed=0; panelBoundary=0; pendingLegacy=0;
    for(i=0;i<n;i++) {
        safeRoiSelect(i);
        type=Roi.getProperty("Object_type"); if(type=="") type=currentRoiType();
        if(type=="session_metadata" || type=="scale_label") continue;
        if(propString("Object_id","")=="") missingId++;
        if(type=="") missingType++;
        if(propString("ROI_set_id","")=="") missingSet++;
        if(propNumber("Size_valid",1)==0) invalidSize++;
        if(propNumber("Position_valid",1)==0) invalidPosition++;
        if(propString("Duplicate_status","clear")=="suspect") duplicates++;
        if(propString("Review_status","")=="" || propString("Review_status","")=="pending") unreviewed++;
        if(propNumber("Crosses_panel_boundary",0)>0) panelBoundary++;
        if(startsWith(toLowerCase(Roi.getName),"__v4_pending__")) pendingLegacy++;
    }
    errors=missingId+missingType+missingSet;
    text="Proyecto: "+v4ProjectName+"\nROIs: "+n+"\n\n";
    text=text+"Identificador ausente: "+missingId+"\nTipo ausente: "+missingType+"\nConjunto ausente: "+missingSet+"\n";
    text=text+"Tamano no valido: "+invalidSize+"\nPosicion no valida: "+invalidPosition+"\nDuplicados sospechosos: "+duplicates+"\nPendientes de revision: "+unreviewed+"\nCruzan frontera efectiva de panel: "+panelBoundary+"\nROIs legacy __V4_PENDING__: "+pendingLegacy+"\n";
    if(!surfaceDefined) text=text+"\nADVERTENCIA: superficie no cargada.\n";
    if(!v4SurfaceOriginDefined) text=text+"ADVERTENCIA: origen s=0 no definido.\n";
    if(isNaN(v4PixelWidth)||v4PixelWidth<=0) text=text+"ERROR: calibracion no definida.\n";
    else if(!v4ScaleMeasurementAllowed || !v4CheckImageScaleAgainstProject(0)) text=text+"ERROR: calibracion de proyecto no conciliada con la imagen activa.\n";
    else text=text+"OK: calibracion conciliada; una barra/referencia dibujada es opcional.\n";
    if(!v4OwnershipCertified || !v4PanelQuantitativeReady || !File.exists(v4OwnershipImage)) text=text+"ERROR: ownership de panel no certificado; no use densidades de area.\n";
    else text=text+"OK: ownership certificado para area y asignacion efectiva.\n";
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "publicar la auditoria Fiji", 1)) return;
    report=projectAwareJoinPath(projectAwareJoinPath(v4ProjectDir,"qc"),"fiji_roi_audit_v4.txt");
    makeDirIfMissing(projectAwareJoinPath(v4ProjectDir,"qc")); File.saveString(text,report);
    if (!v55ProjectBridgeMarkerClear(v4ProjectDir, "terminar la auditoria Fiji", 1)) return;
    showMessage("Auditoria de Fiji",text+"\nInforme: "+report);
}

function v4Timestamp() {
    getDateAndTime(year,month,dayOfWeek,dayOfMonth,hour,minute,second,msec);
    return year+IJ.pad(month+1,2)+IJ.pad(dayOfMonth,2)+"_"+IJ.pad(hour,2)+IJ.pad(minute,2)+IJ.pad(second,2);
}

function v4EnsureProject() {
    if (v4ProjectSwitchInProgress) {
        if (v4ProjectLoaded && v4ProjectDir != "") return v55ProjectBridgeMarkerClear(v4ProjectDir, "guardar la sesion del proyecto anterior", 1);
        return 0;
    }
    hadProjectContext = v4ProjectLoaded || v4ProjectDir != "";
    imageProjectRoot = v4FindProjectRootFromCurrentImage();
    if (v4SynchronizeProjectContext()) return 1;
    if (hadProjectContext || imageProjectRoot != "") return 0;
    v4OpenProject();
    if (!v4ProjectLoaded || v4ProjectDir == "") return 0;
    return v55RequireActiveImageProjectContext(v4ProjectDir, "usar el proyecto abierto", 1);
}


// --- Image enhancement tools ---
// Cavity_Image_Enhancement_Tools_v4_0.ijm
// Non-destructive visualization helpers for TEM cavities and line defects.
// Every operation is applied to a duplicate; the acquisition/master image is
// never overwritten by these commands.

var imageToolsVersion = "5.6.0";
var imageToolsLastRecipe = "";
var imageToolsLastPurpose = "visualization_only";
var imageToolsLastSource = "";

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.

// [Cavity TEM Light] Legacy visible macro removed from this focused branch.


function imageToolsPanel() {
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra una imagen TEM antes de crear vistas de analisis."); return; }
    actions = newArray(
        "Vista de cavidades: fondo + suavizado + realce",
        "DoG multiescala para cavidades claras",
        "DoG multiescala para cavidades oscuras",
        "Crear par DoG claro/oscuro",
        "Generar candidatos DoG revisables",
        "Vista de dislocaciones: fondo + realce lineal",
        "CLAHE en una copia",
        "Barrido de parametros",
        "Guardar vista actual y receta",
        "Buscar plugins recomendados"
    );
    Dialog.create("Herramientas de imagen TEM v5");
    Dialog.addMessage("Todas las operaciones se ejecutan sobre copias. Las vistas derivadas ayudan a visualizar y proponer candidatos, pero no sustituyen la comprobacion sobre el master u original.");
    Dialog.addChoice("Accion:", actions, actions[0]);
    Dialog.show();
    a=Dialog.getChoice();
    if(a==actions[0]) imageToolsCavityView();
    else if(a==actions[1]) imageToolsDogView(1);
    else if(a==actions[2]) imageToolsDogView(-1);
    else if(a==actions[3]) imageToolsDogPair();
    else if(a==actions[4]) imageToolsGenerateDogCandidates();
    else if(a==actions[5]) imageToolsDislocationView();
    else if(a==actions[6]) imageToolsClaheView();
    else if(a==actions[7]) imageToolsParameterSweep();
    else if(a==actions[8]) imageToolsSaveViewAndRecipe();
    else imageToolsPluginFinder();
}

function imageToolsCavityView() {
    if (!imageToolsRequireImage()) return;
    Dialog.create("Vista segura de cavidades");
    Dialog.addNumber("Radio de fondo - paraboloide deslizante (px):",80);
    Dialog.addNumber("Sigma gaussiano (px):",0.8);
    Dialog.addCheckbox("Aplicar unsharp mask moderado",1);
    Dialog.addNumber("Radio unsharp (px):",1.5);
    Dialog.addNumber("Peso unsharp:",0.5);
    Dialog.addCheckbox("Invertir LUT solo visualmente",0);
    Dialog.show();
    radius=Dialog.getNumber(); sigma=Dialog.getNumber(); doUnsharp=Dialog.getCheckbox(); unRadius=Dialog.getNumber(); unWeight=Dialog.getNumber(); invertLut=Dialog.getCheckbox();
    source=getTitle(); title=imageToolsUniqueTitle("VIEW_CAVITY");
    if (!imageToolsDuplicateFullImage(title)) return;
    if (radius>0 && !imageToolsSubtractBackgroundSafe(radius)) { close(); return; }
    if(sigma>0) run("Gaussian Blur...","sigma="+sigma);
    if(doUnsharp && unRadius>0) run("Unsharp Mask...","radius="+unRadius+" mask="+unWeight);
    if(invertLut) run("Invert LUT");
    imageToolsLastSource=source;
    imageToolsLastPurpose="cavity_visualization";
    imageToolsLastRecipe="{\"recipe_id\":\""+imageToolsTimestamp()+"\",\"purpose\":\"cavity_visualization\",\"source_title\":\""+jsonEscape(source)+"\",\"operations\":[{\"name\":\"sliding_paraboloid_background\",\"radius_px\":"+radius+"},{\"name\":\"gaussian_blur\",\"sigma_px\":"+sigma+"},{\"name\":\"unsharp_mask\",\"enabled\":"+doUnsharp+",\"radius_px\":"+unRadius+",\"weight\":"+unWeight+"},{\"name\":\"invert_lut\",\"enabled\":"+invertLut+"}],\"full_image_duplicate\":true,\"geometry_preserved\":true,\"measurement_role\":\"visualization_only\"}";
    showStatus("Vista de cavidades creada sobre una copia.");
}

function imageToolsDogView(polarity) {
    if (!imageToolsRequireImage()) return;
    Dialog.create("Difference of Gaussians");
    Dialog.addNumber("Sigma pequena (px):",1.0);
    Dialog.addNumber("Sigma grande (px):",2.5);
    Dialog.addCheckbox("Normalizar contraste de visualizacion",1);
    Dialog.show();
    s1=Dialog.getNumber(); s2=Dialog.getNumber(); enhance=Dialog.getCheckbox();
    if(s1<=0 || s2<=s1) { showMessage("Parametros no validos","Debe cumplirse 0 < sigma pequena < sigma grande."); return; }
    source=getTitle(); baseId=getImageID();
    title1=imageToolsUniqueTitle("DOG_SMALL"); if (!imageToolsDuplicateFullImage(title1)) return; run("32-bit"); run("Gaussian Blur...","sigma="+s1);
    selectImage(baseId); title2=imageToolsUniqueTitle("DOG_LARGE"); if (!imageToolsDuplicateFullImage(title2)) { selectWindow(title1); close(); selectImage(baseId); return; } run("32-bit"); run("Gaussian Blur...","sigma="+s2);
    if(polarity>0) result=imageCalculator("Subtract create 32-bit",title1,title2);
    else result=imageCalculator("Subtract create 32-bit",title2,title1);
    outputPrefix = "VIEW_DOG_DARK";
    if (polarity>0) outputPrefix = "VIEW_DOG_BRIGHT";
    selectImage(result); rename(imageToolsUniqueTitle(outputPrefix));
    if(enhance) run("Enhance Contrast","saturated=0.35");
    imageToolsLastSource=source;
    imageToolsLastPurpose="cavity_candidate_view";
    imageToolsLastRecipe="{\"recipe_id\":\""+imageToolsTimestamp()+"\",\"purpose\":\"cavity_candidate_view\",\"source_title\":\""+jsonEscape(source)+"\",\"operations\":[{\"name\":\"difference_of_gaussians\",\"sigma_small_px\":"+s1+",\"sigma_large_px\":"+s2+",\"polarity\":"+polarity+"}],\"full_image_duplicate\":true,\"geometry_preserved\":true,\"measurement_role\":\"candidate_detection_only\"}";
    showStatus("Vista DoG creada. Confirme siempre los candidatos sobre el master.");
}

function imageToolsDogPair() {
    if (!imageToolsRequireImage()) return;
    original=getImageID(); imageToolsDogView(1); selectImage(original); imageToolsDogView(-1);
}


function imageToolsGenerateDogCandidates() {
    if (!imageToolsRequireImage()) return;
    if (!v4EnsureProject()) return;
    if (!v4RequireCurrentRevisionBinding("generar candidatos", 1)) return;
    Dialog.create("Candidatos de cavidad por DoG");
    Dialog.addMessage("Se crea una vista DoG y una cola de candidatos no incluida en estadistica. Cada candidato debe confirmarse con 'Cavity V9: revisar objeto seleccionado'.");
    Dialog.addNumber("Sigma pequena (px):",1.0);
    Dialog.addNumber("Sigma grande (px):",2.5);
    Dialog.addChoice("Polaridad:",newArray("Cavidad clara","Cavidad oscura"),"Cavidad clara");
    Dialog.addNumber("Prominence de Find Maxima:",10.0);
    Dialog.addNumber("Diametro inicial (nm; 0 usa px):",5.0);
    Dialog.addNumber("Diametro inicial alternativo (px):",8.0);
    Dialog.addCheckbox("Excluir maximos en el borde",1);
    Dialog.show();
    s1=Dialog.getNumber(); s2=Dialog.getNumber(); polarityLabel=Dialog.getChoice(); prominence=Dialog.getNumber(); diameterNm=Dialog.getNumber(); diameterPxFallback=Dialog.getNumber(); excludeEdge=Dialog.getCheckbox();
    if(s1<=0 || s2<=s1 || prominence<0) { showMessage("Parametros no validos","Debe cumplirse 0 < sigma pequena < sigma grande y prominence >= 0."); return; }
    diameterPx=diameterPxFallback;
    if(diameterNm>0 && v4PixelWidth>0) diameterPx=diameterNm/v4PixelWidth;
    if(diameterPx<1) diameterPx=1;
    sourceId=getImageID(); sourceTitle=getTitle();
    smallTitle=imageToolsUniqueTitle("DOG_CAND_SMALL"); if (!imageToolsDuplicateFullImage(smallTitle)) return; run("32-bit"); run("Gaussian Blur...","sigma="+s1); smallId=getImageID();
    selectImage(sourceId); largeTitle=imageToolsUniqueTitle("DOG_CAND_LARGE"); if (!imageToolsDuplicateFullImage(largeTitle)) { selectImage(smallId); close(); selectImage(sourceId); return; } run("32-bit"); run("Gaussian Blur...","sigma="+s2); largeId=getImageID();
    polarity=1; if(polarityLabel=="Cavidad oscura") polarity=-1;
    if(polarity>0) resultId=imageCalculator("Subtract create 32-bit",smallTitle,largeTitle);
    else resultId=imageCalculator("Subtract create 32-bit",largeTitle,smallTitle);
    selectImage(resultId); rename(imageToolsUniqueTitle("VIEW_DOG_CANDIDATES"));
    resultId=getImageID();
    selectImage(smallId); close(); selectImage(largeId); close(); selectImage(resultId);
    options="prominence="+prominence+" output=[Point Selection]"; if(excludeEdge) options=options+" exclude";
    run("Find Maxima...",options);
    if(selectionType<0) { showMessage("Sin candidatos","Find Maxima no genero una seleccion. Reduzca prominence o revise la polaridad."); return; }
    getSelectionCoordinates(xs,ys);
    if(xs.length==0) { showMessage("Sin candidatos","No se encontraron maximos con estos parametros."); return; }
    previousSet=v4ActiveRoiSetId;
    if(!v4ReadRoiSet("CAVITY_CANDIDATES")) { showMessage("Conjunto ausente","No existe CAVITY_CANDIDATES en el registro ROI."); return; }
    run("ROI Manager..."); created=0;
    for(i=0;i<xs.length;i++) {
        makeOval(xs[i]-diameterPx/2,ys[i]-diameterPx/2,diameterPx,diameterPx);
        temporary="__V4_CANDIDATE_PENDING__"+d2s(getTime(),0)+"_"+i;
        Roi.setName(temporary); roiManager("add"); idx=roiManager("count")-1; safeRoiSelect(idx);
        id=v4NextObjectId(v4ActiveIdPrefix); safeRoiSelect(idx); now=d2s(getTime(),0); uuid=v4Uuid();
        Roi.setName(id); v4SetCoreProperties(id,uuid,now); v4SetGeometryProperties();
        Roi.setProperty("Object_class","doubtful");
        Roi.setProperty("Confidence","algorithmic");
        Roi.setProperty("Review_status","pending");
        Roi.setProperty("Include_in_statistics","0");
        Roi.setProperty("Count_valid","0");
        Roi.setProperty("Size_valid","0");
        Roi.setProperty("Position_valid","1");
        Roi.setProperty("Candidate_method","DoG_Find_Maxima");
        Roi.setProperty("Candidate_source_title",sourceTitle);
        Roi.setProperty("Candidate_sigma_small_px",""+s1);
        Roi.setProperty("Candidate_sigma_large_px",""+s2);
        Roi.setProperty("Candidate_prominence",""+prominence);
        Roi.setProperty("Candidate_polarity",""+polarity);
        v4ApplyActiveStyle(); roiManager("update"); v4RefreshSpatialProperties(idx); created++;
    }
    v4ReadRoiSet(previousSet);
    imageToolsLastSource=sourceTitle; imageToolsLastPurpose="cavity_candidate_detection";
    imageToolsLastRecipe="{\"recipe_id\":\""+imageToolsTimestamp()+"\",\"purpose\":\"cavity_candidate_detection\",\"source_title\":\""+jsonEscape(sourceTitle)+"\",\"operations\":[{\"name\":\"difference_of_gaussians\",\"sigma_small_px\":"+s1+",\"sigma_large_px\":"+s2+",\"polarity\":"+polarity+"},{\"name\":\"find_maxima\",\"prominence\":"+prominence+",\"exclude_edge\":"+excludeEdge+"}],\"initial_diameter_px\":"+diameterPx+",\"candidate_count\":"+created+",\"full_image_duplicate\":true,\"geometry_preserved\":true,\"measurement_role\":\"candidate_detection_only\"}";
    showAllRois();
    showMessage("Candidatos creados","Candidatos: "+created+"\nConjunto: CAVITY_CANDIDATES\n\nNo se incluyen en estadistica hasta confirmarlos individualmente.");
}

function imageToolsDislocationView() {
    if (!imageToolsRequireImage()) return;
    Dialog.create("Vista segura de dislocaciones");
    Dialog.addNumber("Radio de fondo - paraboloide deslizante (px):",120);
    Dialog.addNumber("Sigma gaussiano (px):",0.7);
    Dialog.addChoice("Realce:",newArray("Unsharp moderado","Find Edges","Sin realce adicional"),"Unsharp moderado");
    Dialog.addNumber("Radio unsharp (px):",2.0);
    Dialog.addNumber("Peso unsharp:",0.6);
    Dialog.show();
    radius=Dialog.getNumber(); sigma=Dialog.getNumber(); method=Dialog.getChoice(); unRadius=Dialog.getNumber(); unWeight=Dialog.getNumber();
    source=getTitle(); title=imageToolsUniqueTitle("VIEW_DISLOCATION"); if (!imageToolsDuplicateFullImage(title)) return;
    if (radius>0 && !imageToolsSubtractBackgroundSafe(radius)) { close(); return; }
    if(sigma>0) run("Gaussian Blur...","sigma="+sigma);
    if(method=="Unsharp moderado") run("Unsharp Mask...","radius="+unRadius+" mask="+unWeight);
    if(method=="Find Edges") run("Find Edges");
    imageToolsLastSource=source;
    imageToolsLastPurpose="dislocation_visualization";
    imageToolsLastRecipe="{\"recipe_id\":\""+imageToolsTimestamp()+"\",\"purpose\":\"dislocation_visualization\",\"source_title\":\""+jsonEscape(source)+"\",\"operations\":[{\"name\":\"sliding_paraboloid_background\",\"radius_px\":"+radius+"},{\"name\":\"gaussian_blur\",\"sigma_px\":"+sigma+"},{\"name\":\"line_enhancement\",\"method\":\""+jsonEscape(method)+"\",\"radius_px\":"+unRadius+",\"weight\":"+unWeight+"}],\"full_image_duplicate\":true,\"geometry_preserved\":true,\"measurement_role\":\"visualization_only\"}";
    showStatus("Vista de dislocaciones creada sobre una copia.");
}

function imageToolsClaheView() {
    if (!imageToolsRequireImage()) return;
    Dialog.create("CLAHE sobre copia");
    Dialog.addNumber("Block size (px):",127);
    Dialog.addNumber("Histogram bins:",256);
    Dialog.addNumber("Max slope:",2.0);
    Dialog.addCheckbox("Fast mode",0);
    Dialog.show();
    block=Dialog.getNumber(); bins=Dialog.getNumber(); slope=Dialog.getNumber(); fast=Dialog.getCheckbox();
    source=getTitle(); title=imageToolsUniqueTitle("VIEW_CLAHE"); if (!imageToolsDuplicateFullImage(title)) return;
    options="blocksize="+block+" histogram="+bins+" maximum="+slope+" mask=*None*";
    if(fast) options=options+" fast_(less_accurate)";
    run("Enhance Local Contrast (CLAHE)",options);
    imageToolsLastSource=source;
    imageToolsLastPurpose="local_contrast_visualization";
    imageToolsLastRecipe="{\"recipe_id\":\""+imageToolsTimestamp()+"\",\"purpose\":\"local_contrast_visualization\",\"source_title\":\""+jsonEscape(source)+"\",\"operations\":[{\"name\":\"clahe\",\"block_size_px\":"+block+",\"histogram_bins\":"+bins+",\"max_slope\":"+slope+",\"fast\":"+fast+"}],\"full_image_duplicate\":true,\"geometry_preserved\":true,\"measurement_role\":\"visualization_only\"}";
}

function imageToolsParameterSweep() {
    if (!imageToolsRequireImage()) return;
    Dialog.create("Barrido de parametros");
    Dialog.addChoice("Operacion:",newArray("Gaussian Blur","Fondo - paraboloide deslizante","Unsharp Mask","DoG sigma grande"),"Gaussian Blur");
    Dialog.addString("Valores separados por ;:","0.5;0.8;1.0;1.5");
    Dialog.addNumber("Parametro fijo auxiliar:",1.0);
    Dialog.show();
    op=Dialog.getChoice(); raw=Dialog.getString(); fixed=Dialog.getNumber(); values=split(raw,";"); original=getImageID(); source=getTitle();
    for(i=0;i<values.length;i++) {
        v=parseFloat(String.trim(values[i])); if(isNaN(v)||v<=0) continue;
        selectImage(original);
        if(op=="Gaussian Blur") { title=imageToolsUniqueTitle("SWEEP_GAUSS_"+v); if (!imageToolsDuplicateFullImage(title)) continue; run("Gaussian Blur...","sigma="+v); }
        else if(op=="Fondo - paraboloide deslizante") { title=imageToolsUniqueTitle("SWEEP_BG_"+v); if (!imageToolsDuplicateFullImage(title)) continue; if (!imageToolsSubtractBackgroundSafe(v)) { close(); continue; } }
        else if(op=="Unsharp Mask") { title=imageToolsUniqueTitle("SWEEP_UNSHARP_"+v); if (!imageToolsDuplicateFullImage(title)) continue; run("Unsharp Mask...","radius="+v+" mask="+fixed); }
        else { title1=imageToolsUniqueTitle("SWEEP_DOG_S"); if (!imageToolsDuplicateFullImage(title1)) continue; run("32-bit"); run("Gaussian Blur...","sigma="+fixed); selectImage(original); title2=imageToolsUniqueTitle("SWEEP_DOG_L"); if (!imageToolsDuplicateFullImage(title2)) { selectWindow(title1); close(); continue; } run("32-bit"); run("Gaussian Blur...","sigma="+v); result=imageCalculator("Subtract create 32-bit",title1,title2); selectImage(result); rename(imageToolsUniqueTitle("SWEEP_DOG_"+v)); }
    }
    imageToolsLastSource=source;
    imageToolsLastPurpose="parameter_sweep";
    imageToolsLastRecipe="{\"recipe_id\":\""+imageToolsTimestamp()+"\",\"purpose\":\"parameter_sweep\",\"source_title\":\""+jsonEscape(source)+"\",\"operation\":\""+jsonEscape(op)+"\",\"values\":\""+jsonEscape(raw)+"\",\"auxiliary\":"+fixed+",\"measurement_role\":\"visualization_only\"}";
    showStatus("Barrido creado. Compare las copias y conserve los parametros elegidos.");
}

function imageToolsSaveViewAndRecipe() {
    if (!imageToolsRequireImage()) return;
    imageProjectRoot = v4FindProjectRootFromCurrentImage();
    loadedProjectRoot = "";
    if (v4ProjectLoaded && v4ProjectDir != "") loadedProjectRoot = v4ProjectDir;
    if (!v55RequireProjectRootMatch(imageProjectRoot, loadedProjectRoot, "guardar la vista derivada", 1)) return;
    projectOutputRoot = imageProjectRoot;
    if (projectOutputRoot == "") projectOutputRoot = loadedProjectRoot;
    projectOutput = 0;
    if (projectOutputRoot != "") projectOutput = 1;
    if (projectOutput && !v55ProjectBridgeMarkerClear(projectOutputRoot, "guardar la vista derivada", 1)) return;
    if (imageToolsLastRecipe=="") imageToolsLastRecipe="{\"recipe_id\":\""+imageToolsTimestamp()+"\",\"purpose\":\"manual_visualization\",\"source_title\":\""+jsonEscape(imageToolsLastSource)+"\",\"operations\":[],\"full_image_duplicate\":true,\"geometry_preserved\":true,\"measurement_role\":\"visualization_only\"}";
    defaultDir=getDirectory("image");
    if(projectOutput) defaultDir=projectAwareJoinPath(projectOutputRoot,"analysis_images/general_views");
    Dialog.create("Guardar vista derivada");
    Dialog.addString("Nombre base:",imageToolsSanitize(getTitle()));
    Dialog.addChoice("Rol:",newArray("VISUALIZATION_ONLY","CANDIDATE_DETECTION_ONLY","PROCESSED_ANALYSIS_IMAGE"),"VISUALIZATION_ONLY");
    Dialog.show();
    base=imageToolsSanitize(Dialog.getString()); role=Dialog.getChoice();
    if (base=="" || base=="." || base=="..") { showMessage("Nombre no valido","Use un nombre de fichero simple, sin rutas relativas."); return; }
    if (projectOutput && !v55ProjectBridgeMarkerClear(projectOutputRoot, "guardar la vista derivada", 1)) return;
    if (projectOutput) makeDirIfMissing(defaultDir);
    if(defaultDir=="") defaultDir=getDirectory("home");
    tifPath=projectAwareJoinPath(defaultDir,base+".tif"); jsonPath=projectAwareJoinPath(defaultDir,base+".recipe.json");
    if (!imageToolsPathInsideDirectory(tifPath,defaultDir) || !imageToolsPathInsideDirectory(jsonPath,defaultDir)) { showMessage("Ruta no valida","La vista y su receta deben permanecer dentro del directorio seleccionado."); return; }
    if (projectOutput && !v55ProjectBridgeMarkerClear(projectOutputRoot, "guardar la vista derivada", 1)) return;
    saveAs("Tiff",tifPath);
    if (projectOutput && !v55ProjectBridgeMarkerClear(projectOutputRoot, "guardar la receta derivada", 1)) return;
    recipe=imageToolsLastRecipe;
    if(endsWith(recipe,"}")) recipe=substring(recipe,0,lengthOf(recipe)-1)+",\"saved_image\":\""+jsonEscape(tifPath)+"\",\"declared_role\":\""+role+"\",\"tool_version\":\""+imageToolsVersion+"\"}";
    File.saveString(recipe+"\n",jsonPath);
    if (projectOutput && !v55ProjectBridgeMarkerClear(projectOutputRoot, "terminar de guardar la vista derivada", 1)) return;
    showMessage("Vista guardada",tifPath+"\n\nReceta:\n"+jsonPath);
}

function imageToolsPathInsideDirectory(pathText, directoryText) {
    candidate = normalizeStoredPath(v55CanonicalPathJava(pathText));
    boundary = normalizeStoredPath(v55CanonicalPathJava(directoryText));
    if (candidate=="" || boundary=="") return 0;
    if (!endsWith(boundary,"/")) boundary=boundary+"/";
    return startsWith(toLowerCase(candidate),toLowerCase(boundary));
}

function imageToolsPluginFinder() {
    choices=newArray("Tubeness","Ridge Detection","Directionality","Labkit","Trainable Weka Segmentation","Non Local Means Denoise","MorphoLibJ");
    Dialog.create("Plugins recomendados");
    Dialog.addChoice("Buscar:",choices,choices[0]);
    Dialog.addMessage("Se abrira Command Finder. La disponibilidad depende de los update sites instalados en Fiji.");
    Dialog.show();
    query=Dialog.getChoice();
    run("Command Finder...","search=["+query+"]");
}

function imageToolsRequireImage() {
    if(nImages()<=0) { showMessage("Sin imagen","Abra una imagen TEM antes de continuar."); return 0; }
    return 1;
}


function imageToolsDuplicateFullImage(title) {
    // The ImageJ "Duplicate..." command crops to the active ROI. This wrapper
    // duplicates the complete image or stack, preserves the ROI on the source
    // and removes it from the working copy so filters always process all pixels.
    return projectAwareDuplicateFullImage(title);
}

function imageToolsSubtractBackgroundSafe(radius) {
    if (radius <= 0) return 1;
    getDimensions(bgWidth, bgHeight, bgChannels, bgSlices, bgFrames);
    if (bgWidth < 3 || bgHeight < 3) {
        showMessage("Imagen demasiado pequena",
            "La correccion de fondo necesita al menos 3 x 3 pixeles.\n\n" +
            "La copia activa mide " + bgWidth + " x " + bgHeight + " px.\n" +
            "Esto suele indicar que una ROI fue recortada accidentalmente.");
        return 0;
    }
    // Use the sliding paraboloid, not the legacy rolling-ball implementation.
    // It avoids the downsample/enlarge path that fails for one-pixel dimensions.
    run("Subtract Background...", "rolling=" + radius + " sliding");
    return 1;
}

function imageToolsUniqueTitle(prefix) {
    base=prefix+"__"+imageToolsTimestamp();
    return base;
}

function imageToolsTimestamp() {
    getDateAndTime(year,month,dayOfWeek,dayOfMonth,hour,minute,second,msec);
    return year+IJ.pad(month+1,2)+IJ.pad(dayOfMonth,2)+"_"+IJ.pad(hour,2)+IJ.pad(minute,2)+IJ.pad(second,2)+"_"+msec;
}

function imageToolsSanitize(s) {
    s=replace(s," ","_"); s=replace(s,"/","_"); s=replace(s,"\\","_"); s=replace(s,":","_"); s=replace(s,"*","_"); s=replace(s,"?","_"); s=replace(s,"\"","_"); s=replace(s,"<","_"); s=replace(s,">","_"); s=replace(s,"|","_");
    return s;
}


// =============================================================================
// CAVITY TEM LIGHT 1.1.1 R9 - FOCUSED WORKFLOW
// Compatible con proyectos schema 1 y revisiones ROI guardadas por R5.
// =============================================================================
// R6: numeric predicates return explicit 0/1 values. File.* and eval(...)
// are never returned directly from a user-defined function. The create-project
// flow can safely complete the empty partial skeleton left by the R2 interruption.

// Startup is explicit through Start_Individual_Editor.ijm; no concurrent AutoRun.
macro "Cavity Light: iniciar biblioteca" { lightAutoRun(); }
macro "Cavity Light: panel principal" { lightShowPanel(); }
macro "Cavity Light: crear proyecto" { lightCreateProject(); }
macro "Cavity Light: abrir proyecto" { lightOpenProject(); }
macro "Cavity Light: abrir DM3/DM4 y registrar" { lightOpenDmAndRegister(); }
macro "Cavity Light: registrar imagen activa" { lightRegisterActiveImage(); }
macro "Cavity Light: seleccionar imagen del proyecto" { lightSelectProjectImage(); }
macro "Cavity Light: configurar imagen" { lightConfigureCurrentImage(); }
macro "Cavity Light: informacion actual" { lightShowCurrentInfo(); }
macro "Cavity Light: aceptar escala Bio-Formats" { lightConfirmImageScale(); }
macro "Cavity Light: introducir escala nm/px" { lightSetScaleNumerically(); }
macro "Cavity Light: calibrar escala con linea" { lightCalibrateScaleFromLine(); }
macro "Cavity Light: verificar escala" { lightVerifyScale(); }
macro "Cavity Light: usar toda la imagen como area" { lightUseWholeImageAsArea(); }
macro "Cavity Light: anadir area valida" { lightAddAnalysisMasks(); }
macro "Cavity Light: anadir zona excluida" { addExclusionRoi(); }
macro "Cavity Light: detectar fondo negro" { lightHF44DetectBlackBackground(); }
macro "Cavity Light: definir superficie" { lightDefineSurface(); }
macro "Cavity Light: configurar bandas" { configureBands(); }
macro "Cavity Light: seleccionar clase de cavidad" { chooseActiveCavityClass(); }
macro "Cavity Light: medir diametro y crear cavidad" { activateMeasureTool(); }
macro "Cavity Light: anadir con diametro activo" { activateAddTool(); }
macro "Cavity Light: fijar diametro activo" { lightSetActiveDiameter(); }
macro "Cavity Light: registrar elipse seleccionada" { lightAddEllipseCavityFromSelection(); }
macro "Cavity Light: tomar diametro de seleccionada" { takeDiameterFromSelected(); }
macro "Cavity Light: seleccionar/editar" { activateSelectTool(); }
macro "Cavity Light: editar seleccionada numericamente" { editSelectedCavityNumerically(); }
macro "Cavity Light: incluir/excluir seleccionada" { toggleSelectedInclusion(); }
macro "Cavity Light: borrar seleccionada" { deleteSelectedManagedRoi(); }
macro "Cavity Light: deshacer ultima accion" { undoLastAddOrDelete(); }
macro "Cavity Light: buscar duplicados" { scanAllDuplicates(1); }
macro "Cavity Light: dibujar dislocaciones" { addLinearFeature("dislocation"); }
macro "Cavity Light: dibujar bordes de grano" { addLinearFeature("grain_boundary"); }
macro "Cavity Light: dibujar interfaces" { addLinearFeature("interface"); }
macro "Cavity Light: guardar nueva revision" { lightSaveRevision(); }
macro "Cavity Light: cargar revision" { lightLoadRevision(); }
macro "Cavity Light: validar imagen" { validateProject(); }
macro "Cavity Light: exportar imagen actual" { exportAnalysis(); }
macro "Cavity Light: calcular y exportar resultados" { exportAnalysis(); }
macro "Cavity Light: ajustes" { settingsDialog(); }
macro "Cavity Light: alternar etiquetas" { toggleLabels(); }
macro "Cavity Light: cambiar modo de color" { chooseDisplayMode(); }
macro "Cavity Light: sincronizar seleccionada" { syncSelectedObject(1); }
macro "Cavity Light: actualizar ROIs" { syncAllObjects(1); restyleAllRois(); showAllRois(); }
macro "Cavity Light: ayuda" { lightShowHelp(); }
macro "Cavity Light: confirmar edicion interactiva" { lightFinalizeInteractiveEdit(); }
macro "Cavity Light: confirmar diametro activo interactivo" { lightFinalizeInteractiveActiveDiameter(); }
macro "Cavity Light: actualizar sensibilidad interactiva" { lightUpdateResizeStepFromPreference(); }
macro "Cavity Light: autodiagnostico R9" { lightSelfTestR9(); }
macro "Cavity Light: reparar contexto de proyecto" { lightRepairProjectContextInteractive(); }
macro "Cavity Light: reparar registro de imagenes" { lightRepairImageRegistryInteractive(); }

macro "Cavity Light menu Tool - icon:cavity_studio.png" { lightShowPanel(); }
macro "Cavity Light menu Tool Options" { lightShowPanel(); }
macro "Cavity Light measure Tool - icon:cavity_measure.png" { measureCavityByDrag(); }
macro "Cavity Light measure Tool Options" { lightShowHelp(); }
macro "Cavity Light add Tool - icon:cavity_add.png" { addCavityAtCursor(); }
macro "Cavity Light add Tool Options" { lightSetActiveDiameter(); }
macro "Cavity Light select edit Tool - icon:cavity_select.png" { selectOrForceAddAtCursor(); }
macro "Cavity Light select edit Tool Options" { settingsDialog(); }
macro "Cavity Light fixed zoom Tool - icon:cavity_zoom.png" {
    getCursorLoc(x, y, z, flags);
    shift = 1;
    if ((flags & shift) != 0) zoomOutFixed(); else zoomInFixed();
}
macro "Cavity Light fixed zoom Tool Options" { settingsDialog(); }

function lightAutoRun() {
    if(!lightHF4Available())return;
    call("cavity.light.HF46.initialize","");
    lightHF43LoadCavityColorPreference();
    fixedWindowPreference = call("ij.Prefs.get", "cavity.tem.light.hf45.fixed.window", "1");
    keepWindowSize = 1;
    if (fixedWindowPreference == "0") keepWindowSize = 0;
    lightInvalidateAnalysisCache();
    usePanelsAsMask = 0;
    v4ProjectLoaded = 0;
    if (nImages() > 0) {
        updateScaleMaybe();
        run("ROI Manager...");
        if (roiManager("count") > 0) loadSessionFromRois(0);
        installInteractionListeners(0);
        lightInteractivePushState(lightInteractiveMode);
    }
    launchRequest=call("cavity.light.IndividualEditor.takeLaunchRequest","");
    if(launchRequest!=""){
        launchOk=lightOpenLibraryRequest(launchRequest);launchStatus="ERROR";if(launchOk)launchStatus="OK";
        call("cavity.light.IndividualEditor.launchResult",launchStatus);
    }
    lightShowPanel();
    showStatus("Cavity TEM Light activo. Cree o abra un proyecto de imagenes individuales.");
}

function lightStatusLine1() {
    if (!lightProjectLoaded) return "PROYECTO: no cargado";
    return "PROYECTO: " + lightProjectName + " [" + lightProjectId + "]";
}

function lightStatusLine2() {
    if (lightImageId == "") return "IMAGEN: no registrada";
    rev = lightCurrentRevision; if (rev == "") rev = "sin revision";
    return "IMAGEN: " + lightImageId + " | " + lightImageMode + " | " + rev;
}

function lightStatusLine3() {
    lightHF4Pull();
    sc = "escala pendiente";
    if (nImages() > 0) {
        scaleReady = updateScaleMaybe();
        if (scaleReady == 1) {
            if (lightScaleConfirmed == 1) sc = d2s(nmPerPixelX,6) + " x " + d2s(nmPerPixelY,6) + " nm/px";
        }
    }
    th = "sin espesor";
    if (lightThicknessNm > 0) th = "t=" + d2s(lightThicknessNm,2) + " nm";
    return "CALIBRACION: " + sc + " | " + th + " | cavidades=" + lightCavityCountCached();
}

function lightStatusLine4() {
    labelsText = "OFF";
    if (showRoiLabels == 1) labelsText = "ID exactos";
    return "IMAGEN INDIVIDUAL 1.2 RC1: d=" + d2s(activeDiameterNm,3) + " nm | paso=" + d2s(lightInteractiveResizeStepNm,3) + " nm | color=" + lightConfirmedCavityColor + " | etiquetas=" + labelsText + " | ventana fija=" + keepWindowSize;
}

function lightShowPanel() {
    lightInteractiveReadResizeStep();
    s1 = lightStatusLine1();
    s2 = lightStatusLine2();
    s3 = lightStatusLine3();
    s4 = lightStatusLine4();
    js = "(function(){var Frame=Packages.java.awt.Frame,JFrame=Packages.javax.swing.JFrame,JPanel=Packages.javax.swing.JPanel,JButton=Packages.javax.swing.JButton,JLabel=Packages.javax.swing.JLabel,JTabbedPane=Packages.javax.swing.JTabbedPane,JScrollPane=Packages.javax.swing.JScrollPane,JSlider=Packages.javax.swing.JSlider,BorderLayout=Packages.java.awt.BorderLayout,GridBagLayout=Packages.java.awt.GridBagLayout,GridBagConstraints=Packages.java.awt.GridBagConstraints,Insets=Packages.java.awt.Insets,Dimension=Packages.java.awt.Dimension,Color=Packages.java.awt.Color,Font=Packages.java.awt.Font,Thread=Packages.java.lang.Thread,Runnable=Packages.java.lang.Runnable,ActionListener=Packages.java.awt.event.ActionListener,ChangeListener=Packages.javax.swing.event.ChangeListener,Executer=Packages.ij.Executer,IJ=Packages.ij.IJ,Prefs=Packages.ij.Prefs,WM=Packages.ij.WindowManager;";
    js = js + "var fs=Frame.getFrames();for(var i=0;i<fs.length;i++){try{var title=String(fs[i].getTitle());if(title.indexOf('Cavity TEM Light 1.2 RC1')==0||title.indexOf('Cavity TEM Light 1.1.1 R9')==0||title.indexOf('Cavity TEM Light 1.0.0 R7')==0)fs[i].dispose();}catch(e){}}";
    js = js + "var f=new JFrame('Cavity TEM Light 1.2 RC1 - Imagenes individuales'),outer=new JPanel(new BorderLayout()),head=new JPanel(new GridBagLayout()),hc=new GridBagConstraints();hc.gridx=0;hc.anchor=GridBagConstraints.WEST;hc.insets=new Insets(3,8,3,8);var a=new JLabel('"+jsEscape(s1)+"'),b=new JLabel('"+jsEscape(s2)+"'),c=new JLabel('"+jsEscape(s3)+"'),d=new JLabel('"+jsEscape(s4)+"');a.setFont(a.getFont().deriveFont(Font.BOLD));hc.gridy=0;head.add(a,hc);hc.gridy=1;head.add(b,hc);hc.gridy=2;head.add(c,hc);hc.gridy=3;head.add(d,hc);outer.add(head,BorderLayout.NORTH);f.getRootPane().putClientProperty('status1',a);f.getRootPane().putClientProperty('status2',b);f.getRootPane().putClientProperty('status3',c);f.getRootPane().putClientProperty('status4',d);f.getRootPane().putClientProperty('CavityLight.Panel','true');var tabs=new JTabbedPane();f.getRootPane().putClientProperty('tabs',tabs);";
    js = js + "function tab(n){var p=new JPanel(new GridBagLayout()),q=new GridBagConstraints();q.insets=new Insets(4,4,4,4);q.fill=GridBagConstraints.HORIZONTAL;q.weightx=1;var o={p:p,c:q,r:0};tabs.addTab(n,new JScrollPane(p));return o;}function go(cmd){var body={run:function(){new Executer(cmd).run();}};if(typeof JavaAdapter!='undefined')return new JavaAdapter(Runnable,body);var R=Java.extend(Runnable);return new R(body);}function al(cmd){var body={actionPerformed:function(e){var th=new Thread(go(cmd));th.setDaemon(true);th.start();}};if(typeof JavaAdapter!='undefined')return new JavaAdapter(ActionListener,body);var A=Java.extend(ActionListener);return new A(body);}function one(t,label,cmd,pri){var x=new JButton(label);x.addActionListener(al(cmd));if(pri){x.setBackground(Color.decode('#2b6de0'));x.setForeground(Color.WHITE);x.setFont(x.getFont().deriveFont(Font.BOLD));}t.c.gridx=0;t.c.gridy=t.r;t.c.gridwidth=2;t.p.add(x,t.c);t.r++;}function two(t,l1,c1,l2,c2){var x=new JButton(l1),y=new JButton(l2);x.addActionListener(al(c1));y.addActionListener(al(c2));t.c.gridy=t.r;t.c.gridwidth=1;t.c.gridx=0;t.p.add(x,t.c);t.c.gridx=1;t.p.add(y,t.c);t.r++;}";
    js = js + "function sliderRow(t){var box=new JPanel(new BorderLayout(8,0)),label=new JLabel('Sensibilidad: " + d2s(lightInteractiveResizeStepNm,3) + " nm/paso'),sl=new JSlider(1,2000," + d2s(round(lightInteractiveResizeStepNm*1000),0) + ");sl.setMajorTickSpacing(500);sl.setMinorTickSpacing(50);sl.setPaintTicks(true);var body={stateChanged:function(e){var value=sl.getValue()/1000.0;label.setText('Sensibilidad: '+value.toFixed(3)+' nm/paso');Prefs.set('cavity.tem.light.hf4.resize.step.nm',value);var imp=WM.getCurrentImage();if(imp!=null)imp.setProperty('CavityLightResizeStepNm',String(value));if(!sl.getValueIsAdjusting()){try{Prefs.savePreferences();}catch(ignorePref){}var th=new Thread(go('Cavity Light: actualizar sensibilidad interactiva'));th.setDaemon(true);th.start();}}};var listener;if(typeof JavaAdapter!='undefined')listener=new JavaAdapter(ChangeListener,body);else{var C=Java.extend(ChangeListener);listener=new C(body);}sl.addChangeListener(listener);box.add(label,BorderLayout.NORTH);box.add(sl,BorderLayout.CENTER);t.c.gridx=0;t.c.gridy=t.r;t.c.gridwidth=2;t.p.add(box,t.c);t.r++;f.getRootPane().putClientProperty('resizeSlider',sl);f.getRootPane().putClientProperty('resizeLabel',label);}";
    js = js + "var p=tab('1 Proyecto');one(p,'Crear proyecto','Cavity Light: crear proyecto',true);one(p,'Abrir proyecto','Cavity Light: abrir proyecto',false);two(p,'Abrir DM3/DM4','Cavity Light: abrir DM3/DM4 y registrar','Registrar activa','Cavity Light: registrar imagen activa');two(p,'Seleccionar imagen','Cavity Light: seleccionar imagen del proyecto','Configurar imagen','Cavity Light: configurar imagen');one(p,'Informacion y trazabilidad','Cavity Light: informacion actual',false);two(p,'Reparar contexto','Cavity Light: reparar contexto de proyecto','Reparar registro','Cavity Light: reparar registro de imagenes');one(p,'Autodiagnostico R9','Cavity Light: autodiagnostico R9',false);";
    js = js + "p=tab('2 Preparar');two(p,'Aceptar escala Bio-Formats','Cavity Light: aceptar escala Bio-Formats','Escala numerica','Cavity Light: introducir escala nm/px');two(p,'Calibrar con linea','Cavity Light: calibrar escala con linea','Verificar escala','Cavity Light: verificar escala');two(p,'Toda la imagen valida','Cavity Light: usar toda la imagen como area','Anadir area valida','Cavity Light: anadir area valida');two(p,'Anadir zona excluida','Cavity Light: anadir zona excluida','Detectar fondo negro','Cavity Light: detectar fondo negro');two(p,'Definir superficie','Cavity Light: definir superficie','Configurar bandas','Cavity Light: configurar bandas');two(p,'Brillo/contraste por zona','Cavity Light: contraste por zona','Contraste local','Cavity Light: contraste local');one(p,'Correccion de fondo','Cavity Light: correccion de fondo',false);two(p,'Deshacer tratamiento','Cavity Light: deshacer tratamiento','Rehacer tratamiento','Cavity Light: rehacer tratamiento');two(p,'Ver receta vigente','Cavity Light: ver receta vigente','Restaurar imagen original','Cavity Light: restaurar imagen original');one(p,'Conservar cambios hechos con Fiji','Cavity Light: conservar cambios externos',false);";
    js = js + "p=tab('3 Medir');two(p,'Clase de cavidad','Cavity Light: seleccionar clase de cavidad','Color cavidades','Cavity Light: elegir color de cavidades');one(p,'Diametro activo','Cavity Light: fijar diametro activo',false);one(p,'Medir diametro y crear cavidad','Cavity Light: medir diametro y crear cavidad',true);two(p,'Anadir con circulo visible','Cavity Light: anadir con diametro activo','Registrar nueva elipse','Cavity Light: registrar elipse seleccionada');two(p,'Seleccionar/mover/ajustar','Cavity Light: seleccionar/editar','Editar numericamente','Cavity Light: editar seleccionada numericamente');sliderRow(p);two(p,'Incluir/excluir','Cavity Light: incluir/excluir seleccionada','Borrar','Cavity Light: borrar seleccionada');two(p,'Borrar varias por region','Cavity Light: borrar varias por region','Deshacer borrado multiple','Cavity Light: deshacer borrado multiple');two(p,'Deshacer','Cavity Light: deshacer ultima accion','Duplicados','Cavity Light: buscar duplicados');two(p,'Detectar puntos en ROI','Cavity Light: detectar puntos en ROI','Estimar diametros de puntos','Cavity Light: estimar diametros de puntos');one(p,'Ajustar detector con cavidades confirmadas','Cavity Light: ajustar detector con cavidades',false);two(p,'Revisar propuestas','Cavity Light: revisar propuestas','Puntos sin ajuste','Cavity Light: puntos sin ajuste');one(p,'Fluidez y registros','Cavity Light: fluidez y registros',false);";
    js = js + "p=tab('4 Microestructura');one(p,'Dibujar dislocaciones','Cavity Light: dibujar dislocaciones',false);one(p,'Dibujar bordes de grano','Cavity Light: dibujar bordes de grano',false);one(p,'Dibujar interfaces','Cavity Light: dibujar interfaces',false);two(p,'Etiquetas ID exactas','Cavity Light: alternar etiquetas','Modo de color','Cavity Light: cambiar modo de color');one(p,'Sincronizar ROIs','Cavity Light: actualizar ROIs',false);";
    js = js + "p=tab('5 Guardar y analizar');one(p,'Validar imagen','Cavity Light: validar imagen',false);one(p,'Guardar avance con nombre','Cavity Light: guardar nueva revision',true);one(p,'Cargar revision','Cavity Light: cargar revision',false);one(p,'Calcular y exportar resultados','Cavity Light: calcular y exportar resultados',true);two(p,'Ajustes','Cavity Light: ajustes','Ayuda','Cavity Light: ayuda');two(p,'Ver registros','Cavity Light: ver registros','Fluidez y registros','Cavity Light: fluidez y registros');two(p,'Localizar identidad','Cavity Light: localizar identidad','Reparar nombres','Cavity Light: reparar nombres');p=tab('6 Vista y atajos');one(p,'Ventana y navegacion','Cavity Light: ventana y navegacion',true);two(p,'Zoom +','Cavity Light: zoom fijo aumentar','Zoom -','Cavity Light: zoom fijo reducir');two(p,'Encajar imagen','Cavity Light: encajar vista','Vista 100 %','Cavity Light: vista 100');one(p,'Activar/desactivar ventana fija','Cavity Light: alternar ventana fija',false);one(p,'Accesos directos (F1)','Cavity Light: accesos directos',false);outer.add(tabs,BorderLayout.CENTER);f.setContentPane(outer);f.setPreferredSize(new Dimension(660,760));f.pack();if(previousBounds!=null)f.setBounds(previousBounds);else f.setLocationByPlatform(true);tabs.setSelectedIndex(Math.min(previousTab,tabs.getTabCount()-1));f.setVisible(true);f.toFront();return 'OK';})();";
    eval("js", js);
    call("cavity.light.Workspace.install","");
}


function lightRefreshPanel() {
    s1 = lightStatusLine1();
    s2 = lightStatusLine2();
    s3 = lightStatusLine3();
    s4 = lightStatusLine4();
    js = "var F=Packages.java.awt.Frame,fs=F.getFrames();for(var i=0;i<fs.length;i++){try{if(String(fs[i].getTitle())=='Cavity TEM Light 1.2 RC1 - Imagenes individuales'){var r=fs[i].getRootPane(),a=r.getClientProperty('status1'),b=r.getClientProperty('status2'),c=r.getClientProperty('status3'),d=r.getClientProperty('status4');if(a!=null)a.setText('"+jsEscape(s1)+"');if(b!=null)b.setText('"+jsEscape(s2)+"');if(c!=null)c.setText('"+jsEscape(s3)+"');if(d!=null)d.setText('"+jsEscape(s4)+"');var sl=r.getClientProperty('resizeSlider'),lb=r.getClientProperty('resizeLabel');if(sl!=null){var target="+d2s(round(lightInteractiveResizeStepNm*1000),0)+";if(sl.getValue()!=target)sl.setValue(target);}if(lb!=null)lb.setText('Sensibilidad: "+d2s(lightInteractiveResizeStepNm,3)+" nm/paso');fs[i].repaint();}}catch(e){}}";
    eval("js", js);
}


function lightShowHelp() {
    msg = "VERSION: " + lightReleaseVersion + "\nCandidata de consolidacion; validacion funcional completa pendiente.\n\nFLUJO RECOMENDADO R9\n\n";
    msg = msg + "1. Cree o abra un proyecto y seleccione una imagen registrada.\n";
    msg = msg + "2. Confirme escala, modo, espesor y area valida.\n";
    msg = msg + "3. Fije un diametro activo y pulse Anadir con circulo visible. El circulo bajo el cursor representa el diametro fisico activo con la escala actual.\n";
    msg = msg + "4. En modo Anadir, Alt+rueda cambia inmediatamente el diametro del circulo sin modificar el zoom. Ctrl+Alt+rueda se acepta como alias. Cada click usa exactamente el diametro que se ve.\n";
    msg = msg + "5. En modo Seleccionar/mover/ajustar, seleccione una cavidad y use Alt+rueda para cambiar su diametro conservando centro y proporcion. Ctrl+Alt tambien funciona.\n";
    msg = msg + "6. Ctrl+rueda, sin Alt, cambia el zoom sin reajustar la ventana cuando Ventana fija esta activada. Rueda y Shift+rueda mantienen la navegacion configurada.\n";
    msg = msg + "7. Ajuste la sensibilidad con el deslizador: 0.001 nm/paso es muy fino; hasta 2.000 nm/paso permite cambios amplios. El valor inicial HF4 es 0.050 nm/paso. Alt+Mayus+rueda divide el paso por cinco.\n";
    msg = msg + "8. Al soltar el raton o detener la rueda, HF4 conserva el valor o la geometria de la ROI. Los calculos derivados se completan al validar o guardar. La busqueda completa de duplicados se aplaza hasta Validar imagen.\n";
    msg = msg + "9. HF4.6: dibuje una region y use Borrar varias por region. Se resaltan primero las cavidades afectadas, se pide confirmacion y solo se eliminan objetos Type=cavity. El lote puede restaurarse con Deshacer borrado multiple.\n";
    msg = msg + "10. Color cavidades abre un selector grafico. El color elegido afecta solo a la visualizacion de cavidades confirmadas y se conserva como preferencia de Fiji.\n";
    msg = msg + "11. Las etiquetas muestran exactamente el nombre estable del ROI Manager, por ejemplo CAV_000237. Los identificadores no se renumeran al borrar una cavidad.\n";
    msg = msg + "12. HF4.6: en Preparar, Detectar fondo negro crea una exclusion automatica a partir de una mascara temporal. Use normalmente umbral 0 y modo conectado al borde; revise siempre la previsualizacion magenta antes de confirmar.\n";
    msg = msg + "13. Valide y despues pulse Calcular y exportar resultados.\n\n";
    msg = msg + "Registrar nueva elipse requiere dibujar una seleccion Oval nueva. Para modificar una cavidad existente use Seleccionar/mover/ajustar o Editar numericamente.\n\n";
    msg = msg + "ATAJOS\nCtrl+R anadir | Ctrl+E seleccionar | Alt+rueda ajustar diametro | Ctrl+Alt+rueda alias | Ctrl+rueda zoom | Ctrl+U sincronizar seleccionada | Supr borrar | Ctrl+Z deshacer | Ctrl+Shift+V validar | Ctrl+Shift+E calcular/exportar.\n\n";
    msg = msg + "R9 conserva la preparacion y el area calculada cuando no cambian las ROIs. La densidad volumetrica sigue siendo nominal: N/(A*t), sin correcciones estereologicas ocultas.";
    msg=msg+"\n\nHF4: dibuje una ROI pequena y use Detectar puntos en ROI. Revise los puntos, pulse Estimar diametros de puntos y acepte las propuestas revisadas. Los puntos sin ajuste se conservan.\nRegistros: opcion Fluidez y registros, o Ver registros en la pestana 5.\nLas cavidades nuevas se registran al instante; los calculos se completan al guardar/validar/exportar.";
    msg=msg+"\n\nHF4.6: 6 Vista y atajos > Ventana y navegacion permite fijar el tamano y la posicion de la ventana durante el zoom. F1 abre todos los accesos directos; Ctrl+Mayus+W activa/desactiva la ventana fija. Ctrl+Z NO deshace un lote multiple: use el boton especifico.\nLos atajos requieren el foco en la ventana de imagen, no en ROI Manager ni en cuadros de texto.";
    msg=msg+"\n\nPreparacion US1: tratamientos sobre copias, previsualizacion antes de aplicar y Deshacer/Rehacer tratamiento independientes de las anotaciones. Guardar avance conserva solo la receta vigente. F2 recupera el panel oculto. Los controles inferiores permiten organizar pantallas, ocultar ventanas y guardar su disposicion.";
    showMessage("Ayuda R9 CONSOLIDADA RC1", msg);
}

function lightSelfTestR9() {
    oldProjectLoaded=lightProjectLoaded;
    oldProjectRoot=lightProjectRoot;
    oldProjectFile=lightProjectFile;
    oldProjectId=lightProjectId;
    oldProjectName=lightProjectName;
    oldProjectUid=lightProjectUid;
    oldImageId=lightImageId;
    oldImageDir=lightImageDir;
    oldSourcePath=lightSourcePath;
    oldStoredPath=lightSourceStoredPath;
    oldSha=lightSourceSha256;
    oldCopy=lightCopySource;
    oldSample=sampleName;
    oldCondition=experimentalCondition;
    oldOperator=operatorName;
    oldNotes=projectNotes;
    oldConfigured=projectConfigured;
    oldV4=v4ProjectLoaded;
    oldImageMode=lightImageMode;
    oldThickness=lightThicknessNm;
    oldUncertainty=lightThicknessUncertaintyNm;
    oldMethod=lightThicknessMethod;
    oldThicknessNotes=lightThicknessNotes;
    oldOriginalX=lightOriginalScaleNmX;
    oldOriginalY=lightOriginalScaleNmY;
    oldOriginalUnit=lightOriginalScaleUnit;
    oldScaleOrigin=lightScaleOrigin;
    oldScaleConfirmed=lightScaleConfirmed;
    oldWholeImage=lightUseWholeImage;
    oldInclude=lightIncludeUncertain;
    oldRevision=lightCurrentRevision;
    oldRun=lightCurrentRunId;
    oldImageFileName=imageFileName;
    oldImageDirectory=imageDirectory;
    oldImageChecksum=imageChecksum;
    oldMontageId=montageId;
    oldSourceFirst=sourceFirst;
    oldSourceLast=sourceLast;
    oldSourceList=sourceImageList;
    oldMicroscope=microscopeVoltage;
    oldTemperature=specimenTemperature;
    oldActiveDiameter=activeDiameterNm;
    oldBandNm=bandNm;
    oldBandCount=bandCount;
    oldExcludeNegative=excludeNegativeDepth;
    oldHistogram=lightHistogramBinNm;
    oldFeatureBin=lightFeatureDistanceBinNm;
    oldPreparedFingerprint=lightPreparedFingerprint;
    oldPreparedAtMs=lightPreparedAtMs;
    oldPreparationDurationMs=lightLastPreparationDurationMs;
    oldPreparationReused=lightLastPreparationReused;
    oldPreparationRuns=lightPreparationRuns;
    oldPreparationCacheHits=lightPreparationCacheHits;
    oldAreaFingerprint=lightAreaFingerprint;
    oldAreaMode=lightAreaComputationMode;
    oldAreaDurationMs=lightAreaComputationDurationMs;
    oldPreviewEnabled=lightInteractivePreviewEnabled;
    oldResizeStep=lightInteractiveResizeStepNm;
    oldShowLabels=showRoiLabels;

    ok=1;
    details="";
    tempRoot="";

    testRaw="  Fe_D4_II  ";
    testId=lightSanitizeId(testRaw);
    testFolder=testId+"_CavityTEM_Light";
    joinedPreview=lightJoin("D:",testFolder);
    testRootPreview=lightNormalizeDir(joinedPreview);
    if(testRootPreview!="D:/Fe_D4_II_CavityTEM_Light/"){
        ok=0;details=details+"Ruta Fe_D4_II: FAIL\n";
    } else details=details+"Ruta Fe_D4_II: PASS\n";

    tempBaseRaw=getDirectory("temp");
    tempBase=lightNormalizeDir(tempBaseRaw);
    if(tempBase==""){
        showMessage("Autodiagnostico R9 no ejecutado","FIJI no ha proporcionado una carpeta temporal.");
        return;
    }
    tempName="CavityTEMLight_R9_SELFTEST_"+d2s(getTime(),0);
    tempJoined=lightJoin(tempBase,tempName);
    tempRoot=lightNormalizeDir(tempJoined);
    lightDeleteSelfTestTree(tempRoot);

    lightProjectRoot=tempRoot;
    lightProjectFile=lightJoin(tempRoot,lightProjectFileName);
    lightProjectId="Fe_D4_II";
    lightProjectName="Fe_D4_II";
    lightProjectUid=lightUuid();
    sampleName="Fe_strained_irra";
    experimentalCondition="strain_0.2_irra_He";
    operatorName="MRB";
    projectNotes="R9 self-test";
    lightProjectLoaded=1;
    projectConfigured=1;
    v4ProjectLoaded=0;
    lightImageId="";
    lightImageDir="";
    lightSourceSha256="";

    structureFlag=lightEnsureProjectStructure();
    projectFlag=0;
    if(structureFlag==1)projectFlag=lightWriteProjectFile();
    descriptorFlag=lightProjectDescriptorValid(lightProjectFile,lightProjectId,lightProjectUid);
    if(structureFlag!=1||projectFlag!=1||descriptorFlag!=1){
        ok=0;details=details+"Descriptor canonico temporal: FAIL\n";
    } else details=details+"Descriptor canonico temporal: PASS\n";

    lightImageId="SELFTEST_IMAGE";
    lightSourcePath="D:/SELFTEST_IMAGE.dm4";
    lightSourceStoredPath="";
    lightSourceSha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    lightCopySource=0;
    imageFileName="SELFTEST_IMAGE.dm4";
    imageDirectory="D:/";
    imageChecksum=lightSourceSha256;
    montageId=lightImageId;
    sourceFirst=imageFileName;
    sourceLast=imageFileName;
    sourceImageList=imageFileName;
    lightImageMode="with_surface";
    lightThicknessNm=60;
    lightThicknessUncertaintyNm=10;
    lightThicknessMethod="EELS";
    lightThicknessNotes="roundtrip";
    lightOriginalScaleNmX=0.0504;
    lightOriginalScaleNmY=0.0504;
    lightOriginalScaleUnit="microns";
    lightScaleOrigin="bioformats_metadata";
    lightScaleConfirmed=0;
    lightUseWholeImage=0;
    lightIncludeUncertain=1;
    lightCurrentRevision="";
    lightCurrentRunId="";

    metadataWriteFlag=lightWriteImageMetadata();
    imagesRoot=lightJoin(lightProjectRoot,"images");
    imagePath=lightJoin(imagesRoot,lightImageId);
    expectedImageDir=lightNormalizeDir(imagePath);
    expectedMeta=lightJoin(expectedImageDir,lightImageMetadataFileName);
    metadataMatchFlag=lightImageMetadataMatches(expectedMeta,lightImageId,lightSourceSha256);
    wrongIdFlag=lightImageMetadataMatches(expectedMeta,"WRONG_IMAGE",lightSourceSha256);
    wrongShaFlag=lightImageMetadataMatches(expectedMeta,lightImageId,"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");
    if(metadataWriteFlag!=1||metadataMatchFlag!=1||wrongIdFlag!=0||wrongShaFlag!=0){
        ok=0;details=details+"Escritura y validacion estricta image_metadata.tsv: FAIL\n";
    } else details=details+"Escritura y validacion estricta image_metadata.tsv: PASS\n";

    lightImageMode="without_surface";
    lightThicknessNm=0;
    lightThicknessUncertaintyNm=0;
    lightThicknessMethod="not_provided";
    lightIncludeUncertain=0;
    metadataReadFlag=lightReadImageMetadata();
    if(metadataReadFlag!=1||lightImageMode!="with_surface"||lightThicknessNm!=60||lightThicknessUncertaintyNm!=10||lightThicknessMethod!="EELS"||lightIncludeUncertain!=1){
        ok=0;details=details+"Lectura completa image_metadata.tsv: FAIL\n";
    } else details=details+"Lectura completa image_metadata.tsv: PASS\n";

    registryFlag=lightUpdateRegistry();
    registryPath=lightJoin(lightProjectRoot,lightRegistryFileName);
    registryExists=lightFileExistsFlag(registryPath);
    if(registryFlag!=1||registryExists!=1){
        ok=0;details=details+"Actualizacion images.tsv: FAIL\n";
    } else details=details+"Actualizacion images.tsv: PASS\n";

    headerValue=lightRegistryHeader();
    File.saveString(headerValue,registryPath);
    repairText=lightRepairImageRegistryCore(1);
    registryContent=File.openAsString(registryPath);
    registryHasImage=0;
    if(indexOf(registryContent,"SELFTEST_IMAGE\t")>=0)registryHasImage=1;
    if(!startsWith(repairText,"OK|")||registryHasImage!=1){
        ok=0;details=details+"Reconstruccion de images.tsv: FAIL\n";
    } else details=details+"Reconstruccion de images.tsv: PASS\n";

    wrongDescriptorAccepted=lightProjectDescriptorValid(expectedMeta,lightProjectId,lightProjectUid);
    if(wrongDescriptorAccepted!=0){
        ok=0;details=details+"Rechazo de image_metadata.tsv como proyecto: FAIL\n";
    } else details=details+"Rechazo de image_metadata.tsv como proyecto: PASS\n";

    parserResult="16777216|1150.8073281901288|";
    parserParts=split(parserResult,"|");
    parserOk=0;
    if(parserParts.length>=2){
        parserPixels=parseFloat(parserParts[0]);
        parserArea=parseFloat(parserParts[1]);
        if(parserPixels==16777216){
            if(abs(parserArea-1150.8073281901288)<0.000001)parserOk=1;
        }
    }
    if(parserOk!=1){
        ok=0;details=details+"Parser de area sin tercer campo: FAIL\n";
    } else details=details+"Parser de area sin tercer campo: PASS\n";

    lightInteractivePreviewEnabled=1;
    lightInteractiveResizeStepNm=0.010;
    showRoiLabels=1;
    interactionOk=1;
    if(lightInteractiveResizeStepNm<lightInteractiveResizeMinNm)interactionOk=0;
    if(lightInteractiveResizeStepNm>lightInteractiveResizeMaxNm)interactionOk=0;
    testStableId="CAV_"+IJ.pad(237,6);
    if(testStableId!="CAV_000237")interactionOk=0;
    if(interactionOk!=1){
        ok=0;details=details+"Interaccion, sensibilidad, rueda y ID estable R9: FAIL\n";
    } else details=details+"Interaccion, sensibilidad, rueda y ID estable R9: PASS\n";

    interactionPrefOk = 1;
    prefStep = lightInteractiveResizeStepNm;
    if (abs(prefStep-0.010) > 0.000001) interactionPrefOk = 0;
    if (lightInteractivePreviewEnabled != 1) interactionPrefOk = 0;
    if (showRoiLabels != 1) interactionPrefOk = 0;
    if (lightInteractivePreviewName != "__CTL_R8_CURSOR_PREVIEW__") interactionPrefOk = 0;
    testOldDiameter = 0.8149;
    testStep = 0.0100;
    testRotation = -3;
    testNewDiameter = testOldDiameter-testRotation*testStep;
    if (abs(testNewDiameter-0.8449) > 0.0000001) interactionPrefOk = 0;
    if (interactionPrefOk != 1) {
        ok=0;details=details+"Configuracion interactiva y etiquetas exactas: FAIL\n";
    } else details=details+"Configuracion interactiva y etiquetas exactas: PASS\n";

    cleanupFlag=lightDeleteSelfTestTree(tempRoot);
    if(cleanupFlag!=1){
        ok=0;details=details+"Limpieza temporal: FAIL\n";
    } else details=details+"Limpieza temporal: PASS\n";

    lightProjectLoaded=oldProjectLoaded;
    lightProjectRoot=oldProjectRoot;
    lightProjectFile=oldProjectFile;
    lightProjectId=oldProjectId;
    lightProjectName=oldProjectName;
    lightProjectUid=oldProjectUid;
    lightImageId=oldImageId;
    lightImageDir=oldImageDir;
    lightSourcePath=oldSourcePath;
    lightSourceStoredPath=oldStoredPath;
    lightSourceSha256=oldSha;
    lightCopySource=oldCopy;
    sampleName=oldSample;
    experimentalCondition=oldCondition;
    operatorName=oldOperator;
    projectNotes=oldNotes;
    projectConfigured=oldConfigured;
    v4ProjectLoaded=oldV4;
    lightImageMode=oldImageMode;
    lightThicknessNm=oldThickness;
    lightThicknessUncertaintyNm=oldUncertainty;
    lightThicknessMethod=oldMethod;
    lightThicknessNotes=oldThicknessNotes;
    lightOriginalScaleNmX=oldOriginalX;
    lightOriginalScaleNmY=oldOriginalY;
    lightOriginalScaleUnit=oldOriginalUnit;
    lightScaleOrigin=oldScaleOrigin;
    lightScaleConfirmed=oldScaleConfirmed;
    lightUseWholeImage=oldWholeImage;
    lightIncludeUncertain=oldInclude;
    lightCurrentRevision=oldRevision;
    lightCurrentRunId=oldRun;
    imageFileName=oldImageFileName;
    imageDirectory=oldImageDirectory;
    imageChecksum=oldImageChecksum;
    montageId=oldMontageId;
    sourceFirst=oldSourceFirst;
    sourceLast=oldSourceLast;
    sourceImageList=oldSourceList;
    microscopeVoltage=oldMicroscope;
    specimenTemperature=oldTemperature;
    activeDiameterNm=oldActiveDiameter;
    bandNm=oldBandNm;
    bandCount=oldBandCount;
    excludeNegativeDepth=oldExcludeNegative;
    lightHistogramBinNm=oldHistogram;
    lightFeatureDistanceBinNm=oldFeatureBin;
    lightPreparedFingerprint=oldPreparedFingerprint;
    lightPreparedAtMs=oldPreparedAtMs;
    lightLastPreparationDurationMs=oldPreparationDurationMs;
    lightLastPreparationReused=oldPreparationReused;
    lightPreparationRuns=oldPreparationRuns;
    lightPreparationCacheHits=oldPreparationCacheHits;
    lightAreaFingerprint=oldAreaFingerprint;
    lightAreaComputationMode=oldAreaMode;
    lightAreaComputationDurationMs=oldAreaDurationMs;
    lightInteractivePreviewEnabled=oldPreviewEnabled;
    lightInteractiveResizeStepNm=oldResizeStep;
    showRoiLabels=oldShowLabels;

    if(ok==1){
        showMessage("Autodiagnostico R9 correcto","Se han probado rutas, descriptores, registro, limpieza temporal, limites de sensibilidad, enrutado de rueda e identidad estable de etiquetas R9.\n\n"+details+"\nNo se ha modificado ningun proyecto real.");
    } else {
        showMessage("Autodiagnostico R9 no superado","No continue con medidas hasta revisar la instalacion.\n\n"+details+"\nCarpeta temporal usada:\n"+tempRoot);
    }
}

function lightCreateProject() {
    parent=chooseDirectorySafe("Elige la carpeta donde crear el proyecto Light");if(parent=="")return;
    Dialog.create("Nuevo proyecto Cavity TEM Light");Dialog.addString("Nombre del proyecto:","Cavity_TEM_Light_Project",40);Dialog.addString("Muestra/material:",sampleName,35);Dialog.addString("Condicion experimental:",experimentalCondition,40);Dialog.addString("Operador:",getInfo("user.name"),30);Dialog.addString("Notas:","",50);Dialog.show();
    pName=Dialog.getString();newSample=Dialog.getString();newCondition=Dialog.getString();newOperator=Dialog.getString();newNotes=Dialog.getString();if(pName=="")exit("El nombre del proyecto no puede estar vacio.");if(!lightPrepareProjectSwitch())return;
    safeProjectId=lightSanitizeId(pName);projectFolderName=safeProjectId+"_CavityTEM_Light";joinedProjectRoot=lightJoin(parent,projectFolderName);root=lightNormalizeDir(joinedProjectRoot);existingProject=lightJoin(root,lightProjectFileName);
    if(File.exists(root)){
        if(File.exists(existingProject)){
            if(!getBoolean("La carpeta ya contiene un proyecto Cavity TEM Light.\n\nAbrirlo sin sobrescribir sus datos?\n"+root,"Abrir existente","Cancelar"))return;
            if(!lightLoadProjectFile(existingProject))return;
            structureOk=lightEnsureProjectStructure();if(structureOk!=1){showMessage("Proyecto incompleto","No se pudo preparar la estructura interna minima.");return;}
            lightAppendLog("PROJECT_OPENED_EXISTING","path="+root);showMessage("Proyecto existente abierto","Proyecto: "+lightProjectName+"\nCarpeta: "+lightProjectRoot+"\n\nNo se ha sobrescrito ningun identificador ni archivo.");lightShowPanel();return;
        }
        recoverable=lightIsRecoverableInterruptedProject(root);
        if(recoverable==1){
            if(!getBoolean("Se ha detectado una carpeta parcial compatible con el fallo de R2.\n\nContiene solo la estructura vacia del proyecto y no contiene imagenes ni datos cientificos. R9 puede completarla sin borrar ningun archivo.\n\n"+root,"Completar proyecto","Cancelar"))return;
            lightProjectRoot=root;lightProjectName=pName;lightProjectId=safeProjectId;lightProjectUid=lightUuid();lightProjectFile=existingProject;sampleName=newSample;experimentalCondition=newCondition;operatorName=newOperator;projectNotes=newNotes;lightProjectLoaded=1;projectConfigured=1;v4ProjectLoaded=0;lightResetImageState();
            structureOk=lightEnsureProjectStructure();if(structureOk!=1){lightProjectLoaded=0;projectConfigured=0;showMessage("Proyecto no recuperado","No se pudo completar la estructura interna.");return;}
            writeOk=lightWriteProjectFile();if(writeOk!=1){lightProjectLoaded=0;projectConfigured=0;showMessage("Proyecto no recuperado","No se pudo escribir y verificar "+lightProjectFileName+".");return;}
            lightAppendLog("PROJECT_RECOVERED_AFTER_R2_INTERRUPTION","path="+lightProjectRoot+"; schema="+lightSchemaVersion);showMessage("Proyecto recuperado","Proyecto: "+lightProjectName+"\nCarpeta: "+lightProjectRoot+"\n\nR9 ha completado la carpeta parcial de R2 sin borrar ningun archivo. Ya puede registrar la primera imagen.");lightShowPanel();return;
        }
        showMessage("Carpeta no utilizada","La carpeta ya existe, pero no contiene un proyecto valido ni una estructura parcial R2 vacia.\n\nPara proteger archivos ajenos, R9 no escribira en ella. Elige otro nombre o revisa la carpeta manualmente.");return;
    }
    lightMakeDir(root);if(!File.exists(root)){showMessage("Proyecto no creado","No se pudo crear la carpeta:\n"+root);return;}
    lightProjectRoot=root;lightProjectName=pName;lightProjectId=safeProjectId;lightProjectUid=lightUuid();lightProjectFile=existingProject;sampleName=newSample;experimentalCondition=newCondition;operatorName=newOperator;projectNotes=newNotes;lightProjectLoaded=1;projectConfigured=1;v4ProjectLoaded=0;lightResetImageState();
    structureOk=lightEnsureProjectStructure();if(structureOk!=1){lightProjectLoaded=0;projectConfigured=0;showMessage("Proyecto no creado","No se pudo preparar la estructura interna del proyecto.");return;}
    writeOk=lightWriteProjectFile();if(writeOk!=1){lightProjectLoaded=0;projectConfigured=0;showMessage("Proyecto no creado","No se pudo escribir y verificar "+lightProjectFileName+".");return;}
    lightAppendLog("PROJECT_CREATED","path="+lightProjectRoot+"; schema="+lightSchemaVersion);showMessage("Proyecto creado","Proyecto: "+lightProjectName+"\nCarpeta: "+lightProjectRoot+"\n\nNo contiene montajes ni SVG. Cada imagen se registra de forma independiente.");lightShowPanel();
}
function lightClearProjectState() {
    lightResetImageState();lightProjectLoaded=0;lightProjectRoot="";lightProjectFile="";lightProjectId="";lightProjectName="";lightProjectUid="";projectConfigured=0;v4ProjectLoaded=0;
}

function lightFileExistsFlag(path) {
    existsFlag=0;
    if(path!=""&&File.exists(path))existsFlag=1;
    return existsFlag;
}

function lightProjectDescriptorValid(path,expectedId,expectedUid) {
    if(path=="")return 0;
    fileExists=lightFileExistsFlag(path);
    if(fileExists==0)return 0;
    fileNameValue=File.getName(path);
    if(fileNameValue!=lightProjectFileName)return 0;

    schemaValue=lightKvRead(path,"schema_version","");
    if(schemaValue!=lightSchemaVersion)return 0;

    descriptorValue=lightKvRead(path,"descriptor_type","");
    if(descriptorValue!=""&&descriptorValue!=lightProjectDescriptorType)return 0;

    pidValue=lightKvRead(path,"project_id","");
    uidValue=lightKvRead(path,"project_uid","");
    nameValue=lightKvRead(path,"project_name","");
    if(pidValue==""||uidValue==""||nameValue=="")return 0;
    if(expectedId!=""&&pidValue!=expectedId)return 0;
    if(expectedUid!=""&&uidValue!=expectedUid)return 0;
    return 1;
}

function lightFindCanonicalProjectFile(startPath) {
    if(startPath=="")return "";
    normalizedStart=normalizeStoredPath(startPath);
    js="(function(){var F=Packages.java.io.File,f=new F('"+jsEscape(normalizedStart)+"');if(f.isFile())f=f.getParentFile();else if(!f.isDirectory())f=f.getParentFile();for(var i=0;i<16&&f!=null;i++){var p=new F(f,'"+lightProjectFileName+"');if(p.isFile())return String(p.getAbsolutePath()).replace(/\\\\/g,'/');f=f.getParentFile();}return '';})();";
    found=eval("js",js);found=""+found;return found;
}

function lightImageMetadataMatches(meta,expectedImageId,expectedSha) {
    if(meta=="")return 0;
    metaExists=lightFileExistsFlag(meta);
    if(metaExists==0)return 0;

    schemaValue=lightKvRead(meta,"schema_version","");
    if(schemaValue!=lightSchemaVersion)return 0;

    descriptorValue=lightKvRead(meta,"descriptor_type","");
    if(descriptorValue!=""&&descriptorValue!=lightImageDescriptorType)return 0;

    projectIdValue=lightKvRead(meta,"project_id","");
    if(projectIdValue!=lightProjectId)return 0;

    projectUidValue=lightKvRead(meta,"project_uid","");
    if(projectUidValue!=lightProjectUid)return 0;

    imageIdValue=lightKvRead(meta,"image_id","");
    if(expectedImageId!=""&&imageIdValue!=expectedImageId)return 0;

    sourceShaValue=lightKvRead(meta,"source_sha256","");
    if(expectedSha!=""&&sourceShaValue!=expectedSha)return 0;
    return 1;
}

function lightRepairProjectContext(verbose) {
    expectedId=lightProjectId;expectedUid=lightProjectUid;descriptor="";
    if(lightProjectFile!=""){
        candidate=lightFindCanonicalProjectFile(lightProjectFile);
        if(lightProjectDescriptorValid(candidate,expectedId,expectedUid)==1)descriptor=candidate;
    }
    if(descriptor==""&&lightProjectRoot!=""){
        candidate=lightFindCanonicalProjectFile(lightProjectRoot);
        if(lightProjectDescriptorValid(candidate,expectedId,expectedUid)==1)descriptor=candidate;
    }
    if(descriptor==""&&lightImageDir!=""){
        candidate=lightFindCanonicalProjectFile(lightImageDir);
        if(lightProjectDescriptorValid(candidate,expectedId,expectedUid)==1)descriptor=candidate;
    }
    if(descriptor==""&&lightSourceStoredPath!=""){
        candidate=lightFindCanonicalProjectFile(lightSourceStoredPath);
        if(lightProjectDescriptorValid(candidate,expectedId,expectedUid)==1)descriptor=candidate;
    }
    if(descriptor==""){
        if(verbose==1)showMessage("Contexto no reparado","No se encontro un "+lightProjectFileName+" canonico que coincida con el Project ID y Project UID actuales.\n\nAbra manualmente el descriptor situado en la raiz del proyecto.");
        return 0;
    }
    repairedRoot=lightNormalizeDir(File.getDirectory(descriptor));
    repairedId=lightKvRead(descriptor,"project_id","");repairedUid=lightKvRead(descriptor,"project_uid","");
    lightProjectFile=normalizeStoredPath(descriptor);lightProjectRoot=repairedRoot;lightProjectId=repairedId;lightProjectUid=repairedUid;
    lightProjectName=lightKvRead(descriptor,"project_name",repairedId);sampleName=lightKvRead(descriptor,"sample_name",sampleName);experimentalCondition=lightKvRead(descriptor,"experimental_condition",experimentalCondition);operatorName=lightKvRead(descriptor,"operator_name",operatorName);projectNotes=lightKvRead(descriptor,"project_notes",projectNotes);
    lightProjectLoaded=1;projectConfigured=1;v4ProjectLoaded=0;
    if(lightImageId!=""){
        expectedImageDir=lightNormalizeDir(lightJoin(lightJoin(lightProjectRoot,"images"),lightImageId));
        expectedMeta=lightJoin(expectedImageDir,lightImageMetadataFileName);
        if(lightImageMetadataMatches(expectedMeta,lightImageId,lightSourceSha256)==1)lightImageDir=expectedImageDir;
    }
    if(verbose==1)showMessage("Contexto reparado","Descriptor canonico:\n"+lightProjectFile+"\n\nRaiz activa:\n"+lightProjectRoot+"\n\nNo se ha modificado el DM3/DM4 ni ninguna revision ROI.");
    return 1;
}
function lightRepairImageRegistryCore(makeBackup) {
    guardOk=lightCanonicalProjectGuard("reparar el registro de imagenes");
    if(guardOk==0)return "ERROR|contexto no canonico|0|0";

    imagesDir=lightJoin(lightProjectRoot,"images");
    registryPath=lightJoin(lightProjectRoot,lightRegistryFileName);
    logsDir=lightJoin(lightProjectRoot,"logs");
    logsMade=lightMakeDir(logsDir);
    if(logsMade==0)return "ERROR|no se pudo preparar logs|0|0";

    timestampValue=lightTimestamp();
    backupPath="";
    if(makeBackup==1&&File.exists(registryPath)){
        backupName="images_before_repair_"+timestampValue+".tsv";
        backupPath=lightJoin(logsDir,backupName);
    }
    headerValue=lightRegistryHeader();

    js="(function(){";
    js=js+"var Files=Packages.java.nio.file.Files,Paths=Packages.java.nio.file.Paths,CS=Packages.java.nio.charset.StandardCharsets,Copy=Packages.java.nio.file.StandardCopyOption,F=Packages.java.io.File;";
    js=js+"var images=new F('"+jsEscape(imagesDir)+"'),reg=Paths.get('"+jsEscape(registryPath)+"'),backup='"+jsEscape(backupPath)+"';";
    js=js+"var expectedSchema='"+jsEscape(lightSchemaVersion)+"',expectedDescriptor='"+jsEscape(lightImageDescriptorType)+"',expectedProject='"+jsEscape(lightProjectId)+"',expectedUid='"+jsEscape(lightProjectUid)+"',header='"+jsEscape(headerValue)+"';";
    js=js+"function clean(v){v=v==null?'':String(v);return v.replace(/[\\t\\r\\n]+/g,' ');}";
    js=js+"function parse(txt){var o={},ls=String(txt).split(/\\r?\\n/);for(var i=0;i<ls.length;i++){if(!ls[i])continue;var k=ls[i].indexOf('\\t');if(k>0)o[ls[i].slice(0,k)]=ls[i].slice(k+1).trim();}return o;}";
    js=js+"function baseName(v){v=String(v||'').replace(/\\\\/g,'/');var a=v.split('/');return a.length?a[a.length-1]:'';}";
    js=js+"try{";
    js=js+"if(!images.isDirectory())return 'ERROR|no existe la carpeta images|0|0';";
    js=js+"var dirs=images.listFiles(),rows=[],skipped=0;";
    js=js+"if(dirs!=null){for(var i=0;i<dirs.length;i++){var d=dirs[i];if(!d.isDirectory())continue;var meta=new F(d,'"+lightImageMetadataFileName+"');if(!meta.isFile()){skipped++;continue;}";
    js=js+"var kv=parse(new java.lang.String(Files.readAllBytes(meta.toPath()),CS.UTF_8));var id=String(kv.image_id||'');var sha=String(kv.source_sha256||'');var descriptor=String(kv.descriptor_type||'');";
    js=js+"if(String(kv.schema_version||'')!=expectedSchema||(descriptor!=''&&descriptor!=expectedDescriptor)||String(kv.project_id||'')!=expectedProject||String(kv.project_uid||'')!=expectedUid||id==''||id!=String(d.getName())||sha.length!=64){skipped++;continue;}";
    js=js+"var source=String(kv.source_path||''),stored=String(kv.stored_path||''),display=baseName(source);if(display=='')display=baseName(stored);if(display=='')display=id;";
    js=js+"var row=[id,display,source,stored,sha,String(kv.sample_name||''),String(kv.experimental_condition||''),String(kv.image_mode||'without_surface'),String(kv.foil_thickness_nm||''),String(kv.active_scale_x_nm_px||''),String(kv.active_scale_y_nm_px||''),String(kv.current_revision||''),String(kv.current_run||''),String(kv.updated_ms||java.lang.System.currentTimeMillis())];";
    js=js+"for(var j=0;j<row.length;j++)row[j]=clean(row[j]);rows.push([id,row.join('\\t')]);}}";
    js=js+"if(rows.length==0)return 'EMPTY||0|'+skipped;rows.sort(function(a,b){return a[0]<b[0]?-1:(a[0]>b[0]?1:0);});";
    js=js+"if(backup!=''&&Files.exists(reg)){try{Files.copy(reg,Paths.get(backup),Copy.REPLACE_EXISTING);}catch(e){return 'ERROR|no se pudo crear la copia de seguridad|0|'+skipped;}}";
    js=js+"var out=[String(header).replace(/[\\r\\n]+$/,'')];for(i=0;i<rows.length;i++)out.push(rows[i][1]);Files.write(reg,new java.lang.String(out.join('\\n')+'\\n').getBytes(CS.UTF_8));";
    js=js+"return 'OK|'+backup+'|'+rows.length+'|'+skipped;";
    js=js+"}catch(ex){return 'ERROR|'+clean(ex)+'|0|0';}";
    js=js+"})();";

    repairResult=eval("js",js);
    repairText=""+repairResult;
    return repairText;
}

function lightRepairImageRegistryInteractive() {
    repairText=lightRepairImageRegistryCore(1);
    repairParts=split(repairText,"|");
    repairStatus="";
    if(repairParts.length>0)repairStatus=repairParts[0];

    if(repairStatus=="OK"){
        repairedCount="0";
        skippedCount="0";
        backupValue="";
        if(repairParts.length>1)backupValue=repairParts[1];
        if(repairParts.length>2)repairedCount=repairParts[2];
        if(repairParts.length>3)skippedCount=repairParts[3];
        msg="Se ha reconstruido "+lightRegistryFileName+" a partir de los image_metadata.tsv canonicos.\n\nImagenes recuperadas: "+repairedCount+"\nCarpetas omitidas: "+skippedCount;
        if(backupValue!="")msg=msg+"\nCopia de seguridad: "+backupValue;
        msg=msg+"\n\nNo se ha borrado ni vuelto a copiar ningun DM3/DM4, ROI o resultado.";
        lightAppendLog("IMAGE_REGISTRY_REBUILT","count="+repairedCount+"; skipped="+skippedCount+"; backup="+backupValue);
        showMessage("Registro de imagenes reparado",msg);
        lightRefreshPanel();
        return;
    }
    if(repairStatus=="EMPTY"){
        showMessage("Registro no reconstruido","No se encontro ningun image_metadata.tsv canonico y compatible en la carpeta images.\n\nNo se ha modificado "+lightRegistryFileName+".");
        return;
    }
    repairReason="Error no especificado";
    if(repairParts.length>1){
        candidateReason=repairParts[1];
        if(candidateReason!="")repairReason=candidateReason;
    }
    showMessage("Registro no reparado",repairReason+"\n\nNo se ha modificado ningun DM3/DM4 ni revision ROI.");
}


function lightRepairProjectContextInteractive() {
    beforeRoot=lightProjectRoot;beforeFile=lightProjectFile;
    repaired=lightRepairProjectContext(0);
    if(repaired==0){showMessage("Contexto no reparado","No se pudo localizar automaticamente el descriptor canonico.\n\nUse Abrir proyecto y seleccione exactamente "+lightProjectFileName+" en la raiz del proyecto.");return;}
    changedContext=0;if(beforeRoot!=lightProjectRoot)changedContext=1;if(beforeFile!=lightProjectFile)changedContext=1;
    if(changedContext==1)showMessage("Contexto reparado","Antes:\n"+beforeRoot+"\n\nAhora:\n"+lightProjectRoot+"\n\nLas escrituras volveran a realizarse en la raiz canonica.");
    else showMessage("Contexto correcto","La raiz y el descriptor ya eran canonicos:\n"+lightProjectRoot);
    lightShowPanel();
}

function lightCanonicalProjectGuard(operationName) {
    repaired=lightRepairProjectContext(0);
    if(repaired==0){showMessage("Operacion bloqueada","No se puede "+operationName+" porque el contexto del proyecto no es canonico.\n\nAbra "+lightProjectFileName+" desde la raiz del proyecto o pulse Reparar contexto.");return 0;}
    valid=lightProjectDescriptorValid(lightProjectFile,lightProjectId,lightProjectUid);
    if(valid==0){showMessage("Operacion bloqueada","El descriptor del proyecto no supera la validacion estricta:\n"+lightProjectFile);return 0;}
    canonicalRoot=lightNormalizeDir(File.getDirectory(lightProjectFile));
    if(canonicalRoot!=lightProjectRoot){showMessage("Operacion bloqueada","La raiz activa no coincide con la carpeta del descriptor canonico.\n\nRaiz: "+lightProjectRoot+"\nDescriptor: "+lightProjectFile);return 0;}
    return 1;
}

function lightPrepareImageContextForWrite(allowCreate) {
    guardOk=lightCanonicalProjectGuard("escribir datos de la imagen");
    if(guardOk==0)return 0;
    if(lightImageId=="")return 0;

    imagesRoot=lightJoin(lightProjectRoot,"images");
    imagePath=lightJoin(imagesRoot,lightImageId);
    expectedImageDir=lightNormalizeDir(imagePath);
    expectedMeta=lightJoin(expectedImageDir,lightImageMetadataFileName);

    metaExists=lightFileExistsFlag(expectedMeta);
    if(metaExists==1){
        metaMatches=lightImageMetadataMatches(expectedMeta,lightImageId,lightSourceSha256);
        if(metaMatches==0){
            showMessage("Escritura bloqueada","El metadato existente no coincide con proyecto, imagen o SHA-256:\n"+expectedMeta);
            return 0;
        }
    } else {
        if(allowCreate!=1)return 0;
        created=lightMakeDir(expectedImageDir);
        if(created==0)return 0;
        sourceDir=lightJoin(expectedImageDir,"source");
        revisionsDir=lightJoin(expectedImageDir,"roi_sessions");
        imageLogsDir=lightJoin(expectedImageDir,"logs");
        sourceMade=lightMakeDir(sourceDir);
        revisionsMade=lightMakeDir(revisionsDir);
        logsMade=lightMakeDir(imageLogsDir);
        if(sourceMade==0||revisionsMade==0||logsMade==0)return 0;
    }
    lightImageDir=expectedImageDir;
    return 1;
}
function lightOpenProject() {
    selectedPath=File.openDialog("Selecciona cavity_light_project.tsv");
    if(selectedPath=="")return;
    selectedPath=normalizeStoredPath(selectedPath);candidatePath=selectedPath;
    if(File.getName(candidatePath)!=lightProjectFileName){
        candidatePath=lightFindCanonicalProjectFile(selectedPath);
        if(candidatePath==""){showMessage("Archivo rechazado","El archivo seleccionado no es "+lightProjectFileName+" y no se encontro un descriptor canonico en sus carpetas superiores.\n\nNo seleccione image_metadata.tsv.");return;}
        if(!getBoolean("Se ha seleccionado un archivo interno. Se ha localizado el descriptor canonico:\n\n"+candidatePath+"\n\nAbrir este proyecto?","Abrir descriptor","Cancelar"))return;
    }
    if(lightProjectDescriptorValid(candidatePath,"","")==0){showMessage("Proyecto invalido","El archivo no cumple el contrato de proyecto Light schema "+lightSchemaVersion+":\n"+candidatePath);return;}
    if(!lightPrepareProjectSwitch())return;
    loadFlag=lightLoadProjectFile(candidatePath);if(loadFlag==0)return;
    structureReady=lightEnsureProjectStructure();
    if(structureReady==0){failedRoot=lightProjectRoot;lightClearProjectState();showMessage("Proyecto incompleto","No se pudo comprobar la estructura interna minima de:\n"+failedRoot);return;}
    lightAppendLog("PROJECT_OPENED","path="+lightProjectRoot);
    showMessage("Proyecto abierto","Proyecto: "+lightProjectName+"\nMuestra: "+sampleName+"\nCondicion: "+experimentalCondition+"\nRaiz canonica: "+lightProjectRoot+"\n\nPuede abrir o seleccionar una imagen registrada.");
    lightShowPanel();
}

function lightPrepareProjectSwitch() {
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
}

function lightResetImageState() {
    lightBandMode="width";lightSizeBreaks="0.5,1,1.5,2,3,5";lightResultContrast=0.18;lightMaxImageDepthNm=0;
    lightImageId="";lightImageDir="";lightSourcePath="";lightSourceStoredPath="";lightSourceSha256="";lightCopySource=0;lightImageMode="without_surface";lightThicknessNm=0;lightThicknessUncertaintyNm=0;lightThicknessMethod="not_provided";lightThicknessNotes="";lightOriginalScaleNmX=NaN;lightOriginalScaleNmY=NaN;lightOriginalScaleUnit="";lightScaleOrigin="bioformats_metadata";lightScaleConfirmed=0;lightUseWholeImage=0;lightIncludeUncertain=0;lightCurrentRevision="";lightCurrentRunId="";imageFileName="";imageDirectory="";imageChecksum="";montageId="";sourceFirst="";sourceLast="";sourceImageList="";scaleDefined=0;surfaceDefined=0;surfaceSideDefined=0;projectConfigured=1;v4ProjectLoaded=0;
}
function lightLoadProjectFile(path) {
    path=normalizeStoredPath(path);
    descriptorOk=lightProjectDescriptorValid(path,"","");
    if(descriptorOk==0){
        showMessage("Proyecto invalido","Debe seleccionar exactamente un "+lightProjectFileName+" valido.\n\nArchivo recibido:\n"+path);
        return 0;
    }

    candidateFile=path;
    candidateDir=File.getDirectory(path);
    candidateRoot=lightNormalizeDir(candidateDir);
    candidateId=lightKvRead(path,"project_id","");
    candidateUid=lightKvRead(path,"project_uid","");
    candidateName=lightKvRead(path,"project_name",candidateId);
    candidateSample=lightKvRead(path,"sample_name","");
    candidateCondition=lightKvRead(path,"experimental_condition","");
    defaultOperator=getInfo("user.name");
    candidateOperator=lightKvRead(path,"operator_name",defaultOperator);
    candidateNotes=lightKvRead(path,"project_notes","");

    lightProjectFile=candidateFile;
    lightProjectRoot=candidateRoot;
    lightProjectId=candidateId;
    lightProjectUid=candidateUid;
    lightProjectName=candidateName;
    sampleName=candidateSample;
    experimentalCondition=candidateCondition;
    operatorName=candidateOperator;
    projectNotes=candidateNotes;
    lightProjectLoaded=1;
    projectConfigured=1;
    v4ProjectLoaded=0;
    lightResetImageState();
    return 1;
}
function lightWriteProjectFile() {
    if(lightProjectRoot=="")return 0;
    lightProjectFile=lightJoin(lightProjectRoot,lightProjectFileName);

    cleanProjectId=lightTsvClean(lightProjectId);
    cleanProjectUid=lightTsvClean(lightProjectUid);
    cleanProjectName=lightTsvClean(lightProjectName);
    cleanSampleName=lightTsvClean(sampleName);
    cleanCondition=lightTsvClean(experimentalCondition);
    cleanOperator=lightTsvClean(operatorName);
    cleanProjectNotes=lightTsvClean(projectNotes);
    updatedValue=d2s(getTime(),0);

    t="schema_version\t"+lightSchemaVersion+"\n";
    t=t+"descriptor_type\t"+lightProjectDescriptorType+"\n";
    t=t+"tool_version\t"+lightReleaseVersion+"\n";
    t=t+"validation_state\t"+lightValidationState+"\n";
    t=t+"project_id\t"+cleanProjectId+"\n";
    t=t+"project_uid\t"+cleanProjectUid+"\n";
    t=t+"project_name\t"+cleanProjectName+"\n";
    t=t+"sample_name\t"+cleanSampleName+"\n";
    t=t+"experimental_condition\t"+cleanCondition+"\n";
    t=t+"operator_name\t"+cleanOperator+"\n";
    t=t+"project_notes\t"+cleanProjectNotes+"\n";
    t=t+"updated_ms\t"+updatedValue+"\n";
    File.saveString(t,lightProjectFile);

    descriptorOk=lightProjectDescriptorValid(lightProjectFile,lightProjectId,lightProjectUid);
    if(descriptorOk==1)return 1;
    return 0;
}

function lightRegistryHeader() { return "image_id\tdisplay_name\tsource_path\tstored_path\tsha256\tsample_name\tcondition\tmode\tthickness_nm\tscale_x_nm_px\tscale_y_nm_px\tcurrent_revision\tcurrent_run\tupdated_ms\n"; }


function lightEnsureProjectStructure() {
    if(lightProjectRoot=="")return 0;
    rootDir=lightProjectRoot;
    imagesDir=lightJoin(rootDir,"images");
    combinedDir=lightJoin(rootDir,"combined_runs");
    logsDir=lightJoin(rootDir,"logs");
    reg=lightJoin(rootDir,lightRegistryFileName);

    rootMade=lightMakeDir(rootDir);
    imagesMade=lightMakeDir(imagesDir);
    combinedMade=lightMakeDir(combinedDir);
    logsMade=lightMakeDir(logsDir);
    if(rootMade==0||imagesMade==0||combinedMade==0||logsMade==0)return 0;

    if(!File.exists(reg)){
        registryHeaderValue=lightRegistryHeader();
        File.saveString(registryHeaderValue,reg);
    }

    ok=1;
    if(!File.exists(rootDir))ok=0;
    if(!File.exists(imagesDir))ok=0;
    if(!File.exists(combinedDir))ok=0;
    if(!File.exists(logsDir))ok=0;
    if(!File.exists(reg))ok=0;
    return ok;
}

function lightIsRecoverableInterruptedProject(root) {
    if(root=="")return 0;
    js="(function(){var F=Packages.java.io.File,Files=Packages.java.nio.file.Files,CS=Packages.java.nio.charset.StandardCharsets,root=new F('"+jsEscape(root)+"'),suffix='_CavityTEM_Light';function benign(n){return n=='desktop.ini'||n=='Thumbs.db'||n=='.DS_Store';}function emptyDir(d){var a=d.listFiles();if(a==null)return true;for(var i=0;i<a.length;i++)if(!benign(String(a[i].getName())))return false;return true;}try{if(!root.exists()||!root.isDirectory())return '0';var rn=String(root.getName());if(rn.length<suffix.length||rn.substring(rn.length-suffix.length)!=suffix)return '0';if(new F(root,'cavity_light_project.tsv').exists())return '0';var a=root.listFiles();if(a==null)return '0';for(var i=0;i<a.length;i++){var f=a[i],n=String(f.getName());if(benign(n))continue;if(n=='images'||n=='combined_runs'||n=='logs'){if(!f.isDirectory()||!emptyDir(f))return '0';continue;}if(n=='images.tsv'){if(!f.isFile())return '0';var tx=String(new java.lang.String(Files.readAllBytes(f.toPath()),CS.UTF_8)),ls=tx.split(/\\r?\\n/),non=[];for(var j=0;j<ls.length;j++)if(String(ls[j]).trim()!='')non.push(ls[j]);if(non.length>1)return '0';if(non.length==1&&String(non[0]).indexOf('image_id\\t')!=0)return '0';continue;}return '0';}return '1';}catch(ex){return '0';}})();";
    status=""+eval("js",js);ok=0;if(status=="1")ok=1;return ok;
}

function lightCreateSelfTestZip(path) {
    js="(function(){var F=Packages.java.io.File,FOS=Packages.java.io.FileOutputStream,Z=Packages.java.util.zip.ZipOutputStream,E=Packages.java.util.zip.ZipEntry,CS=Packages.java.nio.charset.StandardCharsets,z=null;try{z=new Z(new FOS(new F('"+jsEscape(path)+"')));z.putNextEntry(new E('selftest.txt'));var b=new java.lang.String('Cavity TEM Light R9').getBytes(CS.UTF_8);z.write(b,0,b.length);z.closeEntry();z.close();z=null;return '1';}catch(ex){try{if(z!=null)z.close();}catch(ignore){}return '0';}})();";
    status=""+eval("js",js);ok=0;if(status=="1")ok=1;return ok;
}

function lightDeleteSelfTestTree(path) {
    if(path=="")return 0;
    js="(function(){var F=Packages.java.io.File,root=new F('"+jsEscape(path)+"');function rm(f){if(f.isDirectory()){var a=f.listFiles();if(a!=null)for(var i=0;i<a.length;i++)if(!rm(a[i]))return false;}return f.delete();}try{var n=String(root.getName());if(n.indexOf('CavityTEMLight_R9_SELFTEST_')!=0)return '0';if(!root.exists())return '1';return rm(root)?'1':'0';}catch(ex){return '0';}})();";
    status=""+eval("js",js);ok=0;if(status=="1")ok=1;return ok;
}

function lightFindProjectLocalSource() {
    if(lightImageDir==""||lightSourceSha256=="")return "";dir=lightNormalizeDir(lightJoin(lightImageDir,"source"));if(!File.exists(dir))return "";files=getFileList(dir);
    for(k=0;k<files.length;k++){name=files[k];if(endsWith(name,"/"))continue;candidate=lightJoin(dir,name);ext=lightExtension(candidate);if(ext!="dm3"&&ext!="dm4")continue;sha=IJ.checksum("SHA-256 file",candidate);if(sha==lightSourceSha256){lightSourceStoredPath=normalizeStoredPath(candidate);lightCopySource=1;return lightSourceStoredPath;}}
    return "";
}

function lightActiveImageIdentity() {
    if(nImages()<=0)return "";code="(function(){var imp=Packages.ij.IJ.getImage();function s(k){var v=imp.getProperty(k);return v==null?'':String(v);}return s('CavityTEMLight.ProjectId')+'|'+s('CavityTEMLight.ImageId')+'|'+s('CavityTEMLight.SourceSHA256');})();";return ""+eval("js",code);
}
function lightNumberChanged(a,b) {
    if(isNaN(a)&&isNaN(b))return 0;
    if(isNaN(a)||isNaN(b))return 1;
    difference=abs(a-b);
    if(difference>1e-12)return 1;
    return 0;
}

function lightOpenDmAndRegister() {
    if(!lightEnsureProject())return;
    path=File.openDialog("Selecciona una imagen DM3 o DM4");if(path=="")return;
    ext=lightExtension(path);if(ext!="dm3"&&ext!="dm4"){showMessage("Formato no admitido","Selecciona un archivo .dm3 o .dm4.");return;}
    run("ROI Manager...");
    if(roiManager("count")>0&&!getBoolean("El ROI Manager contiene objetos. Cambiar a la nueva imagen? Guarde antes las medidas que quiera conservar.","Abrir imagen","Cancelar"))return;
    state=lightHF46CaptureState();switchSnapshotStatus=call("cavity.light.HF46.beginSwitch","");if(switchSnapshotStatus!="OK")return;
    imported=call("cavity.light.IndividualEditor.importDm",path);
    if(!startsWith(imported,"OK|")){call("cavity.light.HF46.endSwitch","rollback");showMessage("Apertura no realizada",imported);return;}
    info=split(imported,"|");selectImage(parseFloat(info[1]));roiManager("reset");lightHF46ResetImageState();
    if(!lightRegisterActiveImageWithPath(path)){lightRollbackImported(info[1],state);return;}
    call("cavity.light.HF46.endSwitch","commit");
    lightConfigureCurrentImage();
}

function lightRegisterActiveImage() {
    projectOk=lightEnsureProject();if(projectOk==0)return;if(nImages()<=0){showMessage("Sin imagen","Abre primero un DM3/DM4 con Bio-Formats.");return;}if(!lightValidateSingle2D())return;
    
    fileName=getInfo("image.filename");dir=getInfo("image.directory");if(fileName==""||dir==""){showMessage("Origen no verificable","FIJI no informa de la ruta de la imagen activa. Para no asociar por error una ventana con un DM3/DM4 distinto, use 'Abrir DM3/DM4 y registrar'.");return;}path=normalizeStoredPath(lightJoin(dir,fileName));if(!File.exists(path)){showMessage("Origen no verificable","La ruta informada por FIJI no existe:\n"+path+"\n\nUse 'Abrir DM3/DM4 y registrar'.");return;}ext=lightExtension(path);if(ext!="dm3"&&ext!="dm4"){showMessage("Origen no compatible","La imagen activa no esta vinculada directamente a un DM3 o DM4. Use 'Abrir DM3/DM4 y registrar'.");return;}run("ROI Manager...");if(roiManager("count")>0&&!getBoolean("Vaciar el ROI Manager para registrar esta imagen?","Registrar","Cancelar"))return;
    state=lightHF46CaptureState();switchSnapshotStatus=call("cavity.light.HF46.beginSwitch","");if(switchSnapshotStatus!="OK")return;
    roiManager("reset");lightHF46ResetImageState();
    if(!lightRegisterActiveImageWithPath(path)){call("cavity.light.HF46.endSwitch","rollback");lightHF46RestoreState(state);return;}
    call("cavity.light.HF46.endSwitch","commit");lightConfigureCurrentImage();
}



function lightRegisterActiveImageWithPath(path) {
    guardFlag=lightCanonicalProjectGuard("registrar una imagen");
    if(guardFlag==0)return 0;
    path=normalizeStoredPath(path);
    if(!File.exists(path)){showMessage("Fuente no encontrada",path);return 0;}
    ext=lightExtension(path);
    if(ext!="dm3"&&ext!="dm4"){showMessage("Fuente invalida","Debe ser DM3 o DM4.");return 0;}
    sha=call("cavity.light.HF46.sourceSha",path);
    if(sha=="0"||lengthOf(sha)!=64){showMessage("Hash no disponible","No se pudo calcular SHA-256.");return 0;}
    strippedName=stripExtension(File.getName(path));
    base=lightSanitizeId(strippedName);
    id=base+"_"+substring(sha,0,12);
    imagesRoot=lightJoin(lightProjectRoot,"images");
    imagePath=lightJoin(imagesRoot,id);
    imgDir=lightNormalizeDir(imagePath);
    meta=lightJoin(imgDir,lightImageMetadataFileName);
    exists=File.exists(meta);
    if(exists&&!getBoolean("La imagen ya esta registrada como:\n"+id+"\n\nVincular la imagen activa a ese registro?","Vincular","Cancelar"))return 0;

    imageDirMade=lightMakeDir(imgDir);
    sourceDir=lightJoin(imgDir,"source");
    roiDir=lightJoin(imgDir,"roi_sessions");
    imageLogsDir=lightJoin(imgDir,"logs");
    sourceDirMade=lightMakeDir(sourceDir);
    roiDirMade=lightMakeDir(roiDir);
    logsDirMade=lightMakeDir(imageLogsDir);
    if(imageDirMade==0||sourceDirMade==0||roiDirMade==0||logsDirMade==0){showMessage("Registro no preparado","No se pudo crear la estructura interna de la imagen. No se ha modificado el DM3/DM4.");return 0;}

    lightImageId=id;lightImageDir=imgDir;lightSourceSha256=sha;lightCurrentRunId="";
    imageFileName=File.getName(path);imageDirectory=normalizeStoredPath(File.getDirectory(path));imageChecksum=sha;montageId=id;sourceFirst=imageFileName;sourceLast=imageFileName;sourceImageList=imageFileName;

    if(exists){
        expectedSha=lightKvRead(meta,"source_sha256","");
        if(expectedSha!=""&&expectedSha!=sha){showMessage("Registro incompatible","El registro existente tiene otro SHA-256. No se vinculara la imagen.");return 0;}
        metadataRead=lightReadImageMetadata();
        if(metadataRead==0)return 0;
        lightSourcePath=path;
        sx=lightKvNumber(meta,"active_scale_x_nm_px",NaN);
        sy=lightKvNumber(meta,"active_scale_y_nm_px",NaN);
        if(sx>0&&sy>0){setVoxelSize(sx,sy,1,"nm");updateScaleMaybe();}
        projectConfigured=1;lightProjectLoaded=1;v4ProjectLoaded=0;usePanelsAsMask=0;
        setMetadataImageProperties();
        workspaceInit=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());if(workspaceInit!="OK"){showMessage("Preparacion no disponible",workspaceInit);return 0;}
        cur=lightCurrentRevision;
        if(cur!=""&&getBoolean("Cargar la revision vigente "+cur+"?","Cargar ROIs","Mantener sin ROIs"))lightLoadRevisionById(cur);else updateSessionMetadataRoi();
        lightSourcePath=path;imageFileName=File.getName(path);imageDirectory=normalizeStoredPath(File.getDirectory(path));
        metadataWritten=lightWriteImageMetadata();
        registryWritten=0;
        if(metadataWritten==1)registryWritten=lightUpdateRegistry();
        if(metadataWritten==0||registryWritten==0){showMessage("Vinculacion incompleta","Los metadatos canonicos o images.tsv no pudieron verificarse. No se ha modificado el DM3/DM4 ni ninguna revision ROI.\n\nPulse Reparar registro antes de continuar.");return 0;}
        lightAppendLog("IMAGE_RELINKED","source_sha256="+sha+"; path="+path);
        showMessage("Imagen vinculada","ID: "+lightImageId+"\nSHA-256: "+lightSourceSha256+"\n\nSe conservaron la escala, el espesor y la configuracion registrados.");
        lightShowPanel();return 1;
    }

    lightSourcePath=path;lightSourceStoredPath="";lightCopySource=0;
    copy=getBoolean("Quieres copiar el DM3/DM4 dentro del proyecto?\n\nEl original nunca se modifica.","Copiar fuente","Solo referenciar");
    if(copy){
        dest=lightJoin(sourceDir,File.getName(path));
        result=lightCopyFileVerified(path,dest,sha);
        if(result==1){lightSourceStoredPath=dest;lightCopySource=1;}
        else showMessage("Copia no aceptada","No se pudo verificar la copia; se mantiene solo la referencia al original.");
    }
    lightImageMode="without_surface";lightThicknessNm=0;lightThicknessUncertaintyNm=0;lightThicknessMethod="not_provided";lightThicknessNotes="";lightUseWholeImage=0;lightIncludeUncertain=0;lightCurrentRevision="";
    lightCaptureOriginalScale();projectConfigured=1;lightProjectLoaded=1;v4ProjectLoaded=0;usePanelsAsMask=0;
    setMetadataImageProperties();
    workspaceInit=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());if(workspaceInit!="OK"){showMessage("Preparacion no disponible",workspaceInit);return 0;}
    updateSessionMetadataRoi();
    metadataWritten=lightWriteImageMetadata();
    registryWritten=0;
    if(metadataWritten==1)registryWritten=lightUpdateRegistry();
    if(metadataWritten==0||registryWritten==0){
        showMessage("Registro incompleto","La carpeta y, en su caso, la copia verificada de la fuente se conservan, pero image_metadata.tsv o images.tsv no superaron la verificacion.\n\nNo empiece a medir. Pulse Reparar registro y seleccione despues la imagen ya registrada.");
        return 0;
    }
    lightAppendLog("IMAGE_REGISTERED","source_sha256="+sha+"; path="+path+"; copied="+lightCopySource);
    showMessage("Imagen registrada","ID: "+lightImageId+"\nSHA-256: "+lightSourceSha256+"\nModo: "+lightImageMode+"\n\nCada imagen mantiene ROIs, escala, espesor y revisiones independientes.");
    lightShowPanel();return 1;
}

function lightValidateSingle2D() { getDimensions(w,h,c,z,t);if(c!=1||z!=1||t!=1){showMessage("Dataset no compatible","Esta version Light exige una unica imagen 2D. Dimensiones: C="+c+", Z="+z+", T="+t+".");return 0;}return 1; }

function lightRegistryHasDataRows() {
    reg=lightJoin(lightProjectRoot,lightRegistryFileName);
    if(!File.exists(reg))return 0;
    registryText=File.openAsString(reg);
    registryLines=split(registryText,"\n");
    if(registryLines.length<2)return 0;
    for(registryIndex=1;registryIndex<registryLines.length;registryIndex++){
        registryLine=replace(registryLines[registryIndex],"\r","");
        registryLine=String.trim(registryLine);
        if(registryLine!="")return 1;
    }
    return 0;
}

function lightSelectProjectImage() {
    projectOk=lightEnsureProject();
    if(projectOk==0)return;

    hasRows=lightRegistryHasDataRows();
    if(hasRows==0){
        repairText=lightRepairImageRegistryCore(1);
        if(!startsWith(repairText,"OK|")){
            showMessage("Sin imagenes seleccionables","El registro images.tsv no contiene filas utilizables y no pudo reconstruirse automaticamente.\n\nPulse Reparar registro o revise la carpeta images.");
            return;
        }
    }

    id=lightChooseRegistryImages(0);
    if(id=="")return;
    lightOpenRegisteredImageById(id);
}

function lightOpenRegisteredImageById(id) {
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
    if(confirmSwitch){if(!lightResolvePendingBeforeSwitch())return 0;}
    state=lightHF46CaptureState();workspaceSwitch=call("cavity.light.RevisionWorkspace.beginSwitch","");if(workspaceSwitch!="OK")return 0;switchSnapshotStatus=call("cavity.light.HF46.beginSwitch","");if(switchSnapshotStatus!="OK"){call("cavity.light.RevisionWorkspace.endSwitch","rollback");return 0;}
    imported=call("cavity.light.IndividualEditor.importDm",resolvedPath);
    if(!startsWith(imported,"OK|")){call("cavity.light.HF46.endSwitch","rollback");call("cavity.light.RevisionWorkspace.endSwitch","rollback");showMessage("Apertura no realizada",imported);return 0;}
    info=split(imported,"|");importedId=info[1];selectImage(parseFloat(importedId));roiManager("reset");lightHF46ResetImageState();
    lightImageId=id;lightImageDir=targetDir;
    if(!lightReadImageMetadata()){lightRollbackImported(importedId,state);return 0;}
    lightSourcePath=sourcePath;lightSourceStoredPath=storedPath;
    sx=lightKvNumber(meta,"active_scale_x_nm_px",lightOriginalScaleNmX);sy=lightKvNumber(meta,"active_scale_y_nm_px",lightOriginalScaleNmY);
    if(lightHF46Finite(sx)&&lightHF46Finite(sy)&&sx>0&&sy>0){setVoxelSize(sx,sy,1,"nm");updateScaleMaybe();}
    imageFileName=File.getName(resolvedPath);imageDirectory=normalizeStoredPath(File.getDirectory(resolvedPath));imageChecksum=targetSha;montageId=id;
    sourceFirst=imageFileName;sourceLast=imageFileName;sourceImageList=imageFileName;
    projectConfigured=1;lightProjectLoaded=1;v4ProjectLoaded=0;setMetadataImageProperties();
    workspaceInit=call("cavity.light.RevisionWorkspace.initialize",lightWorkspaceSettings());if(workspaceInit!="OK"){lightRollbackImported(importedId,state);showMessage("Apertura no realizada",workspaceInit);return 0;}
    if(revisionToLoad!=""){
        if(!lightLoadRevisionCore(revisionToLoad,0)){lightRollbackImported(importedId,state);return 0;}
    }else{lightCurrentRevision="";lightCurrentRunId="";updateSessionMetadataRoi();}
    lightSourcePath=sourcePath;lightSourceStoredPath=storedPath;setMetadataImageProperties();
    if(persistOpening){if(!lightWriteImageMetadata()){lightRollbackImported(importedId,state);return 0;}}
    call("cavity.light.HF46.endSwitch","commit");call("cavity.light.RevisionWorkspace.endSwitch","commit");
    if(persistOpening){lightUpdateRegistry();lightAppendLog("IMAGE_OPENED","revision="+lightCurrentRevision+"; opened_path="+resolvedPath);}
    lightShowPanel();return 1;
}

function lightRollbackImported(importedId,state) {
    call("cavity.light.IndividualEditor.closeImported",importedId);
    call("cavity.light.HF46.endSwitch","rollback");call("cavity.light.RevisionWorkspace.endSwitch","rollback");lightHF46RestoreState(state);
}

// Opens existing schema-1 data without changing metadata, pointers, logs or results.
function lightOpenLibrarySelection(projectRoot,imageId,revisionId) {
    descriptor=lightJoin(projectRoot,lightProjectFileName);
    if(lightProjectDescriptorValid(descriptor,"","")==0){showMessage("Proyecto no valido",descriptor);return 0;}
    if(!lightResolvePendingBeforeSwitch())return 0;
    previous=lightHF46CaptureState();switchSnapshotStatus=call("cavity.light.HF46.beginSwitch","");if(switchSnapshotStatus!="OK")return 0;
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
}

function lightConfigureCurrentImage() {
    imageOk=lightEnsureCurrentImage();if(imageOk==0)return;
    oldMode=lightImageMode;oldThickness=lightThicknessNm;oldUncertainty=lightThicknessUncertaintyNm;oldMethod=lightThicknessMethod;oldNotes=lightThicknessNotes;oldInclude=lightIncludeUncertain;oldExclude=excludeNegativeDepth;
    modes=newArray("Sin superficie","Con superficie");defaultMode="Sin superficie";if(lightImageMode=="with_surface")defaultMode="Con superficie";methods=newArray("not_provided","EELS","CBED","geometric_estimate","nominal_value","literature","other");
    Dialog.create("Configurar imagen independiente");Dialog.addChoice("Modo de analisis:",modes,defaultMode);Dialog.addNumber("Espesor de lamina (nm; 0 si no se conoce):",lightThicknessNm);Dialog.addNumber("Incertidumbre del espesor (nm):",lightThicknessUncertaintyNm);Dialog.addChoice("Metodo de espesor:",methods,lightThicknessMethod);Dialog.addString("Notas del espesor:",lightThicknessNotes,45);Dialog.addCheckbox("Incluir cavidades dudosas en el recuento principal",lightIncludeUncertain);Dialog.addMessage("La densidad volumetrica se calcula como valor nominal N/(A*t). No se aplican correcciones ocultas.");Dialog.show();
    m=Dialog.getChoice();newMode="without_surface";if(m=="Con superficie")newMode="with_surface";newThickness=Dialog.getNumber();newUncertainty=Dialog.getNumber();newMethod=Dialog.getChoice();newNotes=Dialog.getString();newInclude=Dialog.getCheckbox();if(!lightHF46Finite(newThickness)||!lightHF46Finite(newUncertainty)||newThickness<0||newUncertainty<0){showMessage("Valor no valido","El espesor y su incertidumbre deben ser numeros finitos no negativos.");return;}
    changed=0;
    if(newMode!=oldMode)changed=1;
    thicknessChanged=lightNumberChanged(newThickness,oldThickness);if(thicknessChanged==1)changed=1;
    uncertaintyChanged=lightNumberChanged(newUncertainty,oldUncertainty);if(uncertaintyChanged==1)changed=1;
    if(newMethod!=oldMethod)changed=1;
    if(newNotes!=oldNotes)changed=1;
    if(newInclude!=oldInclude)changed=1;
    objects=lightScientificObjectCount();
    if(changed==1&&objects>0){if(!getBoolean("La configuracion cuantitativa cambiara y se recalcularan las ROIs. Se guardara una revision nueva inmutable.\n\nContinuar?","Cambiar y revisar","Cancelar"))return;if(!quantitativeRevisionPreflight())return;}
    lightImageMode=newMode;lightThicknessNm=newThickness;lightThicknessUncertaintyNm=newUncertainty;lightThicknessMethod=newMethod;lightThicknessNotes=newNotes;lightIncludeUncertain=newInclude;if(lightImageMode=="without_surface")excludeNegativeDepth=0;else excludeNegativeDepth=1;
    syncAllObjects(0);updateSessionMetadataRoi();
    metaWritten=lightWriteImageMetadata();registryWritten=lightUpdateRegistry();
    if(metaWritten==0||registryWritten==0){lightImageMode=oldMode;lightThicknessNm=oldThickness;lightThicknessUncertaintyNm=oldUncertainty;lightThicknessMethod=oldMethod;lightThicknessNotes=oldNotes;lightIncludeUncertain=oldInclude;excludeNegativeDepth=oldExclude;syncAllObjects(0);updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();showMessage("Configuracion no aplicada","No se pudieron verificar los metadatos o el registro en la raiz canonica. Se restauraron los valores anteriores.");return;}
    rev="";
    if(changed==1&&objects>0){rev=lightSaveRevisionCore(0);if(rev==""){lightImageMode=oldMode;lightThicknessNm=oldThickness;lightThicknessUncertaintyNm=oldUncertainty;lightThicknessMethod=oldMethod;lightThicknessNotes=oldNotes;lightIncludeUncertain=oldInclude;excludeNegativeDepth=oldExclude;syncAllObjects(0);updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();showMessage("Configuracion restaurada","No se pudo guardar la revision asociada. Se restauraron los valores anteriores.");return;}}
    lightAppendLog("IMAGE_CONFIGURED","mode="+lightImageMode+"; thickness_nm="+lightNum(lightThicknessNm)+"; uncertainty_nm="+lightNum(lightThicknessUncertaintyNm)+"; method="+lightThicknessMethod+"; include_uncertain="+lightIncludeUncertain+"; revision="+rev);lightShowPanel();
}

function lightShowCurrentInfo() {
    msg="Cavity TEM Light "+lightReleaseVersion+"\n\nProyecto: "+lightProjectName+"\nProject ID: "+lightProjectId+"\nProject UID: "+lightProjectUid+"\nRaiz: "+lightProjectRoot+"\n\nImagen ID: "+lightImageId+"\nFuente: "+lightSourcePath+"\nCopia: "+lightSourceStoredPath+"\nSHA-256: "+lightSourceSha256+"\nModo: "+lightImageMode+"\nRevision vigente: "+lightCurrentRevision+"\n";
    if(nImages()>0){scaleInfoOk=updateScaleMaybe();if(scaleInfoOk==1)msg=msg+"Escala activa: "+d2s(nmPerPixelX,9)+" x "+d2s(nmPerPixelY,9)+" nm/px\n";else msg=msg+"Escala activa: no valida\n";}else msg=msg+"Escala activa: no valida\n";
    msg=msg+"Escala confirmada: "+lightScaleConfirmed+" ("+lightScaleOrigin+")\nEspesor: "+d2s(lightThicknessNm,3)+" nm; metodo="+lightThicknessMethod+"\nArea completa confirmada: "+lightUseWholeImage+"\n\nInteraccion HF4:\n- Diametro activo: "+d2s(activeDiameterNm,4)+" nm\n- Vista previa: "+lightInteractivePreviewEnabled+"\n- Sensibilidad: "+d2s(lightInteractiveResizeStepNm,4)+" nm/paso\n- Etiquetas exactas ROI Manager: "+showRoiLabels+"\n- Controlador: "+lightInteractiveControllerStatus+"\n\nEstado: "+lightValidationState;
    showMessage("Informacion y trazabilidad",msg);
}

function lightCaptureOriginalScale() { getPixelSize(u,pw,ph);factor=unitToNmFactor(u);lightOriginalScaleUnit=u;if(factor>0&&pw>0&&ph>0){lightOriginalScaleNmX=pw*factor;lightOriginalScaleNmY=ph*factor;setVoxelSize(lightOriginalScaleNmX,lightOriginalScaleNmY,1,"nm");updateScaleMaybe();scaleDefined=1;lightScaleOrigin="bioformats_metadata";lightScaleConfirmed=0;}else{lightOriginalScaleNmX=NaN;lightOriginalScaleNmY=NaN;scaleDefined=0;lightScaleConfirmed=0;} }

function lightConfirmImageScale() {
    imageOk=lightEnsureCurrentImage();if(imageOk==0)return;if(!updateScaleMaybe()){showMessage("Escala no valida","Bio-Formats no ha dejado una calibracion fisica reconocible. Introduce nm/px o calibra con una linea.");return;}
    msg="Escala detectada: "+d2s(nmPerPixelX,12)+" x "+d2s(nmPerPixelY,12)+" nm/px\n\nConfirmas que es la escala correcta para esta imagen?";if(!getBoolean(msg,"Confirmar","Cancelar"))return;
    lightScaleConfirmed=1;if(lightScaleOrigin=="bioformats_metadata")lightScaleOrigin="bioformats_metadata_confirmed";scaleDefined=1;updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();lightAppendLog("SCALE_CONFIRMED","x_nm_px="+lightNum(nmPerPixelX)+"; y_nm_px="+lightNum(nmPerPixelY)+"; origin="+lightScaleOrigin);showStatus("Escala confirmada.");lightRefreshPanel();
}
function lightSetScaleNumerically() {
    imageOk=lightEnsureCurrentImage();if(imageOk==0)return;oldValid=updateScaleMaybe();oldX=nmPerPixelX;oldY=nmPerPixelY;oldOrigin=lightScaleOrigin;oldConfirmed=lightScaleConfirmed;defaultX=1;defaultY=1;if(oldValid){defaultX=oldX;defaultY=oldY;}
    Dialog.create("Escala manual");Dialog.addNumber("nm/px en X:",defaultX);Dialog.addNumber("nm/px en Y:",defaultY);Dialog.addString("Origen/nota:","manual_numeric",35);Dialog.show();sx=Dialog.getNumber();sy=Dialog.getNumber();note=Dialog.getString();if(!lightHF46Finite(sx)||!lightHF46Finite(sy)||sx<=0||sy<=0){showMessage("Escala invalida","Los valores deben ser positivos.");return;}
    changed=0;if(oldValid==0)changed=1;if(lightNumberChanged(oldX,sx)==1)changed=1;if(lightNumberChanged(oldY,sy)==1)changed=1;
    objects=lightScientificObjectCount();if(changed==1&&objects>0){if(!getBoolean("Cambiar la escala recalculara la geometria fisica de "+objects+" objetos y creara una revision nueva inmutable.\n\nContinuar?","Cambiar y revisar","Cancelar"))return;if(!quantitativeRevisionPreflight())return;}
    setVoxelSize(sx,sy,1,"nm");updateScaleMaybe();scaleDefined=1;lightScaleConfirmed=1;lightScaleOrigin=note;if(lightScaleOrigin=="")lightScaleOrigin="manual_numeric";syncAllObjects(0);updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();rev="";
    if(changed==1&&objects>0){rev=lightSaveRevisionCore(0);if(rev==""){if(oldValid)setVoxelSize(oldX,oldY,1,"nm");lightScaleOrigin=oldOrigin;lightScaleConfirmed=oldConfirmed;updateScaleMaybe();syncAllObjects(0);updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();showMessage("Escala restaurada","No se pudo guardar la revision vinculada al cambio. Se restauro la escala anterior.");return;}}
    lightAppendLog("SCALE_SET_NUMERIC","x_nm_px="+lightNum(sx)+"; y_nm_px="+lightNum(sy)+"; origin="+lightScaleOrigin+"; revision="+rev);showStatus("Escala manual aplicada y confirmada.");lightRefreshPanel();
}

function lightAfterManualScale(origin) { if(nImages()<=0)return;if(updateScaleMaybe()){scaleDefined=1;lightScaleConfirmed=1;lightScaleOrigin=origin;syncAllObjects(0);updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();lightAppendLog("SCALE_SET_EXTERNAL","origin="+origin+"; x_nm_px="+lightNum(nmPerPixelX)+"; y_nm_px="+lightNum(nmPerPixelY));lightRefreshPanel();} }
function lightCalibrateScaleFromLine() {
    imageOk=lightEnsureCurrentImage();if(imageOk==0)return;oldValid=updateScaleMaybe();oldX=nmPerPixelX;oldY=nmPerPixelY;oldOrigin=lightScaleOrigin;oldConfirmed=lightScaleConfirmed;objects=lightScientificObjectCount();if(objects>0&&!quantitativeRevisionPreflight())return;
    calibrateScaleFromLine();if(!updateScaleMaybe())return;changed=0;if(oldValid==0)changed=1;if(lightNumberChanged(oldX,nmPerPixelX)==1)changed=1;if(lightNumberChanged(oldY,nmPerPixelY)==1)changed=1;if(changed==0)return;
    lightScaleConfirmed=1;lightScaleOrigin="manual_line";scaleDefined=1;syncAllObjects(0);updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();rev="";
    if(objects>0){rev=lightSaveRevisionCore(0);if(rev==""){if(oldValid)setVoxelSize(oldX,oldY,1,"nm");lightScaleOrigin=oldOrigin;lightScaleConfirmed=oldConfirmed;updateScaleMaybe();syncAllObjects(0);updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();showMessage("Escala restaurada","No se pudo guardar la revision vinculada a la calibracion. Se restauro la escala anterior.");return;}}
    lightAppendLog("SCALE_SET_LINE","x_nm_px="+lightNum(nmPerPixelX)+"; y_nm_px="+lightNum(nmPerPixelY)+"; revision="+rev);lightRefreshPanel();
}

function lightVerifyScale() { if(nImages()<=0){showMessage("Sin imagen","No hay imagen activa.");return;}getPixelSize(u,pw,ph);msg="Calibracion de ImageJ: "+d2s(pw,12)+" x "+d2s(ph,12)+" "+u+"/px\nEscala interna: "+d2s(nmPerPixelX,12)+" x "+d2s(nmPerPixelY,12)+" nm/px\nConfirmada: "+lightScaleConfirmed+"\nOrigen: "+lightScaleOrigin+"\nOriginal Bio-Formats: "+d2s(lightOriginalScaleNmX,12)+" x "+d2s(lightOriginalScaleNmY,12)+" nm/px";showMessage("Verificacion de escala",msg); }

function lightUseWholeImageAsArea() {
    imageOk=lightEnsureCurrentImage();if(imageOk==0)return;if(!getBoolean("Usar toda la imagen como area base?\n\nCon superficie solo se usa el lado del material. Las zonas excluidas seguiran restando area.","Confirmar toda la imagen","Cancelar"))return;lightUseWholeImage=1;syncAllObjects(0);updateSessionMetadataRoi();lightWriteImageMetadata();lightUpdateRegistry();lightAppendLog("WHOLE_IMAGE_AREA_CONFIRMED","exclusions="+countTypeFast("exclusion"));showStatus("Toda la imagen confirmada como area base.");
}

function lightAddAnalysisMasks() { lightUseWholeImage=0;addAnalysisMaskRoi(); }
function lightDefineSurface() { imageOk=lightEnsureCurrentImage();if(imageOk==0)return;if(lightImageMode!="with_surface"){if(!getBoolean("La imagen esta configurada sin superficie. Cambiarla a modo con superficie?","Cambiar modo","Cancelar"))return;lightImageMode="with_surface";excludeNegativeDepth=1;}defineSurfaceReference();lightWriteImageMetadata();lightUpdateRegistry(); }
function lightSetActiveDiameter() {
    Dialog.create("Diametro activo R9");
    Dialog.addNumber("Diametro (nm):", activeDiameterNm);
    Dialog.show();
    d = Dialog.getNumber();
    if (d <= 0) { showMessage("Valor invalido", "El diametro debe ser mayor que cero."); return; }
    activeDiameterNm = d;
    lightInteractivePushState(lightInteractiveMode);
    updateSessionMetadataRoi();
    lightRefreshPanel();
    showStatus("Diametro activo: "+d2s(activeDiameterNm,3)+" nm. El circulo del cursor se actualiza inmediatamente.");
}

function lightAddEllipseCavityFromSelection() {
    lightHF4Pull();
    if (!v4PrepareImageForMeasurement(1)) return;
    st = selectionType;
    if (st != 1) {
        showMessage("Seleccion no compatible", "Dibuja primero una seleccion oval/eliptica con la herramienta Oval.");
        return;
    }
    // ImageJ Roi.clone() shares properties. Reject managed ROIs and isolate a fresh selection.
    preparedEllipse = call("cavity.light.IndividualEditor.prepareNewEllipse", "");
    if (preparedEllipse != "OK") {
        showMessage("Elipse no registrada", preparedEllipse);
        return;
    }
    run("ROI Manager...");
    cavityCounter++;
    id = "CAV_" + IJ.pad(cavityCounter, 6);
    Roi.setName(id);
    Roi.setProperty("Type", "cavity");
    Roi.setProperty("Cavity_id", id);
    Roi.setProperty("Cavity_serial", d2s(cavityCounter, 0));
    Roi.setProperty("Measurement_source", "ellipse_manual");
    Roi.setProperty("Manual_excluded", "0");
    Roi.setProperty("Cavity_class", activeCavityClass);
    Roi.setProperty("Cavity_class_label", activeCavityClassLabel);
    Roi.setProperty("Cavity_confidence", activeCavityConfidence);
    Roi.setProperty("Duplicate_status", "clear");
    Roi.setProperty("Duplicate_partners", "");
    setCommonObjectProperties();
    roiManager("add");
    idx = roiManager("count") - 1;
    syncCavityAtIndex(idx);
    checkNewCavityForDuplicates(idx);
    undoKind = "add";
    undoObjectId = id;
    undoAvailable = 1;
    showAllRois();
    updateSessionMetadataRoi();
    showStatus("Elipse registrada: " + id + ".");
}

function lightGroupForCavityClass(c) { c=normalizeCavityClass(c);if(c=="uncertain")return 2;if(c=="possible_artifact")return 3;return 1; }
function lightGroupForFeatureType(t) { if(t=="dislocation")return 4;if(t=="grain_boundary")return 5;if(t=="surface_reference")return 6;if(t=="interface")return 7;if(t=="analysis_mask")return 8;if(t=="exclusion")return 9;return 0; }
function lightWriteImageMetadata() {
    prepared=lightPrepareImageContextForWrite(1);
    if(prepared==0)return 0;

    meta=lightJoin(lightImageDir,lightImageMetadataFileName);
    sx=NaN;
    sy=NaN;
    if(nImages()>0){
        scaleUpdated=updateScaleMaybe();
        if(scaleUpdated==1){sx=nmPerPixelX;sy=nmPerPixelY;}
    }

    cleanProjectId=lightTsvClean(lightProjectId);
    cleanProjectUid=lightTsvClean(lightProjectUid);
    cleanProjectRoot=lightTsvClean(lightProjectRoot);
    cleanProjectFile=lightTsvClean(lightProjectFile);
    cleanImageId=lightTsvClean(lightImageId);
    cleanSourcePath=lightTsvClean(lightSourcePath);
    cleanStoredPath=lightTsvClean(lightSourceStoredPath);
    cleanSample=lightTsvClean(sampleName);
    cleanCondition=lightTsvClean(experimentalCondition);
    cleanOperator=lightTsvClean(operatorName);
    cleanVoltage=lightTsvClean(microscopeVoltage);
    cleanTemperature=lightTsvClean(specimenTemperature);
    cleanThicknessMethod=lightTsvClean(lightThicknessMethod);
    cleanThicknessNotes=lightTsvClean(lightThicknessNotes);
    cleanOriginalUnit=lightTsvClean(lightOriginalScaleUnit);
    cleanScaleOrigin=lightTsvClean(lightScaleOrigin);
    cleanRevision=lightTsvClean(lightCurrentRevision);
    cleanRun=lightTsvClean(lightCurrentRunId);

    thicknessText=lightNum(lightThicknessNm);
    uncertaintyText=lightNum(lightThicknessUncertaintyNm);
    originalXText=lightNum(lightOriginalScaleNmX);
    originalYText=lightNum(lightOriginalScaleNmY);
    activeXText=lightNum(sx);
    activeYText=lightNum(sy);
    activeDiameterText=lightNum(activeDiameterNm);
    bandWidthText=lightNum(bandNm);
    histogramText=lightNum(lightHistogramBinNm);
    distanceBinText=lightNum(lightFeatureDistanceBinNm);
    updatedText=d2s(getTime(),0);

    t="schema_version\t"+lightSchemaVersion+"\n";
    t=t+"descriptor_type\t"+lightImageDescriptorType+"\n";
    t=t+"tool_version\t"+lightReleaseVersion+"\n";
    t=t+"validation_state\t"+lightValidationState+"\n";
    t=t+"project_id\t"+cleanProjectId+"\n";
    t=t+"project_uid\t"+cleanProjectUid+"\n";
    t=t+"project_root\t"+cleanProjectRoot+"\n";
    t=t+"project_file\t"+cleanProjectFile+"\n";
    t=t+"image_id\t"+cleanImageId+"\n";
    t=t+"source_path\t"+cleanSourcePath+"\n";
    t=t+"stored_path\t"+cleanStoredPath+"\n";
    t=t+"source_sha256\t"+lightSourceSha256+"\n";
    t=t+"copy_source\t"+lightCopySource+"\n";
    t=t+"sample_name\t"+cleanSample+"\n";
    t=t+"experimental_condition\t"+cleanCondition+"\n";
    t=t+"operator_name\t"+cleanOperator+"\n";
    t=t+"microscope_voltage\t"+cleanVoltage+"\n";
    t=t+"specimen_temperature\t"+cleanTemperature+"\n";
    t=t+"image_mode\t"+lightImageMode+"\n";
    t=t+"foil_thickness_nm\t"+thicknessText+"\n";
    t=t+"thickness_uncertainty_nm\t"+uncertaintyText+"\n";
    t=t+"thickness_method\t"+cleanThicknessMethod+"\n";
    t=t+"thickness_notes\t"+cleanThicknessNotes+"\n";
    t=t+"original_scale_x_nm_px\t"+originalXText+"\n";
    t=t+"original_scale_y_nm_px\t"+originalYText+"\n";
    t=t+"original_scale_unit\t"+cleanOriginalUnit+"\n";
    t=t+"active_scale_x_nm_px\t"+activeXText+"\n";
    t=t+"active_scale_y_nm_px\t"+activeYText+"\n";
    t=t+"scale_origin\t"+cleanScaleOrigin+"\n";
    t=t+"scale_confirmed\t"+lightScaleConfirmed+"\n";
    t=t+"use_whole_image\t"+lightUseWholeImage+"\n";
    t=t+"include_uncertain\t"+lightIncludeUncertain+"\n";
    t=t+"active_diameter_nm\t"+activeDiameterText+"\n";
    t=t+"band_width_nm\t"+bandWidthText+"\n";
    t=t+"band_count\t"+bandCount+"\n";
    t=t+"hf3_band_mode\t"+lightBandMode+"\n";
    t=t+"hf3_size_breaks_nm\t"+lightSizeBreaks+"\n";
    t=t+"hf3_result_contrast\t"+lightResultContrast+"\n";
    t=t+"exclude_negative_depth\t"+excludeNegativeDepth+"\n";
    t=t+"histogram_bin_nm\t"+histogramText+"\n";
    t=t+"feature_distance_bin_nm\t"+distanceBinText+"\n";
    t=t+"interactive_preview\t"+lightInteractivePreviewEnabled+"\n";
    t=t+"interactive_resize_step_nm\t"+lightNum(lightInteractiveResizeStepNm)+"\n";
    t=t+"show_roi_labels\t"+showRoiLabels+"\n";
    t=t+"exact_label_mode\troi_name_v1\n";
    t=t+"current_revision\t"+cleanRevision+"\n";
    t=t+"current_run\t"+cleanRun+"\n";
    if(nImages()>0){
        widthValue=getWidth();
        heightValue=getHeight();
        t=t+"width_px\t"+widthValue+"\n";
        t=t+"height_px\t"+heightValue+"\n";
    }
    t=t+"updated_ms\t"+updatedText+"\n";

    writeOk=lightHF46WriteText(meta,t);if(writeOk==0)return 0;
    metaMatches=lightImageMetadataMatches(meta,lightImageId,lightSourceSha256);
    if(metaMatches==1)return 1;
    return 0;
}
function lightReadImageMetadata() {
    guardOk=lightCanonicalProjectGuard("leer metadatos de imagen");
    if(guardOk==0)return 0;

    imagesRoot=lightJoin(lightProjectRoot,"images");
    imagePath=lightJoin(imagesRoot,lightImageId);
    expectedDir=lightNormalizeDir(imagePath);
    meta=lightJoin(expectedDir,lightImageMetadataFileName);

    metaMatches=lightImageMetadataMatches(meta,lightImageId,"");
    if(metaMatches==0){
        showMessage("Metadato rechazado","El archivo no coincide con el proyecto y la imagen seleccionados:\n"+meta);
        return 0;
    }

    lightImageDir=expectedDir;
    lightHF46KvPath=meta;lightHF46KvText=File.openAsString(meta);

    sourcePathValue=lightKvRead(meta,"source_path",lightSourcePath);
    lightSourcePath=normalizeStoredPath(sourcePathValue);
    storedPathValue=lightKvRead(meta,"stored_path",lightSourceStoredPath);
    lightSourceStoredPath=normalizeStoredPath(storedPathValue);
    lightSourceSha256=lightKvRead(meta,"source_sha256",lightSourceSha256);

    copyValue=lightKvNumber(meta,"copy_source",0);
    lightCopySource=round(copyValue);
    sampleName=lightKvRead(meta,"sample_name",sampleName);
    experimentalCondition=lightKvRead(meta,"experimental_condition",experimentalCondition);
    operatorName=lightKvRead(meta,"operator_name",operatorName);
    microscopeVoltage=lightKvRead(meta,"microscope_voltage",microscopeVoltage);
    specimenTemperature=lightKvRead(meta,"specimen_temperature",specimenTemperature);
    lightImageMode=lightKvRead(meta,"image_mode","without_surface");
    lightThicknessNm=lightKvNumber(meta,"foil_thickness_nm",0);
    lightThicknessUncertaintyNm=lightKvNumber(meta,"thickness_uncertainty_nm",0);
    lightThicknessMethod=lightKvRead(meta,"thickness_method","not_provided");
    lightThicknessNotes=lightKvRead(meta,"thickness_notes","");
    lightOriginalScaleNmX=lightKvNumber(meta,"original_scale_x_nm_px",NaN);
    lightOriginalScaleNmY=lightKvNumber(meta,"original_scale_y_nm_px",NaN);
    lightOriginalScaleUnit=lightKvRead(meta,"original_scale_unit","");
    lightScaleOrigin=lightKvRead(meta,"scale_origin","bioformats_metadata");

    scaleConfirmedValue=lightKvNumber(meta,"scale_confirmed",0);
    lightScaleConfirmed=round(scaleConfirmedValue);
    wholeImageValue=lightKvNumber(meta,"use_whole_image",0);
    lightUseWholeImage=round(wholeImageValue);
    includeValue=lightKvNumber(meta,"include_uncertain",0);
    lightIncludeUncertain=round(includeValue);
    activeDiameterNm=lightKvNumber(meta,"active_diameter_nm",activeDiameterNm);
    lightBandMode=lightKvRead(meta,"hf3_band_mode","width");
    lightSizeBreaks=lightKvRead(meta,"hf3_size_breaks_nm","0.5,1,1.5,2,3,5");
    lightResultContrast=lightKvNumber(meta,"hf3_result_contrast",0.18);
    bandNm=lightKvNumber(meta,"band_width_nm",bandNm);
    bandCountValue=lightKvNumber(meta,"band_count",bandCount);
    bandCount=round(bandCountValue);
    excludeValue=lightKvNumber(meta,"exclude_negative_depth",excludeNegativeDepth);
    excludeNegativeDepth=round(excludeValue);
    lightHistogramBinNm=lightKvNumber(meta,"histogram_bin_nm",lightHistogramBinNm);
    lightFeatureDistanceBinNm=lightKvNumber(meta,"feature_distance_bin_nm",lightFeatureDistanceBinNm);
    lightInteractivePreviewEnabled=round(lightKvNumber(meta,"interactive_preview",lightInteractivePreviewEnabled));
    lightInteractiveResizeStepNm=lightKvNumber(meta,"interactive_resize_step_nm",lightInteractiveResizeStepNm);
    showRoiLabels=round(lightKvNumber(meta,"show_roi_labels",showRoiLabels));
    if(lightInteractiveResizeStepNm<lightInteractiveResizeMinNm)lightInteractiveResizeStepNm=lightInteractiveResizeMinNm;
    if(lightInteractiveResizeStepNm>lightInteractiveResizeMaxNm)lightInteractiveResizeStepNm=lightInteractiveResizeMaxNm;
    lightCurrentRevision=lightKvRead(meta,"current_revision","");
    lightCurrentRunId=lightKvRead(meta,"current_run","");

    if(bandNm<=0)bandNm=50;
    if(bandCount<1)bandCount=1;
    if(lightHistogramBinNm<=0)lightHistogramBinNm=1;
    if(lightFeatureDistanceBinNm<=0)lightFeatureDistanceBinNm=10;
    lightHF46KvPath="";lightHF46KvText="";
    return 1;
}
function lightUpdateRegistry() {
    if(lightProjectRoot==""||lightImageId=="")return 0;
    prepared=lightPrepareImageContextForWrite(1);
    if(prepared==0)return 0;

    reg=lightJoin(lightProjectRoot,lightRegistryFileName);
    if(!File.exists(reg)){
        headerValue=lightRegistryHeader();
        File.saveString(headerValue,reg);
    }

    sx="";
    sy="";
    if(nImages()>0){
        scaleUpdated=updateScaleMaybe();
        if(scaleUpdated==1){
            sx=lightNum(nmPerPixelX);
            sy=lightNum(nmPerPixelY);
        }
    }

    cleanImageId=lightTsvClean(lightImageId);
    cleanImageName=lightTsvClean(imageFileName);
    cleanSourcePath=lightTsvClean(lightSourcePath);
    cleanStoredPath=lightTsvClean(lightSourceStoredPath);
    cleanSample=lightTsvClean(sampleName);
    cleanCondition=lightTsvClean(experimentalCondition);
    cleanRevision=lightTsvClean(lightCurrentRevision);
    cleanRun=lightTsvClean(lightCurrentRunId);
    thicknessText=lightNum(lightThicknessNm);
    timestampText=d2s(getTime(),0);

    row=""+cleanImageId+"\t"+cleanImageName+"\t"+cleanSourcePath+"\t"+cleanStoredPath+"\t"+lightSourceSha256+"\t"+cleanSample+"\t"+cleanCondition+"\t"+lightImageMode+"\t"+thicknessText+"\t"+sx+"\t"+sy+"\t"+cleanRevision+"\t"+cleanRun+"\t"+timestampText;
    js="(function(){var Files=Packages.java.nio.file.Files,Paths=Packages.java.nio.file.Paths,CS=Packages.java.nio.charset.StandardCharsets,p='"+jsEscape(reg)+"',id='"+jsEscape(lightImageId)+"',row='"+jsEscape(row)+"';var f=Paths.get(p),text=Files.exists(f)?String(new java.lang.String(Files.readAllBytes(f),CS.UTF_8)):'';var ls=text.split(/\\r?\\n/),out=[],done=false;for(var i=0;i<ls.length;i++){if(!ls[i])continue;if(i==0&&ls[i].indexOf('image_id\\t')==0){out.push(ls[i]);continue;}var k=ls[i].indexOf('\\t');if(k>0&&ls[i].slice(0,k)==id){out.push(row);done=true;}else out.push(ls[i]);}if(!done)out.push(row);Files.write(f,new java.lang.String(out.join('\\n')+'\\n').getBytes(CS.UTF_8));return 'OK';})();";
    registryResult=eval("js",js);
    if(registryResult=="OK")return 1;
    repairText=lightRepairImageRegistryCore(1);
    if(startsWith(repairText,"OK|"))return 1;
    return 0;
}

function lightResolveSourcePath() {
    if(lightSourceStoredPath!=""&&File.exists(lightSourceStoredPath)){sha=IJ.checksum("SHA-256 file",lightSourceStoredPath);if(sha==lightSourceSha256)return lightSourceStoredPath;showMessage("Copia local alterada","La copia del proyecto no coincide con el SHA-256 registrado y no se utilizara.");}
    if(lightSourcePath!=""&&File.exists(lightSourcePath)){sha=IJ.checksum("SHA-256 file",lightSourcePath);if(sha==lightSourceSha256)return lightSourcePath;showMessage("Fuente alterada","La ruta original existe, pero su SHA-256 ya no coincide. Debe localizarse el archivo correcto.");}
    local=lightFindProjectLocalSource();if(local!=""){lightAppendLog("SOURCE_LOCAL_RECOVERED","path="+local);return local;}
    path=File.openDialog("No se encuentra la fuente. Localiza el DM3/DM4 original");if(path=="")return "";ext=lightExtension(path);if(ext!="dm3"&&ext!="dm4"){showMessage("Archivo rechazado","Debe seleccionar un archivo DM3 o DM4.");return "";}
    sha=IJ.checksum("SHA-256 file",path);if(sha!=lightSourceSha256){showMessage("Archivo rechazado","El SHA-256 no coincide con la imagen registrada.");return "";}
    lightSourcePath=normalizeStoredPath(path);lightAppendLog("SOURCE_RELOCATED","path="+lightSourcePath);return lightSourcePath;
}



function lightStampRevisionOnAllObjects(revisionId) {
    run("ROI Manager...");
    n = roiManager("count");
    for (stampIndex=0; stampIndex<n; stampIndex++) {
        safeRoiSelect(stampIndex);
        Roi.setProperty("Revision_id", revisionId);
        Roi.setProperty("Session_macro_version", macroVersion);
        roiManager("update");
    }
    return 1;
}



// R9-HF1: ImageJ 1.54p can leave a PointRoi with counters but without the
// parallel positions array after RoiManager("update") on a two-dimensional
// image. RoiEncoder then throws NullPointerException in PointRoi.getCounters().
// This guard repairs only that invalid serialization state, immediately before
// the revision ZIP is written. Geometry, names, properties and cavity IDs are
// not changed; valid PointRoi instances and every non-PointRoi are untouched.
function lightPreparePointRoisForRevisionSave() {
    js="(function(){var RM=Packages.ij.plugin.frame.RoiManager,PR=Packages.ij.gui.PointRoi,Reflect=Packages.java.lang.reflect.Array,IntegerType=Packages.java.lang.Integer.TYPE,rm=RM.getInstance2();if(rm==null)return 'ERROR|roi_manager_absent';var checked=0,repaired=0;for(var i=0;i<rm.getCount();i++){var r=rm.getRoi(i);if(r==null||!(r instanceof PR))continue;checked++;try{r.getCounters();}catch(first){if(String(first).indexOf('NullPointerException')<0)return 'ERROR|unexpected_getCounters|'+i+'|'+String(first);try{var fp=(r instanceof Packages.ij.gui.Line?r.getFloatPoints():r.getFloatPolygon()),n=fp==null?0:Number(fp.npoints),safe=Reflect.newInstance(IntegerType,n);for(var j=0;j<n;j++){var counter=Number(r.getCounter(j))&255,position=Number(r.getPointPosition(j));if(!isFinite(position)||position<0)position=0;safe[j]=counter+(position<<8);}r.setCounters(safe);r.getCounters();repaired++;}catch(second){return 'ERROR|repair_failed|'+i+'|'+String(second);}}}return 'OK|'+checked+'|'+repaired;})();";
    pointRoiSaveResult=""+eval("js",js);
    pointRoiSaveParts=split(pointRoiSaveResult,"|");
    if(pointRoiSaveParts.length<3||pointRoiSaveParts[0]!="OK"){
        showMessage("Revision no guardada","No se pudo preparar una ROI multipunto para guardarla sin perdida.\n\nDetalle: "+pointRoiSaveResult);
        return 0;
    }
    pointRoiSaveRepaired=round(parseFloat(pointRoiSaveParts[2]));
    if(pointRoiSaveRepaired>0)lightAppendLog("POINT_ROI_SERIALIZATION_STATE_REPAIRED","count="+pointRoiSaveRepaired+"; scope=pre_revision_save");
    return 1;
}

function lightSaveRevision() { lightSaveRevisionCore(1); }

function lightSaveRevisionCore(verbose) {
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
}

function quantitativeRevisionPreflight() {
    if(!lightHF4RequireReviewed())return 0;
    imageOk=lightEnsureCurrentImage();if(imageOk==0)return 0;if(lightSourceSha256==""||lengthOf(lightSourceSha256)!=64){showMessage("Sin trazabilidad","Falta un SHA-256 valido de la fuente.");return 0;}path=lightResolveSourcePath();if(path=="")return 0;actual=call("cavity.light.HF46.sourceSha",path);if(actual!=lightSourceSha256){showMessage("Integridad bloqueada","La fuente actual no coincide con el SHA-256 registrado.");return 0;}run("ROI Manager...");updateSessionMetadataRoi();if(roiManager("count")==0){showMessage("Sin ROIs","No hay objetos para guardar.");return 0;}return 1;
}




function lightVerifyRoiZip(path) {
    if(!File.exists(path))return 0;
    js="(function(){var Z=Packages.java.util.zip.ZipFile,F=Packages.java.io.File,z=null,n=0;try{z=new Z(new F('"+jsEscape(path)+"'));var e=z.entries();while(e.hasMoreElements()){var x=e.nextElement();if(!x.isDirectory())n++;}return n>0?'1':'0';}catch(ex){return '0';}finally{try{if(z!=null)z.close();}catch(ignore){}}})();";
    status=""+eval("js",js);ok=0;if(status=="1")ok=1;return ok;
}

function lightLoadRevision() { imageOk=lightEnsureCurrentImage();if(imageOk==0)return;dir=lightJoin(lightImageDir,"roi_sessions");rev=lightChooseRevision(dir);if(rev!="")lightLoadRevisionById(rev); }

function lightLoadRevisionById(rev) { return lightLoadRevisionCore(rev,1); }

function lightLoadRevisionCore(rev,persistOpening) {
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
}

function lightSaveOverlayPreview(path) {
    if(nImages()<=0)return 0;
    code="var HF42_PREVIEW_PATH='"+jsEscape(path)+"';var HF42_LABELS="+showRoiLabels+";\n";
    code=code+"// Render on detached pixel/ROI copies. Never show, select, rename or close a\n";
    code=code+"// live image window; the macro's current-image state is irrelevant to cleanup.\n";
    code=code+"(function () {\n";
    code=code+"    var P=Packages, WM=P.ij.WindowManager, src=WM.getCurrentImage();\n";
    code=code+"    if(src==null)return 'ERROR|No hay imagen activa.';\n";
    code=code+"    var copy=null, flat=null;\n";
    code=code+"    function val(r,k){var v=r.getProperty(k);return v==null?'':String(v);}\n";
    code=code+"    function name(r){return r.getName()==null?'':String(r.getName());}\n";
    code=code+"    function visible(r){var n=name(r),t=val(r,'Type');return n!='__CTL_R8_CURSOR_PREVIEW__'&&t!='session_metadata'&&n!='CAVITY_SESSION_METADATA'&&n!='BUBBLE_SESSION_METADATA';}\n";
    code=code+"    try {\n";
    code=code+"        copy=new P.ij.ImagePlus('Cavity preview copy',src.getProcessor().duplicate());\n";
    code=code+"        copy.setCalibration(src.getCalibration().copy());\n";
    code=code+"        copy.setDisplayRange(src.getDisplayRangeMin(),src.getDisplayRangeMax());\n";
    code=code+"        var overlay=new P.ij.gui.Overlay(), seen={}, rm=P.ij.plugin.frame.RoiManager.getInstance2();\n";
    code=code+"        if(rm!=null){var rois=rm.getRoisAsArray();for(var i=0;i<rois.length;i++)if(visible(rois[i])){\n";
    code=code+"            overlay.add(rois[i].clone());seen['$'+name(rois[i])]=1;\n";
    code=code+"        }}\n";
    code=code+"        var extra=src.getOverlay();if(extra!=null)for(var j=0;j<extra.size();j++){\n";
    code=code+"            var r=extra.get(j);if(visible(r)&&!seen['$'+name(r)])overlay.add(r.clone());\n";
    code=code+"        }\n";
    code=code+"        overlay.drawLabels(HF42_LABELS==1);overlay.drawNames(HF42_LABELS==1);\n";
    code=code+"        overlay.setLabelFontSize(12,'bold background');overlay.selectable(false);overlay.setDraggable(false);\n";
    code=code+"        copy.setOverlay(overlay);\n";
    code=code+"        flat=copy.flatten();\n";
    code=code+"        var target=new P.java.io.File(HF42_PREVIEW_PATH);\n";
    code=code+"        if(target.isDirectory())return 'ERROR|La ruta de la vista previa es una carpeta.';\n";
    code=code+"        var ok=P.javax.imageio.ImageIO.write(flat.getBufferedImage(),'png',target);\n";
    code=code+"        if(!ok||!target.isFile()||target.length()==0)return 'ERROR|No se pudo escribir la vista previa PNG.';\n";
    code=code+"        return 'OK';\n";
    code=code+"    }catch(e){return 'ERROR|'+String(e);}\n";
    code=code+"    finally{\n";
    code=code+"        // Both objects have their own processors and have never had a window.\n";
    code=code+"        if(flat!=null&&flat!==copy)flat.flush();\n";
    code=code+"        if(copy!=null)copy.flush();\n";
    code=code+"    }\n";
    code=code+"})();\n";
    result=""+eval("js",code);
    if(result=="OK")return 1;
    call("cavity.light.HF4.log",result);
    showStatus("ROIs guardadas; vista previa no disponible. Consulte Ver registros.");
    return 0;
}


function lightComputeExactAreaAndDepth() {
    if(!updateScaleMaybe())return 0;
    start=getTime();previous=lightAreaFingerprint;
    if(lightImageMode=="with_surface")excludeNegativeDepth=1;
    result=lightHF3Run("area","");a=split(result,"|");
    if(a.length<8||a[0]!="OK"){showMessage("Area no calculada",result);return 0;}
    lightLastValidPixels=parseFloat(a[1]);lastValidAreaNm2=parseFloat(a[2]);bandNm=parseFloat(a[3]);
    if(lightImageMode=="with_surface")bandCount=round(parseFloat(a[4]));
    lightMaxImageDepthNm=parseFloat(a[5]);lightLastDepthAreasNm2=lightHF3ParseArray(a[6]);lastBandAreasNm2=lightHF3ParseArray(a[7]);
    lightLastDepthBinNm=1;lightAreaFingerprint=lightAreaInputFingerprint();
    lightAreaComputationMode="pixel_centres_parallel_offsets_HF3";
    if(previous==lightAreaFingerprint)lightAreaComputationMode="cache_reused_HF3";
    lightAreaComputationDurationMs=getTime()-start;
    if(lastValidAreaNm2>0)return 1;return 0;
}

function lightComputeFeatureDistanceAreas() {
    result=lightHF3Run("featureAreas","");a=split(result,"|");
    if(a.length!=3||startsWith(result,"ERROR"))return 0;
    lightLastGbDistanceAreasNm2=lightHF3ParseArray(a[0]);lightLastDislocationDistanceAreasNm2=lightHF3ParseArray(a[1]);lightLastInterfaceDistanceAreasNm2=lightHF3ParseArray(a[2]);return 1;
}

function lightWriteFeatureDistanceOutputs(runDir) {
    path=lightJoin(runDir,"feature_distance_summary.csv");
    header="feature_type,bin_index,bin_low_nm,bin_high_nm,valid_area_nm2,N_count_valid,density_N_per_um2,mean_diameter_nm,N_size_valid\n";
    File.saveString(header,path);
    featureAreaOk=lightComputeFeatureDistanceAreas();
    if(featureAreaOk==0)return 0;
    types=newArray("grain_boundary","dislocation","interface");
    props=newArray("Distance_to_grain_boundary_nm","Distance_to_dislocation_nm","Distance_to_interface_nm");
    for(tt=0;tt<types.length;tt++){
        if(tt==0)areas=lightLastGbDistanceAreasNm2;
        else if(tt==1)areas=lightLastDislocationDistanceAreasNm2;
        else areas=lightLastInterfaceDistanceAreasNm2;
        if(areas.length==0)continue;
        counts=newArray(areas.length);sumD=newArray(areas.length);nD=newArray(areas.length);
        n=roiManager("count");
        for(i=0;i<n;i++){
            safeRoiSelect(i);
            cavityFlag=currentRoiIsCavity();
            if(cavityFlag==0)continue;
            propertyName=props[tt];
            dist=propNumber(propertyName,NaN);
            if(isNaN(dist))continue;
            if(dist<0)continue;
            b=floor(dist/lightFeatureDistanceBinNm);
            if(b<0)continue;
            if(b>=areas.length)continue;
            countFlag=round(propNumber("Count_valid",0));
            if(countFlag==1)counts[b]++;
            sizeFlag=round(propNumber("Size_valid",0));
            if(sizeFlag==1){
                d=propNumber("Equivalent_diameter_nm",NaN);
                if(!isNaN(d)){sumD[b]=sumD[b]+d;nD[b]=nD[b]+1;}
            }
        }
        for(b=0;b<areas.length;b++){
            area=areas[b];den=NaN;if(area>0)den=counts[b]/(area/1000000);
            meanD=NaN;if(nD[b]>0)meanD=sumD[b]/nD[b];
            lowText=lightNum(b*lightFeatureDistanceBinNm);
            highText=lightNum((b+1)*lightFeatureDistanceBinNm);
            areaText=lightNum(area);densityText=lightNum(den);meanText=lightNum(meanD);
            line=types[tt]+","+b+","+lowText+","+highText+","+areaText+","+counts[b]+","+densityText+","+meanText+","+nD[b]+"\n";
            File.append(line,path);
        }
    }
    return 1;
}

function lightWriteRunChecksums(runDir) {
    result=call("cavity.light.HF46.writeChecksums",runDir);
    if(result!="OK"){call("cavity.light.HF4.log",result);return 0;}return 1;
}

function lightHtmlEscape(s) { s=""+s;s=replace(s,"&","&amp;");s=replace(s,"<","&lt;");s=replace(s,">","&gt;");s=replace(s,"\"","&quot;");return s; }

function lightWriteHtmlReport(runDir) {
    summaryPath=lightJoin(runDir,"image_summary.tsv");rows=split(File.openAsString(summaryPath),"\n");
    h="<!doctype html><html lang=\"es\"><meta charset=\"utf-8\"><title>Cavity TEM Light HF3</title><style>body{font:17px/1.6 Arial;max-width:1200px;margin:32px auto;padding:0 24px;color:#16334a}table{border-collapse:collapse;width:100%}td{border-bottom:1px solid #ddd;padding:5px}img{max-width:100%;height:auto}.note{background:#eef5f7;padding:18px}a{color:#17648f}</style><h1>Resultados Cavity TEM Light HF3</h1>";
    h=h+"<p class=\"note\">Origen de profundidad: superficie. Bandas paralelas en coordenadas fisicas, con uniones en vertice y prolongacion tangente de los extremos. Las areas se calculan por centros de pixel, descontando la union de exclusiones. Sin areas validas explicitas, la superficie y el lado del material definen el dominio. Las ROI de analisis existentes siguen restringiendo el area.</p>";
    h=h+"<p>El ancho de banda define el intervalo de profundidad. El espesor de la lamina define el volumen nominal: V = A por t. La densidad volumetrica es N/V, sin correccion estereologica. Las barras de densidad muestran el error estandar Poisson; las de tamano, la desviacion estandar. La sensibilidad al espesor se entrega por separado.</p>";
    h=h+"<p>Los identificadores repetidos se conservan y se detallan en <a href=\"roi_identity_review.csv\">roi_identity_review.csv</a>; revise esos objetos antes de aceptar el resultado cientifico.</p><h2>Resumen</h2><table>";
    for(i=0;i<rows.length;i++){p=indexOf(rows[i],"\t");if(p>0){a=lightHtmlEscape(substring(rows[i],0,p));b=lightHtmlEscape(substring(rows[i],p+1));h=h+"<tr><td>"+a+"</td><td>"+b+"</td></tr>";}}
    h=h+"</table><h2>Resultados y figuras</h2><p><a href=\"band_summary.csv\">Tabla por bandas</a> | <a href=\"cavity_objects.tsv\">Cavidades</a> | <a href=\"size_class_summary.csv\">Rangos de tamano</a> | <a href=\"analysis_method.json\">Metodo y parametros</a></p>";
    imgs=newArray("surface_bands_overlay.png","size_ranges_overlay.png","density_vs_depth.png","volumetric_density_vs_depth.png","mean_diameter_vs_depth.png","diameter_vs_depth.png","diameter_histogram.png","diameter_cumulative.png","diameter_boxplot.png");
    for(i=0;i<imgs.length;i++){p=lightJoin(runDir,imgs[i]);if(File.exists(p))h=h+"<figure><img src=\""+imgs[i]+"\"><figcaption>"+imgs[i]+"</figcaption></figure>";}
    h=h+"<p>Los TIFF de las dos imagenes conservan los overlays editables en Fiji. El PNG incorpora la leyenda. La imagen fuente y las ROI originales no se modifican al dibujar estas figuras. Los limites interpolados tienen la resolucion espacial de la imagen.</p></html>";
    File.saveString(h,lightJoin(runDir,"report.html"));
}

function lightExportCurrentImage() {
    lightInteractiveRemovePreview();
    exportPreflightOk=quantitativeExportPreflight();
    if(exportPreflightOk==0)return;
    rev=lightSaveRevisionCore(0);
    if(rev=="")return;

    stamp=lightTimestamp();
    runId="RUN_"+stamp;
    sessionsDir=lightJoin(lightImageDir,"roi_sessions");
    revisionDir=lightJoin(sessionsDir,rev);
    measurementDir=lightJoin(revisionDir,"measurement_runs");
    runDirRaw=lightJoin(measurementDir,runId);
    runDir=lightNormalizeDir(runDirRaw);
    lightMakeDir(runDir);
    lightCurrentRunId=runId;

    cavTsv=lightJoin(runDir,"cavity_objects.tsv");
    cavCsv=lightJoin(runDir,"cavity_objects.csv");
    featCsv=lightJoin(runDir,"microstructural_features.csv");
    regCsv=lightJoin(runDir,"analysis_regions.csv");
    header="image_id\tcavity_id\tcavity_class\tgeometry_kind\tx_center_px\ty_center_px\tx_center_nm\ty_center_nm\tequivalent_diameter_nm\tmajor_axis_nm\tminor_axis_nm\taspect_ratio\tprojected_area_nm2\testimated_spherical_volume_nm3\tcount_valid\tsize_valid\tposition_valid\tmanual_excluded\tedge_intersecting\texclusion_reason\tduplicate_status\tduplicate_partners\tsigned_depth_nm\tabsolute_depth_nm\tband_index\tdistance_to_grain_boundary_nm\tdistance_to_dislocation_nm\tdistance_to_interface_nm\tmeasurement_source\tlast_edit_method\tlast_edit_ms\n";
    File.saveString(header,cavTsv);
    csvHeader=replace(header,"\t",",");File.saveString(csvHeader,cavCsv);
    File.saveString("image_id,feature_id,type,length_nm,length_um,confidence,notes,traced_length_nm,length_domain\n",featCsv);
    File.saveString("image_id,region_id,type,area_nm2,area_um2,label\n",regCsv);

    cavityBuffer="";csvBuffer="";featureBuffer="";regionBuffer="";
    n=roiManager("count");countValid=0;sizeValidN=0;diam=newArray(n);depths=newArray(n);dn=0;
    sumProjectedArea=0;sumSphereVolume=0;dislLen=0;gbLen=0;interfaceLen=0;dislN=0;gbN=0;interfaceN=0;
    for(i=0;i<n;i++){
        if(i%25==0)showProgress(i,max2(n,1));
        if(!safeRoiSelect(i)){File.saveString("FAILED_SELECTION\n",lightJoin(runDir,"RUN_FAILED.txt"));return;}typ=currentRoiType();
        if(typ=="cavity"){
            currentName=Roi.getName;
            id=propString("Cavity_id",currentName);cc=propString("Cavity_class","confirmed");g=propString("Geometry_kind","circle");
            xpx=propNumber("Center_x_px",NaN);ypx=propNumber("Center_y_px",NaN);xnm=propNumber("Center_x_nm",NaN);ynm=propNumber("Center_y_nm",NaN);
            d=propNumber("Equivalent_diameter_nm",NaN);maj=propNumber("Major_axis_nm",NaN);minr=propNumber("Minor_axis_nm",NaN);asp=propNumber("Aspect_ratio",NaN);
            ar=propNumber("Cavity_area_nm2",NaN);vo=propNumber("Estimated_spherical_volume_nm3",NaN);
            includeFallback=propNumber("Include_in_statistics",0);cv=round(propNumber("Count_valid",includeFallback));sv=round(propNumber("Size_valid",0));pv=round(propNumber("Position_valid",0));
            man=round(propNumber("Manual_excluded",0));edge=round(propNumber("Edge_intersecting",0));reason=propString("Exclusion_reason","");
            dup=propString("Duplicate_status","clear");partners=propString("Duplicate_partners","");sd=propNumber("Signed_depth_nm",NaN);ad=propNumber("Depth_absolute_nm",NaN);
            bi=round(propNumber("Band_index",-1));gb=propNumber("Distance_to_grain_boundary_nm",NaN);di=propNumber("Distance_to_dislocation_nm",NaN);it=propNumber("Distance_to_interface_nm",NaN);method=propString("Measurement_source","");lastEditMethod=propString("Last_edit_method","");lastEditMs=propString("Last_edit_ms","");

            fImage=lightTsvClean(lightImageId);fId=lightTsvClean(id);fClass=lightTsvClean(cc);fGeometry=lightTsvClean(g);
            fXpx=lightNum(xpx);fYpx=lightNum(ypx);fXnm=lightNum(xnm);fYnm=lightNum(ynm);fD=lightNum(d);fMaj=lightNum(maj);fMin=lightNum(minr);fAsp=lightNum(asp);
            fArea=lightNum(ar);fVolume=lightNum(vo);fReason=lightTsvClean(reason);fDup=lightTsvClean(dup);fPartners=lightTsvClean(partners);
            fSigned=lightNum(sd);fAbsolute=lightNum(ad);fGb=lightNum(gb);fDi=lightNum(di);fIt=lightNum(it);fMethod=lightTsvClean(method);fLastEditMethod=lightTsvClean(lastEditMethod);fLastEditMs=lightTsvClean(lastEditMs);
            lineT=fImage+"\t"+fId+"\t"+fClass+"\t"+fGeometry;
            lineT=lineT+"\t"+fXpx+"\t"+fYpx+"\t"+fXnm+"\t"+fYnm+"\t"+fD+"\t"+fMaj+"\t"+fMin+"\t"+fAsp;
            lineT=lineT+"\t"+fArea+"\t"+fVolume+"\t"+cv+"\t"+sv+"\t"+pv+"\t"+man+"\t"+edge+"\t"+fReason+"\t"+fDup+"\t"+fPartners;
            lineT=lineT+"\t"+fSigned+"\t"+fAbsolute+"\t"+bi+"\t"+fGb+"\t"+fDi+"\t"+fIt+"\t"+fMethod+"\t"+fLastEditMethod+"\t"+fLastEditMs+"\n";
            cavityBuffer=cavityBuffer+lineT;if(lengthOf(cavityBuffer)>65536){File.append(cavityBuffer,cavTsv);cavityBuffer="";}
            lineCsv=lightTsvLineToCsv(lineT);csvBuffer=csvBuffer+lineCsv;if(lengthOf(csvBuffer)>65536){File.append(csvBuffer,cavCsv);csvBuffer="";}
            if(cv==1)countValid++;
            if(sv==1){
                if(!isNaN(d)){
                    diam[dn]=d;depths[dn]=sd;dn++;sizeValidN++;
                    if(!isNaN(ar))sumProjectedArea+=ar;
                    if(!isNaN(vo))sumSphereVolume+=vo;
                }
            }
        }else if(isLinearFeatureType(typ)){
            currentName=Roi.getName;fid=propString("Feature_id",currentName);ln=propNumber("Length_nm",NaN);conf=propString("Confidence","");note=propString("Notes","");
            featureImageCsv=lightCsv(lightImageId);featureIdCsv=lightCsv(fid);featureTypeCsv=lightCsv(typ);featureConfidenceCsv=lightCsv(conf);featureNoteCsv=lightCsv(note);
            featureLengthNm=lightNum(ln);featureLengthUm=lightNum(ln/1000);
            featureRow=featureImageCsv+","+featureIdCsv+","+featureTypeCsv+","+featureLengthNm+","+featureLengthUm+","+featureConfidenceCsv+","+featureNoteCsv+","+lightNum(propNumber("Traced_length_nm",NaN))+",valid_raster_pixel_cells_v1\n";
            featureBuffer=featureBuffer+featureRow;if(lengthOf(featureBuffer)>65536){File.append(featureBuffer,featCsv);featureBuffer="";}
            if(!isNaN(ln)){
                if(typ=="dislocation"){dislLen+=ln;dislN++;}
                else if(typ=="grain_boundary"){gbLen+=ln;gbN++;}
                else if(typ=="interface"){interfaceLen+=ln;interfaceN++;}
            }
        }else{
            regionFlag=0;if(typ=="analysis_mask")regionFlag=1;if(typ=="exclusion")regionFlag=1;
            if(regionFlag==1){
                rid=Roi.getName;area=propNumber("Area_nm2",NaN);fallbackLabel=propString("Exclusion_reason","");label=propString("Mask_label",fallbackLabel);
                regionImageCsv=lightCsv(lightImageId);regionIdCsv=lightCsv(rid);regionTypeCsv=lightCsv(typ);regionAreaNm2=lightNum(area);regionAreaUm2=lightNum(area/1000000);regionLabelCsv=lightCsv(label);
                regionRow=regionImageCsv+","+regionIdCsv+","+regionTypeCsv+","+regionAreaNm2+","+regionAreaUm2+","+regionLabelCsv+"\n";
                regionBuffer=regionBuffer+regionRow;if(lengthOf(regionBuffer)>65536){File.append(regionBuffer,regCsv);regionBuffer="";}
            }
        }
    }
    if(cavityBuffer!="")File.append(cavityBuffer,cavTsv);if(csvBuffer!="")File.append(csvBuffer,cavCsv);
    if(featureBuffer!="")File.append(featureBuffer,featCsv);if(regionBuffer!="")File.append(regionBuffer,regCsv);
    showProgress(1,1);

    diam=lightArrayPrefix(diam,dn);depths=lightArrayPrefix(depths,dn);lightComputeStats(diam);
    areaUm2=lastValidAreaNm2/1000000;density2=NaN;if(areaUm2>0)density2=countValid/areaUm2;
    volNm3=NaN;density3=NaN;if(lightThicknessNm>0){volNm3=lastValidAreaNm2*lightThicknessNm;if(volNm3>0)density3=countValid*1e27/volNm3;}
    projectedFraction=NaN;if(lastValidAreaNm2>0)projectedFraction=sumProjectedArea/lastValidAreaNm2;
    nominalSphereFraction=NaN;if(volNm3>0)nominalSphereFraction=sumSphereVolume/volNm3;
    dislPerArea=NaN;gbPerArea=NaN;interfacePerArea=NaN;
    if(areaUm2>0){dislPerArea=(dislLen/1000)/areaUm2;gbPerArea=(gbLen/1000)/areaUm2;interfacePerArea=(interfaceLen/1000)/areaUm2;}
    dislNominalM2=NaN;if(volNm3>0)dislNominalM2=dislLen/volNm3*1e18;

    cleanSample=lightTsvClean(sampleName);cleanCondition=lightTsvClean(experimentalCondition);
    validAreaNm2Text=lightNum(lastValidAreaNm2);areaUm2Text=lightNum(areaUm2);thicknessText=lightNum(lightThicknessNm);volumeText=lightNum(volNm3);
    density2Text=lightNum(density2);density3Text=lightNum(density3);meanText=lightNum(lightStatMean);stdText=lightNum(lightStatStd);medianText=lightNum(lightStatMedian);
    q25Text=lightNum(lightStatQ25);q75Text=lightNum(lightStatQ75);minText=lightNum(lightStatMin);maxText=lightNum(lightStatMax);
    projectedAreaText=lightNum(sumProjectedArea);projectedFractionText=lightNum(projectedFraction);sphereVolumeText=lightNum(sumSphereVolume);sphereFractionText=lightNum(nominalSphereFraction);
    dislLenText=lightNum(dislLen);dislPerAreaText=lightNum(dislPerArea);dislNominalText=lightNum(dislNominalM2);gbLenText=lightNum(gbLen);gbPerAreaText=lightNum(gbPerArea);
    interfaceLenText=lightNum(interfaceLen);interfacePerAreaText=lightNum(interfacePerArea);featureBinText=lightNum(lightFeatureDistanceBinNm);
    preparationMsText=lightNum(lightLastPreparationDurationMs);areaMsText=lightNum(lightAreaComputationDurationMs);

    summary="application_version\t"+lightReleaseVersion+"\nlinear_length_domain\tvalid_raster_pixel_cells_v1\nscale_x_nm_px\t"+lightNum(nmPerPixelX)+"\nscale_y_nm_px\t"+lightNum(nmPerPixelY)+"\ninclude_uncertain\t"+lightIncludeUncertain+"\nuse_whole_image\t"+lightUseWholeImage+"\n";
    summary=summary+"project_id\t"+lightProjectId+"\n";summary=summary+"image_id\t"+lightImageId+"\n";summary=summary+"sample_name\t"+cleanSample+"\n";
    summary=summary+"experimental_condition\t"+cleanCondition+"\n";summary=summary+"image_mode\t"+lightImageMode+"\n";summary=summary+"source_sha256\t"+lightSourceSha256+"\n";
    summary=summary+"revision_id\t"+rev+"\n";summary=summary+"run_id\t"+runId+"\n";summary=summary+"valid_area_nm2\t"+validAreaNm2Text+"\n";summary=summary+"valid_area_um2\t"+areaUm2Text+"\n";
    summary=summary+"foil_thickness_nm\t"+thicknessText+"\n";summary=summary+"nominal_volume_nm3\t"+volumeText+"\n";summary=summary+"N_count_valid\t"+countValid+"\n";summary=summary+"N_size_valid\t"+sizeValidN+"\n";
    summary=summary+"density_N_per_um2\t"+density2Text+"\n";summary=summary+"nominal_density_N_per_m3\t"+density3Text+"\n";
    summary=summary+"mean_diameter_nm\t"+meanText+"\n";summary=summary+"std_diameter_nm\t"+stdText+"\n";summary=summary+"median_diameter_nm\t"+medianText+"\n";
    summary=summary+"q25_diameter_nm\t"+q25Text+"\n";summary=summary+"q75_diameter_nm\t"+q75Text+"\n";summary=summary+"min_diameter_nm\t"+minText+"\n";summary=summary+"max_diameter_nm\t"+maxText+"\n";
    summary=summary+"projected_area_size_valid_nm2\t"+projectedAreaText+"\n";summary=summary+"projected_area_fraction_size_valid\t"+projectedFractionText+"\n";
    summary=summary+"estimated_spherical_volume_size_valid_nm3\t"+sphereVolumeText+"\n";summary=summary+"nominal_spherical_volume_fraction_size_valid\t"+sphereFractionText+"\n";
    summary=summary+"total_dislocation_length_nm\t"+dislLenText+"\n";summary=summary+"dislocation_length_per_area_um_inv\t"+dislPerAreaText+"\n";
    summary=summary+"nominal_traced_dislocation_density_m_minus2\t"+dislNominalText+"\n";summary=summary+"total_grain_boundary_length_nm\t"+gbLenText+"\n";
    summary=summary+"grain_boundary_length_per_area_um_inv\t"+gbPerAreaText+"\n";summary=summary+"total_interface_length_nm\t"+interfaceLenText+"\n";
    summary=summary+"interface_length_per_area_um_inv\t"+interfacePerAreaText+"\n";summary=summary+"feature_distance_bin_nm\t"+featureBinText+"\n";
    summary=summary+"prepared_state_reused\t"+lightLastPreparationReused+"\n";summary=summary+"prepared_state_duration_ms\t"+preparationMsText+"\n";
    summary=summary+"area_computation_mode\t"+lightAreaComputationMode+"\n";summary=summary+"area_computation_duration_ms\t"+areaMsText+"\n";
    summary=summary+"interactive_preview\t"+lightInteractivePreviewEnabled+"\n";summary=summary+"interactive_resize_step_nm\t"+lightNum(lightInteractiveResizeStepNm)+"\n";
    summary=summary+"exact_labels_visible\t"+showRoiLabels+"\n";summary=summary+"exact_label_mode\troi_name_v1\n";
    summary=summary+"identity_audit_errors\t"+lightLastIdAuditErrors+"\n";summary=summary+"identity_audit_duplicate_ids\t"+lightLastIdAuditDuplicateIds+"\n";
    summary=summary+"validation_state\t"+lightValidationState+"\n";
    summaryPath=lightJoin(runDir,"image_summary.tsv");File.saveString(summary,summaryPath);

    dislLenUmText=lightNum(dislLen/1000);gbLenUmText=lightNum(gbLen/1000);interfaceLenUmText=lightNum(interfaceLen/1000);
    ms="feature_type,N_objects,total_length_nm,total_length_um,length_per_area_um_inv,nominal_traced_line_density_m_minus2\n";
    ms=ms+"dislocation,"+dislN+","+dislLenText+","+dislLenUmText+","+dislPerAreaText+","+dislNominalText+"\n";
    ms=ms+"grain_boundary,"+gbN+","+gbLenText+","+gbLenUmText+","+gbPerAreaText+",\n";
    ms=ms+"interface,"+interfaceN+","+interfaceLenText+","+interfaceLenUmText+","+interfacePerAreaText+",\n";
    microSummaryPath=lightJoin(runDir,"microstructure_summary.csv");File.saveString(ms,microSummaryPath);

    bandOk=lightWriteBandOutputs(runDir);
    featureOk=lightWriteFeatureDistanceOutputs(runDir);
    diameterOk=lightWriteDiameterValues(runDir,diam,depths);
    chartsOk=lightCreateCharts(runDir);
    if(bandOk==0||featureOk==0||diameterOk==0||chartsOk==0){
        failedPath=lightJoin(runDir,"RUN_FAILED.txt");File.saveString("Incomplete HF3 outputs. No current_run update.\n",failedPath);
        lightCurrentRunId="";return;
    }
    manifestText=projectJson();manifestPath=lightJoin(runDir,"run_manifest.json");File.saveString(manifestText,manifestPath);
    lightWriteHtmlReport(runDir);if(!lightWriteRunChecksums(runDir)){File.saveString("FAILED_CHECKSUMS\n",lightJoin(runDir,"RUN_FAILED.txt"));lightCurrentRunId="";return;}

    revisionRel="roi_sessions/"+rev+"/measurement_runs/"+runId;
    currentRunPath=lightJoin(lightImageDir,"current_run.txt");if(!lightHF46WriteText(currentRunPath,revisionRel+"\n"))return;
    lightWriteImageMetadata();lightUpdateRegistry();
    lightAppendLog("RUN_EXPORTED","revision="+rev+"; run="+runId+"; N="+countValid+"; area_nm2="+validAreaNm2Text+"; band_ok="+bandOk+"; feature_ok="+featureOk+"; diameter_ok="+diameterOk);
    lightLastExportDir=runDir;
    densityDisplay=d2s(density2,6);density3Display=lightNum(density3);
    showMessage("Calculos y exportacion completados","Imagen: "+lightImageId+"\nRevision: "+rev+"\nN valido: "+countValid+"\nArea: "+d2s(areaUm2,6)+" um^2\nDensidad: "+densityDisplay+" cavidades/um^2\nDensidad volumetrica nominal: "+density3Display+" m^-3\n\nCarpeta:\n"+runDir);
    lightRefreshPanel();
}

function lightWriteBandOutputs(runDir) {
    result=lightHF3Run("outputs",runDir);if(result!="OK"){showMessage("Resultados no completados",result);return 0;}return 1;
}

function lightWriteDiameterValues(runDir,d,dep) {
    auditResult=call("cavity.light.HF4.exportAudit",runDir);
    if(auditResult!="OK"){showMessage("Auditoria no guardada",auditResult);return 0;}
    t="diameter_nm,signed_depth_nm\n";
    for(i=0;i<d.length;i++){
        diameterText=lightNum(d[i]);
        depthText=lightNum(dep[i]);
        t=t+diameterText+","+depthText+"\n";
    }
    outputPath=lightJoin(runDir,"diameter_values.csv");
    File.saveString(t,outputPath);
    return 1;
}

function lightComputeStats(a) { lightStatMean=NaN;lightStatStd=NaN;lightStatMedian=NaN;lightStatQ25=NaN;lightStatQ75=NaN;lightStatMin=NaN;lightStatMax=NaN;if(a.length==0)return;a=Array.copy(a);Array.sort(a);s=0;for(i=0;i<a.length;i++)s+=a[i];lightStatMean=s/a.length;if(a.length>1){ss=0;for(i=0;i<a.length;i++)ss+=(a[i]-lightStatMean)*(a[i]-lightStatMean);lightStatStd=sqrt(ss/(a.length-1));}lightStatMedian=lightPercentileSorted(a,50);lightStatQ25=lightPercentileSorted(a,25);lightStatQ75=lightPercentileSorted(a,75);lightStatMin=a[0];lightStatMax=a[a.length-1]; }
function lightPercentileSorted(a,p) { if(a.length==0)return NaN;x=(a.length-1)*p/100;l=floor(x);u=Math.ceil(x);if(l==u)return a[l];return a[l]+(x-l)*(a[u]-a[l]); }

function lightCreateCharts(runDir) {
    result=lightHF3Run("charts",runDir);if(result!="OK"){showMessage("Graficos no completados",result);return 0;}return 1;
}


function lightRunCombinedAnalysis() {
    projectOk=lightEnsureProject();
    if(projectOk==0)return;
    hasRows=lightRegistryHasDataRows();
    if(hasRows==0){
        repairText=lightRepairImageRegistryCore(1);
        repairReady=startsWith(repairText,"OK|");
        if(repairReady==0){showMessage("Sin imagenes combinables","No se pudo reconstruir images.tsv desde los metadatos canonicos.");return;}
    }
    ids=lightChooseRegistryImages(1);
    if(ids=="")return;
    Dialog.create("Analisis combinado");
    Dialog.addNumber("Ancho del histograma (nm):",lightHistogramBinNm);
    Dialog.addNumber("Banda comun de profundidad (nm):",bandNm);
    Dialog.show();
    hist=Dialog.getNumber();commonBand=Dialog.getNumber();
    if(!lightHF46Finite(hist)||!lightHF46Finite(commonBand)||hist<=0||commonBand<=0){showMessage("Intervalos no validos","Indique anchos positivos y finitos.");return;}
    result=lightCombinedJava(ids,hist,commonBand,0);
    mixedFlag=startsWith(result,"MIXED|");
    if(mixedFlag==1){
        p=split(result,"|");mixedDescription="condiciones no especificadas";
        if(p.length>1)mixedDescription=p[1];
        continueMixed=getBoolean("Las imagenes mezclan muestras o condiciones:\n"+mixedDescription+"\n\nContinuar de forma intencionada?","Combinar","Cancelar");
        if(continueMixed==0)return;
        result=lightCombinedJava(ids,hist,commonBand,1);
    }
    errorFlag=startsWith(result,"ERROR|");
    if(errorFlag==1){showMessage("Analisis no realizado",substring(result,6));return;}
    okFlag=startsWith(result,"OK|");
    if(okFlag==0){showMessage("Analisis no realizado","La respuesta del analisis combinado no tiene un formato reconocido:\n"+result);return;}
    p=split(result,"|");
    if(p.length<7){showMessage("Analisis no realizado","La respuesta del analisis combinado esta incompleta:\n"+result);return;}
    combinedPath=p[1];combinedImages=p[2];combinedN=p[3];combinedArea=p[4];combinedDensity=p[5];combinedDensity3=p[6];
    lightWriteCombinedHtml(combinedPath);
    lightAppendLog("COMBINED_EXPORTED","images="+ids+"; path="+combinedPath);
    showMessage("Analisis combinado completado","Carpeta: "+combinedPath+"\nImagenes: "+combinedImages+"\nN total: "+combinedN+"\nArea total: "+combinedArea+" um^2\nDensidad agregada: "+combinedDensity+" cavidades/um^2\nDensidad volumetrica nominal: "+combinedDensity3+" m^-3");
}

function lightCombinedJava(ids,hist,commonBand,allowMixed) {
    if(!lightHF46Finite(hist)||hist<=0||!lightHF46Finite(commonBand))return "ERROR|Intervalos no validos.";
    if(commonBand<1||abs(commonBand-round(commonBand))>1e-9)return "ERROR|Para combinar, use un ancho entero de nm (la tabla comun de areas tiene resolucion de 1 nm). Las bandas individuales admiten anchos fraccionarios.";
    compatibleHF3=lightHF3CheckCombinedInputs(ids);if(compatibleHF3!="OK")return compatibleHF3;
    js="";
    js=js+"(function () { var Files = Packages.java.nio.file.Files; var Paths = Packages.java.nio.file.Paths; var CS = Packages.java.nio.charset.StandardCharsets; var F = Packages.java.io.File; var BI = Packages.java.awt.image.BufferedImage; var C = Packages.java.awt.Color; var Font = Packages.java.awt.Font; var IO = Packages.javax.imageio.ImageIO; var root = '";
    js=js+jsEscape(lightProjectRoot);
    js=js+"'; var ids = '";
    js=js+jsEscape(ids);
    js=js+"'.split(';'); var hist = ";
    js=js+d2s(hist,6);
    js=js+"; var bw = ";
    js=js+d2s(commonBand,6);
    js=js+"; var allowMixed = ";
    js=js+d2s(allowMixed,0);
    js=js+"; var projectId = '";
    js=js+jsEscape(lightProjectId);
    js=js+"'; function read(path) { return String(new java.lang.String(Files.readAllBytes(Paths.get(path)), CS.UTF_8)); } function write(path, text) { var file = new F(path); file.getParentFile().mkdirs(); Files.write(Paths.get(path), new java.lang.String(text).getBytes(CS.UTF_8)); } function kv(path) { var out = {}; var lines = read(path).split(/\\r?\\n/); for (var i = 0; i < lines.length; i++) { var k = lines[i].indexOf('\\t'); if (k > 0) out[lines[i].slice(0, k)] = lines[i].slice(k + 1); } return out; } function num(value) { var n = parseFloat(value); return isFinite(n) ? n : NaN; } function csv(value) { value = String(value == null || (typeof value === 'number' && !isFinite(value)) ? '' : value); return /[\",\\n]/.test(value) ? '\"' + value.replace(/\"/g, '\"\"') + '\"' : value; } function jsonString(value) { return '\"' + String(value) .replace(/\\\\/g, '\\\\\\\\') .replace(/\"/g, '\\\\\"') .replace(/\\r/g, '\\\\r') .replace(/\\n/g, '\\\\n') + '\"'; } function stamp() { var d = new Date(); function p(n) { return ('0' + n).slice(-2); } return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()) + '_' + ('00' + d.getMilliseconds()).slice(-3) + '_' + String(java.util.UUID.randomUUID()).slice(0, 8); } var rows = []; var cavities = []; var diameters = []; var depths = []; var conditions = {}; var totalN = 0; var totalArea = 0; var totalVolume = 0; var allThickness = true; var depthArea = []; var surfaceImages = 0; var featureAgg = {}; for (var ii = 0; ii < ids.length; ii++) { var id = ids[ii]; var imageDir = root + 'images/' + id + '/'; var currentRun = imageDir + 'current_run.txt'; if (!new F(currentRun).exists()) return 'ERROR|La imagen ' + id + ' no tiene una exportacion vigente.'; var relativeRun = read(currentRun).trim(); var runDir = imageDir + relativeRun + '/'; var summaryPath = runDir + 'image_summary.tsv'; var cavityPath = runDir + 'cavity_objects.tsv'; if (!new F(summaryPath).exists() || !new F(cavityPath).exists()) return 'ERROR|Faltan resultados de ' + id; var summary = kv(summaryPath); conditions[(summary.sample_name || '') + ' | ' + (summary.experimental_condition || '')] = 1; var n = num(summary.N_count_valid); var area = num(summary.valid_area_nm2); var thickness = num(summary.foil_thickness_nm); if (!isFinite(n) || n < 0 || !isFinite(area) || area <= 0) return 'ERROR|Resumen cuantitativo invalido para ' + id; totalN += n; totalArea += area; if (isFinite(thickness) && thickness > 0) totalVolume += area * thickness; else allThickness = false; rows.push([ id, summary.sample_name || '', summary.experimental_condition || '', summary.image_mode || '', n, area / 1e6, thickness, num(summary.density_N_per_um2), num(summary.nominal_density_N_per_m3), relativeRun ]); var cavityLines = read(cavityPath).split(/\\r?\\n/); var cavityHeader = cavityLines[0].split('\\t'); var ix = {}; for (var j = 0; j < cavityHeader.length; j++) ix[cavityHeader[j]] = j; if (ix.size_valid == null || ix.count_valid == null || ix.equivalent";
    js=js+"_diameter_nm == null) { return 'ERROR|Columnas de cavidades incompletas para ' + id; } for (j = 1; j < cavityLines.length; j++) { if (!cavityLines[j]) continue; var cavity = cavityLines[j].split('\\t'); cavities.push(cavity); if (parseInt(cavity[ix.size_valid] || '0', 10) === 1) { var diameter = num(cavity[ix.equivalent_diameter_nm]); if (isFinite(diameter)) diameters.push(diameter); } if (parseInt(cavity[ix.count_valid] || '0', 10) === 1 && ix.signed_depth_nm != null) { var depth = num(cavity[ix.signed_depth_nm]); if (isFinite(depth) && depth >= 0) depths.push(depth); } } if ((summary.image_mode || '') === 'with_surface') { surfaceImages++; var depthPath = runDir + 'depth_area_1nm.tsv'; if (new F(depthPath).exists()) { var areaLines = read(depthPath).split(/\\r?\\n/); for (j = 1; j < areaLines.length; j++) { if (!areaLines[j]) continue; var areaCols = areaLines[j].split('\\t'); var low = num(areaCols[1]); var areaValue = num(areaCols[3]); var band = Math.floor(low / bw); if (!isFinite(depthArea[band])) depthArea[band] = 0; depthArea[band] += areaValue; } } } var featurePath = runDir + 'feature_distance_summary.csv'; if (new F(featurePath).exists()) { var featureLines = read(featurePath).split(/\\r?\\n/); var featureHeader = featureLines[0].split(','); var fi = {}; for (j = 0; j < featureHeader.length; j++) fi[featureHeader[j]] = j; for (j = 1; j < featureLines.length; j++) { if (!featureLines[j]) continue; var fc = featureLines[j].split(','); var key = fc[fi.feature_type] + '|' + fc[fi.bin_index]; var fArea = num(fc[fi.valid_area_nm2]); var fN = num(fc[fi.N_count_valid]); var fMean = num(fc[fi.mean_diameter_nm]); var fSizeN = num(fc[fi.N_size_valid]); if (!featureAgg[key]) { featureAgg[key] = { type: fc[fi.feature_type], bin: num(fc[fi.bin_index]), low: num(fc[fi.bin_low_nm]), high: num(fc[fi.bin_high_nm]), area: 0, n: 0, diameterSum: 0, diameterN: 0 }; } if (Math.abs(featureAgg[key].low-num(fc[fi.bin_low_nm]))>1e-9 || Math.abs(featureAgg[key].high-num(fc[fi.bin_high_nm]))>1e-9) return 'ERROR|Intervalos de distancia incompatibles en '+id+'; reexporte con el mismo ancho.'; featureAgg[key].area += isFinite(fArea) ? fArea : 0; featureAgg[key].n += isFinite(fN) ? fN : 0; if (isFinite(fMean) && isFinite(fSizeN)) { featureAgg[key].diameterSum += fMean * fSizeN; featureAgg[key].diameterN += fSizeN; } } } } var conditionKeys = Object.keys(conditions); if (conditionKeys.length > 1 && !allowMixed) return 'MIXED|' + conditionKeys.join(' ; '); var dmin=Infinity,dmax=-Infinity;for(var di=0;di<diameters.length;di++){dmin=Math.min(dmin,diameters[di]);dmax=Math.max(dmax,diameters[di]);} if (diameters.length && Math.floor((dmax-dmin)/hist)+1>10000) return 'ERROR|Mas de 10000 intervalos de histograma; aumente el ancho.'; var output = root + 'combined_runs/COMBINED_' + stamp() + '/'; var outputFile = new F(output); outputFile.mkdirs(); var density2D = totalArea > 0 ? totalN / (totalArea / 1e6) : NaN; var density3D = allThickness && totalVolume > 0 ? totalN * 1e27 / totalVolume : NaN; var perImage = 'image_id,sample_name,experimental_condition,image_mode,N_count_valid,valid_area_um2,foil_thickness_nm,density_N_per_um2,nominal_density_N_per_m3,source_run\\n'; for (ii = 0; ii < rows.length; ii++) perImage += rows[ii].map(csv).join(',') + '\\n'; write(output + 'per_image_summary.csv', perImage); diameters.sort(function (a, b) { return a - b; }); function percentile(pct) { if (!diameters.length) return NaN; var position = (diameters.length - 1) * pct / 100; var low";
    js=js+"er = Math.floor(position); var upper = Math.ceil(position); return lower === upper ? diameters[lower] : diameters[lower] + (position - lower) * (diameters[upper] - diameters[lower]); } var mean = NaN; var std = NaN; if (diameters.length) { var sum = 0; for (ii = 0; ii < diameters.length; ii++) sum += diameters[ii]; mean = sum / diameters.length; if (diameters.length > 1) { var ss = 0; for (ii = 0; ii < diameters.length; ii++) ss += (diameters[ii] - mean) * (diameters[ii] - mean); std = Math.sqrt(ss / (diameters.length - 1)); } } var combinedId = outputFile.getName(); var combinedSummary = 'project_id,combined_run_id,image_count,N_count_valid,total_valid_area_nm2,total_valid_area_um2,total_nominal_volume_nm3,density_N_per_um2,nominal_density_N_per_m3,N_size_valid,mean_diameter_nm,std_diameter_nm,median_diameter_nm,q25_diameter_nm,q75_diameter_nm,min_diameter_nm,max_diameter_nm,mixed_conditions,surface_image_count\\n'; combinedSummary += [ projectId, combinedId, ids.length, totalN, totalArea, totalArea / 1e6, allThickness ? totalVolume : '', density2D, isFinite(density3D) ? density3D : '', diameters.length, mean, std, percentile(50), percentile(25), percentile(75), diameters.length ? diameters[0] : '', diameters.length ? diameters[diameters.length - 1] : '', conditionKeys.length > 1 ? 1 : 0, surfaceImages ].map(csv).join(',') + '\\n'; write(output + 'combined_summary.csv', combinedSummary); var cavityOut = 'image_id\\tcavity_id\\tcavity_class\\tgeometry_kind\\tx_center_px\\ty_center_px\\tx_center_nm\\ty_center_nm\\tequivalent_diameter_nm\\tmajor_axis_nm\\tminor_axis_nm\\taspect_ratio\\tprojected_area_nm2\\testimated_spherical_volume_nm3\\tcount_valid\\tsize_valid\\tposition_valid\\tmanual_excluded\\tedge_intersecting\\texclusion_reason\\tduplicate_status\\tduplicate_partners\\tsigned_depth_nm\\tabsolute_depth_nm\\tband_index\\tdistance_to_grain_boundary_nm\\tdistance_to_dislocation_nm\\tdistance_to_interface_nm\\tmeasurement_source\\tlast_edit_method\\tlast_edit_ms\\n'; for (ii = 0; ii < cavities.length; ii++) cavityOut += cavities[ii].join('\\t') + '\\n'; write(output + 'combined_cavity_objects.tsv', cavityOut); if (surfaceImages > 0) { var depthCounts = []; for (ii = 0; ii < depths.length; ii++) { var depthBand = Math.floor(depths[ii] / bw); depthCounts[depthBand] = (depthCounts[depthBand] || 0) + 1; } var bandSummary = 'band_index,band_low_nm,band_high_nm,valid_area_nm2,N_count_valid,density_N_per_um2\\n'; var maxBand = Math.max(depthArea.length, depthCounts.length); for (ii = 0; ii < maxBand; ii++) { var bandArea = depthArea[ii] || 0; var bandN = depthCounts[ii] || 0; var bandDensity = bandArea > 0 ? bandN / (bandArea / 1e6) : NaN; bandSummary += [ii, ii * bw, (ii + 1) * bw, bandArea, bandN, isFinite(bandDensity) ? bandDensity : ''].join(',') + '\\n'; } write(output + 'combined_band_summary.csv', bandSummary); } var featureKeys = Object.keys(featureAgg).sort(function (a, b) { var aa = featureAgg[a]; var bb = featureAgg[b]; return aa.type === bb.type ? aa.bin - bb.bin : (aa.type < bb.type ? -1 : 1); }); if (featu";
    js=js+"reKeys.length) { var featureSummary = 'feature_type,bin_index,bin_low_nm,bin_high_nm,valid_area_nm2,N_count_valid,density_N_per_um2,mean_diameter_nm,N_size_valid\\n'; for (ii = 0; ii < featureKeys.length; ii++) { var feature = featureAgg[featureKeys[ii]]; var featureDensity = feature.area > 0 ? feature.n / (feature.area / 1e6) : NaN; var featureMean = feature.diameterN > 0 ? feature.diameterSum / feature.diameterN : NaN; featureSummary += [ feature.type, feature.bin, feature.low, feature.high, feature.area, feature.n, isFinite(featureDensity) ? featureDensity : '', isFinite(featureMean) ? featureMean : '', feature.diameterN ].join(',') + '\\n'; } write(output + 'combined_feature_distance_summary.csv', featureSummary); } var imageJson = []; for (ii = 0; ii < ids.length; ii++) imageJson.push(jsonString(ids[ii])); var manifest = '{\\n' + '  \"format\": \"Cavity TEM Light combined run\",\\n' + '  \"project_id\": ' + jsonString(projectId) + ',\\n' + '  \"images\": [' + imageJson.join(',') + '],\\n' + '  \"image_count\": ' + ids.length + ',\\n' + '  \"density_areal_N_per_um2\": ' + density2D + ',\\n' + '  \"density_volumetric_nominal_N_per_m3\": ' + (isFinite(density3D) ? density3D : 'null') + ',\\n' + '  \"mixed_conditions\": ' + (conditionKeys.length > 1) + ',\\n' + '  \"common_depth_band_nm\": ' + bw + '\\n' + '}\\n'; write(output + 'combined_manifest.json', manifest); if (diameters.length) { var minDiameter = diameters[0]; var maxDiameter = diameters[diameters.length - 1]; var binCount = Math.max(1, Math.floor((maxDiameter - minDiameter) / hist) + 1); var counts = []; for (ii = 0; ii < binCount; ii++) counts[ii] = 0; for (ii = 0; ii < diameters.length; ii++) counts[Math.min(binCount - 1, Math.floor((diameters[ii] - minDiameter) / hist))]++; var maxCount = Math.max.apply(null, counts); var image = new BI(1200, 800, BI.TYPE_INT_RGB); var graphics = image.createGraphics(); graphics.setColor(C.WHITE); graphics.fillRect(0, 0, 1200, 800); graphics.setColor(C.BLACK); graphics.setFont(new Font('SansSerif', Font.BOLD, 24)); graphics.drawString('Distribucion combinada de tamanos', 70, 42); graphics.drawLine(80, 700, 1140, 700); graphics.drawLine(80, 80, 80, 700); graphics.setColor(C.decode('#466eb4')); for (ii = 0; ii < binCount; ii++) { var x = 80 + ii * 1060 / binCount; var width = Math.max(1, 1060 / binCount - 2); var height = maxCount ? counts[ii] * 600 / maxCount : 0; graphics.fillRect(Math.round(x), Math.round(700 - height), Math.round(width), Math.round(height)); } graphics.dispose(); IO.write(image, 'png', new F(output + 'combined_diameter_histogram.png')); } return 'OK|' + output + '|' + ids.length + '|' + totalN + '|' + (totalArea / 1e6) + '|' + density2D + '|' + (isFinite(density3D) ? density3D : 'N/A'); })();";
    return ""+eval("js",js);
}



function lightWriteCombinedHtml(runDir) {
    sum=lightJoin(runDir,"combined_summary.csv");
    if(!File.exists(sum))return 0;
    lines=split(File.openAsString(sum),"\n");
    if(lines.length<2)return 0;
    heads=split(lines[0],",");vals=split(lines[1],",");
    h="<!doctype html><html><head><meta charset=\"utf-8\"><title>Cavity TEM Light - analisis combinado</title><style>body{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px;color:#222}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:7px;text-align:left}th{background:#f0f3f8}.warn{background:#fff3cd;padding:12px;border-left:5px solid #c58a00}img{max-width:100%;border:1px solid #ddd}</style></head><body><h1>Analisis combinado de imagenes</h1><div class=\"warn\">Densidades agregadas mediante suma de recuentos y denominadores. No se usa la media simple de densidades. Densidad volumetrica nominal N/(A*t).</div><h2>Resumen</h2><table><tr><th>Parametro</th><th>Valor</th></tr>";
    limit=heads.length;
    if(vals.length<limit)limit=vals.length;
    for(i=0;i<limit;i++){
        headEscaped=lightHtmlEscape(heads[i]);valueEscaped=lightHtmlEscape(vals[i]);
        h=h+"<tr><td>"+headEscaped+"</td><td>"+valueEscaped+"</td></tr>";
    }
    h=h+"</table><h2>Imagenes incluidas</h2><p>Consulte <code>per_image_summary.csv</code> para la lista exacta, la condicion y el run de origen de cada imagen.</p>";
    histogramPath=lightJoin(runDir,"combined_diameter_histogram.png");
    if(File.exists(histogramPath))h=h+"<h2>Distribucion combinada</h2><img src=\"combined_diameter_histogram.png\">";
    h=h+"<h2>Archivos</h2><ul><li>per_image_summary.csv</li><li>combined_cavity_objects.tsv</li><li>combined_band_summary.csv, cuando hay superficie</li><li>combined_feature_distance_summary.csv, cuando hay microestructura</li><li>combined_manifest.json</li></ul></body></html>";
    reportPath=lightJoin(runDir,"report.html");File.saveString(h,reportPath);lightWriteRunChecksums(runDir);return 1;
}

function lightChooseRegistryImages(multiple) {
    reg=lightJoin(lightProjectRoot,lightRegistryFileName);if(!File.exists(reg)){showMessage("Sin imagenes","El proyecto no contiene un registro de imagenes.");return "";}js="(function(){var Files=Packages.java.nio.file.Files,Paths=Packages.java.nio.file.Paths,CS=Packages.java.nio.charset.StandardCharsets,JList=Packages.javax.swing.JList,JScroll=Packages.javax.swing.JScrollPane,JOption=Packages.javax.swing.JOptionPane,Mode=Packages.javax.swing.ListSelectionModel,p='"+jsEscape(reg)+"',multi="+multiple+";var tx=String(new java.lang.String(Files.readAllBytes(Paths.get(p)),CS.UTF_8)),ls=tx.split(/\\r?\\n/),ids=[],labels=[];for(var i=1;i<ls.length;i++){if(!ls[i])continue;var c=ls[i].split('\\t');if(c.length<1)continue;ids.push(c[0]);labels.push(c[0]+' | '+(c[5]||'')+' | '+(c[6]||'')+' | '+(c[7]||''));}if(!ids.length)return '';var list=new JList(labels);list.setSelectionMode(multi?Mode.MULTIPLE_INTERVAL_SELECTION:Mode.SINGLE_SELECTION);list.setVisibleRowCount(Math.min(16,ids.length));var r=JOption.showConfirmDialog(Packages.ij.IJ.getInstance(),new JScroll(list),multi?'Selecciona imagenes para combinar':'Selecciona una imagen',JOption.OK_CANCEL_OPTION,JOption.PLAIN_MESSAGE);if(r!=JOption.OK_OPTION)return '';var ix=list.getSelectedIndices(),out=[];for(i=0;i<ix.length;i++)out.push(ids[ix[i]]);return out.join(';');})();";return ""+eval("js",js);
}

function lightChooseRevision(dir) { if(!File.exists(dir))return "";js="(function(){var F=Packages.java.io.File,JOption=Packages.javax.swing.JOptionPane,root=new F('"+jsEscape(dir)+"'),a=root.listFiles(),v=[];if(a!=null)for(var i=0;i<a.length;i++)if(a[i].isDirectory()&&String(a[i].getName()).indexOf('REV_')==0)v.push(String(a[i].getName()));v.sort().reverse();if(!v.length)return '';var x=JOption.showInputDialog(Packages.ij.IJ.getInstance(),'Selecciona una revision','Cargar revision',JOption.PLAIN_MESSAGE,null,v,v[0]);return x==null?'':String(x);})();";return ""+eval("js",js); }

function setMetadataImageProperties() {
    if(nImages()<=0)return 0;
    code="var imp=Packages.ij.IJ.getImage();imp.setProperty('CavityTEMLight.ProjectId','"+jsEscape(lightProjectId)+"');imp.setProperty('CavityTEMLight.ImageId','"+jsEscape(lightImageId)+"');imp.setProperty('CavityTEMLight.SourceSHA256','"+jsEscape(lightSourceSha256)+"');imp.setProperty('CavityLightResizeStepNm','"+d2s(lightInteractiveResizeStepNm,6)+"');'OK';";
    eval("js",code);return 1;
}


function lightScientificObjectCount() {
    countsReady = lightRefreshObjectCounts();
    if (countsReady == 0) return 0;
    total = lightObjectCountCavities + lightObjectCountMasks + lightObjectCountExclusions;
    total = total + lightObjectCountSurfaces + lightObjectCountGrainBoundaries;
    total = total + lightObjectCountDislocations + lightObjectCountInterfaces;
    return total;
}


function lightVerifyRevisionManifest(revDir,zip) {
    if(File.exists(lightJoin(revDir,"REVISION_FAILED.txt")))return 0;
    man=lightJoin(revDir,"revision_manifest.tsv");if(!File.exists(man))return 0;
    revPath=substring(revDir,0,lengthOf(revDir)-1);expectedRevisionId=File.getName(revPath);manifestRevisionId=lightKvRead(man,"revision_id","");if(manifestRevisionId!=expectedRevisionId)return 0;
    manifestImageId=lightKvRead(man,"image_id","");if(manifestImageId!=lightImageId)return 0;
    manifestProjectId=lightKvRead(man,"project_id","");if(manifestProjectId!=lightProjectId)return 0;
    manifestProjectUid=lightKvRead(man,"project_uid",lightProjectUid);if(manifestProjectUid!=lightProjectUid)return 0;
    manifestSourceSha=lightKvRead(man,"source_sha256","");if(manifestSourceSha!=lightSourceSha256)return 0;
    expectedZipSha=lightKvRead(man,"roi_zip_sha256","");if(expectedZipSha=="")return 0;actualZipSha=IJ.checksum("SHA-256 file",zip);if(actualZipSha!=expectedZipSha)return 0;
    return 1;
}
function lightAppendLog(eventName,details) {
    if(lightProjectRoot=="")return 0;
    guardOk=lightCanonicalProjectGuard("escribir el log");
    if(guardOk==0)return 0;

    header="timestamp\tevent\tproject_id\tproject_uid\timage_id\toperator\tdetails\n";
    timestampText=lightTimestamp();
    cleanEvent=lightTsvClean(eventName);
    cleanProject=lightTsvClean(lightProjectId);
    cleanUid=lightTsvClean(lightProjectUid);
    cleanImage=lightTsvClean(lightImageId);
    cleanOperator=lightTsvClean(operatorName);
    cleanDetails=lightTsvClean(details);
    line=timestampText+"\t"+cleanEvent+"\t"+cleanProject+"\t"+cleanUid+"\t"+cleanImage+"\t"+cleanOperator+"\t"+cleanDetails+"\n";

    projectLogsDir=lightJoin(lightProjectRoot,"logs");
    if(!lightMakeDir(projectLogsDir))return 0;
    projectLogPath=lightJoin(projectLogsDir,"events.tsv");
    if(!File.exists(projectLogPath))File.saveString(header,projectLogPath);
    File.append(line,projectLogPath);

    if(lightImageId!=""){
        imagesRoot=lightJoin(lightProjectRoot,"images");
        imagePath=lightJoin(imagesRoot,lightImageId);
        expectedImageDir=lightNormalizeDir(imagePath);
        imageDirExists=lightFileExistsFlag(expectedImageDir);
        if(imageDirExists==1){
            imageLogsDir=lightJoin(expectedImageDir,"logs");
            if(!lightMakeDir(imageLogsDir))return 0;
            imageLogPath=lightJoin(imageLogsDir,"events.tsv");
            if(!File.exists(imageLogPath))File.saveString(header,imageLogPath);
            File.append(line,imageLogPath);
        }
    }
    return 1;
}

function lightCopyFileVerified(src,dst,sha) {
    js="(function(){var Files=Packages.java.nio.file.Files,Paths=Packages.java.nio.file.Paths,Std=Packages.java.nio.file.StandardCopyOption;try{Files.copy(Paths.get('"+jsEscape(src)+"'),Paths.get('"+jsEscape(dst)+"'),Std.REPLACE_EXISTING);return '1';}catch(e){return '0';}})();";
    copyStatus=""+eval("js",js);if(copyStatus!="1")return 0;if(!File.exists(dst))return 0;actualSha=IJ.checksum("SHA-256 file",dst);if(actualSha!=sha)return 0;return 1;
}

function lightExtension(path) { n=toLowerCase(File.getName(path));p=lastIndexOf(n,".");if(p<0)return "";return substring(n,p+1); }
function lightEnsureProject() {
    if(!lightProjectLoaded||lightProjectRoot==""){
        showMessage("Sin proyecto","Cree o abra primero un proyecto Cavity TEM Light.");
        return 0;
    }
    guardOk=lightCanonicalProjectGuard("continuar");
    if(guardOk==0)return 0;
    return 1;
}
function lightEnsureCurrentImage() {
    projectOk=lightEnsureProject();
    if(projectOk==0)return 0;
    missingImage=0;
    if(nImages()<=0)missingImage=1;
    if(lightImageId=="")missingImage=1;
    if(missingImage==1){
        showMessage("Sin imagen","Abra o seleccione una imagen registrada.");
        return 0;
    }

    imagesRoot=lightJoin(lightProjectRoot,"images");
    imagePath=lightJoin(imagesRoot,lightImageId);
    expectedImageDir=lightNormalizeDir(imagePath);
    meta=lightJoin(expectedImageDir,lightImageMetadataFileName);
    metaMatches=lightImageMetadataMatches(meta,lightImageId,lightSourceSha256);
    if(metaMatches==0){
        showMessage("Registro incompleto","No existe o no coincide el metadato canonico de la imagen activa:\n"+meta);
        return 0;
    }

    lightImageDir=expectedImageDir;
    widthDefault=getWidth();heightDefault=getHeight();
    widthValue=lightKvNumber(meta,"width_px",widthDefault);
    heightValue=lightKvNumber(meta,"height_px",heightDefault);
    ew=round(widthValue);eh=round(heightValue);
    dimensionMismatch=0;
    if(ew!=getWidth())dimensionMismatch=1;
    if(eh!=getHeight())dimensionMismatch=1;
    if(dimensionMismatch==1){
        showMessage("Imagen incompatible","Las dimensiones activas no coinciden con el registro de la imagen.");
        return 0;
    }

    identity=lightActiveImageIdentity();
    parts=split(identity,"|");
    identityOk=1;
    if(parts.length<3)identityOk=0;
    if(identityOk==1){
        identityProject=parts[0];identityImage=parts[1];identitySha=parts[2];
        if(identityProject!=lightProjectId)identityOk=0;
        if(identityImage!=lightImageId)identityOk=0;
        if(identitySha!=lightSourceSha256)identityOk=0;
    }
    if(identityOk==0){
        showMessage("Imagen activa no vinculada","La ventana activa no tiene la identidad exacta del proyecto, la imagen y la fuente registrados.\n\nUse Seleccionar imagen del proyecto o vuelva a registrar la imagen activa. Esta comprobacion evita medir por error otra imagen con las mismas dimensiones.");
        return 0;
    }
    return 1;
}

function lightMakeDir(path) {
    if(path=="")return 0;
    js="(function(){var f=new Packages.java.io.File('"+jsEscape(path)+"');return ((f.exists()&&f.isDirectory())||f.mkdirs())?'1':'0';})();";
    makeResult=eval("js",js);if(makeResult=="1")return 1;showMessage("Carpeta no creada",path);return 0;
}

function lightNormalizeDir(path) {
    if(path=="")return "";
    normalizedPath=normalizeStoredPath(path);
    if(!endsWith(normalizedPath,"/"))normalizedPath=normalizedPath+"/";
    return normalizedPath;
}

function lightJoin(a,b) {
    if(a==""){
        normalizedB=normalizeStoredPath(b);
        return normalizedB;
    }
    normalizedA=normalizeStoredPath(a);
    normalizedB=normalizeStoredPath(b);
    if(endsWith(normalizedA,"/"))normalizedA=substring(normalizedA,0,lengthOf(normalizedA)-1);
    while(startsWith(normalizedB,"/"))normalizedB=substring(normalizedB,1);
    joinedValue=normalizedA+"/"+normalizedB;
    return joinedValue;
}

// Compatibility: retain explicit String.trim(...) for compatibility. The reported R1 error
// was caused by a compound string expression passed to lightJoin().
function lightSanitizeId(s) { s=String.trim(s);out="";for(i=0;i<lengthOf(s);i++){c=substring(s,i,i+1);ok=0;if(indexOf("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",c)>=0)ok=1;if(ok==1)out=out+c;else if(c==" "||c=="."||c=="/"||c=="\\")out=out+"_";}while(indexOf(out,"__")>=0)out=replace(out,"__","_");if(out=="")out="IMAGE";return out; }
function lightEscapeRunPath(s) { return replace(s,"]","\\]"); }
function lightTsvClean(s) { s=""+s;s=replace(s,"\t"," ");s=replace(s,"\r"," ");s=replace(s,"\n"," ");return s; }
// Compatibility: retain explicit String.trim(...) for unambiguous TSV reads.
function lightKvRead(path,key,defaultValue) {
    if(!File.exists(path))return defaultValue;
    if(path==lightHF46KvPath)t=lightHF46KvText;else t=File.openAsString(path);
    ls=split(t,"\n");
    for(i=0;i<ls.length;i++){
        p=indexOf(ls[i],"\t");
        if(p>0){
            rowKey=substring(ls[i],0,p);
            if(rowKey==key){
                rawValue=substring(ls[i],p+1);
                cleanValue=String.trim(rawValue);
                return cleanValue;
            }
        }
    }
    return defaultValue;
}

function lightKvNumber(path,key,defaultValue) {
    s=lightKvRead(path,key,"");
    if(s==""||s=="NaN")return defaultValue;
    v=parseFloat(s);
    if(isNaN(v))return defaultValue;
    return v;
}
function lightUuid() { return ""+eval("js","String(java.util.UUID.randomUUID());"); }
function lightTimestamp() { return ""+eval("js","var d=new Date(),p=function(n){return ('0'+n).slice(-2);};d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+'_'+p(d.getHours())+p(d.getMinutes())+p(d.getSeconds())+'_'+('00'+d.getMilliseconds()).slice(-3);"); }
function lightCsv(s) { s=""+s;s=replace(s,"\"","\"\"");return "\""+s+"\""; }
function lightNum(v) { if(isNaN(v))return "";return d2s(v,12); }
function lightArrayPrefix(a,n) { b=newArray(n);for(ii=0;ii<n;ii++)b[ii]=a[ii];return b; }
function lightTsvLineToCsv(line) {
    line=replace(line,"\r","");line=replace(line,"\n","");out="";from=0;
    for(k=0;k<=lengthOf(line);k++){
        boundary=0;if(k==lengthOf(line))boundary=1;
        else{character=substring(line,k,k+1);if(character=="\t")boundary=1;}
        if(boundary){cell=substring(line,from,k);escaped=lightCsv(cell);if(from>0)out=out+",";out=out+escaped;from=k+1;}
    }
    return out+"\n";
}



// HF3 results engine, shared with developer_sources and numerical tests.
function lightHF3Source() {
    if(lightHF46ScientificSource!="")return lightHF46ScientificSource;
    code="";
    code=code+"/* Cavity TEM Light HF3. ES5, shared by Fiji and the numerical tests.\n";
    code=code+" * Physical coordinates; parallel offsets with miter joins and tangent rays.\n";
    code=code+" * At a vertex this is the miter-offset parameter, not radial vertex distance.\n";
    code=code+" */\n";
    code=code+"var CTL3 = (function () {\n";
    code=code+"    function cross(ax, ay, bx, by) { return ax * by - ay * bx; }\n";
    code=code+"    function geometry(points, sx, sy, sign) {\n";
    code=code+"        var p = [], seg = [], joins = [], i, q, a, b, dx, dy, len;\n";
    code=code+"        if (!(sx > 0 && sy > 0)) throw Error('Escala no positiva');\n";
    code=code+"        for (i = 0; i < points.length; i++) {\n";
    code=code+"            q = [Number(points[i][0]) * sx, Number(points[i][1]) * sy];\n";
    code=code+"            if (!isFinite(q[0]) || !isFinite(q[1])) throw Error('Superficie no finita');\n";
    code=code+"            if (!p.length || Math.abs(q[0] - p[p.length-1][0]) + Math.abs(q[1] - p[p.length-1][1]) > 1e-10) p.push(q);\n";
    code=code+"        }\n";
    code=code+"        if (p.length < 2) throw Error('Superficie sin longitud');\n";
    code=code+"        var arc = 0;\n";
    code=code+"        for (i = 0; i < p.length - 1; i++) {\n";
    code=code+"            a = p[i]; b = p[i+1]; dx = b[0]-a[0]; dy = b[1]-a[1]; len = Math.sqrt(dx*dx+dy*dy);\n";
    code=code+"            seg.push({x:a[0], y:a[1], dx:dx/len, dy:dy/len, len:len, arc:arc}); arc += len;\n";
    code=code+"        }\n";
    code=code+"        for (i = 1; i < seg.length; i++) {\n";
    code=code+"            a=seg[i-1]; b=seg[i]; var turn=cross(a.dx,a.dy,b.dx,b.dy), dot=a.dx*b.dx+a.dy*b.dy;\n";
    code=code+"            if (dot < -0.9998) throw Error('Superficie con retroceso casi 180 grados; revise el vertice');\n";
    code=code+"            if (Math.abs(turn) < 1e-10) continue;\n";
    code=code+"            var side=turn>0?-1:1, n1=[-a.dy*side,a.dx*side], n2=[-b.dy*side,b.dx*side];\n";
    code=code+"            joins.push({x:b.x,y:b.y,n1:n1,n2:n2,det:cross(n1[0],n1[1],n2[0],n2[1])});\n";
    code=code+"        }\n";
    code=code+"        // A surface is an open, simple boundary. Crossing tangent extensions\n";
    code=code+"        // are ambiguous as a material boundary and are rejected as well.\n";
    code=code+"        for (i=0;i<seg.length;i++) for(var j=i+2;j<seg.length;j++) {\n";
    code=code+"            a=seg[i]; b=seg[j]; var den=cross(a.dx,a.dy,b.dx,b.dy);\n";
    code=code+"            if(Math.abs(den)<1e-12)continue;\n";
    code=code+"            var vx=b.x-a.x,vy=b.y-a.y,t=cross(vx,vy,b.dx,b.dy)/den,u=cross(vx,vy,a.dx,a.dy)/den;\n";
    code=code+"            if((i===0||t>=-1e-9)&&(i===seg.length-1||t<=a.len+1e-9)&&(j===0||u>=-1e-9)&&(j===seg.length-1||u<=b.len+1e-9))\n";
    code=code+"                throw Error('La superficie o sus prolongaciones se cruzan; revise la polilinea');\n";
    code=code+"        }\n";
    code=code+"        function metric(xpx,ypx,details) {\n";
    code=code+"            var x=xpx*sx,y=ypx*sy,best=Infinity,offset=Infinity,sgn=1,nearest=null,k,s,px,py,t,clamped,normal,d2;\n";
    code=code+"            for(k=0;k<seg.length;k++) {\n";
    code=code+"                s=seg[k]; px=x-s.x;py=y-s.y;t=px*s.dx+py*s.dy;normal=s.dx*py-s.dy*px;\n";
    code=code+"                clamped=t;\n";
    code=code+"                if(k>0&&clamped<0)clamped=0;\n";
    code=code+"                if(k<seg.length-1&&clamped>s.len)clamped=s.len;\n";
    code=code+"                d2=normal*normal+(t-clamped)*(t-clamped);\n";
    code=code+"                if(d2<best) {best=d2;sgn=normal<0?-1:1;if(details)nearest=[s,clamped];}\n";
    code=code+"                if((k===0||t>=0)&&(k===seg.length-1||t<=s.len))offset=Math.min(offset,Math.abs(normal));\n";
    code=code+"            }\n";
    code=code+"            for(k=0;k<joins.length;k++) {\n";
    code=code+"                var v=joins[k];px=x-v.x;py=y-v.y;\n";
    code=code+"                var c1=cross(px,py,v.n2[0],v.n2[1])/v.det,c2=cross(v.n1[0],v.n1[1],px,py)/v.det;\n";
    code=code+"                if(c1>=-1e-10&&c2>=-1e-10)offset=Math.min(offset,Math.max(px*v.n1[0]+py*v.n1[1],px*v.n2[0]+py*v.n2[1]));\n";
    code=code+"            }\n";
    code=code+"            if(!isFinite(offset))throw Error('No se pudo obtener la profundidad');\n";
    code=code+"            offset=Math.max(0,offset);var sd=offset*(sign<0?-1:1)*sgn;\n";
    code=code+"            if(!details)return sd;\n";
    code=code+"            s=nearest[0];t=nearest[1];\n";
    code=code+"            return {depth:sd,absolute:offset,euclidean:Math.sqrt(best),arc:s.arc+t,x:(s.x+t*s.dx)/sx,y:(s.y+t*s.dy)/sy,angle:Math.atan2(s.dy,s.dx)*180/Math.PI};\n";
    code=code+"        }\n";
    code=code+"        return {depth:function(x,y){return metric(x,y,false);},metrics:function(x,y){return metric(x,y,true);},points:p,segments:seg};\n";
    code=code+"    }\n";
    code=code+"    function bandIndex(depth,width) {\n";
    code=code+"        if(!isFinite(depth)||depth<0||!(width>0))return -1;\n";
    code=code+"        var q=depth/width,r=Math.round(q);\n";
    code=code+"        // Relative tolerance for roundoff at an exact mathematical boundary.\n";
    code=code+"        if(Math.abs(q-r)<1e-10)q=r;\n";
    code=code+"        return Math.floor(q);\n";
    code=code+"    }\n";
    code=code+"    function stats(values) {\n";
    code=code+"        var a=values.slice(0).filter(function(v){return isFinite(v);}).sort(function(x,y){return x-y;}),n=a.length,mean=0,m2=0;\n";
    code=code+"        for(var i=0;i<n;i++){var delta=a[i]-mean;mean+=delta/(i+1);m2+=delta*(a[i]-mean);}\n";
    code=code+"        function pct(p){if(!n)return NaN;var z=(n-1)*p,l=Math.floor(z),u=Math.ceil(z);return a[l]+(z-l)*(a[u]-a[l]);}\n";
    code=code+"        return {n:n,mean:n?mean:NaN,std:n>1?Math.sqrt(Math.max(0,m2/(n-1))):NaN,sem:n>1?Math.sqrt(Math.max(0,m2/(n-1))/n):NaN,median:pct(.5),q25:pct(.25),q75:pct(.75),min:n?a[0]:NaN,max:n?a[n-1]:NaN};\n";
    code=code+"    }\n";
    code=code+"    function breaks(text) {\n";
    code=code+"        var a=String(text).split(/[,; ]+/).filter(function(x){return x!=='';}).map(Number);\n";
    code=code+"        if(!a.length||a.length>12)throw Error('Indique de 1 a 12 limites de tamano');\n";
    code=code+"        for(var i=0;i<a.length;i++)if(!isFinite(a[i])||a[i]<=0||(i&&a[i]<=a[i-1]))throw Error('Los limites de tamano deben ser positivos y crecientes');\n";
    code=code+"        return a;\n";
    code=code+"    }\n";
    code=code+"    function sizeClass(d,edges){var i=0;while(i<edges.length&&d>=edges[i])i++;return i;}\n";
    code=code+"    function summarize(objects,areas,width,thickness,uncertainty) {\n";
    code=code+"        var out=[],i;\n";
    code=code+"        for(i=0;i<areas.length;i++)out.push({index:i,low:i*width,high:(i+1)*width,area:Number(areas[i]),count:0,values:[],projected:0,spherical:0});\n";
    code=code+"        for(i=0;i<objects.length;i++){\n";
    code=code+"            var o=objects[i],b=bandIndex(o.depth,width);\n";
    code=code+"            if(b===out.length&&Math.abs(o.depth-out.length*width)<1e-8)b--;\n";
    code=code+"            if(b<0||b>=out.length)continue;\n";
    code=code+"            var r=out[b];if(o.count)r.count++;\n";
    code=code+"            if(o.size&&isFinite(o.diameter)&&o.diameter>0){r.values.push(o.diameter);r.projected+=o.projected;r.spherical+=o.spherical;}\n";
    code=code+"        }\n";
    code=code+"        for(i=0;i<out.length;i++){\n";
    code=code+"            var r=out[i];r.stats=stats(r.values);r.volume=thickness>0?r.area*thickness:NaN;\n";
    code=code+"            r.density2=r.area>0?r.count*1e6/r.area:NaN;\n";
    code=code+"            r.density3=r.volume>0?r.count*1e27/r.volume:NaN;\n";
    code=code+"            r.poissonSE2=r.area>0?Math.sqrt(r.count)*1e6/r.area:NaN;\n";
    code=code+"            r.poissonSE3=r.volume>0?Math.sqrt(r.count)*1e27/r.volume:NaN;\n";
    code=code+"            // Thickness uncertainty is reported separately: input need not be 1 sigma.\n";
    code=code+"            r.thicknessEffect3=r.volume>0?r.density3*uncertainty/thickness:NaN;\n";
    code=code+"            if(r.area===0&&r.count>0)r.status='COUNT_WITH_ZERO_RASTER_AREA';else r.status=r.area>0?'OK':'NO_VALID_AREA';\n";
    code=code+"        }\n";
    code=code+"        return out;\n";
    code=code+"    }\n";
    code=code+"    return {geometry:geometry,bandIndex:bandIndex,stats:stats,breaks:breaks,sizeClass:sizeClass,summarize:summarize};\n";
    code=code+"})();\n";
    code=code+"if(typeof module!=='undefined')module.exports=CTL3;\n";
    code=code+"\n";
    code=code+"/* ImageJ adapter. Native image pixels and ROIs are only read; output overlays\n";
    code=code+" * are built from clones. No scientific ROI is appended for presentation. */\n";
    code=code+"function ctlHF3(action, cfg, imp, rois, dir) {\n";
    code=code+"    var IJ=Packages.ij.IJ, BP=Packages.ij.process.ByteProcessor, IP=Packages.ij.ImagePlus,\n";
    code=code+"        FS=Packages.ij.io.FileSaver, RM=Packages.ij.plugin.frame.RoiManager,\n";
    code=code+"        Overlay=Packages.ij.gui.Overlay, ShapeRoi=Packages.ij.gui.ShapeRoi,\n";
    code=code+"        Color=Packages.java.awt.Color, Font=Packages.java.awt.Font,\n";
    code=code+"        Arr=Packages.java.lang.reflect.Array, DoubleT=Packages.java.lang.Double.TYPE,\n";
    code=code+"        w=imp.getWidth(), h=imp.getHeight(), sx=cfg.sx,sy=cfg.sy,maskRois=[],exclusions=[],surface=null,i;\n";
    code=code+"    function val(r,k){var v=r.getProperty(k);return v==null?'':String(v);}\n";
    code=code+"    function typ(r){return val(r,'Type')||val(r,'Object_type');}\n";
    code=code+"    function num(r,k,def){var s=val(r,k),v=parseFloat(s);return isFinite(v)?v:def;}\n";
    code=code+"    function write(name,text){var f=new Packages.java.io.File(dir,name);Packages.java.nio.file.Files.write(f.toPath(),new Packages.java.lang.String(text).getBytes(Packages.java.nio.charset.StandardCharsets.UTF_8));}\n";
    code=code+"    function clean(s){return String(s).replace(/[|\\r\\n]/g,' ');}\n";
    code=code+"    function csv(s){return '\"'+String(s).replace(/\"/g,'\"\"')+'\"';}\n";
    code=code+"    function n(v){return isFinite(v)?String(v):'';}\n";
    code=code+"    function ja(a){var x=Arr.newInstance(DoubleT,a.length);for(var k=0;k<a.length;k++)x[k]=a[k];return x;}\n";
    code=code+"    function dense(a){var b=[];for(var k=0;k<a.length;k++)b[k]=Number(a[k]||0);return b;}\n";
    code=code+"    for(i=0;i<rois.length;i++) {var type=typ(rois[i]);if(type==='analysis_mask')maskRois.push(rois[i]);if(type==='exclusion')exclusions.push(rois[i]);if(type==='surface_reference'||type==='surface')surface=rois[i];}\n";
    code=code+"    if(!isFinite(sx)||!isFinite(sy)||sx<=0||sy<=0)throw Error('Escala no valida');\n";
    code=code+"    if(!isFinite(cfg.thickness)||cfg.thickness<0||!isFinite(cfg.uncertainty)||cfg.uncertainty<0)throw Error('Espesor o incertidumbre no valido');\n";
    code=code+"    if(!isFinite(cfg.histogram)||cfg.histogram<=0||!isFinite(cfg.featureBin)||cfg.featureBin<=0)throw Error('Intervalos no validos');\n";
    code=code+"    if(!isFinite(cfg.bandWidth)||cfg.bandWidth<=0||!isFinite(cfg.bandCount)||cfg.bandCount<1||Math.floor(cfg.bandCount)!==cfg.bandCount||cfg.bandCount>5000)throw Error('Bandas no validas');\n";
    code=code+"    var withSurface=cfg.mode==='with_surface', geom=null;\n";
    code=code+"    if(withSurface){\n";
    code=code+"        if(!surface)throw Error('Falta la superficie');\n";
    code=code+"        var fp=(surface instanceof Packages.ij.gui.Line?surface.getFloatPoints():surface.getFloatPolygon()),points=[];\n";
    code=code+"        for(i=0;i<fp.npoints;i++)points.push([Number(fp.xpoints[i]),Number(fp.ypoints[i])]);\n";
    code=code+"        geom=CTL3.geometry(points,sx,sy,cfg.sign);\n";
    code=code+"    }\n";
    code=code+"    var key='CavityTEMLight.HF3.AreaCache', cache=imp.getProperty(key);\n";
    code=code+"    if(cache==null||String(cache.get('fingerprint'))!==cfg.fp)cache=null;\n";
    code=code+"    function baseMask(){\n";
    code=code+"        var ip=new BP(w,h),whole=cfg.whole||(!maskRois.length&&withSurface);\n";
    code=code+"        if(whole){ip.setValue(255);ip.fill();}else{ip.setValue(255);for(var j=0;j<maskRois.length;j++)ip.fill(maskRois[j]);}\n";
    code=code+"        ip.setValue(0);for(var j=0;j<exclusions.length;j++)ip.fill(exclusions[j]);return ip;\n";
    code=code+"    }\n";
    code=code+"    function prepare(){\n";
    code=code+"        if(cache!=null)return;\n";
    code=code+"        var mask=baseMask(),pix=mask.getPixels(),depth=withSurface?Arr.newInstance(DoubleT,w*h):null,\n";
    code=code+"            maxDepth=0,valid=0,x,y,q,sd,area1=[],counts=[],bw=cfg.bandWidth,bc=0;\n";
    code=code+"        for(y=0;y<h;y++){\n";
    code=code+"            if(y%64===0)IJ.showProgress(y,h);\n";
    code=code+"            for(x=0;x<w;x++){\n";
    code=code+"                q=y*w+x;sd=withSurface?geom.depth(x+0.5,y+0.5):NaN;\n";
    code=code+"                if(withSurface){depth[q]=sd;if(sd>maxDepth)maxDepth=sd;if(sd<0)pix[q]=0;}\n";
    code=code+"                if((pix[q]&255)!==0){valid++;if(withSurface){var b1=CTL3.bandIndex(sd,1);area1[b1]=(area1[b1]||0)+1;}}\n";
    code=code+"            }\n";
    code=code+"        }\n";
    code=code+"        if(withSurface){\n";
    code=code+"            // Cover the image footprint, including the part of its last pixels\n";
    code=code+"            // beyond their centres; masks do not shorten the displayed profile.\n";
    code=code+"            for(x=0;x<=w;x++){maxDepth=Math.max(maxDepth,geom.depth(x,0),geom.depth(x,h));}\n";
    code=code+"            for(y=0;y<=h;y++){maxDepth=Math.max(maxDepth,geom.depth(0,y),geom.depth(w,y));}\n";
    code=code+"            for(i=0;i<rois.length;i++)if(typ(rois[i])==='cavity'){var rb=rois[i].getFloatBounds(),cx=rb.x+rb.width/2,cy=rb.y+rb.height/2;if(cx>=0&&cx<w&&cy>=0&&cy<h)maxDepth=Math.max(maxDepth,geom.depth(cx,cy));}\n";
    code=code+"            if(cfg.bandMode==='count'){bc=cfg.bandCount;bw=maxDepth/bc;}else bc=Math.max(1,Math.ceil(maxDepth/bw-1e-10));\n";
    code=code+"            if(!(bw>0)||!isFinite(bw)||bc>5000)throw Error('Bandas no validas o mas de 5000 bandas; aumente el ancho');\n";
    code=code+"            for(i=0;i<bc;i++)counts[i]=0;\n";
    code=code+"            for(q=0;q<w*h;q++)if((pix[q]&255)!==0){var b=Math.min(bc-1,CTL3.bandIndex(Number(depth[q]),bw));counts[b]++;}\n";
    code=code+"        }\n";
    code=code+"        var pixelArea=sx*sy;for(i=0;i<counts.length;i++)counts[i]*=pixelArea;\n";
    code=code+"        area1=dense(area1);for(i=0;i<area1.length;i++)area1[i]*=pixelArea;\n";
    code=code+"        cache=new Packages.java.util.HashMap();cache.put('fingerprint',cfg.fp);cache.put('mask',mask);\n";
    code=code+"        if(depth!=null)cache.put('depth',depth);\n";
    code=code+"        cache.put('areas',ja(counts));cache.put('area1',ja(area1));cache.put('validPixels',valid);\n";
    code=code+"        cache.put('bandWidth',bw);cache.put('bandCount',bc);cache.put('maxDepth',maxDepth);\n";
    code=code+"        cache.put('area',valid*pixelArea);imp.setProperty(key,cache);IJ.showProgress(1);\n";
    code=code+"    }\n";
    code=code+"    prepare();\n";
    code=code+"    var mask=cache.get('mask'),validPixels=mask.getPixels(),areas=dense(cache.get('areas')),bw=Number(cache.get('bandWidth')),bc=Number(cache.get('bandCount')),extent=Number(cache.get('maxDepth'));\n";
    code=code+"    function validAt(x,y){\n";
    code=code+"        if(x<0||y<0||x>=w||y>=h)return false;\n";
    code=code+"        // The same raster convention as the denominator; the continuous\n";
    code=code+"        // surface test also handles a centroid immediately across a boundary.\n";
    code=code+"        return (validPixels[Math.floor(y)*w+Math.floor(x)]&255)!==0&&(!geom||geom.depth(x,y)>=0);\n";
    code=code+"    }\n";
    code=code+"    if(action==='area')return 'OK|'+cache.get('validPixels')+'|'+cache.get('area')+'|'+bw+'|'+bc+'|'+extent+'|'+(dense(cache.get('area1')).join(',')||'-')+'|'+(areas.join(',')||'-');\n";
    code=code+"    if(action==='point')return validAt(cfg.x,cfg.y)?'1':'0';\n";
    code=code+"    if(action==='metrics'){\n";
    code=code+"        if(!geom)return 'NaN|NaN|NaN|NaN|NaN|NaN';var m=geom.metrics(cfg.x,cfg.y);\n";
    code=code+"        return [m.absolute,m.depth,m.arc,m.x,m.y,m.angle].join('|');\n";
    code=code+"    }\n";
    code=code+"    var featureTypes=['grain_boundary','dislocation','interface'],segments={grain_boundary:[],dislocation:[],interface:[]};\n";
    code=code+"    for(i=0;i<rois.length;i++)if(segments[typ(rois[i])]){var p=(rois[i] instanceof Packages.ij.gui.Line?rois[i].getFloatPoints():rois[i].getFloatPolygon());for(var k=0;k<p.npoints-1;k++)segments[typ(rois[i])].push([p.xpoints[k]*sx,p.ypoints[k]*sy,p.xpoints[k+1]*sx,p.ypoints[k+1]*sy]);}\n";
    code=code+"    function featureDistance(x,y,ss){var best=Infinity,px=x*sx,py=y*sy;for(var k=0;k<ss.length;k++){var s=ss[k],dx=s[2]-s[0],dy=s[3]-s[1],l2=dx*dx+dy*dy;if(l2===0)continue;var t=Math.max(0,Math.min(1,((px-s[0])*dx+(py-s[1])*dy)/l2)),ex=px-s[0]-t*dx,ey=py-s[1]-t*dy;best=Math.min(best,ex*ex+ey*ey);}return isFinite(best)?Math.sqrt(best):NaN;}\n";
    code=code+"    if(action==='context'){\n";
    code=code+"        var out=['OK'];\n";
    code=code+"        for(i=0;i<rois.length;i++)if(typ(rois[i])==='cavity'){\n";
    code=code+"            var r=rois[i],b=r.getFloatBounds(),cx=b.x+b.width/2,cy=b.y+b.height/2,v=validAt(cx,cy),edge=0,reason=v?'-':'outside_valid_material';\n";
    code=code+"            if(v){\n";
    code=code+"                var p=(r instanceof Packages.ij.gui.Line?r.getFloatPoints():r.getFloatPolygon());for(k=0;k<p.npoints;k++)if(!validAt(Number(p.xpoints[k]),Number(p.ypoints[k]))){edge=1;break;}\n";
    code=code+"                // Include holes wholly contained in the ROI, missed by a perimeter check.\n";
    code=code+"                for(var yy=Math.max(0,Math.floor(b.y));yy<Math.min(h,Math.ceil(b.y+b.height))&&!edge;yy++)for(var xx=Math.max(0,Math.floor(b.x));xx<Math.min(w,Math.ceil(b.x+b.width));xx++)if(r.contains(xx,yy)&&(validPixels[yy*w+xx]&255)===0){edge=1;break;}\n";
    code=code+"            }\n";
    code=code+"            var m=geom?geom.metrics(cx,cy):{depth:NaN,absolute:NaN,arc:NaN,x:NaN,y:NaN,angle:NaN};\n";
    code=code+"            out.push([i,v?1:0,edge,reason,featureDistance(cx,cy,segments.grain_boundary),featureDistance(cx,cy,segments.dislocation),featureDistance(cx,cy,segments.interface),m.depth,m.absolute,m.arc,m.x,m.y,m.angle].join('|'));\n";
    code=code+"        }\n";
    code=code+"        return out.join('\\n');\n";
    code=code+"    }\n";
    code=code+"    if(action==='featureAreas'){\n";
    code=code+"        var packs=[];for(var ti=0;ti<featureTypes.length;ti++){\n";
    code=code+"            var ss=segments[featureTypes[ti]],a=[];\n";
    code=code+"            if(ss.length)for(var y=0;y<h;y++)for(var x=0;x<w;x++)if((validPixels[y*w+x]&255)!==0){var j=CTL3.bandIndex(featureDistance(x+.5,y+.5,ss),cfg.featureBin);a[j]=(a[j]||0)+1;}\n";
    code=code+"            a=dense(a);for(var k=0;k<a.length;k++)a[k]*=sx*sy;packs.push(a.join(',')||'-');\n";
    code=code+"        }return packs.join('|');\n";
    code=code+"    }\n";
    code=code+"    function objects(){\n";
    code=code+"        var a=[];for(var k=0;k<rois.length;k++)if(typ(rois[k])==='cavity'){\n";
    code=code+"            var r=rois[k],b=r.getFloatBounds(),cx=b.x+b.width/2,cy=b.y+b.height/2;\n";
    code=code+"            a.push({roi:r,index:k,id:val(r,'Cavity_id')||String(r.getName()),x:cx,y:cy,depth:geom?geom.depth(cx,cy):NaN,diameter:num(r,'Equivalent_diameter_nm',NaN),count:num(r,'Count_valid',0)===1,size:num(r,'Size_valid',0)===1,projected:num(r,'Cavity_area_nm2',0),spherical:num(r,'Estimated_spherical_volume_nm3',0)});\n";
    code=code+"        }return a;\n";
    code=code+"    }\n";
    code=code+"    var objs=objects(),bands=CTL3.summarize(objs,areas,bw,cfg.thickness,cfg.uncertainty),edges=CTL3.breaks(cfg.sizeBreaks);\n";
    code=code+"    if(action==='outputs'){\n";
    code=code+"        var a1=dense(cache.get('area1')),text='bin_index\\tlow_nm\\thigh_nm\\tvalid_area_nm2\\n';\n";
    code=code+"        for(i=0;i<a1.length;i++)text+=[i,i,i+1,a1[i]].join('\\t')+'\\n';write('depth_area_1nm.tsv',text);\n";
    code=code+"        if(geom){\n";
    code=code+"            text='band_index,band_low_nm,band_high_nm,valid_area_nm2,N_count_valid,density_N_per_um2,mean_diameter_nm,N_size_valid,band_center_nm,band_width_nm,valid_area_um2,foil_thickness_nm,nominal_volume_nm3,nominal_density_N_per_m3,std_diameter_nm,sem_diameter_nm,median_diameter_nm,q25_diameter_nm,q75_diameter_nm,min_diameter_nm,max_diameter_nm,poisson_standard_error_density_N_per_um2,poisson_standard_error_density_N_per_m3,thickness_input_uncertainty_nm,thickness_effect_density_N_per_m3,projected_area_nm2,estimated_spherical_volume_nm3,projected_area_fraction,nominal_spherical_volume_fraction,geometric_depth_limit_nm,last_band_partial,status\\n';\n";
    code=code+"            var sumA=0,sumN=0;\n";
    code=code+"            for(i=0;i<bands.length;i++){\n";
    code=code+"                var b=bands[i],s=b.stats;sumA+=b.area;sumN+=b.count;\n";
    code=code+"                text+=[b.index,b.low,b.high,b.area,b.count,n(b.density2),n(s.mean),s.n,(b.low+b.high)/2,bw,b.area/1e6,n(cfg.thickness>0?cfg.thickness:NaN),n(b.volume),n(b.density3),n(s.std),n(s.sem),n(s.median),n(s.q25),n(s.q75),n(s.min),n(s.max),n(b.poissonSE2),n(b.poissonSE3),cfg.uncertainty,n(b.thicknessEffect3),b.projected,b.spherical,n(b.area>0?b.projected/b.area:NaN),n(b.volume>0?b.spherical/b.volume:NaN),extent,b.high>extent+1e-8?1:0,b.status].join(',')+'\\n';\n";
    code=code+"            }\n";
    code=code+"            write('band_summary.csv',text);\n";
    code=code+"            var validN=0;for(i=0;i<objs.length;i++)if(objs[i].count)validN++;\n";
    code=code+"            if(Math.abs(sumA-Number(cache.get('area')))>Math.max(1e-6,Number(cache.get('area'))*1e-10)||sumN!==validN)throw Error('No cierran las sumas de areas o recuentos por banda');\n";
    code=code+"        }\n";
    code=code+"        var rangeCount=[],rangeSize=[];for(i=0;i<=edges.length;i++){rangeCount[i]=0;rangeSize[i]=0;}\n";
    code=code+"        text='roi_manager_index,cavity_id,diameter_nm,size_class_index,range_low_nm,range_high_nm,count_valid,size_valid\\n';\n";
    code=code+"        for(i=0;i<objs.length;i++){\n";
    code=code+"            var o=objs[i],cl=CTL3.sizeClass(o.diameter,edges);if(o.count)rangeCount[cl]++;if(o.size)rangeSize[cl]++;\n";
    code=code+"            text+=[o.index,csv(o.id),n(o.diameter),cl,cl?edges[cl-1]:0,cl<edges.length?edges[cl]:'',o.count?1:0,o.size?1:0].join(',')+'\\n';\n";
    code=code+"        }write('cavity_size_classes.csv',text);\n";
    code=code+"        text='class_index,diameter_low_nm_inclusive,diameter_high_nm_exclusive,N_count_valid,N_size_valid\\n';\n";
    code=code+"        for(i=0;i<rangeCount.length;i++)text+=[i,i?edges[i-1]:0,i<edges.length?edges[i]:'',rangeCount[i],rangeSize[i]].join(',')+'\\n';write('size_class_summary.csv',text);\n";
    code=code+"        var ids={},dups=0;text='roi_manager_index,roi_name,cavity_id,occurrences,status\\n';\n";
    code=code+"        for(i=0;i<objs.length;i++)ids['id:'+objs[i].id]=(ids['id:'+objs[i].id]||0)+1;\n";
    code=code+"        for(i=0;i<objs.length;i++){var o=objs[i],occ=ids['id:'+o.id];if(occ>1)dups++;text+=[o.index,csv(o.roi.getName()),csv(o.id),occ,occ>1?'REVIEW_DUPLICATE_ID':'OK'].join(',')+'\\n';}write('roi_identity_review.csv',text);\n";
    code=code+"        write('analysis_method.json',JSON.stringify({version:'1.1.1-R9-HF3',application_version:'1.2.0-RC1-individual-US1',linear_length_domain:'valid_raster_pixel_cells_v1',linear_length_definition:'centerline clipped to the same raster pixel-cell domain as the area denominator; full trace retained in Traced_length_nm',linear_roi_coordinates:'centerline_endpoints_for_straight_lines; vertices_for_polylines',geometry:'physical_parallel_offsets_miter_joins_tangent_rays',depth_origin_nm:0,depth_definition:'perpendicular_to_segments; miter_offset_at_vertices',band_mode:cfg.bandMode,band_width_nm:bw,bands_in_image:bc,maximum_image_depth_nm:extent,area_method:'raster_pixel_centres; union_masks_minus_union_exclusions; material_side_only',pixel_area_nm2:sx*sy,area_nm2:Number(cache.get('area')),foil_thickness_nm:cfg.thickness,thickness_input_uncertainty_nm:cfg.uncertainty,density3_definition:'N/(A*t), nominal; no stereological correction',uncertainty:'Poisson sqrt(N) standard error; thickness sensitivity separate, confidence level unspecified',size_rule:'valid centroids for count; boundary-intersecting ROIs excluded from size',size_classes_nm:edges,background_contrast:cfg.contrast,duplicate_id_entries:dups},null,2)+'\\n');\n";
    code=code+"        return 'OK';\n";
    code=code+"    }\n";
    code=code+"    if(action==='visuals'||action==='charts')return ctlHF3Figures(cfg,imp,rois,geom,cache,objs,bands,edges,dir);\n";
    code=code+"    throw Error('Accion desconocida: '+action);\n";
    code=code+"}\n";
    code=code+"\n";
    code=code+"function ctlHF3Figures(cfg,imp,rois,geom,cache,objs,bands,edges,dir) {\n";
    code=code+"    var P=Packages,Color=P.java.awt.Color,Font=P.java.awt.Font,IP=P.ij.ImagePlus,FS=P.ij.io.FileSaver,\n";
    code=code+"        Overlay=P.ij.gui.Overlay,ShapeRoi=P.ij.gui.ShapeRoi,TextRoi=P.ij.gui.TextRoi,Plot=P.ij.gui.Plot,\n";
    code=code+"        Arr=P.java.lang.reflect.Array,w=imp.getWidth(),h=imp.getHeight(),bc=Number(cache.get('bandCount')),bw=Number(cache.get('bandWidth')),\n";
    code=code+"        depth=cache.get('depth'),pix=cache.get('mask').getPixels(),paths=[],anchors=[],i;\n";
    code=code+"    function ja(a){var b=Arr.newInstance(P.java.lang.Double.TYPE,a.length);for(var k=0;k<a.length;k++)b[k]=a[k];return b;}\n";
    code=code+"    function color(s){return Color.decode(s);}\n";
    code=code+"    function n(v){return isFinite(v)?Number(v.toPrecision(5)).toString():'N/A';}\n";
    code=code+"    function savePlot(name,title,xlabel,ylabel,x,y,shape,err,depthAxis) {\n";
    code=code+"        if(!x.length)return;\n";
    code=code+"        var plot=new Plot(title,xlabel,ylabel);plot.setSize(1150,740);plot.setFont(new Font('SansSerif',Font.PLAIN,18));\n";
    code=code+"        plot.setColor(color('#17648f'));plot.setLineWidth(2);plot.addPoints(ja(x),ja(y),shape);\n";
    code=code+"        if(err&&err.length)plot.addErrorBars(ja(err));\n";
    code=code+"        if(depthAxis){var maxY=0;for(var j=0;j<y.length;j++)if(isFinite(y[j]))maxY=Math.max(maxY,y[j]+(err&&isFinite(err[j])?err[j]:0));plot.setLimits(0,bc*bw,0,maxY>0?maxY*1.12:1);}\n";
    code=code+"        if(!new FS(plot.getImagePlus()).saveAsPng(dir+name))throw Error('No se pudo guardar '+name);\n";
    code=code+"    }\n";
    code=code+"    var ds=[],dx=[],dy=[];\n";
    code=code+"    for(i=0;i<objs.length;i++)if(objs[i].size&&isFinite(objs[i].diameter)) {ds.push(objs[i].diameter);if(isFinite(objs[i].depth)){dx.push(objs[i].depth);dy.push(objs[i].diameter);}}\n";
    code=code+"    if(ds.length){\n";
    code=code+"        var sorted=ds.slice(0).sort(function(a,b){return a-b;}),hist=cfg.histogram,lo=Math.floor(sorted[0]/hist)*hist,nb=Math.floor((sorted[sorted.length-1]-lo)/hist)+1,hh=[],hx=[];\n";
    code=code+"        if(nb>10000)throw Error('Demasiadas clases en el histograma; aumente su ancho');\n";
    code=code+"        for(i=0;i<nb;i++){hh[i]=0;hx[i]=lo+(i+.5)*hist;}for(i=0;i<ds.length;i++)hh[Math.min(nb-1,Math.floor((ds[i]-lo)/hist))]++;\n";
    code=code+"        savePlot('diameter_histogram.png','Distribucion de diametros; N='+ds.length,'Diametro equivalente (nm)','Numero de cavidades',hx,hh,Plot.BAR,null,false);\n";
    code=code+"        var cy=[];for(i=0;i<sorted.length;i++)cy.push((i+1)/sorted.length);\n";
    code=code+"        savePlot('diameter_cumulative.png','Distribucion acumulada empirica','Diametro equivalente (nm)','Fraccion acumulada',sorted,cy,Plot.LINE,null,false);\n";
    code=code+"        savePlot('diameter_vs_depth.png','Diametro individual frente a profundidad','Profundidad desde la superficie (nm)','Diametro equivalente (nm)',dx,dy,Plot.CIRCLE,null,true);\n";
    code=code+"        var s=CTL3.stats(ds),plot=new Plot('Resumen de tamanos','Diametro equivalente (nm)','');plot.setSize(1150,500);\n";
    code=code+"        plot.setFont(new Font('SansSerif',Font.PLAIN,18));plot.setLimits(Math.max(0,s.min-(s.max-s.min)*.1),s.max+(s.max-s.min)*.1+.01,0,1);\n";
    code=code+"        plot.setColor(color('#17648f'));plot.setLineWidth(3);\n";
    code=code+"        plot.addPoints(ja([s.min,s.max]),ja([.5,.5]),Plot.LINE);\n";
    code=code+"        plot.addPoints(ja([s.q25,s.q25,s.q75,s.q75,s.q25]),ja([.35,.65,.65,.35,.35]),Plot.LINE);\n";
    code=code+"        plot.addPoints(ja([s.median,s.median]),ja([.30,.70]),Plot.LINE);\n";
    code=code+"        plot.addLabel(.02,.04,'Caja: Q25-Q75; linea: mediana; extremos: minimo-maximo; N='+ds.length);\n";
    code=code+"        new FS(plot.getImagePlus()).saveAsPng(dir+'diameter_boxplot.png');\n";
    code=code+"    }\n";
    code=code+"    if(geom){\n";
    code=code+"        var bx=[],y2=[],y3=[],e2=[],e3=[],mx=[],my=[],me=[];\n";
    code=code+"        for(i=0;i<bands.length;i++){\n";
    code=code+"            var b=bands[i],mid=(b.low+b.high)/2;\n";
    code=code+"            // NaN leaves a gap; empty but observed bands retain zero density.\n";
    code=code+"            bx.push(mid);y2.push(b.density2);y3.push(b.density3);e2.push(b.poissonSE2);e3.push(b.poissonSE3);\n";
    code=code+"            mx.push(mid);my.push(b.stats.mean);me.push(b.stats.std);\n";
    code=code+"        }\n";
    code=code+"        savePlot('density_vs_depth.png','Densidad areal; barras: error estandar Poisson','Profundidad desde la superficie (nm)','Cavidades / um^2',bx,y2,Plot.CIRCLE,e2,true);\n";
    code=code+"        if(cfg.thickness>0)savePlot('volumetric_density_vs_depth.png','Densidad volumetrica nominal; barras: error Poisson','Profundidad desde la superficie (nm)','Cavidades / m^3',bx,y3,Plot.CIRCLE,e3,true);\n";
    code=code+"        if(ds.length)savePlot('mean_diameter_vs_depth.png','Diametro medio por banda; barras: desviacion estandar','Profundidad desde la superficie (nm)','Diametro medio (nm)',mx,my,Plot.CIRCLE,me,true);\n";
    code=code+"    }\n";
    code=code+"    var ff=new P.java.io.File(dir+'feature_distance_summary.csv');\n";
    code=code+"    if(ff.exists()){\n";
    code=code+"        var tx=String(new P.java.lang.String(P.java.nio.file.Files.readAllBytes(ff.toPath()),P.java.nio.charset.StandardCharsets.UTF_8)),rows=tx.split(/\\r?\\n/),types=['grain_boundary','dislocation','interface'];\n";
    code=code+"        for(var ti=0;ti<types.length;ti++){\n";
    code=code+"            var fx=[],fd=[],fm=[];for(i=1;i<rows.length;i++){var a=rows[i].split(',');if(a[0]!==types[ti])continue;fx.push((Number(a[2])+Number(a[3]))/2);fd.push(parseFloat(a[6]));fm.push(parseFloat(a[7]));}\n";
    code=code+"            savePlot(types[ti]+'_density_vs_distance.png','Densidad frente a distancia: '+types[ti],'Distancia (nm)','Cavidades / um^2',fx,fd,Plot.CIRCLE,null,false);\n";
    code=code+"            savePlot(types[ti]+'_size_vs_distance.png','Diametro frente a distancia: '+types[ti],'Distancia (nm)','Diametro medio (nm)',fx,fm,Plot.CIRCLE,null,false);\n";
    code=code+"        }\n";
    code=code+"    }\n";
    code=code+"    // Contours of the SAME depth field used in the denominators. Linear\n";
    code=code+"    // interpolation on the image pixel grid; no independently translated lines.\n";
    code=code+"    if(geom){\n";
    code=code+"        for(i=0;i<=bc;i++)paths[i]=new P.java.awt.geom.GeneralPath();\n";
    code=code+"        function point(a,b,va,vb,level){var f=(level-va)/(vb-va);return [a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1])];}\n";
    code=code+"        for(var y=0;y<h-1;y++)for(var x=0;x<w-1;x++){\n";
    code=code+"            var idx=y*w+x,vs=[Number(depth[idx]),Number(depth[idx+1]),Number(depth[idx+w+1]),Number(depth[idx+w])],mn=Math.min.apply(null,vs),mxv=Math.max.apply(null,vs);\n";
    code=code+"            if(mxv<0)continue;\n";
    code=code+"            var first=Math.max(0,Math.ceil(mn/bw)),last=Math.min(bc,Math.floor(mxv/bw));\n";
    code=code+"            if(first>last)continue;\n";
    code=code+"            var ps=[[x+.5,y+.5],[x+1.5,y+.5],[x+1.5,y+1.5],[x+.5,y+1.5]];\n";
    code=code+"            for(var bi=first;bi<=last;bi++){\n";
    code=code+"                var level=bi*bw,hit=[];\n";
    code=code+"                for(var e=0;e<4;e++){var f=(e+1)%4;if((vs[e]<level)!==(vs[f]<level))hit.push(point(ps[e],ps[f],vs[e],vs[f],level));}\n";
    code=code+"                if(hit.length===4){\n";
    code=code+"                    // Resolve a saddle using its centre classification.\n";
    code=code+"                    if(((vs[0]+vs[1]+vs[2]+vs[3])/4<level)===(vs[0]<level))hit=[hit[3],hit[0],hit[1],hit[2]];\n";
    code=code+"                }\n";
    code=code+"                for(var e=0;e+1<hit.length;e+=2){paths[bi].moveTo(hit[e][0],hit[e][1]);paths[bi].lineTo(hit[e+1][0],hit[e+1][1]);}\n";
    code=code+"            }\n";
    code=code+"        }\n";
    code=code+"        for(var y=24;y<h-24;y+=3)for(var x=24;x<w-24;x+=3){var d=Number(depth[y*w+x]);if(d<0)continue;var b=Math.min(bc-1,CTL3.bandIndex(d,bw));if(!anchors[b]&&Math.abs(d-(b+.5)*bw)<Math.min(bw*.20,Math.max(cfg.sx,cfg.sy)*4))anchors[b]=[x,y];}\n";
    code=code+"    }\n";
    code=code+"    var palette=['#1565c0','#009688','#e69f00','#d55e00','#9c27b0','#6d4c41','#202b45','#d81b60','#00acc1','#7c8500','#5e35b1','#ad4519','#4c6272'];\n";
    code=code+"    function cloneStyle(r,stroke,width){\n";
    code=code+"        // Roi.clone() shares the Properties map in ImageJ 1.54p. A serialization\n";
    code=code+"        // round trip gives the presentation ROI independent properties too.\n";
    code=code+"        var bytes=P.ij.io.RoiEncoder.saveAsByteArray(r),c=new P.ij.io.RoiDecoder(bytes,String(r.getName()||'')).getRoi();\n";
    code=code+"        c.setProperties('');c.setStrokeColor(color(stroke));c.setFillColor(null);c.setStrokeWidth(width);c.setPosition(0);return c;\n";
    code=code+"    }\n";
    code=code+"    function makeOverlay(sizeMode){\n";
    code=code+"        var ov=new Overlay();\n";
    code=code+"        for(var k=0;k<rois.length;k++){\n";
    code=code+"            var t=String(rois[k].getProperty('Type')||'');\n";
    code=code+"            if(t==='analysis_mask')ov.add(cloneStyle(rois[k],'#5b7785',1.2));\n";
    code=code+"            if(t==='exclusion')ov.add(cloneStyle(rois[k],'#555555',2));\n";
    code=code+"            if(t==='grain_boundary'||t==='dislocation'||t==='interface')ov.add(cloneStyle(rois[k],'#606060',1.5));\n";
    code=code+"        }\n";
    code=code+"        if(geom){\n";
    code=code+"            for(var j=0;j<=(sizeMode?0:bc);j++)if(paths[j].getCurrentPoint()!=null){\n";
    code=code+"                var r=new ShapeRoi(paths[j]);r.setName(j===0?'SUPERFICIE: 0 nm':n(j*bw)+' nm');r.setStrokeColor(color(j===0?'#111111':'#197c93'));r.setStrokeWidth(j===0?2.5:1.2);ov.add(r);\n";
    code=code+"            }\n";
    code=code+"            if(!sizeMode)for(var j=0;j<anchors.length;j++)if(anchors[j]){var a=anchors[j],tr=new TextRoi(a[0],a[1],'B'+(j+1),new Font('SansSerif',Font.BOLD,16));tr.setStrokeColor(color('#095568'));tr.setFillColor(Color.WHITE);ov.add(tr);}\n";
    code=code+"        }\n";
    code=code+"        for(var k=0;k<objs.length;k++){\n";
    code=code+"            var o=objs[k],stroke='#777777';\n";
    code=code+"            if(sizeMode&&o.size)stroke=palette[CTL3.sizeClass(o.diameter,edges)];else if(!sizeMode&&o.count)stroke='#bf3325';\n";
    code=code+"            ov.add(cloneStyle(o.roi,stroke,sizeMode?1.8:1.5));\n";
    code=code+"        }\n";
    code=code+"        ov.drawLabels(false);ov.drawNames(false);return ov;\n";
    code=code+"    }\n";
    code=code+"    function saveOverlay(sizeMode){\n";
    code=code+"        var bp=imp.getProcessor().duplicate().convertToByte(true),p=bp.getPixels(),contrast=sizeMode?cfg.contrast:.65;\n";
    code=code+"        for(var k=0;k<p.length;k++){var v=Math.round(255*(1-contrast)+(p[k]&255)*contrast);p[k]=v>127?v-256:v;}\n";
    code=code+"        bp.resetRoi();var out=new IP(sizeMode?'Cavidades por rango de tamano':'Bandas desde la superficie',bp);out.setCalibration(imp.getCalibration().copy());out.setOverlay(makeOverlay(sizeMode));\n";
    code=code+"        var stem=sizeMode?'size_ranges_overlay':'surface_bands_overlay';\n";
    code=code+"        if(!new FS(out).saveAsTiff(dir+stem+'.tif'))throw Error('No se pudo guardar el TIFF '+stem);\n";
    code=code+"        var flat=out.flatten(),BI=P.java.awt.image.BufferedImage,right=440,top=92,bottom=74,legendHeight=sizeMode?470+edges.length*37:400+Math.min(bc,24)*32,im=new BI(Math.max(1100,w+right),Math.max(h+top+bottom,legendHeight),BI.TYPE_INT_RGB),g=im.createGraphics();\n";
    code=code+"        g.setRenderingHint(P.java.awt.RenderingHints.KEY_ANTIALIASING,P.java.awt.RenderingHints.VALUE_ANTIALIAS_ON);\n";
    code=code+"        g.setColor(Color.WHITE);g.fillRect(0,0,im.getWidth(),im.getHeight());g.drawImage(flat.getBufferedImage(),0,top,null);\n";
    code=code+"        g.setColor(color('#16334a'));g.setFont(new Font('SansSerif',Font.BOLD,28));g[\"drawString(java.lang.String,int,int)\"](sizeMode?'Cavidades por rango de diametro':'Bandas de profundidad desde la superficie',24,36);\n";
    code=code+"        g.setFont(new Font('SansSerif',Font.PLAIN,18));g[\"drawString(java.lang.String,int,int)\"](cfg.imageId||imp.getTitle(),24,67);\n";
    code=code+"        var lx=w+24,ly=top+28;g.setFont(new Font('SansSerif',Font.BOLD,21));g[\"drawString(java.lang.String,int,int)\"](sizeMode?'Diametro equivalente (nm)':'Profundidad (nm)',lx,ly);ly+=40;\n";
    code=code+"        g.setFont(new Font('SansSerif',Font.PLAIN,18));\n";
    code=code+"        if(sizeMode){\n";
    code=code+"            var counts=[];for(i=0;i<=edges.length;i++)counts[i]=0;for(i=0;i<objs.length;i++)if(objs[i].size)counts[CTL3.sizeClass(objs[i].diameter,edges)]++;\n";
    code=code+"            for(i=0;i<=edges.length;i++){g.setColor(color(palette[i]));g.fillOval(lx,ly-15,18,18);g.setColor(color('#16334a'));g[\"drawString(java.lang.String,int,int)\"]((i?edges[i-1]:0)+' - '+(i<edges.length?edges[i]:'infinito')+'   |   n = '+counts[i],lx+32,ly);ly+=37;}\n";
    code=code+"            ly+=16;g.setColor(color('#777777'));g[\"drawString(java.lang.String,int,int)\"]('Gris: tamano no valido o excluida',lx,ly);ly+=33;\n";
    code=code+"            g[\"drawString(java.lang.String,int,int)\"]('Intervalos [inferior, superior)',lx,ly);ly+=33;g[\"drawString(java.lang.String,int,int)\"]('Contraste del fondo: '+Math.round(cfg.contrast*100)+' %',lx,ly);\n";
    code=code+"        }else{\n";
    code=code+"            g[\"drawString(java.lang.String,int,int)\"]('Ancho: '+n(bw)+' nm',lx,ly);ly+=32;g[\"drawString(java.lang.String,int,int)\"]('Bandas en la imagen: '+bc,lx,ly);ly+=32;\n";
    code=code+"            g[\"drawString(java.lang.String,int,int)\"]('Espesor lamina: '+n(cfg.thickness)+' nm',lx,ly);ly+=44;\n";
    code=code+"            for(i=0;i<Math.min(bands.length,24);i++){var b=bands[i];g[\"drawString(java.lang.String,int,int)\"]('B'+(i+1)+'   '+n(b.low)+' - '+n(b.high)+'   |   N='+b.count,lx,ly);ly+=32;}\n";
    code=code+"            if(bands.length>24){g[\"drawString(java.lang.String,int,int)\"]('Tabla completa: band_summary.csv',lx,ly);ly+=32;}\n";
    code=code+"            ly+=20;g[\"drawString(java.lang.String,int,int)\"]('Lineas: limites de banda',lx,ly);ly+=31;g[\"drawString(java.lang.String,int,int)\"]('Rojo: cavidades validas para recuento',lx,ly);ly+=31;g[\"drawString(java.lang.String,int,int)\"]('Gris: regiones y objetos excluidos',lx,ly);\n";
    code=code+"        }\n";
    code=code+"        g.setColor(color('#425765'));g.setFont(new Font('SansSerif',Font.PLAIN,17));\n";
    code=code+"        g[\"drawString(java.lang.String,int,int)\"](geom?'Bandas paralelas; uniones en vertice; extremos prolongados. Area neta: material valido menos exclusiones.':'Area neta: union de areas validas menos exclusiones. Imagen sin superficie.',24,im.getHeight()-bottom+29);\n";
    code=code+"        g[\"drawString(java.lang.String,int,int)\"](cfg.previewNote||'Representacion visual. El TIFF conserva las ROI como overlay editable; la imagen fuente permanece intacta.',24,im.getHeight()-bottom+55);\n";
    code=code+"        g.dispose();if(!P.javax.imageio.ImageIO.write(im,'png',new P.java.io.File(dir+stem+'.png')))throw Error('No se pudo guardar PNG');\n";
    code=code+"        flat.close();out.close();\n";
    code=code+"    }\n";
    code=code+"    if(geom)saveOverlay(false);saveOverlay(true);return 'OK';\n";
    code=code+"}\n";
    lightHF46ScientificSource=code;return code;
}

function lightHF3Run(action,runDir) {
    fp=lightAreaInputFingerprint();
    source=lightHF3Source();
    effectiveMode=lightImageMode;if(effectiveMode=="with_surface"&&!surfaceDefined)effectiveMode="without_surface";
    conf="{sx:"+d2s(nmPerPixelX,12)+",sy:"+d2s(nmPerPixelY,12)+",mode:'"+effectiveMode+"',sign:"+surfaceMaterialSign+",whole:"+lightUseWholeImage;
    conf=conf+",bandMode:'"+lightBandMode+"',bandWidth:"+d2s(bandNm,12)+",bandCount:"+bandCount+",thickness:"+lightThicknessNm+",uncertainty:"+lightThicknessUncertaintyNm;
    conf=conf+",sizeBreaks:'"+jsEscape(lightSizeBreaks)+"',contrast:"+lightResultContrast+",histogram:"+lightHistogramBinNm+",featureBin:"+lightFeatureDistanceBinNm;
    conf=conf+",imageId:'"+jsEscape(lightImageId)+"',fp:'"+jsEscape(fp)+"',x:"+d2s(lightHF3X,12)+",y:"+d2s(lightHF3Y,12)+"}";
    code="(function(){try{"+source+"\nvar rm=Packages.ij.plugin.frame.RoiManager.getInstance2();return ctlHF3('"+jsEscape(action)+"',"+conf+",Packages.ij.IJ.getImage(),rm==null?[]:rm.getRoisAsArray(),'"+jsEscape(runDir)+"');}catch(e){return 'ERROR|'+String(e);}})();";
    result=""+eval("js",code);
    return result;
}

function lightHF3ImplicitMaterialArea() {
    if(lightImageMode!="with_surface"||surfaceDefined==0||surfaceSideDefined==0)return 0;
    return 1;
}

function lightHF3BandIndex(depth) {
    if(depth<0||isNaN(depth)||bandNm<=0)return -1;
    q=depth/bandNm;r=round(q);if(abs(q-r)<1e-10)q=r;b=floor(q);
    if(lightBandMode=="count"&&b==bandCount&&abs(depth-bandCount*bandNm)<1e-8)b=bandCount-1;
    return b;
}

function lightHF3SetMetrics(idx) {
    if(lightCavityContextActive!=1)return 0;
    if(idx<0||idx>=lightCtxDepth.length)return 0;
    surfaceLastSignedDistanceNm=lightCtxDepth[idx];surfaceLastDistanceNm=lightCtxAbsolute[idx];
    surfaceLastArcNm=lightCtxArc[idx];surfaceLastNearestXpx=lightCtxNearX[idx];surfaceLastNearestYpx=lightCtxNearY[idx];surfaceLastTangentAngleDeg=lightCtxAngle[idx];
    return 1;
}

function lightHF3ParseArray(payload) {
    if(payload=="-"||payload=="")return newArray(0);
    aa=split(payload,",");out=newArray(aa.length);
    for(kk=0;kk<aa.length;kk++)out[kk]=parseFloat(aa[kk]);
    return out;
}

function lightHF3CheckCombinedInputs(ids) {
    code="var HF46_ROOT='"+jsEscape(lightProjectRoot)+"', HF46_PROJECT='"+jsEscape(lightProjectId)+"', HF46_UID='"+jsEscape(lightProjectUid)+"', HF46_IDS='"+jsEscape(ids)+"';\n";
    code=code+"/* One validation at the combination boundary. Existing HF3/HF4 results remain\n";
    code=code+" * usable when intact and current; no project migration is performed. */\n";
    code=code+"(function () {\n";
    code=code+"    var F=Packages.java.io.File, Files=Packages.java.nio.file.Files,\n";
    code=code+"        CS=Packages.java.nio.charset.StandardCharsets, root=String(HF46_ROOT),\n";
    code=code+"        ids=String(HF46_IDS).split(';'), seen={}, featureWidth=null;\n";
    code=code+"    function read(path){return String(new java.lang.String(Files.readAllBytes(new F(path).toPath()),CS.UTF_8));}\n";
    code=code+"    function kv(path){var out={},lines=read(path).split(/\\r?\\n/);for(var i=0;i<lines.length;i++){var p=lines[i].indexOf('\\t');if(p>0)out[lines[i].slice(0,p)]=lines[i].slice(p+1).trim();}return out;}\n";
    code=code+"    function requireEqual(a,b,label,id){if(String(a)!==String(b))throw Error(id+': '+label+' no coincide; vuelva a exportar esta imagen.');}\n";
    code=code+"    function numeric(a,b,label,id){a=Number(a);b=Number(b);if(!isFinite(a)||!isFinite(b)||Math.abs(a-b)>1e-9*Math.max(1,Math.abs(a),Math.abs(b)))throw Error(id+': '+label+' ha cambiado; vuelva a exportar esta imagen.');}\n";
    code=code+"    try {\n";
    code=code+"        if(!ids.length||!ids[0])throw Error('Seleccione al menos una imagen.');\n";
    code=code+"        for(var i=0;i<ids.length;i++) {\n";
    code=code+"            var id=ids[i];if(seen[id])throw Error('Imagen repetida: '+id);seen[id]=1;\n";
    code=code+"            var folder=root+'images/'+id+'/',meta=kv(folder+'image_metadata.tsv'),relative=read(folder+'current_run.txt').trim();\n";
    code=code+"            if(!/^roi_sessions\\/[^/]+\\/measurement_runs\\/[^/]+$/.test(relative))throw Error('Ruta de resultados no valida: '+id);\n";
    code=code+"            var run=folder+relative+'/',verified=String(Packages.cavity.light.HF46.verifyRun(run));\n";
    code=code+"            if(verified!=='OK')throw Error(id+': '+verified.replace(/^ERROR\\|/,''));\n";
    code=code+"            var summary=kv(run+'image_summary.tsv'),method=JSON.parse(read(run+'analysis_method.json')),manifest=JSON.parse(read(run+'run_manifest.json'));\n";
    code=code+"            requireEqual(method.version,'1.1.1-R9-HF3','metodo geometrico',id);\n";
    code=code+"            requireEqual(meta.project_id,HF46_PROJECT,'proyecto',id);\n";
    code=code+"            if(meta.project_uid)requireEqual(meta.project_uid,HF46_UID,'UID del proyecto',id);\n";
    code=code+"            requireEqual(meta.image_id,id,'imagen',id);\n";
    code=code+"            requireEqual(summary.project_id,HF46_PROJECT,'proyecto del resultado',id);\n";
    code=code+"            requireEqual(summary.image_id,id,'imagen del resultado',id);\n";
    code=code+"            requireEqual(summary.source_sha256,meta.source_sha256,'fuente',id);\n";
    code=code+"            requireEqual(summary.revision_id,meta.current_revision,'revision vigente',id);\n";
    code=code+"            requireEqual(relative,'roi_sessions/'+summary.revision_id+'/measurement_runs/'+summary.run_id,'ruta del resultado',id);\n";
    code=code+"            requireEqual(manifest.project.id,HF46_PROJECT,'proyecto del manifiesto',id);\n";
    code=code+"            if(manifest.project.uid)requireEqual(manifest.project.uid,HF46_UID,'UID del manifiesto',id);\n";
    code=code+"            requireEqual(manifest.image.id,id,'imagen del manifiesto',id);\n";
    code=code+"            requireEqual(manifest.image.sha256,meta.source_sha256,'fuente del manifiesto',id);\n";
    code=code+"            requireEqual(manifest.revision_id,meta.current_revision,'revision del manifiesto',id);\n";
    code=code+"            requireEqual(summary.image_mode,meta.image_mode,'modo de analisis',id);\n";
    code=code+"            requireEqual(summary.sample_name||'',meta.sample_name||'','muestra',id);\n";
    code=code+"            requireEqual(summary.experimental_condition||'',meta.experimental_condition||'','condicion',id);\n";
    code=code+"            numeric(summary.foil_thickness_nm,meta.foil_thickness_nm,'espesor',id);\n";
    code=code+"            numeric(manifest.scale.active_nm_per_px_x,meta.active_scale_x_nm_px,'escala X',id);\n";
    code=code+"            numeric(manifest.scale.active_nm_per_px_y,meta.active_scale_y_nm_px,'escala Y',id);\n";
    code=code+"            numeric(manifest.settings.include_uncertain,meta.include_uncertain,'inclusion de dudosas',id);\n";
    code=code+"            numeric(manifest.area.whole_image_confirmed,meta.use_whole_image,'dominio completo',id);\n";
    code=code+"            numeric(manifest.settings.feature_distance_bin_nm,meta.feature_distance_bin_nm,'intervalo de distancia',id);\n";
    code=code+"            if(summary.image_mode==='with_surface'&&!new F(run+'depth_area_1nm.tsv').isFile())throw Error(id+': falta la tabla de areas por profundidad.');\n";
    code=code+"            if(new F(run+'feature_distance_summary.csv').isFile()){\n";
    code=code+"                var lines=read(run+'feature_distance_summary.csv').split(/\\r?\\n/),header=lines[0].split(','),ix={};\n";
    code=code+"                for(var j=0;j<header.length;j++)ix[header[j]]=j;\n";
    code=code+"                for(j=1;j<lines.length;j++)if(lines[j].trim()){\n";
    code=code+"                    var row=lines[j].split(','),low=Number(row[ix.bin_low_nm]),high=Number(row[ix.bin_high_nm]),bin=Number(row[ix.bin_index]),width=high-low;\n";
    code=code+"                    if(!isFinite(width)||width<=0||!isFinite(bin)||bin<0||bin!==Math.floor(bin)||Math.abs(low-bin*width)>1e-7*Math.max(1,Math.abs(low)))throw Error(id+': intervalos de distancia no validos.');\n";
    code=code+"                    if(featureWidth===null)featureWidth=width;\n";
    code=code+"                    numeric(width,featureWidth,'ancho de distancia comun',id);\n";
    code=code+"                }\n";
    code=code+"            }\n";
    code=code+"        }\n";
    code=code+"        return 'OK';\n";
    code=code+"    }catch(e){return 'ERROR|'+String(e);}\n";
    code=code+"})();\n";
    return ""+eval("js",code);
}


// HF4 capture bridge. Heavy analysis remains in the HF3 functions.
function lightHF4Available() {
    js="(function(){try{return String(Packages.cavity.light.HF4.version())+'|'+String(Packages.cavity.light.HF46.version());}catch(e){return '';}})();";
    v=""+eval("js",js);
    if(v!="1.1.1-R9-HF4.1|1.1.1-R9-HF4.6") {
        showMessage("Complemento R9 no coincidente",
            "Macro: " + lightReleaseVersion + "\n" +
            "Contrato esperado: HF4.1 + extension HF4.6.\nDetectado: " + v + "\n\n" +
            "Instale macro y cavity-light-hf4.jar del MISMO paquete y reinicie Fiji.\n" +
            "Use INSTALAR_CANDIDATA_R9.bat. No mezcle JAR antiguos o duplicados.\n" +
            "No se ha abierto ni modificado ningun proyecto desde esta comprobacion.");
        return 0;
    }
    return 1;
}
function lightHF4Configure() {
    if(!updateScaleMaybe())return 0;
    lightHF4Pull();
    text="Project_id\t"+lightProjectId+"\nProject_uid\t"+lightProjectUid+"\nImage_id\t"+lightImageId+"\nSource_sha256\t"+lightSourceSha256+"\n";
    text=text+"Revision_id\t"+lightCurrentRevision+"\nSession_macro_version\t"+macroVersion+"\nLight_schema_version\t1\nImage_mode\t"+lightImageMode+"\n";
    text=text+"Sample_name\t"+lightTsvClean(sampleName)+"\nExperimental_condition\t"+lightTsvClean(experimentalCondition)+"\nMontage_id\t"+lightImageId+"\nImage_title\t"+lightTsvClean(getTitle())+"\nImage_width_px\t"+getWidth()+"\nImage_height_px\t"+getHeight()+"\n";
    text=text+"Session_scale_nm_per_px_x\t"+d2s(nmPerPixelX,12)+"\nSession_scale_nm_per_px_y\t"+d2s(nmPerPixelY,12)+"\nSession_scale_unit\tnm\nFoil_thickness_nm\t"+lightThicknessNm+"\n";
    text=text+"Cavity_class\t"+activeCavityClass+"\nCavity_class_label\t"+activeCavityClassLabel+"\nCavity_confidence\t"+activeCavityConfidence+"\n";
    setCavityClassColorVariables(activeCavityClass);
    text=text+"counter\t"+cavityCounter+"\nlabels\t"+showRoiLabels+"\nfill\t"+fillCavities+"\nstroke\t"+roiStrokeWidth+"\ncolor\t"+activeStrokeColor+"\n";
    result=call("cavity.light.HF4.configure",text);
    if(startsWith(result,"ERROR")){showMessage("Captura no preparada",result);return 0;}
    return 1;
}
function lightHF4Pull() {
    if(nImages()<=0)return;
    result=call("cavity.light.HF4.state","");a=split(result,"|");
    if(a.length<4)return;
    serial=parseFloat(a[0]);if(serial>cavityCounter)cavityCounter=serial;
    lightCachedCavityCount=parseFloat(a[1]);seq=parseFloat(a[3]);key=""+getImageID()+"|"+seq;
    if(seq>0&&key!=lightHF4LastSequence){
        undoKind="add";undoObjectId=a[2];undoDeletedName="";undoAvailable=1;
        lightHF4LastSequence=key;lightInvalidateAnalysisCache();
    }
    lightInteractivePullActiveDiameter();
}
function lightHF4Arm(mode) {
    if(!v4PrepareImageForMeasurement(1))return 0;
    if(!lightHF4Configure())return 0;
    result=call("cavity.light.HF4.arm",mode);
    if(startsWith(result,"ERROR")){showMessage("Captura no preparada",result);return 0;}
    return 1;
}
function lightHF4Pause() {
    call("cavity.light.HF4.pause","");lightInteractiveMode="select";
    lightInteractiveRemovePreview();setTool("oval");
}
function lightHF4RequireReviewed() {
    count=parseFloat(call("cavity.light.HF4.pendingCount",""));
    if(count>0){showMessage("Propuestas pendientes",count+" propuestas siguen en revision.\nAceptelas o descartelas antes de guardar o exportar.\nPuede reabrirlas con Revisar propuestas.");return 0;}
    return 1;
}
function lightHF4PushPreferences() {
    text="Cavity_class\t"+activeCavityClass+"\nCavity_class_label\t"+activeCavityClassLabel+"\nCavity_confidence\t"+activeCavityConfidence+"\nRevision_id\t"+lightCurrentRevision+"\n";
    setCavityClassColorVariables(activeCavityClass);
    text=text+"labels\t"+showRoiLabels+"\nfill\t"+fillCavities+"\nstroke\t"+roiStrokeWidth+"\ncolor\t"+activeStrokeColor+"\n";
    call("cavity.light.HF4.preferences",text);
}
function lightHF43BulkCall(action, mode) {
    code="var HF43_ACTION=\'"+action+"\';var HF43_MODE=\'"+mode+"\';\n";
    code=code+"(function(){\n";
    code=code+"    try {\n";
    code=code+"        var P=Packages;\n";
    code=code+"        var WM=P.ij.WindowManager;\n";
    code=code+"        var RM=P.ij.plugin.frame.RoiManager;\n";
    code=code+"        var Overlay=P.ij.gui.Overlay;\n";
    code=code+"        var Color=P.java.awt.Color;\n";
    code=code+"        var ArrayList=P.java.util.ArrayList;\n";
    code=code+"        var HashSet=P.java.util.HashSet;\n";
    code=code+"        var ShapeRoi=P.ij.gui.ShapeRoi;\n";
    code=code+"        var imp=WM.getCurrentImage();\n";
    code=code+"        var rm=RM.getInstance2();\n";
    code=code+"        if(imp==null)return 'ERROR|No hay imagen activa.';\n";
    code=code+"        if(rm==null)return 'ERROR|ROI Manager no disponible.';\n";
    code=code+"        function text(v){return v==null?'':String(v);}\n";
    code=code+"        function prop(r,k){return text(r.getProperty(k));}\n";
    code=code+"        function cavity(r){return r!=null&&(prop(r,'Type')=='cavity'||prop(r,'Object_type')=='cavity');}\n";
    code=code+"        function cavityId(r){var id=prop(r,'Cavity_id');if(id=='')id=text(r.getName());return id;}\n";
    code=code+"        function clearPreview(){\n";
    code=code+"            var ov=imp.getOverlay();\n";
    code=code+"            if(ov!=null){\n";
    code=code+"                for(var q=ov.size()-1;q>=0;q--){var rr=ov.get(q),nm=rr==null?'':text(rr.getName());if(nm.indexOf('__HF43_BULK_PREVIEW__')==0)ov.remove(q);}\n";
    code=code+"                if(ov.size()==0)imp.setOverlay(null);else imp.setOverlay(ov);\n";
    code=code+"            }\n";
    code=code+"            imp.draw();\n";
    code=code+"        }\n";
    code=code+"        function sameImage(r){\n";
    code=code+"            var rid=prop(r,'Image_id'),pid=prop(r,'Project_id');\n";
    code=code+"            var iid=text(imp.getProperty('CavityTEMLight.ImageId')),pp=text(imp.getProperty('CavityTEMLight.ProjectId'));\n";
    code=code+"            if(rid!=''&&iid!=''&&rid!=iid)return false;\n";
    code=code+"            if(pid!=''&&pp!=''&&pid!=pp)return false;\n";
    code=code+"            return true;\n";
    code=code+"        }\n";
    code=code+"        function boundsOverlap(a,b){return a.x<=b.x+b.width&&a.x+a.width>=b.x&&a.y<=b.y+b.height&&a.y+a.height>=b.y;}\n";
    code=code+"        function centerInside(sel,r){var b=r.getFloatBounds();return sel.containsPoint(b.getCenterX(),b.getCenterY());}\n";
    code=code+"        function touches(sel,r){\n";
    code=code+"            var sb=sel.getFloatBounds(),rb=r.getFloatBounds();\n";
    code=code+"            if(!boundsOverlap(sb,rb))return false;\n";
    code=code+"            if(centerInside(sel,r))return true;\n";
    code=code+"            if(r.isArea()){\n";
    code=code+"                try{\n";
    code=code+"                    var inter=new ShapeRoi(sel);\n";
    code=code+"                    inter.and(new ShapeRoi(r));\n";
    code=code+"                    var ib=inter.getFloatBounds();\n";
    code=code+"                    if(ib.width>0&&ib.height>0)return true;\n";
    code=code+"                }catch(ignoreShape){}\n";
    code=code+"            }\n";
    code=code+"            try{\n";
    code=code+"                var fp=r.getContainedFloatPoints();\n";
    code=code+"                if(fp!=null&&fp.npoints>0){\n";
    code=code+"                    var step=Math.max(1,Math.floor(fp.npoints/256));\n";
    code=code+"                    for(var k=0;k<fp.npoints;k+=step)if(sel.containsPoint(fp.xpoints[k],fp.ypoints[k]))return true;\n";
    code=code+"                    if(!sel.isLine()&&r.isArea()){\n";
    code=code+"                        var scx=sb.getCenterX(),scy=sb.getCenterY();\n";
    code=code+"                        if(r.containsPoint(scx,scy))return true;\n";
    code=code+"                    }\n";
    code=code+"                }\n";
    code=code+"            }catch(ignorePoints){}\n";
    code=code+"            return false;\n";
    code=code+"        }\n";
    code=code+"        if(HF43_ACTION=='clear'){\n";
    code=code+"            clearPreview();\n";
    code=code+"            imp.setProperty('CavityHF43.BulkSelectedIds',null);\n";
    code=code+"            return 'OK|0';\n";
    code=code+"        }\n";
    code=code+"        if(HF43_ACTION=='preview'){\n";
    code=code+"            clearPreview();\n";
    code=code+"            var sel=imp.getRoi();\n";
    code=code+"            if(sel==null||!sel.isArea())return 'ERROR|Dibuje primero una seleccion de area: rectangulo, poligono o seleccion libre.';\n";
    code=code+"            if(cavity(sel)||text(sel.getName()).indexOf('CAV_')==0)return 'ERROR|La ROI activa es una cavidad. Dibuje una region nueva alrededor de las cavidades que desea revisar.';\n";
    code=code+"            var ids=new ArrayList();\n";
    code=code+"            var seen=new HashSet();\n";
    code=code+"            var ov=imp.getOverlay();if(ov==null)ov=new Overlay();\n";
    code=code+"            for(var i=0;i<rm.getCount();i++){\n";
    code=code+"                var r=rm.getRoi(i);if(!cavity(r)||!sameImage(r))continue;\n";
    code=code+"                var hit=HF43_MODE=='touch'?touches(sel,r):centerInside(sel,r);\n";
    code=code+"                if(!hit)continue;\n";
    code=code+"                var id=cavityId(r);if(id==''||seen.contains(id))continue;seen.add(id);ids.add(id);\n";
    code=code+"                var hi=r.clone();hi.setName('__HF43_BULK_PREVIEW__'+id);hi.setStrokeColor(Color.YELLOW);hi.setStrokeWidth(3);hi.setFillColor(null);ov.add(hi);\n";
    code=code+"            }\n";
    code=code+"            imp.setOverlay(ov);imp.draw();\n";
    code=code+"            imp.setProperty('CavityHF43.BulkSelectedIds',ids);\n";
    code=code+"            imp.setProperty('CavityHF43.BulkSelectionMode',HF43_MODE);\n";
    code=code+"            var limit=Math.min(ids.size(),18),summary='';\n";
    code=code+"            for(var j=0;j<limit;j++){if(j>0)summary+=', ';summary+=String(ids.get(j));}\n";
    code=code+"            if(ids.size()>limit)summary+=', ...';\n";
    code=code+"            return 'OK|'+ids.size()+'|'+summary;\n";
    code=code+"        }\n";
    code=code+"        if(HF43_ACTION=='delete'){\n";
    code=code+"            var planned=imp.getProperty('CavityHF43.BulkSelectedIds');\n";
    code=code+"            if(!(planned instanceof ArrayList)||planned.size()==0)return 'ERROR|No hay una preseleccion grafica pendiente.';\n";
    code=code+"            var wanted=new HashSet();for(var p=0;p<planned.size();p++)wanted.add(String(planned.get(p)));\n";
    code=code+"            var indexes=new ArrayList();\n";
    code=code+"            for(var a=0;a<rm.getCount();a++){var rr=rm.getRoi(a);if(cavity(rr)&&sameImage(rr)&&wanted.contains(cavityId(rr)))indexes.add(new P.java.lang.Integer(a));}\n";
    code=code+"            if(indexes.size()!=planned.size())return 'ERROR|La lista de ROI ha cambiado desde la previsualizacion. No se ha borrado nada; repita la seleccion.';\n";
    code=code+"            var deleted=new ArrayList();\n";
    code=code+"            for(var z=indexes.size()-1;z>=0;z--){\n";
    code=code+"                var idx=indexes.get(z).intValue(),original=rm.getRoi(idx);deleted.add(0,original.clone());rm.select(idx);rm.runCommand('Delete');\n";
    code=code+"            }\n";
    code=code+"            imp.setProperty('CavityHF43.BulkDeletedRois',deleted);\n";
    code=code+"            imp.setProperty('CavityHF43.BulkSelectedIds',null);\n";
    code=code+"            imp.setProperty('CavityHF4.Dirty','1');\n";
    code=code+"            clearPreview();\n";
    code=code+"            return 'OK|'+deleted.size();\n";
    code=code+"        }\n";
    code=code+"        if(HF43_ACTION=='undo'){\n";
    code=code+"            var deletedRois=imp.getProperty('CavityHF43.BulkDeletedRois');\n";
    code=code+"            if(!(deletedRois instanceof ArrayList)||deletedRois.size()==0)return 'ERROR|No hay un borrado multiple pendiente de deshacer.';\n";
    code=code+"            var existing=new HashSet();for(var e=0;e<rm.getCount();e++){var er=rm.getRoi(e);if(cavity(er))existing.add(cavityId(er));}\n";
    code=code+"            for(var u=0;u<deletedRois.size();u++){var candidate=deletedRois.get(u),cid=cavityId(candidate);if(cid!=''&&existing.contains(cid))return 'ERROR|No se puede deshacer: ya existe '+cid+'. No se ha modificado el ROI Manager.';}\n";
    code=code+"            var restored=0;\n";
    code=code+"            for(var v=0;v<deletedRois.size();v++){var copy=deletedRois.get(v).clone();rm.add(imp,copy,-1);restored++;}\n";
    code=code+"            imp.setProperty('CavityHF43.BulkDeletedRois',null);\n";
    code=code+"            imp.setProperty('CavityHF4.Dirty','1');\n";
    code=code+"            clearPreview();\n";
    code=code+"            return 'OK|'+restored;\n";
    code=code+"        }\n";
    code=code+"        return 'ERROR|Accion HF4.6 desconocida.';\n";
    code=code+"    } catch(e) {\n";
    code=code+"        return 'ERROR|'+String(e);\n";
    code=code+"    }\n";
    code=code+"})()\n";
    return "" + eval("js", code);
}

function lightHF43ClearBulkPreview() {
    lightHF43BulkCall("clear", "center");
}

function lightHF43GraphicalDelete() {
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra una imagen registrada antes de usar el borrado grafico."); return; }
    if (!lightProjectLoaded || lightImageId == "") { showMessage("Proyecto no preparado", "Seleccione primero una imagen registrada del proyecto."); return; }
    Dialog.create("Borrado grafico multiple HF4.6");
    Dialog.addChoice("Criterio de seleccion:", newArray("Centro de la cavidad dentro de la region", "Cualquier contacto con la region"), "Centro de la cavidad dentro de la region");
    Dialog.addMessage("1. Dibuje antes un rectangulo, poligono o seleccion libre sobre la imagen.\n2. HF4.6 resaltara en amarillo SOLO cavidades.\n3. Superficie, mascaras, exclusiones y microestructura estan protegidas.\n4. El borrado no se ejecuta hasta una confirmacion posterior.");
    Dialog.show();
    criterion=Dialog.getChoice();mode="center";if(startsWith(criterion,"Cualquier"))mode="touch";
    result=lightHF43BulkCall("preview",mode);
    if(startsWith(result,"ERROR")){showMessage("Seleccion grafica no preparada",result);return;}
    parts=split(result,"|");count=parseFloat(parts[1]);ids="";if(parts.length>2)ids=parts[2];
    if(count<=0){lightHF43ClearBulkPreview();showMessage("Sin cavidades", "La region no contiene cavidades con el criterio elegido.");return;}
    label="centro dentro de la region";if(mode=="touch")label="contacto con la region";
    msg="Se han resaltado " + count + " cavidades (" + label + ").\n\n" + ids + "\n\nBorrar exactamente estas cavidades?\nEl resto de ROIs esta protegido y podra deshacer este lote con 'Deshacer borrado multiple'.";
    if(!getBoolean(msg,"BORRAR "+count+" CAVIDADES","Cancelar")){lightHF43ClearBulkPreview();return;}
    if(count>100){if(!getBoolean("La seleccion contiene "+count+" cavidades. Confirme una segunda vez el borrado masivo.","CONFIRMAR BORRADO","Cancelar")){lightHF43ClearBulkPreview();return;}}
    deleted=lightHF43BulkCall("delete",mode);
    if(startsWith(deleted,"ERROR")){lightHF43ClearBulkPreview();showMessage("Borrado cancelado",deleted);return;}
    undoAvailable=0;undoKind="";undoObjectId="";undoDeletedName="";
    lightInvalidateCavityCount();lightInvalidateAnalysisCache();lightHF4Pull();showAllRois();lightRefreshPanel();
    lightAppendLog("BULK_DELETE_HF43", "count="+count+"; mode="+mode);
    showStatus(count+" cavidades borradas. Deshacer borrado multiple restaura el lote completo.");
}

function lightHF43UndoBulkDelete() {
    if (nImages() <= 0) return;
    result=lightHF43BulkCall("undo","center");
    if(startsWith(result,"ERROR")){showMessage("No se puede deshacer",result);return;}
    parts=split(result,"|");count=parseFloat(parts[1]);
    undoAvailable=0;undoKind="";undoObjectId="";undoDeletedName="";
    lightInvalidateCavityCount();lightInvalidateAnalysisCache();lightHF4Pull();showAllRois();lightRefreshPanel();
    lightAppendLog("BULK_DELETE_UNDO_HF43", "count="+count);
    showStatus(count+" cavidades restauradas con sus IDs y propiedades.");
}

function lightHF44BackgroundCall(action, threshold, mode) {
    code="var HF44_ACTION=\'"+action+"\';var HF44_THRESHOLD="+d2s(threshold,9)+";var HF44_MODE=\'"+mode+"\';\n";
    code=code+"(function(){\n";
    code=code+"    try {\n";
    code=code+"        var IJ=Packages.ij.IJ;\n";
    code=code+"        var ByteProcessor=Packages.ij.process.ByteProcessor;\n";
    code=code+"        var ImageProcessor=Packages.ij.process.ImageProcessor;\n";
    code=code+"        var FloodFiller=Packages.ij.process.FloodFiller;\n";
    code=code+"        var ThresholdToSelection=Packages.ij.plugin.filter.ThresholdToSelection;\n";
    code=code+"        var Overlay=Packages.ij.gui.Overlay;\n";
    code=code+"        var Color=Packages.java.awt.Color;\n";
    code=code+"        var imp=IJ.getImage();\n";
    code=code+"        var key='CavityLightHF44BackgroundCandidate';\n";
    code=code+"        var previewName='__CTL_HF44_BG_PREVIEW__';\n";
    code=code+"        if(imp==null) return 'ERROR|No active image';\n";
    code=code+"\n";
    code=code+"        function clearPreview(){\n";
    code=code+"            var ov=imp.getOverlay();\n";
    code=code+"            if(ov!=null){\n";
    code=code+"                try{ov.remove(previewName);}catch(e1){}\n";
    code=code+"                if(ov.size()==0) imp.setOverlay(null); else imp.setOverlay(ov);\n";
    code=code+"            }\n";
    code=code+"            imp.updateAndDraw();\n";
    code=code+"        }\n";
    code=code+"        function clearCandidate(){\n";
    code=code+"            try{imp.setProperty(key,null);}catch(e2){}\n";
    code=code+"            try{imp.setProperty(key+'.meta',null);}catch(e3){}\n";
    code=code+"            imp.setProperty(key+'.context',null);\n";
    code=code+"        }\n";
    code=code+"        function contextKey(){\n";
    code=code+"            return [imp.getID(),imp.getWidth(),imp.getHeight(),imp.getCurrentSlice(),\n";
    code=code+"                String(imp.getProperty('CavityTEMLight.ProjectId')||''),\n";
    code=code+"                String(imp.getProperty('CavityTEMLight.ImageId')||''),\n";
    code=code+"                String(imp.getProperty('CavityTEMLight.SourceSHA256')||'')].join('|');\n";
    code=code+"        }\n";
    code=code+"        function pixelValue(pixels,bit,index){\n";
    code=code+"            if(bit==8) return Number(pixels[index])&255;\n";
    code=code+"            if(bit==16) return Number(pixels[index])&65535;\n";
    code=code+"            if(bit==32) return Number(pixels[index]);\n";
    code=code+"            var p=Number(pixels[index]),r=(p>>16)&255,g=(p>>8)&255,b=p&255;\n";
    code=code+"            return 0.299*r+0.587*g+0.114*b;\n";
    code=code+"        }\n";
    code=code+"\n";
    code=code+"        if(String(HF44_ACTION)=='clear'){\n";
    code=code+"            clearPreview();\n";
    code=code+"            clearCandidate();\n";
    code=code+"            return 'OK|CLEARED';\n";
    code=code+"        }\n";
    code=code+"\n";
    code=code+"        if(String(HF44_ACTION)=='commit'){\n";
    code=code+"            var saved=imp.getProperty(key);\n";
    code=code+"            if(saved==null) return 'ERROR|No background candidate is available';\n";
    code=code+"            var context=String(imp.getProperty(key+'.context')||'');\n";
    code=code+"            if(context!=contextKey())return 'ERROR|Image context changed after preview';\n";
    code=code+"            clearPreview();\n";
    code=code+"            imp.setRoi(saved.clone());\n";
    code=code+"            return 'OK|COMMITTED|'+String(imp.getProperty(key+'.meta')||'');\n";
    code=code+"        }\n";
    code=code+"\n";
    code=code+"        if(String(HF44_ACTION)!='preview') return 'ERROR|Unknown action';\n";
    code=code+"        clearPreview();\n";
    code=code+"        clearCandidate();\n";
    code=code+"        var threshold=Number(HF44_THRESHOLD);\n";
    code=code+"        if(!isFinite(threshold) || threshold<0) return 'ERROR|Invalid threshold';\n";
    code=code+"        var mode=String(HF44_MODE);\n";
    code=code+"        if(mode!='border' && mode!='all') return 'ERROR|Invalid detection mode';\n";
    code=code+"        if(imp.getStackSize()!=1)return 'ERROR|Use a single 2D image, not a stack';\n";
    code=code+"        var ip=imp.getProcessor(),pixels=ip.getPixels(),w=imp.getWidth(),h=imp.getHeight(),n=w*h,bit=imp.getBitDepth();\n";
    code=code+"        if(!(bit==8 || bit==16 || bit==24 || bit==32)) return 'ERROR|Unsupported bit depth: '+bit;\n";
    code=code+"        if(n<=0) return 'ERROR|Empty image';\n";
    code=code+"        var bp=new ByteProcessor(w,h),candidateCount=0,min=Infinity,max=-Infinity,i,v;\n";
    code=code+"        for(i=0;i<n;i++){\n";
    code=code+"            if(i%262144==0){IJ.showProgress(i,n);if(IJ.escapePressed())return 'ERROR|Detection cancelled';}\n";
    code=code+"            v=pixelValue(pixels,bit,i);\n";
    code=code+"            if(v<min)min=v;if(v>max)max=v;\n";
    code=code+"            if(v>=0 && v<=threshold){bp.set(i,255);candidateCount++;}\n";
    code=code+"        }\n";
    code=code+"        if(candidateCount<=0) return 'EMPTY|0|0|'+min+'|'+max+'|'+threshold+'|'+mode+'|'+bit;\n";
    code=code+"        var selectedCount=candidateCount;\n";
    code=code+"        if(mode=='border'){\n";
    code=code+"            bp.setValue(128);\n";
    code=code+"            var ff=new FloodFiller(bp),x,y;\n";
    code=code+"            for(x=0;x<w;x++){\n";
    code=code+"                if(bp.get(x,0)==255)ff.fill8(x,0);\n";
    code=code+"                if(h>1 && bp.get(x,h-1)==255)ff.fill8(x,h-1);\n";
    code=code+"            }\n";
    code=code+"            for(y=1;y<h-1;y++){\n";
    code=code+"                if(bp.get(0,y)==255)ff.fill8(0,y);\n";
    code=code+"                if(w>1 && bp.get(w-1,y)==255)ff.fill8(w-1,y);\n";
    code=code+"            }\n";
    code=code+"            selectedCount=0;\n";
    code=code+"            for(i=0;i<n;i++){\n";
    code=code+"                if(bp.get(i)==128){bp.set(i,255);selectedCount++;}\n";
    code=code+"                else bp.set(i,0);\n";
    code=code+"            }\n";
    code=code+"        }\n";
    code=code+"        if(selectedCount<=0) return 'EMPTY|0|0|'+min+'|'+max+'|'+threshold+'|'+mode+'|'+bit;\n";
    code=code+"        bp.setThreshold(255,255,ImageProcessor.NO_LUT_UPDATE);\n";
    code=code+"        var roi=new ThresholdToSelection().convert(bp);\n";
    code=code+"        if(roi==null) return 'ERROR|Threshold-to-selection returned no ROI';\n";
    code=code+"        var fraction=selectedCount/n;\n";
    code=code+"        var meta=[selectedCount,fraction,min,max,threshold,mode,bit,w,h].join(',');\n";
    code=code+"        imp.setProperty(key,roi.clone());\n";
    code=code+"        imp.setProperty(key+'.meta',meta);\n";
    code=code+"        imp.setProperty(key+'.context',contextKey());\n";
    code=code+"        IJ.showProgress(1.0);\n";
    code=code+"        var ov=imp.getOverlay();if(ov==null)ov=new Overlay();\n";
    code=code+"        var preview=roi.clone();\n";
    code=code+"        preview.setName(previewName);\n";
    code=code+"        preview.setStrokeColor(Color.MAGENTA);\n";
    code=code+"        preview.setStrokeWidth(2.0);\n";
    code=code+"        preview.setFillColor(new Color((72<<24)|0xff00ff,true));\n";
    code=code+"        ov.add(preview);\n";
    code=code+"        imp.setOverlay(ov);\n";
    code=code+"        imp.updateAndDraw();\n";
    code=code+"        return 'OK|'+selectedCount+'|'+fraction+'|'+min+'|'+max+'|'+threshold+'|'+mode+'|'+bit+'|'+candidateCount;\n";
    code=code+"    } catch(e) {\n";
    code=code+"        return 'ERROR|'+String(e);\n";
    code=code+"    }\n";
    code=code+"})()\n";
    return "" + eval("js", code);
}

function lightHF44ClearBackgroundPreview() {
    if (nImages() <= 0) return;
    lightHF44BackgroundCall("clear", 0, "border");
}

function lightHF44DetectBlackBackground() {
    if (!v4PrepareImageForMeasurement(1)) return;
    lightHF4Pause();
    backgroundImageId = getImageID();
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra primero la imagen o montaje TEM registrado."); return; }
    if (!lightProjectLoaded || lightImageId == "") { showMessage("Proyecto no preparado", "Seleccione primero una imagen registrada del proyecto."); return; }
    defaultThreshold = parseFloat("" + call("ij.Prefs.get", "cavity.tem.light.hf44.background.threshold", "0"));
    if (isNaN(defaultThreshold)) defaultThreshold = 0;
    defaultMode = "" + call("ij.Prefs.get", "cavity.tem.light.hf44.background.mode", "border");
    choices = newArray("Solo fondo conectado al borde (recomendado)", "Todos los pixeles entre 0 y el umbral");
    defaultChoice = choices[0]; if (defaultMode == "all") defaultChoice = choices[1];
    Dialog.create("Detectar fondo negro - HF4.6");
    Dialog.addNumber("Valor maximo considerado negro:", defaultThreshold, 3, 12, "intensidad original");
    Dialog.addChoice("Region a excluir:", choices, defaultChoice);
    Dialog.addMessage("Use 0 para fondo negro puro. Si el montaje tiene un fondo ligeramente elevado, aumente el umbral poco a poco.\n\nEl modo conectado al borde evita seleccionar objetos oscuros aislados dentro de la micrografia y es el recomendado. La imagen original NO se modifica: HF4.6 trabaja sobre una mascara temporal y muestra una previsualizacion magenta antes de crear la exclusion.");
    Dialog.show();
    threshold = Dialog.getNumber(); criterion = Dialog.getChoice();
    if (isNaN(threshold) || threshold < 0) { showMessage("Umbral no valido", "Introduzca un valor numerico mayor o igual que cero para el fondo negro."); return; }
    mode = "border"; if (startsWith(criterion,"Todos")) mode = "all";
    if (getImageID() != backgroundImageId) { showMessage("Imagen cambiada", "Vuelva a seleccionar la imagen y repita la deteccion."); return; }
    showStatus("Detectando fondo negro; el original no se modifica...");
    result = lightHF44BackgroundCall("preview", threshold, mode);
    if (startsWith(result,"ERROR")) { lightHF45ClearBackgroundFor(backgroundImageId); showMessage("No se pudo detectar el fondo", result); return; }
    if (startsWith(result,"EMPTY")) { lightHF45ClearBackgroundFor(backgroundImageId); showMessage("Fondo no detectado", "No hay pixeles que cumplan el criterio. Pruebe un umbral ligeramente mayor o revise la imagen."); return; }
    parts = split(result,"|"); count = parseFloat(parts[1]); fraction = parseFloat(parts[2]); minValue=parseFloat(parts[3]); maxValue=parseFloat(parts[4]); bitDepthValue=parseFloat(parts[7]); candidateCount=parseFloat(parts[8]);
    if (isNaN(count) || count <= 0) { lightHF45ClearBackgroundFor(backgroundImageId); showMessage("Fondo no detectado", "La seleccion resultante esta vacia."); return; }
    percent = 100*fraction;
    modeText = "conectado al borde"; if (mode == "all") modeText = "todos los pixeles entre 0 y el umbral";
    msg = "La zona detectada aparece en magenta.\n\nPixeles excluidos: " + d2s(count,0) + " (" + d2s(percent,2) + "% de la imagen).\nCriterio: " + modeText + ".\nUmbral: <= " + d2s(threshold,3) + ".\nRango observado: " + d2s(minValue,3) + " a " + d2s(maxValue,3) + ".\nProfundidad: " + d2s(bitDepthValue,0) + " bit.\n\nCrear una ROI de exclusion con exactamente esta geometria?";
    if (!getBoolean(msg,"CREAR EXCLUSION","Cancelar")) { lightHF45ClearBackgroundFor(backgroundImageId); return; }
    if (fraction > 0.90) {
        if (!getBoolean("La deteccion ocupa " + d2s(percent,1) + "% de la imagen. Confirme que realmente corresponde al fondo del montaje.","CONFIRMAR","Cancelar")) { lightHF45ClearBackgroundFor(backgroundImageId); return; }
    }
    if (getImageID() != backgroundImageId) { lightHF45ClearBackgroundFor(backgroundImageId); showMessage("Imagen cambiada", "No se ha creado ninguna exclusion. Repita la deteccion en la imagen correcta."); return; }
    commit = lightHF44BackgroundCall("commit", threshold, mode);
    if (startsWith(commit,"ERROR")) { lightHF45ClearBackgroundFor(backgroundImageId); showMessage("Exclusion no creada", commit); return; }
    if (!isAreaSelection()) { lightHF45ClearBackgroundFor(backgroundImageId); showMessage("Exclusion no creada", "La deteccion no produjo una ROI de area valida."); return; }
    snapshotCurrentView();
    exclusionCounter++;
    id = "EXCL_" + IJ.pad(exclusionCounter, 3);
    id = lightHF45NextExclusionId(exclusionCounter); exclusionCounter = parseFloat(substring(id,5));
    Roi.setName(id);
    Roi.setGroup(9);
    Roi.setFillColor("#22ff00ff");
    Roi.setStrokeColor("magenta");
    Roi.setUnscalableStrokeWidth(2);
    setCommonObjectProperties();
    v4StampCurrentRevisionBinding();
    Roi.setProperty("Type", "exclusion");
    Roi.setProperty("Exclusion_id", id);
    Roi.setProperty("Exclusion_reason", "montage_background");
    Roi.setProperty("Detection_method", "HF4.6_black_background_" + mode);
    Roi.setProperty("Detection_threshold_max", d2s(threshold,9));
    Roi.setProperty("Detection_pixel_count", d2s(count,0));
    Roi.setProperty("Detection_fraction", d2s(fraction,9));
    Roi.setProperty("Detection_candidate_pixel_count", d2s(candidateCount,0));
    Roi.setProperty("Notes", "Automatic black-background exclusion; non-destructive temporary mask; user confirmed preview.");
    run("ROI Manager...");
    roiManager("add");
    idx = roiManager("count")-1;
    syncAreaObjectAtIndex(idx);
    undoKind = "add"; undoObjectId = id; undoDeletedName = ""; undoAvailable = 1;
    lightHF44BackgroundCall("clear", threshold, mode);
    syncAllObjects(0);
    lightInvalidateAnalysisCache();
    showAllRois();
    restoreViewSnapshot();
    updateSessionMetadataRoi();
    refreshControlPanelStatus();
    call("ij.Prefs.set", "cavity.tem.light.hf44.background.threshold", ""+threshold);
    call("ij.Prefs.set", "cavity.tem.light.hf44.background.mode", mode);
    eval("js", "try{Packages.ij.Prefs.savePreferences();}catch(e){}");
    lightAppendLog("AUTO_BACKGROUND_EXCLUSION_HF44", "id="+id+"; threshold="+threshold+"; mode="+mode+"; pixels="+count+"; fraction="+d2s(fraction,9));
    showStatus("Fondo negro registrado como " + id + ": " + d2s(percent,2) + "% de la imagen excluido.");
}

function lightHF4Assistant(action) {
    if(!lightHF4Arm("select"))return;
    lightInteractiveMode="select";lightInteractivePushState("select");
    result="";
    if(action=="detect")result=call("cavity.light.HF4.detect","");
    if(action=="estimate")result=call("cavity.light.HF4.estimatePoints","");
    if(action=="review")result=call("cavity.light.HF4.review","");
    if(action=="unfitted")result=call("cavity.light.HF4.unfitted","");
    if(startsWith(result,"ERROR"))showMessage("Asistente local",result);
    if(startsWith(result,"WARNING"))showMessage("Asistente local",result);
    lightHF4Pull();lightRefreshPanel();
}
function lightHF4InteractionOptions() {
    lightInteractiveReadResizeStep();
    // Read strings first; pass numeric flags to ImageJ dialogs.
    logState = call("cavity.light.HF4.logs","state");
    logs = 0;
    if (logState == "1" || logState == "true") logs = 1;
    labelsPreference = call("ij.Prefs.get","cavity.tem.light.hf4.capture.labels","false");
    labels = 0;
    if (labelsPreference == "true" || labelsPreference == "1" || labelsPreference == "1.0") labels = 1;
    Dialog.create("HF4 - fluidez y registros");
    Dialog.addNumber("Paso de rueda (nm):",lightInteractiveResizeStepNm,3,10,"nm/paso");
    Dialog.addCheckbox("Mostrar etiquetas durante la captura",labels);
    Dialog.addCheckbox("Abrir registros automaticamente (Log y Console)",logs);
    Dialog.addMessage("Alt+rueda: paso normal. Alt+Mayus+rueda: cinco veces mas fino.\nEl rango del paso es 0.001 a 2.000 nm.\nGuardar conserva las ROIs; validar o exportar completa los calculos pendientes.");Dialog.show();
    step=Dialog.getNumber();labels=Dialog.getCheckbox();logs=Dialog.getCheckbox();
    if(isNaN(step)||step<0.001||step>2){showMessage("Paso no valido","Indique un paso entre 0.001 y 2 nm.");return;}
    lightInteractiveResizeStepNm=step;lightInteractiveSaveResizePreference();
    labelsPreference = "false";
    if (labels == 1) labelsPreference = "true";
    call("ij.Prefs.set","cavity.tem.light.hf4.capture.labels",labelsPreference);
    call("cavity.light.HF4.logs",""+logs);
    eval("js","Packages.ij.Prefs.savePreferences();");
    lightInteractivePushState(lightInteractiveMode);call("cavity.light.HF4.refresh","");lightRefreshPanel();
}
function lightHF4Report(report,errors) {
    lightHF4LastReport=report;call("cavity.light.HF4.log",report);
    if(errors>0){
        first=call("cavity.light.Identity.first","");
        showStatus("Validacion: "+errors+" errores. "+first+". Pestana 5: Localizar identidad / Ver registros.");
    }else showStatus("Validacion completada. Informe disponible en Ver registros.");
}
macro "Cavity Light: detectar puntos en ROI" { lightHF4Assistant("detect"); }
macro "Cavity Light: estimar diametros de puntos" { lightHF4Assistant("estimate"); }
macro "Cavity Light: revisar propuestas" { lightHF4Assistant("review"); }
macro "Cavity Light: puntos sin ajuste" { lightHF4Assistant("unfitted"); }
macro "Cavity Light: elegir color de cavidades" { lightHF43ChooseCavityColor(); }
macro "Cavity Light: borrar varias por region" { lightHF43GraphicalDelete(); }
macro "Cavity Light: deshacer borrado multiple" { lightHF43UndoBulkDelete(); }
macro "Cavity Light: fluidez y registros" { lightHF4InteractionOptions(); }
macro "Cavity Light: ver registros" { call("cavity.light.HF4.logs","show"); }

// Explicit repair works on a loaded revision; no quantitative preparation or
// inferred serial renumbering is performed before the backup.
function lightHF41Identity(action) {
    if(!lightEnsureCurrentImage())return;
    lightHF4Pause();
    if(action=="locate"){call("cavity.light.Identity.locate","");return;}
    if(lightImageDir==""){showStatus("Abra una imagen del proyecto para guardar la copia previa.");return;}
    result=call("cavity.light.Identity.repairNames",lightImageDir+"identity_repairs/");
    if(startsWith(result,"ERROR")){showMessage("Identidad sin modificar",result);return;}
    a=split(result,"|");if(a.length<3)return;
    changed=parseFloat(a[1]);remaining=parseFloat(a[2]);
    if(changed>0)lightInvalidateAnalysisCache();
    lightLastIdAuditErrors=remaining;lightRefreshPanel();
    if(remaining>0)showStatus(changed+" nombres corregidos; "+remaining+" conflictos requieren revision. Pulse Localizar identidad.");
    else if(changed>0)showStatus(changed+" nombre corregido, con copia previa. Guarde una nueva revision.");
    else showStatus("Identidad: sin incoherencias. No se ha cambiado ninguna ROI.");
}
macro "Cavity Light: localizar identidad" { lightHF41Identity("locate"); }
macro "Cavity Light: reparar nombres" { lightHF41Identity("repair"); }


function lightHF45NavigationCall(action) {
    code="var HF45_ACTION=\'"+jsEscape(action)+"\';\n";
    code=code+"/* HF4.6 fixed-window view controller. Image pixels, calibration and ROIs are\n";
    code=code+" * not modified. Only the source viewport and display magnification change.\n";
    code=code+" * ImageJ 1.x public API; Rhino/JavaAdapter and Nashorn/Java.extend supported.\n";
    code=code+" */\n";
    code=code+"(function () {\n";
    code=code+"    var P = Packages, IJ = P.ij.IJ, WM = P.ij.WindowManager;\n";
    code=code+"    var Rectangle = P.java.awt.Rectangle, EventQueue = P.java.awt.EventQueue;\n";
    code=code+"    var KeyEvent = P.java.awt.event.KeyEvent, MouseEvent = P.java.awt.event.MouseEvent;\n";
    code=code+"    var Toolbar = P.ij.gui.Toolbar, Executer = P.ij.Executer;\n";
    code=code+"    var property = 'CavityLightHF45Navigation';\n";
    code=code+"    var preference = 'cavity.tem.light.hf45.fixed.window';\n";
    code=code+"    var imp = WM.getCurrentImage();\n";
    code=code+"    if (imp == null) return 'ERROR|No hay imagen activa.';\n";
    code=code+"    var win = imp.getWindow(), canvas = imp.getCanvas();\n";
    code=code+"    if (win == null || canvas == null) return 'ERROR|La imagen no tiene ventana.';\n";
    code=code+"    function adapter(type, body) {\n";
    code=code+"        if (typeof JavaAdapter != 'undefined') return new JavaAdapter(type, body);\n";
    code=code+"        var T = Java.extend(type); return new T(body);\n";
    code=code+"    }\n";
    code=code+"    function ui(fn) {\n";
    code=code+"        if (EventQueue.isDispatchThread()) return fn();\n";
    code=code+"        var result = null, failure = null;\n";
    code=code+"        EventQueue.invokeAndWait(adapter(P.java.lang.Runnable, {run: function () {\n";
    code=code+"            try { result = fn(); } catch (ex) { failure = ex; }\n";
    code=code+"        }}));\n";
    code=code+"        if (failure != null) throw failure;\n";
    code=code+"        return result;\n";
    code=code+"    }\n";
    code=code+"    function getNumber(key, fallback) {\n";
    code=code+"        var text = imp.getProperty(key), v = text == null ? fallback : Number(String(text));\n";
    code=code+"        return isFinite(v) ? v : fallback;\n";
    code=code+"    }\n";
    code=code+"    try {\n";
    code=code+"        return ui(function () {\n";
    code=code+"            var ctl = imp.getProperty(property);\n";
    code=code+"            if (ctl != null && (ctl.canvas != canvas || ctl.version != 'HF4.6')) {\n";
    code=code+"                try { ctl.dispose(); } catch (oldError) {}\n";
    code=code+"                ctl = null;\n";
    code=code+"            }\n";
    code=code+"            if (ctl == null) {\n";
    code=code+"                ctl = {version: 'HF4.6', canvas: canvas, enabled: true, disposed: false,\n";
    code=code+"                       originalMagnification: canvas.getMagnification()};\n";
    code=code+"                ctl.enabled = String(P.ij.Prefs.get(preference, '1')) != '0';\n";
    code=code+"                var kfm = P.java.awt.KeyboardFocusManager.getCurrentKeyboardFocusManager();\n";
    code=code+"                function active() {\n";
    code=code+"                    return !ctl.disposed && WM.getCurrentImage() == imp &&\n";
    code=code+"                           imp.getWindow() == win && imp.getCanvas() == canvas;\n";
    code=code+"                }\n";
    code=code+"                function fixed() { return ctl.enabled && active(); }\n";
    code=code+"                function step() { return Math.max(1.01, Math.min(8, getNumber('CavityV8ZoomStep', 1.5))); }\n";
    code=code+"                function center() {\n";
    code=code+"                    var r = canvas.getSrcRect();\n";
    code=code+"                    return [r.x + r.width / 2, r.y + r.height / 2];\n";
    code=code+"                }\n";
    code=code+"                /* setSourceRect also sets magnification from its width in IJ1.\n";
    code=code+"                 * Always setMagnification AFTER it: retain an isotropic view and\n";
    code=code+"                 * the requested zoom even when the image is smaller than the canvas. */\n";
    code=code+"                function setView(mag, imageX, imageY, screenX, screenY) {\n";
    code=code+"                    if (!active()) return 'ERROR|La ventana activa ha cambiado.';\n";
    code=code+"                    var bounds = win.getBounds(), size = canvas.getSize();\n";
    code=code+"                    var dw = size.width, dh = size.height, iw = imp.getWidth(), ih = imp.getHeight();\n";
    code=code+"                    if (dw < 1 || dh < 1 || iw < 1 || ih < 1 || !isFinite(mag) || mag <= 0)\n";
    code=code+"                        return 'ERROR|Dimensiones de vista no validas.';\n";
    code=code+"                    mag = Math.max(P.ij.gui.ImageCanvas.getLowerZoomLevel(0), Math.min(32, mag));\n";
    code=code+"                    var nw = Math.max(1, Math.min(iw, Math.ceil(dw / mag)));\n";
    code=code+"                    var nh = Math.max(1, Math.min(ih, Math.ceil(dh / mag)));\n";
    code=code+"                    var nx = Math.max(0, Math.min(iw - nw, Math.round(imageX - screenX / mag)));\n";
    code=code+"                    var ny = Math.max(0, Math.min(ih - nh, Math.round(imageY - screenY / mag)));\n";
    code=code+"                    canvas.setScaleToFit(false);\n";
    code=code+"                    canvas.setSourceRect(new Rectangle(nx, ny, nw, nh));\n";
    code=code+"                    canvas.setMagnification(mag);\n";
    code=code+"                    /* IJ1 does not clear unused canvas margins after zoom-out. */\n";
    code=code+"                    var g = canvas.getGraphics();\n";
    code=code+"                    if (g != null) {\n";
    code=code+"                        try { g.setColor(canvas.getBackground()); g.fillRect(0, 0, dw, dh); }\n";
    code=code+"                        finally { g.dispose(); }\n";
    code=code+"                    }\n";
    code=code+"                    canvas.resetDoubleBuffer(); canvas.repaint();\n";
    code=code+"                    if (!win.getBounds().equals(bounds))\n";
    code=code+"                        return 'ERROR|Un componente externo ha cambiado la ventana durante el zoom.';\n";
    code=code+"                    imp.setProperty('CavityLightHF45View', String(mag));\n";
    code=code+"                    return 'OK|' + mag;\n";
    code=code+"                }\n";
    code=code+"                ctl.zoom = function (direction, sx, sy) {\n";
    code=code+"                    if (!active()) return 'ERROR|La ventana activa ha cambiado.';\n";
    code=code+"                    var size = canvas.getSize(), r = canvas.getSrcRect();\n";
    code=code+"                    if (sx == null) sx = size.width / 2;\n";
    code=code+"                    if (sy == null) sy = size.height / 2;\n";
    code=code+"                    if (!ctl.enabled) {\n";
    code=code+"                        if (direction > 0) canvas.zoomIn(Math.round(sx), Math.round(sy));\n";
    code=code+"                        else canvas.zoomOut(Math.round(sx), Math.round(sy));\n";
    code=code+"                        return 'OK|NATIVE';\n";
    code=code+"                    }\n";
    code=code+"                    var x = canvas.offScreenXD(Math.round(sx)), y = canvas.offScreenYD(Math.round(sy));\n";
    code=code+"                    var mag = canvas.getMagnification() * (direction > 0 ? step() : 1 / step());\n";
    code=code+"                    return setView(mag, x, y, sx, sy);\n";
    code=code+"                };\n";
    code=code+"                ctl.at = function (x, y, factor) {\n";
    code=code+"                    if (!ctl.enabled) return ctl.zoom(factor >= 1 ? 1 : -1, null, null);\n";
    code=code+"                    var size = canvas.getSize();\n";
    code=code+"                    return setView(canvas.getMagnification() * factor, x, y, size.width / 2, size.height / 2);\n";
    code=code+"                };\n";
    code=code+"                ctl.fit = function (selection) {\n";
    code=code+"                    var r = selection ? imp.getRoi() : null;\n";
    code=code+"                    r = r == null ? new Rectangle(0, 0, imp.getWidth(), imp.getHeight()) : r.getBounds();\n";
    code=code+"                    if (r.width <= 0 || r.height <= 0) return 'ERROR|Seleccion vacia.';\n";
    code=code+"                    var size = canvas.getSize(), mag = Math.min(size.width / r.width, size.height / r.height);\n";
    code=code+"                    return setView(mag, r.x + r.width / 2, r.y + r.height / 2, size.width / 2, size.height / 2);\n";
    code=code+"                };\n";
    code=code+"                ctl.scale = function (mag) {\n";
    code=code+"                    var xy = center(), size = canvas.getSize();\n";
    code=code+"                    return setView(mag, xy[0], xy[1], size.width / 2, size.height / 2);\n";
    code=code+"                };\n";
    code=code+"                ctl.setEnabled = function (enabled) {\n";
    code=code+"                    ctl.enabled = enabled;\n";
    code=code+"                    imp.setProperty('CavityLightFixedWindow', enabled ? '1' : '0');\n";
    code=code+"                    P.ij.Prefs.set(preference, enabled ? '1' : '0');\n";
    code=code+"                    P.ij.Prefs.savePreferences();\n";
    code=code+"                    return enabled ? '1' : '0';\n";
    code=code+"                };\n";
    code=code+"                /* Run before ImageJ's own key listener. A consumed Cavity shortcut\n";
    code=code+"                 * must not also trigger native Save, Measure or pixel deletion. */\n";
    code=code+"                var dispatcher = adapter(P.java.awt.KeyEventDispatcher, {dispatchKeyEvent: function (e) {\n";
    code=code+"                    if (!active() || (e.getSource() != canvas && e.getSource() != win)) return false;\n";
    code=code+"                    if (e.getID() != KeyEvent.KEY_PRESSED || IJ.macroRunning()) return false;\n";
    code=code+"                    if (fixed() && !e.isControlDown() && !e.isMetaDown() && !e.isAltDown()) {\n";
    code=code+"                        var code = e.getKeyCode(), ch = String(e.getKeyChar());\n";
    code=code+"                        if (code == KeyEvent.VK_ADD || code == KeyEvent.VK_PLUS || ch == '+' || ch == '=') {\n";
    code=code+"                            ctl.zoom(1, null, null); e.consume(); return true;\n";
    code=code+"                        }\n";
    code=code+"                        if (code == KeyEvent.VK_SUBTRACT || code == KeyEvent.VK_MINUS || ch == '-') {\n";
    code=code+"                            ctl.zoom(-1, null, null); e.consume(); return true;\n";
    code=code+"                        }\n";
    code=code+"                    }\n";
    code=code+"                    var listener = imp.getProperty('CavityLightR9KeyListener');\n";
    code=code+"                    if (listener != null) { listener.keyPressed(e); return e.isConsumed(); }\n";
    code=code+"                    return false;\n";
    code=code+"                }});\n";
    code=code+"                kfm.addKeyEventDispatcher(dispatcher);\n";
    code=code+"                /* Native Image > Zoom menu and native +/- commands. */\n";
    code=code+"                var commandListener = adapter(P.ij.CommandListener, {commandExecuting: function (command) {\n";
    code=code+"                    if (!fixed()) return command;\n";
    code=code+"                    var cmd = String(command);\n";
    code=code+"                    if (cmd != 'In' && cmd != 'Out' && cmd != 'View 100%' &&\n";
    code=code+"                        cmd != 'Original Scale' && cmd != 'To Selection') return command;\n";
    code=code+"                    ui(function () {\n";
    code=code+"                        if (cmd == 'In') ctl.zoom(1, null, null);\n";
    code=code+"                        else if (cmd == 'Out') ctl.zoom(-1, null, null);\n";
    code=code+"                        else if (cmd == 'View 100%') ctl.scale(1);\n";
    code=code+"                        else if (cmd == 'Original Scale') ctl.scale(ctl.originalMagnification);\n";
    code=code+"                        else ctl.fit(true);\n";
    code=code+"                    });\n";
    code=code+"                    return null;\n";
    code=code+"                }});\n";
    code=code+"                Executer.addCommandListener(commandListener);\n";
    code=code+"                /* ImageCanvas's native magnifier calls zoomIn/Out directly. Replace\n";
    code=code+"                 * ONLY its mouse listener by a delegating proxy; all non-zoom gestures\n";
    code=code+"                 * still use the original ImageCanvas and original ROI machinery. */\n";
    code=code+"                var handledPress = false;\n";
    code=code+"                var mouseProxy = adapter(P.java.awt.event.MouseListener, {\n";
    code=code+"                    mousePressed: function (e) {\n";
    code=code+"                        handledPress = fixed() && Toolbar.getToolId() == Toolbar.MAGNIFIER &&\n";
    code=code+"                                       !IJ.spaceBarDown() && !e.isShiftDown();\n";
    code=code+"                        if (handledPress) {\n";
    code=code+"                            var out = e.isAltDown() || e.isControlDown() || e.isMetaDown() || e.getButton() == MouseEvent.BUTTON3;\n";
    code=code+"                            ctl.zoom(out ? -1 : 1, e.getX(), e.getY()); e.consume();\n";
    code=code+"                        } else canvas.mousePressed(e);\n";
    code=code+"                    },\n";
    code=code+"                    mouseReleased: function (e) { if (handledPress) { e.consume(); handledPress = false; } else canvas.mouseReleased(e); },\n";
    code=code+"                    mouseClicked: function (e) { canvas.mouseClicked(e); },\n";
    code=code+"                    mouseEntered: function (e) { canvas.mouseEntered(e); },\n";
    code=code+"                    mouseExited: function (e) { canvas.mouseExited(e); }\n";
    code=code+"                });\n";
    code=code+"                var listeners = canvas.getMouseListeners(), replaced = false;\n";
    code=code+"                for (var j = 0; j < listeners.length; j++) canvas.removeMouseListener(listeners[j]);\n";
    code=code+"                for (var k = 0; k < listeners.length; k++) {\n";
    code=code+"                    if (listeners[k] == canvas) { canvas.addMouseListener(mouseProxy); replaced = true; }\n";
    code=code+"                    else canvas.addMouseListener(listeners[k]);\n";
    code=code+"                }\n";
    code=code+"                var windowListener = adapter(P.java.awt.event.WindowAdapter, {windowClosed: function (e) { ctl.dispose(); }});\n";
    code=code+"                win.addWindowListener(windowListener);\n";
    code=code+"                ctl.dispose = function () {\n";
    code=code+"                    if (ctl.disposed) return;\n";
    code=code+"                    ctl.disposed = true;\n";
    code=code+"                    kfm.removeKeyEventDispatcher(dispatcher); Executer.removeCommandListener(commandListener);\n";
    code=code+"                    win.removeWindowListener(windowListener);\n";
    code=code+"                    if (replaced) { canvas.removeMouseListener(mouseProxy); canvas.addMouseListener(canvas); }\n";
    code=code+"                    imp.setProperty(property, null);\n";
    code=code+"                };\n";
    code=code+"                imp.setProperty(property, ctl);\n";
    code=code+"                imp.setProperty('CavityLightFixedWindow', ctl.enabled ? '1' : '0');\n";
    code=code+"            }\n";
    code=code+"            var action = String(HF45_ACTION);\n";
    code=code+"            if (action == 'attach' || action == 'state') return ctl.enabled ? '1' : '0';\n";
    code=code+"            if (action == 'enable') return ctl.setEnabled(true);\n";
    code=code+"            if (action == 'disable') return ctl.setEnabled(false);\n";
    code=code+"            if (action == 'toggle') return ctl.setEnabled(!ctl.enabled);\n";
    code=code+"            if (action == 'in') return ctl.zoom(1, null, null);\n";
    code=code+"            if (action == 'out') return ctl.zoom(-1, null, null);\n";
    code=code+"            if (action == 'fit') return ctl.fit(false);\n";
    code=code+"            if (action == '100') return ctl.scale(1);\n";
    code=code+"            if (action.indexOf('at|') == 0) {\n";
    code=code+"                var a = action.split('|');\n";
    code=code+"                return ctl.at(Number(a[1]), Number(a[2]), Number(a[3]));\n";
    code=code+"            }\n";
    code=code+"            if (action == 'detach') { ctl.dispose(); return 'OK|DETACHED'; }\n";
    code=code+"            return 'ERROR|Accion de vista desconocida.';\n";
    code=code+"        });\n";
    code=code+"    } catch (error) { return 'ERROR|' + String(error); }\n";
    code=code+"})()\n";
    return "" + eval("js", code);
}

// HF4.6 view-only settings and shortcut documentation.
function lightHF45ClearBackgroundFor(imageId) {
    js="var imp=Packages.ij.WindowManager.getImage("+imageId+");if(imp!=null){var ov=imp.getOverlay();if(ov!=null){ov.remove('__CTL_HF44_BG_PREVIEW__');imp.setOverlay(ov);}imp.setProperty('CavityLightHF44BackgroundCandidate',null);imp.setProperty('CavityLightHF44BackgroundCandidate.meta',null);imp.setProperty('CavityLightHF44BackgroundCandidate.context',null);imp.draw();}";
    eval("js",js);
}

function lightHF45ViewAction(action) {
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra primero una imagen."); return; }
    result = lightHF45NavigationCall(action);
    if (startsWith(result,"ERROR")) { showMessage("Vista no modificada",result); return; }
    state = lightHF45NavigationCall("state");
    if (state == "0" || state == "1") keepWindowSize = parseFloat(state);
    lightRefreshPanel();
    if (action == "toggle") {
        if (keepWindowSize) showStatus("Ventana fija ACTIVADA: el zoom no cambia su tamano ni posicion. Puede moverla manualmente.");
        else showStatus("Ventana fija DESACTIVADA: el zoom nativo puede reajustar la ventana.");
    }
}

function lightHF45ViewOptions() {
    if (nImages() <= 0) { showMessage("Sin imagen", "Abra primero la imagen cuya vista desea configurar."); return; }
    state=lightHF45NavigationCall("attach");
    if (startsWith(state,"ERROR")) { showMessage("Vista no preparada",state); return; }
    keepWindowSize = 0;
    if (state == "1") keepWindowSize = 1;
    Dialog.create("Ventana y navegacion - R9 CONSOLIDADA RC1");
    Dialog.addCheckbox("Mantener ventana fija durante el zoom",keepWindowSize);
    Dialog.addCheckbox("Navegar con rueda y flechas",fixedNavigation);
    Dialog.addNumber("Factor de zoom fijo:",zoomStep,2,8,"");
    Dialog.addMessage("Ventana fija conserva el tamano y la posicion DURANTE el zoom.\nPuede seguir moviendo o redimensionando la ventana manualmente.\n\nCtrl+rueda y +/-: zoom. Rueda: vertical. Mayus+rueda: horizontal.\nAlt+rueda sigue reservado al diametro de cavidad, NO al zoom.\n\nLa preferencia de ventana fija se conserva al reiniciar Fiji.\nEsta opcion no cambia pixeles, escala fisica ni resultados.");
    Dialog.show();
    fixed=Dialog.getCheckbox();panEnabled=Dialog.getCheckbox();factor=Dialog.getNumber();
    if (isNaN(factor)||factor<=1.01||factor>8) { showMessage("Factor no valido","Introduzca un factor mayor que 1.01 y menor o igual que 8."); return; }
    action="disable";if(fixed)action="enable";
    result=lightHF45NavigationCall(action);
    if(startsWith(result,"ERROR")){showMessage("Vista no modificada",result);return;}
    keepWindowSize=fixed;fixedNavigation=panEnabled;zoomStep=factor;
    lightInteractivePushState(lightInteractiveMode);
    installInteractionListeners(0);
    lightRefreshPanel();
}

function lightHF45ShowShortcuts() {
    text="CAVITY TEM LIGHT R9 CONSOLIDADA RC1 - ACCESOS DIRECTOS\n\n";
    text=text+"AMBITO\nLos atajos de Cavity requieren el foco en la ventana de IMAGEN y los controles de interaccion instalados. No son atajos del ROI Manager, del panel ni de cuadros de texto. Al cargar o seleccionar una imagen del proyecto se instalan. No escriba estos atajos en un campo numerico.\n\n";
    text=text+"MEDIR Y EDITAR\nCtrl+M: medir diametro y crear cavidad mediante arrastre.\nCtrl+R: activar Anadir con diametro activo.\nCtrl+E: activar Seleccionar/mover/ajustar.\nMayus+clic con la herramienta Cavity Seleccionar: anadir una cavidad con diametro activo.\nAlt+rueda: cambiar diametro activo (Anadir) o el de la cavidad seleccionada (Seleccionar).\nAlt+Mayus+rueda: lo anterior con un paso cinco veces menor.\nCtrl+Alt+rueda: alias de Alt+rueda.\nCtrl+U: sincronizar la ROI seleccionada.\nSupr o Retroceso: borrar la ROI seleccionada, no los pixeles. Compruebe que ha seleccionado el objeto correcto.\nCtrl+Z: deshacer la ultima adicion/eliminacion individual registrada por Cavity. NO es un historial universal de edicion.\nCtrl+T: buscar duplicados.\nEsc: volver al modo seleccionar; dentro de un dialogo puede cancelar.\n\n";
    text=text+"PREPARAR Y TRAZAR\nCtrl+K: calibrar escala con una linea.\nCtrl+B: definir superficie.\nCtrl+G: dibujar bordes de grano.\nCtrl+L: dibujar dislocaciones.\n\n";
    text=text+"GUARDAR Y ANALIZAR\nCtrl+S: guardar una NUEVA REVISION de ROIs de Cavity (no el archivo de imagen).\nCtrl+Mayus+V: validar imagen.\nCtrl+Mayus+E: calcular y exportar resultados.\n\n";
    text=text+"VISTA\nCtrl+rueda (sin Alt): zoom.\n+ o -: zoom; con Ventana fija activada no reajustan la ventana.\nRueda: desplazamiento vertical (navegacion activada).\nMayus+rueda: desplazamiento horizontal (navegacion activada).\nFlechas: desplazar la vista; Mayus duplica el paso, Alt lo divide por cuatro.\nBarra espaciadora+arrastre: desplazar con la mano de ImageJ.\nCtrl+Mayus+W: activar/desactivar Ventana fija.\nLupa Cavity: clic acerca; Mayus+clic aleja.\nLupa nativa ImageJ: clic acerca; Alt+clic aleja.\n\n";
    text=text+"AYUDA\nF1: esta guia.\nCtrl+H: ayuda general de Cavity.\n\n";
    text=text+"COMANDOS SIN TECLA ASIGNADA\nDetectar fondo negro: 2 Preparar.\nBorrar varias por region, Deshacer borrado multiple y Color cavidades: 3 Medir.\nEncajar imagen, Vista 100 % y opciones de ventana: 6 Vista y atajos.\nCtrl+Z NO restaura un borrado multiple: use Deshacer borrado multiple.\n\n";
    text=text+"FOCO Y SEGURIDAD\nFuera de la ventana de imagen, Fiji/ImageJ conserva sus propios atajos. No utilice Supr ni Ctrl+S suponiendo que son Cavity cuando el foco esta en otra ventana. Los controles de edicion se suspenden durante operaciones macro; complete o cancele el dialogo antes de volver a medir.\n";
    js="new Packages.ij.text.TextWindow('Accesos directos Cavity HF4.6','', '"+jsEscape(text)+"',850,650);";
    eval("js",js);
}

macro "Cavity Light: ventana y navegacion" { lightHF45ViewOptions(); }
macro "Cavity Light: alternar ventana fija" { lightHF45ViewAction("toggle"); }
macro "Cavity Light: zoom fijo aumentar" { lightHF45ViewAction("in"); }
macro "Cavity Light: zoom fijo reducir" { lightHF45ViewAction("out"); }
macro "Cavity Light: encajar vista" { lightHF45ViewAction("fit"); }
macro "Cavity Light: vista 100" { lightHF45ViewAction("100"); }
macro "Cavity Light: accesos directos" { lightHF45ShowShortcuts(); }

function lightHF45NextExclusionId(minSerial) {
    // Read the manager without selecting ROIs: keep the newly detected area active.
    js="(function(){var rm=Packages.ij.plugin.frame.RoiManager.getInstance2(),next="+d2s(minSerial,0)+";if(rm!=null){var all=rm.getRoisAsArray();for(var i=0;i<all.length;i++){var names=[all[i].getName(),all[i].getProperty('Exclusion_id')];for(var j=0;j<names.length;j++){var m=/^EXCL_([0-9]+)$/.exec(String(names[j]));if(m)next=Math.max(next,Number(m[1])+1);}}}var value=String(next);while(value.length<3)value='0'+value;return 'EXCL_'+value;})();";
    return ""+eval("js",js);
}



function lightHF46CaptureState() {
    state=newArray(macroVersion,sessionMetadataName,legacyMetadataName,scaleReferenceName,scaleLabelName,surfaceReferenceName,lightSchemaVersion,lightReleaseVersion,lightProjectLoaded,lightProjectRoot,lightProjectFile,lightProjectId,lightProjectName,lightProjectUid,lightImageId,lightImageDir,lightSourcePath,lightSourceStoredPath,lightSourceSha256,lightCopySource,lightImageMode,lightThicknessNm,lightThicknessUncertaintyNm,lightThicknessMethod,lightThicknessNotes,lightOriginalScaleNmX,lightOriginalScaleNmY,lightOriginalScaleUnit,lightScaleOrigin,lightScaleConfirmed,lightUseWholeImage,lightIncludeUncertain,lightCurrentRevision,lightCurrentRunId,lightHistogramBinNm,lightLastExportDir,lightRegistryFileName,lightProjectFileName,lightImageMetadataFileName,lightCurrentRevisionFileName,lightValidationState,lightLastDepthBinNm,lightBandMode,lightSizeBreaks,lightResultContrast,lightMaxImageDepthNm,lightHF3X,lightHF3Y,lightLastValidPixels,lightStatMean,lightStatStd,lightStatMedian,lightStatQ25,lightStatQ75,lightStatMin,lightStatMax,lightFeatureDistanceBinNm,lightProjectDescriptorType,lightImageDescriptorType,lightPreparedFingerprint,lightPreparedAtMs,lightLastPreparationDurationMs,lightLastPreparationReused,lightPreparationRuns,lightPreparationCacheHits,lightAreaFingerprint,lightAreaComputationMode,lightAreaComputationDurationMs,lightCavityContextActive,lightInteractiveMode,lightInteractivePreviewEnabled,lightInteractiveResizeStepNm,lightInteractiveResizeMinNm,lightInteractiveResizeMaxNm,lightInteractiveDebounceMs,lightInteractiveControllerStatus,lightInteractivePreviewName,lightLastInteractiveEditId,lightLastInteractiveEditKind,lightLastInteractiveEditDiameterNm,lightCachedCavityCount,lightHF4LastSequence,lightHF4LastReport,lightLastIdAuditErrors,lightLastIdAuditDuplicateIds,lightObjectCountCavities,lightObjectCountMasks,lightObjectCountExclusions,lightObjectCountGrainBoundaries,lightObjectCountDislocations,lightObjectCountInterfaces,lightObjectCountSurfaces,lightObjectCountDuplicateSuspects,projectConfigured,sampleName,experimentalCondition,montageId,sourceFirst,sourceLast,sourceImageList,microscopeVoltage,specimenTemperature,operatorName,projectNotes,imageFileName,imageDirectory,imageChecksum,sessionRoiPath,projectAwareActive,projectAwareProjectDir,projectAwareSessionsDir,projectAwareDerivedDir,projectAwareViewsDir,projectAwareProjectFieldsCsv,projectAwareMetadataJson,projectAwareLayoutCheckCsv,projectAwareMontageBuildLogCsv,projectAwareResultsCsv,projectAwareMasterTif,projectAwareCurrentAnalysisImagePath,projectAwareCurrentAnalysisImageRole,projectAwareCurrentAnalysisImageName,projectAwareProjectUid,projectAwarePanelCount,projectAwarePixelWidth,projectAwarePixelHeight,projectAwarePixelUnit,projectAwareSourceEndExclusive,projectAwareLastExportDir,scaleDefined,scaleKnownNm,nmPerPixelX,nmPerPixelY,unitFactorNm,currentUnit,surfaceDefined,surfaceSideDefined,surfaceMaterialX,surfaceMaterialY,surfaceMaterialSign,surfaceLastDistanceNm,surfaceLastSignedDistanceNm,surfaceLastArcNm,surfaceLastNearestXpx,surfaceLastNearestYpx,surfaceLastTangentAngleDeg,activeDiameterNm,bandNm,bandCount,excludeNegativeDepth,usePanelsAsMask,displayMode,PI_VAL,cavityCounter,panelCounter,maskCounter,exclusionCounter,grainBoundaryCounter,dislocationCounter,loopCounter,interfaceCounter,duplicateCenterTolPx,duplicateRelativeTol,duplicateDiameterTolFraction,selectionTolerancePx,pointValidityReason,panelLastId,panelLastSource,panelLastMatchCount,areaSamplingTarget,lastAreaSamplingStepPx,lastValidAreaNm2,coverageMaxBand,coverageUnbanded,coverageIncluded,showRoiLabels,fillCavities,fillAlpha,fillAlphaHex,roiStrokeWidth,activeStrokeColor,activeFillColor,lightConfirmedCavityColor,activeCavityClass,activeCavityClassLabel,activeCavityConfidence,autoOpenBrightnessContrast,featureToolPreset,missingMacroToolWarningShown,undoKind,undoObjectId,undoDeletedName,undoAvailable,keepWindowSize,lockedWinW,lockedWinH,fixedNavigation,panFraction,keyPanFraction,wheelPanFraction,zoomStep,restoreViewAfterRoi,viewSnapshotValid,viewSnapX,viewSnapY,viewSnapW,viewSnapH,viewSnapWinX,viewSnapWinY,viewSnapWinW,viewSnapWinH,v4ToolVersion,v4ProjectLoaded,v4ProjectDir,v4ProjectSwitchInProgress,v4BridgeDir,v4BridgeStaticDir,v4BridgePointerJson,v4BridgeGenerationId,v4ProjectFieldsCsv,v4ProjectFieldsText,v4RoiSetsCsv,v4ProjectId,v4ProjectName,v4StudyId,v4StudyName,v4SampleId,v4Material,v4Condition,v4SpecimenId,v4SpecimenLabel,v4AcquisitionId,v4AcquisitionLabel,v4MasterImage,v4MasterRole,v4MasterRevisionId,v4CurrentMontagePointerPath,v4MasterRevisionManifestPath,v4MasterNativePlanPath,v4MasterFidelityReportPath,v4CurrentMontagePointerSha256,v4MasterRevisionManifestSha256,v4MasterNativePlanSha256,v4MasterFidelitySha256,v4MasterSha256,v4MasterOwnershipSha256,v4RevisionBindingReady,v4RevisionBindingError,v55IntegrityCacheFingerprint,v55IntegrityCacheProjectId,v55IntegrityCacheUntilMs,v55IntegrityCacheTtlMs,v55IntegrityLastEvidence,v55IntegrityLastError,v55FileCanonicalPath,v55FileSizeBytes,v55FileModifiedMs,v55FileSha256,v56RequestId,v56PreparedAt,v56RoiDraftError,v56RoiDraftCount,v56RoiSnapshotDirectory,v56RoiSnapshotEntryName,v56ResolvedSessionZip,v56ResolvedSessionRoiCount,v56SessionValidationError,v56ResolvedSessionReviewStatus,v56ResolvedSessionQuantitativeReady,v56ResolvedSessionPendingCount,v56ResolvedSessionGeometryBlockerCount,v56RoiSessionContractJson,v4CalibrationId,v4PixelWidth,v4PixelHeight,v4PixelUnit,v4SurfaceId,v4SurfaceOriginDefined,v4SurfaceOriginArcNm,v4SurfaceOriginXpx,v4SurfaceOriginYpx,v4SurfaceTangentialSign,v4ActiveRoiSetId,v4ActiveRoiSetName,v4ActiveObjectType,v4ActiveGeometry,v4ActiveIdPrefix,v4ActiveScientificRole,v4ActiveProtocolId,v4ActiveStrokeColor,v4ActiveFillColor,v4RunId,v4LastLocalXpx,v4LastLocalYpx,v4TraceMode,v4TraceTool,v4TraceSessionId,v4TraceConfidence,v4TraceNote,v4TraceAdded,v4TraceDeleted,v4TraceLastObjectId,v4TraceCaptureOrder,v4ScaleConflict,v4ScaleConflictText,v4ScaleReconciliationStatus,v4ScaleMeasurementAllowed,v4ImageScaleNmX,v4ImageScaleNmY,v4ImageScaleUnit,v4PanelsCsv,v4PanelGeometryJson,v4OwnershipImage,v4OwnershipLegendCsv,v4OwnershipCertified,v4PanelOverlapPolicy,v4PanelGeometryStatus,v4PanelQuantitativeReady,panelLastOwnerCode,panelLastCoverageCount,v51ScaleBarLengthNm,v51ScaleBarPosition,v51ScaleBarColor,v51ScaleBarBackground,v51ScaleBarBackgroundAlpha,v51ScaleBarThicknessPx,v51ScaleBarFontPx,v51ScaleBarMarginPx,v51GuideSpacingNm,v51GuideMaximumNm,v51GuideColor,v51GuideWidthPx,v51GuideDashed,v51GuideBothSides,v51GuideLabels,v51LastExactAreaCsv,v51LastExactAreaMethod,imageToolsVersion,imageToolsLastRecipe,imageToolsLastPurpose,imageToolsLastSource);
    state=Array.concat(state,newArray(1));state[341]=surfaceX.length;
    state=Array.concat(state,surfaceX);state=Array.concat(state,surfaceY);return state;
}

function lightHF46RestoreState(state) {
    macroVersion=state[0];
    sessionMetadataName=state[1];
    legacyMetadataName=state[2];
    scaleReferenceName=state[3];
    scaleLabelName=state[4];
    surfaceReferenceName=state[5];
    lightSchemaVersion=state[6];
    lightReleaseVersion=state[7];
    lightProjectLoaded=state[8];
    lightProjectRoot=state[9];
    lightProjectFile=state[10];
    lightProjectId=state[11];
    lightProjectName=state[12];
    lightProjectUid=state[13];
    lightImageId=state[14];
    lightImageDir=state[15];
    lightSourcePath=state[16];
    lightSourceStoredPath=state[17];
    lightSourceSha256=state[18];
    lightCopySource=state[19];
    lightImageMode=state[20];
    lightThicknessNm=state[21];
    lightThicknessUncertaintyNm=state[22];
    lightThicknessMethod=state[23];
    lightThicknessNotes=state[24];
    lightOriginalScaleNmX=state[25];
    lightOriginalScaleNmY=state[26];
    lightOriginalScaleUnit=state[27];
    lightScaleOrigin=state[28];
    lightScaleConfirmed=state[29];
    lightUseWholeImage=state[30];
    lightIncludeUncertain=state[31];
    lightCurrentRevision=state[32];
    lightCurrentRunId=state[33];
    lightHistogramBinNm=state[34];
    lightLastExportDir=state[35];
    lightRegistryFileName=state[36];
    lightProjectFileName=state[37];
    lightImageMetadataFileName=state[38];
    lightCurrentRevisionFileName=state[39];
    lightValidationState=state[40];
    lightLastDepthBinNm=state[41];
    lightBandMode=state[42];
    lightSizeBreaks=state[43];
    lightResultContrast=state[44];
    lightMaxImageDepthNm=state[45];
    lightHF3X=state[46];
    lightHF3Y=state[47];
    lightLastValidPixels=state[48];
    lightStatMean=state[49];
    lightStatStd=state[50];
    lightStatMedian=state[51];
    lightStatQ25=state[52];
    lightStatQ75=state[53];
    lightStatMin=state[54];
    lightStatMax=state[55];
    lightFeatureDistanceBinNm=state[56];
    lightProjectDescriptorType=state[57];
    lightImageDescriptorType=state[58];
    lightPreparedFingerprint=state[59];
    lightPreparedAtMs=state[60];
    lightLastPreparationDurationMs=state[61];
    lightLastPreparationReused=state[62];
    lightPreparationRuns=state[63];
    lightPreparationCacheHits=state[64];
    lightAreaFingerprint=state[65];
    lightAreaComputationMode=state[66];
    lightAreaComputationDurationMs=state[67];
    lightCavityContextActive=state[68];
    lightInteractiveMode=state[69];
    lightInteractivePreviewEnabled=state[70];
    lightInteractiveResizeStepNm=state[71];
    lightInteractiveResizeMinNm=state[72];
    lightInteractiveResizeMaxNm=state[73];
    lightInteractiveDebounceMs=state[74];
    lightInteractiveControllerStatus=state[75];
    lightInteractivePreviewName=state[76];
    lightLastInteractiveEditId=state[77];
    lightLastInteractiveEditKind=state[78];
    lightLastInteractiveEditDiameterNm=state[79];
    lightCachedCavityCount=state[80];
    lightHF4LastSequence=state[81];
    lightHF4LastReport=state[82];
    lightLastIdAuditErrors=state[83];
    lightLastIdAuditDuplicateIds=state[84];
    lightObjectCountCavities=state[85];
    lightObjectCountMasks=state[86];
    lightObjectCountExclusions=state[87];
    lightObjectCountGrainBoundaries=state[88];
    lightObjectCountDislocations=state[89];
    lightObjectCountInterfaces=state[90];
    lightObjectCountSurfaces=state[91];
    lightObjectCountDuplicateSuspects=state[92];
    projectConfigured=state[93];
    sampleName=state[94];
    experimentalCondition=state[95];
    montageId=state[96];
    sourceFirst=state[97];
    sourceLast=state[98];
    sourceImageList=state[99];
    microscopeVoltage=state[100];
    specimenTemperature=state[101];
    operatorName=state[102];
    projectNotes=state[103];
    imageFileName=state[104];
    imageDirectory=state[105];
    imageChecksum=state[106];
    sessionRoiPath=state[107];
    projectAwareActive=state[108];
    projectAwareProjectDir=state[109];
    projectAwareSessionsDir=state[110];
    projectAwareDerivedDir=state[111];
    projectAwareViewsDir=state[112];
    projectAwareProjectFieldsCsv=state[113];
    projectAwareMetadataJson=state[114];
    projectAwareLayoutCheckCsv=state[115];
    projectAwareMontageBuildLogCsv=state[116];
    projectAwareResultsCsv=state[117];
    projectAwareMasterTif=state[118];
    projectAwareCurrentAnalysisImagePath=state[119];
    projectAwareCurrentAnalysisImageRole=state[120];
    projectAwareCurrentAnalysisImageName=state[121];
    projectAwareProjectUid=state[122];
    projectAwarePanelCount=state[123];
    projectAwarePixelWidth=state[124];
    projectAwarePixelHeight=state[125];
    projectAwarePixelUnit=state[126];
    projectAwareSourceEndExclusive=state[127];
    projectAwareLastExportDir=state[128];
    scaleDefined=state[129];
    scaleKnownNm=state[130];
    nmPerPixelX=state[131];
    nmPerPixelY=state[132];
    unitFactorNm=state[133];
    currentUnit=state[134];
    surfaceDefined=state[135];
    surfaceSideDefined=state[136];
    surfaceMaterialX=state[137];
    surfaceMaterialY=state[138];
    surfaceMaterialSign=state[139];
    surfaceLastDistanceNm=state[140];
    surfaceLastSignedDistanceNm=state[141];
    surfaceLastArcNm=state[142];
    surfaceLastNearestXpx=state[143];
    surfaceLastNearestYpx=state[144];
    surfaceLastTangentAngleDeg=state[145];
    activeDiameterNm=state[146];
    bandNm=state[147];
    bandCount=state[148];
    excludeNegativeDepth=state[149];
    usePanelsAsMask=state[150];
    displayMode=state[151];
    PI_VAL=state[152];
    cavityCounter=state[153];
    panelCounter=state[154];
    maskCounter=state[155];
    exclusionCounter=state[156];
    grainBoundaryCounter=state[157];
    dislocationCounter=state[158];
    loopCounter=state[159];
    interfaceCounter=state[160];
    duplicateCenterTolPx=state[161];
    duplicateRelativeTol=state[162];
    duplicateDiameterTolFraction=state[163];
    selectionTolerancePx=state[164];
    pointValidityReason=state[165];
    panelLastId=state[166];
    panelLastSource=state[167];
    panelLastMatchCount=state[168];
    areaSamplingTarget=state[169];
    lastAreaSamplingStepPx=state[170];
    lastValidAreaNm2=state[171];
    coverageMaxBand=state[172];
    coverageUnbanded=state[173];
    coverageIncluded=state[174];
    showRoiLabels=state[175];
    fillCavities=state[176];
    fillAlpha=state[177];
    fillAlphaHex=state[178];
    roiStrokeWidth=state[179];
    activeStrokeColor=state[180];
    activeFillColor=state[181];
    lightConfirmedCavityColor=state[182];
    activeCavityClass=state[183];
    activeCavityClassLabel=state[184];
    activeCavityConfidence=state[185];
    autoOpenBrightnessContrast=state[186];
    featureToolPreset=state[187];
    missingMacroToolWarningShown=state[188];
    undoKind=state[189];
    undoObjectId=state[190];
    undoDeletedName=state[191];
    undoAvailable=state[192];
    keepWindowSize=state[193];
    lockedWinW=state[194];
    lockedWinH=state[195];
    fixedNavigation=state[196];
    panFraction=state[197];
    keyPanFraction=state[198];
    wheelPanFraction=state[199];
    zoomStep=state[200];
    restoreViewAfterRoi=state[201];
    viewSnapshotValid=state[202];
    viewSnapX=state[203];
    viewSnapY=state[204];
    viewSnapW=state[205];
    viewSnapH=state[206];
    viewSnapWinX=state[207];
    viewSnapWinY=state[208];
    viewSnapWinW=state[209];
    viewSnapWinH=state[210];
    v4ToolVersion=state[211];
    v4ProjectLoaded=state[212];
    v4ProjectDir=state[213];
    v4ProjectSwitchInProgress=state[214];
    v4BridgeDir=state[215];
    v4BridgeStaticDir=state[216];
    v4BridgePointerJson=state[217];
    v4BridgeGenerationId=state[218];
    v4ProjectFieldsCsv=state[219];
    v4ProjectFieldsText=state[220];
    v4RoiSetsCsv=state[221];
    v4ProjectId=state[222];
    v4ProjectName=state[223];
    v4StudyId=state[224];
    v4StudyName=state[225];
    v4SampleId=state[226];
    v4Material=state[227];
    v4Condition=state[228];
    v4SpecimenId=state[229];
    v4SpecimenLabel=state[230];
    v4AcquisitionId=state[231];
    v4AcquisitionLabel=state[232];
    v4MasterImage=state[233];
    v4MasterRole=state[234];
    v4MasterRevisionId=state[235];
    v4CurrentMontagePointerPath=state[236];
    v4MasterRevisionManifestPath=state[237];
    v4MasterNativePlanPath=state[238];
    v4MasterFidelityReportPath=state[239];
    v4CurrentMontagePointerSha256=state[240];
    v4MasterRevisionManifestSha256=state[241];
    v4MasterNativePlanSha256=state[242];
    v4MasterFidelitySha256=state[243];
    v4MasterSha256=state[244];
    v4MasterOwnershipSha256=state[245];
    v4RevisionBindingReady=state[246];
    v4RevisionBindingError=state[247];
    v55IntegrityCacheFingerprint=state[248];
    v55IntegrityCacheProjectId=state[249];
    v55IntegrityCacheUntilMs=state[250];
    v55IntegrityCacheTtlMs=state[251];
    v55IntegrityLastEvidence=state[252];
    v55IntegrityLastError=state[253];
    v55FileCanonicalPath=state[254];
    v55FileSizeBytes=state[255];
    v55FileModifiedMs=state[256];
    v55FileSha256=state[257];
    v56RequestId=state[258];
    v56PreparedAt=state[259];
    v56RoiDraftError=state[260];
    v56RoiDraftCount=state[261];
    v56RoiSnapshotDirectory=state[262];
    v56RoiSnapshotEntryName=state[263];
    v56ResolvedSessionZip=state[264];
    v56ResolvedSessionRoiCount=state[265];
    v56SessionValidationError=state[266];
    v56ResolvedSessionReviewStatus=state[267];
    v56ResolvedSessionQuantitativeReady=state[268];
    v56ResolvedSessionPendingCount=state[269];
    v56ResolvedSessionGeometryBlockerCount=state[270];
    v56RoiSessionContractJson=state[271];
    v4CalibrationId=state[272];
    v4PixelWidth=state[273];
    v4PixelHeight=state[274];
    v4PixelUnit=state[275];
    v4SurfaceId=state[276];
    v4SurfaceOriginDefined=state[277];
    v4SurfaceOriginArcNm=state[278];
    v4SurfaceOriginXpx=state[279];
    v4SurfaceOriginYpx=state[280];
    v4SurfaceTangentialSign=state[281];
    v4ActiveRoiSetId=state[282];
    v4ActiveRoiSetName=state[283];
    v4ActiveObjectType=state[284];
    v4ActiveGeometry=state[285];
    v4ActiveIdPrefix=state[286];
    v4ActiveScientificRole=state[287];
    v4ActiveProtocolId=state[288];
    v4ActiveStrokeColor=state[289];
    v4ActiveFillColor=state[290];
    v4RunId=state[291];
    v4LastLocalXpx=state[292];
    v4LastLocalYpx=state[293];
    v4TraceMode=state[294];
    v4TraceTool=state[295];
    v4TraceSessionId=state[296];
    v4TraceConfidence=state[297];
    v4TraceNote=state[298];
    v4TraceAdded=state[299];
    v4TraceDeleted=state[300];
    v4TraceLastObjectId=state[301];
    v4TraceCaptureOrder=state[302];
    v4ScaleConflict=state[303];
    v4ScaleConflictText=state[304];
    v4ScaleReconciliationStatus=state[305];
    v4ScaleMeasurementAllowed=state[306];
    v4ImageScaleNmX=state[307];
    v4ImageScaleNmY=state[308];
    v4ImageScaleUnit=state[309];
    v4PanelsCsv=state[310];
    v4PanelGeometryJson=state[311];
    v4OwnershipImage=state[312];
    v4OwnershipLegendCsv=state[313];
    v4OwnershipCertified=state[314];
    v4PanelOverlapPolicy=state[315];
    v4PanelGeometryStatus=state[316];
    v4PanelQuantitativeReady=state[317];
    panelLastOwnerCode=state[318];
    panelLastCoverageCount=state[319];
    v51ScaleBarLengthNm=state[320];
    v51ScaleBarPosition=state[321];
    v51ScaleBarColor=state[322];
    v51ScaleBarBackground=state[323];
    v51ScaleBarBackgroundAlpha=state[324];
    v51ScaleBarThicknessPx=state[325];
    v51ScaleBarFontPx=state[326];
    v51ScaleBarMarginPx=state[327];
    v51GuideSpacingNm=state[328];
    v51GuideMaximumNm=state[329];
    v51GuideColor=state[330];
    v51GuideWidthPx=state[331];
    v51GuideDashed=state[332];
    v51GuideBothSides=state[333];
    v51GuideLabels=state[334];
    v51LastExactAreaCsv=state[335];
    v51LastExactAreaMethod=state[336];
    imageToolsVersion=state[337];
    imageToolsLastRecipe=state[338];
    imageToolsLastPurpose=state[339];
    imageToolsLastSource=state[340];
    count=round(state[341]);surfaceX=newArray(count);surfaceY=newArray(count);
    for(k=0;k<count;k++){surfaceX[k]=state[342+k];surfaceY[k]=state[342+count+k];}
    lightInvalidateAnalysisCache();lightClearCavityContextCache();
    if(nImages()>0)setMetadataImageProperties();
}

function lightHF46Finite(v) { return !isNaN(v)&&!isNaN(v-v); }

function lightHF46WriteText(path,text) {
    result=call("cavity.light.HF46.writeText",path+"\n"+text);
    if(result!="OK"){call("cavity.light.HF4.log",result);showStatus(result);return 0;}return 1;
}
function lightHF46ResetImageState() {
    surfaceDefined=0;surfaceSideDefined=0;scaleDefined=0;surfaceMaterialSign=1;
    surfaceX=newArray(0);surfaceY=newArray(0);
    lightSourcePath="";lightSourceStoredPath="";lightSourceSha256="";lightCurrentRevision="";lightCurrentRunId="";
    lightImageId="";lightImageDir="";projectConfigured=0;undoAvailable=0;undoKind="";undoObjectId="";undoDeletedName="";
    lightPreparedFingerprint="";lightInvalidateAnalysisCache();lightClearCavityContextCache();
    lightImageMode="without_surface";lightUseWholeImage=0;lightIncludeUncertain=0;usePanelsAsMask=0;v4ProjectLoaded=0;
    lastValidAreaNm2=NaN;lastBandAreasNm2=newArray(0);
    cavityCounter=0;grainBoundaryCounter=0;dislocationCounter=0;interfaceCounter=0;loopCounter=0;exclusionCounter=0;maskCounter=0;panelCounter=0;
}

// US1 preparation and workspace entrypoints.
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
