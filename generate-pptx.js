/**
 * EasyGestion — Générateur PPTX (pptxgenjs)
 * Lit le JSON canonique et produit une présentation 24 slides (13.33 × 7.5 in).
 */

const pptxgen = require('pptxgenjs');
const fs = require('fs');
const path = require('path');

// ─── Constantes ───────────────────────────────────────────────────────────────

const SLIDE_W = 13.33;
const SLIDE_H = 7.5;
const COL_INK = '111111';
const COL_GREY = '555555';
const COL_ACCENT = 'E0A040';
const COL_WHITE = 'FFFFFF';

const FONT_REG = 'Nunito Sans';
const FONT_BOLD = 'Nunito Sans';

const MX = 0.56;
const MW = 8.88;
const Y_AT = 1.45;
const COL2_L_W = 4.24;
const COL2_R_X = 5.20;
const LINE_SPACING = 16;
const PARA_SPACE_AFTER = 8;

const PPTX_OWN_SLIDE_INDICES = new Set([6, 7, 9, 11, 12, 13, 16]);

// ─── Helpers ──────────────────────────────────────────────────────────────────

function addBackground(slide, slideNum, assetsDir) {
  const num = String(slideNum).padStart(2, '0');
  const imgPath = path.join(assetsDir, `slide_${num}.png`);
  if (fs.existsSync(imgPath)) {
    slide.background = { path: imgPath };
  }
}

function addText(slide, text, opts = {}) {
  if (!text) return;
  const defaults = {
    fontFace: FONT_REG,
    fontSize: 14,
    color: COL_WHITE,
    valign: 'top',
    align: 'left',
    wrap: true,
    autoFit: false,
    shrinkText: false,
  };
  slide.addText(text, { ...defaults, ...opts });
}

function stripMd(text) {
  if (!text) return '';
  return String(text)
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/`(.+?)`/g, '$1')
    .replace(/<[^>]+>/g, '');
}

function fmtEur(amount) {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

// ─── Slides ───────────────────────────────────────────────────────────────────

function buildSlide01_Couverture(slide, data, assetsDir) {
  addBackground(slide, 1, assetsDir);
  const projet = data.projet || {};
  const meta = data.meta || {};
  addText(slide, stripMd(projet.nom || ''), {
    x: 0.5, y: 5.5, w: SLIDE_W - 1, h: 1.0,
    fontSize: 32, bold: true, align: 'center',
  });
  addText(slide, meta.date_creation || '', {
    x: 0.5, y: 6.7, w: SLIDE_W - 1, h: 0.5,
    fontSize: 12, color: COL_GREY, align: 'center',
  });
}

function buildSlide02_Sommaire(slide, data, assetsDir) {
  addBackground(slide, 2, assetsDir);
}

function buildSlide03_Presentation1(slide, data, assetsDir) {
  addBackground(slide, 3, assetsDir);
}

function buildSlide04_Presentation2(slide, data, assetsDir) {
  addBackground(slide, 4, assetsDir);
}

function buildSlide05_Approche(slide, data, assetsDir) {
  addBackground(slide, 5, assetsDir);
}

function buildSlide06_Comprehension(slide, data, assetsDir) {
  addBackground(slide, 6, assetsDir);
}

function buildSlide07_Contexte(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 7, assetsDir);
  const ctx = data.sections?.contexte || {};
  addText(slide, stripMd(ctx.titre || ''), {
    x: MX, y: Y_AT, w: MW, h: 0.6,
    fontSize: 18, bold: true, lineSpacing: 22, color: COL_WHITE, wrap: true, autoFit: false,
  });
  addText(slide, stripMd(ctx.texte || ''), {
    x: MX, y: 2.05, w: MW, h: 1.8,
    fontSize: 14, lineSpacing: 20, color: COL_WHITE, wrap: true, autoFit: false,
  });
}

