# CoursePlatform

CoursePlatform é uma plataforma de aprendizagem com áreas de estudante e administração. O backend usa Python/FastAPI e Postgres no Supabase; o frontend é uma aplicação estática em HTML, CSS e JavaScript servida pela mesma aplicação ou publicada separadamente.

> Estado da linha de base: a plataforma é funcional, mas a auditoria identificou correções de segurança que devem ser concluídas antes de aumentar a exposição. Consulte [docs/auditoria-lms-2026-09-12.md](docs/auditoria-lms-2026-09-12.md). Não use uma base de produção para desenvolvimento ou testes.

## Estrutura

- `api/index.py`: entrada da função Python no Vercel.
- `backend/courseplatform/app.py`: aplicação FastAPI, rotas e entrega dos ficheiros estáticos.
- `backend/courseplatform/actions.py`: adaptador compatível do dispatcher e regras ainda por extrair.
- `backend/courseplatform/contracts.py`: respostas, erros, validação e paginação comuns da API.
- `backend/courseplatform/domains/`: fronteiras e registo de ações dos nove domínios da LMS.
- `backend/courseplatform/db.py`: ligação direta ao Postgres com psycopg.
- `backend/courseplatform/certificate_pdf.py`: geração dos certificados PDF.
- `public/`: frontend usado no deploy estático.
- `backend/courseplatform/static/`: cópia gerada do frontend para fallback empacotado.
- `supabase/migrations/`: única fonte de verdade para criar e evoluir o esquema.
- `supabase/schema.sql`: snapshot de consulta; não substitui a cadeia de migrações.
- `backend/courseplatform/schema.sql`: snapshot legado do esquema, mantido para compatibilidade; pedidos da API não o executam.
- `supabase/chat_realtime.sql`: funções, policy e trigger do chat Realtime.
- `tests/`: testes Python com `unittest`.
- `scripts/`: smoke test, geração de previews e verificações de browser.

`public/` é a única fonte editável do frontend. A cópia em
`backend/courseplatform/static/` é gerada automaticamente; não deve ser editada
manualmente. Para banco, alterações novas pertencem exclusivamente a
`supabase/migrations/`; os snapshots SQL não são executados pela API.

## Pré-requisitos

- Python 3.12.
- Node.js 20 ou superior apenas para os testes de browser.
- npm ou pnpm para instalar Playwright.
- Chrome/Chromium para os testes de browser.
- Um projeto Supabase/Postgres **isolado de produção** apenas quando for necessário testar integração com banco, Storage ou Realtime.

## Instalação local

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Bash:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
```

Para instalar as dependências opcionais dos testes de browser:

```bash
npm install
npx playwright install chromium
```

Também pode usar `pnpm install` e `pnpm exec playwright install chromium`.

Crie a configuração local a partir do modelo, sem copiar credenciais de produção:

```powershell
Copy-Item .env.example .env
```

O ficheiro `.env` está ignorado pelo Git. Preencha apenas as integrações que pretende validar. Os testes unitários atuais não precisam de uma ligação real ao banco.

## Executar os testes

Antes dos testes ou de empacotar o backend, sincronize e confirme a paridade do
frontend:

```powershell
node scripts/sync_frontend.cjs
node scripts/sync_frontend.cjs --check
```

Com npm disponível, os mesmos comandos são `npm run sync:frontend` e
`npm run check:frontend`.

Suíte Python completa:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Contrato local de permissões Supabase da Etapa 3:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_supabase_access_hardening -v
```

Contrato da role Postgres mínima usada pela API:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_runtime_database_role -v
```

Contrato de migrações e health checks:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_schema_migrations_and_health -v
```

Paginação e pesquisa administrativa da Etapa 7:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_stage7_admin_lists -v
```

Contratos de modularização da Etapa 8:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_stage8_modular_monolith -v
```

