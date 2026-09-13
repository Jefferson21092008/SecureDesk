# SecureDesk

API de gestão de chamados de TI, criada como projeto de estudo e portfólio com foco em backend, arquitetura, testes e segurança.

## V0.4 — Segurança (em andamento)

### V0.4.3 — Rate limiting e proteção contra abuso

Esta etapa adiciona limites de requisição e proteção específica contra brute force sem alterar o schema do banco. O objetivo é reduzir abuso automatizado, tentativas repetidas de login e criação excessiva de contas, mantendo respostas previsíveis para o cliente.

Controles desta etapa:

- middleware global aplica uma janela deslizante por endereço do cliente;
- `POST /auth/login` possui um limite próprio por cliente, separado do limite global;
- `POST /auth/register` possui limite próprio por cliente;
- falhas de login são contadas por combinação cliente + identificador de conta;
- após 5 falhas dentro da janela padrão de 5 minutos, novas tentativas para aquela conta recebem `429 Too Many Requests`, inclusive com a senha correta, até a janela expirar;
- um login bem-sucedido limpa o contador de falhas daquela combinação;
- tentativas contra uma conta não bloqueiam outra conta do mesmo cliente;
- respostas `429` incluem `Retry-After`, `X-RateLimit-Limit` e `X-RateLimit-Remaining`;
- respostas permitidas pelo middleware global também expõem `X-RateLimit-Limit` e `X-RateLimit-Remaining`;
- `/health` é isento do limite global para não transformar o próprio healthcheck do container em causa de indisponibilidade;
- `X-Forwarded-For` não é confiado por padrão, evitando que um cliente contorne o limite apenas falsificando esse header.

Configuração padrão:

```text
API_RATE_LIMIT_REQUESTS=120
API_RATE_LIMIT_WINDOW_SECONDS=60
LOGIN_RATE_LIMIT_REQUESTS=20
REGISTER_RATE_LIMIT_REQUESTS=10
AUTH_RATE_LIMIT_WINDOW_SECONDS=60
LOGIN_FAILURE_LIMIT=5
LOGIN_FAILURE_WINDOW_SECONDS=300
```

A implementação desta etapa mantém os contadores em memória, o que é adequado ao container atual com um único processo Uvicorn. Em um deploy com múltiplos workers ou múltiplas réplicas, o armazenamento deve migrar para um backend compartilhado, como Redis, para que todos os processos enxerguem a mesma janela de limite.

Esta etapa não cria migration. O head do Alembic continua sendo `0011_add_revoked_tokens`.

### V0.4.2 — JWT, expiração e revogação

Esta etapa endurece o ciclo de vida dos access tokens JWT. Cada token agora recebe um identificador único (`jti`), horário de emissão (`iat`), expiração (`exp`), tipo (`access`), emissor (`iss`) e audiência (`aud`). A validação exige todos esses claims e continua aceitando somente o algoritmo configurado no servidor.

Controles desta etapa:

- `POST /auth/login` continua emitindo Bearer tokens e agora também informa `expires_in`;
- cada login produz um `jti` diferente, permitindo revogação por sessão;
- `POST /auth/logout` revoga somente o access token usado naquela requisição;
- tokens revogados recebem a mesma resposta `401 Invalid or expired token` de tokens inválidos/expirados;
- a blacklist persiste apenas o `jti` e metadados necessários, nunca o JWT bruto;
- expiração, emissor, audiência, tipo e claims obrigatórios são verificados antes de carregar o usuário;
- revogar uma sessão não invalida automaticamente outras sessões válidas do mesmo usuário.

A migration `0011_add_revoked_tokens` cria a tabela `revoked_tokens`, vinculada ao usuário, para persistir a revogação até o vencimento natural do token.

### V0.4.1 — Autorização e proteção contra IDOR

Esta etapa endurece o controle de acesso a objetos do domínio, especialmente chamados e recursos aninhados. O objetivo é impedir que um `USER` obtenha ou altere dados de outro usuário apenas adivinhando identificadores na URL.

Controles desta etapa:

