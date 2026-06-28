import io
import streamlit as st
import pandas as pd

from pbix_parser import PBIXParser
from tmdl_generator import TMDLGenerator

st.set_page_config(
    page_title="PBIX → TMDL Generator",
    page_icon="⚡",
    layout="centered",
)

with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────
st.markdown("""
<div class="header">
    <div class="header-badge">Power BI</div>
    <h1 class="title">PBIX <span class="arrow">→</span> TMDL</h1>
    <p class="subtitle">
        Carregue seu <code>.pbix</code> e uma amostra dos dados para gerar
        medidas DAX completas — incluindo YTD, MTD, QTD, YoY, MoM e mais.
    </p>
</div>
""", unsafe_allow_html=True)

# ── Uploads ───────────────────────────────────────────────────────────
col_a, col_b = st.columns([1, 1], gap="medium")

with col_a:
    st.markdown('<p class="upload-label">📁 Arquivo <code>.pbix</code> <span class="required">*</span></p>', unsafe_allow_html=True)
    pbix_file = st.file_uploader("pbix", type=["pbix"], label_visibility="collapsed", key="pbix_upload")

with col_b:
    st.markdown('<p class="upload-label">📊 Amostra de dados <code>.csv</code> / <code>.xlsx</code> <span class="required">*</span></p>', unsafe_allow_html=True)
    data_file = st.file_uploader("csv_excel", type=["csv", "xlsx", "xls"], label_visibility="collapsed", key="data_upload")

# ── Config ───────────────────────────────────────────────────────────
with st.expander("⚙️ Configurações avançadas"):
    col_c, col_d = st.columns(2)
    with col_c:
        csv_table_name = st.text_input(
            "Nome da tabela no modelo",
            value="fVendas",
            help="Como a tabela aparece no Power BI. Usado nas expressões DAX: SUM(fVendas[Sales])"
        )
    with col_d:
        date_table = st.text_input(
            "Tabela de datas",
            value="dCalendario",
            help="Nome da tabela calendário para medidas temporais"
        )
    date_col = st.text_input(
        "Coluna de data",
        value="Data",
        help="Coluna Date da tabela calendário. Ex: Data, Date, Fecha"
    )
    st.markdown("---")
    gen_time = st.toggle("Gerar medidas de inteligência temporal", value=True,
                          help="YTD, MTD, QTD, YoY, MoM, Mês Anterior, Ano Anterior")

with st.expander("ℹ️ Por que preciso do CSV?"):
    st.markdown("""
O modelo de dados do `.pbix` usa compressão proprietária **XPress9** da Microsoft,
incompatível com Python 3.14 (versão usada no Streamlit Cloud).

**Solução:** exporte uma amostra da sua tabela fato diretamente do Power BI:

1. Abra o relatório → selecione a tabela no painel *Dados*
2. Botão direito → **Exportar dados** → CSV
3. Faça upload aqui e informe o nome exato da tabela (ex: `fVendas`)

A ferramenta detecta automaticamente quais colunas são numéricas e gera
**15 medidas por coluna**: 5 base + 10 temporais.
""")

# ── Generate ─────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:0.25rem'></div>", unsafe_allow_html=True)

