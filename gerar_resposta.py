from chromadb import Collection
import requests
import json
import re

from utils import calcular_totais

def extrair_itens_do_prompt(prompt_usuario: str) -> dict:
    with open("./dados_estruturados/icms_uf.json", "r") as f: icms_uf = json.load(f)

    prompt_completo = \
    f"""
        Analise o e-mail abaixo e responda SOMENTE com um JSON válido, sem texto adicional.
        E-mail:
        {prompt_usuario}

        Responda exatamente neste formato (sem textos complementares, apenas o JSON):
        {{"uf": "UF", "tipo": "TIPO", "itens": ["item1", "item2", ...]}}

        Regras:
        - "UF": sigla do estado brasileiro mencionado (UF).
        - "TIPO": "pmc" se pessoa física, "pf" se pessoa jurídica ou revendedor. Padrão: "pf".
        - "itens": lista de produtos ou medicamentos pedidos no e-mail, quantos forem pedidos, não limite a lista.
    """

    resposta = requests.post(
        "http://localhost:1234/v1/chat/completions",
        json={
            "model": "local-model",
            "messages": [{"role": "user", "content": prompt_completo}],
            "temperature": 0.4,
        }
    )

    conteudo = resposta.json()["choices"][0]["message"]["content"].strip()

    match = re.search(r'\{.*\}', conteudo, re.DOTALL)
    if not match:
        raise ValueError(f"Modelo não retornou JSON válido: {conteudo}")

    dados = json.loads(match.group())

    uf = dados.get("uf", "SP").upper()
    tipo = dados.get("tipo", "pf")
    itens = dados.get("itens", [])

    print("Dados extraídos do IcMS:", icms_uf["aliquotas_uf"])
    chave_icms = icms_uf["aliquotas_uf"].get(uf, "SP").get("chave_preco", "icms_18")
    chave_preco_tipo = f"preco_{chave_icms}_{tipo}"

    return {
        "itens": itens,
        "chave_preco_tipo": chave_preco_tipo
    }

def gerar_contexto_geral(pergunta_cliente: str, colecao: Collection) -> str:
    extracao = extrair_itens_do_prompt(pergunta_cliente)
    itens = extracao.get("itens", [])
    chave_preco_tipo = extracao.get("chave_preco_tipo", "preco_icms_18_pj")

    contexto_geral = ""
    ids_ja_vistos = set()
    
    for item in itens:
        resultados = colecao.query(
            query_texts=[item],
            n_results=2
        )
        for i in range(len(resultados['documents'][0])):
            doc_id = resultados['ids'][0][i]
            if doc_id in ids_ja_vistos:
                continue
            ids_ja_vistos.add(doc_id)
            
            doc_texto = resultados['documents'][0][i]
            meta = resultados['metadatas'][0][i]
            contexto_geral += f"{doc_texto}\n"
            contexto_geral += f"preco: R$ {meta[chave_preco_tipo]}\n"
    
    return contexto_geral

def gerar_prompt_final(contexto_produtos: str, pergunta_original: str) -> str:
    return \
    f"""
        Você é um assistente de orçamentos de farmácia.
        Leia o pedido e o catálogo abaixo. Responda SOMENTE com JSON válido, sem texto adicional.

        Pedido:
        {pergunta_original}

        Catálogo disponível:
        {contexto_produtos}

        Responda exatamente neste formato:
        {{
            "itens": [{{"produto": "Nome do produto", "codigo": "CODIGO", "quantidade": "QTD", "preco_unitario": PRECO_UNITARIO}}], 
            "cliente": {{"tipo": "TIPO", "uf": "UF"}}
        }}

        Regras para "itens":
        - Use APENAS produtos presentes no catálogo acima.
        - "CODIGO": deve ser o "CÓDIGO SAP" do produto no catálogo.
        - "QTD": número **inteiro** extraído do pedido. Se não mencionado, use 1.
        - "PRECO_UNITARIO": valor exato do catálogo acima em **float**.
        - NÃO calcule preco_total nem total; deixe fora do JSON.
        REGRAS para "cliente":
        - "TIPO": "FÍSICA" se cliente for pessoa física, senão "JURÍDICA/REVENDEDOR".
        - "UF": nome do estado + sigla do estado brasileiro mencionado no final do e-mail (NOME DO ESTADO + UF).
    """


def gerar_resposta(pergunta: str) -> dict:
    """Envia prompt para Gemma 3 1B e retorna orçamento estruturado."""
    resposta = requests.post(
        "http://localhost:1234/v1/chat/completions",
        json={
            "model": "local-model",
            "messages": [{"role": "user", "content": pergunta}],
            "temperature": 0.4,
        }
    )

    conteudo = resposta.json()["choices"][0]["message"]["content"].strip()

    # Extrai JSON mesmo se o modelo adicionar texto ao redor
    match = re.search(r'\{.*\}', conteudo, re.DOTALL)
    if not match:
        raise ValueError(f"Modelo não retornou JSON válido: {conteudo}")

    print("Resposta bruta do modelo:", conteudo)
    dados_brutos = json.loads(match.group())
    orcamento = calcular_totais(dados_brutos)

    print(json.dumps(orcamento, ensure_ascii=False, indent=2))
    return orcamento