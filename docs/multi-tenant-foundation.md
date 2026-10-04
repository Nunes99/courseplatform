# Fundação SaaS multi-instituição

Data da primeira fatia: 4 de outubro de 2026.

## Decisão arquitetural

A CoursePlatform evoluirá como SaaS multi-instituição. A identidade de uma
pessoa permanece global e a autorização institucional passa a ser representada
por uma associação explícita. Assim, a mesma pessoa poderá futuramente estudar
ou trabalhar em mais de uma instituição sem duplicar a conta nem perder o
histórico.

O campo `students.organization` continua a ser informação profissional livre
do perfil, como empresa ou entidade empregadora. Ele não identifica um tenant e
não deve ser usado em filtros de segurança.

## Primeira fatia implementada

A migração `20261004063506_add_multi_tenant_foundation.sql` introduz:

- `courseplatform.organizations`, com slug, estado e configurações não secretas;
- `courseplatform.organization_memberships`, ligando uma identidade global a
  uma organização nos papéis `STUDENT`, `REVIEWER`, `ADMIN` ou `OWNER`;
- `organization_id` obrigatório em cursos, sessões e âmbitos de revisão;
- índices para as consultas institucionais futuras;
- RLS e revogação completa de `public`, `anon` e `authenticated` nas tabelas
  novas;
- acesso apenas de leitura para `courseplatform_runtime` nesta fase;
- backfill determinístico de todos os dados atuais para `ORG-LMTWEBNAIRS`;
- sincronização transitória de novos estudantes e membros de staff com a
  organização inicial, evitando memberships ausentes enquanto o seletor de
  organização ainda não existe.

O backfill não recria estudantes, staff, cursos, sessões ou âmbitos. Os IDs e as
relações históricas permanecem iguais. Uma identidade ligada a staff recebe uma
membership de estudante e outra membership administrativa, sem ganhar
permissões implicitamente.

## Limite de segurança desta fatia

Esta fundação **não autoriza ainda a ativação de uma segunda instituição**. A
API atual foi construída para uma instituição e ainda existem agregados que
obtêm o tenant indiretamente pelo curso, além de Storage, jobs, cache, pesquisa,
relatórios e auditoria que precisam de contexto institucional obrigatório.

Até a conclusão das fases abaixo:

- não deve existir endpoint de criação de organizações;
- a role `courseplatform_runtime` possui apenas `SELECT` nas tabelas novas;
- `service_role` e a role de migração não podem ser usadas pelo frontend;
- `DEFAULT_ORGANIZATION_ID` deve continuar como `ORG-LMTWEBNAIRS` nos ambientes
  com os dados históricos atuais;
- os triggers transitórios da organização inicial devem ser substituídos por
  atribuição explícita e transacional antes de permitir novos tenants;
- criar manualmente outro tenant não torna a aplicação multi-tenant segura.

## Próximas fases

1. Propagar `organization_id` para os agregados que não derivam com segurança o
   tenant pelo curso, incluindo auditoria, notificações, jobs e configuração.
2. Resolver a organização ativa durante login e gravá-la na sessão; exigir
   contexto explícito quando a identidade pertencer a mais de uma organização.
3. Aplicar filtros institucionais em todos os repositórios e mutações, incluindo
   revisores com âmbito `GLOBAL`, que passará a significar global apenas dentro
   da organização.
4. Isolar objetos de Storage por prefixo imutável de organização e verificar o
   tenant antes de gerar qualquer download.
5. Criar administração institucional separada da administração global da
   plataforma, sem promoção implícita entre os dois níveis.
6. Adicionar testes negativos cruzados para estudante, revisor, administrador,
   jobs, relatórios, pesquisa, cache, Realtime e ficheiros.
7. Só então disponibilizar criação, suspensão, branding e seleção de
   organizações na interface.

## Decisões de negócio pendentes

Antes de comercializar a capacidade multi-instituição, ainda devem ser
definidos: cobrança e planos, limites por organização, retenção e exportação,
domínios personalizados, identidade visual, propriedade de conteúdos, política
de uma mesma pessoa em instituições diferentes, administração global, SLA e
eventuais contratos de SSO, LTI, SCORM ou xAPI.

Essas decisões não foram inventadas nesta migração. A estrutura atual permite
avançar por expansão, mantendo compatibilidade com a instituição existente.

O roteiro completo, incluindo administração global, modelo editorial e página
pública do agregador, está em
[saas-multi-institution-roadmap.md](saas-multi-institution-roadmap.md).

## Aplicação e rollback operacional

A migração foi aplicada ao projeto Supabase principal em 4 de outubro de 2026,
após diagnóstico somente leitura e autorização explícita. O histórico remoto e
o marcador da aplicação registam `20261004063506`. A validação confirmou uma
organização, 57 memberships de estudante, 3 memberships de staff, todos os 2
cursos, 399 sessões e 3 âmbitos de revisão associados a `ORG-LMTWEBNAIRS`, FKs
validadas, RLS ativa e ausência de privilégios de cliente nas tabelas novas.

O deployment ainda executava a versão anterior durante a validação: liveness
respondeu `200`, mas readiness respondeu `503` até que o backend com
`EXPECTED_SCHEMA_VERSION = 20261004063506` seja publicado. Login só deve ser
validado depois desse deploy compatível.

Em caso de regressão, reverta primeiro a aplicação. As tabelas e colunas são
aditivas e podem permanecer sem uso. Não remova memberships nem
`organization_id` durante um incidente; uma remoção exige migração própria e
backup confirmado.
