# Checklist de producao

Use esta checklist quando o endpoint `/api?action=health` nao devolver `database: true` e `authConfigured: true`.

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

## Variaveis obrigatorias no Vercel

- `DATABASE_URL`
- `DEFAULT_COURSE_ID`
- `SESSION_HOURS`
- `DB_CONNECT_TIMEOUT`
- `DB_CONNECT_RETRIES`
- `CORS_ORIGINS`

Nao use `PASSWORD_PEPPER` nem `ADMIN_MASTER_KEY_HASH`. A autenticacao atual usa hashes bcrypt por utilizador no Supabase/Postgres.

## DATABASE_URL Supabase

Formato recomendado:

```text
postgresql://postgres.PROJECT_REF:PASSWORD_ENCODED@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require
```

Se a senha tiver `%`, o valor deve estar codificado como `%25`. Exemplo: uma senha que comeca por `%abc` deve entrar na URL como `%25abc`.

O health atual tambem normaliza `%` bruto em runtime, mas a configuracao de producao deve ficar corretamente codificada no Vercel.

## Diagnostico pelo health

O endpoint devolve:

- `authDiagnostics.mode`
- `authDiagnostics.requiresPasswordPepper`
- `authDiagnostics.requiresAdminMasterKeyHash`
- `databaseDiagnostics.host`
- `databaseDiagnostics.port`
- `databaseDiagnostics.database`
- `databaseDiagnostics.sslmode`
- `databaseDiagnostics.issues`

Esses campos nao mostram segredos; servem para confirmar se o ambiente publicado recebeu as variaveis certas.

## Testes locais

```bash
python scripts/smoke_test_platform.py
python scripts/migrate_sheets_to_supabase.py --xlsx "C:\Users\manyu\Downloads\CoursePlatformDB.xlsx" --validate-only
python scripts/migrate_to_supabase_password_auth.py
```

Para ambientes sem `local-secrets/auth-transition-*.txt`, defina:

```text
SMOKE_STUDENT_EMAIL
SMOKE_STUDENT_CODE
SMOKE_ADMIN_EMAIL
SMOKE_ADMIN_KEY
```

## Migrar autenticacao antiga

Dry-run:

```bash
python scripts/migrate_to_supabase_password_auth.py
```

Aplicar gerando novas senhas para utilizadores sem `password_hash`:

```bash
python scripts/migrate_to_supabase_password_auth.py --apply
```

Rotacionar todos os estudantes e admins, mesmo quem ja tinha `password_hash`:

```bash
python scripts/migrate_to_supabase_password_auth.py --apply --rotate-existing
```

O script guarda as senhas temporarias apenas em `local-secrets/supabase-password-auth-*.txt`, que esta ignorado pelo Git.
