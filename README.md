# PBIX → TMDL Generator

Gera automaticamente um script TMDL com medidas DAX a partir de um arquivo `.pbix`.  
Funciona no **Streamlit Cloud** sem nenhuma dependência compilada ou nativa.

---

## Deploy no Streamlit Cloud

1. Suba todos os arquivos para um repositório GitHub
2. Acesse [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Selecione o repositório e defina `app.py` como arquivo principal
4. Clique em **Deploy** — só isso

---

## Instalação local

```bash
git clone https://github.com/seu-usuario/pbix-tmdl-generator.git
cd pbix-tmdl-generator
pip install -r requirements.txt
streamlit run app.py
```

---

## Como usar

### Fluxo básico (só .pbix)
1. Carregue o `.pbix` → a ferramenta lê o TMDL embutido e detecta colunas já referenciadas em medidas existentes
2. Clique em **Gerar script TMDL**
3. Baixe o `.tmdl` e cole no Tabular Editor

### Fluxo completo (.pbix + amostra de dados)
1. Carregue o `.pbix`
2. Exporte uma amostra da sua tabela fato do Power BI como CSV (*botão direito → Exportar dados*)
3. Carregue o CSV e informe o nome exato da tabela no modelo (ex: `fVendas`)
4. Gere e baixe o script

---

## Estrutura

```
pbix-tmdl-generator/
├── app.py              # Interface Streamlit
├── pbix_parser.py      # Parser do .pbix (zipfile puro, sem deps nativas)
├── tmdl_generator.py   # Gerador do script TMDL
├── style.css           # Design
├── requirements.txt    # streamlit + pandas + openpyxl
└── README.md
```

---

## Por que não usa pbixray?

O `pbixray` depende de `xpress9`/`xpress8`/`xmhuffman` — bibliotecas com extensões C
que só têm wheels pré-compilados até Python 3.13. O Streamlit Cloud roda **Python 3.14**
e essas libs falham na instalação.

Esta ferramenta usa apenas `zipfile` (stdlib) + `pandas` para ler os metadados
disponíveis no `.pbix` sem precisar descomprimir o `DataModel` binário.

---

## Medidas geradas por coluna numérica

| Prefixo | DAX |
|---------|-----|
| `Total` | `SUM` |
| `Média` | `AVERAGE` |
| `Contagem` | `COUNT` |
| `Máximo` | `MAX` |
| `Mínimo` | `MIN` |

Medidas que já existem no modelo são detectadas automaticamente e não são duplicadas.
