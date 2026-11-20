# Prueba de estructura del PRD (DOC-14)

## 1. Módulo

- Archivo: `tests/test_prd_structure.py`. Solo biblioteca estándar (`unittest`, `pathlib`, `re`, `unicodedata`), sin red y sin escribir en disco. Debe funcionar en todas las versiones de Python de la matriz del CI (`.github/workflows/tests.yml`: 3.11 a 3.14), así que no usa sintaxis ni funciones posteriores a 3.11.
- `docs/PRD.md` (copia del PRD 2.2 que se conserva por orden del dueño) queda fuera de todas las comprobaciones.
- Raíz: `Path(__file__).resolve().parents[1]`, como `DOCS_ROOT` en `tests/test_integration.py`.
- Métodos: `test_doc_14_NN_<descripción>`, por ejemplo `test_doc_14_03_ids_unique_contiguous_and_next_free`.
- Comentarios y docstrings en inglés. Describen lo que se comprueba y pueden citar el ID del caso. No citan este plan.
- **Capítulos:** los archivos `docs/prd/NN-*.md` (salvo `00-indice.md`), `docs/prd/12.MM-*.md` y `docs/prd/anexos/*.md`. La portada, el glosario, el historial y la plantilla no son capítulos.
- **Bloque de código:** todo lo que va entre una línea que empieza, con hasta tres espacios delante, por tres comillas invertidas o tres virgulillas y la siguiente línea con la misma valla. **Frontmatter:** las líneas entre el `---` de la línea 1 y el siguiente `---`.
- Los archivos se leen como UTF-8. Cuando una comprobación falla, el mensaje lista cada infracción con archivo y línea.

## 2. Casos

**Tabla: Casos de DOC-14**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Ningún archivo `.md` de `docs/prd/` (con `anexos/`) supera 300 líneas, frontmatter incluido. |
| .02 | P | Las secciones esperadas salen de la columna "Sección" de la tabla "Archivos del PRD" de `00-indice.md`: el número inicial (`6`, `12.5`) o `Anexo X`; las filas sin número ni anexo se ignoran. Cada sección esperada tiene exactamente un encabezado en los capítulos, en un archivo de su prefijo: `NN-*.md` para la sección N, `12.MM-*.md` para la 12.M y `anexos/X-*.md` para el anexo X. Todo encabezado de capítulo de nivel `## N.`, `### 12.M` o `### Anexo X` es una sección esperada. Un encabezado numerado más profundo (por ejemplo 10.3.1 o 12.5.2) está en un archivo con el prefijo de su sección o de su subsección 12.M. Encabezado numerado: `^#{2,6} (\d+(?:\.\d+)*)\.? `; de anexo: `^### Anexo ([A-Z]) `. |
| .03 | P | Los IDs se definen una sola vez, en su capítulo dueño, y van de 1 al máximo sin huecos: O (`^\| (O\d+) \|` en `03-objetivos.md`), CU (`^\| (CU-\d+) \|` en `05-usuarios.md`), RF (`^\| (RF-\d+) \|` en `06-requisitos-funcionales.md`), RNF (`^\| (RNF-\d+) \|` en `07-requisitos-no-funcionales.md`), ADR (`^\| (ADR-\d+) \|` en `08-adr.md`) y AC (`^\*\*(AC-\d+)\.\*\*` en `20-criterios-aceptacion.md`). La fila de datos de la tabla "Próximos IDs libres" de `00-indice.md` tiene el máximo + 1 de cada tipo, con el mismo formato (O29, CU-10, RF-80…). |
| .04 | P | Toda referencia de sección de los capítulos (`§` seguido de `\d+(?:\.\d+)*`), también dentro de bloques de código, corresponde a un encabezado numerado de los capítulos. |
| .05 | P | Todo enlace markdown `[…](destino)` de `docs/prd/`, fuera de bloques de código, cuyo destino no empieza por un esquema (`http:`, `https:`, `mailto:`) apunta a un archivo que existe y no lleva ancla `#`. |
| .06 | P | Cada archivo `.md` de `docs/prd/` (con `anexos/`) distinto de `00-indice.md` tiene un enlace desde `00-indice.md`. |
| .07 | P | Toda tabla de `docs/prd/` fuera de bloques de código (primera línea de un grupo de líneas que empiezan por `\|`) tiene como línea no vacía anterior una que empieza por `**Tabla: `. |
| .08 | N | Ningún archivo de `docs/prd/` contiene `docs/plan` ni `plan2/`. |
| .09 | P | Todo archivo `.md` de `docs/prd/` empieza por frontmatter con una línea `aliases: [` y al menos un elemento entre comillas, y una línea `tags: [` cuya lista incluye `prd`. |
| .10 | P | En `GLOSARIO.md`, los encabezados `###` de cada grupo `##` están en orden alfabético. Clave de orden: sin comillas invertidas, en NFKD sin marcas diacríticas, sin caracteres que no sean letras ni dígitos y con `casefold()`. |
| .11 | N | Ningún archivo `.md` de `docs/prd/` empieza por la marca BOM de UTF-8. |

## 3. Cambios en el catálogo de pruebas

**`docs/tests/docs-packaging.md`:** después del grupo DOC-09 y antes de PKG-01 va este grupo.

~~~~markdown
#### DOC-14 — Estructura del PRD

Requisitos: — (estructura de la documentación) · Archivo: `tests/test_prd_structure.py`

**Tabla: Casos de DOC-14**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Ningún archivo de `docs/prd/` supera 300 líneas. |
| .02 | P | Cada sección del Índice de la portada tiene un solo encabezado, en el archivo de su prefijo. |
| .03 | P | Los IDs O, CU, RF, RNF, ADR y AC son únicos y sin huecos en su capítulo dueño, y la portada tiene los próximos libres. |
| .04 | P | Toda referencia de sección de los capítulos corresponde a un encabezado. |
| .05 | P | Todo enlace relativo de `docs/prd/` apunta a un archivo existente y no lleva ancla. |
| .06 | P | La portada enlaza a todos los archivos de `docs/prd/`. |
| .07 | P | Toda tabla tiene su línea `**Tabla: …**`. |
| .08 | N | Ningún archivo de `docs/prd/` cita un plan. |
| .09 | P | Todo archivo de `docs/prd/` tiene frontmatter con `aliases` y la etiqueta `prd`. |
| .10 | P | Los términos del glosario están en orden alfabético dentro de cada grupo. |
| .11 | N | Ningún archivo de `docs/prd/` empieza por BOM. |
~~~~

**`docs/tests/TEST-CATALOG.md`:**

1. Sección "1. Convenciones", al final de la lista, este punto nuevo:

   ~~~~markdown
   - **Estructura de la documentación.** Un grupo DOC puede verificar la estructura de la documentación del producto en lugar de un requisito; lleva `Requisitos: —` y dice qué estructura verifica.
   ~~~~

2. Sección "Qué no entra en el catálogo": `y cualquier comportamiento que el PRD no fija.` pasa a `y cualquier comportamiento que el PRD no fija, salvo la estructura de la documentación (punto "Estructura de la documentación" de las convenciones).`
3. Sección "2. Prefijos y archivos": encima de la tabla (separada por una línea en blanco) va `**Tabla: Prefijos y archivos de la suite**`, porque la tabla cambia en el punto 4.
4. Fila DOC de esa tabla: la columna "Qué cubre" pasa a ``READMEs, skill, ayudas, `config.example.toml` y estructura del PRD``, y la columna "Archivo" añade `` `tests/test_prd_structure.py` ``.
