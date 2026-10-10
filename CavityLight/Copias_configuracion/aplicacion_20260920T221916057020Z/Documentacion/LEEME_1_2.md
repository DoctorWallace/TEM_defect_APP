# Cavity TEM Light 1.2 RC1 · imágenes individuales

Esta candidata reúne una biblioteca local y el editor individual basado en R9 consolidada. Está preparada para Windows con Fiji, Java y Python incluidos. El objetivo es trabajar imagen a imagen y depurar los siguientes detalles durante el uso. Los resultados combinados quedan aplazados.

## Arranque

Abre `INICIAR_CAVITY_LIGHT_1_2.bat` en la carpeta entregada. No requiere activar entornos de Python ni instalar el editor sobre otro Fiji. `ABRIR_EDITOR_INDIVIDUAL.bat` abre directamente el editor para comenzar un proyecto o registrar una imagen.

La instalación previa y sus accesos siguen siendo independientes. Esta distribución tiene sus propias preferencias y registros. No mezcles ediciones simultáneas del mismo proyecto desde varias instancias de Fiji.

## Biblioteca

1. Añade una carpeta que contenga un proyecto, o una carpeta superior con varios proyectos. Puedes seleccionar unidades locales y carpetas de red accesibles desde Windows.
2. Selecciona un proyecto y una imagen. El catálogo muestra sus revisiones y resultados guardados y distingue los proyectos copiados en ubicaciones diferentes.
3. Selecciona un resultado para leer su resumen y comprobar sus archivos. En R9 se presentan los valores que quedaron guardados, con sus parámetros; la biblioteca no aplica una política P3 sobre ellos.
4. Abre tablas, informes y gráficos PNG del resultado seleccionado. Para trabajar en Fiji, utiliza «Abrir imagen en Fiji». En R9 se abre la revisión elegida, también si todavía no tiene RUN; si no seleccionas ninguna fila del historial, se usa la revisión actual de la imagen.
5. Actualiza la biblioteca después de guardar cambios en Fiji. La actualización se ejecuta en segundo plano y puede cancelarse; una cancelación conserva el catálogo completo anterior.

El índice solo lee descriptores, registros y nombres de revisiones. No decodifica las DM3/DM4 ni verifica todos los píxeles durante cada actualización. «Resultado disponible» significa que existe un resultado registrado, no que se haya validado científicamente. Al seleccionar un RUN se comprueba su integridad; esta comprobación técnica tampoco certifica su interpretación física.

Si una unidad está desconectada, se conserva el último inventario y resumen de avance con el estado de no disponible. Leer tablas, mostrar gráficos y verificar un RUN requiere que su carpeta esté accesible. Quitar una ubicación de la biblioteca solo retira su vínculo del índice. El índice y sus referencias aceptadas se guardan en `%LOCALAPPDATA%\CavityTEMLight\library.json`, con copia recuperable `.bak`, fuera de los proyectos.

## Revisiones actuales y referencias aceptadas

Una referencia aceptada corresponde a un proyecto, imagen, revisión, RUN y huella concretos. Guardar una revisión posterior no cambia automáticamente esa elección. El botón de aceptar referencia exige que los archivos sigan coincidiendo con los comprobados. Si aceptas más de un RUN de la misma imagen, se conservan sus marcas en el historial y el panel identifica la última referencia aceptada.

La referencia proporcionada por el usuario es `REV_20260919_025550_534 / RUN_20260919_025554_091` de la imagen `Fe5Cr_450C_V1_II_18MAY15_0014_0039_32df3e7a618d`. Sus resultados guardados contienen 661 cavidades y un diámetro medio de 14.603630862 nm. La revisión posterior del mismo proyecto usa otra escala; la biblioteca conserva ambas y no decide cuál debe sustituir a la referencia aceptada.

## Editor individual

El editor conserva el formato de proyectos, fuentes, revisiones, propiedades de objetos y cálculos de R9 consolidada. Permite abrir o registrar una imagen, recuperar una revisión, trabajar con cavidades y las geometrías de R9, guardar nuevas revisiones y calcular resultados de esa imagen.

