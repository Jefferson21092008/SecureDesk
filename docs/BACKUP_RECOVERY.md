# SecureDesk — Etapa 06: backup e recuperação (PATCH 01)

**Estado: PATCH 01 preparado; não é prova de recuperação.** Neste patch são
adicionadas **exportação e verificação offline**, sem comandos de restauração.
Um backup só será considerado recuperável após **restore real em ambiente
isolado** na continuação da Etapa 06.

## O que existe / riscos

- **Neon PostgreSQL:** contém contas, chamados, permissões, metadados de anexos
  (`attachments.storage_key` e `storage_backend`) e revisão Alembic `0014`.
- **Supabase Storage S3, bucket privado:** contém **bytes** dos novos anexos.
  Dump do PostgreSQL **não** contém os bytes dos objetos S3.
- **`local` legado:** registros antigos com `storage_backend=local` podem
  apontar para arquivos efêmeros já perdidos; não os reconstruímos do dump.
- **Não existe snapshot distribuído atômico** entre PostgreSQL e S3 neste
  projeto. Um backup feito enquanto usuários criam/apagam arquivos pode ficar
  inconsistente. Evitar escritas durante a janela de backup; definir janela de
  manutenção antes de exportar produção.
- **Supabase Free / Neon Free / Render Free:** limites de armazenamento, rede e
  inatividade podem afetar a operação. Consulte as cotas antes de exportar
  muitos arquivos. Não fazer upgrade, habilitar recurso pago nem cadastrar
  cartão. Os comandos aqui NÃO criam produtos/recursos em nuvem.
- **Credenciais S3 do Supabase podem contornar RLS:** armazenar apenas no
  backend/.env privado. Não enviar dumps, manifests ou dados reais por chat.

## Proteções implementadas pelo script

`python scripts/backup_securedesk.py --help`

- `database`: `pg_dump --format=custom`; verifica índice `pg_restore --list`,
  calcula SHA-256 e escreve manifesto JSON. Credenciais não entram no comando
  nem no manifesto. O `pg_dump` pode solicitar a senha no console (ou usar
  seu `pgpass` configurado fora do repositório).
- `objects`: faz **LIST/GET apenas** no bucket configurado nas variáveis `S3_*`
  do SecureDesk. Copia bytes sem alterar objetos remotos. Não usa nomes/chaves
  S3 como caminho no disco: nomes locais são hashes da chave. Faz conferência
  de tamanho listado vs baixado e SHA-256 da cópia offline.
- `verify-database` / `verify-objects`: comprovam integridade **local** do
  backup. `verify-database` não equivale a `pg_restore` em um banco vazio.
- `--environment production` exige `--confirm-production`; para produção,
  `database` exige SSL e recusa host do pooler. Nenhum dos comandos faz restore,
  exclusão de banco ou exclusão S3.
- Recusa destino dentro do repositório Git. Dump e S3 devem permanecer **fora
  do GitHub**, mesmo com novas regras de `.gitignore`.
- Exportação de S3 tem limites de proteção: por padrão **1.000 objetos e
  256 MiB** no total. Não aumente sem estimar espaço em disco e cota de rede.
  É exportação integral dos objetos listados; falha se superar os limites.

Os manifests de S3 **contêm as chaves privadas dos objetos**, indispensáveis
para restauração. Não os publique; um manifesto não é um relatório público.
Armazene cópias offline com proteção do Windows/BitLocker quando disponível,
permissões restritas e acesso apenas ao operador. SHA-256 detecta corrupção da
cópia, **não é criptografia**. Em pasta exposta ou equipamento compartilhado,
use armazenamento criptografado antes de copiar dados reais.

## Checkpoint 02 — primeiro teste: dump do PostgreSQL LOCAL

Usar um CMD aberto na raiz do SecureDesk, com `.venv` ativado. **Confirmar
primeiro que o host é `127.0.0.1`, banco `securedesk`, e não o Neon.**

```cmd
python scripts/backup_securedesk.py --help
python scripts/backup_securedesk.py database --host 127.0.0.1 --port 5432 --dbname securedesk --user securedesk --sslmode disable --environment development --out-dir "%USERPROFILE%\Documents\SecureDesk_Backups\etapa06"
```

A saída será algo como `Backup DB pronto: ...\db-AAAA....json`.
Substitua o caminho indicado pelo seu **manifesto real**:

```cmd
python scripts/backup_securedesk.py verify-database --manifest "CAMINHO_COMPLETO_DO_MANIFESTO.json"
```

O resultado esperado é um SHA-256 compatível e `pg_restore --list OK`.
**Não use `pg_restore -d securedesk` nem tente restaurar o Neon.** O restore
em banco local **descartável** é um checkpoint posterior.

Para ver o ambiente do script:

```cmd
python scripts/backup_securedesk.py database --help
python scripts/backup_securedesk.py objects --help
```

### Diagnóstico do dump

- `pg_dump e pg_restore precisam estar no PATH`: revisar instalação do
  PostgreSQL 18 no Windows; `pg_dump --version`, `pg_restore --version`.
- `password authentication failed`: revisar login local; não colar senha.
- `pg_dump falhou`: confirmar PostgreSQL Running, host/porta/banco/usuário e
  espaço livre. Não repetir em produção antes de diagnóstico.
