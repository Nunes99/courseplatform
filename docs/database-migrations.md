# Migrações e health checks

## Fonte de verdade

`supabase/migrations/` é a única fonte de verdade do esquema. A API não lê nem
executa `supabase/schema.sql`, `supabase/chat_realtime.sql` ou
`backend/courseplatform/schema.sql` durante pedidos.

A versão exigida pelo backend é `20260920115325`. A última migração grava esse
valor em `courseplatform.schema_versions`. Uma ausência ou diferença produz
`DATABASE_MIGRATION_REQUIRED`; a aplicação não tenta corrigir a base.

## DDL retirado dos pedidos

As seguintes verificações continuam no backend, mas executam apenas `SELECT`:

| Função | Capacidade verificada | Migração equivalente |
| --- | --- | --- |
| `prepare_notification_feature_schema` / `ensure_notification_feature_schema` | notificações e canais | `20260913120000_materialize_notification_schema.sql` |
| `prepare_chat_feature_schema` / `ensure_chat_feature_schema` | salas, mensagens, leituras e presença | `20260913121000_materialize_chat_schema.sql` |
| `ensure_chat_realtime_schema` | policy, funções e trigger Realtime | `20260913122000_materialize_chat_realtime.sql` |
| `prepare_assessment_feature_schema` / `ensure_assessment_feature_schema` | submissões, estado e repetição | `20260913123000_materialize_assessment_workflow.sql` |
| `ensure_certificate_feature_schema` | certificados e solicitações | `20260913124000_materialize_certificate_schema.sql` |

`ensure_simple_certificate` tem nome semelhante, mas é uma operação de negócio:
emite um certificado numa transação e não altera o esquema.

## Ordem

1. `20260911000000_initial_courseplatform_schema.sql`: baseline idempotente para base vazia.
2. Migrações das Etapas 1, 2 e 3.
3. Migrações `2026091312*`: materialização do DDL legado.
4. `20260913131500_create_courseplatform_runtime_role.sql`: role mínima da API.
5. `20260913185739_add_application_schema_version.sql`: marcador de compatibilidade.
6. `20260914103215_private_submission_storage.sql`: metadados e buckets privados para trabalhos e comprovativos.
7. `20260915101047_model_course_versions_and_offerings.sql`: separa catálogo, versão publicada, edição/turma e matrícula histórica.
8. `20260920115325_unify_staff_student_identity.sql`: liga atribuições administrativas à identidade de estudante sem remover credenciais legadas não associadas.

As migrações da Etapa 4 são aditivas e repetíveis. A migração histórica da role
runtime é a exceção deliberada: uma segunda execução falha antes de alterar
qualquer privilégio e exige inspeção manual. O teste confirma esse bloqueio,
repete as restantes migrações e verifica que um registo sentinela permanece.
Futuras migrações devem declarar o próprio comportamento e rollback operacional.

## Teste local descartável

Nunca use estas instruções com uma URL remota. O teste recusa qualquer host que
não seja `localhost`/`127.0.0.1` e qualquer base sem `test` no nome.

```powershell
docker run --name courseplatform-migration-test --detach `
  --env POSTGRES_PASSWORD=local-test-only `
  --env POSTGRES_DB=courseplatform_test `
  --publish 55432:5432 postgres:17-alpine

$env:COURSEPLATFORM_TEST_DATABASE_URL = "postgresql://postgres:local-test-only@127.0.0.1:55432/courseplatform_test"
.\.venv\Scripts\python.exe -m unittest tests.test_migration_postgres_integration -v
Remove-Item Env:COURSEPLATFORM_TEST_DATABASE_URL

docker rm --force courseplatform-migration-test
```

O teste cria contratos sintéticos mínimos para roles e Realtime do Supabase,
aplica uma base vazia, simula a atualização do esquema anterior, valida a falha
segura da role e repete as migrações idempotentes, preservando dados relacionados.
Também valida múltiplas edições do mesmo curso, imutabilidade de versões
publicadas e vínculos históricos dos certificados. Não valida o serviço Supabase real.

## Base existente

O baseline foi introduzido depois de ambientes já estarem em funcionamento. Não
o execute às cegas numa base existente. Em staging isolado:

1. Faça backup e confirme a restauração.
2. Execute `supabase migration list --linked`.
3. Confirme por diagnóstico somente leitura que as tabelas centrais do baseline já existem.
4. Apenas nesse caso, reconcilie o histórico com `supabase migration repair --linked --status applied 20260911000000`.
5. Execute `supabase db push --linked --include-all --dry-run` e reveja cada migração pendente.
6. Com autorização, execute `supabase db push --linked --include-all`.
7. Valide `/health/ready`, login, cursos, submissões, certificados e Realtime com utilizadores sintéticos.

Se a base não corresponder ao baseline, não marque a migração como aplicada.
Produza primeiro um diff e uma migração de expansão específica.

Em produção, repita o mesmo fluxo apenas depois de staging, backup verificado,
janela de mudança e autorização explícita. A role administrativa é usada somente
pela ferramenta de migração; a API continua ligada como `courseplatform_api`.

## Rollback operacional

Estas migrações preservam estruturas antigas e dados. Em caso de falha após o
deploy, reverta primeiro a aplicação e mantenha as tabelas/colunas aditivas. Não
apague tabelas nem reduza a versão manualmente durante o incidente. Uma remoção
futura exige migração própria, confirmação de ausência de leitores e backup.

## Health checks

- `GET /health/live`: público, não consulta a base e responde `200` com `{"status":"ok"}`.
- `GET /health/ready`: público, consulta apenas conectividade e versão; responde `200` ou `503`, sem detalhes internos.
- `GET /health/diagnostics`: exige `X-Admin-Token` de `OWNER` ou `ADMIN`; devolve versão, contagens operacionais e estado de autenticação, sem host, URL, credenciais ou texto SQL.
- `GET /api/index?action=health`: alias legado e mínimo de readiness.

O token administrativo deve ser enviado em header, nunca na query string.
