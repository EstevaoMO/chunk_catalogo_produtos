"""
Bateria de testes para o sistema RAG de orçamentos de farmácia.

Cada teste simula um e-mail real de cliente e cobre um tipo de busca por vez:
  - Nome comercial do produto
  - Código SAP do produto
  - Princípio ativo
  - Abreviações / nomes parciais
  - Quantidades variadas
  - Textos informais

Execução:
    python -m pytest bateria_testes.py -v
    ou
    python bateria_testes.py

Resultados de cada teste são salvos automaticamente em:
    ./resultados_testes/<grupo>/<nome_do_teste>.json
"""

import inspect
import json
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Setup compartilhado (carrega o banco vetorial uma vez para toda a suite)
# ---------------------------------------------------------------------------

from gerar_chunks import gerar_chunk
from utils import normalizar_notacao
from db import obter_colecao, obter_bm25
from gerar_resposta import gerar_contexto_geral, gerar_prompt_final, gerar_resposta


# Diretório raiz onde os resultados dos testes serão salvos
RESULTADO_DIR = Path("./resultados_testes")


def _setup_colecao():
    df = pd.read_csv(
        "Catalogo-Produtos.csv",
        dtype={"CÓDIGO SAP": str, "CÓDIGO EAN": str},
        sep=";",
    )
    colunas_para_normalizar = ["CÓDIGO SAP", "CÓDIGO EAN", "REGISTRO MS"]
    df_normalizado = normalizar_notacao(df, colunas_para_normalizar)
    df_normalizado.apply(gerar_chunk, axis=1)
    con_chroma = obter_colecao(bateria_teste=True)
    bm25, catalogo_bm25 = obter_bm25()
    return con_chroma, bm25, catalogo_bm25


# Instância global — criada uma única vez durante a session do pytest
_COLECAO = _BM25 = _CATALOGO_BM25 = None

def get_colecao():
    global _COLECAO, _BM25, _CATALOGO_BM25
    if _COLECAO is None and _BM25 is None and _CATALOGO_BM25 is None:
        _COLECAO, _BM25, _CATALOGO_BM25 = _setup_colecao()
    return _COLECAO, _BM25, _CATALOGO_BM25


# ---------------------------------------------------------------------------
# Salvamento semântico de resultados
# ---------------------------------------------------------------------------

def _nome_teste_atual() -> tuple[str, str]:
    """
    Sobe a pilha de chamadas para encontrar o método de teste em execução.
    Retorna (nome_da_classe, nome_do_metodo).
    """
    for frame_info in inspect.stack():
        nome = frame_info.function
        frame_locals = frame_info.frame.f_locals
        if nome.startswith("test_") and "self" in frame_locals:
            classe = type(frame_locals["self"]).__name__
            return classe, nome
    return "SemClasse", "sem_nome"


def salvar_resultado(orcamento: dict, email: str, passou: bool, erro: str = "") -> Path:
    """
    Salva o orçamento gerado pelo modelo em um arquivo JSON semanticamente nomeado.

    Estrutura do arquivo salvo:
        ./resultados_testes/<NomeClasse>/<nome_do_teste>__<YYYYMMDD_HHMMSS>.json

    O envelope inclui:
        - teste:     grupo e nome do teste
        - status:    "PASSOU" ou "FALHOU"
        - erro:      mensagem de erro, se houver
        - email:     e-mail de entrada (para auditoria)
        - timestamp: momento da execução
        - orcamento: resposta completa do modelo
    """
    classe, metodo = _nome_teste_atual()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    pasta = RESULTADO_DIR / classe
    pasta.mkdir(parents=True, exist_ok=True)

    nome_arquivo = f"{metodo}__{ts}.json"
    caminho = pasta / nome_arquivo

    envelope = {
        "teste": {
            "grupo": classe,
            "nome": metodo,
        },
        "status": "PASSOU" if passou else "FALHOU",
        "erro": erro,
        "timestamp": datetime.now().isoformat(),
        "email_entrada": email.strip(),
        "orcamento": orcamento,
    }

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)

    return caminho


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rodar_pipeline(email: str) -> dict:
    """Executa o pipeline completo e retorna o orçamento estruturado."""
    colecao, bm25, catalogo_25 = get_colecao()
    contexto = gerar_contexto_geral(email, colecao=colecao, bm25=bm25, catalogo_bm25=catalogo_25)
    prompt = gerar_prompt_final(contexto, email)
    return gerar_resposta(prompt)


