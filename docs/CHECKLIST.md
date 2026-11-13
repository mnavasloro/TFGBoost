# Checklist TFGBoost de revisión formativa de memorias de TFG

Versión `2026-11`. Documento generado desde [`app/checklist/tfg_checklist.json`](../app/checklist/tfg_checklist.json) con `python scripts/render_checklist.py`: edita el JSON, no este fichero.

## Fuentes

- **solicitud**: Solicitud del piloto TFGBoost (UPM, Vicerrectorado de Universidad Digital): categorías ortografía, estructura, claridad y coherencia; detectar conceptos sin explicar, distribución de capítulos y referencias mal citadas; no redactar por el alumno.
- **encuesta**: Cuestionario a tutores de TFG (16 respuestas, ETSISI y otros centros UPM). P8: frecuencia 1-5 de cada error; P9: errores que más tiempo consumen; P10: otros errores; P11: errores que el alumno debería corregir siempre; P13: preocupaciones; P16: qué no debe hacer nunca la herramienta.
- **revision**: Guía de revisión por fases usada en la versión anterior del prototipo (revision-tfg-prompts.md).
- **normativa**: Requisitos habituales de la normativa de TFG del centro. Adaptar `required_sections` a la normativa oficial vigente de cada escuela.

## Cómo se usa

- Cada punto se evalúa con reglas transparentes, con un modelo de lenguaje o con ambos; el estado final es el más desfavorable.
- Estados: **cumple**, **por revisar**, **no cumple**, **no evaluable** (sin evidencia suficiente o sin modelo) y **revisión manual**.
- Las citas aportadas por la IA se buscan literalmente en el borrador; si ninguna aparece, el punto no puede quedar en «no cumple» (mitiga las alucinaciones, la principal preocupación de los tutores en la encuesta).
- **Madurez**: La madurez es la media ponderada del estado de cada punto evaluado (cumple = 1, por revisar = 0,5, no cumple = 0). El peso de cada punto es su prioridad en la encuesta: 0,7 × frecuencia media normalizada + 0,3 × proporción de tutores que lo señalan como el que más tiempo consume. Los puntos sin dato de encuesta usan el peso por defecto.
- **Semáforo**: verde ≥ 75 sin puntos imprescindibles en «no cumple»; ámbar ≥ 50; rojo por debajo.
- **Imprescindible**: errores que los tutores piden corregir siempre antes de enviar (encuesta, P11). Si alguno queda en «no cumple», el estudiante debe corregirlo o justificar por qué no aplica antes de enviar el borrador al tutor.
- La herramienta nunca reescribe el texto (encuesta, P16): señala el problema, explica por qué importa y orienta la corrección.

## Resumen priorizado

Ordenado por peso (prioridad según la encuesta a 16 tutores; los puntos sin dato de encuesta usan el peso por defecto).

