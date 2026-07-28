# Alinhamento da base Google Sheets -> Supabase

Referencia analisada em 2026-07-28:

- `C:\Users\manyu\Downloads\CoursePlatformDB.xlsx`
- 25 abas encontradas no workbook.
- A aba `MediaContent` existe, mas sem cabecalho e sem dados no ficheiro exportado.
- A configuracao de midia usada atualmente pelo Apps Script continua em `Settings`, chave `MEDIA_CONFIG`, como JSON.

## Abas cobertas pela migracao

| Aba Google Sheets | Tabela Supabase | Estado |
| --- | --- | --- |
| Students | `courseplatform.students` | Coberta |
| Admins | `courseplatform.admins` | Coberta |
| Sessions | `courseplatform.sessions` | Coberta |
| Courses | `courseplatform.courses` | Coberta |
| Lessons | `courseplatform.lessons` | Coberta |
| LessonContent | `courseplatform.lesson_content` | Coberta |
| Questions | `courseplatform.questions` | Coberta |
| QuestionOptions | `courseplatform.question_options` | Coberta |
| Enrollments | `courseplatform.enrollments` | Coberta |
| Groups | `courseplatform.groups` | Coberta |
| GroupMembers | `courseplatform.group_members` | Coberta |
| LessonProgress | `courseplatform.lesson_progress` | Coberta |
| Attempts | `courseplatform.attempts` | Coberta |
| Answers | `courseplatform.answers` | Coberta |
| Files | `courseplatform.files` | Coberta |
| Reviews | `courseplatform.reviews` | Coberta |
| Certificates | `courseplatform.certificates` | Coberta |
| AuditLog | `courseplatform.audit_log` | Coberta |
| Settings | `courseplatform.settings` | Coberta |
| Lists | `courseplatform.lists` | Coberta |
| StudentImport | `courseplatform.student_import` | Coberta |
| StudentImportResults | `courseplatform.student_import_results` | Coberta |
| NewCredentials | `courseplatform.new_credentials` | Coberta |
| SchemaGuide | `courseplatform.schema_guide` | Coberta |
| MediaContent | `courseplatform.media_content` | Preparada, sem dados atuais |

## Cuidados de compatibilidade

- `studentId`, `publicStudentId`, `accessCode`, progresso, tentativas, revisoes e certificados sao preservados.
- `accessCode` continua migrado exatamente como esta no Sheets, para manter a autenticacao existente.
- Datas numericas vindas do Sheets/Excel sao convertidas para `timestamptz`.
- Campos booleanos como `active`, `isRequired`, `isCorrect`, `retryAuthorized` e `unlockNextLesson` sao convertidos para booleano real.
- `detailsJson` e `allowedEmails` sao guardados como `jsonb`.
- Linhas auxiliares sem ID proprio, como `StudentImport`, recebem um `row_id` deterministico baseado na aba e numero da linha.

## Observacao sobre MediaContent

Hoje a plataforma le e grava videos atraves da chave `MEDIA_CONFIG` na aba `Settings`. Por isso, a migracao ja preserva a midia atual via `courseplatform.settings`.

A tabela `courseplatform.media_content` fica preparada para uma evolucao futura, caso a midia passe a ser guardada em linhas independentes com campos como:

- `mediaId` ou `id`
- `courseId`
- `title`
- `url`
- `description`
- `visibility`
- `allowedEmails`
- `status`
- `sortOrder`
- `createdAt`
- `updatedAt`
