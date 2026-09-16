# Arquitetura atual da CoursePlatform

Data da linha de base: 12 de setembro de 2026. Commit de referência: `c1a8188`.

Atualização arquitetural preparada em 15 de setembro de 2026: catálogo, versões
publicadas, edições/turmas e matrículas foram separados por migração expansiva.
Esta atualização permanece local até validação e aplicação autorizada.

Na mesma data começou a Etapa 8: contratos comuns, o manifesto do dispatcher e
os fluxos completos de identidade, avaliações, submissões, certificados,
pagamentos, catálogo, matrículas, comunicação, chat, aprendizagem e
administração foram separados por domínio sem alterar a superfície de 115
ações.

Em 16 de setembro começou também uma superfície HTTP versionada em `/api/v1`.
Ela possui contratos Pydantic por domínio e reutiliza o dispatcher existente,
permitindo migração gradual sem criar uma segunda implementação das regras.
As primeiras leituras de catálogo, matrículas, aprendizagem e avaliações já
possuem rotas tipadas. O cliente utiliza essas rotas para curso, media pública,
lista de cursos, media autorizada, home, dashboard, aula e estado da tentativa,
com fallback controlado por operação para deploys anteriores.

## Âmbito

Este documento descreve o que existe no repositório. Não é a arquitetura-alvo e não confirma a configuração real do Supabase ou Vercel. Foram inspecionados código, SQL, frontend, testes e scripts locais; não foram consultados dados, credenciais ou logs de produção.

## Visão geral

```text
Browser do estudante/admin
        |
        | HTML/CSS/JavaScript + JSON por action ou rota tipada
        v
FastAPI / Vercel Python Function
  api/index.py -> backend.courseplatform.app
        |
        +-- /api/v1 -> api/* -> dispatch(action, payload)
        |
        +-- /api, /api/index -> dispatch(action, payload)
        v
backend/courseplatform/actions.py (adaptador compatível)
        |
        +------ contracts.py + serializers.py + domains/*
        |
        +------ psycopg síncrono ------> Supabase Postgres
        |
        +------ HTTPS -----------------> Supabase Storage
        |
        +------ SMTP/HTTP/Web Push ----> fornecedores de notificação
        |
        +------ ReportLab -------------> PDF A4 horizontal

Supabase Postgres -- trigger/policy --> Supabase Realtime --> Browser/chat
```

O sistema é um monólito em transição para módulos internos: frontend estático,
API e regras de negócio continuam no mesmo repositório. A maior parte das regras
e consultas ainda está em `backend/courseplatform/actions.py`; o registo das
ações, contratos comuns e os handlers de identidade, avaliações, submissões,
certificados, pagamentos, catálogo, matrículas, comunicação, chat,
aprendizagem e administração têm módulos próprios. Para compatibilidade,
`actions.py` continua a expor adaptadores finos que injetam as dependências
concretas no domínio em tempo de chamada.

## Pontos de entrada

### Deploy e aplicação

- `api/index.py` importa e expõe `backend.courseplatform.app:app`.
- `GET /`, `GET /api` e `GET /api/index` chamam o dispatcher. Sem `action` na raiz, `/` entrega `index.html`; nas rotas de API, o action padrão é `health`.
- `POST /`, `POST /api` e `POST /api/index` recebem JSON com `action` e respetivo payload.
- `/api/v1/auth/*`, `/api/v1/catalog/*`, `/api/v1/students/*` e
  `/api/v1/admin/*` compõem a superfície tipada. Nesta fase cobrem sessões,
  catálogo/media, cursos, media autorizada, home, dashboard, aula, estado da
  tentativa e listas de estudantes/staff, chamando os mesmos handlers do
  dispatcher legado.
- `GET /docs` e `GET /openapi.json` documentam apenas os contratos HTTP
  declarados; o dispatcher legado continua documentado neste ficheiro.

