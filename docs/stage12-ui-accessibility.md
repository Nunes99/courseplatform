# Etapa 12 - UI, navegação e acessibilidade

## Âmbito desta entrega

Esta primeira fatia estabelece a fundação transversal da Etapa 12 sem alterar regras de negócio:

- cada secção principal do painel administrativo possui URL própria por hash;
- a navegação restaura a secção pedida após recarregar a página;
- a secção ativa é exposta com `aria-current="page"`;
- o foco segue para o título principal após uma mudança de página;
- estudante e administração possuem ligação para saltar diretamente ao conteúdo;
- os diálogos comuns recebem nome acessível, foco contido, fecho por `Escape` e reposição do foco;
- carregamentos e notificações passam a expor semântica de estado;
- foco visível, alvos móveis e preferência por movimento reduzido são tratados globalmente.

## URLs administrativas

As secções usam `admin.html#/nome-da-seccao`, incluindo `overview`, `pending`, `gradebook`, `calendar`, `notifications`, `chat`, `students`, `courses`, `videos`, `brand`, `certifications`, `surveys`, `staff`, `credentials` e `profile`.

Uma URL indisponível para o papel autenticado é substituída pela página inicial permitida. Esta navegação não substitui a autorização do backend.

## Verificação local

```powershell
npm run qa:stage12-ui
npm run check:frontend
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

O teste de browser usa dados sintéticos e não comunica com produção. Valida desktop e mobile, URLs, estado ativo, foco, teclado, diálogo, cabeçalho fixo, overflow horizontal e erros de consola.

## Trabalho ainda pendente na Etapa 12

- rever visualmente cada página de dados extensos e cada estado vazio/erro;
- concluir uma passagem de texto e consistência editorial em toda a plataforma;
- validar os fluxos completos com leitor de ecrã real;
- medir contraste e reflow em todas as variantes de tema;
- recolher evidência visual em Preview com dados representativos.

Esses pontos não são declarados como concluídos por esta entrega.
