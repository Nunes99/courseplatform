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

Esta fatia não altera o esquema nem reescreve versões publicadas. O rascunho
guarda uma cópia independente no campo `content_snapshot_json`, já existente.
Atualizá-lo substitui apenas essa cópia e regista `COURSE_VERSION_DRAFT_REFRESHED`
na auditoria. As ofertas, matrículas, progressos, tentativas e certificados
existentes permanecem inalterados.

## Trabalho ainda pendente na Etapa 10

- oferecer edição direta do snapshot do rascunho, além da atualização integral
  e explícita a partir das tabelas de trabalho;
- ordenar módulos e conteúdos com uma operação transacional explícita;
- versionar e reutilizar um banco de questões;
- configurar limites de tentativa, janela, tempo e randomização por avaliação;
- introduzir rubricas, pauta consolidada e histórico de alterações de notas;
- formalizar regras de conclusão, exceções individuais e calendário de prazos;
- validar o fluxo completo em Preview com contas administrativas reais.

## Reversão

Reverter a aplicação remove a nova pré-visualização e a validação de publicação.
Não existe rollback de banco para esta fatia porque nenhuma migração foi criada.
