"""Testa as ferramentas com o ApiClient real contra uma API simulada por HTTP."""

import pytest

from agente import api_client as modulo_api
from agente.api_client import ApiClient
from agente.config import Config
from agente.tools import DECLARACOES, ERRO_INDISPONIVEL, ERRO_RESULTADO_INCERTO, Ferramentas
from conftest import ApiFalsa

MENU = ("GET", "/menu/list")
MESAS_ROTA = ("GET", "/tables")
PEDIDOS = ("POST", "/orders")

# O id é diferente do número de propósito: é isso que revela se os dois foram confundidos.
MESAS = [
    {"id": 11, "tableNumber": 3, "status": "FREE", "accessCode": "a", "qrCodeUrl": "b"},
    {"id": 12, "tableNumber": 4, "status": "FREE", "accessCode": "c", "qrCodeUrl": "d"},
]

CARDAPIO = [
    {
        "id": 2,
        "name": "Pizza Calabresa Grande",
        "description": "Calabresa e cebola",
        "category": "PIZZA",
        "price": 55.0,
        "available": True,
        "imageUrl": None,
    },
    {
        "id": 9,
        "name": "Água sem Gás",
        "description": "500 ml",
        "category": "DRINK",
        "price": 5.0,
        "available": True,
        "imageUrl": None,
    },
    {
        "id": 7,
        "name": "Pizza Quatro Queijos Grande",
        "description": "Indisponível",
        "category": "PIZZA",
        "price": 60.0,
        "available": False,
        "imageUrl": None,
    },
]

PEDIDO_CRIADO = {
    "id": 42,
    "tableId": 11,
    "status": "ABERTO",
    "totalAmount": 55.0,
    "createdAt": "2026-11-05T19:00:00Z",
    "items": [
        {
            "id": 1,
            "productId": 2,
            "productName": "Pizza Calabresa Grande",
            "quantity": 1,
            "unitPrice": 55.0,
            "subtotal": 55.0,
            "notes": "sem cebola",
        }
    ],
}

ITEM_VALIDO = {"produto_id": 2, "quantidade": 1, "observacoes": "sem cebola"}


@pytest.fixture
def ferramentas(api_falsa, api_client):
    api_falsa.rotas[MENU] = (200, CARDAPIO)
    api_falsa.rotas[MESAS_ROTA] = (200, MESAS)
    api_falsa.rotas[PEDIDOS] = (201, PEDIDO_CRIADO)
    return Ferramentas(api_client)


def assert_falhou_sem_criar(resultado, api_falsa):
    assert resultado["ok"] is False
    assert resultado["erro"]
    assert api_falsa.chamadas_de("POST") == []


def assert_mensagem_amigavel(mensagem):
    for termo in ("Traceback", "Exception", "http://", "127.0.0.1", "Error"):
        assert termo not in mensagem


# consultar_cardapio


def test_cardapio_devolve_so_id_nome_e_preco(ferramentas):
    assert ferramentas.consultar_cardapio() == {
        "ok": True,
        "itens": [
            {"id": 2, "nome": "Pizza Calabresa Grande", "preco": 55.0},
            {"id": 9, "nome": "Água sem Gás", "preco": 5.0},
        ],
    }


def test_cardapio_com_api_fora_do_ar():
    ferramentas = Ferramentas(ApiClient(Config("c", "m", "http://127.0.0.1:9", "t")))

    resultado = ferramentas.consultar_cardapio()

    assert resultado["ok"] is False
    assert_mensagem_amigavel(resultado["erro"])


@pytest.mark.parametrize("status", [401, 500])
def test_cardapio_com_erro_da_api(api_falsa, ferramentas, status):
    api_falsa.rotas[MENU] = (status, {})

    resultado = ferramentas.consultar_cardapio()

    assert resultado["ok"] is False
    assert_mensagem_amigavel(resultado["erro"])


def test_cardapio_com_resposta_em_formato_inesperado(api_falsa, ferramentas):
    api_falsa.rotas[MENU] = (200, [{"id": 1}])

    assert ferramentas.consultar_cardapio()["ok"] is False


# criar_pedido: caminho feliz


