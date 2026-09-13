-- Etapa 2: contratos seguros de avaliação e versão imutável por tentativa.
-- Ordem de rollout: aplicar esta migração em staging/produção antes de publicar
-- a versão da API que grava e lê assessment_snapshot_json.
-- Rollback operacional: voltar a versão da API e conservar estas colunas
-- aditivas. Não remover snapshots durante rollback, pois preservam o histórico.

alter table courseplatform.lessons
  add column if not exists feedback_release_mode text not null default 'AFTER_REVIEW',
  add column if not exists show_correct_answers boolean not null default false,
  add column if not exists show_explanations boolean not null default false;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'courseplatform.lessons'::regclass
      and conname = 'lessons_feedback_release_mode_check'
  ) then
    alter table courseplatform.lessons
      add constraint lessons_feedback_release_mode_check
      check (feedback_release_mode in ('NEVER', 'AFTER_SUBMISSION', 'AFTER_REVIEW'))
      not valid;
  end if;
end
$$;

alter table courseplatform.lessons
  validate constraint lessons_feedback_release_mode_check;

alter table courseplatform.attempts
  add column if not exists objective_score numeric,
  add column if not exists assessment_snapshot_json jsonb not null default '{}'::jsonb;

with question_snapshots as (
  select
    q.lesson_id,
    q.question_id,
    q.question_order,
    jsonb_build_object(
      'question_id', q.question_id,
      'lesson_id', q.lesson_id,
      'question_order', q.question_order,
      'question_type', q.question_type,
      'prompt', q.prompt,
      'points', q.points,
      'correct_answer', q.correct_answer,
      'explanation', q.explanation,
      'is_required', q.is_required,
      'status', q.status,
      'options', coalesce((
        select jsonb_agg(
          jsonb_build_object(
            'option_id', qo.option_id,
            'question_id', qo.question_id,
            'option_order', qo.option_order,
            'option_label', qo.option_label,
            'option_text', qo.option_text,
            'is_correct', qo.is_correct
          ) order by qo.option_order
        )
        from courseplatform.question_options qo
        where qo.question_id = q.question_id
      ), '[]'::jsonb)
    ) as question_json
  from courseplatform.questions q
  where coalesce(q.status, 'ACTIVE') = 'ACTIVE'
), lesson_snapshots as (
  select
    l.lesson_id,
    jsonb_build_object(
      'version', 1,
      'source', 'legacy-backfill',
      'feedbackPolicy', jsonb_build_object(
        'releaseMode', l.feedback_release_mode,
        'showCorrectAnswers', l.show_correct_answers,
        'showExplanations', l.show_explanations
      ),
      'questions', coalesce(
        jsonb_agg(qs.question_json order by qs.question_order)
          filter (where qs.question_id is not null),
        '[]'::jsonb
      )
    ) as snapshot_json
  from courseplatform.lessons l
  left join question_snapshots qs on qs.lesson_id = l.lesson_id
  group by l.lesson_id, l.feedback_release_mode, l.show_correct_answers, l.show_explanations
)
update courseplatform.attempts a
set assessment_snapshot_json = ls.snapshot_json || jsonb_build_object(
      'capturedAt', coalesce(a.started_at, a.created_at, now())
    )
from lesson_snapshots ls
where ls.lesson_id = a.lesson_id
  and (a.assessment_snapshot_json is null or a.assessment_snapshot_json = '{}'::jsonb);

do $$
declare
  constraint_name text;
begin
  for constraint_name in
    select c.conname
    from pg_constraint c
    join pg_attribute a
      on a.attrelid = c.conrelid
     and a.attnum = any(c.conkey)
    where c.conrelid = 'courseplatform.answers'::regclass
      and c.contype = 'f'
      and a.attname = 'question_id'
  loop
    execute format(
      'alter table courseplatform.answers drop constraint %I',
      constraint_name
    );
  end loop;

  alter table courseplatform.answers
    add constraint answers_question_id_fkey
    foreign key (question_id)
    references courseplatform.questions(question_id)
    on delete restrict;
end
$$;

comment on column courseplatform.lessons.feedback_release_mode is
  'Momento em que o feedback pode ser divulgado: NEVER, AFTER_SUBMISSION ou AFTER_REVIEW.';
comment on column courseplatform.attempts.objective_score is
  'Percentagem interna calculada pelo backend apenas para questões objetivas.';
comment on column courseplatform.attempts.assessment_snapshot_json is
  'Versão imutável das questões, opções, gabarito e política associada à tentativa.';
