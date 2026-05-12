import os
import json
import chromadb
from chromadb.utils import embedding_functions

from utils import achatar_precos


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
            texto_busca = f"Produto: {nome_produto}"

            precos = dados_produto.get("precos", {})
            metadado = achatar_precos(precos)
            metadado["nome"] = nome_produto

            ids.append(arquivo)
            textos.append(texto_busca)
            metadados.append(metadado)

    if textos:
        colecao.add(documents=textos, metadatas=metadados, ids=ids)
        print(f"{len(ids)} produtos indexados com sucesso!")


def obter_colecao() -> chromadb.Collection:
    """Retorna a coleção existente ou cria uma nova se necessário."""
    cliente = chromadb.PersistentClient(path=DB_PATH)
    
    colecoes_existentes = [c.name for c in cliente.list_collections()]
    banco_existe = "catalogo_produtos" in colecoes_existentes

    if banco_existe:
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