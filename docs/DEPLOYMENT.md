# Deploy do SecureDesk

O SecureDesk 1.0 usa uma configuração de referência para publicação no **Render** com infraestrutura como código (`render.yaml`). O objetivo é manter o mesmo desenho usado localmente: frontend Nginx, API FastAPI e PostgreSQL, sem liberar CORS desnecessariamente.

## Arquitetura publicada

```mermaid
flowchart LR
    Browser[Navegador] --> Web[SecureDesk Web Service]
    Web --> Nginx[Nginx : PORT]
    Nginx -->|/api/*| API[FastAPI :8000]
    API --> DB[(Neon Postgres)]
    API --> Temp[(attachments temporários)]
```

O deploy de referência usa **um único Web Service** para o frontend e a API: o Nginx recebe o tráfego público e encaminha `/api/*` para o Uvicorn dentro do mesmo container. Isso mantém o mesmo origin do ambiente local, evita CORS e funciona sem depender de recebimento pela rede privada entre dois serviços gratuitos. O PostgreSQL continua como serviço gerenciado separado no Neon, desacoplado do ciclo de vida do Web Service do Render.

## 1. Pré-requisitos

- repositório atualizado no GitHub;
- conta no Render conectada ao GitHub;
- projeto PostgreSQL criado no Neon;
- uma senha **nova e exclusiva** para o administrador inicial.

Não use `SecureDesk!2026` no ambiente público. Essa senha existe somente no seed local.

## 2. Criar o Blueprint

No Render:

1. escolha **New > Blueprint**;
2. conecte o repositório `SecureDesk`;
3. use o `render.yaml` da raiz;
4. selecione a branch `main`;
5. quando o Render solicitar `DATABASE_URL`, cole a connection string do projeto Neon;
6. informe `INITIAL_ADMIN_EMAIL` e `INITIAL_ADMIN_PASSWORD`;
7. revise o recurso e execute **Deploy Blueprint**.

O Blueprint cria apenas:

- `securedesk` — Web Service com Nginx + FastAPI no mesmo container.

O banco é o projeto Neon criado separadamente. `DATABASE_URL` é marcada como `sync: false`, portanto o segredo é informado no painel do Render e não fica versionado. `JWT_SECRET` continua sendo gerado pela plataforma.

## 3. Inicialização

O container de produção executa, nessa ordem:

```text
renderiza a configuração do Nginx com $PORT
alembic upgrade head
python scripts/bootstrap_admin.py
uvicorn em 127.0.0.1:8000
Nginx em $PORT
```

O bootstrap é idempotente: cria o administrador somente quando necessário ou promove a conta informada para `ADMIN`. Ele nunca usa credenciais de demonstração.

Depois do primeiro deploy bem-sucedido, remova `INITIAL_ADMIN_PASSWORD` e `INITIAL_ADMIN_EMAIL` das variáveis do serviço se você não quiser manter essas credenciais disponíveis no ambiente. A conta já permanece persistida no banco.

## 4. Validar o deploy

Confirme:

- frontend abre sem erro;
- login do administrador funciona;
- `GET /api/health` retorna `{"status":"ok"}` no domínio público;
- criação de chamado persiste após refresh;
- dashboard carrega métricas;
- página de auditoria aparece somente para `ADMIN`;
- logout invalida a sessão atual.

Swagger e ReDoc ficam disponíveis no mesmo domínio público, através do proxy `/api`:

```text
/api/docs
/api/redoc
/api/openapi.json
```

## 5. Banco e migrations

`DATABASE_URL` vem do Neon. O SecureDesk normaliza URLs `postgresql://` para o driver SQLAlchemy `postgresql+psycopg://` usado pelo projeto. Use uma connection string com TLS habilitado (`sslmode=require`); para este deploy de uma única instância, a URL direta é suficiente. Se optar pela URL pooled do Neon, mantenha a mesma variável e valide as migrations no primeiro deploy.

A migration atual continua:

```text
0012_add_security_audit_logs
```

## 6. IP real e rate limiting

`TRUST_PROXY_HEADERS=true` é ativado pelo Blueprint porque a aplicação fica atrás da infraestrutura do Render. Fora de um proxy confiável, mantenha essa opção desabilitada para evitar spoofing de IP por headers enviados pelo cliente.

## 7. Anexos

A configuração gratuita de referência usa:

```text
/tmp/securedesk-attachments
```

Esse armazenamento é **efêmero**. Arquivos enviados podem desaparecer quando a instância é recriada ou redeployada. Para um ambiente durável, use um disco persistente compatível com o provedor ou mova anexos para object storage (S3/R2/compatível).

## 8. Limitações da configuração gratuita

A configuração `render.yaml` prioriza demonstração de portfólio e baixo custo. O Web Service do Render e o projeto Neon podem suspender recursos quando ficam ociosos e possuem limites próprios no plano gratuito. Antes de usar o sistema como serviço real, revise os planos, persistência de anexos, backups, disponibilidade e escalabilidade.

O rate limiter atual continua em memória e foi projetado para uma única instância da API. Para múltiplas réplicas, migre o estado do limiter para Redis/Key Value antes de escalar horizontalmente.

## 9. Checklist antes de divulgar

- trocar/remover qualquer credencial temporária;
- não executar `scripts/seed_demo.py` em produção;
- confirmar `APP_ENV=production` e `DEBUG=false`;
- confirmar que `JWT_SECRET` e `DATABASE_URL` não estão no repositório;
- testar login/logout e papéis;
- validar health checks;
- verificar logs de deploy;
- testar a URL pública em janela anônima;
- adicionar a URL pública ao README somente depois de o deploy estar estável.
## 10. Ambiente público de referência

A release 1.0 foi validada no seguinte endereço público:

- aplicação: `https://securedesk-e2pb.onrender.com`;
- Swagger: `https://securedesk-e2pb.onrender.com/api/docs`;
- ReDoc: `https://securedesk-e2pb.onrender.com/api/redoc`;
- health check: `https://securedesk-e2pb.onrender.com/api/health`.

Após cada deploy, execute também o smoke test incluído no repositório:

```bash
python scripts/smoke_test.py https://securedesk-e2pb.onrender.com
```

O script valida a página inicial, o health check e a versão publicada no OpenAPI sem precisar de credenciais.

> Segredos de ambiente nunca devem ser copiados para issues, logs, commits ou screenshots. O bootstrap do administrador converte erros de validação em uma mensagem genérica para evitar que o valor rejeitado apareça no traceback de produção.

