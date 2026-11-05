"""Chamadas HTTP para a API da pizzaria (LAB06)."""

from typing import Any

import requests

from agente.config import Config

TIMEOUT_S = 10


class ApiError(Exception):
    """A chamada à API falhou."""


class ApiIndisponivelError(ApiError):
    """A API não respondeu, ou respondeu algo que não dá para ler."""


class ApiStatusError(ApiError):
    """A API respondeu com um status de erro."""

    def __init__(self, status: int):
        super().__init__(f"A API respondeu com o status {status}.")
        self.status = status


class ApiClient:
    def __init__(self, config: Config):
        self._base = config.api_base_url
        self._sessao = requests.Session()
        self._sessao.headers["Authorization"] = f"Bearer {config.api_token}"

    def listar_cardapio(self) -> Any:
        return self._requisitar("GET", "/menu/list")

    def listar_mesas(self) -> Any:
        return self._requisitar("GET", "/tables")

    def criar_pedido(self, corpo: dict) -> Any:
        return self._requisitar("POST", "/orders", json=corpo)

    def _requisitar(self, metodo: str, rota: str, **kwargs: Any) -> Any:
        # Único ponto que faz HTTP: assim, nenhuma chamada fica sem timeout.
        try:
            resposta = self._sessao.request(
                metodo, f"{self._base}{rota}", timeout=TIMEOUT_S, **kwargs
            )
            if resposta.ok:
                return resposta.json()
        except requests.RequestException as erro:
            raise ApiIndisponivelError("Não foi possível falar com a API.") from erro

        raise ApiStatusError(resposta.status_code)