Os métodos `publicCourseConfig`, `publicMediaConfig`, `myCourses`, `mediaConfig`,
`studentHome`, `dashboard`, `getLesson` e `attemptStatus` em `public/api.js`
consomem essas rotas. Cada um repete a leitura pelo seu action apenas para
`404/405` que identifique uma rota ainda não instalada. Erros de domínio e
infraestrutura são devolvidos sem fallback, evitando duplicação de carga e
diagnósticos enganadores.
- `GET /api/certificates/{certificate_id}/pdf` gera o PDF. Aceita sessão de estudante ou sessão administrativa nos headers/query params tratados pela rota.
- `GET /api/files/{file_id}/content` entrega trabalhos após validar a sessão e a propriedade ou papel administrativo.
- `GET /api/certificate-requests/{request_id}/receipt` entrega comprovativos após validar estudante proprietário ou OWNER/ADMIN.
- `GET /{static_path:path}` entrega ficheiros estáticos e aliases `/admin`, `/verify` e `/connection-test`.

O backend procura assets primeiro em `public/` e depois em `backend/courseplatform/static/`. No deploy estático do Vercel, `public/` também é publicado diretamente.

### Frontend

- `public/index.html` + `public/app.js`: autenticação e área do estudante.
- `public/admin.html` + `public/admin.js`: autenticação e área administrativa.
- `public/api.js`: cliente para todas as ações JSON e download de certificados.
- `public/chat.js`: cliente de chat e integração Realtime.
- `public/verify.html` + `public/verify.js`: verificação pública de certificados.
- `public/config.js`: resolução da URL da API e configuração pública da aplicação.
- `public/sw.js` + `manifest.webmanifest`: PWA, notificações e service worker.
- `public/professional-certificate.js`: componente de pré-visualização do certificado.

A área do estudante usa rotas por hash. A sessão do estudante é guardada em `localStorage`; a sessão administrativa, em `sessionStorage`. O backend guarda apenas SHA-256 dos tokens opacos na tabela de sessões.

### Fonte dos assets

`public/` é a fonte canónica e única para alterações do frontend.
`backend/courseplatform/static/` é uma distribuição gerada pelo script
`scripts/sync_frontend.cjs`. O modo `--check` compara conjunto de ficheiros e
SHA-256 e falha se houver divergência. A paridade integral das árvores também é
protegida por teste unitário.

Os entrypoints existentes não mudaram. `admin.js` importa a paginação partilhada
de `public/admin/pagination.js`, `app.js` importa o parser de rotas de
`public/student/routes.js`, e `styles.css` importa os tokens de
`public/assets/css/tokens.css`.

## Superfície da API

O dispatcher regista **115 nomes de ação** através de nove manifestos de domínio
em `backend/courseplatform/domains/`. `actions.py` resolve esses nomes para os
handlers existentes e permanece o adaptador público durante a extração. Vários
nomes administrativos reutilizam o mesmo handler do chat;
`adminListPendingSubmissions` é alias de `adminListSubmissions`.

### Públicas ou de autenticação

- Estado/configuração: `health`, `publicCourseConfig`, `publicMediaConfig`.
- Certificados: `verifyCertificate`.
- Estudante: `login`, `recoverStudentAccess`, `completeStudentPasswordReset`.
- Administração: `adminLogin`, `recoverAdminAccess`.
- `logout`/`adminLogout` recebem uma sessão existente, mas devolvem sucesso mesmo sem token.

O fluxo de recuperação do estudante é público por necessidade funcional. `recoverStudentAccess` devolve sempre a mesma mensagem e cria um token de utilização única para contas ativas; `completeStudentPasswordReset` consome o token, altera o hash bcrypt e revoga as sessões na mesma transação. A entrega usa o email associado à conta e o SMTP do servidor.

### Sessão de estudante

