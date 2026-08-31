# AP2 — API REST de Inscrições em Oficinas

Atividade Prática II de Sistemas Distribuídos. API REST para gestão de oficinas
com vagas limitadas e das inscrições de participantes nelas.

O domínio é diferente do exemplo da apostila (dispositivos/leituras) e foi
escolhido por ter conflitos de concorrência intrínsecos: duas pessoas podem
disputar a última vaga, e é isso que torna observáveis os problemas que a
disciplina discute.

---

## Execução

Requer Python 3.10 ou superior.

```bash
python -m venv .venv
```

Ative o ambiente virtual — no Windows PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

No Linux ou macOS:

```bash
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

Gere os dados de demonstração **antes** de subir o servidor — a API carrega o
estado do arquivo na inicialização, então semear com o servidor no ar não teria
efeito sobre o processo já em execução:

```bash
python seed.py
```

Suba a API:

```bash
fastapi dev app/main.py
```

A documentação interativa fica em <http://127.0.0.1:8000/docs>. Ela é útil para
exploração, mas os testes abaixo usam linha de comando e cliente programático
para deixar a mensagem HTTP explícita.

---

## Endpoints

### Oficinas

| Método | Caminho | Descrição | Status |
| --- | --- | --- | --- |
| `GET` | `/oficinas` | Lista paginada, filtrável por `status` | 200, 422 |
| `POST` | `/oficinas` | Cria oficina | 201, 422 |
| `GET` | `/oficinas/{id}` | Obtém oficina | 200, 304, 404 |
| `PUT` | `/oficinas/{id}` | Substitui a representação | 200, 404, 409, 412, 422, 428 |
| `PATCH` | `/oficinas/{id}` | Altera parcialmente | 200, 404, 409, 412, 422, 428 |
| `DELETE` | `/oficinas/{id}` | Remove oficina | 204, 404, 409, 412, 428 |

### Inscrições

| Método | Caminho | Descrição | Status |
| --- | --- | --- | --- |
| `GET` | `/oficinas/{id}/inscricoes` | Lista as inscrições da oficina | 200, 404 |
| `POST` | `/oficinas/{id}/inscricoes` | Inscreve participante | 201, 404, 409, 422 |
| `GET` | `/inscricoes/{id}` | Obtém inscrição | 200, 404 |
| `PATCH` | `/inscricoes/{id}` | Altera o status | 200, 404, 409, 422 |
| `DELETE` | `/inscricoes/{id}` | Cancela e libera a vaga | 204, 404 |

### Operacionais

Existem para tornar reproduzíveis os experimentos da seção 4.8 da apostila.

| Método | Caminho | Descrição |
| --- | --- | --- |
| `GET` | `/saude` | 200 normal, 503 em manutenção |
| `POST` | `/admin/manutencao` | Liga/desliga manutenção (exige `X-Token-Admin`) |
| `GET` | `/debug/lento?segundos=2` | Atraso deliberado, para exercer timeouts |

---

## Conflitos tratados (409)

Seis regras distintas produzem conflito. Todas dependem do **estado atual** do
recurso, e não da representação enviada — é o que as separa do 422:

| Código | Situação |
| --- | --- |
| `oficina_lotada` | Não há vagas disponíveis |
| `inscricao_duplicada` | O e-mail já tem inscrição ativa nesta oficina |
| `oficina_nao_aberta` | A oficina não está com status `aberta` |
| `oficina_com_inscricoes` | Remoção de oficina com participantes ativos |
| `vagas_abaixo_do_ocupado` | Redução de `vagas_totais` abaixo do ocupado |
| `transicao_invalida` | Mudança de status fora do ciclo de vida |

---

## Controle de concorrência

Escritas em oficina exigem o cabeçalho `If-Match` com o ETag obtido na leitura.
Sem a precondição, dois clientes que leram a mesma versão sobrescreveriam um ao
outro sem que nenhum percebesse.

| Situação | Status |
| --- | --- |
| `If-Match` ausente | 428 Precondition Required |
| `If-Match` divergente | 412 Precondition Failed |
| `If-None-Match` igual à versão atual | 304 Not Modified |

O ETag é derivado de um contador de versão incrementado a cada escrita.

---

## Testando com curl

```bash
curl -i http://127.0.0.1:8000/oficinas
```

Criar uma oficina — a resposta traz `Location` e `ETag`:

```bash
curl -i -X POST http://127.0.0.1:8000/oficinas -H "Content-Type: application/json" -d "{\"titulo\":\"Filas e mensageria\",\"instrutor\":\"Ana Reis\",\"vagas_totais\":2,\"inicio\":\"2026-09-10T14:00:00Z\",\"duracao_min\":120,\"status\":\"aberta\"}"
```

Inscrever um participante:

```bash
curl -i -X POST http://127.0.0.1:8000/oficinas/1/inscricoes -H "Content-Type: application/json" -d "{\"participante_nome\":\"Bruno Lima\",\"participante_email\":\"bruno@exemplo.com\"}"
```

Repetir o comando acima devolve **409**: o mesmo e-mail já tem inscrição ativa.

Alterar sem precondição devolve **428**:

```bash
curl -i -X PATCH http://127.0.0.1:8000/oficinas/1 -H "Content-Type: application/json" -d "{\"titulo\":\"Titulo novo\"}"
```

Alterar com o ETag correto devolve **200**:

```bash
curl -i -X PATCH http://127.0.0.1:8000/oficinas/1 -H "Content-Type: application/json" -H "If-Match: \"1\"" -d "{\"titulo\":\"Titulo novo\"}"
```

---

## Testes

### Suíte automatizada

Roda em processo, sem servidor. Cobre contrato, códigos de status e os
invariantes da seção 4.13.

```bash
python -m pytest -v
```

### Tabela de evidências

Com o servidor no ar, executa os cenários por HTTP real e **gera**
`evidencias/tabela.md`:

```bash
python cliente_testes.py
```

Em seguida, desligue o servidor e execute a variante offline. Ela acrescenta os
cenários de falha de conectividade à mesma tabela, mantendo a numeração
contínua:

```bash
python cliente_testes.py --offline
```

A tabela é gerada a partir da execução, e não redigida à mão: uma tabela escrita
manualmente descreve o que se acredita que a API faz, esta descreve o que ela
fez.

### Experimentos de concorrência

```bash
python cliente_concorrente.py
```

Doze clientes disputam uma única vaga e dois clientes editam a mesma oficina a
partir da mesma leitura. A saída registrada está em `evidencias/concorrencia.txt`.

---

## Estrutura

```
app/
  config.py           configuração por variável de ambiente
  modelos.py          modelos Pydantic, enums e ciclos de vida
  erros.py            exceções de domínio e mapeamento para status HTTP
  repositorio.py      persistência JSON com escrita atômica e exclusão mútua
  observabilidade.py  log estruturado com identificador de correlação
  main.py             rotas, middlewares e tratadores de erro
