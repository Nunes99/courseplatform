# Matriz inicial de controlo de acesso

Data da linha de base: 12 de setembro de 2026.

## Como ler

Esta é a **política esperada**, derivada dos handlers e do produto atual. Não prova que os grants, RLS e Storage aplicados em produção correspondem à matriz.

- **Público**: operação sem sessão, com resposta de dados mínimos.
- **Próprio**: apenas dados pertencentes ao estudante e ao seu contexto autorizado.
- **Âmbito**: acesso limitado a cursos, grupos, submissões ou tarefas atribuídas ao membro de staff. A implementação atual aplica papel, mas ainda não modela todos estes âmbitos finos.
- **Gestão**: criar/editar/bloquear de acordo com a operação.
- **Não**: acesso deve ser recusado pelo backend, mesmo que o botão esteja oculto.

Papéis administrativos atuais: `REVIEWER`, `ADMIN` e `OWNER`. O `OWNER` é o único papel que gere contas de staff.

## Matriz funcional

| Recurso/operação | Anónimo | Estudante | REVIEWER | ADMIN | OWNER |
| --- | --- | --- | --- | --- | --- |
| Health público mínimo | Público | Público | Público | Público | Público |
| Configuração pública de curso/media | Público | Público | Público | Público | Público |
| Login | Público | Público | Público | Público | Público |
| Recuperação de estudante | Pedir link sem enumeração e concluir com token válido | Igual ao público | Igual ao público | Igual ao público | Igual ao público |
| Recuperação administrativa | Iniciar com mecanismo protegido | Não | Própria conta | Própria conta | Própria conta/emergência auditada |
| Verificação de certificado | Dados públicos mínimos pelo código | Igual ao público | Igual ao público | Igual ao público | Igual ao público |
| Perfil do estudante | Não | Próprio: ler/editar | Leitura no âmbito | Leitura/gestão | Leitura/gestão |
| Email/senha do estudante | Não | Alterar a própria com comprovação | Não | Recuperar/alterar conforme fluxo auditado | Igual a ADMIN |
| Lista de estudantes | Não | Não | Leitura no âmbito | Leitura/gestão | Leitura/gestão |
| Estado/matrícula do estudante | Não | Ler próprio | Leitura no âmbito | Gestão | Gestão |
| Cursos públicos | Apenas publicados | Apenas atribuídos/publicados | Leitura | Gestão | Gestão |
| Estrutura e módulos | Apenas conteúdo público | Conforme matrícula/acesso | Leitura | Gestão | Gestão |
| Enunciado e opções sem gabarito | Não | Próprios, conforme matrícula/acesso | Leitura no âmbito | Gestão | Gestão |
| Gabarito antes da entrega | Não | Não | No âmbito de revisão | Sim | Sim |
| Gabarito após a entrega | Não | Conforme política de feedback | No âmbito de revisão | Sim | Sim |
| Pontuação interna por questão | Não | Não | No âmbito de revisão | Sim | Sim |
| Snapshot histórico da avaliação | Não | Apenas representação filtrada da própria tentativa | Leitura integral no âmbito | Leitura integral | Leitura integral |
| Progresso e notas | Não | Próprios | Leitura/atualização no âmbito | Gestão | Gestão |
| Iniciar tentativa/responder | Não | Próprio e dentro das regras | Não | Não | Não |
| Upload/remover trabalho | Não | Própria tentativa editável | Não | Gestão pela revisão, se prevista | Gestão pela revisão, se prevista |
| Ver submissões | Não | Próprias | No âmbito de revisão | Todas no âmbito administrativo | Todas |
| Rever/reabrir submissão | Não | Não | No âmbito de revisão | Gestão | Gestão |
| Media/vídeos restritos | Apenas públicos | Conforme email/matrícula/regra | Leitura | Gestão | Gestão |
| Notificações internas | Não | Próprias | Visibilidade administrativa | Gestão | Gestão |
| Configurar canais/templates | Não | Preferências próprias | Não | Gestão | Gestão |
| Repetir entregas falhadas | Não | Não | Não | Gestão | Gestão |
| Chat de curso/grupo/comunidade | Não | Salas autorizadas | Salas administrativas não diretas | Salas administrativas não diretas | Salas administrativas não diretas |
| Chat direto entre estudantes | Não | Apenas participante | Não por padrão | Não por padrão | Não por padrão |
| Chat de suporte | Não | Próprio | Atendimento | Atendimento | Atendimento |
| Editar/apagar mensagem | Não | Própria e dentro das regras | Própria/admin conforme regra | Própria/admin conforme regra | Própria/admin conforme regra |
| Certificados do estudante | Verificação mínima | Próprios e autorizados | Leitura administrativa | Gestão | Gestão |
| Pedido/pagamento de certificado | Não | Próprio | Leitura | Rever/gerir | Rever/gerir |
| Configuração de certificado | Não | Não | Leitura | Gestão | Gestão |
| Inquéritos: configuração | Não | Não | Leitura | Gestão | Gestão |
| Inquéritos: respostas | Não | Próprias quando necessário | Leitura administrativa | Leitura/relatório | Leitura/relatório |
| Assets de certificado/branding | Apenas os explicitamente públicos | Apenas os necessários ao documento | Leitura administrativa | Upload/gestão | Upload/gestão |
| Lista de staff | Não | Não | Leitura atual | Leitura atual | Leitura/gestão |
| Criar/editar/desativar staff | Não | Não | Não | Não | Gestão exclusiva |
| Auditoria | Não | Não | Apenas se for criada permissão específica | Consulta administrativa prevista | Consulta integral |
| Configuração/segredos da plataforma | Não | Não | Não | Estado sem valor secreto | Gestão sem retorno de segredo |