- o acesso a um chamado é centralizado em `get_accessible_ticket`;
- para `USER`, um chamado inexistente e um chamado pertencente a outra pessoa produzem a mesma resposta `404 Ticket not found`, reduzindo enumeração de IDs;
- comentários, histórico e anexos validam primeiro o acesso ao chamado pai;
- `attachment_id` é sempre consultado junto com o `ticket_id`, evitando troca do recurso filho entre chamados;
- `GET /tickets` aplica o escopo do proprietário antes dos filtros, busca, paginação e ordenação;
- rotas que um `USER` nunca pode executar, como atribuição, fechamento/reabertura e exclusão de chamados, negam pelo papel antes de consultar o objeto;
- campos sensíveis controlados pelo servidor, como `owner_id`, `assigned_agent_id`, `status` na criação e `closed_at`, não podem ser alterados por mass assignment;
- `AGENT` e `ADMIN` continuam com o acesso transversal previsto pelas regras de negócio.

A suíte inclui cenários de IDOR com IDs adivinhados, recursos aninhados, tentativa de mass assignment, enumeração de existência e verificação de que o escopo de busca não pode ser contornado.

Esta etapa não altera o schema do banco e, portanto, não cria uma nova migration. O head continua sendo `0010_add_ticket_departments`.

## V0.3 — Organização (concluída)

### V0.3.5 — Departamentos

Chamados podem ser encaminhados para um departamento de atendimento por meio de `department_id`. Departamentos representam a fila/área responsável pelo chamado, enquanto categorias continuam descrevendo o tipo do incidente ou solicitação.

Rotas de departamentos:

- `GET /departments` — qualquer usuário autenticado;
- `GET /departments/{department_id}` — qualquer usuário autenticado;
- `POST /departments` — somente `ADMIN`;
- `PATCH /departments/{department_id}` — somente `ADMIN`;
- `DELETE /departments/{department_id}` — somente `ADMIN`, desde que não existam chamados usando o departamento.

Regras atuais:

- nomes são únicos sem diferenciar maiúsculas/minúsculas;
- `USER` pode escolher um departamento existente ao abrir um chamado, mas não pode redirecioná-lo depois;
- `AGENT` e `ADMIN` podem alterar ou remover o departamento de um chamado;
- departamentos inexistentes são rejeitados;
- mudanças de departamento entram no histórico do chamado;
- `GET /tickets` aceita `department_id` como filtro.

Exemplo:

```text
GET /tickets?department_id=2&status=OPEN&page=1&page_size=20
```

### V0.3.4 — SLA e prioridade

Cada chamado possui agora um prazo de resolução (`sla_due_at`) calculado a partir da data de criação e da prioridade. Nesta etapa, o SecureDesk usa uma política-base fixa para demonstrar o fluxo de SLA:

- `HIGH`: 4 horas;
- `MEDIUM`: 8 horas;
- `LOW`: 24 horas.

O SLA pode assumir três estados:

- `ON_TRACK`: chamado ainda aberto e dentro do prazo;
- `MET`: chamado fechado dentro do prazo;
- `BREACHED`: prazo estourado, independentemente de o chamado continuar aberto ou ter sido fechado depois do limite.

`TicketRead` expõe `sla_due_at`, `sla_target_hours` e `sla_status`. Ao mudar a prioridade, o prazo é recalculado sempre a partir de `created_at`, evitando que uma alteração de prioridade reinicie o relógio do SLA. A mudança de prioridade continua registrada como `UPDATED`, e a alteração do prazo gera também `SLA_RECALCULATED` no histórico.

`GET /tickets` aceita ainda:

```text
?sla_status=BREACHED
&sort_by=sla_due_at
```

O cálculo desta versão considera o tempo corrido desde a criação; não há pausa por horário comercial, finais de semana ou reabertura. Essas regras podem evoluir depois para políticas configuráveis.

### V0.3.3 — Anexos

Chamados podem receber anexos armazenados fora do PostgreSQL. O banco guarda apenas metadados e uma chave aleatória de armazenamento; os bytes ficam no volume persistente `securedesk_attachments` quando a API roda via Docker.

Rotas:

- `POST /tickets/{ticket_id}/attachments` — envia um arquivo via `multipart/form-data`;
- `GET /tickets/{ticket_id}/attachments` — lista os metadados dos anexos;
- `GET /tickets/{ticket_id}/attachments/{attachment_id}` — baixa o arquivo;
- `DELETE /tickets/{ticket_id}/attachments/{attachment_id}` — remove o anexo.