La apertura normal no solicita una carpeta de freezes de campañas de desarrollo. La candidata utiliza el recorrido funcional de R9, con su importación y controles, y no el recorrido experimental P1 que pedía esos archivos externos. Los proyectos P3 existentes se reconocen y se abren con su gestor instalado correspondiente; en ese gestor hay que seleccionar el proyecto indicado por la biblioteca. No se migran silenciosamente entre formatos.

La edición numérica de una ROI oval conserva ahora la proporción entre sus dos ejes y sus propiedades al cambiar el centro o el diámetro equivalente. Antes, ese recorrido podía convertir una elipse en un círculo. Este cambio solo afecta a ediciones que realices: no modifica ROIs guardadas al abrir un proyecto ni recalcula resultados históricos. La entrada es el diámetro equivalente; ambos ejes se escalan por el mismo factor, manteniendo la relación física con las escalas X/Y existentes. Una selección que haya cambiado durante el diálogo se rechaza para evitar aplicar la edición al objeto incorrecto.

Al reabrir una revisión se conservan su indicador de calibración y el paso de ajuste interactivo. Una escala guardada válida no pierde su indicador por carecer de una línea de calibración, y el paso propio de la sesión tiene prioridad sobre la preferencia general del editor.

Guardar una revisión mantiene la geometría y puede marcar las medidas derivadas como pendientes de recalcular, siguiendo el funcionamiento de R9. «Calcular y exportar resultados» comprueba y prepara esas medidas y crea un RUN nuevo. Los resultados históricos y su revisión permanecen separados.

Las cancelaciones y errores de importación conservan la sesión anterior y cierran únicamente las ventanas creadas por la operación fallida. Los accesos a combinados están retirados de esta candidata.

## Trazabilidad y recuperación

- `VERSION_1_2.json` identifica la candidata y las huellas de sus componentes. El JAR R9 original se conserva; la corrección de geometría y el puente de apertura están en un JAR adicional con su fuente Java.
- `Aplicacion/individual_editor_source` contiene las fuentes y la procedencia de la adaptación; el desarrollo completo se mantiene en el repositorio activo.
- `Registro` contiene errores de arranque y solicitudes de apertura. No contiene copias de las fuentes TEM.
- `Copias_configuracion` conserva versiones anteriores de archivos operativos que actualice el constructor y los registros de reubicación del gestor P3.
- `COMPROBAR_APLICACION.bat` contrasta los archivos de aplicación y accesos con sus huellas de empaquetado. No valida científicamente proyectos ni recorre todo el runtime de Fiji.
- Los proyectos y resultados se guardan donde elijas en el editor. Conserva tus copias de seguridad habituales antes de trabajar con una candidata.

## Alcance de las comprobaciones

El informe de entrega enumera las pruebas efectivamente ejecutadas. Las pruebas de software, la integridad de la referencia y un recorrido técnico sobre copias no equivalen a validación científica general. No se ha ampliado la matriz de plataformas ni se prometen todas las funciones de los prompts históricos. La siguiente depuración se centra en incidencias concretas del trabajo por imagen.

La comprobación integrada de esta entrega abrió la imagen de referencia, guardó una revisión nueva, la reabrió y exportó un RUN en una copia controlada. Se conservaron los 661 objetos, las 664 ROI, la escala X/Y de 1 nm/píxel, el indicador de calibración, la inclusión de dudosas y el paso de ajuste de 2 nm. La geometría decodificada del ZIP guardado coincide exactamente con la del ZIP aceptado.

Leer el RUN histórico en la biblioteca conserva sus valores escritos. Reabrir las ROI y recalcular puede producir pequeños cambios numéricos por la precisión de 32 bits del formato ROI de ImageJ, que ya afecta al ZIP histórico: en esta imagen, el diámetro medio pasa de 14.603630862 a 14.603630908 nm. En siete objetos situados en límites enteros, el redondeo también cambia su intervalo en el histograma de 1 nm, sin cambiar el recuento total. Por ello, no se promete que un gráfico recalculado sea idéntico al histórico. La entrega conserva el informe de comparación literal, que detecta esas diferencias, y una comprobación causal separada. No se sustituye ni se corrige el resultado aceptado para hacerlo coincidir.
