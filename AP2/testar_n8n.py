import requests

url = '' # inserir url do n8n

mensagem = """
Me envie orçamento de 6 unidades de Acheflan creme bisnaga de 30g

Farmácia Bom Sucesso - RJ
"""

body = {
    "solicitacao": mensagem
}

resp = requests.post(url, json=body)

print(resp.content)