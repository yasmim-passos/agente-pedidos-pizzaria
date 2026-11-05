"""Conversa com o agente pelo terminal: python -m agente.cli"""

import argparse
import logging

from agente.agent import Agente
from agente.api_client import ApiClient
from agente.config import ConfigError, carregar_config
from agente.llm_client import LLMClient
from agente.tools import DECLARACOES, Ferramentas

COMANDOS_DE_SAIDA = {"sair", "exit", "quit"}


def conversar(agente, ler=input, escrever=print):
    escrever("Atendente da pizzaria. Digite 'sair' para encerrar.")
    while True:
        try:
            mensagem = ler("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if mensagem.lower() in COMANDOS_DE_SAIDA:
            break
        if mensagem:
            escrever(f"Atendente: {agente.responder('terminal', mensagem)}")


def main():
    parser = argparse.ArgumentParser(description="Agente de pedidos da pizzaria")
    parser.add_argument("-v", "--verbose", action="store_true", help="mostra cada passo do agente")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("agente").setLevel(logging.INFO if args.verbose else logging.WARNING)

    try:
        config = carregar_config()
    except ConfigError as erro:
        raise SystemExit(str(erro))

    agente = Agente(LLMClient(config, ferramentas=DECLARACOES), Ferramentas(ApiClient(config)))
    conversar(agente)


if __name__ == "__main__":
    main()
