"""Configuracao central da API de oficinas.

Valores vem de variaveis de ambiente para que os testes possam apontar o
armazenamento para um arquivo temporario sem tocar nos dados de demonstracao.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Arquivo JSON que guarda o estado. Os testes sobrescrevem via OFICINAS_DB.
CAMINHO_DADOS = Path(os.getenv("OFICINAS_DB", RAIZ / "dados" / "estado.json"))

# Log estruturado de requisicoes; e entregavel, entao vive em evidencias/.
CAMINHO_LOG = Path(os.getenv("OFICINAS_LOG", RAIZ / "evidencias" / "servidor.log"))

# Token do endpoint administrativo. O valor padrao serve apenas ao laboratorio:
# em producao um segredo nunca teria default embutido no codigo.
TOKEN_ADMIN = os.getenv("OFICINAS_TOKEN_ADMIN", "token-de-laboratorio")

# Limites de paginacao. Listagem sem teto e o erro descrito na secao 4.10 da
# apostila: o custo da resposta cresce sem limite junto com a colecao.
LIMITE_PADRAO = 20
LIMITE_MAXIMO = 100

# Teto da rota de latencia artificial, para que um cliente nao consiga manter
# uma conexao aberta indefinidamente.
ATRASO_MAXIMO_S = 10.0
