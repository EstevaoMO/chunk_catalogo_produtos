import os
import json
import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

from utils import achatar_precos, tokenizar_ngrams


DB_PATH = "./.vector_db"
EMBD_MODEL = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2" 
)

def indexar_chunks_json(colecao: chromadb.Collection, pasta_chunks="./chunks") -> None:
    ids, textos, metadados = [], [], []

    for arquivo in os.listdir(pasta_chunks):
        if arquivo.endswith(".json"):
            caminho = os.path.join(pasta_chunks, arquivo)
            with open(caminho, 'r', encoding='utf-8') as f:
                dados_produto = json.load(f)

            nome_produto = dados_produto.get("nome", "Desconhecido")
            principio_ativo = dados_produto.get("principio_ativo", "Desconhecido")
            sap = dados_produto.get("sap", "0")

            precos = dados_produto.get("precos", {})
            metadado = achatar_precos(precos)
            metadado["nome"] = nome_produto
            metadado["sap"] = sap
            metadado["principio_ativo"] = principio_ativo

            # indexando produto por nome
            ids.append(f"{sap}_nome")
            textos.append(nome_produto)
            metadados.append(metadado)

            # indexando produto por princípio ativo
            if principio_ativo and principio_ativo != "Desconhecido":
                ids.append(f"{sap}_pa")
                textos.append(principio_ativo)
                metadados.append(metadado)

    if textos:
        colecao.add(documents=textos, metadatas=metadados, ids=ids)
        print(f"{len(ids)} produtos indexados com sucesso!")


def obter_colecao(bateria_teste=False) -> chromadb.Collection:
    """Retorna a coleção existente ou cria uma nova se necessário."""
    cliente = chromadb.PersistentClient(path=DB_PATH)
    
    colecoes_existentes = [c.name for c in cliente.list_collections()]
    banco_existe = "catalogo_produtos" in colecoes_existentes

    if banco_existe and not bateria_teste:
        sobrescrever = input("Banco vetorial já existe. Deseja sobrescrever? (y/N): ").strip().lower()
        if sobrescrever == "y":
            cliente.delete_collection("catalogo_produtos")
            print("Banco anterior removido.")
            banco_existe = False

    if not banco_existe:
        colecao = cliente.create_collection(
            name="catalogo_produtos",
            embedding_function=EMBD_MODEL
        )
        indexar_chunks_json(colecao)
    else:
        colecao = cliente.get_collection(
            name="catalogo_produtos",
            embedding_function=EMBD_MODEL
        )
        print("Banco vetorial carregado do disco.")

    return colecao

def obter_bm25(pasta_chunks="./chunks"):
    """
    Lê os chunks e cria um índice BM25 em memória para busca léxica rápida.
    Retorna o objeto BM25 e uma lista com os metadados (catálogo) na mesma ordem.
    """
    catalogo_meta = []
    textos_para_indexar = []
    
    for arquivo in os.listdir(pasta_chunks):
        if arquivo.endswith(".json"):
            caminho = os.path.join(pasta_chunks, arquivo)
            with open(caminho, 'r', encoding='utf-8') as f:
                dados_produto = json.load(f)
                
            nome_produto = dados_produto.get("nome", "")
            principio_ativo = dados_produto.get("principio_ativo", "")
            sap = dados_produto.get("sap", "0")
            precos = dados_produto.get("precos", {})
            
            # Montamos o texto de busca para o BM25 (Nome + Princípio)
            texto_busca = f"{nome_produto} {principio_ativo}"
            textos_para_indexar.append(texto_busca)
            
            # Guardamos os metadados na mesma posição do índice
            meta = achatar_precos(precos)
            meta["nome"] = nome_produto
            meta["sap"] = sap
            meta["principio_ativo"] = principio_ativo
            catalogo_meta.append(meta)
            
    # Tokeniza tudo e cria o motor
    corpus_tokenizado = [tokenizar_ngrams(texto) for texto in textos_para_indexar]
    bm25 = BM25Okapi(corpus_tokenizado)
    
    print("Índice BM25 carregado em memória.")
    return bm25, catalogo_meta