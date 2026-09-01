# Tabela de evidencias -- AP2

Gerada por `cliente_testes.py` a partir da execucao real contra o
servidor. Os valores da coluna *obtido* nao sao transcritos a mao.

**48 de 48 cenarios com resultado igual ao esperado.**


## Sucesso

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Sonda de saude | `GET /saude` | 200 | 200 | - | OK |
| 2 | Criar oficina | `POST /oficinas` | 201 | 201 | - | OK |
| | _Responde Location e ETag_ | | | | | |
| 3 | Criar a mesma oficina de novo | `POST /oficinas` | 201 | 201 | - | OK |
| | _POST nao e idempotente: cria um segundo recurso_ | | | | | |
| 4 | Listar oficinas | `GET /oficinas` | 200 | 200 | - | OK |
| 5 | Obter oficina | `GET /oficinas/6` | 200 | 200 | - | OK |
| 6 | Listar inscricoes da oficina | `GET /oficinas/6/inscricoes` | 200 | 200 | - | OK |

## Validacao de entrada (422)

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 7 | Criar oficina com titulo curto | `POST /oficinas` | 422 | 422 | entrada_invalida | OK |
| 8 | Criar oficina com campo desconhecido | `POST /oficinas` | 422 | 422 | entrada_invalida | OK |
| | _Campo nao previsto e erro, nao silencio_ | | | | | |
| 9 | Inscrever com e-mail malformado | `POST /oficinas/6/inscricoes` | 422 | 422 | entrada_invalida | OK |
| 10 | Listar com limite acima do teto | `GET /oficinas?limite=1000` | 422 | 422 | entrada_invalida | OK |
| | _Paginacao tem teto para a resposta nao crescer sem limite_ | | | | | |

## Recurso inexistente (404)

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 11 | Obter oficina inexistente | `GET /oficinas/9999` | 404 | 404 | nao_encontrado | OK |
| 12 | Listar inscricoes de oficina inexistente | `GET /oficinas/9999/inscricoes` | 404 | 404 | nao_encontrado | OK |
| | _404, e nao lista vazia: sao situacoes distintas_ | | | | | |
| 13 | Obter inscricao inexistente | `GET /inscricoes/9999` | 404 | 404 | nao_encontrado | OK |

## Concorrencia e cache (304/412/428)

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 14 | Obter com If-None-Match atual | `GET /oficinas/6` | 304 | 304 | - | OK |
| | _Representacao inalterada: resposta sem corpo_ | | | | | |
| 15 | Alterar sem If-Match | `PATCH /oficinas/6` | 428 | 428 | precondicao_obrigatoria | OK |
| | _A precondicao e exigida para evitar perda de atualizacao_ | | | | | |
| 16 | Alterar com ETag inexistente | `PATCH /oficinas/6` | 412 | 412 | precondicao_falhou | OK |
| 17 | Alterar com ETag correto | `PATCH /oficinas/6` | 200 | 200 | - | OK |
| | _A versao avanca e o ETag anterior deixa de valer_ | | | | | |
| 18 | Repetir a alteracao com o ETag ja consumido | `PATCH /oficinas/6` | 412 | 412 | precondicao_falhou | OK |
| | _Perda de atualizacao detectada em vez de sobrescrita silenciosa_ | | | | | |
| 19 | Reler para obter o ETag vigente | `GET /oficinas/6` | 200 | 200 | - | OK |
| 20 | Substituir com If-Match vigente | `PUT /oficinas/6` | 200 | 200 | - | OK |

