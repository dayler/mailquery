"""Structure checks for the PRD split into one file per section (DOC-14).

The PRD lives in ``docs/prd/``. The cover page (``00-indice.md``) lists the
sections that must exist; the chapters hold the numbered headings and the
identifiers. These tests read the Markdown files only: no network, no writes.
"""

from __future__ import annotations

import re
import unicodedata
import unittest
from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parents[1]
PRD_DIR = DOCS_ROOT / "docs" / "prd"
INDEX = PRD_DIR / "00-indice.md"
GLOSSARY = PRD_DIR / "GLOSARIO.md"

MAX_LINES = 300
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
NUMBERED_HEADING_RE = re.compile(r"^#{2,6} (\d+(?:\.\d+)*)\.? ")
ANNEX_HEADING_RE = re.compile(r"^### Anexo ([A-Z]) ")
SECTION_REF_RE = re.compile(r"§(\d+(?:\.\d+)*)")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
SCHEMES = ("http:", "https:", "mailto:")

ID_OWNERS = (
    ("O", re.compile(r"^\| (O\d+) \|"), "03-objetivos.md"),
    ("CU", re.compile(r"^\| (CU-\d+) \|"), "05-usuarios.md"),
    ("RF", re.compile(r"^\| (RF-\d+) \|"), "06-requisitos-funcionales.md"),
    ("RNF", re.compile(r"^\| (RNF-\d+) \|"), "07-requisitos-no-funcionales.md"),
    ("ADR", re.compile(r"^\| (ADR-\d+) \|"), "08-adr.md"),
    ("AC", re.compile(r"^\*\*(AC-\d+)\.\*\*"), "20-criterios-aceptacion.md"),
)


def all_files() -> list[Path]:
    """Every Markdown file of the PRD, annexes included, sorted by path."""
    return sorted(PRD_DIR.rglob("*.md"))


def rel(path: Path) -> str:
    """Path relative to the PRD directory, with forward slashes."""
    return path.relative_to(PRD_DIR).as_posix()


def chapters() -> list[Path]:
    """Numbered section files, 12.MM subsection files and annex files; not the cover page."""
    result = []
    for path in all_files():
        name = rel(path)
        if name.startswith("anexos/") or re.match(r"^(\d\d|12\.\d\d)-", name):
            if name != "00-indice.md":
                result.append(path)
    return result


def read_lines(path: Path) -> list[str]:
    """Lines of a UTF-8 file without line terminators."""
    return path.read_text(encoding="utf-8").splitlines()


def classify(lines: list[str]) -> list[tuple[int, str, bool]]:
    """(line number, text, in code) for each line after the frontmatter.

    A code block runs from a fence line (up to three leading spaces, then three
    or more backticks or tildes) to the next line holding the same fence.
    """
    start = 0
    if lines and lines[0] == "---":
        for index in range(1, len(lines)):
            if lines[index] == "---":
                start = index + 1
                break
    result = []
    fence = None
    for index in range(start, len(lines)):
        line = lines[index]
        match = FENCE_RE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
                result.append((index + 1, line, True))
                continue
            result.append((index + 1, line, False))
        else:
            result.append((index + 1, line, True))
            stripped = line.strip()
            if match and stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                fence = None
    return result


def section_prefixes(number: str) -> tuple[str, ...]:
    """File name prefixes that may hold a heading with this section number."""
    parts = number.split(".")
    if parts[0] == "12" and len(parts) >= 2:
        return (f"12.{int(parts[1]):02d}-",)
    return (f"{int(parts[0]):02d}-",)


def numbered_headings() -> list[tuple[str, str, int]]:
    """(number, file, line) for every numbered heading of the chapters, outside code blocks."""
    result = []
    for path in chapters():
        for number, text, in_code in classify(read_lines(path)):
            if in_code:
                continue
            match = NUMBERED_HEADING_RE.match(text)
            if match:
                result.append((match.group(1), rel(path), number))
    return result


def annex_headings() -> list[tuple[str, str, int]]:
    """(letter, file, line) for every annex heading of the chapters, outside code blocks."""
    result = []
    for path in chapters():
        for number, text, in_code in classify(read_lines(path)):
            if not in_code:
                match = ANNEX_HEADING_RE.match(text)
                if match:
                    result.append((match.group(1), rel(path), number))
    return result


