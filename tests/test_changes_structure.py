"""Structure checks for the change units of the PRD (DOC-15).

A change unit is a Markdown file in ``docs/changes/`` that holds the final
text the PRD must have. The checks take the directory to validate, so they
run on the repository and on sample units written to a temporary directory.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from tests.test_prd_structure import DOCS_ROOT, ID_OWNERS, PRD_DIR, classify, index_table, read_lines

CHANGES_DIR = DOCS_ROOT / "docs" / "changes"
PROTOCOL_NAME = "PROTOCOLO.md"
TEMPLATE_NAME = "PLANTILLA.md"
NOT_UNITS = (PROTOCOL_NAME, TEMPLATE_NAME)

SECTIONS = (
    "Estado",
    "Contexto",
    "IDs",
    "Dependencias",
    "Cambios en el PRD",
    "Decisiones",
    "Glosario",
    "Secciones relacionadas y textos obsoletos",
    "Documentos consumidores",
    "Desviaciones aprobadas",
)
HEADER_FIELDS = ("Tipo", "Base", "Fecha", "Aprobación", "Paquete")
OPERATIONS = ("añadir", "modificar", "eliminar")
ID_LINES = ("- Crea:", "- Elimina:")
NEW_FILE = "archivo nuevo"
NOT_APPROVED = "—"
NO_DEPENDENCIES = "Ninguna"
NO_DECISIONS = "Ninguna"
NO_GLOSSARY = "Sin cambios"
NO_CHANGES = "Ninguno"
NO_CONSUMERS = "Ninguno"
CONSUMER_STATES = ("pendiente", "actualizado", "sin cambio")
RELATED_VALUES = ("cambia", "sin cambio")
RELATED_TABLE = "Secciones que suelen cambiar a la vez"
CLASSES_TABLE = "Clases de cambio del paquete"
TREATMENT_TABLE = "Tratamiento de cada tipo de cambio"
NO_UNIT = "Sin unidad"
OBSOLETE_KEY = "Textos obsoletos"
COVER_PAGE = "00-indice.md"
COVER_LABEL = "Portada"

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
OWNER_FILES = {(kind if kind == "O" else f"{kind}-"): owner for kind, _, owner in ID_OWNERS}
CHANGE_HEADING_RE = re.compile(r"^### (\S+\.md) — (sección \d+(?:\.\d+)?|Anexo [A-Z]|Portada)$")
TABLE_RULE_RE = re.compile(r"^\|\s*:?-{3,}")
LINK_TARGET_RE = re.compile(r"\]\(([^)\s]+)\)")
MD_HEADING_RE = re.compile(r"^(#{1,6}) ")
LIST_ITEM_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)]) ")
FIELD_LINE_RE = re.compile(r"^\*\*[^*]+:\*\* ")
TABLE_TITLE = "**Tabla: "

# An ID is (kind, number) when it is real and (kind, "x<n>") when it is a marker.
Ident = tuple[str, "int | str"]


@dataclass
class Change:
    """One change of a unit: target file, operation, location block and final text block."""

    file: str
    line: int
    operation: str
    location: list[str] | None = None
    final: list[str] | None = None


@dataclass
class FileHeading:
    """A file heading of the changes section; file and label are empty when the heading is malformed."""

    file: str
    label: str
    line: int
    changes: int = 0


@dataclass
class Unit:
    """A parsed change unit: header fields, sections, file headings and changes."""

    path: Path
    title: str = ""
    header: dict[str, list[str]] = field(default_factory=dict)
    sections: list[tuple[str, list[tuple[int, str, bool]]]] = field(default_factory=list)
    headings: list[FileHeading] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)

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


def related_rows() -> list[str]:
    """First cell of each row of the related-sections table of the protocol."""
    return [row[0] for row in table_rows(CHANGES_DIR / PROTOCOL_NAME, RELATED_TABLE)]


def classes_by_type() -> dict[str, tuple[str, ...]]:
    """Package classes that each unit type allows, from the package-classes table of the protocol."""
    result: dict[str, list[str]] = {}
    for row in table_rows(CHANGES_DIR / PROTOCOL_NAME, CLASSES_TABLE):
        for kind in re.findall(r"`([^`]+)`", row[2]):
            result.setdefault(kind, []).append(row[0].strip("`"))
    return {kind: tuple(classes) for kind, classes in result.items()}


def section_labels() -> dict[str, str | None]:
    """Section label of each PRD file, in the order of the cover page.

    The cover page comes first. A file of a numbered section or of an annex has
    the label of its row in the cover-page table; any other listed file has None.
    """
    labels: dict[str, str | None] = {COVER_PAGE: COVER_LABEL}
    for row in index_table("Archivos del PRD"):
        number = re.match(r"^(\d+(?:\.\d+)?) ", row[0])
        annex = re.match(r"^Anexo ([A-Z]) ", row[0])
        label = f"sección {number.group(1)}" if number else f"Anexo {annex.group(1)}" if annex else None
        for target in LINK_TARGET_RE.findall(row[1]):
            labels[target] = label
    return labels


def next_free_ids() -> dict[str, int]:
    """Next free number of each ID kind, from the PRD cover page."""
    result = {}
    for cell in index_table("Próximos IDs libres")[0]:
        match = ID_RE.fullmatch(cell)
        if match:
            result[match.group(1)] = int(match.group(2))
    return result


def parse(path: Path) -> Unit:
    """Read a unit: title, header fields before the first section, sections and changes."""
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
    _parse_changes(unit)
    return unit


def _parse_changes(unit: Unit) -> None:
    """Fill the file headings and the changes of a unit from its changes section.

    A change starts at its operation line and belongs to the last file heading.
    The code block after the location label is its location and the one after
    the final-text label is its final text; fence lines are not part of either.
    """
    heading: FileHeading | None = None
    change: Change | None = None
    target = ""
    block: list[str] | None = None

    def close_block() -> None:
        nonlocal block, target
        if block is not None and change is not None and target:
            setattr(change, target, block[:-1])
        block = None
        target = ""

    for number, text, in_code in unit.section("Cambios en el PRD"):
        if in_code:
            if block is None:
                block = []
            else:
                block.append(text)
            continue
        if block is not None:
            close_block()
        stripped = text.strip()
        if text.startswith("### "):
            match = CHANGE_HEADING_RE.match(text)
            heading = FileHeading(
                file=match.group(1) if match else "", label=match.group(2) if match else "", line=number
            )
            unit.headings.append(heading)
        elif stripped.startswith("- **Operación:**"):
            change = Change(
                file=heading.file if heading else "",
                line=number,
                operation=stripped.split(":**", 1)[1].strip(),
            )
            unit.changes.append(change)
            if heading:
                heading.changes += 1
        elif stripped.startswith("- **Ubicación:**"):
            target = "location"
        elif stripped.startswith("- **Texto final:**"):
            target = "final"
    close_block()


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
    """Whether the locations of the unit must exist in the PRD: it is open and no dependency of it is open."""
    return unit.is_open and not any(
        name in by_name and by_name[name].is_open for name in dependency_names(unit)
    )


def location_line(change: Change) -> str | None:
    """The single non-empty line of the location block, or None when it does not have exactly one."""
    lines = [line for line in (change.location or []) if line.strip()]
    return lines[0].rstrip() if len(lines) == 1 else None


def matching_lines(prd_dir: Path, file: str, location: str) -> list[int]:
    """Numbers of the lines of a PRD file that start with the location text; empty when the file is missing."""
    target = prd_dir / file
    if not target.is_file():
        return []
    return [number for number, line in enumerate(read_lines(target), start=1) if line.startswith(location)]


def block_range(lines: list[str], number: int) -> tuple[int, int]:
    """First and last line numbers of the block that the line with this number identifies.

    A line inside a code block selects the whole code block. A table row
    selects itself. A table title selects the title and its table. A field
    line selects itself and its continuation lines, up to the next field line
    or blank line.
    A heading selects its section, up to the next heading of the same or a
    higher level. A list item selects itself with its continuation lines and
    sub-items. Any other line selects its paragraph.
    """
    in_code = {line_number: code for line_number, _, code in classify(lines)}
    last = len(lines)
    text = lines[number - 1]
    if in_code.get(number):
        start = end = number
        while in_code.get(start - 1):
            start -= 1
        while in_code.get(end + 1):
            end += 1
        return start, end
    if text.startswith("|"):
        return number, number
    if text.startswith(TABLE_TITLE):
        end = number
        cursor = number + 1
        while cursor <= last and not lines[cursor - 1].strip():
            cursor += 1
        while cursor <= last and lines[cursor - 1].startswith("|"):
            end = cursor
            cursor += 1
        return number, end
    if FIELD_LINE_RE.match(text):
        end = number
        while end < last and lines[end].strip() and not FIELD_LINE_RE.match(lines[end]):
            end += 1
        return number, end
    heading = MD_HEADING_RE.match(text)
    if heading:
        end = number
        for cursor in range(number + 1, last + 1):
            other = MD_HEADING_RE.match(lines[cursor - 1])
            if other and not in_code.get(cursor) and len(other.group(1)) <= len(heading.group(1)):
                break
            end = cursor
        return number, end
    item = LIST_ITEM_RE.match(text)
    if item:
        end = number
        for cursor in range(number + 1, last + 1):
            line = lines[cursor - 1]
            other = LIST_ITEM_RE.match(line)
            if not line.strip() or (other and len(other.group(1)) <= len(item.group(1))):
                break
            end = cursor
        return number, end
    start = end = number
    while start > 1 and lines[start - 2].strip():
        start -= 1
    while end < last and lines[end].strip():
        end += 1
    return start, end


def changed_blocks(unit: Unit, prd_dir: Path) -> list[tuple[Change, list[str], int, int, int]]:
    """(change, file lines, selected line, first line, last line) for each modification or removal.

    Only the changes whose location selects exactly one line of the PRD file are returned.
    """
    result = []
    for change in unit.changes:
        location = location_line(change)
        if change.operation not in ("modificar", "eliminar") or location is None:
            continue
        numbers = matching_lines(prd_dir, change.file, location)
        if len(numbers) == 1:
            lines = read_lines(prd_dir / change.file)
            result.append((change, lines, numbers[0], *block_range(lines, numbers[0])))
    return result


def removed_ids(unit: Unit, prd_dir: Path) -> set[Ident]:
    """IDs that the changes of the unit take out of the PRD.

    A removal takes out every ID its block defines; a modification takes out
    the IDs its block defines that its final text no longer defines.
    """
    removed: set[Ident] = set()
    for change, lines, _, start, end in changed_blocks(unit, prd_dir):
        kept = definitions(change.final or []) if change.operation == "modificar" else set()
        removed |= definitions(lines[start - 1:end]) - kept
    return removed


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
    """The IDs section is well formed and agrees with the changes of the unit.

    The section has the created line and the removed line, with valid ranges.
    Drafts create only markers and other units hold no markers. In an open
    unit, the created IDs are exactly the new IDs its final texts define, each
    in the PRD file that owns its kind; an ID created by an open unit it
    depends on is not new. When the locations of the unit must exist in the PRD, the
    removed IDs are exactly the IDs its changes take out, and a modification
    of a line that defines an ID keeps that ID. The IDs created by
    approved and implemented units are unique and continue, per kind, from the
    next free ID of the PRD.
    """
    by_name = {unit.name: unit for unit in units}
    created_by = {unit.name: set(id_line(unit, ID_LINES[0])[0]) for unit in units}
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
            for change in unit.changes:
                for ident in definitions(change.final or []) - inherited:
                    kind, tail = ident
                    if isinstance(tail, str) or tail >= next_free.get(kind, 0):
                        new.add(ident)
                        if change.file != OWNER_FILES[kind]:
                            problems.append(f"{label}: {show(ident)} defined outside {OWNER_FILES[kind]}")
            if new != set(created):
                problems.append(
                    f"{label}: creates {sorted(map(show, created))} "
                    f"but its final texts define {sorted(map(show, new))}"
                )
        if is_resolvable(unit, by_name):
            for change, lines, number, _, _ in changed_blocks(unit, prd_dir):
                dropped = definitions([lines[number - 1]]) - definitions(change.final or [])
                if change.operation == "modificar" and dropped:
                    problems.append(
                        f"{label}:{change.line}: a modification drops {sorted(map(show, dropped))}"
                    )
            taken_out = removed_ids(unit, prd_dir)
            if taken_out != set(removed):
                problems.append(
                    f"{label}: removes {sorted(map(show, removed))} "
                    f"but its changes take out {sorted(map(show, taken_out))}"
                )
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


def check_changes(units: list[Unit], prd_dir: Path, labels: dict[str, str | None]) -> list[str]:
    """Each unit has well-formed changes, grouped by file in the order of the PRD.

    A unit without changes says so and changes the glossary or adds decisions.
    Every file heading is valid, appears once, holds at least one change and
    carries the section label of its file; the glossary and the history have
    no heading. Every change has a valid operation, a one-line location and a
    final text, except a removal, which has none. When the locations of the
    unit must exist in the PRD, exactly one line of the file starts with the
    location; the location of a new file belongs to an addition to a file that
    does not exist yet.
    """
    by_name = {unit.name: unit for unit in units}
    order = list(labels)
    problems = []
    for unit in units:
        label = unit.path.name
        if not unit.changes:
            declared = not unit.headings and unit.text_lines("Cambios en el PRD") == [NO_CHANGES]
            elsewhere = (
                unit.text_lines("Glosario") != [NO_GLOSSARY] or unit.text_lines("Decisiones") != [NO_DECISIONS]
            )
            if not (declared and elsewhere):
                problems.append(f"{label}: no changes")
        files: list[str] = []
        for heading in unit.headings:
            if not heading.file:
                problems.append(f"{label}:{heading.line}: invalid change heading")
                continue
            if not heading.changes:
                problems.append(f"{label}:{heading.line}: file heading without changes")
            if heading.file in files:
                problems.append(f"{label}:{heading.line}: {heading.file} has two headings")
            files.append(heading.file)
            if heading.file in labels and labels[heading.file] is None:
                problems.append(f"{label}:{heading.line}: {heading.file} does not go in the changes section")
            elif heading.file in labels and heading.label != labels[heading.file]:
                problems.append(f"{label}:{heading.line}: {heading.file} is {labels[heading.file]!r}")
        positions = [order.index(file) for file in files if file in order]
        if positions != sorted(positions):
            problems.append(f"{label}: files out of the PRD order")
        resolvable = is_resolvable(unit, by_name)
        for change in unit.changes:
            where = f"{label}:{change.line}"
            if not change.file:
                problems.append(f"{where}: change outside a valid file heading")
            if change.operation not in OPERATIONS:
                problems.append(f"{where}: invalid operation {change.operation!r}")
            has_final = any(line.strip() for line in change.final or [])
            if change.operation == "eliminar":
                if change.final is not None:
                    problems.append(f"{where}: a removal has a final text")
            elif not has_final:
                problems.append(f"{where}: no final text")
            location = location_line(change)
            if location is None:
                count = len([line for line in (change.location or []) if line.strip()])
                problems.append(f"{where}: the location has {count} lines")
                continue
            if not resolvable or not change.file:
                continue
            if location.strip() == NEW_FILE:
                if change.operation != "añadir":
                    problems.append(f"{where}: a new file is only added")
                if (prd_dir / change.file).exists():
                    problems.append(f"{where}: {change.file} already exists")
            elif not (prd_dir / change.file).is_file():
                problems.append(f"{where}: missing {change.file}")
            else:
                count = len(matching_lines(prd_dir, change.file, location))
                if count != 1:
                    problems.append(f"{where}: {count} lines of {change.file} start with the location")
    return problems


def check_final_text(units: list[Unit]) -> list[str]:
    """No final text cites a plan, and every whole table in a final text has a title line right above it."""
    problems = []
    for unit in units:
        for change in unit.changes:
            lines = change.final or []
            previous = ""
            for index, line in enumerate(lines):
                if "docs/plan" in line:
                    problems.append(f"{unit.path.name}:{change.line}: the final text cites a plan")
                starts_table = line.startswith("|") and (index == 0 or not lines[index - 1].startswith("|"))
                whole_table = index + 1 < len(lines) and TABLE_RULE_RE.match(lines[index + 1])
                if starts_table and whole_table and not previous.startswith(TABLE_TITLE):
                    problems.append(f"{unit.path.name}:{change.line}: table without title in the final text")
                if line.strip():
                    previous = line
    return problems


def check_overlaps(units: list[Unit], prd_dir: Path) -> list[str]:
    """No two open units modify or remove blocks that share a line, unless one depends on the other.

    The block of a location that selects one line of the PRD file is its range
    of lines; a location that selects no single line is compared as text.
    """
    by_name = {unit.name: unit for unit in units}
    ranges: list[tuple[str, int, int, str]] = []
    texts: dict[tuple[str, str], set[str]] = {}
    for unit in units:
        if not unit.is_open:
            continue
        resolved = {id(change) for change, _, _, _, _ in changed_blocks(unit, prd_dir)}
        for change, _, _, start, end in changed_blocks(unit, prd_dir):
            ranges.append((change.file, start, end, unit.name))
        for change in unit.changes:
            location = location_line(change)
            if change.operation in ("modificar", "eliminar") and location and id(change) not in resolved:
                texts.setdefault((change.file, location.strip()), set()).add(unit.name)

    def related(first: str, second: str) -> bool:
        return (
            second in dependency_closure(by_name[first], by_name)
            or first in dependency_closure(by_name[second], by_name)
        )

    found: set[tuple[str, str, str]] = set()
    for index, (file, start, end, name) in enumerate(ranges):
        for other_file, other_start, other_end, other in ranges[index + 1:]:
            if file == other_file and name != other and start <= other_end and other_start <= end:
                found.add((file, *sorted((name, other))))
    for (file, _), names in texts.items():
        ordered = sorted(names)
        for index, first in enumerate(ordered):
            for second in ordered[index + 1:]:
                found.add((file, first, second))
    return [
        f"{file}: {first}.md and {second}.md change the same block"
        for file, first, second in sorted(found)
        if not related(first, second)
    ]


def check_related(units: list[Unit], rows: list[str]) -> list[str]:
    """Each unit marks every row of the related-sections table once and has the obsolete-texts line."""
    problems = []
    for unit in units:
        found: dict[str, list[str]] = {}
        for line in unit.text_lines("Secciones relacionadas y textos obsoletos"):
            match = ITEM_RE.match(line)
            if not match:
                problems.append(f"{unit.path.name}: invalid related-sections line {line!r}")
                continue
            found.setdefault(match.group(1), []).append(match.group(2).strip())
        for row in rows:
            values = found.pop(row, [])
            if len(values) != 1 or values[0] not in RELATED_VALUES:
                problems.append(f"{unit.path.name}: row {row!r} marked {values}")
        obsolete = found.pop(OBSOLETE_KEY, [])
        if len(obsolete) != 1 or not obsolete[0]:
            problems.append(f"{unit.path.name}: {len(obsolete)} obsolete-texts lines with text")
        for key in found:
            problems.append(f"{unit.path.name}: unknown related-sections row {key!r}")
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
        "changes": check_changes(units, PRD_DIR, section_labels()),
        "final_text": check_final_text(units),
        "overlaps": check_overlaps(units, PRD_DIR),
        "related": check_related(units, related_rows()),
        "consumers": check_consumers(units),
        "tables": check_tables(directory),
    }


OBJECTIVES_FILE = "03-objetivos.md"
REQUIREMENTS_FILE = "06-requisitos-funcionales.md"
DEFAULT = "<default>"
OBJECTIVE_START_RE = re.compile(r"^\| O\d+ \|")


def objective_rows() -> list[tuple[str, str]]:
    """(row start up to the second pipe, whole line) of each objective row of the PRD."""
    result = []
    for line in read_lines(PRD_DIR / OBJECTIVES_FILE):
        match = OBJECTIVE_START_RE.match(line)
        if match:
            result.append((match.group(0), line))
    return result


def objectives_heading() -> str:
    """The heading of the PRD section that holds the objective rows."""
    heading = ""
    for line in read_lines(PRD_DIR / OBJECTIVES_FILE):
        if MD_HEADING_RE.match(line):
            heading = line
        if OBJECTIVE_START_RE.match(line):
            break
    return heading


def related_text(rows: list[str] | None = None) -> str:
    """Related-sections lines that mark every row as unchanged and declare no obsolete text."""
    lines = [f"- {row}: sin cambio" for row in (related_rows() if rows is None else rows)]
    return "\n".join(lines + [f"- {OBSOLETE_KEY}: Ninguno"])


def change_block(file: str, section: str, operation: str, location: str, final: str | None) -> str:
    """Markdown of a file heading with one change; without a final text when it is None."""
    text = (
        f"### {file} — {section}\n\n"
        f"- **Operación:** {operation}\n"
        f"- **Ubicación:**\n\n```markdown\n{location}\n```\n"
    )
    if final is not None:
        text += f"\n- **Texto final:**\n\n```markdown\n{final}\n```\n"
    return text


def sample(
    *,
    kind: str = "funcionalidad",
    package: str = "3.0.0 (menor)",
    state: str = "aprobado",
    approval: str = "owner, 2026-01-02",
    created: str = "—",
    removed: str = "—",
    dependencies: str = NO_DEPENDENCIES,
    file: str = OBJECTIVES_FILE,
    section: str = "sección 3",
    operation: str = "modificar",
    location: str = DEFAULT,
    final: str | None = DEFAULT,
    extra: str = "",
    changes: str = DEFAULT,
    decisions: str = NO_DECISIONS,
    glossary: str = NO_GLOSSARY,
    related: str = DEFAULT,
    consumers: str = "- `README.md`: sin cambio",
) -> str:
    """Text of a unit that is valid by default: approved, with no new IDs, it modifies the first objective row.

    The default final text keeps the ID of the objective row that the location selects.
    """
    start = objective_rows()[0][0]
    if location == DEFAULT:
        location = start
    if final == DEFAULT:
        kept = location if OBJECTIVE_START_RE.fullmatch(location) else start
        final = f"{kept} Sample objective | Sample measure |"
    if related == DEFAULT:
        related = related_text()
    if changes == DEFAULT:
        changes = f"{change_block(file, section, operation, location, final)}\n{extra}".rstrip("\n")
    return (
        '---\naliases: ["Sample unit"]\ntags: [cambio]\n---\n\n'
        "# Sample unit\n\n"
        f"**Tipo:** {kind}\n**Base:** PRD 2.4\n**Fecha:** 2026-01-01\n"
        f"**Aprobación:** {approval}\n**Paquete:** {package}\n\n"
        f"## Estado\n\n{state}\n\n"
        "## Contexto\n\nContext text.\n\n"
        f"## IDs\n\n- Crea: {created}\n- Elimina: {removed}\n\n"
        f"## Dependencias\n\n{dependencies}\n\n"
        f"## Cambios en el PRD\n\n{changes}\n\n"
        f"## Decisiones\n\n{decisions}\n\n"
        f"## Glosario\n\n{glossary}\n\n"
        f"## Secciones relacionadas y textos obsoletos\n\n{related}\n\n"
        f"## Documentos consumidores\n\n{consumers}\n\n"
        "## Desviaciones aprobadas\n\nNinguna\n"
    )


def sample_requirements(first: int, count: int = 1, **values: str) -> str:
    """Text of a valid approved unit that adds consecutive requirement rows starting at this number."""
    numbers = range(first, first + count)
    fields = {
        "created": f"RF-{first}" if count == 1 else f"RF-{first}…RF-{first + count - 1}",
        "file": REQUIREMENTS_FILE,
        "section": "sección 6",
        "operation": "añadir",
        "location": f"| RF-{first - 1} |",
        "final": "\n".join(f"| RF-{number} | Sample requirement | M |" for number in numbers),
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
        """Created and removed IDs match the changes, drafts hold markers and reserved IDs have no gaps."""
        self.assertEqual(check_ids(self.units, next_free_ids(), PRD_DIR), [])
        labels = [line.split(":")[0] + ":" for line in self.template.text_lines("IDs")]
        self.assertEqual(labels, list(ID_LINES))

    def test_doc_15_06_dependencies(self) -> None:
        """Dependencies name other existing units and form no cycle."""
        self.assertEqual(check_dependencies(self.units), [])

    def test_doc_15_07_changes_and_locations(self) -> None:
        """Changes are grouped by file in the PRD order, well formed, and each location starts one line of its file."""
        self.assertEqual(check_changes(self.units, PRD_DIR, section_labels()), [])
        self.assertEqual(len(self.template.changes), 1)
        self.assertEqual(len(self.template.changes[0].location or []), 1)
        self.assertEqual(len(self.template.changes[0].final or []), 1)

    def test_doc_15_08_final_text(self) -> None:
        """No final text cites a plan and every whole table in a final text has a title."""
        self.assertEqual(check_final_text(self.units), [])

    def test_doc_15_09_no_overlaps(self) -> None:
        """No two open units change blocks that share a line unless one depends on the other."""
        self.assertEqual(check_overlaps(self.units, PRD_DIR), [])

    def test_doc_15_10_related_sections(self) -> None:
        """Units mark every row of the related-sections table; the template lists the same rows."""
        rows = related_rows()
        self.assertEqual(len(rows), 8)
        self.assertEqual(check_related(self.units, rows), [])
        listed = [
            ITEM_RE.match(line).group(1)
            for line in self.template.text_lines("Secciones relacionadas y textos obsoletos")
        ]
        self.assertEqual(listed, rows + [OBSOLETE_KEY])

    def test_doc_15_11_consumer_documents(self) -> None:
        """Consumer documents have a valid state and none is pending in an implemented unit."""
        self.assertEqual(check_consumers(self.units), [])

    def test_doc_15_12_tables_have_title(self) -> None:
        """Every table of the protocol, the template and the units has a title line right above it."""
        self.assertEqual(check_tables(CHANGES_DIR), [])

    def test_doc_15_13_valid_sample_units_pass(self) -> None:
        """Valid units of every shape raise no problem."""
        free = next_free_ids()["RF-"]
        objectives = objective_rows()
        second_id = objectives[1][0].strip("| ")
        decisions = (
            "**Tabla: Filas para el Anexo D**\n\n"
            "| Pregunta original | Decisión |\n|---|---|\n| Sample question | Sample decision |"
        )
        problems = self.problems_of({
            "old.md": sample_requirements(free, state="conciliado (2026-01-03)"),
            "first.md": sample_requirements(free, dependencies="- old", decisions=decisions),
            "second.md": sample_requirements(free + 1, 2, dependencies="- first"),
            "row-change.md": sample(
                dependencies="- first",
                file=REQUIREMENTS_FILE,
                section="sección 6",
                location=f"| RF-{free} |",
                final=f"| RF-{free} | Sample requirement, changed | M |",
            ),
            "draft.md": sample_requirements(
                free,
                state="borrador",
                approval=NOT_APPROVED,
                created="RF-x1",
                location=f"| RF-{free - 1} |",
                final="| RF-x1 | Sample requirement | M |",
                consumers="- `README.md`: pendiente",
            ),
            "base.md": sample(),
            "dependent.md": sample(dependencies="- base"),
            "removal.md": sample(operation="eliminar", location=objectives[1][0], final=None, removed=second_id),
            "new-file.md": sample(
                file="25-sample.md", section="sección 25", operation="añadir", location=NEW_FILE, final="# Sample"
            ),
            "no-consumers.md": sample(location=objectives[2][0], consumers=NO_CONSUMERS),
            "errata.md": sample(kind="errata", package="3.0.0 (sin efecto)", location=objectives[3][0]),
            "release.md": sample(kind="versión", package="3.0.1 (parche)", location=objectives[4][0]),
            "glossary-only.md": sample(changes=NO_CHANGES, glossary="- **Sample term:** sample definition."),
            "reconciled.md": sample(
                state="conciliado (2026-01-03)", dependencies="- deleted-unit", location="text that is gone"
            ),
        })
        self.assertEqual({name: found for name, found in problems.items() if found}, {})

    def test_doc_15_14_invalid_sample_units_are_reported(self) -> None:
        """Each kind of structural defect is reported by its check."""
        free = next_free_ids()["RF-"]
        (start, line), (second_start, _) = objective_rows()[:2]
        second_id = second_start.strip("| ")
        heading = objectives_heading()
        table = "| Column |\n|---|\n| value |"
        rows = related_rows()
        default_block = change_block(
            OBJECTIVES_FILE, "sección 3", "modificar", start, f"{start} Sample objective | Sample measure |"
        )
        second_block = change_block(
            OBJECTIVES_FILE, "sección 3", "modificar", second_start, f"{second_start} Sample objective | Sample |"
        )
        cases: list[tuple[str, dict[str, str | None]]] = [
            ("files", {"Bad_Unit.md": sample()}),
            ("files", {"unit.md": sample().replace("tags: [cambio]", "tags: [other]")}),
            ("files", {"unit.md": "﻿" + sample()}),
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
            ("states", {"unit.md": sample(state="approved")}),
            ("states", {"unit.md": sample(state="implementado", kind="errata", package="3.0.0 (sin efecto)")}),
            ("states", {"unit.md": sample(state="borrador")}),
            ("states", {"unit.md": sample(approval=NOT_APPROVED)}),
            ("ids", {"unit.md": sample_requirements(free, state="borrador", approval=NOT_APPROVED)}),
            ("ids", {"unit.md": sample_requirements(free, created="RF-x1")}),
            ("ids", {"unit.md": sample_requirements(free).replace("Sample requirement", "Sample of RF-x9")}),
            ("ids", {"unit.md": sample_requirements(free + 1, location=f"| RF-{free - 1} |")}),
            ("ids", {"one.md": sample_requirements(free), "two.md": sample_requirements(free)}),
            ("ids", {"unit.md": sample(created=f"RF-{free}…AC-{free}")}),
            ("ids", {"unit.md": sample_requirements(free, created="—")}),
            ("ids", {"unit.md": sample(created=f"RF-{free}")}),
            ("ids", {"unit.md": sample(created=f"RF-{free}", final=f"| RF-{free} | Sample requirement | M |")}),
            ("ids", {"unit.md": sample().replace("- Elimina: —\n", "")}),
            ("ids", {"unit.md": sample(removed=second_id)}),
            ("ids", {"unit.md": sample(operation="eliminar", location=second_start, final=None)}),
            ("ids", {"unit.md": sample(removed=f"{second_id}…RF-3")}),
            ("ids", {"unit.md": sample(final=f"{second_start} Sample objective | Sample |", removed=start.strip("| "))}),
            ("dependencies", {"unit.md": sample(dependencies="- missing-unit")}),
            ("dependencies", {"unit.md": sample(dependencies="- unit")}),
            ("dependencies", {
                "one.md": sample(dependencies="- two"),
                "two.md": sample(dependencies="- one", location=second_start),
            }),
            ("dependencies", {"one.md": sample(), "unit.md": sample(dependencies="`one`", location=second_start)}),
            ("changes", {"unit.md": sample(location="text that is not in the file")}),
            ("changes", {"unit.md": sample(location="|")}),
            ("changes", {"unit.md": sample(location=line[len(start) + 1:len(start) + 16])}),
            ("changes", {"unit.md": sample(operation="move")}),
            ("changes", {"unit.md": sample(location=NEW_FILE)}),
            ("changes", {"unit.md": sample().replace(f"### {OBJECTIVES_FILE} — sección 3", "### Objectives")}),
            ("changes", {"unit.md": sample(section="Section 3")}),
            ("changes", {"unit.md": sample(section="sección 99")}),
            ("changes", {"unit.md": sample(file="GLOSARIO.md", section="sección 1")}),
            ("changes", {"unit.md": sample(file="99-missing.md", section="sección 99")}),
            ("changes", {"unit.md": sample(final=None)}),
            ("changes", {"unit.md": sample(location="")}),
            ("changes", {"unit.md": sample(location=f"{start}\n{second_start}")}),
            ("changes", {"unit.md": sample(operation="eliminar")}),
            ("changes", {"unit.md": sample(extra="### 05-usuarios.md — sección 5\n")}),
            ("changes", {"unit.md": sample(extra=second_block)}),
            ("changes", {"unit.md": sample_requirements(free, extra=default_block)}),
            ("changes", {"unit.md": sample(changes="")}),
            ("changes", {"unit.md": sample(changes=NO_CHANGES)}),
            ("final_text", {"unit.md": sample(final=table)}),
            ("final_text", {"unit.md": sample(final="See docs/plan/sample.md.")}),
            ("overlaps", {"one.md": sample(), "two.md": sample()}),
            ("overlaps", {"one.md": sample(), "two.md": sample(location=line[:len(start) + 6])}),
            ("overlaps", {"one.md": sample(), "two.md": sample(location=heading, final=f"{heading}\n\nSample.")}),
            ("overlaps", {
                "one.md": sample(location="text of a later unit"),
                "two.md": sample(location="text of a later unit"),
            }),
            ("related", {"unit.md": sample(related=related_text(rows[1:]))}),
            ("related", {"unit.md": sample(related=related_text().replace("sin cambio", "maybe", 1))}),
            ("related", {"unit.md": sample(related="\n".join(f"- {row}: cambia" for row in rows))}),
            ("related", {"unit.md": sample(related=related_text() + "\n- Unknown row: cambia")}),
            ("consumers", {"unit.md": sample(consumers="- `README.md`: done")}),
            ("consumers", {"unit.md": sample(state="implementado", consumers="- `README.md`: pendiente")}),
            ("consumers", {"unit.md": sample(state="conciliado (2026-01-03)", consumers="- `README.md`: pendiente")}),
            ("consumers", {"unit.md": sample(consumers="")}),
            ("tables", {"unit.md": sample(decisions=table)}),
        ]
        for index, (check, files) in enumerate(cases):
            with self.subTest(case=index, check=check):
                self.assertNotEqual(self.problems_of(files)[check], [])

    def test_doc_15_15_block_of_each_kind_of_line(self) -> None:
        """The block of a line is the one the block table of the protocol gives to its kind."""
        lines = [
            "# Title",
            "",
            "**Field:** first",
            "continued",
            "**Other:** value",
            "",
            "## Section",
            "",
            "Paragraph one",
            "still the paragraph",
            "",
            "**Tabla: Sample**",
            "",
            "| A |",
            "|---|",
            "| 1 |",
            "",
            "- item",
            "  continued",
            "  - sub-item",
            "- next item",
            "",
            "```",
            "## code",
            "```",
            "",
            "## Next section",
            "text",
        ]
        expected = {
            1: (1, 28),
            3: (3, 4),
            5: (5, 5),
            7: (7, 26),
            10: (9, 10),
            12: (12, 16),
            16: (16, 16),
            18: (18, 20),
            21: (21, 21),
            24: (23, 25),
            27: (27, 28),
        }
        self.assertEqual({number: block_range(lines, number) for number in expected}, expected)


if __name__ == "__main__":
    unittest.main()
