"""
pbix_parser.py
Parses a .pbix file (ZIP archive) and extracts table/column metadata
using the DataModel (via pbixray) and falls back to TMDL scripts.
"""

import io
import zipfile
import re
from typing import Dict, List
import pandas as pd

# Prefixes used by Power BI for internal/hidden date tables
HIDDEN_PREFIXES = (
    "DateTableTemplate_",
    "LocalDateTable_",
)

NUMERIC_PANDAS_TYPES = {"int64", "float64", "int32", "float32", "Int64", "Float64"}
DATE_PANDAS_TYPES = {"datetime64[ns]", "datetime64[us]"}


class PBIXParser:
    def __init__(self, file_bytes: bytes):
        self.file_bytes = file_bytes
        self._tables: Dict[str, dict] = {}

    def get_tables(self) -> Dict[str, dict]:
        """
        Returns a dict keyed by table name with:
            numeric: list of numeric column names
            text:    list of string column names
            date:    list of date column names
            is_hidden: bool
        """
        self._tables = {}
        self._parse_via_pbixray()
        return self._tables

    def _parse_via_pbixray(self):
        """Use pbixray to read the DataModel binary."""
        try:
            import tempfile, os
            from pbixray import PBIXRay

            with tempfile.NamedTemporaryFile(suffix=".pbix", delete=False) as tmp:
                tmp.write(self.file_bytes)
                tmp_path = tmp.name

            try:
                model = PBIXRay(tmp_path)
                for table_name in model.tables:
                    is_hidden = str(table_name).startswith(HIDDEN_PREFIXES)
                    try:
                        df = model.get_table(table_name)
                        numeric, text, date = self._classify_columns(df)
                        self._tables[table_name] = {
                            "numeric": numeric,
                            "text": text,
                            "date": date,
                            "is_hidden": is_hidden,
                        }
                    except Exception:
                        # Table exists but couldn't read rows (e.g. empty/error)
                        self._tables[table_name] = {
                            "numeric": [],
                            "text": [],
                            "date": [],
                            "is_hidden": is_hidden,
                        }
            finally:
                os.unlink(tmp_path)

        except ImportError:
            # pbixray not available — fall back to TMDL script parsing
            self._parse_via_tmdl_scripts()

    def _classify_columns(self, df: pd.DataFrame):
        numeric, text, date = [], [], []
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            if any(t in dtype_str for t in ("datetime",)):
                date.append(col)
            elif any(t in dtype_str for t in ("int", "float", "Int", "Float")):
                numeric.append(col)
            else:
                text.append(col)
        return numeric, text, date

    def _parse_via_tmdl_scripts(self):
        """
        Fallback: scan TMDLScripts inside the ZIP for table/measure hints.
        This gives measure names already defined; we won't generate duplicates.
        """
        try:
            buf = io.BytesIO(self.file_bytes)
            with zipfile.ZipFile(buf, "r") as z:
                for name in z.namelist():
                    if name.startswith("TMDLScripts/") and name.endswith(".tmdl"):
                        raw = z.read(name)
                        try:
                            content = raw.decode("utf-16-le")
                        except Exception:
                            content = raw.decode("utf-8", errors="replace")
                        self._parse_tmdl_text(content)
        except Exception:
            pass

    def _parse_tmdl_text(self, content: str):
        """Very lightweight TMDL text parser to extract table names."""
        table_re = re.compile(r"^\s*table\s+'?([^'\r\n]+)'?", re.MULTILINE)
        for m in table_re.finditer(content):
            table_name = m.group(1).strip()
            if table_name not in self._tables:
                self._tables[table_name] = {
                    "numeric": [],
                    "text": [],
                    "date": [],
                    "is_hidden": False,
                }