Contratos e rotas HTTP tipadas em adoção incremental:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_typed_api_routes -v
node scripts/verify_versioned_api_client.cjs
```

Os fluxos de login, sessão, recuperação de acesso e perfil estão em
`backend/courseplatform/domains/identity.py`. Tentativas, respostas, ficheiros,
submissões, revisão e reenvios estão em
`backend/courseplatform/domains/assessments.py`. Emissão, configuração e acesso
a certificados estão em `backend/courseplatform/domains/certificates.py`; os
pedidos, comprovativos e decisões de pagamento estão em
`backend/courseplatform/domains/financial.py`. Cursos, módulos, conteúdos,
media e versões publicadas estão em `backend/courseplatform/domains/catalog.py`;
ofertas, grupos, matrículas e inicialização do progresso estão em
`backend/courseplatform/domains/enrollments.py`. Notificações internas,
preferências, Push, Telegram, WhatsApp, email, filas de entrega, chat e tokens
Realtime estão em `backend/courseplatform/domains/communication.py`.
Dashboard, acesso aos conteúdos, serialização segura das aulas e gestão do
progresso estão em `backend/courseplatform/domains/learning.py`. `actions.py`
mantém adaptadores compatíveis. Health operacional, estatísticas, gestão de
estudantes e staff, permissões administrativas e identidade visual estão em
`backend/courseplatform/domains/administration.py`.

As primeiras rotas tipadas e versionadas estão em `backend/courseplatform/api/`.
Elas reutilizam o dispatcher e os mesmos serviços de domínio; os clientes atuais
continuam compatíveis com `POST /api` e os nomes de ação existentes. Os
serializadores académicos partilhados residem em
`backend/courseplatform/serializers.py`, com adaptadores temporários em
`actions.py`.

As leituras tipadas cobrem agora configuração pública de curso/media, lista de
cursos, media autorizada, home, dashboard, aula e estado da tentativa do
estudante. As oito operações do cliente tentam `/api/v1` primeiro e voltam ao
respetivo action legado somente quando a rota versionada não existe no ambiente.
Falhas reais de autenticação, autorização ou infraestrutura não acionam uma
segunda chamada.

Integração das migrações numa base PostgreSQL local descartável:

```powershell
$env:COURSEPLATFORM_TEST_DATABASE_URL = "postgresql://postgres:local-test-only@127.0.0.1:55432/courseplatform_test"
.\.venv\Scripts\python.exe -m unittest tests.test_migration_postgres_integration -v
Remove-Item Env:COURSEPLATFORM_TEST_DATABASE_URL
```

O teste recusa hosts remotos e bases cujo nome não contenha `test`. A preparação
do contentor e o fluxo de staging/produção estão em
[docs/database-migrations.md](docs/database-migrations.md).

O diagnóstico SQL e o verificador de integração estão documentados em
[docs/stage3-supabase-hardening.md](docs/stage3-supabase-hardening.md). O
verificador recusa execução sem uma referência explícita de staging e não deve
ser apontado para produção.

Os testes unitários usam mocks e dados sintéticos. O resultado local não valida permissões, desempenho, backups ou configuração de produção.

Testes de certificados:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_certificate*.py" -v
.\.venv\Scripts\python.exe scripts/preview_professional_certificate.py
```

## Executar localmente

Configure uma base isolada quando quiser testar ações que consultam o Postgres. Em seguida:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.courseplatform.app:app --host 127.0.0.1 --port 8765
```

Páginas e endpoints locais:

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/admin.html`
- `http://127.0.0.1:8765/verify.html`
- `http://127.0.0.1:8765/connection-test.html`
- `http://127.0.0.1:8765/health/live`
- `http://127.0.0.1:8765/docs`
- `http://127.0.0.1:8765/openapi.json`
- `http://127.0.0.1:8765/health/ready`
- `http://127.0.0.1:8765/health/diagnostics` com `X-Admin-Token`
- `http://127.0.0.1:8765/api/index?action=health` como alias legado de readiness

Liveness não consulta o banco. Readiness faz apenas verificações leves de ligação e versão. Pedidos de negócio devolvem `DATABASE_MIGRATION_REQUIRED` quando a versão é incompatível; nenhum endpoint tenta reparar o esquema.

## Testes de browser

