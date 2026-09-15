import { escapeHtml } from './utils.js';

let resources;
function loadResources() {
  if (!resources) {
    resources = Promise.all([
      fetch(new URL('./assets/certificate-layout.json', import.meta.url)).then((response) => {
        if (!response.ok) throw new Error('Não foi possível carregar o modelo do certificado.');
        return response.json();
      }).catch(() => { throw new Error('Não foi possível carregar o modelo do certificado.'); }),
      import('./vendor/qrcode-generator.mjs').catch(() => { throw new Error('Não foi possível carregar o gerador do código QR.'); }),
      ...['Vera.ttf', 'VeraBd.ttf'].map(async (file, index) => {
        try {
          const face = new FontFace('CertificateSans', `url(${new URL(`./assets/fonts/${file}`, import.meta.url)})`, { weight: index ? '700' : '400' });
          document.fonts.add(await face.load());
        } catch {
          return null;
        }
      })
    ]).catch((error) => { resources = null; throw error; });
  }
  return resources;
}

const clean = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
const months = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];

function dateLabel(value) {
  const match = String(value || new Date().toISOString()).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${Number(match[3])} de ${months[Number(match[2]) - 1]} de ${match[1]}` : clean(value);
}

export function certificateWorkloadLabel(certificate) {
  const hours = Number(certificate?.templateSnapshot?.courseHours);
  if (!Number.isFinite(hours) || hours <= 0) return 'Não definida';
  return `${new Intl.NumberFormat('pt-PT', { maximumFractionDigits: 2 }).format(hours)} horas`;
}

function fieldsFor(certificate) {
  const profile = certificate.templateSnapshot?.profile || {};
  const issuer = profile.issuerName || certificate.issuerName || 'LMTWEBNAIRS Summer School';
  const code = certificate.verificationCode || certificate.certificateNumber || '';
  const summary = profile.certifiedContents || certificate.contentSummary || '';
  const score = certificate.finalScore == null || certificate.finalScore === '' ? '--' : `${Math.round(Number(certificate.finalScore))}%`;
  return {
    issuer, title: (profile.certificateTitle || 'Certificado de Qualificação').toUpperCase(),
    qualification: profile.qualificationType || 'sobre o aumento da qualificação profissional',
    number: certificate.certificateNumber || certificate.certificateId || '',
    documentLabel: 'Documento de qualificação', registerLabel: 'Número de registo', code,
    location: profile.issueLocation || 'Cidade de Maputo, Moçambique', date: dateLabel(certificate.issueDate),
    lead: 'O presente documento certifica que', student: certificate.studentName || 'Nome do participante',
    statement: `concluiu com sucesso o programa de qualificação profissional na ${issuer}.`,
    courseLabel: 'CURSO / PROGRAMA', course: certificate.courseTitle || 'Curso',
    description: 'demonstrando aproveitamento satisfatório em atividades académicas, estudos de caso, discussões técnicas e avaliação final.',
    topicsLabel: clean(summary) ? 'O programa abordou:' : '',
    workload: `Carga horária: ${certificateWorkloadLabel(certificate)}`,
    score: `Resultado final: ${score}`,
    director: profile.directorName || 'Diretor Académico', directorTitle: profile.directorTitle || 'Direção académica',
    coordinator: profile.coordinatorName || 'Coordenador do Programa', coordinatorTitle: profile.coordinatorTitle || 'Coordenação do programa',
    verifyLabel: 'Verifique a autenticidade do certificado', verifyCode: code, credit: profile.productCredit || ''
  };
}

function wrapText(text, width, context) {
  const lines = [];
  let current = '';
  for (const word of clean(text).split(' ')) {
    const candidate = current ? `${current} ${word}` : word;
    if (context.measureText(candidate).width <= width) { current = candidate; continue; }
    if (current) lines.push(current);
    current = '';
    for (const character of word) {
      if (context.measureText(current + character).width > width && current) {
        lines.push(current);
        current = '';
      }
      current += character;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function fitText(value, box, key, context) {
  let size = box.size;
  while (true) {
    context.font = `${box.bold ? 700 : 400} ${size}px CertificateSans`;
    const lines = wrapText(value, box.w - 2, context);
    if (lines.length * size * 1.22 <= box.h + 0.01) return { size, lines };
    if (size <= box.min) throw new Error(`O texto do campo "${key}" é demasiado longo. Resuma-o na configuração do certificado.`);
    size = Math.max(box.min, size - 0.25);
  }
}

function safeImageUrl(value) {
  const url = String(value || '');
  return /^(https?:\/\/|data:image\/(png|jpeg|webp);base64,)/i.test(url) ? escapeHtml(url) : '';
}

function verificationUrl(certificate) {
  const config = window.COURSE_PLATFORM_CONFIG || {};
  const url = new URL('/verify.html', config.apiUrl || window.location.origin);
  url.searchParams.set('code', certificate.verificationCode || certificate.certificateNumber || '');
  return url.href;
}

export function renderProfessionalSvg(certificate, layout, qrcode) {
  const fields = fieldsFor(certificate);
  const profile = certificate.templateSnapshot?.profile || {};
  const assets = profile.assets || {};
  const context = document.createElement('canvas').getContext('2d');
  context.fontKerning = 'none';
  const blocks = Object.entries(fields).filter(([, value]) => value).map(([key, value]) => [key, value, layout.texts[key]]);
  const topics = String(profile.certifiedContents || certificate.contentSummary || '').split(/\r?\n/).map((line) => line.replace(/^[\s•-]+|[\s•-]+$/g, '')).filter(Boolean);
  const area = layout.topics;
  if (topics.length > area.limit) throw new Error('Use até oito conteúdos resumidos no certificado profissional.');
  const rows = Math.max(1, Math.ceil(topics.length / 2));
  const width = (area.w - area.gap) / 2;
  topics.forEach((topic, index) => blocks.push([`topic${index}`, topic, {
    x: area.x + Math.floor(index / rows) * (width + area.gap) + 9,
    y: area.y + (index % rows) * area.h / rows, w: width - 9, h: area.h / rows - 1,
    size: area.size, min: area.min, align: 'left'
  }]));
  const palette = layout.colors;
  const text = blocks.map(([key, value, box]) => {
    const { size, lines } = fitText(value, box, key, context);
    const leading = size * 1.22;
    const top = box.y + (box.h - lines.length * leading) / 2;
    const x = box.align === 'left' ? box.x + 1 : box.x + box.w / 2;
    const bullet = /^topic\d+$/.test(key) ? `<circle cx="${box.x - 6}" cy="${top + size * 0.62}" r="1.1"/>` : '';
    return `<g data-field="${key}" fill="${palette[box.color || 'ink']}">${bullet}<text font-size="${size}" font-weight="${box.bold ? 700 : 400}" text-anchor="${box.align === 'left' ? 'start' : 'middle'}">${lines.map((line, index) => `<tspan x="${x}" y="${top + index * leading + size * 0.93}">${escapeHtml(line)}</tspan>`).join('')}</text></g>`;
  }).join('');
  const images = Object.entries(layout.images).map(([key, box]) => {
    const url = safeImageUrl(assets[key]);
    return url ? `<image data-asset="${key}" href="${url}" x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" preserveAspectRatio="xMidYMid meet"/>` : '';
  }).join('');
  const frames = `<rect width="${layout.width}" height="${layout.height}" fill="#fff"/><rect x="10" y="10" width="${layout.width - 20}" height="${layout.height - 20}" fill="none" stroke="${palette.frame}" stroke-width="7"/><rect x="20" y="20" width="${layout.width - 40}" height="${layout.height - 40}" fill="none" stroke="${palette.ink}" stroke-width="2"/>`;
  const corners = [0, 18].map((inset) => {
    const margin = 38 + inset;
    return [[margin, margin, 1, 1], [layout.width - margin, margin, -1, 1], [margin, layout.height - margin, 1, -1], [layout.width - margin, layout.height - margin, -1, -1]].map(([x, y, sx, sy]) => `<path d="M${x + sx * 42} ${y}H${x}V${y + sy * 42}M${x + sx * 34} ${y + sy * 8}H${x + sx * 8}V${y + sy * 34}" fill="none" stroke="${inset ? palette.frame : palette.ink}" stroke-width="1.3"/>`).join('');
  }).join('');
  const signatureLines = layout.signatureLines.map(([x1, y1, x2, y2]) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${palette.ink}" stroke-width="0.6"/>`).join('');
  const qr = qrcode(0, 'M');
  const verifyUrl = verificationUrl(certificate);
  qr.addData(verifyUrl);
  qr.make();
  const count = qr.getModuleCount();
  const cells = [];
  for (let row = 0; row < count; row++) for (let col = 0; col < count; col++) {
    if (qr.isDark(row, col)) cells.push(`M${col + 4},${row + 4}h1v1h-1z`);
  }
  const qb = layout.qr;
  const qrSvg = `<a href="${escapeHtml(verifyUrl)}" target="_blank" rel="noopener"><svg data-qr="true" x="${qb.x}" y="${qb.y}" width="${qb.size}" height="${qb.size}" viewBox="0 0 ${count + 8} ${count + 8}"><rect width="100%" height="100%" fill="#fff"/><path d="${cells.join('')}" fill="#000"/></svg></a>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${layout.width} ${layout.height}" role="img" aria-label="Certificado de qualificação de ${escapeHtml(fields.student)}" style="font-family:CertificateSans,sans-serif;letter-spacing:0;font-kerning:none;font-variant-ligatures:none;text-rendering:geometricPrecision">${frames}${corners}<line x1="${layout.width / 2}" y1="60" x2="${layout.width / 2}" y2="${layout.height - 78}" stroke="${palette.line}" stroke-width="0.6"/>${images}${signatureLines}${text}${qrSvg}</svg>`;
}

