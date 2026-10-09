# SecureDesk — Etapa 05: Supabase Storage S3 (plano Free)

## Decisão de infraestrutura

A Etapa 05 permite `ATTACHMENT_STORAGE_BACKEND=local`, `r2` ou `s3`. Para este
projeto, usar **Supabase Storage S3** (`s3`) com bucket privado
`securedesk-attachments`, região `sa-east-1` (confira os valores no dashboard).
O backend `r2` foi mantido apenas por compatibilidade com o PATCH já aplicado.

- PostgreSQL/Neon continua a guardar os metadados e permissões.
- Supabase guarda **apenas o conteúdo dos novos anexos** após ativar `s3`.
- Os anexos existentes ficam com `storage_backend=local`; não são migrados
  automaticamente. Arquivos antigos ausentes do Render Free não se recuperam
  do banco de dados.
- O bucket fica **privado**, sem URLs públicas ou assinadas no frontend.
  O backend FastAPI confere as permissões antes de acessar o S3.
- Credenciais S3 do Supabase **ignoram RLS e dão acesso a todos os buckets
  deste projeto Supabase**: crie apenas o bucket necessário e proteja as
  chaves; elas nunca devem aparecer no frontend, no Git ou em conversas.

## Configuração local — quando chegar ao checkpoint de credenciais

No painel do projeto Supabase, Storage → S3, obtenha o endpoint/região e gere
uma chave S3 **somente quando os testes de código estiverem aprovados**.
Armazene o identificador e a chave secreta em seu gerenciador de segredos.

No `.env` local (não versionado), configure:

```ini
ATTACHMENT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<project-ref>.storage.supabase.co/storage/v1/s3
S3_BUCKET_NAME=securedesk-attachments
S3_REGION=sa-east-1
S3_ACCESS_KEY_ID=<chave-gerada-localmente>
S3_SECRET_ACCESS_KEY=<segredo-gerado-localmente>
```

Use **exatamente o endpoint exibido no dashboard**, com
`/storage/v1/s3`. O hostname pode ser `<project-ref>.supabase.co` ou
`<project-ref>.storage.supabase.co`; o segundo é recomendado pela Supabase.
Não use `anon`, `service_role`, JWT do usuário nem URLs públicas.

Não comite `.env`; não cole seus valores em chats. Não compartilhe capturas
contendo Access Key/Secret.

## Implantação futura (somente depois do teste real)

Depois do teste local, configure os campos `S3_*` como **Environment Variables
secretas** no Render e `ATTACHMENT_STORAGE_BACKEND=s3`. Não altere a conexão
`DATABASE_URL` com o Neon. A migration 0014 deve ter sido aplicada nesse banco.
O `render.yaml` não força a troca para `local` nos syncs do Blueprint.

**Importante:** o plano Supabase Free tem cotas; excedê-las pode provocar
limitação de serviço. Projetos gratuitos podem pausar por inatividade.
A disponibilidade da aplicação não é garantida em planos gratuitos.
Nunca habilite upgrade ou add-ons pagos sem decisão explícita.

## Validação necessária para aprovar a Etapa 05

1. Testes automatizados com fake S3 e suíte de regressão completa.
2. API real com R2/S3 simulados desativados e Supabase configurado somente
   no backend; testar upload, download, remoção e HTTP 403 para não autorizado.
3. Confirmar `storage_backend=s3` no banco para um anexo de teste.
4. Reiniciar a API e baixar **o mesmo arquivo** (mesmo identificador e bytes).
5. Depois, testar novo deploy apenas quando a migração do Neon e as variáveis
   no Render estiverem validadas; anexo deve sobreviver ao deploy.

A exclusão física após commit pode deixar órfãos se a API do provedor falhar.
Uma falha de rede durante streaming também pode encerrar a resposta; monitore
os logs `attachment_s3_*` e nunca exponha erros/segredos do SDK ao usuário.

## Referências

- https://supabase.com/docs/guides/storage/s3/authentication
- https://supabase.com/docs/guides/storage/s3/compatibility
