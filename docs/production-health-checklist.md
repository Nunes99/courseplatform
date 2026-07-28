# Checklist de producao

Use esta checklist quando o endpoint `/api/index?action=health` nao devolver `database: true` e `authConfigured: true`.

## Resultado esperado

```json
{
  "success": true,
  "data": {
    "database": true,
    "databaseConfigured": true,
    "databaseError": "",
    "authConfigured": true
  }
}
```

## Estrutura do projeto no Vercel

A plataforma nao depende de `vercel.json`.

- `public/`: site estatico publicado na raiz do dominio.
- `api/index.py`: funcao Python publicada como `/api/index`.
- `backend/courseplatform/`: codigo interno usado pela funcao Python.
- `supabase/schema.sql`: schema atual da base.

No painel do Vercel, o **Root Directory** deve estar vazio ou `./`. Nao use `api` como Root Directory, senao o deploy cria apenas a funcao e ignora o site.

Links esperados:

- `/`
- `/admin.html`
- `/verify.html`
- `/connection-test.html`
- `/api/index?action=health`

## Variaveis obrigatorias no Vercel

- `DEFAULT_COURSE_ID`
- `SESSION_HOURS`
- `DB_CONNECT_TIMEOUT`
- `DB_CONNECT_RETRIES`
- `CORS_ORIGINS`

Nao use `PASSWORD_PEPPER` nem `ADMIN_MASTER_KEY_HASH`. A autenticacao atual usa hashes bcrypt por utilizador no Supabase/Postgres.

## Conexao Supabase/Postgres

Pode usar uma destas opcoes.

Opcao 1, recomendada:

- `DATABASE_URL`

Formato:


```text
postgresql://postgres.PROJECT_REF:PASSWORD_ENCODED@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require
```

Opcao 2, variaveis separadas:

- `POSTGRES_HOST`
- `POSTGRES_DATABASE`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`

Opcao 3, fallback:

- `SUPABASE_URL`
- `POSTGRES_PASSWORD`

Com `SUPABASE_URL + POSTGRES_PASSWORD`, a API tenta usar o host direto `db.PROJECT_REF.supabase.co:5432`.

Se a senha tiver `%`, o valor deve estar codificado como `%25`. Exemplo: uma senha que comeca por `%abc` deve entrar na URL como `%25abc`.

O health atual tambem normaliza `%` bruto em runtime, mas a configuracao de producao deve ficar corretamente codificada no Vercel.

Estas variaveis nao substituem a senha Postgres para esta API Python:

- `SUPABASE_JWT_SECRET`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`

Elas podem ser uteis para Supabase Auth/Storage/REST, mas a camada atual usa Postgres direto com `psycopg`.

## Diagnostico pelo health

O endpoint devolve:

- `authDiagnostics.mode`
- `authDiagnostics.requiresPasswordPepper`
- `authDiagnostics.requiresAdminMasterKeyHash`
- `databaseDiagnostics.host`
- `databaseDiagnostics.port`
- `databaseDiagnostics.database`
- `databaseDiagnostics.sslmode`
- `databaseDiagnostics.source`
- `databaseDiagnostics.issues`

Esses campos nao mostram segredos; servem para confirmar se o ambiente publicado recebeu as variaveis certas.

Se `databaseError` for `ProgrammingError`, normalmente o deploy conectou ao Postgres, mas o schema esperado nao esta no banco apontado pela variavel ativa. Confirme `databaseDiagnostics.source`, `host` e `database`, e execute `supabase/schema.sql` nesse mesmo projeto Supabase.

A API tambem tenta criar o schema automaticamente quando ele esta ausente, usando a copia empacotada em `backend/courseplatform/schema.sql`. Isso cria tabelas vazias, mas nao recria os dados historicos dos estudantes. Depois disso:

- `schemaCreated: true`: o schema foi criado automaticamente.
- `dataDiagnostics.dataReady: false`: a base esta vazia ou sem utilizadores com password.
- `DATABASE_EMPTY`: o login chegou ao banco, mas esse banco nao tem estudantes/admins migrados.

Se aparecer `DATABASE_EMPTY`, o Vercel esta ligado a uma base diferente da base que recebeu os dados migrados, ou os dados ainda nao foram importados para esse projeto Supabase.

## Testes locais

```bash
python scripts/smoke_test_platform.py
```

Para ambientes sem `local-secrets/auth-transition-*.txt`, defina:

```text
SMOKE_STUDENT_EMAIL
SMOKE_STUDENT_CODE
SMOKE_ADMIN_EMAIL
SMOKE_ADMIN_KEY
```

As migracoes antigas foram removidas do fluxo operacional. Novos dados devem ser registados diretamente no Supabase pela API Python.
