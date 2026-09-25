# Etapa 10: núcleo pedagógico

## Estado

Etapa iniciada. A primeira fatia implementa a barreira de qualidade da autoria
antes da publicação de uma versão de curso. Não declara concluídos o banco de
questões versionado, rubricas, pauta, calendário ou regras avançadas de
conclusão.

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

## Trabalho ainda pendente na Etapa 10

- configurar limites de tentativa, janela, tempo e randomização por avaliação;
- introduzir rubricas, pauta consolidada e histórico de alterações de notas;
- formalizar regras de conclusão, exceções individuais e calendário de prazos;
- validar o fluxo completo em Preview com contas administrativas reais.

## Reversão

Antes de aplicar a migração, reverter a aplicação remove o editor sem impacto nos
dados. Depois de aplicada, reverta primeiro a aplicação e mantenha as tabelas até
confirmar que nenhum rascunho referencia versões do banco; uma remoção física
exige uma migração posterior e backup validado.
