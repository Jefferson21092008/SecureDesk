# SecureDesk

API de gestão de chamados de TI, criada como projeto de estudo e portfólio com foco em backend, arquitetura, testes e segurança.

## V0.2 — Atendimento (em desenvolvimento)

Blocos concluídos até aqui:

- comentários em chamados;
- autoria e data/hora dos comentários;
- histórico de criação e alterações dos chamados;
- registro de quem realizou cada alteração;
- autorização: `USER` só acessa dados dos próprios chamados; `AGENT` e `ADMIN` podem acessar qualquer chamado.

Rotas adicionadas na V0.2:

- `POST /tickets/{ticket_id}/comments`
- `GET /tickets/{ticket_id}/comments`
- `GET /tickets/{ticket_id}/history`

### Histórico de alterações

Ao criar um chamado, o sistema registra uma entrada `CREATED`.

Ao alterar um chamado com `PATCH /tickets/{ticket_id}`, cada campo que realmente mudou gera uma entrada `UPDATED` contendo:

- campo alterado;
- valor anterior;
- novo valor;
- usuário que executou a alteração;
- data/hora.

Enviar novamente o mesmo valor não cria uma entrada falsa de histórico.

A evolução do banco segue migrations incrementais:

```text
0001_initial
    ↓
0002_add_comments
    ↓
0003_add_ticket_history
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

- V0.2: comentários e histórico implementados; próximos blocos: atribuição para agente e fechamento/reabertura.
- V0.3: filtros, paginação, busca, ordenação, anexos, categorias, SLA e departamentos.
- V0.4: auditoria, rate limiting, validação rigorosa, secrets, melhoria do JWT, revogação, políticas de senha, proteção contra IDOR e testes de autorização.
- V0.5: métricas/dashboard.
- V1.0: documentação completa, frontend e deploy.
