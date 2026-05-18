# Manual: Técnicas de Preparação de Dados para Gemma 3 1B

## 📖 Introdução

Este manual documenta as técnicas de preparação e otimização de dados implementadas para maximizar a acurácia e performance do modelo **Gemma 3 1B** em tarefas de extração e processamento de informações farmacêuticas.

O Gemma 3 1B é um modelo compacto de 1.2GB com excelente relação desempenho/tamanho. A qualidade dos dados preparados é fundamental para explorar seu potencial máximo.

---

## 🎯 Princípios Fundamentais

### 1. **Normalização de Dados Estruturados**

#### Por que normalizar?
- Elimina variações que podem confundir o modelo
- Padroniza formatos para interpretação consistente
- Reduz ruído que afeta a acurácia

#### Técnicas Aplicadas

**Notação Científica → Numérica**
```python
# Antes: 1E+06, 7896660000000 em notação científica
# Depois: 1000001, 7896660000000 (números limpos)

def normalizar_notacao(df, colunas_para_normalizar):
    """Converte notação científica para formato padrão"""
    for coluna in colunas_para_normalizar:
        df[coluna] = df[coluna].apply(lambda x: x.replace(',', '.'))
        df[coluna] = df[coluna].apply(lambda x: f"{float(x):.0f}" 
                                      if not ("-" in x or "ISENTO" in x) else x)
    return df
```

**Aplicação em Campos-Chave**
- `CÓDIGO SAP`: Identificador único do produto
- `CÓDIGO EAN`: Código de barras padronizado
- `REGISTRO MS`: Registro no Ministério da Saúde

---

## 📊 Estratégia de Chunking (Segmentação)

### 2. **Divisão Lógica de Dados em Chunks**

O chunking é a divisão de dados em blocos semanticamente significativos que o modelo consegue processar eficientemente.

#### Estrutura do Chunk JSON
```json
{
  "sap": "1000001",
  "nome": "ACICLOVIR 200MG COM BLX25",
  "principio_ativo": "ACICLOVIR",
  "familia": "ANTIVIRAIS",
  "ncm": "3004905000",
  "tipo": "MEDICAMENTO",
  "tarja": "VERMELHA",
  "qtde": "25",
  "precos": {
    "icms_0": { "pf": "97.19", "pmc": "116.63" },
    "icms_12": { "pf": "89.45", "pmc": "107.34" },
    "icms_18": { "pf": "79.62", "pmc": "95.54" }
  },
  "ean": "7896660000000",
  "registro_ms": "1234567"
}
```

#### Vantagens desta Estrutura
✅ **Rastreabilidade**: Cada arquivo é um produto único  
✅ **Modularidade**: Fácil atualizar ou remover itens  
✅ **Performance**: Indexação rápida em banco vetorial  
✅ **Clareza**: Estrutura JSON facilita parsing

#### Tamanho Otimizado
- **Um arquivo por produto**: ~500-800 bytes (ideal)
- **Não muito pequeno**: Evita fragmentação
- **Não muito grande**: Cabe em memória de modelos pequenos

---


## 🧮 Busca Híbrida: Semântica + Léxica

### 3. **Dual Retrieval para Máxima Cobertura**

O sistema combina duas estratégias complementares:

#### A. Busca Semântica (ChromaDB + Embeddings)

**Como funciona:**
```
Entrada: "Aciclovir comprimido"
↓
Embedding (all-MiniLM-L6-v2): [0.12, -0.45, 0.89, ...]
↓
Comparação de similaridade com banco vetorial
↓
Resultado: ACICLOVIR 200MG COM BLX25 (score: 0.92)
```

**Vantagens:**
- Compreende variações (Aciclovir, Aciclovir 200, Acyclovir)
- Identifica sinônimos (antibiótico, remédio)
- Captura semântica de nomes comerciais

**Limitações:**
- Não encontra por código SAP numérico puro
- Sensível a typos severos

#### B. Busca Léxica (BM25)

**Como funciona:**
```
Entrada: "1000001"
↓
Tokenização N-gram: ["100", "000", "001", ...]
↓
Pontuação BM25 no corpus
↓
Resultado: SAP 1000001 (score BM25: 8.5)
```

**Vantagens:**
- Encontra códigos exatos
- Recupera termos específicos
- Rápido e determinístico

**Limitações:**
- Não compreende semântica
- Falha com variações de escrita

#### C. Fusão Inteligente

