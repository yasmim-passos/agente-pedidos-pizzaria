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
Copy-Item .env.example .env
```

Depois, preencha o `.env`.

## Como rodar os testes

```powershell
pytest
```
