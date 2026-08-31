"""Excecoes de dominio e seu mapeamento para status HTTP.

O dominio levanta excecoes que descrevem *o que* deu errado; a traducao para
codigo HTTP acontece num unico lugar. Isso mantem as regras de negocio
independentes do protocolo e evita que o mesmo tipo de falha seja mapeado para
status diferentes conforme a rota.

A distincao central e entre 422 e 409:

- 422 fala da *representacao enviada* -- ela e bem formada, mas nao satisfaz as
  restricoes do modelo. E tratado pelo Pydantic, antes de chegar aqui.
- 409 fala do *estado do servidor* -- a requisicao e valida em si, mas conflita
  com a situacao atual do recurso. A mesma requisicao poderia ter sido aceita um
  segundo antes.
"""


class ErroDominio(Exception):
    """Base das falhas esperadas do dominio.

    Falha esperada nao e defeito: e resultado previsto de uma regra de negocio e
    deve produzir resposta descritiva. Excecoes que nao herdam desta classe sao
    tratadas como falha interna (500) e nao expoem detalhes ao cliente.
    """

    status = 400
    codigo = "erro_dominio"

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class NaoEncontrado(ErroDominio):
    status = 404
    codigo = "nao_encontrado"


class Conflito(ErroDominio):
    """Violacao de um invariante do dominio -- 409 Conflict."""

    status = 409
    codigo = "conflito"


class OficinaLotada(Conflito):
    codigo = "oficina_lotada"


class InscricaoDuplicada(Conflito):
    codigo = "inscricao_duplicada"


class OficinaNaoAberta(Conflito):
    codigo = "oficina_nao_aberta"


class OficinaComInscricoes(Conflito):
    codigo = "oficina_com_inscricoes"


class VagasAbaixoDoOcupado(Conflito):
    codigo = "vagas_abaixo_do_ocupado"


class TransicaoInvalida(Conflito):
    codigo = "transicao_invalida"


class PrecondicaoObrigatoria(ErroDominio):
    """Escrita sem `If-Match` -- 428 Precondition Required.

    Exigir a precondicao transforma perda silenciosa de atualizacao em erro
    visivel: sem ela o servidor nao tem como saber sobre qual versao o cliente
    baseou a alteracao.
    """

    status = 428
    codigo = "precondicao_obrigatoria"


class PrecondicaoFalhou(ErroDominio):
    """`If-Match` divergente -- 412 Precondition Failed.

    O cliente enviou a precondicao e ela nao confere: houve escrita concorrente
    entre a leitura dele e esta requisicao.
    """

    status = 412
    codigo = "precondicao_falhou"


class NaoAutorizado(ErroDominio):
    status = 401
    codigo = "nao_autorizado"


class EmManutencao(ErroDominio):
    """503 Service Unavailable.

    Diferente de uma falha de conectividade: aqui existe resposta HTTP, com
    status e `Retry-After`. O cliente sabe que o servico esta vivo e quando
    tentar de novo. Sem servidor, o cliente nao obtem resposta alguma e nao
    consegue distinguir indisponibilidade de problema de rede.
    """

    status = 503
    codigo = "em_manutencao"
