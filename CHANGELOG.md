# Changelog

Todas as mudanças relevantes do SecureDesk são registradas neste arquivo.

## [Unreleased] — Confiabilidade dos uploads (etapa 04)
- Gravação em arquivo temporário no mesmo volume, seguida de publicação atômica no nome definitivo.
- Limpeza de arquivos parciais quando o upload falha, com resposta 503 em falhas de armazenamento.
- Alertas de log quando a remoção de arquivos após commit não é concluída.
- Limites do proxy Nginx compatíveis com o máximo configurável da API, incluindo overhead multipart.
- Testes de falha de gravação, publicação atômica e limpeza; guia de diagnóstico em `docs/ATTACHMENT_RELIABILITY.md`.
- Sem novas dependências nem migrations; persistência durável de anexos permanece na etapa 05.

## [Unreleased] — Observabilidade e diagnóstico (etapa 03)
- Middleware com `X-Request-ID` UUID v4 gerado pelo servidor, inclusive para 429 e falhas 500.
- Logs HTTP JSON com método, template seguro de rota, status, duração e ID para correlação.
- Resposta genérica segura para exceções inesperadas, sem expor segredos ao cliente.
- Testes de requisições concorrentes, privacidade de logs, erros e rate limiting.
- `docs/OBSERVABILITY.md` com procedimentos e limitações do diagnóstico.
- Sem nova dependência, migration ou alteração do frontend.

## [Unreleased] — Experiência e operação de chamados (etapa 02)
- Interface de detalhes de chamados: status, prioridade, descrição, solicitante, atribuição, SLA e datas.
- Comentários e histórico com acesso pelos endpoints existentes e conteúdo escapado no HTML.
- Upload e download autenticado de anexos via API, com suporte a FormData e Blob.
- Atribuição de agentes e fechamento/reabertura com ações condicionais à permissão e validação final da API.
- Paginação real de chamados, navegação e filtros com proteção contra respostas assíncronas atrasadas.
- Testes de contrato de frontend, instruções de teste manual e responsividade aprimorada.
- Nenhuma nova migration ou dependência externa para a interface.

## [Unreleased] — Gestão de usuários e convites (etapa 01)
- Cadastro público desabilitado em produção, preservado para testes e desenvolvimento.
- Convites administrativos de 48 horas com uso único, token armazenado somente como hash e reemissão que revoga o anterior.
- Ativação de contas `USER` e `AGENT` e auditoria de emissão/aceitação.
- Interface de administrador para emissão de convites e listagem de contas.
- Bootstrap administrativo protegido contra promoção de conta comum preexistente.
- Nova migration `0013_add_user_invitations` e testes focados.

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
