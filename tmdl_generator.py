"""
tmdl_generator.py
Gera script TMDL com indentação idêntica ao padrão do Power BI.

Estrutura de referência (níveis de tab):
  0t  createOrReplace
  0t  (blank)
  1t  table Medidas
  2t    lineageTag: <uuid>
  0t  (blank)
  2t    measure 'Nome' = DAX
  3t      formatString: ...
  3t      lineageTag: <uuid>
  0t  (blank)
  ... (próxima measure)
  2t    partition Medidas = m
  3t      mode: import
  3t      source =
  5t          let
  5t            Origem = ...
  5t            #"Colunas Removidas" = ...
  5t          in
  5t            #"Colunas Removidas"
  0t  (blank)
  2t    annotation PBI_NavigationStepName = Navegação
  0t  (blank)
  2t    annotation PBI_ResultType = Table
"""

import uuid
from typing import Dict, List, Optional

# ── Constants ────────────────────────────────────────────────────────

CURRENCY_KEYWORDS = (
    "sales", "revenue", "price", "cost", "profit", "discount",
    "gross", "cogs", "venda", "receita", "preco", "preço",
    "custo", "lucro", "desconto", "faturamento", "valor",
    "amount", "net", "bruto", "liquido", "líquido",
)

SKIP_TIME_KEYWORDS = (
    "month number", "month name", "year", "monthno", "monno",
    "id", "rank", "order",
)

DATE_TABLE   = "dCalendario"
DATE_COLUMN  = "Data"
MEASURES_TBL = "Medidas"

# Tabs as string constants for clarity
T1 = "\t"
T2 = "\t\t"
T3 = "\t\t\t"
T5 = "\t\t\t\t\t"

PARTITION_LINES = [
    f"{T2}partition {MEASURES_TBL} = m",
    f"{T3}mode: import",
    f"{T3}source =",
    f'{T5}let',
    f'{T5}  Origem = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("i44FAA==", BinaryEncoding.Base64), Compression.Deflate)), let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [#"Coluna 1" = _t]),',
    f'{T5}    #"Colunas Removidas" = Table.RemoveColumns(Origem,{{"Coluna 1"}})',
    f'{T5}in',
    f'{T5}  #"Colunas Removidas"',
]

FOOTER_LINES = [
    "",
    f"{T2}annotation PBI_NavigationStepName = Navegação",
    "",
    f"{T2}annotation PBI_ResultType = Table",
]


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Generator ────────────────────────────────────────────────────────

