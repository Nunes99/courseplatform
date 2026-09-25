# Validação das Etapas 3, 4, 6, 8 e 9

Data da revisão: 25 de setembro de 2026.

Este documento separa evidência automática, diagnóstico somente leitura em
produção e validação manual com contas reais. Nenhum teste destrutivo foi
executado na base normal.

## Estado resumido

| Etapa | Evidência automática e de dados | Validação operacional |
| --- | --- | --- |
| 3 - Supabase, RLS e views | Concluída para RLS e papéis atuais | Estudante, revisor e proprietário validados; âmbito fino do revisor ainda não existe |
| 4 - Migrações e health checks | Concluída localmente e reconciliada com o histórico remoto | Concluída em produção |
| 6 - Storage privado | Backfill e reconciliação concluídos | Encerrada: estudante, revisor e proprietário validados com ficheiros privados reais; comprovativo recusado ao revisor |
| 8 - Domínios e rotas tipadas | Suíte e verificadores de compatibilidade concluídos | Leituras reais de estudante, revisor e proprietário concluídas |
| 9 - Catálogo, versões e turmas | Esquema, vínculos e interface sintética validados | Leitura do estudante e gestão do proprietário concluídas |

Uma etapa só deve ser marcada como operacionalmente encerrada depois de todos
os itens da sua coluna pendente serem confirmados.

## Evidência de produção somente leitura

### Etapa 3

- 47 tabelas do esquema `courseplatform`; todas com RLS ativo.
- 32 views de compatibilidade no esquema `public`; nenhuma sem
  `security_invoker` e nenhuma concessão indevida às roles cliente.
- Nenhuma role cliente lê as tabelas privadas verificadas.
- Os buckets `courseplatform-submissions` e
  `courseplatform-payment-receipts` existem e são privados.
- Não existem policies de Storage que concedam acesso direto às roles cliente;
  uploads e downloads passam pela API autorizada.
- `courseplatform_api` existe sem `SUPERUSER`, `CREATEDB`, `CREATEROLE`,
  `REPLICATION` ou `BYPASSRLS`.
- `chat_realtime_topic_allowed` só permite `EXECUTE` a `authenticated` entre
  as roles cliente verificadas.

O Security Advisor não encontrou exposição por RLS. O aviso restante é a
proteção de palavras-passe comprometidas do Supabase Auth desativada; a
autenticação atual da plataforma usa o domínio próprio com bcrypt, portanto o
aviso não altera o fluxo atual. Deve ser reavaliado se a identidade for migrada
para Supabase Auth.

### Etapa 4

- Na validação encerrada, a base reportava a versão de aplicação
  `20260921120000`, então igual a `EXPECTED_SCHEMA_VERSION`. A implementação
  posterior de âmbitos de revisor elevou o contrato local para `20260925120000`;
  a respetiva migração continua pendente até ser aplicada com autorização.
- O histórico remoto contém as 15 migrações esperadas.
- Os três timestamps locais divergentes foram alinhados aos identificadores
  remotos sem alterar o SQL, os dados ou as chaves internas de reconciliação.
- A role de runtime e os endpoints não possuem caminho de reparação automática
  do esquema durante pedidos normais.

Os quatro testes PostgreSQL de integração permanecem intencionalmente
ignorados sem `COURSEPLATFORM_TEST_DATABASE_URL`: criam e alteram esquemas e o
próprio teste recusa uma URL que não seja local e identificada como teste. Não
devem ser apontados para produção.

### Etapa 6

- 78 registos históricos foram examinados.
- 73 trabalhos e 4 comprovativos estão prontos no Storage privado.
- Foram encontrados exatamente 73 objetos no bucket de trabalhos e 4 no bucket
  de comprovativos.
- Objetos ausentes: 0.
- Eventos de auditoria do backfill: 77.
- O dry-run atual não encontrou ficheiros elegíveis, falhas ou cópias pendentes.
- Os 77 Base64 originais continuam preservados para rollback operacional.

A remoção gradual dos Base64 só pode ser preparada depois dos downloads reais,
backup confirmado e período de estabilidade acordado.

### Etapa 9

- Cursos: 2; versões: 2; versões publicadas: 2; edições/turmas: 2.
- Matrículas: 195; sem contexto histórico: 0; divergências de contexto: 0.
- Certificados com contexto histórico: 11; sem contexto: 0.
- Problemas de reconciliação abertos: 0.
- Constraints e triggers obrigatórios da modelação de versões e edições estão
  presentes.

## Testes automáticos executados

```text
python -m unittest tests.test_supabase_access_hardening
  tests.test_runtime_database_role
  tests.test_schema_migrations_and_health
  tests.test_migration_postgres_integration
  tests.test_private_storage
  tests.test_stage8_modular_monolith
  tests.test_typed_api_routes
  tests.test_course_versions_offerings -v

Resultado: 111 testes OK; 4 ignorados por exigirem uma base PostgreSQL local
descartável.
```

```text
python -m unittest discover -s tests -p "test_*.py" -v

Resultado: 286 testes OK; 4 ignorados pela mesma razão.
```

Verificadores do frontend concluídos:

- sincronização entre `public/` e `backend/courseplatform/static/`;
- sete leituras tipadas e respetivos fallbacks legados;
- dashboard do estudante e estados de erro;
- listas administrativas em desktop e mobile;
- atribuição de staff;
- versões e edições de cursos em desktop e mobile.

Depois da validação real, foram corrigidas tanto a visualização pós-revisão
como a visualização compacta de aula aprovada, para manter os ficheiros
próprios da tentativa acessíveis ao estudante em modo somente leitura. O
verificador de avaliações confirmou ambos os fluxos em desktop e mobile, com
um botão `Abrir`, um botão `Baixar`, ausência de `Eliminar`, ausência de
overflow e consola limpa. Os 29 testes de Storage privado também passaram.
Após o deploy, um estudante real abriu a própria tentativa aprovada e o
ficheiro privado foi entregue numa URL `blob:` criada a partir da resposta
autenticada.