Regras atuais:

- a autorização segue o acesso ao chamado: `USER` somente nos próprios chamados; `AGENT` e `ADMIN` podem acessar os demais;
- somente o usuário que enviou o arquivo ou um `ADMIN` pode removê-lo;
- os nomes originais não são usados como caminho de armazenamento, reduzindo risco de path traversal;
- tipos aceitos nesta etapa: PDF, PNG, JPEG, TXT e LOG;
- o limite padrão é 5 MiB e pode ser configurado por `ATTACHMENT_MAX_BYTES`;
- uploads vazios, tipos não permitidos e combinações inválidas de extensão/MIME são rejeitados;
- upload e remoção geram eventos `ATTACHMENT_ADDED` e `ATTACHMENT_DELETED` no histórico do chamado.

A validação de conteúdo por assinatura/magic bytes será endurecida na V0.4 de segurança.

### V0.3.2 — Categorias

Os chamados podem ser classificados com uma categoria opcional por meio de `category_id`.

Rotas de categorias:

- `GET /categories` — qualquer usuário autenticado pode listar as categorias;
- `GET /categories/{category_id}` — qualquer usuário autenticado pode consultar uma categoria;
- `POST /categories` — somente `ADMIN`;
- `PATCH /categories/{category_id}` — somente `ADMIN`;
- `DELETE /categories/{category_id}` — somente `ADMIN`, e apenas quando a categoria não estiver em uso.

Regras atuais:

- nomes de categoria não podem se repetir, inclusive com diferença apenas de maiúsculas/minúsculas;
- `USER` pode selecionar uma categoria existente ao criar ou editar os próprios chamados;
- `category_id: null` remove a categoria de um chamado;
- categorias inexistentes são rejeitadas antes de gravar o chamado;
- mudanças de categoria entram no histórico do chamado;
- `GET /tickets` aceita `category_id` como filtro.

Exemplo:

```text
GET /tickets?category_id=2&page=1&page_size=20
```

### V0.3.1 — Consulta de chamados

O endpoint `GET /tickets` suporta filtros, busca, paginação e ordenação.

Exemplo:

```text
GET /tickets?status=OPEN&priority=HIGH&search=vpn&page=1&page_size=20&sort_by=created_at&sort_order=desc
```

Parâmetros atuais:

- `status`: `OPEN`, `IN_PROGRESS` ou `CLOSED`;
- `priority`: `LOW`, `MEDIUM` ou `HIGH`;
- `category_id`: identificador de uma categoria;
- `department_id`: identificador do departamento responsável;
- `sla_status`: `ON_TRACK`, `MET` ou `BREACHED`;
- `search`: busca case-insensitive em título e descrição;
- `page`: página, começando em 1;
- `page_size`: quantidade por página, de 1 a 100;
- `sort_by`: `created_at`, `id`, `title` ou `sla_due_at`;
- `sort_order`: `asc` ou `desc`.

