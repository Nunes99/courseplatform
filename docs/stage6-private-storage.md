# Etapa 6: Storage privado

## Resultado local

Trabalhos e comprovativos novos deixam de persistir Base64 no Postgres. O backend:

1. valida Base64, tamanho descodificado, assinatura binária, MIME e extensão;
2. autoriza a tentativa ou o pedido antes do upload;
3. grava o objeto num bucket privado por caminho determinístico;
4. guarda apenas bucket, caminho, tamanho real, SHA-256 e estado no Postgres;
5. autoriza novamente cada abertura/download e confirma o checksum.

Os formatos aceites para trabalhos são PDF, JPG, PNG, WebP, TXT, Word, Excel e PowerPoint. Comprovativos aceitam apenas PDF, JPG, PNG e WebP. Os limites padrão são 10 MiB e 5 MiB, respetivamente.

## Compatibilidade histórica

`drive_url` e `payment_receipt_url` não são removidos. O backend deixa de expor data URLs nas respostas, mas consegue servi-los depois da autorização. URLs HTTPS legadas continuam disponíveis durante a transição.

O backfill copia Base64 histórico para Storage e mantém a origem:

```powershell
# Apenas inventário/validação. Não faz upload nem atualiza linhas.
.\.venv\Scripts\python.exe scripts\backfill_private_storage.py --limit 100

# Executar somente após migração, backup e validação em staging.
.\.venv\Scripts\python.exe scripts\backfill_private_storage.py --apply --limit 100
```

O comando só apresenta contagens agregadas. Uma repetição ignora linhas já marcadas como `READY`. Objetos usam caminhos determinísticos; repetir um upload idêntico não cria uma nova referência lógica.

## Ordem de aplicação

1. Confirmar backup e restauro num ambiente isolado.
2. Aplicar `20260914100000_private_submission_storage.sql`. A migração não reescreve os blobs históricos; as constraints ficam `NOT VALID`, mas já protegem novas escritas.
3. Configurar `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (recomendada) ou
   `SUPABASE_SERVICE_ROLE_KEY` (legada), e os nomes dos dois buckets apenas no backend.
4. Publicar a API compatível e validar upload/download com estudante, REVIEWER, ADMIN e OWNER sintéticos.
5. Executar o backfill sem `--apply`; investigar todos os inválidos.
6. Executar lotes pequenos com `--apply` e comparar tamanho/checksum/download.
7. Manter Base64 original até existir relatório de cobertura integral e backup do Storage.

## Rollback operacional

Reverter primeiro a aplicação. As colunas e buckets são aditivos e podem permanecer. Não baixar manualmente `schema_versions`, não apagar objetos e não limpar os campos legados durante o incidente.

## Verificações pendentes por ambiente

- bucket realmente privado e sem policies para `anon`/`authenticated`;
- chaves `SUPABASE_SECRET_KEY`/`SUPABASE_SERVICE_ROLE_KEY` ausentes dos bundles e logs do frontend;
- upload e download com objetos próximos dos limites;
- recusa de ficheiro de outro estudante e de comprovativo por REVIEWER;
- comportamento sob interrupção/repetição e concorrência;
- métricas de latência, memória e erros no Preview.