| ID | Punto | Categoría | Método | Imprescindible | Frecuencia media (1-5) | % tutores 4-5 | Votos «más tiempo» | Peso |
|---|---|---|---|---|---|---|---|---|
| R1 | Afirmaciones respaldadas por citas | Citas y fuentes | Modelo de IA |  | 4.56 | 94 % | 9 | 0.792 |
| E3 | Introducción con motivación, objetivos y alcance claros | Estructura y normativa | Modelo de IA |  | 4.0 | 75 % | 10 | 0.712 |
| L4 | Frases largas, confusas o mal construidas | Ortografía y redacción | Regla + IA | Sí | 4.19 | 81 % | 7 | 0.69 |
| N2 | Decisiones técnicas justificadas | Contenido y claridad | Modelo de IA |  | 4.06 | 62 % | 7 | 0.667 |
| L6 | Redundancias y texto de relleno | Ortografía y redacción | Regla + IA |  | 4.12 | 81 % | 6 | 0.658 |
| C2 | Saltos lógicos y conexión entre secciones | Coherencia y argumentación | Modelo de IA |  | 3.75 | 62 % | 9 | 0.65 |
| N3 | Resultados analizados e interpretados | Contenido y claridad | Modelo de IA |  | 3.81 | 62 % | 7 | 0.623 |
| E2 | Equilibrio entre capítulos | Estructura y normativa | Regla + IA | Sí | 3.94 | 62 % | 5 | 0.608 |
| L5 | Registro poco académico (coloquialismos, primera persona inadecuada) | Ortografía y redacción | Regla + IA | Sí | 3.69 | 56 % | 7 | 0.602 |
| C3 | Conclusiones con reflexión propia | Coherencia y argumentación | Modelo de IA |  | 3.94 | 69 % | 4 | 0.589 |
| R2 | Formato de citas consistente | Citas y fuentes | Regla + IA | Sí | 3.94 | 75 % | 3 | 0.571 |
| A1 | Voz propia: pasajes genéricos sin aportación del estudiante | Autoría e integridad | Modelo de IA |  | 3.38 | 50 % | 8 | 0.567 |
| N1 | Términos técnicos, siglas y conceptos definidos | Contenido y claridad | Regla + IA | Sí | 3.62 | 56 % | 5 | 0.552 |
| F1 | Figuras y tablas numeradas, con pie y citadas en el texto | Figuras, tablas y anexos | Regla + IA | Sí | 3.62 | 50 % | 4 | 0.533 |
| R3 | Correspondencia entre citas y bibliografía | Citas y fuentes | Regla automática | Sí | 3.75 | 69 % | 2 | 0.519 |
| C1 | Objetivos alineados con resultados y conclusiones | Coherencia y argumentación | Modelo de IA | Sí | 3.31 | 44 % | 6 | 0.517 |
| L3 | Puntuación y espaciado | Ortografía y redacción | Regla + IA |  | 3.5 | 56 % | 4 | 0.512 |
| L2 | Errores gramaticales y de concordancia | Ortografía y redacción | Modelo de IA |  | 3.56 | 56 % | 2 | 0.485 |
| L7 | Terminología y estilo consistentes | Ortografía y redacción | Modelo de IA |  | – | – | – | 0.45 |
| E5 | Restos de borrador (TODO, secciones vacías, marcadores) | Estructura y normativa | Regla + IA | Sí | – | – | – | 0.45 |
| E6 | Contenido en el capítulo adecuado | Estructura y normativa | Modelo de IA |  | – | – | – | 0.45 |
| C4 | Afirmaciones proporcionadas a la evidencia | Coherencia y argumentación | Modelo de IA |  | – | – | – | 0.45 |
| N4 | Metodología y requisitos trazables | Contenido y claridad | Modelo de IA |  | – | – | – | 0.45 |
| N5 | Limitaciones y trabajo futuro concretos | Contenido y claridad | Modelo de IA |  | – | – | – | 0.45 |
| R4 | Fiabilidad y variedad de las fuentes | Citas y fuentes | Regla + IA |  | – | – | – | 0.45 |
| F2 | Fuente indicada en figuras y tablas ajenas | Figuras, tablas y anexos | Modelo de IA |  | – | – | – | 0.45 |
| F3 | Legibilidad y tamaño de figuras, capturas y código | Figuras, tablas y anexos | Comprobación manual |  | – | – | – | 0.45 |
| P1 | Páginas preliminares y requisitos formales | Requisitos formales y éticos | Modelo de IA |  | – | – | – | 0.45 |
| P2 | Protección de datos, ética e impacto | Requisitos formales y éticos | Modelo de IA |  | – | – | – | 0.45 |
| P3 | Datos sensibles, credenciales y repositorio | Requisitos formales y éticos | Regla + IA | Sí | – | – | – | 0.45 |
| E4 | Resumen y abstract coherentes con el contenido | Estructura y normativa | Regla + IA |  | 3.06 | 31 % | 4 | 0.435 |
| E1 | Secciones obligatorias según la normativa | Estructura y normativa | Regla automática | Sí | 3.0 | 25 % | 4 | 0.425 |
| A2 | Posible copia o parafraseo excesivo de fuentes | Autoría e integridad | Modelo de IA |  | 2.81 | 19 % | 3 | 0.373 |
| L1 | Faltas de ortografía, acentuación y erratas | Ortografía y redacción | Modelo de IA | Sí | 3.0 | 31 % | 1 | 0.369 |

## Detalle por categoría

### Ortografía y redacción

#### L1 · Faltas de ortografía, acentuación y erratas

