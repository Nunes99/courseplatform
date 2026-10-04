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

## M1 — Contexto institucional na autenticação

A implementação M1 foi aplicada e validada em 4 de outubro de 2026 pela
migração `20261004103000_add_tenant_session_guards.sql` e pelo domínio de
identidade.

- Logins com uma única membership ativa continuam diretos e compatíveis.
- Depois de validar as credenciais, contas com várias memberships recebem
  apenas identificador, nome, slug e papel das instituições permitidas.
- A instituição enviada pelo cliente é sempre revalidada no servidor.
- A sessão grava o `organization_id`; payloads posteriores não podem substituí-lo.
- `student_context` e `admin_context` exigem membership e organização ativas.
- A troca de instituição invalida o token atual e emite uma sessão nova.
- Suspender/remover uma membership revoga somente as sessões desse tenant.
- Suspender uma organização revoga todas as suas sessões ativas.

O login com uma instituição e a seleção explícita de tenant para uma identidade
com mais de uma membership foram validados. Os registos temporários usados na
validação foram removidos e nenhuma segunda organização permanece ativa. Novos
testes cruzados devem preferir uma base descartável até a conclusão do
isolamento dos domínios na M2.

O frontend guarda a validade da sessão, elimina localmente tokens expirados e
confirma a sessão no servidor antes de carregar o dashboard. Sessões revogadas,
inválidas ou sem membership ativa regressam imediatamente à autenticação após
essa verificação, sem iniciar o conjunto de leituras do painel.

## M2 — Isolamento de aprendizagem e avaliações

As leituras privadas de aprendizagem usam agora exclusivamente o
`organization_id` da sessão validada:

- `getMyCourses` filtra cursos pela organização ativa;
- home e dashboard resolvem matrícula, curso, versão e oferta no mesmo tenant;
- a leitura de aula valida a organização do curso antes de carregar o snapshot;
- a configuração de media autenticada exige que o curso pertença ao tenant;
- relações entre matrícula, versão e oferta confirmam também o mesmo curso.

As mutações de aprendizagem e avaliações validam agora a organização da sessão
na mesma ligação usada pela operação:

- iniciar, consultar, responder, anexar, remover e submeter uma tentativa exige
  que matrícula, curso e tentativa pertençam à organização ativa;
- o download de um trabalho confirma estudante, tentativa e organização antes
  de ler Storage ou o Base64 histórico;
- revisão, reenvio, exceções e atualização administrativa recusam tentativas de
  outra organização, inclusive para administradores e proprietários;
- concessão de acesso e atualização de progresso validam curso, grupo, aula e
  membership ativa de todos os estudantes antes de qualquer escrita em lote;
- testes negativos sintéticos cobrem instituições A e B sem criar um segundo
  tenant permanente.

O domínio de certificados também está vinculado à organização ativa:

- emissão, consulta, PDF e contagem de downloads resolvem curso, matrícula e
  certificado dentro do tenant da sessão do estudante;
- listagem, bloqueio, reativação, eliminação e reemissão administrativas recusam
  certificados pertencentes a outra organização;
- configuração e ativos gráficos só podem ser alterados em cursos da
  organização administrativa ativa;
- novos ativos usam um caminho de Storage iniciado por `organization_id`;
- o âmbito global de um revisor é global apenas dentro da sua organização;
- a verificação pública por número/código permanece pública e expõe somente o
  contrato mínimo de validação do certificado.

O domínio de pagamentos e comprovativos também respeita o tenant da sessão:

- pedidos profissionais só aceitam comprovativos quando estudante, pedido e
  curso pertencem à organização ativa;
- novos comprovativos privados incluem `organization_id` no caminho de
  Storage, sem alterar ou invalidar os caminhos históricos;
- listagem, aprovação, rejeição e eliminação administrativa filtram o curso
  pela organização antes de qualquer escrita;
- downloads de comprovativos validam organização e proprietário, tanto para o
  estudante como para o administrador;
- cursores da lista administrativa são vinculados ao tenant e não podem ser
  reutilizados após uma troca de organização;
- testes negativos sintéticos confirmam que A não submete, consulta, aprova,
  elimina nem descarrega pedidos ou comprovativos de B.

Os domínios de inquéritos, comunicação e administração também passaram a usar
a organização ativa da sessão:

- configuração e listagem de inquéritos exigem que o curso pertença ao tenant;
- notificações, preferências, Push, Telegram, salas, presença e tópicos
  Realtime carregam `organization_id` e não reutilizam chaves globais;
- a fila pode continuar a ser processada globalmente por jobs internos, mas o
  retry iniciado por um administrador reclama apenas entregas do tenant ativo;
- contagens, listas, detalhes, alterações de estado, recuperação de acesso,
  staff e âmbitos de revisão são filtrados pela membership institucional;
- desativar um estudante ou staff revoga apenas as sessões da organização
  afetada; uma membership suspensa continua visível ao administrador para poder
  ser reativada;
- testes negativos sintéticos cobrem inquérito, sala, fila de entrega e
  estudante entre instituições A e B.

A migração `20261004180000_isolate_communication_by_organization.sql` é
expansiva: preserva mensagens, notificações, dispositivos e tokens existentes,
faz o backfill para a organização histórica e só depois instala `NOT NULL`, FKs,
índices e unicidade composta. Ela ainda não foi aplicada externamente nesta
fatia.

Durante o rollout, essas cinco colunas mantêm temporariamente o default da única
instituição ativa para que o deployment anterior continue funcional enquanto o
backend compatível é publicado. O código novo sempre envia `organization_id`
explicitamente. Uma migração posterior deve remover os defaults antes de criar
ou ativar a segunda instituição.

M2 permanece aberta para o inventário final das operações em lote, projeções
públicas e auditoria persistida. Configurações de transporte como SMTP, bot e
VAPID continuam sendo infraestrutura global da plataforma; não devem ser
expostas como configuração independente por instituição até existir um plano de
controlo global separado da administração institucional.

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

O backend compatível foi publicado depois da migração. Em 4 de outubro de 2026,
`/health/live` e `/health/ready` responderam `200`, confirmando que o deployment
reconhece `EXPECTED_SCHEMA_VERSION = 20261004063506`. Um login real de estudante
carregou o painel e criou uma sessão recente, ativa e válida, ligada a
`ORG-LMTWEBNAIRS` e a uma membership ativa correspondente. Nenhuma segunda
organização foi ativada.

Em caso de regressão, reverta primeiro a aplicação. As tabelas e colunas são
aditivas e podem permanecer sem uso. Não remova memberships nem
`organization_id` durante um incidente; uma remoção exige migração própria e
backup confirmado.
