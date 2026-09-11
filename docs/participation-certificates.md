# Certificados de participacao

## Configuracao por curso

Em Administracao > Certificacoes > Configuracao do curso, o certificado de
participacao tem uma politica independente do certificado profissional:

- Disponibilizar ou desativar a emissao e o acesso dos estudantes.
- Libertacao automatica apos conclusao ou mediante aprovacao administrativa.
- Limite de 1 a 1000 downloads por estudante; campo vazio significa sem limite.
- Inicio e fim opcionais do periodo de download, gravados com fuso horario UTC.
- Condicoes adicionais visiveis para o estudante (texto informativo, sem
  validacao automatica de requisitos externos).

O certificado de participacao continua gratuito. Desative-o e mantenha a politica
profissional com pagamento obrigatorio para cursos sem certificado gratuito.

## Aprovacao e recuperacao de acesso

O estudante solicita acesso em Minhas certificacoes. O pedido surge na lista de
pedidos do admin identificado como Participacao e nao necessita de comprovativo.
Internamente reutiliza o estado PAYMENT_SUBMITTED (pronto para revisao), mas o
tipo PARTICIPATION impede confundir este fluxo com um pagamento profissional.

A aprovacao restaura o mesmo certificado e reinicia o contador de downloads;
o contador anterior fica registado na auditoria. A libertacao individual permite
escolher se o contador deve ser reiniciado. Nenhuma destas operacoes ultrapassa
a desativacao ou o periodo de acesso definidos no curso.

Certificados apagados nao sao recriados automaticamente ao abrir a pagina.
Podem ser reatribuidos pelo administrador ou mediante um novo pedido aprovado.

## Compatibilidade e seguranca

A politica fica em certificate_settings.certificate_profile_json.participation.
Nao e necessaria nova tabela, migracao SQL nem variavel de ambiente. Cursos sem
esta configuracao mantem o comportamento anterior: gratuito, automatico e sem
limite. Atualizacoes parciais do perfil preservam a politica existente.

As regras de acesso atuais aplicam-se tambem aos certificados antigos, mas nao
reescrevem o conteudo nem o template_snapshot_json capturado na emissao. PDFs ja
descarregados nao podem ser retirados dos dispositivos dos estudantes.

Os endpoints de PDF e de contagem verificam propriedade, estado e politica. A
contagem usa bloqueio de linha para que downloads concorrentes nao excedam a
quota. A pre-visualizacao administrativa nao consome a quota do estudante.

## Verificacao local

`python -m unittest discover -s tests -v`

`node scripts/verify_participation_policy.cjs` (Playwright e Chrome locais;
PREVIEW_URL e PLAYWRIGHT_MODULE configuraveis).

Os testes usam uma base simulada e pedidos de API simulados no navegador. Nao
alteram dados de producao nem substituem a validacao num ambiente Supabase de teste.
