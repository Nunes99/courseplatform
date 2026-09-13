# Role Postgres de runtime

## Objetivo

A API deve ligar ao Postgres com `courseplatform_api`, e não com `postgres`.
A migração `20260913131500_create_courseplatform_runtime_role.sql` separa:

- `courseplatform_runtime`: role de grupo sem login que concentra privilégios;
- `courseplatform_api`: role de login, membro do grupo, criada sem palavra-passe ativa.

A role recebe apenas `CONNECT`, uso do esquema `courseplatform`, DML por tabela
e operação conforme as consultas atuais, e grants explícitos nas quatro funções
`pgcrypto` usadas pelo backend. Não recebe acesso às tabelas legadas sem uso,
sequências, privilégios automáticos sobre tabelas futuras, `SUPERUSER`,
`BYPASSRLS`, criação de roles/bases, `CREATE`, `TRUNCATE` nem DDL sobre o
esquema.

## Ordem de transição

1. Publicar primeiro a versão da API que não executa DDL em pedidos.
2. Aplicar a migração versionada com uma ligação administrativa controlada.
3. Confirmar os atributos, grants, policies e funções acessíveis à nova role.
4. Definir uma palavra-passe aleatória forte fora do Git e dos logs. Use um
   mecanismo interativo, como `\password courseplatform_api` no `psql`; não
   coloque a palavra-passe num ficheiro SQL ou argumento de linha de comandos.
5. Criar a URL do transaction pooler com o utilizador
   `courseplatform_api.PROJECT_REF` e a porta `6543`.
6. Alterar apenas o `DATABASE_URL` do ambiente Preview e publicar novamente.
7. Executar os testes de leitura e mutação listados abaixo.
8. Só depois de aprovação, repetir a troca em produção.

O processo web nunca deve receber a URL administrativa usada para migrações.

## Validação SQL

Execute com uma ligação administrativa. As consultas não contêm segredos:

```sql
select rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolinherit, rolreplication, rolbypassrls
from pg_roles
where rolname in ('courseplatform_runtime', 'courseplatform_api')
order by rolname;

select has_database_privilege('courseplatform_api', current_database(), 'connect') as can_connect,
       has_schema_privilege('courseplatform_api', 'courseplatform', 'usage') as can_use_schema,
       has_schema_privilege('courseplatform_api', 'courseplatform', 'create') as can_create;

select table_name,
       has_table_privilege('courseplatform_api', format('courseplatform.%I', table_name), 'select') as can_select,
       has_table_privilege('courseplatform_api', format('courseplatform.%I', table_name), 'insert') as can_insert,
       has_table_privilege('courseplatform_api', format('courseplatform.%I', table_name), 'update') as can_update,
       has_table_privilege('courseplatform_api', format('courseplatform.%I', table_name), 'delete') as can_delete,
       has_table_privilege('courseplatform_api', format('courseplatform.%I', table_name), 'truncate') as can_truncate
from information_schema.tables
where table_schema = 'courseplatform' and table_type = 'BASE TABLE'
order by table_name;
```

O resultado esperado é `can_connect=true`, `can_use_schema=true` e
`can_create=false`. Cada operação DML deve estar permitida apenas nas tabelas
listadas pela migração; `can_truncate` deve ser `false` em todas elas.

## Testes antes da produção

- `health`, login de estudante e login administrativo;
- leitura de cursos, módulos, perfil, submissões e certificados;
- atualização de perfil e progresso com utilizadores sintéticos;
- submissão/revisão de uma tentativa sintética;
- criação e leitura de notificações com campos encriptados;
- emissão e download de certificado sintético;
- Realtime do chat;
- tentativa negativa de `CREATE TABLE`, `ALTER TABLE`, `TRUNCATE`, leitura de
  esquemas privados e alteração de roles.

Os testes de mutação devem usar staging ou dados sintéticos dedicados. Não devem
ser executados diretamente sobre dados reais de produção.

## Reversão operacional

Se a Preview falhar, restaure o `DATABASE_URL` anterior e publique novamente
antes de alterar a role. Depois investigue o privilégio em falta e produza uma
nova migração; não conceda `SUPERUSER`, `BYPASSRLS` ou `ALL PRIVILEGES` como
atalho.

Para remover as roles numa reversão definitiva, primeiro restaure todas as APIs
para outra credencial, encerre conexões da role, remova as policies
`courseplatform_runtime_access`, revogue a associação e os grants, e só então
elimine `courseplatform_api` e `courseplatform_runtime`. Essa operação é
destrutiva e exige autorização própria.
