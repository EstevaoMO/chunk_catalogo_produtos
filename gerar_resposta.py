from chromadb import Collection
import requests
import json
import re

from utils import calcular_totais, tokenizar_ngrams

def extrair_itens_do_prompt(prompt_usuario: str) -> dict:
    with open("./dados_estruturados/icms_uf.json", "r") as f: icms_uf = json.load(f)

    prompt_completo = \
    f"""
        Você é um assistente especialista em extração de dados. Sua única tarefa é ler e-mails de pedidos e retornar EXCLUSIVAMENTE um objeto JSON válido, sem marcações markdown e sem nenhum texto adicional.

        REGRAS PARA OS CAMPOS DO JSON:
        1. "uf": A sigla do estado brasileiro do cliente. DEVE ser obrigatoriamente um destes valores: AC, AL, AM, AP, BA, CE, DF, ES, GO, MA, MT, MS, MG, PB, PR, PE, PI, RN, RS, RJ, RO, RR, SC, SP, SE, TO. Se o estado não for mencionado, retorne null.
        2. "tipo": Retorne "pmc" se o remetente for uma Pessoa Física comum. Retorne "pf" se o remetente for Pessoa Jurídica (como farmácias, clínicas, revendedores) ou se não for possível determinar com certeza. O padrão é "pf".
        3. "itens": Uma lista contendo apenas os nomes dos produtos, princípios ativos ou códigos SAP solicitados. Não inclua as quantidades (ex: remova "10x", "5 caixas", etc). Caso detecte um item de pedido com código SAP, retorne APENAS O NÚMERO.

        EXEMPLOS DE USO:

        ---
        E-mail:
        Olá, gostaria de receber um orçamento dos seguintes produtos:
        4x ACHEFLAN CREM BGX30G
        10x ACETILCISTEINA 20MG XPE FRAM VDX120ML
        15x CLOR RANITIDINA 300MG COMR BLX20
        At.te,
        José Pedidor
        JoseFarmacia - Rio de Janeiro - RJ

        Saída:
        {{"uf": "RJ", "tipo": "pf", "itens": ["ACHEFLAN CREM BGX30G", "ACETILCISTEINA 20MG XPE FRAM VDX120ML", "CLOR RANITIDINA 300MG COMR BLX20"]}}
        ---
        E-mail:
        Bom dia, sou o Marcos, moro em São Paulo (SP). Gostaria de saber o preço do paracetamol e também do item de código SAP 987654.

        Saída:
        {{"uf": "SP", "tipo": "pmc", "itens": ["paracetamol", "987654"]}}
        ---
        E-mail:
        Favor cotar 5 frascos de dipirona em gotas.

        Saída:
        {{"uf": null, "tipo": "pf", "itens": ["dipirona em gotas"]}}
        ---

        E-mail:
        {prompt_usuario}

        Saída:
    """

    resposta = requests.post(
        "http://localhost:1234/v1/chat/completions",
        json={
            "model": "local-model",
            "messages": [{"role": "user", "content": prompt_completo}],
            "temperature": 0.1,
        }
    )

    conteudo = resposta.json()["choices"][0]["message"]["content"].strip()

    match = re.search(r'\{.*\}', conteudo, re.DOTALL)
    if not match:
        raise ValueError(f"Modelo não retornou JSON válido: {conteudo}")

    dados = json.loads(match.group())
    print("ITENS EXTRAÍDOS DO EMAIL:")
    print(dados)

    uf = dados.get("uf", "SP").upper()
    tipo = dados.get("tipo", "pf")
    itens = dados.get("itens", [])

    # print("Dados extraídos do IcMS:", icms_uf["aliquotas_uf"])
    chave_icms = icms_uf["aliquotas_uf"].get(uf, icms_uf["aliquotas_uf"]["SP"]).get("chave_preco", "icms_18")
    chave_preco_tipo = f"preco_{chave_icms}_{tipo}"
    return {
        "itens": itens,
        "chave_preco_tipo": chave_preco_tipo
    }

