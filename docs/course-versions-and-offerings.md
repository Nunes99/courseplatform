# Cursos, versões e ofertas

## Objetivo

Esta etapa separa quatro conceitos que anteriormente estavam concentrados em
`courses` e `groups`:

- `courses`: identidade estável do catálogo;
- `course_versions`: metadados e conteúdo publicados numa versão imutável;
- `course_offerings`: edição concreta, com período, capacidade, responsáveis e regras;
- `enrollments`: participação de um estudante numa oferta específica.

Um grupo organiza estudantes dentro de uma oferta. Não substitui a matrícula.

## Invariantes

1. Uma oferta aponta para exatamente uma versão publicada do mesmo curso.
2. Um estudante pode ter uma matrícula por oferta e várias matrículas no mesmo curso.
3. A versão de uma oferta não pode mudar depois de existir uma matrícula.
4. Uma versão publicada não pode ter conteúdo ou metadados alterados. Pode apenas ser arquivada.
5. Progresso, tentativas e nota pertencem à matrícula. Certificados e pedidos guardam também a matrícula, oferta e versão.
6. Um grupo pertence a uma oferta. A matrícula e o grupo devem pertencer à mesma oferta.
7. Relações históricas que não possam ser inferidas de forma única são registadas em `migration_reconciliation_issues`.

## Estratégia de migração

A migração `20260915173343_model_course_versions_and_offerings.sql` segue expansão,
backfill e validação:

1. cria as novas tabelas sem remover dados existentes;
2. captura cada curso atual numa versão 1 publicada, incluindo módulos, conteúdo, perguntas e opções;
3. cria uma oferta inicial determinística para cada curso;
4. liga grupos e matrículas à oferta inicial;
5. liga certificados e pedidos apenas quando existe uma matrícula histórica única;
6. regista casos ambíguos para reconciliação manual;
7. substitui a unicidade estudante/curso por estudante/oferta;
8. adiciona chaves estrangeiras, índices, RLS e privilégios mínimos da API.

Ao criar uma matrícula, a API inicializa de forma idempotente o progresso dos
módulos ativos presentes no snapshot da versão. Módulos sem pré-requisito ficam
disponíveis; módulos dependentes começam bloqueados. A oferta inicial migrada
não recebe uma capacidade presumida: permanece sem limite até configuração
explícita pela administração.

Os campos `course_id` e `group_id` existentes permanecem durante a fase de
compatibilidade. A sua remoção não faz parte desta etapa.

## Validação antes de produção

Execute primeiro numa base local ou de staging restaurada a partir de um backup
sanitizado. Confirme:

```sql
select entity_type, issue_code, count(*)
from courseplatform.migration_reconciliation_issues
where migration_key = '20260915101047' and status = 'OPEN'
group by entity_type, issue_code
order by entity_type, issue_code;
```

Compare também contagens de cursos, matrículas, progressos, tentativas,
certificados e pedidos antes e depois. Nenhum caso `OPEN` deve ser corrigido por
suposição; confirme a oferta correta com os dados operacionais.

Valide ainda que `certificate_id`, `certificate_number`, `verification_code`,
`template_snapshot_json`, contagens de download e estados permanecem iguais. A
nova referência composta impede que um certificado ou pedido seja ligado a uma
matrícula de outro estudante, curso, oferta ou versão.

## Compatibilidade e reversão

A aplicação anterior deixa de ser compatível quando a versão lógica do esquema
avança. Para reversão operacional, restaure primeiro a versão anterior da
aplicação. As novas tabelas e colunas podem permanecer sem afetar os dados
legados; não faça `DROP` durante o rollback de emergência.

Depois de um período de estabilidade e reconciliação completa, uma migração de
contrato futura poderá tornar obrigatórias as referências históricas ainda
opcionais e remover consultas por `student_id + course_id`.
