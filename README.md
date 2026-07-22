# CoursePlatform — GitHub + Tilda + Apps Script

Pacote completo da plataforma individual do curso **Economia e Avaliação de Projetos Industriais**.

## Estrutura

```text
courseplatform-github-tilda/
├── web/
│   ├── index.html
│   ├── admin.html
│   ├── verify.html
│   ├── connection-test.html
│   └── assets/
├── apps-script/
│   ├── Code.gs
│   └── src/
├── tilda/
├── .github/workflows/
└── docs/
```

## 1. Inicializar o Apps Script

Execute:

```javascript
setupCoursePlatformApi();
seedCoursePlatformContent();
installMaintenanceTrigger();
```

A função `seedCoursePlatformContent()` preenche:

- `Courses`
- `Lessons`
- `LessonContent`
- `Questions`
- `QuestionOptions`

## 2. Configurar a interface

Abra:

```text
web/assets/js/config.js
```

Substitua:

```javascript
apiUrl: 'COLE_AQUI_A_URL_EXEC_DO_APPS_SCRIPT'
publicAppUrl: 'COLE_AQUI_A_URL_DO_GITHUB_PAGES'
```

A URL da API deve terminar em `/exec`.

## 3. Publicar no GitHub Pages

1. Crie um repositório.
2. Envie todo o conteúdo deste pacote.
3. Abra **Settings → Pages**.
4. Em Source, escolha **GitHub Actions**.
5. O workflow publica automaticamente a pasta `web`.

Páginas:

```text
/                         Portal do estudante
/admin.html               Painel do avaliador
/verify.html              Verificação de certificado
/connection-test.html     Teste da API
```

## 4. Integrar no Tilda

Adicione:

```text
Block Library → Other → T123
```

Cole o conteúdo de:

```text
tilda/T123-course-platform.html
```

Substitua a URL completa e a origem do GitHub Pages.

Exemplo:

```text
URL: https://utilizador.github.io/repositorio
Origem: https://utilizador.github.io
```

## 5. Teste obrigatório

Abra `connection-test.html` antes do Tilda. O teste deve mostrar:

- API online;
- identificação da `CoursePlatformDB`;
- curso e três aulas.

Se aparecer `NETWORK_ERROR`, o navegador bloqueou a comunicação entre origens. Nesse caso, a alternativa imediata é hospedar a interface no Apps Script ou acrescentar um proxy HTTPS com os cabeçalhos CORS necessários.

## Segurança

- Nunca coloque a chave administrativa em `config.js`.
- O administrador introduz a chave apenas em `admin.html`.
- Não partilhe a Google Sheet com estudantes.
- Não exponha o campo `accessCode`.
- Use a URL `/exec`, nunca `/dev`.
