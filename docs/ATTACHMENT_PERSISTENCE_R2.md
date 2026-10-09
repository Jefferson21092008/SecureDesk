# SecureDesk — Etapa 05: anexos persistentes com Cloudflare R2

## Arquitetura e segurança

- `local` continua sendo o backend **padrão em desenvolvimento**. Em produção, configure
  `ATTACHMENT_STORAGE_BACKEND=r2` **somente depois de preparar um bucket R2 privado**.
- `r2` utiliza a API S3 com **boto3**; nenhum objeto recebe ACL pública, URL pública ou URL pré-assinada.
- A API FastAPI valida autenticação, permissão de acesso ao chamado e proprietário/admin para remoção,
  **antes** de consultar o armazenamento. Não compartilhe URL de objeto com o frontend.
- PostgreSQL/Neon armazena a coluna `attachments.storage_backend` (`local` ou `r2`). A migration
  `0014_attachment_storage_backend` marca registros antigos como `local`.
- A aplicação acessa o R2 com credenciais de **bucket específico**, permissões mínimas
  de leitura/gravação de objetos. Evite tokens globais e nunca cole segredos em chats ou commits.

## Configuração (não executar ainda sem revisão da conta Cloudflare)

1. Crie um bucket privado no Cloudflare R2, na conta que será usada no deploy.
2. Gere um token **R2 S3 API** com escopo só nesse bucket e permissões de leitura/escrita de objetos.
   Copie `Access Key ID` e `Secret Access Key` para seu gerenciador de segredos.
3. Configure no Render **Environment**, de forma privada:

   - `ATTACHMENT_STORAGE_BACKEND=r2`
   - `R2_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`
   - `R2_BUCKET_NAME=<NOME_BUCKET_PRIVADO>`
   - `R2_ACCESS_KEY_ID=<ACCESS_KEY_ID>`
   - `R2_SECRET_ACCESS_KEY=<SECRET_ACCESS_KEY>`

4. No deploy, aplique Alembic até o HEAD **antes de servir tráfego com a nova versão**:
   `alembic upgrade head` (a infraestrutura atual já executa migrations na inicialização).
5. Faça upload/download/exclusão de arquivo TXT sem informações reais, pelo login da aplicação.
6. Reinicie ou faça novo deploy e confirme download **do mesmo anexo** (mesma ID e bytes).
7. Teste que uma conta sem permissão não consegue baixar o anexo e que o bucket não tem acesso público.

## Compatibilidade, migração e dados existentes

- **Não alterar** `storage_backend` de registros antigos manualmente: eles apontam para arquivos
  locais. A coluna salva o backend **usado no momento do upload**, não a configuração atual.
- Ativar `r2` só torna **novos uploads** persistentes. Arquivos locais antigos NÃO são movidos
  automaticamente. Antes de mudar/redeployar, faça backup dos arquivos locais que ainda existem e
  planeje cópia verificada para R2 e atualização transacional dos registros correspondentes.
- A migration recusa downgrade quando há registros marcados `r2`, para evitar perder a informação do provedor.
- Se o arquivo antigo já sumiu do `/tmp` do Render, a coluna do PostgreSQL não o recupera.
  Não afirme que o arquivo foi migrado; sinalize o anexo faltante.
- A aplicação mantém o backend local para ler anexos antigos **enquanto eles existirem**.
  Para garantir persistência de anexos antigos, a transferência verificada é uma tarefa operacional
  separada, a realizar com janela de manutenção e backup do PostgreSQL.

## Falhas e limites conhecidos

- Upload para R2 retorna HTTP `503` em falhas normais de rede ou provedor.
  Uploads vazios, grandes demais e tipos inválidos mantêm `400`, `413` e `415`.
- Objeto inexistente retorna `404` e falha no `GetObject` retorna `503`.
  Uma falha **durante** o streaming pode interromper a conexão após os cabeçalhos HTTP;
  monitore as exceções de streaming no servidor.
- Em falha do commit do banco, a API tenta limpar o objeto já criado. Em timeout de upload,
  tenta remover a possível cópia. Uma falha de limpeza pode deixar objeto órfão.
- Exclusões físicas ocorrem após commit do banco, também podendo deixar objeto órfão
  quando o R2 estiver indisponível. Procure `attachment_r2_cleanup_failed` nos logs.
  Evite remover objetos diretamente no console Cloudflare sem conferir referências no banco.
- Persistência em bucket não substitui backup/rotina de reconciliação. Um teste real de
  reinício/deploy é obrigatório para aprovar esta etapa em produção.

## Testes locais e validação

```cmd
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_attachment_r2.py tests/test_attachment_r2_config.py tests/test_attachments.py tests/test_attachment_reliability.py
python -m ruff check .
python -m compileall -q app tests alembic scripts
python -m coverage run --source=app -m pytest -q
python -m coverage report -m
python -m pip check
python -m pip_audit
```

Os testes R2 usam provedor simulado (sem dados reais nem internet). Depois, teste
com bucket real e usuário autorizado; **não publique credenciais, tokens ou arquivos privados**.

## Infraestrutura

Em `render.yaml`, `ATTACHMENT_STORAGE_BACKEND` é `sync: false` para que um próximo
sincronismo de Blueprint não sobrescreva o valor do dashboard. Sem valor configurado,
o aplicativo utiliza o padrão `local`, que **não é persistente no Render Free**.
A produção só fica persistente para **novos** anexos quando o operador configura
`ATTACHMENT_STORAGE_BACKEND=r2` no serviço e valida um novo deploy.