function buildSlide08_Fonctionnalites(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 8, assetsDir);
  const foncs = data.sections?.fonctionnalites || [];
  const colsData = [foncs.slice(0, 2), foncs.slice(2)];
  const xCols = [MX, COL2_R_X];
  colsData.forEach((groupe, ci) => {
    const paragraphs = [];
    groupe.forEach((cat, gi) => {
      if (!cat) return;
      if (gi > 0) paragraphs.push({ text: '', options: { fontSize: 8 } });
      paragraphs.push({
        text: `${stripMd(cat.categorie || '')} :`,
        options: {
          bold: true, fontSize: 20, color: COL_WHITE, lineSpacing: 24,
          paraSpaceBefore: 14, paraSpaceAfter: 6,
        },
      });
      (cat.items || []).slice(0, 4).forEach((it) => {
        paragraphs.push({
          text: stripMd(it.titre || ''),
          options: {
            bullet: true, fontSize: 16, color: COL_WHITE,
            lineSpacing: 22, paraSpaceAfter: 12,
          },
        });
      });
    });
    if (paragraphs.length) {
      slide.addText(paragraphs, {
        x: xCols[ci], y: 1.55, w: COL2_L_W, h: 3.8,
        autoFit: false, wrap: true,
      });
    }
  });
}

function buildSlide09_TitreAcquisition(slide, data, assetsDir) {
  addBackground(slide, 9, assetsDir);
}

function buildSlide10_Acquisition(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 10, assetsDir);
  const acq = data.sections?.acquisition || [];
  const bullets = acq.slice(0, 5).map((a) => ({
    text: stripMd(a.titre || '') + (a.detail ? ` : ${stripMd(a.detail)}` : ''),
    options: {
      bullet: true, fontSize: 16, color: COL_WHITE,
      lineSpacing: 22, paraSpaceAfter: 12,
    },
  }));
  if (bullets.length) {
    slide.addText(bullets, {
      x: MX, y: 1.8, w: COL2_L_W, h: 3.5,
      autoFit: false, wrap: true,
    });
  }
}

function buildSlide11_TitrePlanAction(slide, data, assetsDir) {
  addBackground(slide, 11, assetsDir);
}

function buildSlide12_PlanAction(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 12, assetsDir);
  const phases = data.sections?.plan_action || [];

  const col1Phases = [phases[0], phases[2]].filter(Boolean);
  const col2Phases = [phases[1], phases[3]].filter(Boolean);

  [[col1Phases, MX], [col2Phases, COL2_R_X]].forEach(([colPhases, x]) => {
    const paragraphs = [];
    colPhases.forEach((p, pi) => {
      if (pi > 0) paragraphs.push({ text: '', options: { fontSize: 8 } });
      paragraphs.push({
        text: stripMd(p.phase || ''),
        options: {
          bold: true, fontSize: 18, color: COL_WHITE,
          lineSpacing: 22, paraSpaceAfter: 8,
        },
      });
      (p.taches || []).slice(0, 5).forEach((t) => {
        paragraphs.push({
          text: stripMd(t),
          options: {
            bullet: true, fontSize: 16, color: COL_WHITE,
            lineSpacing: 22, paraSpaceAfter: 8,
          },
        });
      });
    });
    if (paragraphs.length) {
      slide.addText(paragraphs, {
        x, y: 1.6, w: COL2_L_W, h: 3.7,
        autoFit: false, wrap: true,
      });
    }
  });
}

function buildSlide13_Equipe(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 13, assetsDir);
  const equipe = data.sections?.equipe || [];
  addText(slide, 'Une équipe expérimentée mobilisée tout au long du projet.', {
    x: MX, y: 1.5, w: 8.0, h: 0.5,
    fontSize: 16, lineSpacing: 22, color: COL_WHITE, wrap: true, autoFit: false,
  });
  const mid = Math.ceil(equipe.length / 2);
  const cols = [equipe.slice(0, mid), equipe.slice(mid)];
  const xCols = [MX, COL2_R_X];
  cols.forEach((col, ci) => {
    const paragraphs = [];
    col.forEach((e) => {
      paragraphs.push({
        text: `${stripMd(e.role || '')} :`,
        options: {
          bold: true, fontSize: 18, color: COL_WHITE,
          lineSpacing: 22, paraSpaceAfter: 4,
        },
      });
      paragraphs.push({
        text: stripMd(e.expertise || ''),
        options: {
          fontSize: 16, color: COL_WHITE,
          lineSpacing: 22, paraSpaceAfter: 10,
        },
      });
    });
    if (paragraphs.length) {
      slide.addText(paragraphs, {
        x: xCols[ci], y: 2.55, w: 3.5, h: 3.0,
        autoFit: false, wrap: true,
      });
    }
  });
}