def test_cria_o_pedido_no_formato_exato_da_api(api_falsa, ferramentas):
    resultado = ferramentas.criar_pedido(3, [ITEM_VALIDO])

    assert api_falsa.chamadas_de("POST")[0]["corpo"] == {
        "tableId": 3,
        "items": [{"productId": 2, "quantity": 1, "notes": "sem cebola"}],
    }
    assert resultado == {
        "ok": True,
        "pedido_id": 42,
        "mesa_id": 3,
        "total": 55.0,
        "itens": [
            {
                "nome": "Pizza Calabresa Grande",
                "quantidade": 1,
                "subtotal": 55.0,
                "observacoes": "sem cebola",
            }
        ],
    }


def test_aceita_varios_itens_e_observacao_opcional(api_falsa, ferramentas):
    ferramentas.criar_pedido(
        3, [{"produto_id": 2, "quantidade": 2}, {"produto_id": 9, "quantidade": 1}]
    )

    assert api_falsa.chamadas_de("POST")[0]["corpo"]["items"] == [
        {"productId": 2, "quantity": 2, "notes": None},
        {"productId": 9, "quantity": 1, "notes": None},
    ]


def test_aceita_numeros_inteiros_enviados_como_decimal(api_falsa, ferramentas):
    # O JSON do modelo pode trazer 3.0 no lugar de 3.
    resultado = ferramentas.criar_pedido(3.0, [{"produto_id": 2.0, "quantidade": 1.0}])

    assert resultado["ok"] is True
    corpo = api_falsa.chamadas_de("POST")[0]["corpo"]
    assert corpo["tableId"] == 3
    assert corpo["items"][0]["productId"] == 2


def test_campos_a_mais_do_modelo_nao_chegam_a_api(api_falsa, ferramentas):
    # O preço vem sempre da API: o modelo não consegue dar desconto.
    ferramentas.criar_pedido(3, [{"produto_id": 2, "quantidade": 1, "preco": 0.01}])

    assert api_falsa.chamadas_de("POST")[0]["corpo"]["items"] == [
        {"productId": 2, "quantity": 1, "notes": None}
    ]


# criar_pedido: validação antes de chamar a API


def test_recusa_produto_inventado(api_falsa, ferramentas):
    resultado = ferramentas.criar_pedido(3, [{"produto_id": 999, "quantidade": 1}])

    assert_falhou_sem_criar(resultado, api_falsa)
    assert "999" in resultado["erro"]


def test_recusa_produto_indisponivel(api_falsa, ferramentas):
    resultado = ferramentas.criar_pedido(3, [{"produto_id": 7, "quantidade": 1}])

    assert_falhou_sem_criar(resultado, api_falsa)


def test_um_item_invalido_barra_o_pedido_inteiro(api_falsa, ferramentas):
    resultado = ferramentas.criar_pedido(3, [ITEM_VALIDO, {"produto_id": 999, "quantidade": 1}])

    assert_falhou_sem_criar(resultado, api_falsa)


@pytest.mark.parametrize("quantidade", [0, -1, 1.5, None, "muitas"])
def test_recusa_quantidade_invalida(api_falsa, ferramentas, quantidade):
    resultado = ferramentas.criar_pedido(3, [{"produto_id": 2, "quantidade": quantidade}])

    assert_falhou_sem_criar(resultado, api_falsa)
    assert "quantidade" in resultado["erro"]


@pytest.mark.parametrize("mesa", [None, 0, -1, "varanda"])
def test_recusa_mesa_nao_informada_ou_invalida(api_falsa, ferramentas, mesa):
    resultado = ferramentas.criar_pedido(mesa, [ITEM_VALIDO])

    assert_falhou_sem_criar(resultado, api_falsa)
    assert "mesa" in resultado["erro"]


@pytest.mark.parametrize("itens", [None, [], "uma pizza", [{"quantidade": 1}]])
def test_recusa_itens_invalidos(api_falsa, ferramentas, itens):
    resultado = ferramentas.criar_pedido(3, itens)

    assert_falhou_sem_criar(resultado, api_falsa)
    assert "item" in resultado["erro"]


# criar_pedido: erros da API


