# Editor de imágenes individuales 1.2 RC1

Este componente incorpora al repositorio activo el recorrido funcional de R9
consolidada HF4.6. Su procedencia y los hashes de la macro fuente, JAR e iconos
se conservan en `PROVENANCE.json`. No sustituye los desarrollos P2/P3 existentes.
La interfaz habilita análisis por imagen; el código histórico de combinado se
conserva como referencia, sin comandos ni botones que lo ejecuten.

## Cambios concretos

- La edición numérica de una ROI Oval conserva la proporción física de sus dos
  ejes, incluso con calibración X/Y anisótropa. Cambia el centro y el diámetro
  equivalente mediante un factor común aplicado a los ejes existentes.
- Se conservan todas las propiedades, identidad, clase, exclusión, grupo y notas
  de la ROI. La edición rechaza un diálogo desactualizado si cambió la imagen,
  el objeto seleccionado o su geometría. Las medidas derivadas se recalculan
  después mediante el mismo núcleo científico R9.
- La biblioteca puede abrir un proyecto, imagen y revisión exactos sin escribir
  metadatos, índices, registros, revisiones ni resultados al abrir. La escala y
  configuración proceden de la revisión elegida, incluida la inclusión histórica
  de dudosas. El guardado y la exportación siguen siendo operaciones explícitas.
- Al abrir una copia trasladada se prefiere su descriptor validado y su fuente
  local `images/<id>/source/<archivo>`, contrastada con SHA-256. No se vincula
  silenciosamente la revisión con la carpeta histórica de otro disco.
- El cambio de proyecto o imagen registrada permite Guardar/Descartar/Cancelar.
  Ante fallo después de importar, solo se cierra la ventana creada por esa
  operación, por su ID; se restaura la imagen y sesión anteriores.
- La configuración de una imagen recién registrada se abre después de confirmar
  la transacción. Cancelar ese diálogo conserva el alta ya completada y no deja
  pendiente una restauración de la importación.
- El guardado prepara las carpetas de registros antes de publicar una revisión,
  para que una carpeta `logs` ausente no interrumpa después una operación válida.
- Una escala válida restaurada de los metadatos conserva su indicador de escala
  definida aunque no exista una ROI de línea de calibración. La sensibilidad de
  la rueda se restaura por sesión; las preferencias globales solo proporcionan
  el valor inicial para una imagen sin ese ajuste.

No se requieren freezes de campaña. Los controles de hash de fuente, identidad,
dimensiones y manifiesto de revisión siguen vigentes. No se han cambiado las
reglas científicas de área, bandas, clases, densidad, distancias o exclusiones.
El identificador del método HF3 se mantiene; las nuevas salidas registran la
versión real de aplicación `1.2.0-RC1-individual`.

## Archivos de ejecución

En una copia aislada de Fiji:

1. Copiar `cavity-light-hf4.jar` y `cavity-light-individual.jar` a `plugins/`.
2. Copiar `Cavity_TEM_Light_1_2_RC1.ijm` y los cinco iconos PNG a
   `macros/toolsets/`.
3. Ejecutar Fiji con `-macro Start_Individual_Editor.ijm`. El argumento opcional
   de la macro es la ruta absoluta del toolset; si no se proporciona, se busca
   en `getDirectory("imagej") + macros/toolsets/`.

El wrapper instala la macro en el proceso actual y llama el comando explícito
`Cavity Light: iniciar biblioteca`. La candidata no declara AutoRun: el arranque
se realiza una sola vez desde el wrapper, sin depender de cómo ImageJ detecte
la macro instaladora. Si se instala manualmente el toolset desde Fiji, ejecutar
después `Cavity Light: iniciar biblioteca` para abrir el panel y consumir una
selección pendiente de la biblioteca.

Para una selección procedente de la biblioteca, el lanzador añade la propiedad
JVM `cavity.light.library.request` con la ruta de un archivo UTF-8 de dos columnas
separadas por tabulador, fuera de los proyectos:

```text
project_root    C:/Carpeta/Proyecto_CavityTEM_Light
image_id        IDENTIFICADOR_DE_IMAGEN
revision_id     REV_20260919_025550_534
```

Los espacios del ejemplo representan tabuladores reales. Si falta `revision_id`,
se usa la vigente; si su valor está vacío, se abre sin ROI. Si `image_id` está
vacío, se carga solo el proyecto. La petición se consume una vez. El resultado
queda en la propiedad `cavity.light.library.result` (`OK` o `ERROR`). Una fuente
ausente produce un mensaje; el usuario puede localizarla con el editor normal.

## Desarrollo y comprobaciones

`upgrade_editor.py <macro_R9_original>` aplica de forma reproducible los cambios
a la macro original identificada en el manifiesto; nunca edita la extracción
histórica. `build.ps1 -FijiRoot <Fiji>` compila la extensión con el JDK incluido
en Fiji y ejecuta ocho grupos de comprobaciones Java sin interfaz.

Desde la raíz del repositorio:

```powershell
python -m unittest discover -s tests -p test_individual_editor.py -v
```

Las diez comprobaciones Python cubren activos originales, hashes de funciones
científicas, alcance, apertura sin publicación, edición protegida y prioridad
del proyecto seleccionado al cargar una revisión trasladada, y preparación de
registros antes de publicar una revisión. También verifican la restauración de
la escala, la prioridad del paso por sesión y la correspondencia exacta de los
341 parámetros del snapshot. En ImageJ IJM,
`&&` **evalúa ambos operandos**: los controles que condicionan una escritura o un
diálogo deben usar `if` anidados. Se verificó ese comportamiento con el
intérprete real y se incluyó en las comprobaciones de los nuevos recorridos.

`make_smoke_toolset.py` genera una macro temporal para la prueba integrada con
`--allow-save-to-test-copy`: apertura de revisión exacta, guardado de una nueva
revisión y reapertura, con comparación de recuento, escala, indicador de escala
definida, paso de rueda e inclusión de dudosas. Debe apuntar a una copia
desechable explícita; escribe un informe TSV
por etapas y deja abierta la imagen para inspección visual. La integridad de
los originales y las geometrías guardadas se contrastan fuera de esa macro.
El informe registra la propiedad de respuesta y el estado de imagen/revisión
antes de guardar. Una apertura fallida termina sin publicar ninguna revisión y
sin abrir un diálogo modal adicional. `--export` añade un RUN mediante el mismo
comando de exportación utilizado por la aplicación.

Las comprobaciones Java/Python son técnicas; la evidencia de Fiji y sus límites
se registran con la entrega. No equivalen a validación científica. La edición
numérica nueva cubre Oval alineada con los ejes; no añade edición de elipses
rotadas ni cambia los métodos de interpretación de proyectos existentes.
