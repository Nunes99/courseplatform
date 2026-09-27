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
`courseplatform_runtime`, sem privilégio `DELETE`. O deploy correspondente da
aplicação e os testes com contas reais continuam pendentes.

## Trabalho ainda pendente na Etapa 10

- introduzir rubricas, pauta consolidada e histórico de alterações de notas;
- formalizar regras de conclusão e calendário académico consolidado;
- validar o fluxo completo em Preview com contas administrativas reais.

## Reversão

Antes de aplicar as migrações, reverter a aplicação remove os novos controlos sem
impacto nos dados. Depois de aplicadas, reverta primeiro a aplicação e mantenha as
tabelas e colunas aditivas. A remoção física do banco de questões, das políticas
ou das exceções exige uma migração posterior, confirmação de ausência de leitores
e backup validado.
