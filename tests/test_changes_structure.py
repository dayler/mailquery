"""Structure checks for the change units (DOC-15).

A change unit is a Markdown file in ``docs/changes/`` that defines a change of
the product: its requirement, its acceptance criteria, the PRD sections to
reconcile and the reconciliation checklist. The checks take the directory to
validate, so they run on the repository and on sample units written to a
temporary directory.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from tests.test_prd_structure import DOCS_ROOT, PRD_DIR, classify, index_table, read_lines

CHANGES_DIR = DOCS_ROOT / "docs" / "changes"
PROTOCOL_NAME = "PROTOCOLO.md"
TEMPLATE_NAME = "PLANTILLA.md"
NOT_UNITS = (PROTOCOL_NAME, TEMPLATE_NAME)

REQUIREMENT = "Requerimiento"
CRITERIA = "Criterios de aceptación"
RECONCILIATION = "Conciliación con el PRD"
CHECKLIST = "Checklist de conciliación"
SECTIONS = (
    "Estado",
    "Contexto",
    REQUIREMENT,
    CRITERIA,
    "IDs",
    "Dependencias",
    "Decisiones",
    "Glosario",
    RECONCILIATION,
    "Documentos consumidores",
    CHECKLIST,
    "Desviaciones aprobadas",
)
HEADER_FIELDS = ("Tipo", "Base", "Fecha", "Aprobación", "Paquete")
ID_LINES = ("- Crea:", "- Elimina:")
NOT_APPROVED = "—"
NO_DEPENDENCIES = "Ninguna"
NO_DECISIONS = "Ninguna"
NO_GLOSSARY = "Sin cambios"
NO_RECONCILIATION = "Ninguna"
NO_CONSUMERS = "Ninguno"
CONSUMER_STATES = ("pendiente", "actualizado", "sin cambio")
CLASSES_TABLE = "Clases de cambio del paquete"
TREATMENT_TABLE = "Tratamiento de cada tipo de cambio"
NO_UNIT = "Sin unidad"
PLAN_DIR = "docs/plan"
DEFECT = "defecto"

RECONCILIATION_COLUMNS = ("ID", "Contrato", "Archivo", "Ancla", "Qué cambia", "Estado")
NEW_FILE = "(nuevo)"
NO_ANCHOR = "—"
ROW_STATES = {
    "borrador": ("pendiente",),
    "aprobado": ("pendiente", "implementado"),
    "implementado": ("implementado",),
    "conciliado": ("conciliado",),
}
COMMON_ITEMS_TABLE = "Ítems comunes del checklist de conciliación"
CHECKLIST_COLUMNS = ("ID", "Ítem", "Cómo se verifica", "Estado")
CHECKLIST_STATES = ("pendiente", "cumplido", "no aplica")

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
HEADER_RE = re.compile(r"^\*\*([^:*]+):\*\* (.+)$")
STATE_RE = re.compile(r"^(borrador|aprobado|implementado|conciliado \(\d{4}-\d{2}-\d{2}\))$")
APPROVAL_RE = re.compile(r"^[^,]+, \d{4}-\d{2}-\d{2}$")
PACKAGE_RE = re.compile(r"^\d+\.\d+\.\d+ \((mayor|menor|parche|sin efecto)\)$")
ITEM_RE = re.compile(r"^- (.+?): (.*)$")
HEADER_VALUE_RES = {
    "Base": re.compile(r"^PRD \d+\.\d+$"),
    "Fecha": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "Paquete": PACKAGE_RE,
}
KIND = r"(O|CU-|RF-|RNF-|ADR-|AC-)"
BEFORE = r"(?<![A-Za-z0-9_-])"
AFTER = r"(?![A-Za-z0-9])"
ID_RE = re.compile(rf"{BEFORE}{KIND}(\d+){AFTER}")
MARKER_RE = re.compile(rf"{BEFORE}{KIND}x(\d+){AFTER}")
RANGE_RE = re.compile(rf"{BEFORE}{KIND}(x?)(\d+)…{KIND}(x?)(\d+){AFTER}")
DEFINITION_RES = (
    re.compile(r"^\| (O|CU-|RF-|RNF-|ADR-)(x?\d+) \|"),
    re.compile(r"^\*\*(AC-)(x?\d+)\.\*\*"),
)
UNIT_DEFINITION_RE = re.compile(r"^\*\*(O|CU-|RF-|RNF-|ADR-|AC-)(x?\d+)\.")
CRITERION_KIND = "AC-"
FILE_CELL_RE = re.compile(r"^`([^`]+\.md)`( \(nuevo\))?$")
ANCHOR_RE = re.compile(rf"``\s(.+?)\s``|`([^`]+)`|{BEFORE}{KIND}(\d+){AFTER}")
TABLE_TITLE = "**Tabla: "

OBJECTIVES_FILE = "03-objetivos.md"
REQUIREMENTS_FILE = "06-requisitos-funcionales.md"
DEFAULT = "<default>"
OBJECTIVE_START_RE = re.compile(r"^\| O\d+ \|")

# An ID is (kind, number) when it is real and (kind, "x<n>") when it is a marker.
Ident = tuple[str, "int | str"]


@dataclass
class Unit:
    """A parsed change unit: title, header fields and sections."""

    path: Path
    title: str = ""
    header: dict[str, list[str]] = field(default_factory=dict)
    sections: list[tuple[str, list[tuple[int, str, bool]]]] = field(default_factory=list)

    @property
    def name(self) -> str:
        """File name without the extension."""
        return self.path.stem

    def section(self, title: str) -> list[tuple[int, str, bool]]:
        """Classified lines of the first section with this title, or an empty list."""
        for name, rows in self.sections:
            if name == title:
                return rows
        return []

    def text_lines(self, title: str) -> list[str]:
        """Non-empty lines of a section outside code blocks, stripped."""
        return [text.strip() for _, text, in_code in self.section(title) if not in_code and text.strip()]

    def table(self, section: str, title: str) -> tuple[list[str], list[list[str]]] | None:
        """Header cells and data rows of the table of a section that carries this title.

        None when the section has no such title or no table follows it.
        """
        lines = [text for _, text, in_code in self.section(section) if not in_code]
        marker = f"{TABLE_TITLE}{title}**"
        positions = [index for index, line in enumerate(lines) if line.strip() == marker]
        if not positions:
            return None
        collected: list[list[str]] = []
        for line in lines[positions[0] + 1:]:
            if not line.strip() and not collected:
                continue
            if not line.startswith("|"):
                break
            collected.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        if len(collected) < 2:
            return None
        return collected[0], collected[2:]

    @property
    def kind(self) -> str:
        """Unit type of the header, or an empty string."""
        return (self.header.get("Tipo") or [""])[0]

    @property
    def state(self) -> str:
        """First line of the state section, or an empty string."""
        lines = self.text_lines("Estado")
        return lines[0] if lines else ""

    @property
    def state_word(self) -> str:
        """First word of the state."""
        return self.state.split(" ")[0] if self.state else ""

    @property
    def is_open(self) -> bool:
        """Whether the unit is not reconciled."""
        return self.state_word != "conciliado"


def unit_files(directory: Path) -> list[Path]:
    """Markdown files in the first level of the directory that are change units, sorted by name."""
    return sorted(path for path in directory.glob("*.md") if path.name not in NOT_UNITS)


def table_rows(path: Path, title: str) -> list[list[str]]:
    """Data rows of the table of a file that carries this title, as cell lists."""
    lines = read_lines(path)
    start = lines.index(f"{TABLE_TITLE}{title}**")
    rows = []
    for line in lines[start + 1:]:
        if not line.strip() and not rows:
            continue
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows[2:]


def classes_by_type() -> dict[str, tuple[str, ...]]:
    """Package classes that each unit type allows, from the package-classes table of the protocol."""
    result: dict[str, list[str]] = {}
    for row in table_rows(CHANGES_DIR / PROTOCOL_NAME, CLASSES_TABLE):
        for kind in re.findall(r"`([^`]+)`", row[2]):
            result.setdefault(kind, []).append(row[0].strip("`"))
    return {kind: tuple(classes) for kind, classes in result.items()}


def next_free_ids() -> dict[str, int]:
    """Next free number of each ID kind, from the PRD cover page."""
    result = {}
    for cell in index_table("Próximos IDs libres")[0]:
        match = ID_RE.fullmatch(cell)
        if match:
            result[match.group(1)] = int(match.group(2))
    return result


def common_items() -> list[str]:
    """Item text of each row of the common-items table of the protocol, in order."""
    return [row[0] for row in table_rows(CHANGES_DIR / PROTOCOL_NAME, COMMON_ITEMS_TABLE)]


def parse(path: Path) -> Unit:
    """Read a unit: title, header fields before the first section, and sections."""
    unit = Unit(path=path)
    current: list[tuple[int, str, bool]] | None = None
    for number, text, in_code in classify(read_lines(path)):
        if not in_code and text.startswith("## "):
            current = []
            unit.sections.append((text[3:].strip(), current))
            continue
        if current is not None:
            current.append((number, text, in_code))
            continue
        if in_code:
            continue
        if text.startswith("# ") and not unit.title:
            unit.title = text[2:].strip()
        match = HEADER_RE.match(text)
        if match:
            unit.header.setdefault(match.group(1), []).append(match.group(2).strip())
    return unit


def id_line(unit: Unit, label: str) -> tuple[list[Ident], list[str]]:
    """IDs and markers of a line of the IDs section, ranges expanded, and the ranges that are not valid.

    A range joins two real IDs or two markers of the same kind, in ascending order.
    """
    line = next((l for l in unit.text_lines("IDs") if l.startswith(label)), "")
    result: list[Ident] = []
    invalid = []
    for match in RANGE_RE.finditer(line):
        kind, marker, first, kind2, marker2, last = match.groups()
        if kind != kind2 or marker != marker2 or int(last) < int(first):
            invalid.append(match.group(0))
            continue
        for number in range(int(first), int(last) + 1):
            result.append((kind, f"x{number}" if marker else number))
    rest = RANGE_RE.sub(" ", line)
    if "…" in rest:
        invalid.append(rest.strip())
    result.extend((match.group(1), int(match.group(2))) for match in ID_RE.finditer(rest))
    result.extend((match.group(1), f"x{match.group(2)}") for match in MARKER_RE.finditer(rest))
    return result, invalid


def definitions(lines: list[str]) -> set[Ident]:
    """IDs that these lines define: the first cell of a table row or the label of an acceptance criterion."""
    result: set[Ident] = set()
    for line in lines:
        for pattern in DEFINITION_RES:
            match = pattern.match(line)
            if match:
                tail = match.group(2)
                result.add((match.group(1), tail if tail.startswith("x") else int(tail)))
    return result


def show(ident: Ident) -> str:
    """Text form of an ID."""
    return f"{ident[0]}{ident[1]}"


def dependency_names(unit: Unit) -> list[str]:
    """Unit names listed in the dependencies section; empty when it says there are none."""
    lines = unit.text_lines("Dependencias")
    if lines == [NO_DEPENDENCIES]:
        return []
    return [line[2:].strip() for line in lines if line.startswith("- ")]


def dependency_closure(unit: Unit, by_name: dict[str, Unit]) -> set[str]:
    """Names of the units this one depends on, directly or through other units."""
    seen: set[str] = set()
    pending = dependency_names(unit)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        if name in by_name:
            pending.extend(dependency_names(by_name[name]))
    return seen


def is_resolvable(unit: Unit, by_name: dict[str, Unit]) -> bool:
    """Whether what the unit says about the PRD must hold now: it is open and no dependency of it is open."""
    return unit.is_open and not any(
        name in by_name and by_name[name].is_open for name in dependency_names(unit)
    )


def section_definitions(unit: Unit, title: str) -> set[Ident]:
    """IDs that a section of a unit defines: paragraphs that start with a bold ID, outside code blocks."""
    result: set[Ident] = set()
    for _, text, in_code in unit.section(title):
        match = None if in_code else UNIT_DEFINITION_RE.match(text)
        if match:
            tail = match.group(2)
            result.add((match.group(1), tail if tail.startswith("x") else int(tail)))
    return result


def prd_definitions(prd_dir: Path) -> set[Ident]:
    """IDs that the files of the PRD define."""
    result: set[Ident] = set()
    for path in sorted(prd_dir.rglob("*.md")):
        result |= definitions(read_lines(path))
    return result


def check_files(directory: Path) -> list[str]:
    """The directory has no subdirectories and unit file names are lowercase words joined by hyphens.

    Every unit and the template have a quoted alias, the cambio tag and no byte order mark.
    """
    problems = [f"{path.name}: subdirectory" for path in sorted(directory.iterdir()) if path.is_dir()]
    paths = unit_files(directory)
    for path in paths:
        if not NAME_RE.match(path.name):
            problems.append(f"{path.name}: invalid file name")
    template = directory / TEMPLATE_NAME
    for path in paths + ([template] if template.is_file() else []):
        if path.read_bytes().startswith(b"\xef\xbb\xbf"):
            problems.append(f"{path.name}: byte order mark")
        lines = read_lines(path)
        if not lines or lines[0] != "---" or "---" not in lines[1:]:
            problems.append(f"{path.name}: no frontmatter")
            continue
        front = lines[1:lines.index("---", 1)]
        aliases = [l for l in front if l.startswith("aliases: [")]
        tags = [l for l in front if l.startswith("tags: [")]
        if not aliases or not re.search(r'"[^"]+"', aliases[0]):
            problems.append(f"{path.name}: no quoted alias")
        tag_list = re.match(r"^tags: \[(.*)\]\s*$", tags[0]) if tags else None
        if not tag_list or "cambio" not in [t.strip().strip("\"'") for t in tag_list.group(1).split(",")]:
            problems.append(f"{path.name}: no cambio tag")
    return problems


def check_header(units: list[Unit], classes: dict[str, tuple[str, ...]], strict: bool = True) -> list[str]:
    """Each unit has a title and one value per header field.

    With strict, the values have their format and the package class is one that
    the unit type allows.
    """
    problems = []
    for unit in units:
        label = unit.path.name
        if not unit.title:
            problems.append(f"{label}: no title")
        for name in HEADER_FIELDS:
            values = unit.header.get(name, [])
            if len(values) != 1:
                problems.append(f"{label}: {len(values)} values for {name}")
            elif strict and name == "Tipo" and values[0] not in classes:
                problems.append(f"{label}: invalid Tipo {values[0]!r}")
            elif strict and name in HEADER_VALUE_RES and not HEADER_VALUE_RES[name].match(values[0]):
                problems.append(f"{label}: invalid {name} {values[0]!r}")
        kind = (unit.header.get("Tipo") or [""])[0]
        package = PACKAGE_RE.match((unit.header.get("Paquete") or [""])[0])
        if strict and kind in classes and package and package.group(1) not in classes[kind]:
            problems.append(f"{label}: class {package.group(1)!r} is not valid for type {kind!r}")
    return problems


def check_sections(units: list[Unit]) -> list[str]:
    """Each unit has exactly the required sections, in order."""
    return [
        f"{unit.path.name}: sections {[name for name, _ in unit.sections]}"
        for unit in units
        if tuple(name for name, _ in unit.sections) != SECTIONS
    ]


def check_states(units: list[Unit]) -> list[str]:
    """Each state has a valid form, and an errata is never in the implemented state.

    A draft has no approval; any other state has the approver and the date in the header.
    """
    problems = []
    for unit in units:
        if not STATE_RE.match(unit.state):
            problems.append(f"{unit.path.name}: invalid state {unit.state!r}")
            continue
        if unit.header.get("Tipo") == ["errata"] and unit.state_word == "implementado":
            problems.append(f"{unit.path.name}: an errata has no implemented state")
        approval = (unit.header.get("Aprobación") or [""])[0]
        if unit.state_word == "borrador":
            if approval != NOT_APPROVED:
                problems.append(f"{unit.path.name}: a draft has an approval")
        elif not APPROVAL_RE.match(approval):
            problems.append(f"{unit.path.name}: invalid approval {approval!r}")
    return problems


def check_ids(units: list[Unit], next_free: dict[str, int], prd_dir: Path) -> list[str]:
    """The IDs section is well formed and agrees with the requirement of the unit.

    The section has the created line and the removed line, with valid ranges.
    Drafts create only markers and other units hold no markers. In an open
    unit, the created IDs are exactly the new IDs it defines: acceptance
    criteria in the criteria section and every other kind in the requirement
    section; an ID created by an open unit it depends on is not new. When what
    the unit says about the PRD must hold now, every removed ID is defined in
    the PRD. The IDs created by approved and implemented units are unique and
    continue, per kind, from the next free ID of the PRD.
    """
    by_name = {unit.name: unit for unit in units}
    created_by = {unit.name: set(id_line(unit, ID_LINES[0])[0]) for unit in units}
    in_prd = prd_definitions(prd_dir)
    problems = []
    reserved: dict[str, list[tuple[int, str]]] = {}
    for unit in units:
        label = unit.path.name
        labels = [line.split(":")[0] + ":" for line in unit.text_lines("IDs")]
        if labels != list(ID_LINES):
            problems.append(f"{label}: the IDs section has the lines {labels}")
        created, invalid = id_line(unit, ID_LINES[0])
        removed, invalid_removed = id_line(unit, ID_LINES[1])
        problems.extend(f"{label}: invalid range {text!r}" for text in invalid + invalid_removed)
        real = [ident for ident in created if isinstance(ident[1], int)]
        word = unit.state_word
        if word == "borrador":
            if real:
                problems.append(f"{label}: a draft creates real IDs")
        else:
            body = "\n".join(text for _, rows in unit.sections for _, text, _ in rows)
            if MARKER_RE.search(body):
                problems.append(f"{label}: markers outside a draft")
        if unit.is_open:
            inherited: set[Ident] = set()
            for name in dependency_closure(unit, by_name):
                if name in by_name and by_name[name].is_open:
                    inherited |= created_by[name]
            new = set()
            for title in (REQUIREMENT, CRITERIA):
                for ident in section_definitions(unit, title) - inherited:
                    kind, tail = ident
                    if isinstance(tail, str) or tail >= next_free.get(kind, 0):
                        new.add(ident)
                        if (kind == CRITERION_KIND) != (title == CRITERIA):
                            problems.append(f"{label}: {show(ident)} defined in the section {title!r}")
            if new != set(created):
                problems.append(
                    f"{label}: creates {sorted(map(show, created))} "
                    f"but it defines {sorted(map(show, new))}"
                )
        if is_resolvable(unit, by_name):
            for ident in removed:
                if ident not in in_prd:
                    problems.append(f"{label}: removes {show(ident)}, which the PRD does not define")
        for kind, number in real:
            if kind not in next_free:
                problems.append(f"{label}: unknown ID kind {kind}")
            elif word in ("aprobado", "implementado"):
                reserved.setdefault(kind, []).append((number, label))
    for kind, entries in sorted(reserved.items()):
        numbers = sorted(number for number, _ in entries)
        expected = list(range(next_free[kind], next_free[kind] + len(numbers)))
        if numbers != expected:
            names = sorted({name for _, name in entries})
            problems.append(f"{kind}: reserved {numbers} in {names}, expected {expected}")
    return problems


def check_dependencies(units: list[Unit]) -> list[str]:
    """The dependencies section says there are none or lists one unit name per line.

    An open unit depends only on existing units other than itself, and no
    dependency chain leads back to the unit.
    """
    by_name = {unit.name: unit for unit in units}
    problems = []
    for unit in units:
        lines = unit.text_lines("Dependencias")
        if lines == [NO_DEPENDENCIES]:
            continue
        if not lines or any(not re.match(r"^- [a-z0-9]+(-[a-z0-9]+)*$", line) for line in lines):
            problems.append(f"{unit.path.name}: dependencies are neither {NO_DEPENDENCIES!r} nor a list of unit names")
            continue
        if not unit.is_open:
            continue
        for name in dependency_names(unit):
            if name == unit.name or name not in by_name:
                problems.append(f"{unit.path.name}: unknown dependency {name!r}")
        if unit.name in dependency_closure(unit, by_name):
            problems.append(f"{unit.path.name}: dependency cycle")
    return problems


def check_requirement(units: list[Unit]) -> list[str]:
    """Each unit has a requirement and acceptance criteria, and no line of it cites a plan."""
    problems = []
    for unit in units:
        label = unit.path.name
        for title in (REQUIREMENT, CRITERIA):
            if not any(text.strip() for _, text, _ in unit.section(title)):
                problems.append(f"{label}: empty section {title!r}")
        for _, rows in unit.sections:
            for number, text, _ in rows:
                if PLAN_DIR in text:
                    problems.append(f"{label}:{number}: the unit cites a plan")
    return problems


def numbered(rows: list[list[str]], prefix: str) -> bool:
    """Whether the first cells of the rows are prefix-01, prefix-02 and so on, without gaps."""
    return [row[0] for row in rows] == [f"{prefix}-{number:02d}" for number in range(1, len(rows) + 1)]


def anchors(cell: str) -> list[str]:
    """Anchors of a cell: the text of each code span and each ID outside the code spans."""
    result = []
    for match in ANCHOR_RE.finditer(cell):
        double, single, kind, number = match.groups()
        result.append(double or single or f"{kind}{number}")
    return result


def anchor_lines(path: Path, anchor: str) -> int:
    """Number of lines of a PRD file that an anchor selects.

    An ID selects the lines that define it. Any other anchor selects the lines
    that start with it, or whose first table cell starts with it.
    """
    lines = read_lines(path)
    ident = ID_RE.fullmatch(anchor)
    if ident:
        wanted = (ident.group(1), int(ident.group(2)))
        return sum(1 for line in lines if wanted in definitions([line]))
    return sum(1 for line in lines if line.startswith(anchor) or line.startswith(f"| {anchor}"))


def check_reconciliation(units: list[Unit], prd_dir: Path) -> list[str]:
    """Each unit has a well-formed reconciliation table, or says there is none.

    Only a defect unit may have none. The table has the required columns and
    at least one row; the rows are numbered without gaps and the contract and
    the change are not empty. The state of each row is one that the state of
    the unit allows. In an open unit, every row names one PRD file and at
    least one anchor; a row for a new file has no anchor. When what the unit
    says about the PRD must hold now, the file exists and each anchor selects
    exactly one line of it, and a new file does not exist yet.
    """
    by_name = {unit.name: unit for unit in units}
    problems = []
    for unit in units:
        label = unit.path.name
        if unit.text_lines(RECONCILIATION) == [NO_RECONCILIATION]:
            if unit.kind != DEFECT:
                problems.append(f"{label}: only a {DEFECT} unit has no reconciliation table")
            continue
        table = unit.table(RECONCILIATION, RECONCILIATION)
        if table is None:
            problems.append(f"{label}: no reconciliation table")
            continue
        header, rows = table
        if tuple(header) != RECONCILIATION_COLUMNS:
            problems.append(f"{label}: reconciliation columns {header}")
            continue
        if not rows:
            problems.append(f"{label}: reconciliation table without rows")
        if any(len(row) != len(RECONCILIATION_COLUMNS) for row in rows):
            problems.append(f"{label}: a reconciliation row does not have {len(RECONCILIATION_COLUMNS)} cells")
            continue
        if not numbered(rows, "RC"):
            problems.append(f"{label}: reconciliation IDs {[row[0] for row in rows]}")
        allowed = ROW_STATES.get(unit.state_word, ())
        resolvable = is_resolvable(unit, by_name)
        for identifier, contract, file_cell, anchor_cell, what, state in rows:
            where = f"{label}: {identifier}"
            if not contract or not what:
                problems.append(f"{where}: empty cell")
            if state not in allowed:
                problems.append(f"{where}: state {state!r} in a unit {unit.state_word!r}")
            if not unit.is_open:
                continue
            file_match = FILE_CELL_RE.match(file_cell)
            if not file_match:
                problems.append(f"{where}: invalid file cell {file_cell!r}")
                continue
            name, is_new = file_match.groups()
            target = prd_dir / name
            if is_new:
                if anchor_cell != NO_ANCHOR:
                    problems.append(f"{where}: a new file has no anchor")
                if resolvable and target.exists():
                    problems.append(f"{where}: {name} already exists")
                continue
            found = anchors(anchor_cell)
            if not found:
                problems.append(f"{where}: no anchor")
            if not resolvable:
                continue
            if not target.is_file():
                problems.append(f"{where}: missing {name}")
                continue
            for anchor in found:
                count = anchor_lines(target, anchor)
                if count != 1:
                    problems.append(f"{where}: {count} lines of {name} match the anchor {anchor!r}")
    return problems


def check_checklist(units: list[Unit], common: list[str]) -> list[str]:
    """Each unit has a well-formed reconciliation checklist that starts with the common items.

    The table has the required columns, its rows are numbered without gaps,
    no cell is empty and every state is valid. No item is pending once the
    unit is reconciled.
    """
    problems = []
    for unit in units:
        label = unit.path.name
        table = unit.table(CHECKLIST, CHECKLIST)
        if table is None:
            problems.append(f"{label}: no checklist table")
            continue
        header, rows = table
        if tuple(header) != CHECKLIST_COLUMNS:
            problems.append(f"{label}: checklist columns {header}")
            continue
        if any(len(row) != len(CHECKLIST_COLUMNS) for row in rows):
            problems.append(f"{label}: a checklist row does not have {len(CHECKLIST_COLUMNS)} cells")
            continue
        if not numbered(rows, "CL"):
            problems.append(f"{label}: checklist IDs {[row[0] for row in rows]}")
        items = [row[1] for row in rows]
        if len(items) < len(common) or any(not item.startswith(text) for item, text in zip(items, common)):
            problems.append(f"{label}: the checklist does not start with the common items")
        for identifier, item, how, state in rows:
            if not item or not how:
                problems.append(f"{label}: {identifier}: empty cell")
            if state not in CHECKLIST_STATES:
                problems.append(f"{label}: {identifier}: invalid state {state!r}")
            elif state == "pendiente" and not unit.is_open:
                problems.append(f"{label}: {identifier} is pending in a reconciled unit")
    return problems


def check_consumers(units: list[Unit]) -> list[str]:
    """Each unit says it has no consumer documents or lists them with a valid state.

    No consumer document is pending once the unit is implemented or reconciled.
    """
    problems = []
    for unit in units:
        lines = unit.text_lines("Documentos consumidores")
        if lines == [NO_CONSUMERS]:
            continue
        if not lines:
            problems.append(f"{unit.path.name}: no consumer documents")
        for line in lines:
            match = ITEM_RE.match(line)
            if not match or match.group(2).strip() not in CONSUMER_STATES:
                problems.append(f"{unit.path.name}: invalid consumer document line {line!r}")
            elif match.group(2).strip() == "pendiente" and unit.state_word in ("implementado", "conciliado"):
                problems.append(f"{unit.path.name}: {match.group(1)} is pending in state {unit.state_word}")
    return problems


def check_tables(directory: Path) -> list[str]:
    """Every table outside code blocks, in any Markdown file of the directory, has a title line right above it."""
    problems = []
    for path in sorted(directory.glob("*.md")):
        previous = ""
        previous_is_table = False
        for number, text, in_code in classify(read_lines(path)):
            is_table = not in_code and text.startswith("|")
            if is_table and not previous_is_table and not previous.startswith(TABLE_TITLE):
                problems.append(f"{path.name}:{number}")
            previous_is_table = is_table
            if text.strip():
                previous = text
    return problems


def check_all(directory: Path) -> dict[str, list[str]]:
    """Problems of every check on the units of a directory, by check name."""
    units = [parse(path) for path in unit_files(directory)]
    return {
        "files": check_files(directory),
        "header": check_header(units, classes_by_type()),
        "sections": check_sections(units),
        "states": check_states(units),
        "ids": check_ids(units, next_free_ids(), PRD_DIR),
        "dependencies": check_dependencies(units),
        "requirement": check_requirement(units),
        "reconciliation": check_reconciliation(units, PRD_DIR),
        "checklist": check_checklist(units, common_items()),
        "consumers": check_consumers(units),
        "tables": check_tables(directory),
    }


def objective_rows() -> list[tuple[str, str]]:
    """(row start up to the second pipe, whole line) of each objective row of the PRD."""
    result = []
    for line in read_lines(PRD_DIR / OBJECTIVES_FILE):
        match = OBJECTIVE_START_RE.match(line)
        if match:
            result.append((match.group(0), line))
    return result


def first_objective() -> str:
    """ID of the first objective row of the PRD."""
    return objective_rows()[0][0].strip("| ")


def reconciliation_table(
    rows: list[tuple[str, str, str]], columns: tuple[str, ...] = RECONCILIATION_COLUMNS
) -> str:
    """Markdown of a reconciliation table with one row per (file cell, anchor cell, state)."""
    lines = [f"{TABLE_TITLE}{RECONCILIATION}**", "", "| " + " | ".join(columns) + " |", "|---" * len(columns) + "|"]
    for number, (file_cell, anchor_cell, state) in enumerate(rows, start=1):
        lines.append(f"| RC-{number:02d} | Sample contract | {file_cell} | {anchor_cell} | Sample change | {state} |")
    return "\n".join(lines)


def objective_row(state: str, anchor: str | None = None) -> tuple[str, str, str]:
    """A reconciliation row on the objectives file, anchored at the first objective by default."""
    return (f"`{OBJECTIVES_FILE}`", first_objective() if anchor is None else anchor, state)


def checklist_table(state: str, items: list[str] | None = None) -> str:
    """Markdown of a checklist with these items, the common ones by default, all in one state."""
    lines = [f"{TABLE_TITLE}{CHECKLIST}**", "", "| " + " | ".join(CHECKLIST_COLUMNS) + " |", "|---|---|---|---|"]
    for number, item in enumerate(common_items() if items is None else items, start=1):
        lines.append(f"| CL-{number:02d} | {item} | Sample check | {state} |")
    return "\n".join(lines)


def sample(
    *,
    kind: str = "funcionalidad",
    package: str = "3.0.0 (menor)",
    state: str = "aprobado",
    approval: str = "owner, 2026-01-02",
    requirement: str = "Sample behavior.",
    criteria: str = "- Sample criterion.",
    created: str = "—",
    removed: str = "—",
    dependencies: str = NO_DEPENDENCIES,
    decisions: str = NO_DECISIONS,
    glossary: str = NO_GLOSSARY,
    reconciliation: str = DEFAULT,
    consumers: str = "- `README.md`: sin cambio",
    checklist: str = DEFAULT,
) -> str:
    """Text of a unit that is valid by default: approved, with no new IDs and one reconciliation row.

    By default the reconciliation row and the checklist items carry the state
    that matches the state of the unit.
    """
    word = state.split(" ")[0]
    if reconciliation == DEFAULT:
        reconciliation = reconciliation_table([objective_row(ROW_STATES.get(word, ("pendiente",))[0])])
    if checklist == DEFAULT:
        checklist = checklist_table("cumplido" if word == "conciliado" else "pendiente")
    return (
        '---\naliases: ["Sample unit"]\ntags: [cambio]\n---\n\n'
        "# Sample unit\n\n"
        f"**Tipo:** {kind}\n**Base:** PRD 2.4\n**Fecha:** 2026-01-01\n"
        f"**Aprobación:** {approval}\n**Paquete:** {package}\n\n"
        f"## Estado\n\n{state}\n\n"
        "## Contexto\n\nContext text.\n\n"
        f"## {REQUIREMENT}\n\n{requirement}\n\n"
        f"## {CRITERIA}\n\n{criteria}\n\n"
        f"## IDs\n\n- Crea: {created}\n- Elimina: {removed}\n\n"
        f"## Dependencias\n\n{dependencies}\n\n"
        f"## Decisiones\n\n{decisions}\n\n"
        f"## Glosario\n\n{glossary}\n\n"
        f"## {RECONCILIATION}\n\n{reconciliation}\n\n"
        f"## Documentos consumidores\n\n{consumers}\n\n"
        f"## {CHECKLIST}\n\n{checklist}\n\n"
        "## Desviaciones aprobadas\n\nNinguna\n"
    )


def requirement_rows(identifiers: list[str]) -> str:
    """Markdown of one requirement per ID: a paragraph that starts with the bold ID and title, and a rule."""
    return "\n\n".join(f"**{identifier}. Sample requirement.**\n\n- Sample rule." for identifier in identifiers)


def sample_requirements(first: int, count: int = 1, **values: str) -> str:
    """Text of a valid approved unit that defines consecutive requirements starting at this number."""
    fields = {
        "created": f"RF-{first}" if count == 1 else f"RF-{first}…RF-{first + count - 1}",
        "requirement": requirement_rows([f"RF-{number}" for number in range(first, first + count)]),
    }
    fields.update(values)
    return sample(**fields)


class ChangeUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.units = [parse(path) for path in unit_files(CHANGES_DIR)]
        self.template = parse(CHANGES_DIR / TEMPLATE_NAME)

    def problems_of(self, files: dict[str, str | None]) -> dict[str, list[str]]:
        """Problems of every check on a temporary directory; a None value creates a subdirectory."""
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in files.items():
                if text is None:
                    (Path(tmp) / name).mkdir()
                else:
                    (Path(tmp) / name).write_text(text, encoding="utf-8", newline="\n")
            return check_all(Path(tmp))

    def test_doc_15_01_files_have_valid_names_and_frontmatter(self) -> None:
        """The directory is flat, unit names are valid, and units and template have alias and cambio tag."""
        self.assertEqual(check_files(CHANGES_DIR), [])

    def test_doc_15_02_header_fields(self) -> None:
        """Units and the template have one value per header field; unit values have their format and class.

        The unit types of the two protocol tables and of the template are the same.
        """
        classes = classes_by_type()
        self.assertEqual(check_header(self.units, classes), [])
        self.assertEqual(check_header([self.template], classes, strict=False), [])
        treated = {
            row[2].strip("`")
            for row in table_rows(CHANGES_DIR / PROTOCOL_NAME, TREATMENT_TABLE)
            if row[2] != NO_UNIT
        }
        self.assertEqual(treated, set(classes))
        offered = {name.strip() for name in self.template.header["Tipo"][0].strip("{}").split("|")}
        self.assertEqual(offered, set(classes))

    def test_doc_15_03_sections_in_order(self) -> None:
        """Units and the template have exactly the required sections, in order."""
        self.assertEqual(check_sections(self.units + [self.template]), [])

    def test_doc_15_04_states_and_approval(self) -> None:
        """Every unit state has a valid form with its approval, and the template is a draft without approval."""
        self.assertEqual(check_states(self.units + [self.template]), [])
        self.assertEqual(self.template.state, "borrador")

    def test_doc_15_05_ids(self) -> None:
        """Created IDs are the ones the unit defines, removed IDs exist, and reserved IDs have no gaps."""
        self.assertEqual(check_ids(self.units, next_free_ids(), PRD_DIR), [])
        labels = [line.split(":")[0] + ":" for line in self.template.text_lines("IDs")]
        self.assertEqual(labels, list(ID_LINES))

    def test_doc_15_06_dependencies(self) -> None:
        """Dependencies name other existing units and form no cycle."""
        self.assertEqual(check_dependencies(self.units), [])

    def test_doc_15_07_requirement_and_criteria(self) -> None:
        """Units and the template have a requirement and acceptance criteria, and cite no plan."""
        self.assertEqual(check_requirement(self.units + [self.template]), [])

    def test_doc_15_08_reconciliation_table(self) -> None:
        """Reconciliation tables are well formed and their anchors select one line of their PRD file.

        The template has the table with one pending row.
        """
        self.assertEqual(check_reconciliation(self.units, PRD_DIR), [])
        header, rows = self.template.table(RECONCILIATION, RECONCILIATION)
        self.assertEqual(tuple(header), RECONCILIATION_COLUMNS)
        self.assertEqual([row[-1] for row in rows], ["pendiente"])

    def test_doc_15_09_checklist(self) -> None:
        """Checklists are well formed and start with the common items; the template lists exactly those."""
        common = common_items()
        self.assertEqual(len(common), 9)
        self.assertEqual(check_checklist(self.units + [self.template], common), [])
        _, rows = self.template.table(CHECKLIST, CHECKLIST)
        self.assertEqual(len(rows), len(common))

    def test_doc_15_10_consumer_documents(self) -> None:
        """Consumer documents have a valid state and none is pending in an implemented unit."""
        self.assertEqual(check_consumers(self.units), [])

    def test_doc_15_11_tables_have_title(self) -> None:
        """Every table of the protocol, the template and the units has a title line right above it."""
        self.assertEqual(check_tables(CHANGES_DIR), [])

    def test_doc_15_12_valid_sample_units_pass(self) -> None:
        """Valid units of every shape raise no problem."""
        free = next_free_ids()
        rf = free["RF-"]
        criterion = free["AC-"]
        second_objective = objective_rows()[1][0].strip("| ")
        heading = next(line for line in read_lines(PRD_DIR / OBJECTIVES_FILE) if line.startswith("## "))
        decisions = "- **Sample question** (2026-01-01) Sample decision."
        requirements = f"`{REQUIREMENTS_FILE}`"
        problems = self.problems_of({
            "old.md": sample_requirements(rf, state="conciliado (2026-01-03)"),
            "first.md": sample_requirements(rf, dependencies="- old", decisions=decisions),
            "second.md": sample_requirements(rf + 1, 2, dependencies="- first"),
            "row-change.md": sample(
                dependencies="- first",
                requirement=requirement_rows([f"RF-{rf}"]),
                reconciliation=reconciliation_table([(requirements, f"RF-{rf}", "pendiente")]),
            ),
            "draft.md": sample(
                state="borrador",
                approval=NOT_APPROVED,
                created="RF-x1, AC-x1",
                requirement=requirement_rows(["RF-x1"]),
                criteria="**AC-x1.** Sample criterion.",
                consumers="- `README.md`: pendiente",
            ),
            "criterion.md": sample(created=f"AC-{criterion}", criteria=f"**AC-{criterion}.** Sample criterion."),
            "base.md": sample(),
            "dependent.md": sample(dependencies="- base"),
            "removal.md": sample(removed=second_objective),
            "existing.md": sample(requirement=requirement_rows([f"RF-{rf - 1}"])),
            "in-progress.md": sample(
                reconciliation=reconciliation_table([
                    objective_row("implementado"),
                    (requirements, f"después de RF-{rf - 1}", "pendiente"),
                ])
            ),
            "text-anchor.md": sample(
                reconciliation=reconciliation_table([objective_row("pendiente", f"{first_objective()}; después de `{heading}`")])
            ),
            "new-file.md": sample(reconciliation=reconciliation_table([(f"`25-sample.md` {NEW_FILE}", NO_ANCHOR, "pendiente")])),
            "implemented.md": sample(state="implementado"),
            "no-consumers.md": sample(consumers=NO_CONSUMERS),
            "errata.md": sample(kind="errata", package="3.0.0 (sin efecto)"),
            "release.md": sample(kind="versión", package="3.0.1 (parche)"),
            "defect.md": sample(kind=DEFECT, package="3.0.0 (parche)", reconciliation=NO_RECONCILIATION),
            "own-items.md": sample(checklist=checklist_table("pendiente", common_items() + ["Sample item"])),
            "not-applicable.md": sample(checklist=checklist_table("no aplica")),
            "reconciled.md": sample(
                state="conciliado (2026-01-03)",
                dependencies="- deleted-unit",
                reconciliation=reconciliation_table([("`98-gone.md`", "`text that is gone`", "conciliado")]),
            ),
        })
        self.assertEqual({name: found for name, found in problems.items() if found}, {})

    def test_doc_15_13_invalid_sample_units_are_reported(self) -> None:
        """Each kind of structural defect is reported by its check."""
        free = next_free_ids()
        rf = free["RF-"]
        criterion = free["AC-"]
        second_objective = objective_rows()[1][0].strip("| ")
        table = "| Column |\n|---|\n| value |"
        common = common_items()
        one_row = reconciliation_table([objective_row("pendiente")])
        old_columns = ("ID", "Contrato", "Sección del PRD", "Qué cambia", "Estado")

        def with_row(file_cell: str, anchor_cell: str, row_state: str = "pendiente", **values: str) -> str:
            return sample(reconciliation=reconciliation_table([(file_cell, anchor_cell, row_state)]), **values)

        cases: list[tuple[str, dict[str, str | None]]] = [
            ("files", {"Bad_Unit.md": sample()}),
            ("files", {"unit.md": sample().replace("tags: [cambio]", "tags: [other]")}),
            ("files", {"unit.md": "\ufeff" + sample()}),
            ("files", {"unit.md": sample().split("---\n", 2)[2]}),
            ("files", {"unit.md": sample(), "archive": None}),
            ("header", {"unit.md": sample(kind="improvement")}),
            ("header", {"unit.md": sample().replace("**Paquete:** 3.0.0 (menor)\n", "")}),
            ("header", {"unit.md": sample().replace("# Sample unit\n", "")}),
            ("header", {"unit.md": sample(package="3.0.0a1 (menor)")}),
            ("header", {"unit.md": sample(kind="errata", package="— (sin efecto)")}),
            ("header", {"unit.md": sample(kind="errata")}),
            ("header", {"unit.md": sample(kind="versión", package="3.0.0 (sin efecto)")}),
            ("header", {"unit.md": sample(package="3.0.0 (parche)")}),
            ("sections", {"unit.md": sample().replace(f"## Glosario\n\n{NO_GLOSSARY}\n\n", "")}),
            ("sections", {"unit.md": sample().replace(f"## {CHECKLIST}", "## Cambios en el PRD")}),
            ("states", {"unit.md": sample(state="approved")}),
            ("states", {"unit.md": sample(state="implementado", kind="errata", package="3.0.0 (sin efecto)")}),
            ("states", {"unit.md": sample(state="borrador")}),
            ("states", {"unit.md": sample(approval=NOT_APPROVED)}),
            ("ids", {"unit.md": sample_requirements(rf, state="borrador", approval=NOT_APPROVED)}),
            ("ids", {"unit.md": sample_requirements(rf, created="RF-x1")}),
            ("ids", {"unit.md": sample_requirements(rf).replace("Sample requirement", "Sample of RF-x9")}),
            ("ids", {"unit.md": sample_requirements(rf + 1)}),
            ("ids", {"one.md": sample_requirements(rf), "two.md": sample_requirements(rf)}),
            ("ids", {"unit.md": sample(created=f"RF-{rf}…AC-{rf}")}),
            ("ids", {"unit.md": sample_requirements(rf, created="—")}),
            ("ids", {"unit.md": sample(created=f"RF-{rf}")}),
            ("ids", {"unit.md": sample().replace("- Elimina: —\n", "")}),
            ("ids", {"unit.md": sample(removed="RF-9999")}),
            ("ids", {"unit.md": sample(removed=f"{second_objective}…RF-3")}),
            ("ids", {"unit.md": sample(created=f"AC-{criterion}", requirement=f"**AC-{criterion}.** Sample.")}),
            ("ids", {"unit.md": sample(created=f"RF-{rf}", criteria=requirement_rows([f"RF-{rf}"]))}),
            ("dependencies", {"unit.md": sample(dependencies="- missing-unit")}),
            ("dependencies", {"unit.md": sample(dependencies="- unit")}),
            ("dependencies", {"one.md": sample(dependencies="- two"), "two.md": sample(dependencies="- one")}),
            ("dependencies", {"one.md": sample(), "unit.md": sample(dependencies="`one`")}),
            ("requirement", {"unit.md": sample(requirement="")}),
            ("requirement", {"unit.md": sample(criteria="")}),
            ("requirement", {"unit.md": sample(requirement="See docs/plan/sample.md.")}),
            ("reconciliation", {"unit.md": sample(reconciliation="")}),
            ("reconciliation", {"unit.md": sample(reconciliation=NO_RECONCILIATION)}),
            ("reconciliation", {"unit.md": sample(reconciliation=one_row.split("\n", 2)[2])}),
            ("reconciliation", {"unit.md": sample(reconciliation=one_row.replace("Qué cambia", "Texto final"))}),
            ("reconciliation", {"unit.md": sample(reconciliation=reconciliation_table([objective_row("pendiente")], old_columns))}),
            ("reconciliation", {"unit.md": sample(reconciliation="\n".join(one_row.split("\n")[:4]))}),
            ("reconciliation", {"unit.md": sample(reconciliation=one_row.replace("RC-01", "RC-02"))}),
            ("reconciliation", {"unit.md": sample(reconciliation=one_row.replace("Sample change", ""))}),
            ("reconciliation", {"unit.md": sample(reconciliation=one_row.replace("| Sample change ", ""))}),
            ("reconciliation", {"unit.md": with_row("`99-missing.md`", first_objective())}),
            ("reconciliation", {"unit.md": with_row(OBJECTIVES_FILE, first_objective())}),
            ("reconciliation", {"unit.md": with_row("sección 3", first_objective())}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}`", "")}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}`", "the first objective")}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}`", "`text that is not in the file`")}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}`", "`O`")}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}`", "RF-1")}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}`", f"{first_objective()}; O9999")}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}` {NEW_FILE}", NO_ANCHOR)}),
            ("reconciliation", {"unit.md": with_row(f"`25-sample.md` {NEW_FILE}", first_objective())}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}`", first_objective(), "done")}),
            ("reconciliation", {"unit.md": with_row(f"`{OBJECTIVES_FILE}`", first_objective(), "conciliado")}),
            ("reconciliation", {"unit.md": sample(state="implementado", reconciliation=one_row)}),
            ("reconciliation", {"unit.md": sample(state="conciliado (2026-01-03)", reconciliation=one_row)}),
            ("reconciliation", {
                "unit.md": with_row(
                    f"`{OBJECTIVES_FILE}`", first_objective(), "implementado", state="borrador", approval=NOT_APPROVED
                )
            }),
            ("checklist", {"unit.md": sample(checklist="")}),
            ("checklist", {"unit.md": sample(checklist=checklist_table("pendiente", common[1:]))}),
            ("checklist", {"unit.md": sample(checklist=checklist_table("pendiente", common[:-1]))}),
            ("checklist", {"unit.md": sample(checklist=checklist_table("pendiente").replace("CL-02", "CL-12"))}),
            ("checklist", {"unit.md": sample(checklist=checklist_table("done"))}),
            ("checklist", {"unit.md": sample(checklist=checklist_table("pendiente").replace("Ítem", "Item", 1))}),
            ("checklist", {"unit.md": sample(checklist=checklist_table("pendiente").replace("Sample check", "", 1))}),
            ("checklist", {"unit.md": sample(state="conciliado (2026-01-03)", checklist=checklist_table("pendiente"))}),
            ("consumers", {"unit.md": sample(consumers="- `README.md`: done")}),
            ("consumers", {"unit.md": sample(state="implementado", consumers="- `README.md`: pendiente")}),
            ("consumers", {"unit.md": sample(state="conciliado (2026-01-03)", consumers="- `README.md`: pendiente")}),
            ("consumers", {"unit.md": sample(consumers="")}),
            ("tables", {"unit.md": sample(decisions=table)}),
        ]
        for index, (check, files) in enumerate(cases):
            with self.subTest(case=index, check=check):
                self.assertNotEqual(self.problems_of(files)[check], [])


if __name__ == "__main__":
    unittest.main()
