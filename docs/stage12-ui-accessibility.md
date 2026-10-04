# Etapa 12 - UI, navegação e acessibilidade

## Estado

Encerrada por aceitação do proprietário em 4 de outubro de 2026. A cobertura
automática descrita neste documento foi executada; as verificações que exigem
observação humana ou dispositivos reais foram dispensadas como porta de saída.
Isso não equivale a afirmar conformidade validada manualmente com NVDA ou em
todos os dispositivos.

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
npm run qa:stage12-accessibility
npm run qa:stage12-admin
npm run check:frontend
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Os testes de browser usam dados sintéticos e não comunicam com produção. Validam
desktop e mobile, URLs, estado ativo, foco, teclado, diálogo, cabeçalho fixo,
regiões de tabela, validação de formulários, estados vazios e de erro, menu móvel,
visibilidade de todos os campos de submissões, pauta, calendário, certificados,
pagamentos e inquéritos, overflow horizontal e erros de consola.

O comando `qa:stage12-accessibility` acrescenta uma passagem automatizada sobre
os temas claro e escuro. Mede contraste de texto segundo os limiares WCAG AA,
verifica nomes acessíveis, hierarquia de títulos, IDs, landmarks, árvore de
acessibilidade do Chromium, o equivalente ao zoom de 200% numa janela física de
1280 px e reflow adicional a 320 CSS pixels.

Os cenários dedicados de diálogo cobrem formulários de recuperação e cadastro,
inquérito, pagamento, detalhes em carregamento, pré-visualização de certificado
e seleção aninhada do banco de questões. O suporte transversal garante papel,
nome acessível, botão de fecho identificado, foco contido e retorno do foco para
os restantes diálogos construídos com a infraestrutura comum.

## Validação manual com NVDA

Esta validação deve ser feita no Edge ou Chrome com NVDA, primeiro no modo de
navegação e depois no modo de foco:

1. Abrir o login do estudante e confirmar que título, campos, erros, recuperação
   e criação de conta são anunciados com nome, papel e estado corretos.
2. Entrar como estudante e percorrer visão geral, curso, aula, submissão,
   certificados e pagamento apenas com `Tab`, `Shift+Tab`, `Enter` e setas.
3. Confirmar que mudanças de página anunciam o título e que mensagens de erro,
   carregamento, sucesso e estados vazios são anunciadas uma única vez.
4. Abrir os diálogos de submissão, pagamento e certificado; confirmar nome do
   diálogo, contenção do foco, fecho por `Escape` e retorno ao controlo de origem.
5. Entrar como revisor e percorrer submissões, pauta, calendário, certificados,
   pagamentos e inquéritos, confirmando cabeçalhos e relações das tabelas.
6. Repetir os fluxos principais nos temas claro e escuro, a 200% de zoom e com
   largura de 320 px, registando página, passo, anúncio recebido e resultado.

A execução desta checklist requer escuta e julgamento humano. A passagem
automatizada não deve ser apresentada como validação concluída com NVDA.

## Verificações manuais opcionais após o encerramento

- validar com dados reais os editores de versões de curso, módulos e banco de
  questões, cuja infraestrutura comum já possui cobertura automatizada;
- concluir uma passagem de texto e consistência editorial em toda a plataforma;
- validar os fluxos completos com leitor de ecrã real usando a checklist acima;
- confirmar visualmente em dispositivos reais os resultados automatizados de
  contraste e reflow nos dois temas;
- recolher evidência visual em Preview com dados representativos.

Esses pontos foram aceites como acompanhamento futuro e não bloqueiam o avanço
do plano. Permanecem explicitamente não executados até existir evidência humana.
