# Plano de evolução SaaS multi-instituição

Data do plano: 4 de outubro de 2026.

## Objetivo

Evoluir a CoursePlatform de uma LMS de uma instituição para uma plataforma SaaS
capaz de servir várias instituições com isolamento verificável, administração
independente, identidade global e um agregador público de instituições, cursos
e ofertas.

O programa deve preservar estudantes, staff, matrículas, progressos,
submissões, notas, pagamentos, ficheiros e certificados existentes. A segunda
instituição só poderá ser ativada quando os testes negativos de isolamento
estiverem completos.

## Princípios obrigatórios

1. A pessoa possui uma identidade global; o acesso nasce de uma membership
   institucional e nunca de uma cópia da conta.
2. Todo dado pertencente a um tenant deve ter `organization_id` direto ou uma
   relação obrigatória, simples e indexada que determine o tenant.
3. O tenant ativo vem da sessão validada no servidor. IDs, slugs, headers ou
   parâmetros enviados pelo navegador nunca concedem acesso por si mesmos.
4. Administração global da plataforma e administração de uma instituição são
   autoridades diferentes.
5. `OWNER` institucional não recebe privilégios globais implícitos.
6. O agregador lê apenas projeções publicadas e mínimas. Ele nunca consulta
   diretamente dados administrativos, matrículas ou perfis de estudantes.
7. Storage, jobs, cache, pesquisa, Realtime, auditoria, métricas e relatórios
   obedecem ao mesmo isolamento do Postgres.
8. Alterações estruturais seguem expansão, backfill, validação e só depois
   remoção de compatibilidade antiga.
9. Nenhuma fase declara segurança ou escala sem testes e medição.

## Vocabulário

- **Plataforma:** produto CoursePlatform e a sua operação global.
- **Organização:** instituição cliente isolada, como escola, universidade ou
  centro de formação.
- **Membership:** relação entre uma identidade global e uma organização.
- **Tenant ativo:** organização selecionada e gravada na sessão atual.
- **Curso:** identidade académica mantida pela organização.
- **Versão:** snapshot editável/publicado do conteúdo do curso.
- **Oferta:** edição ou turma que usa uma versão num período definido.
- **Entrada de catálogo:** projeção pública deliberadamente publicada no
  agregador, ligada a uma versão e, opcionalmente, a uma oferta.
- **Agregador:** experiência pública para descobrir instituições, cursos e
  ofertas; não é o painel académico autenticado.

## Arquitetura alvo

### Estratégia de tenancy

A estratégia recomendada para esta fase é **base e esquema partilhados com
isolamento por `organization_id`**, mantendo o Postgres/Supabase atual. Não será
criado um projeto Supabase, esquema Postgres ou deployment Vercel por
instituição. Essa abordagem preserva a arquitetura atual e permite operação e
migrações centralizadas, desde que o isolamento seja aplicado e testado em
todas as superfícies.

O backend Python continua como única fronteira de dados do produto. A Data API
não deve expor tabelas internas ao navegador. RLS, constraints e grants são
defesa adicional; como a autenticação principal ainda é própria, o backend
continua obrigado a resolver a membership e filtrar cada consulta pelo tenant
da sessão.

Uma arquitetura de base dedicada por tenant só deverá ser reconsiderada se
requisitos contratuais de residência, chaves próprias, isolamento físico ou
escala medida justificarem o custo operacional.

### Classificação dos dados

| Classe | Exemplos | Regra |
| --- | --- | --- |
| Global de identidade | Conta, email confirmado, métodos de autenticação | Não pertence implicitamente a uma instituição |
| Privado institucional | Cursos, matrículas, notas, submissões, pagamentos, relatórios | Tenant obrigatório e acesso pela membership |
| Projeção pública | Perfil institucional e entrada publicada de catálogo | DTO mínimo, snapshot editorial e leitura anónima |
| Operacional global | Estado da plataforma, migrações, métricas agregadas | Apenas operadores globais e processos internos |

Dados privados nunca se tornam públicos apenas porque o curso ou a instituição
estão ativos. Publicação é uma ação editorial separada, versionada e auditada.

### Identidade e autorização

`students` permanece como identidade global durante a transição. As permissões
institucionais vivem em `organization_memberships`. Uma conta pode ter várias
memberships e papéis diferentes em organizações distintas.

Papéis institucionais iniciais:

| Papel | Âmbito |
| --- | --- |
| `STUDENT` | Próprias matrículas, dados e atividades na organização ativa |
| `REVIEWER` | Cursos, ofertas ou grupos atribuídos na organização ativa |
| `ADMIN` | Gestão operacional da organização, sem gerir operadores globais |
| `OWNER` | Staff, políticas e configuração da própria organização |