- Erro de SSL local: usar `--sslmode disable` para `127.0.0.1` **quando sua
  instância local não exigir TLS**; no Neon usar require ou mais forte.
- Dump legível não prova restauração: somente `pg_restore` em outro banco e
  consultas SQL comprovam isso. **Não afirmar restore concluído ainda.**

## Próximos checkpoints (não executar ainda)

**A. Restore isolado do banco:** criar banco descartável, restaurar dump,
confirmar `alembic_version` = `0014_attachment_storage_backend`, tabelas,
contagens e amostra sintética; destruir apenas a base descartável identificada.
Nunca restaurar sobre `securedesk` em uso ou `neondb` produção.

**B. Exportação de S3:** com `.env` **privado** já configurado e permissão
explícita para ler dados do bucket, e cotas verificadas, executar:

```cmd
python scripts/backup_securedesk.py objects --environment production --confirm-production --out-dir "%USERPROFILE%\Documents\SecureDesk_Backups\etapa06" --max-total-mib 30
python scripts/backup_securedesk.py verify-objects --manifest "CAMINHO_COMPLETO_DO_MANIFESTO.json"
```

Esse comando é só **leitura**, mas realiza downloads reais e pode consumir
cota de egress do Supabase. **Não o execute até o checkpoint autorizar.**
Não use bucket público nem envie manifest/dumps aqui.

**C. Recuperação conjunta:** comparar os objetos do manifesto com as chaves
`storage_backend='s3'` do banco restaurado. Usar dados sintéticos para
reconstruir os bytes em diretório isolado ou bucket de TESTE privado, se um
bucket extra realmente for necessário e permitido pelas cotas. Nunca usar
`delete_object` ou `put_object` no bucket de produção como exercício.

**D. Janela consistente:** suspender uploads/exclusões e demais alterações de
metadados relevantes, registrar o momento da coleta, produzir DB+S3,
verificar manifestos, só então liberar alterações. Mesmo assim, a prova de
consistência deverá ser por reconciliação; não existe transação global.

**E. Evidências / política:** registrar horários sem valores sensíveis,
resumo de objetos, tamanhos, hashes e eventuais falhas. Definir retenção,
frequência, operador e local de segunda cópia. **RPO/RTO não medidos** até
execução e cronometragem de um restore real. Sem backups agendados pagos.

## Comandos de qualidade

```cmd
python -m pytest -q tests/test_backup_securedesk.py
python -m ruff check .
python -m compileall -q app tests alembic scripts
python -m pytest -q
python -m coverage run --source=app -m pytest -q
python -m coverage report -m
python -m pip check
python -m pip_audit
```

Este patch não altera os endpoints, o frontend, a modelagem SQL, as migrations,
o deploy, as configurações da produção nem os objetos existentes do Supabase.

## PATCH 02 — Backup verificável dos anexos legados locais

Os registros `attachments.storage_backend = 'local'` apontam para arquivos
físicos que **não** fazem parte do dump PostgreSQL nem da exportação S3.
Quando esses arquivos ainda existem no DEV local, preservá-los separadamente.

O PATCH 02 acrescenta dois comandos **somente leitura nas origens**:

- `local`: consulta apenas o PostgreSQL DEV em `localhost`/`127.0.0.1`/`::1`
  e copia apenas arquivos referenciados por registros `local`. Requer
  `APP_ENV=development` e `--environment development`. Falha se arquivo
  faltar, tamanho não corresponder, chave for insegura ou exceder os limites.
  **Não** acessa Neon, não faz upload ao Supabase, não altera o banco.
- `verify-local`: confere manifesto, quantidade exata dos arquivos, tamanho
  e SHA-256 de cada cópia, **sem consultar banco nem armazenamento original**.

No CMD da raiz do SecureDesk, com `.venv` e banco local já confirmados:

```cmd
python scripts/backup_securedesk.py local --environment development --out-dir "%USERPROFILE%\Documents\SecureDesk_Backups\etapa06" --max-files 10 --max-total-mib 30
```

O script devolve `Backup local pronto: ...\local-...\manifest.json`.
Para verificar, **substitua o exemplo pelo caminho completo retornado**:

```cmd
python scripts/backup_securedesk.py verify-local --manifest "CAMINHO_COMPLETO_DO_MANIFESTO.json"
```

Os arquivos são guardados sob `objects/` com nomes SHA-256 da chave do
anexo e extensão `.bin`; o manifesto confidencial preserva a relação entre
a chave original e o arquivo salvo, para uma recuperação posterior.
Não divulgar manifesto, anexos, chaves ou dados reais. Guardar junto ao dump
do PostgreSQL e à exportação S3 em armazenamento privado, preferencialmente
com **segunda cópia protegida e criptografada**.

**Limites da prova:** a cópia dos arquivos `local` no computador DEV não prova
que um arquivo local antigo sobreviveu ao filesystem efêmero do Render.
Também **não** torna atômico o backup PostgreSQL + S3 + local. Não executar
comandos de restauração sobre produção para comprovar recuperação. O exercício
final usa exclusivamente ambiente isolado.
