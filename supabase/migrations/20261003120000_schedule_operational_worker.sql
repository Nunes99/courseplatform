-- Etapa 13: agenda o executor duravel sem persistir credenciais no repositorio.

create schema if not exists extensions;

do $migration$
declare
  existing_job_id bigint;
begin
  -- Vanilla PostgreSQL used by restore rehearsals does not ship Supabase's
  -- pg_net/Vault stack. Keep the schema chain repeatable there while applying
  -- the scheduler on Supabase, where both extensions are available.
  begin
    execute 'create extension if not exists pg_net with schema extensions';
    execute 'create extension if not exists pg_cron';
  exception when others then
    raise notice 'Operational scheduler skipped: Supabase cron extensions are unavailable.';
    return;
  end;

  if to_regclass('vault.secrets') is null
     or to_regclass('vault.decrypted_secrets') is null then
    raise notice 'Operational scheduler skipped: Supabase Vault is unavailable.';
    return;
  end if;

  if not exists (
    select 1 from vault.secrets where name = 'courseplatform_platform_url'
  ) or not exists (
    select 1 from vault.secrets where name = 'courseplatform_job_runner_secret'
  ) then
    raise exception 'Operational scheduler secrets are missing from Supabase Vault.';
  end if;

  select jobid
  into existing_job_id
  from cron.job
  where jobname = 'courseplatform-operational-worker'
  limit 1;

  if existing_job_id is not null then
    perform cron.unschedule(existing_job_id);
  end if;

  perform cron.schedule(
    'courseplatform-operational-worker',
    '* * * * *',
    $worker$
      select net.http_post(
        url := rtrim((
          select decrypted_secret
          from vault.decrypted_secrets
          where name = 'courseplatform_platform_url'
        ), '/') || '/api/internal/jobs/run',
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || (
            select decrypted_secret
            from vault.decrypted_secrets
            where name = 'courseplatform_job_runner_secret'
          )
        ),
        body := jsonb_build_object('triggeredAt', now()),
        timeout_milliseconds := 55000
      ) as request_id;
    $worker$
  );
end
$migration$;