Papéis globais deverão usar uma estrutura separada, por exemplo
`platform_role_assignments`, com `PLATFORM_OWNER`, `PLATFORM_OPERATOR` e
`PLATFORM_SUPPORT`. O suporte global deve exigir motivo, janela temporal e
auditoria para qualquer acesso delegado a um tenant.

### Dados institucionais

O `organization_id` deve ser propagado para configurações, branding,
notificações, auditoria, jobs, relatórios e outros agregados que não possam
derivá-lo inequivocamente por uma FK de curso/oferta. Relações redundantes só
serão adicionadas quando reduzirem risco ou melhorarem consultas medidas, com
constraints que impeçam combinações entre tenants.

### Publicação no agregador

O catálogo público não será uma view com `select *` sobre `courses`. O modelo
recomendado é uma projeção própria:

- `organization_public_profiles`: nome público, resumo, localização, contactos
  públicos, branding aprovado, estado editorial e SEO;
- `catalog_entries`: organização, curso, versão, oferta opcional, slug, resumo,
  audiência, modalidade, idioma, duração, datas, política de inscrição, preço
  público opcional, imagem, estado e snapshot publicado;
- `catalog_categories` e `catalog_entry_categories`: taxonomia controlada;
- `organization_domains`: domínios verificados e respetivo estado;
- `catalog_publication_log`: publicação, retirada, autor e versão do snapshot.

Somente registos `PUBLISHED`, de organizações `ACTIVE` e com período público
válido aparecem no agregador. Retirar uma oferta deve removê-la das listagens
sem apagar o curso, a versão ou os históricos académicos.

### Rotas alvo

Rotas públicas recomendadas:

- `GET /api/v1/public/organizations`
- `GET /api/v1/public/organizations/{organization_slug}`
- `GET /api/v1/public/catalog`
- `GET /api/v1/public/organizations/{organization_slug}/courses/{course_slug}`
- `GET /api/v1/public/catalog/categories`

Todas usam paginação por cursor, filtros validados, DTOs mínimos, cache público
controlado e limites de frequência. Nenhuma devolve IDs internos desnecessários.

Estrutura de páginas alvo:

- `/`: agregador público após a transição final;
- `/explorar`: primeira implantação do agregador, sem quebrar a raiz atual;
- `/instituicoes/{slug}`: perfil público da instituição;
- `/instituicoes/{slug}/cursos/{courseSlug}`: curso/oferta pública;
- `/entrar`: autenticação unificada;
- `/app`: área do estudante;
- `/admin`: área institucional de staff;
- `/platform`: operação global, nunca acessível a staff institucional comum.

Durante a migração, os URLs atuais continuam funcionais. A raiz só muda para o
agregador depois de `/app`, `/admin`, recuperação, confirmação de email e links
enviados por notificações estarem validados.

## Experiência do agregador público

### Página inicial

A primeira viewport deve oferecer utilidade imediata:

- cabeçalho compacto com marca da plataforma, Instituições, Cursos, pesquisa e
  Entrar;
- pesquisa principal por curso, competência ou instituição;
- filtros visíveis para categoria, modalidade, idioma, duração, período,
  certificado e tipo de acesso;
- resultados de cursos e instituições logo abaixo, sem uma página de marketing
  a bloquear o catálogo;
- ordenação por relevância, início próximo, novidade e nome;
- paginação por cursor com URL partilhável e estado preservado.

Cada curso mostra apenas informações comparáveis: instituição, título, resumo,
modalidade, duração, datas, certificado, política de inscrição e preço quando
for público. O CTA varia entre `Ver curso`, `Inscrever-me`, `Candidatar-me` ou
`Entrar com convite`.

### Página da instituição

Deve apresentar identidade verificada, descrição, localização, contactos
públicos, cursos publicados, certificações/credenciais institucionais aprovadas
e políticas públicas. Não deve mostrar staff interno, estudantes, métricas
privadas ou configurações operacionais.

### Página do curso

Deve mostrar versão publicada, resultados de aprendizagem, programa resumido,
carga horária, modalidade, idioma, requisitos, calendário da oferta,
certificação, política de preço/inscrição e instituição responsável. Conteúdos
de aula, gabaritos e materiais protegidos permanecem fora da página pública.

### Qualidade de interface

- Layout responsivo a 320 px, 200% de zoom e desktop amplo.
- Navegação completa por teclado, foco visível e landmarks semânticos.
- Contraste WCAG AA e suporte a tema claro/escuro quando ambos forem mantidos.
- Skeletons estáveis, estados vazios úteis e erros recuperáveis.
- Imagens com dimensões reservadas, variantes otimizadas e fallback de marca.
- Metadados SEO, canonical, Open Graph e dados estruturados apenas a partir do
  snapshot público.
