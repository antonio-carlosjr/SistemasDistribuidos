"""API REST de inscricoes em oficinas -- AP2 de Sistemas Distribuidos.

A aplicacao expoe duas colecoes relacionadas, `/oficinas` e as `/inscricoes` de
cada oficina, e um pequeno conjunto de rotas operacionais que existem para
tornar reproduziveis os experimentos da secao 4.8 da apostila.
"""

import time
import uuid
from typing import Optional

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import config, observabilidade
from .erros import ErroDominio, PrecondicaoFalhou
from .modelos import (
    Inscricao,
    InscricaoEntrada,
    InscricaoPatch,
    Oficina,
    OficinaEntrada,
    OficinaPatch,
    PaginaInscricoes,
    PaginaOficinas,
    StatusOficina,
)
from .repositorio import QUALQUER_VERSAO, repositorio

app = FastAPI(
    title="API de Inscricoes em Oficinas",
    version="1.0",
    description=(
        "AP2 -- Sistemas Distribuidos. Colecoes relacionadas de oficinas e "
        "inscricoes, com controle otimista de concorrencia via ETag/If-Match."
    ),
)


def _corpo_erro(codigo: str, mensagem: str, request_id: str) -> dict:
    """Formato unico de erro para toda a API.

    Um envelope estavel permite ao cliente tratar falhas sem inspecionar o texto
    da mensagem, e carregar o `request_id` na resposta liga o erro visto pelo
    cliente a linha correspondente no log do servidor.
    """
    return {"erro": {"codigo": codigo, "mensagem": mensagem, "request_id": request_id}}


@app.middleware("http")
async def correlacionar_e_registrar(request: Request, chamar_proxima):
    """Atribui identificador de correlacao e mede a duracao de cada requisicao."""
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id

    inicio = time.perf_counter()
    try:
        resposta = await chamar_proxima(request)
    except Exception as excecao:
        # Falha nao prevista: registra e devolve 500 sem expor o rastreamento.
        # A secao 4.12 pede que mensagens de erro nao revelem detalhes internos.
        duracao_ms = (time.perf_counter() - inicio) * 1000
        observabilidade.registrar_requisicao(
            request_id,
            request.method,
            request.url.path,
            500,
            duracao_ms,
            erro=type(excecao).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=_corpo_erro(
                "erro_interno", "Erro inesperado no servidor", request_id
            ),
            headers={"X-Request-Id": request_id},
        )

    duracao_ms = (time.perf_counter() - inicio) * 1000
    resposta.headers["X-Request-Id"] = request_id
    observabilidade.registrar_requisicao(
        request_id, request.method, request.url.path, resposta.status_code, duracao_ms
    )
    return resposta


@app.exception_handler(ErroDominio)
async def tratar_erro_dominio(request: Request, excecao: ErroDominio):
    """Traduz falhas esperadas do dominio em respostas HTTP descritivas."""
    request_id = getattr(request.state, "request_id", "-")
    cabecalhos = {}

    # 503 acompanha Retry-After: o cliente recebe uma resposta e sabe quando
    # tentar de novo -- diferente de uma falha de conectividade, em que nao ha
    # resposta alguma para interpretar.
    if excecao.status == 503:
        cabecalhos["Retry-After"] = "5"

    return JSONResponse(
        status_code=excecao.status,
        content=_corpo_erro(excecao.codigo, excecao.mensagem, request_id),
        headers=cabecalhos,
    )


@app.exception_handler(RequestValidationError)
async def tratar_erro_validacao(request: Request, excecao: RequestValidationError):
    """422 -- a representacao enviada nao satisfaz as restricoes do modelo.

    Distinto de 409: aqui o problema esta no corpo da requisicao, nao no estado
    do servidor. A mesma requisicao seria rejeitada em qualquer instante.
    """
    request_id = getattr(request.state, "request_id", "-")
    problemas = [
        {
            "campo": ".".join(str(parte) for parte in problema["loc"][1:]),
            "motivo": problema["msg"],
        }
        for problema in excecao.errors()
    ]
    corpo = _corpo_erro("entrada_invalida", "Representacao invalida", request_id)
    corpo["erro"]["problemas"] = problemas
    return JSONResponse(status_code=422, content=corpo)


# ----------------------------------------------------------------------
# Validacao condicional: ETag, If-Match e If-None-Match
# ----------------------------------------------------------------------


def etag_de(oficina: Oficina) -> str:
    """Deriva o ETag da versao do recurso.

    Um contador de versao serve melhor que o hash da representacao: ele muda a
    cada escrita mesmo quando a escrita repoe os mesmos valores, o que preserva
    a nocao de "houve alteracao concorrente" que o controle otimista precisa.
    """
    return f'"{oficina.versao}"'