- **Método**: Modelo de IA · **Gravedad**: Importante · **Imprescindible**
- **Origen**: solicitud, encuesta P8a, encuesta P11
- **Pregunta al modelo**: Localiza faltas de ortografía, tildes y erratas. Cita literalmente cada palabra o fragmento erróneo. No incluyas la palabra corregida completa: indica solo qué regla revisar (tilde diacrítica, b/v, mayúsculas, etc.).
- **Orientación al estudiante**: Las erratas restan credibilidad y hacen que el tutor dedique su revisión a lo formal. Pasa el corrector del procesador de textos y relee en voz alta los párrafos señalados.

#### L2 · Errores gramaticales y de concordancia

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: solicitud, encuesta P8a
- **Pregunta al modelo**: Busca errores de concordancia (género, número, sujeto-verbo), tiempos verbales incoherentes, preposiciones incorrectas (dequeísmo, queísmo) y oraciones sin verbo principal. Cita el fragmento y nombra el tipo de error.
- **Orientación al estudiante**: Identifica el sujeto y el verbo de cada oración señalada y comprueba que concuerdan; mantén el mismo tiempo verbal dentro de cada capítulo.

#### L3 · Puntuación y espaciado

- **Método**: Regla + IA · **Gravedad**: Menor
- **Origen**: solicitud, encuesta P8a
- **Pregunta al modelo**: Señala errores de puntuación: coma entre sujeto y verbo, falta de coma en incisos y conectores, punto y coma mal usado, signos de apertura ausentes (¿ ¡). Cita el fragmento.
- **Orientación al estudiante**: Revisa especialmente las comas tras conectores (sin embargo, por tanto) y los incisos. Elimina espacios antes de los signos de puntuación y espacios dobles.

#### L4 · Frases largas, confusas o mal construidas

- **Método**: Regla + IA · **Gravedad**: Importante · **Imprescindible**
- **Origen**: solicitud, encuesta P8a, encuesta P9, encuesta P11
- **Pregunta al modelo**: Señala oraciones confusas, demasiado largas (más de 40 palabras) o mal construidas: cita el comienzo y explica qué dificulta su comprensión (varias ideas encadenadas, subordinadas anidadas, referente ambiguo).
- **Orientación al estudiante**: Una idea por oración. Separa las ideas independientes y comprueba que sujeto, verbo y complemento se entienden en una sola lectura.

#### L5 · Registro poco académico (coloquialismos, primera persona inadecuada)

- **Método**: Regla + IA · **Gravedad**: Importante · **Imprescindible**
- **Origen**: encuesta P8a, encuesta P9, encuesta P11
- **Pregunta al modelo**: Señala coloquialismos, expresiones informales, valoraciones subjetivas sin respaldo y usos de la primera persona del singular inadecuados para una memoria técnica. Cita el fragmento.
- **Orientación al estudiante**: Una memoria técnica usa un registro impersonal o la primera persona del plural de forma consistente. Sustituye las valoraciones ("muy bueno", "genial") por datos o argumentos.

#### L6 · Redundancias y texto de relleno

- **Método**: Regla + IA · **Gravedad**: Importante
- **Origen**: encuesta P8a, encuesta P9
- **Pregunta al modelo**: Localiza ideas repetidas, frases que no aportan información (relleno, muletillas, generalidades del tipo "hoy en día la tecnología es muy importante") y párrafos que repiten lo dicho en otro apartado. Cita el fragmento.
- **Orientación al estudiante**: Pregúntate qué perdería el lector si eliminaras la frase. Si la respuesta es "nada", sobra. Concreta con datos, ejemplos o referencias.

#### L7 · Terminología y estilo consistentes

- **Método**: Modelo de IA · **Gravedad**: Menor
- **Origen**: revision
- **Pregunta al modelo**: ¿Se usa un único término por concepto? Señala sinónimos alternados para el mismo concepto técnico, extranjerismos innecesarios o sin cursiva, y cambios de persona gramatical o tiempo verbal.
- **Orientación al estudiante**: Elige un término por concepto y mantenlo en todo el documento; registra los términos en el glosario.

### Estructura y normativa

#### E1 · Secciones obligatorias según la normativa

- **Método**: Regla automática · **Gravedad**: Crítico · **Imprescindible**
- **Origen**: solicitud, normativa, encuesta P8b, encuesta P11
- **Orientación al estudiante**: Comprueba la normativa de TFG de tu centro y titulación: añade los apartados requeridos y usa encabezados inequívocos y numerados.

#### E2 · Equilibrio entre capítulos