```python
def gerar_contexto_geral(pergunta, colecao, bm25, catalogo_bm25):
    produtos_encontrados = {}
    
    for item in itens_solicitados:
        # Se for SAP (numérico)
        if eh_sap(item):
            resultados_chroma = colecao.query(
                query_texts=[item],
                n_results=2,
                where={"sap": item}  # Filtro exato
            )
        else:
            # Busca semântica
            resultados_chroma = colecao.query(
                query_texts=[item],
                n_results=2
            )
            
            # Busca léxica complementar
            tokens = tokenizar_ngrams(item)
            scores_bm25 = bm25.get_scores(tokens)
            top_indices = sorted(range(len(scores_bm25)), 
                                key=lambda i: scores_bm25[i], 
                                reverse=True)[:2]
        
        # Combina resultados únicos
        for resultado in combinar_resultados(chroma, bm25):
            produtos_encontrados[resultado['sap']] = resultado
    
    return produtos_encontrados
```

**Resultado:**
- ✅ Encontra por nome semelhante
- ✅ Encontra por código exato
- ✅ Remove duplicatas
- ✅ Mantém apenas produtos mais relevantes

---

## 💾 Processamento de Preços em Múltiplos Formatos

### 4. **Normalização de Estrutura de Preços**

O catálogo contém preços em múltiplos formatos (18 variações por estado).

#### Estrutura Original (CSV)
```
ICMS 0 % (PF) | ICMS 0 % (PMC) | ICMS 12 % (PF) | ... | ICMS 18 % (PMC)
97.19         | 116.63         | 89.45          | ... | 95.54
```

#### Transformação para JSON Aninhado

```python
def achatar_precos(precos):
    """Converte dict aninhado em chaves planas para ChromaDB"""
    metadado_precos = {}
    for icms, valores in precos.items():
        for tipo, valor_str in valores.items():
            chave = f"preco_{icms}_{tipo}"  # Ex: "preco_icms_18_pf"
            try:
                valor_float = float(valor_str.replace(",", "."))
            except (ValueError, AttributeError):
                valor_float = 0.0
            metadado_precos[chave] = valor_float
    return metadado_precos
```

**Resultado:**
```json
{
  "preco_icms_0_pf": 97.19,
  "preco_icms_0_pmc": 116.63,
  "preco_icms_12_pf": 89.45,
  "preco_icms_12_pmc": 107.34,
  "preco_icms_18_pf": 79.62,
  "preco_icms_18_pmc": 95.54,
  ...
}
```

#### Seleção Dinâmica de Preço

```python
# Extrai UF e tipo cliente do email
uf = "SP"  # Extraído do prompt
tipo = "pf"  # Extraído do prompt

# Seleciona chave correta
chave_icms = icms_uf[uf].get("chave_preco", "icms_18")
chave_preco_tipo = f"preco_{chave_icms}_{tipo}"

# Recupera valor correto
preco_unitario = produto[chave_preco_tipo]
```

---

## 🎓 Otimização para Gemma 3 1B

### 5. **Adaptações Específicas para Modelo Compacto**

O Gemma 3 1B tem limitações que exigem adaptações:

#### Limitação 1: Contexto Reduzido
- **Solução**: Fornecer apenas informações relevantes
- **Implementação**: Limitar a 2 melhores resultados por busca

```python
resultado_chroma = colecao.query(
    query_texts=[item],
    n_results=2
)
```

#### Limitação 2: Capacidade de Raciocínio
- **Solução**: Decomposição em passos simples
- **Implementação**: Prompts com exemplos claros

```
RUIM: "Qual é o melhor preço para este medicamento?"
BOM: "Se o cliente está em SP e é PF, qual é o preço?
      Responda apenas com o número: R$ XXX.XX"
```

#### Limitação 3: Consistência com JSON
- **Solução**: Regex para extrair JSON da resposta
- **Implementação**: Validação robusta

```python
match = re.search(r'\{.*\}', conteudo, re.DOTALL)
if not match:
    raise ValueError("Modelo não retornou JSON válido")

dados = json.loads(match.group())
```

---

## 📈 Métricas de Qualidade

### 6. **Métrica utilizada para definir sucesso**

#### Parâmetros

Consideramos os seguintes modelos de email, nos quais o cliente cobra por/utilizando-se de:

- Nome comercial do produto
- Código SAP do produto
- Princípio ativo
- Abreviações / nomes parciais
- Quantidades variadas
- Textos informais

#### Resultados

O modelo `GEMMA 3 1B` foi capaz de responder com cerca de *95.6%* (43/45) de acertividade.
No entanto, o modelo `GEMMA 3 4B` foi capaz de responder a mesma bateria de testes com *100%* (45/45) de acertividade.

A maior dificuldade do modelo de menos parâmetros (1Bi) gira em torno dos email muito confusos e/ou mal estruturados. Uma consistência simples e estrutura padrão já são o suficiente para trazer uma acertividade excelsa.  

> OBS: os testes podem ser feitos a partir do arquivo `bateria_testes.py`!!!
