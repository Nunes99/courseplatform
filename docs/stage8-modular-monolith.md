# Etapa 8: monólito modular

Data: 16 de setembro de 2026.

## Objetivo e estado

A primeira fatia estabeleceu fronteiras internas sem alterar contratos HTTP,
regras de autorização, dados ou URLs. A segunda extraiu identidade e recuperação
de acesso; a terceira extraiu os handlers de avaliações e submissões para
`domains/assessments.py`; a quarta extraiu certificados e pagamentos para
`domains/certificates.py` e `domains/financial.py`; a quinta extraiu catálogo e
matrículas para `domains/catalog.py` e `domains/enrollments.py`; a sexta extraiu
comunicação e chat para `domains/communication.py`; a sétima extraiu
aprendizagem para `domains/learning.py`; a oitava extraiu administração para
`domains/administration.py`. A extração vertical dos handlers dos nove
domínios está concluída; `actions.py` permanece como adaptador público de
compatibilidade enquanto as rotas e testes dependem desses nomes.

A nona fatia iniciou a redução desse adaptador: contratos Pydantic e rotas
versionadas foram separados em `api/`, e os serializadores de curso, versão,
oferta, matrícula e associação a grupo foram movidos para `serializers.py`.
As novas rotas chamam os mesmos nomes no dispatcher, portanto não duplicam
autorização, transações nem regras de domínio.

A décima fatia adicionou routers de catálogo e aprendizagem para configuração
pública do curso, media, home, dashboard e leitura de aula. O cliente migrou as
cinco operações para preferir a rota tipada; cada operação usa o respetivo
action legado somente quando um deploy antigo não possui essa rota.

Verificado nesta entrega:

- as 115 ações externas continuam registadas e têm handlers chamáveis;
- cada ação pertence a exatamente um dos nove domínios;
- `actions.ApiError` e os helpers públicos usados pelos testes continuam
  disponíveis por compatibilidade;
- imports de `app.py`, dispatcher e domínios não formam ciclos;
- os dez handlers únicos das onze ações de identidade são adaptadores sem SQL;
- validação, regras, transações e serialização de identidade residem no domínio;
- dependências substituíveis nos testes são resolvidas em tempo de chamada;
- os onze handlers únicos das doze ações de avaliações são adaptadores sem SQL;
- início, resposta, upload, submissão, revisão, reenvio e gestão de estado foram
  movidos para o domínio, incluindo o resolvedor privado de downloads;
- os handlers de certificados são adaptadores sem SQL, incluindo emissão,
  configuração, inquéritos, estado, pré-visualização e downloads;
- pedidos profissionais, comprovativos privados e decisões administrativas
  residem no domínio financeiro, preservando transações e auditoria;
- catálogo concentra cursos, módulos, conteúdos, media e snapshots imutáveis
  das versões publicadas;
- matrículas concentra ofertas/turmas, grupos, inscrições, resolução de contexto
  e inicialização idempotente do progresso a partir da versão contratada;
- comunicação concentra notificações internas, preferências, templates, email,
  Push, Telegram, WhatsApp, filas de entrega, chat e tokens Realtime;
- os 27 handlers únicos das 35 ações de comunicação são adaptadores sem SQL;
- auxiliares de autorização de salas, serialização e entrega também permanecem
  disponíveis por adaptadores compatíveis para os testes existentes;
- aprendizagem concentra dashboard, resolução da matrícula, leitura do snapshot
  publicado, acesso aos módulos e recomputação do progresso da matrícula;
- os cinco handlers de aprendizagem são adaptadores sem SQL e o contrato do
  estudante continua a omitir gabaritos, explicações e pesos não autorizados;
- administração concentra health, diagnósticos protegidos, estatísticas,
  estudantes, staff, permissões e identidade visual;
- os 14 handlers administrativos são adaptadores sem SQL, mantendo OWNER para
  gestão de staff e OWNER/ADMIN nos fluxos operacionais correspondentes;
- `public/` e a distribuição empacotada têm paridade integral;
- os entrypoints e URLs do frontend não mudaram.
- login de estudante/admin, logout, cursos do estudante e listas de estudantes
  e staff possuem agora rotas tipadas em `/api/v1` e documentação OpenAPI;
- validação estrutural rejeita campos desconhecidos antes de chegar ao domínio;
- erros das rotas tipadas usam códigos HTTP coerentes sem expor detalhes internos;
- `POST /api` e as 115 ações legadas permanecem disponíveis sem alteração;
- cinco serializadores académicos partilhados saíram de `actions.py`, mantendo
  adaptadores para os testes e clientes internos existentes.
- catálogo expõe leituras em `/api/v1/catalog/courses/{course_id}` e respetiva
  configuração pública de media;
