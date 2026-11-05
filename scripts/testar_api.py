"""Confere se a API local está pronta para o agente. Cria pedidos de verdade no banco local.

Uso: python scripts/testar_api.py
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import dotenv_values

ARQUIVO_ENV = Path(__file__).resolve().parents[1] / ".env"
TIMEOUT = 10
ID_INEXISTENTE = 999999


def conferir(descricao: str, passou: bool, detalhe: object = "") -> bool:
    print(f"[{'OK' if passou else 'FALHOU'}] {descricao} {detalhe}".rstrip())
    return passou


def main() -> int:
    env = dotenv_values(ARQUIVO_ENV)
    base = (env.get("API_BASE_URL") or "").rstrip("/")
    token = env.get("API_TOKEN") or ""

    if not base or not token:
        print("Preencha API_BASE_URL e API_TOKEN no .env (veja o README).")
        return 1

    # Trava de segurança: este script cria pedidos, então só roda na máquina local.
    if urlparse(base).hostname not in ("localhost", "127.0.0.1"):
        print(f"Este script só roda contra a API local, e não contra {base}.")
        return 1

    autenticado = {"Authorization": f"Bearer {token}"}
    resultados = []

    def novo_pedido(mesa: int, produto: int, quantidade: int) -> requests.Response:
        corpo = {
            "tableId": mesa,
            "items": [{"productId": produto, "quantity": quantidade, "notes": "sem cebola"}],
        }
        return requests.post(f"{base}/orders", json=corpo, headers=autenticado, timeout=TIMEOUT)

    resposta = requests.get(f"{base}/menu/list", timeout=TIMEOUT)
    resultados.append(conferir("Sem token, a API recusa (401)", resposta.status_code == 401))

    resposta = requests.get(f"{base}/menu/list", headers=autenticado, timeout=TIMEOUT)
    if not conferir("Com token, lista o cardápio (200)", resposta.status_code == 200, resposta.status_code):
        return 1
    cardapio = resposta.json()
    disponiveis = [item for item in cardapio if item["available"]]
    resultados.append(conferir("Cardápio tem itens disponíveis", bool(disponiveis), f"({len(cardapio)} itens)"))

    resposta = requests.get(f"{base}/tables", headers=autenticado, timeout=TIMEOUT)
    mesas = resposta.json() if resposta.status_code == 200 else []
    resultados.append(conferir("Lista as mesas da empresa", bool(mesas), f"({len(mesas)} mesas)"))

    if not (disponiveis and mesas):
        print("Sem cardápio ou mesas: rode o scripts/seed_dev.sql (veja o README).")
        return 1

    item = disponiveis[0]
    mesa = mesas[0]["id"]

    resposta = novo_pedido(mesa, item["id"], 2)
    if conferir("Cria um pedido (201)", resposta.status_code == 201, resposta.status_code):
        pedido = resposta.json()
        criado = pedido["items"][0]
        resultados.append(
            conferir(
                "O id do cardápio aponta para o mesmo produto do pedido",
                criado["productName"] == item["name"],
                f"({item['name']})",
            )
        )
        resultados.append(
            conferir(
                "O total é calculado pela API",
                float(pedido["totalAmount"]) == float(item["price"]) * 2,
                f"(R$ {pedido['totalAmount']})",
            )
        )
        resultados.append(conferir("A observação é salva", criado["notes"] == "sem cebola"))
    else:
        resultados.append(False)

    resultados.append(conferir("Produto inexistente: 404", novo_pedido(mesa, ID_INEXISTENTE, 1).status_code == 404))
    resultados.append(conferir("Mesa inexistente: 404", novo_pedido(ID_INEXISTENTE, item["id"], 1).status_code == 404))
    resultados.append(conferir("Quantidade 0: 400", novo_pedido(mesa, item["id"], 0).status_code == 400))

    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
