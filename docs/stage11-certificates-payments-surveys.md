# Etapa 11: certificados, pagamentos e inquéritos

## Resultado

A certificação passa a usar um snapshot documental imutável na emissão. O mesmo contrato alimenta a pré-visualização administrativa, a área do estudante e o PDF. O snapshot v2 preserva:

- identidade do formando no momento da emissão;
- curso, versão publicada, carga horária, nota mínima e conteúdos certificados;
- número, código, data, classificação e nível de reconhecimento;
- identidade institucional, responsáveis e elementos gráficos;
- políticas de participação, certificado profissional, pagamento e downloads;
- configuração do inquérito aplicável no momento da emissão.

O hash SHA-256 do JSON canónico é guardado separadamente. A verificação pública compara esse hash e recusa documentos v2 alterados. Certificados antigos sem hash continuam identificados como `LEGACY_UNVERIFIED`; não são reescritos automaticamente.

## Reemissão

`adminRefreshCertificateFormat` permanece como adaptador temporário do frontend, mas agora executa uma reemissão individual:

1. bloqueia o certificado original na transação;
2. exige um motivo;
3. cria novo número, código, snapshot, hash e revisão;
4. marca o original como `SUPERSEDED`, sem alterar o snapshot anterior;
5. atualiza a associação do pedido financeiro, quando existir;
6. regista `CERTIFICATE_REISSUED` na auditoria.

Não existe reemissão em massa. Um índice parcial impede duas reemissões diretas concorrentes do mesmo documento. Estado e autorização de download continuam separados: um certificado bloqueado é reemitido bloqueado.

Quando um certificado profissional é apagado, bloqueado ou atinge o limite de
downloads, o estudante pode iniciar uma nova emissão. O pedido aprovado anterior
permanece histórico e nunca é reutilizado: o sistema cria uma nova solicitação,
um novo inquérito e, quando a política do curso for paga, exige novo pagamento e
novo comprovativo. Um certificado ainda disponível impede a cobrança duplicada.

## Separação funcional

- A lista de solicitações em **Certificações** não recebe respostas do inquérito.
- A página de **Inquéritos** solicita explicitamente `surveyOnly` e recebe as respostas.
- Novas respostas são gravadas em `certificate_survey_responses`, com perguntas e respostas congeladas; a migração copia respostas históricas sem apagar a coluna legada.
- Comprovativos permanecem no fluxo financeiro e no Storage privado.
- O certificado de participação continua configurável por curso, inclusive desativado, com janela, aprovação e limite de downloads.

## Migração

Aplicar `supabase/migrations/20260929120000_complete_stage11_certification_contract.sql` antes do backend correspondente. A migração é expansiva e não faz backfill destrutivo:

- documentos existentes ficam com versão/revisão 1 e hash nulo;
- novas emissões usam versão 2 e hash;
- não há remoção nem alteração do snapshot histórico;
- rollback operacional: voltar o backend anterior mantendo as colunas adicionais. Não remover colunas enquanto houver documentos v2.

A migração foi aplicada ao projeto Supabase principal em 30 de setembro de 2026,
antes do deploy do backend correspondente. A verificação pós-migração confirmou
o histórico remoto, o marcador da aplicação, RLS, privilégios mínimos e o
backfill completo das quatro respostas históricas. Ainda é necessário validar
em Preview ou produção controlada a emissão de participação e profissional,
pagamento, inquérito, PDF, QR, verificação pública, bloqueio, limite de download
e reemissão depois do deploy.