## Conflitos de dominio (409)

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 21 | Inscrever participante | `POST /oficinas/6/inscricoes` | 201 | 201 | - | OK |
| 22 | Inscrever o mesmo e-mail de novo | `POST /oficinas/6/inscricoes` | 409 | 409 | inscricao_duplicada | OK |
| | _Repetir POST aqui conflita, em vez de duplicar_ | | | | | |
| 23 | Inscrever um segundo participante | `POST /oficinas/6/inscricoes` | 201 | 201 | - | OK |
| | _Leva a oficina a duas vagas ocupadas de tres_ | | | | | |
| 24 | Remover oficina com inscritos | `DELETE /oficinas/6` | 409 | 409 | oficina_com_inscricoes | OK |
| | _409 e nao 403: o impedimento vem do estado, nao da permissao_ | | | | | |
| 25 | Reduzir vagas abaixo do ocupado | `PATCH /oficinas/6` | 409 | 409 | vagas_abaixo_do_ocupado | OK |
| | _Ha duas inscricoes ativas; aceitar deixaria estado impossivel_ | | | | | |
| 26 | Transicao de status invalida | `PATCH /oficinas/6` | 409 | 409 | transicao_invalida | OK |
| 27 | Criar oficina de vaga unica | `POST /oficinas` | 201 | 201 | - | OK |
| 28 | Ocupar a unica vaga | `POST /oficinas/8/inscricoes` | 201 | 201 | - | OK |
| 29 | Inscrever com a oficina lotada | `POST /oficinas/8/inscricoes` | 409 | 409 | oficina_lotada | OK |
| 30 | Criar oficina em rascunho | `POST /oficinas` | 201 | 201 | - | OK |
| 31 | Inscrever em oficina nao aberta | `POST /oficinas/9/inscricoes` | 409 | 409 | oficina_nao_aberta | OK |

## Idempotencia

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 32 | Marcar presenca | `PATCH /inscricoes/3` | 200 | 200 | - | OK |
| 33 | Cancelar inscricao | `DELETE /inscricoes/3` | 204 | 204 | - | OK |
| 34 | Cancelar a mesma inscricao de novo | `DELETE /inscricoes/3` | 204 | 204 | - | OK |
| | _Mesmo efeito e mesmo status: idempotente_ | | | | | |
| 35 | Reativar inscricao cancelada | `PATCH /inscricoes/3` | 409 | 409 | transicao_invalida | OK |
| | _Reativar sem reavaliar capacidade furaria o limite de vagas_ | | | | | |
| 36 | Cancelar a segunda inscricao | `DELETE /inscricoes/4` | 204 | 204 | - | OK |
| | _Esvazia a oficina para o cenario de remocao_ | | | | | |
| 37 | Reler a oficina liberada | `GET /oficinas/6` | 200 | 200 | - | OK |
| 38 | Remover oficina sem inscritos | `DELETE /oficinas/6` | 204 | 204 | - | OK |
| 39 | Remover a mesma oficina de novo | `DELETE /oficinas/6` | 404 | 404 | nao_encontrado | OK |
| | _Efeito identico, status diferente: 404 relata esta requisicao_ | | | | | |

## Timeout do cliente

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 40 | Rota de 2s com timeout de 0.5s | `GET /debug/lento?segundos=2 (timeout 0.5s)` | Timeout | Timeout | - | OK |
| 41 | Rota de 2s com timeout de 1.0s | `GET /debug/lento?segundos=2 (timeout 1.0s)` | Timeout | Timeout | - | OK |
| 42 | Rota de 2s com timeout de 3.0s | `GET /debug/lento?segundos=2` | 200 | 200 | - | OK |

## Indisponibilidade (503)

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 43 | Ativar manutencao sem token | `POST /admin/manutencao` | 401 | 401 | nao_autorizado | OK |
| 44 | Ativar manutencao com token | `POST /admin/manutencao` | 200 | 200 | - | OK |
| 45 | Listar oficinas em manutencao | `GET /oficinas` | 503 | 503 | em_manutencao | OK |
| | _Ha resposta: status e Retry-After informam o cliente_ | | | | | |
| 46 | Desativar manutencao | `POST /admin/manutencao` | 200 | 200 | - | OK |

## Falha de conectividade

| # | Cenario | Requisicao | Esperado | Obtido | Codigo | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 47 | Listar oficinas com o servidor desligado | `GET /oficinas` | ConnectionError | ConnectionError | - | OK |
| | _Nao ha resposta: nem status, nem corpo, nem Retry-After_ | | | | | |
| 48 | Criar oficina com o servidor desligado | `POST /oficinas` | ConnectionError | ConnectionError | - | OK |
| | _O cliente nao sabe se a operacao ocorreu_ | | | | | |
