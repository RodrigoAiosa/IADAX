import io
import os
import streamlit as st
import pandas as pd

from pbix_parser import PBIXParser
from tmdl_generator import TMDLGenerator
from ai_suggester import get_ai_measures

st.set_page_config(
    page_title="IADAX — Gerador de Medidas DAX",
    page_icon="⚡",
    layout="centered",
)

with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────
st.markdown("""
<div class="header">
    <div class="header-badge">Power BI · DAX · TMDL</div>
    <h1 class="title">IA<span class="arrow">DAX</span></h1>
    <p class="subtitle">
        Carregue seu <code>.pbix</code> e gere automaticamente todas as medidas DAX —
        YTD, MTD, QTD, YoY, MoM e medidas contextuais sugeridas por IA.
    </p>
</div>
""", unsafe_allow_html=True)

# ── Uploads ───────────────────────────────────────────────────────────
col_a, col_b = st.columns([1, 1], gap="medium")

with col_a:
    st.markdown('<p class="upload-label">📁 Arquivo <code>.pbix</code> <span class="required">*</span></p>', unsafe_allow_html=True)
    pbix_file = st.file_uploader("pbix", type=["pbix"], label_visibility="collapsed", key="pbix_upload")

with col_b:
    st.markdown('<p class="upload-label">📊 Amostra de dados <code>.csv</code> / <code>.xlsx</code> <span class="optional">(opcional)</span></p>', unsafe_allow_html=True)
    data_file = st.file_uploader("csv_excel", type=["csv", "xlsx", "xls"], label_visibility="collapsed", key="data_upload")

# ── Config ───────────────────────────────────────────────────────────
with st.expander("⚙️ Configurações avançadas"):
    col_c, col_d = st.columns(2)
    with col_c:
        csv_table_name = st.text_input(
            "Nome da tabela no modelo",
            value="fVendas",
            help="Como a tabela aparece no Power BI. Ex: fVendas"
        )
    with col_d:
        date_table = st.text_input(
            "Tabela de datas",
            value="dCalendario",
            help="Nome da tabela calendário para medidas temporais"
        )
    col_e, col_f = st.columns(2)
    with col_e:
        date_col = st.text_input(
            "Coluna de data",
            value="Data",
            help="Coluna Date da tabela calendário. Ex: Data, Date, Fecha"
        )
    with col_f:
        measures_table = st.text_input(
            "Tabela de medidas",
            value="Medidas",
            help="Nome da tabela onde as medidas serão criadas no TMDL"
        )
    st.markdown("---")
    col_g, col_h = st.columns(2)
    with col_g:
        gen_time = st.toggle("Medidas de inteligência temporal", value=True,
                              help="YTD, MTD, QTD, YoY, MoM, Mês Anterior, Ano Anterior")
    with col_h:
        use_ai = st.toggle("Sugestões extras por IA", value=False,
                            help="Usa o Claude para sugerir medidas contextuais adicionais")

    if use_ai:
        api_key_input = st.text_input(
            "Chave API Anthropic",
            type="password",
            value=os.environ.get("ANTHROPIC_API_KEY", ""),
            help="Necessária para medidas sugeridas por IA. Obtenha em console.anthropic.com",
            placeholder="sk-ant-..."
        )
    else:
        api_key_input = ""

with st.expander("ℹ️ Como funciona"):
    st.markdown("""
O **IADAX** analisa seu `.pbix` e gera automaticamente medidas DAX prontas para importar no Power BI.

**O que é extraído do `.pbix`:**
- Tabelas e colunas (via `DataModelSchema` e `TMDLScripts`)
- Medidas já existentes (para não duplicar)

**Se o CSV/Excel for enviado:** as colunas dessa tabela são classificadas com mais precisão (numérico, data, texto), especialmente em arquivos com compressão XPress9.

**Medidas geradas por coluna numérica:**
- Base: `Total`, `Média`, `Contagem`, `Máximo`, `Mínimo`
- Temporais: `YTD`, `YTD Ano Anterior`, `MTD`, `QTD`, `Mês Anterior`, `Ano Anterior`, `Var YoY`, `% YoY`, `Var MoM`, `% MoM`

**Com IA ativada:** o Claude analisa o contexto do modelo e sugere medidas adicionais como rankings, proporções, contagens distintas e KPIs de negócio.
""")

# ── Generate ─────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:0.25rem'></div>", unsafe_allow_html=True)

