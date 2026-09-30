# Etapa 12 - UI, navegação e acessibilidade

## Âmbito desta entrega

Esta entrega estabelece a fundação transversal e conclui a segunda fatia da
Etapa 12, sem alterar regras de negócio:

- cada secção principal do painel administrativo possui URL própria por hash;
- a navegação restaura a secção pedida após recarregar a página;
- a secção ativa é exposta com `aria-current="page"`;
- o foco segue para o título principal após uma mudança de página;
- estudante e administração possuem ligação para saltar diretamente ao conteúdo;
- os diálogos comuns recebem nome acessível, foco contido, fecho por `Escape` e reposição do foco;
- carregamentos e notificações passam a expor semântica de estado;
- foco visível, alvos móveis e preferência por movimento reduzido são tratados globalmente.

## Listas, formulários e estados

- tabelas extensas são regiões identificadas e alcançáveis por teclado;
- os cabeçalhos de coluna recebem `scope="col"` e permanecem visíveis durante
  a deslocação vertical dentro da tabela;
- estudantes, cursos e notificações usam apresentação responsiva sem manter a
  navegação lateral sobre o conteúdo em ecrãs móveis;
- campos inválidos recebem `aria-invalid`, mensagem associada e anúncio de erro;
- falhas ao carregar páginas administrativas ou do estudante deixam de manter
  apenas o indicador de carregamento e passam a oferecer uma tentativa segura;
- listas vazias de submissões, estudantes e cursos explicam o estado e permitem
  limpar os filtros aplicados;
- pauta, calendário, certificados, pagamentos e inquéritos distinguem ausência
  de dados de pesquisas sem resultados e oferecem recuperação adequada;
- tabelas de submissões, pauta e calendário, bem como o registo de certificados,
  passam para registos verticais completos em mobile, sem esconder colunas;
- a exportação da pauta fica indisponível quando não existem linhas para exportar;
- textos administrativos revistos nesta fatia usam grafia consistente para
  estudantes, progresso, conclusão e publicação de vídeos.

## URLs administrativas

As secções usam `admin.html#/nome-da-seccao`, incluindo `overview`, `pending`, `gradebook`, `calendar`, `notifications`, `chat`, `students`, `courses`, `videos`, `brand`, `certifications`, `surveys`, `staff`, `credentials` e `profile`.

Uma URL indisponível para o papel autenticado é substituída pela página inicial permitida. Esta navegação não substitui a autorização do backend.

## Verificação local

```powershell
npm run qa:stage12-ui
npm run qa:stage12-admin
npm run check:frontend
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Os testes de browser usam dados sintéticos e não comunicam com produção. Validam
desktop e mobile, URLs, estado ativo, foco, teclado, diálogo, cabeçalho fixo,
regiões de tabela, validação de formulários, estados vazios e de erro, menu móvel,
visibilidade de todos os campos de submissões, pauta, calendário, certificados,
pagamentos e inquéritos, overflow horizontal e erros de consola.

## Trabalho ainda pendente na Etapa 12

- concluir a revisão individual dos editores internos e diálogos de detalhe que
  ainda não possuem cenários visuais dedicados;
- concluir uma passagem de texto e consistência editorial em toda a plataforma;
- validar os fluxos completos com leitor de ecrã real;
- medir contraste e reflow em todas as variantes de tema;
- recolher evidência visual em Preview com dados representativos.

Esses pontos não são declarados como concluídos por esta entrega.