- **Método**: Regla + IA · **Gravedad**: Importante · **Imprescindible**
- **Origen**: solicitud, encuesta P8b, encuesta P10 (nivel de detalle), encuesta P11
- **Pregunta al modelo**: ¿El nivel de detalle es adecuado y equilibrado? Señala capítulos o apartados demasiado escuetos para su importancia, o excesivamente detallados (p. ej., explicaciones de tecnologías conocidas, listados de código o capturas que no aportan).
- **Orientación al estudiante**: El peso de cada capítulo debe reflejar su importancia: el desarrollo y la evaluación son el núcleo del trabajo. Lleva los detalles secundarios a anexos y desarrolla los apartados escasos.

#### E3 · Introducción con motivación, objetivos y alcance claros

- **Método**: Modelo de IA · **Gravedad**: Crítico
- **Origen**: encuesta P8b, encuesta P9, revision
- **Pregunta al modelo**: ¿La introducción presenta el problema, por qué merece resolverse (motivación), qué se pretende conseguir y qué queda fuera del alcance? ¿Los objetivos son concretos y verificables? Enumera los objetivos tal como aparecen.
- **Orientación al estudiante**: La introducción debe responder: ¿qué problema hay?, ¿por qué importa?, ¿qué haré exactamente?, ¿qué no haré? Formula los objetivos de forma verificable (con verbos como implementar, evaluar, comparar).

#### E4 · Resumen y abstract coherentes con el contenido

- **Método**: Regla + IA · **Gravedad**: Importante
- **Origen**: encuesta P8c, revision, normativa
- **Pregunta al modelo**: ¿El resumen (y el abstract) describe el problema, el método, los resultados principales y la conclusión reales del trabajo? Señala afirmaciones del resumen que no se desarrollan en el documento o resultados clave que faltan en él. ¿Hay palabras clave?
- **Orientación al estudiante**: Escribe el resumen al final: problema, qué has hecho, cómo, qué has obtenido y qué significa. Comprueba que español e inglés dicen lo mismo.

#### E5 · Restos de borrador (TODO, secciones vacías, marcadores)

- **Método**: Regla + IA · **Gravedad**: Crítico · **Imprescindible**
- **Origen**: revision, encuesta P10 (lectura activa)
- **Pregunta al modelo**: ¿Hay secciones vacías o con solo un título, notas internas (TODO, pendiente, completar), texto de ejemplo de la plantilla o referencias cruzadas rotas ("Figura ??", "Error! Reference source not found")?
- **Orientación al estudiante**: Busca y elimina todos los marcadores antes de enviar el borrador; si una sección está pendiente, indícalo al tutor en el mensaje, no en la memoria.

#### E6 · Contenido en el capítulo adecuado

- **Método**: Modelo de IA · **Gravedad**: Menor
- **Origen**: revision, solicitud
- **Pregunta al modelo**: ¿Se distinguen estado del arte (trabajos de otros), marco tecnológico (herramientas utilizadas) y desarrollo (trabajo propio)? Señala contenido que esté en un capítulo equivocado.
- **Orientación al estudiante**: Estado del arte: qué han hecho otros y en qué se diferencia tu propuesta. Marco tecnológico: con qué herramientas trabajas y por qué. Desarrollo: qué has hecho tú.

### Coherencia y argumentación

#### C1 · Objetivos alineados con resultados y conclusiones

- **Método**: Modelo de IA · **Gravedad**: Crítico · **Imprescindible**
- **Origen**: encuesta P8b, encuesta P9, encuesta P11, revision
- **Pregunta al modelo**: Enumera los objetivos declarados y, para cada uno, indica si hay desarrollo, resultado y conclusión asociados. Señala objetivos sin cerrar, y conclusiones o resultados que no responden a ningún objetivo.
- **Orientación al estudiante**: Construye una tabla objetivo → dónde se desarrolla → qué resultado lo demuestra → qué conclusión lo cierra. Si un objetivo no se ha cumplido, explícalo en las conclusiones.

#### C2 · Saltos lógicos y conexión entre secciones

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: solicitud, encuesta P8b, encuesta P9
- **Pregunta al modelo**: Señala saltos lógicos: conclusiones que no se siguen de lo anterior, párrafos sin transición, apartados que no se conectan con el capítulo o con el objetivo del trabajo. Cita el fragmento donde se produce el salto.
- **Orientación al estudiante**: Al inicio de cada capítulo indica qué aporta y cómo se relaciona con el anterior; entre párrafos, explicita la relación (causa, contraste, consecuencia).

