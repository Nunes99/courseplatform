# Etapa 10: núcleo pedagógico

## Estado

Implementação técnica concluída localmente em 28 de setembro de 2026. A etapa
inclui a barreira de qualidade da autoria, banco de questões, regras e exceções
versionadas das avaliações, rubricas congeladas, histórico imutável de notas,
pauta consolidada, calendário académico e regras de conclusão por versão.

A migração final foi aplicada ao projeto Supabase principal em 28 de setembro
de 2026, após autorização explícita, e registada no histórico remoto. A leitura
posterior confirmou o marcador `20260928190000`, as novas colunas, a tabela
privada de histórico de notas, RLS ativo e os privilégios mínimos da role de
runtime. O deploy compatível e a validação funcional com contas reais continuam
atividades de release, não lacunas de implementação desta etapa.

## Pré-publicação

O painel de administração permite pré-visualizar qualquer versão usando sempre
o snapshot guardado nela. Criar um rascunho captura a estrutura atual do editor;
alterações posteriores só entram nesse rascunho através da ação explícita
`Atualizar do editor`. Publicar usa exatamente o snapshot pré-visualizado.

O administrador também pode editar diretamente os metadados do curso, módulos
e conteúdos do rascunho, e reordenar módulos ou conteúdos. Cada comando bloqueia
a linha da versão, aplica uma operação limitada sobre o snapshot mais recente e
faz uma única gravação antes do commit. Uma versão publicada nunca aceita estas
operações. O contrato do editor não devolve perguntas, respostas corretas ou
gabaritos.

Módulos e conteúdos também podem ser criados, removidos e restaurados dentro do
rascunho. A remoção é lógica: o item e o respetivo identificador permanecem no
snapshot com estado `DELETED`, permitindo restauro sem perda de texto, ordem ou
relações. Novos identificadores são sempre gerados pelo backend.

A resposta contém apenas o resumo necessário para o editor: metadados do curso,
ordem dos módulos e contagens de conteúdos e questões. Respostas corretas e o
conteúdo integral do banco de questões não são devolvidos pela pré-visualização.

## Validações bloqueantes

A publicação é recusada pelo backend quando existir pelo menos uma destas
inconsistências:

- código, título ou carga horária do curso ausentes;
- nota mínima fora do intervalo de 0 a 100;
- ausência de módulos ativos;
- módulo sem título, sem posição válida ou com posição duplicada;
- módulo sem conteúdo e sem atividade;
- pré-requisito inexistente, posterior, autorreferente ou cíclico;
- questão sem enunciado ou sem pontuação positiva;
- questão objetiva sem duas opções válidas ou sem resposta correta.

Um módulo que tenha avaliação mas não tenha conteúdo gera um aviso, sem impedir
a publicação. A pré-visualização e a publicação executam a mesma função de
validação; a interface não é a barreira de segurança.

## Compatibilidade e dados

O editor guarda uma cópia independente no campo `content_snapshot_json`, já existente.
Atualizá-lo substitui apenas essa cópia e regista `COURSE_VERSION_DRAFT_REFRESHED`
na auditoria. As edições diretas registam `COURSE_VERSION_DRAFT_EDITED`, incluindo
o tipo de operação. As ofertas, matrículas, progressos, tentativas e certificados
existentes permanecem inalterados.

O banco de questões separa a identidade reutilizável das versões. Cada versão
guarda tipo, opções, explicação, dificuldade, etiquetas, pontuação e resposta de
referência. Ao anexar uma versão publicada a um módulo, a API copia os dados para
o snapshot e preserva os identificadores de origem. Alterações posteriores no
banco não modificam cursos publicados, tentativas ou avaliações históricas.

A migração `20260925071234_add_versioned_question_bank.sql` é expansiva e não
reescreve questões existentes. As tabelas privadas têm RLS ativo, não concedem
acesso a `anon` ou `authenticated`, e versões publicadas, incluindo as respetivas
opções, tornam-se imutáveis. A migração foi apenas preparada localmente.

## Regras versionadas das avaliações

Cada módulo guarda no rascunho e na versão publicada a política da avaliação:

- limite de tentativas;
- início e fim da disponibilidade;
- duração máxima;
- randomização das questões e, opcionalmente, das opções;
- quantidade de questões apresentada;
- nota mínima e política de apresentação do feedback.

Ao iniciar uma tentativa, o backend calcula a política efetiva, aplica uma
eventual exceção individual e grava a política completa no snapshot da própria
tentativa. Alterações posteriores no curso ou na exceção não modificam tentativas
históricas. A randomização trabalha sobre uma cópia das questões e não altera o
snapshot da versão publicada.

Uma exceção pertence à matrícula e ao módulo, exige motivo e autor, e pode
alterar limite de tentativas, janela ou duração. Criar, atualizar e revogar uma
exceção é transacional e gera auditoria. Revisores continuam limitados ao seu
âmbito efetivo no backend. A interface administrativa apresenta a política e a
exceção ativa no detalhe da submissão.

