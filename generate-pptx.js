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

const MX = 0.56;
const MW = 8.88;
const Y_AT = 1.45;
const COL2_L_W = 4.24;
const COL2_R_X = 5.20;
const COL3_W = 2.69;
const COL3_X = [0.56, 3.65, 6.74];
const GAP = 0.4;

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
    fontFace: 'DejaVu Sans',
    fontSize: 14,
    color: COL_INK,
    x: 0.5,
    y: 0.5,
    w: SLIDE_W - 1,
    h: 1,
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
    x: MX, y: Y_AT, w: MW, h: 0.5,
    fontSize: 17, bold: true, color: COL_WHITE, wrap: true, align: 'left',
  });
  const texte = stripMd(ctx.texte || '');
  addText(slide, texte, {
    x: MX, y: 2.05, w: MW, h: 1.7,
    fontSize: 11, color: COL_WHITE, wrap: true, align: 'left',
  });
}

function buildSlide08_Fonctionnalites(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 8, assetsDir);
  const foncs = data.sections?.fonctionnalites || [];
  const cols = [[foncs[0], foncs[1]], [foncs[2]]];
  const xCols = [MX, COL2_R_X];
  cols.forEach((groupe, ci) => {
    let y = Y_AT + 0.1;
    groupe.forEach((cat) => {
      if (!cat) return;
      addText(slide, `${stripMd(cat.categorie || '')} :`, {
        x: xCols[ci], y, w: COL2_L_W, h: 0.35,
        fontSize: 12, bold: true, color: COL_WHITE, wrap: true,
      });
      y += 0.38;
      (cat.items || []).slice(0, 4).forEach((it) => {
        addText(slide, `• ${stripMd(it.titre || '')}`, {
          x: xCols[ci], y, w: COL2_L_W, h: 0.3,
          fontSize: 11, color: COL_WHITE, wrap: true,
        });
        y += 0.3;
      });
      y += 0.2;
    });
  });
}

function buildSlide09_TitreAcquisition(slide, data, assetsDir) {
  addBackground(slide, 9, assetsDir);
}

function buildSlide10_Acquisition(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 10, assetsDir);
  const acq = data.sections?.acquisition || [];
  let y = 1.8;
  acq.slice(0, 4).forEach((a) => {
    addText(slide, `• ${stripMd(a.titre || '')} : ${stripMd(a.detail || '')}`, {
      x: MX, y, w: COL2_L_W, h: 0.5,
      fontSize: 11, color: COL_WHITE, wrap: true,
    });
    y += 0.55;
  });
}

function buildSlide11_TitrePlanAction(slide, data, assetsDir) {
  addBackground(slide, 11, assetsDir);
}

function buildSlide12_PlanAction(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 12, assetsDir);
  const phases = data.sections?.plan_action || [];
  const positions = [
    { x: MX, y: 1.9 },
    { x: COL2_R_X, y: 1.9 },
    { x: MX, y: 3.7 },
    { x: COL2_R_X, y: 3.7 },
  ];
  phases.slice(0, 4).forEach((p, i) => {
    const { x, y } = positions[i];
    addText(slide, stripMd(p.phase || ''), {
      x, y, w: COL2_L_W, h: 0.45,
      fontSize: 13, bold: true, color: COL_WHITE, wrap: true,
    });
    let ty = y + 0.5;
    (p.taches || []).slice(0, 4).forEach((t) => {
      addText(slide, `• ${stripMd(t)}`, {
        x, y: ty, w: COL2_L_W, h: 0.3,
        fontSize: 11, color: COL_WHITE, wrap: true,
      });
      ty += 0.3;
    });
  });
}

