# Chunk Catálogo de Produtos

Automação inteligente para processamento de solicitações de orçamento de medicamentos. O sistema analisa emails de clientes, identifica produtos solicitados e gera orçamentos estruturados com preços e impostos por estado.

## Sobre o trabalho
Um trabalho referente ao 5º período da graduação de Ciência de Dados e Inteligência Artificial da IBMEC.
Participantes:

- Marcelle Lohane
- Eduardo Peruzzo
- Estevão Moraes
- Gabriel Corrêa
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
├── agent_server.py              # API FastAPI para integração com n8n
├── utils.py                     # Funções auxiliares
├── workflow.json                # Fluxo n8n importável
└── .vector_db/                  # Banco de dados vetorial (Chroma)
```

## 🛠️ Tecnologias Utilizadas

- **Python 3.12+** - Linguagem de programação
- **FastAPI** - API para integração com o n8n
- **Pandas** - Processamento e manipulação de dados tabulares
- **Chroma DB** - Banco de dados vetorial para busca semântica
- **Sentence Transformers** - Embeddings semânticos (`all-MiniLM-L6-v2`)
- **Ollama + Gemma 3 1B** - Modelo LLM local para processamento de linguagem natural
- **BM25** - Busca léxica/fuzzy para produtos
- **Rank-BM25** - Implementação Python do algoritmo BM25
- **n8n** - Orquestrador do fluxo de automação

## 📦 Instalação

### Pré-requisitos
- Python 3.12 ou superior
- Ollama
- n8n

### Passos

1. **Clone o repositório**
   ```bash
   git clone <repositorio>
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

---

# Instruções para Execução do Projeto no n8n

## Pré-requisitos

Instalar:
* Python 3.12 ou superior
* Ollama
* n8n

---

## 1. Clonar o projeto

```bash
git clone <repositorio>
cd chunk_catalogo_produtos
```

---

## 2. Criar ambiente virtual

Windows:
```powershell
python -m venv venv
.\venv\Scripts\activate
```

Linux/Mac:
```bash
python -m venv venv
source venv/bin/activate
```

---

## 3. Instalar dependências

```bash
pip install -r requirements.txt
```

---

## 4. Instalar o modelo de IA

Instalar o Ollama:  
https://ollama.com

Baixar o modelo:
```bash
ollama pull gemma3:1b
```

Verificar instalação:
```bash
ollama list
```

O modelo `gemma3:1b` deve aparecer na lista.

---

## 5. Iniciar o Ollama

```bash
ollama serve
```

Caso já esteja rodando, nenhuma ação adicional é necessária.

---

## 6. Iniciar a API

Na pasta do projeto:
```bash
uvicorn agent_server:app --host 0.0.0.0 --port 8000
```

Verificar funcionamento — abrir no navegador:
```
http://localhost:8000/docs
```

A documentação da API deve aparecer.

---

## 7. Testar a API

Na página Swagger (`/docs`), executar:

**POST /processar**

Exemplo de body:
```json
{
  "email": "Preciso de orçamento de dipirona",
  "salvar": false
}
```

A API deve retornar um orçamento em JSON.

---

## 8. Executar o workflow n8n

Abrir o n8n:
```bash
n8n
```

Acessar:
```
http://localhost:5678
```

Importar o arquivo:
```
workflow.json
```

Executar o workflow.

---

## ⚙️ Fluxo Executado

O workflow realiza:

1. Recebimento da solicitação de orçamento
2. Envio da solicitação para a API FastAPI
3. Consulta ao banco vetorial ChromaDB
4. Busca híbrida utilizando BM25
5. Processamento pelo modelo Gemma 3
6. Geração do orçamento estruturado
7. Retorno do orçamento ao usuário

---

## 🧰 Tecnologias Utilizadas

* Python
* FastAPI
* Ollama
* Gemma 3
* ChromaDB
* BM25
* n8n
* Pandas
* Sentence Transformers

---

## 🐛 Troubleshooting

| Problema | Solução |
|----------|---------|
| Ollama não conecta | Verifique se `ollama serve` está rodando |
| Chunks não encontrados | Certifique-se que `./chunks/` existe e contém arquivos `.json` |
| Banco vetorial está lento | Recrie o banco com `obter_colecao(sobrescrever_banco=True)` |
| Módulo não encontrado | Confirme que o ambiente virtual está ativado |
| API não responde em :8000 | Verifique se o uvicorn está rodando sem erros no terminal |

## 📄 Licença

Este projeto é licenciado sob a MIT License - veja o arquivo LICENSE para detalhes.
