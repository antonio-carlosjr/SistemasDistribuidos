"""Modelos de dominio e representacoes de entrada/saida.

Separar o modelo de entrada do modelo de saida evita que o cliente consiga
definir campos de responsabilidade do servidor -- `id`, `versao` e `criada_em`
sao atribuidos aqui, nunca aceitos do corpo da requisicao.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Padrao deliberadamente simples: valida a forma do endereco sem tentar
# reimplementar a RFC 5322. Usar EmailStr exigiria a dependencia
# email-validator, que nao acrescenta nada ao objetivo da atividade.
PADRAO_EMAIL = r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$"


class StatusOficina(str, Enum):
    RASCUNHO = "rascunho"
    ABERTA = "aberta"
    ENCERRADA = "encerrada"
    CANCELADA = "cancelada"


class StatusInscricao(str, Enum):
    CONFIRMADA = "confirmada"
    PRESENTE = "presente"
    CANCELADA = "cancelada"


#: Situacoes em que a inscricao ocupa uma vaga da oficina.
STATUS_QUE_OCUPAM_VAGA = {StatusInscricao.CONFIRMADA, StatusInscricao.PRESENTE}

#: Transicoes permitidas no ciclo de vida da inscricao. `cancelada` e terminal:
#: reativar uma inscricao cancelada furaria o limite de vagas, ja que a
#: verificacao de capacidade so acontece na criacao.
TRANSICOES_INSCRICAO = {
    StatusInscricao.CONFIRMADA: {StatusInscricao.PRESENTE, StatusInscricao.CANCELADA},
    StatusInscricao.PRESENTE: {StatusInscricao.CANCELADA},
    StatusInscricao.CANCELADA: set(),
}

#: Transicoes permitidas no ciclo de vida da oficina.
TRANSICOES_OFICINA = {
    StatusOficina.RASCUNHO: {StatusOficina.ABERTA, StatusOficina.CANCELADA},
    StatusOficina.ABERTA: {StatusOficina.ENCERRADA, StatusOficina.CANCELADA},
    StatusOficina.ENCERRADA: set(),
    StatusOficina.CANCELADA: set(),
}


class OficinaEntrada(BaseModel):
    """Representacao aceita em POST e PUT: todos os campos editaveis."""

    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(min_length=3, max_length=120)
    instrutor: str = Field(min_length=3, max_length=80)
    vagas_totais: int = Field(ge=1, le=500)
    inicio: datetime
    duracao_min: int = Field(ge=15, le=480)
    status: StatusOficina = StatusOficina.RASCUNHO


class OficinaPatch(BaseModel):
    """Representacao aceita em PATCH: todo campo e opcional.

    `extra="forbid"` faz com que um nome de campo digitado errado vire 422 em
    vez de ser silenciosamente ignorado -- uma alteracao que o cliente acredita
    ter feito, mas que nao aconteceu, e pior que um erro explicito.
    """

    model_config = ConfigDict(extra="forbid")

    titulo: Optional[str] = Field(default=None, min_length=3, max_length=120)
    instrutor: Optional[str] = Field(default=None, min_length=3, max_length=80)
    vagas_totais: Optional[int] = Field(default=None, ge=1, le=500)
    inicio: Optional[datetime] = None
    duracao_min: Optional[int] = Field(default=None, ge=15, le=480)
    status: Optional[StatusOficina] = None


class Oficina(OficinaEntrada):
    """Representacao devolvida ao cliente."""

    id: int
    versao: int
    vagas_ocupadas: int = 0
    vagas_disponiveis: int = 0


class InscricaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participante_nome: str = Field(min_length=3, max_length=120)
    participante_email: str = Field(pattern=PADRAO_EMAIL, max_length=160)


class InscricaoPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StatusInscricao


class Inscricao(InscricaoEntrada):
    id: int
    oficina_id: int
    status: StatusInscricao
    criada_em: datetime


class Pagina(BaseModel):
    """Envelope de listagem.

    Devolver um objeto em vez de um array cru permite acrescentar metadados de
    paginacao sem quebrar o contrato depois -- trocar array por objeto seria
    uma mudanca incompativel, conforme a secao 4.11 da apostila.
    """

    total: int
    limite: int
    offset: int


class PaginaOficinas(Pagina):
    itens: list[Oficina]


class PaginaInscricoes(Pagina):
    itens: list[Inscricao]


class DetalheErro(BaseModel):
    codigo: str
    mensagem: str
    request_id: str


class RespostaErro(BaseModel):
    erro: DetalheErro