def rodar_e_salvar(email: str) -> dict:
    """
    Executa o pipeline e salva o resultado automaticamente.
    Em caso de exceção no pipeline, salva o erro e re-lança para o pytest.
    """
    try:
        orcamento = rodar_pipeline(email)
        # Resultado provisório como PASSOU; o assert do teste pode mudar isso
        # O salvamento final (com status correto) é feito por cada teste via
        # `salvar_resultado()` após suas asserções.
        return orcamento
    except Exception as exc:
        salvar_resultado({}, email, passou=False, erro=str(exc))
        raise


def extrair_nomes_produtos(orcamento: dict) -> list[str]:
    return [item["produto"].upper() for item in orcamento.get("itens", [])]


def extrair_codigos(orcamento: dict) -> list[str]:
    return [str(item["codigo"]) for item in orcamento.get("itens", [])]


def extrair_quantidades(orcamento: dict) -> dict[str, int]:
    return {
        item["produto"].upper(): int(item["quantidade"])
        for item in orcamento.get("itens", [])
    }


def _executar_com_salvamento(email: str, corpo_teste):
    """
    Padrão reutilizável: roda o pipeline, executa as asserções de `corpo_teste`
    e salva o resultado com o status correto independentemente do desfecho.

    `corpo_teste` deve ser um callable que recebe o orçamento e faz os asserts.
    """
    orcamento = {}
    try:
        orcamento = rodar_pipeline(email)
        corpo_teste(orcamento)
        salvar_resultado(orcamento, email, passou=True)
    except AssertionError as exc:
        salvar_resultado(orcamento, email, passou=False, erro=str(exc))
        raise
    except Exception as exc:
        salvar_resultado(orcamento, email, passou=False, erro=str(exc))
        raise


# ===========================================================================
# GRUPO 1 — NOME COMERCIAL DO PRODUTO
# ===========================================================================

class TestNomeComercial:
    """Pedidos feitos usando o nome comercial/marca do produto."""

    def test_nome_comercial_accuvit(self):
        """Busca pelo nome de marca ACCUVIT."""
        email = """
        Bom dia,

        Preciso de um orçamento para o produto ACCUVIT COMREV FRX30.

        Att,
        Distribuidora Saúde Total
        São Paulo - SP
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACCUVIT" in n for n in nomes), f"ACCUVIT não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_nome_comercial_acheflan_aerossol(self):
        """Busca pelo nome de marca ACHEFLAN na forma aerossol."""
        email = """
        Olá, equipe de vendas!

        Gostaríamos de receber cotação para:
        ACHEFLAN AER FRX54G

        Grato,
        Farmácia Boa Saúde
        Belo Horizonte - MG
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACHEFLAN" in n for n in nomes), f"ACHEFLAN não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_nome_comercial_adipept(self):
        """Busca pelo nome de marca ADIPEPT 20MG."""
        email = """
        Prezados,

        Solicito cotação do medicamento ADIPEPT 20MG COMR BLAX28.

        Atenciosamente,
        Drogaria Moderna
        Curitiba - PR
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ADIPEPT" in n for n in nomes), f"ADIPEPT não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_nome_comercial_vertix(self):
        """Busca pelo nome de marca VERTIX comprimidos."""
        email = """
        Boa tarde,

        Por favor, preciso de um orçamento para VERTIX 10MG COM 2BLX25.

        Obrigado,
        Farmácia Central
        Porto Alegre - RS
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("VERTIX" in n for n in nomes), f"VERTIX não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_nome_comercial_zyad(self):
        """Busca pelo nome de marca ZYAD 20MG."""
        email = """
        Olá,

        Gostaria de receber orçamento de ZYAD 20MG COMR BLX4.

        Att,
        Drogaria Vida e Saúde
        Florianópolis - SC
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ZYAD" in n for n in nomes), f"ZYAD não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_nome_comercial_zirk(self):
        """Busca pelo nome de marca ZIRK 500MG."""
        email = """
        Prezados,

        Solicito orçamento para ZIRK 500MG COM REV CT BL X 5.

        Atenciosamente,
        Farmácias Reunidas Ltda
        Salvador - BA
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ZIRK" in n for n in nomes), f"ZIRK não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_nome_comercial_vidmax(self):
        """Busca pelo nome de marca VIDMAX 50MG."""
        email = """
        Bom dia,

        Pode me passar o preço do VIDMAX 50MG COMR BLAX60?

        Grato,
        Drogaria Esperança
        Fortaleza - CE
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("VIDMAX" in n for n in nomes), f"VIDMAX não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_nome_comercial_vita_e(self):
        """Busca pelo nome de marca VITA E cápsulas."""
        email = """
        Olá,

        Preciso cotar VITA E CAP FRX30 para nossa farmácia.

        Obrigado,
        Drogaria Familiar
        Manaus - AM
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("VITA" in n for n in nomes), f"VITA E não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)


