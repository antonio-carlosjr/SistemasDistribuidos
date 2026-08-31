"""Testes por propriedade e invariantes do dominio.

A secao 4.13 da apostila sugere ir alem do teste endpoint a endpoint e escrever
invariantes: propriedades que devem valer para qualquer sequencia de operacoes.
Testes assim pegam uma classe de defeito diferente -- nao "esta rota devolve o
status errado", mas "existe um caminho pelo qual o sistema chega a um estado
impossivel".
"""

from concurrent.futures import ThreadPoolExecutor

from conftest import OFICINA_VALIDA, inscrever


def test_apos_remover_o_recurso_esta_ausente(cliente, oficina):
    """Invariante: depois de DELETE, GET indica ausencia."""
    corpo, etag = oficina
    cliente.delete(f"/oficinas/{corpo['id']}", headers={"If-Match": etag})

    assert cliente.get(f"/oficinas/{corpo['id']}").status_code == 404
    assert cliente.get("/oficinas").json()["total"] == 0


def test_entrada_invalida_nao_persiste_estado(cliente):
    """Invariante: criar recurso invalido nunca deixa rastro.

    Uma requisicao rejeitada nao pode consumir identificador nem gravar dado
    parcial -- caso contrario o estado passa a depender do historico de
    tentativas fracassadas.
    """
    antes = cliente.get("/oficinas").json()["total"]

    cliente.post("/oficinas", json={"titulo": "x"})
    cliente.post("/oficinas", json={**OFICINA_VALIDA, "vagas_totais": -5})
    cliente.post("/oficinas", json={**OFICINA_VALIDA, "duracao_min": 1})

    assert cliente.get("/oficinas").json()["total"] == antes

    # O identificador tambem nao pode ter sido consumido pelas tentativas.
    criada = cliente.post("/oficinas", json=OFICINA_VALIDA)
    assert criada.json()["id"] == antes + 1


def test_put_identico_repetido_leva_ao_mesmo_estado(cliente, oficina):
    """Invariante: PUT e idempotente quanto ao estado final.

    A repeticao exige reler o ETag, ja que a precondicao consome a versao
    anterior. O que se verifica e que a representacao resultante e a mesma: a
    idempotencia de PUT esta no estado final do recurso, nao na igualdade das
    respostas nem na estabilidade do contador de versao.
    """
    corpo, etag = oficina
    novo = {**OFICINA_VALIDA, "titulo": "Titulo definitivo"}

    primeira = cliente.put(
        f"/oficinas/{corpo['id']}", json=novo, headers={"If-Match": etag}
    ).json()

    etag_atual = cliente.get(f"/oficinas/{corpo['id']}").headers["ETag"]
    segunda = cliente.put(
        f"/oficinas/{corpo['id']}", json=novo, headers={"If-Match": etag_atual}
    ).json()

    comparaveis = lambda representacao: {
        chave: valor for chave, valor in representacao.items() if chave != "versao"
    }
    assert comparaveis(primeira) == comparaveis(segunda)


def test_cancelamento_repetido_mantem_o_mesmo_estado(cliente, oficina):
    """Invariante: DELETE de inscricao e idempotente em efeito e em status."""
    corpo, _ = oficina
    inscricao = inscrever(cliente, corpo["id"], "bruno@exemplo.com").json()

    primeira = cliente.delete(f"/inscricoes/{inscricao['id']}")
    segunda = cliente.delete(f"/inscricoes/{inscricao['id']}")

    assert primeira.status_code == segunda.status_code == 204
    assert cliente.get(f"/inscricoes/{inscricao['id']}").json()["status"] == "cancelada"
    assert cliente.get(f"/oficinas/{corpo['id']}").json()["vagas_ocupadas"] == 0


def test_capacidade_nunca_e_excedida_sob_concorrencia(cliente):
    """Invariante central: inscricoes ativas nunca ultrapassam as vagas.

    Doze clientes disputam simultaneamente uma unica vaga. Sem exclusao mutua no
    repositorio, varios passariam pela verificacao de capacidade antes que
    qualquer um gravasse -- o padrao *check-then-act* -- e a oficina terminaria
    com mais inscritos do que vagas.

    A asercao verifica o estado final, e nao apenas a contagem de respostas: e o
    estado que precisa permanecer coerente.
    """
    corpo = cliente.post(
        "/oficinas", json={**OFICINA_VALIDA, "vagas_totais": 1}
    ).json()

    with ThreadPoolExecutor(max_workers=12) as executor:
        respostas = list(
            executor.map(
                lambda indice: inscrever(
                    cliente, corpo["id"], f"participante{indice}@exemplo.com"
                ),
                range(12),
            )
        )

    criadas = [r for r in respostas if r.status_code == 201]
    conflitos = [r for r in respostas if r.status_code == 409]

    assert len(criadas) == 1
    assert len(conflitos) == 11
    assert cliente.get(f"/oficinas/{corpo['id']}").json()["vagas_ocupadas"] == 1


def test_identificadores_nao_se_repetem_sob_concorrencia(cliente):
    """Invariante: a atribuicao de identificadores nao sofre corrida."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        respostas = list(
            executor.map(
                lambda indice: cliente.post(
                    "/oficinas", json={**OFICINA_VALIDA, "titulo": f"Oficina {indice}"}
                ),
                range(10),
            )
        )

    identificadores = [r.json()["id"] for r in respostas]

    assert len(set(identificadores)) == 10
    assert cliente.get("/oficinas?limite=100").json()["total"] == 10


def test_estado_sobrevive_a_nova_instancia_do_repositorio(cliente, oficina):
    """Invariante: o que a API confirmou como gravado esta no arquivo.

    Uma instancia nova le o mesmo arquivo, sem compartilhar memoria com a que
    respondeu a requisicao -- e o que distingue persistencia real de cache de
    processo.
    """
    from app.repositorio import Repositorio

    corpo, _ = oficina

    relida = Repositorio().obter_oficina(corpo["id"])

    assert relida.titulo == corpo["titulo"]
    assert relida.versao == corpo["versao"]
