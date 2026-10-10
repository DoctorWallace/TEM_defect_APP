// This wrapper installs into the running isolated Fiji process, not another installation.
editorPath=getArgument();
if(editorPath=="")editorPath=getDirectory("imagej")+"macros/toolsets/Cavity_TEM_Light_1_2_RC1.ijm";
installed=call("cavity.light.IndividualEditor.install",editorPath);
if(installed!="OK")exit(installed);
// The packaged toolset has no AutoRun; this is the only startup entrypoint.
run("Cavity Light: iniciar biblioteca");
