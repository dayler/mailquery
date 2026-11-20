# Plan — PRD en capítulos

**Estado:** borrador revisado · **Fecha:** 2026-11-19 · **Rama de trabajo:** `feature/prd-chapters`

Archivos del plan:

- [`00-plan.md`](00-plan.md): objetivo, restricciones, decisiones, hitos y verificación (este archivo).
- [`01-mapa.md`](01-mapa.md): de qué líneas del PRD base sale cada archivo y qué cambios de contenido se permiten.
- [`02-textos.md`](02-textos.md): texto final de los archivos nuevos y de cada edición fuera de `docs/prd/`.
- [`03-prueba-estructura.md`](03-prueba-estructura.md): especificación de la prueba automática DOC-14 y de los cambios del catálogo de pruebas.
- [`04-registro.md`](04-registro.md): registro de ejecución y evidencia; lo rellena quien implementa.

## 1. Objetivo

Partir `docs/PRD.md` en archivos pequeños dentro de `docs/prd/` **sin reescribir el PRD**: el mismo texto, la misma numeración de secciones, los mismos IDs y el mismo orden de líneas. A la vez se añaden:

- una portada (`00-indice.md`) con el índice, cómo se organiza el PRD, cómo se concilia un cambio por unidades atómicas, cómo se añade una funcionalidad y los próximos IDs libres;
- el glosario como documento aparte (`GLOSARIO.md`);
- el historial de versiones del documento como documento aparte (`HISTORIAL.md`);
- una plantilla de documento de cambio (`PLANTILLA-CAMBIO.md`);
- una prueba automática de la estructura (DOC-14), que corre en el CI.

Todos los archivos se leen igual en GitHub y en Obsidian.

## 2. Restricciones

**Tabla: Restricciones del plan**

| ID | Restricción |
|---|---|
| R-01 | **Presupuesto de cambio.** En la comparación de la sección 7.2, las líneas añadidas más las eliminadas no superan **299** (el 10 % de las 2991 líneas del PRD base). La previsión es de unas 155; una simulación de la partición con E-01…E-07 dio 156. |
| R-02 | Solo se hacen los cambios de contenido E-01…E-07 de `01-mapa.md`. Un cambio no previsto que resulte imprescindible se anota en `04-registro.md` con su motivo, cuenta para R-01 y se informa al dueño en la entrega. |
| R-03 | No cambian la numeración de secciones, los IDs (O, CU, RF, RNF, ADR, AC, `E_*`, `W_*`), los niveles de los encabezados ni el orden de las líneas. Las referencias de sección del texto (por ejemplo `§12.5`) se quedan como texto. |
| R-04 | No se tocan `docs/PRD.md`, `docs/plan/`, `docs/archive/`, `docs/PRD-v2.2.md`, `docs/KNOWN-DEFECTS.md`, `docs/tmp/` ni `src/`. El comportamiento del producto no cambia. |
| R-05 | Ningún archivo de `docs/prd/` supera 300 líneas, frontmatter incluido. |
| R-06 | Todo archivo nuevo o editado se escribe en UTF-8 sin BOM. En PowerShell no se usan `>`, `Out-File` ni `Set-Content` sin `-Encoding`; los archivos se escriben con el editor o desde Git Bash. |
| R-07 | La ejecución no delega en subagentes. Se aplican las reglas de lectura y salida de `CLAUDE.md` con sus límites por defecto. El directorio de logs es `../mailquery-plan2-logs/`, hermano del checkout y fuera de él. |
| R-08 | Los commits van en `feature/prd-chapters`. El merge a `develop` (gitflow: `--no-ff`, borrar la rama y push de `develop`) se hace solo con orden expresa del dueño, después de que revise la evidencia. |
| R-09 | **Tamaño (orden del dueño, 2026-11-20).** El conjunto de los archivos de `docs/prd/` no tiene más de un 10 % de caracteres que el PRD base: como mucho 390.261 frente a 354.783 (finales de línea LF). Se mide en la sección 7.2. |

## 3. Prerrequisitos

**Tabla: Prerrequisitos**

