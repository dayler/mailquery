# M04 — Detector de contenido activo en adjuntos (A7)

**Lote:** I1 · rama del lote `integration/i1-prep` · **Oleada:** W1 (en paralelo con M01, M02 y M03)
**Rama:** `feature/m04-active-content-scanner`, creada desde la punta de `integration/i1-prep` · **Worktree:** `../mailquery-wt/m04`
**Estado:** ⚪ (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Crear el detector puro de marcadores de contenido activo de RF-62 sobre los bytes de un archivo ya extraído: `pdf-javascript`, `office-macros` y `archive-executable`, sin abrir, ejecutar ni descomprimir nada. La conexión con el comando `attachment` (warning, caché, orden) la hace M09.

## 2. Alcance

**Dentro:** módulo nuevo `src/mailquery/attachments/active_content.py` con:

```python
ACTIVE_CONTENT_TYPES = ("pdf-javascript", "office-macros", "archive-executable")

def active_content_types(path: Path) -> tuple[str, ...]:
    """Ordered subset of ACTIVE_CONTENT_TYPES whose markers appear in the file."""
```

Reglas (RF-62):

- **`pdf-javascript`:** `%PDF-` aparece en los primeros 1.024 bytes y el archivo contiene un nombre PDF `/JavaScript`, `/JS` o `/Launch`, también con caracteres escritos como `#xx` (p. ej. `/J#61vaScript`, `/#4A#53`), seguido de un delimitador PDF (espacio en blanco, `/`, `<`, `>`, `[`, `]`, `(`, `)`, `{`, `}`, `%`) o del final del archivo. Se decodifican los `#xx` del nombre antes de comparar; la comparación distingue mayúsculas (los nombres PDF son sensibles a mayúsculas).
- **`office-macros`:** (a) contenedor OLE: el archivo empieza por `D0 CF 11 E0 A1 B1 1A E1` y contiene `"_VBA_PROJECT".encode("utf-16-le")`; o (b) ZIP (definición abajo) con una entrada cuyo último segmento es `vbaProject.bin` (comparación exacta, en cualquier carpeta).
- **`archive-executable`:** ZIP con al menos una entrada cuyo último segmento del nombre (tras el último `/` o `\`) tiene una extensión, simple o encadenada, del catálogo de extensiones peligrosas, comparada como en el catálogo (`attachments.catalog.dangerous_extension`), salvo `.bin`. No se aplican a las entradas las demás reglas de nombre (carpetas, `..`, `:`, controles, reservados).
- **ZIP:** empieza por `PK\x03\x04` y `zipfile.ZipFile(path)` lee su directorio central. Si no puede (`zipfile.BadZipFile` u otra excepción), no se señala ni `office-macros` por ZIP ni `archive-executable`. Solo se usa `namelist()`/`infolist()`; nunca `open()`, `read()`, `extract()` ni `testzip()`. Un ZIP cifrado se lista igual (el bit de cifrado no impide leer los nombres).
- **Lectura:** lineal y sin cargar el archivo entero en memoria: `mmap` de solo lectura (archivos vacíos → sin marcadores, `mmap` no admite longitud 0) y búsquedas `re` sobre bytes.
- Cualquier `OSError` al leer → tupla vacía (el detector nunca hace fallar `attachment`; M09 decide el registro).

**Fuera:** emitir el warning, recorrer `attachments[]`, la caché o el tope de tiempo (M09); bloquear (el catálogo y los *magic bytes* siguen siendo la única barrera); objetos comprimidos de PDF, RAR, 7z, RTF, ZIP anidados.

## 3. Dependencias y ACs

- **Entrada:** ninguna.
- **Salida:** M09 conecta el detector con `attachment`.
- **ACs:** AC-H12 (parte del detector).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Crea | `src/mailquery/attachments/active_content.py` |
| Crea | `tests/test_active_content.py` |
| Crea | `tests/fixtures/active_content_samples.py` (fabrica PDF, OLE y ZIP de prueba en un directorio temporal, incluido el ZIP cifrado de A-05) |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 4, 7, 8), `docs/INTERFACES.md` (sección de `attachments/`) |

No se toca `attachments/__init__.py` (M09 decide si lo exporta).

## 5. Refactorizaciones previas

Ninguna.

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Fixtures | `active_content_samples.py`: PDF con y sin marcadores, OLE con y sin `_VBA_PROJECT`, ZIP con `vbaProject.bin`, `.docx` sin macros con entradas `.bin` propias, ZIP con `factura.pdf.exe`, ZIP con solo PDF, ZIP cifrado (bytes fabricados con el bit 0 de *general purpose flag* en las cabeceras local y central), archivo con `PK\x03\x04` y directorio central roto | 🟢 |
| F2 — Detector | `active_content_types` según la sección 2 | 🟢 |
| F3 — Cierre | Suite completa, evidencia cruda, bloques | 🟢 |

## 7. Tests

Archivo `tests/test_active_content.py`, prefijo nuevo **UT-ACT** ("Contenido activo en adjuntos").

**UT-ACT-01 — `pdf-javascript`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | PDF con `/JavaScript`, con `/JS` y con `/Launch` seguidos de espacio, `<<`, `(` o final del archivo → `("pdf-javascript",)`. |
| .02 | P | Nombres con `#xx` (`/J#61vaScript`, `/#4A#53`) → detectado. |
| .03 | N | `/JavaScriptX`, `/JSON`, `/Launcher` y `/javascript` (minúsculas) no cuentan. |
| .04 | N | `%PDF-` después del byte 1.024 → no es PDF, no se detecta. |
| .05 | N | PDF sin esos nombres → `()`. |
| .06 | B | `%PDF-` cuyo último byte es exactamente el byte 1.024 del archivo (empieza en el desplazamiento 1.019) → es PDF y se detecta. |
| .07 | B | Ramas del decodificador: `#xx` con hexadecimal inválido (`/J#zzavaScript`) no se decodifica ni cuenta; `/JS` justo al final del archivo, sin delimitador, cuenta. |

**UT-ACT-02 — `office-macros`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `.doc`/`.xls` OLE con `_VBA_PROJECT` en UTF-16LE → detectado. |
| .02 | N | OLE sin `_VBA_PROJECT`; `_VBA_PROJECT` en ASCII dentro de un OLE; la cadena UTF-16LE en un archivo que no empieza por la firma OLE → no detectado. |
| .03 | P | ZIP con `xl/vbaProject.bin` y con `vbaProject.bin` en la raíz → detectado. |
| .04 | N | `.docx`, `.xlsx` y `.pptx` sin macros (con carpetas y entradas `.bin` propias del formato, p. ej. `word/embeddings/oleObject1.bin`) → `()`. |

**UT-ACT-03 — `archive-executable`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | ZIP con `docs/factura.pdf.exe` (encadenada) y con `run.bat` → detectado. |
| .02 | P | ZIP cifrado con una entrada `.exe` → detectado. |
| .03 | P | Separador `\` en el nombre (`dir\\x.scr`) → se toma el último segmento. |
| .04 | N | ZIP con solo PDF, con solo `.bin` o con `..`/`:` en nombres inocuos → `()`. |
| .05 | N | Archivo que empieza por `PK\x03\x04` con directorio central ilegible → `()`. |
| .06 | P | Entrada `RUN.EXE` (mayúsculas) → detectado, porque la extensión se compara como en el catálogo (sin distinguir mayúsculas). |
| .07 | N | Entrada de directorio terminada en `/` (`payload.exe/`): su último segmento está vacío y no cuenta; un ZIP solo con esa entrada → `()`. |
| .08 | N | `zipfile.ZipFile` lanza una excepción distinta de `BadZipFile` (simulada con `mock.patch`, p. ej. `ValueError` o `OSError`) → `()` sin excepción. |

**UT-ACT-04 — Propiedades del detector**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un ZIP con `vbaProject.bin` y un `.exe` da los dos tipos en el orden de `ACTIVE_CONTENT_TYPES`. |
| .02 | B | Nunca descomprime: con `mock.patch.object(zipfile.ZipFile, "open")`, `read` y `extract` que fallan si se llaman, todos los casos anteriores dan el mismo resultado. |
| .03 | B | Archivo vacío y archivo inexistente → `()` sin excepción. |
| .04 | B | Determinismo: dos llamadas sobre el mismo archivo dan el mismo resultado. |

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_act_
python -B -m unittest tests.test_active_content -v
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
python -B -m coverage report --include=src/mailquery/attachments/active_content.py --fail-under=85
```

## 8. Tests existentes afectados

Ninguno.

## 9. Documentación

- Bloque para `INTERFACES.md`, sección `attachments/`: `active_content.py`, `ACTIVE_CONTENT_TYPES`, `active_content_types(path)`, garantías (sin descomprimir, `mmap`, nunca lanza).
- Bloques para `TEST-CATALOG.md`: sección 2, prefijo `UT-ACT` → `tests/test_active_content.py`; sección 4, `tests/fixtures/active_content_samples.py`; sección 8, UT-ACT-01–UT-ACT-04; sección 7, fila parcial de AC-H12 (delta `PRD-v2.2.md`).
- README, skill, ayudas: sin cambios (M09).

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: fila "Inspección de adjuntos (F1)" → nota "detector implementado"; estado sigue `Pendiente` hasta M09.
- Tabla de supersesión y checklist: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupo `test_ut_act_` solo; (c) goldens: ninguno; (d) UT-ACT-01–04 con AC; (e) `git diff --check` y `git diff --stat integration/i1-prep...HEAD`; (f) cómo se fabricó el ZIP cifrado, riesgos, decisiones y pendientes; (g) cobertura: salida completa de `coverage report` y de `coverage report --include=src/mailquery/attachments/active_content.py --fail-under=85`, con sus líneas sin cubrir y la justificación de cada pragma nuevo. Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] `active_content_types` cumple RF-62, sin descomprimir y con lectura lineal.
- [ ] UT-ACT-01–UT-ACT-04 verdes solos.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=src/mailquery/attachments/active_content.py --fail-under=85` verde; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-13 | F1 | `tests/fixtures/active_content_samples.py` con PDF, OLE y ZIP de prueba; el ZIP cifrado activa el bit 0 en las cabeceras local y central y el ZIP roto conserva la firma local sin directorio central legible. |
| 2026-11-13 | F2 | `src/mailquery/attachments/active_content.py` con `ACTIVE_CONTENT_TYPES` y `active_content_types`; lectura con `mmap` de solo lectura y sin descomprimir. |
| 2026-11-13 | F3 | UT-ACT-01–04 verdes solos, suite completa y cobertura medidas; informe con evidencia y bloques entregado al orquestador. |