export function professionalCertificateTemplate(certificate, options = {}) {
  return `<professional-certificate ${options.compact ? 'compact' : ''} data-certificate="${escapeHtml(JSON.stringify(certificate))}"></professional-certificate>`;
}

class ProfessionalCertificate extends HTMLElement {
  static observedAttributes = ['data-certificate'];
  constructor() { super(); this.attachShadow({ mode: 'open' }); this.renderVersion = 0; }
  connectedCallback() { this.render(); }
  disconnectedCallback() { this.resizeObserver?.disconnect(); }
  attributeChangedCallback() { if (this.isConnected) this.render(); }
  async render() {
    const version = ++this.renderVersion;
    this.resizeObserver?.disconnect();
    delete this.dataset.ready;
    this.shadowRoot.innerHTML = '<p role="status">A preparar a pré-visualização…</p>';
    try {
      const [layout, { default: qrcode }] = await loadResources();
      if (version !== this.renderVersion || !this.isConnected) return;
      const certificate = JSON.parse(this.dataset.certificate);
      const compact = this.hasAttribute('compact');
      this.shadowRoot.innerHTML = `<style>
        :host{display:block;min-width:0;width:100%;color:#143b50;font:13px Arial,sans-serif;letter-spacing:0}
        *{box-sizing:border-box}.toolbar{display:flex;justify-content:flex-end;gap:8px;padding:0 0 10px}
        button{height:32px;min-width:38px;padding:0 10px;border:1px solid #bccbd1;border-radius:4px;background:#fff;color:#143b50;font:inherit;cursor:pointer}
        button:hover{background:#edf3f5}button:focus-visible{outline:2px solid #143b50;outline-offset:2px}
        .viewport{max-width:100%;max-height:${compact ? 'none' : 'calc(100dvh - 200px)'};overflow:auto;background:#edf0f2;overscroll-behavior:contain}
        .paper{width:100%;margin:auto}.paper>svg{display:block;width:100%;height:auto}
        .error{padding:16px;border:1px solid #c55454;background:#fff7f7;color:#8d2525;line-height:1.5}
        @media print{.toolbar{display:none}.viewport{max-height:none;overflow:visible}.paper{width:297mm!important;height:210mm}}
      </style>${compact ? '' : '<div class="toolbar" aria-label="Ampliação do certificado"><button type="button" data-fit title="Ajustar à janela">Ajustar</button><button type="button" data-zoom="-1" title="Diminuir" aria-label="Diminuir">−</button><button type="button" data-actual title="Tamanho A4 a 100%">100%</button><button type="button" data-zoom="1" title="Aumentar" aria-label="Aumentar">+</button></div>'}<div class="viewport"><div class="paper">${renderProfessionalSvg(certificate, layout, qrcode)}</div></div>`;
      const paper = this.shadowRoot.querySelector('.paper');
      const viewport = this.shadowRoot.querySelector('.viewport');
      let scale = null;
      const applyScale = () => {
        const heightLimit = parseFloat(getComputedStyle(viewport).maxHeight);
        const fittedWidth = Math.min(viewport.clientWidth, Number.isFinite(heightLimit) ? heightLimit * layout.width / layout.height : Infinity);
        paper.style.width = `${scale == null ? fittedWidth : layout.width * 96 / 72 * scale}px`;
      };
      this.resizeObserver = new ResizeObserver(() => { if (scale == null) applyScale(); });
      this.resizeObserver.observe(viewport);
      applyScale();
      this.shadowRoot.querySelector('[data-fit]')?.addEventListener('click', () => { scale = null; applyScale(); });
      this.shadowRoot.querySelector('[data-actual]')?.addEventListener('click', () => { scale = 1; applyScale(); });
      this.shadowRoot.querySelectorAll('[data-zoom]').forEach((button) => button.addEventListener('click', () => {
        scale = Math.max(0.25, Math.min(2, (scale ?? viewport.clientWidth / (layout.width * 96 / 72)) + Number(button.dataset.zoom) * 0.25));
        applyScale();
      }));
      this.dataset.ready = 'true';
      this.dispatchEvent(new Event('certificate-ready', { bubbles: true }));
    } catch (error) {
      if (version !== this.renderVersion) return;
      this.shadowRoot.innerHTML = `<p role="alert" style="font:14px/1.5 Arial,sans-serif;color:#8d2525;padding:16px">${escapeHtml(error.message)}</p>`;
      this.dataset.ready = 'error';
    }
  }
}

if (!customElements.get('professional-certificate')) customElements.define('professional-certificate', ProfessionalCertificate);