| ID | Prerrequisito | Quién |
|---|---|---|
| P-01 | `feature/prd-v22-reconciliation` integrada en `develop`, con el cambio pendiente de `docs/KNOWN-DEFECTS.md` incluido o descartado. | Dueño |
| P-02 | En `develop`, `git hash-object docs/PRD.md` es `ca24a3576fce0b6abd0c4f251aea5ebb313ad52a` (el blob de `9a3080a`). Si no coincide, los rangos de `01-mapa.md` se recalculan por sus primeras líneas, que no dependen de los números de línea; se anota en el registro y no requiere consulta. | Quien implementa |

## 4. Decisiones

**Tabla: Decisiones del plan**

| ID | Decisión |
|---|---|
| D-01 | El PRD vive en `docs/prd/`. Hay un archivo por sección de primer nivel (`NN-<nombre>.md`); la sección 12 va por subsecciones (`12.MM-<nombre>.md`), y los dos dígitos hacen que el orden alfabético coincida con el del documento. La 12.5 (519 líneas) se parte en tres archivos con el prefijo `12.05`, numerados `12.05-1-`, `12.05-2-` y `12.05-3-` para que también conserven el orden del documento. Cada anexo va en `docs/prd/anexos/<letra>-<nombre>.md`. |
| D-02 | Los encabezados conservan su nivel (`##`, `###`, `####`). Un capítulo no añade un título `#` propio; Obsidian lo nombra por el archivo y los `aliases`. |
| D-03 | Las referencias de sección del texto no se convierten en enlaces. La numeración no cambia y la regla "sección N → `NN-*.md`" las resuelve. |
| D-04 | Los enlaces nuevos son markdown relativos al archivo, sin anclas a encabezados y sin wikilinks. GitHub y Obsidian los resuelven igual. |
| D-05 | Cada archivo de `docs/prd/` empieza con frontmatter YAML con `aliases` y `tags` (formato en `01-mapa.md`, sección 2). |
| D-06 | **Orden del dueño (2026-11-20):** `docs/PRD.md` no se borra ni se modifica; renombrarlo solo se permite si fuera estrictamente necesario, y no lo es. Queda como copia del PRD 2.2 en un solo archivo; el PRD vigente es `docs/prd/`. Su retirada, si se decide, es una orden aparte del dueño. |
| D-07 | La versión del documento pasa a **2.3**, como en 1.2 y 1.3, que cambiaron el documento sin cambiar el producto. La versión del paquete no cambia. Las menciones "PRD v2.2" de los README, `docs/INTERFACES.md` y `docs/security/threat-model.md` pasan a v2.3 (`02-textos.md`, secciones 6 y 7). |
| D-08 | La estructura se verifica con una prueba `unittest` (grupo DOC-14, `tests/test_prd_structure.py`) y no con un script aparte, para que corra en el CI sin pasos nuevos. El catálogo de pruebas admite grupos DOC de estructura de la documentación (`03-prueba-estructura.md`, sección 3). |
| D-09 | Las 14 tablas del PRD base que no tienen título reciben el título de E-05. Lo exige la regla de títulos de `CLAUDE.md` y lo comprueba DOC-14. |
| D-10 | El glosario se reorganiza en dos grupos (`## Términos generales`, `## Términos de los backends`) y un encabezado `###` por término, en orden alfabético dentro de cada grupo. La definición se copia literal, con la primera letra en mayúscula. |
| D-11 | Los documentos existentes (`docs/PRD-v2.2.md`, `docs/KNOWN-DEFECTS.md`, `docs/security/threat-model.md`) no se migran a la plantilla de documento de cambio. La plantilla se aplica a los documentos de cambio nuevos, que viven en `docs/changes/`. Este plan no crea esa carpeta: aparece con el primer documento de cambio. |
| D-12 | Fuera de `docs/prd/` solo se reapuntan los **enlaces markdown** a `PRD.md`, los árboles de carpetas que lo listan y las menciones de versión de D-07. Las menciones de texto "`PRD.md` §N" en documentos y tests no cambian: la numeración es la misma y `docs/PRD.md` sigue existiendo (D-06). |
| D-13 | `.gitignore` no cambia: su patrón `.obsidian/` ya excluye la carpeta que crea Obsidian al abrir `docs/` como vault. |
| D-14 | `CLAUDE.md` cambia en dos puntos (`02-textos.md`, sección 6): la excepción de tests cita `docs/prd/`, y un párrafo nuevo dice dónde vive el PRD, dónde viven los documentos de cambio y cómo se concilian. |
| D-15 | La portada y la plantilla no numeran sus encabezados y nombran sus partes por el título, para que no se confundan con las secciones del PRD ni con la regla "sección N → `NN-*.md`". |
| D-16 | Este plan vive en `docs/plan2/` por orden expresa del dueño. Las reglas de `CLAUDE.md` para `docs/plan/` se le aplican igual: nada fuera de `docs/plan2/` lo cita, y se elimina solo cuando su trabajo, pruebas y evidencia están verificados, un revisor humano lo ha aprobado y el dueño lo ordena. |

