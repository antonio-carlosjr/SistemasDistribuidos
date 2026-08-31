"""Configuracao comum dos testes.

As variaveis de ambiente sao definidas antes de importar a aplicacao porque o
repositorio le o caminho do arquivo no momento da importacao. Apontar o estado
para um diretorio temporario mantem os testes isolados dos dados de
demonstracao -- rodar a suite nunca apaga o que foi semeado para a apresentacao.
"""

import os
import tempfile

import pytest

_TEMPORARIO = tempfile.mkdtemp(prefix="ap2-testes-")
os.environ["OFICINAS_DB"] = os.path.join(_TEMPORARIO, "estado.json")
os.environ["OFICINAS_LOG"] = os.path.join(_TEMPORARIO, "servidor.log")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import EstadoOperacional, app  # noqa: E402
from app.repositorio import repositorio  # noqa: E402

OFICINA_VALIDA = {
    "titulo": "Introducao a Kubernetes",
    "instrutor": "Ana Reis",
    "vagas_totais": 3,
    "inicio": "2026-09-10T14:00:00Z",
    "duracao_min": 180,
    "status": "aberta",
}


@pytest.fixture
def cliente():
    """Cliente com estado limpo.

    Zerar o repositorio a cada teste garante independencia de ordem: um teste
    que falha nao pode derrubar os seguintes por deixar estado residual.
    """
    repositorio.redefinir()
    EstadoOperacional.em_manutencao = False
    with TestClient(app) as instancia:
        yield instancia


@pytest.fixture
def oficina(cliente):
    """Cria uma oficina aberta e devolve sua representacao mais o ETag."""
    resposta = cliente.post("/oficinas", json=OFICINA_VALIDA)
    assert resposta.status_code == 201
    return resposta.json(), resposta.headers["ETag"]


def inscrever(cliente, oficina_id, email, nome="Participante Teste"):
    return cliente.post(
        f"/oficinas/{oficina_id}/inscricoes",
        json={"participante_nome": nome, "participante_email": email},
    )


def codigo_de_erro(resposta):
    return resposta.json()["erro"]["codigo"]
