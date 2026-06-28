"""
measure_folders.py
Configuração de pastas para organização das medidas no Power BI.
"""

MEASURE_FOLDERS = {
    "Agregadores": {
        "icon": "📊",
        "description": "Medidas de agregação básica",
        "measures": ["Total", "Média", "Contagem", "Máximo", "Mínimo"]
    },
    "Acumulados (YTD)": {
        "icon": "📈",
        "description": "Acumulado do ano",
        "measures": ["YTD", "YTD Ano Anterior"]
    },
    "Acumulados (MTD)": {
        "icon": "📅",
        "description": "Acumulado do mês",
        "measures": ["MTD"]
    },
    "Acumulados (QTD)": {
        "icon": "📆",
        "description": "Acumulado do trimestre",
        "measures": ["QTD"]
    },
    "Períodos Anteriores": {
        "icon": "⏪",
        "description": "Comparações com períodos anteriores",
        "measures": ["Mês Anterior", "Ano Anterior"]
    },
    "Variações (YoY)": {
        "icon": "📉",
        "description": "Variação ano a ano",
        "measures": ["Var YoY", "% YoY"]
    },
    "Variações (MoM)": {
        "icon": "📉",
        "description": "Variação mês a mês",
        "measures": ["Var MoM", "% MoM"]
    }
}
