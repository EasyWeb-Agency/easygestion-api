# EasyGestion — Pipeline de génération de devis PDF

Bundle complet pour déployer le générateur sur Railway et l'appeler depuis EasyGestion.

## Contenu du bundle

```
easygestion_pipeline/
├── generate_devis_v4.py     # Le générateur (2353 lignes, ne pas toucher)
├── server.py                # Wrapper FastAPI minimal (~120 lignes)
├── requirements.txt         # Dépendances Python
├── Dockerfile               # Build Railway
├── Procfile                 # Fallback Railway (si pas de Dockerfile détecté)
├── devis.ts                 # Client TypeScript pour le frontend EasyGestion
├── assets/                  # PNGs de fond ESW (4790×7200 px)
│   ├── Page_de_garde.png
│   ├── Premie_re_page.png
│   ├── Page_classique.png
│   └── Projection_ROI.png
└── fonts/                   # Nunito Sans (utilisée par reportlab)
    ├── NunitoSans-Regular.ttf
    ├── NunitoSans-Medium.ttf
    └── NunitoSans-Bold.ttf
```

## Architecture

```
┌─────────────────────┐         POST /devis           ┌──────────────────────┐
│  EasyGestion (Vercel)│ ─── JSON canonique  ──────→  │  Railway (FastAPI)   │
│  React + TS         │                                │  generate_devis_v4   │
│  /devis/nouveau     │ ←── application/pdf  ────────  │  reportlab           │
└─────────────────────┘                                └──────────────────────┘
```

## Déploiement Railway (15 minutes)

1. **Créer un projet Railway** (https://railway.app) → `New Project` → `Deploy from GitHub`.
2. Push ce dossier dans un repo GitHub (ou utiliser `railway up` en CLI).
3. Railway détecte le `Dockerfile` automatiquement.
4. Dans `Settings → Variables`, ajouter :
   - `API_KEY` = une longue chaîne aléatoire (ex. `openssl rand -hex 32`)
   - `ALLOWED_ORIGINS` = `https://easy-agency-ultime.vercel.app,http://localhost:5173`
5. Railway expose une URL publique, par exemple `https://easygestion-devis.up.railway.app`.
6. Tester : `curl https://easygestion-devis.up.railway.app/healthz`

Coût Railway : ~5 $/mois sur le starter plan.

## Côté EasyGestion (Vercel)

1. Copier `devis.ts` dans `src/lib/devis.ts`.
2. Dans Vercel → `Settings → Environment Variables`, ajouter :
   - `VITE_RAILWAY_URL` = `https://easygestion-devis.up.railway.app`
   - `VITE_DEVIS_API_KEY` = même valeur que `API_KEY` côté Railway
3. Redéployer.
4. Dans la page `/devis/:id`, utiliser :

```ts
import { generateDevisPdf, downloadPdfBlob, previewPdfBlob } from "@/lib/devis";

async function handleDownload(devis: DevisCanonique) {
  try {
    setLoading(true);
    const blob = await generateDevisPdf(devis);
    downloadPdfBlob(blob, `devis_${devis.meta.devis_no}.pdf`);
  } catch (err) {
    toast.error(String(err));
  } finally {
    setLoading(false);
  }
}
```

## Endpoints exposés

| Méthode | Route       | Description                          |
|---------|-------------|--------------------------------------|
| GET     | `/`         | Info de l'API                        |
| GET     | `/healthz`  | Check de santé + assets présents     |
| POST    | `/devis`    | JSON in → PDF out (bytes)            |

## Structure du JSON canonique

Voir les exemples dans `/mnt/user-data/outputs/` (Vibraforce, Pupilles-Mousses, gîte familial, TK Pro…). Blocs requis :

- `meta` : `devis_no`, `date_creation`, `version`, `template`
- `client` : `nom`, `representant`, `adresse_l1`, `siret`…
- `emetteur` : info ESW (fixe)
- `projet` : `nom`, `type`, `budget`, `duree_mois`, `tjm`
- `sections` : `objet_mission`, `contexte`, `fonctionnalites`, `plan_action`, `equipe`, `technologies`, `acquisition`, etc.
- `budget_detail` : `modules` (pôles + items + heures) + `jalons` (libellés + montants)

Le script détecte automatiquement le mode :
- **Standard** (`budget_detail.modules` + `jalons`)
- **Partenariat** (`partenariat` block)
- **Options pricing V1/V2/V3** (`options_pricing` block avec `v1`/`v2`/`v3`)
- **Packs** (3 colonnes horizontales)

## Pourquoi un endpoint, pas une lambda directe ?

- **Subprocess plus simple** que d'importer les classes : le script évolue, le wrapper reste stable.
- **Timeout 120s** : on gère les devis longs (20+ pages) sans souci.
- **Fichiers temporaires** auto-nettoyés via `tempfile.TemporaryDirectory()`.
- **CORS** : restrictif par défaut, ajouter le domaine via `ALLOWED_ORIGINS`.
- **Auth API key** : suffisant pour usage interne. Si exposition publique future, passer à OAuth/JWT.

## Tests rapides

```bash
# Test local avant déploiement
cd easygestion_pipeline
pip install -r requirements.txt
uvicorn server:app --reload --port 8080

# Healthz
curl http://localhost:8080/healthz

# Génération d'un devis (avec un JSON existant)
curl -X POST http://localhost:8080/devis \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev" \
  -d @vibraforce_odoo_v5.json \
  --output test.pdf
```

## Évolutions possibles (V2)

- **Cache S3** : stocker les PDFs générés sur Supabase Storage, renvoyer l'URL plutôt que les bytes (utile si plusieurs téléchargements).
- **Génération asynchrone** : `POST /devis` retourne `job_id`, le client poll `GET /devis/{job_id}` (utile si génération > 30s).
- **PPTX en plus** : ajouter `generate-pptx.js` sur le même serveur (multistage Dockerfile Python+Node).
- **Auth Supabase JWT** : à la place de la simple API key, valider le JWT du user EasyGestion pour tracer qui génère quoi.

## Maintenance

- Le **script `generate_devis_v4.py`** ne doit pas être modifié dans Railway directement — toute évolution se fait dans le workspace de dev, puis push GitHub → Railway redéploie.
- Les **PNGs et fonts** sont dans le repo, donc immuables après build. Pour changer la charte, refaire le build complet.
- **Variables d'env** : `API_KEY` peut être rotée à tout moment (changer Railway + Vercel en même temps).
