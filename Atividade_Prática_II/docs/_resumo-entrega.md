# Visão geral

## O domínio

A API gerencia **oficinas** com vagas limitadas e as **inscrições** de
participantes nelas. O domínio é distinto do exemplo da apostila
(dispositivos/leituras), conforme exigido, e foi escolhido por três motivos:

1. Possui **duas coleções com dependência real** — uma inscrição não existe sem
   a oficina a que pertence.
2. Produz **conflitos de naturezas diferentes**: capacidade esgotada e violação
   de unicidade são ambos 409, mas por razões distintas.
3. Tem **disputa natural por um recurso escasso** — a última vaga —, o que torna
   demonstráveis os problemas de concorrência que a disciplina discute.

## Entregáveis

| # | Entregável exigido | Onde está nesta entrega |
| --- | --- | --- |
| 1 | Código-fonte organizado | Repositório, seção 3 descreve a estrutura |
| 2 | README com instruções de execução | Seção 3 |
| 3 | Coleção de testes/curl ou script cliente | Seção 3 e 5; suíte pytest, `cliente_testes.py` e os scripts em `demo/` |
| 4 | Tabela cenário / requisição / status esperado / obtido | Seção 4 |
| 5 | Demonstração prática curta | Seção 5, com capturas de cada passo |

As questões de análise, as justificativas de URI, método e status, e a
modelagem prévia dos recursos estão nas seções 6 e 2.

## Requisitos obrigatórios

| Requisito | Atendimento |
| --- | --- |
| Pelo menos duas coleções relacionadas | `/oficinas` e `/oficinas/{id}/inscricoes` |
| No mínimo seis endpoints, com GET, POST, PUT ou PATCH e DELETE | 14 endpoints: 11 de domínio e 3 operacionais |
| Validação de entrada | Pydantic com restrições por campo e `extra="forbid"` |
| Tratamento explícito de 404 | Oficina e inscrição inexistentes, em ambos os níveis |
| Tratamento explícito de 409 | Seis regras distintas de conflito |
| Cliente de teste programático com timeout definido | `cliente_testes.py`, com `timeout` em toda chamada |
| Persistência em arquivo ou banco | Arquivo JSON com escrita atômica e exclusão mútua |

## Roteiro mínimo

| Passo | Cumprimento |
| --- | --- |
| 1. Modelar recursos e relações antes de programar | Seção 2, escrita e versionada antes do código |
| 2. Implementar a API e gerar dados de teste | `seed.py` prepara os cinco estados da demonstração |
| 3. Criar roteiro automatizado de testes | 40 testes pytest e 48 cenários no cliente programático |
| 4. Provocar dois erros de aplicação e uma falha de conectividade | Seis conflitos, além de 404, 422, 412, 428, 503 e `ConnectionError` |
| 5. Coletar logs e organizar evidências | Log estruturado por requisição, tabela gerada e capturas de tela |

## Desafios opcionais

| Desafio | Situação |
| --- | --- |
| ETag / versionamento otimista | Implementado, com 428, 412 e 304 |
| Autenticação baseada em token | Parcial — protege apenas o endpoint administrativo |
| Dois clientes concorrentes observando conflitos | Implementado em `cliente_concorrente.py`, com dois experimentos |

## Resultados verificados

| Verificação | Resultado |
| --- | --- |
| Suíte automatizada | 40 de 40 testes aprovados |
| Cenários do cliente programático | 48 de 48 com status obtido igual ao esperado |
| Disputa de 12 clientes por 1 vaga | Exatamente um 201 e onze 409; capacidade preservada |
| Perda de atualização | Detectada com 412; a primeira escrita sobrevive |

Os dois testes de concorrência foram validados por contraprova: substituindo o
lock do repositório por um contexto vazio, ambos passam a falhar. Eles não
passam por acaso.

## Limites conhecidos

Três limitações são registradas explicitamente, porque uma análise que só
descreve acertos é incompleta:

1. **A persistência não é transacional.** As escritas são atômicas por arquivo,
   e não por operação lógica.
2. **A coordenação não atravessa processos.** O lock protege threads de uma
   única instância; duas instâncias sobre o mesmo arquivo não estariam
   protegidas.
3. **Não há autenticação de participantes.** Qualquer cliente pode cancelar
   qualquer inscrição; o token cobre apenas o endpoint administrativo.

Nenhuma das três é resolvida por usar REST ou HTTP — o que é, em si, a
observação central da atividade.
