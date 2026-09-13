-- Etapa 4: DDL anteriormente executado no caminho dos pedidos.
-- Migração expansiva e repetível; não remove dados de negócio.

alter table courseplatform.lessons add column if not exists submission_duration_minutes integer;
alter table courseplatform.lesson_progress add column if not exists content_access_status text;
alter table courseplatform.lesson_progress add column if not exists evaluation_status text;
alter table courseplatform.attempts add column if not exists retry_authorized boolean not null default false;
update courseplatform.lesson_progress
set content_access_status = case when status = 'LOCKED' then 'LOCKED' else 'AVAILABLE' end
where content_access_status is null;
update courseplatform.lesson_progress
set evaluation_status = case
  when status in ('IN_PROGRESS', 'UNDER_REVIEW', 'CORRECTION_REQUIRED', 'APPROVED', 'FAILED', 'TIME_EXCEEDED') then status
  else 'NOT_STARTED'
end
where evaluation_status is null;
alter table courseplatform.lesson_progress alter column content_access_status set default 'LOCKED';
alter table courseplatform.lesson_progress alter column evaluation_status set default 'NOT_STARTED';
create index if not exists idx_progress_access_evaluation
  on courseplatform.lesson_progress(content_access_status, evaluation_status);
