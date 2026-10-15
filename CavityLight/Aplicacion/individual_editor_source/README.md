# Editor de imágenes individuales 1.2 RC1

Este componente incorpora al repositorio activo el recorrido funcional de R9
consolidada HF4.6. Su procedencia y los hashes de la macro fuente, JAR e iconos
se conservan en `PROVENANCE.json`. No sustituye los desarrollos P2/P3 existentes.
El editor analiza cada imagen de forma independiente. La biblioteca incorpora
un estudio conjunto que utiliza exclusivamente RUN guardados y verificados;
el código histórico de combinado de la macro sigue sin ejecutarse.

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
versión real de aplicación `1.2.0-RC1-individual-US1`.

## Usabilidad y revisiones US1

- El panel conserva posición y pestaña al actualizarse. Sus controles inferiores
  muestran u ocultan ROI Manager y barra Fiji, mantienen el panel encima,
  organizan las ventanas en uno o dos monitores y guardan su disposición.
  F2 recupera el panel oculto. Siguen siendo ventanas de Fiji coordinadas;
  esta entrega no introduce una ventana única con paneles acoplados.
- Preparar ofrece brillo/contraste por zonas, contraste local basado en media y
  variación local, y corrección de fondo. Se previsualiza antes de aplicar.
  Las zonas se conservan como ROIs de tratamiento separadas de las cavidades.
  Las operaciones trabajan sobre copias; nunca escriben el DM3/DM4 original.
- Deshacer/Rehacer tratamiento tiene un recorrido independiente de las
  anotaciones. Guardar conserva únicamente las operaciones vigentes, con sus
  parámetros, zonas y hashes de píxeles. Al reabrir se recuperan los píxeles
  exactos guardados; el deshacer anterior a esa reapertura no se conserva.
- Los cambios de píxeles hechos con comandos externos de Fiji se detectan.
  «Conservar cambios hechos con Fiji» permite describirlos y guardarlos como
  una etapa de trazabilidad parcial, sin inventar sus filtros o parámetros.
- «Guardar avance con nombre» admite nombre/comentario, incluso antes de
  marcar cavidades. Guarda TIFF de trabajo, PNG anotado, miniatura, ROIs y
  configuración congelada en una nueva revisión. El espacio ocupado crece con
  cada revisión manual; no se crea una imagen por cada clic ni un autoguardado.
- La publicación de la revisión es atómica: primero se comprueban todos sus
  artefactos y después se activa. Si falla un guardado o una carga, se conservan
  los píxeles y la sesión anterior. Las revisiones existentes no se sobrescriben.
- La biblioteca muestra avances con o sin RUN, su miniatura y configuración;
  permite comparar dos revisiones de una imagen. Los datos antiguos sin receta
  muestran «No registrado». Esta mejora no reconstruye pasos históricos ni
  repara automáticamente identidades ya dañadas.
- «Estudio del proyecto» combina un RUN por imagen con muestra, condición y
  protocolo compatibles, escalas confirmadas e integridad verificada. La
  densidad usa suma de cavidades/suma de áreas; las estadísticas de tamaño
  utilizan las cavidades individuales. Se exige confirmar que los campos no
  se solapan. CSV, JSON y HTML se guardan en una carpeta nueva fuera del proyecto.
- «Ajustar detector con cavidades confirmadas» propone tamaños y separación
  iniciales editables para las herramientas existentes. Es una ayuda estadística,
  no un modelo entrenado, y las propuestas requieren revisión manual.

Las comprobaciones técnicas cubren el motor de preparación, hashes, restauración,
publicación, biblioteca, agregación y el intérprete IJM. Este entorno no dispone
de pantalla: la prueba visual de Fiji/Tk y el recorrido completo con DM3/DM4
reales en Windows siguen pendientes. No se declara validación científica.

## Archivos de ejecución

En una copia aislada de Fiji:

1. Copiar `cavity-light-hf4.jar` y `cavity-light-individual.jar` a `plugins/`.
   Fiji debe conservar `gson-*.jar` en `jars/`.
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
en Fiji y ejecuta las comprobaciones Java sin interfaz.

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

## Corrección de identidad ID1

ImageJ 1.54p comparte el mapa de propiedades al clonar una ROI. Registrar como
nueva una elipse seleccionada del ROI Manager podía sobrescribir el ID y el
serial de la cavidad histórica, dejando su nombre anterior. El botón ahora
se llama «Registrar nueva elipse»: rechaza objetos gestionados antes de
incrementar el contador o escribir identidad. Una selección Oval nueva se
separa mediante una nueva ROI con la misma geometría subpíxel y propiedades.

La corrección previene ese recorrido; no modifica archivos de proyectos ni
repara identidades ya sobrescritas. Se han superado 28 comprobaciones Java
sin interfaz, incluida la reproducción de propiedades compartidas, el rechazo
sin cambios y la separación de una selección nueva. La prueba visual de esta
corrección en Fiji bajo Windows queda pendiente.