Resposta paginada:

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0,
  "pages": 0
}
```

A autorização continua sendo aplicada antes dos filtros: `USER` consulta somente os próprios chamados, enquanto `AGENT` e `ADMIN` podem consultar o conjunto completo permitido pelo papel.

Os chamados agora possuem `created_at`, usado também como ordenação padrão.

## V0.2 — Atendimento (concluída)

Funcionalidades concluídas:

- comentários em chamados;
- autoria e data/hora dos comentários;
- histórico de criação e alterações dos chamados;
- registro de quem realizou cada alteração;
- atribuição e desatribuição de chamados para agentes;
- fechamento e reabertura controlados de chamados;
- autorização: `USER` só acessa dados dos próprios chamados; `AGENT` e `ADMIN` podem acessar qualquer chamado.

Rotas da V0.2:

- `POST /tickets/{ticket_id}/comments`
- `GET /tickets/{ticket_id}/comments`
- `GET /tickets/{ticket_id}/history`
- `PATCH /tickets/{ticket_id}/assignment`
- `POST /tickets/{ticket_id}/close`
- `POST /tickets/{ticket_id}/reopen`

### Ciclo de vida do chamado

O fechamento e a reabertura usam endpoints dedicados para manter o status e `closed_at` consistentes.

Regras atuais:

- `USER` não pode fechar ou reabrir chamados;
- `AGENT` só pode fechar/reabrir chamados atribuídos a ele;
- `ADMIN` pode fechar/reabrir qualquer chamado;
- fechar um chamado já fechado retorna conflito;
- reabrir um chamado que não está fechado retorna conflito;
- `PATCH /tickets/{ticket_id}` não pode ser usado para contornar essas regras;
- fechamento e reabertura são registrados no histórico com ator e transição de status.

### Atribuição para agentes

A atribuição usa um campo opcional `assigned_agent_id` no chamado.

Regras atuais:

- `USER` não pode atribuir chamados;
- `AGENT` pode assumir um chamado para si e desatribuir um chamado que esteja atribuído a ele;
- `AGENT` não pode atribuir chamados a outro agente nem tomar um chamado já atribuído a outro agente;
- `ADMIN` pode atribuir, reatribuir e desatribuir chamados;
- o destino da atribuição precisa ter papel `AGENT`;
- atribuições, reatribuições e desatribuições entram no histórico do chamado.

### Histórico de alterações

Ao criar um chamado, o sistema registra uma entrada `CREATED`.

Ao alterar um chamado com `PATCH /tickets/{ticket_id}`, cada campo que realmente mudou gera uma entrada `UPDATED` contendo campo alterado, valor anterior, novo valor, usuário que executou a alteração e data/hora.

Enviar novamente o mesmo valor não cria uma entrada falsa de histórico.

A evolução atual do banco é:

```text
0001_initial
    ↓
0002_add_comments
    ↓
0003_add_ticket_history
    ↓
0004_add_ticket_assignment
    ↓
0005_ticket_lifecycle
    ↓
0006_add_ticket_created_at
    ↓
0007_add_ticket_categories
    ↓
0008_add_ticket_attachments
    ↓
0009_add_ticket_sla
    ↓
0010_add_ticket_departments
    ↓
0011_add_revoked_tokens
```

As migrations antigas não são alteradas depois de aplicadas.

## V0.1 — Fundação

- FastAPI + PostgreSQL 17
- SQLAlchemy 2 + Alembic
- Autenticação JWT
- Hash de senha com Argon2
- Papéis `USER`, `AGENT` e `ADMIN`
- CRUD inicial de chamados
- Controle de autorização por papel
- Testes automatizados
- Docker Compose para API + PostgreSQL
- GitHub Actions
- Configuração por variáveis de ambiente

## Executar com Docker

No Windows:

```powershell
copy .env.example .env
docker compose up --build
```

No Linux/macOS:

```bash
cp .env.example .env
docker compose up --build
```

O container da API espera o PostgreSQL ficar saudável, executa automaticamente:

```bash
alembic upgrade head
```

e depois inicia o Uvicorn.

A API ficará em `http://localhost:8000`.

Documentação:

- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

### Login pelo Swagger

1. Crie um usuário em `POST /auth/register`.
2. Clique em **Authorize**.
3. No campo `username`, informe o e-mail cadastrado.
4. Informe a senha e autorize.

## Comandos úteis

Ver os containers:

```bash
docker compose ps
```

Conferir a migration atual:

```bash
docker compose exec api alembic current
```

Executar os testes:

```bash
docker compose exec api pytest -q
```

Executar o lint:

```bash
docker compose exec api ruff check .
```

Parar os containers sem apagar o banco:

```bash
docker compose down
```

Apagar também o volume do banco:

```bash
docker compose down -v
```

> `down -v` apaga os dados locais do PostgreSQL e também o volume de anexos deste projeto. Use somente quando quiser realmente reiniciar o ambiente de desenvolvimento.

## Evolução planejada

- V0.2: atendimento concluído com comentários, histórico, atribuição e ciclo de vida.
- V0.3: consulta, categorias, anexos, SLA e departamentos concluídos.
- V0.4: segurança em andamento; V0.4.1 conclui autorização/IDOR, V0.4.2 conclui JWT/expiração/revogação e V0.4.3 conclui rate limiting/anti-abuso; seguem auditoria, validação rigorosa, secrets e política de senha.
- V0.5: métricas/dashboard.
- V1.0: documentação completa, frontend e deploy.