- Sem contagens, avaliações ou classificações inventadas.

## Fases de execução

### M0 — Fundação e contrato de transição

Estado: **concluída**.

Entregas:

- `organizations` e `organization_memberships`;
- organização inicial `ORG-LMTWEBNAIRS`;
- vínculo de cursos, sessões e âmbitos de revisão;
- backfill e sincronização transitória de identidades novas;
- documentação e testes de contrato.

Gate de saída:

- publicar o backend que exige `20261004063506`;
- readiness compatível;
- login, cursos e revisão sem regressão;
- nenhuma segunda organização ativa.

### M1 — Contexto institucional na autenticação

Estado: **implementada localmente; migração, deploy e validação externa
pendentes**.

Entregas:

- resolver memberships ativas no login;
- sessão com `organization_id` imutável;
- seletor seguro quando a identidade tiver várias organizações;
- troca de organização por nova sessão ou rotação de token;
- suspensão de membership revoga sessões daquele tenant;
- `admin_context` e `student_context` devolvem tenant validado.

Testes de saída:

- parâmetro adulterado não troca tenant;
- sessão de A não funciona em B;
- conta com duas memberships seleciona explicitamente;
- suspensão numa organização não destrói o acesso legítimo noutra.

### M2 — Isolamento de consultas e mutações

Entregas:

- catálogo, aprendizagem, matrículas, avaliações, certificados, pagamentos,
  inquéritos, comunicação e administração filtrados pelo tenant da sessão;
- `GLOBAL` do revisor passa a significar global apenas na organização;
- constraints impedem relações entre cursos, ofertas, grupos e memberships de
  organizações diferentes;
- helpers/repositórios comuns para evitar filtros manuais esquecidos.

Testes de saída:

- matriz negativa entre organização A e B para cada domínio;
- IDs válidos de outro tenant resultam em `404`/`403` seguro;
- operações em lote não misturam tenants;
- logs não revelam existência de dados externos.

### M3 — Storage, Realtime e operação isolados

Entregas:

- objetos privados em `{organization_id}/{domain}/{owner}/{object}`;
- autorização institucional antes de upload, download e URL assinada;
- tópicos Realtime com tenant obrigatório e claims mínimas;
- jobs, deduplicação, dead-letter, notificações, auditoria e métricas com
  `organization_id`;
- cache e pesquisa com namespace institucional.

Testes de saída:

- caminho ou object key de B não pode ser lido por A;
- worker nunca processa payload no tenant errado;
- subscrição Realtime cruzada é recusada;
- invalidação de cache não afeta outra instituição.

### M4 — Administração global e onboarding institucional

Entregas:

- painel `/platform` separado;
- criar, suspender e arquivar organizações;
- convite do primeiro `OWNER` institucional;
- limites, funcionalidades, branding, domínios e estado operacional;
- impersonação apenas se contratada, temporária, justificada e auditada;
- exportação e encerramento de tenant sem apagar históricos silenciosamente.

Testes de saída:

- owner institucional não alcança `/platform`;
- operador global não entra em dados académicos sem fluxo delegado;
- suspensão bloqueia novas sessões e preserva dados;
- onboarding é idempotente e recuperável.

### M5 — Modelo editorial do agregador

Entregas:

- migrações das projeções públicas;
- workflow `DRAFT → IN_REVIEW → PUBLISHED → WITHDRAWN`;
- preview autenticado antes da publicação;
- slugs únicos por organização e histórico de redirects;
- snapshots imutáveis e log editorial;
- API pública paginada e cacheável.

Testes de saída:

- curso ativo interno não aparece sem publicação explícita;
- retirar entrada não apaga matrículas;
- alteração futura do curso não modifica snapshot já publicado;
- DTO público não contém emails privados, IDs sensíveis ou configurações.

### M6 — Interface do agregador público

Entregas:

- `/explorar`, perfil institucional e detalhe do curso;
- pesquisa, filtros, ordenação, paginação e URLs partilháveis;
- SEO técnico, sitemap apenas de conteúdos publicados e robots coerente;
- analytics com consentimento e sem PII académica;
- navegação para autenticação/inscrição preservando a intenção do utilizador.

Testes de saída:

- desktop, mobile, teclado, 200% e 320 px;
- sem sobreposição, layout shift relevante ou erros de consola;
- resultados e filtros correspondem à API;
- conteúdo retirado deixa sitemap, cache e resultados dentro do SLA definido.

### M7 — Inscrição, candidatura e comercialização

Entregas:

