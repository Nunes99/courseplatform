# Validação e retirada do Base64 legado

## Validação dos downloads publicados

O verificador `scripts/validate_private_downloads.py` é read-only. Ele usa três
sessões ativas fornecidas apenas pelo ambiente local e seleciona objetos `READY`
sem apresentar tokens, IDs, nomes ou conteúdo nos logs.

Configure contas de teste controladas para estudante, revisor e administrador:

```powershell
$env:COURSEPLATFORM_VALIDATION_BASE_URL = "https://ORIGEM-DA-API"
$env:COURSEPLATFORM_VALIDATION_STUDENT_TOKEN = "TOKEN-DE-TESTE"
$env:COURSEPLATFORM_VALIDATION_REVIEWER_TOKEN = "TOKEN-DE-TESTE"
$env:COURSEPLATFORM_VALIDATION_ADMIN_TOKEN = "TOKEN-DE-TESTE"
.\.venv\Scripts\python.exe scripts\validate_private_downloads.py
```

Casos obrigatórios:

- anónimo recebe HTTP 401;
- estudante baixa o próprio trabalho com tamanho e SHA-256 corretos;
- estudante não lê trabalho de terceiro;
- revisor baixa trabalhos, mas recebe HTTP 403 para comprovativos;
- administrador baixa trabalhos e comprovativos;
- respostas binárias usam `Cache-Control: private, no-store`, `nosniff` e
  `Content-Disposition: attachment`.

Os tokens devem ser removidos do ambiente assim que a validação terminar.

## Janela de estabilidade

O Base64 histórico permanece como fallback durante pelo menos 30 dias depois do
backfill. Antes da retirada, confirme:

1. backup recuperável do Postgres e política de recuperação dos buckets;
2. zero falhas de integridade ou disponibilidade nos downloads publicados;
3. validação por estudante, revisor e administrador;
4. contagem integral em `storage.objects`, metadados e `audit_log`;
5. monitorização de erros durante toda a janela de retenção.

## Dry-run da retirada

O comando padrão nunca limpa dados. Para validar apenas os primeiros 25 objetos
que já cumpriram 30 dias:

```powershell
.\.venv\Scripts\python.exe scripts\cleanup_legacy_base64.py --limit 25
```

O script valida novamente Base64, metadados, tamanho, checksum e download do
Storage. Apenas apresenta contagens agregadas.

## Aplicação futura

A aplicação fica bloqueada antes dos 30 dias e exige duas confirmações:

```powershell
.\.venv\Scripts\python.exe scripts\cleanup_legacy_base64.py `
  --apply --limit 10 --retention-days 30 --confirm-backup --confirm-stability
```

Cada linha é atualizada com condição otimista e auditada individualmente. O
processo limpa apenas `drive_url` ou `payment_receipt_url`; não remove linhas,
metadados, checksums, objetos do Storage ou colunas. Interrompa no primeiro lote
com falhas e restaure a origem pelo backup caso seja necessário.
