# Instruções para o agente: evolução gradual da CoursePlatform para LMS

Este documento transforma a [auditoria técnica](C:/Users/manyu/Documents/GitHub/courseplatform/docs/auditoria-lms-2026-09-12.md) numa sequência de tarefas executáveis. Envie ao agente primeiro a **Instrução-mestra** e, depois, **apenas uma etapa de cada vez**, pela ordem indicada.

Não peça a execução de todas as etapas numa única tarefa. Cada etapa deve terminar com código verificado, documentação atualizada e um resumo claro antes de iniciar a seguinte.

## Instrução-mestra

Copie este bloco para o início de toda tarefa enviada ao agente:

```text
Trabalhe no projeto CoursePlatform localizado no workspace atual.

Objetivo geral: transformar gradualmente a plataforma numa LMS segura, modular, escalável e profissional, preservando todos os estudantes, matrículas, progressos, tentativas, avaliações, ficheiros, pagamentos e certificados já existentes.

Regras obrigatórias:
1. Leia primeiro docs/auditoria-lms-2026-09-12.md e inspecione o estado atual do código relacionado com esta tarefa. Não suponha que o relatório ainda corresponde exatamente ao código: confirme antes de editar.
2. Verifique git status antes de começar. Preserve todas as alterações existentes que não tenham sido feitas por si. Não reverta, apague ou reescreva trabalho do utilizador.
3. Limite as alterações ao objetivo desta etapa. Não faça uma reescrita geral, não introduza microserviços e não altere o design ou domínios não relacionados.
4. Mantenha compatibilidade com a arquitetura atual em Python/FastAPI, Supabase/Postgres e frontend existente, salvo quando esta etapa indicar explicitamente uma transição.
5. Nunca inclua senhas, tokens, chaves Supabase, URLs com credenciais ou dados pessoais reais no código, testes, logs, documentação ou resposta. Não leia nem mostre segredos sem necessidade.
6. Não execute migrações, resets, uploads, eliminações, alterações de permissões ou testes destrutivos na produção. Prepare scripts versionados e valide-os num ambiente local/staging. Peça autorização explícita antes de qualquer ação externa ou deploy.
7. Toda alteração de banco deve usar uma migração versionada, repetível quando apropriado, com estratégia de compatibilidade e rollback operacional. Não execute CREATE ou ALTER durante pedidos normais da API.
8. Preserve IDs e relações históricas. Não recrie estudantes nem certificados para simplificar uma migração. Alterações estruturais devem usar expansão, backfill, validação e só depois remoção de estruturas antigas.
9. Aplique autorização no backend. Ocultar botões ou campos no frontend não é controlo de acesso.
10. Para cada mutação, considere transações, concorrência, idempotência, auditoria, repetição de pedido e mensagens de erro seguras.
11. Antes de editar, explique sucintamente o que será alterado. Depois implemente a solução completa dentro do escopo; não pare numa proposta.
12. Adicione ou atualize testes proporcionais ao risco. Execute a suíte relevante e a suíte completa. Para UI, valide desktop e mobile, consola, teclado, estados de carregamento/erro/vazio e ausência de sobreposição.
13. Não declare desempenho, segurança, acessibilidade ou escalabilidade sem medição. Diferencie claramente testes locais, staging e produção.
14. Não faça deploy nem commit, a menos que isso seja solicitado explicitamente. Deixe o worktree pronto para revisão.

Formato obrigatório da entrega:
- Resultado implementado.
- Ficheiros alterados e motivo.
- Migrações e impacto nos dados.
- Testes executados com resultado exato.
- Riscos ou verificações que dependem de staging/produção.
- Próxima etapa recomendada, sem a executar.

Se encontrar um bloqueio, investigue alternativas seguras. Pare apenas quando faltar uma decisão do utilizador, acesso externo ou autorização para uma ação com impacto real. Nesse caso, descreva precisamente o bloqueio e não improvise dados ou credenciais.
```

## Etapa 0: criar uma linha de base verificável