#### C3 · Conclusiones con reflexión propia

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: encuesta P8b, encuesta P10 (reflexión)
- **Pregunta al modelo**: ¿Las conclusiones aportan reflexión (qué se ha aprendido, qué significan los resultados, limitaciones, líneas futuras concretas) o solo repiten el resumen o enumeran lo hecho?
- **Orientación al estudiante**: Las conclusiones no son un resumen: valora el grado de cumplimiento de cada objetivo, explica qué significan los resultados, reconoce limitaciones y propone continuaciones concretas.

#### C4 · Afirmaciones proporcionadas a la evidencia

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: revision
- **Pregunta al modelo**: ¿Alguna conclusión o afirmación sobre el sistema va más allá de lo que demuestran los resultados (generalizaciones, superlativos, "el sistema es eficiente/robusto" sin medida)? Cita el fragmento.
- **Orientación al estudiante**: Cada afirmación sobre la calidad del trabajo debe apoyarse en un resultado concreto; si no lo hay, matiza la afirmación o preséntala como hipótesis.

### Contenido y claridad

#### N1 · Términos técnicos, siglas y conceptos definidos

- **Método**: Regla + IA · **Gravedad**: Importante · **Imprescindible**
- **Origen**: solicitud, encuesta P8c, encuesta P11, encuesta P14
- **Pregunta al modelo**: Lista los términos técnicos, siglas y conceptos clave que se usan sin haber sido definidos o explicados en su primera aparición.
- **Orientación al estudiante**: Define cada sigla en su primer uso, p. ej. "interfaz de programación de aplicaciones (API)", y recógelas en un glosario. Explica los conceptos clave antes de usarlos.

#### N2 · Decisiones técnicas justificadas

- **Método**: Modelo de IA · **Gravedad**: Crítico
- **Origen**: encuesta P8c, encuesta P9, encuesta P10 (proceso frente a producto)
- **Pregunta al modelo**: ¿Las decisiones técnicas (tecnologías, arquitectura, algoritmos, metodología) se justifican frente a alternativas razonables? ¿Se explica el proceso de construcción y no solo el producto o el código? Señala decisiones presentadas sin justificación.
- **Orientación al estudiante**: Para cada decisión importante, explica qué alternativas consideraste, con qué criterios elegiste y por qué. Describe el proceso, no solo el resultado final.

#### N3 · Resultados analizados e interpretados

- **Método**: Modelo de IA · **Gravedad**: Crítico
- **Origen**: encuesta P8c, encuesta P9, revision
- **Pregunta al modelo**: ¿Los resultados se analizan e interpretan (qué significan, comparación con una referencia o con el estado del arte, criterios de evaluación explícitos) o solo se presentan (tablas, capturas, cifras) sin discusión?
- **Orientación al estudiante**: Tras cada tabla o figura de resultados, explica qué muestra, por qué ocurre y qué implica para tus objetivos. Define antes los criterios con los que evalúas.

#### N4 · Metodología y requisitos trazables

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: revision
- **Pregunta al modelo**: ¿Se describe una metodología aplicada realmente en el trabajo? Si hay requisitos, ¿son verificables y se trazan hasta la implementación y las pruebas? ¿Se distingue la aportación propia del trabajo de terceros?
- **Orientación al estudiante**: Describe cómo has trabajado de verdad (iteraciones, planificación, validación) y relaciona cada requisito con dónde se implementa y cómo se prueba.

#### N5 · Limitaciones y trabajo futuro concretos

- **Método**: Modelo de IA · **Gravedad**: Menor
- **Origen**: revision, encuesta P10 (reflexión)
- **Pregunta al modelo**: ¿Se reconocen limitaciones del trabajo y se proponen líneas futuras concretas y realistas (no genéricas)?
- **Orientación al estudiante**: Reconocer limitaciones demuestra espíritu crítico. Propón trabajo futuro concreto y justificado por esas limitaciones.

### Citas y fuentes

#### R1 · Afirmaciones respaldadas por citas

