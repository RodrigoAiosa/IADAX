import streamlit as st
import io
from pbix_parser import PBIXParser
from tmdl_generator import TMDLGenerator

st.set_page_config(
    page_title="PBIX → TMDL Generator",
    page_icon="⚡",
    layout="centered",
)

# Load CSS
with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="header">
    <div class="header-badge">Power BI</div>
    <h1 class="title">PBIX <span class="arrow">→</span> TMDL</h1>
    <p class="subtitle">Carregue um arquivo <code>.pbix</code> e gere automaticamente um script TMDL com todas as medidas possíveis com base nos seus dados.</p>
</div>
""", unsafe_allow_html=True)

# Upload section
st.markdown('<div class="upload-section">', unsafe_allow_html=True)
uploaded_file = st.file_uploader(
    "Arraste ou selecione seu arquivo .pbix",
    type=["pbix"],
    label_visibility="collapsed",
)
st.markdown('</div>', unsafe_allow_html=True)

if uploaded_file is not None:
    with st.spinner("Analisando o arquivo .pbix..."):
        try:
            file_bytes = uploaded_file.read()
            parser = PBIXParser(file_bytes)
            tables = parser.get_tables()

            if not tables:
                st.error("Nenhuma tabela de dados encontrada no arquivo.")
                st.stop()

            st.markdown('<div class="results-section">', unsafe_allow_html=True)

            # Summary cards
            numeric_cols_total = sum(len(t["numeric"]) for t in tables.values())
            measures_count = sum(
                len(t["numeric"]) * 5
                for t in tables.values()
                if not t.get("is_hidden", False)
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-number">{len(tables)}</div>
                    <div class="stat-label">Tabelas</div>
                </div>""", unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-number">{numeric_cols_total}</div>
                    <div class="stat-label">Colunas Numéricas</div>
                </div>""", unsafe_allow_html=True)
            with col3:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-number">{measures_count}</div>
                    <div class="stat-label">Medidas Geradas</div>
                </div>""", unsafe_allow_html=True)

            # Table preview
            with st.expander("📋 Tabelas e colunas detectadas", expanded=False):
                for table_name, info in tables.items():
                    hidden_badge = " <span class='badge-hidden'>oculta</span>" if info.get("is_hidden") else ""
                    st.markdown(f"**{table_name}**{hidden_badge}", unsafe_allow_html=True)
                    if info["numeric"]:
                        st.markdown(
                            "Numéricas: " + ", ".join(f"`{c}`" for c in info["numeric"])
                        )
                    if info["text"]:
                        st.markdown(
                            "Texto: " + ", ".join(f"`{c}`" for c in info["text"])
                        )
                    if info["date"]:
                        st.markdown(
                            "Data: " + ", ".join(f"`{c}`" for c in info["date"])
                        )
                    st.markdown("---")

            # Generate TMDL
            generator = TMDLGenerator(tables)
            tmdl_script = generator.generate()

            st.markdown("### Script TMDL Gerado")
            st.code(tmdl_script, language="sql")

            # Download button
            st.download_button(
                label="⬇️ Baixar script .tmdl",
                data=tmdl_script.encode("utf-8"),
                file_name="medidas_geradas.tmdl",
                mime="text/plain",
                use_container_width=True,
            )

            st.markdown('</div>', unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {e}")
            st.exception(e)

else:
    st.markdown("""
    <div class="instructions">
        <div class="instruction-item">
            <span class="instruction-icon">📂</span>
            <div>
                <strong>Carregue seu arquivo .pbix</strong><br>
                Exportado diretamente do Power BI Desktop
            </div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">⚙️</span>
            <div>
                <strong>Análise automática</strong><br>
                Detecta tabelas, colunas numéricas e tipos de dados
            </div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">📄</span>
            <div>
                <strong>Script TMDL pronto</strong><br>
                Baixe e cole diretamente no Power BI ou Tabular Editor
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