def versao_do_if_match(if_match: Optional[str]) -> Optional[int]:
    """Converte o cabecalho `If-Match` na versao que o cliente supoe vigente.

    Retorna `None` quando o cabecalho esta ausente, o que a camada de dominio
    trata como 428. Um valor ilegivel vira `PrecondicaoFalhou` (412), e nao 400:
    o cabecalho foi enviado e simplesmente nao corresponde a nenhuma versao
    existente, que e exatamente o que 412 comunica.
    """
    if if_match is None:
        return None

    valor = if_match.strip()
    if valor == "*":
        return QUALQUER_VERSAO

    # Aceita a forma fraca (W/"3") por tolerancia, ainda que a API so emita
    # validadores fortes.
    if valor.startswith("W/"):
        valor = valor[2:]
    valor = valor.strip('"')

    try:
        return int(valor)
    except ValueError:
        raise PrecondicaoFalhou(f"ETag {if_match!r} nao corresponde a nenhuma versao")


# ----------------------------------------------------------------------
# Oficinas
# ----------------------------------------------------------------------


@app.get("/oficinas", response_model=PaginaOficinas, tags=["oficinas"])
def listar_oficinas(
    status_oficina: Optional[StatusOficina] = Query(default=None, alias="status"),
    limite: int = Query(default=config.LIMITE_PADRAO, ge=1, le=config.LIMITE_MAXIMO),
    offset: int = Query(default=0, ge=0),
):
    """Lista oficinas com paginacao obrigatoria.

    O teto em `limite` e deliberado: a secao 4.10 aponta listagens sem limite
    como erro comum, porque o custo da resposta cresce junto com a colecao ate
    consumir memoria e banda de forma imprevisivel.
    """
    total, itens = repositorio.listar_oficinas(status_oficina, limite, offset)
    return PaginaOficinas(total=total, limite=limite, offset=offset, itens=itens)


@app.post("/oficinas", response_model=Oficina, status_code=201, tags=["oficinas"])
def criar_oficina(entrada: OficinaEntrada, resposta: Response):
    """Cria uma oficina.

    Repetir esta requisicao cria um segundo recurso, distinto do primeiro: POST
    nao e idempotente. O contraste com `POST /oficinas/{id}/inscricoes`, que
    responde 409 na repeticao, esta discutido em `docs/analise.md`.
    """
    oficina = repositorio.criar_oficina(entrada)
    resposta.headers["Location"] = f"/oficinas/{oficina.id}"
    resposta.headers["ETag"] = etag_de(oficina)
    return oficina


@app.get("/oficinas/{oficina_id}", response_model=Oficina, tags=["oficinas"])
def obter_oficina(
    oficina_id: int,
    resposta: Response,
    if_none_match: Optional[str] = Header(default=None, alias="If-None-Match"),
):
    """Obtem uma oficina, com suporte a validacao condicional.

    Quando o cliente informa `If-None-Match` com o ETag que ja possui e nada
    mudou, a resposta e 304 sem corpo: economiza banda mantendo a garantia de
    que o cliente nao esta usando dado obsoleto sem saber.
    """
    oficina = repositorio.obter_oficina(oficina_id)
    etag = etag_de(oficina)

    if if_none_match is not None and if_none_match.strip().strip('"') == str(
        oficina.versao
    ):
        return Response(status_code=304, headers={"ETag": etag})

    resposta.headers["ETag"] = etag
    resposta.headers["Cache-Control"] = "no-cache"
    return oficina


@app.put("/oficinas/{oficina_id}", response_model=Oficina, tags=["oficinas"])
def substituir_oficina(
    oficina_id: int,
    entrada: OficinaEntrada,
    resposta: Response,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
):
    """Substitui a representacao completa da oficina.

    Exige `If-Match`. Sem a precondicao, dois clientes que leram a mesma versao
    sobrescreveriam um ao outro sem que nenhum percebesse -- a perda de
    atualizacao da secao 4.6. Com ela, o segundo recebe 412 e pode reler e
    decidir o que fazer.

    Repetir a mesma requisicao com o ETag ja consumido devolve 412, e nao um
    segundo efeito. A idempotencia de PUT esta no estado final do recurso, nao
    na igualdade das respostas.
    """
    oficina = repositorio.substituir_oficina(
        oficina_id, entrada, versao_do_if_match(if_match)
    )
    resposta.headers["ETag"] = etag_de(oficina)
    return oficina


@app.patch("/oficinas/{oficina_id}", response_model=Oficina, tags=["oficinas"])
def atualizar_oficina(
    oficina_id: int,
    patch: OficinaPatch,
    resposta: Response,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
):
    """Altera parcialmente a oficina.

    Diferente do PUT, o corpo carrega apenas os campos a mudar, o que reduz o
    acoplamento: o cliente nao precisa conhecer a representacao inteira nem
    reenviar campos que nao lhe dizem respeito.
    """
    oficina = repositorio.atualizar_oficina(
        oficina_id, patch, versao_do_if_match(if_match)
    )
    resposta.headers["ETag"] = etag_de(oficina)
    return oficina


