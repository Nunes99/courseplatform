# Etapa 14 - Seguranca continua e recuperacao periodica

## Controlos implementados

- Dependabot semanal para Python e npm, e mensal para GitHub Actions.
- Auditoria semanal e em cada alteracao com `pip-audit` e `pnpm audit`.
- Analise estatica Python com Bandit e Python/JavaScript com CodeQL.
- Baseline Bandit explicita para o passivo existente: novas ocorrencias medias
  ou altas bloqueiam o CI; ocorrencias antigas continuam visiveis para reducao
  gradual. A baseline atual nao contem ocorrencias de gravidade alta.
- Baseline revisto do `detect-secrets`; qualquer novo candidato bloqueia o CI.
- Verificacao mensal da evidencia de recuperacao e do prazo do proximo ensaio.

Os workflows de seguranca nao recebem chaves Supabase, credenciais Postgres,
segredos SMTP nem o segredo do executor. Resultados nunca devem copiar valores
detetados; mostram apenas que existe um candidato a rever localmente.

## Politica de dependencias

1. Dependabot abre PRs pequenos e separados por ecossistema.
2. Atualizacoes de seguranca exigem a suite completa e os workflows Security e
   CodeQL verdes.
3. Atualizacoes principais devem ser testadas em Preview antes de producao.
4. Nao usar `pip-audit --fix` ou correcoes forcadas do gestor npm automaticamente.
5. Dependencias de runtime permanecem fixadas em `requirements.txt`; ferramentas
   de desenvolvimento ficam em `requirements-dev.txt`; o frontend usa
   `pnpm-lock.yaml`.

## Gestao de segredos

O ficheiro `.secrets.baseline` contem somente hashes dos candidatos revistos,
nunca os respetivos valores. Para verificar localmente:

```powershell
.\.venv\Scripts\python.exe scripts/check_secrets.py
```

Se o comando falhar, execute o scanner localmente e reveja o ficheiro indicado
sem copiar o valor para issues, logs ou mensagens. Um segredo verdadeiro deve
ser revogado primeiro e removido do historico apenas com um plano aprovado.
O `pnpm-lock.yaml` e excluido do scanner de entropia por conter hashes de
integridade gerados pelo gestor; um teste separado impede URLs de registry com
credenciais embutidas.

## Recuperacao periodica

O registo sem dados pessoais fica em `docs/recovery-drills.json`. O workflow
mensal falha quando o ensaio trimestral esta vencido ou quando faltam evidencias
essenciais. A verificacao automatica nao restaura dados e nao confirma RPO/RTO.

O ensaio humano trimestral deve usar um projeto isolado, backup real aprovado,
Storage copiado separadamente e credenciais sinteticas. Depois do ensaio:

1. Registar data, resultado, tabelas e objetos validados.
2. Atualizar `docs/recovery-drills.json` sem PII, URLs privadas ou segredos.
3. Anexar evidencias seguras ao registo operacional externo.
4. Corrigir desvios de RPO/RTO antes do proximo release de alto risco.

O proximo ensaio vence em 1 de janeiro de 2027. A automacao apenas sinaliza o
prazo; nunca cria, restaura ou elimina recursos Supabase por conta propria.

## Comandos locais

```powershell
.\.venv\Scripts\python.exe -m pip_audit --requirement requirements.txt --strict
.\.venv\Scripts\bandit.exe --recursive backend api scripts --format json --output bandit-current.json
.\.venv\Scripts\python.exe scripts/check_bandit_baseline.py bandit-current.json
.\.venv\Scripts\python.exe scripts/check_secrets.py
.\.venv\Scripts\python.exe scripts/check_recovery_readiness.py --fail-if-overdue
pnpm audit --audit-level=high
```

Na primeira execucao local desta etapa, as consultas de vulnerabilidades Python
e npm foram impedidas pela cadeia TLS da rede local. Nao desative a verificacao
TLS para contornar esse erro. Os mesmos comandos permanecem obrigatorios no CI,
onde qualquer falha de consulta ou vulnerabilidade dentro do limite configurado
deve bloquear o workflow.