- **Método**: Modelo de IA · **Gravedad**: Crítico
- **Origen**: solicitud, encuesta P8d, encuesta P9
- **Pregunta al modelo**: ¿Qué afirmaciones, datos, cifras, definiciones o comparativas necesitarían una referencia y no la tienen? Cita cada fragmento.
- **Orientación al estudiante**: Todo dato, cifra, definición ajena o afirmación sobre el estado del arte debe llevar su cita. Si no encuentras fuente, matiza la afirmación o elimínala.

#### R2 · Formato de citas consistente

- **Método**: Regla + IA · **Gravedad**: Importante · **Imprescindible**
- **Origen**: solicitud, encuesta P8d, encuesta P11
- **Pregunta al modelo**: ¿Las citas en el texto y las entradas bibliográficas siguen un estilo único y completo (autor, título, año, editorial o URL con fecha de consulta)? Señala entradas incompletas o con formatos mezclados.
- **Orientación al estudiante**: Usa un único estilo (IEEE, APA…) según indique tu titulación; un gestor bibliográfico (BibTeX, Zotero) evita inconsistencias. Las fuentes web necesitan fecha de consulta.

#### R3 · Correspondencia entre citas y bibliografía

- **Método**: Regla automática · **Gravedad**: Importante · **Imprescindible**
- **Origen**: encuesta P8d, encuesta P11
- **Orientación al estudiante**: Cada cita del texto debe tener su entrada en la bibliografía y cada entrada debe citarse al menos una vez en el texto.

#### R4 · Fiabilidad y variedad de las fuentes

- **Método**: Regla + IA · **Gravedad**: Menor
- **Origen**: encuesta P10 (adecuación de fuentes), encuesta P17
- **Pregunta al modelo**: ¿Las fuentes son fiables, relevantes y actuales (artículos, libros, documentación oficial) o predominan blogs, foros, Wikipedia y páginas comerciales? ¿Hay equilibrio entre fuentes académicas y web?
- **Orientación al estudiante**: Prioriza artículos revisados por pares, libros y documentación oficial. Usa la biblioteca de la UPM y valora la autoridad de cada fuente.

### Figuras, tablas y anexos

#### F1 · Figuras y tablas numeradas, con pie y citadas en el texto

- **Método**: Regla + IA · **Gravedad**: Importante · **Imprescindible**
- **Origen**: encuesta P8d, encuesta P11, encuesta P14
- **Pregunta al modelo**: ¿Las figuras y tablas tienen numeración correlativa y pie descriptivo, y se mencionan y comentan en el texto? Lista las que no se citan.
- **Orientación al estudiante**: Cada figura y tabla necesita número, pie autoexplicativo y una mención en el texto que explique qué debe observar el lector.

#### F2 · Fuente indicada en figuras y tablas ajenas

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: encuesta P10 (citas en tablas e imágenes), revision
- **Pregunta al modelo**: ¿Las figuras, tablas o fragmentos de código tomados de otros trabajos indican su fuente (y licencia si procede)? Señala los pies que parecen describir material ajeno sin cita.
- **Orientación al estudiante**: Si una figura o tabla procede de otro trabajo (aunque la hayas adaptado), indica "Fuente: [ref]" o "Adaptado de [ref]" en el pie.

#### F3 · Legibilidad y tamaño de figuras, capturas y código

- **Método**: Comprobación manual · **Gravedad**: Menor
- **Origen**: encuesta P10 (tamaño de figuras), revision
- **Orientación al estudiante**: Comprueba manualmente que las figuras se leen impresas sin ampliar, que las capturas no son decorativas ni redundantes y que no muestran datos personales, credenciales o rutas locales. El análisis de texto no puede verificar el aspecto visual.

### Autoría e integridad

#### A1 · Voz propia: pasajes genéricos sin aportación del estudiante

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: solicitud, encuesta P8e, encuesta P9, encuesta P12, encuesta P15
- **Pregunta al modelo**: Señala pasajes genéricos e impersonales que no aportan nada específico del trabajo (enumeraciones vacías, frases comodín, tono de folleto, ausencia de datos o decisiones concretas), que podrían corresponder a texto generado automáticamente sin elaboración propia. Es solo un indicio a revisar, nunca una acusación.
- **Orientación al estudiante**: Este indicador NO detecta IA con fiabilidad: señala pasajes genéricos que no reflejan tu trabajo. Reescríbelos con tus palabras incluyendo tus decisiones, datos y experiencia concretos. Si has usado IA generativa, decláralo según la normativa.

