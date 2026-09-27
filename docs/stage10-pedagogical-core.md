# Etapa 10: núcleo pedagógico

## Estado

Etapa em desenvolvimento. Estão implementados a barreira de qualidade da
autoria, o banco de questões versionado e as regras versionadas das avaliações.
Não estão concluídos rubricas, pauta, calendário académico ou regras avançadas
de conclusão.

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

Esta migração está preparada localmente e ainda não foi aplicada ao Supabase.
Antes de publicação, um responsável académico deve rever factos, linguagem,
fontes, adequação das rubricas e nível de dificuldade. A publicação e a associação
a uma oferta devem ser decisões posteriores e separadas.

## Trabalho ainda pendente na Etapa 10

- introduzir rubricas, pauta consolidada e histórico de alterações de notas;
- formalizar regras de conclusão e calendário académico consolidado;
- validar numa conta de estudante uma exceção individual ativa durante a janela,
  sem iniciar nem alterar uma tentativa histórica;
- produzir conteúdos e questões para o segundo curso, agora com metadados
  reparados, antes de o considerar pedagogicamente publicável. O rascunho técnico
  está preparado, mas ainda depende de revisão académica e aplicação autorizada.

## Reversão

Antes de aplicar as migrações, reverter a aplicação remove os novos controlos sem
impacto nos dados. Depois de aplicadas, reverta primeiro a aplicação e mantenha as
tabelas e colunas aditivas. A remoção física do banco de questões, das políticas
ou das exceções exige uma migração posterior, confirmação de ausência de leitores
e backup validado.
