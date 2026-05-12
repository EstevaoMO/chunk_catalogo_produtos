import pandas as pd

def normalizar_notacao(df, colunas_para_normalizar) -> pd.DataFrame:
    """
    Normaliza algumas colunas que estão em notação científica, convertendo-as para o formato numérico padrão.
    """

    for coluna in colunas_para_normalizar:
        df[coluna] = df[coluna].apply(lambda x: x.replace(',', '.'))
        df[coluna] = df[coluna].apply(lambda x: f"{float(x):.0f}" if not ("-" in x or "ISENTO" in x) else x)
    
    return df


def gerar_chunk(row) -> None:
    """
    Gera um arquivo JSON para cada linha do DataFrame, contendo as informações do medicamento de acordo com a estrutura definida.
    """

    chunk = {
        "sap": row["CÓDIGO SAP"],
        "nome": row["APRESENTAÇÃO"],
        "principio_ativo": row["PRINCIPIO ATIVO"],
        "familia": row["FAMÍLIA"],
        "ncm": row["NCM (CLASS FISCAL)"],
        "tipo": row["TIPO DE MEDICAMENTO"],
        "tarja": row["TARJA"],
        "qtde": row["QTDE"],
        "precos": {
            "icms_0":   { "pf": row["ICMS 0 % (PF)"], "pmc": row["ICMS 0 % (PMC)"] },
            "icms_12":  { "pf": row["ICMS 12 %  (PF)"], "pmc": row["ICMS 12 % (PMC) "] },
            "icms_17":  { "pf": row["ICMS 17 % (PF)"], "pmc": row["ICMS 17 % (PMC)"] },
            "icms_175": { "pf": row["ICMS 17,5 % (PF)"], "pmc": row["ICMS 17,5 % (PMC)"] },
            "icms_18":  { "pf": row["ICMS 18 %  (PF)"], "pmc": row["ICMS 18 %  (PMC)"] },
            "icms_20":  { "pf": row["ICMS 20 % (PF)"], "pmc": row["ICMS 20 % (PMC)"] },
            "icms_17_ac_rr": { "pf": row["ICMS 17 % (ALC) AC/RR (PF)"], "pmc": row["ICMS 17 % (ALC) AC/RR (PMC)"] },
            "icms_175_ro":   { "pf": row["ICMS 17,5 % (ALC) RO (PF)"],   "pmc": row["ICMS 17,5 % (ALC) RO (PMC)"] },
            "icms_18_am_ap": { "pf": row["ICMS 18 % (ALC) AM/AP (PF)"],   "pmc": row["ICMS 18 % (ALC) AM/AP (PMC)"] }
        },
        "ean": str(row["CÓDIGO EAN"]),
        "registro_ms": str(row["REGISTRO MS"])
    }
    
    with open(f"./chunks/chunk_{str(row['CÓDIGO SAP']).strip()}-{str(row['CÓDIGO EAN']).strip()}.json", "w") as f:
        import json
        json.dump(chunk, f, ensure_ascii=False, indent=2)


def main() -> None:
    df = pd.read_csv("https://raw.githubusercontent.com/alvaroriz/datascience_datasets/refs/heads/main/Catalogo-Produtos.csv", dtype={'CÓDIGO SAP': str, 'CÓDIGO EAN': str}, sep=";")
    
    colunas_para_normalizar = [
        "CÓDIGO SAP",
        "CÓDIGO EAN",
        "REGISTRO MS"
    ]
    df_normalizado = normalizar_notacao(df, colunas_para_normalizar)

    df_normalizado.apply(gerar_chunk, axis=1)


if __name__ == "__main__":
    main()