- Área académica: `getDashboard`, `getStudentHome`, `getMyCourses`, `getMediaConfig`, `getLesson`.
- Perfil/identidade: `updateMyProfile`, `changeMyAccessCode`, `changeMyEmail`.
- Avaliações: `startAttempt`, `getAttemptStatus`, `saveAnswer`, `uploadFile`, `deleteUploadedFile`, `submitAttempt`.
- Notificações: `getMyNotifications`, `markNotificationRead`, `getPushConfiguration`, `subscribePush`, `unsubscribePush`.
- Telegram: `studentStartTelegramLink`, `studentConfirmTelegramLink`, `studentUnlinkTelegram`.
- Certificados: `getMyCertificate`, `getMyCertifications`, `requestParticipationCertificate`, `requestProfessionalCertificate`, `submitProfessionalCertificatePayment`, `recordCertificateDownload`.
- Chat: `getChatRealtimeConfiguration`, `getChatRooms`, `getChatContacts`, `startDirectChat`, `updatePresence`, `getChatMessages`, `sendChatMessage`, `editChatMessage`, `deleteChatMessage`, `markChatRoomRead`, `reportChatMessage`.

Os handlers chamam `student_context`/`student_context_with_conn`, validam sessão ativa e voltam a carregar o estudante ativo. Algumas operações também validam matrícula, acesso ao módulo e propriedade da tentativa/ficheiro/certificado.

### Staff: leitura e operação académica

Os papéis `OWNER`, `ADMIN` e `REVIEWER` podem usar:

- `adminMe`, `adminGetMediaConfig`, `adminGetPlatformStatistics`.
- `adminListCourses`, `adminGetCourseStructure`, `adminListGroups`, `adminListStudents`, `adminGetStudentDetails`, `adminListStaff`.
- `adminListSubmissions`, `adminListPendingSubmissions`, `adminGetSubmission`, `adminReviewSubmission`, `adminAuthorizeRetry`, `adminUpdateAttempt`.
- `adminListCertificateRequests`, `adminListCertificates`, `adminGetCertificateSettings`, `adminListCertificateSurveys`.
- `adminListNotifications`.
- Chat administrativo: `adminListChatRooms`, `adminGetChatRealtimeConfiguration`, `adminUpdatePresence`, `adminGetChatMessages`, `adminSendChatMessage`, `adminEditChatMessage`, `adminDeleteChatMessage`, `adminMarkChatRoomRead`.

No chat, staff ativo pode aceder a salas não diretas; a autorização concreta também depende do tipo da sala e da ação.

### OWNER e ADMIN: gestão

- Media e estudantes: `adminSaveMediaConfig`, `adminCreateStudent`, `adminChangeStudentEmail`, `adminSetStudentStatus`, `adminResetStudentAccessCode`, `adminRestoreCredentials`.
- Cursos e aprendizagem: `adminSaveCourse`, `adminSaveLesson`, `adminSaveLessonContent`, `adminCreateCourseVersion`, `adminPublishCourseVersion`, `adminSaveCourseOffering`, `adminEnrollStudentsInOffering`, `adminListCourseReconciliationIssues`, `adminSaveGroup`, `adminAssignStudentsToGroup`, `adminSetLessonAccess`, `adminManageLessonProgress`.
- Certificados: `adminSetCertificateStatus`, `adminRefreshCertificateFormat`, `adminDeleteCertificate`, `adminReviewCertificateRequest`, `adminDeleteCertificateRequest`, `adminSaveCertificateSettings`, `adminSaveCertificateSurvey`, `adminUploadCertificateAsset`, `adminUploadBrandLogo`.
- Notificações: `adminCreateNotification`, `adminSaveNotificationTemplate`, `adminResetNotificationTemplate`, `adminSaveWhatsAppConfiguration`, `adminSaveEmailConfiguration`, `adminSaveTelegramConfiguration`, `adminRetryNotificationDeliveries`.

### Apenas OWNER