can_generate = pbix_file is not None
if st.button("⚡ Gerar script TMDL", use_container_width=True, type="primary", disabled=not can_generate):
    with st.spinner("Analisando e gerando medidas..."):
        try:
            # ── Parse .pbix ──
            parser = PBIXParser(pbix_file.read())
            tables = parser.get_tables()
            existing = parser.get_existing_measures()
            parse_sources = parser.get_parse_sources()

            # ── Enrich from CSV/Excel (optional) ──
            if data_file:
                tname = (csv_table_name or "").strip() or data_file.name.rsplit(".", 1)[0]
                ext = data_file.name.rsplit(".", 1)[-1].lower()
                df = pd.read_csv(data_file) if ext == "csv" else pd.read_excel(data_file)
                parser.enrich_from_dataframe(tname, df)
                tables = parser._tables

            SKIP = {"Medidas", "Measures", "_Measures", measures_table}
            active = {k: v for k, v in tables.items()
                      if not v.get("is_hidden") and k not in SKIP}

            if not active:
                st.warning("Nenhuma tabela de dados encontrada no arquivo. Envie também um CSV/Excel para enriquecer a detecção.")
                st.stop()

            has_numerics = any(v["numeric"] for v in active.values())
            if not has_numerics:
                st.warning("Nenhuma coluna numérica detectada. Envie também um CSV/Excel da sua tabela fato para detectar as colunas corretamente.")

            # ── AI suggestions (optional) ──
            ai_measures = []
            if use_ai and api_key_input:
                with st.spinner("🤖 Consultando IA para sugestões adicionais..."):
                    ai_measures = get_ai_measures(
                        api_key=api_key_input,
                        tables=active,
                        existing_measures=existing,
                        date_table=date_table,
                        date_column=date_col,
                        file_name=pbix_file.name,
                    )
            elif use_ai and not api_key_input:
                st.warning("⚠️ Chave API não fornecida. Sugestões de IA serão ignoradas.")

            # ── Stats ──
            numeric_total = sum(len(v["numeric"]) for v in active.values())
            skip_time_kws = ("month number", "year", "month name")
            time_skipped = sum(
                1 for v in active.values()
                for c in v["numeric"]
                if any(kw == c.lower() for kw in skip_time_kws)
            )
            base_count = numeric_total * 5
            time_count = (numeric_total - time_skipped) * 10 if gen_time else 0
            estimated = base_count + time_count + len(ai_measures)
            new_measures = max(0, estimated - len(existing))

            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f'<div class="stat-card"><div class="stat-number">{len(active)}</div><div class="stat-label">Tabelas</div></div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="stat-card"><div class="stat-number">{numeric_total}</div><div class="stat-label">Cols Numéricas</div></div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="stat-card"><div class="stat-number">{new_measures}</div><div class="stat-label">Medidas Geradas</div></div>', unsafe_allow_html=True)
            c4.markdown(f'<div class="stat-card"><div class="stat-number">{len(existing)}</div><div class="stat-label">Já Existiam</div></div>', unsafe_allow_html=True)

            if parse_sources:
                st.markdown(
                    f'<p style="font-size:0.75rem;color:#64748b;text-align:center;margin-top:0.5rem">'
                    f'Fontes detectadas: {" · ".join(parse_sources)}</p>',
                    unsafe_allow_html=True
                )

            st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)

            # ── Detected columns expander ──
            with st.expander("📋 Colunas detectadas por tabela"):
                for tname_k, info in active.items():
                    parts = []
                    if info["numeric"]:
                        parts.append("**Numéricas:** " + ", ".join(f"`{c}`" for c in info["numeric"]))
                    if info["text"]:
                        parts.append("**Texto:** " + ", ".join(f"`{c}`" for c in info["text"]))
                    if info["date"]:
                        parts.append("**Data:** " + ", ".join(f"`{c}`" for c in info["date"]))
                    if parts:
                        st.markdown(f"**{tname_k}**")
                        for p in parts:
                            st.markdown(p)
                        st.markdown("---")

            # ── AI measures expander ──
            if ai_measures:
                with st.expander(f"🤖 {len(ai_measures)} medidas sugeridas pela IA"):
                    for m in ai_measures:
                        st.markdown(f"**{m['name']}**")
                        if m.get("description"):
                            st.caption(m["description"])
                        st.code(f"= {m['expression']}", language="sql")
                        st.markdown("---")

            # ── Legend ──
            legend_parts = ["Base: `Total` · `Média` · `Contagem` · `Máximo` · `Mínimo`"]
            if gen_time:
                legend_parts.append("Temporais: `YTD` · `YTD Ano Anterior` · `MTD` · `QTD` · `Mês Anterior` · `Ano Anterior` · `Var YoY` · `% YoY` · `Var MoM` · `% MoM`")
            if ai_measures:
                legend_parts.append(f"IA: {len(ai_measures)} medidas contextuais adicionais")

            st.markdown(
                '<div class="legend"><strong>Medidas geradas por coluna numérica:</strong><br>'
                + "<br>".join(legend_parts)
                + "</div>",
                unsafe_allow_html=True,
            )

            # ── Generate TMDL ──
            generator = TMDLGenerator(
                tables=active,
                existing_measures=existing,
                date_table=date_table,
                date_column=date_col,
                gen_time=gen_time,
                measures_table_name=measures_table or "Medidas",
                ai_measures=ai_measures,
            )
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
            st.error(f"Erro ao processar o arquivo: {e}")
            st.exception(e)

elif not pbix_file:
    st.markdown("""
    <div class="instructions">
        <div class="instruction-item">
            <span class="instruction-icon">📂</span>
            <div><strong>1. Carregue o .pbix</strong><br>Exportado do Power BI Desktop ou serviço</div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">📊</span>
            <div><strong>2. (Opcional) Envie o CSV da tabela fato</strong><br>Melhora a detecção de colunas numéricas em arquivos com compressão XPress9</div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">⚙️</span>
            <div><strong>3. Ajuste as configurações</strong><br>Nome da tabela, tabela de datas, coluna de data, medidas por IA</div>
        </div>
        <div class="instruction-item">
            <span class="instruction-icon">📄</span>
            <div><strong>4. Baixe o .tmdl gerado</strong><br>Cole no Tabular Editor ou importe via Power BI</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
