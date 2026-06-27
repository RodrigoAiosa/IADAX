"""
tmdl_generator.py
Generates a TMDL script with DAX measures based on detected numeric columns.

Measure templates per numeric column:
  - Total <Column>     → SUM
  - Média <Column>     → AVERAGE
  - Qtd <Column>       → COUNT
  - Máx <Column>       → MAX
  - Mín <Column>       → MIN

Format strings are inferred from column name keywords.
"""

from typing import Dict, List
import re

# Keywords that hint at currency columns (case-insensitive)
CURRENCY_KEYWORDS = (
    "sales", "revenue", "price", "cost", "profit", "discount",
    "gross", "cogs", "venda", "receita", "preco", "preço",
    "custo", "lucro", "desconto", "faturamento",
)

# Keywords that hint at integer/count columns
COUNT_KEYWORDS = (
    "units", "qty", "quantity", "count", "num", "qtd",
    "unidades", "quantidade", "numero", "número",
)

PARTITION_M_SOURCE = (
    'let\n'
    '          Origem = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("i44FAA==", BinaryEncoding.Base64), Compression.Deflate)), '
    'let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [#"Coluna 1" = _t]),\n'
    '            #"Colunas Removidas" = Table.RemoveColumns(Origem,{"Coluna 1"})\n'
    '        in\n'
    '            #"Colunas Removidas"'
)

MEASURES_TABLE_NAME = "Medidas"


class TMDLGenerator:
    def __init__(self, tables: Dict[str, dict]):
        self.tables = tables

    def generate(self) -> str:
        measures = self._collect_measures()

        if not measures:
            return "// Nenhuma medida pôde ser gerada. Verifique se o arquivo contém colunas numéricas."

        lines = ["createOrReplace", ""]
        lines.append(f"\ttable {MEASURES_TABLE_NAME}")
        lines.append("")

        for m in measures:
            lines.append(f"\t\tmeasure '{m['name']}' = {m['expression']}")
            if m.get("format"):
                lines.append(f"\t\t\tformatString: {m['format']}")
            if m.get("annotation"):
                lines.append(f"\n\t\t\tannotation {m['annotation']}")
            lines.append("")

        # Partition (required boilerplate for Measures table)
        lines.append(f"\t\tpartition {MEASURES_TABLE_NAME} = m")
        lines.append("\t\t\tmode: import")
        lines.append("\t\t\tsource =")
        for src_line in PARTITION_M_SOURCE.splitlines():
            lines.append(f"\t\t\t\t\t{src_line}")
        lines.append("")
        lines.append("\t\tannotation PBI_NavigationStepName = Navegação")
        lines.append("")
        lines.append("\t\tannotation PBI_ResultType = Table")
        lines.append("")

        return "\n".join(lines)

    def _collect_measures(self) -> List[dict]:
        measures = []
        for table_name, info in self.tables.items():
            if info.get("is_hidden"):
                continue
            for col in info.get("numeric", []):
                measures.extend(self._measures_for_column(table_name, col))
        return measures

    def _measures_for_column(self, table: str, col: str) -> List[dict]:
        ref = f"{table}[{col}]"
        fmt_currency, fmt_int, fmt_decimal = self._infer_formats(col)
        measures = []

        # SUM
        measures.append({
            "name": f"Total {col}",
            "expression": f"SUM({ref})",
            "format": fmt_currency if fmt_currency else fmt_decimal,
            "annotation": 'PBI_FormatHint = {"currencyCulture":"pt-BR"}' if fmt_currency else None,
        })

        # AVERAGE
        measures.append({
            "name": f"Média {col}",
            "expression": f"AVERAGE({ref})",
            "format": fmt_currency if fmt_currency else fmt_decimal,
            "annotation": 'PBI_FormatHint = {"currencyCulture":"pt-BR"}' if fmt_currency else None,
        })

        # COUNT
        measures.append({
            "name": f"Contagem {col}",
            "expression": f"COUNT({ref})",
            "format": "#,0",
            "annotation": None,
        })

        # MAX
        measures.append({
            "name": f"Máximo {col}",
            "expression": f"MAX({ref})",
            "format": fmt_currency if fmt_currency else fmt_decimal,
            "annotation": 'PBI_FormatHint = {"currencyCulture":"pt-BR"}' if fmt_currency else None,
        })

        # MIN
        measures.append({
            "name": f"Mínimo {col}",
            "expression": f"MIN({ref})",
            "format": fmt_currency if fmt_currency else fmt_decimal,
            "annotation": 'PBI_FormatHint = {"currencyCulture":"pt-BR"}' if fmt_currency else None,
        })

        return measures

    def _infer_formats(self, col: str):
        col_lower = col.lower()

        is_currency = any(kw in col_lower for kw in CURRENCY_KEYWORDS)
        is_count = any(kw in col_lower for kw in COUNT_KEYWORDS)

        fmt_currency = None
        fmt_int = "#,0"
        fmt_decimal = "#,0.00"

        if is_currency:
            fmt_currency = r'R$\ #,0.00;(R$\ #,0.00);R$\ #,0.00'

        return fmt_currency, fmt_int, fmt_decimal