```text
Execute apenas a Etapa 0: estabelecer a linha de base técnica antes das correções.

Objetivos:
- Inventariar os pontos de entrada da API, ações públicas, ações de estudante, ações administrativas, tabelas, views, Storage e tarefas em segundo plano.
- Executar a suíte atual sem tocar em produção e registar os resultados.
- Identificar as variáveis necessárias pelo nome, sem revelar valores.
- Criar documentação curta para instalação local, execução de testes e arquitetura atual.
- Criar uma matriz inicial de papéis: anónimo, estudante, revisor, administrador e proprietário, indicando as operações autorizadas.

Entregas:
- README.md com configuração local segura e comandos reais do projeto.
- docs/architecture-current.md com componentes, fluxos e fonte de verdade dos dados.
- docs/access-control-matrix.md com permissões esperadas.
- Manifesto reproduzível de dependências de desenvolvimento, se estiver em falta.

Restrições:
- Não corrigir ainda os achados da auditoria.
- Não ligar os testes à base de produção.
- Não copiar valores de .env para documentação.

Aceitação:
- Uma pessoa consegue instalar e executar testes seguindo o README.
- A suíte existente continua a passar.
- O relatório distingue claramente o que foi verificado do que permanece desconhecido.
```

## Etapa 1: corrigir a recuperação de acesso dos estudantes

```text
Execute apenas a Etapa 1: substituir a recuperação insegura de acesso do estudante.

Problema confirmado:
recover_student_access aceita email + ID público, redefine a senha e devolve temporaryPassword na resposta. O ID STU é público e nunca pode funcionar como segredo.

Resultado necessário:
- O pedido de recuperação recebe apenas os dados estritamente necessários e devolve sempre uma mensagem genérica.
- A mudança de senha só é permitida após o titular usar um token aleatório, de utilização única e com expiração, recebido pelo canal de email verificado.
- O token deve ser armazenado apenas na forma de hash, ter expiração curta, estado de consumo e auditoria sem o valor secreto.
- Aplicar limites de tentativas por conta e origem usando mecanismo compatível com a infraestrutura. Não depender apenas do frontend.
- Ao concluir a recuperação, revogar sessões anteriores e notificar o utilizador.
- Preservar todos os dados académicos.

Decisão arquitetural:
Antes de implementar, compare o menor caminho seguro na arquitetura atual com uma migração gradual para Supabase Auth. Não misture as duas estratégias. Se Supabase Auth exigir configuração externa ou decisão do utilizador, implemente primeiro um fluxo seguro compatível e documente a transição, ou pare para obter a decisão antes de alterar identidades.

Testes obrigatórios:
- Conta existente e inexistente produzem resposta pública indistinguível.
- ID público não permite obter nem alterar senha.
- Token válido funciona uma única vez.
- Token expirado, alterado ou reutilizado falha.
- O token nunca aparece em logs, auditoria ou banco em texto simples.
- Recuperação não altera student_id, matrículas, progresso, submissões ou certificados.
- Pedidos repetidos e concorrentes não deixam vários tokens utilizáveis indevidamente.

Não faça deploy. Entregue também as variáveis/configurações externas que terão de ser criadas, apenas pelos nomes.
```

## Etapa 2: proteger avaliações e gabaritos

```text
Execute apenas a Etapa 2: impedir que estudantes recebam o gabarito antes da altura autorizada.

Problema confirmado:
Os serializadores públicos incluem correctAnswer, explanation e isCorrect, e get_lesson envia esses campos ao estudante.

Resultado necessário:
- Criar contratos de resposta distintos para estudante e administração/revisão.
- A resposta do estudante antes da submissão não pode conter resposta correta, marca de opção correta, explicação reveladora, pontuação interna ou metadados de revisão.
- Definir uma política explícita por avaliação para mostrar ou não respostas e explicações após submissão/revisão.
- Calcular a avaliação exclusivamente no backend, com base na versão da questão associada à tentativa.
- Não alterar avaliações históricas quando uma questão for posteriormente editada.

Testes obrigatórios:
- Testes HTTP com estudante verificam ausência de todos os campos proibidos.
- Testes com revisor autorizado verificam presença do gabarito necessário.
- Um estudante não consegue consultar avaliações de outro.
- Alterar a questão após iniciar/submeter uma tentativa não muda silenciosamente o resultado histórico.
- Os fluxos de trabalhos manuais, reenvio e revisão existentes continuam funcionais.

Atualize a matriz de permissões e documente a política de divulgação do feedback.
```