function buildSlide14_Technologies(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 14, assetsDir);
  const techs = data.sections?.technologies || [];
  const mid = Math.ceil(techs.length / 2);
  const cols = [techs.slice(0, mid), techs.slice(mid)];
  const xCols = [MX, COL2_R_X];
  cols.forEach((col, ci) => {
    const paragraphs = [];
    col.forEach((t, ti) => {
      paragraphs.push({
        text: `${stripMd(t.categorie || '')} :`,
        options: {
          bold: true, fontSize: 18, color: COL_WHITE, lineSpacing: 22,
          paraSpaceBefore: ti > 0 ? 12 : 0, paraSpaceAfter: 4,
        },
      });
      paragraphs.push({
        text: stripMd(t.detail || ''),
        options: {
          fontSize: 16, color: COL_WHITE,
          lineSpacing: 22, paraSpaceAfter: 8,
        },
      });
    });
    if (paragraphs.length) {
      slide.addText(paragraphs, {
        x: xCols[ci], y: 1.6, w: COL2_L_W, h: 3.8,
        autoFit: false, wrap: true,
      });
    }
  });
}

function buildSlide15_TitreBudget(slide, data, assetsDir) {
  addBackground(slide, 15, assetsDir);
}

function buildSlide16_BudgetHeader(slide, data, assetsDir) {
  addBackground(slide, 16, assetsDir);
  const projet = data.projet || {};
  addText(slide, `${fmtEur(projet.budget || 0)} HT`, {
    x: 0.5, y: 5.5, w: SLIDE_W - 1, h: 1.0,
    fontSize: 36, bold: true, color: COL_ACCENT, align: 'center',
  });
  if (projet.duree_mois) {
    addText(slide, `${projet.duree_mois} mois`, {
      x: 0.5, y: 6.3, w: SLIDE_W - 1, h: 0.5,
      fontSize: 16, color: COL_GREY, align: 'center',
    });
  }
}

function buildSlide17_Repartition(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 17, assetsDir);
  const modules = data.budget_detail?.modules || [];
  const tjm = data.projet?.tjm || 100;

  const X_POLE = 0.56;
  const W_POLE = 5.0;
  const X_HRS = 5.6;
  const W_HRS = 1.8;
  const X_COUT = 7.5;
  const W_COUT = 1.9;
  const Y_HDR = 1.45;
  const Y_START = 2.2;
  const nb = Math.min(modules.length, 7);
  const ROW_H = Math.min(0.62, (5.0 - Y_START) / (nb + 1));

  addText(slide, 'Pôles de développement', {
    x: X_POLE, y: Y_HDR, w: W_POLE, h: 0.4,
    fontSize: 13, bold: true, color: COL_WHITE, align: 'left', autoFit: false,
  });
  addText(slide, 'Volume horaire', {
    x: X_HRS, y: Y_HDR, w: W_HRS, h: 0.4,
    fontSize: 13, bold: true, color: COL_WHITE, align: 'center', autoFit: false,
  });
  addText(slide, `Coût total (TJM : ${tjm}€/h)`, {
    x: X_COUT, y: Y_HDR, w: W_COUT, h: 0.4,
    fontSize: 13, bold: true, color: COL_WHITE, align: 'right', autoFit: false,
  });

  let totalH = 0;
  let totalEur = 0;
  modules.slice(0, 7).forEach((m, i) => {
    const h = (m.items || []).reduce((s, it) => s + (it.heures || 0), 0);
    const eur = h * tjm;
    totalH += h;
    totalEur += eur;
    const y = Y_START + i * ROW_H;
    addText(slide, stripMd(m.titre || ''), {
      x: X_POLE, y, w: W_POLE, h: ROW_H,
      fontSize: 13, color: COL_WHITE, wrap: true, valign: 'middle', autoFit: false,
    });
    addText(slide, `${h} h`, {
      x: X_HRS, y, w: W_HRS, h: ROW_H,
      fontSize: 13, color: COL_WHITE, align: 'center', valign: 'middle', autoFit: false,
    });
    addText(slide, `${eur.toLocaleString('fr-FR')} €`, {
      x: X_COUT, y, w: W_COUT, h: ROW_H,
      fontSize: 13, color: COL_ACCENT, align: 'right', valign: 'middle', autoFit: false,
    });
  });

  const Y_TOTAL = Y_START + nb * ROW_H + 0.15;
  addText(slide, 'TOTAL', {
    x: X_POLE, y: Y_TOTAL, w: W_POLE, h: 0.5,
    fontSize: 14, bold: true, color: COL_WHITE, autoFit: false,
  });
  addText(slide, `${totalH} h`, {
    x: X_HRS, y: Y_TOTAL, w: W_HRS, h: 0.5,
    fontSize: 14, bold: true, color: COL_WHITE, align: 'center', autoFit: false,
  });
  addText(slide, `${totalEur.toLocaleString('fr-FR')} €`, {
    x: X_COUT, y: Y_TOTAL, w: W_COUT, h: 0.5,
    fontSize: 14, bold: true, color: COL_WHITE, align: 'right', autoFit: false,
  });
}

