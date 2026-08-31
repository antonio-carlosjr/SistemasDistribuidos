# Análise — AP2

Documento escrito depois da coleta de evidências, e não antes. As respostas
citam resultados observados em `evidencias/tabela.md`, `evidencias/concorrencia.txt`
e `evidencias/servidor.log`.

---

## 1. Quais operações são idempotentes e por quê?

Idempotência é uma propriedade do **efeito no estado do servidor**, não da
resposta. Uma operação é idempotente quando executá-la N vezes deixa o recurso
no mesmo estado em que uma única execução o deixaria. O status devolvido pode
variar entre as tentativas sem que isso quebre a propriedade.

| Operação | Idempotente | Observação |
| --- | --- | --- |
| `GET` | Sim | Não altera estado; é também segura |
| `PUT /oficinas/{id}` | Sim, quanto ao estado final | A repetição exige o ETag vigente |
| `PATCH /oficinas/{id}` | Depende do conteúdo | Aqui sim: todos os campos são atribuições absolutas |
| `DELETE /oficinas/{id}` | Sim, quanto ao efeito | Segunda chamada responde 404 |
| `DELETE /inscricoes/{id}` | Sim, integralmente | Segunda chamada responde 204 |
| `POST /oficinas` | Não | Cada chamada cria um recurso distinto |
| `POST /oficinas/{id}/inscricoes` | Não | A repetição conflita em vez de duplicar |

### O que as evidências mostram

**`DELETE` de oficina** (cenários 38 e 39 da tabela): a primeira chamada devolve
204, a segunda devolve 404. O efeito é idempotente — o recurso está ausente nos
dois casos —, mas os status diferem porque **cada resposta descreve a requisição
que a originou**, e não o estado final. A segunda requisição de fato não
encontrou nada para remover, e dizer isso é mais informativo do que mentir 204.

**`DELETE` de inscrição** (cenários 33 e 34): as duas chamadas devolvem 204. A
diferença vem da modelagem: cancelar não apaga o registro, apenas muda seu
status para `cancelada`. Como o registro permanece, a segunda chamada encontra o
recurso e reaplica uma operação que já estava aplicada. É o caso mais limpo de
idempotência da API — mesmo efeito e mesmo status.

**Os dois comportamentos de `POST`.** Esta é a observação mais interessante que a
API produz, porque os dois casos convivem na mesma aplicação:

- Repetir `POST /oficinas` (cenário 3) devolve **201** e cria um segundo
  recurso, com identificador diferente. É a não-idempotência clássica.
- Repetir `POST /oficinas/{id}/inscricoes` (cenário 22) devolve **409**.

Nenhum dos dois é idempotente. A diferença não está no método, mas no
**invariante do recurso**: inscrições têm uma regra de unicidade — um e-mail
ativo por oficina — e oficinas não têm. Onde existe invariante de unicidade, a
repetição encontra o conflito; onde não existe, ela duplica. Isso mostra que a
não-idempotência do POST não é um comportamento único, e sim a ausência de
garantia: o que acontece na repetição depende inteiramente do domínio.

**Escritas repetidas com o mesmo ETag.** Reenviar uma alteração com o ETag já
consumido devolve **412**, e não 200 — observado no cenário 18, um `PATCH`, e
válido igualmente para `PUT`. Isso não viola a idempotência: o teste
`test_put_identico_repetido_leva_ao_mesmo_estado`
demonstra que, relendo o ETag entre as tentativas, a representação resultante é
idêntica em todos os campos exceto `versao`. A precondição é uma camada de
controle de concorrência sobreposta ao método; ela restringe *quando* a operação
é aceita, sem alterar *qual* estado ela produz.

---

## 2. Qual a diferença entre "servidor respondeu erro" e "cliente não conseguiu obter resposta"?

A diferença é a existência de informação.

Quando o servidor responde um erro, há uma mensagem HTTP completa: status,
cabeçalhos e corpo. O cliente sabe que a requisição chegou, foi interpretada e
recebeu um veredito. Pode agir sobre ele.

Quando o cliente não obtém resposta, ele não sabe praticamente nada. Não sabe se
a requisição chegou ao servidor, se chegou e foi processada, se foi processada e
a resposta se perdeu no caminho, ou se nunca saiu da máquina dele.

### Três situações que as evidências separam

