"""API REST de inscricoes em oficinas -- AP2 de Sistemas Distribuidos.

A aplicacao expoe duas colecoes relacionadas, `/oficinas` e as `/inscricoes` de
cada oficina, e um pequeno conjunto de rotas operacionais que existem para
tornar reproduziveis os experimentos da secao 4.8 da apostila.
"""

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import observabilidade
from .erros import ErroDominio

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