## Etapa 3: auditar e restringir Supabase, RLS e views públicas

```text
Execute apenas a Etapa 3: preparar e validar o endurecimento das permissões do Supabase.

Resultado necessário:
- Inventariar grants efetivos para anon, authenticated, service_role e roles de execução da API.
- Rever as views no esquema public, especialmente students, admins, sessions, questions, question_options, answers, audit_log e new_credentials.
- Remover do esquema exposto as views sem uso legítimo ou substituí-las por views de colunas mínimas com security_invoker quando apropriado.
- Revogar privilégios não necessários e definir default privileges seguros.
- Rever RLS das tabelas e políticas do Storage segundo a matriz de papéis.
- Garantir que service-role/secret keys existem apenas no servidor.

Processo obrigatório:
1. Produzir primeiro uma migração de diagnóstico/read-only ou instruções SQL que mostrem grants e policies.
2. Não aplicar revogações na produção sem confirmar quais clientes usam essas views.
3. Preparar migração versionada e estratégia de compatibilidade.
4. Validar num projeto/staging isolado com utilizadores representativos.

Testes obrigatórios:
- Anónimo não lê dados privados.
- Estudante lê apenas os seus dados e os conteúdos permitidos pela matrícula.
- Revisor e administrador respeitam o âmbito definido.
- Nenhuma role cliente lê hashes, sessões, segredos, gabaritos ou dados de terceiros.
- Downloads e uploads privados obedecem às políticas de propriedade/curso.

Se não houver acesso ao Supabase real, entregue a migração, os testes e uma checklist de execução; não afirme que a produção já está protegida.
```

## Etapa 4: introduzir migrações e health checks seguros

```text
Execute apenas a Etapa 4: retirar alterações de esquema do caminho dos pedidos.

Resultado necessário:
- Identificar todas as funções prepare_* e ensure_* que executam DDL durante ações da API.
- Criar uma sequência de migrações SQL numeradas para representar o esquema atual e alterações futuras.
- Remover CREATE/ALTER dos pedidos normais depois de existir migração equivalente.
- Separar liveness pública, readiness e diagnóstico protegido.
- O health check público não modifica dados/esquema e não revela host, credenciais, detalhes SQL ou informações internas desnecessárias.
- A aplicação deve detetar versão incompatível do esquema e falhar de forma explícita, sem tentar repará-lo durante um pedido.

Testes obrigatórios:
- Base vazia recebe todas as migrações na ordem correta.
- Base no esquema anterior é atualizada sem perda de dados.
- Executar a migração novamente tem comportamento definido e seguro.
- Endpoints de estudante/admin não executam DDL.
- Liveness funciona mesmo sem consultar tabelas pesadas; readiness deteta dependências indisponíveis.

Documente como aplicar migrações em staging e produção, mas não as aplique externamente sem autorização.
```

## Etapa 5: corrigir concorrência e desempenho do backend