## 5. Archivos que cambian

**Tabla: Archivos que crea o modifica el plan**

| Archivo | Acción | Hito |
|---|---|---|
| `docs/plan2/` (este plan) | Se incluye en el primer commit de la rama si aún no está en `develop`; `04-registro.md` se actualiza en cada hito | M1–M5 |
| `docs/prd/*.md`, `docs/prd/anexos/*.md` (47 archivos) | Crear según `01-mapa.md` y `02-textos.md` | M2 |
| `tests/test_prd_structure.py` | Crear (DOC-14) | M3 |
| `docs/tests/docs-packaging.md` | Añadir el grupo DOC-14 | M3 |
| `docs/tests/TEST-CATALOG.md` | Convención nueva, excepción en "Qué no entra", título de la tabla de prefijos y fila DOC (M3); enlace de la línea 3 (M4) | M3, M4 |
| `README.md`, `README.es.md` | Enlace y versión de la línea de referencias, los dos en el mismo commit | M4 |
| `CLAUDE.md` | Dos cambios de D-14 | M4 |
| `docs/INTERFACES.md`, `docs/security/threat-model.md`, `docs/PERFORMANCE-BACKLOG.md`, `docs/ROADMAP.md` | Enlaces, árbol y versiones de `02-textos.md`, sección 7 | M4 |

## 6. Hitos

### M1 — Preparación

1. Comprobar P-01 y crear `feature/prd-chapters` desde `develop`.
2. Comprobar P-02 y guardar el PRD base desde Git Bash: `git show develop:docs/PRD.md > ../mailquery-plan2-logs/PRD-base.md`.
3. Línea base, con la salida en el directorio de logs:
   - suite completa `python -B -m unittest discover -s tests -t .`: línea de resumen, fallos y saltos conocidos;
   - tablas sin título fuera de bloques de código: se esperan 14 (las de E-05);
   - referencias de sección (`§N`) sin encabezado correspondiente: se esperan 0;
   - IDs O, CU, RF, RNF, ADR y AC: únicos y sin huecos, con máximos O28, CU-09, RF-79, RNF-22, ADR-49 y AC-62.
4. Anotar los resultados en `04-registro.md`. Si un valor no coincide con lo esperado, se anota y se sigue: el plan no corrige el PRD.

**Salida:** rama creada, PRD base guardado, línea base anotada.

### M2 — Partición

1. Crear `docs/prd/` y `docs/prd/anexos/`.
2. Por cada fila de `01-mapa.md`, sección 1: crear el archivo con su frontmatter (sección 2) seguido de las líneas del PRD base de su rango, copiadas sin cambios, en UTF-8 sin BOM (R-06).
3. Aplicar E-01…E-07 de `01-mapa.md`, sección 3.
4. Crear `00-indice.md`, `PLANTILLA-CAMBIO.md` y `HISTORIAL.md` con el texto de `02-textos.md`.
5. Medir R-01 y R-09 (sección 7.2) y comprobar la reconstrucción (sección 7.3). `docs/PRD.md` no se toca (D-06).
6. Commit: `docs(prd): split the PRD into one file per section` (incluye `docs/plan2/` si aún no está en `develop`).

**Salida:** R-01 y R-09 cumplidos; el diff de la sección 7.3 solo muestra E-01…E-07.

### M3 — Prueba de estructura

