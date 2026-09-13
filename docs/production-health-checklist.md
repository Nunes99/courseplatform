# Checklist de produção

Esta checklist não autoriza deploy nem migração. Use-a somente depois de validar
staging e obter autorização explícita para produção.

## Endpoints

- `/health/live` deve responder `200` com `{"status":"ok"}` mesmo que o Postgres esteja indisponível.
- `/health/ready` deve responder `200` com `{"status":"ready"}`.
- `/api/index?action=health` deve devolver apenas o estado mínimo legado.
- `/health/diagnostics` sem `X-Admin-Token` deve responder `401`.

Readiness `503` significa dependência indisponível ou versão de esquema
incompatível. Consulte logs protegidos e o diagnóstico administrativo; o health
público deliberadamente não mostra host, SQL, contagens ou configuração.

## Banco e migrações

1. Confirme que `DATABASE_URL` usa `courseplatform_api` no runtime.
2. Confirme que uma credencial administrativa separada está disponível somente ao operador de migração.
3. Faça backup e teste restauração.
4. Compare históricos com `supabase migration list --linked`.
5. Reveja `supabase db push --linked --include-all --dry-run`.
6. Aplique apenas com autorização e seguindo [database-migrations.md](database-migrations.md).
7. Confirme que `courseplatform.schema_versions` contém a versão esperada pela aplicação.

Nunca execute `supabase/schema.sql` nem o snapshot empacotado para reparar um
pedido HTTP. A API não cria nem altera o esquema automaticamente.

## Validação funcional

Depois da migração e antes de promover o frontend/backend:

- login e recuperação de estudante;
- login e recuperação administrativa;
- cursos, módulos e progresso;
- submissão, revisão e reenvio autorizado;
- emissão, pagamento, visualização e download de certificados;
- chat por polling e Realtime;
- upload e download privados;
- logout e expiração de sessão.

Use apenas contas sintéticas autorizadas. Registe resultados e tempos; não trate
um health `200` como prova de que todos os fluxos funcionam.