function buildSlide18_Nouveau1(pptx, _d, a) {
  const s = pptx.addSlide();
  addBackground(s, 18, a);
}

function buildSlide19_Nouveau2(pptx, _d, a) {
  const s = pptx.addSlide();
  addBackground(s, 19, a);
}

function buildSlide20_PourquoiNousTitre(pptx, _d, a) {
  const s = pptx.addSlide();
  addBackground(s, 20, a);
}

function buildSlide21_PourquoiNous(pptx, _d, a) {
  const s = pptx.addSlide();
  addBackground(s, 21, a);
}

function buildSlide22_Annexes1(pptx, _d, a) {
  const s = pptx.addSlide();
  addBackground(s, 22, a);
}

function buildSlide23_Annexes2(pptx, _d, a) {
  const s = pptx.addSlide();
  addBackground(s, 23, a);
}

function buildSlide24_Merci(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 24, assetsDir);
  const em = data.emetteur || {};
  addText(slide, em.contact_nom || '', {
    x: 7, y: 5.6, w: 5.5, h: 0.4, fontSize: 14, bold: true,
  });
  addText(slide, em.contact_email || '', {
    x: 7, y: 6.0, w: 5.5, h: 0.4, fontSize: 12, color: COL_GREY,
  });
  addText(slide, em.contact_tel || '', {
    x: 7, y: 6.4, w: 5.5, h: 0.4, fontSize: 12, color: COL_GREY,
  });
}

// ─── Génération ───────────────────────────────────────────────────────────────

const SLIDE_BUILDERS = [
  buildSlide01_Couverture,
  buildSlide02_Sommaire,
  buildSlide03_Presentation1,
  buildSlide04_Presentation2,
  buildSlide05_Approche,
  buildSlide06_Comprehension,
  buildSlide07_Contexte,
  buildSlide08_Fonctionnalites,
  buildSlide09_TitreAcquisition,
  buildSlide10_Acquisition,
  buildSlide11_TitrePlanAction,
  buildSlide12_PlanAction,
  buildSlide13_Equipe,
  buildSlide14_Technologies,
  buildSlide15_TitreBudget,
  buildSlide16_BudgetHeader,
  buildSlide17_Repartition,
  buildSlide19_Nouveau2,
  buildSlide18_Nouveau1,
  buildSlide20_PourquoiNousTitre,
  buildSlide21_PourquoiNous,
  buildSlide22_Annexes1,
  buildSlide23_Annexes2,
  buildSlide24_Merci,
];

async function generatePptx(data, outputPath, assetsDir) {
  const pptx = new pptxgen();
  pptx.defineLayout({ name: 'WIDE', width: SLIDE_W, height: SLIDE_H });
  pptx.layout = 'WIDE';

  SLIDE_BUILDERS.forEach((builder, index) => {
    if (index >= 17 || PPTX_OWN_SLIDE_INDICES.has(index)) {
      builder(pptx, data, assetsDir);
    } else {
      const slide = pptx.addSlide();
      builder(slide, data, assetsDir);
    }
  });

  await pptx.writeFile({ fileName: outputPath });
}

// ─── CLI ──────────────────────────────────────────────────────────────────────

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    input: null,
    output: null,
    assetsDir: path.join(__dirname, 'assets'),
  };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--input') opts.input = args[++i];
    else if (args[i] === '--output') opts.output = args[++i];
    else if (args[i] === '--assets-dir') opts.assetsDir = args[++i];
  }
  return opts;
}

async function main() {
  const opts = parseArgs();
  if (!opts.input || !opts.output) {
    console.error(
      'Usage: node generate-pptx.js --input <data.json> --output <out.pptx> [--assets-dir <dir>]',
    );
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(opts.input, 'utf8'));
  await generatePptx(data, opts.output, opts.assetsDir);
  console.log(`PPTX généré : ${opts.output}`);
}

if (require.main === module) {
  main().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}

module.exports = { generatePptx };