def gerar_contexto_geral(pergunta_cliente: str, colecao: Collection, bm25, catalogo_bm25) -> str:
    extracao = extrair_itens_do_prompt(pergunta_cliente)
    itens = extracao.get("itens", [])
    chave_preco_tipo = extracao.get("chave_preco_tipo", "preco_icms_18_pj")

    produtos_encontrados = {} # Usaremos um dicionário (chave=SAP) para evitar itens duplicados
    
    for item in itens:
        is_sap = item.isdigit() or ("SAP" in item.upper() and item.replace("SAP", "").strip().isdigit())
        
        if is_sap:
            # Se for SAP, usamos a busca filtrada e exata do ChromaDB
            sap_limpo = item.replace("SAP", "").strip()
            resultados = colecao.query(
                query_texts=[item], 
                n_results=2,
                where={"sap": sap_limpo}
            )
            for i in range(len(resultados['documents'][0])):
                meta = resultados['metadatas'][0][i]
                produtos_encontrados[meta['sap']] = meta
                
        else:
            # --- BUSCA HÍBRIDA PARA NOMES/ABREVIAÇÕES ---
            
            # 1. Busca Semântica (ChromaDB)
            res_chroma = colecao.query(query_texts=[item], n_results=2)
            for i in range(len(res_chroma['documents'][0])):
                meta = res_chroma['metadatas'][0][i]
                produtos_encontrados[meta['sap']] = meta
                
            # 2. Busca Léxica/Fuzzy (BM25)
            busca_tokenizada = tokenizar_ngrams(item)
            scores = bm25.get_scores(busca_tokenizada)
            
            # Pegando os índices dos 2 melhores resultados do BM25
            top_2_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:2]
            
            for idx in top_2_indices:
                if scores[idx] > 0: # Só adiciona se teve alguma pontuação
                    meta_bm25 = catalogo_bm25[idx]
                    produtos_encontrados[meta_bm25['sap']] = meta_bm25
                    
    # Monta a string final do catálogo a partir dos itens únicos encontrados
    contexto_geral = ""
    for meta in produtos_encontrados.values():
        contexto_geral += f"Produto: {meta['nome']}\n"
        contexto_geral += f"preco: R$ {meta[chave_preco_tipo]}\n"
        contexto_geral += f"sap: {meta['sap']}\n"
        contexto_geral += f"principio_ativo: {meta['principio_ativo']}\n\n"
        
    print(contexto_geral)
    return contexto_geral

