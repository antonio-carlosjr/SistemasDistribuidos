"""Gera dados de teste para a demonstracao.

Atende ao passo 2 do roteiro minimo ("implemente a API e gere dados de teste").
O conjunto e escolhido para que os cenarios de erro sejam alcancaveis sem
preparacao manual: ha uma oficina a uma vaga do limite, uma ja lotada, uma em
rascunho e uma encerrada. Sem isso, demonstrar um 409 exigiria montar o estado
na hora, o que e lento e fragil numa apresentacao.

Uso:
    python seed.py
"""

from app.modelos import InscricaoEntrada, OficinaEntrada
from app.repositorio import repositorio

OFICINAS = [
    # Aberta e vazia: destino dos cenarios de sucesso.
    {
        "titulo": "Introducao a Kubernetes",
        "instrutor": "Ana Reis",
        "vagas_totais": 20,
        "inicio": "2026-09-10T14:00:00Z",
        "duracao_min": 180,
        "status": "aberta",
    },
    # Uma unica vaga: e nela que os dois clientes concorrentes disputam.
    {
        "titulo": "Observabilidade com OpenTelemetry",
        "instrutor": "Bruno Carvalho",
        "vagas_totais": 1,
        "inicio": "2026-09-12T09:00:00Z",
        "duracao_min": 120,
        "status": "aberta",
    },
    # Ja lotada: produz 409 de imediato.
    {
        "titulo": "Filas e mensageria com RabbitMQ",
        "instrutor": "Carla Nogueira",
        "vagas_totais": 2,
        "inicio": "2026-09-15T19:00:00Z",
        "duracao_min": 240,
        "status": "aberta",
    },
    # Nao aceita inscricoes: produz 409 por status.
    {
        "titulo": "Consenso distribuido e Raft",
        "instrutor": "Diego Alves",
        "vagas_totais": 30,
        "inicio": "2026-10-01T14:00:00Z",
        "duracao_min": 180,
        "status": "rascunho",
    },
    {
        "titulo": "Padroes de resiliencia em microsservicos",
        "instrutor": "Elisa Prado",
        "vagas_totais": 15,
        "inicio": "2026-08-01T14:00:00Z",
        "duracao_min": 120,
        "status": "encerrada",
    },
]

#: Preenche a oficina de indice 2 ate a lotacao.
INSCRICOES_INICIAIS = [
    (3, "Fernanda Dias", "fernanda.dias@exemplo.com"),
    (3, "Gabriel Matos", "gabriel.matos@exemplo.com"),
]


def semear() -> None:
    repositorio.redefinir()

    for dados in OFICINAS:
        oficina = repositorio.criar_oficina(OficinaEntrada(**dados))
        print(
            f"oficina {oficina.id:>2}  {oficina.status.value:<10} "
            f"{oficina.vagas_totais:>3} vagas  {oficina.titulo}"
        )

    for oficina_id, nome, email in INSCRICOES_INICIAIS:
        inscricao = repositorio.criar_inscricao(
            oficina_id,
            InscricaoEntrada(participante_nome=nome, participante_email=email),
        )
        print(f"inscricao {inscricao.id:>2} na oficina {oficina_id}  {email}")

    print("\nEstado pronto para a demonstracao:")
    print("  oficina 1 -- aberta e vazia (cenarios de sucesso)")
    print("  oficina 2 -- aberta com 1 vaga (disputa concorrente)")
    print("  oficina 3 -- lotada (409 oficina_lotada)")
    print("  oficina 4 -- rascunho (409 oficina_nao_aberta)")
    print("  oficina 5 -- encerrada (409 oficina_nao_aberta)")


if __name__ == "__main__":
    semear()
