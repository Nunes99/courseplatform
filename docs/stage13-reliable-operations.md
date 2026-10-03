# Etapa 13 - Operacao confiavel da LMS

## Estado desta entrega

Implementado e validado em producao em 3 de outubro de 2026:

- fila `courseplatform.operational_jobs` com payload cifrado, idempotencia,
  claim com `FOR UPDATE SKIP LOCKED`, lease, retries exponenciais e estado `DEAD`;
- cadastro e recuperacao de palavra-passe deixam de depender de
  `BackgroundTasks` do processo serverless;
- executor protegido `POST /api/internal/jobs/run`;
- metricas protegidas em `GET /health/metrics`;
- logs JSON com `request_id`, metodo, caminho, estado e duracao;
- CI e smoke checks nao destrutivos;
- runbooks iniciais de backup, rollback e incidentes;
- agendador Supabase Cron a cada minuto, com URL e bearer guardados no Vault;
- alertas operacionais por SMTP para proprietarios ativos, com deduplicacao,
  lease e intervalo minimo de 30 minutos;
- monitor externo GitHub Actions a cada cinco minutos para disponibilidade,
  respostas 5xx sinteticas, latencia e utilizacao das ligacoes Postgres;
- ensaio local de migracao, dump e restauracao num PostgreSQL temporario isolado.

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

1. Aplicar `20261001120000_add_durable_operational_jobs.sql` e
   `20261003060000_add_operational_alert_delivery.sql`.
2. Configurar `NOTIFICATION_CONFIG_ENCRYPTION_KEY` e `JOB_RUNNER_SECRET` com
   valores independentes de pelo menos 32 bytes.
3. Fazer deploy e confirmar `GET /health/ready`.
4. Guardar `courseplatform_platform_url` e
   `courseplatform_job_runner_secret` no Supabase Vault e aplicar
   `20261003120000_schedule_operational_worker.sql`. O job chama a cada minuto
   `POST /api/internal/jobs/run` com o bearer protegido.
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

Quando `deadJobs > 0`, `overdueJobs > 0` ou `failedNotifications > 0`, o worker
emite o evento estruturado `operational_alert` e envia um email aos utilizadores
ativos com papel `OWNER`, `ADMIN` ou `ADMINISTRATOR`. O estado persistente evita
duplicacao concorrente e repete o aviso no maximo uma vez a cada 30 minutos para
o mesmo incidente. A taxa agregada de 5xx e a saturacao do Supavisor ainda
poderao ser ligadas a um provedor dedicado quando houver um destino contratado.

O workflow `production-monitor.yml` executa fora da Vercel, a cada cinco
minutos. Ele valida liveness, readiness, pagina inicial e metricas protegidas,
falha acima de 2500 ms ou 80% de utilizacao das ligacoes e abre um unico issue
operacional no GitHub. Quando o servico recupera, o mesmo issue e encerrado. O
workflow exige o secret de repositorio `COURSEPLATFORM_MONITOR_JOB_SECRET`, com
o mesmo valor server-only de `JOB_RUNNER_SECRET`. O valor nunca aparece no YAML
nem no relatorio.

Esta taxa 5xx e sintetica: representa as rotas sondadas pelo monitor. A taxa
agregada de todo o trafego continua a depender dos logs estruturados da Vercel
ou de um futuro drain de observabilidade; nao deve ser inferida a partir destas
quatro sondagens.

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

Ensaio de 3 de outubro de 2026: a cadeia completa foi aplicada a uma base vazia
em PostgreSQL 18 local/WSL; os quatro cenarios de integracao passaram. Um dump
custom foi restaurado numa segunda base local: 56 tabelas, versao de esquema e
contagens de linhas coincidiram. Uma amostra sintetica de tres objetos foi
arquivada e restaurada com SHA-256 identico. Isto valida o procedimento local,
mas nao substitui um ensaio futuro com um backup real e objetos reais do
Supabase Storage num projeto isolado.

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