```text
Execute apenas a Etapa 5: eliminar o bloqueio indevido das rotas e estabelecer medições.

Resultado necessário:
- Corrigir a combinação de rotas async com psycopg e trabalho síncrono. Escolher uma estratégia coerente: endpoints síncronos executados no threadpool, ou stack assíncrona completa.
- Não misturar drivers sync/async sem limites explícitos.
- Isolar geração pesada de PDF, importações e notificações quando ultrapassarem o orçamento de uma resposta HTTP.
- Rever timeouts, retries e número de conexões em conjunto com o Supabase pooler.
- Acrescentar observabilidade de duração, erros e correlação sem dados pessoais.

Medição obrigatória:
- Criar um cenário de benchmark representativo em ambiente isolado.
- Medir p50, p95, p99, throughput, erros, conexões e memória.
- Comparar antes/depois nas mesmas condições.
- Não usar o tempo dos unit tests como medida de desempenho.

Testes obrigatórios:
- Chamadas concorrentes não serializam por bloqueio do event loop.
- Timeout/retry não duplica mutações.
- PDF e notificações falham de forma controlada.
- Toda a suíte continua a passar.

Não aumentar indiscriminadamente o pool ou a concorrência; fundamente os limites com a medição.
```

## Etapa 6: migrar ficheiros para Supabase Storage privado

```text
Execute apenas a Etapa 6: substituir Base64/data URLs no Postgres por objetos privados no Storage.

Âmbito:
- Trabalhos dos estudantes.
- Comprovativos de pagamento.
- Elementos gráficos dos certificados, respeitando a política de visibilidade de cada tipo.

Resultado necessário:
- Criar buckets/prefixos e políticas de acesso apropriadas.
- Guardar no Postgres apenas object_key, proprietário, tamanho real, MIME validado, checksum, estado e datas.
- Validar bytes reais no servidor, extensão, assinatura do formato, limites e quotas.
- Gerar download autorizado e temporário; não confiar em driveUrl arbitrário enviado pelo cliente.
- Prever upload interrompido, repetição idempotente, quarentena e futura análise antivírus.
- As listas não devem transportar o conteúdo binário.

Migração:
- Implementar leitura compatível dos registos antigos durante a transição.
- Copiar por lotes, verificar checksum/tamanho e registar resultado.
- Não apagar Base64/originais antes da validação, período de retenção e autorização explícita.
- Criar relatório de registos migrados, falhados e pendentes, sem conteúdo pessoal.

Testes obrigatórios:
- Acesso cruzado entre estudantes é recusado.
- Staff sem função adequada não descarrega o ficheiro.
- Upload excessivo, falso MIME e bytes inválidos são recusados.
- URLs expiram e não concedem enumeração do bucket.
- Ficheiros antigos e novos abrem e baixam durante a transição.
```

## Etapa 7: paginação, pesquisa e listas administrativas

```text
Execute apenas a Etapa 7: tornar as listas completas e rápidas para grandes volumes.

Resultado necessário:
- Implementar paginação por cursor nas submissões, certificados, solicitações e restantes listas ainda truncadas.
- Usar ordenação determinística, por exemplo data + ID, e devolver nextCursor/hasMore.
- Aplicar filtros, pesquisa e autorização no backend antes do limite.
- Carregar detalhes apenas ao abrir um registo.
- Corrigir o chat para evitar consultas por sala e filtros de autorização em Python quando puderem ser feitos por consulta segura.
- No frontend, implementar debounce, cancelamento e proteção contra respostas antigas.
- “Selecionar todos” deve indicar se seleciona a página ou todos os resultados filtrados.

Processo obrigatório:
- Criar dados sintéticos suficientes para ultrapassar 500 registos.
- Analisar EXPLAIN ANALYZE em staging/local e acrescentar apenas índices justificados.

Testes obrigatórios:
- Percorrer todos os resultados sem duplicações ou omissões.
- Inserções concorrentes não quebram a navegação do cursor.
- Pesquisa rápida não mostra resultados de um pedido anterior.
- Filtros e posição da lista são preservados ao voltar do detalhe.
- Número de consultas do chat permanece controlado com muitas salas.
```

## Etapa 8: tornar o código um monólito modular

