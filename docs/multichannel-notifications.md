# Notificações por Email e Telegram

A notificação interna continua a ser a fonte de verdade. WhatsApp, Email e
Telegram são canais opcionais e podem ser selecionados separadamente ou em
simultâneo no mesmo envio administrativo.

## Segurança e consentimento

- Apenas `OWNER` e `ADMIN` podem guardar configurações ou repetir entregas.
- Palavras-passe SMTP e tokens de bots são encriptados no PostgreSQL com
  `pgcrypto` e `NOTIFICATION_CONFIG_ENCRYPTION_KEY` (mínimo de 32 bytes).
- Os segredos desencriptados existem apenas no processo do servidor e nunca são
  incluídos nas respostas da API, auditoria ou vistas públicas.
- Cada canal exige consentimento próprio do estudante e uma preferência ativa
  para a categoria da atualização.
- O Telegram utiliza exclusivamente o `chat.id` numérico confirmado pelo bot;
  usernames digitados nunca são tratados como destinatários.

## Email (SMTP)

Variáveis opcionais: `EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`,
`SMTP_USE_TLS` e `SMTP_TIMEOUT_SECONDS`.

Defina também `PLATFORM_URL` para transformar destinos internos como
`#/notifications` em links completos nas mensagens de Email e Telegram.

A porta 465 utiliza SMTP sobre TLS com validação de certificado. Nas restantes
portas, `SMTP_USE_TLS=true` inicia STARTTLS e também valida o certificado. O
servidor pode ser usado sem autenticação ao deixar utilizador e palavra-passe
vazios, caso o relay SMTP o permita.

O painel não permite ativar uma configuração SMTP sem transporte seguro: use a
porta 465 ou mantenha a opção TLS ativa.

O painel usa o contrato:

```json
{
  "emailConfiguration": {
    "enabled": true,
    "smtpHost": "smtp.example.org",
    "smtpPort": 587,
    "smtpUsername": "notifications@example.org",
    "smtpPassword": "server-only",
    "fromEmail": "notifications@example.org",
    "fromName": "Plataforma de formação",
    "useTls": true,
    "removeSmtpPassword": false
  }
}
```

## Telegram

Crie um bot através do BotFather e configure `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_BOT_USERNAME`, `TELEGRAM_PARSE_MODE` e `TELEGRAM_TIMEOUT_SECONDS`, ou
guarde os mesmos dados pelo painel. `parseMode` aceita `HTML`, `MarkdownV2` ou
`NONE`.

O vínculo do estudante é verificável e não depende de entrada manual:

1. `studentStartTelegramLink` gera um token opaco, de uso único, válido por 15
   minutos e devolve `https://t.me/<bot>?start=<token>`.
2. O estudante abre o link e toca em **Iniciar** no bot.
3. `studentConfirmTelegramLink` consulta `getUpdates` sem long polling, processa
   todos os tokens pendentes e associa o `chat.id` privado ao estudante correto.
4. `studentUnlinkTelegram` elimina o vínculo e revoga o consentimento.

Este mecanismo requer que o bot não tenha um webhook ativo, pois a Bot API não
permite usar `getUpdates` e webhook simultaneamente.

## Fila, simultaneidade e repetição

Cada combinação `(notification_id, channel)` possui uma entrega independente.
Os workers reclamam linhas atomicamente com `FOR UPDATE SKIP LOCKED`, aplicam
uma licença de processamento de cinco minutos e limitam cada canal a três
tentativas. Uma falha externa nunca reverte a notificação interna.

O compositor aceita `sendWhatsApp`, `sendEmail` e `sendTelegram`. A repetição
administrativa aceita opcionalmente `channels: ["EMAIL", "TELEGRAM"]`; sem essa
lista, tenta os três canais.

## Aplicação do esquema

Execute `backend/courseplatform/schema.sql` na base de dados antes de ativar os
novos canais. Em instalações já existentes, o bootstrap idempotente da API
também adiciona as colunas e tabelas necessárias.