# ===========================================================================
# GRUPO 2 — CÓDIGO SAP DO PRODUTO
# ===========================================================================

class TestCodigoSAP:
    """Pedidos feitos usando o código SAP do produto."""

    def test_codigo_sap_aciclovir_comprimido(self):
        """Busca pelo código SAP 1005119 (ACICLOVIR 200MG COM BLX25)."""
        email = """
        Olá,

        Gostaria de um orçamento para o produto de código SAP 1005119.

        Att,
        Drogaria Norte
        Belém - PA
        """
        def _asserts(orcamento):
            codigos = extrair_codigos(orcamento)
            produto = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert "1005119" in codigos and any("ACICLOVIR" in n for n in produto), f"Código 1005119 não encontrado em {codigos}"
        _executar_com_salvamento(email, _asserts)

    def test_codigo_sap_albendazol_comprimido(self):
        """Busca pelo código SAP 1005748 (ALBENDAZOL 400MG COMM BLX1)."""
        email = """
        Boa tarde,

        Por favor, cotar o item SAP 1005748.

        Grato,
        Farmácia do Povo
        Recife - PE
        """
        def _asserts(orcamento):
            codigos = extrair_codigos(orcamento)
            produto = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert "1005748" in codigos and any("ALBENDAZOL" in n for n in produto), f"Código 1005748 não encontrado em {codigos}"
        _executar_com_salvamento(email, _asserts)

    def test_codigo_sap_alendronato(self):
        """Busca pelo código SAP 1002506 (ALENDRONATO SODIO 70MG COM BLAX4)."""
        email = """
        Prezados,

        Cotação do código 1002506, por favor.

        Atenciosamente,
        Drogaria São Lucas
        Goiânia - GO
        """
        def _asserts(orcamento):
            codigos = extrair_codigos(orcamento)
            produto = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert "1002506" in codigos and any("ALENDRONATO" in n for n in produto), f"Código 1002506 não encontrado em {codigos}"
        _executar_com_salvamento(email, _asserts)

    def test_codigo_sap_adipept_40mg(self):
        """Busca pelo código SAP 1003799 (ADIPEPT 40MG COMR BLAX28)."""
        email = """
        Bom dia,

        Preciso do preço do SAP 1003799.

        Obrigado,
        Distribuidora Pharma Sul
        Porto Alegre - RS
        """
        def _asserts(orcamento):
            codigos = extrair_codigos(orcamento)
            produto = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert "1003799" in codigos and any("ADIPEPT" in n for n in produto), f"Código 1003799 não encontrado em {codigos}"
        _executar_com_salvamento(email, _asserts)

    def test_codigo_sap_zargus(self):
        """Busca pelo código SAP 1006335 (ZARGUS 1MG COMR BLX30)."""
        email = """
        Olá,

        Solicito cotação para o produto código 1006335.

        Att,
        Rede Farmácias Capital
        Brasília - DF
        """
        def _asserts(orcamento):
            codigos = extrair_codigos(orcamento)
            produto = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert "1006335" in codigos and any("ZARGUS" in n for n in produto), f"Código 1006335 não encontrado em {codigos}"
        _executar_com_salvamento(email, _asserts)

    def test_codigo_sap_verapamil(self):
        """Busca pelo código SAP 1000647 (CL VERAPAMIL 80MG 2BLX15)."""
        email = """
        Prezados,

        Gostaria de orçar o SAP 1000647.

        Att,
        Farmácia Bom Preço
        Natal - RN
        """
        def _asserts(orcamento):
            codigos = extrair_codigos(orcamento)
            produto = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert "1000647" in codigos and any("CL VERAPAMIL" in n for n in produto), f"Código 1000647 não encontrado em {codigos}"
        _executar_com_salvamento(email, _asserts)

    def test_codigo_sap_venlafaxina(self):
        """Busca pelo código SAP 1000603 (CLOR VENLAFAXINA 75MG BLX28)."""
        email = """
        Bom dia equipe,

        Preciso da cotação do produto SAP 1000603.

        Grato,
        Farmácias Unidas Ltda
        São Luís - MA
        """
        def _asserts(orcamento):
            codigos = extrair_codigos(orcamento)
            produto = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert "1000603" in codigos and any("CLOR VENLAFAXINA" in n for n in produto), f"Código 1000603 não encontrado em {codigos}"
        _executar_com_salvamento(email, _asserts)