```text
Execute apenas a Etapa 8: modularizar sem mudar o comportamento do produto.

Resultado necessário:
- Criar módulos por domínio: identidade, catálogo, matrículas, aprendizagem, avaliações, certificados, financeiro, comunicação e administração.
- Extrair de actions.py por fatias verticais pequenas, mantendo temporariamente o dispatcher como adaptador compatível.
- Separar validação HTTP, regras de negócio, consultas/transações e serialização.
- Dividir admin.js, app.js e styles.css por páginas/componentes/tokens sem quebrar URLs atuais.
- Definir uma única fonte para os assets frontend. Se uma cópia de distribuição for necessária, gerá-la automaticamente e testar a paridade.
- Não criar uma camada genérica que esconda SQL e regras do domínio sem benefício concreto.

Ordem interna recomendada:
1. Identidade e recuperação.
2. Avaliações/submissões.
3. Certificados/pagamentos.
4. Cursos/matrículas.
5. Comunicação/chat.

Aceitação:
- Mesmos contratos externos durante cada extração, salvo alterações versionadas e documentadas.
- Suíte completa passa após cada módulo extraído.
- Não há ficheiros frontend divergentes que exijam edição manual duplicada.
- Métricas de complexidade/tamanho melhoram sem aumentar acoplamento circular.
```

## Etapa 9: modelar curso, versão, edição/turma e matrícula

```text
Execute apenas a Etapa 9: permitir várias edições do mesmo curso preservando histórico.

Modelo pretendido:
- Course: identidade do catálogo.
- CourseVersion: conteúdo publicado e imutável para uma edição em curso.
- CourseOffering/Cohort: período, capacidade, responsáveis, regras e calendário.
- Enrollment: participação de um estudante numa oferta específica.
- Grupos podem organizar estudantes dentro da oferta sem substituir a matrícula.

Resultado necessário:
- O mesmo estudante pode frequentar o mesmo curso em períodos diferentes.
- Tentativas, progresso, notas, pagamentos e certificados apontam para a matrícula/oferta e versão corretas.
- Editar um curso futuro não altera o conteúdo ou resultado de uma edição passada.
- Conteúdos seguem rascunho, pré-visualização, publicação e nova versão.
- Converter os cursos atuais numa versão/oferta inicial sem recriar utilizadores.

Processo obrigatório:
- Desenhar primeiro o modelo e invariantes.
- Preparar migração expand/backfill/validate/contract.
- Incluir reconciliação de casos ambíguos e relatório, não adivinhar relações.

Testes obrigatórios:
- Duas edições do mesmo curso para o mesmo estudante coexistem.
- Certificado e nota da primeira edição não mudam após publicar a segunda.
- Atribuir grupo não cria uma matrícula incoerente nem remove outra.
- Pré-requisitos e permissões usam a oferta/matrícula correta.
```

## Etapa 10: completar o núcleo pedagógico

```text
Execute apenas a Etapa 10: evoluir autoria, avaliação e acompanhamento académico sobre o modelo da Etapa 9.

Resultado necessário:
- Editor de curso com rascunho, ordenação, pré-visualização, validação e publicação.
- Banco de questões versionado com tipos necessários, opções, explicações, dificuldade e tags.
- Avaliações com limite de tentativas, tempo, janela, randomização, nota mínima e política de feedback.
- Trabalhos com ficheiros, prazos, reenvio autorizado, rubricas, comentários e histórico de revisão.
- Pauta consolidada por turma, exportação autorizada e trilho de alterações.
- Regras explícitas de pré-requisitos, conclusão, disponibilidade de módulos e elegibilidade para certificados.
- Calendário e notificações de prazos.

Princípios:
- Não implementar motores complexos de standards educacionais do zero.
- Não usar compra de certificado como condição pedagógica de conclusão.
- Exceções individuais devem ter prazo, motivo, autor e auditoria.

Testes completos:
- Criar, publicar, matricular, aprender, avaliar, rever, reabrir, concluir e certificar.
- Alterações de regras não reescrevem resultados históricos.
- Estados e razões de bloqueio são claros para estudante e administração.
```

## Etapa 11: unificar certificados, pagamentos e inquéritos

