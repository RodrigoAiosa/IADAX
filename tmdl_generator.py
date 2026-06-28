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
        self.measure_groups = {}  # Para organizar por categoria

    # ── Public ────────────────────────────────────────────────────────

    def generate(self) -> str:
        """Gera o script TMDL completo com medidas organizadas."""
        measures = self._collect_measures()
        
        if not measures:
            return (
                "// Nenhuma medida nova pôde ser gerada.\n"
                "// Todas as medidas possíveis já existem ou não há colunas numéricas detectadas."
            )

        # Organizar medidas por grupo
        grouped = self._group_measures(measures)
        
        lines = ["createOrReplace", ""]
        lines.append(f"\ttable {MEASURES_TABLE}")
        lines.append("")

        # Adicionar medidas por grupo com comentários
        for group_name, group_measures in grouped.items():
            if group_measures:
                lines.append(f"\t\t// ── {group_name} ──")
                for m in group_measures:
                    lines.extend(self._format_measure(m))
                lines.append("")

        # Partition boilerplate
        lines.extend(self._get_partition_lines())
        lines.append("")

        return "\n".join(lines)

    # ── Collectors ────────────────────────────────────────────────────

    def _collect_measures(self) -> List[dict]:
        """Coleta todas as medidas a serem geradas."""
        measures = []
        for table_name, info in self.tables.items():
            if info.get("is_hidden"):
                continue
            for col in info.get("numeric", []):
                col_lower = col.lower()

                # Skip pure calendar columns entirely
                if any(kw == col_lower for kw in SKIP_ENTIRELY_KEYWORDS):
                    continue

                # Base measures (sempre geradas)
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

    def _group_measures(self, measures: List[dict]) -> Dict[str, List[dict]]:
        """Agrupa medidas por categoria."""
        groups = {}
        
        for m in measures:
            name = m["name"]
            
            # Determinar grupo baseado no nome da medida
            if name.startswith("Total "):
                group = "Agregadores"
            elif name.startswith("Média "):
                group = "Agregadores"
            elif name.startswith("Contagem "):
                group = "Agregadores"
            elif name.startswith("Máximo "):
                group = "Agregadores"
            elif name.startswith("Mínimo "):
                group = "Agregadores"
            elif "YTD" in name:
                group = "Acumulados (YTD)"
            elif "MTD" in name:
                group = "Acumulados (MTD)"
            elif "QTD" in name:
                group = "Acumulados (QTD)"
            elif "Ano Anterior" in name:
                group = "Períodos Anteriores"
            elif "Mês Anterior" in name:
                group = "Períodos Anteriores"
            elif "MoM" in name:
                group = "Variações (MoM)"
            elif "YoY" in name:
                group = "Variações (YoY)"
            else:
                group = "Outras"
            
            if group not in groups:
                groups[group] = []
            groups[group].append(m)
        
        return groups

    # ── Base measures ─────────────────────────────────────────────────

    def _base_measures(self, table: str, col: str) -> List[dict]:
        """Gera medidas base (agregadores)."""
        ref = f"{table}[{col}]"
        fmt, ann, is_currency = self._fmt(col)
        return [
            {
                "name": f"Total {col}",
                "expression": f"SUM({ref})",
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency
            },
            {
                "name": f"Média {col}",
                "expression": f"AVERAGE({ref})",
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency
            },
            {
                "name": f"Contagem {col}",
                "expression": f"COUNT({ref})",
                "format": "#,0",
                "annotation": None,
                "is_currency": False
            },
            {
                "name": f"Máximo {col}",
                "expression": f"MAX({ref})",
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency
            },
            {
                "name": f"Mínimo {col}",
                "expression": f"MIN({ref})",
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency
            },
        ]

    # ── Time-intelligence measures ────────────────────────────────────

    def _time_measures(self, table: str, col: str) -> List[dict]:
        """Gera medidas de inteligência temporal."""
        dt = f"{self.date_table}[{self.date_column}]"
        fmt, ann, is_currency = self._fmt(col)
        pct_fmt = "0.00%"

        # Reference the base SUM measure by name (keeps DAX DRY)
        base_name = f"Total {col}"
        base_ref = f"[{base_name}]"

        return [
            # ── YTD ──────────────────────────────────────────────────
            {
                "name": f"YTD {col}",
                "expression": f"TOTALYTD({base_ref}, {dt})",
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency,
                "single_line": True
            },
            {
                "name": f"YTD {col} Ano Anterior",
                "expression": (
                    f"CALCULATE(\n"
                    f"\t\t\t\tTOTALYTD({base_ref}, {dt}),\n"
                    f"\t\t\t\tSAMEPERIODLASTYEAR({dt})\n"
                    f"\t\t\t)"
                ),
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency,
                "single_line": False
            },
            # ── MTD ──────────────────────────────────────────────────
            {
                "name": f"MTD {col}",
                "expression": f"TOTALMTD({base_ref}, {dt})",
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency,
                "single_line": True
            },
            # ── QTD ──────────────────────────────────────────────────
            {
                "name": f"QTD {col}",
                "expression": f"TOTALQTD({base_ref}, {dt})",
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency,
                "single_line": True
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
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency,
                "single_line": False
            },
            {
                "name": f"{col} Ano Anterior",
                "expression": (
                    f"CALCULATE(\n"
                    f"\t\t\t\t{base_ref},\n"
                    f"\t\t\t\tSAMEPERIODLASTYEAR({dt})\n"
                    f"\t\t\t)"
                ),
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency,
                "single_line": False
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
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency,
                "single_line": False
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
                "format": pct_fmt,
                "annotation": None,
                "is_currency": False,
                "single_line": False
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
                "format": fmt,
                "annotation": ann,
                "is_currency": is_currency,
                "single_line": False
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
                "format": pct_fmt,
                "annotation": None,
                "is_currency": False,
                "single_line": False
            },
        ]

    # ── Formatting ────────────────────────────────────────────────────

    def _format_measure(self, measure: dict) -> List[str]:
        """Formata uma medida para TMDL com indentação correta."""
        lines = []
        name = measure["name"]
        expr = measure["expression"]
        fmt = measure.get("format")
        ann = measure.get("annotation")
        single_line = measure.get("single_line", False)

        # Determinar se é uma medida de porcentagem
        is_pct = fmt == "0.00%"
        
        # Formatar a expressão
        if single_line:
            # Expressão em uma única linha
            if "YTD" in name and "Ano Anterior" not in name:
                lines.append(f"\t\tmeasure '{name}' = {expr}")
            elif "MTD" in name:
                lines.append(f"\t\tmeasure '{name}' = {expr}")
            elif "QTD" in name:
                lines.append(f"\t\tmeasure '{name}' = {expr}")
            else:
                lines.append(f"\t\tmeasure '{name}' = {expr}")
        else:
            # Expressão em múltiplas linhas - manter indentação
            expr_lines = expr.split('\n')
            if len(expr_lines) == 1:
                lines.append(f"\t\tmeasure '{name}' = {expr}")
            else:
                lines.append(f"\t\tmeasure '{name}' = {expr_lines[0]}")
                for line in expr_lines[1:]:
                    lines.append(f"\t\t\t{line}")

        # Adicionar formatString
        if fmt:
            if is_pct:
                lines.append(f"\t\t\tformatString: {fmt}")
            else:
                lines.append(f"\t\t\tformatString: {fmt}")
        
        # Adicionar annotation
        if ann:
            lines.append(f"\t\t\tannotation {ann}")
        
        return lines

    def _fmt(self, col: str) -> Tuple[str, Optional[str], bool]:
        """Determina o formato e annotation para uma coluna."""
        is_currency = any(kw in col.lower() for kw in CURRENCY_KEYWORDS)
        if is_currency:
            return (
                r'"R$ #,0.00;(R$ #,0.00);R$ #,0.00"',
                'PBI_FormatHint = {"currencyCulture":"pt-BR"}',
                True
            )
        return '"#,0.00"', None, False

    def _get_partition_lines(self) -> List[str]:
        """Gera as linhas da partition."""
        lines = [
            f"\t\tpartition {MEASURES_TABLE} = m",
            "\t\t\tmode: import",
            "\t\t\tsource ="
        ]
        for src_line in PARTITION_SOURCE.splitlines():
            lines.append(f"\t\t\t\t\t{src_line}")
        lines.append("\t\tannotation PBI_NavigationStepName = Navegação")
        lines.append("\t\tannotation PBI_ResultType = Table")
        return lines