#### A2 · Posible copia o parafraseo excesivo de fuentes

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: encuesta P8e, revision
- **Pregunta al modelo**: ¿Hay pasajes que parecen copiados o traducidos casi literalmente de una fuente (cambios bruscos de estilo, terminología distinta, sin cita)? Señálalos solo como sospecha a verificar.
- **Orientación al estudiante**: Las ideas ajenas se citan y se explican con tus palabras; las citas literales van entre comillas con su referencia. Es una sospecha a comprobar, no una acusación.

### Requisitos formales y éticos

#### P1 · Páginas preliminares y requisitos formales

- **Método**: Modelo de IA · **Gravedad**: Menor
- **Origen**: normativa, revision
- **Pregunta al modelo**: ¿Se identifican portada, índice, resumen bilingüe, palabras clave y, si la normativa lo exige, declaración de uso de IA generativa y licencia? Indica qué debe comprobarse manualmente (márgenes, tipografía, interlineado, extensión, numeración de páginas).
- **Orientación al estudiante**: Revisa la plantilla oficial de tu centro: portada, extensión, márgenes, tipografía y numeración no se pueden verificar completamente a partir del texto.

#### P2 · Protección de datos, ética e impacto

- **Método**: Modelo de IA · **Gravedad**: Importante
- **Origen**: revision, normativa
- **Pregunta al modelo**: Si el trabajo usa datos personales o usuarios reales, ¿se trata el consentimiento, la anonimización y la protección de datos? ¿Se analiza el impacto social, ambiental o ético del trabajo cuando procede?
- **Orientación al estudiante**: Si hay usuarios o datos reales, explica cómo has obtenido el consentimiento y anonimizado los datos. Revisa si tu normativa exige un apartado de impacto (ODS, ética).

#### P3 · Datos sensibles, credenciales y repositorio

- **Método**: Regla + IA · **Gravedad**: Crítico · **Imprescindible**
- **Origen**: revision
- **Pregunta al modelo**: ¿Aparecen credenciales, contraseñas, claves de API, correos personales, rutas locales o datos sensibles en el texto o en los fragmentos de código? ¿El repositorio o software se enlaza con licencia?
- **Orientación al estudiante**: Elimina credenciales, claves y rutas locales del texto y de las capturas. Enlaza el repositorio e indica su licencia.

## Apartados de la memoria reconocidos

| Apartado | Obligatorio | Encabezados aceptados |
|---|---|---|
| Portada | No | portada |
| Resumen (español) | Sí | resumen |
| Abstract (inglés) | Sí | abstract, summary |
| Índice | Sí | indice, tabla de contenidos, contenido, indice general |
| Introducción | Sí | introduccion |
| Objetivos | Sí | objetivos, objetivo, objetivos del proyecto, objetivos del trabajo |
| Estado del arte / antecedentes | Sí | estado del arte, trabajos relacionados, antecedentes, marco teorico, estado de la cuestion |
| Marco tecnológico | No | marco tecnologico, tecnologias, tecnologias utilizadas, herramientas, herramientas utilizadas |
| Requisitos | No | requisitos, analisis de requisitos, especificacion de requisitos |
| Metodología / planificación | Sí | metodologia, metodo, planificacion, metodologia y planificacion |
| Desarrollo | Sí | desarrollo, implementacion, diseno, analisis, diseno e implementacion, arquitectura, propuesta, solucion propuesta |
| Resultados / evaluación | Sí | resultados, evaluacion, experimentos, validacion, pruebas, experimentacion |
| Análisis de impacto (ODS, ética) | No | impacto, impacto social, analisis de impacto, impacto social y medioambiental, objetivos de desarrollo sostenible, responsabilidad etica y profesional |
| Conclusiones | Sí | conclusiones, conclusion, conclusiones y trabajo futuro, conclusiones y lineas futuras |
| Trabajo futuro | No | trabajo futuro, lineas futuras, trabajos futuros |
| Glosario / acrónimos | No | glosario, acronimos, siglas, abreviaturas, lista de acronimos |
| Referencias | Sí | referencias, bibliografia, referencias bibliograficas |
| Anexos | No | anexos, anexo, apendices, apendice |

> Ajusta `required_sections` a la normativa oficial de TFG de cada escuela antes del piloto.
