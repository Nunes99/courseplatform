# Reenvio de trabalhos

Em Administracao > Submissoes > Abrir, o administrador ou revisor pode:

- Escolher "Devolver para correcao" na avaliacao, autorizar o reenvio e indicar um novo prazo.
- Usar "Devolver e autorizar novo envio" para trabalhos expirados, nao aprovados ou com documentos incorretos, sem precisar de atribuir uma nota.
- Cancelar uma autorizacao pendente antes de o estudante iniciar a nova tentativa.

O prazo e enviado em UTC e armazenado no campo existente `reviews.correction_deadline`.
Nao ha novas tabelas, colunas ou configuracoes de ambiente.

Ao iniciar o reenvio, o backend bloqueia o registo de progresso durante a transacao,
valida a autorizacao e o prazo, cria uma tentativa e consome a autorizacao anterior.
As respostas anteriores sao copiadas sem classificacoes. Os ficheiros anteriores
permanecem na tentativa original; o estudante carrega os documentos corrigidos na nova.
Pedidos repetidos de inicio reutilizam a tentativa ativa.

Uma tentativa mais antiga continua disponivel no historico, mas nao pode ser
devolvida novamente depois de existir uma tentativa mais recente. O estudante so
pode guardar respostas, carregar ou eliminar ficheiros e submeter a sua tentativa
atual enquanto estiver em curso, dentro do prazo e com acesso ao modulo.

Autorizacoes antigas sem prazo de correcao conservam a duracao configurada do modulo.
Novas autorizacoes exigem sempre um prazo futuro. Alterar apenas o estado para
"Correcao solicitada" no controlo administrativo nao equivale a autorizar reenvio;
deve ser utilizada a acao especifica de devolucao ou a opcao da avaliacao.

## Verificacao local

```powershell
& .venv/Scripts/python.exe -m unittest discover -s tests -v
```

Com a API local em execucao, `scripts/verify_submission_retry.cjs` verifica os
formularios reais de administrador e estudante com dados sinteticos e API simulada.
Usa Playwright; `PLAYWRIGHT_MODULE`, `CHROME_PATH` e `PREVIEW_URL` permitem indicar
o runtime e o servidor local (por omissao, `http://127.0.0.1:8766`).
As capturas ficam em `tmp/ui/submission-retry/` e nao sao versionadas.

Os testes nao escrevem no Supabase de producao. A publicacao e a verificacao com
contas de teste no ambiente publicado devem ser feitas separadamente.
