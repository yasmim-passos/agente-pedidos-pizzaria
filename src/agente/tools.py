"""Ferramentas que o modelo pode pedir para executar.

O modelo pode inventar ids e valores, então tudo é validado aqui antes de chegar à API.
As ferramentas não levantam erros esperados: devolvem {"ok": False, "erro": "..."},
e o modelo usa esse texto para explicar o problema ao cliente.
"""

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agente.api_client import ApiClient, ApiError, ApiIndisponivelError, ApiStatusError

logger = logging.getLogger(__name__)

DECLARACOES = (
    {
        "nome": "consultar_cardapio",
        "descricao": (
            "Lista os itens disponíveis no cardápio, com id, nome e preço. Use antes de "
            "citar um item ou um preço e para descobrir o id de um produto."
        ),
        "parametros": {"type": "object", "properties": {}},
    },
    {
        "nome": "criar_pedido",
        "descricao": (
            "Registra o pedido na cozinha. Só use depois de mostrar o resumo do pedido "
            'e de o cliente responder "sim" de forma clara.'
        ),
        "parametros": {
            "type": "object",
            "properties": {
                "mesa_numero": {
                    "type": "integer",
                    "description": "Número da mesa informado pelo cliente. Nunca adivinhe.",
                },
                "itens": {
                    "type": "array",
                    "description": "Itens do pedido. Precisa ter pelo menos um.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "produto_id": {
                                "type": "integer",
                                "description": "Id do item, obtido em consultar_cardapio.",
                            },
                            "quantidade": {
                                "type": "integer",
                                "description": "Quantidade do item. Precisa ser maior que zero.",
                            },
                            "observacoes": {
                                "type": "string",
                                "description": 'Pedido especial, como "sem cebola". Omita se não houver.',
                            },
                        },
                        "required": ["produto_id", "quantidade"],
                    },
                },
            },
            "required": ["mesa_numero", "itens"],
        },
    },
)

ERRO_INDISPONIVEL = "O sistema de pedidos está indisponível agora. Nenhum pedido foi criado."
# Sem resposta ao criar, o pedido pode ter sido registrado. Tentar de novo poderia duplicá-lo.
ERRO_RESULTADO_INCERTO = (
    "Não foi possível confirmar se o pedido foi registrado. Não tente criar o pedido de "
    "novo: peça ao cliente para confirmar com um atendente."
)
ERRO_POR_STATUS = {
    400: "O sistema recusou os dados do pedido. Nenhum pedido foi criado.",
    404: (
        "O sistema não encontrou a mesa ou um dos produtos. Nenhum pedido foi criado. "
        "Confirme a mesa com o cliente e consulte o cardápio de novo."
    ),
}


class _ItemPedido(BaseModel):
    produto_id: int
    quantidade: int = Field(gt=0)
    observacoes: str | None = None


class _Pedido(BaseModel):
    mesa_numero: int = Field(gt=0)
    itens: list[_ItemPedido] = Field(min_length=1)


def _falha(mensagem: str) -> dict:
    return {"ok": False, "erro": mensagem}


def _explicar_validacao(erro: ValidationError) -> str:
    campos = {campo for detalhe in erro.errors() for campo in detalhe["loc"]}
    if "mesa_numero" in campos:
        return "Falta um número de mesa válido. Pergunte ao cliente qual é a mesa."
    if "quantidade" in campos:
        return "A quantidade de cada item precisa ser um número inteiro maior que zero."
    return "O pedido precisa ter pelo menos um item, com o id de um produto do cardápio."


class Ferramentas:
    def __init__(self, api: ApiClient):
        self._api = api

    def consultar_cardapio(self) -> dict:
        try:
            cardapio = self._api.listar_cardapio()
            itens = [
                {"id": item["id"], "nome": item["name"], "preco": item["price"]}
                for item in cardapio
                if item["available"]
            ]
        except (ApiError, KeyError, TypeError) as erro:
            logger.error("Falha ao consultar o cardápio: %s", erro)
            return _falha("O cardápio está indisponível agora. Tente de novo em instantes.")
        return {"ok": True, "itens": itens}

    def criar_pedido(self, mesa_numero: Any, itens: Any) -> dict:
        try:
            pedido = _Pedido(mesa_numero=mesa_numero, itens=itens)
        except ValidationError as erro:
            return _falha(_explicar_validacao(erro))

        # O cardápio é lido na hora para recusar ids inventados e itens indisponíveis.
        # A API não confere a disponibilidade, então essa regra precisa ficar aqui.
        # O cliente fala o número da mesa, mas a API espera o id: usar um no lugar do
        # outro mandaria o pedido para a mesa errada, sem nenhum erro.
        try:
            disponiveis = {
                item["id"] for item in self._api.listar_cardapio() if item["available"]
            }
            ids_das_mesas = {
                mesa["tableNumber"]: mesa["id"] for mesa in self._api.listar_mesas()
            }
        except (ApiError, KeyError, TypeError) as erro:
            logger.error("Falha ao validar o pedido: %s", erro)
            return _falha(ERRO_INDISPONIVEL)

        invalidos = [i.produto_id for i in pedido.itens if i.produto_id not in disponiveis]
        if invalidos:
            return _falha(
                f"Os produtos com id {invalidos} não estão disponíveis. Nenhum pedido foi "
                "criado. Consulte o cardápio e use apenas os itens dele."
            )

        if pedido.mesa_numero not in ids_das_mesas:
            return _falha(
                f"A mesa {pedido.mesa_numero} não existe. Nenhum pedido foi criado. "
                "Confirme o número da mesa com o cliente."
            )

        corpo = {
            "tableId": ids_das_mesas[pedido.mesa_numero],
            "items": [
                {"productId": i.produto_id, "quantity": i.quantidade, "notes": i.observacoes}
                for i in pedido.itens
            ],
        }

        try:
            criado = self._api.criar_pedido(corpo)
            return {
                "ok": True,
                "pedido_id": criado["id"],
                "mesa_numero": pedido.mesa_numero,
                "total": criado["totalAmount"],
                "itens": [
                    {
                        "nome": item["productName"],
                        "quantidade": item["quantity"],
                        "subtotal": item["subtotal"],
                        "observacoes": item["notes"],
                    }
                    for item in criado["items"]
                ],
            }
        except ApiStatusError as erro:
            logger.error("Falha ao criar o pedido: %s", erro)
            return _falha(ERRO_POR_STATUS.get(erro.status, ERRO_INDISPONIVEL))
        except (ApiIndisponivelError, KeyError, TypeError) as erro:
            logger.error("Resultado incerto ao criar o pedido: %s", erro)
            return _falha(ERRO_RESULTADO_INCERTO)

    def executar(self, nome: str, argumentos: dict) -> dict:
        """Executa a ferramenta que o modelo pediu."""
        if nome == "consultar_cardapio":
            return self.consultar_cardapio()
        if nome == "criar_pedido":
            return self.criar_pedido(argumentos.get("mesa_numero"), argumentos.get("itens"))
        return _falha(f"A ferramenta {nome} não existe.")