A primeira publicação confirmou que a rota individual da aula podia ser
aberta sem o `activeAttempt` presente no estado restaurado do dashboard. A
leitura tipada da aula passou a devolver explicitamente a tentativa mais
recente e o frontend usa esse valor como fallback antes de consultar os
ficheiros. Um teste de regressão cobre agora a navegação direta para uma aula
aprovada. Dois testes adicionais confirmam o isolamento da matrícula pela
identidade autenticada, a limpeza do estado entre contas e a prioridade da
tentativa devolvida pela API.

## Validação manual com contas reais

Use contas que já existam e não altere dados apenas para testar.

Execução de 24 e 25 de setembro de 2026:

- estudante: dashboard, dois cursos matriculados, lista de atividades e
  certificações próprias carregaram sem alerta visível;
- proprietário: dashboard, submissões, respostas, gabarito autorizado,
  catálogo, versão publicada, edição e matrículas carregaram;
- Storage: um trabalho submetido e um comprovativo de pagamento foram abertos
  com sucesso por URLs `blob:` criadas a partir da resposta autenticada;
- estudante: depois do deploy, a aula aprovada apresentou apenas os ficheiros
  da própria tentativa em modo somente leitura, com ações `Abrir` e `Baixar` e
  sem ação de eliminação;
- certificados: lista, pedidos, condições de pagamento e configuração por
  curso carregaram na administração;
- revisor: login administrativo com a identidade normal, leitura de submissões,
  respostas e gabarito e abertura de um trabalho privado foram confirmados;
- identidade unificada: a mesma conta manteve simultaneamente uma sessão de
  estudante e uma sessão administrativa `REVIEWER`; a área do estudante exibiu
  apenas o curso da própria matrícula;
- revisor: Staff e Credenciais não foram apresentados; o backend recusou a
  abertura de comprovativo de pagamento e nenhum objeto foi devolvido;
- nenhuma ação de escrita foi executada durante a validação.

As sessões e conteúdos usados no teste não são identificados neste documento.

### Estudante

1. [confirmado] Entrar na área do estudante e confirmar que home, cursos e
   media carregam.
2. [confirmado] Abrir um trabalho próprio no Storage numa aula aprovada; a
   resposta autenticada criou uma URL `blob:` funcional em produção.
3. [confirmado] A API restringe matrícula, tentativa e ficheiro pelo estudante
   autenticado. O teste de regressão recusa o ficheiro de outro estudante e as
   duas sessões reais observadas apresentaram somente a tentativa da própria
   conta.
4. [confirmado] Abrir certificados próprios e confirmar que cursos não
   matriculados não aparecem.

### Revisor

1. [confirmado] Entrar com as mesmas credenciais da conta normal nas áreas de
   estudante e administração, mantendo as duas sessões ativas.
2. [limitação conhecida] O revisor lê submissões e cursos, mas a plataforma
   ainda não modela atribuições por curso/grupo; o âmbito atual é global.
3. [confirmado] Abrir um trabalho autorizado.
4. [confirmado] Staff e Credenciais ficaram ocultos e o comprovativo foi
   recusado pelo backend.

### Administrador ou proprietário

1. [confirmado] Abrir dashboard, cursos, submissões e certificados.
2. [confirmado] Abrir um trabalho e um comprovativo autorizados.
3. [confirmado parcialmente] Confirmar versões e edições; a atribuição de staff
   já é coberta pelo verificador automatizado e não foi alterada em produção.
4. [confirmado] O diagnóstico sem sessão administrativa foi recusado sem expor
   host, URL de base, SQL ou credenciais.

### Health checks

1. [confirmado] `GET /health/live` respondeu com `{"status":"ok"}`.
2. [confirmado] `GET /health/ready` respondeu com `{"status":"ready"}`.
3. [confirmado] `GET /health/diagnostics` sem token foi recusado com
   `ADMIN_SESSION_REQUIRED`, sem revelar detalhes internos.

Registe apenas resultado, papel e data. Não guarde tokens, emails, nomes, URLs
com credenciais ou respostas privadas neste documento.

## Pendências não bloqueantes

- O Performance Advisor reporta foreign keys ainda sem índice e uma policy de
  Realtime que pode evitar uma otimização de plano. São melhorias de desempenho
  e devem receber migração própria; não representam uma falha de isolamento
  observada nesta validação.
- O bucket opcional de recursos gráficos de certificados ainda não existe; só
  deve ser criado quando esse upload for efetivamente ativado.
- A página de certificados ainda mostra ao revisor controlos de escrita. O
  backend recusa as operações, portanto não houve falha de autorização, mas os
  controlos devem ser ocultados para consistência e melhor experiência.
- No primeiro carregamento da área do estudante após o login duplo, a API teve
  uma falha transitória e a página permaneceu no estado de carregamento. Um
  recarregamento concluiu dashboard e cursos sem novo erro. Deve ser acompanhado
  nos logs e tratado como resiliência/observabilidade, não como falha de login.

## Limitação que impede âmbito fino de revisão

O papel `REVIEWER` continua global. Não existe ainda uma relação versionada que
associe o membro de staff a cursos, edições, grupos ou filas de revisão. Por
isso, não é possível provar isolamento entre dois âmbitos de revisão: a lista
real apresentou todas as submissões visíveis ao papel. A correção exige uma
migração aditiva, autorização no backend e filtros em todas as consultas de
revisor; ocultar registos no frontend não é suficiente.
