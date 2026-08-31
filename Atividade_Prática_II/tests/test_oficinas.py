"""Testes de contrato do recurso oficina."""

from conftest import OFICINA_VALIDA, codigo_de_erro


def test_criar_devolve_201_com_location_e_etag(cliente):
    resposta = cliente.post("/oficinas", json=OFICINA_VALIDA)

    assert resposta.status_code == 201
    corpo = resposta.json()
    # 201 deve informar onde o recurso passou a existir: sem Location o cliente
    # teria de deduzir a URI a partir do corpo, acoplando-se ao formato do id.
    assert resposta.headers["Location"] == f"/oficinas/{corpo['id']}"
    assert resposta.headers["ETag"] == '"1"'
    assert corpo["vagas_ocupadas"] == 0
    assert corpo["vagas_disponiveis"] == OFICINA_VALIDA["vagas_totais"]


def test_criar_duas_vezes_gera_dois_recursos(cliente):
    """POST nao e idempotente: a repeticao acrescenta um recurso."""
    primeira = cliente.post("/oficinas", json=OFICINA_VALIDA)
    segunda = cliente.post("/oficinas", json=OFICINA_VALIDA)

    assert primeira.json()["id"] != segunda.json()["id"]
    assert cliente.get("/oficinas").json()["total"] == 2


def test_entrada_invalida_devolve_422(cliente):
    resposta = cliente.post("/oficinas", json={**OFICINA_VALIDA, "titulo": "ab"})

    assert resposta.status_code == 422
    assert codigo_de_erro(resposta) == "entrada_invalida"


def test_campo_desconhecido_devolve_422(cliente):
    """Campo nao previsto e erro, nao silencio.

    Aceitar e ignorar faria o cliente acreditar numa alteracao que nunca
    aconteceu -- falha silenciosa e pior que erro explicito.
    """
    resposta = cliente.post("/oficinas", json={**OFICINA_VALIDA, "vagas": 10})

    assert resposta.status_code == 422


def test_obter_inexistente_devolve_404(cliente):
    resposta = cliente.get("/oficinas/999")

    assert resposta.status_code == 404
    assert codigo_de_erro(resposta) == "nao_encontrado"


def test_listagem_respeita_limite_e_offset(cliente):
    for indice in range(5):
        cliente.post("/oficinas", json={**OFICINA_VALIDA, "titulo": f"Oficina {indice}"})

    pagina = cliente.get("/oficinas?limite=2&offset=2").json()

    assert pagina["total"] == 5
    assert len(pagina["itens"]) == 2
    assert pagina["offset"] == 2


def test_limite_acima_do_teto_devolve_422(cliente):
    """O teto de paginacao e parte do contrato, nao uma sugestao."""
    assert cliente.get("/oficinas?limite=1000").status_code == 422


def test_filtro_por_status(cliente):
    cliente.post("/oficinas", json=OFICINA_VALIDA)
    cliente.post("/oficinas", json={**OFICINA_VALIDA, "status": "rascunho"})

    assert cliente.get("/oficinas?status=aberta").json()["total"] == 1


def test_substituir_exige_if_match(cliente, oficina):
    corpo, _ = oficina

    resposta = cliente.put(f"/oficinas/{corpo['id']}", json=OFICINA_VALIDA)

    assert resposta.status_code == 428
    assert codigo_de_erro(resposta) == "precondicao_obrigatoria"


def test_substituir_com_etag_obsoleto_devolve_412(cliente, oficina):
    corpo, etag = oficina
    cliente.put(
        f"/oficinas/{corpo['id']}",
        json={**OFICINA_VALIDA, "titulo": "Primeira alteracao"},
        headers={"If-Match": etag},
    )

    # Segundo cliente ainda trabalha com a versao anterior.
    resposta = cliente.put(
        f"/oficinas/{corpo['id']}",
        json={**OFICINA_VALIDA, "titulo": "Segunda alteracao"},
        headers={"If-Match": etag},
    )

    assert resposta.status_code == 412
    assert cliente.get(f"/oficinas/{corpo['id']}").json()["titulo"] == "Primeira alteracao"


def test_substituir_incrementa_a_versao(cliente, oficina):
    corpo, etag = oficina

    resposta = cliente.put(
        f"/oficinas/{corpo['id']}",
        json={**OFICINA_VALIDA, "titulo": "Titulo revisado"},
        headers={"If-Match": etag},
    )

    assert resposta.status_code == 200
    assert resposta.headers["ETag"] == '"2"'


def test_if_match_curinga_e_aceito(cliente, oficina):
    corpo, _ = oficina

    resposta = cliente.patch(
        f"/oficinas/{corpo['id']}",
        json={"titulo": "Alterado com curinga"},
        headers={"If-Match": "*"},
    )

    assert resposta.status_code == 200


def test_if_none_match_devolve_304(cliente, oficina):
    corpo, etag = oficina

    resposta = cliente.get(f"/oficinas/{corpo['id']}", headers={"If-None-Match": etag})

    assert resposta.status_code == 304
    assert resposta.content == b""


def test_if_none_match_obsoleto_devolve_representacao(cliente, oficina):
    corpo, _ = oficina

    resposta = cliente.get(f"/oficinas/{corpo['id']}", headers={"If-None-Match": '"0"'})

    assert resposta.status_code == 200


def test_patch_altera_apenas_o_campo_enviado(cliente, oficina):
    corpo, etag = oficina

    resultado = cliente.patch(
        f"/oficinas/{corpo['id']}",
        json={"titulo": "Somente o titulo muda"},
        headers={"If-Match": etag},
    ).json()

    assert resultado["titulo"] == "Somente o titulo muda"
    assert resultado["instrutor"] == corpo["instrutor"]


def test_transicao_de_status_invalida_devolve_409(cliente, oficina):
    corpo, etag = oficina

    resposta = cliente.patch(
        f"/oficinas/{corpo['id']}",
        json={"status": "rascunho"},
        headers={"If-Match": etag},
    )

    assert resposta.status_code == 409
    assert codigo_de_erro(resposta) == "transicao_invalida"


def test_remover_devolve_204_e_depois_404(cliente, oficina):
    corpo, etag = oficina

    assert cliente.delete(f"/oficinas/{corpo['id']}", headers={"If-Match": etag}).status_code == 204
    # Efeito idempotente, status diferente: o recurso segue ausente nas duas
    # chamadas, mas a segunda relata que nao havia o que remover.
    assert cliente.delete(f"/oficinas/{corpo['id']}", headers={"If-Match": "*"}).status_code == 404
