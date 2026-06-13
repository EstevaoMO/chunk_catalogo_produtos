import streamlit as st
import requests
import json
import time

# Configuração inicial da página
st.set_page_config(page_title="Validador de Orçamentos RAG", page_icon="💊", layout="wide")

# Estado da sessão para manter a URL ao trocar de página
if "webhook_url" not in st.session_state:
    st.session_state.webhook_url = ""

# --- SIDEBAR ---
st.sidebar.title("Configurações ⚙️")
st.session_state.webhook_url = st.sidebar.text_input(
    "URL do Webhook do n8n (POST)", 
    value=st.session_state.webhook_url,
    placeholder="https://seu-n8n.../webhook/orcamento",
    help="Cole aqui a URL de produção ou teste do seu nó Webhook."
)

st.sidebar.markdown("---")
pagina = st.sidebar.radio("Navegação", ["1️⃣ Teste Manual", "2️⃣ Bateria de Testes"])

# Função auxiliar para chamar o webhook
def chamar_webhook(url, mensagem):
    # O n8n foi configurado para aceitar a chave "solicitacao"
    payload = {"solicitacao": mensagem}
    try:
        start_time = time.time()
        # Timeout de 60s pois RAG pode demorar dependendo da LLM
        response = requests.post(url, json=payload, timeout=60)
        end_time = time.time()
        
        try:
            dados = response.json()
        except:
            dados = {"texto_puro": response.text}
            
        return response.status_code, dados, round(end_time - start_time, 2)
    except Exception as e:
        return None, {"erro_local": str(e)}, 0


# --- PÁGINA 1: TESTE MANUAL ---
if pagina == "1️⃣ Teste Manual":
    st.title("Teste de Orçamento Manual")
    st.markdown("Digite uma mensagem abaixo para simular o e-mail de um cliente.")
    
    mensagem = st.text_area("Mensagem do Cliente", height=150, placeholder="Ex: Preciso cotar 5 caixas de dipirona e 2 de paracetamol...")
    
    if st.button("Enviar Solicitação", type="primary"):
        if not st.session_state.webhook_url:
            st.warning("⚠️ Por favor, insira a URL do Webhook na barra lateral primeiro.")
        elif not mensagem:
            st.warning("⚠️ Digite uma mensagem para testar.")
        else:
            with st.spinner("Processando orçamento no n8n... (Aguardando LLM e Vector Store)"):
                status_code, resposta, tempo = chamar_webhook(st.session_state.webhook_url, mensagem)
                
            if status_code:
                st.success(f"Resposta recebida em {tempo} segundos! (Status HTTP: {status_code})")
                
                # Extraindo o status mapeado dentro do JSON (200, 404, 422, 500)
                status_interno = resposta.get("status", "Desconhecido")
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.metric("Status Retornado", status_interno)
                    st.metric("Total do Orçamento", f"R$ {resposta.get('total_orcamento', 0):.2f}")
                with col2:
                    st.info(f"**Observações (obs):**\n\n{resposta.get('obs', 'Nenhuma')}")
                
                st.markdown("### JSON Completo da Resposta")
                st.json(resposta)
            else:
                st.error("Falha ao conectar com o Webhook. Verifique a URL ou se o n8n está ativo.")
                st.json(resposta)


# --- PÁGINA 2: BATERIA DE TESTES ---
elif pagina == "2️⃣ Bateria de Testes":
    st.title("Bateria Automatizada de Testes")
    st.markdown("Esta página executa os 10 casos de teste oficiais da avaliação, além de testes extras para validar as rotas de tratamento de erros configuradas no fluxo.")
    
    # Lista de testes baseada no documento PDF e testes extras
    casos_de_teste = [
        {"id": 1, "nome": "Nome comercial", "input": "Preciso de 3 unidades de ACCUVIT.", "status_esperado": "200"},
        {"id": 2, "nome": "Código SAP", "input": "Favor cotar 5 unidades do código 1003649.", "status_esperado": "200"},
        {"id": 3, "nome": "Princípio ativo e dosagem", "input": "Gostaria de orçamento para 2 unidades de acetilcisteína 40mg xarope.", "status_esperado": "200"},
        {"id": 4, "nome": "Erro de digitação", "input": "Quero 4 unidades de acetilsisteina 20mg.", "status_esperado": "200"},
        {"id": 5, "nome": "Apresentação específica", "input": "Me envie orçamento de 6 unidades de Acheflan creme bisnaga de 30g.", "status_esperado": "200"},
        {"id": 6, "nome": "Múltiplos itens", "input": "Preciso cotar:\n2 unidades de ACICLOVIR 200MG\n3 unidades de ACICLOVIR creme 50mg\n1 unidade de ACHEFLAN aerosol", "status_esperado": "200"},
        {"id": 7, "nome": "Misturando código e nome", "input": "Cotar 2 unidades do código 1005119 e 3 unidades de ácido mefenâmico 500mg.", "status_esperado": "200"},
        {"id": 8, "nome": "Pedido informal", "input": "Oi, consegue ver pra mim 10 caixas daquele remédio de herpes, aciclovir comprimido?", "status_esperado": "200"},
        {"id": 9, "nome": "Produto ambíguo", "input": "Preciso de 5 unidades de ACEBROFILINA.", "status_esperado": "422"},
        {"id": 10, "nome": "Produto fora da base", "input": "Preciso de 2 unidades de miojo.", "status_esperado": "404"},
        # Testes adicionais focados no sistema de Stop and Error do seu n8n
        {"id": 11, "nome": "Falha Forçada - Payload Vazio (Erro Entrada)", "input": "", "status_esperado": "500"},
        {"id": 12, "nome": "Falha Forçada - Sem Produto", "input": "cotar", "status_esperado": "500"}
    ]

    if st.button("▶️ Iniciar Bateria de Testes", type="primary"):
        if not st.session_state.webhook_url:
            st.error("⚠️ Insira a URL do Webhook na barra lateral primeiro.")
        else:
            barra_progresso = st.progress(0)
            resultados = []
            
            for i, teste in enumerate(casos_de_teste):
                with st.status(f"Executando Teste {teste['id']} - {teste['nome']}...", expanded=False) as status:
                    st.write(f"**Entrada:** `{teste['input']}`")
                    
                    status_http, resposta, tempo = chamar_webhook(st.session_state.webhook_url, teste["input"])
                    
                    if status_http:
                        # Pega o status mapeado dentro do JSON, se falhar pega o HTTP
                        status_recebido = str(resposta.get("status", status_http))
                        
                        st.write(f"**Status Esperado:** {teste['status_esperado']} | **Status Recebido:** {status_recebido}")
                        st.write(f"Tempo de resposta: {tempo}s")
                        
                        if status_recebido == teste["status_esperado"]:
                            status.update(label=f"✅ Teste {teste['id']} Passou ({tempo}s)", state="complete")
                        else:
                            status.update(label=f"❌ Teste {teste['id']} Falhou ({tempo}s)", state="error")
                            
                        st.json(resposta)
                    else:
                        status.update(label=f"❌ Teste {teste['id']} Erro de Conexão", state="error")
                        st.error(resposta.get("erro_local"))
                
                barra_progresso.progress((i + 1) / len(casos_de_teste))
            
            st.success("🏁 Bateria de testes finalizada!")