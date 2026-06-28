import streamlit as st
import pandas as pd

from pbix_parser import PBIXParser
from tmdl_generator import TMDLGenerator

st.set_page_config(
    page_title="PBIX → TMDL Generator",
    page_icon="⚡",
    layout="wide",
)

with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
<div class="header">
    <div class="header-badge">Power BI</div>
    <h1 class="title">PBIX <span class="arrow">→</span> TMDL</h1>
    <p class="subtitle">
        Carregue seu <code>.pbix</code>, selecione as colunas desejadas
        e gere medidas DAX completas — base e temporais.
    </p>
</div>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────
if "parser"           not in st.session_state: st.session_state.parser           = None
if "selected_cols"    not in st.session_state: st.session_state.selected_cols    = {}   # {table: [col,...]}
if "tmdl_script"      not in st.session_state: st.session_state.tmdl_script      = None
if "last_file_name"   not in st.session_state: st.session_state.last_file_name   = None

# ═══════════════════════════════════════════════════════════════════════
# STEP 1 — Upload
# ═══════════════════════════════════════════════════════════════════════
st.markdown('<div class="step-header"><span class="step-num">1</span> Carregar arquivo</div>', unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Selecione o arquivo .pbix",
    type=["pbix"],
    label_visibility="collapsed",
)

