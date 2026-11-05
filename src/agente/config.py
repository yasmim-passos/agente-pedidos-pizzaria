"""Lê a configuração do agente a partir do .env e das variáveis de ambiente."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

ARQUIVO_ENV = Path(__file__).resolve().parents[2] / ".env"
VARIAVEIS_OBRIGATORIAS = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "API_BASE_URL",
    "API_TOKEN",
)


class ConfigError(Exception):
    """A configuração está incompleta."""


@dataclass(frozen=True)
class Config:
    # repr=False impede que os segredos apareçam em logs e mensagens de erro.
    gemini_api_key: str = field(repr=False)
    gemini_model: str
    api_base_url: str
    api_token: str = field(repr=False)


def carregar_config(arquivo_env: Path = ARQUIVO_ENV) -> Config:
    # Variáveis de ambiente têm prioridade sobre o .env.
    valores = {**dotenv_values(arquivo_env), **os.environ}
    limpos = {
        nome: (valores.get(nome) or "").strip() for nome in VARIAVEIS_OBRIGATORIAS
    }

    faltando = [nome for nome, valor in limpos.items() if not valor]
    if faltando:
        raise ConfigError(
            f"Variáveis sem valor: {', '.join(faltando)}. "
            "Copie o .env.example para .env e preencha."
        )

    return Config(
        gemini_api_key=limpos["GEMINI_API_KEY"],
        gemini_model=limpos["GEMINI_MODEL"],
        api_base_url=limpos["API_BASE_URL"].rstrip("/"),
        api_token=limpos["API_TOKEN"],
    )
