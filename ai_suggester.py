"""
ai_suggester.py
Uses Anthropic Claude to suggest additional contextual DAX measures
based on the detected model metadata (tables, columns, existing measures).
"""

import json
from typing import Dict, List, Optional


def build_prompt(
    tables: Dict[str, dict],
    existing_measures: List[str],
    date_table: str,
    date_column: str,
    file_name: str = "",
) -> str:
    """Builds the prompt for the AI to suggest DAX measures."""
    lines = []

    if file_name:
        lines.append(f"Arquivo Power BI: {file_name}")
        lines.append("")

    lines.append("Modelo de dados detectado:")
    lines.append("")

    for tname, info in tables.items():
        if info.get("is_hidden"):
            continue
        cols_num = info.get("numeric", [])
        cols_txt = info.get("text", [])
        cols_date = info.get("date", [])
        if not (cols_num or cols_txt or cols_date):
            continue

        lines.append(f"Tabela: {tname}")
        if cols_num:
            lines.append(f"  Numéricas: {', '.join(cols_num)}")
        if cols_date:
            lines.append(f"  Datas: {', '.join(cols_date)}")
        if cols_txt:
            lines.append(f"  Texto: {', '.join(cols_txt)}")
        lines.append("")

    if existing_measures:
        lines.append(f"Medidas já existentes: {', '.join(existing_measures[:20])}")
        lines.append("")

    lines.append(f"Tabela de calendário: {date_table}[{date_column}]")
    lines.append("")
    lines.append(
        "Com base no modelo acima, sugira medidas DAX adicionais e contextuais "
        "que ainda NÃO foram listadas. Foque em medidas de negócio relevantes: "
        "rankings (RANKX), proporções (DIVIDE), contagens distintas (DISTINCTCOUNT), "
        "médias ponderadas, medidas de mix/participação, medidas condicionais com SWITCH/IF, "
        "e medidas de desempenho (metas vs realizado). Use os nomes reais das tabelas e colunas."
    )
    lines.append("")
    lines.append(
        'Retorne APENAS um JSON válido, sem markdown, sem texto extra, no formato:\n'
        '{"measures": [{"name": "...", "expression": "= ...", "format": "...", "description": "..."}]}\n'
        "O campo format deve ser uma string DAX (ex: #,0.00 ou 0.00% ou R$ #,0.00). "
        "Gere entre 8 e 15 medidas."
    )

    return "\n".join(lines)


def parse_ai_response(text: str) -> List[dict]:
    """Parses the JSON returned by the AI."""
    text = text.strip()
    # Strip markdown fences
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
        measures = data.get("measures", [])
        result = []
        for m in measures:
            name = m.get("name", "").strip()
            expr = m.get("expression", "").strip().lstrip("= ")
            fmt = m.get("format", "#,0.00").strip('"')
            desc = m.get("description", "")
            if name and expr:
                result.append({
                    "name": name,
                    "expression": expr,
                    "format": f'"{fmt}"',
                    "annotation": None,
                    "is_currency": False,
                    "single_line": "\n" not in expr,
                    "group": "IA Sugeridas",
                    "description": desc,
                })
        return result
    except Exception:
        return []


def get_ai_measures(
    api_key: str,
    tables: Dict[str, dict],
    existing_measures: List[str],
    date_table: str,
    date_column: str,
    file_name: str = "",
) -> List[dict]:
    """
    Calls the Anthropic API to get AI-suggested DAX measures.
    Returns list of measure dicts compatible with TMDLGenerator.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = build_prompt(tables, existing_measures, date_table, date_column, file_name)

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text
        return parse_ai_response(response_text)
    except Exception as e:
        return []
