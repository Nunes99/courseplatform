# Notificações internas, Email, Telegram e Web Push

A notificação interna continua a ser a fonte de verdade. WhatsApp, Email,
Telegram e Web Push são canais opcionais e podem ser selecionados separadamente
ou em simultâneo no mesmo envio administrativo.

## Segurança e consentimento

- Apenas `OWNER` e `ADMIN` podem guardar configurações ou repetir entregas.
- Palavras-passe SMTP e tokens de bots são encriptados no PostgreSQL com
  `pgcrypto` e `NOTIFICATION_CONFIG_ENCRYPTION_KEY` (mínimo de 32 bytes).
- Os segredos desencriptados existem apenas no processo do servidor e nunca são
  incluídos nas respostas da API, auditoria ou vistas públicas.
- Cada canal exige consentimento próprio do estudante e uma preferência ativa
  para a categoria da atualização.
- No Web Push, a subscrição do navegador representa o consentimento do
  dispositivo. Endpoint e chaves da subscrição são encriptados na base de dados.
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

## Web Push e aplicação instalável

O site inclui `manifest.webmanifest` e `sw.js`. O estudante pode guardar a
plataforma no ecrã principal e ativar notificações no perfil ou na recomendação
apresentada em dispositivos móveis. A autorização só é pedida após uma ação
explícita do estudante.

Ao abrir o perfil, o assistente de instalação volta a ser apresentado enquanto
o dispositivo ainda não estiver identificado como instalado. Depois da
instalação, um segundo diálogo recomenda a ativação do Push; ele continua a ser
apresentado nos acessos seguintes ao perfil até a subscrição deste dispositivo
estar ativa. Se o navegador tiver bloqueado a permissão, o diálogo troca a ação
automática por instruções para rever as definições do site.

Configure no ambiente do servidor:

```dotenv
WEB_PUSH_ENABLED=true
VAPID_PUBLIC_KEY=CHAVE_PUBLICA_BASE64URL
VAPID_PRIVATE_KEY=CHAVE_PRIVADA_BASE64URL
VAPID_SUBJECT=mailto:suporte@example.org
WEB_PUSH_TTL_SECONDS=86400
WEB_PUSH_TIMEOUT_SECONDS=12
PLATFORM_URL=https://example.org/plataforma/
NOTIFICATION_CONFIG_ENCRYPTION_KEY=CHAVE_ALEATORIA_COM_PELO_MENOS_32_BYTES
```

Gere um único par VAPID e mantenha-o estável entre publicações:

```powershell
python scripts/generate_vapid_keys.py
```

Copie o resultado para as variáveis do ambiente de produção. A chave privada
nunca deve ser colocada em JavaScript, no repositório ou no painel público. Não
troque o par VAPID sem necessidade, porque as subscrições já criadas dependem da
mesma identidade de aplicação.

No iPhone e iPad, o estudante deve abrir a plataforma no Safari, usar
**Partilhar → Adicionar ao ecrã principal**, abrir a aplicação pelo novo ícone e
só depois tocar em **Ativar notificações**. Nos navegadores compatíveis com o
diálogo de instalação, o botão **Guardar aplicação** utiliza o diálogo nativo.

As entregas expiradas (`HTTP 404` ou `410`) desativam automaticamente a
subscrição. Outras falhas são contabilizadas e a subscrição é desativada após
falhas repetidas.

## Personalização dos textos

No painel administrativo, a secção **Notificações → Modelos de notificações**
permite editar, por evento automático:

- título e mensagem da notificação interna;
- assunto e mensagem do Email;
- título e mensagem curta do Push.

Os modelos aceitam apenas as variáveis apresentadas pelo painel, por exemplo
`{{student_name}}`, `{{module}}`, `{{activity}}`, `{{status}}`, `{{deadline}}`,
`{{feedback}}`, `{{details}}` e `{{action_url}}`. O servidor valida as variáveis,
limita os tamanhos e guarda em cada notificação uma cópia já renderizada. Assim,
uma alteração posterior do modelo não muda o histórico.

No envio manual, os campos específicos de Email e Push são opcionais. Quando
ficam vazios, o servidor reutiliza o título e a mensagem interna.

## Fila, simultaneidade e repetição

Cada combinação `(notification_id, channel)` possui uma entrega independente.
Os workers reclamam linhas atomicamente com `FOR UPDATE SKIP LOCKED`, aplicam
uma licença de processamento de cinco minutos e limitam cada canal a três
tentativas. Uma falha externa nunca reverte a notificação interna.

O compositor aceita `sendWhatsApp`, `sendEmail`, `sendTelegram` e `sendPush`. A
repetição administrativa aceita opcionalmente
`channels: ["EMAIL", "TELEGRAM", "PUSH"]`; sem essa lista, tenta os quatro
canais.

## Aplicação do esquema

Execute `backend/courseplatform/schema.sql` na base de dados antes de ativar os
novos canais. Em instalações já existentes, o bootstrap idempotente da API
também adiciona as colunas e tabelas necessárias.
