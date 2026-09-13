# SecureDesk

API de gestão de chamados de TI, criada como projeto de estudo e portfólio com foco em backend, arquitetura, testes e segurança.

## V0.3 — Organização (em desenvolvimento)

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
- `search`: busca case-insensitive em título e descrição;
- `page`: página, começando em 1;
- `page_size`: quantidade por página, de 1 a 100;
- `sort_by`: `created_at`, `id` ou `title`;
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

> `down -v` apaga os dados locais do PostgreSQL deste projeto. Use somente quando quiser realmente reiniciar o banco de desenvolvimento.

## Evolução planejada

- V0.2: atendimento concluído com comentários, histórico, atribuição e ciclo de vida.
- V0.3: consulta e categorias concluídas; próximos blocos: anexos, SLA e departamentos.
- V0.4: auditoria, rate limiting, validação rigorosa, secrets, melhoria do JWT, revogação, políticas de senha, proteção contra IDOR e testes de autorização.
- V0.5: métricas/dashboard.
- V1.0: documentação completa, frontend e deploy.