function buildSlide13_Equipe(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 13, assetsDir);
  const equipe = data.sections?.equipe || [];
  addText(slide, 'Une équipe expérimentée mobilisée tout au long du projet.', {
    x: MX, y: 1.5, w: 8.0, h: 0.4,
    fontSize: 11, color: COL_WHITE, wrap: true,
  });
  const midPoint = Math.ceil(equipe.length / 2);
  const cols = [equipe.slice(0, midPoint), equipe.slice(midPoint)];
  const xCols = [MX, 3.90];
  cols.forEach((col, ci) => {
    let y = 2.55;
    col.forEach((e) => {
      addText(slide, `${stripMd(e.role || '')} :`, {
        x: xCols[ci], y, w: 3.6, h: 0.3,
        fontSize: 11, bold: true, color: COL_WHITE, wrap: true,
      });
      y += 0.3;
      addText(slide, stripMd(e.expertise || ''), {
        x: xCols[ci], y, w: 3.6, h: 0.35,
        fontSize: 10, color: COL_WHITE, wrap: true,
      });
      y += 0.45;
    });
  });
}

function buildSlide14_Technologies(pptx, data, assetsDir) {
  const slide = pptx.addSlide();
  addBackground(slide, 14, assetsDir);
  const techs = data.sections?.technologies || [];
  const midPoint = Math.ceil(techs.length / 2);
  const cols = [techs.slice(0, midPoint), techs.slice(midPoint)];
  const xCols = [MX, COL2_R_X];
  cols.forEach((col, ci) => {
    let y = 1.8;
    col.forEach((t) => {
      addText(slide, `${stripMd(t.categorie || '')} :`, {
        x: xCols[ci], y, w: COL2_L_W, h: 0.3,
        fontSize: 11, bold: true, color: COL_WHITE, wrap: true,
      });
      y += 0.3;
      addText(slide, stripMd(t.detail || ''), {
        x: xCols[ci], y, w: COL2_L_W, h: 0.35,
        fontSize: 10, color: COL_WHITE, wrap: true,
      });
      y += 0.45;
    });
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
  addText(slide, 'Pôles de développement', {
    x: MX, y: 1.4, w: 3.6, h: 0.4, fontSize: 11, bold: true, color: COL_WHITE,
  });
  addText(slide, 'Volume horaire', {
    x: 4.2, y: 1.4, w: 2.5, h: 0.4, fontSize: 11, bold: true, color: COL_WHITE, align: 'center',
  });
  addText(slide, `Coût total (TJM : ${tjm}€/h)`, {
    x: 7.0, y: 1.4, w: 2.4, h: 0.4, fontSize: 11, bold: true, color: COL_WHITE, align: 'right',
  });

  let totalH = 0;
  let totalEur = 0;
  modules.slice(0, 5).forEach((m, i) => {
    const h = (m.items || []).reduce((s, it) => s + (it.heures || 0), 0);
    const eur = h * tjm;
    totalH += h;
    totalEur += eur;
    const y = 2.2 + i * 0.7;
    addText(slide, stripMd(m.titre || ''), {
      x: MX, y, w: 3.6, h: 0.6, fontSize: 11, color: COL_WHITE, wrap: true, valign: 'middle',
    });
    addText(slide, `${h} h`, {
      x: 4.2, y, w: 2.5, h: 0.6, fontSize: 11, color: COL_WHITE, align: 'center', valign: 'middle',
    });
    addText(slide, `${eur.toLocaleString('fr-FR')} €`, {
      x: 7.0, y, w: 2.4, h: 0.6, fontSize: 11, color: COL_ACCENT, align: 'right', valign: 'middle',
    });
  });

  addText(slide, 'TOTAL', {
    x: MX, y: 5.0, w: 3.6, h: 0.5, fontSize: 12, bold: true, color: COL_WHITE,
  });
  addText(slide, `${totalH} h`, {
    x: 4.2, y: 5.0, w: 2.5, h: 0.5, fontSize: 12, bold: true, color: COL_WHITE, align: 'center',
  });
  addText(slide, `${totalEur.toLocaleString('fr-FR')} €`, {
    x: 7.0, y: 5.0, w: 2.4, h: 0.5, fontSize: 12, bold: true, color: COL_WHITE, align: 'right',
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
