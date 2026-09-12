# Auditoria técnica e evolução para uma LMS de grande escala

Data: 12 de setembro de 2026. Base analisada: commit `c1a8188`.

## Conclusão executiva

A plataforma já tem uma base funcional relevante: cursos, módulos, grupos, matrículas, trabalhos, revisão, certificados, pagamentos por comprovativo, inquéritos e comunicação. O próximo salto não deve ser uma reescrita nem apenas mais ecrãs. Deve ser transformar estas funcionalidades num produto seguro, previsível, testável e fácil de operar.

**Há duas falhas confirmadas que devem preceder a expansão:** recuperação de acesso sem comprovação da posse do email e envio do gabarito na resposta destinada ao estudante. Também há limitações concretas de concorrência, armazenamento de ficheiros e navegação em grandes listas.

Recomendação: manter Python/FastAPI e Supabase/Postgres; evoluir para um **monólito modular**, com uma única fonte de verdade para dados e componentes. Adotar serviços separados apenas quando medições ou necessidades de isolamento o justificarem.

## Âmbito e limites

- Análise local de backend, esquema SQL, frontend, configuração de execução, documentação e testes.
- Execução da suíte existente: **96 testes aprovados**. A última execução reportou 0,911 s de execução dos testes; isto não mede a velocidade da plataforma.
- Reproduções com dados sintéticos e dependências simuladas para recuperação de acesso, campos das avaliações e bloqueio das rotas assíncronas.
- Não foram alteradas contas, certificados, ficheiros de estudantes ou dados de produção. Não foi feito deploy.
- Não foram verificados os privilégios reais no Supabase, os backups, o WAF, os logs de produção, o plano contratado ou os limites efetivos da infraestrutura.
- Não foi realizado um novo ensaio visual em browser, uma auditoria completa de acessibilidade, um teste de carga ou um pentest. A análise de UI/UX abaixo distingue problemas estruturais de verificações visuais ainda necessárias.
- Este relatório não certifica capacidade para um número específico de estudantes. Utilizadores registados, utilizadores simultâneos, volume de ficheiros e picos de submissão são grandezas diferentes.

Prioridades: **P0** = corrigir imediatamente; **P1** = corrigir antes de aumentar a exposição/carga; **P2** = consolidar nas próximas fases. “Confirmado” significa observado no código e, quando indicado, reproduzido localmente; não significa exploração em produção.

## Achados prioritários

### A01. P0: recuperação de acesso permite obter a conta com email e ID público

**Confirmado no código e numa simulação local.** `recover_student_access` recebe email e `publicStudentId`, altera a senha, revoga sessões e devolve `temporaryPassword` na própria resposta. Não exige um token recebido pelo titular do email. Conhecer o email e o identificador público não comprova identidade.

Evidência: [actions.py:3770](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:3770). A simulação, com uma conta fictícia, confirmou a devolução da senha sem desafio por email. Não encontrei limitação de tentativas neste fluxo na aplicação; eventuais proteções externas não foram verificadas.

