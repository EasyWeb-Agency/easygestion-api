#!/usr/bin/env python3
"""
EasyGestion — Générateur de devis PDF (v4)
===========================================

Architecture "PNG background + texte par-dessus" :
  - Page_de_garde.png    → page 1, aucun texte superposé
  - Premie_re_page.png   → page 2, infos client + objet mission
  - Page_classique.png   → pages 3+, contenu courant

Texte superposé via reportlab. Aucune déformation : la page PDF prend
exactement le ratio des PNG (4790×7200 px = 1.503).

3 modes de devis (détection automatique selon le JSON) :
  1. STANDARD            → modules + jalons + signature + CGV/TMA/SEO
  2. PARTENARIAT         → modules + récap + valeur offerte + 8 articles + CGV
                            (bloc "partenariat" dans le JSON)
  3. OPTIONS_PRICING     → modules + tableau comparatif V1/V2 + 2 échéanciers
                            (bloc "options_pricing" dans le JSON)

Usage :
    python3 generate_devis_v4.py --input devis.json --output devis.pdf
    python3 generate_devis_v4.py --input devis.json --output devis.pdf --assets-dir ./assets
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph, Table, TableStyle, Spacer


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES & HELPERS
# ═══════════════════════════════════════════════════════════════════════════

PNG_W, PNG_H = 4790, 7200
PAGE_W = 595.0
PAGE_H = PAGE_W * (PNG_H / PNG_W)   # ≈ 894.4 pt

# ─── Constantes pour la page ROI (format paysage 16:9) ───
ROI_PNG_W, ROI_PNG_H = 8000, 4500
ROI_PAGE_W = 842.0  # A4 paysage en pt
ROI_PAGE_H = ROI_PAGE_W * (ROI_PNG_H / ROI_PNG_W)  # ≈ 473.6 pt

COL_INK = HexColor("#111111")
COL_GREY = HexColor("#555555")
COL_LIGHT_GREY = HexColor("#CCCCCC")
COL_BG_LIGHT = HexColor("#F5F5F5")
COL_BG_YELLOW = HexColor("#FFF4E0")
COL_ACCENT_ORANGE = HexColor("#E0A040")
COL_RED_DARK = HexColor("#B71C1C")
COL_WHITE = HexColor("#FFFFFF")

FONT_REG = "BodyFont"
FONT_BOLD = "BodyFont-Bold"
FONT_ITALIC = "BodyFont-Italic"
FONT_MEDIUM = "BodyFont-Medium"  # graisse intermédiaire pour les titres (Avenir Medium-like)


def px_to_pdf(x_px: float, y_px: float) -> tuple[float, float]:
    """Convertit (x,y) du repère PNG (top-left) au repère PDF (bottom-left)."""
    x_pt = (x_px / PNG_W) * PAGE_W
    y_pt = PAGE_H - (y_px / PNG_H) * PAGE_H
    return x_pt, y_pt


def px_size(px: float) -> float:
    """Convertit une taille en px vers points PDF."""
    return px * PAGE_W / PNG_W


def roi_px_to_pdf(x_px: float, y_px: float) -> tuple[float, float]:
    """Convertit (x,y) du PNG ROI vers les coordonnées PDF paysage."""
    x_pt = (x_px / ROI_PNG_W) * ROI_PAGE_W
    y_pt = ROI_PAGE_H - (y_px / ROI_PNG_H) * ROI_PAGE_H
    return x_pt, y_pt


def roi_px_size(px: float) -> float:
    """Convertit une taille en px vers points PDF (page ROI paysage)."""
    return px * ROI_PAGE_W / ROI_PNG_W


def compute_roi_scenarios(panier_moyen: float, tc_pct: float,
                          tx_closing_pct: float, investissement_mensuel: float,
                          profil: str = "btob_premium") -> list[dict]:
    """Calcule les 4 scénarios de projection ROI.

    Formule :
      V/m  (ventes/mois) = T/m × (tc/100) × (tx_closing/100)
      CA/m = V/m × panier_moyen
      ROI  = CA/m / investissement_mensuel

    Le point d'équilibre est calculé mathématiquement : T/m tel que ROI = 1.
    Les autres scénarios sont des multipliers selon le profil.

    Profils de croissance (multiplicateurs sur le point d'équilibre) :
      - "btob_premium"  : 1 / 1,5 / 2,5 / 3,5 (conservateur)
      - "ecommerce_mass": 1 / 2   / 4   / 6   (plus optimiste)
    """
    tc = tc_pct / 100
    closing = tx_closing_pct / 100
    coeff = tc * closing  # taux conversion total visiteur → vente

    # Point d'équilibre mathématique : T/m tel que ROI = 1
    t_eq = investissement_mensuel / (panier_moyen * coeff)

    multipliers_map = {
        "btob_premium":   [1.0, 1.5, 2.5, 3.5],
        "ecommerce_mass": [1.0, 2.0, 4.0, 6.0],
    }
    multipliers = multipliers_map.get(profil, multipliers_map["btob_premium"])

    labels = [
        "Point d'équilibre (Minimum)",
        "Prudent",
        "Réaliste (Objectif)",
        "Optimiste",
    ]

    scenarios = []
    for label, m in zip(labels, multipliers):
        t = t_eq * m
        v = t * coeff
        ca = v * panier_moyen
        roi = ca / investissement_mensuel
        scenarios.append({
            "label": label,
            "tm": t,
            "tc_pct": tc_pct,
            "vm": v,
            "cam": ca,
            "roi": roi,
        })
    return scenarios


def _md(text: str) -> str:
    """Convertit le markdown léger en HTML pour reportlab.

    Supporte : **gras**, *italique*, `code`
    """
    if not text:
        return ""
    # Échapper d'abord les caractères HTML dangereux
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # **gras** → <b>gras</b>
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    # *italique* → <i>italique</i>
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<i>\1</i>", text)
    # `code` → font mono (simulé)
    text = re.sub(r"`([^`]+)`", r"<font face='Courier'>\1</font>", text)
    return text


def _fmt_eur(n: int | float) -> str:
    """Formate un montant en euros à la française : 12345 → '12 345 €'."""
    return f"{int(n):,}".replace(",", "\u202f") + "\u00a0€"


def _fmt_h(h: float) -> str:
    """Formate des heures : 3.5 → '3,5 h' / 14 → '14 h'."""
    if h == int(h):
        return f"{int(h)}\u00a0h"
    return f"{h:.1f}\u00a0h".replace(".", ",")


# ═══════════════════════════════════════════════════════════════════════════
# POLICES
# ═══════════════════════════════════════════════════════════════════════════

def register_fonts(fonts_dir: Path | None = None) -> None:
    """Enregistre les polices d'écriture pour le devis.

    Stratégie de chargement, par ordre de priorité :
      1. **Nunito Sans** (Regular 400 / Medium 500 / Bold 700) — proche d'Avenir,
         poids fins privilégiés pour les titres (style « Avenir Medium »).
         Cherche les fichiers dans, dans cet ordre :
           - `fonts_dir` (paramètre)
           - `<script>/fonts/`
           - `/usr/share/fonts/truetype/nunito/`
      2. **DejaVu Sans** (Regular / Bold / Oblique) — fallback système Linux ;
         dans ce cas FONT_MEDIUM pointe vers DejaVu Sans Regular (effet « moins
         gras » que Bold sans changer de famille).
      3. **Liberation Sans** — fallback ultime.
      4. **Helvetica** — fallback Acrobat natif (si tout le reste a échoué).

    Args:
        fonts_dir: dossier optionnel contenant `NunitoSans-Regular.ttf`,
            `NunitoSans-Medium.ttf`, `NunitoSans-Bold.ttf`. Si None, cherche
            dans `<script>/fonts/`.
    """
    from reportlab.pdfbase.pdfmetrics import registerFontFamily

    script_dir = Path(__file__).parent
    candidate_dirs: list[Path] = []
    if fonts_dir is not None:
        candidate_dirs.append(Path(fonts_dir))
    candidate_dirs.append(script_dir / "fonts")
    candidate_dirs.append(Path("/usr/share/fonts/truetype/nunito"))

    # ─── Tentative 1 : Nunito Sans (3 graisses) ───
    for d in candidate_dirs:
        reg = d / "NunitoSans-Regular.ttf"
        med = d / "NunitoSans-Medium.ttf"
        bold = d / "NunitoSans-Bold.ttf"
        if reg.exists() and med.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont(FONT_REG, str(reg)))
            pdfmetrics.registerFont(TTFont(FONT_MEDIUM, str(med)))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
            # Italic : DejaVu Oblique en fallback (Nunito Italic non chargé)
            ital_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf")
            if ital_path.exists():
                pdfmetrics.registerFont(TTFont(FONT_ITALIC, str(ital_path)))
            else:
                pdfmetrics.registerFont(TTFont(FONT_ITALIC, str(reg)))
            registerFontFamily(FONT_REG,
                               normal=FONT_REG, bold=FONT_BOLD,
                               italic=FONT_ITALIC)
            return

    # ─── Tentative 2 : DejaVu Sans (Regular pour Medium fallback) ───
    dejavu = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"),
    ]
    for reg, bold, ital in dejavu:
        if Path(reg).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont(FONT_REG, reg))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))
            # FONT_MEDIUM = Regular (effet "moins gras" sans changer de famille)
            pdfmetrics.registerFont(TTFont(FONT_MEDIUM, reg))
            if Path(ital).exists():
                pdfmetrics.registerFont(TTFont(FONT_ITALIC, ital))
            else:
                pdfmetrics.registerFont(TTFont(FONT_ITALIC, reg))
            registerFontFamily(FONT_REG,
                               normal=FONT_REG, bold=FONT_BOLD,
                               italic=FONT_ITALIC)
            return

    # ─── Fallback final : Helvetica (pas idéal mais ne plante pas) ───
    pdfmetrics.registerFont(TTFont(FONT_REG, "Helvetica"))
    pdfmetrics.registerFont(TTFont(FONT_MEDIUM, "Helvetica"))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, "Helvetica-Bold"))


# ═══════════════════════════════════════════════════════════════════════════
# STYLES TYPOGRAPHIQUES
# ═══════════════════════════════════════════════════════════════════════════

def make_styles() -> dict[str, ParagraphStyle]:
    """Génère les styles ParagraphStyle utilisés dans tout le document.

    Les titres (h1, h2, h3) utilisent **FONT_MEDIUM** (Nunito Sans Medium —
    proche d'Avenir Medium) pour un rendu moins lourd qu'un Bold classique.
    Le corps et les puces restent en Regular.
    """
    return {
        "h1": ParagraphStyle("H1",
            fontName=FONT_MEDIUM, fontSize=20, leading=26,
            textColor=COL_INK, spaceAfter=10, alignment=TA_LEFT),
        "h2": ParagraphStyle("H2",
            fontName=FONT_MEDIUM, fontSize=11, leading=16,
            textColor=COL_INK, spaceAfter=14, alignment=TA_LEFT),
        "h3": ParagraphStyle("H3",
            fontName=FONT_MEDIUM, fontSize=12, leading=18,
            textColor=COL_INK, spaceAfter=10, alignment=TA_LEFT),
        "body": ParagraphStyle("Body",
            fontName=FONT_REG, fontSize=10, leading=14,
            textColor=COL_INK, spaceAfter=10, alignment=TA_LEFT),
        "bullet": ParagraphStyle("Bullet",
            fontName=FONT_REG, fontSize=10, leading=14,
            textColor=COL_INK, spaceAfter=4, alignment=TA_LEFT,
            leftIndent=14, bulletIndent=2),
        "small": ParagraphStyle("Small",
            fontName=FONT_REG, fontSize=9, leading=12,
            textColor=COL_GREY, spaceAfter=4, alignment=TA_LEFT),
    }


# ═══════════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Section:
    """Une section du devis. Le `kind` détermine le rendu."""
    kind: str  # 'h1' | 'h2' | 'h3' | 'p' | 'bullet' | 'spacer' | 'pagebreak'
               # | 'table' | 'module' | 'module_total' | 'signature'
               # | 'recap_table' | 'partenariat_valeur_table'
               # | 'partenariat_sla_table' | 'options_table'
    text: str = ""
    data: Any = None
    height: float = 0


@dataclass
class ClientInfo:
    nom: str = ""
    representant: str = ""
    adresse_l1: str = ""
    adresse_l2: str = ""
    email: str = ""
    siret: str = ""


@dataclass
class EmetteurInfo:
    nom: str = ""
    adresse_l1: str = ""
    adresse_l2: str = ""
    siret: str = ""


@dataclass
class ContactInfo:
    nom: str = ""
    email: str = ""
    tel: str = ""


@dataclass
class ProjetInfo:
    nom: str = ""
    type: str = "web"  # 'web' | 'mobile' | 'seo'
    budget: float = 0
    duree_mois: int = 0
    tjm: int = 100


# ═══════════════════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Devis:
    devis_no: str
    date_creation: str
    client: ClientInfo
    sections: list[Section] = field(default_factory=list)
    contact: ContactInfo = field(default_factory=ContactInfo)
    emetteur: EmetteurInfo = field(default_factory=EmetteurInfo)
    assets_dir: Path = field(default_factory=lambda: Path(__file__).parent)

    # ─── Constructeur depuis JSON canonique ────────────────────────────────
    @classmethod
    def from_json(cls, json_path: str | Path,
                  assets_dir: Path | None = None) -> "Devis":
        """Construit un Devis à partir du JSON canonique EasyGestion.

        Le JSON peut être en 3 modes :
        - Standard : `budget_detail.jalons` présent
        - Partenariat : bloc `partenariat` présent
        - Options : bloc `budget_detail.options_pricing` présent
        """
        json_path = Path(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            d = json.load(f)

        # ─── Header info ───
        meta = d["meta"]
        proj_d = d["projet"]
        cli_d = d["client"]
        emi_d = d["emetteur"]

        client = ClientInfo(
            nom=cli_d.get("nom", ""),
            representant=cli_d.get("representant", ""),
            adresse_l1=cli_d.get("adresse_l1", ""),
            adresse_l2=cli_d.get("adresse_l2", ""),
            email=cli_d.get("email", ""),
            siret=cli_d.get("siret", ""),
        )
        contact = ContactInfo(
            nom=emi_d.get("contact_nom", ""),
            email=emi_d.get("contact_email", ""),
            tel=emi_d.get("contact_tel", ""),
        )
        emetteur = EmetteurInfo(
            nom=emi_d.get("nom", ""),
            adresse_l1=emi_d.get("adresse_l1", ""),
            adresse_l2=emi_d.get("adresse_l2", ""),
            siret=emi_d.get("siret", ""),
        )
        proj = ProjetInfo(
            nom=proj_d.get("nom", ""),
            type=proj_d.get("type", "web"),
            budget=proj_d.get("budget", 0),
            duree_mois=proj_d.get("duree_mois", 0),
            tjm=proj_d.get("tjm", 100),
        )

        # ─── Construction des sections ───
        sections: list[Section] = []
        sec_data = d.get("sections", {})
        bud = d.get("budget_detail", {})

        # 1. Objet de la mission (sur la première page de contenu)
        if sec_data.get("objet_mission"):
            sections.append(Section("h1", "Objet de la mission"))
            for para in sec_data["objet_mission"].split("\n\n"):
                if para.strip():
                    sections.append(Section("p", _md(para)))

        # 2. Contexte
        ctx = sec_data.get("contexte")
        if ctx:
            sections.append(Section("h3", "1. Contexte actuel"))
            if ctx.get("texte"):
                sections.append(Section("p", _md(ctx["texte"])))
            for b in ctx.get("bullets", []):
                sections.append(Section("bullet", _md(b)))

        # 3. Fonctionnalités clés
        fonctionnalites = sec_data.get("fonctionnalites", [])
        if fonctionnalites:
            sections.append(Section("h3", "2. Fonctionnalités clés"))
            sections.append(Section("p",
                "L'application sera structurée autour de "
                f"<b>{len(fonctionnalites)} grandes familles de fonctionnalités</b>\u00a0:"))
            for cat in fonctionnalites:
                sections.append(Section("h3", cat["categorie"]))
                for item in cat.get("items", []):
                    sections.append(Section("bullet",
                        f"<b>{_md(item['titre'])}</b> — {_md(item['detail'])}"))

        # 4. Stratégie d'acquisition
        acq = sec_data.get("acquisition", [])
        if acq:
            sections.append(Section("pagebreak"))
            sections.append(Section("h1", "Stratégie d'acquisition"))
            sections.append(Section("p",
                "Pour atteindre rapidement la masse critique, nous combinons "
                "plusieurs leviers complémentaires\u00a0:"))
            for a in acq:
                sections.append(Section("bullet",
                    f"<b>{_md(a['titre'])}</b> — {_md(a['detail'])}"))

        # 5. Plan d'action
        plan = sec_data.get("plan_action", [])
        if plan:
            sections.append(Section("h1", "Plan d'action"))
            sections.append(Section("p",
                f"Le projet sera mené sur <b>{proj.duree_mois}\u00a0mois</b> "
                f"selon les phases suivantes\u00a0:"))
            for phase in plan:
                sections.append(Section("h3", phase["phase"]))
                for t in phase.get("taches", []):
                    sections.append(Section("bullet", _md(t)))

        # 6. Équipe dédiée
        eq = sec_data.get("equipe", [])
        if eq:
            sections.append(Section("h1", "L'équipe dédiée"))
            sections.append(Section("p",
                "Une équipe expérimentée sera mobilisée tout au long du projet\u00a0:"))
            for m in eq:
                sections.append(Section("bullet",
                    f"<b>{_md(m['role'])}</b> ({m['experience']}) — "
                    f"{_md(m['expertise'])}"))

        # 7. Technologies
        techs = sec_data.get("technologies", [])
        if techs:
            sections.append(Section("h1", "Stack technologique"))
            sections.append(Section("p",
                "Les choix techniques privilégient la robustesse et la pérennité\u00a0:"))
            for t in techs:
                sections.append(Section("bullet",
                    f"<b>{_md(t['categorie'])}</b> — {_md(t['detail'])}"))

        # 8. Répartition budgétaire détaillée
        modules = bud.get("modules", [])
        if modules:
            sections.append(Section("pagebreak"))
            sections.append(Section("h1", "Répartition budgétaire détaillée"))
            sections.append(Section("p",
                "La présente estimation est établie sur la base d'un taux "
                f"journalier de <b>{proj.tjm}\u00a0€/heure HT</b>. Le détail "
                "ci-dessous présente l'ensemble des fonctionnalités, leur "
                "volume horaire estimé et le coût associé, regroupés par "
                "module fonctionnel."))
            sections.append(Section("spacer", height=8))
            total_h = 0
            for mod in modules:
                items = [(it["nom"], it["heures"]) for it in mod["items"]]
                offert = bool(mod.get("offert", False))
                sections.append(Section("module", text=mod["titre"],
                                        data={"items": items, "offert": offert}))
                # Un module offert ne s'ajoute pas au total général
                if not offert:
                    total_h += sum(h for _, h in items)
            total_amt = total_h * proj.tjm
            sections.append(Section("spacer", height=10))

            # En mode "options_pricing", on n'affiche pas le total général
            options_pricing = bud.get("options_pricing")
            if not options_pricing:
                sections.append(Section("module_total",
                    data=[("Total général de la prestation", total_h, total_amt)]))
            sections.append(Section("spacer", height=14))

        # ─── 9. Récap financier : 3 chemins selon le bloc présent ───
        partenariat = d.get("partenariat")
        options_pricing = bud.get("options_pricing")

        # ╔═══ CHEMIN 1 : OPTIONS_PRICING (V1 / V2 ou V1 / V2 / V3) ═══
        if options_pricing:
            v1 = options_pricing["v1"]
            v2 = options_pricing["v2"]
            v3 = options_pricing.get("v3")  # optionnel : 3e pack

            sections.append(Section("h1",
                options_pricing.get("titre", "Options de démarrage")))
            if options_pricing.get("preambule"):
                sections.append(Section("p", _md(options_pricing["preambule"])))
            sections.append(Section("spacer", height=12))

            # Tableau comparatif V1 / V2 (ou V1 / V2 / V3)
            table_data = {"v1": v1, "v2": v2}
            if v3:
                table_data["v3"] = v3
            sections.append(Section("options_table", data=table_data))
            sections.append(Section("spacer", height=14))

            # Échéanciers : un par option
            echeancier_v1 = bud.get("echeancier_v1", [])
            echeancier_v2 = bud.get("echeancier_v2", [])
            echeancier_v3 = bud.get("echeancier_v3", []) if v3 else []

            sections.append(Section("pagebreak"))
            sections.append(Section("h1", "Échéanciers de facturation"))
            sections.append(Section("p",
                "Selon l'option choisie à la signature, l'échéancier de "
                "facturation s'établit comme suit\u00a0:"))
            sections.append(Section("spacer", height=8))

            options_list = [
                (v1.get("code", "Option A"), echeancier_v1, v1),
                (v2.get("code", "Option B"), echeancier_v2, v2),
            ]
            if v3:
                options_list.append(
                    (v3.get("code", "Option C"), echeancier_v3, v3))

            for label, ech, opt in options_list:
                if ech:
                    prix_fmt = _fmt_eur(opt.get("prix", 0)).replace("\u00a0€", "")
                    sections.append(Section("h3",
                        f"{label} — {opt.get('titre', '')} "
                        f"({prix_fmt}\u00a0€\u00a0HT)"))
                    for e in ech:
                        sections.append(Section("bullet",
                            f"<b>{_fmt_eur(e['montant']).replace('€', 'HT')}</b> "
                            f"— {_md(e['libelle'])}"))
                    sections.append(Section("spacer", height=10))

            # Bon pour accord avec choix d'option
            sections.append(Section("pagebreak"))
            sections.append(Section("h1", "Bon pour accord"))
            sections.append(Section("p",
                "La signature du présent devis vaut <b>acceptation pleine et "
                "entière</b> du périmètre de la mission, de l'option de "
                "démarrage choisie ci-dessous, et des Conditions Générales "
                "de Vente figurant en annexe."))
            sections.append(Section("spacer", height=10))
            sections.append(Section("h3", "Option de démarrage retenue"))
            sections.append(Section("bullet",
                f"☐\u00a0&nbsp;&nbsp;<b>{v1.get('code')}</b> — {v1.get('titre')}\u00a0: "
                f"<b>{_fmt_eur(v1.get('prix', 0))} HT</b> ({v1.get('duree', '')})"))
            sections.append(Section("bullet",
                f"☐\u00a0&nbsp;&nbsp;<b>{v2.get('code')}</b> — {v2.get('titre')}\u00a0: "
                f"<b>{_fmt_eur(v2.get('prix', 0))} HT</b> ({v2.get('duree', '')})"))
            if v3:
                hl = " (recommandé)" if v3.get("highlight") else ""
                sections.append(Section("bullet",
                    f"☐\u00a0&nbsp;&nbsp;<b>{v3.get('code')}</b> — {v3.get('titre')}{hl}\u00a0: "
                    f"<b>{_fmt_eur(v3.get('prix', 0))} HT</b> ({v3.get('duree', '')})"))
            sections.append(Section("spacer", height=8))
            sections.append(Section("p",
                "<i>Cocher l'option retenue. À défaut, l'Option A sera "
                "considérée comme retenue par défaut.</i>"))
            sections.append(Section("spacer", height=14))
            sections.append(Section("signature"))
            sections.extend(_default_cgv_sections())

            return cls(
                devis_no=meta["devis_no"],
                date_creation=meta["date_creation"],
                client=client, sections=sections, contact=contact,
                emetteur=emetteur,
                assets_dir=assets_dir or Path(__file__).parent,
            )

        # ╔═══ CHEMIN 2 : PARTENARIAT (SeniorLink type) ═══
        if partenariat:
            remise = bud.get("remise")
            offerts = bud.get("offerts", [])
            echeancier = bud.get("echeancier", [])

            sections.append(Section("h3", "Récapitulatif financier"))
            sections.append(Section("p",
                "Le présent récapitulatif détaille la valeur totale du "
                "développement, la remise partenariat exclusive et les "
                "éléments offerts dans le cadre de notre engagement long terme."))

            recap_rows = []
            if modules:
                total_h = sum(it["heures"] for m in modules for it in m["items"])
                total_amt = total_h * proj.tjm
                recap_rows.append(("Valeur totale du développement (base forfait)",
                                   _fmt_eur(total_amt) + " HT"))
            if remise:
                recap_rows.append((f"<i>{_md(remise['libelle'])}</i>",
                                   f"− {_fmt_eur(remise['montant'])} HT"))
            for o in offerts:
                recap_rows.append((f"<i>{_md(o['libelle'])}</i>",
                                   f"<b>OFFERT</b> (valorisé {_fmt_eur(o['valeur'])} HT)"))
            forfait_final = total_amt - (remise["montant"] if remise else 0)
            recap_rows.append(("<b>TOTAL FORFAIT INITIAL HT</b>",
                               f"<b>{_fmt_eur(forfait_final)} HT</b>"))
            tva = int(forfait_final * 0.20)
            recap_rows.append(("TVA 20\u00a0%", _fmt_eur(tva)))
            recap_rows.append(("<b>TOTAL TTC</b>",
                               f"<b>{_fmt_eur(forfait_final + tva)} TTC</b>"))
            sections.append(Section("recap_table", data=recap_rows))
            sections.append(Section("spacer", height=14))

            if echeancier:
                sections.append(Section("h3", "Échéancier de facturation"))
                sections.append(Section("p",
                    f"Le forfait initial est réglé en <b>{len(echeancier)} "
                    "versements</b> calés sur les jalons de livraison\u00a0:"))
                for e in echeancier:
                    sections.append(Section("bullet",
                        f"<b>{_fmt_eur(e['montant'])} HT</b> — {_md(e['libelle'])}"))

            # Bloc optionnel : options_seo (utile aussi pour les propositions
            # à tiroirs avec choix d'option au moment de la signature)
            opt_seo = d.get("options_seo")
            if opt_seo:
                sections.append(Section("pagebreak"))
                sections.append(Section("h1",
                    opt_seo.get("titre", "Options disponibles")))
                if opt_seo.get("preambule"):
                    for para in opt_seo["preambule"].split("\n\n"):
                        if para.strip():
                            sections.append(Section("p", _md(para)))
                sections.append(Section("spacer", height=8))
                sections.append(Section("options_seo_table",
                    data={"options": opt_seo["options"]}))
                if opt_seo.get("footer"):
                    sections.append(Section("spacer", height=8))
                    for para in opt_seo["footer"].split("\n\n"):
                        if para.strip():
                            sections.append(Section("p", _md(para)))

            # Bon pour accord
            first_ech = echeancier[0] if echeancier else None
            acompte_txt = ""
            if first_ech:
                acompte_txt = (f"Un premier versement de "
                               f"<b>{_fmt_eur(first_ech['montant'])} HT</b> "
                               f"sera appelé à la signature du devis.")
            sections.append(Section("pagebreak"))
            sections.append(Section("h1", "Bon pour accord"))
            sections.append(Section("p",
                "La signature du présent devis vaut <b>acceptation pleine et "
                "entière</b> du périmètre de la mission, du récapitulatif "
                "financier, des <b>Conditions Particulières de Partenariat</b> "
                "et des Conditions Générales de Vente figurant en annexe. "
                + acompte_txt))
            sections.append(Section("spacer", height=20))
            sections.append(Section("signature"))

            # Section "Conditions Particulières de Partenariat"
            sections.extend(_build_partenariat_sections(partenariat))
            sections.extend(_default_cgv_sections())

            return cls(
                devis_no=meta["devis_no"],
                date_creation=meta["date_creation"],
                client=client, sections=sections, contact=contact,
                emetteur=emetteur,
                assets_dir=assets_dir or Path(__file__).parent,
            )

        # ╔═══ CHEMIN 3 : STANDARD (jalons + signature classique) ═══
        jalons = bud.get("jalons", [])
        if jalons:
            sections.append(Section("p",
                "Les <b>jalons de facturation</b> sont alignés sur les "
                "livrables techniques\u00a0:"))
            for j in jalons:
                sections.append(Section("bullet",
                    f"{_md(j['libelle'])}\u00a0: "
                    f"<b>{j['pourcentage']}\u00a0% — {_fmt_eur(j['montant'])} HT</b>"))

        # ─── Bloc optionnel : Projection de ROI (mini-tableau inline) ───
        # Dans la lettre de mission, le ROI est présenté de façon classique :
        # un paragraphe de contexte + un tableau Tabular avec les 4 scénarios.
        # (La version paysage "diapo" est dans la présentation séparée.)
        # Format JSON attendu :
        # {
        #   "projection_roi": {
        #     "panier_moyen": 10000,
        #     "taux_conversion": 1.5,
        #     "taux_closing": 10,
        #     "investissement_mensuel": 248,
        #     "point_equilibre_mois": 6,
        #     "profil": "btob_premium"        # ou "ecommerce_mass"
        #   }
        # }
        roi = d.get("projection_roi")
        if roi:
            sections.append(Section("pagebreak"))
            sections.append(Section("h1", "Projection de ROI"))
            # Paragraphe de contexte
            scenarios = compute_roi_scenarios(
                float(roi["panier_moyen"]),
                float(roi["taux_conversion"]),
                float(roi["taux_closing"]),
                float(roi["investissement_mensuel"]),
                roi.get("profil", "btob_premium"),
            )
            panier = float(roi["panier_moyen"])
            invest = float(roi["investissement_mensuel"])
            tc_pct = float(roi["taux_conversion"])
            closing_pct = float(roi["taux_closing"])
            eq_mois = roi.get("point_equilibre_mois", 6)

            # Helpers de format inline pour le paragraphe
            def _fmt_eur_inline(x):
                return f"{int(round(x)):,}".replace(",", " ")
            def _fmt_pct_inline(x):
                # Affiche 1,5 % et 10 % (pas 10,0 %), virgule décimale française
                if abs(x - round(x)) < 0.05:
                    return f"{int(round(x))}"
                return f"{x:.1f}".replace(".", ",")

            sections.append(Section("p",
                f"Sur la base d'un <b>panier moyen de "
                f"{_fmt_eur_inline(panier)}\u00a0€ HT</b>, d'un taux de conversion "
                f"visiteur → lead de <b>{_fmt_pct_inline(tc_pct)}\u202f%</b>, d'un taux de "
                f"closing lead → vente de <b>{_fmt_pct_inline(closing_pct)}\u202f%</b>, et "
                f"d'un investissement mensuel de "
                f"<b>{_fmt_eur_inline(invest)}\u00a0€ HT</b>, voici la projection "
                f"de retour sur investissement attendue selon 4 scénarios "
                f"de croissance du trafic mensuel."))
            sections.append(Section("p",
                f"Le <b>point d'équilibre</b> (ROI = 1) est estimé "
                f"atteint à partir du <b>{eq_mois}ème mois</b> après mise "
                f"en ligne du site."))
            sections.append(Section("spacer", height=6))
            sections.append(Section("roi_table", data={
                "scenarios": scenarios,
            }))

        # ─── Bloc optionnel : extension à d'autres sites (grille dégressive) ───
        # Permet d'inciter le client à dupliquer la prestation sur ses filiales
        # avec une remise par effet d'échelle. Format JSON attendu :
        # {
        #   "extension_filiales": {
        #     "titre": "Étendre la mission aux filiales du Groupe",
        #     "preambule": "texte d'intro...",
        #     "base_annuelle_par_site": 12400,
        #     "grille": [
        #       {"nb_sites": 1,  "remise_pct": 0,  "prix_par_site_an": 12400,
        #        "total_an": 12400, "economie_an": 0},
        #       ...
        #     ],
        #     "footer": "phrase de conclusion (optionnel)"
        #   }
        # }
        ext = d.get("extension_filiales")
        if ext:
            sections.append(Section("pagebreak"))
            sections.append(Section("h1",
                ext.get("titre", "Extension de la mission à d'autres sites")))
            if ext.get("preambule"):
                for para in ext["preambule"].split("\n\n"):
                    if para.strip():
                        sections.append(Section("p", _md(para)))
            sections.append(Section("spacer", height=8))
            sections.append(Section("extension_table",
                data={"grille": ext["grille"],
                      "base": ext.get("base_annuelle_par_site")}))
            if ext.get("footer"):
                sections.append(Section("spacer", height=10))
                for para in ext["footer"].split("\n\n"):
                    if para.strip():
                        sections.append(Section("p", _md(para)))

        # ─── Bloc optionnel : Options SEO disponibles à la signature ───
        # Permet de présenter SEO Build + SEO Run en options activables au
        # moment de la signature, sans les inclure dans le total général.
        # Format JSON attendu :
        # {
        #   "options_seo": {
        #     "titre": "Options SEO disponibles",
        #     "preambule": "texte d'intro...",
        #     "options": [
        #       {"nom": "SEO Build", "description": "audit + plan...",
        #        "tarif": 2000, "unite": "forfait initial"},
        #       {"nom": "SEO Run",   "description": "production + netlinking",
        #        "tarif": 850,  "unite": "/ mois (12 mois)"}
        #     ],
        #     "footer": "phrase de conclusion (optionnel)"
        #   }
        # }
        opt_seo = d.get("options_seo")
        if opt_seo:
            sections.append(Section("pagebreak"))
            sections.append(Section("h1",
                opt_seo.get("titre", "Options SEO disponibles")))
            if opt_seo.get("preambule"):
                for para in opt_seo["preambule"].split("\n\n"):
                    if para.strip():
                        sections.append(Section("p", _md(para)))
            sections.append(Section("spacer", height=8))
            sections.append(Section("options_seo_table",
                data={"options": opt_seo["options"]}))
            if opt_seo.get("footer"):
                sections.append(Section("spacer", height=10))
                for para in opt_seo["footer"].split("\n\n"):
                    if para.strip():
                        sections.append(Section("p", _md(para)))

        first_jalon = jalons[0] if jalons else None
        acompte_txt = ""
        if first_jalon:
            acompte_txt = (f"Un acompte de <b>{first_jalon['pourcentage']}\u00a0% — "
                           f"{_fmt_eur(first_jalon['montant'])} HT</b> sera appelé "
                           f"à réception du devis signé.")
        sections.append(Section("pagebreak"))
        sections.append(Section("h1", "Bon pour accord"))
        sections.append(Section("p",
            "La signature du présent devis vaut <b>acceptation pleine et "
            "entière</b> du périmètre de la mission, de la répartition "
            "budgétaire et des Conditions Générales de Vente figurant en "
            f"annexe. {acompte_txt}"))
        sections.append(Section("spacer", height=20))
        sections.append(Section("signature"))
        sections.extend(_default_cgv_sections())

        return cls(
            devis_no=meta["devis_no"],
            date_creation=meta["date_creation"],
            client=client, sections=sections, contact=contact,
            emetteur=emetteur,
            assets_dir=assets_dir or Path(__file__).parent,
        )

    # ─── Rendu PDF ─────────────────────────────────────────────────────────
    def render(self, out_path: str | Path) -> Path:
        out_path = Path(out_path)
        register_fonts()
        styles = make_styles()

        c = canvas.Canvas(str(out_path), pagesize=(PAGE_W, PAGE_H))

        # ─── Page 1 : garde ───
        self._draw_background(c, "Page_de_garde.png")
        c.showPage()

        # ─── Page 2 : première page (header + objet mission) ───
        self._draw_background(c, "Premie_re_page.png")
        self._draw_first_page_header(c)
        c.showPage()

        # ─── Pages 3+ : contenu paginé via Frame ───
        margin_lat = px_size(184)
        top_px = 640
        bot_px = 6900
        top_pt = PAGE_H - (top_px / PNG_H) * PAGE_H
        bot_pt = PAGE_H - (bot_px / PNG_H) * PAGE_H

        x_frame = margin_lat
        w_frame = PAGE_W - 2 * margin_lat
        h_frame = top_pt - bot_pt

        def new_page():
            self._draw_background(c, "Page_classique.png")
            return Frame(x_frame, bot_pt, w_frame, h_frame,
                         leftPadding=0, rightPadding=0,
                         topPadding=0, bottomPadding=0, showBoundary=0)

        frame = new_page()
        flowables = self._build_flowables(styles)

        i = 0
        while i < len(flowables):
            f = flowables[i]
            if f is None:  # pagebreak signal
                c.showPage()
                frame = new_page()
                i += 1
                continue
            try:
                added = frame.add(f, c)
            except Exception as e:
                print(f"[WARN] flowable add failed: {e}", file=sys.stderr)
                added = True
            if added:
                i += 1
            else:
                # Page pleine, on bascule
                c.showPage()
                frame = new_page()

        c.save()
        return out_path

    # ─── Helpers de rendu ──────────────────────────────────────────────────
    def _draw_background(self, c: canvas.Canvas, asset_name: str) -> None:
        p = self.assets_dir / asset_name
        if p.exists():
            c.drawImage(str(p), 0, 0, width=PAGE_W, height=PAGE_H,
                        preserveAspectRatio=False, mask="auto")

    def _draw_first_page_header(self, c: canvas.Canvas) -> None:
        """Dessine sur la page 2 uniquement les **champs dynamiques** par-dessus
        le PNG `Premie_re_page.png`, dont les labels, le contact ESW et l'émetteur
        sont déjà gravés en dur dans l'image.

        Champs à superposer :
          - N° de devis (à droite de « DEVIS No » gravé)
          - Date de création (à droite de « Date de création » gravée)
          - Nom du client (sous « A l'attention de : » gravé)
          - Adresse client lignes 1 et 2
        Le contact ESW et le bloc émetteur sont gravés dans le PNG → on n'écrit
        rien dessus.

        Coordonnées calibrées en px sur le PNG natif 4790×7200, au baseline
        ReportLab. Mesurées par analyse colorimétrique du PNG :
          - Label « DEVIS No » : y baseline ≈ 1945 px (haut du glyphe ≈ 1903)
          - Label « Date de création » : y baseline ≈ 2045 px
          - Label « A l'attention de : » : y baseline ≈ 1945 px (x ≈ 2100 px)
          - Interligne typo gravée ≈ 110 px PNG (≈ 13.6 pt PDF)
        """
        register_fonts()
        FS = 10  # taille de police pour matcher la typo gravée du PNG
        LH_PX = 110  # interligne en px PNG entre deux lignes gravées

        c.setFont(FONT_REG, FS)
        c.setFillColor(COL_INK)

        # ── Colonne gauche : N° devis et date, à droite des labels gravés
        # Labels mesurés sur le PNG :
        #   « DEVIS No »          se termine à x=563  → valeur à x=620
        #   « Date de création »  se termine à x=828  → valeur à x=885
        x_devis_value, y_devis = px_to_pdf(620, 1945)
        c.drawString(x_devis_value, y_devis, str(self.devis_no))

        x_date_value, y_date = px_to_pdf(885, 1945 + LH_PX)
        c.drawString(x_date_value, y_date, str(self.date_creation))

        # ── Colonne centre : nom + adresse client, SOUS le label gravé
        # « A l'attention de : » commence à x=1725 px (mesuré), y≈1945
        x_client, _ = px_to_pdf(1725, 0)
        _, y_client_l1 = px_to_pdf(0, 1945 + LH_PX)
        _, y_client_l2 = px_to_pdf(0, 1945 + 2 * LH_PX)
        _, y_client_l3 = px_to_pdf(0, 1945 + 3 * LH_PX)

        c.drawString(x_client, y_client_l1, self.client.nom)
        if self.client.adresse_l1 and self.client.adresse_l1.strip() not in ("", "À préciser"):
            c.drawString(x_client, y_client_l2, self.client.adresse_l1)
            if self.client.adresse_l2:
                c.drawString(x_client, y_client_l3, self.client.adresse_l2)

    def _draw_roi_page(self, c: canvas.Canvas, data: dict) -> None:
        """Dessine une page paysage de projection ROI avec le PNG en arrière-plan
        et les valeurs (paramètres d'entrées + 4 scénarios) dessinées par-dessus.

        Coordonnées calibrées par OCR sur le PNG `Projection_ROI.png` (8000×4500 px).

        data attendu :
          {
            "panier_moyen": 10000,
            "taux_conversion": 1.5,
            "taux_closing": 10,
            "investissement_mensuel": 248,
            "point_equilibre_mois": 6,
            "profil": "btob_premium"
          }
        """
        # ─── Calcul des scénarios ───
        panier = float(data["panier_moyen"])
        tc_pct = float(data["taux_conversion"])
        closing_pct = float(data["taux_closing"])
        invest = float(data["investissement_mensuel"])
        eq_mois = data.get("point_equilibre_mois", "—")
        profil = data.get("profil", "btob_premium")

        scenarios = compute_roi_scenarios(panier, tc_pct, closing_pct,
                                          invest, profil)

        # ─── Switch en mode paysage ───
        c.setPageSize((ROI_PAGE_W, ROI_PAGE_H))

        # ─── Background : le PNG de la diapo ROI ───
        p = self.assets_dir / "Projection_ROI.png"
        if p.exists():
            c.drawImage(str(p), 0, 0, width=ROI_PAGE_W, height=ROI_PAGE_H,
                        preserveAspectRatio=False, mask="auto")

        # ─── Helpers de format ───
        def fmt_num(x: float, force_decimal: bool = False) -> str:
            """Formate un nombre à la française (séparateur d'espace, virgule décimale)."""
            if not force_decimal and abs(x - round(x)) < 0.005:
                # Entier
                return f"{int(round(x)):,}".replace(",", " ")
            # Décimal (1 ou 2 décimales selon la valeur)
            if abs(x) >= 10:
                s = f"{x:,.1f}".replace(",", " ").replace(".", ",")
            else:
                s = f"{x:,.2f}".replace(",", " ").replace(".", ",")
            return s

        def fmt_eur(x: float) -> str:
            return f"{int(round(x)):,}".replace(",", " ")

        # ─── Paramètres d'entrées (ligne y ~ 1062 px, baselines des labels gravés) ───
        # Les libellés "Panier moyen :", "Investissement mensuel :", "Point d'équilibre :"
        # sont déjà gravés dans le PNG. On ajoute la valeur juste après.
        font_size_param = roi_px_size(80)
        c.setFillColor(COL_WHITE)
        c.setFont(FONT_REG, font_size_param)

        # baseline_y_px : y de la baseline du texte (les labels finissent à y_baseline)
        baseline_y_px = 1062 + 80  # +80 pour passer du top vers la baseline

        # Panier moyen → valeur démarre après "Panier moyen :" (fini vers x=3030)
        x_pt, y_pt = roi_px_to_pdf(3100, baseline_y_px)
        c.drawString(x_pt, y_pt, f"{fmt_eur(panier)} \u20ac")

        # Investissement mensuel → après "Investissement mensuel :" (fini vers x=4820)
        x_pt, y_pt = roi_px_to_pdf(4900, baseline_y_px)
        c.drawString(x_pt, y_pt, f"{fmt_eur(invest)} \u20ac")

        # Point d'équilibre → après "Point d'équilibre :" (fini vers x=6365)
        x_pt, y_pt = roi_px_to_pdf(6450, baseline_y_px)
        eq_str = f"{eq_mois}ème mois" if isinstance(eq_mois, int) else str(eq_mois)
        c.drawString(x_pt, y_pt, eq_str)

        # ─── Tableau des scénarios ───
        # y des lignes (baseline du texte) ; libellés gravés à ces y
        row_ys_px = [2010, 2543, 3076, 3614]
        # Centres x des colonnes T/m, tc, V/m, CA/m, ROI/m
        col_xs_px = [2434, 3262, 4227, 5190, 6234]

        font_size_val = roi_px_size(90)
        c.setFont(FONT_REG, font_size_val)

        for y_px, sc in zip(row_ys_px, scenarios):
            values = [
                fmt_num(sc["tm"]),                         # T/m
                f"{fmt_num(sc['tc_pct'], force_decimal=True)}%",  # tc
                fmt_num(sc["vm"], force_decimal=True),     # V/m
                fmt_num(sc["cam"]),                        # CA/m
                fmt_num(sc["roi"], force_decimal=True),    # ROI/m
            ]
            for x_px, val in zip(col_xs_px, values):
                # On centre la valeur sur le x de la colonne (comme l'image originale)
                w = c.stringWidth(val, FONT_REG, font_size_val)
                x_pt, y_pt = roi_px_to_pdf(x_px, y_px + 80)
                c.drawString(x_pt - w / 2, y_pt, val)

        # ─── Reset des couleurs et fin de page ───
        c.setFillColor(COL_INK)
        c.showPage()

        # ─── Restaurer le format portrait pour les pages suivantes ───
        c.setPageSize((PAGE_W, PAGE_H))

    def _build_flowables(self, styles: dict) -> list:
        """Convertit les Section en flowables ReportLab."""
        out = []
        for s in self.sections:
            if s.kind == "spacer":
                out.append(Spacer(1, s.height))
                continue
            if s.kind == "pagebreak":
                out.append(None)  # signal de pagebreak
                continue
            if s.kind == "h1":
                out.append(Paragraph(s.text, styles["h1"]))
                continue
            if s.kind == "h2":
                out.append(Paragraph(s.text, styles["h2"]))
                continue
            if s.kind == "h3":
                out.append(Paragraph(s.text, styles["h3"]))
                continue
            if s.kind == "p":
                out.append(Paragraph(s.text, styles["body"]))
                continue
            if s.kind == "bullet":
                out.append(Paragraph("•&nbsp;&nbsp;" + s.text, styles["bullet"]))
                continue
            if s.kind == "module":
                # Compatibilité ascendante : data peut être soit la liste d'items
                # (ancien format), soit un dict {"items": [...], "offert": bool}
                if isinstance(s.data, dict):
                    out.append(self._build_module_table(
                        s.text, s.data["items"],
                        offert=s.data.get("offert", False)))
                else:
                    out.append(self._build_module_table(s.text, s.data))
                continue
            if s.kind == "module_total":
                out.append(self._build_grand_total(s.data))
                continue
            if s.kind == "recap_table":
                out.append(self._build_recap_table(s.data))
                continue
            if s.kind == "partenariat_valeur_table":
                out.append(self._build_partenariat_valeur_table(s.data))
                continue
            if s.kind == "partenariat_sla_table":
                out.append(self._build_partenariat_sla_table(s.data))
                continue
            if s.kind == "options_table":
                out.append(self._build_options_table(s.data))
                continue
            if s.kind == "extension_table":
                out.append(self._build_extension_table(s.data))
                continue
            if s.kind == "options_seo_table":
                out.append(self._build_options_seo_table(s.data))
                continue
            if s.kind == "roi_table":
                out.append(self._build_roi_inline_table(s.data))
                continue
            if s.kind == "signature":
                out.append(self._build_signature_block())
                continue
        return out

    def _build_module_table(self, titre: str, items: list[tuple[str, float]],
                            offert: bool = False) -> Table:
        """Tableau d'un module : entête noir + lignes + sous-total.

        Si `offert=True`, ajoute une ligne « Remise commerciale » qui annule
        le sous-total, et le sous-total final affiche « OFFERT » avec la
        valeur initiale barrée — utile pour mettre en avant un geste
        commercial tout en montrant la valeur réelle du travail.
        """
        tjm = 100  # TJM par défaut, surchargeable
        header_style = ParagraphStyle("mh", fontName=FONT_BOLD, fontSize=10,
            leading=14, textColor=COL_WHITE, alignment=TA_LEFT)
        subheader_style = ParagraphStyle("msh", fontName=FONT_BOLD, fontSize=9,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        cell_style = ParagraphStyle("mc", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        h_style = ParagraphStyle("mh2", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_CENTER)
        eur_style = ParagraphStyle("me", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_RIGHT)
        total_style = ParagraphStyle("mt", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        # Styles spécifiques à un module offert
        offert_label_style = ParagraphStyle("ml", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_ACCENT_ORANGE, alignment=TA_LEFT)
        offert_eur_style = ParagraphStyle("moe", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_ACCENT_ORANGE, alignment=TA_RIGHT)

        rows = [[Paragraph(titre, header_style), "", ""]]
        rows.append([
            Paragraph("Fonctionnalité", subheader_style),
            Paragraph("Heures", subheader_style),
            Paragraph("Coût HT", subheader_style),
        ])
        total_h = 0
        for nom, h in items:
            rows.append([
                Paragraph(_md(nom), cell_style),
                Paragraph(_fmt_h(h), h_style),
                Paragraph(_fmt_eur(h * tjm), eur_style),
            ])
            total_h += h

        montant_initial = total_h * tjm
        if offert:
            # Ligne intermédiaire « Remise commerciale »
            rows.append([
                Paragraph("<i>Remise commerciale — geste commercial inclus</i>",
                          cell_style),
                Paragraph("—", h_style),
                Paragraph(f"<i>− {_fmt_eur(montant_initial)}</i>", eur_style),
            ])
            # Sous-total « OFFERT (valorisé X € HT) »
            rows.append([
                Paragraph(f"<b>Sous-total — {_md(titre)}</b>", offert_label_style),
                Paragraph(f"<b>{_fmt_h(total_h)}</b>", h_style),
                Paragraph(f"<b>OFFERT</b> "
                          f"<font size=8 color='#888888'>"
                          f"(valorisé {_fmt_eur(montant_initial)} HT)</font>",
                          offert_eur_style),
            ])
        else:
            rows.append([
                Paragraph(f"<b>Sous-total — {_md(titre)}</b>", total_style),
                Paragraph(f"<b>{_fmt_h(total_h)}</b>", h_style),
                Paragraph(f"<b>{_fmt_eur(montant_initial)}</b>", eur_style),
            ])

        col_w = [549 * 0.62, 549 * 0.18, 549 * 0.20]
        t = Table(rows, colWidths=col_w)
        # Background du sous-total final : jaune doux si offert, sinon gris léger
        last_bg = COL_BG_YELLOW if offert else COL_BG_LIGHT
        ts = [
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), COL_INK),
            ("BACKGROUND", (0, -1), (-1, -1), last_bg),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 1), (-1, 1), 0.3, COL_LIGHT_GREY),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, COL_INK),
        ]
        if offert:
            # Barre orange à gauche pour attirer l'œil sur le geste commercial
            ts.append(("LINEBEFORE", (0, -1), (0, -1), 3, COL_ACCENT_ORANGE))
        t.setStyle(TableStyle(ts))
        return t

    def _build_grand_total(self, data: list) -> Table:
        """Ligne 'Total général de la prestation' en pleine largeur."""
        label, h, amt = data[0]
        rows = [[
            Paragraph(f"<b>{label}</b>", ParagraphStyle("gtl",
                fontName=FONT_BOLD, fontSize=14, leading=18,
                textColor=COL_WHITE, alignment=TA_LEFT)),
            Paragraph(f"<b>{_fmt_h(h)}</b>", ParagraphStyle("gth",
                fontName=FONT_BOLD, fontSize=14, leading=18,
                textColor=COL_WHITE, alignment=TA_CENTER)),
            Paragraph(f"<b>{_fmt_eur(amt)}</b>", ParagraphStyle("gte",
                fontName=FONT_BOLD, fontSize=14, leading=18,
                textColor=COL_WHITE, alignment=TA_RIGHT)),
        ]]
        col_w = [549 * 0.62, 549 * 0.18, 549 * 0.20]
        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COL_INK),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def _build_recap_table(self, data: list) -> Table:
        """Tableau récap financier (cas partenariat).
        Lignes : valeur dev / remise (italique) / OFFERT (jaune) / TOTAL (noir).
        """
        label_style = ParagraphStyle("rl", fontName=FONT_REG, fontSize=10,
            leading=14, textColor=COL_INK, alignment=TA_LEFT)
        val_style = ParagraphStyle("rv", fontName=FONT_REG, fontSize=10,
            leading=14, textColor=COL_INK, alignment=TA_RIGHT)

        # Détecter les lignes spéciales par le contenu
        rows = []
        for lbl, val in data:
            rows.append([Paragraph(lbl, label_style), Paragraph(val, val_style)])

        col_w = [549 * 0.62, 549 * 0.38]
        t = Table(rows, colWidths=col_w)
        ts_cmds = [
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, COL_LIGHT_GREY),
        ]
        # Repérer les lignes totales et offertes pour stylage
        for i, (lbl, val) in enumerate(data):
            if "TOTAL FORFAIT INITIAL" in lbl or "TOTAL TTC" in lbl:
                ts_cmds.append(("BACKGROUND", (0, i), (-1, i), COL_INK))
            elif "OFFERT" in val:
                ts_cmds.append(("BACKGROUND", (0, i), (-1, i), COL_BG_YELLOW))

        # Reconstruire les paragraphes pour les lignes noires
        for i, (lbl, val) in enumerate(data):
            if "TOTAL FORFAIT INITIAL" in lbl or "TOTAL TTC" in lbl:
                white_l = ParagraphStyle("rlw", parent=label_style,
                    textColor=COL_WHITE, fontName=FONT_BOLD)
                white_r = ParagraphStyle("rvw", parent=val_style,
                    textColor=COL_WHITE, fontName=FONT_BOLD)
                rows[i] = [Paragraph(lbl, white_l), Paragraph(val, white_r)]
        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle(ts_cmds))
        return t

    def _build_partenariat_valeur_table(self, data: list) -> Table:
        """Tableau « Tout ce que nous vous offrons » — fond jaune + barre orange,
        avec ligne totale en bandeau noir."""
        label_style = ParagraphStyle("pvl", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        val_style = ParagraphStyle("pvv", fontName=FONT_BOLD, fontSize=10,
            leading=13, textColor=COL_INK, alignment=TA_RIGHT)
        rows = []
        for lbl, val in data:
            if "VALEUR TOTALE" in lbl:
                rows.append([
                    Paragraph(lbl, ParagraphStyle("pvlt", parent=label_style,
                        textColor=COL_WHITE, fontName=FONT_BOLD, fontSize=11)),
                    Paragraph(val, ParagraphStyle("pvvt", parent=val_style,
                        textColor=COL_WHITE, fontSize=12)),
                ])
            else:
                rows.append([Paragraph(lbl, label_style), Paragraph(val, val_style)])
        col_w = [549 * 0.68, 549 * 0.32]
        t = Table(rows, colWidths=col_w)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -2), COL_BG_YELLOW),
            ("BACKGROUND", (0, -1), (-1, -1), COL_INK),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEABOVE", (0, 0), (-1, 0), 1, COL_ACCENT_ORANGE),
            ("LINEBELOW", (0, -2), (-1, -2), 0.5, COL_ACCENT_ORANGE),
            ("LINEBEFORE", (0, 0), (0, -2), 3, COL_ACCENT_ORANGE),
        ]))
        return t

    def _build_partenariat_sla_table(self, data: list) -> Table:
        """Tableau SLA Zéro Bug : 3 colonnes (Type / Description / Délai)."""
        header_style = ParagraphStyle("slh", fontName=FONT_BOLD, fontSize=10,
            leading=13, textColor=COL_WHITE, alignment=TA_LEFT)
        type_style = ParagraphStyle("slt", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        body_style = ParagraphStyle("slb", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        delay_style = ParagraphStyle("sld", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_RED_DARK, alignment=TA_LEFT)
        rows = [[
            Paragraph("Type d'incident", header_style),
            Paragraph("Description", header_style),
            Paragraph("Temps de réaction", header_style),
        ]]
        for type_, desc, delai in data:
            rows.append([
                Paragraph(type_, type_style),
                Paragraph(desc, body_style),
                Paragraph(delai, delay_style),
            ])
        col_w = [549 * 0.18, 549 * 0.52, 549 * 0.30]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COL_INK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
            ("TOPPADDING", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [COL_WHITE, COL_BG_LIGHT]),
        ]))
        return t

    def _build_options_table(self, data: dict) -> Table:
        """Tableau comparatif V1/V2 ou V1/V2/V3 (2 ou 3 colonnes côte à côte).

        Si v3 est présent, on rend 3 colonnes ; sinon, on rend 2 colonnes.
        Un pack peut porter `highlight: true` pour être mis en valeur visuellement
        (fond doré clair).
        """
        v1 = data["v1"]
        v2 = data["v2"]
        v3 = data.get("v3")  # optionnel
        has_v3 = v3 is not None

        header_label = ParagraphStyle("ohl", fontName=FONT_BOLD, fontSize=11,
            leading=15, textColor=COL_WHITE, alignment=TA_LEFT)
        header_price = ParagraphStyle("ohp", fontName=FONT_BOLD, fontSize=14,
            leading=18, textColor=COL_WHITE, alignment=TA_LEFT)
        header_duree = ParagraphStyle("ohd", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_WHITE, alignment=TA_LEFT)
        header_saving = ParagraphStyle("ohs", fontName=FONT_BOLD, fontSize=9,
            leading=12, textColor=COL_ACCENT_ORANGE, alignment=TA_LEFT,
            backColor=COL_WHITE, borderPadding=3)
        section_label = ParagraphStyle("osl", fontName=FONT_BOLD, fontSize=10,
            leading=14, textColor=COL_INK, alignment=TA_LEFT)
        item_style = ParagraphStyle("oi", fontName=FONT_REG, fontSize=9,
            leading=12, textColor=COL_INK, alignment=TA_LEFT, spaceAfter=2)
        excl_style = ParagraphStyle("oe", fontName=FONT_REG, fontSize=9,
            leading=12, textColor=HexColor("#888888"), alignment=TA_LEFT,
            spaceAfter=2)

        def _opt_header(opt: dict) -> list:
            block = [
                Paragraph(opt.get("code", ""), header_label),
                Paragraph(opt.get("titre", ""), header_label),
                Spacer(1, 4),
                Paragraph(f"{_fmt_eur(opt.get('prix', 0))} HT", header_price),
            ]
            duree = opt.get("duree", "")
            heures = opt.get("heures", 0)
            if duree and heures:
                block.append(Paragraph(f"{duree} · {heures}\u00a0h", header_duree))
            elif duree:
                block.append(Paragraph(duree, header_duree))
            # Pastille "saving" pour mettre en avant la remise
            if opt.get("saving"):
                block.append(Spacer(1, 4))
                block.append(Paragraph(opt["saving"], header_saving))
            return block

        def _opt_body(opt: dict) -> list:
            body = [Spacer(1, 4), Paragraph("<b>Inclus</b>", section_label),
                    Spacer(1, 3)]
            for it in opt.get("inclus", []):
                body.append(Paragraph(f"✓\u00a0&nbsp;{_md(it)}", item_style))
            excl = opt.get("exclus", [])
            if excl:
                body.append(Spacer(1, 6))
                body.append(Paragraph("<b>Non inclus dans cette option</b>",
                    section_label))
                body.append(Spacer(1, 3))
                for it in excl:
                    body.append(Paragraph(f"·\u00a0&nbsp;{_md(it)}", excl_style))
            return body

        if has_v3:
            rows = [
                [_opt_header(v1), _opt_header(v2), _opt_header(v3)],
                [_opt_body(v1), _opt_body(v2), _opt_body(v3)],
            ]
            col_w = [549 * 0.333, 549 * 0.333, 549 * 0.334]
        else:
            rows = [
                [_opt_header(v1), _opt_header(v2)],
                [_opt_body(v1), _opt_body(v2)],
            ]
            col_w = [549 * 0.5, 549 * 0.5]

        t = Table(rows, colWidths=col_w)

        style = [
            ("BACKGROUND", (0, 0), (-1, 0), COL_INK),
            ("LEFTPADDING", (0, 0), (-1, 0), 12),
            ("RIGHTPADDING", (0, 0), (-1, 0), 12),
            ("TOPPADDING", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("VALIGN", (0, 0), (-1, 0), "TOP"),
            ("LEFTPADDING", (0, 1), (-1, 1), 12),
            ("RIGHTPADDING", (0, 1), (-1, 1), 12),
            ("TOPPADDING", (0, 1), (-1, 1), 12),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
            ("VALIGN", (0, 1), (-1, 1), "TOP"),
            ("LINEAFTER", (0, 0), (0, -1), 1, COL_WHITE),
        ]

        if has_v3:
            # Coloration de fond du body :
            # - V1 : fond gris clair
            # - V2 : fond gris clair
            # - V3 : fond jaune (mise en valeur si highlight, sinon orange)
            style.append(("BACKGROUND", (0, 1), (0, 1), COL_BG_LIGHT))
            style.append(("BACKGROUND", (1, 1), (1, 1), COL_BG_LIGHT))
            if v3.get("highlight"):
                style.append(("BACKGROUND", (2, 1), (2, 1), COL_BG_YELLOW))
                style.append(("LINEBEFORE", (2, 0), (2, -1), 3,
                              COL_ACCENT_ORANGE))
            else:
                style.append(("BACKGROUND", (2, 1), (2, 1), COL_BG_LIGHT))
            style.append(("LINEAFTER", (1, 0), (1, -1), 1, COL_WHITE))
        else:
            style.append(("BACKGROUND", (0, 1), (0, 1), COL_BG_LIGHT))
            style.append(("BACKGROUND", (1, 1), (1, 1), COL_BG_YELLOW))
            style.append(("LINEBEFORE", (1, 0), (1, -1), 3, COL_ACCENT_ORANGE))

        t.setStyle(TableStyle(style))
        return t

    def _build_extension_table(self, data: dict) -> Table:
        """Tableau dégressif pour l'extension de la prestation à plusieurs sites.

        data attendu :
          {
            "grille": [
              {"nb_sites": 1, "remise_pct": 0, "prix_par_site_an": 12400,
               "total_an": 12400, "economie_an": 0},
              ...
            ],
            "base": 12400   # optionnel, pour mention en sous-titre
          }

        Colonnes : Nombre de sites | Remise/site | Prix/site/an | Total annuel | Économie
        Ligne mise en évidence orange clair pour la ligne « la plus avantageuse »
        (= dernière ligne avec remise non plafonnée, ou ligne la plus grande
        économie en valeur absolue).
        """
        grille = data["grille"]

        # ─── Styles ───
        header_style = ParagraphStyle("eth", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_WHITE, alignment=TA_CENTER)
        cell_nb = ParagraphStyle("etn", fontName=FONT_BOLD, fontSize=10,
            leading=13, textColor=COL_INK, alignment=TA_CENTER)
        cell_c = ParagraphStyle("etc", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_CENTER)
        cell_eur = ParagraphStyle("ete", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_RIGHT)
        cell_eco = ParagraphStyle("etec", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_RED_DARK, alignment=TA_RIGHT)
        cell_eco_zero = ParagraphStyle("etez", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_GREY, alignment=TA_RIGHT)

        # ─── Construction des lignes ───
        rows = [[
            Paragraph("Nombre de sites", header_style),
            Paragraph("Remise par site", header_style),
            Paragraph("Prix par site / an", header_style),
            Paragraph("Total annuel HT", header_style),
            Paragraph("Économie annuelle", header_style),
        ]]
        for g in grille:
            n = g["nb_sites"]
            pct = g["remise_pct"]
            prix = g["prix_par_site_an"]
            total = g["total_an"]
            eco = g.get("economie_an", 0)
            rows.append([
                Paragraph(f"{n}\u00a0site{'s' if n > 1 else ''}", cell_nb),
                Paragraph(f"−\u00a0{pct}\u202f%" if pct else "—", cell_c),
                Paragraph(_fmt_eur(prix) + "\u00a0HT", cell_eur),
                Paragraph("<b>" + _fmt_eur(total) + "\u00a0HT</b>", cell_eur),
                Paragraph("−\u00a0" + _fmt_eur(eco) + "\u00a0HT"
                          if eco else "—",
                          cell_eco if eco else cell_eco_zero),
            ])

        # ─── Largeurs et style ───
        col_w = [549 * 0.16, 549 * 0.16, 549 * 0.21, 549 * 0.23, 549 * 0.24]
        t = Table(rows, colWidths=col_w, repeatRows=1)

        # Style de base
        ts = [
            ("BACKGROUND", (0, 0), (-1, 0), COL_INK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, COL_INK),
        ]
        # Lignes alternées blanc / gris clair pour la lisibilité
        for i in range(1, len(rows)):
            if i % 2 == 0:
                ts.append(("BACKGROUND", (0, i), (-1, i), COL_BG_LIGHT))
            ts.append(("LINEBELOW", (0, i), (-1, i), 0.25, COL_LIGHT_GREY))

        # Mise en évidence : ligne avec la plus grande économie
        # (généralement la dernière, mais on calcule pour être robuste)
        max_eco_idx = max(range(len(grille)),
                          key=lambda i: grille[i].get("economie_an", 0))
        hl_row = max_eco_idx + 1  # +1 pour le header
        ts.append(("BACKGROUND", (0, hl_row), (-1, hl_row), COL_BG_YELLOW))
        ts.append(("LINEBEFORE", (0, hl_row), (0, hl_row), 3, COL_ACCENT_ORANGE))

        t.setStyle(TableStyle(ts))
        return t

    def _build_options_seo_table(self, data: dict) -> Table:
        """Tableau simple Option / Description / Tarif pour proposer des
        prestations complémentaires (SEO Build, SEO Run...) activables à la
        signature, sans les inclure dans le total général.

        data attendu :
          {
            "options": [
              {"nom": "SEO Build",
               "description": "audit + étude + plan d'action 12 mois",
               "tarif": 2000,
               "unite": "forfait initial"},
              {"nom": "SEO Run",
               "description": "production éditoriale + netlinking + reporting",
               "tarif": 850,
               "unite": "/ mois (engagement 12 mois)"}
            ]
          }

        Chaque ligne affiche une case à cocher dessinée pour indiquer que
        l'option est à activer au moment de la signature.
        """
        from reportlab.graphics.shapes import Drawing, Rect
        options = data["options"]

        # ─── Styles ───
        header_style = ParagraphStyle("oh", fontName=FONT_BOLD, fontSize=10,
            leading=14, textColor=COL_WHITE, alignment=TA_LEFT)
        nom_style = ParagraphStyle("on", fontName=FONT_BOLD, fontSize=10.5,
            leading=14, textColor=COL_INK, alignment=TA_LEFT)
        desc_style = ParagraphStyle("od", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        tarif_style = ParagraphStyle("ot", fontName=FONT_BOLD, fontSize=11,
            leading=14, textColor=COL_ACCENT_ORANGE, alignment=TA_RIGHT)
        unite_style = ParagraphStyle("ou", fontName=FONT_REG, fontSize=8.5,
            leading=11, textColor=COL_GREY, alignment=TA_RIGHT)

        def make_checkbox() -> Drawing:
            """Petit carré vide 14×14 pt, bordure noire fine."""
            d = Drawing(14, 14)
            d.add(Rect(0, 0, 14, 14, strokeColor=COL_INK,
                       strokeWidth=1, fillColor=None))
            return d

        # ─── Lignes ───
        rows = [[
            "",
            Paragraph("Option", header_style),
            Paragraph("Tarif", header_style),
        ]]
        for opt in options:
            tarif_html = f"<b>{_fmt_eur(opt['tarif'])} HT</b>"
            unite_html = opt.get("unite", "")
            tarif_block = (Paragraph(tarif_html, tarif_style) if not unite_html
                           else [Paragraph(tarif_html, tarif_style),
                                 Paragraph(unite_html, unite_style)])
            nom_block = [Paragraph(_md(opt["nom"]), nom_style)]
            if opt.get("description"):
                nom_block.append(Paragraph(_md(opt["description"]), desc_style))

            rows.append([
                make_checkbox(),
                nom_block,
                tarif_block,
            ])

        col_w = [549 * 0.08, 549 * 0.62, 549 * 0.30]
        t = Table(rows, colWidths=col_w, repeatRows=1)

        ts = [
            ("BACKGROUND", (0, 0), (-1, 0), COL_INK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, COL_INK),
        ]
        # Lignes alternées + filet de séparation + barre orange à gauche
        for i in range(1, len(rows)):
            if i % 2 == 0:
                ts.append(("BACKGROUND", (0, i), (-1, i), COL_BG_LIGHT))
            ts.append(("LINEBELOW", (0, i), (-1, i), 0.25, COL_LIGHT_GREY))
            ts.append(("LINEBEFORE", (0, i), (0, i), 3, COL_ACCENT_ORANGE))

        t.setStyle(TableStyle(ts))
        return t

    def _build_roi_inline_table(self, data: dict) -> Table:
        """Mini-tableau inline de projection ROI pour la lettre de mission.

        data : {"scenarios": [{"label", "tm", "tc_pct", "vm", "cam", "roi"}]}

        Colonnes : Scénario | T/m | tc | V/m | CA/m | ROI/m
        Style : cohérent avec les autres tableaux noirs du devis.
        Ligne "Réaliste (Objectif)" mise en évidence (background jaune + barre orange).
        """
        scenarios = data["scenarios"]

        # ─── Helpers de format (réutilisés depuis _draw_roi_page) ───
        def fmt_num(x: float, force_decimal: bool = False) -> str:
            if not force_decimal and abs(x - round(x)) < 0.005:
                return f"{int(round(x)):,}".replace(",", " ")
            if abs(x) >= 10:
                s = f"{x:,.1f}".replace(",", " ").replace(".", ",")
            else:
                s = f"{x:,.2f}".replace(",", " ").replace(".", ",")
            return s

        def fmt_eur(x: float) -> str:
            return f"{int(round(x)):,}".replace(",", " ") + "\u00a0€"

        # ─── Styles ───
        header_style = ParagraphStyle("rh", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_WHITE, alignment=TA_CENTER)
        label_style = ParagraphStyle("rl", fontName=FONT_BOLD, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        cell_c = ParagraphStyle("rc", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_CENTER)
        cell_r = ParagraphStyle("rr", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_RIGHT)

        rows = [[
            Paragraph("Scénario de croissance", header_style),
            Paragraph("T/m", header_style),
            Paragraph("tc", header_style),
            Paragraph("V/m", header_style),
            Paragraph("CA/m", header_style),
            Paragraph("ROI/m", header_style),
        ]]
        # Identifier l'index "Réaliste (Objectif)" pour le mettre en évidence
        objectif_idx = None
        for sc in scenarios:
            if "Réaliste" in sc.get("label", ""):
                objectif_idx = scenarios.index(sc)
                break

        for sc in scenarios:
            rows.append([
                Paragraph(_md(sc["label"]), label_style),
                Paragraph(fmt_num(sc["tm"]), cell_c),
                Paragraph(f"{fmt_num(sc['tc_pct'], force_decimal=True)}\u202f%", cell_c),
                Paragraph(fmt_num(sc["vm"], force_decimal=True), cell_c),
                Paragraph(fmt_eur(sc["cam"]), cell_r),
                Paragraph(fmt_num(sc["roi"], force_decimal=True), cell_c),
            ])

        col_w = [549 * 0.30, 549 * 0.10, 549 * 0.10, 549 * 0.12, 549 * 0.20, 549 * 0.18]
        t = Table(rows, colWidths=col_w, repeatRows=1)

        ts = [
            ("BACKGROUND", (0, 0), (-1, 0), COL_INK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, COL_INK),
        ]
        # Alternance des lignes
        for i in range(1, len(rows)):
            if i % 2 == 0:
                ts.append(("BACKGROUND", (0, i), (-1, i), COL_BG_LIGHT))
            ts.append(("LINEBELOW", (0, i), (-1, i), 0.25, COL_LIGHT_GREY))

        # Mise en évidence du scénario "Réaliste (Objectif)"
        if objectif_idx is not None:
            hl = objectif_idx + 1  # +1 pour le header
            ts.append(("BACKGROUND", (0, hl), (-1, hl), COL_BG_YELLOW))
            ts.append(("LINEBEFORE", (0, hl), (0, hl), 3, COL_ACCENT_ORANGE))

        t.setStyle(TableStyle(ts))
        return t

    def _build_signature_block(self) -> Table:
        """Bloc signature 2 colonnes : Prestataire / Client."""
        bold_style = ParagraphStyle("sb", fontName=FONT_BOLD, fontSize=10,
            leading=14, textColor=COL_INK, alignment=TA_LEFT)
        body_style = ParagraphStyle("sb2", fontName=FONT_REG, fontSize=9.5,
            leading=13, textColor=COL_INK, alignment=TA_LEFT)
        italic_style = ParagraphStyle("si", fontName=FONT_ITALIC, fontSize=9,
            leading=12, textColor=COL_GREY, alignment=TA_LEFT)

        left_col = [
            Paragraph("<b>Pour le Prestataire</b>", bold_style),
            Spacer(1, 8),
            Paragraph(f"<b>{self.emetteur.nom}</b>", body_style),
            Paragraph(self.emetteur.adresse_l1, body_style),
            Paragraph(self.emetteur.adresse_l2, body_style),
            Paragraph(f"SIRET\u00a0: {self.emetteur.siret}", body_style),
            Spacer(1, 8),
            Paragraph(f"Représenté par\u00a0: {self.contact.nom}", body_style),
            Spacer(1, 6),
            Paragraph("Fait à Tournefeuille, le\u00a0: ______________", body_style),
            Spacer(1, 6),
            Paragraph("Signature précédée de la mention manuscrite", italic_style),
            Paragraph("«\u00a0Bon pour accord\u00a0»", italic_style),
            Spacer(1, 80),
        ]
        right_col = [
            Paragraph("<b>Pour le Client</b>", bold_style),
            Spacer(1, 8),
            Paragraph(f"<b>{self.client.nom}</b>", body_style),
            Paragraph(self.client.adresse_l1, body_style),
            Paragraph(self.client.adresse_l2 or "À préciser", body_style),
            Paragraph(f"SIRET\u00a0: ______________", body_style),
            Spacer(1, 8),
            Paragraph("Représenté par\u00a0: ______________", body_style),
            Spacer(1, 6),
            Paragraph("Fait à\u00a0: ______________ le\u00a0: ______________",
                      body_style),
            Spacer(1, 6),
            Paragraph("Signature précédée de la mention manuscrite", italic_style),
            Paragraph("«\u00a0Bon pour accord\u00a0»", italic_style),
            Spacer(1, 80),
        ]
        t = Table([[left_col, right_col]], colWidths=[549 * 0.5, 549 * 0.5])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 20),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t


# ═══════════════════════════════════════════════════════════════════════════
# SECTION PARTENARIAT (Conditions Particulières)
# ═══════════════════════════════════════════════════════════════════════════

def _build_partenariat_sections(part: dict) -> list[Section]:
    """Construit la section « Conditions Particulières de Partenariat ».

    Structure attendue de `part` :
    {
      "preambule": "...",
      "valeur_offerte": [{"libelle": "...", "valeur": 1375}, ...],
      "valeur_totale": 16000,
      "articles": [
        {
          "titre": "Article 1 — ...",
          "corps": "paragraphe...",
          "bullets": ["puce 1", ...],         # optionnel
          "tableau_sla": [["Type","Desc","Délai"], ...],  # optionnel
          "corps_suite": "..."                # optionnel
        }
      ]
    }
    """
    secs = [
        Section("pagebreak"),
        Section("h1", "Conditions Particulières de Partenariat"),
        Section("h2", "Un engagement stratégique long terme"),
        Section("p", _md(part.get("preambule", ""))),
        Section("spacer", height=10),
    ]

    # Tableau "Tout ce que nous vous offrons"
    val_off = part.get("valeur_offerte", [])
    val_tot = part.get("valeur_totale",
                      sum(v["valeur"] for v in val_off))
    if val_off:
        secs.append(Section("h3", "Tout ce que nous vous offrons"))
        rows = []
        for v in val_off:
            rows.append((f"✓\u00a0\u00a0{_md(v['libelle'])}",
                         _fmt_eur(v["valeur"]) + " HT"))
        rows.append(("<b>VALEUR TOTALE OFFERTE — 1ʳᵉ ANNÉE</b>",
                     f"<b>{_fmt_eur(val_tot)} HT</b>"))
        secs.append(Section("partenariat_valeur_table", data=rows))
        secs.append(Section("spacer", height=14))

    # Articles
    for art in part.get("articles", []):
        secs.append(Section("h3", art["titre"]))
        if art.get("corps"):
            for para in art["corps"].split("\n\n"):
                if para.strip():
                    secs.append(Section("p", _md(para)))
        if art.get("tableau_sla"):
            secs.append(Section("partenariat_sla_table", data=art["tableau_sla"]))
            secs.append(Section("spacer", height=6))
        for b in art.get("bullets", []):
            secs.append(Section("bullet", _md(b)))
        if art.get("corps_suite"):
            secs.append(Section("spacer", height=6))
            for para in art["corps_suite"].split("\n\n"):
                if para.strip():
                    secs.append(Section("p", _md(para)))
        secs.append(Section("spacer", height=4))

    return secs


# ═══════════════════════════════════════════════════════════════════════════
# CGV + TMA + SEO standards (annexes en fin de devis)
# ═══════════════════════════════════════════════════════════════════════════

def _default_cgv_sections() -> list[Section]:
    """Annexes officielles ESW : CGV (10 art.) + TMA (6 art.) + Contrat SEO (6 art.).

    Texte intégral retranscrit du PDF de référence Easyweb / B.M.J.W.L.
    Ces sections sont ajoutées en fin de devis pour les 3 modes (standard,
    partenariat, options_pricing).
    """
    # ═══ CGV ═══════════════════════════════════════════════════════════════
    cgv = [
        Section("pagebreak"),
        Section("h1", "Conditions Générales de Vente (CGV)"),
        Section("h3", "Easyweb – B.M.J.W.L"),

        Section("h3", "Article 1. Champ d'application"),
        Section("p", "Les présentes Conditions Générales de Vente (CGV) "
                "constituent le socle unique de la relation commerciale "
                "entre les parties."),
        Section("p", "Elles définissent les conditions dans lesquelles la SAS "
                "<b>B.M.J.W.L (Easyweb)</b>, ci-après dénommée « le Prestataire », "
                "fournit à ses clients, ci-après dénommés « le Client » ou "
                "« les Clients », les services suivants :"),
        Section("bullet", "Création d'applications mobiles,"),
        Section("bullet", "Création de sites internet,"),
        Section("bullet", "Prestations associées de conseil, design et développement "
                "(« les Services »)."),
        Section("p", "Elles s'appliquent sans restriction ni réserve à toutes les "
                "prestations rendues par le Prestataire, quelles que soient les "
                "clauses pouvant figurer sur les documents du Client, notamment "
                "ses conditions générales d'achat."),
        Section("p", "Conformément à la réglementation en vigueur, ces CGV sont "
                "communiquées à tout Client qui en fait la demande, pour lui "
                "permettre de passer commande auprès du Prestataire."),
        Section("p", "Toute commande de Services implique l'acceptation pleine et "
                "entière des présentes CGV."),
        Section("p", "Le Prestataire se réserve le droit de déroger à certaines "
                "clauses par l'établissement de <b>Conditions Particulières</b> "
                "ou d'un <b>devis signé</b> précisant les modalités propres à "
                "chaque projet."),

        Section("h3", "Article 2. Objet"),
        Section("p", "Les présentes CGV ont pour objet de définir les droits et "
                "obligations du Prestataire et du Client."),
        Section("p", "Elles régissent la vente des prestations décrites sur le "
                "devis accepté et signé par le Client."),
        Section("p", "Seules les conditions particulières énoncées sur le devis, "
                "les présentes CGV et les dispositions du Code du Commerce "
                "s'appliquent à la relation contractuelle entre Easyweb et le "
                "Client."),
        Section("p", "Elles prévalent sur tout autre document ou échange antérieur."),

        Section("h3", "Article 3. Prix et consistance de la prestation"),
        Section("p", "Les prix s'entendent <b>hors taxes</b>."),
        Section("p", "Ils sont valables <b>un mois</b> à compter de la date "
                "d'émission du devis."),
        Section("p", "La prestation comprend tout ce qui est explicitement listé "
                "dans le devis accepté par le Client."),
        Section("p", "Toute demande complémentaire fera l'objet d'un "
                "<b>devis additionnel</b>."),
        Section("p", "Les délais mentionnés dans le devis sont <b>indicatifs</b> "
                "et peuvent être révisés en cas de modification du périmètre, "
                "d'ajout de fonctionnalités ou de retard lié au Client."),

        Section("h3", "Article 4. Commande et règlement"),
        Section("p", "Un <b>acompte</b> est exigé à la signature du devis, le "
                "solde à la <b>signature de la recette</b> (sauf clauses "
                "contraires)."),
        Section("p", "Tout retard de paiement à compter du 31ᵉ jour après émission "
                "de la facture entraînera l'application des pénalités légales en "
                "vigueur, ainsi qu'une <b>indemnité forfaitaire de recouvrement</b>."),
        Section("p", "L'acompte versé ne pourra être remboursé en cas d'annulation "
                "du projet par le Client après signature."),
        Section("p", "Les paiements se font par <b>virement bancaire</b> ou "
                "<b>chèque</b>, sauf accord contraire."),
        Section("p", "La validation de la commande vaut acceptation sans réserve "
                "des présentes CGV."),

        Section("h3", "Article 5. Collaboration et délais de réalisation"),
        Section("h3", "Phase 1 : Charte graphique et maquettes"),
        Section("p", "Cette première phase n'est <b>pas soumise à un délai fixe</b>."),
        Section("p", "Sa durée dépend de plusieurs facteurs :"),
        Section("bullet", "La réactivité du Client dans la transmission des "
                "éléments nécessaires (textes, images, logos, etc.),"),
        Section("bullet", "Le nombre d'allers-retours et ajustements demandés,"),
        Section("bullet", "Les changements éventuels d'orientation en cours de "
                "création."),
        Section("p", "Le Prestataire s'engage à avancer rapidement selon les "
                "validations successives du Client."),
        Section("p", "Le Client s'engage à répondre dans des délais raisonnables "
                "afin de ne pas ralentir la progression du projet."),
        Section("h3", "Phase 2 : Développement et mise en ligne"),
        Section("p", "Une fois les maquettes <b>validées et signées</b>, un "
                "<b>délai de livraison estimatif</b> sera communiqué par écrit."),
        Section("p", "Ce délai est donné à titre indicatif et dépend d'une "
                "<b>collaboration continue</b> du Client."),
        Section("p", "Tout retard dans la validation, la fourniture de contenus "
                "ou toute demande de modification en cours de route entraînera "
                "un <b>report automatique du délai initial</b> sans possibilité "
                "de recours."),

        Section("h3", "Article 6. Responsabilité et retards imputables au client"),
        Section("p", "Le Prestataire ne pourra être tenu responsable d'un retard "
                "de livraison résultant de causes extérieures à sa volonté, "
                "notamment :"),
        Section("bullet", "Non-validation ou validation tardive d'une étape,"),
        Section("bullet", "Demandes de modifications majeures après validation,"),
        Section("bullet", "Retard dans la fourniture de contenus,"),
        Section("bullet", "Absence de réponse du Client dans des délais "
                "raisonnables."),
        Section("p", "En cas de retard imputable au Client, les délais seront "
                "<b>prolongés d'une durée équivalente</b>."),
        Section("p", "Si le Client annule le projet pour cause de retard dont il "
                "est responsable, <b>les sommes déjà versées resteront acquises</b> "
                "à Easyweb."),

        Section("h3", "Article 7. Cas des propositions non retenues"),
        Section("p", "Les devis établis par Easyweb sont gratuits."),
        Section("p", "Les projets présentés demeurent la <b>propriété exclusive</b> "
                "d'Easyweb et doivent être restitués (documents numériques et "
                "papiers) si le projet n'est pas retenu."),
        Section("p", "Toute réutilisation, partielle ou totale, sans accord écrit, "
                "constitue une <b>contrefaçon</b> et pourra donner lieu à des "
                "poursuites."),

        Section("h3", "Article 8. Force majeure"),
        Section("p", "Easyweb ne saurait être tenue responsable d'un manquement "
                "à ses obligations contractuelles en cas de force majeure ou "
                "d'événements imprévisibles :"),
        Section("p", "grève, incendie, inondation, panne serveur, pandémie, "
                "cyberattaque, ou tout autre événement échappant à son contrôle."),
        Section("p", "Le Prestataire informera le Client dans les plus brefs "
                "délais et s'efforcera de limiter les conséquences du retard."),

        Section("h3", "Article 9. Clause résolutoire"),
        Section("p", "En cas d'inexécution d'une obligation essentielle par l'une "
                "des parties (notamment non-paiement ou non-réalisation), le "
                "contrat pourra être <b>résolu de plein droit</b> 30 jours après "
                "mise en demeure restée sans effet."),
        Section("p", "Les acomptes versés resteront acquis à Easyweb à titre de "
                "dédommagement."),

        Section("h3", "Article 10. Droit applicable et juridiction compétente"),
        Section("p", "Les présentes CGV sont soumises au <b>droit français</b>."),
        Section("p", "En cas de litige et à défaut de solution amiable, la "
                "<b>compétence exclusive</b> revient au <b>Tribunal de Commerce "
                "de Toulouse</b>."),
    ]

    # ═══ TMA ═══════════════════════════════════════════════════════════════
    tma = [
        Section("pagebreak"),
        Section("h1", "Contrat de Tierce Maintenance Applicative (TMA)"),
        Section("p", "Le présent contrat a pour objet de définir les conditions "
                "dans lesquelles le Prestataire assure la maintenance corrective "
                "et évolutive des solutions digitales (Site Web ou Application "
                "Mobile) du Client."),

        Section("h3", "Article 1. La Maintenance Évolutive : le forfait d'heures "
                "mensuel"),
        Section("p", "Afin de garantir que la solution digitale du Client reste "
                "performante et alignée avec ses besoins métiers, le Prestataire "
                "met en place un accompagnement basé sur un forfait d'heures "
                "mensuel. Ce volume d'heures est pré-alloué au projet pour toute "
                "modification ou amélioration technique."),
        Section("h3", "1.1. Périmètre d'intervention"),
        Section("p", "Le forfait d'heures peut être utilisé pour le développement "
                "de nouvelles fonctionnalités, l'optimisation de l'ergonomie, "
                "les mises à jour de sécurité des composants tiers, ou encore "
                "le conseil technique."),
        Section("h3", "1.2. Mécanisme de report (Crédit d'heures)"),
        Section("p", "Le Prestataire s'engage à une flexibilité totale : si les "
                "heures allouées au forfait mensuel ne sont pas intégralement "
                "consommées au cours du mois échu, le solde restant est "
                "automatiquement reporté sur le mois suivant. Ce crédit d'heures "
                "cumulé permet au Client de financer des évolutions plus "
                "importantes sans surcoût immédiat."),
        Section("h3", "1.3. Dépassement de forfait"),
        Section("p", "Dans l'éventualité où les demandes du Client nécessiteraient "
                "un temps de travail supérieur au forfait mensuel et au crédit "
                "d'heures disponible, le Prestataire en informera le Client. "
                "Toute heure travaillée au-delà du forfait sera facturée au tarif "
                "préférentiel de <b>100 euros Hors Taxes (HT) par heure</b>. "
                "Ces interventions hors forfait ne seront déclenchées qu'après "
                "accord écrit du Client."),

        Section("h3", "Article 2. La Maintenance Corrective et Réactivité (SLA)"),
        Section("p", "La maintenance corrective vise à assurer la disponibilité "
                "du service en corrigeant tout bug ou anomalie logicielle. Le "
                "Prestataire s'engage à intervenir selon les délais suivants, "
                "basés sur la gravité de l'incident :"),
        Section("h3", "2.1. Anomalie Bloquante"),
        Section("p", "En cas d'interruption totale du service ou de "
                "dysfonctionnement d'une fonction vitale (paiement, accès "
                "utilisateur), le Prestataire s'engage à débuter les "
                "interventions de diagnostic et de correction dans un délai de "
                "<b>24 heures ouvrées</b>."),
        Section("h3", "2.2. Anomalie Majeure"),
        Section("p", "En cas de dysfonctionnement d'une fonctionnalité importante "
                "mais n'empêchant pas l'utilisation globale du service, le "
                "Prestataire s'engage à intervenir dans un délai de "
                "<b>48 heures ouvrées</b>."),
        Section("h3", "2.3. Anomalie Mineure"),
        Section("p", "Pour tout défaut cosmétique ou bug léger n'entravant pas "
                "l'expérience utilisateur, l'intervention est planifiée dans un "
                "délai de <b>5 jours ouvrés</b>."),

        Section("h3", "Article 3. Conditions Financières et Modalités de Paiement"),
        Section("h3", "3.1. Facturation du forfait"),
        Section("p", "Le forfait de maintenance fait l'objet d'une facturation "
                "mensuelle récurrente, émise en début de période. Le règlement "
                "doit intervenir dans un délai de 30 jours à compter de la date "
                "d'émission de la facture, sauf accord particulier mentionné au "
                "devis."),
        Section("h3", "3.2. Facturation des dépassements"),
        Section("p", "Les heures supplémentaires effectuées hors forfait (tarif "
                "de 100 € HT/h) sont facturées à terme échu, à la fin du mois "
                "concerné, sur la base d'un relevé d'activité transparent fourni "
                "par le Prestataire."),
        Section("h3", "3.3. Révision des prix"),
        Section("p", "Le Prestataire se réserve le droit de réviser le tarif "
                "horaire ou le montant du forfait annuellement, sous réserve "
                "d'en informer le Client par écrit au moins deux mois avant "
                "l'application des nouveaux tarifs."),

        Section("h3", "Article 4. Obligations des Parties"),
        Section("h3", "4.1. Obligations du Prestataire"),
        Section("p", "Le Prestataire est tenu à une obligation de moyens. Il "
                "s'engage à mobiliser les compétences techniques nécessaires et "
                "à apporter un soin professionnel à l'exécution des prestations. "
                "Il doit tenir le Client informé de l'état d'avancement des "
                "interventions et l'alerter en cas de difficultés techniques "
                "majeures."),
        Section("h3", "4.2. Obligations du Client"),
        Section("p", "Le Client s'engage à collaborer activement avec le "
                "Prestataire en fournissant toutes les informations et accès "
                "nécessaires (serveurs, consoles d'administration, API). Il est "
                "responsable de la désignation d'un interlocuteur unique pour la "
                "validation des travaux et doit signaler les anomalies de manière "
                "précise via l'outil de ticketing mis à sa disposition."),

        Section("h3", "Article 5. Confidentialité et Propriété Intellectuelle"),
        Section("h3", "5.1. Confidentialité"),
        Section("p", "Chacune des parties s'engage à considérer comme "
                "confidentielles toutes les informations, documents ou données "
                "échangés dans le cadre de l'exécution du contrat. Cette "
                "obligation survit à la résiliation du contrat pour une durée "
                "de deux ans."),
        Section("h3", "5.2. Propriété Intellectuelle"),
        Section("p", "Le Prestataire cède au Client, au fur et à mesure du "
                "paiement intégral des factures, la propriété de tous les "
                "développements spécifiques réalisés exclusivement pour le compte "
                "du Client dans le cadre de la maintenance évolutive. Toutefois, "
                "le Prestataire conserve la propriété de ses outils, méthodes, "
                "savoir-faire et codes sources préexistants utilisés pour "
                "réaliser la prestation."),

        Section("h3", "Article 6. Durée et Résiliation"),
        Section("h3", "6.1. Durée et Reconduction"),
        Section("p", "Le présent contrat est conclu pour une durée initiale "
                "mentionnée au devis (généralement 12 mois). À l'issue de cette "
                "période, il se renouvelle tacitement par périodes successives "
                "d'un mois, sauf dénonciation par l'une des parties."),
        Section("h3", "6.2. Résiliation"),
        Section("p", "Chaque partie peut mettre fin au contrat à tout moment, "
                "sous réserve du respect d'un préavis de <b>deux mois</b>, "
                "notifié par lettre recommandée avec accusé de réception. En cas "
                "de manquement grave de l'une des parties à ses obligations "
                "(notamment le défaut de paiement), la résiliation pourra "
                "intervenir de plein droit 15 jours après une mise en demeure "
                "restée infructueuse."),
        Section("h3", "6.3. Récupération des données"),
        Section("p", "En cas de résiliation, le Prestataire s'engage à restituer "
                "au Client l'ensemble des accès et, sur demande et devis de "
                "réversibilité, à fournir une copie des fichiers sources et des "
                "bases de données dans un format standard."),
    ]

    # ═══ Contrat SEO ═══════════════════════════════════════════════════════
    seo = [
        Section("pagebreak"),
        Section("h1", "Contrat de prestation SEO (référencement naturel)"),
        Section("p", "Le présent contrat a pour objet de définir les conditions "
                "dans lesquelles le Prestataire accompagne le Client dans "
                "l'optimisation de sa visibilité sur les moteurs de recherche "
                "(SEO - Search Engine Optimization), dans le but de générer un "
                "trafic organique qualifié vers son site web."),

        Section("h3", "Article 1. Structure de l'Accompagnement et Modèles "
                "Tarifaires"),
        Section("p", "Le référencement naturel nécessite une base technique et "
                "stratégique solide. Quel que soit le modèle choisi, la "
                "prestation débute toujours par une phase de mise en place "
                "(Setup). Le Prestataire propose ensuite deux modèles "
                "d'accompagnement distincts, définis conjointement dans le "
                "devis :"),
        Section("h3", "Option A : Prestation clé en main (Setup + Mensualités "
                "récurrentes)"),
        Section("p", "Ce modèle implique une délégation complète des actions SEO "
                "au Prestataire sur le long terme."),
        Section("bullet", "<b>Un coût de mise en place (Setup)</b> : facturé au "
                "lancement du projet. Il couvre le travail intensif initial "
                "(audits techniques et sémantiques, corrections structurelles, "
                "définition de la stratégie)."),
        Section("bullet", "<b>Des mensualités de suivi et d'optimisation</b> : "
                "un forfait mensuel récurrent couvrant le travail continu de "
                "création de contenu, d'acquisition de liens (netlinking) et "
                "d'ajustements techniques."),
        Section("h3", "Option B : Accompagnement par la formation "
                "(Setup + 1 seule Mensualité)"),
        Section("p", "Ce modèle est destiné aux Clients souhaitant internaliser "
                "l'exécution du SEO après avoir posé des bases saines."),
        Section("bullet", "<b>Un coût de mise en place (Setup)</b> : facturé au "
                "lancement du projet. Il couvre les mêmes audits et la création "
                "de la stratégie initiale que dans l'Option A."),
        Section("bullet", "<b>Une mensualité unique de formation</b> : le "
                "Prestataire facture un seul et unique mois d'accompagnement à "
                "la suite du Setup. Ce mois est dédié à la formation des équipes "
                "du Client, au transfert de compétences et à la remise de la "
                "feuille de route afin de les rendre autonomes."),

        Section("h3", "Article 2. Détail des Prestations"),
        Section("h3", "2.1. Phase de Setup et Stratégie (Commune aux Options A et B)"),
        Section("bullet", "<b>Audit technique</b> : analyse de la structure du "
                "site, de la vitesse de chargement, de l'indexabilité et de la "
                "compatibilité mobile."),
        Section("bullet", "<b>Audit sémantique et concurrentiel</b> : étude des "
                "mots-clés stratégiques liés à l'activité du Client et analyse "
                "du positionnement des concurrents directs."),
        Section("bullet", "<b>Recommandations et plan d'action</b> : livraison "
                "d'une feuille de route priorisant les actions à mener."),
        Section("h3", "2.2. Optimisation Continue et Exécution (Spécifique à "
                "l'Option A)"),
        Section("bullet", "<b>Optimisation On-Site</b> : rédaction et/ou "
                "optimisation des balises (Title, Meta Description, Hn), "
                "maillage interne, et enrichissement sémantique des pages."),
        Section("bullet", "<b>Optimisation Off-Site (Netlinking)</b> : recherche "
                "et acquisition de liens entrants pertinents (backlinks) pour "
                "renforcer la popularité du domaine."),
        Section("bullet", "<b>Suivi et Reporting</b> : analyse des positions et "
                "du trafic organique via un rapport mensuel."),
        Section("h3", "2.3. Formation et Transfert de compétences (Spécifique à "
                "l'Option B)"),
        Section("bullet", "<b>Sessions de formation</b> : réalisation de sessions "
                "de travail (durant l'unique mois facturé) pour former les "
                "équipes du Client aux bonnes pratiques du SEO (rédaction, "
                "intégration)."),
        Section("bullet", "<b>Autonomie</b> : à l'issue de ce mois, le Client est "
                "pleinement responsable de l'exécution de la stratégie et le "
                "contrat prend fin naturellement."),

        Section("h3", "Article 3. Limites de Responsabilité : Obligation de Moyens"),
        Section("h3", "3.1. Absence d'obligation de résultat"),
        Section("p", "De convention expresse entre les parties, le Prestataire "
                "est soumis à une <b>obligation de moyens et non de résultats</b> "
                "concernant le positionnement du site du Client sur les moteurs "
                "de recherche."),
        Section("p", "Le Prestataire s'engage à mettre en œuvre son expertise, "
                "les meilleures pratiques de l'industrie (dites \"White Hat\") "
                "et les outils adéquats pour optimiser la visibilité du site. "
                "Toutefois, le Prestataire ne peut en aucun cas garantir "
                "l'atteinte d'une position spécifique (ex : \"Première page sur "
                "Google\"), ni garantir un volume exact de trafic organique ou "
                "de chiffre d'affaires."),
        Section("h3", "3.2. Indépendance des algorithmes"),
        Section("p", "Cette limite de responsabilité s'explique par la nature "
                "même du fonctionnement des moteurs de recherche. Les "
                "algorithmes de classement (notamment ceux de Google) sont "
                "propriétaires, tenus secrets, et font l'objet de mises à jour "
                "constantes et imprévisibles. Les moteurs de recherche demeurent "
                "les seuls et uniques décisionnaires de l'indexation et du "
                "positionnement final des pages web."),

        Section("h3", "Article 4. Obligations du Client"),
        Section("p", "La réussite d'une stratégie SEO repose sur une "
                "collaboration étroite. Le Client s'engage à :"),
        Section("bullet", "Fournir au Prestataire l'ensemble des accès "
                "nécessaires (Back-office du CMS, accès FTP/Serveur si requis, "
                "Google Analytics, Google Search Console)."),
        Section("bullet", "Valider les propositions de contenus ou de mots-clés "
                "dans des délais raisonnables afin de ne pas bloquer le "
                "déploiement de la stratégie (Option A)."),
        Section("bullet", "Dans le cadre de l'Option B, le Client est seul "
                "responsable de l'intégration et de l'exécution finale des "
                "recommandations une fois le mois de formation achevé."),

        Section("h3", "Article 5. Conditions Financières et Facturation"),
        Section("h3", "5.1. Modalités de paiement"),
        Section("bullet", "<b>Frais de mise en place (Setup)</b> : facturés à la "
                "signature du devis et payables à réception pour déclencher les "
                "audits initiaux."),
        Section("bullet", "<b>Mensualités récurrentes (Option A)</b> : facturées "
                "en début de mois par prélèvement automatique ou virement "
                "bancaire, payables à 30 jours."),
        Section("bullet", "<b>Mensualité unique de formation (Option B)</b> : "
                "facturée à l'issue du Setup, payable à 30 jours, marquant la "
                "fin de la prestation financière."),
        Section("h3", "5.2. Frais annexes (Option A uniquement)"),
        Section("p", "Tout achat d'articles sponsorisés, de campagnes de "
                "netlinking spécifiques ou d'outils tiers non inclus dans le "
                "forfait initial fera l'objet d'un devis séparé soumis à la "
                "validation du Client."),

        Section("h3", "Article 6. Durée, Engagement et Résiliation"),
        Section("h3", "6.1. Durée d'engagement (Option A)"),
        Section("p", "Le SEO nécessitant du temps pour produire des effets "
                "mesurables, le contrat en Option A est conclu pour une durée "
                "d'engagement initiale minimale mentionnée au devis (généralement "
                "6 à 12 mois). À l'issue de cette période, il est reconduit "
                "tacitement par périodes successives d'un mois, résiliable "
                "moyennant un préavis d'un mois."),
        Section("h3", "6.2. Durée d'engagement (Option B)"),
        Section("p", "Le contrat en Option B prend fin automatiquement et de "
                "plein droit à l'issue du mois de formation, une fois les "
                "compétences transférées et la mensualité unique réglée."),
        Section("h3", "6.3. Confidentialité"),
        Section("p", "Le Prestataire s'engage à garder strictement "
                "confidentielles les données de trafic, les stratégies "
                "commerciales et les informations internes du Client auxquelles "
                "il aura accès durant sa mission."),
    ]

    return cgv + tma + seo


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    p = argparse.ArgumentParser(
        description="Générateur PDF de devis EasyGestion.",
    )
    p.add_argument("--input", "-i", required=True,
                   help="Chemin vers le JSON canonique du devis.")
    p.add_argument("--output", "-o", default="devis.pdf",
                   help="Chemin du PDF de sortie.")
    p.add_argument("--assets-dir", default=None,
                   help="Dossier contenant les 3 PNG templates "
                        "(par défaut : à côté du script).")
    args = p.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERREUR] Fichier introuvable : {input_path}", file=sys.stderr)
        return 1

    assets_dir = Path(args.assets_dir) if args.assets_dir else Path(__file__).parent

    try:
        devis = Devis.from_json(input_path, assets_dir=assets_dir)
        out = devis.render(args.output)
    except Exception as e:
        print(f"[ERREUR] Génération échouée : {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2

    print(f"✓ Devis généré : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
