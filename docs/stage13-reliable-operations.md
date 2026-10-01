# Etapa 13 - Operacao confiavel da LMS

## Estado desta entrega

Implementado localmente e ainda nao aplicado externamente:

- fila `courseplatform.operational_jobs` com payload cifrado, idempotencia,
  claim com `FOR UPDATE SKIP LOCKED`, lease, retries exponenciais e estado `DEAD`;
- cadastro e recuperacao de palavra-passe deixam de depender de
  `BackgroundTasks` do processo serverless;
- executor protegido `POST /api/internal/jobs/run`;
- metricas protegidas em `GET /health/metrics`;
- logs JSON com `request_id`, metodo, caminho, estado e duracao;
- CI e smoke checks nao destrutivos;
- runbooks iniciais de backup, rollback e incidentes.

A migracao, o agendador, os alertas externos e o ensaio real de restauracao
continuam dependentes de autorizacao e de um ambiente externo seguro.

## Inventario operacional

| Fluxo | Estado anterior | Estado nesta etapa | Dependencia |
| --- | --- | --- | --- |
| Email de confirmacao | execucao ligada ao pedido | job cifrado e duravel | Postgres, SMTP, agendador |
| Email de recuperacao | `BackgroundTasks` | job cifrado e duravel | Postgres, SMTP, agendador |
| Notificacoes multicanal | tabela duravel, disparo oportunista | varrida em cada ciclo do worker | SMTP, Meta, Telegram, Web Push |
| Telegram linking | polling invocado pela aplicacao | permanece polling; candidato a job dedicado | Telegram API |
| PDF de certificado | gerado no pedido | permanece sincrono; medir antes de extrair | CPU, ReportLab, imagens |
| Upload/download privado | HTTP sincrono | permanece sincrono e limitado | Supabase Storage |
| Realtime/chat | tokens e publicacao Supabase | sem alteracao | Supabase Realtime |

Dependencias criticas: Postgres/Supavisor, Storage, SMTP, WhatsApp Cloud API,
Telegram Bot API, Web Push/VAPID, Realtime, Vercel e DNS. Segredos ficam apenas
no runtime do servidor.

## Aplicacao e agendamento

1. Aplicar `20261001120000_add_durable_operational_jobs.sql` primeiro.
2. Configurar `NOTIFICATION_CONFIG_ENCRYPTION_KEY` e `JOB_RUNNER_SECRET` com
   valores independentes de pelo menos 32 bytes.
3. Fazer deploy e confirmar `GET /health/ready`.
4. Configurar um agendador a cada minuto para `POST /api/internal/jobs/run`,
   usando `Authorization: Bearer <JOB_RUNNER_SECRET>`.
5. Confirmar `GET /health/metrics` com o mesmo header.

O endpoint devolve somente contagens. Nunca envie o segredo em query string. Um
segundo worker pode executar em paralelo: o claim transacional impede que ambos
obtenham o mesmo job. Jobs abandonados regressam a processamento quando a lease
de dois minutos expira.

## Metricas e alertas

Metricas minimas:

- `pendingJobs`, `processingJobs`, `deadJobs` e `overdueJobs`;
- `failedNotifications` depois do limite atual de tentativas;
- taxa HTTP 5xx e p95/p99 por rota a partir dos logs `http_request_completed`;
- falhas por provedor via `notification_channel_cycle_failed`;
- saturacao de ligacoes no painel Supabase;
- latencia e erros de Storage, PDF e Realtime nos logs da plataforma.

Alertar imediatamente quando `deadJobs > 0`, `overdueJobs > 0`, readiness falhar
por dois ciclos ou a taxa de 5xx ultrapassar o limite operacional acordado. Esta
entrega emite o evento `operational_alert`; a integracao com o destino de alerta
da equipa ainda deve ser configurada no provedor de observabilidade.

## SLO, RPO e RTO iniciais

Valores provisórios, a validar com negocio e por ensaio medido:

- disponibilidade mensal alvo: 99,5%;
- RPO da base: 24 horas enquanto depender de backup diario;
- RPO de Storage: 24 horas mediante copia/exportacao separada;
- RTO alvo: 4 horas para restaurar base, objetos e configuracao;
- notificacao operacional: reconhecer incidente critico em 30 minutos.

Nao declarar estes objetivos atingidos antes de medir restauracao e resposta.

## Backup e restauracao

O backup do Postgres nao inclui os objetos do Supabase Storage. Manter inventario
e copia separados para os buckets privados de submissoes, comprovativos e ativos
de certificados. Guardar tambem, num cofre, configuracao de runtime, lista de
variaveis por nome e procedimento de recriacao da role `courseplatform_api`.

Ensaio seguro trimestral:

1. Criar projeto isolado e vazio, sem URLs ou chaves de producao.
2. Restaurar o backup Postgres e aplicar apenas migracoes posteriores.
3. Restaurar os objetos de Storage preservando bucket e caminho.
4. Configurar chaves sintéticas e SMTP capturador, nunca provedores reais.
5. Validar contagens, chaves estrangeiras, checksums de amostra e downloads.
6. Executar a suite, o smoke test e os fluxos login, curso, submissao e certificado.
7. Medir tempo total e perda maxima de dados; comparar com RPO/RTO.
8. Destruir o ambiente isolado depois de guardar evidencias sem dados pessoais.

O ensaio desta entrega nao foi executado porque nao existe autorizacao para criar
ou restaurar um ambiente externo isolado.

## Rollback

Se o deploy falhar depois da migracao, reverter primeiro a aplicacao. A tabela
nova e expansiva pode permanecer sem afetar fluxos antigos. Nao apagar jobs com
tokens ainda validos. Para voltar temporariamente ao envio anterior seria
necessario um release de compatibilidade explicitamente revisto; nao executar
DDL de rollback durante pedidos.

## Resposta a incidentes

1. Classificar impacto: autenticacao, aprendizagem, submissao, pagamento ou dados.
2. Registar inicio, responsavel, versao, `request_id` e sintomas sem PII.
3. Conter: pausar worker se houver duplicacao; manter fila se o provedor falhar.
4. Diagnosticar com readiness, metricas protegidas e logs estruturados.
5. Recuperar por rollback da aplicacao ou restauracao aprovada.
6. Validar fluxos criticos e monitorizar pelo menos dois ciclos completos.
7. Produzir analise sem culpabilizacao, causa raiz e acoes com prazo.
