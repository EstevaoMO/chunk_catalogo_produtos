# Chunk Catálogo de Produtos

Automação inteligente para processamento de solicitações de orçamento de medicamentos. O sistema analisa emails de clientes, identifica produtos solicitados e gera orçamentos estruturados com preços e impostos por estado.

## 📋 Visão Geral

Este projeto implementa um pipeline de processamento de texto que:

- **Lê** catálogos de medicamentos (formato CSV)
- **Normaliza** dados de produtos e converte para chunks estruturados
- **Indexa** produtos em banco de dados vetorial para busca semântica
- **Processa** emails de solicitação de orçamento
- **Gera** respostas estruturadas em JSON com preços calculados por ICMS por UF

## 📁 Estrutura do Projeto

```
.
├── main.py                      # Pipeline
├── Catalogo-Produtos.csv        # Base de dados de medicamentos
├── chunks/                      # Chunks JSON gerados (um por produto)
│   ├── chunk_1000001-*.json
│   └── ...
├── dados_estruturados/          # Dados estruturados para consulta
├── resultados/                  # Orçamentos gerados (JSON)
├── gerar_chunks.py              # Normalização e geração de chunks
├── db.py                        # Gerenciamento do banco vetorial
├── gerar_resposta.py            # Processamento de emails e geração de respostas
├── utils.py                     # Funções auxiliares
└── .vector_db/                  # Banco de dados vetorial (Chroma)
```

## 🛠️ Tecnologias Utilizadas

- **Python 3.9+** - Linguagem de programação
- **Pandas** - Processamento e manipulação de dados tabulares
- **Chroma DB** - Banco de dados vetorial para busca semântica
- **Sentence Transformers** - Embeddings semânticos (`all-MiniLM-L6-v2`)
- **Chromadb** - Persistência e indexação de dados

## 📦 Instalação

### Pré-requisitos
- Python 3.9 ou superior
- pip (gerenciador de pacotes Python)

### Passos

1. **Clone o repositório**
   ```bash
   git clone https://github.com/EstevaoMO/chunk_catalogo_produtos.git
   cd chunk_catalogo
   ```

2. **Crie um ambiente virtual**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # ou
   .venv\Scripts\activate     # Windows
   ```

3. **Instale as dependências**
   ```bash
   pip install -r requirements.txt
   ```

## 🚀 Como Usar

### Execução Principal

```bash
python main.py
```

O script irá:
1. Carregar o catálogo de medicamentos do CSV
2. Normalizar os dados
3. Gerar chunks JSON para cada produto
4. Criar/atualizar o banco vetorial
5. Processar um email de exemplo (definido em `main.py`)
6. Gerar um orçamento estruturado em `resultados/`

### Fluxo de Processamento

**1. Normalização de Dados**
```python
from gerar_chunks import normalizar_notacao, gerar_chunk
df = pd.read_csv("Catalogo-Produtos.csv", sep=";")
df_normalizado = normalizar_notacao(df, colunas_para_normalizar)
```

**2. Geração de Chunks**
Cada linha do catálogo é convertida em um arquivo JSON contendo:
- Informações do produto (código SAP, nome, princípio ativo)
- Família e tipo de medicamento
- Preços com diferentes alíquotas de ICMS por estado
- Dados de registro

**3. Indexação Vetorial**
```python
from db import obter_colecao, indexar_chunks_json
colecao = obter_colecao()
indexar_chunks_json(colecao, pasta_chunks="./chunks")
```

**4. Processamento de Email**
```python
from gerar_resposta import gerar_contexto_geral, gerar_prompt_final, gerar_resposta
contexto = gerar_contexto_geral(email_cliente, colecao=colecao)
resposta = gerar_resposta(contexto)
```

## 📝 Exemplo de Saída

```json
{
  "itens": [
    {
      "nome": "ACICLOVIR 200MG COM BLX25",
      "codigo_sap": "1000001",
      "quantidade": 10,
      "precos_por_uf": {
        "RJ": {"icms": "18%", "valor": 45.90},
        "SP": {"icms": "20%", "valor": 42.50}
      }
    }
  ],
  "cliente": {
    "tipo": "Pessoa Jurídica",
    "uf": "RJ"
  }
}
```

## 📌 Notas Importantes

- O sistema se adapta automaticamente aos diferentes tipos de clientes (PF, PJ, Revendedora)
- Os preços são calculados automaticamente de acordo com a alíquota de ICMS do estado
- O banco vetorial é persistido em `.vector_db/` para reutilização
- Emails de exemplo podem ser configurados em `main.py`