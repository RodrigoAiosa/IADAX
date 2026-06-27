"""
tmdl_generator.py
Generates a TMDL script with DAX measures.

For each numeric business column (non-ID/non-calendar):
  Base:      Total, Média, Contagem, Máximo, Mínimo
  Time:      YTD, YTD Ano Anterior, MTD, QTD
             Var YoY (abs), Var YoY (%), Var MoM (abs), Var MoM (%)
             Mês Anterior, Ano Anterior

Requires a date table named dCalendario with a [Data] column.
"""

from typing import Dict, List, Optional

CURRENCY_KEYWORDS = (
    "sales", "revenue", "price", "cost", "profit", "discount",
    "gross", "cogs", "venda", "receita", "preco", "preço",
    "custo", "lucro", "desconto", "faturamento", "valor",
    "amount", "net", "bruto", "liquido", "líquido",
)

# Columns that are IDs or calendar-only — skip time intelligence for these
SKIP_TIME_KEYWORDS = (
    "month number", "year", "month name", "mes", "ano",
    "id", "rank", "order", "num", "numero", "número",
    "monno", "monthno",
)

# Columns to skip entirely (pure calendar/dimension identifiers)
SKIP_ENTIRELY_KEYWORDS = (
    "month number", "month name", "year",
)

DATE_TABLE  = "dCalendario"
DATE_COLUMN = "Data"
MEASURES_TABLE = "Medidas"

PARTITION_SOURCE = (
    'let\n'
    '          Origem = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("i44FAA==", BinaryEncoding.Base64), Compression.Deflate)), '
    'let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [#"Coluna 1" = _t]),\n'
    '            #"Colunas Removidas" = Table.RemoveColumns(Origem,{"Coluna 1"})\n'
    '        in\n'
    '            #"Colunas Removidas"'
)


