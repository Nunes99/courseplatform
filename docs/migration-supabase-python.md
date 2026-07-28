# Migracao para Supabase + API Python

Este plano prepara a migracao sem destruir o Apps Script atual. O frontend pode continuar usando `config.js` com a URL do Apps Script ate o momento do corte.

## Objetivo

- Migrar todos os dados do Google Sheets para Supabase/Postgres.
- Preservar `studentId`, `publicStudentId`, progresso, submissões, certificados, grupos e cursos.
- Preservar `accessCode` ja hasheado e `sessionToken` ja hasheado.
- Usar uma API Python com o mesmo contrato atual: `GET ?action=...` e `POST { action: ... }`.

## Arquivos adicionados

- `supabase/schema.sql`: schema Postgres compatível com as abas atuais.
- `api/index.py`: entrada Python para Vercel.
- `backend/courseplatform/*`: API FastAPI/Postgres.
- `scripts/migrate_sheets_to_supabase.py`: migracao Google Sheets -> Supabase.
- `.env.example`: variáveis necessárias para dev/deploy.

## Variáveis críticas

No Apps Script, copie de `Script Properties`:

- `PASSWORD_PEPPER`
- `ADMIN_MASTER_KEY_HASH`

Essas variáveis precisam ser iguais no Vercel. Sem o mesmo `PASSWORD_PEPPER`, os códigos atuais dos estudantes e tokens ativos não serão validados.

## Passos de migracao

1. Criar projeto no Supabase.
2. Abrir SQL Editor e executar `supabase/schema.sql`.
3. Criar uma Service Account no Google Cloud com acesso de leitura ao Google Sheets.
4. Partilhar a planilha atual com o email da Service Account.
5. Instalar dependências localmente:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

6. Rodar ensaio sem escrever:

```bash
python scripts/migrate_sheets_to_supabase.py --dry-run
```

7. Rodar migracao real:

```bash
python scripts/migrate_sheets_to_supabase.py
```

8. Configurar variáveis no Vercel:

- `DATABASE_URL`
- `PASSWORD_PEPPER`
- `ADMIN_MASTER_KEY_HASH`
- `DEFAULT_COURSE_ID`
- `SESSION_HOURS`
- `CORS_ORIGINS`

9. Fazer deploy pelo GitHub/Vercel.
10. Testar:

```text
https://SEU-PROJETO.vercel.app/api?action=health
```

11. Quando estiver validado, alterar `config.js`:

```js
apiUrl: 'https://SEU-PROJETO.vercel.app/api'
```

## Corte seguro

Recomendacao:

1. Fazer migracao em modo leitura.
2. Testar login de estudante e admin.
3. Testar dashboard, cursos, estudantes e submissões.
4. Fazer congelamento curto no Google Sheets.
5. Rodar migracao final.
6. Trocar `apiUrl`.
7. Manter Apps Script publicado como rollback temporario.

## Estado atual da API Python

Ja preparado:

- `health`
- `publicCourseConfig`
- `publicMediaConfig`
- `verifyCertificate`
- `login`
- `logout`
- `adminLogin`
- `adminLogout`
- `adminMe`
- `getDashboard`
- `getMyCourses`
- `adminListCourses`
- `adminGetCourseStructure`
- `adminListGroups`
- `adminListStudents`

Ainda deve ser portado antes do corte total:

- tentativas e submissões completas
- upload de ficheiros
- revisões administrativas
- criacao/edicao de estudantes, cursos, modulos, grupos e staff
- media save/admin management

Enquanto essas ações não forem portadas, o Apps Script atual continua sendo a API de produção.