# ===========================================================================
# GRUPO 3 — PRINCÍPIO ATIVO
# ===========================================================================

class TestPrincipioAtivo:
    """Pedidos feitos usando o princípio ativo do medicamento."""

    def test_principio_ativo_aciclovir(self):
        """Busca pelo princípio ativo ACICLOVIR."""
        email = """
        Olá,

        Preciso de um orçamento para aciclovir 200mg comprimido, blister com 25.

        Att,
        Drogaria Popular
        Rio de Janeiro - RJ
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACICLOVIR" in n for n in nomes), f"Aciclovir não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_principio_ativo_albendazol(self):
        """Busca pelo princípio ativo ALBENDAZOL."""
        email = """
        Boa tarde,

        Gostaria de cotar albendazol 400mg comprimido mastigável.

        Grato,
        Farmácia Central
        João Pessoa - PB
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ALBENDAZOL" in n for n in nomes), f"Albendazol não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_principio_ativo_alendronato_sodio(self):
        """Busca pelo princípio ativo ALENDRONATO DE SÓDIO."""
        email = """
        Prezados,

        Solicito orçamento para alendronato de sódio 70mg, blister com 4 comprimidos.

        Atenciosamente,
        Drogaria Bem Estar
        Cuiabá - MT
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ALENDRONATO" in n for n in nomes), f"Alendronato não encontrado em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_principio_ativo_acebrofilina(self):
        """Busca pelo princípio ativo ACEBROFILINA."""
        email = """
        Olá,

        Preciso de orçamento para acebrofilina xarope 25mg/5ml, frasco 120ml.

        Obrigado,
        Distribuidora Nordeste
        Teresina - PI
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACEBROFILINA" in n for n in nomes), f"Acebrofilina não encontrada em {nomes}"
        _executar_com_salvamento(email, _asserts)

    def test_principio_ativo_pantoprazol(self):
        """Busca pelo princípio ativo PANTOPRAZOL."""
        email = """
        Bom dia,

        Gostaria de cotar pantoprazol 40mg comprimido revestido, blister com 28 unidades.

        Att,
        Farmácia Saúde e Vida
        Campo Grande - MS
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ADIPEPT" in n or "PANTOPRAZOL" in n for n in nomes), (
                f"Pantoprazol/Adipept não encontrado em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_principio_ativo_azitromicina(self):
        """Busca pelo princípio ativo AZITROMICINA."""
        email = """
        Prezados,

        Preciso de cotação para azitromicina di-hidratada 500mg, blister com 5 comprimidos.

        Grato,
        Drogaria Saúde Total
        Maceió - AL
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ZIRK" in n or "AZITROMICINA" in n for n in nomes), (
                f"Azitromicina/Zirk não encontrado em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_principio_ativo_risperidona(self):
        """Busca pelo princípio ativo RISPERIDONA."""
        email = """
        Olá,

        Gostaria de um orçamento para risperidona 1mg comprimido revestido, caixa blister x30.

        Att,
        Farmácia Rede Sul
        Porto Alegre - RS
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ZARGUS" in n or "RISPERIDONA" in n for n in nomes), (
                f"Risperidona/Zargus não encontrado em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_principio_ativo_topiramato(self):
        """Busca pelo princípio ativo TOPIRAMATO."""
        email = """
        Boa tarde,

        Solicito orçamento para topiramato 50mg comprimido revestido, caixa blister x60.

        Atenciosamente,
        Distribuidora Farma Nordeste
        Aracaju - SE
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("VIDMAX" in n or "TOPIRAMATO" in n for n in nomes), (
                f"Topiramato/Vidmax não encontrado em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)


# ===========================================================================
# GRUPO 4 — ABREVIAÇÕES / NOMES PARCIAIS
# ===========================================================================

class TestAbreviacoes:
    """Pedidos com abreviações, siglas ou nomes parciais dos produtos."""

    def test_abreviacao_aciclo_creme(self):
        """Abreviação: 'aciclo creme 50mg' em vez do nome completo."""
        email = """
        Oi,

        Me manda o preço do aciclo creme 50mg bisnaga 10g.

        Obrigado,
        Farmácia do Bairro
        Vitória - ES
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACICLOVIR" in n for n in nomes), (
                f"Aciclovir (creme) não encontrado com abreviação 'aciclo' em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_abreviacao_acetilcis_xarope(self):
        """Abreviação: 'acetilcis' para acetilcisteína."""
        email = """
        Boa tarde,

        Preciso de orçamento de acetilcis 20mg xarope frasco 120ml.

        Att,
        Drogaria Boa Vista
        Boa Vista - RR
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACETILCISTEINA" in n for n in nomes), (
                f"Acetilcisteína não encontrada com abreviação 'acetilcis' em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_abreviacao_alend_70mg(self):
        """Abreviação: 'alend 70mg' para alendronato de sódio."""
        email = """
        Prezados,

        Cotação para alend 70mg, blister x4.

        Grato,
        Farmácia da Praça
        Macapá - AP
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ALENDRONATO" in n for n in nomes), (
                f"Alendronato não encontrado com abreviação 'alend' em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_abreviacao_achef_aer(self):
        """Abreviação: 'achef aerossol' para Acheflan aerossol."""
        email = """
        Olá,

        Preciso do preço do achef aerossol 54g.

        Att,
        Distribuidora Farma Leste
        Salvador - BA
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACHEFLAN" in n for n in nomes), (
                f"Acheflan não encontrado com abreviação 'achef aer' em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_abreviacao_venlaf_75(self):
        """Abreviação: 'venlaf 75' para cloridrato de venlafaxina 75mg."""
        email = """
        Bom dia,

        Orçamento de venlaf 75, blister com 28 comprimidos, por favor.

        Obrigado,
        Rede Farmácia Nordeste
        Fortaleza - CE
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("VENLAFAXINA" in n for n in nomes), (
                f"Venlafaxina não encontrada com abreviação 'venlaf' em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_abreviacao_verap_80(self):
        """Abreviação: 'verap 80mg' para cloridrato de verapamil 80mg."""
        email = """
        Boa tarde,

        Cotação verap 80mg, 2 blisters x15, por favor.

        Att,
        Farmácia Pague Menos Filial
        Belém - PA
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("VERAPAMIL" in n for n in nomes), (
                f"Verapamil não encontrado com abreviação 'verap' em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_abreviacao_alben_susp(self):
        """Abreviação: 'alben 40mg/ml susp' para albendazol suspensão."""
        email = """
        Olá equipe,

        Quero cotar alben 40mg/ml susp, frasco 10ml.

        Grato,
        Farmácia Central Filial 3
        Porto Velho - RO
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ALBENDAZOL" in n for n in nomes), (
                f"Albendazol não encontrado com abreviação 'alben susp' em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)


# ===========================================================================
# GRUPO 5 — QUANTIDADES VARIADAS
# ===========================================================================

class TestQuantidades:
    """Pedidos com diferentes formatos e volumes de quantidade."""

    def test_quantidade_numero_escrito_por_extenso(self):
        """Quantidade informada por extenso: 'cinco caixas'."""
        email = """
        Olá,

        Preciso de cinco caixas do ACHEFLAN CREM BGX30G.

        Att,
        Drogaria Saúde em Dia
        Campinas - SP
        """
        def _asserts(orcamento):
            qtds = extrair_quantidades(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            produto_chave = next((k for k in qtds if "ACHEFLAN" in k), None)
            assert produto_chave, f"Produto Acheflan não encontrado em {qtds}"
            assert qtds[produto_chave] == 5, f"Quantidade esperada 5, obtida {qtds[produto_chave]}"
        _executar_com_salvamento(email, _asserts)

    def test_quantidade_formato_xN(self):
        """Quantidade no formato 'x10' após o nome do produto."""
        email = """
        Boa tarde,

        Orçamento de ACICLOVIR 200MG COM BLX25 x10, por favor.

        Grato,
        Distribuidora Farma Centro
        Uberlândia - MG
        """
        def _asserts(orcamento):
            qtds = extrair_quantidades(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            produto_chave = next((k for k in qtds if "ACICLOVIR" in k), None)
            assert produto_chave, f"Produto Aciclovir não encontrado em {qtds}"
            assert qtds[produto_chave] == 10, f"Quantidade esperada 10, obtida {qtds[produto_chave]}"
        _executar_com_salvamento(email, _asserts)

    def test_quantidade_formato_Nx(self):
        """Quantidade no formato 'Nx' antes do nome do produto."""
        email = """
        Prezados,

        Preciso de 20x ALBENDAZOL 400MG COMM BLX1 CL.

        Atenciosamente,
        Drogaria Mega Saúde
        Ribeirão Preto - SP
        """
        def _asserts(orcamento):
            qtds = extrair_quantidades(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            produto_chave = next((k for k in qtds if "ALBENDAZOL" in k), None)
            assert produto_chave, f"Albendazol não encontrado em {qtds}"
            # O modelo pode duplicar o item; considera a maior quantidade retornada
            max_qtd = max(
                int(item["quantidade"])
                for item in orcamento["itens"]
                if "ALBENDAZOL" in item["produto"].upper()
            )
            assert max_qtd == 20, f"Quantidade esperada 20, maior obtida {max_qtd}"
        _executar_com_salvamento(email, _asserts)

    def test_quantidade_omitida_default_1(self):
        """Quantidade não informada — deve assumir 1 por padrão."""
        email = """
        Olá,

        Gostaria do preço de ADIPEPT 20MG COMR BLAX14.

        Obrigado,
        Farmácia Nova Esperança
        Londrina - PR
        """
        def _asserts(orcamento):
            qtds = extrair_quantidades(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            produto_chave = next((k for k in qtds if "ADIPEPT" in k), None)
            assert produto_chave, f"Adipept não encontrado em {qtds}"
            assert qtds[produto_chave] == 1, f"Quantidade padrão deveria ser 1, obtida {qtds[produto_chave]}"
        _executar_com_salvamento(email, _asserts)

    def test_quantidade_alta_volume(self):
        """Pedido de alto volume: 100 unidades."""
        email = """
        Bom dia,

        Preciso cotar 100 unidades do ZIRK 500MG COM REV CT BL X 5.

        Att,
        Rede Hospitalar São José
        São Paulo - SP
        """
        def _asserts(orcamento):
            qtds = extrair_quantidades(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            produto_chave = next((k for k in qtds if "ZIRK" in k), None)
            assert produto_chave, f"Zirk não encontrado em {qtds}"
            assert qtds[produto_chave] == 100, f"Quantidade esperada 100, obtida {qtds[produto_chave]}"
        _executar_com_salvamento(email, _asserts)

    def test_quantidade_formato_unidades_abreviado(self):
        """Quantidade no formato '50 un.'."""
        email = """
        Boa tarde,

        Solicito orçamento de ALENDRONATO SODIO 70MG COM BLAX4 - 50 un.

        Grato,
        Drogaria Popular Filial 2
        Recife - PE
        """
        def _asserts(orcamento):
            qtds = extrair_quantidades(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            produto_chave = next((k for k in qtds if "ALENDRONATO" in k), None)
            assert produto_chave, f"Alendronato não encontrado em {qtds}"
            assert qtds[produto_chave] == 50, f"Quantidade esperada 50, obtida {qtds[produto_chave]}"
        _executar_com_salvamento(email, _asserts)

    def test_quantidade_uma_unidade_escrita(self):
        """Quantidade 'uma caixa' — forma escrita do numeral 1."""
        email = """
        Olá,

        Preciso de uma caixa do ACHEFLAN CREM BGX60G.

        Att,
        Farmácia Modelo
        Joinville - SC
        """
        def _asserts(orcamento):
            qtds = extrair_quantidades(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            produto_chave = next((k for k in qtds if "ACHEFLAN" in k), None)
            assert produto_chave, f"Acheflan não encontrado em {qtds}"
            assert qtds[produto_chave] == 1, f"Quantidade esperada 1, obtida {qtds[produto_chave]}"
        _executar_com_salvamento(email, _asserts)


# ===========================================================================
# GRUPO 6 — TEXTOS INFORMAIS
# ===========================================================================

class TestTextosInformais:
    """E-mails com linguagem informal, erros de digitação ou estrutura livre."""

    def test_informal_sem_saudacao(self):
        """E-mail direto sem saudação ou assinatura formal."""
        email = """
        quero cotar accuvit frx30 pra nossa farmacia

        obrigado
        Farmácia do Zé
        São Paulo - SP
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACCUVIT" in n for n in nomes), (
                f"ACCUVIT não encontrado em pedido informal em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_informal_com_erros_ortograficos_leve(self):
        """E-mail com erro ortográfico leve: 'aciclovil' em vez de 'aciclovir'."""
        email = """
        Boa tarde!

        Queria cotar o aciclovil 200mg comprimido, blister de 25.

        Valeu,
        Drogaria Fast
        Campinas - SP
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACICLOVIR" in n for n in nomes), (
                f"Aciclovir não encontrado com erro ortográfico em {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_informal_lista_sem_formatacao(self):
        """E-mail sem formatação de lista, pedidos separados por vírgula."""
        email = """
        Olá, preciso de orçamento de albendazol 400mg mastigavel e alendronato 70mg blx4.

        Abraço,
        Drogaria Popular
        Fortaleza - CE
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            encontrou_albendazol = any("ALBENDAZOL" in n for n in nomes)
            encontrou_alendronato = any("ALENDRONATO" in n for n in nomes)
            assert encontrou_albendazol or encontrou_alendronato, (
                f"Nenhum produto encontrado em pedido informal sem lista: {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_informal_pedido_em_forma_de_pergunta(self):
        """E-mail com pedido formulado como pergunta."""
        email = """
        Olá! Vocês têm o Acheflan aerossol 54g? Se sim, qual o preço?

        Att,
        Farmácia Esperança
        Natal - RN
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACHEFLAN" in n for n in nomes), (
                f"Acheflan não encontrado em pedido na forma de pergunta: {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_informal_com_contexto_clinico(self):
        """E-mail com contexto clínico — médico/farmacêutico mencionando uso."""
        email = """
        Boa tarde,

        Preciso de orçamento de acetilcisteína 40mg xarope frasco 120ml para dispensa hospitalar.

        At.te,
        Dr. Rodrigo Mendes - CRF 1234
        Hospital São Rafael
        Salvador - BA
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACETILCISTEINA" in n for n in nomes), (
                f"Acetilcisteína não encontrada em pedido com contexto clínico: {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_informal_pedido_urgente_com_caps(self):
        """E-mail urgente com uso de CAPS LOCK e exclamação."""
        email = """
        BOA TARDE! PRECISO URGENTE DO PREÇO DE ACIDO MEFENAMICO 500MG 3BLX8!!

        FARMÁCIA URGÊNCIA EXPRESS
        RIO DE JANEIRO - RJ
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ACIDO MEFENAMICO" in n or "MEFENÂMICO" in n or "MEFENAMICO" in n for n in nomes), (
                f"Ácido mefenâmico não encontrado em pedido urgente em caps: {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_informal_mensagem_muito_curta(self):
        """Mensagem mínima: apenas o nome do produto e UF."""
        email = """
        Adipept 40mg blx42. São Paulo SP
        """
        def _asserts(orcamento):
            nomes = extrair_nomes_produtos(orcamento)
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            assert any("ADIPEPT" in n for n in nomes), (
                f"Adipept não encontrado em mensagem mínima: {nomes}"
            )
        _executar_com_salvamento(email, _asserts)

    def test_informal_cliente_pessoa_fisica(self):
        """E-mail de pessoa física — deve classificar tipo como PMC/PF."""
        email = """
        Olá boa tarde!

        Sou paciente e gostaria de saber o preço do Vertix 10mg comprimido para uso pessoal.

        Obrigado,
        Maria da Silva
        Curitiba - PR
        """
        def _asserts(orcamento):
            assert orcamento["itens"], "Orçamento não retornou nenhum item"
            cliente = orcamento.get("cliente", {})
            tipo = cliente.get("tipo", "").upper()
            assert "FÍSICA" in tipo or "FISICA" in tipo or tipo == "PF" or tipo == "PMC", (
                f"Tipo de cliente deveria ser pessoa física, obtido: {tipo!r}"
            )
        _executar_com_salvamento(email, _asserts)


# ===========================================================================
# Execução direta (sem pytest)
# ===========================================================================

if __name__ == "__main__":
    import sys

    grupos = [
        ("NOME COMERCIAL",   TestNomeComercial),
        ("CÓDIGO SAP",       TestCodigoSAP),
        ("PRINCÍPIO ATIVO",  TestPrincipioAtivo),
        ("ABREVIAÇÕES",      TestAbreviacoes),
        ("QUANTIDADES",      TestQuantidades),
        ("TEXTOS INFORMAIS", TestTextosInformais),
    ]

    print(f"\nResultados serão salvos em: {RESULTADO_DIR.resolve()}")

    total = passou = falhou = 0
    falhas = []

    for grupo_nome, cls in grupos:
        print(f"\n{'='*60}")
        print(f"  GRUPO: {grupo_nome}")
        print(f"{'='*60}")
        instancia = cls()
        metodos = [m for m in dir(cls) if m.startswith("test_")]
        for metodo in sorted(metodos):
            total += 1
            try:
                getattr(instancia, metodo)()
                print(f"  ✅ PASSOU  — {metodo}")
                passou += 1
            except Exception as e:
                print(f"  ❌ FALHOU  — {metodo}: {e}")
                falhou += 1
                falhas.append((grupo_nome, metodo, str(e)))

    print(f"\n{'='*60}")
    print(f"RESULTADO FINAL: {passou}/{total} testes passaram, {falhou} falharam.")
    if falhas:
        print("\nFalhas detalhadas:")
        for gn, mn, err in falhas:
            print(f"  [{gn}] {mn}: {err}")
    sys.exit(0 if falhou == 0 else 1)