| Situação | O que o cliente recebe | O que ele sabe |
| --- | --- | --- |
| **503** (cenário 45) | Status, corpo e `Retry-After: 5` | O serviço existe, está indisponível e sugere quando tentar de novo |
| **Timeout** (cenários 40–41) | Exceção `Timeout` | Desistiu de esperar. **Não sabe se a operação ocorreu** |
| **ConnectionError** (cenários 47–48) | Exceção `ConnectionError` | Não houve conexão. A operação quase certamente não ocorreu |

O par 503 versus `ConnectionError` é frequentemente tratado como equivalente —
"o serviço está fora" — mas são coisas diferentes na prática. Com 503 há um
servidor vivo que escolheu recusar, e o `Retry-After` é uma instrução dele. Com
`ConnectionError` não há interlocutor: qualquer política de reenvio é uma
suposição do cliente.

O **timeout é o caso mais difícil dos três**, e é o que justifica a atenção da
disciplina à idempotência. O cliente desistiu, mas o servidor pode ter executado
a operação inteira e a resposta pode ter chegado tarde demais. Para uma leitura,
isso é irrelevante: basta repetir. Para uma escrita, é decisivo. Repetir um
`PUT` após timeout é seguro, porque o estado final é o mesmo tenha a primeira
tentativa ocorrido ou não. Repetir um `POST /oficinas` pode criar duas oficinas,
sendo que o usuário pediu uma. Repetir um `POST` de inscrição é seguro por
acidente: se a primeira tentativa passou, a segunda recebe 409 e o estado
permanece correto — a regra de unicidade acaba funcionando como proteção contra
reenvio.

É por isso que todo `requests` em `cliente_testes.py` tem `timeout` explícito.
Sem ele a biblioteca espera indefinidamente, e um cliente travado é pior que um
cliente com erro: a falha deixa de ser observável e se propaga como lentidão
para quem depende dele.

---

## 3. Que decisões da API aumentam ou reduzem o acoplamento entre cliente e servidor?

### Decisões que reduzem acoplamento

**Operações de item da inscrição em primeiro nível.** Criar e listar são
aninhadas (`/oficinas/{id}/inscricoes`), mas obter, alterar e cancelar usam
`/inscricoes/{id}`. Se o cancelamento exigisse o caminho completo, todo cliente
que possuísse apenas o identificador da inscrição precisaria também guardar o da
oficina. A URI passaria a codificar uma informação que o servidor já conhece.

**`Location` nas criações.** O servidor informa onde o recurso passou a existir.
Sem esse cabeçalho o cliente teria de montar a URI a partir do corpo, o que o
acopla ao formato do identificador — e uma futura troca de inteiro sequencial por
UUID quebraria todos os clientes.

**Listagens em envelope, não em array cru.** `GET /oficinas` devolve
`{total, limite, offset, itens}`. Acrescentar metadados a um objeto é uma
mudança compatível; trocar um array por um objeto não é. O envelope reserva o
espaço de evolução desde o início.

**Envelope de erro estável.** Todo erro tem a forma
`{erro: {codigo, mensagem, request_id}}`. O cliente decide o que fazer pelo
`codigo`, um identificador estável, sem inspecionar o texto da `mensagem` — que
pode ser reescrito a qualquer momento sem quebrar ninguém.

**Códigos de status distintos por causa.** Separar 404, 409, 412, 422 e 428
permite ao cliente reagir apropriadamente a cada um. Uma API que devolvesse 400
para tudo obrigaria o cliente a fazer análise textual da mensagem para descobrir
o que houve.

**`vagas_disponiveis` calculado pelo servidor.** O cliente não precisa conhecer
a regra de quais status ocupam vaga. Se essa regra mudar, nenhum cliente muda
junto.

### Decisões que aumentam acoplamento

**`If-Match` obrigatório nas escritas de oficina.** O cliente é obrigado a ler
antes de escrever e a manter o ETag entre as duas operações. Isso é acoplamento
real, adotado deliberadamente: o preço de não ter é a perda silenciosa de
atualização, demonstrada na questão 4. A alternativa — precondição opcional — foi
descartada porque tornaria a proteção efetiva apenas para os clientes que já
sabem que ela existe, isto é, justamente os que menos precisam dela.

**`extra="forbid"` nos modelos de entrada.** Um campo não previsto vira 422 em
vez de ser ignorado. Acopla o cliente ao conjunto exato de campos aceitos, mas
evita a falha silenciosa em que ele acredita ter feito uma alteração que nunca
aconteceu. Erro explícito é melhor que silêncio, e a assimetria de custo entre
os dois justifica a rigidez.

