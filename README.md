# CoursePlatform

CoursePlatform é uma plataforma de aprendizagem com áreas de estudante e administração. O backend usa Python/FastAPI e Postgres no Supabase; o frontend é uma aplicação estática em HTML, CSS e JavaScript servida pela mesma aplicação ou publicada separadamente.

> Estado da linha de base: a plataforma é funcional, mas a auditoria identificou correções de segurança que devem ser concluídas antes de aumentar a exposição. Consulte [docs/auditoria-lms-2026-09-12.md](docs/auditoria-lms-2026-09-12.md). Não use uma base de produção para desenvolvimento ou testes.

## Estrutura

- `api/index.py`: entrada da função Python no Vercel.
- `backend/courseplatform/app.py`: aplicação FastAPI, rotas e entrega dos ficheiros estáticos.
- `backend/courseplatform/actions.py`: dispatcher e regras de negócio atuais.
- `backend/courseplatform/db.py`: ligação direta ao Postgres com psycopg.
- `backend/courseplatform/certificate_pdf.py`: geração dos certificados PDF.
- `public/`: frontend usado no deploy estático.
- `backend/courseplatform/static/`: fallback estático empacotado com o backend.
- `supabase/schema.sql`: esquema para instalação manual no Supabase.
- `backend/courseplatform/schema.sql`: esquema que a API atual usa na criação automática.
- `supabase/chat_realtime.sql`: funções, policy e trigger do chat Realtime.
- `tests/`: testes Python com `unittest`.
- `scripts/`: smoke test, geração de previews e verificações de browser.

Os dois ficheiros de esquema e as duas cópias do frontend não são atualmente idênticos. Essa divergência está registada em [docs/architecture-current.md](docs/architecture-current.md) e não deve ser resolvida dentro de uma alteração sem migração e testes próprios.

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

Suíte Python completa:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Na linha de base de 12 de setembro de 2026 foram executados 96 testes, todos aprovados. Estes testes usam mocks e dados sintéticos; o resultado não valida permissões, desempenho, backups ou configuração de produção.

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
- `http://127.0.0.1:8765/api/index?action=health`

O health check atual pode consultar e criar o esquema quando este está ausente. Por isso, aponte a aplicação apenas para uma base descartável ou staging autorizado.

## Testes de browser

Os scripts de browser executam as páginas reais com respostas sintéticas e intercetam pedidos à API. Inicie o servidor local e, numa segunda consola PowerShell:

```powershell
$env:PREVIEW_URL = "http://127.0.0.1:8765"
node scripts/verify_certificate_browser.cjs
node scripts/verify_assessment_feedback.cjs
node scripts/verify_submission_retry.cjs
node scripts/verify_participation_policy.cjs
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

Aplicação e conexão:

- `DEFAULT_COURSE_ID`, `SESSION_HOURS`, `DB_CONNECT_TIMEOUT`, `DB_CONNECT_RETRIES`, `CORS_ORIGINS`, `APP_VERSION`.

Recuperação de estudantes:

- `PASSWORD_RESET_HASH_KEY` (segredo de servidor com pelo menos 32 bytes);
- `PASSWORD_RESET_TTL_MINUTES`, `PASSWORD_RESET_ACCOUNT_LIMIT`, `PASSWORD_RESET_ACCOUNT_WINDOW_MINUTES`;
- `PASSWORD_RESET_SOURCE_LIMIT`, `PASSWORD_RESET_SOURCE_WINDOW_MINUTES`, `PASSWORD_RESET_COMPLETION_LIMIT`, `PASSWORD_RESET_COMPLETION_WINDOW_MINUTES`.
- Requer também SMTP ativo e `PLATFORM_URL`. A resposta pública é sempre genérica; o link de utilização única é enviado apenas para o email guardado na conta.

Supabase Storage e Realtime:

- `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_CERTIFICATE_BUCKET`;
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

- A autenticação atual é própria: bcrypt no Postgres, tokens opacos e apenas hashes dos tokens em `courseplatform.sessions`. Ainda não usa Supabase Auth.
- A recuperação do estudante guarda apenas hashes HMAC do email/origem e SHA-256 do token. O token chega ao browser no fragmento do link, é removido imediatamente da barra de endereço e só pode ser consumido uma vez.
- A API usa ligação direta ao Postgres. A chave `SUPABASE_SERVICE_ROLE_KEY` é usada no backend para uploads administrativos no Storage e nunca deve chegar ao navegador.
- Não aplique `supabase/schema.sql`, `supabase/chat_realtime.sql` ou o esquema empacotado numa base existente sem backup, revisão do diff e autorização.
- Não use IDs públicos de estudantes como segredo.
- Consulte [docs/access-control-matrix.md](docs/access-control-matrix.md) antes de acrescentar endpoints ou ações.

## Documentação

- [Arquitetura atual](docs/architecture-current.md)
- [Matriz inicial de acessos](docs/access-control-matrix.md)
- [Auditoria e roteiro LMS](docs/auditoria-lms-2026-09-12.md)
- [Instruções de evolução por etapas](docs/instrucoes-agente-evolucao-lms.md)
- [Certificados](docs/certificate-layout.md)
- [Reenvio de trabalhos](docs/submission-retry.md)
- [Notificações multicanal](docs/multichannel-notifications.md)
- [Checklist de produção existente](docs/production-health-checklist.md)

## Deploy

O repositório está organizado para servir o frontend de `public/` e publicar `api/index.py` como função Python no Vercel. Esta linha de base não executa nem autoriza deploy. Antes de publicar, valide variáveis no ambiente correto, migrações, smoke tests de staging e possibilidade de rollback.
