# Migracao para Supabase + API Python

Este documento descreve a arquitetura atual da plataforma: Supabase como base de dados e API Python como backend.

## Objetivo

- Usar Supabase/Postgres como fonte ativa dos dados.
- Usar a API Python com o mesmo contrato do frontend: `GET ?action=...` e `POST { action: ... }`.
- Preservar estudantes, cursos, grupos, modulos, progresso, submisssoes, revisoes e historico.
- Usar segredos proprios da API Python para autenticacao.

## Arquivos principais

- `supabase/schema.sql`: schema Postgres da plataforma.
- `api/index.py`: entrada Python para Vercel.
- `backend/courseplatform/*`: API FastAPI/Postgres.
- `scripts/migrate_sheets_to_supabase.py`: utilitario de migracao/importacao historica.
- `.env.example`: variaveis necessarias para desenvolvimento/deploy.
- `docs/database-alignment.md`: mapa das abas exportadas para tabelas Supabase.

## Variaveis criticas

Configure no Vercel:

- `DATABASE_URL`
- `DEFAULT_COURSE_ID`
- `SESSION_HOURS`
- `DB_CONNECT_TIMEOUT`
- `DB_CONNECT_RETRIES`
- `CORS_ORIGINS`

A autenticacao usa `password_hash` bcrypt por estudante/admin no Supabase/Postgres. Nao ha dependencia de `PASSWORD_PEPPER` nem de chave master administrativa global.

## Validacao

Validar ficheiro Excel exportado, sem escrever no Supabase:

```bash
python scripts/migrate_sheets_to_supabase.py --xlsx "C:\Users\manyu\Downloads\CoursePlatformDB.xlsx" --validate-only
```

Testar escrita com rollback:

```bash
python scripts/migrate_sheets_to_supabase.py --xlsx "C:\Users\manyu\Downloads\CoursePlatformDB.xlsx" --dry-run
```

Migracao real:

```bash
python scripts/migrate_sheets_to_supabase.py --xlsx "C:\Users\manyu\Downloads\CoursePlatformDB.xlsx"
```

Health check:

```text
https://courseplatform-mauve.vercel.app/api?action=health
```

Resultado esperado:

```json
{
  "database": true,
  "databaseConfigured": true,
  "databaseError": "",
  "authConfigured": true
}
```

## Estado da API Python

Acoes publicas e estudante:

- `health`
- `publicCourseConfig`
- `publicMediaConfig`
- `verifyCertificate`
- `login`
- `logout`
- `getDashboard`
- `getMyCourses`
- `getLesson`
- `getAttemptStatus`
- `getMediaConfig`
- `updateMyProfile`
- `changeMyAccessCode`
- `startAttempt`
- `saveAnswer`
- `uploadFile`
- `deleteUploadedFile`
- `submitAttempt`
- `getMyCertificate`

Acoes administrativas:

- `adminLogin`
- `adminLogout`
- `adminMe`
- `adminListStaff`
- `adminSaveStaff`
- `adminSetStaffStatus`
- `adminListCourses`
- `adminGetCourseStructure`
- `adminSaveCourse`
- `adminSaveLesson`
- `adminSaveLessonContent`
- `adminListGroups`
- `adminSaveGroup`
- `adminAssignStudentsToGroup`
- `adminListStudents`
- `adminCreateStudent`
- `adminSetStudentStatus`
- `adminResetStudentAccessCode`
- `adminListSubmissions`
- `adminListPendingSubmissions`
- `adminGetSubmission`
- `adminReviewSubmission`
- `adminAuthorizeRetry`
- `adminSetLessonAccess`
- `adminGetMediaConfig`
- `adminSaveMediaConfig`

## Corte operacional

1. Garantir `DATABASE_URL`, `DEFAULT_COURSE_ID`, `SESSION_HOURS`, `DB_CONNECT_TIMEOUT`, `DB_CONNECT_RETRIES` e `CORS_ORIGINS` no Vercel.
2. Fazer deploy.
3. Confirmar `health` com `database: true` e `authConfigured: true`.
4. Testar login de estudante.
5. Testar login admin.
6. Testar dashboard, cursos, modulos, submisssoes e media.

Depois disso, a operacao normal fica concentrada em Supabase + API Python.