**Ciclo de vida de status validado no servidor.** As transições permitidas são
uma regra que o cliente precisa conhecer para construir uma interface coerente.
O acoplamento é aceito porque a alternativa — deixar qualquer transição passar —
permitiria estados sem sentido, como uma oficina cancelada que volta a aceitar
inscrições.

**Ausência de hipermídia.** A API não devolve links de navegação. Os clientes
constroem URIs a partir de conhecimento prévio da estrutura, o que os acopla ao
desenho dos caminhos. É a decisão mais distante do REST original, tomada por
proporcionalidade: hipermídia se paga em APIs públicas com muitos consumidores
independentes, não num laboratório com um cliente conhecido.

---

## 4. Como evitar perda de atualização quando dois clientes editam o mesmo recurso?

### O problema

Dois clientes leem a mesma representação, ambos a modificam e ambos gravam. A
segunda gravação sobrescreve a primeira. Ninguém recebe erro, e a alteração do
primeiro desaparece sem deixar rastro. É a pior classe de falha: silenciosa e
indistinguível de funcionamento normal.

### A solução adotada: controle otimista com ETag e If-Match

Cada oficina tem um contador `versao`, incrementado a cada escrita e exposto
como `ETag`. Escritas exigem `If-Match`. O servidor compara a versão informada
com a vigente e recusa quando divergem.

`evidencias/concorrencia.txt` registra o experimento:

```
Cliente A leu a versao "1"
Cliente B leu a versao "1"

PATCH do cliente A -> 200
PATCH do cliente B -> 412 (precondicao_falhou)

instrutor no servidor: 'Alterado pelo cliente A'
```

A alteração de A sobreviveu. B foi informado de que sua leitura ficou obsoleta e
pôde reler antes de decidir — na repetição com o ETag vigente, sua alteração foi
aceita com 200. A perda de atualização deixou de ser silenciosa e virou um erro
que o cliente pode tratar.

Ausência da precondição recebe **428 Precondition Required**, e não é tratada
como permissão para sobrescrever. Essa escolha é o que dá valor ao mecanismo: se
o `If-Match` fosse opcional, um cliente que simplesmente não o enviasse
continuaria capaz de causar a perda que o mecanismo existe para impedir.

### Por que otimista e não pessimista

O controle pessimista — travar o recurso na leitura e liberar na escrita —
resolveria o mesmo problema, mas transfere um novo: um cliente que lê e nunca
grava mantém o recurso travado. Seria preciso expiração de trava, renovação e
tratamento de trava órfã. O controle otimista não bloqueia nada e só custa uma
releitura no caso raro de conflito real. Em recursos com muito mais leituras que
escritas concorrentes, essa é a troca certa.

### O segundo mecanismo: exclusão mútua no repositório

O ETag protege contra escritas baseadas em leituras obsoletas. Ele **não**
protege o outro problema: `POST` de inscrição não tem representação prévia para
validar, e portanto não tem ETag. Ali a proteção precisa vir da atomicidade.

`Repositorio` executa todo ciclo ler-verificar-escrever sob um `RLock`.
Verificar se há vaga e inserir a inscrição são operações distintas, e sem
exclusão mútua dois clientes podem passar pela verificação antes que qualquer um
grave — o padrão *check-then-act*. O experimento com 12 clientes disputando uma
vaga confirma o resultado esperado:

```
201 Created  : 1
409 Conflict : 11
vagas_ocupadas no servidor: 1
```

Que o teste tem valor foi verificado diretamente: substituindo o `RLock` por um
contexto vazio e inserindo uma pausa entre a verificação e a inserção, tanto
`test_capacidade_nunca_e_excedida_sob_concorrencia` quanto
`test_identificadores_nao_se_repetem_sob_concorrencia` passam a falhar. O teste
não passa por acaso — ele passa por causa do lock.

A conferência do `If-Match` também acontece **dentro** do lock. Fora dele, o
próprio controle de versão teria a corrida que existe para eliminar: dois
clientes poderiam validar a mesma versão antes que qualquer um a incrementasse.

### Limite conhecido

O `RLock` coordena apenas threads do mesmo processo. Duas instâncias do servidor
sobre o mesmo arquivo não estariam protegidas: cada uma teria seu próprio lock e
sua própria cópia do estado em memória. Resolver isso exigiria trava de arquivo
do sistema operacional, um armazenamento com transações reais, ou mover o
invariante para uma restrição do banco.

