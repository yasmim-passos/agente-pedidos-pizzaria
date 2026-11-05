# Agente de pedidos para pizzaria

**Status: em desenvolvimento.**

Agente em Python que usa o Gemini com *function calling* para entender pedidos em português e registrá-los na API de uma pizzaria.

A API da pizzaria (Java/Spring Boot) é do time do [LAB06](https://github.com/LAB06/backend-spring). Este repositório contém apenas o agente.

## Como preparar o ambiente

Requer Python 3.12 ou superior. Comandos para o PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## Como subir a API local

Clone o [backend](https://github.com/LAB06/backend-spring) como pasta irmã deste repositório (`../backend-spring`) e, com o Docker aberto, rode os comandos abaixo a partir da raiz deste repositório:

```powershell
# 1. Cria as chaves locais (na primeira vez), gera o token e cria o .env
python scripts/gerar_token_dev.py

# 2. Sobe a API (porta 8080) e o PostgreSQL
docker compose -f ../backend-spring/docker-compose.yml -f infra/compose.dev.yml up -d --build postgres app

# 3. Quando a API terminar de subir, cria o cardápio e as mesas de teste
docker cp scripts/seed_dev.sql pizzaria-postgres-dev:/tmp/seed_dev.sql
docker exec pizzaria-postgres-dev psql -U postgres -d pizzaria_db -v ON_ERROR_STOP=1 -f /tmp/seed_dev.sql

# 4. Confere se está tudo funcionando (cria pedidos de teste no banco local)
python scripts/testar_api.py
```

O token vale 24 horas. Se a API começar a responder 401, rode de novo o passo 1.

Depois, preencha `GEMINI_API_KEY` e `GEMINI_MODEL` no `.env`.

## Rotas da API usadas pelo agente

Confirmadas nos controllers do backend. Todas exigem `Authorization: Bearer <token>`, exceto a rota marcada como pública.

| Método | Rota | Para que serve |
|---|---|---|
| `GET` | `/menu/list` | Lista o cardápio |
| `GET` | `/menu/{id}` | Busca um item do cardápio |
| `GET` | `/tables` | Lista as mesas da empresa do token |
| `GET` | `/tables/access/{accessCode}` | Busca a mesa pelo QR Code (**pública**) |
| `POST` | `/orders` | Cria um pedido |
| `GET` | `/orders` | Lista os pedidos da empresa do token |
| `PATCH` | `/orders/{id}/status?statusNew=` | Atualiza o status de um pedido |

Formato do `POST /orders`:

```json
{
  "tableId": 1,
  "items": [
    { "productId": 2, "quantity": 1, "notes": "sem cebola" }
  ]
}
```

## Decisões sobre o ambiente local

**Autenticação.** A API valida um JWT RS256 com a chave pública e exige `iss=restaurant-auth`, `sub`, `empresa_id` (UUID), `iat` e `exp`. O serviço que emite esse token não faz parte do `docker-compose.yml` do backend. Em ambiente local, o `scripts/gerar_token_dev.py` cria um par de chaves próprio e assina um token com a mesma estrutura. A chave privada fica em `../backend-spring/keys/`, pasta ignorada pelo Git, e o token fica no `.env`, também ignorado. Em produção, o token viria do serviço de autenticação.

**Porta da API.** O `docker-compose.yml` do backend só publica a API pelo nginx, e o `nginx.conf` depende de um serviço `node-app` que não está no compose. O `infra/compose.dev.yml` expõe a API na porta 8080 sem alterar os arquivos do time.

## Limitações conhecidas da API

- **Cardápio e pedido usam tabelas separadas.** `GET /menu/list` lê `menu_items`, mas `POST /orders` procura o produto em `produto`, e não há rota para listar `produto`. O `scripts/seed_dev.sql` contorna isso inserindo cada item nas duas tabelas com o mesmo id. Em um ambiente real, as duas tabelas precisariam ser unificadas.
- **A API não recusa produto indisponível.** O `POST /orders` não confere o campo `disponivel`, então o agente precisa fazer essa validação.
- **O cardápio não é separado por empresa.** `menu_items` não tem `empresa_id`, ao contrário de mesas e produtos.

## Como rodar os testes

```powershell
pytest
```
