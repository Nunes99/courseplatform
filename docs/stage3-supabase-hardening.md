# Etapa 3: endurecimento do Supabase

Estado em 13 de setembro de 2026: diagnóstico concluído e migração
`stage3_harden_supabase_access` aplicada diretamente em produção após autorização
explícita. O plano atual não permitiu criar uma branch Supabase; por isso a
validação isolada não foi executada.

## O que foi verificado

No repositório:

- o frontend não consulta tabelas ou views com PostgREST;
- a chave publicável é usada apenas pelo transporte privado do Realtime;
- dados académicos passam pela API FastAPI e por uma ligação Postgres do servidor;
- `SUPABASE_SERVICE_ROLE_KEY` é lida apenas pelo backend para uploads administrativos;
- não foram encontrados nomes de segredos de servidor nos ficheiros frontend;
- o login principal usa sessões próprias e não cria identidades Supabase Auth.

No projeto Supabase, através de SQL somente leitura:

- antes da migração, 40 das 42 tabelas em `courseplatform` tinham RLS ativa;
- depois da migração, as 42 tabelas têm RLS ativa e continuam sem policies;
- `anon` e `authenticated` não têm privilégios diretos nessas tabelas;
- `service_role` tem acesso total às tabelas e ignora RLS;
- a sessão administrativa de diagnóstico usa `postgres`, que também ignora RLS;
- no instante do diagnóstico estavam visíveis apenas sessões de infraestrutura
  (`authenticator`, `postgres`/gestão e `supabase_admin`); não havia uma sessão da
  API Vercel que permitisse confirmar a sua role efetiva;
- as 32 views de compatibilidade em `public` passaram a usar `security_invoker`;
- `anon` e `authenticated` ficaram sem privilégios nessas 32 views;
- `service_role` mantém apenas SELECT nessas views, sem mutações;
- os default privileges pertencentes a `postgres` foram restringidos;
- permanecem defaults geridos pela role interna `supabase_admin`; o executor de
  migrações não tem permissão para alterá-los e a tentativa foi revertida;
- essas views incluem dados sensíveis como estudantes, administradores, sessões,
  perguntas, opções, respostas, auditoria e credenciais de transição;
- existe uma policy Realtime para `authenticated`, limitada a broadcast privado e
  validada por `courseplatform.chat_realtime_topic_allowed`;
- `public.rls_auto_enable()` deixou de ser executável por `anon`, `authenticated`
  e `service_role`;
- não existem buckets nem policies de Storage no projeto consultado;
- não existem branches de desenvolvimento no projeto.

O diagnóstico confirmou a exposição anterior pelas views públicas. A migração
removeu essa exposição sem eliminar as views de compatibilidade.

## Artefactos

- `supabase/diagnostics/stage3_access_audit.sql`: inventário somente leitura;
- `supabase/migrations/20260913072447_stage3_harden_supabase_access.sql`:
  migração de endurecimento aplicada em produção com a versão
  `20260913091442`;
- `scripts/verify_supabase_access.py`: verificação pós-migração para staging;
- `tests/test_supabase_access_hardening.py`: contratos estáticos de segurança.

## Estratégia de compatibilidade

A primeira fase não elimina as views. Ela:

1. converte as views conhecidas para `security_invoker`;
2. revoga todos os privilégios de `PUBLIC`, `anon` e `authenticated`;
3. limita `service_role` a SELECT nas views;
4. nega acesso cliente direto ao esquema `courseplatform`;
5. preserva apenas `USAGE` do esquema e `EXECUTE` na função de autorização do
   Realtime para `authenticated`;
6. revoga a execução pública das funções operacionais `SECURITY DEFINER`;
7. corrige os default privileges de `postgres` para objetos futuros;
8. força o bucket padrão de certificados a privado, caso já exista.

As views ficam disponíveis ao SQL Editor e à `service_role` durante uma janela de
compatibilidade. Depois de confirmar logs e integrações externas, uma migração
posterior pode eliminar as views sem uso. Não se deve restaurar acesso cliente às
views que contêm hashes, sessões, credenciais ou gabaritos.

## Validação efetuada

- diagnóstico de grants e RLS antes e depois da migração;
- 32/32 views com `security_invoker` e sem acesso cliente;
- 42/42 tabelas com RLS e sem privilégios diretos de cliente;
- exceção Realtime limitada a `authenticated` e à função de autorização;
- tópico sintético inexistente recusado pela função de autorização;
- policy Realtime privada preservada;
- página pública com HTTP 200;
- health check com base e autenticação ativas;
- Security Advisor sem os erros de views `security_definer` e sem exposição de
  `rls_auto_enable`.

Não foram criadas contas sintéticas em produção nem usadas credenciais reais.
Assim, login, cursos, submissões e certificados não foram testados ponta a ponta
contra a produção.

## Validação recomendada em staging

1. Criar ou selecionar um projeto/branch isolado, sem dados pessoais reais.
2. Aplicar todas as migrações anteriores e carregar apenas fixtures sintéticas.
3. Executar `supabase/diagnostics/stage3_access_audit.sql` e arquivar o resultado
   sem linhas da aplicação.
4. Aplicar todas as migrações, incluindo
   `20260913072447_stage3_harden_supabase_access.sql`.
5. Executar o diagnóstico novamente e comparar grants, owners, RLS e policies.
6. Executar o verificador:

```powershell
$env:STAGING_DATABASE_URL = "definida-fora-do-repositorio"
$env:STAGING_SUPABASE_PROJECT_REF = "referencia-do-staging"
$env:PRODUCTION_SUPABASE_PROJECT_REF = "referencia-da-producao"
$env:ALLOW_STAGE3_STAGING_VALIDATION = "1"
.\.venv\Scripts\python.exe scripts\verify_supabase_access.py
```

7. Com contas sintéticas, validar pela API: anónimo recusado; estudante A sem
   acesso ao estudante B; revisor limitado às ações autorizadas; ADMIN sem gestão
   de OWNER; OWNER com gestão de staff auditada.
8. Validar Realtime com estudante e staff em salas permitidas e recusadas.
9. Se o bucket for criado, validar upload administrativo, ausência de listagem
   pública e download apenas por endpoint autenticado/URL assinada.
10. Executar a suíte completa e o smoke test de staging antes de qualquer rollout.

## Rollback

Se surgir uma integração legítima, o rollback deve restaurar apenas a operação e
as colunas mínimas de uma view específica. Nunca restaurar grants globais nem
remover `security_invoker`. O bucket deve permanecer privado.

## Riscos ainda abertos

- a role efetiva da API em cada ambiente depende do utilizador presente na URL de
  conexão; o código não executa `SET ROLE`;
- usar `postgres` como role da aplicação concede `BYPASSRLS` e administração de
  objetos; deve ser substituído numa etapa própria por uma role de runtime mínima;
- os papéis estudante/revisor/admin são papéis da aplicação, não roles Postgres;
- Storage ainda não contém o bucket esperado, portanto a validação real de upload
  e download privado depende da etapa de migração de ficheiros;
- a opção **Integrations > Data API > Default privileges for new entities** foi
  desativada pelo proprietário em 13 de setembro de 2026; a confirmação por SQL
  ficou pendente devido a indisponibilidade temporária do conector;
- a proteção contra palavras-passe comprometidas do Supabase Auth não se aplica ao
  login atual e não substitui a política bcrypt da aplicação.