def gerar_prompt_final(contexto_produtos: str, pergunta_original: str) -> str:
    return \
    f"""Você é um sistema especialista em extração e cruzamento de dados. Sua tarefa é ler um [E-MAIL DO CLIENTE], compará-lo com um [CATÁLOGO] retornado do banco de dados e gerar EXCLUSIVAMENTE um objeto JSON válido.

NÃO inclua saudações, explicações ou marcações markdown. Apenas retorne o JSON bruto.

REGRAS PARA "itens":
1. FILTRO RIGOROSO: O catálogo pode conter produtos extras que o cliente NÃO pediu. Inclua APENAS os produtos que o cliente efetivamente solicitou. Descarte todos os outros.
2. COMPLETUDE: Se o cliente pediu N produtos distintos, o JSON deve ter exatamente N itens. Não descarte pedidos válidos e nem adicione mais itens do que o cliente pediu. Ex: cliente pediu exatamente 1 item, o JSON deve incluir apenas 1 item; cliente pediu 2 itens, o JSON deve incluir exatamente os 2 itens que foram pedidos, e assim por diante.
3. "produto": Copie o NOME EXATO da linha "Produto:" no [CATÁLOGO]. Não altere nenhuma letra.
4. "codigo": Copie o valor EXATO da linha "sap:" no [CATÁLOGO]. Apenas os dígitos numéricos, sem prefixos como "SAP".
5. "quantidade": Leia ATENTAMENTE o [E-MAIL DO CLIENTE] seguindo estas regras de prioridade:
   a. "10x PRODUTO" ou "10 x PRODUTO" → quantidade é 10
   b. "PRODUTO x10" ou "PRODUTO X10" → quantidade é 10
   c. "10 caixas/unidades/frascos de PRODUTO" → quantidade é 10
   d. ATENÇÃO: sufixos como BLX, BLAX, FRX, CX dentro do nome do produto NÃO são quantidade. Ex: "BLX25" é parte do nome, não indica 25 unidades.
   e. Se não houver nenhuma indicação de quantidade, use 1.
6. "preco_unitario": Valor da linha "preco" no [CATÁLOGO] em formato numérico float. Obrigatório.
7. DUPLICATAS NO CATÁLOGO: O catálogo pode conter o mesmo produto listado mais de uma vez.
   - Nomes idênticos, preços diferentes → escolha o de MAIOR PREÇO, descarte os outros.
   - Nomes idênticos, preços iguais → escolha APENAS O PRIMEIRO que aparecer. Ignore os demais completamente.
   - Em ambos os casos: um único produto pedido = um único item no JSON, independente de quantas linhas ele aparecer no catálogo.

REGRAS PARA "cliente":
1. "tipo": Retorne "FÍSICA" se o remetente for uma Pessoa Física comum. Retorne "JURÍDICA/REVENDEDOR" se o remetente for Pessoa Jurídica (como farmácias, clínicas, revendedores) ou se não for possível determinar com certeza. O padrão é "JURÍDICA/REVENDEDOR".
2. "uf": Busque a sigla de 2 letras do estado no final do e-mail (ex: - SP, - RJ). Se não encontrar, use null.

EXEMPLOS DE USO:

---
[E-MAIL DO CLIENTE]
Boa tarde, preciso de orçamento:
ACICLOVIR 200MG COM BLX25 x10
5x ACHEFLAN CREM BGX30G
Distribuidora Norte
Belém - PA

[CATÁLOGO]
Produto: ACICLOVIR 200MG COM BLX25
preco: R$ 8.50
sap: 1005119
principio_ativo: ACICLOVIR

Produto: ACHEFLAN CREM BGX30G
preco: R$ 45.00
sap: 1001234
principio_ativo: ÁCIDO SALICÍLICO

Produto: ACHEFLAN AER FRX54G
preco: R$ 52.00
sap: 1001235
principio_ativo: ÁCIDO SALICÍLICO

[SAÍDA JSON]
{{"itens": [{{"produto": "ACICLOVIR 200MG COM BLX25", "codigo": "1005119", "quantidade": 10, "preco_unitario": 8.50}}, {{"produto": "ACHEFLAN CREM BGX30G", "codigo": "1001234", "quantidade": 5, "preco_unitario": 45.00}}], "cliente": {{"tipo": "JURÍDICA/REVENDEDOR", "uf": "PA"}}}}
---
[E-MAIL DO CLIENTE]
Olá, preciso de orçamento de alprazolam 0,5MG e angipress 25MG blx30.
Drogaria Popular
Fortaleza - CE

[CATÁLOGO]
Produto: ALPRAZOLAM 0,5MG COM BLX30 (B1)
preco: R$ 7.32
sap: 1005748
principio_ativo: ALPRAZOLAM

Produto: ANGIPRESS 25MG COM BLX30
preco: R$ 24.59
sap: 1006523
principio_ativo: ATENOLOL

Produto: ANGIPRESS 50MG COM BLX30
preco: R$ 59.90
sap: 1006524
principio_ativo: ATENOLOL

[SAÍDA JSON]
{{"itens": [{{"produto": "ALPRAZOLAM 0,5MG COM BLX30 (B1)", "codigo": "1005748", "quantidade": 1, "preco_unitario": 7.32}}, {{"produto": "ANGIPRESS 25MG COM BLX30", "codigo": "1006523", "quantidade": 1, "preco_unitario": 24.59}}], "cliente": {{"tipo": "JURÍDICA/REVENDEDOR", "uf": "CE"}}}}
---
[E-MAIL DO CLIENTE]
Vocês tem o PANTOPRAZOL 40MG? Quero 1 caixa só, por favor.
Ana Júlia - BA

[CATÁLOGO]
Produto: PANTOPRAZOL 40MG CT BL AL
preco: R$ 22.00
sap: 800455
principio_ativo: PANTOPRAZOL

Produto: PANTOPRAZOL 40MG CT BL AL
preco: R$ 25.50
sap: 800456
principio_ativo: PANTOPRAZOL

Produto: PANTOPRAZOL 20MG CT BL AL
preco: R$ 12.00
sap: 800999
principio_ativo: PANTOPRAZOL

[SAÍDA JSON]
{{"itens": [{{"produto": "PANTOPRAZOL 40MG CT BL AL", "codigo": "800456", "quantidade": 1, "preco_unitario": 25.50}}], "cliente": {{"tipo": "FÍSICA", "uf": "BA"}}}}
---
[E-MAIL DO CLIENTE]
ola, preciso de 2x paracet infantil
Drogaria Silva - MG

[CATÁLOGO]
Produto: PARACETAMOL BEBE SUSP FR 15ML
preco: R$ 10.50
sap: 700111
principio_ativo: PARACETAMOL

Produto: PARACETAMOL 750MG CX 20 COMP
preco: R$ 15.00
sap: 700222
principio_ativo: PARACETAMOL

[SAÍDA JSON]
{{"itens": [{{"produto": "PARACETAMOL BEBE SUSP FR 15ML", "codigo": "700111", "quantidade": 2, "preco_unitario": 10.50}}], "cliente": {{"tipo": "JURÍDICA/REVENDEDOR", "uf": "MG"}}}}
---
[E-MAIL DO CLIENTE]
Boa tarde, preciso de AMOXICILINA 875MG COM BLX14 x10.
Distribuidora Farma Centro
Uberlândia - MG

[CATÁLOGO]
Produto: AMOXICILINA 875MG COM BLX14
preco: R$ 97.19
sap: 1005726
principio_ativo: AMOXICILINA TRIIDRATADA

Produto: AMOXICILINA 875MG COM BLX14
preco: R$ 97.19
sap: 1006545
principio_ativo: AMOXICILINA TRIIDRATADA

[SAÍDA JSON]
{{"itens": [{{"produto": "AMOXICILINA 875MG COM BLX14", "codigo": "1005726", "quantidade": 10, "preco_unitario": 97.19}}], "cliente": {{"tipo": "JURÍDICA/REVENDEDOR", "uf": "MG"}}}}
---

[E-MAIL DO CLIENTE]
{pergunta_original}

[CATÁLOGO]
{contexto_produtos}

[SAÍDA JSON]
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
    # Filtra removendo produtos que a IA inventou ou gerou sem preço
    itens_validos = []
    for item in dados_brutos.get("itens", []):
        if "preco_unitario" in item and item["preco_unitario"] > 0:
            itens_validos.append(item)
            
    dados_brutos["itens"] = itens_validos
    
    orcamento = calcular_totais(dados_brutos)

    print(json.dumps(orcamento, ensure_ascii=False, indent=2))
    return orcamento