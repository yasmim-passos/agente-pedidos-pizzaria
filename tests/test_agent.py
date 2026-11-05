import logging

import pytest

from agente import agent as modulo
from agente.agent import ERRO_DUPLICADO, ERRO_SEM_CONFIRMACAO, MENSAGEM_ERRO, Agente, _confirmou
from agente.llm_client import (
    ChamadaFerramenta,
    LLMError,
    Mensagem,
    RespostaLLM,
    ResultadosFerramentas,
)
from agente.tools import ERRO_RESULTADO_INCERTO

ARGUMENTOS = {"mesa_numero": 3, "itens": [{"produto_id": 2, "quantidade": 1}]}
RESUMO = RespostaLLM(texto="1 Calabresa Grande na mesa 3. Confirma o pedido?")
CRIAR = RespostaLLM(chamadas=(ChamadaFerramenta("criar_pedido", ARGUMENTOS),))
CONSULTAR = RespostaLLM(chamadas=(ChamadaFerramenta("consultar_cardapio", {}),))
FINAL = RespostaLLM(texto="Pedido registrado!")
PEDIDO_OK = {"ok": True, "pedido_id": 1}


class LLMFalso:
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.historicos = []

    def gerar(self, historico):
        self.historicos.append(list(historico))
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class FerramentasFalsas:
    def __init__(self, resultado=PEDIDO_OK):
        self.resultado = resultado
        self.chamadas = []

    def executar(self, nome, argumentos):
        self.chamadas.append((nome, argumentos))
        return {"ok": True, "itens": []} if nome == "consultar_cardapio" else self.resultado

    def pedidos(self):
        return [c for c in self.chamadas if c[0] == "criar_pedido"]


def criar_agente(*respostas, resultado=PEDIDO_OK):
    llm = LLMFalso(*respostas)
    ferramentas = FerramentasFalsas(resultado)
    return Agente(llm, ferramentas), llm, ferramentas


def ultimo_resultado(llm):
    return next(
        item for item in reversed(llm.historicos[-1]) if isinstance(item, ResultadosFerramentas)
    ).resultados[0][1]


def test_resposta_direta_sem_ferramenta():
    agente, _, ferramentas = criar_agente(RespostaLLM(texto="Olá!"))

    assert agente.responder("s1", "Oi") == "Olá!"
    assert ferramentas.chamadas == []


def test_resultado_da_ferramenta_volta_ao_modelo():
    agente, llm, ferramentas = criar_agente(CONSULTAR, RespostaLLM(texto="Temos calabresa."))

    assert agente.responder("s1", "O que tem?") == "Temos calabresa."
    assert ferramentas.chamadas == [("consultar_cardapio", {})]
    assert llm.historicos[1][-2:] == [
        CONSULTAR,
        ResultadosFerramentas((("consultar_cardapio", {"ok": True, "itens": []}),)),
    ]


def test_varias_chamadas_voltam_juntas():
    duas = RespostaLLM(chamadas=(ChamadaFerramenta("consultar_cardapio", {}),) * 2)
    agente, llm, _ = criar_agente(duas, FINAL)

    agente.responder("s1", "O que tem?")

    assert len(llm.historicos[1][-1].resultados) == 2


def test_para_no_limite_de_iteracoes():
    agente, llm, _ = criar_agente(*[CONSULTAR] * 20)

    assert agente.responder("s1", "Oi") == MENSAGEM_ERRO
    assert len(llm.historicos) == modulo.MAX_ITERACOES


def test_erro_do_modelo_vira_mensagem_amigavel():
    agente, _, _ = criar_agente(LLMError("falhou"))

    assert agente.responder("s1", "Oi") == MENSAGEM_ERRO


def test_cria_o_pedido_depois_do_resumo_e_do_sim():
    agente, _, ferramentas = criar_agente(RESUMO, CRIAR, FINAL)

    agente.responder("s1", "1 calabresa grande, mesa 3")
    assert agente.responder("s1", "sim") == "Pedido registrado!"

    assert ferramentas.pedidos() == [("criar_pedido", ARGUMENTOS)]


def test_nao_cria_sem_confirmacao_do_cliente():
    agente, llm, ferramentas = criar_agente(CRIAR, RESUMO)

    agente.responder("s1", "1 calabresa grande, mesa 3")

    assert ferramentas.pedidos() == []
    assert ultimo_resultado(llm)["erro"] == ERRO_SEM_CONFIRMACAO


def test_sim_sem_resumo_antes_nao_cria():
    agente, _, ferramentas = criar_agente(RespostaLLM(texto="Quer ver o cardápio?"), CRIAR, RESUMO)

    agente.responder("s1", "Oi")
    agente.responder("s1", "sim")

    assert ferramentas.pedidos() == []


def test_mudanca_de_ideia_depois_do_resumo_nao_cria():
    agente, _, ferramentas = criar_agente(RESUMO, CRIAR, RESUMO)

    agente.responder("s1", "1 calabresa grande, mesa 3")
    agente.responder("s1", "troca por marguerita")

    assert ferramentas.pedidos() == []


def test_mesmo_turno_nao_cria_duas_vezes():
    agente, llm, ferramentas = criar_agente(RESUMO, CRIAR, CRIAR, FINAL)

    agente.responder("s1", "1 calabresa grande, mesa 3")
    agente.responder("s1", "sim")

    assert len(ferramentas.pedidos()) == 1
    assert ultimo_resultado(llm)["erro"] == ERRO_SEM_CONFIRMACAO


