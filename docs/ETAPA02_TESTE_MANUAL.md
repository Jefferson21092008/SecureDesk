# SecureDesk — Etapa 02: validação manual da operação de chamados

**Escopo:** interface operacional de chamados, sem mudança de schema ou endpoints. Aplique o patch na branch `feat/experiencia-operacao-chamados` criada do merge `4d4b204` e rode a bateria de testes antes do commit.

## Cuidados

- Execute apenas no ambiente **local/de desenvolvimento**, com banco PostgreSQL de desenvolvimento e conta ADMIN/AGENT/USER de teste.
- Não aponte a API local ao Neon/Render de produção. Não envie `.env`, senhas, JWT ou anexos privados.
- O armazenamento atual de anexos do Render gratuito é **efêmero**; anexos não devem ser considerados duráveis em produção.
- O frontend tem autorização de interface para melhorar a experiência; a API valida RBAC e IDOR independentemente.

## Teste funcional sugerido

1. Inicie PostgreSQL e API local; abra o frontend pelo Nginx Docker (`http://localhost:3000`) ou por servidor local com proxy `/api` para `127.0.0.1:8000`. Nunca abra HTML diretamente por `file://`.
2. Entre como ADMIN, crie 25 chamados de teste pelo Swagger/seed se necessário e abra **Chamados**. Verifique contagem total e navegação entre páginas 1 e 2. Busque e filtre; a página deve voltar à primeira.
3. Clique no título de um chamado no dashboard e na lista. A janela precisa mostrar título, descrição, prioridade, status, solicitante, responsável, SLA e datas.
4. Adicione um comentário. Ele deve aparecer na lista ao atualizar os detalhes. Coloque texto como `<img src=x onerror=alert(1)>`: deve aparecer como texto e não ser executado.
5. Anexe um arquivo pequeno de teste permitido pelo backend. Veja o nome e baixe com a autenticação JWT ativa. Teste um arquivo não permitido e confira erro legível sem travar a página.
6. Como ADMIN, atribua o chamado a um AGENT existente; confira nome/ID e histórico de atribuição. Feche e reabra o chamado, verificando status e histórico.
7. Entre como AGENT. Veja a opção de se atribuir um chamado sem responsável; confira possibilidade de liberar seu próprio chamado. Quando atribuído a outro agente, as ações devem ficar indisponíveis. A API deve recusar requisições proibidas mesmo que enviadas fora da interface.
8. Entre como USER. Confirme leitura/comentário/anexo dos **próprios** chamados e ausência de controles administrativos. Tente consultar um chamado de outra conta pelo Swagger; espere `404` sem revelar dados.
9. Em dispositivos/larguras de 390px, 768px e desktop, verifique janela de detalhes, campos, botões, rolamento, fechamento por botão e tecla ESC.
10. Verifique resultados após sessão expirar, em respostas `401`, `403`, `429`, API indisponível e arquivos ausentes, sem exibir mensagens genéricas de sucesso.

## Validação automatizada

```cmd
python -m pytest -q tests/test_frontend_ticket_operations.py
python -m ruff check .
python -m compileall -q app tests scripts alembic
python -m pytest -q
python -m coverage run --source=app -m pytest -q
python -m coverage report -m
python -m pip_audit
python -m alembic current
python -m alembic heads
git diff --check
git status --short
```

`node --check frontend/app.js` é recomendado quando Node.js estiver disponível.

**Critérios para concluir:** testes, migrações e CI aprovados; RBAC/IDOR e downloads autenticados testados; erros tratados; frontend responsivo; commit/PR/merge sem artefatos ou credenciais sensíveis.
