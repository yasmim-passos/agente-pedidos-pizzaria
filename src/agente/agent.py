"""Loop do agente: modelo -> ferramentas -> resultado de volta ao modelo -> resposta."""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

from agente.llm_client import (
    ChamadaFerramenta,
    ItemHistorico,
    LLMClient,
    LLMError,
    Mensagem,
    ResultadosFerramentas,
)
from agente.tools import ERRO_RESULTADO_INCERTO, Ferramentas

logger = logging.getLogger(__name__)

MAX_ITERACOES = 5
MAX_ITENS_HISTORICO = 40

MENSAGEM_ERRO = "Tive um problema para concluir o atendimento. Por favor, chame um atendente."
ERRO_SEM_CONFIRMACAO = (
    "Pedido não criado: o cliente ainda não confirmou. Mostre o resumo e pergunte se ele confirma."
)
ERRO_DUPLICADO = "Pedido não criado: este mesmo pedido já foi registrado nesta conversa."

_CONFIRMACOES = {"sim", "confirmo", "confirma", "confirmado", "pode", "ok", "isso", "certo", "fechado"}
_RESSALVAS = {"não", "nao", "mas", "troca", "muda", "sem", "com", "tira", "um", "uma"}


@dataclass
class Sessao:
    historico: list[ItemHistorico] = field(default_factory=list)
    ultima_resposta: str = ""
    confirmado: bool = False
    ultimo_pedido: dict | None = None


def _confirmou(mensagem: str) -> bool:
    palavras = re.findall(r"\w+", mensagem.lower())
    return (
        0 < len(palavras) <= 4
        and palavras[0] in _CONFIRMACOES
        and not _RESSALVAS.intersection(palavras)
    )


def _limitar(historico: list[ItemHistorico]) -> list[ItemHistorico]:
    """Corta o início, sempre em uma mensagem do cliente, para não separar chamada e resultado."""
    recente = historico[-MAX_ITENS_HISTORICO:]
    inicio = next(
        i for i, item in enumerate(recente) if isinstance(item, Mensagem) and item.papel == "usuario"
    )
    return recente[inicio:]


class Agente:
    def __init__(self, llm: LLMClient, ferramentas: Ferramentas):
        self._llm = llm
        self._ferramentas = ferramentas
        self._sessoes: defaultdict[str, Sessao] = defaultdict(Sessao)

    def responder(self, sessao_id: str, mensagem: str) -> str:
        sessao = self._sessoes[sessao_id]
        sessao.historico.append(Mensagem("usuario", mensagem))
        sessao.confirmado = _confirmou(mensagem) and "confirm" in sessao.ultima_resposta.lower()

        try:
            texto = self._rodar_loop(sessao)
        except LLMError as erro:
            logger.error("Falha no modelo: %s", erro)
            texto = MENSAGEM_ERRO

        sessao.historico.append(Mensagem("modelo", texto))
        sessao.historico = _limitar(sessao.historico)
        sessao.ultima_resposta = texto
        return texto

    def _rodar_loop(self, sessao: Sessao) -> str:
        for _ in range(MAX_ITERACOES):
            resposta = self._llm.gerar(sessao.historico)
            if not resposta.chamadas:
                return resposta.texto

            sessao.historico.append(resposta)
            resultados = tuple(
                (chamada.nome, self._executar(sessao, chamada)) for chamada in resposta.chamadas
            )
            sessao.historico.append(ResultadosFerramentas(resultados))

        logger.error("Limite de %d iterações atingido.", MAX_ITERACOES)
        return MENSAGEM_ERRO

    def _executar(self, sessao: Sessao, chamada: ChamadaFerramenta) -> dict:
        if chamada.nome == "criar_pedido":
            resultado = self._criar_pedido(sessao, chamada.argumentos)
        else:
            resultado = self._ferramentas.executar(chamada.nome, chamada.argumentos)

        logger.info(
            "Ferramenta %s | argumentos=%s | resultado=%s",
            chamada.nome,
            chamada.argumentos,
            resultado,
        )
        return resultado

    def _criar_pedido(self, sessao: Sessao, argumentos: dict) -> dict:
        if not sessao.confirmado:
            return {"ok": False, "erro": ERRO_SEM_CONFIRMACAO}
        if argumentos == sessao.ultimo_pedido:
            return {"ok": False, "erro": ERRO_DUPLICADO}

        resultado = self._ferramentas.executar("criar_pedido", argumentos)
        if resultado["ok"] or resultado["erro"] == ERRO_RESULTADO_INCERTO:
            sessao.ultimo_pedido = argumentos
            sessao.confirmado = False
        return resultado