def test_chamada_dupla_na_mesma_resposta_cria_um_pedido():
    duas = RespostaLLM(chamadas=(ChamadaFerramenta("criar_pedido", ARGUMENTOS),) * 2)
    agente, _, ferramentas = criar_agente(RESUMO, duas, FINAL)

    agente.responder("s1", "1 calabresa grande, mesa 3")
    agente.responder("s1", "sim")

    assert len(ferramentas.pedidos()) == 1


def test_segundo_sim_nao_duplica_o_pedido():
    agente, llm, ferramentas = criar_agente(
        RESUMO, CRIAR, RespostaLLM(texto="Pedido confirmado!"), CRIAR, FINAL
    )

    agente.responder("s1", "1 calabresa grande, mesa 3")
    agente.responder("s1", "sim")
    agente.responder("s1", "sim")

    assert len(ferramentas.pedidos()) == 1
    assert ultimo_resultado(llm)["erro"] == ERRO_DUPLICADO


def test_resultado_incerto_nao_permite_tentar_de_novo():
    agente, _, ferramentas = criar_agente(
        RESUMO,
        CRIAR,
        RespostaLLM(texto="Não consegui confirmar."),
        CRIAR,
        FINAL,
        resultado={"ok": False, "erro": ERRO_RESULTADO_INCERTO},
    )

    agente.responder("s1", "1 calabresa grande, mesa 3")
    agente.responder("s1", "sim")
    agente.responder("s1", "pode confirmar")

    assert len(ferramentas.pedidos()) == 1


def test_erro_de_validacao_permite_corrigir_no_mesmo_turno():
    agente, _, ferramentas = criar_agente(
        RESUMO, CRIAR, CRIAR, FINAL, resultado={"ok": False, "erro": "Produto inválido."}
    )

    agente.responder("s1", "1 calabresa grande, mesa 3")
    agente.responder("s1", "sim")

    assert len(ferramentas.pedidos()) == 2


def test_novo_pedido_diferente_com_nova_confirmacao():
    outros = {"mesa_numero": 3, "itens": [{"produto_id": 9, "quantidade": 1}]}
    agente, _, ferramentas = criar_agente(
        RESUMO,
        CRIAR,
        RespostaLLM(texto="Pedido registrado!"),
        RespostaLLM(texto="1 água na mesa 3. Confirma?"),
        RespostaLLM(chamadas=(ChamadaFerramenta("criar_pedido", outros),)),
        FINAL,
    )

    agente.responder("s1", "1 calabresa grande, mesa 3")
    agente.responder("s1", "sim")
    agente.responder("s1", "agora quero uma água")
    agente.responder("s1", "sim")

    assert [c[1] for c in ferramentas.pedidos()] == [ARGUMENTOS, outros]


def test_sessoes_nao_se_misturam():
    agente, llm, ferramentas = criar_agente(RESUMO, RespostaLLM(texto="Oi"), CRIAR, RESUMO)

    agente.responder("s1", "1 calabresa grande, mesa 3")
    agente.responder("s2", "Oi")
    agente.responder("s2", "sim")

    assert llm.historicos[1] == [Mensagem("usuario", "Oi")]
    assert ferramentas.pedidos() == []


def test_historico_tem_tamanho_limitado(monkeypatch):
    monkeypatch.setattr(modulo, "MAX_ITENS_HISTORICO", 6)
    agente, llm, _ = criar_agente(*[RespostaLLM(texto="ok")] * 20)

    for numero in range(20):
        agente.responder("s1", f"mensagem {numero}")

    assert len(llm.historicos[-1]) <= 7
    assert llm.historicos[-1][-1] == Mensagem("usuario", "mensagem 19")


def test_corte_do_historico_nao_separa_chamada_e_resultado(monkeypatch):
    monkeypatch.setattr(modulo, "MAX_ITENS_HISTORICO", 6)
    agente, llm, _ = criar_agente(
        CONSULTAR,
        RespostaLLM(texto="a"),
        RespostaLLM(texto="b"),
        RespostaLLM(texto="c"),
        RespostaLLM(texto="d"),
    )

    agente.responder("s1", "primeira")
    agente.responder("s1", "segunda")
    agente.responder("s1", "terceira")
    agente.responder("s1", "quarta")

    assert llm.historicos[-1][0] == Mensagem("usuario", "segunda")


def test_loga_cada_ferramenta_sem_o_token(caplog):
    agente, _, _ = criar_agente(CONSULTAR, FINAL)

    with caplog.at_level(logging.INFO, logger="agente.agent"):
        agente.responder("s1", "O que tem?")

    assert "Ferramenta consultar_cardapio" in caplog.text
    assert "resultado=" in caplog.text


@pytest.mark.parametrize(
    "mensagem",
    ["sim", "Sim!", "SIM.", "sim, por favor", "confirmo", "pode confirmar", "ok", "isso mesmo", "sim pode criar"],
)
def test_reconhece_confirmacao(mensagem):
    assert _confirmou(mensagem)


@pytest.mark.parametrize(
    "mensagem",
    [
        "",
        "não",
        "quero uma pizza",
        "sim, mas troca por marguerita",
        "sim, sem cebola",
        "pode ser uma marguerita",
        "agora não, ok?",
        "sim eu quero também mais uma coca",
    ],
)
def test_nao_confunde_outras_mensagens_com_confirmacao(mensagem):
    assert not _confirmou(mensagem)
