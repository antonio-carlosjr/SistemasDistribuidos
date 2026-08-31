"""Experimento de timeout da secao 4.8 da apostila.

Chama a rota que demora 2 segundos usando tres limites diferentes. Os dois
primeiros expiram; o terceiro completa. O ponto nao e que o timeout funciona, e
sim o que o cliente sabe em cada caso: quando ele expira, o cliente desistiu sem
saber se o servidor executou a operacao ou nao.

Uso (com o servidor no ar):
    python demo_timeout.py
"""

import sys

import requests

URL = "http://127.0.0.1:8000/debug/lento?segundos=2"
LIMITES = (0.5, 1.0, 3.0)


def main() -> int:
    print("Rota que demora 2s, chamada com tres limites de timeout:\n")

    for limite in LIMITES:
        rotulo = f"  timeout={limite}s"
        try:
            resposta = requests.get(URL, timeout=limite)
            print(f"{rotulo:<18} -> HTTP {resposta.status_code}  {resposta.json()}")
        except requests.exceptions.Timeout:
            print(f"{rotulo:<18} -> Timeout: desistiu antes de qualquer resposta")
        except requests.exceptions.ConnectionError:
            print(f"{rotulo:<18} -> ConnectionError: servidor fora do ar")
            return 2

    print(
        "\nTimeout nao e o mesmo que erro do servidor: aqui nao ha status nem\n"
        "corpo para interpretar. Para uma escrita, o cliente fica sem saber se\n"
        "a operacao foi aplicada -- e por isso que idempotencia importa."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