@app.delete("/oficinas/{oficina_id}", status_code=204, tags=["oficinas"])
def remover_oficina(
    oficina_id: int,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
):
    """Remove a oficina.

    Recusa a remocao quando ha inscricoes ativas: apagar a oficina invalidaria
    silenciosamente a inscricao de terceiros. O conflito e 409, nao 403 -- o
    problema esta no estado do recurso, nao na autorizacao de quem pede.

    Uma segunda chamada ao mesmo URI responde 404. O efeito e idempotente (o
    recurso segue ausente); o status difere porque descreve o que aconteceu
    naquela requisicao, e nao o estado final.
    """
    repositorio.remover_oficina(oficina_id, versao_do_if_match(if_match))
    return Response(status_code=204)


# ----------------------------------------------------------------------
# Inscricoes
#
# Criacao e listagem sao aninhadas sob a oficina, porque a colecao so existe no
# contexto do pai e a verificacao de capacidade precisa saber de qual oficina se
# trata. As operacoes de item ficam em primeiro nivel: quem ja possui o
# identificador da inscricao -- que o `Location` da criacao devolve -- nao
# deveria precisar guardar tambem o identificador da oficina para cancela-la.
# ----------------------------------------------------------------------


@app.get(
    "/oficinas/{oficina_id}/inscricoes",
    response_model=PaginaInscricoes,
    tags=["inscricoes"],
)
def listar_inscricoes(
    oficina_id: int,
    limite: int = Query(default=config.LIMITE_PADRAO, ge=1, le=config.LIMITE_MAXIMO),
    offset: int = Query(default=0, ge=0),
):
    """Lista as inscricoes de uma oficina.

    Responde 404 quando a oficina nao existe, em vez de uma lista vazia: sao
    situacoes diferentes, e confundi-las esconde do cliente que ele esta
    consultando um identificador errado.
    """
    total, itens = repositorio.listar_inscricoes(oficina_id, limite, offset)
    return PaginaInscricoes(total=total, limite=limite, offset=offset, itens=itens)


@app.post(
    "/oficinas/{oficina_id}/inscricoes",
    response_model=Inscricao,
    status_code=201,
    tags=["inscricoes"],
)
def criar_inscricao(oficina_id: int, entrada: InscricaoEntrada, resposta: Response):
    """Inscreve um participante na oficina.

    Concentra tres conflitos distintos, todos 409 porque dependem do estado
    atual do recurso e nao da representacao enviada:

    - `oficina_lotada`: as vagas acabaram;
    - `inscricao_duplicada`: o mesmo e-mail ja tem inscricao ativa aqui;
    - `oficina_nao_aberta`: a oficina nao esta recebendo inscricoes.

    A repeticao desta requisicao devolve 409, enquanto repetir `POST /oficinas`
    cria um segundo recurso. Ambos sao POST e nenhum e idempotente; a diferenca
    e que aqui existe um invariante de unicidade que o servidor protege.
    """
    inscricao = repositorio.criar_inscricao(oficina_id, entrada)
    resposta.headers["Location"] = f"/inscricoes/{inscricao.id}"
    return inscricao


@app.get("/inscricoes/{inscricao_id}", response_model=Inscricao, tags=["inscricoes"])
def obter_inscricao(inscricao_id: int):
    return repositorio.obter_inscricao(inscricao_id)


@app.patch("/inscricoes/{inscricao_id}", response_model=Inscricao, tags=["inscricoes"])
def atualizar_inscricao(inscricao_id: int, patch: InscricaoPatch):
    """Altera o status da inscricao, respeitando o ciclo de vida.

    Transicoes invalidas -- reativar uma inscricao cancelada, por exemplo --
    resultam em 409. A restricao nao e formal: reativar sem passar de novo pela
    verificacao de capacidade permitiria ultrapassar o limite de vagas.
    """
    return repositorio.atualizar_inscricao(inscricao_id, patch.status)


@app.delete("/inscricoes/{inscricao_id}", status_code=204, tags=["inscricoes"])
def cancelar_inscricao(inscricao_id: int):
    """Cancela a inscricao e libera a vaga.

    O registro permanece com status `cancelada` em vez de ser apagado: o
    historico de desistencias tem valor, e a vaga volta a ficar disponivel
    porque a contagem de ocupacao so considera os status ativos.

    Repetir a chamada mantem o mesmo estado final -- a inscricao segue cancelada
    -- e responde 204 novamente. E o caso mais limpo de idempotencia de efeito
    da API.
    """
    repositorio.cancelar_inscricao(inscricao_id)
    return Response(status_code=204)
