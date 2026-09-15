# Etapa 7: paginação, pesquisa e consultas administrativas

## Âmbito implementado

As listas administrativas de estudantes, cursos, grupos, staff, inquéritos e
notificações passaram a aplicar pesquisa, filtros, ordenação e limite no
Postgres antes de devolver os registos. A navegação usa cursores opacos e
ordenação estável, com o identificador do registo como critério de desempate.

Também permanecem paginadas por cursor as listas de submissões, certificados e
solicitações de certificados introduzidas anteriormente. A interface cancela o
pedido anterior com `AbortController`, ignora qualquer resposta antiga que
ainda consiga terminar e usa debounce nos campos de pesquisa que carregam dados
automaticamente.

## Contrato de paginação

Os pedidos aceitam `limit` e `cursor`. Cada resposta inclui `pagination` com:

- `returned`: quantidade devolvida na página atual;
- `total`: total após aplicar os filtros, quando calculado pelo endpoint;
- `hasMore`: indica se existe uma página seguinte;
- `nextCursor`: cursor opaco da página seguinte.

O frontend mantém uma pilha local de cursores para permitir regressar à página
anterior. Um cursor só pode ser reutilizado com os mesmos filtros, ordenação e
limite; o backend rejeita cursores cujo âmbito não corresponda ao pedido.

"Selecionar todos" significa selecionar apenas os registos apresentados na
página atual. Operações globais explícitas, como notificar todos os estudantes
ativos, continuam a ser executadas no backend e não dependem da página visível.

## Carregamento de detalhes

A lista de cursos devolve apenas os dados necessários aos cartões. Módulos,
aulas e grupos do curso são carregados quando o administrador abre os detalhes.
As listas são limitadas por página, evitando o carregamento inicial de centenas
de cursos ou grupos.

A lista de estudantes mantém matrículas e grupos resumidos porque estes dados
ainda alimentam seletores administrativos existentes. O volume está limitado à
página atual; uma separação adicional desses seletores deve ser feita numa
etapa futura sem quebrar os fluxos de grupo, edição e acesso a módulos.

## Verificação local

Testes unitários da etapa:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_stage7_admin_lists -v
```

Verificação visual com API sintética e mais de 500 estudantes:

```powershell
.\.venv\Scripts\python.exe -m http.server 8765 -d public
$env:PREVIEW_URL = "http://127.0.0.1:8765"
node scripts/verify_stage7_admin_lists.cjs
Remove-Item Env:PREVIEW_URL
```

O verificador percorre as páginas com um conjunto sintético de 507 registos,
confirma estabilidade perante uma inserção concorrente e valida estudantes,
cursos, staff, inquéritos e notificações em 1440 px e 390 px. As capturas ficam
em `tmp/ui/stage7-admin-lists/` e não são versionadas.

## EXPLAIN ANALYZE

Os planos reais devem ser medidos apenas numa base local ou staging com dados
representativos. Configure `COURSEPLATFORM_TEST_DATABASE_URL` para uma base
descartável cujo nome contenha `test`, aplique as migrações e execute os testes
de integração antes de recolher `EXPLAIN (ANALYZE, BUFFERS)` das consultas mais
frequentes.

Não foi executado `EXPLAIN ANALYZE` contra produção. Este repositório não tinha
uma base PostgreSQL local elegível configurada durante a implementação; por
isso, tempos e índices adicionais permanecem uma validação operacional de
staging, não uma afirmação de desempenho em produção.

## Dados e compatibilidade

Esta etapa não altera o esquema, não executa migrações e não modifica dados.
Clientes que não enviam filtros ou cursor recebem a primeira página com limites
seguros. O frontend público e a cópia estática empacotada no backend permanecem
sincronizados.