1. Crear `tests/test_prd_structure.py` según `03-prueba-estructura.md`.
2. Aplicar los cambios del catálogo de pruebas de `03-prueba-estructura.md`, sección 3.
3. `python -B -m unittest discover -s tests -t . -k doc_14` pasa.
4. Prueba negativa: en el árbol de trabajo, duplicar una fila RF de `docs/prd/06-requisitos-funcionales.md`, ejecutar `python -B -m unittest discover -s tests -t . -k doc_14_03`, comprobar que falla y restaurar con `git checkout -- docs/prd/06-requisitos-funcionales.md`. Repetir con un archivo nuevo vacío en `docs/prd/` para DOC-14.06 y borrarlo. Anotar ambas en el registro.
5. Commit: `test(docs): check the structure of the split PRD`.

**Salida:** DOC-14 en verde y las dos pruebas negativas anotadas.

### M4 — Referencias fuera de `docs/prd/`

1. Aplicar las ediciones de `02-textos.md`, secciones 6 y 7, y el enlace de la línea 3 de `docs/tests/TEST-CATALOG.md`.
2. Búsquedas de la sección 7.4.
3. Commit: `docs: point the references to the split PRD`.

**Salida:** las búsquedas de la sección 7.4 dan el resultado esperado.

### M5 — Verificación final

1. Suite completa: resumen sin fallos nuevos respecto de la línea base de M1.
2. DOC-14, R-01 y las búsquedas de la sección 7.4, otra vez sobre el último commit.
3. `git diff --stat develop...HEAD`: solo archivos de la sección 5.
4. Completar `04-registro.md` (estado propuesto, commits, conteos) y hacer commit del registro.
5. Entregar al dueño: commits, R-01 medido, suite y las comprobaciones manuales de Obsidian (sección 7.5).

**Salida:** evidencia completa; el merge espera la orden del dueño (R-08).

## 7. Verificación

### 7.1 Gates

**Tabla: Gates de verificación**

| Gate | Comando | Pasa si |
|---|---|---|
| Suite | `python -B -m unittest discover -s tests -t . > ../mailquery-plan2-logs/suite.log 2>&1` (Git Bash) | Código de salida 0, o el resumen solo lista los fallos y saltos de la línea base |
| DOC-14 | `python -B -m unittest discover -s tests -t . -k doc_14` | Código de salida 0 |
| R-01, R-09 | Script de la sección 7.2 | Añadidas + eliminadas ≤ 299; caracteres de `docs/prd/` ≤ 390.261 |
| Reconstrucción | Sección 7.3 | El diff solo contiene E-01…E-07 |

### 7.2 Medición de R-01

Se compara el PRD base con la reconstrucción en este orden: la cabecera de `00-indice.md` (desde el final del frontmatter hasta la línea anterior a `## Cómo se organiza`), el cuerpo de `HISTORIAL.md`, los capítulos y anexos en el orden de la tabla de `01-mapa.md`, sección 1, y el cuerpo de `GLOSARIO.md`. El resto de la portada y `PLANTILLA-CAMBIO.md` son texto nuevo, no cambios del PRD, y no cuentan. El frontmatter no cuenta. Los finales de línea se normalizan a LF. El script se guarda como `../mailquery-plan2-logs/measure.py` y se ejecuta desde la raíz del checkout:

`python -I ../mailquery-plan2-logs/measure.py ../mailquery-plan2-logs/PRD-base.md docs/prd`

```python
import difflib, pathlib, re, sys

base = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n").split("\n")
root = pathlib.Path(sys.argv[2])
ORDER = (["00-indice.md", "HISTORIAL.md"]
         + [l.split("`")[1] for l in (root.parent / "plan2" / "01-mapa.md").read_text(encoding="utf-8").splitlines()
            if re.match(r"^\| `((?!00)\d\d|anexos/)", l)]
         + ["GLOSARIO.md"])  # capítulos y anexos en el orden de la tabla del mapa

def body(p):
    t = (root / p).read_text(encoding="utf-8").replace("\r\n", "\n")
    t = re.sub(r"\A---\n.*?\n---\n\n?", "", t, flags=re.S)
    if p == "00-indice.md":
        t = t.split("\n## Cómo se organiza")[0] + "\n"
    return t.split("\n")[:-1] if t.endswith("\n") else t.split("\n")

