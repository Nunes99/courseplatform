# Etapa 8: monólito modular

Data: 15 de setembro de 2026.

## Objetivo e estado

Esta primeira fatia estabelece fronteiras internas sem alterar contratos HTTP,
regras de autorização, SQL, dados ou URLs. A Etapa 8 ainda não está concluída:
os handlers com regras e consultas continuam maioritariamente em `actions.py` e
serão extraídos verticalmente, com testes, nas fatias seguintes.

Verificado nesta entrega:

- as 115 ações externas continuam registadas e têm handlers chamáveis;
- cada ação pertence a exatamente um dos nove domínios;
- `actions.ApiError` e os helpers públicos usados pelos testes continuam
  disponíveis por compatibilidade;
- imports de `app.py`, dispatcher e domínios não formam ciclos;
- `public/` e a distribuição empacotada têm paridade integral;
- os entrypoints e URLs do frontend não mudaram.

Não verificado nesta entrega: produção, staging, Supabase remoto, Vercel,
desempenho sob carga e fluxos com dados reais.

## Fronteiras atuais

| Domínio | Responsabilidade |
| --- | --- |
| `identity` | login, sessões, recuperação e perfil |
| `catalog` | cursos, versões, módulos, conteúdo e media |
| `enrollments` | ofertas/turmas, matrículas e grupos |
| `learning` | dashboard, acesso e progresso |
| `assessments` | tentativas, respostas, ficheiros e revisão |
| `certificates` | emissão, configuração, inquéritos e downloads |
| `financial` | pedidos e comprovativos de certificados |
| `communication` | notificações, canais, Telegram, push e chat |
| `administration` | health, estatísticas, estudantes e staff |

`domains/registry.py` valida duplicações e handlers ausentes ao importar a
aplicação. O dispatcher continua mutável para preservar testes e aliases atuais.
Os helpers de contratos e paginação foram movidos para `contracts.py`; identidade
já contém normalização, política mínima de senha, geração do ID público e
serializadores com dependências explícitas.

## Frontend

Edite apenas `public/`. Depois execute:

```powershell
node scripts/sync_frontend.cjs
node scripts/sync_frontend.cjs --check
```

O primeiro comando recria `backend/courseplatform/static/`; o segundo não
escreve e falha perante ficheiro ausente, obsoleto ou diferente. Com npm
disponível, use `npm run sync:frontend` e `npm run check:frontend`.

Os primeiros componentes extraídos são deliberadamente pequenos: paginação das
listas administrativas, parser das rotas do estudante e tokens CSS. Isso reduz
risco antes de mover páginas que partilham estado global.

## Estratégia das próximas fatias

Cada handler será separado em validação de entrada, serviço/regra de negócio,
consulta/transação explícita e serialização. Enquanto testes ainda substituírem
dependências em `actions`, o adaptador construirá essas dependências em tempo de
chamada. Isso mantém os contratos observáveis sem criar um repositório genérico
que esconda SQL ou autorização.

A próxima fatia recomendada é identidade e recuperação de acesso completas.
Depois seguem avaliações/submissões, certificados/pagamentos, catálogo/matrículas
e comunicação/chat. Nenhuma dessas extrações foi iniciada aqui.

## Impacto operacional

Não há migração SQL nem backfill. Não há alteração de IDs, relações ou dados
históricos. Não foi feito deploy. O único passo adicional de empacotamento é a
sincronização determinística dos assets antes dos testes/deploy.