tests/                suíte pytest: contrato e invariantes
docs/
  modelagem.md        recursos e relações, escrito antes do código
  analise.md          respostas às questões da atividade
evidencias/
  tabela.md           cenário, requisição, status esperado e obtido
  concorrencia.txt    saída dos experimentos concorrentes
  servidor.log        uma linha JSON por requisição
seed.py               dados de demonstração
cliente_testes.py     cliente programático que gera a tabela
cliente_concorrente.py experimentos de concorrência
```

O estado de execução fica em `dados/estado.json`, fora do controle de versão.

---

## Observabilidade

Cada requisição gera uma linha JSON em `evidencias/servidor.log` e no stdout:

```json
{"ts": "...", "request_id": "3f31109f4407", "metodo": "GET", "caminho": "/oficinas", "status": 200, "duracao_ms": 1.24}
```

O `request_id` vem do cabeçalho `X-Request-Id` quando o cliente o envia, e é
gerado quando não vem. Ele volta na resposta e aparece no corpo de erro, ligando
o que o cliente viu à linha correspondente no servidor. Credenciais nunca são
registradas.

---

## Configuração

| Variável | Padrão | Uso |
| --- | --- | --- |
| `OFICINAS_DB` | `dados/estado.json` | Arquivo de estado |
| `OFICINAS_LOG` | `evidencias/servidor.log` | Log estruturado |
| `OFICINAS_TOKEN_ADMIN` | `token-de-laboratorio` | Token do endpoint administrativo |

O token tem valor padrão por ser um laboratório. Em produção um segredo nunca
teria default embutido no código.
