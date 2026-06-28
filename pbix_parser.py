"""
pbix_parser.py — lê schema completo do .pbix.

Estratégia em camadas (da mais rica para a mais simples):
  1. pbixray  → DataModel descomprimido, schema completo com tipos
  2. zipfile  → DiagramLayout (nomes de tabelas) + TMDLScripts (refs DAX)

No Streamlit Cloud (Python 3.14) pbixray não instala; usamos a camada 2.
A UI detecta automaticamente qual nível de informação foi obtido e
ajusta a experiência (ex.: mostra aviso se só obteve nomes de tabelas).
"""

import io
import re
import json
import zipfile
import tempfile
import os
from typing import Dict, List, Tuple, Optional

import pandas as pd

HIDDEN_PREFIXES  = ("DateTableTemplate_", "LocalDateTable_")
SKIP_TABLE_NAMES = {"Medidas", "Measures", "_Measures"}

NUMERIC_DTYPES = {"int", "float", "Int", "Float"}
DATE_DTYPES    = {"datetime"}


class PBIXParser:
    def __init__(self, file_bytes: bytes):
        self.file_bytes   = file_bytes
        self._tables: Dict[str, dict] = {}
        self._existing_measures: List[str] = []
        self._source: str = "unknown"   # "pbixray" | "tmdl" | "layout"

    # ── Public API ────────────────────────────────────────────────────

    @property
    def source(self) -> str:
        """Which layer supplied the schema."""
        return self._source

    def get_tables(self) -> Dict[str, dict]:
        """
        Returns dict keyed by table name:
            numeric:   list[str]
            text:      list[str]
            date:      list[str]
            is_hidden: bool
        Parse is idempotent — subsequent calls return cached result.
        """
        if self._tables:
            return self._tables

        if self._try_pbixray():
            return self._tables

        # Fallback: zipfile-only
        self._parse_diagram_layout()
        self._parse_tmdl_scripts()
        return self._tables

    def get_existing_measures(self) -> List[str]:
        if not self._tables:
            self.get_tables()
        return self._existing_measures

    # ── Layer 1: pbixray ──────────────────────────────────────────────

    def _try_pbixray(self) -> bool:
        try:
            from pbixray import PBIXRay
        except ImportError:
            return False

        try:
            with tempfile.NamedTemporaryFile(suffix=".pbix", delete=False) as tmp:
                tmp.write(self.file_bytes)
                tmp_path = tmp.name

            model = PBIXRay(tmp_path)

            for table_name in model.tables:
                if self._is_hidden(table_name) or table_name in SKIP_TABLE_NAMES:
                    continue
                try:
                    df = model.get_table(table_name)
                    numeric, text, date = self._classify_df(df)
                except Exception:
                    numeric, text, date = [], [], []

                self._tables[table_name] = {
                    "numeric":   numeric,
                    "text":      text,
                    "date":      date,
                    "is_hidden": False,
                }

            self._source = "pbixray"
            return True

        except Exception:
            return False

        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # ── Layer 2: zipfile ──────────────────────────────────────────────

    def _parse_diagram_layout(self):
        try:
            buf = io.BytesIO(self.file_bytes)
            with zipfile.ZipFile(buf) as z:
                if "DiagramLayout" not in z.namelist():
                    return
                data = json.loads(self._decode(z.read("DiagramLayout")))
                for diagram in data.get("diagrams", []):
                    for node in diagram.get("nodes", []):
                        name = node.get("nodeIndex", "").strip("'")
                        if name and not self._is_hidden(name) and name not in SKIP_TABLE_NAMES:
                            self._ensure_table(name)
                self._source = "layout"
        except Exception:
            pass

    def _parse_tmdl_scripts(self):
        try:
            buf = io.BytesIO(self.file_bytes)
            with zipfile.ZipFile(buf) as z:
                for fname in z.namelist():
                    if fname.startswith("TMDLScripts/") and fname.endswith(".tmdl"):
                        raw = z.read(fname)
                        if raw:
                            self._parse_tmdl_content(self._decode(raw))
            if self._source == "layout":
                self._source = "tmdl"
        except Exception:
            pass

    def _parse_tmdl_content(self, content: str):
        # existing measure names
        self._existing_measures += re.findall(r"measure '([^']+)'", content)

        # DAX function refs → numeric columns
        for m in re.compile(
            r"\b(SUM|AVERAGE|MIN|MAX|COUNT)\s*\(\s*'?([\w][\w\s]*?)'?\[([^\]]+)\]",
            re.IGNORECASE,
        ).finditer(content):
            table, col = m.group(2).strip(), m.group(3).strip()
            if self._is_hidden(table) or table in SKIP_TABLE_NAMES:
                continue
            self._ensure_table(table)
            if col not in self._tables[table]["numeric"]:
                self._tables[table]["numeric"].append(col)

    # ── Helpers ───────────────────────────────────────────────────────

    def _is_hidden(self, name: str) -> bool:
        return name.startswith(HIDDEN_PREFIXES)

    def _ensure_table(self, name: str):
        if name not in self._tables:
            self._tables[name] = {
                "numeric": [], "text": [], "date": [],
                "is_hidden": self._is_hidden(name),
            }

    def _decode(self, raw: bytes) -> str:
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
            if any(t in dtype_str for t in DATE_DTYPES):
                date.append(col)
            elif any(t in dtype_str for t in NUMERIC_DTYPES):
                numeric.append(col)
            else:
                text.append(col)
        return numeric, text, date
