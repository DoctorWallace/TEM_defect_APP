// Resolve the manager from this running Fiji; no workspace or example binding.
runtime = getDirectory("imagej") + "scripts/Plugins/Cavity_TEM_Light/Prompt3_Masks_Manager.js";
if (!File.exists(runtime)) exit("No se encuentra el gestor en esta copia de Fiji. Extraiga el paquete completo.");
eval("js", File.openAsString(runtime));
