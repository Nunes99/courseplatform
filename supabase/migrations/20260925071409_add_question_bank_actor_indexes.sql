-- Índices de suporte para as chaves estrangeiras administrativas do banco de questões.
-- Não altera dados nem a versão mínima exigida pela aplicação.

set lock_timeout = '5s';
set statement_timeout = '120s';

create index if not exists idx_question_bank_items_created_by
  on courseplatform.question_bank_items(created_by)
  where created_by is not null;

create index if not exists idx_question_bank_versions_created_by
  on courseplatform.question_bank_versions(created_by)
  where created_by is not null;

create index if not exists idx_question_bank_versions_published_by
  on courseplatform.question_bank_versions(published_by)
  where published_by is not null;
