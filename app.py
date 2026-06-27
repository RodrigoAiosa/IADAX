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
        Carregue seu arquivo <code>.pbix</code> e, opcionalmente, uma amostra
        dos seus dados em <code>.csv</code> ou <code>.xlsx</code> para gerar
        um script TMDL com todas as medidas DAX possíveis.
    </p>
</div>
""", unsafe_allow_html=True)

# ── Upload section ────────────────────────────────────────────────────
col_a, col_b = st.columns([1, 1], gap="medium")

with col_a:
    st.markdown('<p class="upload-label">📁 Arquivo <code>.pbix</code> <span class="required">*</span></p>', unsafe_allow_html=True)
    pbix_file = st.file_uploader(
        "pbix",
        type=["pbix"],
        label_visibility="collapsed",
        key="pbix_upload",
    )

with col_b:
    st.markdown('<p class="upload-label">📊 Amostra de dados <span class="optional">(opcional)</span></p>', unsafe_allow_html=True)
    data_file = st.file_uploader(
        "csv_excel",
        type=["csv", "xlsx", "xls"],
        label_visibility="collapsed",
        key="data_upload",
    )

st.markdown("<div style='margin-top:0.5rem'></div>", unsafe_allow_html=True)

# ── Why the data file? ────────────────────────────────────────────────
with st.expander("ℹ️ Por que enviar uma amostra de dados?"):
    st.markdown("""
O modelo de dados do `.pbix` usa a compressão proprietária **XPress9** da Microsoft,
que requer bibliotecas nativas não disponíveis no Streamlit Cloud.

Por isso, a ferramenta lê os **scripts TMDL** embutidos no `.pbix` para descobrir
tabelas e colunas já referenciadas em medidas existentes.

Se você quiser gerar medidas para **novas colunas** que ainda não têm medidas criadas,
envie também um arquivo `.csv` ou `.xlsx` com uma amostra dos dados daquela tabela.
A ferramenta detecta automaticamente as colunas numéricas e gera todas as medidas.

**Como exportar do Power BI Desktop:**
1. Abra o relatório → selecione uma tabela no painel de dados
2. Clique com o botão direito → *Exportar dados* → CSV
""")

# ── Table name for CSV ────────────────────────────────────────────────
csv_table_name = None
if data_file is not None:
    csv_table_name = st.text_input(
        "Nome da tabela no modelo (como aparece no Power BI):",
        placeholder="Ex: fVendas",
        help="Esse nome é usado nas expressões DAX geradas, ex: SUM(fVendas[Sales])",
    )

# ── Process ──────────────────────────────────────────────────────────
if pbix_file is not None:
    if st.button("⚡ Gerar script TMDL", use_container_width=True, type="primary"):
        with st.spinner("Analisando..."):
            try:
                file_bytes = pbix_file.read()
                parser = PBIXParser(file_bytes)
                tables = parser.get_tables()
                existing_measures = parser.get_existing_measures()

                # Enrich from uploaded data file
                if data_file is not None:
                    tname = (csv_table_name or "").strip() or data_file.name.rsplit(".", 1)[0]
                    ext = data_file.name.rsplit(".", 1)[-1].lower()
                    if ext == "csv":
                        df = pd.read_csv(data_file)
                    else:
                        df = pd.read_excel(data_file)
                    parser.enrich_from_dataframe(tname, df)
                    tables = parser.get_tables()

                # Filter out measure table and hidden tables
                SKIP_TABLES = {"Medidas", "Measures", "_Measures"}
                active_tables = {
                    k: v for k, v in tables.items()
                    if not v.get("is_hidden") and k not in SKIP_TABLES
                }

                if not active_tables or all(
                    not v["numeric"] for v in active_tables.values()
                ):
                    st.warning(
                        "⚠️ Nenhuma coluna numérica detectada no arquivo TMDL. "
                        "Envie também uma amostra CSV/Excel para gerar medidas completas."
                    )
                else:
                    numeric_total = sum(len(v["numeric"]) for v in active_tables.values())
                    measures_count = numeric_total * 5

                    # Stats
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f'<div class="stat-card"><div class="stat-number">{len(active_tables)}</div><div class="stat-label">Tabelas</div></div>', unsafe_allow_html=True)
                    c2.markdown(f'<div class="stat-card"><div class="stat-number">{numeric_total}</div><div class="stat-label">Colunas Numéricas</div></div>', unsafe_allow_html=True)
                    c3.markdown(f'<div class="stat-card"><div class="stat-number">{measures_count}</div><div class="stat-label">Medidas Geradas</div></div>', unsafe_allow_html=True)

                    st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)

                    # Table preview
                    with st.expander("📋 Tabelas e colunas detectadas"):
                        for tname, info in active_tables.items():
                            st.markdown(f"**{tname}**")
                            if info["numeric"]:
                                st.markdown("Numéricas: " + ", ".join(f"`{c}`" for c in info["numeric"]))
                            if info["text"]:
                                st.markdown("Texto: " + ", ".join(f"`{c}`" for c in info["text"]))
                            if info["date"]:
                                st.markdown("Data: " + ", ".join(f"`{c}`" for c in info["date"]))
                            st.markdown("---")

                    # Generate TMDL
                    generator = TMDLGenerator(active_tables, existing_measures)
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
                st.error(f"Erro ao processar: {e}")
                st.exception(e)
else:
    st.markdown("""
    <div class="instructions">
        <div class="instruction-item">
            <span class="instruction-icon">📂</span>
            <div>
                <strong>1. Carregue o .pbix</strong><br>
                Exportado diretamente do Power BI Desktop ou serviço
            </div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">📊</span>
            <div>
                <strong>2. (Opcional) Envie uma amostra CSV/Excel</strong><br>
                Para detectar colunas que ainda não têm medidas no modelo
            </div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">📄</span>
            <div>
                <strong>3. Baixe o script .tmdl</strong><br>
                Cole no Tabular Editor ou importe via Power BI
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
