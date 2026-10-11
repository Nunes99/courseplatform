# Inventário de isolamento M2

Data de revisão: 5 de outubro de 2026.

Este documento é o gate técnico antes de ativar uma segunda instituição. Ele
distingue comportamento verificado, compatibilidade transitória e trabalho que
ainda bloqueia o encerramento da M2.

## Verificado

| Área | Evidência | Estado |
| --- | --- | --- |
| Aprendizagem e avaliações | Contexto da sessão, curso, matrícula, tentativa, revisão e exceções validam `organization_id`; testes A/B automatizados | Isolada |
| Catálogo privado, ofertas, grupos e matrículas | Mutações em lote validam curso/oferta/grupo e memberships antes da escrita | Isolada |
| Certificados | Leitura, emissão, PDF, downloads, gestão e Storage resolvem a organização pelo curso | Isolada |
| Pagamentos e comprovativos | Pedido, revisão, eliminação, upload e download validam curso e proprietário | Isolada |
| Inquéritos | Configuração e listagem recusam cursos externos; teste A/B real passou | Isolada |
| Notificações | Listas e destinatários usam tenant; teste A/B real passou | Isolada |
| Chat e Realtime | Sala, presença e autorização de tópico usam tenant; testes A/B de lista e leitura passaram | Isolada |
| Retry de entregas | Retry administrativo reclama apenas notificações do tenant ativo; teste A/B real passou | Isolada |
| Estudantes e staff | Consultas corrigidas, publicadas e validadas por API e navegador | Isolada |
| Auditoria persistida | `organization_id`, âmbito explícito, constraints validadas e zero registos inválidos no pós-flight | Aplicada e validada |
| Projeção pública institucional | Perfil e catálogo públicos responderam em Preview e produção sem campos internos | Aplicada e validada |
| Defaults de comunicação | Os cinco defaults transitórios foram removidos; pós-flight confirmou zero defaults restantes | Aplicada e validada |

As fixtures A/B e a sessão administrativa temporária são eliminadas no bloco
`finally` do verificador. Nenhuma segunda organização permanente é criada.

## Operações globais intencionais

As configurações SMTP, Push/VAPID, Telegram, WhatsApp, templates de transporte
e cursores de consumidores são infraestrutura da plataforma. Permanecem
globais e não podem ser expostas a administradores institucionais. A futura
administração global deve ser o único contexto autorizado a alterá-las.

## Risco residual aceite

Os cinco testes PostgreSQL destrutivos continuam sem execução. Em 5 de outubro
de 2026, foi decidido avançar para a M3 sem esses testes. Eles permanecem
registados como risco residual e só podem ser executados numa base descartável;
nunca devem ser apontados para produção.

`20261004213604_complete_m2_tenant_isolation.sql` foi aplicada em 5 de outubro
de 2026. O pós-flight confirmou a versão, três colunas públicas, zero auditorias
inválidas, zero defaults transitórios e zero constraints não validadas. O
deployment de produção `dpl_R7t4HZjcgEsp8UczMNhuMSWqb1nE` ficou `Ready`, com
liveness, readiness, perfil, catálogo e página administrativa saudáveis.

A suíte local terminou com 453 testes aprovados e cinco integrações PostgreSQL
ignoradas. Esta máquina não possui Docker ativo nem uma instância PostgreSQL
local. Em 5 de outubro de 2026, o gate A/B foi executado em produção com
autorização explícita e fixtures sintéticas temporárias. Passaram as negações e
o isolamento de inquéritos, notificações, chat, entregas, estudantes, staff e
estatísticas administrativas. A limpeza automática terminou com sucesso e uma
consulta independente confirmou `synthetic_rows_remaining=0`.

## Critério de encerramento

M2 foi encerrada operacionalmente em 5 de outubro de 2026 com o risco residual
acima explicitamente aceite. O gate negativo A/B confirmou que A não lê,
altera, descarrega ou reclama os registos B cobertos pelo verificador. A M3
pode avançar, mas uma segunda instituição permanente continua dependente dos
gates próprios das fases seguintes.
