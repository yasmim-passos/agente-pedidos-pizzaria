# Agente de pedidos para pizzaria

**Status: em desenvolvimento.**

Agente em Python que usa o Gemini com *function calling* para entender pedidos em português e registrá-los na API de uma pizzaria.

A API da pizzaria (Java/Spring Boot) é um projeto do time do LAB06 e não faz parte deste repositório. Este repositório contém apenas o agente, que conversa com a API por HTTP, seguindo o contrato descrito abaixo.

## Como preparar o ambiente

Requer Python 3.12 ou superior. Comandos para o PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
Copy-Item .env.example .env
```

Depois, preencha o `.env`:

| Variável | O que é |
|---|---|
| `GEMINI_API_KEY` | Chave do Google AI Studio |
| `GEMINI_MODEL` | Nome do modelo do Gemini |
| `API_BASE_URL` | Endereço da API da pizzaria |
| `API_TOKEN` | Token JWT aceito pela API |

O `.env` não vai para o Git.

## Contrato da API

O agente usa três rotas. Todas recebem `Authorization: Bearer <API_TOKEN>`.

| Método | Rota | Para que o agente usa |
|---|---|---|
| `GET` | `/menu/list` | Consultar o cardápio |
| `GET` | `/tables` | Descobrir o id de uma mesa a partir do número |
| `POST` | `/orders` | Criar o pedido |

**`GET /menu/list`** devolve uma lista. O agente lê `id`, `name`, `price` e `available` de cada item.

**`GET /tables`** devolve uma lista. O agente lê `id` e `tableNumber` de cada mesa.

**`POST /orders`** recebe:

```json
{
  "tableId": 1,
  "items": [
    { "productId": 2, "quantity": 1, "notes": "sem cebola" }
  ]
}
```

e responde com o pedido criado. O agente lê `id`, `totalAmount` e, em cada item, `productName`, `quantity`, `subtotal` e `notes`.

Respostas de erro (`400`, `401`, `404` e `5xx`) viram mensagens amigáveis para o cliente, sem detalhes técnicos.

## Como rodar os testes

Os testes usam servidores locais que imitam a API e o Gemini, então não precisam da API real, de internet nem de chave.

```powershell
pytest
```
