# Changelog

Todas as mudanças relevantes do SecureDesk são registradas neste arquivo.

## [1.0.0] — 2026-09-20

Primeira release completa de portfólio do SecureDesk.

### Produto

- frontend responsivo integrado à API real;
- autenticação JWT, sessão, logout e controle por papel;
- gestão de chamados com assignment, lifecycle, comentários, histórico e anexos;
- categorias, departamentos e SLA;
- métricas de overview, SLA e breakdown com filtros por período;
- auditoria de segurança para administradores.

### Segurança

- Argon2 para senhas;
- JWT com `jti`, expiração, issuer, audience e revogação por sessão;
- RBAC, proteção contra IDOR e mass assignment;
- rate limiting e proteção contra abuso de autenticação;
- validação de uploads e defesa contra path traversal;
- headers de segurança e configuração endurecida para produção;
- bootstrap inicial do ADMIN sem exposição de credenciais inválidas em traceback.

### Qualidade e operação

- migrations Alembic até `0012_add_security_audit_logs`;
- suíte automatizada com mais de 200 testes;
- CI com compile check, Ruff, migrations e Pytest;
- Swagger, ReDoc e OpenAPI organizados;
- Docker Compose para desenvolvimento;
- deploy de referência com Render + Neon Postgres;
- smoke test para validar a publicação sem credenciais.

## [0.5.0] — 2026-09-20

- métricas operacionais, SLA e breakdown;
- filtros de período;
- agregações executadas no banco.

## [0.4.0] — 2026-09-13

- hardening de autorização e IDOR;
- JWT revogável;
- rate limiting e anti-abuso;
- audit log de segurança;
- validação de entrada, política de senha e secrets;
- revisão de vulnerabilidades.

## [0.3.0]

- querying, categorias, anexos, SLA e departamentos.

## [0.2.0]

- comentários, histórico, assignment e lifecycle de chamados.

## [0.1.0]

- fundação FastAPI/PostgreSQL, autenticação, RBAC, Docker, testes e CI.
