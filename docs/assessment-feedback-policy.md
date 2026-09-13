# Política de feedback das avaliações

Data: 13 de setembro de 2026.

## Objetivo

O gabarito é confidencial por defeito. A API usa contratos separados para estudantes e staff, e a autorização é aplicada no backend. A interface não é considerada uma barreira de segurança.

## Política por módulo

Cada módulo define `feedback_release_mode`:

- `NEVER`: não divulgar gabarito nem explicações.
- `AFTER_SUBMISSION`: permitir a divulgação apenas depois de existir `submitted_at`.
- `AFTER_REVIEW`: permitir a divulgação apenas depois de existir `reviewed_at`.

Os controlos `show_correct_answers` e `show_explanations` são independentes. O valor inicial para módulos existentes é `AFTER_REVIEW`, com ambos desativados. Um prazo expirado sem submissão não satisfaz `AFTER_SUBMISSION`.

## Contratos

Antes da divulgação autorizada, o estudante recebe o enunciado, tipo, ordem, obrigatoriedade e opções sem qualquer marca de correção. Não recebe `points`, `correctAnswer`, `explanation`, `isCorrect`, `awardedPoints`, `objectiveScore`, identidade do revisor ou comentários internos.

O estudante pode receber a própria nota e o comentário final apenas depois da revisão. `REVIEWER`, `ADMIN` e `OWNER` recebem o contrato de staff com gabarito e pontuação necessários às operações autorizadas.

## Versão associada à tentativa

Ao iniciar a primeira tentativa, o backend guarda em `attempts.assessment_snapshot_json` uma cópia das questões, opções, gabarito e política. Um reenvio mantém o snapshot da tentativa devolvida. Assim, uma edição posterior do módulo não altera silenciosamente a avaliação em curso nem o resultado histórico.

As tentativas existentes são preenchidas pela migração com a versão disponível no momento da migração, identificada como `legacy-backfill`. Isso preserva o estado disponível, mas não consegue reconstruir versões anteriores que nunca tenham sido guardadas.

## Correção

Questões `SINGLE_CHOICE`, `TRUE_FALSE` e `MULTIPLE_CHOICE` são corrigidas no backend a partir do snapshot. A seleção múltipla exige correspondência exata do conjunto de opções corretas. A percentagem objetiva fica em `objective_score`, visível apenas ao staff.

Questões textuais, ficheiros e restantes trabalhos continuam no fluxo de revisão manual. A pontuação objetiva não substitui automaticamente a nota final da tentativa.

## Operação e rollout

1. Aplicar a migração versionada primeiro em staging e validar o backfill.
2. Confirmar que todas as tentativas têm um objeto com a chave `questions` no snapshot.
3. Publicar a API e o frontend.
4. Executar smoke tests com estudante e revisor sintéticos.

Se o snapshot estiver ausente após o rollout, a API falha de forma segura e não reconstrói o gabarito a partir da versão atual. O rollback operacional recomendado é voltar a aplicação e manter as colunas aditivas e os snapshots.

## Limites verificados

Os testes locais verificam contratos, política, isolamento por estudante e estabilidade da correção baseada no snapshot. A migração e os grants reais ainda precisam de validação numa base isolada de staging antes de produção.
