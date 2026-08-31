# Modelagem de recursos — AP2

Documento escrito **antes** da implementação, conforme o passo 1 do roteiro mínimo
("Modele recursos e relações antes de programar").

## Domínio

Gestão de **oficinas** com vagas limitadas e as **inscrições** de participantes nelas.
O domínio é distinto do exemplo da apostila (dispositivos/leituras) e foi escolhido por
possuir conflitos de concorrência intrínsecos: duas pessoas podem disputar a última vaga.

## Recursos

### Oficina

Uma sessão com título, instrutor, horário e um número finito de vagas.

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | inteiro | Atribuído pelo servidor |
| `titulo` | texto | 3 a 120 caracteres |
| `instrutor` | texto | 3 a 80 caracteres |
| `vagas_totais` | inteiro | 1 a 500 |
| `inicio` | ISO-8601 UTC | Instante de início |
| `duracao_min` | inteiro | 15 a 480 minutos |
| `status` | enumeração | `rascunho`, `aberta`, `encerrada`, `cancelada` |
| `versao` | inteiro | Incrementado a cada escrita; base do `ETag` |
| `vagas_ocupadas` | inteiro | **Derivado** — contagem de inscrições ativas |

`vagas_ocupadas` não é armazenado. Se fosse, existiriam duas fontes de verdade para a
mesma informação (o contador e a lista de inscrições), que poderiam divergir sob
concorrência ou falha parcial de escrita. Calcular sob demanda elimina a classe inteira
de bugs de contador dessincronizado.

`versao` existe para o controle otimista de concorrência e é exposto como `ETag`.

#### Ciclo de vida do status

```
rascunho ──> aberta ──> encerrada
    │           │
    └──────> cancelada <──┘
```

Só oficinas em `aberta` aceitam novas inscrições. As demais transições produzem conflito.

### Inscrição

A participação de uma pessoa em uma oficina.

| Campo | Tipo | Regras |
| --- | --- | --- |
| `id` | inteiro | Atribuído pelo servidor |
| `oficina_id` | inteiro | Referência à oficina |
| `participante_nome` | texto | 3 a 120 caracteres |
| `participante_email` | texto | Validado por padrão de expressão regular |
| `status` | enumeração | `confirmada`, `cancelada`, `presente` |
| `criada_em` | ISO-8601 UTC | Instante do registro |

Inscrições `confirmada` e `presente` ocupam vaga; `cancelada` libera a vaga.

`participante_email` usa `Field(pattern=...)` em vez de `EmailStr` do Pydantic, que
exigiria a dependência externa `email-validator` sem agregar nada à atividade.

#### Ciclo de vida do status

```
confirmada ──> presente
     │
     └──────> cancelada
```

`cancelada` é terminal: uma inscrição cancelada não volta a ocupar vaga. Reingressar
exige criar uma nova inscrição, o que passa novamente pela verificação de capacidade —
caso contrário, um cancelamento seguido de reativação poderia furar o limite de vagas.

## Relação entre os recursos

Uma oficina possui muitas inscrições. Uma inscrição **não existe sem** a oficina: é um
recurso subordinado, e não uma entidade independente que apenas referencia outra.

Isso se reflete no desenho das URIs:

| Operação | URI | Motivo |
| --- | --- | --- |
| Criar e listar inscrições | `/oficinas/{id}/inscricoes` | A coleção só faz sentido no contexto do pai; o identificador do pai é necessário para verificar capacidade |
| Obter, alterar e cancelar uma inscrição | `/inscricoes/{id}` | O identificador da inscrição já a localiza sozinho |

A escolha de expor as operações de item em primeiro nível é deliberada. Se o
cancelamento exigisse `/oficinas/{oficina_id}/inscricoes/{id}`, todo cliente que
possuísse apenas o identificador da inscrição — o que o `Location` da criação lhe
devolve — precisaria também guardar o identificador do pai. Isso é acoplamento
desnecessário: a URI passaria a codificar uma informação que o servidor já conhece.

O custo dessa escolha é que existem dois caminhos relacionados ao mesmo conceito. O
`Location` devolvido na criação resolve a ambiguidade ao indicar qual é a URI canônica
do item.

## Invariantes do domínio

Estas são as propriedades que a API precisa preservar sob qualquer sequência de
requisições, inclusive concorrentes:

1. O número de inscrições ativas de uma oficina nunca excede `vagas_totais`.
2. Um mesmo e-mail não possui duas inscrições ativas na mesma oficina.
3. Inscrições só são criadas em oficinas com status `aberta`.
4. Nenhuma oficina com inscrições ativas é removida.
5. `vagas_totais` nunca é reduzido abaixo do número de inscrições ativas.
6. Requisição rejeitada não deixa efeito colateral no estado.

O invariante 1 é o mais interessante: verificá-lo e depois inserir são duas operações
distintas, e sem exclusão mútua dois clientes podem passar pela verificação antes que
qualquer um dos dois grave. É o padrão *check-then-act*, e é exatamente o que o
experimento de concorrência tenta provocar.

## Mapeamento para semântica HTTP

| Regra violada | Status | Justificativa |
| --- | --- | --- |
| Corpo sintaticamente válido, semanticamente inválido | 422 | Representação bem formada que não satisfaz as restrições do modelo |
| Recurso inexistente | 404 | Nada há na URI solicitada |
| Invariantes 1 a 5 | 409 | A requisição é válida em si, mas conflita com o **estado atual** do recurso |
| `If-Match` ausente em escrita de oficina | 428 | O servidor exige a precondição para evitar perda de atualização |
| `If-Match` divergente | 412 | A precondição foi enviada e falhou: houve escrita concorrente |

A distinção entre 422 e 409 é a que mais se erra: 422 é sobre a **representação
enviada**, 409 é sobre o **estado do servidor**. Uma mesma requisição pode ser aceita
agora e conflitar um segundo depois sem que nada nela tenha mudado.
