"""Testa o llm_client com o SDK real contra um servidor local que imita o Gemini.

Nada sai da máquina e nenhuma chave real é usada.
"""

import http.server
import json
import re
import threading
from pathlib import Path

import pytest

import agente
from agente import llm_client
from agente.config import Config
from agente.llm_client import (
    MAX_TENTATIVAS,
    PROMPT_SISTEMA,
    TEMPERATURA,
    ChamadaFerramenta,
    LimiteExcedidoError,
    LLMClient,
    LLMError,
    Mensagem,
)
from agente.tools import DECLARACOES

CHAVE_FALSA = "chave-falsa-de-teste"
MODELO = "modelo-de-teste"
CONFIG = Config(CHAVE_FALSA, MODELO, "http://nao-usada", "nao-usado")
PERGUNTA = [Mensagem("usuario", "Oi")]

RESPOSTA_OK = (
    200,
    {"candidates": [{"content": {"role": "model", "parts": [{"text": "Olá!"}]}, "finishReason": "STOP"}]},
)
RESPOSTA_BLOQUEADA = (200, {"candidates": [{"finishReason": "SAFETY"}]})


def erro(codigo, status="ERRO", detalhes=None):
    corpo = {"code": codigo, "message": "mensagem", "status": status}
    if detalhes:
        corpo["details"] = detalhes
    return codigo, {"error": corpo}


ERRO_429 = erro(429, "RESOURCE_EXHAUSTED")
ERRO_503 = erro(503, "UNAVAILABLE")