- `adminSaveStaff`: cria/edita staff e respetivo papel.
- `adminSetStaffStatus`: ativa/desativa staff.

Esta classificação documenta verificações de papel encontradas nos handlers, mas não substitui testes de autorização por ação.

## Autenticação e autorização atuais

- Senhas de estudante e staff são verificadas por bcrypt via `pgcrypto`/`crypt` no Postgres.
- O sistema não usa Supabase Auth para login principal.
- Ao autenticar, a API devolve um token opaco. Apenas o SHA-256 é guardado em `courseplatform.sessions`.
- A validade padrão da sessão é controlada por `SESSION_HOURS`.
- A reposição de palavra-passe guarda apenas o hash do token e identificadores HMAC para limitação por email/origem. Pedidos e tentativas são limitados no Postgres; tokens expiram, são invalidados por um novo pedido e não podem ser reutilizados.
- Os sujeitos administrativos são guardados como `ADMIN:{admin_id}`.
- `student_context` exige estudante ativo; `admin_context` exige staff ativo e, quando indicado, um dos papéis permitidos.
- Regras de propriedade e acesso são implementadas sobretudo nas consultas/handlers Python.
- O cliente Realtime recebe JWT de curta duração assinado no backend e limitado por tópico/ator.

Pontos ainda desconhecidos: rate limiting/WAF externo, MFA, grants reais, policies efetivas no projeto Supabase e políticas de rotação/retensão das sessões.

## Persistência

### Postgres

`backend/courseplatform/db.py` abre ligações psycopg síncronas e desativa prepared statements automáticos para compatibilidade com transaction pooling do Supavisor. A API usa a URL Postgres diretamente.

A cadeia em `supabase/migrations/` termina com **46 tabelas** no esquema
`courseplatform`, incluindo o marcador operacional `schema_versions`:

- Identidade: `students`, `admins`, `sessions`, `student_password_resets`, `student_password_reset_attempts`, `new_credentials`.
- Catálogo e publicação: `courses`, `course_versions`, `course_offerings`, `lessons`, `lesson_content`, `media_content`.
- Avaliações: `questions`, `question_options`, `lesson_progress`, `attempts`, `answers`, `files`, `reviews`.
- Turmas: `groups`, `enrollments`, `group_members`, `migration_reconciliation_issues`.
- Chat: `chat_rooms`, `chat_messages`, `chat_reads`, `chat_message_receipts`, `chat_presence`, `chat_message_reports`.
- Notificações: `notifications`, `notification_deliveries`, `notification_channel_settings`, `notification_templates`, `push_subscriptions`, `telegram_link_tokens`, `notification_channel_state`.
- Certificação: `certificates`, `certificate_settings`, `certificate_requests`.
- Operação/importação: `audit_log`, `settings`, `lists`, `student_import`, `student_import_results`, `schema_guide`, `schema_versions`.

O esquema ativa RLS nas tabelas declaradas. A migração da role de runtime prepara
`courseplatform_runtime` (grupo sem login) e `courseplatform_api` (login) com
DML por tabela/operação e grants explícitos nas funções `pgcrypto` utilizadas
pela API. A role não recebe acesso automático a objetos futuros, `BYPASSRLS`,
DDL nem privilégios administrativos.
Até a troca controlada de `DATABASE_URL`, o ambiente publicado pode continuar a
usar a ligação anterior; isso deve ser confirmado por ambiente.

### Views públicas

`supabase/schema.sql` cria **32 views** no esquema `public`. Em geral espelham tabelas privadas com `select *`, incluindo estudantes, staff, sessões, questões, respostas, ficheiros e auditoria. `notification_channel_settings` expõe um subconjunto sem os segredos encriptados.

O SQL concede `SELECT` dessas views ao `service_role`; privilégios reais de `anon` e `authenticated` não foram consultados. A auditoria exige validação no ambiente antes de concluir se existe exposição.

### Esquemas divergentes e migrações

