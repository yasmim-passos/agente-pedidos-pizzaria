import pytest

from agente.config import VARIAVEIS_OBRIGATORIAS, ConfigError, carregar_config

ENV_COMPLETO = """\
GEMINI_API_KEY=chave-falsa
GEMINI_MODEL=modelo-falso
API_BASE_URL=http://api.teste/
API_TOKEN=token-falso
"""


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    """Garante que os testes não leiam variáveis reais da máquina."""
    for nome in VARIAVEIS_OBRIGATORIAS:
        monkeypatch.delenv(nome, raising=False)


@pytest.fixture
def arquivo_env(tmp_path):
    return tmp_path / ".env"


def test_le_todas_as_variaveis_do_arquivo(arquivo_env):
    arquivo_env.write_text(ENV_COMPLETO, encoding="utf-8")

    config = carregar_config(arquivo_env)

    assert config.gemini_api_key == "chave-falsa"
    assert config.gemini_model == "modelo-falso"
    assert config.api_token == "token-falso"


def test_remove_barra_final_da_url(arquivo_env):
    arquivo_env.write_text(ENV_COMPLETO, encoding="utf-8")

    assert carregar_config(arquivo_env).api_base_url == "http://api.teste"


def test_variavel_de_ambiente_tem_prioridade_sobre_o_arquivo(arquivo_env, monkeypatch):
    arquivo_env.write_text(ENV_COMPLETO, encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "modelo-do-ambiente")

    assert carregar_config(arquivo_env).gemini_model == "modelo-do-ambiente"


def test_erro_lista_todas_as_variaveis_faltando(arquivo_env):
    arquivo_env.write_text("GEMINI_MODEL=modelo-falso\nAPI_TOKEN=\n", encoding="utf-8")

    with pytest.raises(ConfigError) as erro:
        carregar_config(arquivo_env)

    mensagem = str(erro.value)
    assert "GEMINI_API_KEY" in mensagem
    assert "API_BASE_URL" in mensagem
    assert "API_TOKEN" in mensagem
    assert "GEMINI_MODEL" not in mensagem


def test_arquivo_inexistente_gera_erro_de_configuracao(arquivo_env):
    with pytest.raises(ConfigError):
        carregar_config(arquivo_env)


def test_repr_nao_expoe_segredos(arquivo_env):
    arquivo_env.write_text(ENV_COMPLETO, encoding="utf-8")

    texto = repr(carregar_config(arquivo_env))

    assert "chave-falsa" not in texto
    assert "token-falso" not in texto
