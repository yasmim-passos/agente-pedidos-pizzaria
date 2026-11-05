"""Gera um JWT de DESENVOLVIMENTO para a API da pizzaria e grava no .env.

O serviço de autenticação do LAB06 não está no docker compose. A API só confere
a assinatura com uma chave pública, então, em ambiente local, este script cria um
par de chaves próprio e assina o token que o serviço de auth emitiria.

Uso: python scripts/gerar_token_dev.py [--horas 24] [--chaves CAMINHO]
"""

import argparse
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import set_key

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO_ENV = RAIZ / ".env"
ARQUIVO_EXEMPLO = RAIZ / ".env.example"

# A pasta keys/ já é ignorada pelo Git do backend. A chave privada nunca fica neste repositório.
PASTA_CHAVES = RAIZ.parent / "backend-spring" / "keys"

# Valores que a API exige (SecurityConfig e JwtContractValidator).
EMISSOR = "restaurant-auth"
SUJEITO = "agente-pedidos"

# Empresa fictícia: precisa ser a mesma do scripts/seed_dev.sql.
EMPRESA_DEV = "550e8400-e29b-41d4-a716-446655440000"


def garantir_chaves(pasta: Path) -> bytes:
    """Devolve a chave privada, criando o par de chaves se ainda não existir."""
    arquivo_privada = pasta / "pizzaria-api-private.pem"
    arquivo_publica = pasta / "pizzaria-api-public.pem"

    if not arquivo_privada.exists():
        pasta.mkdir(parents=True, exist_ok=True)
        chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        arquivo_privada.write_bytes(
            chave.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        arquivo_publica.write_bytes(
            chave.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        print(f"Par de chaves criado em {pasta}")

    return arquivo_privada.read_bytes()


def gerar_token(chave_privada: bytes, horas: int) -> str:
    agora = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": EMISSOR,
            "sub": SUJEITO,
            "empresa_id": EMPRESA_DEV,
            "iat": agora,
            "exp": agora + timedelta(hours=horas),
        },
        chave_privada,
        algorithm="RS256",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horas", type=int, default=24, help="validade do token")
    parser.add_argument("--chaves", type=Path, default=PASTA_CHAVES, help="pasta das chaves")
    args = parser.parse_args()

    if not ARQUIVO_ENV.exists():
        shutil.copy(ARQUIVO_EXEMPLO, ARQUIVO_ENV)

    token = gerar_token(garantir_chaves(args.chaves), args.horas)
    set_key(ARQUIVO_ENV, "API_TOKEN", token, quote_mode="never")

    # O token não é impresso de propósito, para não parar em logs do terminal.
    print(f"API_TOKEN gravado no .env (válido por {args.horas} h).")


if __name__ == "__main__":
    main()
