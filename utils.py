import pandas as pd


def calcular_totais(dados_brutos: dict) -> dict:
    """Calcula os totais dos itens do orçamento."""
    itens_completos = []
    for item in dados_brutos.get("itens", []):
        preco_unitario = float(item.get("preco_unitario", 0.0))
         
        if isinstance(item.get("quantidade", 1), str):
            quantidade = int(item.get("quantidade", 1).replace("x", "").strip())
        else:
            quantidade = int(item.get("quantidade", 1))

        item["preco_total"] = round(preco_unitario * quantidade, 2)
        itens_completos.append(item)

    total_geral = round(sum(i["preco_total"] for i in itens_completos), 2)

    return {
        "itens": itens_completos,
        "cliente": dados_brutos.get("cliente", {}),
        "total": total_geral
    }

def achatar_precos(precos: dict) -> dict:
    """Converte o dict aninhado de preços em chaves planas para o ChromaDB."""
    metadado_precos = {}
    for icms, valores in precos.items():
        for tipo, valor_str in valores.items():
            chave = f"preco_{icms}_{tipo}"
            try:
                valor_float = float(valor_str.replace(",", "."))
            except (ValueError, AttributeError):
                valor_float = 0.0
            metadado_precos[chave] = valor_float
    return metadado_precos

def normalizar_notacao(df, colunas_para_normalizar) -> pd.DataFrame:
    """
    Normaliza algumas colunas que estão em notação científica, convertendo-as para o formato numérico padrão.
    """

    for coluna in colunas_para_normalizar:
        df[coluna] = df[coluna].apply(lambda x: x.replace(',', '.'))
        df[coluna] = df[coluna].apply(lambda x: f"{float(x):.0f}" if not ("-" in x or "ISENTO" in x) else x)
    
    return df

def tokenizar_ngrams(texto: str, n: int = 3) -> list:
    """Quebra o texto em n-grams e palavras inteiras para o BM25."""
    texto = str(texto).lower()
    if len(texto) < n:
        return [texto]
    
    tokens = []
    # Pedaços de 3 letras
    for i in range(len(texto) - n + 1):
        tokens.append(texto[i:i+n])
    
    # Palavras inteiras
    tokens.extend(texto.split())
    return tokens