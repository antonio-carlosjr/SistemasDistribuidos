"""Dois experimentos de concorrencia contra o servidor real.

Cobre os desafios opcionais da AP2 e produz a evidencia da questao 4 da analise
("como evitar perda de atualizacao quando dois clientes editam o mesmo
recurso"). Os dois experimentos atacam o mesmo problema por angulos distintos:

1. **Disputa pela ultima vaga** -- varios clientes tentam ocupar a unica vaga
   simultaneamente. Exercita o *check-then-act* do lado do servidor: verificar
   capacidade e inserir precisam ser indivisiveis.

2. **Perda de atualizacao** -- dois clientes leem a mesma versao da oficina e
   ambos tentam altera-la. Exercita o controle otimista: sem `If-Match`, o
   segundo sobrescreveria o primeiro sem que ninguem percebesse.

Uso:
    python cliente_concorrente.py
"""

import sys
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "http://127.0.0.1:8000"
TIMEOUT = 5.0
CLIENTES = 12

OFICINA = {
    "titulo": "Disputa pela ultima vaga",
    "instrutor": "Helena Bastos",
    "vagas_totais": 1,
    "inicio": "2026-12-01T14:00:00Z",
    "duracao_min": 60,
    "status": "aberta",
}


def criar_oficina(dados: dict) -> tuple[int, str]:
    resposta = requests.post(f"{BASE}/oficinas", json=dados, timeout=TIMEOUT)
    resposta.raise_for_status()
    return resposta.json()["id"], resposta.headers["ETag"]


def experimento_ultima_vaga() -> bool:
    print("=" * 68)
    print(f"Experimento 1 -- {CLIENTES} clientes disputam 1 vaga")
    print("=" * 68)

    oficina_id, _ = criar_oficina(OFICINA)

    def tentar(indice: int):
        return requests.post(
            f"{BASE}/oficinas/{oficina_id}/inscricoes",
            json={
                "participante_nome": f"Participante {indice:02d}",
                "participante_email": f"participante{indice:02d}@exemplo.com",
            },
            timeout=TIMEOUT,
        )

    # As requisicoes partem praticamente juntas: o pool libera todas as threads
    # de uma vez, entao a chance de duas atingirem a verificacao de capacidade
    # antes que qualquer uma grave e alta.
    with ThreadPoolExecutor(max_workers=CLIENTES) as executor:
        respostas = list(executor.map(tentar, range(CLIENTES)))

    criadas = [r for r in respostas if r.status_code == 201]
    conflitos = [r for r in respostas if r.status_code == 409]
    inesperadas = [r for r in respostas if r.status_code not in (201, 409)]

    oficina = requests.get(f"{BASE}/oficinas/{oficina_id}", timeout=TIMEOUT).json()

    print(f"  201 Created  : {len(criadas)}")
    print(f"  409 Conflict : {len(conflitos)}")
    if inesperadas:
        print(f"  inesperadas  : {[r.status_code for r in inesperadas]}")
    print(f"  vagas_ocupadas no servidor: {oficina['vagas_ocupadas']}")
    print(f"  vagas_totais              : {oficina['vagas_totais']}")

    # A contagem de respostas sozinha nao basta: e o estado final que precisa
    # permanecer coerente, e e nele que um defeito de concorrencia apareceria.
    coerente = (
        len(criadas) == 1
        and len(conflitos) == CLIENTES - 1
        and oficina["vagas_ocupadas"] <= oficina["vagas_totais"]
    )
    print(f"\n  Resultado: {'invariante preservado' if coerente else 'INVARIANTE VIOLADO'}")
    print(
        "  Exatamente um cliente conseguiu a vaga; os demais receberam um\n"
        "  conflito explicito em vez de uma inscricao que nao caberia.\n"
    )
    return coerente


def experimento_perda_de_atualizacao() -> bool:
    print("=" * 68)
    print("Experimento 2 -- dois clientes editam a mesma oficina")
    print("=" * 68)

    oficina_id, _ = criar_oficina({**OFICINA, "titulo": "Edicao concorrente", "vagas_totais": 10})

    # Ambos leem a mesma representacao, como aconteceria se dois operadores
    # abrissem a mesma tela ao mesmo tempo.
    leitura_a = requests.get(f"{BASE}/oficinas/{oficina_id}", timeout=TIMEOUT)
    leitura_b = requests.get(f"{BASE}/oficinas/{oficina_id}", timeout=TIMEOUT)
    etag_a = leitura_a.headers["ETag"]
    etag_b = leitura_b.headers["ETag"]
    print(f"  Cliente A leu a versao {etag_a}")
    print(f"  Cliente B leu a versao {etag_b}")

    resposta_a = requests.patch(
        f"{BASE}/oficinas/{oficina_id}",
        json={"instrutor": "Alterado pelo cliente A"},
        headers={"If-Match": etag_a},
        timeout=TIMEOUT,
    )
    print(f"\n  PATCH do cliente A -> {resposta_a.status_code}")

    resposta_b = requests.patch(
        f"{BASE}/oficinas/{oficina_id}",
        json={"instrutor": "Alterado pelo cliente B"},
        headers={"If-Match": etag_b},
        timeout=TIMEOUT,
    )
    print(f"  PATCH do cliente B -> {resposta_b.status_code}", end="")
    if resposta_b.status_code == 412:
        print(f" ({resposta_b.json()['erro']['codigo']})")
    else:
        print()

    final = requests.get(f"{BASE}/oficinas/{oficina_id}", timeout=TIMEOUT).json()
    print(f"\n  instrutor no servidor: {final['instrutor']!r}")

    detectou = (
        resposta_a.status_code == 200
        and resposta_b.status_code == 412
        and final["instrutor"] == "Alterado pelo cliente A"
    )
    print(f"\n  Resultado: {'perda de atualizacao detectada' if detectou else 'FALHA NA DETECCAO'}")
    print(
        "  A alteracao de A sobreviveu. B foi informado de que sua leitura\n"
        "  ficou obsoleta e pode reler antes de decidir -- em vez de apagar\n"
        "  silenciosamente o trabalho de A.\n"
    )

    # Depois de reler, B consegue aplicar sua alteracao de forma consciente.
    etag_atual = requests.get(f"{BASE}/oficinas/{oficina_id}", timeout=TIMEOUT).headers["ETag"]
    repeticao = requests.patch(
        f"{BASE}/oficinas/{oficina_id}",
        json={"instrutor": "Alterado pelo cliente B apos reler"},
        headers={"If-Match": etag_atual},
        timeout=TIMEOUT,
    )
    print(f"  B rele e tenta de novo -> {repeticao.status_code}\n")

    return detectou and repeticao.status_code == 200


def main() -> int:
    try:
        requests.get(f"{BASE}/saude", timeout=TIMEOUT).raise_for_status()
    except requests.exceptions.RequestException:
        print(
            "Nao foi possivel conectar ao servidor.\n"
            "Suba a API com 'fastapi dev app/main.py' antes de rodar este script.",
            file=sys.stderr,
        )
        return 2

    primeiro = experimento_ultima_vaga()
    segundo = experimento_perda_de_atualizacao()
    return 0 if primeiro and segundo else 1


if __name__ == "__main__":
    sys.exit(main())