Os snapshots SQL não são iguais e nenhum deles é a fonte de migração:

- `supabase/schema.sql`: snapshot com 43 tabelas e 32 views.
- `backend/courseplatform/schema.sql`: snapshot legado com 42 tabelas e 34 views.
- `supabase/migrations/`: cadeia canónica com as 42 tabelas funcionais e `schema_versions`.

O DDL legado de preparação foi removido de `actions.py` e convertido em
migrações numeradas. As funções `prepare_*` e `ensure_*` fazem apenas consultas
de capacidades; a validação global compara `courseplatform.schema_versions`
com a versão esperada pelo backend. Novas alterações do banco passam
exclusivamente por `supabase/migrations/`. Os snapshots SQL são apenas material
de consulta e não são executados durante pedidos.

### Storage

O backend usa `SUPABASE_SECRET_KEY` exclusivamente no servidor, mantendo
`SUPABASE_SERVICE_ROLE_KEY` apenas como alternativa legada. Assets administrativos
usam `SUPABASE_CERTIFICATE_BUCKET`; trabalhos e comprovativos novos usam
`SUPABASE_SUBMISSION_BUCKET` e `SUPABASE_PAYMENT_RECEIPT_BUCKET`.

A migração `20260914103215_private_submission_storage.sql` cria os buckets privados e acrescenta bucket, caminho, checksum, tamanho e estado aos registos. A API autoriza cada leitura e suporta temporariamente Base64/HTTPS legado. O script `scripts/backfill_private_storage.py` copia os objetos históricos sem apagar a origem; a execução externa permanece pendente.

### Realtime

`supabase/chat_realtime.sql` cria:

- função `chat_realtime_topic_allowed` com `security definer` e `search_path` vazio;
- policy privada em `realtime.messages` para a role `authenticated`;
- trigger que publica mudanças mínimas de mensagens nos tópicos de sala/inbox.

O contrato completo também está na migração
`20260913122000_materialize_chat_realtime.sql`. A instalação e alteração do
Realtime pertencem a migrações ou operações administrativas autorizadas.

## Fluxos principais

### Login e sessão

```text
Browser -> action login/adminLogin -> bcrypt no Postgres
        <- token opaco
Browser guarda token -> action autenticada -> hash do token
        -> valida sessions + sujeito ativo -> regra/consulta -> JSON
```

### Recuperação da palavra-passe do estudante

```text
Browser -> recoverStudentAccess(email) -> resposta genérica
        -> Postgres guarda apenas hash/HMAC e limites de tentativa
        -> SMTP envia link com token no fragmento da URL
Browser -> completeStudentPasswordReset(token, nova senha)
        -> lock + valida expiração/uso -> bcrypt + revogação de sessões
        -> consumo do token + auditoria + notificação interna
```

### Aprendizagem e submissão

```text
Curso de catálogo -> versão publicada imutável -> edição/turma -> matrícula
  -> lesson_progress -> startAttempt -> attempts
  -> saveAnswer / uploadFile -> submitAttempt
  -> adminReviewSubmission -> reviews + estado da tentativa/progresso
  -> possível autorização de reenvio -> nova tentativa preservando histórico
```

### Certificação

```text
Conclusão da matrícula -> elegibilidade/política do curso
  -> certificado de participação ou pedido profissional
  -> inquérito/pagamento quando aplicável
  -> revisão administrativa -> emissão/snapshot
  -> preview/PDF/verificação -> controlo de estado e downloads
```

### Notificações

```text
Ação académica/admin -> notifications (fonte interna)
  -> notification_deliveries por canal
  -> FastAPI BackgroundTasks ou chamada direta
  -> claim com SKIP LOCKED -> pool local até 5 envios
  -> SENT/FAILED; retry administrativo disponível
```

Não foi encontrado um worker/scheduler independente no repositório. Campanhas maiores podem permanecer na fila até nova execução/retry.

## Configuração

