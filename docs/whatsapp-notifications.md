# Notificações internas e WhatsApp

A plataforma guarda sempre a notificação interna antes de tentar o envio externo. Uma falha no WhatsApp não anula a alteração administrativa nem remove a atualização da central do estudante.

## Preparação na Meta

1. Crie ou associe um portefólio empresarial, uma conta WhatsApp Business e um número empresarial.
2. Obtenha o `Phone Number ID` e um token de acesso adequado ao ambiente de produção.
3. Crie e submeta para aprovação um modelo de mensagem de utilidade com quatro variáveis no corpo.

Modelo sugerido:

```text
Olá, {{1}}.

{{2}}
{{3}}

Consulte os detalhes na plataforma: {{4}}
```

As variáveis recebem, por ordem:

1. Nome do estudante.
2. Título da atualização.
3. Mensagem.
4. Link para a plataforma.

Referências oficiais: [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/) e [política do WhatsApp Business](https://whatsappbusiness.com/policy/).

## Variáveis do servidor

```env
WHATSAPP_ENABLED=true
WHATSAPP_ACCESS_TOKEN=token_protegido
WHATSAPP_PHONE_NUMBER_ID=identificador_do_numero
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_TEMPLATE_NAME=nome_do_modelo_aprovado
WHATSAPP_TEMPLATE_LANGUAGE=pt_PT
WHATSAPP_PLATFORM_URL=https://endereco-da-plataforma/
WHATSAPP_TIMEOUT_SECONDS=12
```

O token nunca deve ser colocado no frontend, em `config.js` ou no repositório.

## Consentimento

O estudante ativa o canal no próprio perfil e informa o telefone com indicativo internacional, por exemplo `+258`. Pode desativar o canal ou tipos específicos de atualização a qualquer momento.

## Entregas

- `PENDING`: aguarda configuração ou tentativa de envio.
- `SENT`: aceite pela API da Meta.
- `FAILED`: a tentativa falhou e pode ser repetida no painel.
- `SKIPPED`: o estudante não autorizou o canal, desativou a categoria ou não possui telefone válido.

O painel administrativo mostra apenas o estado da configuração; nunca devolve o token ao navegador.
