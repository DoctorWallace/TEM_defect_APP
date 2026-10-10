# Cavity Light · Resultados descriptivos

Desde `python_companion`, ejecutar `python -m cavity_stats_app` para abrir la
ventana de lectura. Solo biblioteca estándar de Python 3.10 o posterior; la
ventana necesita Tkinter. La herramienta de línea de comandos no necesita Tk.

Uso sin ventana:

```text
python -m cavity_stats_app --run-dir "ruta\sesion\runs\RUN_RUN_000003" --output-dir "ruta\informes"
```

La ruta de ejemplo no selecciona un resultado automáticamente: hay que indicar
la carpeta concreta del RUN. La carpeta de salida debe existir y estar fuera
del proyecto. Se crea un subdirectorio nuevo, sin sobrescribir informes previos,
con HTML, resumen CSV, objetos CSV, JSON y hashes. Los valores vacíos de tamaño
del CSV significan no definido; JSON conserva sus estados. El CSV de objetos
protege texto que una hoja de cálculo pudiera interpretar como fórmula; el JSON
conserva los valores originales.

La aplicación verifica el contexto físico de proyecto/sesión, el registro,
los hashes del RUN, la revisión, la evidencia persistida de escala de Prompt 3
y cualquier invalidación científica. No cambia proyecto, RUN, preferencias,
sesiones ni fuentes. Solo admite revisiones `CTL_P2A_REVISION_MANIFEST_V2`.
Un RUN exportado fuera de su proyecto o sin evidencia de escala se rechaza.

El primario incluye confirmadas; sensibilidad incluye confirmadas e inciertas.
Cada indicador de recuento, tamaño y posición se aplica independientemente.
Densidad y estadísticas se calculan con las funciones del núcleo existente.
Se muestran diámetros equivalentes, no ejes ni tamaños 3D.

Esta entrega es una `TECHNICAL_PREVIEW` de alcance P8 parcial: no combina RUN,
no hace inferencia jerárquica, intervalos de confianza, repetibilidad ni modelos
3D, y no acredita validación científica o cierre completo de Prompt 8. Las
sesiones clonadas no representan réplicas independientes. Los informes son
instantáneas verificadas a su fecha: volver a cargar ante cambios posteriores.