A migração `20260926120000_add_versioned_assessment_policies.sql` é expansiva:
adiciona colunas aos módulos, uma tabela privada de exceções e a referência
opcional usada pela tentativa. Mantém os valores históricos, aplica padrões
compatíveis com o comportamento anterior e não recria tentativas. A migração foi
aplicada ao projeto Supabase principal em 27 de setembro de 2026, após autorização
explícita, e registada em `supabase_migrations.schema_migrations`.

A validação remota confirmou a versão `20260926120000`, as novas colunas, a
tabela de exceções e os privilégios mínimos `SELECT`, `INSERT` e `UPDATE` da role
`courseplatform_runtime`, sem privilégio `DELETE`. Após o deploy, em 28 de
setembro de 2026, os endpoints públicos de liveness e readiness responderam com
HTTP 200. Uma sessão administrativa real confirmou o editor das políticas
versionadas e o formulário de exceção individual no detalhe da submissão. Uma
sessão real de estudante confirmou o dashboard, a lista de cursos, o bloqueio
sequencial dos módulos, uma tentativa histórica aprovada e, numa aula ainda não
iniciada, a apresentação do limite de tentativas e da duração.

Em 28 de setembro de 2026, uma validação controlada com sessão administrativa
real criou uma exceção individual temporária, confirmou no detalhe da submissão
o limite de quatro tentativas, a duração de 45 minutos, a janela de 30 minutos e
o motivo, e revogou-a em seguida. A leitura direta posterior confirmou estado
`REVOKED`, zero exceções ativas e os eventos de auditoria de gravação e
revogação. Nenhuma tentativa de estudante foi iniciada durante o teste.

A migração de dados `20260928120000_repair_epg_course_metadata.sql` também foi
aplicada ao projeto principal em 28 de setembro de 2026. Ela corrigiu o título do
curso, a ordem e os títulos dos dois módulos importados, preservando IDs,
matrículas, progressos, tentativas e a versão publicada. O estado anterior ficou
guardado em `migration_reconciliation_issues` para rollback operacional. A
interface do estudante confirmou os metadados corrigidos. A versão publicada
continua sem conteúdos e questões; qualquer autoria posterior deve entrar numa
nova versão.

## Rascunho académico do curso EPG

A migração de dados `20260928133000_seed_epg_v2_draft_content.sql` prepara a
versão 2 do curso `COURSE-EPG-001`, sem alterar a versão 1 publicada. O rascunho
contém dois módulos sequenciais, oito unidades de conteúdo e dez questões, com
uma carga estimada total de 720 minutos. Cada avaliação vale 100 pontos, permite
duas tentativas, tem 60 minutos de duração e só apresenta feedback depois da
revisão.

O conteúdo cobre cronologia do setor, cadeia de valor, instituições,
infraestruturas de gás e GNL, regulação, valor nacional e transição energética.
As fontes anexadas ao snapshot são páginas institucionais do INP e a Estratégia
de Transição Energética publicada pelo MIREME. Questões discursivas incluem
rubricas de referência e as questões objetivas têm versões imutáveis no banco de
questões.

A migração é deliberadamente conservadora:

- recusa executar se existir outro rascunho para o curso;
- recusa colisões de identificadores ou conteúdo divergente numa repetição;
- cria as opções antes de publicar a versão da questão;
- não cria ofertas nem altera matrículas, progresso, tentativas ou certificados;
- mantém a versão do curso em `DRAFT`, marcada para revisão académica.

Em 28 de setembro de 2026, o rascunho recebeu revisão factual e pedagógica com
base em fontes institucionais do INP, MIREME e ENH. A revisão confirmou os marcos
históricos, os papéis institucionais e os quatro pilares da Estratégia de
Transição Energética, e atualizou a referência às Leis n.º 8/2026 e 9/2026.
A aprovação institucional, a publicação e a associação a uma oferta continuam a
ser decisões posteriores e separadas.

Após autorização explícita, a migração foi aplicada ao projeto Supabase
principal e registada no histórico remoto. A leitura posterior confirmou a
versão 2 em `DRAFT`, dois módulos, oito unidades de conteúdo, dez questões no
snapshot, dez versões publicadas no banco de questões e nenhuma oferta associada.
O contrato usado pelo editor administrativo foi validado diretamente sobre o
snapshot remoto: a validação de publicação não encontrou erros ou avisos e os
dados de pré-visualização e edição foram produzidos corretamente. A confirmação
visual no browser não foi automatizada porque o controlo de browser estava
indisponível; não houve publicação do curso.

## Aprovação institucional do rascunho

