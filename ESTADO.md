# Cavity TEM Light 1.2 RC1 — lista para prueba de imágenes individuales

Comprobación final del 20 de septiembre de 2026, en este equipo Windows. La candidata está preparada para una prueba funcional del usuario. Los cálculos combinados siguen aplazados.

## Abrir y probar

1. Abre [ABRIR_CAVITY_LIGHT_1_2.bat](../../ABRIR_CAVITY_LIGHT_1_2.bat), situado en `C:\Cavity light`.
2. En la biblioteca, selecciona un proyecto y una imagen. «Añadir carpeta» permite incorporar ubicaciones de proyectos, incluidas carpetas de red accesibles desde Windows. Las imágenes y resultados permanecen en sus ubicaciones.
3. Selecciona una revisión o un RUN y pulsa «Abrir imagen en Fiji». En el editor puedes guardar una revisión nueva y calcular/exportar resultados de esa imagen. Después pulsa «Actualizar biblioteca» para ver el avance guardado.

El [manual de la candidata](CavityLight/Documentacion/LEEME_1_2.md) explica las referencias aceptadas, los formatos de proyecto y la recuperación. Fiji, Java y Python están incluidos en `CavityLight`. Para comprobar sus archivos de aplicación, ejecuta `CavityLight/COMPROBAR_APLICACION.bat`.

## Comprobaciones realizadas

| Comprobación | Resultado observado |
| --- | --- |
| Arranque desde el nuevo acceso | Biblioteca visible, sin errores de arranque; 1 proyecto, 2 imágenes y 2 RUN del catálogo existente |
| Abrir la revisión aceptada sobre una copia | Fuente e identidad correctas; 661 cavidades |
| Guardar y reabrir una revisión nueva | 664 ROI recuperadas con geometría idéntica, incluidos 661 objetos; identidad, clases y exclusiones conservadas |
| Parámetros de sesión | Escala X/Y 1 nm/píxel, escala definida, inclusión de dudosas y paso interactivo 2 nm conservados |
| Calcular y exportar | RUN nuevo completo; 28 archivos comprobados por sus huellas, más la identidad y huella del ZIP de revisión |
| Recuento, área y densidad | 661; 44.421778 µm²; 14.880088771 µm⁻² |
| Originales | 38 archivos comprobados por SHA-256 sin cambios: 3 registros, 33 archivos de la revisión aceptada y las dos ubicaciones de la fuente DM4 |
| Editor y cálculos conservados | 10 comprobaciones focales Python y 8 grupos Java; hashes de las seis funciones científicas centrales conservados |
| Biblioteca | Comprobaciones focales de integridad, cancelación, recuperación del catálogo, ubicaciones duplicadas, identidad P3, selección tardía e historial; registro detallado disponible |
| Runtime P3 existente | Integridad de 34 archivos de runtime y 10 artefactos; lectura explícita de un RUN P3 comprobada separadamente |
| Paquete final | 68 archivos de aplicación, editor y accesos coinciden con el manifiesto de entrega; comprobador ejecutado con el Python incluido |

El recorrido integrado utiliza las funciones de producción en Fiji, automatizadas mediante una macro de comprobación sobre la copia. La fuente de producción de esa ejecución coincide con la desplegada. No supone que se hayan recorrido manualmente todos los botones ni todas las variantes de imagen.

## Diferencia numérica explicada, sin modificar la referencia

La comparación literal del RUN histórico con el recalculado detectó diferencias en coordenadas y valores derivados. Su estado `FAIL` se conserva en `Comprobacion/INTEGRATED_VERIFICATION.json`: no se ha cambiado la tolerancia para ocultarlas.

La revisión aceptada ya contiene geometrías serializadas con coordenadas de 32 bits, mientras sus propiedades y tablas conservan valores previos al guardado. Al reabrir, el cálculo trabaja sobre la geometría que ImageJ realmente guardó. La comprobación causal separada reproduce esta transformación para los 661 objetos. No cambian los identificadores, clases, exclusiones, elegibilidad, bandas, recuentos ni métodos. La geometría decodificada de las ROI históricas y de las guardadas por la candidata es exactamente igual.

El diámetro medio histórico es **14.603630862 nm**; el recalculado es **14.603630908 nm**, una diferencia de **0.000000046 nm**. En los objetos individuales, el cambio máximo de diámetro es 0.000244 nm y el de coordenada es 0.000651 nm. La biblioteca presenta los valores históricos escritos cuando se consulta ese RUN. El RUN nuevo y su explicación permanecen separados del resultado aceptado.

Hay una consecuencia visible en el histograma de intervalos de 1 nm: siete objetos situados en límites enteros pasan al intervalo inmediatamente inferior tras recalcular las ROI guardadas (tres junto a 13 nm, uno junto a 15 nm y tres junto a 17 nm). El total sigue siendo 661. No se afirma que los histogramas históricos y recalculados sean idénticos; no se ha alterado el criterio de intervalos de R9 ni añadido una tolerancia para forzar esa igualdad. La evidencia está en `Comprobacion/HISTOGRAM_PRECISION.json`.

## Evidencia y límites

El índice de evidencias y sus huellas está en [VERIFICACION_ENTREGA.json](VERIFICACION_ENTREGA.json). Los detalles de apertura/guardado/reapertura/exportación, comparación literal, precisión numérica, integridad de originales y pruebas focales están en `Comprobacion`.

La referencia aceptada continúa siendo `REV_20260919_025550_534 / RUN_20260919_025554_091`. El puntero actual posterior del proyecto permanece distinto; no se ha sustituido la referencia aceptada. Los RUN de la comprobación están únicamente en `Comprobacion/Proyecto_copia_661`.

Esta entrega permite probar el flujo individual en Windows/Fiji. La comprobación de compatibilidad se limita a la imagen de referencia utilizada y a las pruebas de software descritas; no constituye validación científica general. Los proyectos P3 se mantienen con su gestor correspondiente y requieren seleccionar el proyecto en él. No se declara completado todo el alcance histórico Prompt 10 ni se han probado otros equipos físicos.