Os nomes e valores-modelo estão em `.env.example`. Categorias:

- Postgres: URLs completas ou componentes `POSTGRES_*`.
- Aplicação: curso padrão, duração das sessões, timeout/retries, CORS e versão.
- Supabase: URL, chave de serviço, bucket, chave publicável e segredo Realtime/JWT.
- Recuperação administrativa.
- WhatsApp, SMTP, Telegram e Web Push.
- Variáveis exclusivas de QA: `SMOKE_*`, `PREVIEW_URL`, `PLAYWRIGHT_MODULE`, `CHROME_PATH`.

Valores não foram lidos nem registados nesta linha de base.

## Testes atuais

Existem 10 módulos Python e 96 testes na linha de base. Cobrem:

- branding e validação de imagens;
- composição e rota PDF dos certificados;
- chat e token Realtime;
- compatibilidade da ligação com pooler;
- canais de notificações e proteção dos segredos;
- política de certificados de participação;
- reenvio/revisão de submissões;
- Web Push e WhatsApp.

São maioritariamente unitários, com mocks de banco e fornecedores. A rota PDF usa `TestClient`. Não constituem testes completos com Postgres/Supabase real.

Scripts de browser com Playwright cobrem certificados, reenvio e política de participação usando dados sintéticos. `scripts/smoke_test_platform.py` usa a base configurada, pode ler `local-secrets` e faz login/logout; deve ficar restrito a staging.

## Processos de desenvolvimento e deploy observados

- Dependências de runtime estavam fixadas em `requirements.txt`.
- A linha de base não possuía `requirements-dev.txt`, `package.json`, `.python-version`, README ou pipeline em `.github/`.
- Não foi encontrado um diretório de migrações versionadas.
- O deploy esperado usa a deteção de `api/index.py` e `public/` no Vercel, sem `vercel.json`.

Configurações externas de branch protection, Vercel, Supabase, backups e CI não foram inspecionadas.

## Fonte de verdade atual por domínio

| Domínio | Fonte atual | Observação |
| --- | --- | --- |
| Estudantes, cursos e progresso | `courseplatform.*` no Postgres | Backend Python aplica a maior parte da autorização |
| Senhas e sessões | Postgres | Autenticação própria, não Supabase Auth |
| Trabalhos/comprovativos | Storage privado + metadados no Postgres | Base64/URL legada permanece apenas durante o backfill compatível |
| Assets de certificados | Configuração no Postgres; cópia opcional no Storage | Upload usa service role no servidor |
| Certificado emitido | `certificates` + snapshot JSON | PDF é gerado a pedido |
| Notificação interna | `notifications` | Fonte principal do histórico de comunicação |
| Entrega por canal | `notification_deliveries` | Claims/retries na base; execução ligada à API |
| Chat persistente | Tabelas de chat no Postgres | Realtime transporta invalidações/eventos |
| Frontend publicado | `public/` no Vercel | Backend possui fallback divergente em `static/` |
| Esquema | Dois snapshots divergentes + migrações versionadas | Os pedidos validam capacidades; a consolidação dos snapshots permanece pendente |

## Limites desta verificação

Permanece por confirmar em staging/produção:

- grants, policies RLS e policies de Storage realmente aplicados;
- tabelas/colunas existentes e versão efetiva do esquema;
- volumes, índices utilizados e planos de consulta;
- capacidade, latência, conexões e custos;
- políticas de backup, retenção e restauro;
- WAF/rate limiting, headers de segurança, logs e alertas;
- configuração de SMTP, WhatsApp, Telegram, Web Push e Realtime;
- integridade/paridade dos dados migrados;
- acessibilidade e renderização visual completa em dispositivos reais.

## Próxima etapa

Depois de aprovada esta linha de base, executar separadamente a Etapa 1: recuperação segura de acesso. Não combinar essa correção com a proteção do gabarito ou com alterações de esquema não relacionadas.
