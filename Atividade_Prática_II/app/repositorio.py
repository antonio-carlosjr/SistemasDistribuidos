"""Persistencia em arquivo JSON com escrita atomica e exclusao mutua.

A apostila observa que "a logica distribuida vale mais que a tecnologia de
banco". Por isso a persistencia aqui e deliberadamente simples: o objetivo e
manter visivel no proprio codigo o mecanismo que protege os invariantes, em vez
de delega-lo a um motor de banco de dados.

Duas garantias importam:

**Exclusao mutua.** Todo ciclo ler-verificar-escrever ocorre sob um `RLock`. Sem
ele, verificar se ha vaga e inserir a inscricao seriam duas operacoes separadas,
e duas requisicoes concorrentes poderiam passar pela verificacao antes que
qualquer uma gravasse -- o padrao *check-then-act*. O mesmo vale para a
conferencia do `If-Match`: ela precisa acontecer dentro do lock, senao o proprio
controle de versao teria a corrida que pretende evitar.

**Atomicidade da gravacao.** O estado e escrito num arquivo temporario e movido
sobre o definitivo com `os.replace`, que e atomico no Windows e no POSIX. Uma
interrupcao no meio da escrita deixa o arquivo anterior intacto, em vez de um
JSON truncado que nao carrega mais.

Limite conhecido: o `RLock` so coordena threads do mesmo processo. Varias
instancias do servidor sobre o mesmo arquivo exigiriam trava de arquivo do
sistema operacional ou um armazenamento com transacoes reais. A analise volta a
esse ponto.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config
from .erros import (
    Conflito,
    InscricaoDuplicada,
    NaoEncontrado,
    OficinaComInscricoes,
    OficinaLotada,
    OficinaNaoAberta,
    PrecondicaoFalhou,
    PrecondicaoObrigatoria,
    TransicaoInvalida,
    VagasAbaixoDoOcupado,
)
from .modelos import (
    STATUS_QUE_OCUPAM_VAGA,
    TRANSICOES_INSCRICAO,
    TRANSICOES_OFICINA,
    Inscricao,
    InscricaoEntrada,
    Oficina,
    OficinaEntrada,
    OficinaPatch,
    StatusInscricao,
    StatusOficina,
)

ESTADO_VAZIO = {
    "proximo_id_oficina": 1,
    "proximo_id_inscricao": 1,
    "oficinas": {},
    "inscricoes": {},
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Repositorio:
    def __init__(self, caminho: Optional[Path] = None):
        self._caminho = Path(caminho or config.CAMINHO_DADOS)
        self._lock = threading.RLock()
        self._estado = self._carregar()

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def _carregar(self) -> dict:
        if not self._caminho.exists():
            return json.loads(json.dumps(ESTADO_VAZIO))
        with self._caminho.open(encoding="utf-8") as arquivo:
            return json.load(arquivo)

    def _gravar(self) -> None:
        """Grava o estado de forma atomica.

        O arquivo temporario e criado no mesmo diretorio de destino porque
        `os.replace` so e atomico dentro do mesmo sistema de arquivos.
        """
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        descritor, temporario = tempfile.mkstemp(
            dir=self._caminho.parent, prefix=".estado-", suffix=".tmp"
        )
        try:
            with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
                json.dump(self._estado, arquivo, ensure_ascii=False, indent=2)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporario, self._caminho)
        except Exception:
            Path(temporario).unlink(missing_ok=True)
            raise

    def redefinir(self) -> None:
        """Zera o estado. Usado por `seed.py` e pelos testes."""
        with self._lock:
            self._estado = json.loads(json.dumps(ESTADO_VAZIO))
            self._gravar()

    # ------------------------------------------------------------------
    # Auxiliares internos -- sempre chamados com o lock ja adquirido
    # ------------------------------------------------------------------

    def _bruta_oficina(self, oficina_id: int) -> dict:
        registro = self._estado["oficinas"].get(str(oficina_id))
        if registro is None:
            raise NaoEncontrado(f"Oficina {oficina_id} nao encontrada")
        return registro

    def _bruta_inscricao(self, inscricao_id: int) -> dict:
        registro = self._estado["inscricoes"].get(str(inscricao_id))
        if registro is None:
            raise NaoEncontrado(f"Inscricao {inscricao_id} nao encontrada")
        return registro

    def _ocupadas(self, oficina_id: int) -> int:
        """Conta as vagas ocupadas a partir das inscricoes.

        Derivar em vez de manter um contador elimina a possibilidade de o
        contador divergir da lista -- nao existe segunda fonte de verdade para
        dessincronizar.
        """
        return sum(
            1
            for inscricao in self._estado["inscricoes"].values()
            if inscricao["oficina_id"] == oficina_id
            and StatusInscricao(inscricao["status"]) in STATUS_QUE_OCUPAM_VAGA
        )

    def _montar_oficina(self, registro: dict) -> Oficina:
        ocupadas = self._ocupadas(registro["id"])
        return Oficina(
            **registro,
            vagas_ocupadas=ocupadas,
            vagas_disponiveis=max(0, registro["vagas_totais"] - ocupadas),
        )

    @staticmethod
    def _conferir_precondicao(registro: dict, versao_esperada: Optional[int]) -> None:
        """Valida o `If-Match` da requisicao.

        Executa dentro do lock por necessidade: conferir a versao e gravar
        precisam ser indivisiveis, senao o controle otimista teria a mesma
        corrida que existe para eliminar.
        """
        if versao_esperada is None:
            raise PrecondicaoObrigatoria(
                "Envie o cabecalho If-Match com o ETag obtido na leitura"
            )
        if versao_esperada != registro["versao"]:
            raise PrecondicaoFalhou(
                f"O recurso esta na versao {registro['versao']}; "
                f"a requisicao supunha a versao {versao_esperada}"
            )

    @staticmethod
    def _conferir_transicao_oficina(atual: StatusOficina, novo: StatusOficina) -> None:
        if atual == novo:
            return
        if novo not in TRANSICOES_OFICINA[atual]:
            raise TransicaoInvalida(
                f"Nao e possivel passar a oficina de '{atual.value}' para '{novo.value}'"
            )

    # ------------------------------------------------------------------
    # Oficinas
    # ------------------------------------------------------------------

    def listar_oficinas(
        self, status: Optional[StatusOficina], limite: int, offset: int
    ) -> tuple[int, list[Oficina]]:
        with self._lock:
            registros = list(self._estado["oficinas"].values())
            if status is not None:
                registros = [r for r in registros if r["status"] == status.value]
            registros.sort(key=lambda r: r["id"])
            recorte = registros[offset : offset + limite]
            return len(registros), [self._montar_oficina(r) for r in recorte]

    def criar_oficina(self, entrada: OficinaEntrada) -> Oficina:
        with self._lock:
            novo_id = self._estado["proximo_id_oficina"]
            registro = entrada.model_dump(mode="json")
            registro["id"] = novo_id
            registro["versao"] = 1
            self._estado["oficinas"][str(novo_id)] = registro
            self._estado["proximo_id_oficina"] = novo_id + 1
            self._gravar()
            return self._montar_oficina(registro)

    def obter_oficina(self, oficina_id: int) -> Oficina:
        with self._lock:
            return self._montar_oficina(self._bruta_oficina(oficina_id))

    def substituir_oficina(
        self, oficina_id: int, entrada: OficinaEntrada, versao_esperada: Optional[int]
    ) -> Oficina:
        with self._lock:
            registro = self._bruta_oficina(oficina_id)
            self._conferir_precondicao(registro, versao_esperada)
            self._conferir_transicao_oficina(
                StatusOficina(registro["status"]), entrada.status
            )

            ocupadas = self._ocupadas(oficina_id)
            if entrada.vagas_totais < ocupadas:
                raise VagasAbaixoDoOcupado(
                    f"A oficina tem {ocupadas} inscricoes ativas; "
                    f"vagas_totais nao pode ser {entrada.vagas_totais}"
                )

            novo = entrada.model_dump(mode="json")
            novo["id"] = oficina_id
            novo["versao"] = registro["versao"] + 1
            self._estado["oficinas"][str(oficina_id)] = novo
            self._gravar()
            return self._montar_oficina(novo)

    def atualizar_oficina(
        self, oficina_id: int, patch: OficinaPatch, versao_esperada: Optional[int]
    ) -> Oficina:
        with self._lock:
            registro = self._bruta_oficina(oficina_id)
            self._conferir_precondicao(registro, versao_esperada)

            alteracoes = patch.model_dump(mode="json", exclude_unset=True)
            if not alteracoes:
                raise Conflito("Informe ao menos um campo para alterar")

            if "status" in alteracoes:
                self._conferir_transicao_oficina(
                    StatusOficina(registro["status"]),
                    StatusOficina(alteracoes["status"]),
                )

            if "vagas_totais" in alteracoes:
                ocupadas = self._ocupadas(oficina_id)
                if alteracoes["vagas_totais"] < ocupadas:
                    raise VagasAbaixoDoOcupado(
                        f"A oficina tem {ocupadas} inscricoes ativas; "
                        f"vagas_totais nao pode ser {alteracoes['vagas_totais']}"
                    )

            registro.update(alteracoes)
            registro["versao"] += 1
            self._gravar()
            return self._montar_oficina(registro)

    def remover_oficina(self, oficina_id: int, versao_esperada: Optional[int]) -> None:
        with self._lock:
            registro = self._bruta_oficina(oficina_id)
            self._conferir_precondicao(registro, versao_esperada)

            ocupadas = self._ocupadas(oficina_id)
            if ocupadas:
                raise OficinaComInscricoes(
                    f"A oficina tem {ocupadas} inscricoes ativas e nao pode ser removida"
                )

            del self._estado["oficinas"][str(oficina_id)]
            # Inscricoes canceladas perdem o pai: removidas junto para nao
            # restarem registros orfaos referenciando uma oficina inexistente.
            self._estado["inscricoes"] = {
                chave: inscricao
                for chave, inscricao in self._estado["inscricoes"].items()
                if inscricao["oficina_id"] != oficina_id
            }
            self._gravar()

    # ------------------------------------------------------------------
    # Inscricoes
    # ------------------------------------------------------------------

    def listar_inscricoes(
        self, oficina_id: int, limite: int, offset: int
    ) -> tuple[int, list[Inscricao]]:
        with self._lock:
            self._bruta_oficina(oficina_id)  # 404 se a oficina nao existe
            registros = [
                r
                for r in self._estado["inscricoes"].values()
                if r["oficina_id"] == oficina_id
            ]
            registros.sort(key=lambda r: r["id"])
            recorte = registros[offset : offset + limite]
            return len(registros), [Inscricao(**r) for r in recorte]

    def criar_inscricao(self, oficina_id: int, entrada: InscricaoEntrada) -> Inscricao:
        with self._lock:
            oficina = self._bruta_oficina(oficina_id)

            if StatusOficina(oficina["status"]) is not StatusOficina.ABERTA:
                raise OficinaNaoAberta(
                    f"A oficina esta em '{oficina['status']}' e nao aceita inscricoes"
                )

            email = entrada.participante_email.strip().lower()
            for inscricao in self._estado["inscricoes"].values():
                if (
                    inscricao["oficina_id"] == oficina_id
                    and inscricao["participante_email"] == email
                    and StatusInscricao(inscricao["status"]) in STATUS_QUE_OCUPAM_VAGA
                ):
                    raise InscricaoDuplicada(
                        f"{email} ja possui inscricao ativa nesta oficina"
                    )

            # Verificacao de capacidade e insercao no mesmo trecho protegido:
            # e este par que o experimento de concorrencia tenta quebrar.
            if self._ocupadas(oficina_id) >= oficina["vagas_totais"]:
                raise OficinaLotada(
                    f"A oficina tem {oficina['vagas_totais']} vagas, todas ocupadas"
                )

            novo_id = self._estado["proximo_id_inscricao"]
            registro = {
                "id": novo_id,
                "oficina_id": oficina_id,
                "participante_nome": entrada.participante_nome,
                "participante_email": email,
                "status": StatusInscricao.CONFIRMADA.value,
                "criada_em": _agora().isoformat(),
            }
            self._estado["inscricoes"][str(novo_id)] = registro
            self._estado["proximo_id_inscricao"] = novo_id + 1
            self._gravar()
            return Inscricao(**registro)

    def obter_inscricao(self, inscricao_id: int) -> Inscricao:
        with self._lock:
            return Inscricao(**self._bruta_inscricao(inscricao_id))

    def atualizar_inscricao(
        self, inscricao_id: int, novo_status: StatusInscricao
    ) -> Inscricao:
        with self._lock:
            registro = self._bruta_inscricao(inscricao_id)
            atual = StatusInscricao(registro["status"])

            if atual != novo_status and novo_status not in TRANSICOES_INSCRICAO[atual]:
                raise TransicaoInvalida(
                    f"Nao e possivel passar a inscricao de '{atual.value}' "
                    f"para '{novo_status.value}'"
                )

            registro["status"] = novo_status.value
            self._gravar()
            return Inscricao(**registro)

    def cancelar_inscricao(self, inscricao_id: int) -> None:
        """Cancela a inscricao, liberando a vaga.

        O registro e mantido com status `cancelada` em vez de apagado: o
        historico de quem se inscreveu e desistiu tem valor, e a vaga volta a
        ficar disponivel porque `_ocupadas` so conta os status ativos.
        """
        with self._lock:
            registro = self._bruta_inscricao(inscricao_id)
            registro["status"] = StatusInscricao.CANCELADA.value
            self._gravar()


#: Instancia usada pela aplicacao. Os testes criam a sua apontando para um
#: arquivo temporario.
repositorio = Repositorio()
