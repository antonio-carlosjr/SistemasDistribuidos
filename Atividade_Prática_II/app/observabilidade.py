"""Log estruturado de requisicoes com identificador de correlacao.

A secao 4.7 da apostila pede logs contendo metodo, caminho, status, duracao e
identificador de correlacao, e adverte contra registrar segredos.

O identificador de correlacao vem do cabecalho `X-Request-Id` quando o cliente
o envia, e e gerado quando nao vem. Devolve-lo na resposta permite que o cliente
cite o mesmo identificador ao relatar um problema, e e o que torna possivel
seguir uma operacao que atravessa varios servicos -- num sistema distribuido o
log de um servico isolado raramente conta a historia inteira.

O log e escrito como uma linha JSON por requisicao. O formato e mais verboso que
texto puro, mas e consultavel sem expressao regular, o que importa quando as
evidencias precisam ser filtradas na hora da demonstracao.
"""

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config

#: Cabecalhos que jamais entram no log. A secao 4.12 e explicita sobre nao
#: registrar credenciais; deixar isso como uma lista evita que um cabecalho
#: sensivel seja incluido por descuido quando novos forem adicionados.
CABECALHOS_OMITIDOS = {"authorization", "x-token-admin", "cookie", "set-cookie"}

_lock_arquivo = threading.Lock()


def registrar(evento: dict) -> None:
    """Emite um evento como linha JSON em stdout e no arquivo de evidencias."""
    evento = {"ts": datetime.now(timezone.utc).isoformat(), **evento}
    linha = json.dumps(evento, ensure_ascii=False)

    print(linha, file=sys.stdout, flush=True)

    caminho: Path = config.CAMINHO_LOG
    with _lock_arquivo:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")


def registrar_requisicao(
    request_id: str,
    metodo: str,
    caminho: str,
    status: int,
    duracao_ms: float,
    erro: Optional[str] = None,
) -> None:
    evento = {
        "request_id": request_id,
        "metodo": metodo,
        "caminho": caminho,
        "status": status,
        "duracao_ms": round(duracao_ms, 2),
    }
    if erro:
        evento["erro"] = erro
    registrar(evento)