O editor administrativo separa agora três decisões: revisão do rascunho,
aprovação institucional e publicação. Para cursos cujo snapshot define
`academicReview.publicationApprovalRequired`, apenas proprietários e
administradores podem registar a aprovação institucional, mediante confirmação
explícita e observação obrigatória. A operação bloqueia a linha do rascunho,
verifica concorrência e valida novamente todo o snapshot antes de guardar a
decisão e o respetivo evento de auditoria. A repetição do mesmo pedido depois de
uma aprovação concluída é idempotente e não cria uma segunda decisão.

Qualquer edição, atualização a partir do editor ou associação de uma nova versão
de questão invalida automaticamente uma aprovação anterior. O backend recusa a
publicação enquanto a aprovação exigida estiver pendente ou invalidada; ocultar
o botão no frontend é apenas um reforço visual desse controlo. Cursos legados
sem a marca de aprovação obrigatória mantêm o comportamento anterior.

Esta alteração usa os metadados versionados de `content_snapshot_json` e não
exige migração de esquema. A publicação da versão 2 e a associação a uma oferta
ou turma permanecem ações posteriores, independentes e não executadas nesta
etapa.

## Rubricas e histórico de notas

Cada módulo pode definir até 30 critérios, com identificador, título, descrição
e pontuação máxima. A rubrica entra no snapshot imutável da tentativa. A revisão
exige todos os critérios, calcula a nota normalizada no backend e rejeita
critérios ausentes, desconhecidos, repetidos ou fora do limite. O valor enviado
pelo frontend não pode divergir do total calculado.

Cada revisão cria uma nova revisão e um registo imutável em
`courseplatform.grade_change_log`. Alterar uma decisão ou nota já registada exige
motivo. O detalhe da submissão apresenta a rubrica congelada e o histórico sem
reescrever avaliações anteriores.

## Pauta e conclusão

A pauta administrativa consolida estudante, curso, versão, edição/turma, grupo,
progresso, nota final e estado de conclusão. Usa paginação por cursor e aplica o
âmbito do revisor no backend antes de devolver os registos. A exportação CSV usa
somente a página já autorizada pela API.

O progresso é recalculado com o snapshot da versão associada à matrícula, nunca
com a estrutura viva do editor. A política versionada define os módulos
obrigatórios, a nota mínima e se todos precisam de aprovação. A matrícula guarda
o snapshot e o motivo da decisão de conclusão. Estados `BLOCKED`, `INACTIVE` e
`CANCELLED` não são reativados pelo recálculo.

## Calendário académico

O calendário pertence à edição/turma e guarda eventos normalizados com tipo,
início, fim, descrição e antecedência de aviso. Revisores podem ler apenas
calendários dentro do respetivo âmbito; apenas `ADMIN` e `OWNER` podem alterar.
Toda gravação bloqueia a edição, substitui o calendário numa transação e gera
auditoria. O painel do estudante mostra os próximos eventos da edição da própria
matrícula e usa avaliações/prazos futuros no resumo do próximo prazo.

`notifyBeforeMinutes` preserva a regra de antecedência necessária para avisos. O
disparo multicanal no instante calculado não ocorre dentro do pedido HTTP: será
consumido pelo worker durável da Etapa 13. Esta separação evita temporizadores
efémeros em funções Vercel e duplicação de notificações.

## Validação de release ainda necessária

- validar no painel do estudante o calendário e a conclusão com uma conta real;
- validar uma revisão por rubrica quando existir uma tentativa criada com o novo
  snapshot; tentativas históricas sem rubrica continuam compatíveis;
- confirmar desktop/mobile, consola, teclado e estados vazio/erro/carregamento;
- confirmar o backup e o plano de reversão operacional antes dos testes que
  alterem notas ou estados de conclusão.

Após o deploy de 28 de setembro de 2026, uma sessão administrativa real
confirmou a Pauta paginada, o Calendário académico por edição, a lista e o
detalhe das submissões, as respostas comparadas com o gabarito, os ficheiros
privados, o reenvio, as exceções individuais e os controlos administrativos.
Nenhuma nota, conclusão, exceção ou evento foi alterado. A tentativa histórica
inspecionada não possuía rubrica congelada, pelo que o formulário manteve o modo
legado esperado. A validação encontrou apenas precisão decimal excessiva numa
nota da Pauta; a interface passou a apresentar no máximo duas casas decimais,
sem arredondar ou reescrever o valor persistido ou exportado.

A produção de conteúdos de outros cursos, a aprovação institucional e a
associação de versões a novas ofertas continuam decisões académicas do produto;
não fazem parte da infraestrutura concluída nesta etapa.

## Reversão

Antes de aplicar a migração final, reverter a aplicação remove os novos controlos
sem impacto nos dados. Depois de aplicada, reverta primeiro a aplicação para uma
versão compatível e mantenha as tabelas e colunas aditivas. A remoção física do
banco de questões, das políticas, exceções ou histórico de notas exige uma
migração posterior, confirmação de ausência de leitores e backup validado.
