# Etapa 5: concorrência, paginação e consultas

## Resultado implementado

- As rotas FastAPI descarregam chamadas síncronas ao Postgres e geração de PDF para o threadpool limitado do runtime. A leitura assíncrona do pedido continua no event loop.
- `adminListSubmissions`, `adminListCertificates` e `adminListCertificateRequests` usam paginação por cursor com ordenação estável e consulta de `limit + 1` para determinar `hasMore`.
- Os cursores são opacos, têm versão e ficam vinculados à ação e aos filtros. Um cursor reutilizado com filtros diferentes é rejeitado com `CURSOR_FILTER_MISMATCH`.
- O painel administrativo mantém histórico local de cursores para avançar e regressar, usa páginas independentes para certificados e pedidos e ignora respostas antigas de pesquisas rápidas.
- A sincronização de salas do chat passou de operações por sala para um único `INSERT ... SELECT` idempotente.
- Resumos de salas, mensagens recentes, não lidas, presença, participantes e perfis são carregados em lotes. A quantidade de consultas deixa de crescer por cada sala apresentada.

## Contrato de paginação

Pedido:

```json
{
  "limit": 50,
  "cursor": "cursor-opaco-da-pagina-anterior"
}
```

Omitir `cursor` abre a primeira página. A resposta preserva as coleções existentes e acrescenta:

```json
{
  "pagination": {
    "limit": 50,
    "returned": 50,
    "hasMore": true,
    "nextCursor": "cursor-opaco"
  }
}
```

Clientes antigos que não enviam cursor continuam a receber a primeira página e mantêm o limite solicitado até ao máximo histórico de 500 registos. O painel atualizado usa 50 registos por pedido.

## Verificação de consultas

Em 14 de setembro de 2026 foi feita uma inspeção somente leitura dos índices e `EXPLAIN (FORMAT JSON)` sem `ANALYZE` no projeto ligado. Não foram lidos conteúdos de estudantes nem executado DDL.

- Submissões filtradas por estado usam o índice existente `idx_attempts_status_dates`, seguido de uma ordenação de custo reduzido no volume atual.
- Certificados e pedidos usam varrimentos/ordenações de custo reduzido no volume atual.
- Presença do chat também tem custo reduzido no volume atual.

Como o volume atual não demonstra um gargalo, esta etapa não cria índices especulativos. Antes de adicionar índices de expressão para os novos cursores, repetir os planos com uma carga representativa em Preview e registar tempo, buffers, tamanho das tabelas e custo de escrita.

O Performance Advisor reportou 34 chaves estrangeiras sem índice de cobertura e um aviso de `auth_rls_initplan` na política Realtime. Estes avisos foram inventariados, mas não corrigidos em bloco: índices têm custo de escrita e devem ser escolhidos pelos fluxos medidos; a política Realtime pertence ao endurecimento de permissões. Referências: [unindexed foreign keys](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys) e [RLS initialization plan](https://supabase.com/docs/guides/database/database-linter?lint=0003_auth_rls_initplan).

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_stage5_concurrency_pagination -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

O teste específico comprova concorrência das rotas, isolamento dos cursores, linhas de sondagem não expostas e quantidade fixa de consultas para 40 salas. Os testes de integração Postgres continuam a exigir `COURSEPLATFORM_TEST_DATABASE_URL` apontando para uma base descartável.

## Validação manual

Na Preview, validar com uma conta administrativa de teste:

1. Pesquisar rapidamente nas submissões e confirmar que um resultado antigo não substitui a pesquisa atual.
2. Avançar e regressar nas listas de submissões, certificados e pedidos sem duplicações ou omissões.
3. Alterar um filtro depois de avançar e confirmar o retorno à primeira página.
4. Abrir o chat como estudante e administrador e conferir nomes, contadores, presença e última mensagem.
5. Gerar um PDF enquanto outras páginas da API são consultadas e confirmar que permanecem responsivas.

## Impacto e limites

Não há migração de esquema nem alteração de dados nesta etapa. Nenhuma alteração foi aplicada ao Supabase ou à Vercel. Latência p50/p95/p99, utilização do pool e memória ainda precisam de medição em Preview com carga representativa; os testes locais não demonstram desempenho de produção.