if pbix_file and data_file:
    if st.button("⚡ Gerar script TMDL", use_container_width=True, type="primary"):
        with st.spinner("Analisando e gerando medidas..."):
            try:
                # Parse .pbix
                parser = PBIXParser(pbix_file.read())
                tables = parser.get_tables()
                existing = parser.get_existing_measures()

                # Load CSV / Excel
                tname = (csv_table_name or "").strip() or data_file.name.rsplit(".", 1)[0]
                ext = data_file.name.rsplit(".", 1)[-1].lower()
                df = pd.read_csv(data_file) if ext == "csv" else pd.read_excel(data_file)
                parser.enrich_from_dataframe(tname, df)
                tables = parser._tables  # use enriched dict directly

                SKIP = {"Medidas", "Measures", "_Measures"}
                active = {k: v for k, v in tables.items()
                          if not v.get("is_hidden") and k not in SKIP}

                if not active or all(not v["numeric"] for v in active.values()):
                    st.warning("Nenhuma coluna numérica detectada. Verifique o CSV enviado.")
                    st.stop()

                # Stats
                numeric_total = sum(len(v["numeric"]) for v in active.values())
                measures_per_col = 15 if gen_time else 5
                # Subtract cols that will be skipped for time (month number, year, etc.)
                skip_time_kws = ("month number", "year", "month name")
                time_skipped = sum(
                    1 for v in active.values()
                    for c in v["numeric"]
                    if any(kw == c.lower() for kw in ("month number", "year", "month name"))
                )
                estimated = numeric_total * 5 + (numeric_total - time_skipped) * 10 if gen_time else numeric_total * 5
                new_measures = max(0, estimated - len(existing))

                c1, c2, c3 = st.columns(3)
                c1.markdown(f'<div class="stat-card"><div class="stat-number">{numeric_total}</div><div class="stat-label">Colunas Numéricas</div></div>', unsafe_allow_html=True)
                c2.markdown(f'<div class="stat-card"><div class="stat-number">{new_measures}</div><div class="stat-label">Medidas Geradas</div></div>', unsafe_allow_html=True)
                c3.markdown(f'<div class="stat-card"><div class="stat-number">{len(existing)}</div><div class="stat-label">Já Existiam</div></div>', unsafe_allow_html=True)

                st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)

                with st.expander("📋 Colunas detectadas por tabela"):
                    for tname_k, info in active.items():
                        if info["numeric"]:
                            st.markdown(f"**{tname_k}**")
                            st.markdown("Numéricas: " + ", ".join(f"`{c}`" for c in info["numeric"]))
                            if info["text"]:
                                st.markdown("Texto: " + ", ".join(f"`{c}`" for c in info["text"]))
                            if info["date"]:
                                st.markdown("Data: " + ", ".join(f"`{c}`" for c in info["date"]))
                            st.markdown("---")

                if gen_time:
                    st.markdown("""
<div class="legend">
<strong>Medidas geradas por coluna numérica de negócio:</strong><br>
Base: <code>Total</code> · <code>Média</code> · <code>Contagem</code> · <code>Máximo</code> · <code>Mínimo</code><br>
Temporais: <code>YTD</code> · <code>YTD Ano Anterior</code> · <code>MTD</code> · <code>QTD</code> · <code>Mês Anterior</code> · <code>Ano Anterior</code> · <code>Var YoY</code> · <code>% YoY</code> · <code>Var MoM</code> · <code>% MoM</code>
</div>
""", unsafe_allow_html=True)

                # Generate
                generator = TMDLGenerator(
                    active, existing,
                    date_table=date_table,
                    date_column=date_col,
                )
                if not gen_time:
                    generator._time_measures = lambda t, c: []

                tmdl_script = generator.generate()

                st.markdown("### Script TMDL Gerado")
                st.code(tmdl_script, language="sql")

                st.download_button(
                    label="⬇️ Baixar medidas_geradas.tmdl",
                    data=tmdl_script.encode("utf-8"),
                    file_name="medidas_geradas.tmdl",
                    mime="text/plain",
                    use_container_width=True,
                )

            except Exception as e:
                st.error(f"Erro: {e}")
                st.exception(e)

elif pbix_file and not data_file:
    st.info("📊 Envie também uma amostra CSV/Excel da sua tabela fato para detectar todas as colunas numéricas.")
else:
    st.markdown("""
    <div class="instructions">
        <div class="instruction-item">
            <span class="instruction-icon">📂</span>
            <div><strong>1. Carregue o .pbix</strong><br>Exportado do Power BI Desktop ou serviço</div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">📊</span>
            <div><strong>2. Exporte e envie o CSV da tabela fato</strong><br>No Power BI: botão direito na tabela → Exportar dados</div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">⚙️</span>
            <div><strong>3. Ajuste as configurações se necessário</strong><br>Nome da tabela, tabela de datas, coluna de data</div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">📄</span>
            <div><strong>4. Baixe o .tmdl gerado</strong><br>Cole no Tabular Editor ou importe via Power BI</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