O ETag, por ser um mecanismo de protocolo e não de processo, continuaria
funcionando parcialmente entre instâncias — mas só se a versão fosse lida e
gravada atomicamente no armazenamento compartilhado, o que recai no mesmo
requisito. Vale registrar a conclusão geral: **HTTP oferece o vocabulário para
expressar o conflito, não a garantia de detectá-lo**. Quem detecta é a camada de
armazenamento.

---

## Justificativa das escolhas de URI, método e status

### URIs

Substantivos no plural, hierarquia refletindo a dependência real entre as
entidades, e nenhum verbo no caminho. Cancelar uma inscrição é
`DELETE /inscricoes/{id}`, e não `POST /inscricoes/{id}/cancelar`: a combinação
de recurso e método já expressa a semântica.

A exceção consciente é `/admin/manutencao`, que não é um recurso do domínio e
sim uma chave operacional. Está isolada sob um prefixo próprio justamente para
não se confundir com o modelo de negócio.

### Métodos

`PUT` e `PATCH` coexistem porque servem a necessidades diferentes. `PUT` carrega
a representação inteira e é a operação natural de um formulário de edição
completo. `PATCH` carrega apenas o que muda, e é o que um cliente usa para
alterar só o status ou só o número de vagas, sem precisar conhecer nem reenviar
os demais campos.

`DELETE` de inscrição faz cancelamento lógico em vez de remoção física. Do ponto
de vista do cliente a semântica é a esperada — a vaga é liberada e a inscrição
deixa de valer —, e o histórico de desistências é preservado.

### Status

| Código | Quando | Por quê |
| --- | --- | --- |
| 200 | Operação concluída com corpo | — |
| 201 | Recurso criado | Acompanha `Location` |
| 204 | Sucesso sem corpo | Remoção e cancelamento |
| 304 | Representação inalterada | Resposta a `If-None-Match` |
| 401 | Token administrativo ausente ou inválido | Autenticação, não autorização |
| 404 | Recurso inexistente | Inclusive ao listar filhos de pai inexistente |
| 409 | Conflito com o estado atual | As seis regras de domínio |
| 412 | `If-Match` divergente | Houve escrita concorrente |
| 422 | Representação semanticamente inválida | Padrão do FastAPI |
| 428 | `If-Match` ausente | A precondição é exigida, não opcional |
| 500 | Falha não prevista | Sem expor detalhes internos |
| 503 | Manutenção | Acompanha `Retry-After` |

A distinção mais importante é entre **422 e 409**, e é a que mais se erra na
prática. 422 fala da representação enviada: ela está malformada segundo as
regras do modelo e seria rejeitada em qualquer instante. 409 fala do estado do
servidor: a requisição está correta em si e conflita com a situação atual. A
mesma inscrição rejeitada com 409 por lotação seria aceita um segundo antes, sem
que nada nela mudasse.

`404` ao listar inscrições de uma oficina inexistente, em vez de lista vazia, é
outra decisão deliberada. São situações distintas — "esta oficina não tem
inscritos" e "esta oficina não existe" — e confundi-las esconderia do cliente
que ele está consultando um identificador errado.

---

## Considerações finais

Três limites desta implementação merecem registro explícito, porque uma análise
que só descreve acertos é incompleta:

1. **A persistência não é transacional.** Escritas são atômicas por arquivo, não
   por operação lógica. Uma falha entre duas gravações relacionadas deixaria
   estado inconsistente. O lock reduz a janela, mas não a elimina.

2. **A coordenação não atravessa processos.** Está detalhado na questão 4. É o
   limite mais relevante do ponto de vista de sistemas distribuídos: a solução
   funciona porque há uma única instância.

3. **Não há autenticação de participantes.** Qualquer cliente pode cancelar
   qualquer inscrição. O token cobre apenas o endpoint administrativo. Numa
   aplicação real, a posse da inscrição precisaria ser verificada — e o status
   correto para a recusa seria 403, não 409.

Nenhum dos três é resolvido por usar REST ou HTTP. É a observação que atravessa
o capítulo 4 da apostila e que esta atividade confirma na prática: o protocolo
oferece vocabulário e semântica para expressar problemas de sistemas
distribuídos, mas resolvê-los continua sendo trabalho da aplicação e da camada
de armazenamento.