class TMDLGenerator:
    def __init__(
        self,
        tables: Dict[str, dict],
        existing_measures: Optional[List[str]] = None,
        date_table: str = DATE_TABLE,
        date_column: str = DATE_COLUMN,
        generate_time: bool = True,
    ):
        self.tables        = tables
        self.existing      = set(existing_measures or [])
        self.date_table    = date_table
        self.date_column   = date_column
        self.generate_time = generate_time

    # ── Public ───────────────────────────────────────────────────────

    def generate(self) -> str:
        measures = self._collect_measures()
        if not measures:
            return (
                "// Nenhuma medida nova pôde ser gerada.\n"
                "// Todas as medidas já existem ou nenhuma coluna foi selecionada."
            )

        lines: List[str] = []

        # Header
        lines.append("createOrReplace")
        lines.append("")
        lines.append(f"{T1}table {MEASURES_TBL}")
        lines.append(f"{T2}lineageTag: {_uuid()}")

        # Measures
        for m in measures:
            lines.append("")
            lines.append(f"{T2}measure '{m['name']}' = {m['expression']}")
            if m.get("format"):
                lines.append(f"{T3}formatString: {m['format']}")
            lines.append(f"{T3}lineageTag: {_uuid()}")
            if m.get("annotation"):
                lines.append("")
                lines.append(f"{T3}annotation {m['annotation']}")

        # Partition
        lines.append("")
        lines.extend(PARTITION_LINES)

        # Footer annotations
        lines.extend(FOOTER_LINES)

        return "\n".join(lines)

    # ── Collectors ───────────────────────────────────────────────────

    def _collect_measures(self) -> List[dict]:
        out = []
        for table_name, info in self.tables.items():
            if info.get("is_hidden"):
                continue
            for col in info.get("numeric", []):
                for m in self._base(table_name, col):
                    if m["name"] not in self.existing:
                        out.append(m)
                if self.generate_time and not self._skip_time(col):
                    for m in self._time(table_name, col):
                        if m["name"] not in self.existing:
                            out.append(m)
        return out

    def _skip_time(self, col: str) -> bool:
        return any(kw in col.lower() for kw in SKIP_TIME_KEYWORDS)

    # ── Base measures ────────────────────────────────────────────────

    def _base(self, table: str, col: str) -> List[dict]:
        ref = f"{table}[{col}]"
        fmt, ann = self._fmt(col)
        return [
            {"name": f"Total {col}",    "expression": f"SUM({ref})",     "format": fmt,   "annotation": ann},
            {"name": f"Média {col}",    "expression": f"AVERAGE({ref})", "format": fmt,   "annotation": ann},
            {"name": f"Contagem {col}", "expression": f"COUNT({ref})",   "format": "#,0", "annotation": None},
            {"name": f"Máximo {col}",   "expression": f"MAX({ref})",     "format": fmt,   "annotation": ann},
            {"name": f"Mínimo {col}",   "expression": f"MIN({ref})",     "format": fmt,   "annotation": ann},
        ]

    # ── Time intelligence ────────────────────────────────────────────

    def _time(self, table: str, col: str) -> List[dict]:
        dt   = f"{self.date_table}[{self.date_column}]"
        fmt, ann = self._fmt(col)
        base = f"[Total {col}]"
        pct  = "0.00%"

        # Multi-line DAX expressions use T2 indent for continuation lines
        # so they align correctly inside the measure block (3-tab base)
        def calc(*inner_lines):
            body = f"\n{T3}\t".join(inner_lines)
            return f"CALCULATE(\n{T3}\t{body}\n{T3})"

        def var_block(atual_expr, ant_expr, return_expr):
            # VAR lines sit at T3 (3 tabs) — same indent as formatString
            return (
                f"VAR _atual = {atual_expr}\n"
                f"{T3}VAR _ant   = {ant_expr}\n"
                f"{T3}RETURN\n"
                f"{T3}\t{return_expr}"
            )

        return [
            # YTD
            {"name": f"YTD {col}",
             "expression": f"TOTALYTD({base}, {dt})",
             "format": fmt, "annotation": ann},

            # YTD Ano Anterior
            {"name": f"YTD {col} Ano Anterior",
             "expression": calc(f"TOTALYTD({base}, {dt}),", f"SAMEPERIODLASTYEAR({dt})"),
             "format": fmt, "annotation": ann},

            # MTD
            {"name": f"MTD {col}",
             "expression": f"TOTALMTD({base}, {dt})",
             "format": fmt, "annotation": ann},

            # QTD
            {"name": f"QTD {col}",
             "expression": f"TOTALQTD({base}, {dt})",
             "format": fmt, "annotation": ann},

            # Mês Anterior
            {"name": f"{col} Mês Anterior",
             "expression": calc(f"{base},", f"DATEADD({dt}, -1, MONTH)"),
             "format": fmt, "annotation": ann},

            # Ano Anterior
            {"name": f"{col} Ano Anterior",
             "expression": calc(f"{base},", f"SAMEPERIODLASTYEAR({dt})"),
             "format": fmt, "annotation": ann},

            # Var YoY absoluta
            {"name": f"Var YoY {col}",
             "expression": var_block(
                 base,
                 f"CALCULATE({base}, SAMEPERIODLASTYEAR({dt}))",
                 f"IF(NOT ISBLANK(_ant), _atual - _ant)"
             ),
             "format": fmt, "annotation": ann},

            # % YoY
            {"name": f"% YoY {col}",
             "expression": var_block(
                 base,
                 f"CALCULATE({base}, SAMEPERIODLASTYEAR({dt}))",
                 f"IF(NOT ISBLANK(_ant) && _ant <> 0, DIVIDE(_atual - _ant, _ant))"
             ),
             "format": pct, "annotation": None},

            # Var MoM absoluta
            {"name": f"Var MoM {col}",
             "expression": var_block(
                 base,
                 f"CALCULATE({base}, DATEADD({dt}, -1, MONTH))",
                 f"IF(NOT ISBLANK(_ant), _atual - _ant)"
             ),
             "format": fmt, "annotation": ann},

            # % MoM
            {"name": f"% MoM {col}",
             "expression": var_block(
                 base,
                 f"CALCULATE({base}, DATEADD({dt}, -1, MONTH))",
                 f"IF(NOT ISBLANK(_ant) && _ant <> 0, DIVIDE(_atual - _ant, _ant))"
             ),
             "format": pct, "annotation": None},
        ]

    # ── Format helpers ───────────────────────────────────────────────

    def _fmt(self, col: str):
        if any(kw in col.lower() for kw in CURRENCY_KEYWORDS):
            return (
                r"\$#,0.###############;(\$#,0.###############);\$#,0.###############",
                'PBI_FormatHint = {"currencyCulture":"en-US"}',
            )
        return "#,0.###############", None