```text
Execute apenas a Etapa 11: consolidar a lógica de certificação sem alterar documentos já emitidos.

Resultado necessário:
- Criar um contrato único de dados para pré-visualização do admin, pré-visualização do estudante e PDF.
- Corrigir a inconsistência entre Certificado de Participação e Certificado de Conclusão e eliminar carga horária fixa de 10 horas.
- Usar snapshots completos no momento da emissão: textos, curso/versão, conteúdos, carga horária, responsáveis, assets e política.
- Alterações futuras de configuração não modificam certificados antigos. Reemissão deve ser explícita, auditada e versionada.
- Separar elegibilidade académica, emissão, estado/revogação, pagamento, autorização de download e contador de downloads.
- Manter certificados de participação configuráveis por curso, inclusive a opção de não emitir.
- Manter solicitações/pagamentos em Certificações e respostas/configuração em Inquéritos.
- QR e página de verificação devem validar código, estado e integridade sem expor dados excessivos.

Testes obrigatórios:
- Pré-visualização e PDF apresentam os mesmos dados.
- Nomes/cursos longos não sobrepõem elementos em A4 horizontal.
- QR é legível no PDF renderizado.
- Certificado antigo permanece byte/semanticamente estável após mudar configuração.
- Bloqueio, nova autorização, limite e repetição de download funcionam sob concorrência.
- Certificado gratuito e profissional obedecem às políticas de cada curso.
```

## Etapa 12: consolidar UI/UX e acessibilidade

```text
Execute apenas a Etapa 12: organizar a interface num sistema consistente e responsivo.

Resultado necessário:
- Criar tokens de tipografia, espaçamento, cores, raios, bordas, estados e tamanhos de controlos.
- Padronizar sidebar fixa, cabeçalho fixo, área de conteúdo e comportamento mobile sem sobreposição.
- Cada item principal do menu deve representar uma página/estado navegável com URL própria e foco inicial correto.
- Administração: listas pesquisáveis primeiro; detalhe de um registo por página; ações contextuais; confirmações e resultados claros.
- Estudante: visão geral, cursos, aulas, submissões, notas, certificações, suporte e perfil sem conteúdo duplicado.
- Implementar loading, vazio, erro, sucesso, retry e skeleton apenas onde melhora a compreensão.
- Garantir navegação por teclado, foco visível, labels, mensagens associadas aos campos, contraste e reflow como objetivo WCAG 2.2 AA.

Validação obrigatória:
- Capturas e inspeção em desktop e mobile representativos.
- Console sem erros.
- Sem texto cortado, sobreposto ou fora dos contentores.
- Sidebar/cabeçalho não ocultam o conteúdo ao fazer scroll ou usar âncoras.
- Modais prendem e restauram foco, fecham por meios acessíveis e não excedem o viewport.
- Tabelas grandes e formulários continuam utilizáveis em ecrãs pequenos.
- Auditoria automatizada de acessibilidade complementada por revisão manual.

Não faça apenas alterações cosméticas globais. Corrija componentes e fluxos e inclua evidência visual antes/depois.
```

## Etapa 13: jobs duráveis, observabilidade, backups e releases

```text
Execute apenas a Etapa 13: preparar operação confiável da LMS.

Resultado necessário:
- Usar a fila de entregas existente com worker/scheduler durável, claims recuperáveis, retries com backoff, idempotência e fila de falhas.
- Separar tarefas críticas da duração de um pedido HTTP.
- Logs estruturados com request ID, action, duração e resultado; redigir tokens, senhas, conteúdo de trabalhos e dados pessoais.
- Métricas e alertas para erros, latência, conexões, filas atrasadas, falhas de email/WhatsApp/push, Storage e geração de PDF.
- Pipeline de CI obrigatório para testes, verificação de migrações e checks estáticos.
- Ambiente de staging separado e smoke tests pós-deploy.
- Documentar backup, retenção, RPO/RTO, rollback e resposta a incidentes.
- Executar um restauro de teste de banco e Storage em ambiente isolado.

Testes obrigatórios:
- Interromper/reiniciar worker não perde nem duplica notificações.
- Falha temporária do fornecedor é repetida; falha permanente vai para tratamento explícito.
- Deploy incompatível é bloqueado antes da produção.
- Restauro recupera estudantes, matrículas, progresso, ficheiros e certificados, com verificação de integridade.

Não declare disaster recovery pronto sem realizar e documentar o ensaio de restauro.
```

