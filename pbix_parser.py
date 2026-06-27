"""
pbix_parser.py
Parses a .pbix file using only stdlib (zipfile) + pandas.
No pbixray, no xpress9, no compiled dependencies.

Strategy:
1. Extract TMDL scripts from TMDLScripts/*.tmdl  → gives us existing
   table[column] references and measure names.
2. If the user also uploads a CSV/Excel sample, classify columns from that.
3. Build a unified table/column schema from both sources.
"""

import io
import re
import zipfile
from typing import Dict, List, Tuple, Optional
import pandas as pd


HIDDEN_TABLE_PREFIXES = ("DateTableTemplate_", "LocalDateTable_")

# DAX aggregate functions and their column types
NUMERIC_HINTS = {
    "SUM", "AVERAGE", "MIN", "MAX", "COUNT", "DISTINCTCOUNT",
    "SUMX", "AVERAGEX", "MINX", "MAXX", "COUNTX",
}

CURRENCY_KEYWORDS = (
    "sales", "revenue", "price", "cost", "profit", "discount",
    "gross", "cogs", "venda", "receita", "preco", "preço",
    "custo", "lucro", "desconto", "faturamento", "valor", "total",
    "amount", "net", "bruto", "liquido", "líquido",
)

INTEGER_KEYWORDS = (
    "units", "qty", "quantity", "count", "num", "qtd",
    "unidades", "quantidade", "numero", "número", "id",
    "month", "year", "mes", "ano", "rank", "order",
)


class PBIXParser:
    def __init__(self, file_bytes: bytes):
        self.file_bytes = file_bytes
        self._tables: Dict[str, dict] = {}
        self._existing_measures: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tables(self) -> Dict[str, dict]:
        """
        Returns dict keyed by table name:
            numeric:   [col, ...]
            text:      [col, ...]
            date:      [col, ...]
            is_hidden: bool
        """
        self._tables = {}
        self._parse_tmdl_scripts()
        return self._tables

    def get_existing_measures(self) -> List[str]:
        return self._existing_measures

    def enrich_from_dataframe(self, table_name: str, df: pd.DataFrame):
        """Enrich (or create) a table entry from a pandas DataFrame."""
        numeric, text, date = self._classify_df(df)
        if table_name not in self._tables:
            self._tables[table_name] = {
                "numeric": numeric,
                "text": text,
                "date": date,
                "is_hidden": False,
            }
        else:
            # Merge: add columns not already present
            existing_num = set(self._tables[table_name]["numeric"])
            existing_txt = set(self._tables[table_name]["text"])
            existing_date = set(self._tables[table_name]["date"])
            for c in numeric:
                if c not in existing_num:
                    self._tables[table_name]["numeric"].append(c)
            for c in text:
                if c not in existing_txt:
                    self._tables[table_name]["text"].append(c)
            for c in date:
                if c not in existing_date:
                    self._tables[table_name]["date"].append(c)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_tmdl_scripts(self):
        """Read all TMDLScripts/*.tmdl inside the .pbix ZIP."""
        try:
            buf = io.BytesIO(self.file_bytes)
            with zipfile.ZipFile(buf, "r") as z:
                tmdl_files = [n for n in z.namelist()
                              if n.startswith("TMDLScripts/") and n.endswith(".tmdl")]
                for fname in tmdl_files:
                    raw = z.read(fname)
                    content = self._decode(raw)
                    self._parse_tmdl_content(content)
        except zipfile.BadZipFile:
            pass

    def _decode(self, raw: bytes) -> str:
        """Try UTF-16-LE first (Power BI default), then UTF-8."""
        try:
            return raw.decode("utf-16-le")
        except Exception:
            return raw.decode("utf-8", errors="replace")

    def _parse_tmdl_content(self, content: str):
        """
        Extract table names, column references, and measure names from TMDL text.
        """
        # Existing measure names (to skip regenerating them)
        measure_names = re.findall(r"measure '([^']+)'", content)
        self._existing_measures.extend(measure_names)

        # table[column] references inside DAX expressions
        # e.g.: SUM(fVendas[Gross Sales])
        dax_refs = re.findall(r"'?([\w][\w\s]*?)'?\[([^\]]+)\]", content)

        # Infer column types from the DAX function wrapping them
        # e.g.: SUM(fVendas[Sales]) → Sales is numeric
        for func_match in re.finditer(
            r"(\bSUM\b|\bAVERAGE\b|\bMIN\b|\bMAX\b|\bCOUNT\b)\s*\(\s*'?([\w][\w\s]*?)'?\[([^\]]+)\]",
            content,
            re.IGNORECASE,
        ):
            func, table, col = func_match.group(1), func_match.group(2).strip(), func_match.group(3).strip()
            if table.startswith(HIDDEN_TABLE_PREFIXES):
                continue
            if table in ("meta ", "in type table "):
                continue
            self._ensure_table(table)
            if col not in self._tables[table]["numeric"]:
                self._tables[table]["numeric"].append(col)

        # Also collect table names from `table <Name>` declarations
        for m in re.finditer(r"^\s*table\s+(\S+)", content, re.MULTILINE):
            name = m.group(1).strip("'")
            if not name.startswith(HIDDEN_TABLE_PREFIXES):
                self._ensure_table(name)

    def _ensure_table(self, name: str):
        if name not in self._tables:
            self._tables[name] = {
                "numeric": [],
                "text": [],
                "date": [],
                "is_hidden": name.startswith(HIDDEN_TABLE_PREFIXES),
            }

    def _classify_df(self, df: pd.DataFrame) -> Tuple[List, List, List]:
        numeric, text, date = [], [], []
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            if "datetime" in dtype_str:
                date.append(col)
            elif any(t in dtype_str for t in ("int", "float", "Int", "Float")):
                numeric.append(col)
            else:
                # Try to coerce to numeric
                try:
                    pd.to_numeric(df[col].dropna().head(50))
                    numeric.append(col)
                except (ValueError, TypeError):
                    text.append(col)
        return numeric, text, date
