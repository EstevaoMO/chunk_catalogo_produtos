import json

import pandas as pd
from datetime import datetime
from pathlib import Path
from gerar_chunks import gerar_chunk
from utils import normalizar_notacao
from db import obter_colecao, obter_bm25

def main() -> None:
    email_cliente = \
    """
        Olá, gostaria de receber um orçamento dos seguintes produtos:

        10x ACICLOVIR 200MG COM BLX25
        10x ALENIA 12/400MCG POINAL CAP FRX60+INAL
        10x BIOMAG 15MG CAP BLX30 (B2)

        At.te,
        José Pedidor
        JoseFarmacia - Rio de Janeiro - RJ
    """
    

    # Criando os chunks normalizados a partir do CSV
    df = pd.read_csv("https://raw.githubusercontent.com/alvaroriz/datascience_datasets/refs/heads/main/Catalogo-Produtos.csv", dtype={'CÓDIGO SAP': str, 'CÓDIGO EAN': str}, sep=";")
    
    colunas_para_normalizar = [
        "CÓDIGO SAP",
        "CÓDIGO EAN",
        "REGISTRO MS"
    ]
    df_normalizado = normalizar_notacao(df, colunas_para_normalizar)
    df_normalizado.apply(gerar_chunk, axis=1)

    # Iniciando o banco vetorial e indexando os chunks
    con_db = obter_colecao()
    # Iniciando BM25
    bm25, catalogo_bm25 = obter_bm25()

    # Gerando respostas
    from gerar_resposta import gerar_prompt_final, gerar_contexto_geral, gerar_resposta

    contexto = gerar_contexto_geral(email_cliente, colecao=con_db, bm25=bm25, catalogo_bm25=catalogo_bm25)
    prompt_final = gerar_prompt_final(contexto, email_cliente)
    print('PROMPT FINAL:')
    print(prompt_final)
    resposta = gerar_resposta(prompt_final)

    respostas_dir = Path("./chunks")
    respostas_dir.mkdir(exist_ok=True)
    with open(f"./resultados/res_{str(datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))}.json", "w", encoding="utf-8") as f:
        f.write((json.dumps(resposta, ensure_ascii=False, indent=2)))


if __name__ == "__main__":
    main()