## Etapa 14: múltiplas instituições e integrações

```text
Execute apenas a Etapa 14 quando as etapas anteriores estiverem concluídas e o modelo comercial estiver decidido.

Primeiro obtenha respostas explícitas:
- A plataforma será usada por uma instituição ou vendida a várias organizações?
- Quais papéis, políticas de dados, personalizações e relatórios cada organização exige?
- Quais metas de utilizadores simultâneos, disponibilidade, retenção e custo devem ser cumpridas?
- Quais integrações são contratos reais, e não apenas possibilidades futuras?

Se for multi-instituição:
- Projetar organizations, memberships e permissões com âmbito.
- Aplicar isolamento a tabelas, consultas, Storage, cache, jobs, pesquisa, relatórios e logs.
- Testar sistematicamente acesso cruzado.
- Definir administração global e administração da instituição sem privilégios implícitos.

Integrações:
- API versionada, paginação, scopes, quotas e idempotência.
- Webhooks assinados, repetíveis e auditáveis.
- SSO/OIDC conforme contratos.
- Considerar LTI 1.3 para ferramentas educacionais externas.
- Considerar SCORM/xAPI/cmi5 apenas quando existirem conteúdos/clientes que os exijam e usar bibliotecas/serviços comprovados.

Escala:
- Executar testes com carga representativa e medir p50/p95/p99, erros, conexões, filas, Storage e custo por aluno ativo.
- Adicionar cache, réplicas, workers especializados ou serviços separados apenas para gargalos comprovados.

Aceitação:
- Isolamento entre instituições comprovado por testes negativos.
- Integrações têm contratos, observabilidade, retries e processos de desativação.
- Capacidade e custos são medidos nas condições-alvo e não inferidos pelo número de testes unitários.
```

## Prompt de revisão após cada etapa

Depois de o primeiro agente terminar uma etapa, envie este prompt ao mesmo agente ou, preferencialmente, a um agente revisor separado:

```text
Faça uma revisão rigorosa apenas das alterações da etapa recém-concluída.

Priorize:
1. Falhas de segurança e autorização.
2. Perda/corrupção de dados e incompatibilidade de migrações.
3. Condições de corrida, repetição de pedidos e transações incompletas.
4. Regressões dos fluxos existentes.
5. Testes insuficientes ou que passam sem validar o comportamento real.
6. Problemas de acessibilidade e responsividade, quando houver frontend.

Leia o diff e o código adjacente. Execute os testes relevantes. Não faça uma refatoração fora do escopo. Apresente primeiro os achados por gravidade, com ficheiro e linha. Se não houver achados, diga isso claramente e indique os riscos que dependem de staging/produção.
```

## Ordem de execução e regra de avanço

Execute nesta ordem:

1. Etapa 0.
2. Etapas 1 e 2, separadamente e com revisão imediata.
3. Etapas 3 e 4.
4. Etapas 5, 6 e 7.
5. Etapa 8 por fatias pequenas.
6. Etapas 9 e 10.
7. Etapas 11 e 12.
8. Etapa 13.
9. Etapa 14 apenas após decisões de negócio e medições.

Uma etapa só está concluída quando:

- Os critérios de aceitação foram demonstrados.
- Os testes relevantes e a suíte completa passam.
- Migrações foram testadas numa base isolada quando aplicável.
- Não ficaram segredos ou dados reais no diff.
- O agente apresentou limitações honestamente.
- A revisão não tem achados P0/P1 em aberto.
- O utilizador aprovou avançar para a etapa seguinte.

Se uma etapa revelar um problema crítico fora do seu escopo, o agente deve documentá-lo e interromper apenas a parte dependente; não deve aproveitar para modificar áreas não autorizadas.
