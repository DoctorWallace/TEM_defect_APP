# Probar Cavity Light US1 en Windows

[Descargar el actualizador US1](CavityLight_1_2_RC1_US1.zip)

Este paquete actualiza CavityLight 1.2 RC1, con o sin la corrección ID1. No incluye Fiji completo. El ZIP ocupa 444.061 bytes; su huella está en `CavityLight_1_2_RC1_US1.sha256`.

1. Descarga el ZIP y extrae todo su contenido en una carpeta de Windows.
2. Cierra Fiji y la biblioteca de Cavity Light.
3. Dentro de `CavityLight_US1`, ejecuta `ACTUALIZAR_CAVITY_LIGHT.bat` y selecciona tu carpeta `CavityLight`, que contiene `Fiji`, `Python` y `INICIAR_CAVITY_LIGHT_1_2.bat`.
4. Ejecuta `COMPROBAR_APLICACION.bat` en esa instalación y después `INICIAR_CAVITY_LIGHT_1_2.bat`.

El actualizador comprueba la base, crea una copia de los archivos reemplazados y permite restaurarlos mediante `RESTAURAR_VERSION_ANTERIOR.bat`. Los proyectos y las imágenes originales se conservan.

US1 incorpora tratamientos de imagen con previsualización, zonas conservadas, receta vigente, guardados manuales con nombre e imagen, consulta/comparación de revisiones, controles de ventanas y estudios conjuntos de RUN compatibles. El autoguardado y una interfaz única con paneles acoplados siguen fuera de esta entrega.

## Abrir el código en Codex local

El código de esta entrega está en la rama `codex/cavity-light-us1`. Si usas una copia Git local, descarga esa rama y ábrela en Codex. Si utilizas Download ZIP de GitHub, selecciona primero esa rama; esto descarga el repositorio completo, no solo el actualizador. La aplicación sigue arrancando desde `CavityLight/INICIAR_CAVITY_LIGHT_1_2.bat`.

## Validación

Pasaron 92 tests Python, 547 comprobaciones Java y 133 comprobaciones con el intérprete ImageJ, además de actualización/restauración en copias aisladas RC1 e ID1. Las seis funciones científicas auditadas conservan sus hashes. La prueba visual Fiji/Tk y el recorrido completo con DM3/DM4 reales en Windows quedan pendientes. No se declara validación científica.