def erro_429_com_espera(segundos):
    retry_info = {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": segundos}
    return erro(429, "RESOURCE_EXHAUSTED", [retry_info])


class GeminiFalso:
    """Servidor local que devolve as respostas do roteiro, na ordem."""

    TRAVAR = object()

    def __init__(self):
        self.roteiro = []
        self.chamadas = []
        self.liberar = threading.Event()
        falso = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                tamanho = int(self.headers["content-length"])
                falso.chamadas.append(
                    {"caminho": self.path, "corpo": json.loads(self.rfile.read(tamanho))}
                )
                acao = falso.roteiro.pop(0)
                if acao is GeminiFalso.TRAVAR:
                    falso.liberar.wait(5)
                    return
                status, dados = acao
                corpo = json.dumps(dados).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

        self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()


@pytest.fixture
def gemini(monkeypatch):
    falso = GeminiFalso()
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", f"http://127.0.0.1:{falso.servidor.server_port}")
    yield falso
    falso.liberar.set()
    falso.servidor.shutdown()
    falso.servidor.server_close()


@pytest.fixture
def esperas():
    return []


@pytest.fixture
def cliente(gemini, esperas):
    config = Config(
        gemini_api_key=CHAVE_FALSA,
        gemini_model=MODELO,
        api_base_url="http://nao-usada",
        api_token="nao-usado",
    )
    # Guarda as esperas em vez de dormir, para o teste não demorar.
    return LLMClient(config, dormir=esperas.append)


def test_devolve_o_texto_do_modelo(gemini, cliente):
    gemini.roteiro = [RESPOSTA_OK]

    assert cliente.gerar(PERGUNTA).texto == "Olá!"


def test_envia_modelo_prompt_temperatura_e_historico(gemini, cliente):
    gemini.roteiro = [RESPOSTA_OK]

    cliente.gerar(
        [
            Mensagem("usuario", "Oi"),
            Mensagem("modelo", "Olá! O que deseja?"),
            Mensagem("usuario", "Uma pizza"),
        ]
    )

    chamada = gemini.chamadas[0]
    corpo = chamada["corpo"]
    assert MODELO in chamada["caminho"]
    assert corpo["systemInstruction"]["parts"][0]["text"] == PROMPT_SISTEMA
    assert corpo["generationConfig"]["temperature"] == TEMPERATURA
    assert [c["role"] for c in corpo["contents"]] == ["user", "model", "user"]
    assert corpo["contents"][2]["parts"][0]["text"] == "Uma pizza"


def test_sem_ferramentas_nao_envia_tools(gemini, cliente):
    gemini.roteiro = [RESPOSTA_OK]

    cliente.gerar(PERGUNTA)

    assert "tools" not in gemini.chamadas[0]["corpo"]


def test_declara_as_ferramentas_para_o_gemini(gemini, esperas):
    gemini.roteiro = [RESPOSTA_OK]
    cliente = LLMClient(CONFIG, ferramentas=DECLARACOES, dormir=esperas.append)

    cliente.gerar(PERGUNTA)

    declaradas = gemini.chamadas[0]["corpo"]["tools"][0]["functionDeclarations"]
    assert [d["name"] for d in declaradas] == ["consultar_cardapio", "criar_pedido"]
    criar = declaradas[1]
    assert criar["description"]
    assert set(criar["parameters_json_schema"]["required"]) == {"mesa_numero", "itens"}


def test_devolve_a_chamada_de_ferramenta_pedida_pelo_modelo(gemini, cliente):
    argumentos = {"mesa_numero": 3, "itens": [{"produto_id": 2, "quantidade": 1}]}
    parte = {"functionCall": {"name": "criar_pedido", "args": argumentos}}
    gemini.roteiro = [
        (200, {"candidates": [{"content": {"role": "model", "parts": [parte]}, "finishReason": "STOP"}]})
    ]

    resposta = cliente.gerar(PERGUNTA)

    assert resposta.texto == ""
    assert resposta.chamadas == (ChamadaFerramenta("criar_pedido", argumentos),)


def test_chamada_sem_argumentos_vira_dicionario_vazio(gemini, cliente):
    parte = {"functionCall": {"name": "consultar_cardapio"}}
    gemini.roteiro = [
        (200, {"candidates": [{"content": {"role": "model", "parts": [parte]}, "finishReason": "STOP"}]})
    ]

    assert cliente.gerar(PERGUNTA).chamadas == (ChamadaFerramenta("consultar_cardapio", {}),)


def test_temperatura_e_baixa():
    assert 0 <= TEMPERATURA <= 0.3


def test_429_tenta_de_novo_e_devolve_a_resposta(gemini, cliente, esperas):
    gemini.roteiro = [ERRO_429, ERRO_429, RESPOSTA_OK]

    assert cliente.gerar(PERGUNTA).texto == "Olá!"
    assert len(gemini.chamadas) == 3
    assert len(esperas) == 2


def test_429_sem_parar_desiste_no_maximo_de_tentativas(gemini, cliente, esperas):
    gemini.roteiro = [ERRO_429] * (MAX_TENTATIVAS + 2)

    with pytest.raises(LimiteExcedidoError):
        cliente.gerar(PERGUNTA)

    assert len(gemini.chamadas) == MAX_TENTATIVAS
    assert len(esperas) == MAX_TENTATIVAS - 1


def test_503_tenta_de_novo_e_devolve_a_resposta(gemini, cliente, esperas):
    gemini.roteiro = [ERRO_503, ERRO_503, RESPOSTA_OK]

    assert cliente.gerar(PERGUNTA).texto == "Olá!"
    assert len(gemini.chamadas) == 3
    assert len(esperas) == 2


def test_503_sem_parar_desiste_e_nao_e_limite_excedido(gemini, cliente, esperas):
    gemini.roteiro = [ERRO_503] * (MAX_TENTATIVAS + 2)

    with pytest.raises(LLMError) as capturado:
        cliente.gerar(PERGUNTA)

    assert not isinstance(capturado.value, LimiteExcedidoError)
    assert len(gemini.chamadas) == MAX_TENTATIVAS
    assert len(esperas) == MAX_TENTATIVAS - 1


def test_alterna_429_e_503_ate_conseguir(gemini, cliente, esperas):
    gemini.roteiro = [ERRO_429, ERRO_503, RESPOSTA_OK]

    assert cliente.gerar(PERGUNTA).texto == "Olá!"
    assert len(esperas) == 2


def test_espera_e_crescente(gemini, cliente, esperas):
    gemini.roteiro = [ERRO_429] * MAX_TENTATIVAS

    with pytest.raises(LimiteExcedidoError):
        cliente.gerar(PERGUNTA)

    assert esperas == sorted(esperas)
    assert esperas[0] < esperas[-1]


def test_respeita_a_espera_sugerida_pelo_gemini(gemini, cliente, esperas):
    gemini.roteiro = [erro_429_com_espera("37s"), RESPOSTA_OK]

    cliente.gerar(PERGUNTA)

    assert esperas == [37.0]


def test_espera_longa_demais_desiste_sem_aguardar(gemini, cliente, esperas):
    gemini.roteiro = [erro_429_com_espera("3600s"), RESPOSTA_OK]

    with pytest.raises(LimiteExcedidoError):
        cliente.gerar(PERGUNTA)

    assert len(gemini.chamadas) == 1
    assert esperas == []


def test_espera_sugerida_invalida_usa_o_backoff(gemini, cliente, esperas):
    gemini.roteiro = [erro_429_com_espera("logo"), RESPOSTA_OK]

    assert cliente.gerar(PERGUNTA).texto == "Olá!"
    assert len(esperas) == 1


@pytest.mark.parametrize("codigo", [400, 403, 500])
def test_outros_erros_nao_tentam_de_novo(gemini, cliente, esperas, codigo):
    gemini.roteiro = [erro(codigo), RESPOSTA_OK]

    with pytest.raises(LLMError) as capturado:
        cliente.gerar(PERGUNTA)

    assert not isinstance(capturado.value, LimiteExcedidoError)
    assert len(gemini.chamadas) == 1
    assert esperas == []


def test_erro_nao_expoe_a_chave(gemini, cliente):
    gemini.roteiro = [erro(403)]

    with pytest.raises(LLMError) as capturado:
        cliente.gerar(PERGUNTA)

    assert CHAVE_FALSA not in str(capturado.value)


def test_resposta_bloqueada_vira_erro(gemini, cliente):
    gemini.roteiro = [RESPOSTA_BLOQUEADA]

    with pytest.raises(LLMError):
        cliente.gerar(PERGUNTA)


def test_timeout_vira_erro(gemini, esperas, monkeypatch):
    monkeypatch.setattr(llm_client, "TIMEOUT_MS", 300)
    config = Config(CHAVE_FALSA, MODELO, "http://nao-usada", "nao-usado")
    cliente = LLMClient(config, dormir=esperas.append)
    gemini.roteiro = [GeminiFalso.TRAVAR]

    with pytest.raises(LLMError):
        cliente.gerar(PERGUNTA)


def test_conexao_recusada_vira_erro(esperas, monkeypatch):
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "http://127.0.0.1:9")
    config = Config(CHAVE_FALSA, MODELO, "http://nao-usada", "nao-usado")
    cliente = LLMClient(config, dormir=esperas.append)

    with pytest.raises(LLMError):
        cliente.gerar(PERGUNTA)


def test_so_o_llm_client_importa_a_biblioteca_do_gemini():
    importa_gemini = re.compile(r"^\s*(from|import)\s+google(\.genai)?\b", re.MULTILINE)
    pasta = Path(agente.__file__).parent

    arquivos = [
        arquivo.name
        for arquivo in pasta.rglob("*.py")
        if importa_gemini.search(arquivo.read_text(encoding="utf-8"))
    ]

    assert arquivos == ["llm_client.py"]
