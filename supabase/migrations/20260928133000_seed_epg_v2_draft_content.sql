-- Conteúdo académico versionado para COURSE-EPG-001.
-- Cria exclusivamente a versão 2 em rascunho e versões publicadas do banco de
-- questões. Não altera a versão 1 publicada, ofertas, matrículas ou históricos.
--
-- Rollback operacional (apenas enquanto CRSV-EPG-001-V2 permanecer DRAFT e
-- sem referências posteriores): remover a versão 2 e, em seguida, as opções,
-- versões e itens QB-EPG-001-*. Nunca remover ou reescrever a versão 1.

set lock_timeout = '5s';
set statement_timeout = '120s';

do $migration$
declare
  snapshot jsonb := $course_snapshot$
{
  "schemaVersion": 1,
  "authoredAt": "2026-09-28",
  "editorialStatus": "ACADEMIC_REVIEW_REQUIRED",
  "course": {
    "course_id": "COURSE-EPG-001",
    "course_code": "EPG-001",
    "title": "História da Indústria Petrolífera Moçambicana",
    "description": "Percurso introdutório sobre a evolução histórica, a cadeia de valor, as instituições, a regulação e os desafios da transição energética em Moçambique.",
    "total_hours": 12,
    "passing_score": 60
  },
  "lessons": [
    {
      "lesson_id": "LESSON-EAPI-004",
      "lesson_number": 1,
      "title": "Fundamentos da Indústria Petrolífera Moçambicana",
      "summary": "Evolução histórica, cadeia de valor e instituições do setor petrolífero moçambicano.",
      "status": "ACTIVE",
      "prerequisite_lesson_id": null,
      "assessment_attempt_limit": 2,
      "assessment_available_from": null,
      "assessment_available_until": null,
      "submission_duration_minutes": 60,
      "assessment_randomization_mode": "QUESTIONS_AND_OPTIONS",
      "assessment_question_limit": 5,
      "passing_score": 60,
      "feedback_release_mode": "AFTER_REVIEW",
      "show_correct_answers": true,
      "show_explanations": true,
      "content": [
        {
          "content_id": "CONTENT-EPG-001-01",
          "section_order": 1,
          "section_type": "READING",
          "title": "Marcos históricos do petróleo e gás em Moçambique",
          "body_html": "<p>A história moderna do setor começa com as primeiras atividades de pesquisa registadas em 1904. As descobertas de gás em Pande, Buzi e Temane, nas décadas de 1960, estabeleceram a base geológica do setor. A criação da Empresa Nacional de Hidrocarbonetos, em 1981, reforçou a participação do Estado. A produção comercial do gás de Pande e Temane iniciou-se em 2004; as descobertas na Bacia do Rovuma, a partir de 2010, ampliaram a dimensão internacional do setor; e o início da produção de GNL do Coral Sul, em 2022, marcou a entrada do país na produção offshore de GNL.</p><p><strong>Objetivo de aprendizagem:</strong> ordenar os principais marcos e explicar por que cada um alterou a escala, as instituições ou as possibilidades económicas do setor.</p>",
          "estimated_minutes": 90,
          "is_required": true,
          "status": "ACTIVE",
          "sources": [
            {"title": "INP - Historial do INP", "url": "https://www.inp.gov.mz/historial-do-inp/"},
            {"title": "INP - Hidrocarbonetos", "url": "https://www.inp.gov.mz/hidrocarbonetos/"}
          ]
        },
        {
          "content_id": "CONTENT-EPG-001-02",
          "section_order": 2,
          "section_type": "READING",
          "title": "Da pesquisa ao consumidor: a cadeia de valor",
          "body_html": "<p>A cadeia de valor organiza-se em três blocos. O <strong>upstream</strong> inclui pesquisa, avaliação, desenvolvimento e produção. O <strong>midstream</strong> cobre processamento, armazenamento e transporte. O <strong>downstream</strong> inclui refinação, distribuição e comercialização de produtos.</p><p>Um projeto avança por decisões sucessivas: interpretar dados geológicos, perfurar, avaliar a descoberta, demonstrar viabilidade, desenvolver instalações, produzir e entregar energia ao mercado. Cada etapa tem riscos técnicos, ambientais, financeiros e sociais próprios. Em Moçambique, distinguir estes blocos ajuda a compreender projetos de gás canalizado e GNL sem confundir reservas, capacidade de produção e receitas efetivamente realizadas.</p>",
          "estimated_minutes": 90,
          "is_required": true,
          "status": "ACTIVE",
          "sources": [
            {"title": "INP - Projetos", "url": "https://www.inp.gov.mz/projectos/"}
          ]
        },
        {
          "content_id": "CONTENT-EPG-001-03",
          "section_order": 3,
          "section_type": "READING",
          "title": "Instituições, papéis e interesse público",
          "body_html": "<p>A governação do setor exige separar formulação de política, regulação e participação empresarial do Estado. O ministério competente orienta a política pública; o Instituto Nacional de Petróleo regula, licencia e fiscaliza operações petrolíferas; e a Empresa Nacional de Hidrocarbonetos representa interesses comerciais do Estado em projetos.</p><p>Esta separação reduz conflitos de função e permite avaliar decisões sob critérios de legalidade, segurança, proteção ambiental, benefício económico e transparência. O estudante deve identificar a instituição adequada para cada decisão e evitar atribuir ao regulador funções comerciais ou ao operador poderes regulatórios.</p>",
          "estimated_minutes": 90,
          "is_required": true,
          "status": "ACTIVE",
          "sources": [
            {"title": "INP - Historial do INP", "url": "https://www.inp.gov.mz/historial-do-inp/"},
            {"title": "INP - Políticas e quadro legal", "url": "https://www.inp.gov.mz/politicas-e-quadro-legal/"}
          ]
        },
        {
          "content_id": "CONTENT-EPG-001-04",
          "section_order": 4,
          "section_type": "CASE_STUDY",
          "title": "Estudo orientado: construir uma cronologia com evidências",
          "body_html": "<p>Construa uma cronologia com seis marcos: início da pesquisa, descobertas de Pande/Buzi/Temane, criação da ENH, início da produção comercial, descobertas do Rovuma e início do GNL do Coral Sul. Para cada marco, registe a data, a fonte, a alteração produzida e uma questão que ainda precise de investigação.</p><p>Na síntese, diferencie factos comprovados, interpretação e expectativa. Não trate recursos descobertos como receitas imediatas nem confunda anúncio de projeto com produção efetiva.</p>",
          "estimated_minutes": 90,
          "is_required": true,
          "status": "ACTIVE",
          "sources": [
            {"title": "INP - Hidrocarbonetos", "url": "https://www.inp.gov.mz/hidrocarbonetos/"}
          ]
        }
      ],
      "questions": [
        {
          "question_id": "QUESTION-EPG-001-01", "question_order": 1,
          "bank_question_id": "QB-EPG-001-01", "bank_question_version_id": "QBVER-EPG-001-01-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M1-Q01", "title": "Início da produção comercial", "question_type": "SINGLE_CHOICE",
          "prompt": "Em que ano começou a produção comercial do gás natural de Pande e Temane?",
          "explanation": "O projeto de Pande e Temane iniciou a produção comercial em 2004.", "difficulty": "EASY", "tags": ["história", "pande-temane"], "points": 10, "correct_answer": "B", "status": "ACTIVE",
          "options": [
            {"option_id": "OPTION-EPG-001-01-A", "bank_option_id": "QBOPT-EPG-001-01-A", "option_order": 1, "option_label": "A", "option_text": "1981", "is_correct": false},
            {"option_id": "OPTION-EPG-001-01-B", "bank_option_id": "QBOPT-EPG-001-01-B", "option_order": 2, "option_label": "B", "option_text": "2004", "is_correct": true},
            {"option_id": "OPTION-EPG-001-01-C", "bank_option_id": "QBOPT-EPG-001-01-C", "option_order": 3, "option_label": "C", "option_text": "2010", "is_correct": false},
            {"option_id": "OPTION-EPG-001-01-D", "bank_option_id": "QBOPT-EPG-001-01-D", "option_order": 4, "option_label": "D", "option_text": "2022", "is_correct": false}
          ]
        },
        {
          "question_id": "QUESTION-EPG-001-02", "question_order": 2,
          "bank_question_id": "QB-EPG-001-02", "bank_question_version_id": "QBVER-EPG-001-02-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M1-Q02", "title": "Atividade upstream", "question_type": "SINGLE_CHOICE",
          "prompt": "Qual atividade pertence principalmente ao segmento upstream?",
          "explanation": "O upstream reúne pesquisa, avaliação, desenvolvimento e produção de hidrocarbonetos.", "difficulty": "EASY", "tags": ["cadeia-de-valor", "upstream"], "points": 10, "correct_answer": "A", "status": "ACTIVE",
          "options": [
            {"option_id": "OPTION-EPG-001-02-A", "bank_option_id": "QBOPT-EPG-001-02-A", "option_order": 1, "option_label": "A", "option_text": "Pesquisa e produção", "is_correct": true},
            {"option_id": "OPTION-EPG-001-02-B", "bank_option_id": "QBOPT-EPG-001-02-B", "option_order": 2, "option_label": "B", "option_text": "Venda a retalho de combustíveis", "is_correct": false},
            {"option_id": "OPTION-EPG-001-02-C", "bank_option_id": "QBOPT-EPG-001-02-C", "option_order": 3, "option_label": "C", "option_text": "Distribuição de produtos refinados", "is_correct": false},
            {"option_id": "OPTION-EPG-001-02-D", "bank_option_id": "QBOPT-EPG-001-02-D", "option_order": 4, "option_label": "D", "option_text": "Comercialização ao consumidor final", "is_correct": false}
          ]
        },
        {
          "question_id": "QUESTION-EPG-001-03", "question_order": 3,
          "bank_question_id": "QB-EPG-001-03", "bank_question_version_id": "QBVER-EPG-001-03-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M1-Q03", "title": "Papel do regulador", "question_type": "SINGLE_CHOICE",
          "prompt": "Qual descrição corresponde melhor ao papel do Instituto Nacional de Petróleo?",
          "explanation": "O INP exerce funções de regulação, licenciamento e fiscalização das operações petrolíferas.", "difficulty": "MEDIUM", "tags": ["instituições", "regulação"], "points": 10, "correct_answer": "C", "status": "ACTIVE",
          "options": [
            {"option_id": "OPTION-EPG-001-03-A", "bank_option_id": "QBOPT-EPG-001-03-A", "option_order": 1, "option_label": "A", "option_text": "Operar comercialmente todos os campos", "is_correct": false},
            {"option_id": "OPTION-EPG-001-03-B", "bank_option_id": "QBOPT-EPG-001-03-B", "option_order": 2, "option_label": "B", "option_text": "Definir sozinho toda a política energética", "is_correct": false},
            {"option_id": "OPTION-EPG-001-03-C", "bank_option_id": "QBOPT-EPG-001-03-C", "option_order": 3, "option_label": "C", "option_text": "Regular, licenciar e fiscalizar operações petrolíferas", "is_correct": true},
            {"option_id": "OPTION-EPG-001-03-D", "bank_option_id": "QBOPT-EPG-001-03-D", "option_order": 4, "option_label": "D", "option_text": "Substituir as empresas concessionárias", "is_correct": false}
          ]
        },
        {
          "question_id": "QUESTION-EPG-001-04", "question_order": 4,
          "bank_question_id": "QB-EPG-001-04", "bank_question_version_id": "QBVER-EPG-001-04-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M1-Q04", "title": "Impacto das descobertas do Rovuma", "question_type": "SINGLE_CHOICE",
          "prompt": "Qual foi um efeito central das grandes descobertas de gás na Bacia do Rovuma a partir de 2010?",
          "explanation": "As descobertas ampliaram a escala internacional do setor e sustentaram projetos de GNL, sem significar receitas automáticas ou imediatas.", "difficulty": "MEDIUM", "tags": ["rovuma", "gnl"], "points": 10, "correct_answer": "D", "status": "ACTIVE",
          "options": [
            {"option_id": "OPTION-EPG-001-04-A", "bank_option_id": "QBOPT-EPG-001-04-A", "option_order": 1, "option_label": "A", "option_text": "Eliminou a necessidade de regulação", "is_correct": false},
            {"option_id": "OPTION-EPG-001-04-B", "bank_option_id": "QBOPT-EPG-001-04-B", "option_order": 2, "option_label": "B", "option_text": "Transformou imediatamente todas as reservas em receitas", "is_correct": false},
            {"option_id": "OPTION-EPG-001-04-C", "bank_option_id": "QBOPT-EPG-001-04-C", "option_order": 3, "option_label": "C", "option_text": "Encerrou os projetos no sul do país", "is_correct": false},
            {"option_id": "OPTION-EPG-001-04-D", "bank_option_id": "QBOPT-EPG-001-04-D", "option_order": 4, "option_label": "D", "option_text": "Ampliou a escala internacional do setor e viabilizou projetos de GNL", "is_correct": true}
          ]
        },
        {
          "question_id": "QUESTION-EPG-001-05", "question_order": 5,
          "bank_question_id": "QB-EPG-001-05", "bank_question_version_id": "QBVER-EPG-001-05-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M1-Q05", "title": "Síntese histórica fundamentada", "question_type": "LONG_TEXT",
          "prompt": "Selecione três marcos da história petrolífera moçambicana e explique, com base nas fontes do módulo, como cada um alterou a escala ou a organização institucional do setor.",
          "explanation": "A resposta deve apresentar três marcos datados, relacionar causa e efeito e distinguir factos, interpretação e expectativas.", "difficulty": "HARD", "tags": ["síntese", "história", "argumentação"], "points": 60,
          "correct_answer": "Rubrica: três marcos corretos e datados (30%); explicação do efeito de cada marco (40%); uso de fontes e distinção entre facto e interpretação (20%); clareza e organização (10%).", "status": "ACTIVE", "options": []
        }
      ]
    },
    {
      "lesson_id": "LESSON-EAPI-005",
      "lesson_number": 2,
      "title": "Exploração, Regulação e Transição Energética",
      "summary": "Infraestruturas de gás e GNL, quadro regulatório, valor nacional e escolhas da transição energética.",
      "status": "ACTIVE",
      "prerequisite_lesson_id": "LESSON-EAPI-004",
      "assessment_attempt_limit": 2,
      "assessment_available_from": null,
      "assessment_available_until": null,
      "submission_duration_minutes": 60,
      "assessment_randomization_mode": "QUESTIONS_AND_OPTIONS",
      "assessment_question_limit": 5,
      "passing_score": 60,
      "feedback_release_mode": "AFTER_REVIEW",
      "show_correct_answers": true,
      "show_explanations": true,
      "content": [
        {
          "content_id": "CONTENT-EPG-001-05", "section_order": 1, "section_type": "READING",
          "title": "Infraestruturas de gás natural e GNL",
          "body_html": "<p>Uma cadeia de gás pode incluir reservatório, poços, instalações de recolha, processamento, gasoduto e entrega a consumidores. Quando o destino exige transporte marítimo, o gás é tratado e arrefecido até se tornar GNL, carregado em navios e posteriormente regaseificado ou utilizado conforme a infraestrutura do mercado de destino.</p><p>Cada interface exige medição, segurança de processo, manutenção e resposta a emergências. A existência de reservas não substitui estudos de viabilidade, contratos, financiamento, licenças, infraestrutura e capacidade operacional.</p>",
          "estimated_minutes": 90, "is_required": true, "status": "ACTIVE",
          "sources": [{"title": "INP - Projetos", "url": "https://www.inp.gov.mz/projectos/"}]
        },
        {
          "content_id": "CONTENT-EPG-001-06", "section_order": 2, "section_type": "READING",
          "title": "Regulação, concessões e proteção do interesse público",
          "body_html": "<p>O quadro regulatório estabelece como os direitos petrolíferos são atribuídos, exercidos, fiscalizados e encerrados. Na análise de uma concessão, importa considerar obrigações técnicas, fiscais, ambientais, de segurança, conteúdo local, prestação de informação e abandono responsável.</p><p>As normas podem mudar. Por isso, decisões operacionais devem consultar sempre a legislação e os instrumentos contratuais vigentes, além de orientação jurídica competente. O objetivo académico desta secção é compreender a função das regras e não prestar aconselhamento jurídico.</p>",
          "estimated_minutes": 90, "is_required": true, "status": "ACTIVE",
          "sources": [
            {"title": "INP - Políticas e quadro legal", "url": "https://www.inp.gov.mz/politicas-e-quadro-legal/"},
            {"title": "INP - Nova Lei de Petróleos", "url": "https://inp.gov.mz/assembleia-da-republica-aprova-nova-lei-de-petroleos/"}
          ]
        },
        {
          "content_id": "CONTENT-EPG-001-07", "section_order": 3, "section_type": "READING",
          "title": "Valor nacional, competências e gestão de riscos",
          "body_html": "<p>O benefício nacional pode resultar do abastecimento ao mercado interno, receitas públicas, emprego qualificado, desenvolvimento de fornecedores, infraestrutura e transferência de competências. Estes benefícios não são automáticos: dependem de planeamento, capacidade institucional, transparência, competição, formação e acompanhamento de resultados.</p><p>Uma avaliação equilibrada inclui custos de oportunidade, volatilidade dos mercados, impactos ambientais e sociais, segurança, ritmo de desenvolvimento e capacidade de absorção da economia. Conteúdo local sustentável desenvolve empresas e pessoas competitivas, em vez de medir apenas compromissos declarados.</p>",
          "estimated_minutes": 90, "is_required": true, "status": "ACTIVE",
          "sources": [{"title": "INP - Políticas e quadro legal", "url": "https://www.inp.gov.mz/politicas-e-quadro-legal/"}]
        },
        {
          "content_id": "CONTENT-EPG-001-08", "section_order": 4, "section_type": "CASE_STUDY",
          "title": "Caso aplicado: gás e transição energética",
          "body_html": "<p>A Estratégia de Transição Energética de Moçambique organiza-se em quatro pilares: expansão de energias renováveis, industrialização verde, acesso universal a energias modernas e transportes limpos. A estratégia admite o gás natural como combustível de transição, ao mesmo tempo que prioriza soluções renováveis onde sejam técnica e economicamente adequadas.</p><p>Analise um cenário em que o país precisa equilibrar exportação, uso doméstico do gás, eletrificação, investimento renovável e proteção ambiental. Proponha critérios de decisão, grupos afetados, indicadores e mecanismos de revisão. Uma conclusão robusta reconhece incertezas e evita apresentar uma fonte de energia como solução isolada.</p>",
          "estimated_minutes": 90, "is_required": true, "status": "ACTIVE",
          "sources": [{"title": "MIREME - Estratégia de Transição Energética", "url": "https://mireme.gov.mz/wp-content/uploads/2026/04/RESOLUCAO_61-2023_ESTRATEGIA_TRANSICAO_ENERGETICA1.pdf"}]
        }
      ],
      "questions": [
        {
          "question_id": "QUESTION-EPG-001-06", "question_order": 1,
          "bank_question_id": "QB-EPG-001-06", "bank_question_version_id": "QBVER-EPG-001-06-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M2-Q01", "title": "Conceito de GNL", "question_type": "SINGLE_CHOICE",
          "prompt": "O que caracteriza o gás natural liquefeito (GNL)?",
          "explanation": "O GNL é gás natural tratado e arrefecido até ao estado líquido, facilitando transporte e armazenamento.", "difficulty": "EASY", "tags": ["gnl", "infraestrutura"], "points": 10, "correct_answer": "B", "status": "ACTIVE",
          "options": [
            {"option_id": "OPTION-EPG-001-06-A", "bank_option_id": "QBOPT-EPG-001-06-A", "option_order": 1, "option_label": "A", "option_text": "Petróleo refinado misturado com gás", "is_correct": false},
            {"option_id": "OPTION-EPG-001-06-B", "bank_option_id": "QBOPT-EPG-001-06-B", "option_order": 2, "option_label": "B", "option_text": "Gás natural tratado e arrefecido até ao estado líquido", "is_correct": true},
            {"option_id": "OPTION-EPG-001-06-C", "bank_option_id": "QBOPT-EPG-001-06-C", "option_order": 3, "option_label": "C", "option_text": "Gás distribuído apenas por gasoduto", "is_correct": false},
            {"option_id": "OPTION-EPG-001-06-D", "bank_option_id": "QBOPT-EPG-001-06-D", "option_order": 4, "option_label": "D", "option_text": "Carvão convertido diretamente em eletricidade", "is_correct": false}
          ]
        },
        {
          "question_id": "QUESTION-EPG-001-07", "question_order": 2,
          "bank_question_id": "QB-EPG-001-07", "bank_question_version_id": "QBVER-EPG-001-07-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M2-Q02", "title": "Sequência de infraestrutura", "question_type": "SINGLE_CHOICE",
          "prompt": "Qual sequência representa melhor uma cadeia simplificada de GNL para exportação?",
          "explanation": "A cadeia parte da produção, passa pelo processamento e liquefação, segue por transporte marítimo e termina na regaseificação ou entrega.", "difficulty": "MEDIUM", "tags": ["gnl", "cadeia-de-valor"], "points": 10, "correct_answer": "A", "status": "ACTIVE",
          "options": [
            {"option_id": "OPTION-EPG-001-07-A", "bank_option_id": "QBOPT-EPG-001-07-A", "option_order": 1, "option_label": "A", "option_text": "Produção, processamento, liquefação, transporte e regaseificação", "is_correct": true},
            {"option_id": "OPTION-EPG-001-07-B", "bank_option_id": "QBOPT-EPG-001-07-B", "option_order": 2, "option_label": "B", "option_text": "Regaseificação, pesquisa, produção e perfuração", "is_correct": false},
            {"option_id": "OPTION-EPG-001-07-C", "bank_option_id": "QBOPT-EPG-001-07-C", "option_order": 3, "option_label": "C", "option_text": "Venda, descoberta, liquefação e abandono", "is_correct": false},
            {"option_id": "OPTION-EPG-001-07-D", "bank_option_id": "QBOPT-EPG-001-07-D", "option_order": 4, "option_label": "D", "option_text": "Refinação, mineração, transporte e combustão", "is_correct": false}
          ]
        },
        {
          "question_id": "QUESTION-EPG-001-08", "question_order": 3,
          "bank_question_id": "QB-EPG-001-08", "bank_question_version_id": "QBVER-EPG-001-08-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M2-Q03", "title": "Objetivo regulatório", "question_type": "SINGLE_CHOICE",
          "prompt": "Qual é um objetivo essencial da regulação das operações petrolíferas?",
          "explanation": "A regulação procura compatibilizar aproveitamento do recurso com legalidade, segurança, ambiente, informação e interesse público.", "difficulty": "MEDIUM", "tags": ["regulação", "interesse-público"], "points": 10, "correct_answer": "C", "status": "ACTIVE",
          "options": [
            {"option_id": "OPTION-EPG-001-08-A", "bank_option_id": "QBOPT-EPG-001-08-A", "option_order": 1, "option_label": "A", "option_text": "Eliminar toda a incerteza geológica", "is_correct": false},
            {"option_id": "OPTION-EPG-001-08-B", "bank_option_id": "QBOPT-EPG-001-08-B", "option_order": 2, "option_label": "B", "option_text": "Garantir lucro a qualquer projeto", "is_correct": false},
            {"option_id": "OPTION-EPG-001-08-C", "bank_option_id": "QBOPT-EPG-001-08-C", "option_order": 3, "option_label": "C", "option_text": "Proteger segurança, ambiente, legalidade e interesse público", "is_correct": true},
            {"option_id": "OPTION-EPG-001-08-D", "bank_option_id": "QBOPT-EPG-001-08-D", "option_order": 4, "option_label": "D", "option_text": "Substituir todas as decisões técnicas dos operadores", "is_correct": false}
          ]
        },
        {
          "question_id": "QUESTION-EPG-001-09", "question_order": 4,
          "bank_question_id": "QB-EPG-001-09", "bank_question_version_id": "QBVER-EPG-001-09-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M2-Q04", "title": "Pilares da transição", "question_type": "MULTIPLE_CHOICE",
          "prompt": "Quais opções correspondem a pilares da Estratégia de Transição Energética de Moçambique? Selecione todas as corretas.",
          "explanation": "A estratégia inclui expansão renovável, industrialização verde, acesso universal a energias modernas e transportes limpos.", "difficulty": "MEDIUM", "tags": ["transição-energética", "política-pública"], "points": 10, "correct_answer": "A,B,C,D", "status": "ACTIVE",
          "options": [
            {"option_id": "OPTION-EPG-001-09-A", "bank_option_id": "QBOPT-EPG-001-09-A", "option_order": 1, "option_label": "A", "option_text": "Expansão de energias renováveis", "is_correct": true},
            {"option_id": "OPTION-EPG-001-09-B", "bank_option_id": "QBOPT-EPG-001-09-B", "option_order": 2, "option_label": "B", "option_text": "Industrialização verde", "is_correct": true},
            {"option_id": "OPTION-EPG-001-09-C", "bank_option_id": "QBOPT-EPG-001-09-C", "option_order": 3, "option_label": "C", "option_text": "Acesso universal a energias modernas", "is_correct": true},
            {"option_id": "OPTION-EPG-001-09-D", "bank_option_id": "QBOPT-EPG-001-09-D", "option_order": 4, "option_label": "D", "option_text": "Transportes limpos", "is_correct": true},
            {"option_id": "OPTION-EPG-001-09-E", "bank_option_id": "QBOPT-EPG-001-09-E", "option_order": 5, "option_label": "E", "option_text": "Abandono imediato de todas as fontes não renováveis", "is_correct": false}
          ]
        },
        {
          "question_id": "QUESTION-EPG-001-10", "question_order": 5,
          "bank_question_id": "QB-EPG-001-10", "bank_question_version_id": "QBVER-EPG-001-10-V1", "bank_question_version_number": 1,
          "question_code": "EPG-M2-Q05", "title": "Decisão integrada de transição", "question_type": "LONG_TEXT",
          "prompt": "Proponha uma decisão para equilibrar exportação de gás, uso doméstico, acesso à energia, investimento renovável e proteção ambiental. Justifique critérios, indicadores e mecanismos de revisão.",
          "explanation": "A resposta deve integrar dimensões económicas, sociais, ambientais e institucionais, reconhecer incertezas e usar evidências do módulo.", "difficulty": "HARD", "tags": ["estudo-de-caso", "transição-energética", "decisão"], "points": 60,
          "correct_answer": "Rubrica: critérios coerentes e partes interessadas (25%); equilíbrio entre uso doméstico, exportação e renováveis (30%); riscos e salvaguardas ambientais e sociais (25%); indicadores, revisão e clareza (20%).", "status": "ACTIVE", "options": []
        }
      ]
    }
  ]
}
$course_snapshot$::jsonb;
  lesson jsonb;
  question jsonb;
  option_row jsonb;
  existing_draft_id text;
