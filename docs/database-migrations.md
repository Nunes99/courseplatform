# Migrações e health checks

## Fonte de verdade

`supabase/migrations/` é a única fonte de verdade do esquema. A API não lê nem
executa `supabase/schema.sql`, `supabase/chat_realtime.sql` ou
`backend/courseplatform/schema.sql` durante pedidos.

A versão exigida pelo backend é `20260929120000`. A última migração estrutural grava esse
valor em `courseplatform.schema_versions`. Uma ausência ou diferença produz
`DATABASE_MIGRATION_REQUIRED`; a aplicação não tenta corrigir a base.

O timestamp no nome do ficheiro identifica o registo no histórico de migrações
do Supabase. O valor em `schema_versions` é um contrato independente da API e
não deve ser inferido a partir desse nome.

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
7. `20260915173343_model_course_versions_and_offerings.sql`: separa catálogo, versão publicada, edição/turma e matrícula histórica.
8. `20260920221040_unify_staff_student_identity.sql`: liga atribuições administrativas à identidade de estudante sem remover credenciais legadas não associadas.
9. `20260920232716_unified_account_registration.sql`: adiciona verificação de email para novos cadastros, preserva contas históricas e materializa tokens de confirmação de utilização única.
10. `20260925043513_add_reviewer_scopes.sql`: adiciona âmbitos de revisão por curso, edição/turma ou grupo e preserva revisores existentes com um âmbito global inicial.
11. `20260925071234_add_versioned_question_bank.sql`: adiciona identidades reutilizáveis, versões imutáveis, opções, dificuldade e tags para o banco de questões.
12. `20260925071409_add_question_bank_actor_indexes.sql`: adiciona índices de suporte às relações administrativas do banco de questões.
13. `20260926120000_add_versioned_assessment_policies.sql`: versiona limites, janela, duração e randomização das avaliações e adiciona exceções individuais auditáveis.
14. `20260928120000_repair_epg_course_metadata.sql`: reparação de dados do curso EPG importado sem títulos ou ordem; preserva IDs, matrículas, progressos e a versão publicada, guardando o estado anterior para rollback operacional.
15. `20260928133000_seed_epg_v2_draft_content.sql`: cria a versão 2 em rascunho do curso EPG e dez versões imutáveis de questões, sem publicar o curso nem alterar registos académicos históricos.
16. `20260928190000_complete_stage10_pedagogical_core.sql`: adiciona rubricas, histórico imutável de notas e snapshots de conclusão por matrícula.
17. `20260929120000_complete_stage11_certification_contract.sql`: congela o contrato documental dos certificados, introduz reemissões encadeadas e separa as respostas dos inquéritos das solicitações financeiras.

A migração `20260926120000` foi aplicada ao projeto Supabase principal em 27 de
setembro de 2026 e registada no histórico remoto. A validação posterior confirmou
o marcador da aplicação, a tabela e colunas novas e os privilégios mínimos da
role runtime. O deploy da aplicação que exige esta versão deve ocorrer antes dos
testes funcionais com contas reais.

A migração de reparação `20260928120000` foi aplicada ao projeto Supabase
principal em 28 de setembro de 2026 e registada em
`supabase_migrations.schema_migrations`. A validação posterior confirmou o
backup de reconciliação, os metadados corrigidos na interface do estudante e a
preservação dos identificadores históricos. A migração é exclusivamente de
dados e não altera a versão estrutural do esquema.

A migração de dados `20260928133000` é repetível apenas quando os identificadores
e o snapshot existente forem exatamente equivalentes; caso encontre outro
rascunho ou uma colisão divergente, falha antes de substituir dados. Não atualiza
o marcador estrutural de esquema, não publica o curso e não altera ofertas nem
registos académicos históricos. Numa instalação onde `COURSE-EPG-001` não
exista, termina sem alterações para não bloquear o baseline. Foi aplicada ao
projeto Supabase principal em 28 de setembro de 2026, após autorização explícita,
e registada em `supabase_migrations.schema_migrations`. A validação posterior
confirmou estado `DRAFT`, dois módulos, oito conteúdos, dez questões e ausência
de oferta associada.

O rollback operacional é permitido apenas enquanto a versão 2 continuar em
`DRAFT` e não tiver referências posteriores: remover primeiro a versão do curso
e depois as opções, versões e itens `QB-EPG-001-*`. A versão 1 publicada nunca
deve ser removida ou reescrita durante esse rollback.

A migração `20260928190000` é expansiva e repetível: adiciona colunas com valores
padrão compatíveis e cria o histórico privado de alterações de notas sem
reescrever revisões, tentativas, progressos ou matrículas existentes. Revoga
acesso de `public`, `anon` e `authenticated`; `courseplatform_runtime` recebe
somente `SELECT` e `INSERT`. Foi aplicada ao projeto Supabase principal em 28 de
setembro de 2026 e registada em `supabase_migrations.schema_migrations`. A
validação posterior confirmou o marcador `20260928190000`, as colunas novas,
RLS ativo e a ausência de privilégios para `anon` e `authenticated`.

A migração `20260929120000` foi aplicada ao projeto Supabase principal em 30 de
setembro de 2026 e registada em `supabase_migrations.schema_migrations`. A
validação posterior confirmou o marcador `20260929120000`, seis colunas novas,
quatro constraints, quatro índices, RLS ativo e ausência de leitura para `anon`
e `authenticated`. As quatro respostas históricas de inquéritos foram copiadas
para a tabela dedicada, sem remover nem alterar os dados legados.

As migrações da Etapa 4 são aditivas e repetíveis. A migração histórica da role
runtime é a exceção deliberada: uma segunda execução falha antes de alterar
qualquer privilégio e exige inspeção manual. O teste confirma esse bloqueio,
repete as restantes migrações e verifica que um registo sentinela permanece.
Futuras migrações devem declarar o próprio comportamento e rollback operacional.
As migrações das políticas e do fecho pedagógico são expansivas e repetíveis:
mantêm tentativas e módulos existentes, usam padrões compatíveis e atualizam o
marcador de versão quando alteram o contrato estrutural exigido pela aplicação.

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
