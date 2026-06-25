/**
 * EasyGestion — Générateur PPTX (pptxgenjs)
 * Lit le JSON canonique et produit une présentation 22 slides (13.33 × 7.5 in).
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

function moduleHours(mod) {
  return (mod.items || []).reduce((sum, it) => sum + (it.heures || 0), 0);
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

function buildSlide02_Intro(slide, data, assetsDir) {
  addBackground(slide, 2, assetsDir);
}

function buildSlide03_Enjeux(slide, data, assetsDir) {
  addBackground(slide, 3, assetsDir);
}

function buildSlide04_Solution(slide, data, assetsDir) {
  addBackground(slide, 4, assetsDir);
}

function buildSlide05_Methodologie(slide, data, assetsDir) {
  addBackground(slide, 5, assetsDir);
}

function buildSlide06_Objectifs(slide, data, assetsDir) {
  addBackground(slide, 6, assetsDir);
}

function buildSlide07_Contexte(slide, data, assetsDir) {
  addBackground(slide, 7, assetsDir);
  const ctx = (data.sections && data.sections.contexte) || {};
  addText(slide, stripMd(ctx.titre || 'Contexte actuel'), {
    x: 0.8, y: 1.0, w: 11.5, h: 0.7,
    fontSize: 20, bold: true,
  });
  if (ctx.texte) {
    addText(slide, stripMd(ctx.texte), {
      x: 0.8, y: 1.9, w: 11.5, h: 2.0,
      fontSize: 12, color: COL_GREY, valign: 'top',
    });
  }
  const bullets = (ctx.bullets || [])
    .map((b) => `• ${stripMd(b)}`)
    .join('\n');
  if (bullets) {
    addText(slide, bullets, {
      x: 0.8, y: 4.1, w: 11.5, h: 2.8,
      fontSize: 11, valign: 'top',
    });
  }
}

function buildSlide08_Fonctionnalites(slide, data, assetsDir) {
  addBackground(slide, 8, assetsDir);
  const cats = (data.sections && data.sections.fonctionnalites) || [];
  const COLS = 2;
  const ROWS = 3;
  const cellW = 6.0;
  const cellH = 1.9;
  const startX = 0.7;
  const startY = 1.2;
  const gapX = 0.5;

  cats.slice(0, COLS * ROWS).forEach((cat, idx) => {
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    const x = startX + col * (cellW + gapX);
    const y = startY + row * cellH;
    const items = (cat.items || [])
      .slice(0, 3)
      .map((it) => `• ${stripMd(it.titre)}`)
      .join('\n');
    const text = `${stripMd(cat.categorie)}\n${items}`;
    addText(slide, text, {
      x, y, w: cellW, h: cellH - 0.1,
      fontSize: 10, valign: 'top',
    });
  });
}

function buildSlide09_Processus(slide, data, assetsDir) {
  addBackground(slide, 9, assetsDir);
}

function buildSlide10_Acquisition(slide, data, assetsDir) {
  addBackground(slide, 10, assetsDir);
  const items = (data.sections && data.sections.acquisition) || [];
  const COLS = 2;
  const ROWS = 3;
  const cellW = 6.0;
  const cellH = 1.9;
  const startX = 0.7;
  const startY = 1.2;
  const gapX = 0.5;

  items.slice(0, COLS * ROWS).forEach((item, idx) => {
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    const x = startX + col * (cellW + gapX);
    const y = startY + row * cellH;
    const text = `${stripMd(item.titre)}\n${stripMd(item.detail)}`;
    addText(slide, text, {
      x, y, w: cellW, h: cellH - 0.1,
      fontSize: 10, valign: 'top',
    });
  });
}

function buildSlide11_Engagement(slide, data, assetsDir) {
  addBackground(slide, 11, assetsDir);
}

function buildSlide12_PlanAction(slide, data, assetsDir) {
  addBackground(slide, 12, assetsDir);
  const phases = (data.sections && data.sections.plan_action) || [];
  const COLS = 2;
  const ROWS = 2;
  const cellW = 6.0;
  const cellH = 2.8;
  const startX = 0.7;
  const startY = 1.2;
  const gapX = 0.5;

  phases.slice(0, COLS * ROWS).forEach((phase, idx) => {
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    const x = startX + col * (cellW + gapX);
    const y = startY + row * cellH;
    const taches = (phase.taches || [])
      .slice(0, 4)
      .map((t) => `• ${stripMd(t)}`)
      .join('\n');
    const text = `${stripMd(phase.phase)}\n${taches}`;
    addText(slide, text, {
      x, y, w: cellW, h: cellH - 0.1,
      fontSize: 10, valign: 'top',
    });
  });
}

function buildSlide13_Equipe(slide, data, assetsDir) {
  addBackground(slide, 13, assetsDir);
  const members = (data.sections && data.sections.equipe) || [];
  const COLS = 3;
  const ROWS = 2;
  const cellW = 4.0;
  const cellH = 2.5;
  const startX = 0.5;
  const startY = 1.3;
  const gapX = 0.35;

  members.slice(0, COLS * ROWS).forEach((m, idx) => {
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    const x = startX + col * (cellW + gapX);
    const y = startY + row * cellH;
    const text = [
      stripMd(m.role),
      `(${m.experience || ''})`,
      stripMd(m.expertise),
    ].filter(Boolean).join('\n');
    addText(slide, text, {
      x, y, w: cellW, h: cellH - 0.1,
      fontSize: 9.5, valign: 'top',
    });
  });
}

function buildSlide14_Technologies(slide, data, assetsDir) {
  addBackground(slide, 14, assetsDir);
  const techs = (data.sections && data.sections.technologies) || [];
  const COLS = 2;
  const ROWS = 3;
  const cellW = 6.0;
  const cellH = 1.9;
  const startX = 0.7;
  const startY = 1.2;
  const gapX = 0.5;

  techs.slice(0, COLS * ROWS).forEach((t, idx) => {
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    const x = startX + col * (cellW + gapX);
    const y = startY + row * cellH;
    const text = `${stripMd(t.categorie)}\n${stripMd(t.detail)}`;
    addText(slide, text, {
      x, y, w: cellW, h: cellH - 0.1,
      fontSize: 10, valign: 'top',
    });
  });
}

function buildSlide15_Partenariat(slide, data, assetsDir) {
  addBackground(slide, 15, assetsDir);
}

function buildSlide16_Budget(slide, data, assetsDir) {
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

function buildSlide17_Repartition(slide, data, assetsDir) {
  addBackground(slide, 17, assetsDir);
  const projet = data.projet || {};
  const tjm = projet.tjm || 100;
  const modules = (data.budget_detail && data.budget_detail.modules) || [];
  const startY = 1.5;
  const lineH = 0.85;

  modules.slice(0, 5).forEach((mod, i) => {
    const heures = moduleHours(mod);
    const montant = heures * tjm;
    const y = startY + i * lineH;
    addText(slide, stripMd(mod.titre), {
      x: 0.8, y, w: 7.0, h: lineH, fontSize: 12,
    });
    addText(slide, `${heures} h`, {
      x: 8.0, y, w: 2.0, h: lineH, fontSize: 12, align: 'right',
    });
    addText(slide, fmtEur(montant), {
      x: 10.2, y, w: 2.5, h: lineH,
      fontSize: 12, bold: true, align: 'right', color: COL_ACCENT,
    });
  });
}

function buildSlide18_Garanties(slide, data, assetsDir) {
  addBackground(slide, 18, assetsDir);
}

function buildSlide19_Jalons(slide, data, assetsDir) {
  addBackground(slide, 19, assetsDir);
}

function buildSlide20_Facturation(slide, data, assetsDir) {
  addBackground(slide, 20, assetsDir);
}

function buildSlide21_ProchainesEtapes(slide, data, assetsDir) {
  addBackground(slide, 21, assetsDir);
}

function buildSlide22_Merci(slide, data, assetsDir) {
  addBackground(slide, 22, assetsDir);
  const emi = data.emetteur || {};
  addText(slide, emi.contact_nom || '', {
    x: 9.0, y: 6.0, w: 4.0, h: 0.35,
    fontSize: 11, align: 'right',
  });
  addText(slide, emi.contact_email || '', {
    x: 9.0, y: 6.4, w: 4.0, h: 0.35,
    fontSize: 10, color: COL_GREY, align: 'right',
  });
  addText(slide, emi.contact_tel || '', {
    x: 9.0, y: 6.75, w: 4.0, h: 0.35,
    fontSize: 10, color: COL_GREY, align: 'right',
  });
}

// ─── Génération ───────────────────────────────────────────────────────────────

const SLIDE_BUILDERS = [
  buildSlide01_Couverture,
  buildSlide02_Intro,
  buildSlide03_Enjeux,
  buildSlide04_Solution,
  buildSlide05_Methodologie,
  buildSlide06_Objectifs,
  buildSlide07_Contexte,
  buildSlide08_Fonctionnalites,
  buildSlide09_Processus,
  buildSlide10_Acquisition,
  buildSlide11_Engagement,
  buildSlide12_PlanAction,
  buildSlide13_Equipe,
  buildSlide14_Technologies,
  buildSlide15_Partenariat,
  buildSlide16_Budget,
  buildSlide17_Repartition,
  buildSlide18_Garanties,
  buildSlide19_Jalons,
  buildSlide20_Facturation,
  buildSlide21_ProchainesEtapes,
  buildSlide22_Merci,
];

async function generatePptx(data, outputPath, assetsDir) {
  const pptx = new pptxgen();
  pptx.defineLayout({ name: 'WIDE', width: SLIDE_W, height: SLIDE_H });
  pptx.layout = 'WIDE';

  SLIDE_BUILDERS.forEach((builder) => {
    const slide = pptx.addSlide();
    builder(slide, data, assetsDir);
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