def test_404_pede_para_confirmar_a_mesa(api_falsa, ferramentas):
    api_falsa.rotas[PEDIDOS] = (404, {"status": 404, "error": "Not Found", "path": "/orders"})

    resultado = ferramentas.criar_pedido(99, [ITEM_VALIDO])

    assert resultado["ok"] is False
    assert "mesa" in resultado["erro"]
    assert_mensagem_amigavel(resultado["erro"])


@pytest.mark.parametrize("status", [400, 401, 403, 500, 502])
def test_outros_status_viram_mensagem_amigavel(api_falsa, ferramentas, status):
    api_falsa.rotas[PEDIDOS] = (status, {"status": status, "path": "/orders"})

    resultado = ferramentas.criar_pedido(3, [ITEM_VALIDO])

    assert resultado["ok"] is False
    assert "Nenhum pedido foi criado" in resultado["erro"]
    assert_mensagem_amigavel(resultado["erro"])


def test_api_fora_do_ar_na_validacao_nao_tenta_criar(api_falsa, ferramentas):
    api_falsa.rotas[MENU] = (500, {})

    resultado = ferramentas.criar_pedido(3, [ITEM_VALIDO])

    assert_falhou_sem_criar(resultado, api_falsa)
    assert resultado["erro"] == ERRO_INDISPONIVEL


def test_sem_resposta_ao_criar_avisa_que_o_resultado_e_incerto(api_falsa, ferramentas, monkeypatch):
    monkeypatch.setattr(modulo_api, "TIMEOUT_S", 0.3)
    api_falsa.rotas[PEDIDOS] = ApiFalsa.TRAVAR

    resultado = ferramentas.criar_pedido(3, [ITEM_VALIDO])

    assert resultado == {"ok": False, "erro": ERRO_RESULTADO_INCERTO}
    assert len(api_falsa.chamadas_de("POST")) == 1


def test_conexao_derrubada_ao_criar_nao_diz_que_falhou(api_falsa, ferramentas):
    api_falsa.rotas[PEDIDOS] = ApiFalsa.FECHAR

    assert ferramentas.criar_pedido(3, [ITEM_VALIDO])["erro"] == ERRO_RESULTADO_INCERTO


def test_resposta_estranha_ao_criar_e_resultado_incerto(api_falsa, ferramentas):
    api_falsa.rotas[PEDIDOS] = (201, {"inesperado": True})

    assert ferramentas.criar_pedido(3, [ITEM_VALIDO])["erro"] == ERRO_RESULTADO_INCERTO


# executar


def test_executar_consulta_o_cardapio(ferramentas):
    assert ferramentas.executar("consultar_cardapio", {})["ok"] is True


def test_executar_cria_o_pedido(ferramentas):
    resultado = ferramentas.executar("criar_pedido", {"mesa_id": 3, "itens": [ITEM_VALIDO]})

    assert resultado["pedido_id"] == 42


def test_executar_sem_argumentos_nao_quebra(api_falsa, ferramentas):
    assert_falhou_sem_criar(ferramentas.executar("criar_pedido", {}), api_falsa)


def test_executar_ferramenta_inventada_pelo_modelo(ferramentas):
    assert ferramentas.executar("dar_desconto", {"valor": 100})["ok"] is False


# declarações


def test_toda_ferramenta_declarada_existe():
    for declaracao in DECLARACOES:
        assert callable(getattr(Ferramentas, declaracao["nome"]))
        assert declaracao["descricao"]


def test_declaracao_de_criar_pedido_usa_os_mesmos_nomes_da_validacao(api_falsa, ferramentas):
    criar = next(d for d in DECLARACOES if d["nome"] == "criar_pedido")["parametros"]
    item = criar["properties"]["itens"]["items"]

    assert set(criar["required"]) == {"mesa_id", "itens"}
    assert set(item["properties"]) == {"produto_id", "quantidade", "observacoes"}

    resultado = ferramentas.executar(
        "criar_pedido",
        {"mesa_id": 3, "itens": [{nome: valor for nome, valor in ITEM_VALIDO.items() if nome in item["properties"]}]},
    )
    assert resultado["ok"] is True
