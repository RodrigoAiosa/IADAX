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

from typing import Dict, List, Optional, Tuple
import re

CURRENCY_KEYWORDS = (
    "sales", "revenue", "price", "cost", "profit", "discount",
    "gross", "cogs", "venda", "receita", "preco", "preço",
    "custo", "lucro", "desconto", "faturamento", "valor",
    "amount", "net", "bruto", "liquido", "líquido",
)

# Columns that are IDs or calendar-only — skip time intelligence
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

# Ordered group names for display
GROUP_ORDER = [
    "Agregadores",
    "Acumulados (YTD)",
    "Acumulados (MTD)",
    "Acumulados (QTD)",
    "Períodos Anteriores",
    "Variações (YoY)",
    "Variações (MoM)",
    "Outras",
]


class TMDLGenerator:
    def __init__(
        self,
        tables: Dict[str, dict],
        existing_measures: Optional[List[str]] = None,
        date_table: str = DATE_TABLE,
        date_column: str = DATE_COLUMN,
        gen_time: bool = True,
        measures_table_name: str = MEASURES_TABLE,
        ai_measures: Optional[List[dict]] = None,
    ):
        self.tables = tables
        self.existing = set(existing_measures or [])
        self.date_table = date_table
        self.date_column = date_column
        self.gen_time = gen_time
        self.measures_table_name = measures_table_name
        self.ai_measures = ai_measures or []

    # ── Public ────────────────────────────────────────────────────────

    def generate(self) -> str:
        """Gera o script TMDL completo com medidas organizadas."""
        measures = self._collect_measures()

        # Append AI-suggested measures (if not already existing)
        for ai_m in self.ai_measures:
            if ai_m.get("name") and ai_m["name"] not in self.existing:
                ai_m.setdefault("format", '"#,0.00"')
                ai_m.setdefault("annotation", None)
                ai_m.setdefault("is_currency", False)
                ai_m.setdefault("single_line", True)
                ai_m.setdefault("group", "IA Sugeridas")
                measures.append(ai_m)

        if not measures:
            return (
                "// Nenhuma medida nova pôde ser gerada.\n"
                "// Todas as medidas possíveis já existem ou não há colunas numéricas detectadas."
            )

        grouped = self._group_measures(measures)

        lines = ["createOrReplace", ""]
        lines.append(f"\ttable {self.measures_table_name}")
        lines.append("")

        # Output groups in defined order, then any remaining
        all_group_keys = list(GROUP_ORDER)
        for g in grouped:
            if g not in all_group_keys:
                all_group_keys.append(g)

        for group_name in all_group_keys:
            group_measures = grouped.get(group_name, [])
            if group_measures:
                lines.append(f"\t\t// ── {group_name} ──")
                for m in group_measures:
                    lines.extend(self._format_measure(m))
                lines.append("")

        lines.extend(self._get_partition_lines())
        lines.append("")
        return "\n".join(lines)

    def count_measures(self) -> dict:
        """Returns counts for the stats display."""
        measures = self._collect_measures()
        grouped = self._group_measures(measures)
        total = len(measures) + len(self.ai_measures)
        return {
            "total": total,
            "by_group": {k: len(v) for k, v in grouped.items()},
            "ai_count": len(self.ai_measures),
        }

    # ── Collectors ────────────────────────────────────────────────────

    def _collect_measures(self) -> List[dict]:
        measures = []
        for table_name, info in self.tables.items():
            if info.get("is_hidden"):
                continue
            for col in info.get("numeric", []):
                col_lower = col.lower()

                if any(kw == col_lower for kw in SKIP_ENTIRELY_KEYWORDS):
                    continue

                for m in self._base_measures(table_name, col):
                    if m["name"] not in self.existing:
                        measures.append(m)

                if self.gen_time:
                    skip_time = any(kw in col_lower for kw in SKIP_TIME_KEYWORDS)
                    if not skip_time:
                        for m in self._time_measures(table_name, col):
                            if m["name"] not in self.existing:
                                measures.append(m)

        return measures

    def _group_measures(self, measures: List[dict]) -> Dict[str, List[dict]]:
        groups: Dict[str, List[dict]] = {}
        for m in measures:
            group = m.get("group") or self._infer_group(m["name"])
            groups.setdefault(group, []).append(m)
        return groups

    def _infer_group(self, name: str) -> str:
        if name.startswith(("Total ", "Média ", "Contagem ", "Máximo ", "Mínimo ")):
            return "Agregadores"
        if "YTD" in name:
            return "Acumulados (YTD)"
        if "MTD" in name:
            return "Acumulados (MTD)"
        if "QTD" in name:
            return "Acumulados (QTD)"
        if "Ano Anterior" in name or "Mês Anterior" in name:
            return "Períodos Anteriores"
        if "MoM" in name:
            return "Variações (MoM)"
        if "YoY" in name:
            return "Variações (YoY)"
        return "Outras"

    # ── Base measures ─────────────────────────────────────────────────

    def _base_measures(self, table: str, col: str) -> List[dict]:
        ref = f"{table}[{col}]"
        fmt, ann, is_currency = self._fmt(col)
        return [
            {"name": f"Total {col}", "expression": f"SUM({ref})", "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": True},
            {"name": f"Média {col}", "expression": f"AVERAGE({ref})", "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": True},
            {"name": f"Contagem {col}", "expression": f"COUNT({ref})", "format": '"#,0"', "annotation": None, "is_currency": False, "single_line": True},
            {"name": f"Máximo {col}", "expression": f"MAX({ref})", "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": True},
            {"name": f"Mínimo {col}", "expression": f"MIN({ref})", "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": True},
        ]

    # ── Time-intelligence measures ────────────────────────────────────

    def _time_measures(self, table: str, col: str) -> List[dict]:
        dt = f"{self.date_table}[{self.date_column}]"
        fmt, ann, is_currency = self._fmt(col)
        pct_fmt = '"0.00%"'
        base_ref = f"[Total {col}]"

        # TMDL multiline format: expression on next line, indented with \t\t\t\t
        # measure 'Name' =
        #     CALCULATE(
        #         [Base],
        #         FILTER(...)
        #     )
        # Properties (formatString, annotation) go at \t\t\t level

        return [
            {
                "name": f"YTD {col}",
                "expression": f"TOTALYTD({base_ref}, {dt})",
                "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": True,
            },
            {
                "name": f"YTD {col} Ano Anterior",
                "expression": (
                    "\n\t\t\t\tCALCULATE(\n"
                    f"\t\t\t\t\tTOTALYTD({base_ref}, {dt}),\n"
                    f"\t\t\t\t\tSAMEPERIODLASTYEAR({dt})\n"
                    "\t\t\t\t)"
                ),
                "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": False,
            },
            {
                "name": f"MTD {col}",
                "expression": f"TOTALMTD({base_ref}, {dt})",
                "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": True,
            },
            {
                "name": f"QTD {col}",
                "expression": f"TOTALQTD({base_ref}, {dt})",
                "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": True,
            },
            {
                "name": f"{col} Mês Anterior",
                "expression": (
                    "\n\t\t\t\tCALCULATE(\n"
                    f"\t\t\t\t\t{base_ref},\n"
                    f"\t\t\t\t\tDATEADD({dt}, -1, MONTH)\n"
                    "\t\t\t\t)"
                ),
                "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": False,
            },
            {
                "name": f"{col} Ano Anterior",
                "expression": (
                    "\n\t\t\t\tCALCULATE(\n"
                    f"\t\t\t\t\t{base_ref},\n"
                    f"\t\t\t\t\tSAMEPERIODLASTYEAR({dt})\n"
                    "\t\t\t\t)"
                ),
                "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": False,
            },
            {
                "name": f"Var YoY {col}",
                "expression": (
                    "\n"
                    f"\t\t\t\tVAR _atual = {base_ref}\n"
                    f"\t\t\t\tVAR _anterior = CALCULATE({base_ref}, SAMEPERIODLASTYEAR({dt}))\n"
                    "\t\t\t\tRETURN\n"
                    "\t\t\t\t\tIF(NOT ISBLANK(_anterior), _atual - _anterior)"
                ),
                "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": False,
            },
            {
                "name": f"% YoY {col}",
                "expression": (
                    "\n"
                    f"\t\t\t\tVAR _atual = {base_ref}\n"
                    f"\t\t\t\tVAR _anterior = CALCULATE({base_ref}, SAMEPERIODLASTYEAR({dt}))\n"
                    "\t\t\t\tRETURN\n"
                    "\t\t\t\t\tIF(\n"
                    "\t\t\t\t\t\tNOT ISBLANK(_anterior) && _anterior <> 0,\n"
                    "\t\t\t\t\t\tDIVIDE(_atual - _anterior, _anterior)\n"
                    "\t\t\t\t\t)"
                ),
                "format": pct_fmt, "annotation": None, "is_currency": False, "single_line": False,
            },
            {
                "name": f"Var MoM {col}",
                "expression": (
                    "\n"
                    f"\t\t\t\tVAR _atual = {base_ref}\n"
                    f"\t\t\t\tVAR _anterior = CALCULATE({base_ref}, DATEADD({dt}, -1, MONTH))\n"
                    "\t\t\t\tRETURN\n"
                    "\t\t\t\t\tIF(NOT ISBLANK(_anterior), _atual - _anterior)"
                ),
                "format": fmt, "annotation": ann, "is_currency": is_currency, "single_line": False,
            },
            {
                "name": f"% MoM {col}",
                "expression": (
                    "\n"
                    f"\t\t\t\tVAR _atual = {base_ref}\n"
                    f"\t\t\t\tVAR _anterior = CALCULATE({base_ref}, DATEADD({dt}, -1, MONTH))\n"
                    "\t\t\t\tRETURN\n"
                    "\t\t\t\t\tIF(\n"
                    "\t\t\t\t\t\tNOT ISBLANK(_anterior) && _anterior <> 0,\n"
                    "\t\t\t\t\t\tDIVIDE(_atual - _anterior, _anterior)\n"
                    "\t\t\t\t\t)"
                ),
                "format": pct_fmt, "annotation": None, "is_currency": False, "single_line": False,
            },
        ]

    # ── Formatting ────────────────────────────────────────────────────

    def _format_measure(self, measure: dict) -> List[str]:
        lines = []
        name = measure["name"]
        expr = measure["expression"]
        fmt = measure.get("format")
        ann = measure.get("annotation")
        single_line = measure.get("single_line", False)

        if single_line or "\n" not in expr:
            # Single-line: measure 'Name' = EXPRESSION
            lines.append(f"\t\tmeasure '{name}' = {expr.strip()}")
        else:
            # Multiline: measure 'Name' =
            #     (expression already contains leading \n and correct tabs)
            lines.append(f"\t\tmeasure '{name}' ={expr}")

        if fmt:
            clean_fmt = fmt.strip('"')
            lines.append(f'\t\t\tformatString: "{clean_fmt}"')

        if ann:
            lines.append(f"\t\t\tannotation {ann}")

        return lines

    def _fmt(self, col: str) -> Tuple[str, Optional[str], bool]:
        is_currency = any(kw in col.lower() for kw in CURRENCY_KEYWORDS)
        if is_currency:
            return (
                r'"R$ #,0.00;(R$ #,0.00);R$ #,0.00"',
                'PBI_FormatHint = {"currencyCulture":"pt-BR"}',
                True
            )
        return '"#,0.00"', None, False

    def _get_partition_lines(self) -> List[str]:
        lines = [
            f"\t\tpartition {self.measures_table_name} = m",
            "\t\t\tmode: import",
            "\t\t\tsource ="
        ]
        for src_line in PARTITION_SOURCE.splitlines():
            lines.append(f"\t\t\t\t\t{src_line}")
        lines.append("\t\tannotation PBI_NavigationStepName = Navegação")
        lines.append("\t\tannotation PBI_ResultType = Table")
        return lines
