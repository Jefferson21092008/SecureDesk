# SecureDesk — Etapa 04: confiabilidade dos uploads

## O que mudou

- O backend **não publica mais o arquivo enquanto ele está sendo escrito**: cria um
  `.upload-*.part` no mesmo diretório, valida o tamanho em blocos e conclui a escrita;
  só então o nome definitivo é publicado com `os.replace` (substituição atômica
  **no mesmo sistema de arquivos**).
- Falhas normais de abertura, escrita e publicação do arquivo retornam `503` com
  mensagem genérica e removem o temporário, quando possível. Arquivos vazios,
  grandes demais e tipos inválidos mantêm os códigos anteriores (`400`, `413`, `415`).
- A exclusão continua ocorrendo **após o commit no banco**: caso o sistema de
  arquivos falhe, o registro já excluído **não é recriado**. A falha passa a
  produzir aviso `attachment_cleanup_failed`, com chave aleatória e tipo de erro,
  para investigação e eventual limpeza manual.
- Configurações Nginx de desenvolvimento e produção passam a aceitar **26 MiB
  de corpo HTTP** em `/api/` (limite configurável máximo da API: 25 MiB por
  arquivo, com margem para multipart). **O backend continua aplicando o valor
  de `ATTACHMENT_MAX_BYTES`, 5 MiB por padrão**.

## Verificações sugeridas no Windows

Em dois terminais separados, com PostgreSQL local respondendo:

```cmd
python -m pytest -q tests/test_attachment_reliability.py tests/test_attachments.py
python -m ruff check .
python -m compileall -q app tests alembic scripts
```

Depois executar a suíte completa e cobertura como nos demais checkpoints.
Com Uvicorn e o frontend local iniciados, fazer um upload autorizado de TXT pequeno,
confirmar listagem, download com conteúdo idêntico e exclusão. Testar o mesmo fluxo
pela rota `/api/` do proxy, se disponível. Não publicar tokens nem arquivos pessoais.

Uma simulação de falha de armazenamento deve retornar `503` e não deixar um arquivo
com o nome definitivo. Os testes automatizados cobrem abertura/escrita/publicação
com falha, tamanho excedido e limpeza de exclusão.

## Diagnóstico e limites conhecidos

- `attachment_upload_storage_failed` indica erro de I/O ao armazenar. A mensagem
  exposta ao cliente não revela caminhos do servidor.
- `attachment_temp_cleanup_failed` indica que a limpeza de um `.part` falhou.
- `attachment_cleanup_failed` indica que uma exclusão física falhou **depois do
  commit da exclusão no banco**. Investigue o armazenamento e confira a chave
  gerada internamente antes de intervir. Não apague arquivos indiscriminadamente.
- Uma queda de energia/processo pode deixar um `.upload-*.part` antigo. Limpeza
  manual deve ocorrer **com o serviço parado**, após conferir que não há uploads
  ativos; o serviço não remove esses arquivos automaticamente.
- Sistema de arquivos e PostgreSQL **não formam uma transação única**. Ainda pode
  restar um arquivo órfão se o processo morrer após publicar o arquivo, mas antes
  do `COMMIT`, ou se a exclusão física falhar após o `COMMIT`. Um mecanismo de
  reconciliação/armazenamento durável será considerado na **Etapa 05**.
- Em Render, o diretório `/tmp/securedesk-attachments` continua temporário. Esta
  etapa **não** torna anexos persistentes após reinícios/deploys.
- Os testes unitários não substituem testes reais de proxy, falha de disco ou
  deploy. Verificar o limite de upload de outras camadas, caso existam.

## Escopo

Sem migrations, novas dependências, mudanças de permissões de usuário ou alterações
no contrato dos endpoints de anexos. A resposta `503` em falhas de armazenamento
substitui um erro 500 genérico nesses casos.