- aprendizagem expõe home, dashboard e aula sob `/api/v1/students/me`, exigindo
  o token opaco no header `X-Session-Token`;
- os parâmetros externos `courseId` e `enrollmentId` preservam a nomenclatura
  atual, embora os handlers Python usem nomes internos em snake case;
- o frontend migrou `publicCourseConfig`, `publicMediaConfig`, home, dashboard
  e aula, preservando um fallback isolado por operação;
- o fallback não é usado para falhas reais, evitando repetir consultas ou
  esconder indisponibilidade da base de dados.

Não verificado nesta entrega: produção, staging, Supabase remoto, Vercel,
desempenho sob carga e fluxos com dados reais.

## Fronteiras atuais

| Domínio | Responsabilidade |
| --- | --- |
| `identity` | login, sessões, recuperação e perfil |
| `catalog` | cursos, versões, módulos, conteúdo e media |
| `enrollments` | ofertas/turmas, matrículas e grupos |
| `learning` | dashboard, acesso e progresso |
| `assessments` | tentativas, respostas, ficheiros e revisão |
| `certificates` | emissão, configuração, inquéritos e downloads |
| `financial` | pedidos e comprovativos de certificados |
| `communication` | notificações, canais, Telegram, push e chat |
| `administration` | health, estatísticas, estudantes e staff |

`domains/registry.py` valida duplicações e handlers ausentes ao importar a
aplicação. O dispatcher continua mutável para preservar testes e aliases atuais.
Os helpers de contratos e paginação foram movidos para `contracts.py`. Identidade
contém normalização, política mínima de senha, geração do ID público,
serializadores e os fluxos de login, logout, recuperação, perfil e alteração de
credenciais. Avaliações contém os fluxos transacionais de tentativas, respostas,
ficheiros, submissão, revisão e reenvio. Certificados contém emissão, políticas,
configuração, inquéritos, documentos e gestão de acesso. Financeiro contém
pedidos, comprovativos e aprovação ou rejeição administrativa. Catálogo contém
os cursos editáveis e os snapshots publicados; matrículas mantém ofertas,
grupos, inscrições e progresso inicial ligados à versão escolhida. `actions.py`
injeta dependências nomeadas pelos nove objetos `*Runtime` para preservar
temporariamente os pontos de substituição usados pelos testes. Comunicação
contém preferências e configurações públicas sem segredos, consentimento por
canal, filas com lease, entrega pelos fornecedores, ligação Telegram, tokens
Realtime de curta duração e regras de acesso às salas. Aprendizagem resolve a
matrícula e a versão publicada antes de montar dashboard/aula, separa acesso ao
conteúdo do estado de avaliação e atualiza progresso sem substituir históricos.
Administração mantém o health público mínimo, protege diagnósticos detalhados,
pagina listas e conserva transações e auditoria nas mutações de contas.

`api/contracts.py` define apenas contratos HTTP; `contracts.py` continua a
concentrar erros e helpers internos. `api/executor.py` liga as rotas versionadas
ao dispatcher e traduz erros de domínio para estados HTTP. Os routers de
identidade, catálogo, matrículas, aprendizagem e administração são agregados por
`api/router.py` antes do fallback de ficheiros estáticos.

## Frontend

Edite apenas `public/`. Depois execute:

```powershell
node scripts/sync_frontend.cjs
node scripts/sync_frontend.cjs --check
```

O primeiro comando recria `backend/courseplatform/static/`; o segundo não
escreve e falha perante ficheiro ausente, obsoleto ou diferente. Com npm
disponível, use `npm run sync:frontend` e `npm run check:frontend`.

Os primeiros componentes extraídos são deliberadamente pequenos: paginação das
listas administrativas, parser das rotas do estudante e tokens CSS. Isso reduz
risco antes de mover páginas que partilham estado global.

## Estratégia das próximas fatias

Cada handler será separado em validação de entrada, serviço/regra de negócio,
consulta/transação explícita e serialização. Enquanto testes ainda substituírem
dependências em `actions`, o adaptador construirá essas dependências em tempo de
chamada. Isso mantém os contratos observáveis sem criar um repositório genérico
que esconda SQL ou autorização.

A próxima etapa recomendada é validar em Preview, individualmente,
`publicCourseConfig`, home, dashboard e aula, incluindo sessão expirada, aula
bloqueada, estados vazios e conteúdo permitido. Após essa validação, a leitura
de cursos do estudante pode ser migrada mantendo a mesma janela de
compatibilidade.

## Impacto operacional

Não há migração SQL nem backfill. Não há alteração de IDs, relações ou dados
históricos. Não foi feito deploy. O único passo adicional de empacotamento é a
sincronização determinística dos assets antes dos testes/deploy.