new = [line for p in ORDER for line in body(p)]
pathlib.Path(sys.argv[1]).with_name("reconstruccion.md").write_text("\n".join(new) + "\n", encoding="utf-8")
diff = [d for d in list(difflib.unified_diff(base, new, lineterm="", n=0))[2:] if d[:1] in "+-"]
added = sum(d.startswith("+") for d in diff); removed = sum(d.startswith("-") for d in diff)
print(f"added={added} removed={removed} total={added + removed} limit=299")
chars = sum(len(f.read_text(encoding="utf-8").replace("\r\n", "\n")) for f in root.rglob("*.md"))
base_chars = len("\n".join(base)) + 1
print(f"chars={chars} base={base_chars} increase={(chars - base_chars) / base_chars:.2%} limit={base_chars + base_chars // 10}")
```

El script toma de la tabla de `01-mapa.md`, sección 1, las filas cuyo archivo empieza por dos dígitos distintos de `00` o por `anexos/`, en el orden de la tabla. Si no puede leerlas, el orden se escribe a mano en el script y se anota en el registro.

### 7.3 Reconstrucción

El script de la sección 7.2 deja la reconstrucción en `../mailquery-plan2-logs/reconstruccion.md`. Desde Git Bash:

`git diff --no-index ../mailquery-plan2-logs/PRD-base.md ../mailquery-plan2-logs/reconstruccion.md > ../mailquery-plan2-logs/reconstruccion.diff`

Cada bloque del diff corresponde a uno de E-01…E-07. En el registro se anota a qué E-n corresponde cada bloque.

### 7.4 Búsquedas

**Tabla: Búsquedas de verificación**

| Búsqueda | Resultado esperado |
|---|---|
| `git grep -nE "\]\([^)]*PRD\.md" -- ':!docs/plan' ':!docs/plan2' ':!docs/archive' ':!docs/PRD-v2.2.md' ':!docs/tmp'` | Ninguno |
| `git grep -n "PRD.md#L"` con las mismas exclusiones | Ninguno |
| `git grep -n "docs/PRD.md" -- CLAUDE.md README.md README.es.md` | Ninguno |
| `git grep -nE "v2\.2" -- README.md README.es.md` | Ninguno |
| `git grep -nE "docs/plan|plan2/" -- docs/prd` | Ninguno |
| `git diff --stat develop...HEAD -- src docs/PRD.md docs/plan docs/archive docs/PRD-v2.2.md docs/KNOWN-DEFECTS.md docs/tmp` | Vacío |

### 7.5 Comprobaciones manuales de Obsidian (dueño, opcional)

1. Abrir `docs/` como vault: la carpeta `docs/.obsidian/` no aparece en `git status`.
2. Desde `prd/00-indice.md`, cada enlace del índice abre su archivo.
3. El buscador rápido encuentra "Sección 12.5" y "Glosario" por sus `aliases`.
4. El panel de esquema de `GLOSARIO.md` muestra un encabezado por término.
5. Los marcadores `{…}` de `PLANTILLA-CAMBIO.md` se ven en el modo de lectura.

## 8. Riesgos

**Tabla: Riesgos y mitigaciones**

| Riesgo | Mitigación |
|---|---|
| El PRD cambia entre la redacción del plan y su ejecución | P-02: los cortes se localizan por su primera línea y los rangos se recalculan |
| `core.autocrlf` cambia los finales de línea al copiar | Copia literal; la medición normaliza a LF |
| PowerShell escribe archivos con BOM o en UTF-16 | R-06 y DOC-14.11 |
| Un capítulo cerca del límite de 300 líneas (`15-configuracion.md`: 289 + 5 de frontmatter + 2 de E-05 = 296) | DOC-14.01 lo vigila; la próxima conciliación que lo supere lo parte con el mismo prefijo |
| `docs/PRD.md` sigue existiendo y alguien lo toma por el PRD vigente | Los README, `CLAUDE.md` y los enlaces apuntan a `docs/prd/`; la retirada de `docs/PRD.md` queda para una orden del dueño |
| GitHub muestra el frontmatter como una tabla al principio de cada archivo | Aceptado: es la forma estándar de los `aliases` de Obsidian |
| Las anclas a encabezados no son compatibles entre GitHub y Obsidian | D-04: enlaces solo a archivo |