begin
  if not exists (
    select 1 from courseplatform.courses where course_id = 'COURSE-EPG-001'
  ) then
    raise notice 'COURSE-EPG-001 is absent; skipping its optional academic seed';
    return;
  end if;

  select course_version_id into existing_draft_id
  from courseplatform.course_versions
  where course_id = 'COURSE-EPG-001' and status = 'DRAFT';

  if existing_draft_id is not null and existing_draft_id <> 'CRSV-EPG-001-V2' then
    raise exception 'COURSE-EPG-001 already has a different draft: %', existing_draft_id;
  end if;

  if exists (
    select 1 from courseplatform.course_versions
    where course_version_id = 'CRSV-EPG-001-V2'
      and (course_id <> 'COURSE-EPG-001' or version_number <> 2 or status <> 'DRAFT')
  ) then
    raise exception 'CRSV-EPG-001-V2 exists with incompatible identity or status';
  end if;

  insert into courseplatform.course_versions (
    course_version_id, course_id, version_number, status, title, description,
    total_hours, passing_score, content_snapshot_json, created_at, updated_at
  ) values (
    'CRSV-EPG-001-V2', 'COURSE-EPG-001', 2, 'DRAFT',
    snapshot #>> '{course,title}', snapshot #>> '{course,description}',
    (snapshot #>> '{course,total_hours}')::numeric,
    (snapshot #>> '{course,passing_score}')::numeric,
    snapshot, now(), now()
  ) on conflict (course_version_id) do nothing;

  if not exists (
    select 1 from courseplatform.course_versions
    where course_version_id = 'CRSV-EPG-001-V2'
      and course_id = 'COURSE-EPG-001'
      and version_number = 2
      and status = 'DRAFT'
      and content_snapshot_json = snapshot
  ) then
    raise exception 'CRSV-EPG-001-V2 differs from the reviewed academic snapshot';
  end if;

  for lesson in select value from jsonb_array_elements(snapshot -> 'lessons') loop
    for question in select value from jsonb_array_elements(lesson -> 'questions') loop
      insert into courseplatform.question_bank_items (
        bank_question_id, course_id, question_code, title, status
      ) values (
        question ->> 'bank_question_id', 'COURSE-EPG-001',
        question ->> 'question_code', question ->> 'title', 'ACTIVE'
      ) on conflict (bank_question_id) do nothing;

      if not exists (
        select 1 from courseplatform.question_bank_items
        where bank_question_id = question ->> 'bank_question_id'
          and course_id = 'COURSE-EPG-001'
          and question_code = question ->> 'question_code'
      ) then
        raise exception 'Question bank identity collision: %', question ->> 'bank_question_id';
      end if;

      insert into courseplatform.question_bank_versions (
        bank_question_version_id, bank_question_id, version_number, status,
        question_type, prompt, explanation, difficulty, tags, points, correct_answer
      ) values (
        question ->> 'bank_question_version_id', question ->> 'bank_question_id', 1, 'DRAFT',
        question ->> 'question_type', question ->> 'prompt', question ->> 'explanation',
        question ->> 'difficulty',
        array(select jsonb_array_elements_text(question -> 'tags')),
        (question ->> 'points')::numeric, question ->> 'correct_answer'
      ) on conflict (bank_question_version_id) do nothing;

      if not exists (
        select 1 from courseplatform.question_bank_versions
        where bank_question_version_id = question ->> 'bank_question_version_id'
          and bank_question_id = question ->> 'bank_question_id'
          and version_number = 1
          and question_type = question ->> 'question_type'
          and prompt = question ->> 'prompt'
          and points = (question ->> 'points')::numeric
      ) then
        raise exception 'Question version collision: %', question ->> 'bank_question_version_id';
      end if;

      for option_row in select value from jsonb_array_elements(question -> 'options') loop
        insert into courseplatform.question_bank_options (
          bank_option_id, bank_question_version_id, option_order,
          option_label, option_text, is_correct
        )
        select
          option_row ->> 'bank_option_id', question ->> 'bank_question_version_id',
          (option_row ->> 'option_order')::integer, option_row ->> 'option_label',
          option_row ->> 'option_text', (option_row ->> 'is_correct')::boolean
        where exists (
          select 1 from courseplatform.question_bank_versions
          where bank_question_version_id = question ->> 'bank_question_version_id'
            and status = 'DRAFT'
        )
        on conflict (bank_option_id) do nothing;
      end loop;

      update courseplatform.question_bank_versions
      set status = 'PUBLISHED', published_at = now(), updated_at = now()
      where bank_question_version_id = question ->> 'bank_question_version_id'
        and status = 'DRAFT';
    end loop;
  end loop;
end
$migration$;