Os scripts de browser executam as páginas reais com respostas sintéticas e intercetam pedidos à API. Inicie o servidor local e, numa segunda consola PowerShell:

```powershell
$env:PREVIEW_URL = "http://127.0.0.1:8765"
node scripts/verify_certificate_browser.cjs
node scripts/verify_assessment_feedback.cjs
node scripts/verify_submission_retry.cjs
node scripts/verify_participation_policy.cjs
node scripts/verify_course_editions_browser.cjs
node scripts/verify_stage7_admin_lists.cjs
Remove-Item Env:PREVIEW_URL
```

Variáveis opcionais: `PREVIEW_URL`, `PLAYWRIGHT_MODULE` e `CHROME_PATH`. Os scripts guardam capturas em subdiretórios ignorados de `tmp/ui/`.

## Smoke test autenticado

`scripts/smoke_test_platform.py` chama diretamente o dispatcher, consulta a base configurada, cria sessões de login e termina essas sessões no final. Pode também ler credenciais de transição existentes em `local-secrets/`.

**Não execute este script contra produção.** Use apenas uma base de staging autorizada e credenciais de teste dedicadas:

```powershell
$env:SMOKE_STUDENT_EMAIL = "utilizador-de-teste@example.invalid"
$env:SMOKE_STUDENT_CODE = "valor-definido-no-staging"
$env:SMOKE_ADMIN_EMAIL = "admin-de-teste@example.invalid"
$env:SMOKE_ADMIN_KEY = "valor-definido-no-staging"
.\.venv\Scripts\python.exe scripts/smoke_test_platform.py
```

Nunca guarde estes valores num ficheiro versionado.

## Configuração por variáveis

Os valores e exemplos permanecem em `.env.example`. Apenas os nomes são documentados aqui.

Ligação ao Postgres, por ordem de resolução:

- `DATABASE_URL`, `POSTGRES_URL`, `POSTGRES_URL_NON_POOLING` ou `POSTGRES_PRISMA_URL`;
- ou `POSTGRES_HOST`, `POSTGRES_DATABASE`/`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`;
- ou `SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_URL` com `POSTGRES_PASSWORD`.

Em ambientes publicados, `DATABASE_URL` deve autenticar como a role mínima
`courseplatform_api`, não como `postgres`. A criação, ativação, validação e
reversão estão descritas em
[docs/runtime-database-role.md](docs/runtime-database-role.md). URLs com a role
administrativa continuam reservadas à execução controlada de migrações e nunca
devem ser fornecidas ao processo web.

Aplicação e conexão:

- `DEFAULT_COURSE_ID`, `SESSION_HOURS`, `DB_CONNECT_TIMEOUT`, `DB_CONNECT_RETRIES`, `CORS_ORIGINS`, `APP_VERSION`.

Recuperação de estudantes:

- `PASSWORD_RESET_HASH_KEY` (segredo de servidor com pelo menos 32 bytes);
- `PASSWORD_RESET_TTL_MINUTES`, `PASSWORD_RESET_ACCOUNT_LIMIT`, `PASSWORD_RESET_ACCOUNT_WINDOW_MINUTES`;
- `PASSWORD_RESET_SOURCE_LIMIT`, `PASSWORD_RESET_SOURCE_WINDOW_MINUTES`, `PASSWORD_RESET_COMPLETION_LIMIT`, `PASSWORD_RESET_COMPLETION_WINDOW_MINUTES`.
- Requer também SMTP ativo e `PLATFORM_URL`. A resposta pública é sempre genérica; o link de utilização única é enviado apenas para o email guardado na conta.

Supabase Storage e Realtime:

- `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SECRET_KEY`;
- `SUPABASE_SERVICE_ROLE_KEY` apenas como compatibilidade legada;
- `SUPABASE_CERTIFICATE_BUCKET`, `SUPABASE_SUBMISSION_BUCKET`, `SUPABASE_PAYMENT_RECEIPT_BUCKET`;
- `SUBMISSION_FILE_MAX_BYTES`, `PAYMENT_RECEIPT_MAX_BYTES`, `STORAGE_LEGACY_READ_MAX_BYTES`, `SUPABASE_STORAGE_TIMEOUT_SECONDS`;
- `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`;
- `SUPABASE_REALTIME_JWT_SECRET`, `SUPABASE_JWT_SECRET`, `CHAT_REALTIME_ENABLED`, `CHAT_REALTIME_TOKEN_MINUTES`.

