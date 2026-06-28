"""
pbix_parser.py
Parses a .pbix file using only stdlib (zipfile) + pandas.
No pbixray, no xpress9, no compiled dependencies.

Approach:
  1. Read TMDLScripts/*.tmdl  → existing measures + column refs from DAX
  2. Read DiagramLayout JSON   → real table names in the model
  3. If user provides CSV/Excel → classify columns from that DataFrame
  4. Expose enrich_from_dataframe() so app.py can add more columns
"""

import io
import re
import json
import zipfile
from typing import Dict, List, Tuple, Optional
import pandas as pd


HIDDEN_TABLE_PREFIXES = ("DateTableTemplate_", "LocalDateTable_")

SKIP_TABLES = {"Medidas", "Measures", "_Measures"}

CURRENCY_KEYWORDS = (
    "sales", "revenue", "price", "cost", "profit", "discount",
    "gross", "cogs", "venda", "receita", "preco", "preço",
    "custo", "lucro", "desconto", "faturamento", "valor",
    "amount", "net", "bruto", "liquido", "líquido",
)


class PBIXParser:
    def __init__(self, file_bytes: bytes):
        self.file_bytes = file_bytes
        self._tables: Dict[str, dict] = {}
        self._existing_measures: List[str] = []

    # ── Public API ────────────────────────────────────────────────────

    def get_tables(self) -> Dict[str, dict]:
        # Parse only once; subsequent calls return the already-enriched dict
        if not self._tables:
            self._parse_diagram_layout()
            self._parse_tmdl_scripts()
        return self._tables

    def get_existing_measures(self) -> List[str]:
        return self._existing_measures

    def enrich_from_dataframe(self, table_name: str, df: pd.DataFrame):
        """Add/merge column classifications from a user-uploaded DataFrame."""
        numeric, text, date = self._classify_df(df)
        if table_name not in self._tables:
            self._tables[table_name] = {
                "numeric": [], "text": [], "date": [], "is_hidden": False
            }
        t = self._tables[table_name]
        for lst, new in [("numeric", numeric), ("text", text), ("date", date)]:
            existing_set = set(t[lst])
            for c in new:
                if c not in existing_set:
                    t[lst].append(c)

    # ── Parsers ───────────────────────────────────────────────────────

    def _parse_diagram_layout(self):
        """Extract real table names from DiagramLayout JSON."""
        try:
            buf = io.BytesIO(self.file_bytes)
            with zipfile.ZipFile(buf) as z:
                if "DiagramLayout" not in z.namelist():
                    return
                raw = z.read("DiagramLayout")
                text = self._decode(raw)
                data = json.loads(text)
                for diagram in data.get("diagrams", []):
                    for node in diagram.get("nodes", []):
                        name = node.get("nodeIndex", "")
                        if name and not name.startswith(HIDDEN_TABLE_PREFIXES) and name not in SKIP_TABLES:
                            self._ensure_table(name)
        except Exception:
            pass

    def _parse_tmdl_scripts(self):
        """Read TMDLScripts/*.tmdl for existing measures and column refs."""
        try:
            buf = io.BytesIO(self.file_bytes)
            with zipfile.ZipFile(buf) as z:
                tmdl_files = [
                    n for n in z.namelist()
                    if n.startswith("TMDLScripts/") and n.endswith(".tmdl")
                ]
                for fname in tmdl_files:
                    raw = z.read(fname)
                    if not raw:
                        continue
                    content = self._decode(raw)
                    self._parse_tmdl_content(content)
        except zipfile.BadZipFile:
            pass

    def _parse_tmdl_content(self, content: str):
        # Existing measure names
        for name in re.findall(r"measure '([^']+)'", content):
            self._existing_measures.append(name)

        # DAX aggregate references  →  numeric columns
        pattern = re.compile(
            r"\b(SUM|AVERAGE|MIN|MAX|COUNT|SUMX|AVERAGEX|MINX|MAXX)\s*\(\s*'?([\w][\w\s]*?)'?\[([^\]]+)\]",
            re.IGNORECASE,
        )
        for m in pattern.finditer(content):
            table = m.group(2).strip()
            col   = m.group(3).strip()
            if table.startswith(HIDDEN_TABLE_PREFIXES) or table in SKIP_TABLES:
                continue
            if table in ("meta ", "in type table "):
                continue
            self._ensure_table(table)
            if col not in self._tables[table]["numeric"]:
                self._tables[table]["numeric"].append(col)

        # table declarations
        for m in re.finditer(r"^\s*table\s+'?(\S+?)'?\s*$", content, re.MULTILINE):
            name = m.group(1).strip("'")
            if not name.startswith(HIDDEN_TABLE_PREFIXES) and name not in SKIP_TABLES:
                self._ensure_table(name)

    # ── Helpers ───────────────────────────────────────────────────────

    def _ensure_table(self, name: str):
        if name not in self._tables:
            self._tables[name] = {
                "numeric": [], "text": [], "date": [],
                "is_hidden": name.startswith(HIDDEN_TABLE_PREFIXES),
            }

    def _decode(self, raw: bytes) -> str:
        # Power BI uses UTF-16-LE for most internal files
        for enc in ("utf-16-le", "utf-16", "utf-8"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode("latin-1", errors="replace")

    def _classify_df(self, df: pd.DataFrame) -> Tuple[List, List, List]:
        numeric, text, date = [], [], []
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            if "datetime" in dtype_str:
                date.append(col)
            elif any(t in dtype_str for t in ("int", "float", "Int", "Float")):
                numeric.append(col)
            else:
                try:
                    pd.to_numeric(df[col].dropna().head(50))
                    numeric.append(col)
                except (ValueError, TypeError):
                    text.append(col)
        return numeric, text, date
