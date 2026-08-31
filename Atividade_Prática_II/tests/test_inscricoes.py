"""Testes de contrato do recurso inscricao e das regras de conflito."""

from conftest import OFICINA_VALIDA, codigo_de_erro, inscrever


def test_inscrever_devolve_201_com_location(cliente, oficina):
    corpo, _ = oficina

    resposta = inscrever(cliente, corpo["id"], "bruno@exemplo.com", "Bruno Lima")

    assert resposta.status_code == 201
    # A URI canonica da inscricao e de primeiro nivel: quem a recebe consegue
    # cancela-la sem precisar guardar tambem o identificador da oficina.
    assert resposta.headers["Location"] == f"/inscricoes/{resposta.json()['id']}"
    assert resposta.json()["status"] == "confirmada"


def test_inscricao_ocupa_vaga(cliente, oficina):
    corpo, _ = oficina
    inscrever(cliente, corpo["id"], "bruno@exemplo.com")

    atualizada = cliente.get(f"/oficinas/{corpo['id']}").json()

    assert atualizada["vagas_ocupadas"] == 1
    assert atualizada["vagas_disponiveis"] == corpo["vagas_totais"] - 1


def test_oficina_lotada_devolve_409(cliente):
    corpo = cliente.post(
        "/oficinas", json={**OFICINA_VALIDA, "vagas_totais": 1}
    ).json()
    inscrever(cliente, corpo["id"], "bruno@exemplo.com")

    resposta = inscrever(cliente, corpo["id"], "carla@exemplo.com")

    assert resposta.status_code == 409
    assert codigo_de_erro(resposta) == "oficina_lotada"


def test_email_duplicado_devolve_409(cliente, oficina):
    corpo, _ = oficina
    inscrever(cliente, corpo["id"], "bruno@exemplo.com")

    resposta = inscrever(cliente, corpo["id"], "bruno@exemplo.com")

    assert resposta.status_code == 409
    assert codigo_de_erro(resposta) == "inscricao_duplicada"


def test_email_e_comparado_sem_diferenciar_maiusculas(cliente, oficina):
    """Endereco de e-mail nao distingue caixa na parte do dominio, e tratar
    'Bruno@' como pessoa diferente de 'bruno@' permitiria burlar a unicidade."""
    corpo, _ = oficina
    inscrever(cliente, corpo["id"], "bruno@exemplo.com")

    resposta = inscrever(cliente, corpo["id"], "BRUNO@Exemplo.com")

    assert resposta.status_code == 409


def test_mesmo_email_em_oficinas_diferentes_e_permitido(cliente):
    """A unicidade vale por oficina, nao globalmente."""
    primeira = cliente.post("/oficinas", json=OFICINA_VALIDA).json()
    segunda = cliente.post("/oficinas", json=OFICINA_VALIDA).json()

    assert inscrever(cliente, primeira["id"], "bruno@exemplo.com").status_code == 201
    assert inscrever(cliente, segunda["id"], "bruno@exemplo.com").status_code == 201


def test_oficina_nao_aberta_devolve_409(cliente):
    corpo = cliente.post(
        "/oficinas", json={**OFICINA_VALIDA, "status": "rascunho"}
    ).json()

    resposta = inscrever(cliente, corpo["id"], "bruno@exemplo.com")

    assert resposta.status_code == 409
    assert codigo_de_erro(resposta) == "oficina_nao_aberta"


def test_email_invalido_devolve_422(cliente, oficina):
    corpo, _ = oficina

    resposta = inscrever(cliente, corpo["id"], "isto-nao-e-um-email")

    assert resposta.status_code == 422


def test_inscrever_em_oficina_inexistente_devolve_404(cliente):
    assert inscrever(cliente, 999, "bruno@exemplo.com").status_code == 404


def test_listar_inscricoes_de_oficina_inexistente_devolve_404(cliente):
    """404 e nao lista vazia: sao situacoes distintas e confundi-las esconde do
    cliente que ele esta consultando um identificador errado."""
    assert cliente.get("/oficinas/999/inscricoes").status_code == 404


def test_cancelar_libera_a_vaga(cliente):
    corpo = cliente.post(
        "/oficinas", json={**OFICINA_VALIDA, "vagas_totais": 1}
    ).json()
    inscricao = inscrever(cliente, corpo["id"], "bruno@exemplo.com").json()

    assert cliente.delete(f"/inscricoes/{inscricao['id']}").status_code == 204
    assert cliente.get(f"/oficinas/{corpo['id']}").json()["vagas_disponiveis"] == 1
    # Com a vaga liberada, outra pessoa consegue entrar.
    assert inscrever(cliente, corpo["id"], "carla@exemplo.com").status_code == 201


def test_cancelar_preserva_o_registro(cliente, oficina):
    corpo, _ = oficina
    inscricao = inscrever(cliente, corpo["id"], "bruno@exemplo.com").json()

    cliente.delete(f"/inscricoes/{inscricao['id']}")

    consulta = cliente.get(f"/inscricoes/{inscricao['id']}")
    assert consulta.status_code == 200
    assert consulta.json()["status"] == "cancelada"


def test_reativar_inscricao_cancelada_devolve_409(cliente, oficina):
    corpo, _ = oficina
    inscricao = inscrever(cliente, corpo["id"], "bruno@exemplo.com").json()
    cliente.delete(f"/inscricoes/{inscricao['id']}")

    resposta = cliente.patch(
        f"/inscricoes/{inscricao['id']}", json={"status": "presente"}
    )

    assert resposta.status_code == 409
    assert codigo_de_erro(resposta) == "transicao_invalida"


def test_marcar_presenca(cliente, oficina):
    corpo, _ = oficina
    inscricao = inscrever(cliente, corpo["id"], "bruno@exemplo.com").json()

    resposta = cliente.patch(
        f"/inscricoes/{inscricao['id']}", json={"status": "presente"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "presente"


def test_remover_oficina_com_inscritos_devolve_409(cliente, oficina):
    corpo, etag = oficina
    inscrever(cliente, corpo["id"], "bruno@exemplo.com")

    resposta = cliente.delete(f"/oficinas/{corpo['id']}", headers={"If-Match": etag})

    assert resposta.status_code == 409
    assert codigo_de_erro(resposta) == "oficina_com_inscricoes"


def test_reduzir_vagas_abaixo_do_ocupado_devolve_409(cliente, oficina):
    corpo, etag = oficina
    inscrever(cliente, corpo["id"], "bruno@exemplo.com")
    inscrever(cliente, corpo["id"], "carla@exemplo.com")

    resposta = cliente.patch(
        f"/oficinas/{corpo['id']}",
        json={"vagas_totais": 1},
        headers={"If-Match": etag},
    )

    assert resposta.status_code == 409
    assert codigo_de_erro(resposta) == "vagas_abaixo_do_ocupado"
