# SecureDesk — Security

Este documento resume o modelo de segurança do SecureDesk. Ele complementa o relatório técnico [`../SECURITY_REVIEW.md`](../SECURITY_REVIEW.md), que registra a revisão de vulnerabilidades realizada no fechamento da V0.4.

## Objetivos de segurança

O backend foi projetado para reduzir riscos comuns em APIs de negócio:

- account takeover por credenciais fracas ou brute force;
- acesso horizontal indevido entre usuários;
- escalada de privilégio;
- manipulação de JWT;
- mass assignment;
- enumeração de objetos;
- abuso automatizado;
- upload de conteúdo inconsistente;
- path traversal em anexos;
- vazamento de credenciais/tokens em logs;
- configuração insegura em produção.

## Autenticação

Senhas são armazenadas com Argon2. O login emite access tokens JWT com tempo de vida configurável e claims obrigatórios:

```text
sub
jti
iat
exp
iss
aud
type=access
```

A validação aceita apenas o algoritmo configurado (`HS256`) e verifica issuer, audience, tipo, expiração e formato do subject.

Tokens revogados têm o `jti` persistido em `revoked_tokens`; o JWT bruto não é armazenado.

## Autorização e IDOR

O SecureDesk combina RBAC com autorização por recurso.

- `USER` acessa os próprios tickets;
- `AGENT` e `ADMIN` possuem capacidades adicionais definidas pelas rotas;
- recursos filhos — comentários, histórico e anexos — validam primeiro o ticket pai;
- attachment IDs são escopados ao ticket informado;
- mass assignment de campos controlados pelo servidor é rejeitado pelos schemas;
- em cenários sensíveis, ticket inexistente e ticket de outro usuário produzem a mesma resposta `404` para reduzir enumeração.

## Política de senha e validação

O cadastro aplica política de senha forte e limites de tamanho. Payloads rejeitam campos desconhecidos e textos passam por regras de tamanho/normalização.

O login também limita o tamanho de credenciais antes do Argon2, evitando que entradas arbitrariamente grandes sejam usadas para amplificar custo computacional.

## Redução de enumeração de conta

Falhas de login usam resposta genérica. Para usuários inexistentes, o backend executa verificação contra um hash dummy, reduzindo a diferença de trabalho computacional entre conta existente e inexistente.

Isso reduz side channels de timing, mas não é uma garantia matemática contra análise estatística de rede.

## Rate limiting e anti-abuso

Existem quatro controles relevantes:

1. limite global por cliente;
2. limite específico para login;
3. limite específico para registro;
4. limite de falhas por combinação cliente + identificador.

Respostas `429` incluem `Retry-After` e metadados de rate limit.

`X-Forwarded-For` não é confiado por padrão, evitando bypass simples por spoofing do header.

### Limitação atual

O estado do limiter é mantido em memória do processo. Isso é adequado ao ambiente single-process atual. Em produção com múltiplas réplicas/workers, deve ser usado um backend compartilhado, como Redis.

## Uploads e filesystem

Uploads possuem:

- limite de tamanho;
- allowlist de tipos suportados;
- validação de extensão e MIME;
- checagem básica de assinatura para PDF, PNG e JPEG;
- validação UTF-8/NUL para texto;
- `storage_key` gerada pelo servidor;
- validação de caminho no download/remoção.

Essa validação não substitui antivírus ou sandbox de arquivos.

## Auditoria

O sistema registra eventos como:

```text
ACCOUNT_CREATED
LOGIN_SUCCESS
LOGIN_FAILED
LOGOUT
RATE_LIMIT_EXCEEDED
UNAUTHORIZED_ACCESS
FORBIDDEN_ACCESS
```

Os registros podem conter ator, rota, status, IP, User-Agent, timestamp e detalhes mínimos. Senhas e Bearer tokens brutos não devem ser persistidos.

A consulta é restrita a `ADMIN` em:

```text
GET /security/audit
```

## Headers HTTP

As respostas incluem proteção básica:

```text
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
```

Rotas de autenticação/segurança recebem `Cache-Control: no-store`.

HSTS não é forçado pela aplicação porque o ambiente Docker local usa HTTP. Em produção, TLS/HSTS devem ser tratados na camada de proxy/plataforma.

## Configuração de produção

Quando `APP_ENV=production`, a configuração recusa condições conhecidamente inseguras, incluindo:

- `DEBUG=true`;
- secret JWT padrão de desenvolvimento;
- credenciais padrão do PostgreSQL presentes na URL.

Secrets reais devem ser injetados por mecanismo seguro da plataforma de deploy.

## Testes de segurança

A suíte automatizada inclui regressões para:

- IDOR;
- recursos aninhados;
- mass assignment;
- escalada de privilégio;
- token expirado/revogado;
- JWT com claims inválidos;
- `alg=none` e algoritmo alternativo;
- brute force/rate limiting;
- spoofing de `X-Forwarded-For`;
- SQL-injection-shaped input;
- path traversal;
- conteúdo de upload incompatível;
- proteção contra armazenamento de segredo em audit logs.

## Checklist antes de deploy público

- [ ] definir `APP_ENV=production`;
- [ ] gerar `JWT_SECRET` de alta entropia;
- [ ] remover credenciais padrão do PostgreSQL;
- [ ] usar TLS no domínio público;
- [ ] configurar CORS somente para o frontend esperado;
- [ ] usar banco persistente com backup;
- [ ] usar object storage privado para anexos;
- [ ] adicionar malware scanning caso uploads públicos sejam aceitos;
- [ ] centralizar logs/auditoria;
- [ ] substituir rate limiter em memória por backend compartilhado se houver múltiplas instâncias;
- [ ] habilitar dependency/SAST scanning no CI;
- [ ] definir política de retenção de audit logs e tokens revogados;
- [ ] revisar exposição de Swagger/ReDoc conforme o ambiente.

## Riscos residuais conhecidos

Os principais limites atuais são intencionais e documentados:

- rate limit process-local;
- filesystem local para anexos;
- ausência de antivírus;
- cadastro retorna `409` para e-mail duplicado;
- ausência de MFA e refresh token;
- audit log não é tamper-evident;
- secrets dependem do ambiente;
- TLS é responsabilidade do proxy/plataforma;
- dependency/SAST scanning ainda não é gate obrigatório de CI.

Esses itens não são tratados como “invisíveis”; eles orientam as decisões da etapa de deploy da V1.0.