- políticas `OPEN`, `APPLICATION`, `INVITE_ONLY` e `EXTERNAL`;
- candidatura e consentimentos versionados;
- pagamentos por organização apenas após decisão de fornecedor e contrato;
- webhooks assinados, idempotentes e auditáveis;
- quotas e planos sem bloquear acesso a históricos já adquiridos.

Testes de saída:

- repetição de callback não duplica pagamento ou matrícula;
- preço e moeda ficam congelados no pedido;
- cancelamento e reembolso têm estados explícitos;
- uma instituição nunca recebe fundos ou comprovativos de outra.

### M8 — Piloto com segunda instituição

Entregas:

- tenant sintético primeiro e instituição piloto depois;
- importação, branding, staff, curso, oferta e estudantes isolados;
- testes de carga representativos e custo por estudante ativo;
- backup/restauro por tenant e runbook de incidente;
- revisão de segurança independente antes da ativação comercial.

Gate final:

- zero achados P0/P1;
- matriz cruzada integral aprovada;
- RPO/RTO ensaiados;
- p50/p95/p99, erros, conexões, filas e Storage medidos;
- rollback e suspensão de tenant demonstrados.

### M9 — Transição da raiz e evolução contratada

Depois do piloto, promover o agregador de `/explorar` para `/`, manter redirects
dos links antigos e estabilizar `/app`, `/admin` e `/platform`. SSO/OIDC, LTI,
SCORM, xAPI/cmi5, domínios personalizados avançados e integrações externas só
entram mediante necessidade contratada e desenho específico.

## Estratégia de migração e compatibilidade

Cada alteração de dados seguirá:

1. Criar colunas/tabelas e índices sem remover estruturas antigas.
2. Preencher `organization_id` com operações determinísticas e auditáveis.
3. Executar diagnóstico de nulos, órfãos e relações cruzadas.
4. Fazer o backend escrever o formato novo e continuar a ler o antigo apenas
   durante uma janela definida.
5. Ativar constraints e filtros obrigatórios.
6. Validar com duas organizações sintéticas.
7. Remover defaults e triggers transitórios numa migração posterior.

O deploy da aplicação que exige uma nova versão do esquema ocorre somente após
a migração correspondente e o readiness confirmado.

## Estratégia de testes

Para cada fase:

- testes unitários de resolução de tenant e serialização pública;
- testes PostgreSQL numa base descartável para migração e constraints;
- testes de integração com organização A e B;
- testes negativos por papel e domínio;
- verificação de Storage, jobs, Realtime e cache;
- suíte completa e smoke tests pós-deploy;
- auditoria de frontend em desktop/mobile, teclado, consola, erro e vazio.

O teste essencial será sempre tentar usar um identificador real de B enquanto a
sessão pertence a A. Um `organization_id` presente na tabela não substitui essa
prova.

## Observabilidade e operação

Métricas e logs devem incluir `organization_id`, `request_id` e domínio, mas não
PII, tokens ou segredos. Alertas globais precisam permitir agregação por tenant
sem expor dados entre instituições. Devem existir limites para conexões, jobs,
Storage, emails e APIs externas, com comportamento definido quando a quota for
atingida.

Backups continuam globais no início, mas o produto deve suportar exportação e
restauração lógica verificável por organização antes de prometer portabilidade
ou eliminação seletiva.

## Decisões ainda necessárias

O desenvolvimento técnico pode avançar até M3 sem inventar regras comerciais.
Antes de M4–M7 precisam de decisão explícita:

- quem pode criar organizações e qual o processo de aprovação;
- planos, quotas, faturação e moeda;
- política de domínio e identidade visual;
- propriedade e reutilização de conteúdos entre organizações;
- retenção, exportação, eliminação e requisitos legais;
- disponibilidade e suporte contratados;
- inscrições gratuitas, candidaturas e pagamentos;
- relevância e ordenação no agregador;
- integrações externas realmente contratadas.

## Estado resumido

| Fase | Estado |
| --- | --- |
| M0 Fundação | Concluída |
| M1 Contexto na autenticação | Implementada localmente; rollout pendente |
| M2 Isolamento dos domínios | Não iniciada |
| M3 Storage e operação | Não iniciada |
| M4 Administração global | Não iniciada |
| M5 Publicação editorial | Não iniciada |
| M6 Agregador público | Planeada |
| M7 Inscrição/comercialização | Não iniciada |
| M8 Segundo tenant piloto | Bloqueada pelas fases anteriores |
| M9 Transição da raiz/integrações | Futura |

## Próxima ação autorizável

Aplicar e validar M0 antes de iniciar M1. Nenhum endpoint de criação de tenant,
nenhuma página de agregador e nenhuma segunda instituição devem ser ativados na
mesma mudança da fundação.
