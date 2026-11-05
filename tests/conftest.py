"""Servidor local que imita a API da pizzaria. Nada sai da máquina."""

import http.server
import json
import threading

import pytest

from agente.api_client import ApiClient
from agente.config import Config

TOKEN_FALSO = "token-falso-de-teste"


class ApiFalsa:
    """Responde conforme o dicionário de rotas e registra as chamadas recebidas.

    Cada rota aponta para (status, corpo). Se o corpo for texto, é enviado como está.
    TRAVAR faz o servidor não responder, e FECHAR derruba a conexão sem responder.
    """

    TRAVAR = "travar"
    FECHAR = "fechar"

    def __init__(self):
        self.rotas = {}
        self.chamadas = []
        self.liberar = threading.Event()
        falsa = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _responder(self):
                tamanho = int(self.headers.get("content-length") or 0)
                bruto = self.rfile.read(tamanho)
                falsa.chamadas.append(
                    {
                        "metodo": self.command,
                        "rota": self.path,
                        "autorizacao": self.headers.get("authorization"),
                        "corpo": json.loads(bruto) if bruto else None,
                    }
                )
                acao = falsa.rotas[(self.command, self.path)]
                if acao == ApiFalsa.TRAVAR:
                    falsa.liberar.wait(5)
                    return
                if acao == ApiFalsa.FECHAR:
                    self.close_connection = True
                    return

                status, dados = acao
                corpo = dados.encode() if isinstance(dados, str) else json.dumps(dados).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            do_GET = _responder
            do_POST = _responder

        self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.servidor.server_port}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def chamadas_de(self, metodo):
        return [chamada for chamada in self.chamadas if chamada["metodo"] == metodo]


@pytest.fixture
def api_falsa():
    falsa = ApiFalsa()
    yield falsa
    falsa.liberar.set()
    falsa.servidor.shutdown()
    falsa.servidor.server_close()


@pytest.fixture
def api_client(api_falsa):
    return ApiClient(Config("chave-falsa", "modelo-falso", api_falsa.url, TOKEN_FALSO))
