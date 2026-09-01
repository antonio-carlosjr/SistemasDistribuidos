"""Cliente programatico de testes -- gera a tabela de evidencias da AP2.

Complementa a suite pytest em vez de duplica-la. Os testes automatizados rodam
dentro do processo e verificam contrato e invariantes; este script fala com um
servidor real por HTTP e por isso e o unico capaz de exercer o que so existe na
rede: timeout do cliente e ausencia de resposta.

Todo `requests` aqui leva `timeout` explicito. Sem ele a biblioteca espera
indefinidamente, e um cliente travado e pior que um erro: a falha deixa de ser
observavel e passa a se manifestar como lentidao em quem depende dele.

A tabela e gerada a partir da execucao, e nao escrita a mao. Uma tabela redigida
manualmente descreve o que se acredita que a API faz; esta descreve o que ela
fez.

Uso:
    python cliente_testes.py                 # servidor no ar
    python cliente_testes.py --offline       # servidor desligado
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Union

import requests

BASE = "http://127.0.0.1:8000"
TIMEOUT_PADRAO = 3.0
TOKEN_ADMIN = "token-de-laboratorio"
SAIDA = Path(__file__).parent / "evidencias" / "tabela.md"
#: Resultados acumulados entre execucoes. Permite que a rodada com o
#: servidor no ar e a rodada offline componham uma unica tabela numerada de
#: ponta a ponta, em vez de duas tabelas independentes.
CACHE = Path(__file__).parent / "evidencias" / "resultados.json"
GRUPO_OFFLINE = "Falha de conectividade"

OFICINA_BASE = {
    "titulo": "Arquitetura de sistemas distribuidos",
    "instrutor": "Helena Bastos",
    "vagas_totais": 3,
    "inicio": "2026-11-05T14:00:00Z",
    "duracao_min": 180,
    "status": "aberta",
}

#: Marcadores para resultados que nao sao status HTTP. Distinguir os dois casos
#: e o ponto da questao 2 da analise: em um deles o servidor respondeu, no outro
#: nao houve resposta para interpretar.
TIMEOUT = "Timeout"
SEM_CONEXAO = "ConnectionError"

Dinamico = Union[str, Callable[[dict], str]]


@dataclass
class Resultado:
    grupo: str
    nome: str
    requisicao: str
    esperado: Any
    obtido: Any
    codigo: str = ""
    observacao: str = ""

    @property
    def ok(self) -> bool:
        return str(self.esperado) == str(self.obtido)


@dataclass
class Executor:
    contexto: dict = field(default_factory=dict)
    resultados: list = field(default_factory=list)
    grupo: str = "Geral"

    def secao(self, titulo: str) -> None:
        self.grupo = titulo

    def _resolver(self, valor):
        return valor(self.contexto) if callable(valor) else valor

    def chamar(
        self,
        nome: str,
        metodo: str,
        caminho: Dinamico,
        esperado: Any,
        corpo: Optional[Any] = None,
        cabecalhos: Optional[Any] = None,
        timeout: float = TIMEOUT_PADRAO,
        guardar: Optional[str] = None,
        observacao: str = "",
    ):
        caminho = self._resolver(caminho)
        corpo = self._resolver(corpo)
        cabecalhos = self._resolver(cabecalhos)
        requisicao = f"{metodo} {caminho}"
        if timeout != TIMEOUT_PADRAO:
            requisicao += f" (timeout {timeout}s)"

        codigo = ""
        try:
            resposta = requests.request(
                metodo,
                f"{BASE}{caminho}",
                json=corpo,
                headers=cabecalhos,
                timeout=timeout,
            )
            obtido: Any = resposta.status_code
            if resposta.status_code >= 400:
                try:
                    codigo = resposta.json()["erro"]["codigo"]
                except (ValueError, KeyError):
                    codigo = ""
            if guardar:
                self.contexto[guardar] = self._extrair(resposta)
        except requests.exceptions.Timeout:
            # O cliente desistiu antes de qualquer resposta. Nao se sabe se o
            # servidor executou a operacao -- para escritas, essa incerteza e o
            # motivo de idempotencia importar.
            obtido = TIMEOUT
        except requests.exceptions.ConnectionError:
            # Nao houve resposta alguma. Nem status, nem corpo, nem Retry-After.
            obtido = SEM_CONEXAO

        resultado = Resultado(
            self.grupo, nome, requisicao, esperado, obtido, codigo, observacao
        )
        self.resultados.append(resultado)
        marcador = "ok" if resultado.ok else "FALHA"
        print(f"[{marcador:>5}] {nome:<46} esperado={esperado:<6} obtido={obtido}")
        return resultado

    @staticmethod
    def _extrair(resposta) -> dict:
        try:
            dados = resposta.json()
        except ValueError:
            dados = {}
        return {"corpo": dados, "etag": resposta.headers.get("ETag", "")}


def _id(chave: str) -> Callable[[dict], Any]:
    return lambda ctx: ctx[chave]["corpo"]["id"]


def _etag(chave: str) -> Callable[[dict], dict]:
    return lambda ctx: {"If-Match": ctx[chave]["etag"]}


def roteiro(executor: Executor) -> None:
    """Executa os cenarios em ordem, construindo o estado de que precisa."""

    # ------------------------------------------------------------------
    executor.secao("Sucesso")

    executor.chamar("Sonda de saude", "GET", "/saude", 200)
    executor.chamar(
        "Criar oficina",
        "POST",
        "/oficinas",
        201,
        corpo=OFICINA_BASE,
        guardar="oficina",
        observacao="Responde Location e ETag",
    )
    executor.chamar(
        "Criar a mesma oficina de novo",
        "POST",
        "/oficinas",
        201,
        corpo=OFICINA_BASE,
        guardar="duplicata",
        observacao="POST nao e idempotente: cria um segundo recurso",
    )
    executor.chamar("Listar oficinas", "GET", "/oficinas", 200)
    executor.chamar(
        "Obter oficina",
        "GET",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        200,
        guardar="oficina",
    )
    executor.chamar(
        "Listar inscricoes da oficina",
        "GET",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}/inscricoes",
        200,
    )

    # ------------------------------------------------------------------
    executor.secao("Validacao de entrada (422)")

    executor.chamar(
        "Criar oficina com titulo curto",
        "POST",
        "/oficinas",
        422,
        corpo={**OFICINA_BASE, "titulo": "ab"},
    )
    executor.chamar(
        "Criar oficina com campo desconhecido",
        "POST",
        "/oficinas",
        422,
        corpo={**OFICINA_BASE, "vagas": 10},
        observacao="Campo nao previsto e erro, nao silencio",
    )
    executor.chamar(
        "Inscrever com e-mail malformado",
        "POST",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}/inscricoes",
        422,
        corpo={"participante_nome": "Igor Farias", "participante_email": "sem-arroba"},
    )
    executor.chamar(
        "Listar com limite acima do teto",
        "GET",
        "/oficinas?limite=1000",
        422,
        observacao="Paginacao tem teto para a resposta nao crescer sem limite",
    )

    # ------------------------------------------------------------------
    executor.secao("Recurso inexistente (404)")

    executor.chamar("Obter oficina inexistente", "GET", "/oficinas/9999", 404)
    executor.chamar(
        "Listar inscricoes de oficina inexistente",
        "GET",
        "/oficinas/9999/inscricoes",
        404,
        observacao="404, e nao lista vazia: sao situacoes distintas",
    )
    executor.chamar("Obter inscricao inexistente", "GET", "/inscricoes/9999", 404)

    # ------------------------------------------------------------------
    executor.secao("Concorrencia e cache (304/412/428)")

    executor.chamar(
        "Obter com If-None-Match atual",
        "GET",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        304,
        cabecalhos=lambda ctx: {"If-None-Match": ctx["oficina"]["etag"]},
        observacao="Representacao inalterada: resposta sem corpo",
    )
    executor.chamar(
        "Alterar sem If-Match",
        "PATCH",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        428,
        corpo={"titulo": "Tentativa sem precondicao"},
        observacao="A precondicao e exigida para evitar perda de atualizacao",
    )
    executor.chamar(
        "Alterar com ETag inexistente",
        "PATCH",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        412,
        corpo={"titulo": "Tentativa com ETag errado"},
        cabecalhos={"If-Match": '"999"'},
    )
    executor.chamar(
        "Alterar com ETag correto",
        "PATCH",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        200,
        corpo={"titulo": "Titulo revisado pelo cliente A"},
        cabecalhos=_etag("oficina"),
        observacao="A versao avanca e o ETag anterior deixa de valer",
    )
    executor.chamar(
        "Repetir a alteracao com o ETag ja consumido",
        "PATCH",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        412,
        corpo={"titulo": "Titulo revisado pelo cliente B"},
        cabecalhos=_etag("oficina"),
        observacao="Perda de atualizacao detectada em vez de sobrescrita silenciosa",
    )
    executor.chamar(
        "Reler para obter o ETag vigente",
        "GET",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        200,
        guardar="oficina",
    )
    executor.chamar(
        "Substituir com If-Match vigente",
        "PUT",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        200,
        corpo={**OFICINA_BASE, "titulo": "Representacao substituida"},
        cabecalhos=_etag("oficina"),
        guardar="oficina",
    )

    # ------------------------------------------------------------------
    executor.secao("Conflitos de dominio (409)")

    executor.chamar(
        "Inscrever participante",
        "POST",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}/inscricoes",
        201,
        corpo={
            "participante_nome": "Bruno Lima",
            "participante_email": "bruno.lima@exemplo.com",
        },
        guardar="inscricao",
    )
    executor.chamar(
        "Inscrever o mesmo e-mail de novo",
        "POST",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}/inscricoes",
        409,
        corpo={
            "participante_nome": "Bruno Lima",
            "participante_email": "BRUNO.LIMA@exemplo.com",
        },
        observacao="Repetir POST aqui conflita, em vez de duplicar",
    )
    executor.chamar(
        "Inscrever um segundo participante",
        "POST",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}/inscricoes",
        201,
        corpo={
            "participante_nome": "Fernanda Dias",
            "participante_email": "fernanda.dias@exemplo.com",
        },
        guardar="inscricao2",
        observacao="Leva a oficina a duas vagas ocupadas de tres",
    )
    executor.chamar(
        "Remover oficina com inscritos",
        "DELETE",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        409,
        cabecalhos=_etag("oficina"),
        observacao="409 e nao 403: o impedimento vem do estado, nao da permissao",
    )
    executor.chamar(
        "Reduzir vagas abaixo do ocupado",
        "PATCH",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        409,
        corpo={"vagas_totais": 1},
        cabecalhos=_etag("oficina"),
        observacao="Ha duas inscricoes ativas; aceitar deixaria estado impossivel",
    )
    executor.chamar(
        "Transicao de status invalida",
        "PATCH",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        409,
        corpo={"status": "rascunho"},
        cabecalhos=_etag("oficina"),
    )

    executor.chamar(
        "Criar oficina de vaga unica",
        "POST",
        "/oficinas",
        201,
        corpo={**OFICINA_BASE, "titulo": "Oficina de vaga unica", "vagas_totais": 1},
        guardar="unica",
    )
    executor.chamar(
        "Ocupar a unica vaga",
        "POST",
        lambda ctx: f"/oficinas/{_id('unica')(ctx)}/inscricoes",
        201,
        corpo={
            "participante_nome": "Carla Souza",
            "participante_email": "carla.souza@exemplo.com",
        },
    )
    executor.chamar(
        "Inscrever com a oficina lotada",
        "POST",
        lambda ctx: f"/oficinas/{_id('unica')(ctx)}/inscricoes",
        409,
        corpo={
            "participante_nome": "Davi Rocha",
            "participante_email": "davi.rocha@exemplo.com",
        },
    )

    executor.chamar(
        "Criar oficina em rascunho",
        "POST",
        "/oficinas",
        201,
        corpo={**OFICINA_BASE, "titulo": "Oficina ainda em rascunho", "status": "rascunho"},
        guardar="rascunho",
    )
    executor.chamar(
        "Inscrever em oficina nao aberta",
        "POST",
        lambda ctx: f"/oficinas/{_id('rascunho')(ctx)}/inscricoes",
        409,
        corpo={
            "participante_nome": "Elisa Prado",
            "participante_email": "elisa.prado@exemplo.com",
        },
    )

    # ------------------------------------------------------------------
    executor.secao("Idempotencia")

    executor.chamar(
        "Marcar presenca",
        "PATCH",
        lambda ctx: f"/inscricoes/{_id('inscricao')(ctx)}",
        200,
        corpo={"status": "presente"},
    )
    executor.chamar(
        "Cancelar inscricao",
        "DELETE",
        lambda ctx: f"/inscricoes/{_id('inscricao')(ctx)}",
        204,
    )
    executor.chamar(
        "Cancelar a mesma inscricao de novo",
        "DELETE",
        lambda ctx: f"/inscricoes/{_id('inscricao')(ctx)}",
        204,
        observacao="Mesmo efeito e mesmo status: idempotente",
    )
    executor.chamar(
        "Reativar inscricao cancelada",
        "PATCH",
        lambda ctx: f"/inscricoes/{_id('inscricao')(ctx)}",
        409,
        corpo={"status": "presente"},
        observacao="Reativar sem reavaliar capacidade furaria o limite de vagas",
    )
    executor.chamar(
        "Cancelar a segunda inscricao",
        "DELETE",
        lambda ctx: f"/inscricoes/{_id('inscricao2')(ctx)}",
        204,
        observacao="Esvazia a oficina para o cenario de remocao",
    )
    executor.chamar(
        "Reler a oficina liberada",
        "GET",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        200,
        guardar="oficina",
    )
    executor.chamar(
        "Remover oficina sem inscritos",
        "DELETE",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        204,
        cabecalhos=_etag("oficina"),
    )
    executor.chamar(
        "Remover a mesma oficina de novo",
        "DELETE",
        lambda ctx: f"/oficinas/{_id('oficina')(ctx)}",
        404,
        cabecalhos={"If-Match": "*"},
        observacao="Efeito identico, status diferente: 404 relata esta requisicao",
    )

    # ------------------------------------------------------------------
    executor.secao("Timeout do cliente")

    for limite, esperado in ((0.5, TIMEOUT), (1.0, TIMEOUT), (3.0, 200)):
        executor.chamar(
            f"Rota de 2s com timeout de {limite}s",
            "GET",
            "/debug/lento?segundos=2",
            esperado,
            timeout=limite,
        )

    # ------------------------------------------------------------------
    executor.secao("Indisponibilidade (503)")

    executor.chamar(
        "Ativar manutencao sem token",
        "POST",
        "/admin/manutencao",
        401,
        corpo={"ativo": True},
    )
    executor.chamar(
        "Ativar manutencao com token",
        "POST",
        "/admin/manutencao",
        200,
        corpo={"ativo": True},
        cabecalhos={"X-Token-Admin": TOKEN_ADMIN},
    )
    executor.chamar(
        "Listar oficinas em manutencao",
        "GET",
        "/oficinas",
        503,
        observacao="Ha resposta: status e Retry-After informam o cliente",
    )
    executor.chamar(
        "Desativar manutencao",
        "POST",
        "/admin/manutencao",
        200,
        corpo={"ativo": False},
        cabecalhos={"X-Token-Admin": TOKEN_ADMIN},
    )


def roteiro_offline(executor: Executor) -> None:
    """Cenario de conectividade -- exige o servidor desligado."""
    executor.secao(GRUPO_OFFLINE)
    executor.chamar(
        "Listar oficinas com o servidor desligado",
        "GET",
        "/oficinas",
        SEM_CONEXAO,
        observacao="Nao ha resposta: nem status, nem corpo, nem Retry-After",
    )
    executor.chamar(
        "Criar oficina com o servidor desligado",
        "POST",
        "/oficinas",
        SEM_CONEXAO,
        corpo=OFICINA_BASE,
        observacao="O cliente nao sabe se a operacao ocorreu",
    )


def carregar_cache() -> list:
    if not CACHE.exists():
        return []
    return [Resultado(**dados) for dados in json.loads(CACHE.read_text("utf-8"))]


def salvar_cache(resultados: list) -> None:
    CACHE.write_text(
        json.dumps([asdict(r) for r in resultados], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def gerar_tabela(resultados: list) -> str:
    aprovados = sum(1 for r in resultados if r.ok)
    tem_offline = any(r.grupo == GRUPO_OFFLINE for r in resultados)
    linhas = [
        "# Tabela de evidencias -- AP2",
        "",
        "Gerada por `cliente_testes.py` a partir da execucao real contra o",
        "servidor. Os valores da coluna *obtido* nao sao transcritos a mao.",
        "",
        f"**{aprovados} de {len(resultados)} cenarios com resultado igual ao esperado.**",
        "",
    ]
    if not tem_offline:
        linhas += [
            "> Os cenarios de falha de conectividade ainda nao foram coletados.",
            "> Desligue o servidor e rode `python cliente_testes.py --offline`",
            "> para acrescenta-los a esta tabela.",
            "",
        ]

    grupo_atual = None
    for indice, resultado in enumerate(resultados, start=1):
        if resultado.grupo != grupo_atual:
            grupo_atual = resultado.grupo
            linhas += [
                # A linha em branco separa o titulo da tabela anterior. Sem ela,
                # o Markdown trata o cabecalho como mais uma linha daquela
                # tabela em vez de iniciar uma secao.
                "",
                f"## {grupo_atual}",
                "",
                "| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        linhas.append(
            f"| {indice} | {resultado.nome} | `{resultado.requisicao}` | "
            f"{resultado.esperado} | {resultado.obtido} | "
            f"{resultado.codigo or '-'} | {'OK' if resultado.ok else 'FALHOU'} |"
        )
        if resultado.observacao:
            linhas.append(
                f"| | _{resultado.observacao}_ | | | | | |"
            )
    linhas.append("")
    return "\n".join(linhas)


def main() -> int:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument(
        "--offline",
        action="store_true",
        help="executa apenas os cenarios de falha de conectividade",
    )
    analisador.add_argument("--saida", default=str(SAIDA))
    argumentos = analisador.parse_args()

    executor = Executor()
    if argumentos.offline:
        roteiro_offline(executor)
    else:
        roteiro(executor)

    saida = Path(argumentos.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)

    # Cada rodada substitui apenas os cenarios que ela mesma cobre, preservando
    # os da outra. Assim as duas condicoes -- servidor no ar e servidor
    # desligado -- convivem numa tabela unica e numerada continuamente.
    anteriores = carregar_cache()
    if argumentos.offline:
        todos = [r for r in anteriores if r.grupo != GRUPO_OFFLINE]
        todos += executor.resultados
    else:
        todos = list(executor.resultados)
        todos += [r for r in anteriores if r.grupo == GRUPO_OFFLINE]

    salvar_cache(todos)
    saida.write_text(gerar_tabela(todos), encoding="utf-8")

    falhas = [r for r in executor.resultados if not r.ok]
    print(f"\nTabela gravada em {saida}")
    print(f"{len(executor.resultados) - len(falhas)}/{len(executor.resultados)} cenarios conforme o esperado")
    if falhas:
        print("\nCenarios divergentes:")
        for resultado in falhas:
            print(f"  - {resultado.nome}: esperado {resultado.esperado}, obtido {resultado.obtido}")
    return 1 if falhas else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.exceptions.ConnectionError:
        print(
            "Nao foi possivel conectar ao servidor.\n"
            "Suba a API com 'fastapi dev app/main.py' ou use --offline.",
            file=sys.stderr,
        )
        sys.exit(2)
