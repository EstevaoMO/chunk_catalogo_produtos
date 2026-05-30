from fastapi import FastAPI
from pydantic import BaseModel
from db import obter_colecao, obter_bm25
from gerar_resposta import gerar_contexto_geral, gerar_prompt_final, gerar_resposta
import json
import os

app = FastAPI()

colecao = None
bm25 = None
catalogo_bm25 = None

@app.on_event("startup")
def startup():
    global colecao, bm25, catalogo_bm25

    colecao = obter_colecao()
    bm25, catalogo_bm25 = obter_bm25()

class EmailInput(BaseModel):
    email: str
    salvar: bool = True

@app.post("/processar")
def processar(payload: EmailInput):
    ctx = gerar_contexto_geral(
        payload.email,
        colecao,
        bm25,
        catalogo_bm25
    )

    prompt = gerar_prompt_final(ctx, payload.email)
    orcamento = gerar_resposta(prompt)

    if payload.salvar:
        os.makedirs("resultados", exist_ok=True)

        with open(
            f"resultados/orcamento_{hash(payload.email)}.json",
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                orcamento,
                f,
                ensure_ascii=False,
                indent=2
            )

    return orcamento

@app.get("/health")
def health():
    return {"status": "ok"}