"""
tmdl_generator.py
Generates a TMDL script with DAX measures based on detected numeric columns.
Skips measures that already exist in the model.

Per numeric column (5 measures):
  Total <Col>     → SUM
  Média <Col>     → AVERAGE
  Contagem <Col>  → COUNT
  Máximo <Col>    → MAX
  Mínimo <Col>    → MIN
"""

from typing import Dict, List, Optional

CURRENCY_KEYWORDS = (
    "sales", "revenue", "price", "cost", "profit", "discount",
    "gross", "cogs", "venda", "receita", "preco", "preço",
    "custo", "lucro", "desconto", "faturamento", "valor",
    "amount", "net", "bruto", "liquido", "líquido",
)

MEASURES_TABLE = "Medidas"

PARTITION_SOURCE = (
    "let\n"
    "              Origem = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText(\"i44FAA==\", BinaryEncoding.Base64), Compression.Deflate)), "
    "let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [#\"Coluna 1\" = _t]),\n"
    "                #\"Colunas Removidas\" = Table.RemoveColumns(Origem,{\"Coluna 1\"})\n"
    "            in\n"
    "                #\"Colunas Removidas\""
)


class TMDLGenerator:
    def __init__(self, tables: Dict[str, dict], existing_measures: Optional[List[str]] = None):
        self.tables = tables
        self.existing = set(existing_measures or [])

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

    def _collect_measures(self) -> List[dict]:
        measures = []
        for table_name, info in self.tables.items():
            if info.get("is_hidden"):
                continue
            for col in info.get("numeric", []):
                for m in self._measures_for(table_name, col):
                    if m["name"] not in self.existing:
                        measures.append(m)
        return measures

    def _measures_for(self, table: str, col: str) -> List[dict]:
        ref = f"{table}[{col}]"
        is_currency = any(kw in col.lower() for kw in CURRENCY_KEYWORDS)
        fmt = r"R$\ #,0.00;(R$\ #,0.00);R$\ #,0.00" if is_currency else "#,0.00"
        annotation = 'PBI_FormatHint = {"currencyCulture":"pt-BR"}' if is_currency else None

        return [
            {"name": f"Total {col}",    "expression": f"SUM({ref})",          "format": fmt,   "annotation": annotation},
            {"name": f"Média {col}",    "expression": f"AVERAGE({ref})",       "format": fmt,   "annotation": annotation},
            {"name": f"Contagem {col}", "expression": f"COUNT({ref})",         "format": "#,0", "annotation": None},
            {"name": f"Máximo {col}",   "expression": f"MAX({ref})",           "format": fmt,   "annotation": annotation},
            {"name": f"Mínimo {col}",   "expression": f"MIN({ref})",           "format": fmt,   "annotation": annotation},
        ]