if uploaded:
    # Re-parse only when a new file is uploaded
    if uploaded.name != st.session_state.last_file_name:
        with st.spinner("Lendo modelo de dados..."):
            parser = PBIXParser(uploaded.read())
            parser.get_tables()
            st.session_state.parser         = parser
            st.session_state.selected_cols  = {}
            st.session_state.tmdl_script    = None
            st.session_state.last_file_name = uploaded.name

    parser: PBIXParser = st.session_state.parser
    tables = parser.get_tables()

    # Warn if schema is incomplete (pbixray unavailable)
    if parser.source in ("layout", "tmdl"):
        st.warning(
            "⚠️ **Metadados parciais** — o ambiente atual não suporta leitura completa "
            "do DataModel (Python 3.14+). Foram detectados os **nomes das tabelas**, "
            "mas as colunas numéricas não puderam ser identificadas automaticamente. "
            "Marque manualmente as colunas que deseja usar na etapa abaixo, "
            "ou rode localmente onde `pbixray` funciona para detecção automática completa.",
            icon="⚠️",
        )

    SKIP = {"Medidas", "Measures", "_Measures"}
    active_tables = {
        k: v for k, v in tables.items()
        if not v.get("is_hidden") and k not in SKIP
    }

    if not active_tables:
        st.error("Nenhuma tabela de dados encontrada no arquivo.")
        st.stop()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2 — Column selection
    # ═══════════════════════════════════════════════════════════════════
    st.markdown("")
    st.markdown('<div class="step-header"><span class="step-num">2</span> Selecionar colunas para gerar medidas</div>', unsafe_allow_html=True)
    st.markdown('<p class="step-sub">Marque as colunas numéricas que devem receber medidas DAX. As não selecionadas são ignoradas.</p>', unsafe_allow_html=True)

    new_selected: dict = {}

    for table_name, info in active_tables.items():
        all_cols    = info["numeric"] + info["text"] + info["date"]
        numeric_set = set(info["numeric"])
        date_set    = set(info["date"])

        if not all_cols:
            # No columns known (partial parse) — show empty state with note
            st.markdown(f"""
<div class="table-card table-card-empty">
    <div class="table-name">{table_name}</div>
    <div class="empty-note">Colunas não detectadas automaticamente neste ambiente.<br>
    Execute localmente com <code>pbixray</code> para detecção completa.</div>
</div>""", unsafe_allow_html=True)
            continue

        # Build the card header
        default_checked = [c for c in info["numeric"]]  # numeric pre-selected, text/date unchecked
        prev_selection  = st.session_state.selected_cols.get(table_name, default_checked)

        st.markdown(f"""
<div class="table-card">
    <div class="table-name">🗂 {table_name}
        <span class="col-counts">{len(info['numeric'])} numéricas · {len(info['text'])} texto · {len(info['date'])} data</span>
    </div>
</div>""", unsafe_allow_html=True)

        # Group columns visually: numeric | date | text
        groups = [
            ("Numéricas",  info["numeric"],  "badge-numeric"),
            ("Data",       info["date"],     "badge-date"),
            ("Texto",      info["text"],     "badge-text"),
        ]

        table_selected = []
        for group_label, cols, badge_cls in groups:
            if not cols:
                continue

            st.markdown(f'<div class="col-group-label">{group_label}</div>', unsafe_allow_html=True)

            # Render checkboxes in a 4-column grid
            grid_cols = st.columns(4)
            for i, col in enumerate(cols):
                badge = f'<span class="{badge_cls} badge-inline">{col}</span>'
                is_numeric = col in numeric_set
                default_on = col in prev_selection
                checked = grid_cols[i % 4].checkbox(
                    col,
                    value=default_on,
                    key=f"chk_{table_name}_{col}",
                    help="Coluna numérica — pré-selecionada" if is_numeric else
                         "Coluna de data" if col in date_set else "Coluna de texto",
                )
                if checked:
                    table_selected.append(col)

        new_selected[table_name] = table_selected
        st.markdown("<hr class='table-divider'>", unsafe_allow_html=True)

    st.session_state.selected_cols = new_selected

    # Total selected count
    total_selected = sum(len(v) for v in new_selected.values())

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3 — Settings + Generate
    # ═══════════════════════════════════════════════════════════════════
    st.markdown('<div class="step-header"><span class="step-num">3</span> Configurações e geração</div>', unsafe_allow_html=True)

    with st.container():
        cfg1, cfg2, cfg3 = st.columns(3)
        with cfg1:
            date_table = st.text_input("Tabela de datas", value="dCalendario",
                                       help="Nome da tabela calendário no modelo")
        with cfg2:
            date_col = st.text_input("Coluna de data", value="Data",
                                     help="Coluna Date da tabela calendário")
        with cfg3:
            gen_time = st.toggle("Medidas temporais", value=True,
                                 help="YTD, MTD, QTD, YoY, MoM, Mês/Ano Anterior")

    if gen_time:
        st.markdown("""
<div class="legend">
<strong>Por coluna selecionada serão geradas:</strong><br>
Base: <code>Total</code> · <code>Média</code> · <code>Contagem</code> · <code>Máximo</code> · <code>Mínimo</code> &nbsp;|&nbsp;
Temporais: <code>YTD</code> · <code>YTD Ano Anterior</code> · <code>MTD</code> · <code>QTD</code> · <code>Mês Anterior</code> · <code>Ano Anterior</code> · <code>Var YoY</code> · <code>% YoY</code> · <code>Var MoM</code> · <code>% MoM</code>
</div>""", unsafe_allow_html=True)

    btn_disabled = total_selected == 0
    st.markdown(f'<p class="selected-count">{"✅ " + str(total_selected) + " coluna(s) selecionada(s)" if total_selected > 0 else "⬆️ Selecione ao menos uma coluna acima"}</p>', unsafe_allow_html=True)

    if st.button("⚡ Gerar script TMDL", use_container_width=True, type="primary", disabled=btn_disabled):
        with st.spinner("Gerando medidas..."):
            # Build tables dict from user selection
            selected_tables = {}
            for table_name, selected_cols in new_selected.items():
                if not selected_cols:
                    continue
                # Classify selected columns by original type
                orig = active_tables.get(table_name, {})
                numeric_set = set(orig.get("numeric", []))
                date_set    = set(orig.get("date", []))
                selected_tables[table_name] = {
                    "numeric":   [c for c in selected_cols if c in numeric_set or c not in date_set],
                    "text":      [],
                    "date":      [c for c in selected_cols if c in date_set],
                    "is_hidden": False,
                }

            existing = parser.get_existing_measures()
            generator = TMDLGenerator(
                selected_tables,
                existing,
                date_table=date_table,
                date_column=date_col,
                generate_time=gen_time,
            )
            st.session_state.tmdl_script = generator.generate()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4 — Output
    # ═══════════════════════════════════════════════════════════════════
    if st.session_state.tmdl_script:
        script = st.session_state.tmdl_script
        import re
        measure_names = re.findall(r"measure '([^']+)'", script)
        n = len(measure_names)

        st.markdown("")
        st.markdown('<div class="step-header"><span class="step-num">4</span> Script gerado</div>', unsafe_allow_html=True)

        mc1, mc2 = st.columns(2)
        mc1.markdown(f'<div class="stat-card"><div class="stat-number">{n}</div><div class="stat-label">Medidas Geradas</div></div>', unsafe_allow_html=True)
        mc2.markdown(f'<div class="stat-card"><div class="stat-number">{total_selected}</div><div class="stat-label">Colunas Usadas</div></div>', unsafe_allow_html=True)

        st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
        st.code(script, language="sql")

        st.download_button(
            label="⬇️ Baixar medidas_geradas.tmdl",
            data=script.encode("utf-8"),
            file_name="medidas_geradas.tmdl",
            mime="text/plain",
            use_container_width=True,
        )

else:
    # Empty state
    st.markdown("""
<div class="instructions">
    <div class="instruction-item">
        <span class="instruction-icon">📂</span>
        <div><strong>1. Carregue o .pbix</strong><br>Exportado do Power BI Desktop ou serviço</div>
    </div>
    <div class="instruction-item">
        <span class="instruction-icon">☑️</span>
        <div><strong>2. Selecione as colunas</strong><br>Tabelas e colunas são detectadas automaticamente do modelo</div>
    </div>
    <div class="instruction-item">
        <span class="instruction-icon">⚙️</span>
        <div><strong>3. Configure e gere</strong><br>Ajuste a tabela de datas e clique em Gerar</div>
    </div>
    <div class="instruction-item">
        <span class="instruction-icon">📄</span>
        <div><strong>4. Baixe o .tmdl</strong><br>Cole no Tabular Editor ou importe via Power BI</div>
    </div>
</div>
""", unsafe_allow_html=True)
