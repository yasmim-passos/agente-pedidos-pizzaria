import pytest

from agente import api_client as modulo
from agente.api_client import ApiClient, ApiIndisponivelError, ApiStatusError
from agente.config import Config
from conftest import TOKEN_FALSO, ApiFalsa

MENU = ("GET", "/menu/list")
MESAS = ("GET", "/tables")
PEDIDOS = ("POST", "/orders")
CORPO = {"tableId": 1, "items": []}


def chamar(cliente, rota):
    if rota == MENU:
        return cliente.listar_cardapio()
    if rota == MESAS:
        return cliente.listar_mesas()
    return cliente.criar_pedido(CORPO)


def test_lista_o_cardapio_com_o_token(api_falsa, api_client):
    api_falsa.rotas[MENU] = (200, [{"id": 1}])

    assert api_client.listar_cardapio() == [{"id": 1}]
    assert api_falsa.chamadas[0]["autorizacao"] == f"Bearer {TOKEN_FALSO}"


def test_lista_as_mesas_com_o_token(api_falsa, api_client):
    api_falsa.rotas[MESAS] = (200, [{"id": 11, "tableNumber": 3}])

    assert api_client.listar_mesas() == [{"id": 11, "tableNumber": 3}]
    assert api_falsa.chamadas[0]["autorizacao"] == f"Bearer {TOKEN_FALSO}"


def test_cria_o_pedido_com_token_e_corpo(api_falsa, api_client):
    api_falsa.rotas[PEDIDOS] = (201, {"id": 7})

    assert api_client.criar_pedido(CORPO) == {"id": 7}

    chamada = api_falsa.chamadas[0]
    assert chamada["corpo"] == CORPO
    assert chamada["autorizacao"] == f"Bearer {TOKEN_FALSO}"


@pytest.mark.parametrize("rota", [MENU, MESAS, PEDIDOS])
@pytest.mark.parametrize("status", [400, 401, 404, 500])
def test_status_de_erro_vira_excecao_com_o_status(api_falsa, api_client, rota, status):
    api_falsa.rotas[rota] = (status, {"status": status})

    with pytest.raises(ApiStatusError) as capturado:
        chamar(api_client, rota)

    assert capturado.value.status == status


@pytest.mark.parametrize("rota", [MENU, MESAS, PEDIDOS])
def test_toda_chamada_tem_timeout(api_falsa, api_client, rota, monkeypatch):
    monkeypatch.setattr(modulo, "TIMEOUT_S", 0.3)
    api_falsa.rotas[rota] = ApiFalsa.TRAVAR

    with pytest.raises(ApiIndisponivelError):
        chamar(api_client, rota)


def test_timeout_padrao_e_de_10_segundos():
    assert modulo.TIMEOUT_S == 10


def test_api_fora_do_ar():
    cliente = ApiClient(Config("chave", "modelo", "http://127.0.0.1:9", "token"))

    with pytest.raises(ApiIndisponivelError):
        cliente.listar_cardapio()


def test_conexao_derrubada(api_falsa, api_client):
    api_falsa.rotas[PEDIDOS] = ApiFalsa.FECHAR

    with pytest.raises(ApiIndisponivelError):
        api_client.criar_pedido(CORPO)


def test_resposta_que_nao_e_json(api_falsa, api_client):
    api_falsa.rotas[MENU] = (200, "<html>nao e json</html>")

    with pytest.raises(ApiIndisponivelError):
        api_client.listar_cardapio()


def test_erro_nao_expoe_o_token(api_falsa, api_client):
    api_falsa.rotas[MENU] = (500, {})

    with pytest.raises(ApiStatusError) as capturado:
        api_client.listar_cardapio()

    assert TOKEN_FALSO not in str(capturado.value)
