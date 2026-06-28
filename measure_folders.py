"""
measure_folders.py
Configuração de pastas para organização das medidas no Power BI.
Usado como referência para documentação e geração de grupos.
"""

MEASURE_FOLDERS = {
    "Agregadores": {
        "icon": "📊",
        "description": "Medidas de agregação básica",
        "prefixes": ["Total", "Média", "Contagem", "Máximo", "Mínimo"],
    },
    "Acumulados (YTD)": {
        "icon": "📈",
        "description": "Acumulado do ano (Year-to-Date)",
        "prefixes": ["YTD"],
    },
    "Acumulados (MTD)": {
        "icon": "📅",
        "description": "Acumulado do mês (Month-to-Date)",
        "prefixes": ["MTD"],
    },
    "Acumulados (QTD)": {
        "icon": "📆",
        "description": "Acumulado do trimestre (Quarter-to-Date)",
        "prefixes": ["QTD"],
    },
    "Períodos Anteriores": {
        "icon": "⏪",
        "description": "Comparações com períodos anteriores",
        "suffixes": ["Mês Anterior", "Ano Anterior"],
    },
    "Variações (YoY)": {
        "icon": "📉",
        "description": "Variação ano a ano (Year-over-Year)",
        "prefixes": ["Var YoY", "% YoY"],
    },
    "Variações (MoM)": {
        "icon": "📉",
        "description": "Variação mês a mês (Month-over-Month)",
        "prefixes": ["Var MoM", "% MoM"],
    },
    "IA Sugeridas": {
        "icon": "🤖",
        "description": "Medidas contextuais sugeridas pela IA",
        "prefixes": [],
    },
}