class TMDLGenerator:
    def __init__(
        self,
        tables: Dict[str, dict],
        existing_measures: Optional[List[str]] = None,
        date_table: str = DATE_TABLE,
        date_column: str = DATE_COLUMN,
    ):
        self.tables = tables
        self.existing = set(existing_measures or [])
        self.date_table = date_table
        self.date_column = date_column

    # ── Public ────────────────────────────────────────────────────────

    def generate(self) -> str:
        measures = self._collect_measures()
        if not measures:
            return (
                "// Nenhuma medida nova pôde ser gerada.\n"
                "// Todas as medidas possíveis já existem ou não há colunas numéricas detectadas."
            )

        lines = ["createOrReplace", ""]
        lines.append(f"\ttable {MEASURES_TABLE}")
        lines.append("")

        for m in measures:
            lines.append(f"\t\tmeasure '{m['name']}' = {m['expression']}")
            if m.get("format"):
                lines.append(f"\t\t\tformatString: {m['format']}")
            if m.get("annotation"):
                lines.append(f"\n\t\t\tannotation {m['annotation']}")
            lines.append("")

        # Partition boilerplate
        lines.append(f"\t\tpartition {MEASURES_TABLE} = m")
        lines.append("\t\t\tmode: import")
        lines.append("\t\t\tsource =")
        for src_line in PARTITION_SOURCE.splitlines():
            lines.append(f"\t\t\t\t\t{src_line}")
        lines.append("")
        lines.append("\t\tannotation PBI_NavigationStepName = Navegação")
        lines.append("")
        lines.append("\t\tannotation PBI_ResultType = Table")
        lines.append("")

        return "\n".join(lines)

    # ── Collectors ────────────────────────────────────────────────────

    def _collect_measures(self) -> List[dict]:
        measures = []
        for table_name, info in self.tables.items():
            if info.get("is_hidden"):
                continue
            for col in info.get("numeric", []):
                col_lower = col.lower()

                # Skip pure calendar columns entirely
                if any(kw == col_lower for kw in SKIP_ENTIRELY_KEYWORDS):
                    continue

                for m in self._base_measures(table_name, col):
                    if m["name"] not in self.existing:
                        measures.append(m)

                # Time intelligence: skip for ID/calendar-like columns
                skip_time = any(kw in col_lower for kw in SKIP_TIME_KEYWORDS)
                if not skip_time:
                    for m in self._time_measures(table_name, col):
                        if m["name"] not in self.existing:
                            measures.append(m)

        return measures

    # ── Base measures ─────────────────────────────────────────────────

    def _base_measures(self, table: str, col: str) -> List[dict]:
        ref = f"{table}[{col}]"
        fmt, ann = self._fmt(col)
        return [
            {"name": f"Total {col}",    "expression": f"SUM({ref})",     "format": fmt,   "annotation": ann},
            {"name": f"Média {col}",    "expression": f"AVERAGE({ref})", "format": fmt,   "annotation": ann},
            {"name": f"Contagem {col}", "expression": f"COUNT({ref})",   "format": "#,0", "annotation": None},
            {"name": f"Máximo {col}",   "expression": f"MAX({ref})",     "format": fmt,   "annotation": ann},
            {"name": f"Mínimo {col}",   "expression": f"MIN({ref})",     "format": fmt,   "annotation": ann},
        ]

    # ── Time-intelligence measures ────────────────────────────────────

    def _time_measures(self, table: str, col: str) -> List[dict]:
        ref  = f"{table}[{col}]"
        dt   = f"{self.date_table}[{self.date_column}]"
        fmt, ann = self._fmt(col)
        pct_fmt = "0.00%"

        # Reference the base SUM measure by name (keeps DAX DRY)
        base_name = f"Total {col}"
        base_ref  = f"[{base_name}]"

        measures = [
            # ── YTD ──────────────────────────────────────────────────
            {
                "name": f"YTD {col}",
                "expression": f"TOTALYTD({base_ref}, {dt})",
                "format": fmt, "annotation": ann,
            },
            {
                "name": f"YTD {col} Ano Anterior",
                "expression": (
                    f"CALCULATE(\n"
                    f"\t\t\t\tTOTALYTD({base_ref}, {dt}),\n"
                    f"\t\t\t\tSAMEPERIODLASTYEAR({dt})\n"
                    f"\t\t\t)"
                ),
                "format": fmt, "annotation": ann,
            },

            # ── MTD ──────────────────────────────────────────────────
            {
                "name": f"MTD {col}",
                "expression": f"TOTALMTD({base_ref}, {dt})",
                "format": fmt, "annotation": ann,
            },

            # ── QTD ──────────────────────────────────────────────────
            {
                "name": f"QTD {col}",
                "expression": f"TOTALQTD({base_ref}, {dt})",
                "format": fmt, "annotation": ann,
            },

            # ── Período anterior ─────────────────────────────────────
            {
                "name": f"{col} Mês Anterior",
                "expression": (
                    f"CALCULATE(\n"
                    f"\t\t\t\t{base_ref},\n"
                    f"\t\t\t\tDATEADD({dt}, -1, MONTH)\n"
                    f"\t\t\t)"
                ),
                "format": fmt, "annotation": ann,
            },
            {
                "name": f"{col} Ano Anterior",
                "expression": (
                    f"CALCULATE(\n"
                    f"\t\t\t\t{base_ref},\n"
                    f"\t\t\t\tSAMEPERIODLASTYEAR({dt})\n"
                    f"\t\t\t)"
                ),
                "format": fmt, "annotation": ann,
            },

            # ── Variações YoY ────────────────────────────────────────
            {
                "name": f"Var YoY {col}",
                "expression": (
                    f"VAR _atual = {base_ref}\n"
                    f"\t\t\tVAR _anterior = CALCULATE({base_ref}, SAMEPERIODLASTYEAR({dt}))\n"
                    f"\t\t\tRETURN\n"
                    f"\t\t\t\tIF(NOT ISBLANK(_anterior), _atual - _anterior)"
                ),
                "format": fmt, "annotation": ann,
            },
            {
                "name": f"% YoY {col}",
                "expression": (
                    f"VAR _atual = {base_ref}\n"
                    f"\t\t\tVAR _anterior = CALCULATE({base_ref}, SAMEPERIODLASTYEAR({dt}))\n"
                    f"\t\t\tRETURN\n"
                    f"\t\t\t\tIF(\n"
                    f"\t\t\t\t\tNOT ISBLANK(_anterior) && _anterior <> 0,\n"
                    f"\t\t\t\t\tDIVIDE(_atual - _anterior, _anterior)\n"
                    f"\t\t\t\t)"
                ),
                "format": pct_fmt, "annotation": None,
            },

            # ── Variações MoM ────────────────────────────────────────
            {
                "name": f"Var MoM {col}",
                "expression": (
                    f"VAR _atual = {base_ref}\n"
                    f"\t\t\tVAR _anterior = CALCULATE({base_ref}, DATEADD({dt}, -1, MONTH))\n"
                    f"\t\t\tRETURN\n"
                    f"\t\t\t\tIF(NOT ISBLANK(_anterior), _atual - _anterior)"
                ),
                "format": fmt, "annotation": ann,
            },
            {
                "name": f"% MoM {col}",
                "expression": (
                    f"VAR _atual = {base_ref}\n"
                    f"\t\t\tVAR _anterior = CALCULATE({base_ref}, DATEADD({dt}, -1, MONTH))\n"
                    f"\t\t\tRETURN\n"
                    f"\t\t\t\tIF(\n"
                    f"\t\t\t\t\tNOT ISBLANK(_anterior) && _anterior <> 0,\n"
                    f"\t\t\t\t\tDIVIDE(_atual - _anterior, _anterior)\n"
                    f"\t\t\t\t)"
                ),
                "format": pct_fmt, "annotation": None,
            },
        ]
        return measures

    # ── Helpers ───────────────────────────────────────────────────────

    def _fmt(self, col: str):
        is_currency = any(kw in col.lower() for kw in CURRENCY_KEYWORDS)
        if is_currency:
            return (
                r"R$\ #,0.00;(R$\ #,0.00);R$\ #,0.00",
                'PBI_FormatHint = {"currencyCulture":"pt-BR"}',
            )
        return "#,0.00", None