**Correção:** suspender este mecanismo até existir recuperação por token de utilização única, com expiração, enviado para email verificado; resposta genérica, limites de tentativas e notificação de alteração. A autenticação atual usa bcrypt e sessões próprias no Postgres; **não é Supabase Auth**. A adoção de Supabase Auth exige uma migração explícita de identidade, mantendo os identificadores académicos existentes. O fluxo oficial de recuperação por email é uma referência adequada. [Supabase: autenticação e recuperação de senha](https://supabase.com/docs/guides/auth/passwords).

**Aceitação:** email e ID público nunca bastam para mudar a senha; tokens expirados/reutilizados são recusados; a recuperação não revela a existência de uma conta; o estudante mantém matrículas, trabalhos, notas e certificados.

### A02. P1: a API das aulas entrega o gabarito ao estudante

**Confirmado no código e nos serializadores simulados.** `public_question` inclui `correctAnswer` e `explanation`; `public_option` inclui `isCorrect`. `get_lesson` utiliza estes serializadores na resposta do estudante. Ocultar os campos no ecrã não impede a leitura da resposta da API.

Evidência: [actions.py:364](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:364) e [actions.py:4121](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:4121).

**Correção:** contratos de resposta separados para estudante e administração; política explícita de divulgação da correção após a avaliação. Não depender de remoção de campos no JavaScript.

**Aceitação:** testes HTTP comprovam que perguntas/opções recebidas antes da submissão não contêm respostas corretas nem explicações que as revelem; os revisores continuam a receber o gabarito mediante autorização.

### A03. P1: views de gestão no esquema público exigem verificação de privilégios

**Risco condicionado à configuração real do banco.** O SQL cria views `public.students`, `public.admins`, `public.sessions`, `public.questions` e outras com `select *`. O bloco não define `security_invoker` nem revoga explicitamente o acesso de `anon`/`authenticated`. Não foi confirmado que estas roles tenham acesso em produção.

Evidência: [schema.sql:666](C:/Users/manyu/Documents/GitHub/courseplatform/supabase/schema.sql:666). Views podem executar com privilégios do proprietário e contornar a RLS das tabelas subjacentes; ativar RLS apenas nas tabelas não resolve necessariamente este caso. [Supabase: RLS e views](https://supabase.com/docs/guides/database/postgres/row-level-security).

**Correção:** inventariar grants reais e privilégios por defeito; retirar views sensíveis do esquema exposto ou restringi-las; evitar `select *`; usar `security_invoker` quando apropriado; separar acesso operacional de administração. A chave de serviço permanece exclusivamente no servidor.

**Aceitação:** testes com utilizador anónimo, estudante e staff comprovam que credenciais, sessões, gabaritos e dados de terceiros não são acessíveis fora das permissões previstas.

### A04. P1: operações síncronas bloqueiam rotas assíncronas

**Confirmado.** Rotas `async def` chamam diretamente `dispatch`, que executa psycopg síncrono. O PDF também é produzido diretamente na rota. A ligação ao banco inclui esperas síncronas entre tentativas.

Evidência: [app.py:36](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/app.py:36), [app.py:47](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/app.py:47) e [db.py:31](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/db.py:31).

Numa reprodução local, duas chamadas concorrentes com `dispatch` simulado a demorar 200 ms cada levaram aproximadamente 401 ms. Isto demonstra serialização nesse caminho, não a latência real da produção.

**Correção:** usar execução síncrona em threadpool limitado ou adotar um caminho assíncrono coerente. Isolar trabalho pesado de PDF, notificações e importações. Dimensionar conexões e concorrência em conjunto com o pooler, sem simplesmente aumentar limites. [FastAPI: concorrência e async/await](https://fastapi.tiangolo.com/async/).

**Aceitação:** teste concorrente sem bloqueio do event loop; benchmark em staging com consultas reais, tempos p50/p95/p99, conexões abertas, erros e consumo de memória.

### A05. P1: criação e alteração do esquema durante pedidos normais

**Confirmado.** `ensure_certificate_feature_schema` executa DDL em operações de certificados. O health check também pode chamar `ensure_schema`. Há mecanismos semelhantes de preparação de funcionalidades, alguns com cache apenas no processo.

Evidência: [actions.py:2851](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:2851), [actions.py:3477](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:3477) e [db.py:135](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/db.py:135).

**Impacto:** pedidos dependem de permissões de alteração de esquema, podem disputar locks e têm comportamento menos previsível em arranques de novas instâncias. O instalador também trata algumas falhas SQL como opcionais, dificultando perceber diferenças de ambiente.

**Correção:** migrações SQL versionadas e executadas separadamente da API; validação de versão em readiness; role de execução com privilégios mínimos. Health público leve e sem alterações; diagnóstico detalhado protegido.

**Aceitação:** nenhuma operação de estudante/admin executa `CREATE` ou `ALTER`; instalação limpa e atualização de uma base existente passam testes; migrações preservam dados e são compatíveis com a versão anterior durante o deploy.

### A06. P1: trabalhos e comprovativos são guardados como Base64 no Postgres

**Confirmado.** `upload_file` grava um data URL em `files.drive_url`, aceita tipo MIME e conteúdo fornecidos pelo cliente e contabiliza o tamanho da string Base64 como `size_bytes`. Não há, neste caminho, validação efetiva dos bytes, assinatura do formato ou limite de tamanho descodificado. Comprovativos seguem um padrão semelhante. Alguns uploads gráficos validam formato/tamanho e utilizam Storage, mas ainda devolvem Base64 para configurações.

Evidência: [actions.py:4953](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:4953) e [actions.py:7691](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:7691).

**Correção:** ficheiros em Storage privado; apenas caminho, proprietário, tamanho real, checksum, tipo e estado no Postgres. Validar upload no servidor, impor quotas, prever quarentena/análise de ficheiros e autorizar cada download. Restringir esquemas/domínios dos links externos. As políticas devem refletir estudante, matrícula e função do staff. [Supabase Storage: controlo de acesso](https://supabase.com/docs/guides/storage/security/access-control).

**Aceitação:** downloads de ficheiros alheios são recusados; ficheiros inválidos/excessivos não são publicados; uploads interrompidos podem ser repetidos; trabalhos antigos continuam acessíveis durante a migração. Não eliminar os originais antes de validar a cópia.

### A07. P2: listas administrativas truncadas e chat com consultas por sala

**Confirmado.** Submissões, certificados e solicitações têm limites máximos de 500 resultados, sem cursor para continuar a navegação nesses endpoints. Algumas outras áreas já têm paginação; o problema não afeta todas as listas igualmente. O chat carrega salas e filtra permissões em Python, acrescentando várias consultas por sala.

Evidência: [actions.py:5765](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:5765), [actions.py:7212](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:7212), [actions.py:7243](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:7243) e [actions.py:9114](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:9114).

**Correção:** paginação com cursor e ordenação estável; filtros e autorização na consulta; respostas de lista pequenas, com detalhes carregados ao abrir. Reduzir consultas N+1 do chat com agregações em lote. Na interface, debounce, cancelamento e proteção contra respostas antigas sobrescreverem a pesquisa atual. Usar índices orientados por planos de execução, não índices indiscriminados.

**Aceitação:** navegar por mais de 500 registos sem omissões/duplicações; pesquisar sem perder o foco; custo por página previsível; quantidade de consultas não cresce linearmente com as salas apresentadas.

### A08. P2: excesso de responsabilidades nos mesmos ficheiros e cópias de frontend

**Confirmado estruturalmente.** `actions.py` tem 9.537 linhas; `admin.js`, 7.253; `app.js`, 4.124; a folha principal de estilos, 15.080. O frontend existe em `public/` e em `backend/courseplatform/static/`. O tamanho não é, isoladamente, um erro, mas amplifica o impacto de alterações e o risco de corrigir apenas uma cópia.

Evidência: [actions.py](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py), [admin.js](C:/Users/manyu/Documents/GitHub/courseplatform/public/admin.js), [styles.css](C:/Users/manyu/Documents/GitHub/courseplatform/public/assets/css/styles.css) e [app.py:20](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/app.py:20).

**Correção:** extrair módulos por domínio, contratos de entrada/saída e componentes partilhados. Definir uma origem única para os assets e gerar a cópia de distribuição automaticamente, se ela continuar necessária. Manter o dispatcher atual como adaptador de compatibilidade enquanto se introduzem rotas tipadas.

**Aceitação:** uma alteração de tabela/modal/validação não exige cópias manuais; testes garantem paridade dos artefactos; funcionalidades migram uma a uma, sem trocar toda a interface de uma vez.

### A09. P2: o modelo de matrículas limita novas edições do mesmo curso

**Limitação confirmada no esquema.** `enrollments` impõe `unique(student_id, course_id)` e tem um único `group_id`. Isto representa mal o estudante que repete o mesmo curso noutra edição, com novas datas, avaliações e certificado, mantendo o histórico anterior separado.

Evidência: [schema.sql:149](C:/Users/manyu/Documents/GitHub/courseplatform/supabase/schema.sql:149). Edição de módulos e atribuição a grupos devem ser revistas em conjunto, não como operações independentes sobre o mesmo curso.

**Correção:** distinguir curso de catálogo, versão publicada e edição/turma. A matrícula pertence à edição; tentativas, progresso, avaliação e certificado referenciam a matrícula/versão correspondente. Separar grupos pedagógicos de ofertas temporais quando necessário.

**Aceitação:** o mesmo estudante faz duas edições sem substituir notas, tentativas ou certificados da primeira; mudanças futuras de conteúdo não reescrevem uma avaliação já submetida.

### A10. P2: identificadores públicos precisam de uma estratégia de crescimento

**Confirmado.** `STU-` com cinco algarismos aleatórios tem 100.000 combinações. Existe uma verificação de colisão antes de inserir, mas essa verificação e o insert não constituem uma reserva atómica entre pedidos concorrentes. Perto da ocupação total, as tentativas tornam-se caras; ao esgotar o espaço, não é possível criar outro ID nesse formato.

Evidência: [actions.py:212](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:212) e [actions.py:6285](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:6285).

**Correção:** manter os IDs internos e públicos já atribuídos; implementar alocação com controlo de concorrência e limite de tentativas; planear extensão compatível do formato ou namespace por instituição. Nunca utilizar o ID público como segredo de autenticação.

**Aceitação:** criação concorrente não falha por colisão não tratada; esgotamento produz erro controlado; URLs e referências antigas continuam válidas.

### A11. P2: pré-visualização e PDF de participação têm semântica diferente

**Confirmado no código, sem nova renderização visual nesta auditoria.** A interface apresenta “Certificado de Participação”, enquanto o gerador PDF de participação escreve “CERTIFICADO DE CONCLUSÃO”. A preparação do PDF também usa “10 horas” fixas para o modelo de participação, independentemente da carga horária real do curso.

Evidência: [app.js:3846](C:/Users/manyu/Documents/GitHub/courseplatform/public/app.js:3846), [certificate_pdf.py:65](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/certificate_pdf.py:65) e [actions.py:5302](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:5302).

**Correção:** contrato único dos dados do documento para admin, estudante e PDF; carga horária e textos obtidos do snapshot de emissão; eliminar valores demonstrativos como fallback de documentos oficiais. Separar a imutabilidade do conteúdo emitido da política atual de acesso/download. Uma atualização de modelo deve gerar uma reemissão explícita, não alterar silenciosamente um documento antigo.

**Aceitação:** título, titular, curso, carga horária, datas, código e estado coincidem em todas as representações; testes semânticos e visuais para os dois modelos, nomes longos e QR legível.

### A12. P2: testes e operação ainda não constituem uma barreira suficiente de qualidade

**Confirmado no repositório, com limites de âmbito.** Há 96 testes aprovados e scripts de browser úteis, mas as falhas A01/A02 não são impedidas pela suíte atual. Não encontrei `README.md`, diretório `.github/` com pipeline, nem uma cadeia de migrações versionadas. Isto não exclui configurações externas de CI/deploy.

O sistema já persiste entregas de notificações e estados de processamento; não é necessário descartar essa base. Contudo, o disparo usa tarefas ligadas ao pedido e não foi encontrado no repositório um worker/scheduler independente que garanta o escoamento contínuo e recuperação após interrupções.

Evidência: [app.py:58](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/app.py:58) e [actions.py:2318](C:/Users/manyu/Documents/GitHub/courseplatform/backend/courseplatform/actions.py:2318).

**Correção:** CI obrigatório, dependências de desenvolvimento reproduzíveis, testes HTTP e de integração com banco isolado, staging e smoke tests pós-deploy. Worker durável sobre a fila existente com retries, backoff, idempotência, recuperação de claims abandonados e fila de falhas. Logs estruturados sem segredos, correlação de pedidos, métricas e alertas. Documentar backups e ensaiar restauro do banco e do Storage.

**Aceitação:** falhar um teste crítico impede release; reiniciar um worker não perde notificações; um restauro reproduz matrículas, progresso, ficheiros e certificados; erros são investigáveis sem expor dados pessoais.

## O que devemos preservar

- Domínios académicos já implementados e identificadores que ligam o histórico do estudante.
- SQL parametrizado, hashes de senha/sessão, verificações de titularidade e permissões existentes, reforçando os pontos em falta.
- Controlo transacional nas revisões, reenvios e limites de certificados; expandir testes de concorrência.
- Snapshots e gestão de acesso dos certificados, incluindo política de participação por curso recentemente adicionada.
- Auditoria de ações e estados de exclusão/bloqueio onde já existem.
- Sanitização de conteúdo HTML, preferências de comunicação e proteção dos segredos das integrações.
- Testes existentes de certificados, reenvio, notificações e chat. São uma base, não algo a substituir.

## Arquitetura-alvo incremental

Manter uma aplicação principal e um banco transacional, com limites de responsabilidade claros:

| Módulo | Responsabilidade |
| --- | --- |
| Identidade e acesso | Autenticação, recuperação, sessões, MFA, funções e permissões por âmbito |
| Catálogo e autoria | Cursos, versões, módulos, recursos, rascunhos e publicação |
| Ofertas e matrículas | Edições/turmas, datas, capacidade, grupos e inscrições |
| Aprendizagem | Progresso, pré-requisitos, calendário e regras de disponibilidade |
| Avaliações | Banco de questões, tentativas, trabalhos, rubricas, revisão e pauta |
| Certificações | Elegibilidade, inquéritos, emissão, snapshots, verificação e revogação |
| Financeiro | Pedidos, pagamentos, comprovativos, reconciliação e direitos de download |
| Comunicação | Notificações, campanhas, preferências, chat e jobs duráveis |
| Operação e relatórios | Auditoria, indicadores, importações/exportações e suporte |

As regras de negócio ficam em serviços do domínio; a camada HTTP valida pedidos e aplica autenticação; a camada de persistência concentra consultas/transações. Evitar uma abstração genérica para tudo. Começar por extrair identidade e avaliações, onde já há riscos concretos.

O frontend pode evoluir por componentes e páginas carregadas conforme necessário. TypeScript e um sistema de componentes podem ajudar, mas não é necessário mudar todo o framework para obter ganhos. O fator decisivo é ter contratos tipados, estado previsível e componentes reutilizáveis.

## Plano gradual de evolução

### Fase 1: confiança e segurança

Entregas: corrigir recuperação, impedir divulgação do gabarito, validar privilégios reais de views/tabelas/Storage, reforçar recuperação administrativa, exigir MFA para staff privilegiado e introduzir testes negativos de autorização. Rever/rodar credenciais que tenham sido partilhadas fora dos canais previstos, sem as incluir em relatórios ou código.

**Porta de saída:** A01/A02 resolvidos e cobertos por testes; exposição do banco verificada; utilizadores só acedem aos próprios dados ou aos âmbitos atribuídos; recuperação mantém o histórico académico.

### Fase 2: estabilidade e desempenho

Entregas: CI/staging, migrações versionadas, correção da execução bloqueante, uploads privados, paginação consistente, diagnósticos protegidos, métricas de latência e jobs duráveis. Criar um runbook de incidentes e realizar o primeiro restauro de teste.

**Porta de saída:** deploy e rollback da aplicação ensaiados; instalação limpa e upgrade de dados existentes verificados; listas completas; carga controlada medida sem perda de submissões ou ficheiros.

### Fase 3: núcleo pedagógico de uma LMS

Entregas: versões de curso e edições/turmas; editor com rascunho, pré-visualização e publicação; biblioteca de conteúdos reutilizáveis; banco de questões; avaliações configuráveis; pauta consolidada; rubricas e comentários; calendário e pré-requisitos; regras de conclusão explícitas.

O aluno deve conseguir retomar a última aula, ver prazos e estado de avaliação, acompanhar correções e compreender exatamente por que razão um módulo ou certificado está indisponível. A administração deve gerir exceções por estudante/turma com prazo, motivo e histórico.

**Porta de saída:** um curso pode ser criado, publicado, lecionado, avaliado e concluído sem editar diretamente o banco; uma segunda edição preserva integralmente a primeira.

### Fase 4: administração profissional e várias instituições

Entregas: instituições, equipas, professores, tutores, revisores e funções financeiras com âmbitos próprios; fluxos de aprovação; ações em lote; importações com validação e relatório de erros; relatórios por turma/curso; suporte operacional; identidade visual configurável.

Se o objetivo incluir várias organizações clientes, a separação por organização tem de abranger dados, consultas, Storage, cache, jobs e relatórios. Não basta acrescentar `organization_id` a uma tabela. Implementar antes de receber o segundo cliente institucional.

Separar curso concluído, pagamento aprovado e download autorizado. Automatizar pagamentos apenas quando houver volume e requisitos claros; manter comprovativos e decisões auditáveis. Tornar preço, condições e limites de download transparentes para o estudante.

**Porta de saída:** testes de isolamento entre instituições; permissões por curso/turma verificadas; alterações em lote têm confirmação, resultado parcial e recuperação controlada.

### Fase 5: ecossistema e escala comprovada

Entregas orientadas pela procura: SSO institucional, API pública versionada, webhooks assinados/idempotentes, integrações com ferramentas de ensino, relatórios analíticos e aplicações móveis quando a utilização o justificar. LTI 1.3 é uma opção para integrar ferramentas externas com identidade e contexto de aprendizagem. [1EdTech: LTI](https://www.1edtech.org/standards/lti).

Avaliar SCORM/xAPI apenas quando houver conteúdos ou clientes que os exijam, usando implementações estabelecidas após uma análise específica. IA, recomendações avançadas e marketplace vêm depois da qualidade dos dados e da governação, não antes.

**Porta de saída:** capacidade medida para o pico-alvo, custos por aluno ativo conhecidos, recuperação comprovada e integrações cobertas por contratos/testes. Extrair serviços ou adicionar réplicas/cache apenas quando o gargalo estiver identificado.

## UI/UX: organização a consolidar

| Área | Organização recomendada |
| --- | --- |
| Estudante | Visão geral, Meus cursos, curso/aulas, trabalhos, notas, certificações, suporte e perfil com URLs próprias |
| Curso no admin | Lista pesquisável; detalhe de um único curso com visão geral, conteúdos, turmas e configuração |
| Submissões | Filtros e fila de trabalho; detalhe com ficheiros, respostas, rubrica, histórico e reabertura com prazo |
| Certificações | Certificados emitidos, solicitações/pagamentos e configuração por curso claramente separados |
| Inquéritos | Lista e configuração próprias; respostas e indicadores aqui, sem misturar com solicitações de certificados |
| Pessoas | Estudantes, matrículas, staff e permissões com contexto e ações compatíveis com a função |

Padronizar tipografia, espaçamento, tabelas, estados, inputs, botões e diálogos num pequeno design system. Priorizar densidade legível, não títulos de dimensão promocional. Cabeçalho/menu fixos devem reservar espaço real no layout. Em mobile, filtros e navegação precisam de comportamento próprio sem encobrir conteúdos.

Estados vazios, carregamento, sucesso, erro e repetição de pedido devem existir em todas as operações. Preservar pesquisa/página ao regressar de um detalhe. “Selecionar todos” deve distinguir a página atual de todos os resultados filtrados. Ações destrutivas devem indicar impacto e respeitar o histórico académico, preferindo arquivo quando apropriado.

Adotar WCAG 2.2 AA como objetivo: navegação por teclado, foco visível, rótulos, mensagens de erro, contraste e reflow. Validar com ferramentas automáticas e revisão humana, incluindo leitores de ecrã. Isto é um objetivo de qualidade, não uma declaração de conformidade atual. [W3C: WCAG 2.2](https://www.w3.org/TR/WCAG22/).

## Plano de testes e métricas

| Camada | Testes a acrescentar |
| --- | --- |
| Segurança | Recuperação, tokens expirados/reutilizados, gabaritos, acesso cruzado, permissões de staff e isolamento de ficheiros |
| Integração | Postgres descartável com migrações; locks/retries; matrículas; pagamentos; acesso a certificados |
| Fluxos completos | Autenticar, abrir curso, submeter, rever, reabrir, concluir, responder ao inquérito, solicitar e baixar certificado |
| Concorrência | Reenvios simultâneos, revisão simultânea, download limitado, criação de IDs e notificações duplicadas |
| Interface | Desktop/mobile, teclado, nomes longos, listas grandes, erros/retries, modais e PDFs dos dois modelos |
| Operação | Deploy/rollback, falha do banco/provedor, worker interrompido, recuperação de fila e restauro de backup |

Definir primeiro a carga representativa: dimensão do catálogo, matrículas, mensagens, tamanho dos ficheiros e pico de estudantes simultâneos. Medir latência p50/p95/p99, erros, consultas por pedido, tempo de fila, conexões, tamanho dos payloads e custo. Não usar apenas médias nem o tempo de abertura da página.

Como objetivos iniciais a negociar, não resultados medidos: p95 de leituras comuns até 500 ms, p95 de escritas comuns até 1 s e disponibilidade mensal de 99,9%, sob carga e condições explicitadas. Upload, login com hashing e geração de PDF precisam de orçamentos próprios. Ajustar estes objetivos à infraestrutura e ao custo aceitável.

Indicadores pedagógicos: ativação após matrícula, progressão, conclusão, abandono por módulo, tempo de revisão, reenvios, satisfação e procura de suporte. Evitar usar tempo com a página aberta como prova de aprendizagem.

## Migração sem perda de histórico

1. Inventariar tabelas, volumes, relações, ficheiros e permissões reais; fazer backup e testar restauro.
2. Acrescentar estruturas novas sem apagar as antigas, com migrações versionadas.
3. Relacionar identidades novas aos IDs existentes; não criar outro estudante para a mesma pessoa sem reconciliação.
4. Criar versões/edições iniciais para os cursos atuais e mapear matrículas, tentativas, progresso e certificados.
5. Transferir ficheiros por lotes, verificar checksum/tamanho/acesso e manter fallback até concluir a validação.
6. Comparar contagens e invariantes, validar amostras e testar todos os percursos críticos em staging.
7. Ativar por funcionalidade/coorte, observar erros e manter reversão da aplicação compatível com o esquema expandido.
8. Remover compatibilidade e dados antigos apenas após validação, retenção definida e aprovação explícita.

## Ordem prática do backlog

| Ordem | Trabalho | Esforço relativo | Critério principal |
| --- | --- | --- | --- |
| 1 | Recuperação segura e proteção do gabarito | Médio | Não é possível recuperar conta sem prova de identidade nem obter resposta antecipada |
| 2 | Privilégios/RLS e testes negativos de autorização | Médio | Matriz de acessos comprovada no ambiente real |
| 3 | CI, staging e migrações | Médio | Release reproduzível com validação automática |
| 4 | Concorrência, paginação e consultas | Médio | Navegação completa e benchmark com carga definida |
| 5 | Uploads privados e transição dos ficheiros existentes | Alto | Ficheiros íntegros, autorizados e fora dos payloads de listagem |
| 6 | Certificados: consistência de dados e renderização | Médio | Pré-visualização e PDF representam o mesmo documento |
| 7 | Extração de módulos e componentes partilhados | Alto, incremental | Alterações localizadas e sem duplicação manual |
| 8 | Edições/turmas, autoria e avaliações completas | Alto | Percurso académico integral com histórico por edição |
| 9 | Instituições, relatórios e operação avançada | Alto | Isolamento e gestão por âmbito demonstrados |
| 10 | Integrações e expansão de escala | Conforme procura | Capacidade/custo e valor de produto medidos |

Esforço relativo não é estimativa de prazo. Equipa, disponibilidade, prioridades comerciais e condições de produção ainda precisam de ser definidos.

## Decisões e verificações pendentes

- A LMS será de uma instituição ou um produto para várias organizações?
- Quantos alunos ativos e simultâneos são esperados, e em que horizontes?
- Quais tipos de conteúdo e avaliação são realmente necessários?
- Que equipa mantém produto, conteúdo, suporte, segurança e operação?
- Quais são os privilégios efetivos, backups, limites, regiões, custos e alertas da infraestrutura atual?
- Que regras de privacidade, retenção, exportação e eliminação de dados se aplicam aos públicos atendidos? Validar com apoio competente antes de prometer conformidade.
- Quais RPO/RTO, disponibilidade e tempos de resposta o negócio consegue sustentar?

**Primeiro incremento recomendado:** fechar A01/A02, confirmar A03 e acrescentar os testes que impedem a sua regressão. Depois, estabilizar execução, migrações e ficheiros. Essa sequência permite crescer aproveitando o trabalho existente, com menos risco de voltar a corrigir as mesmas classes de problemas.
