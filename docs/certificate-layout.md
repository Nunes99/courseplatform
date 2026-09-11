# Certificado profissional

O modelo continua em A4 horizontal, com identidade e registo à esquerda,
formando e programa à direita, e áreas próprias para assinaturas, carimbo,
selo e verificação. Os elementos gráficos continuam opcionais.

## Ficheiros

- `backend/courseplatform/static/assets/certificate-layout.json`: medidas em pontos,
  limites dos textos, cores e áreas gráficas. A cópia em `public/assets/` deve ser idêntica.
- `backend/courseplatform/certificate_pdf.py`: PDF ReportLab, com fonte incorporada.
- `public/professional-certificate.js`: componente partilhado entre o admin,
  a miniatura de configuração e a área do estudante. O SVG está isolado num Shadow DOM.
- `public/assets/fonts/`: Bitstream Vera, com licença de redistribuição.
- `public/vendor/qrcode-generator.mjs`: qrcode-generator 2.0.4, licença MIT.

O PDF e o SVG usam as mesmas medidas, tamanhos mínimos, fonte e quebras de linha.
O ajuste ao ecrã altera a escala da folha inteira. A ampliação não reorganiza os textos.
O QR tem fundo branco e margem de quatro módulos. O endereço usa a página de verificação da API.

## Dados e validação

A configuração guardada no certificado continua a ser a fonte dos dados.
A pré-visualização do formulário reflete as alterações locais antes de guardar.
Não são necessárias alterações ao schema, às permissões nem ao fluxo de pagamentos.
O acesso ao download continua a passar pelo endpoint autenticado existente.

O certificado admite até oito conteúdos resumidos. Textos que não cabem na sua
área ao tamanho mínimo são sinalizados; o gerador não corta nomes nem omite conteúdos.
Um erro de composição devolve `CERTIFICATE_LAYOUT_INVALID` sem consumir um download.

## Verificação local

Dependências de QA: `pypdf`, `pypdfium2`, `zxing-cpp`, `httpx` e Playwright.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_certificate*.py' -v
.venv/Scripts/python.exe scripts/preview_professional_certificate.py
# Com o servidor local em execução:
node scripts/verify_certificate_browser.cjs
```

O teste de navegador aceita `PREVIEW_URL`, `PLAYWRIGHT_MODULE` e `CHROME_PATH`.
Usa dados sintéticos e interceta pedidos à API; não acede a contas de estudantes.
Testa ambos os painéis, três tamanhos de ecrã, ampliação, miniatura, nomes longos e excesso de texto.
O script de PDF gera um exemplo e confirma o QR com um descodificador independente.

Na publicação, sincronizar os ficheiros públicos alterados com
`backend/courseplatform/static/`, incluindo fontes e biblioteca QR.