## Mapeamento dos handlers atuais

### Sem sessão ativa

`health`, `publicCourseConfig`, `publicMediaConfig`, `verifyCertificate`, `login`, `recoverStudentAccess`, `adminLogin` e `recoverAdminAccess` são alcançáveis sem sessão prévia. O facto de uma ação ser pública não autoriza devolver dados sensíveis.

`recoverStudentAccess` não cumpre ainda a política da matriz: aceita email + ID público e devolve uma senha temporária. Esta discrepância é o achado A01 da auditoria.

### Estudante autenticado

Os handlers usam `student_context` ou `student_context_with_conn`. Ações principais:

- Perfil: `updateMyProfile`, `changeMyAccessCode`, `changeMyEmail`.
- Cursos: `getDashboard`, `getStudentHome`, `getMyCourses`, `getMediaConfig`, `getLesson`.
- Avaliações: `startAttempt`, `getAttemptStatus`, `saveAnswer`, `uploadFile`, `deleteUploadedFile`, `submitAttempt`.
- Certificados: `getMyCertificate`, `getMyCertifications`, pedidos, pagamento e registo de download.
- Comunicação: notificações, Push, Telegram e chat.

`getLesson` usa o contrato de estudante e omite gabarito, explicações, pesos e marcas de correção. `getAttemptStatus` aplica a política congelada na tentativa e só divulga os campos autorizados no momento configurado. A correção da Etapa 2 está documentada em [assessment-feedback-policy.md](assessment-feedback-policy.md).

### Todos os papéis de staff ativos

Leitura administrativa e revisão usam `admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})`. Atualmente isto inclui estatísticas, cursos, estrutura, grupos, estudantes, staff, submissões, revisão/reabertura/alteração de tentativas, listas/configuração de certificados em leitura, inquéritos em leitura, notificações e chat não direto.

Limitação conhecida: a autorização é sobretudo por papel global; a noção de “revisor apenas do curso/grupo atribuído” ainda não está modelada de forma consistente. Portanto “âmbito” na matriz é um objetivo a validar/implementar gradualmente.

### ADMIN e OWNER

Usam `admin_context(payload, {"OWNER", "ADMIN"})` para gerir estudantes, cursos, módulos, grupos, acessos/progresso, media, certificados, pedidos, inquéritos e notificações/configurações.

### Apenas OWNER

`adminSaveStaff` e `adminSetStaffStatus` exigem `OWNER`.

## Regras de dados

Estas regras devem ser testadas no backend:

1. Um estudante nunca escolhe `student_id` para ler ou alterar um recurso próprio; a identidade vem da sessão.
2. Toda tentativa, resposta e ficheiro deve pertencer ao estudante da sessão e a uma matrícula/acesso válidos.
3. Acesso ao curso não implica automaticamente acesso a todos os módulos, respostas ou ficheiros.
4. `REVIEWER` não deve alterar estudantes, cursos, certificados ou configurações fora das tarefas explicitamente autorizadas.
5. Alterar papel/estado de staff deve revogar sessões incompatíveis e ficar auditado.
6. Certificado bloqueado/revogado não pode ser baixado por URL antiga; a verificação pública deve mostrar apenas estado e dados mínimos.
7. Pagamento aprovado não substitui conclusão académica; conclusão não substitui autorização de download quando a política exige aprovação.
8. Segredos de SMTP, bots, VAPID e Supabase nunca entram em DTOs, logs ou auditoria.
9. `service_role` é exclusivo do servidor e não constitui um papel de utilizador.
10. O ID público `STU-00000` identifica; não autentica.

## Banco, views e Storage

### Estado verificado em 13 de setembro de 2026

- As 42 tabelas `courseplatform.*` têm RLS ativa e não têm policies; sem grants,
  isto produz negação por defeito para clientes.
- Em produção, `anon` e `authenticated` não têm acesso direto às tabelas internas
  nem às 32 views `public.*` de compatibilidade.
- A migração da Etapa 3 foi aplicada em 13 de setembro de 2026; todas as views
  preservadas usam `security_invoker`.
- `service_role` tem acesso total às tabelas internas e deve permanecer exclusiva
  do servidor; nas views de compatibilidade será limitada a SELECT.
- O Realtime tem policy para `authenticated` e valida tópicos com claims assinadas pelo backend.
- Não existem buckets nem policies de Storage no projeto verificado.
- A API liga diretamente ao Postgres e aplica a maioria das regras no Python.
  A migração preparada substitui a ligação administrativa por
  `courseplatform_api`, membro de `courseplatform_runtime`, sem `BYPASSRLS`, DDL
  ou privilégios de gestão de roles. A troca de credenciais ainda exige
  validação e execução controlada por ambiente.

### Verificações obrigatórias em staging/produção

- Role efetiva usada por `DATABASE_URL` e capacidade de ignorar RLS.
- Grants explícitos e herdados de `anon`, `authenticated`, `service_role` e `public`.
- Dono e modo `security_invoker`/`security_definer` de cada view/função.
- Policies efetivas em todas as tabelas expostas e `storage.objects`.
- Buckets públicos/privados, listagem, upload, update e delete.
- Ausência de service key, JWT secret e credenciais Postgres nos bundles frontend.

Alterações futuras devem repetir o inventário de dependências e usar migrações versionadas.

## Casos de teste mínimos por papel

| Caso | Resultado esperado |
| --- | --- |
| Anónimo consulta perfil, lista ou ficheiro | `401/403` ou resposta pública mínima definida |
| Estudante A usa ID do estudante B | Recusado em perfil, tentativa, ficheiro, mensagem e certificado |
| Estudante inspeciona JSON da aula | Sem resposta correta antes da política permitir |
| REVIEWER tenta criar staff/curso | Recusado |
| REVIEWER revê submissão atribuída | Permitido e auditado |
| REVIEWER revê curso fora do âmbito futuro | Recusado |
| ADMIN tenta promover/desativar OWNER | Recusado |
| OWNER altera staff | Permitido, auditado e sessões revistas |
| URL de ficheiro privado sem sessão | Recusada/expirada |
| Chave pública Supabase consulta view sensível | Recusado |
| Service role aparece no frontend/log | Teste/release falha |

## Pontos ainda não verificados

- Testes pós-endurecimento com utilizadores sintéticos numa branch/staging isolada.
- Confirmação por SQL da desativação já efetuada dos defaults geridos de
  autoexposição em **Integrations > Data API**.
- Aplicação da migração da role mínima, ativação segura do login e confirmação
  de que cada ambiente Vercel usa `courseplatform_api` em vez de `postgres`.
- Políticas de Storage após a criação do bucket privado.
- WAF, rate limiting, CAPTCHA e proteção contra enumeração.
- MFA e SSO para staff.
- Atribuição de revisores a cursos/grupos.
- Gestão de consentimento/retensão conforme requisitos legais aplicáveis.
- Revogação de todas as formas de acesso após mudança de papel, email ou estado.

Esta matriz deve ser atualizada sempre que um papel, ação ou recurso for adicionado.
