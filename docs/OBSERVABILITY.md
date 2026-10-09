# SecureDesk — Observabilidade e Diagnóstico (Etapa 03)

## 1. O que foi implementado

A API gera um UUID v4 independente **no servidor** para cada requisição HTTP e
inclui `X-Request-ID` na resposta. Cabeçalhos `X-Request-ID` fornecidos pelo
cliente **não são aceitos como fonte da identidade**, impedindo falsificação ou
poluição dos logs por valores arbitrários.

O middleware escreve um registro JSON por requisição na saída de erro padrão
(stderr) do processo (capturável por Uvicorn, Docker e Render). Exemplo com
valores fictícios:

```json
{"event":"http_request","request_id":"c26c35bf-90c4-4df4-908e-ebbb29470651","method":"GET","route":"/health","status_code":200,"duration_ms":1.5}
```

Campos: `event`, `request_id`, `method`, `route` (template da rota),
`status_code`, `duration_ms`. Em falhas não tratadas: `error_type` com **apenas o
nome da classe**. Tempo medido até os cabeçalhos da resposta estarem prontos:
**não é o tempo completo de transferência de um download/stream**.

`request.state.request_id` está disponível em handlers que recebem `Request`.
`app.core.observability.current_request_id()` permite obter o identificador
em código executado no contexto assíncrono da mesma requisição. Esse contexto
é redefinido ao final do middleware.

## 2. Privacidade e segurança

O novo log **não registra** IP, `Authorization`, cookies, JWTs, senhas, email,
request body, nomes de arquivos, URL completa, query string, valores de path
parameters, `DATABASE_URL` nem `str(exc)`/tracebacks. Se não for possível
identificar uma rota registrada, o campo `route` será `<unmatched>`; para
`/tickets/123`, o campo é `/tickets/{ticket_id}` quando a rota é reconhecida.

Erros HTTP de negócio mantêm seus códigos e conteúdos existentes. Para erros
inesperados (500), o cliente recebe `{"detail":"Internal server error"}` e o
mesmo `X-Request-ID` do registro de falha. O log registra a classe da exceção,
sem mensagem, variável ou stack trace. Logs estruturados não são equivalentes
à tabela `security_audit_logs`, que continua registrando eventos de segurança.

O cabeçalho é anexado inclusive nas respostas `401`, `403`, `404`, `429` e
`500`; o rate limiter, os headers de segurança e as políticas RBAC existentes
permanecem ativos.

## 3. Diagnóstico local no Windows

Ative `.venv` e rode o servidor normalmente com o ambiente de desenvolvimento
já configurado:

```cmd
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Em **outro CMD**, sem usar credenciais reais, consulte:

```cmd
curl.exe -i http://127.0.0.1:8000/health
curl.exe -i http://127.0.0.1:8000/rota-inexistente
```

Procure o header `x-request-id` e localize **o mesmo UUID** na saída do
servidor. Os registros têm o evento `http_request` e código 200 ou 404.

Para um incidente: registre horário (e fuso), Request ID, status, rota,
latência aproximada, consumo de recursos e se `/health` continuou respondendo.
Compare chamadas de upload com o estado do Uvicorn, mas **não cole logs com
segredos nem arquivos enviados** em issues ou chats.

Em Docker, use `docker compose logs api --tail 100` quando esse serviço estiver
ativo. Em Render, consulte os logs de aplicação. O nome e disponibilidade dos
serviços dependem do ambiente real.

## 4. Checkpoints e testes

```cmd
python -m pytest -q tests/test_observability.py
python -m ruff check .
python -m compileall -q app tests alembic scripts
python -m pytest -q
python -m coverage run --source=app -m pytest -q
python -m coverage report -m
python -m pip check
python -m pip_audit
```

Valide também: autenticação ADMIN/AGENT/USER, um erro 401, um 429 controlado e
pelo menos um upload autorizado de arquivo de teste. Não use dados reais ou
reinicialize banco de produção para reproduzir falhas.

## 5. Limitações / próxima etapa

- Logs não diagnosticam sozinhos a causa de bloqueio de I/O ou upload.
- Não foi adicionado backend externo de métricas/tracing ou alerta proativo.
- A causa do timeout durante upload na Etapa 02 **continua não comprovada**.
- Uma falha durante streaming após os cabeçalhos serem enviados não poderá
  alterar o código HTTP nem o `X-Request-ID` já enviado.
- O log contém somente metadados, não stack trace: diagnosticar falhas
  complexas requer reprodução controlada e investigação adicional.
- Persistência/rotação dos logs em produção depende do ambiente de hospedagem.
- A Etapa 04 irá avaliar e testar a confiabilidade de anexos e requisições.
