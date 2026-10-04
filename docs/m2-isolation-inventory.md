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
| Estudantes e staff | Consultas locais corrigidas e testes unitários passam | Aguarda novo deployment e repetição A/B |

As fixtures A/B e a sessão administrativa temporária são eliminadas no bloco
`finally` do verificador. Nenhuma segunda organização permanente é criada.

## Operações globais intencionais

As configurações SMTP, Push/VAPID, Telegram, WhatsApp, templates de transporte
e cursores de consumidores são infraestrutura da plataforma. Permanecem
globais e não podem ser expostas a administradores institucionais. A futura
administração global deve ser o único contexto autorizado a alterá-las.

## Bloqueios para a segunda instituição

1. Publicar as correções de estatísticas, estudantes e staff e executar
   `scripts/validate_m2_cross_tenant.py --apply` até terminar com
   `m2_cross_tenant_validation=passed cleanup=passed`.
2. Adicionar `organization_id` ao `audit_log`, fazer backfill sem perder o
   histórico e exigir tenant explícito em toda nova escrita de auditoria.
3. Criar projeções públicas próprias para organização e catálogo. As ações
   legadas `publicCourseConfig` e `getMediaConfig` aceitam um `courseId` ativo,
   mas não representam uma política editorial de agregador, slug institucional
   ou publicação pública.
4. Remover os defaults temporários de `organization_id` em `notifications`,
   `push_subscriptions`, `telegram_link_tokens`, `chat_rooms` e
   `chat_presence` por migração compensatória, depois do deployment compatível.
5. Executar as cinco integrações PostgreSQL ignoradas pela suíte numa base
   descartável para confirmar a cadeia completa de migrações e os triggers.

## Critério de encerramento

M2 só pode ser marcada como concluída quando todos os bloqueios acima estiverem
resolvidos e os testes negativos A/B confirmarem que A não lê, altera,
descarrega, reclama ou audita registos de B. M3, o cadastro institucional e o
agregador podem ser desenvolvidos depois desse gate, sem ativar ainda um segundo
tenant permanente.
