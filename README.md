# Chunk Catálogo de Produtos

Automação inteligente para processamento de solicitações de orçamento de medicamentos. O sistema analisa emails de clientes, identifica produtos solicitados e gera orçamentos estruturados com preços e impostos por estado.

## Sobre o trabalho
Um trabalho referente ao 5º período da graduação de Ciência de Dados e Inteligência Artificial da IBMEC.
Participantes:

- Eduardo Peruzzo
- Estevão Moraes
- Gabriel Corrêa
- Marcelle Lohane
- Mateus Sachinho


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
├── resultados_testes/           # Orçamentos gerados nos testes (JSON)
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
- **Ollama + Gemma 3 1B** - Modelo LLM local para processamento de linguagem natural
- **BM25** - Busca léxica/fuzzy para produtos
- **Rank-BM25** - Implementação Python do algoritmo BM25

## 📦 Instalação

### Pré-requisitos
- Python 3.9 ou superior
- pip (gerenciador de pacotes Python)

### Passos

1. **Clone o repositório**
   ```bash
   git clone https://github.com/EstevaoMO/chunk_catalogo_produtos.git
   cd chunk_catalogo_produtos
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

### Configurar Modelo Local (Gemma 3 1B ou outro de sua preferẽncia)

Para usar o Ollama com o modelo Gemma 3 1B:

```bash
# Instale o Ollama (https://ollama.ai)
# Depois execute:
ollama pull gemma3:1b

# Inicie o servidor Ollama
ollama serve
```

> OBS: o mesmo processo pode ser feito via interface do LMStudio.

O código está configurado para usar a API local em `http://localhost:1234/v1/chat/completions`

### Fluxo de Processamento

**1. Normalização de Dados**
```python
from gerar_chunks import normalizar_notacao, gerar_chunk
df = pd.read_csv("https://raw.githubusercontent.com/alvaroriz/datascience_datasets/refs/heads/main/Catalogo-Produtos.csv", sep=";")
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
      "preco_unitario": 97.19,
      "preco_total": 971.9
    }
  ],
  "cliente": {
    "tipo": "Pessoa Jurídica",
    "uf": "RJ"
  },
  "total": 971.9
}
```

## 📌 Notas Importantes

- O sistema se adapta automaticamente aos diferentes tipos de clientes (PF, PJ, Revendedora)
- Os preços são calculados automaticamente de acordo com a alíquota de ICMS do estado
- O banco vetorial é persistido em `.vector_db/` para reutilização
- Emails de exemplo podem ser configurados em `main.py`

## 🔍 Sistema de Busca Híbrido

O projeto utiliza uma abordagem **RAG (Retrieval-Augmented Generation)** combinando:

### 1. **Busca Semântica (ChromaDB)**
- Embeddings com `all-MiniLM-L6-v2`
- Captura significado semântico dos produtos
- Ideal para nomes comerciais, abreviações e variações

### 2. **Busca Léxica (BM25)**
- Tokens e n-gramas de 3 letras
- Recuperação precisa por código SAP
- Busca exata por componentes do nome

### 3. **Fusão de Resultados**
- Combina resultados das duas buscas
- Remove duplicatas mantendo relevância
- Melhora acurácia para produtos encontrados

## 📚 Documentação Adicional

Para entender as técnicas de preparação de dados e otimizações específicas para o Gemma 3 1B, consulte **[MANUAL.md](MANUAL.md)**

## 🐛 Troubleshooting

| Problema | Solução |
|----------|---------|
| Ollama não conecta | Verifique se `ollama serve` está rodando em `localhost:1234` |
| Chunks não encontrados | Certifique-se que `./chunks/` existe e contém arquivos `.json` |
| Banco vetorial está lento | Recrie o banco com `obter_colecao(sobrescrever_banco=True)` |

## 📄 Licença

Este projeto é licenciado sob a MIT License - veja o arquivo LICENSE para detalhes.
