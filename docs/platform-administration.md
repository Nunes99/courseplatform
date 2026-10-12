# Administração global e onboarding institucional

## Estado da M4

A primeira fundação da M4 separa a administração global da administração de
cada instituição. Ela não cria nem ativa uma segunda instituição.

- `/platform` é um ponto de entrada independente de `/admin`.
- `platform_operators` concede explicitamente um papel global a uma identidade
  já verificada em `students`.
- `platform_sessions` não reutiliza tokens de estudante ou de staff.
- `organization_onboarding_requests` recebe candidaturas idempotentes.
- `READY_FOR_PROVISIONING` significa apenas que a análise terminou. A constraint
  desta fase impede associar o pedido a uma nova `organization`.
- `platform_audit_log` regista login e decisões de onboarding sem dados
  académicos dos tenants.

## Primeiro operador

A migração não promove automaticamente nenhum `OWNER` institucional. Depois de
aplicar a migração, um administrador da base deve conceder o primeiro papel
global a uma identidade existente e ativa, usando parâmetros e uma transação.
O procedimento deve ser executado fora dos pedidos HTTP e registado na mudança
operacional do ambiente.

Exemplo parametrizado para o procedimento controlado:

```sql
begin;

insert into courseplatform.platform_operators
  (operator_id, student_id, operator_role, status)
select :operator_id, student_id, 'GLOBAL_OWNER', 'ACTIVE'
from courseplatform.students
where lower(email) = lower(:verified_operator_email)
  and status = 'ACTIVE'
on conflict (student_id) do nothing;

commit;
```

Não substitua os parâmetros por credenciais em ficheiros versionados. Confirme
que exatamente uma linha foi selecionada antes do `commit`.

## Aplicação controlada

1. Criar backup e confirmar a versão atual do esquema.
2. Aplicar `20261012120000_add_platform_onboarding_foundation.sql` pelo processo
   normal de migrações.
3. Confirmar `schema_versions.application = 20261012120000`.
4. Publicar o backend compatível.
5. Conceder o primeiro operador pelo procedimento acima.
6. Validar login em `/platform`, leitura do dashboard, submissão idempotente e
   transições de onboarding.
7. Confirmar que um `OWNER` institucional sem linha em `platform_operators`
   recebe credenciais globais inválidas.

## Rollback operacional

O rollback da aplicação deve voltar para a versão anterior antes de remover as
novas tabelas. As tabelas são aditivas e podem permanecer sem utilização. Não
elimine candidaturas ou auditoria durante um rollback emergencial. A remoção
física, se algum dia for necessária, deve ser uma migração separada após exportar
e validar os dados.
