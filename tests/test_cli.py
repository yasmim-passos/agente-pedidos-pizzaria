import pytest

from agente import cli
from agente.config import ConfigError


class AgenteFalso:
    def __init__(self):
        self.chamadas = []

    def responder(self, sessao_id, mensagem):
        self.chamadas.append((sessao_id, mensagem))
        return f"resposta a {mensagem}"


def conversar_com(entradas, agente):
    restantes = iter(entradas)
    saidas = []

    def ler(_):
        try:
            return next(restantes)
        except StopIteration:
            raise EOFError

    cli.conversar(agente, ler, saidas.append)
    return saidas


def test_envia_a_mensagem_e_mostra_a_resposta():
    agente = AgenteFalso()

    saidas = conversar_com(["Oi", "sair"], agente)

    assert agente.chamadas == [("terminal", "Oi")]
    assert saidas[-1] == "Atendente: resposta a Oi"


def test_todas_as_mensagens_usam_a_mesma_sessao():
    agente = AgenteFalso()

    conversar_com(["Oi", "Quero uma pizza", "sair"], agente)

    assert {sessao for sessao, _ in agente.chamadas} == {"terminal"}


def test_ignora_linhas_vazias():
    agente = AgenteFalso()

    conversar_com(["", "   ", "Oi", "sair"], agente)

    assert agente.chamadas == [("terminal", "Oi")]


@pytest.mark.parametrize("comando", ["sair", "SAIR", " exit ", "quit"])
def test_comando_de_saida_encerra_sem_chamar_o_agente(comando):
    agente = AgenteFalso()

    conversar_com([comando, "Oi"], agente)

    assert agente.chamadas == []


def test_fim_da_entrada_encerra_a_conversa():
    agente = AgenteFalso()

    conversar_com(["Oi"], agente)

    assert agente.chamadas == [("terminal", "Oi")]


def test_sem_configuracao_mostra_o_erro_e_sai(monkeypatch):
    def sem_config():
        raise ConfigError("Variáveis sem valor: GEMINI_API_KEY.")

    monkeypatch.setattr(cli, "carregar_config", sem_config)
    monkeypatch.setattr("sys.argv", ["agente"])

    with pytest.raises(SystemExit) as saida:
        cli.main()

    assert "GEMINI_API_KEY" in str(saida.value)