def index_table(title: str) -> list[list[str]]:
    """Data rows of the cover-page table that carries this title, as cell lists."""
    lines = read_lines(INDEX)
    marker = f"**Tabla: {title}**"
    start = lines.index(marker)
    rows = []
    for line in lines[start + 1:]:
        if not line.strip() and not rows:
            continue
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows[2:]


def links(path: Path) -> list[tuple[int, str]]:
    """(line, target) of every Markdown link outside code blocks and inline code."""
    result = []
    for number, text, in_code in classify(read_lines(path)):
        if in_code:
            continue
        for match in LINK_RE.finditer(INLINE_CODE_RE.sub("", text)):
            result.append((number, match.group(1)))
    return result


def sort_key(term: str) -> str:
    """Glossary ordering key: no backticks, no diacritics, letters and digits only, case-folded."""
    text = unicodedata.normalize("NFKD", term.replace("`", ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c for c in text if c.isalnum()).casefold()


class PrdStructureTests(unittest.TestCase):
    def test_doc_14_01_files_within_line_limit(self) -> None:
        """No PRD file exceeds the line limit, frontmatter included."""
        too_long = [
            f"{rel(path)}: {len(read_lines(path))} lines"
            for path in all_files()
            if len(read_lines(path)) > MAX_LINES
        ]
        self.assertEqual(too_long, [])

    def test_doc_14_02_index_sections_have_one_heading_in_their_file(self) -> None:
        """Each section listed on the cover page has exactly one heading, in a file with its prefix."""
        expected_numbers = set()
        expected_annexes = set()
        for row in index_table("Archivos del PRD"):
            match = re.match(r"^(\d+(?:\.\d+)*) ", row[0])
            annex = re.match(r"^Anexo ([A-Z]) ", row[0])
            if match:
                expected_numbers.add(match.group(1))
            elif annex:
                expected_annexes.add(annex.group(1))
        self.assertTrue(expected_numbers)

        problems = []
        headings = numbered_headings()
        for number in sorted(expected_numbers):
            found = [h for h in headings if h[0] == number]
            if len(found) != 1:
                problems.append(f"section {number}: {len(found)} headings {found}")
        annexes = annex_headings()
        for letter in sorted(expected_annexes):
            found = [h for h in annexes if h[0] == letter]
            if len(found) != 1:
                problems.append(f"annex {letter}: {len(found)} headings {found}")
            elif not found[0][1].startswith(f"anexos/{letter}-"):
                problems.append(f"annex {letter}: heading in {found[0][1]}:{found[0][2]}")

        for number, name, line in headings:
            parts = number.split(".")
            top_level = len(parts) == 1
            subsection_12 = len(parts) == 2 and parts[0] == "12"
            if (top_level or subsection_12) and number not in expected_numbers:
                problems.append(f"{name}:{line}: section {number} is not on the cover page")
            if not name.startswith(section_prefixes(number)):
                problems.append(f"{name}:{line}: section {number} outside {section_prefixes(number)[0]}*")
        for letter, name, line in annexes:
            if letter not in expected_annexes:
                problems.append(f"{name}:{line}: annex {letter} is not on the cover page")
        self.assertEqual(problems, [])

    def test_doc_14_03_ids_unique_contiguous_and_next_free(self) -> None:
        """IDs are defined once, in their owner chapter, from 1 to the maximum, and the cover page has the next free ones."""
        rows = index_table("Próximos IDs libres")
        self.assertEqual(len(rows), 1)
        next_free = rows[0]
        self.assertEqual(len(next_free), len(ID_OWNERS))

        problems = []
        for column, (kind, pattern, owner) in enumerate(ID_OWNERS):
            found = []
            for path in chapters():
                for number, text, _ in classify(read_lines(path)):
                    match = pattern.match(text)
                    if match:
                        found.append((match.group(1), rel(path), number))
            for ident, name, line in found:
                if name != owner:
                    problems.append(f"{name}:{line}: {ident} defined outside {owner}")
            idents = [ident for ident, _, _ in found]
            duplicates = sorted({i for i in idents if idents.count(i) > 1})
            if duplicates:
                problems.append(f"{kind}: duplicated {duplicates}")
            if not idents:
                problems.append(f"{kind}: no IDs in {owner}")
                continue
            values = sorted({int(re.search(r"\d+$", i).group()) for i in idents})
            missing = sorted(set(range(1, values[-1] + 1)) - set(values))
            if missing:
                problems.append(f"{kind}: gaps {missing}")
            width = len(re.search(r"\d+$", idents[0]).group())
            stem = idents[0][: -width]
            expected = f"{stem}{str(values[-1] + 1).zfill(width)}"
            if next_free[column] != expected:
                problems.append(f"00-indice.md: next free {kind} is {next_free[column]}, expected {expected}")
        self.assertEqual(problems, [])

    def test_doc_14_04_section_references_resolve(self) -> None:
        """Every section reference in the chapters matches a numbered heading."""
        known = {number for number, _, _ in numbered_headings()}
        problems = []
        for path in chapters():
            for number, text, _ in classify(read_lines(path)):
                for match in SECTION_REF_RE.finditer(text):
                    if match.group(1) not in known:
                        problems.append(f"{rel(path)}:{number}: §{match.group(1)}")
        self.assertEqual(problems, [])

    def test_doc_14_05_relative_links_point_to_files_without_anchor(self) -> None:
        """Every relative link of the PRD points to an existing file and carries no anchor."""
        problems = []
        for path in all_files():
            for number, target in links(path):
                if target.startswith(SCHEMES):
                    continue
                if "#" in target:
                    problems.append(f"{rel(path)}:{number}: anchor in {target}")
                    continue
                if not (path.parent / target).resolve().is_file():
                    problems.append(f"{rel(path)}:{number}: missing {target}")
        self.assertEqual(problems, [])

    def test_doc_14_06_cover_page_links_every_file(self) -> None:
        """The cover page links every other PRD file."""
        linked = {
            (INDEX.parent / target).resolve()
            for _, target in links(INDEX)
            if not target.startswith(SCHEMES)
        }
        unlinked = [rel(path) for path in all_files() if path != INDEX and path.resolve() not in linked]
        self.assertEqual(unlinked, [])

    def test_doc_14_07_tables_have_title(self) -> None:
        """Every table outside code blocks has a title line right above it."""
        problems = []
        for path in all_files():
            previous = ""
            previous_is_table = False
            for number, text, in_code in classify(read_lines(path)):
                is_table = not in_code and text.startswith("|")
                if is_table and not previous_is_table and not previous.startswith("**Tabla: "):
                    problems.append(f"{rel(path)}:{number}")
                previous_is_table = is_table
                if text.strip():
                    previous = text
        self.assertEqual(problems, [])

    def test_doc_14_08_no_plan_citations(self) -> None:
        """No PRD file cites a plan."""
        problems = [
            f"{rel(path)}:{number}"
            for path in all_files()
            for number, text in enumerate(read_lines(path), start=1)
            if "docs/plan" in text or "plan2/" in text
        ]
        self.assertEqual(problems, [])

    def test_doc_14_09_frontmatter_has_aliases_and_prd_tag(self) -> None:
        """Every PRD file starts with frontmatter holding quoted aliases and the prd tag."""
        problems = []
        for path in all_files():
            lines = read_lines(path)
            if not lines or lines[0] != "---" or "---" not in lines[1:]:
                problems.append(f"{rel(path)}: no frontmatter")
                continue
            front = lines[1:lines.index("---", 1)]
            aliases = [l for l in front if l.startswith("aliases: [")]
            tags = [l for l in front if l.startswith("tags: [")]
            if not aliases or not re.search(r'"[^"]+"', aliases[0]):
                problems.append(f"{rel(path)}: no quoted alias")
            tag_list = re.match(r"^tags: \[(.*)\]\s*$", tags[0]) if tags else None
            if not tag_list or "prd" not in [t.strip().strip("\"'") for t in tag_list.group(1).split(",")]:
                problems.append(f"{rel(path)}: no prd tag")
        self.assertEqual(problems, [])

    def test_doc_14_10_glossary_terms_sorted(self) -> None:
        """Glossary terms are in alphabetical order within each group."""
        groups: list[list[str]] = []
        for _, text, in_code in classify(read_lines(GLOSSARY)):
            if in_code:
                continue
            if text.startswith("## "):
                groups.append([])
            elif text.startswith("### ") and groups:
                groups[-1].append(text[4:].strip())
        self.assertTrue(groups)
        for terms in groups:
            self.assertEqual(terms, sorted(terms, key=sort_key))

    def test_doc_14_11_no_utf8_bom(self) -> None:
        """No PRD file starts with the UTF-8 byte order mark."""
        with_bom = [rel(path) for path in all_files() if path.read_bytes().startswith(b"\xef\xbb\xbf")]
        self.assertEqual(with_bom, [])


if __name__ == "__main__":
    unittest.main()