Recuperação administrativa atual:

- `ADMIN_RECOVERY_KEY_HASH`; `ADMIN_RECOVERY_KEY` existe apenas como fallback de desenvolvimento.

Notificações:

- `NOTIFICATION_CONFIG_ENCRYPTION_KEY`;
- `WHATSAPP_ENABLED`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_CONFIG_ENCRYPTION_KEY`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_GRAPH_API_VERSION`, `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANGUAGE`, `WHATSAPP_PLATFORM_URL`, `WHATSAPP_TIMEOUT_SECONDS`;
- `EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_USE_TLS`, `SMTP_TIMEOUT_SECONDS`;
- `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_PARSE_MODE`, `TELEGRAM_TIMEOUT_SECONDS`;
- `WEB_PUSH_ENABLED`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `WEB_PUSH_TTL_SECONDS`, `WEB_PUSH_TIMEOUT_SECONDS`, `PLATFORM_URL`.

Frontend: a URL da API é resolvida em `public/config.js` por `window.COURSE_PLATFORM_API_URL`, override local ou origem Vercel. Não coloque chaves secretas no frontend.

## Dados e segurança

- A autenticação atual é própria: bcrypt no Postgres, tokens opacos e apenas hashes dos tokens em `courseplatform.sessions`. Staff ligado a um estudante usa a mesma credencial, enquanto `admins` concede apenas o papel administrativo; contas administrativas antigas permanecem temporariamente compatíveis. Ainda não usa Supabase Auth.
- A recuperação do estudante guarda apenas hashes HMAC do email/origem e SHA-256 do token. O token chega ao browser no fragmento do link, é removido imediatamente da barra de endereço e só pode ser consumido uma vez.
- A API usa ligação direta ao Postgres. A chave `SUPABASE_SECRET_KEY` (ou a
  `SUPABASE_SERVICE_ROLE_KEY` legada) é usada apenas no backend para objetos
  privados e nunca deve chegar ao navegador.
- Trabalhos e comprovativos novos são validados pelo conteúdo e guardados em buckets privados. A migração histórica é descrita em [docs/stage6-private-storage.md](docs/stage6-private-storage.md).
- Não aplique snapshots SQL diretamente numa base existente. Use apenas a cadeia versionada e o processo de [migrações](docs/database-migrations.md), com backup, revisão do dry-run e autorização.
- Não use IDs públicos de estudantes como segredo.
- Consulte [docs/access-control-matrix.md](docs/access-control-matrix.md) antes de acrescentar endpoints ou ações.

## Documentação

- [Arquitetura atual](docs/architecture-current.md)
- [Matriz inicial de acessos](docs/access-control-matrix.md)
- [Endurecimento Supabase da Etapa 3](docs/stage3-supabase-hardening.md)
- [Migrações e health checks](docs/database-migrations.md)
- [Paginação e pesquisa administrativa da Etapa 7](docs/stage7-pagination-and-search.md)
- [Monólito modular da Etapa 8](docs/stage8-modular-monolith.md)
- [Auditoria e roteiro LMS](docs/auditoria-lms-2026-09-12.md)
- [Instruções de evolução por etapas](docs/instrucoes-agente-evolucao-lms.md)
- [Certificados](docs/certificate-layout.md)
- [Reenvio de trabalhos](docs/submission-retry.md)
- [Notificações multicanal](docs/multichannel-notifications.md)
- [Checklist de produção existente](docs/production-health-checklist.md)

## Deploy

O repositório está organizado para servir o frontend de `public/` e publicar `api/index.py` como função Python no Vercel. Esta linha de base não executa nem autoriza deploy. Antes de publicar, valide variáveis no ambiente correto, migrações, smoke tests de staging e possibilidade de rollback.
