# Alteração segura do email de acesso

O email é um identificador de autenticação e não é tratado como um campo comum
do perfil.

## Alteração pelo estudante

O estudante informa duas vezes o novo endereço e confirma a operação com a
palavra-passe atual. Depois da alteração:

- todas as sessões do estudante são revogadas;
- o novo login utiliza o novo email e a mesma palavra-passe;
- o consentimento para notificações por email é retirado;
- entregas pendentes para o endereço anterior são canceladas;
- a operação é registada na auditoria com endereços mascarados.

## Correção pela administração

Apenas perfis `OWNER` e `ADMIN` podem corrigir o email de um estudante. A
operação exige confirmação com a palavra-passe do próprio administrador, dupla
digitação do novo endereço, confirmação de verificação junto do estudante e um
motivo de auditoria.

O administrador permanece autenticado, mas todas as sessões do estudante são
encerradas. A palavra-passe do estudante não é alterada.

## Garantias do servidor

- normalização para minúsculas e validação do formato;
- verificação de unicidade sem confiar no navegador;
- atualização transacional com bloqueio do registo do estudante;
- mensagens de erro sem palavras-passe ou endereços completos;
- nenhuma palavra-passe é guardada ou incluída na auditoria;
- notificações internas de segurança não são encaminhadas para canais externos.
