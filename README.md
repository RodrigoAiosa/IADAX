# PBIX → TMDL Generator

Ferramenta em Python + Streamlit que recebe um arquivo `.pbix` do Power BI e gera automaticamente um script **TMDL** com todas as medidas DAX possíveis com base nas colunas numéricas detectadas no modelo de dados.

---

## Estrutura do projeto

```
pbix-tmdl-generator/
├── app.py              # Interface Streamlit (UI principal)
├── pbix_parser.py      # Leitura e parse do arquivo .pbix
├── tmdl_generator.py   # Geração do script TMDL com as medidas DAX
├── style.css           # Estilos customizados para o Streamlit
├── packages.txt        # Pacotes apt (necessário para Streamlit Cloud)
├── requirements.txt    # Dependências Python
└── README.md
```

---

## Deploy no Streamlit Cloud

1. Suba todos os arquivos para um repositório GitHub público
2. Acesse [share.streamlit.io](https://share.streamlit.io) e clique em **New app**
3. Selecione o repositório e defina `app.py` como arquivo principal
4. Clique em **Deploy**

> **Por que o `packages.txt`?**  
> A dependência `apsw` (usada internamente pelo `pbixray` para ler o DataModel do `.pbix`) não tem wheel pré-compilado disponível via PyPI em todos os ambientes. O arquivo `packages.txt` instrui o Streamlit Cloud a instalar `python3-apsw` via `apt` antes do `pip`, resolvendo o problema.

---

## Instalação local

```bash
git clone https://github.com/seu-usuario/pbix-tmdl-generator.git
cd pbix-tmdl-generator

python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# .venv\Scripts\activate       # Windows

pip install -r requirements.txt
streamlit run app.py
```

> **Linux/Mac:** Se `pbixray` falhar na instalação, rode antes:  
> `sudo apt install python3-apsw` (Ubuntu/Debian)  
> `brew install apsw` (macOS)

---

## Como funciona

1. O `.pbix` é lido como ZIP e o `DataModel` binário é descomprimido via **pbixray**
2. Tabelas internas do Power BI (`DateTableTemplate_*`, `LocalDateTable_*`) são ignoradas
3. Para cada coluna numérica de tabelas de dados são geradas **5 medidas DAX**:
   - `Total <Coluna>` → `SUM`
   - `Média <Coluna>` → `AVERAGE`
   - `Contagem <Coluna>` → `COUNT`
   - `Máximo <Coluna>` → `MAX`
   - `Mínimo <Coluna>` → `MIN`
4. O formato é inferido pelo nome da coluna (detecta colunas monetárias automaticamente)
5. O script TMDL pode ser colado no **Tabular Editor** ou importado via Power BI

---

## Exemplo de saída

```tmdl
createOrReplace

	table Medidas

		measure 'Total Gross Sales' = SUM(fVendas[Gross Sales])
			formatString: R$\ #,0.00;(R$\ #,0.00);R$\ #,0.00

			annotation PBI_FormatHint = {"currencyCulture":"pt-BR"}

		measure 'Média Gross Sales' = AVERAGE(fVendas[Gross Sales])
			formatString: R$\ #,0.00;(R$\ #,0.00);R$\ #,0.00
		...
```

---

## Dependências

| Pacote | Instalação | Função |
|--------|-----------|--------|
| `streamlit` | pip | Interface web |
| `pbixray` | pip | Leitura do DataModel do `.pbix` |
| `xpress9/8` | pip | Descompressão do formato Microsoft XPress |
| `python3-apsw` | **apt** (`packages.txt`) | Wrapper SQLite usado pelo pbixray |
| `pandas` | pip | Classificação de tipos de coluna |

---

## Requisitos

- Python 3.9+
- Linux x86_64 (Streamlit Cloud, Ubuntu, Debian) ou macOS
