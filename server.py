"""
EasyGestion — Backend FastAPI wrapper
======================================
Expose generate_devis_v4.py via une API HTTP, déployable sur Railway.

Endpoints :
  POST /devis          → body JSON canonique → renvoie le PDF (bytes)
  GET  /healthz        → check de santé
  GET  /               → info API

Sécurité : header X-API-Key (variable d'env API_KEY).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

# --- Configuration via variables d'environnement ---
API_KEY = os.environ.get("API_KEY", "")  # secret partagé avec EasyGestion
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://easy-agency-ultime.vercel.app,http://localhost:5173,http://localhost:5174",
    ).split(",")
    if o.strip()
]

BASE_DIR = Path(__file__).parent
SCRIPT = BASE_DIR / "generate_devis_v4.py"
ASSETS_DIR = BASE_DIR / "assets"

app = FastAPI(title="EasyGestion Devis API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def _check_auth(x_api_key: str | None) -> None:
    """Vérifie l'API key passée dans le header."""
    if not API_KEY:
        # Pas de clé configurée côté serveur → on laisse passer (dev only)
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@app.get("/")
def root() -> dict:
    return {
        "service": "EasyGestion Devis API",
        "version": "1.0",
        "endpoints": ["/devis (POST)", "/healthz (GET)", "/v1/storage/client-files (DELETE)"],
    }


@app.get("/healthz")
def healthz() -> dict:
    """Check que le script et les assets sont bien présents."""
    return {
        "ok": True,
        "script_exists": SCRIPT.is_file(),
        "assets_exists": ASSETS_DIR.is_dir(),
        "assets_files": [p.name for p in ASSETS_DIR.glob("*.png")] if ASSETS_DIR.is_dir() else [],
    }


@app.delete("/v1/storage/client-files")
def delete_client_storage_file(
    path: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Supprime un fichier du bucket client-files (service role, contourne RLS)."""
    _check_auth(x_api_key)

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY requis sur Railway",
        )

    clean = path.strip().lstrip("/")
    if not clean or ".." in clean.split("/"):
        raise HTTPException(status_code=400, detail="Chemin invalide")

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }

    def _delete(url: str, body: bytes | None = None) -> int:
        req_headers = dict(headers)
        if body is not None:
            req_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, method="DELETE", headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status
        except urllib.error.HTTPError as err:
            raise HTTPException(status_code=err.code, detail=err.read().decode()[:500]) from err

    object_url = f"{SUPABASE_URL}/storage/v1/object/client-files/{clean}"
    try:
        status = _delete(object_url)
        return {"ok": True, "status": status, "path": clean}
    except HTTPException as first_err:
        if first_err.status_code not in (400, 404):
            raise
        prefix_url = f"{SUPABASE_URL}/storage/v1/object/client-files"
        body = json.dumps({"prefixes": [clean]}).encode("utf-8")
        status = _delete(prefix_url, body)
        return {"ok": True, "status": status, "path": clean, "mode": "prefix"}


@app.post("/devis")
async def generate_devis(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Response:
    """
    Reçoit le JSON canonique du devis (cf. structure dans generate_devis_v4.py)
    et renvoie le PDF généré en bytes.

    Body : application/json — structure complète du devis
    Response : application/pdf
    """
    _check_auth(x_api_key)

    # 1. Récupérer le JSON
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}")

    if not isinstance(data, dict) or "projet" not in data:
        raise HTTPException(status_code=400, detail="Missing required 'projet' block in JSON")

    # 2. Préparer un répertoire de travail temporaire
    job_id = uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix=f"devis_{job_id}_") as tmp:
        tmp_path = Path(tmp)
        in_path = tmp_path / "input.json"
        out_path = tmp_path / f"devis_{job_id}.pdf"

        in_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        # 3. Invoquer le script
        cmd = [
            "python3",
            str(SCRIPT),
            "--input", str(in_path),
            "--output", str(out_path),
            "--assets-dir", str(ASSETS_DIR),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "PDF generation failed",
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-2000:],
                },
            )

        if not out_path.is_file():
            raise HTTPException(status_code=500, detail="PDF file not produced")

        pdf_bytes = out_path.read_bytes()

    # 4. Renvoyer le PDF en bytes
    devis_no = data.get("meta", {}).get("devis_no", job_id)
    filename = f"devis_{devis_no}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Devis-No": devis_no,
        },
    )


@app.post("/v1/generate-devis")
async def generate_devis_v1(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Response:
    return await generate_devis(request, x_api_key)


@app.post("/v1/generate-pptx")
async def generate_pptx_endpoint(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Response:
    _check_auth(x_api_key)
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    job_id = uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix=f"pptx_{job_id}_") as tmp:
        tmp_path = Path(tmp)
        canonical_path = tmp_path / "canonical.json"
        pptx_json_path = tmp_path / "pptx_input.json"
        out_path = tmp_path / f"presentation_{job_id}.pptx"

        canonical_path.write_text(json.dumps(data, ensure_ascii=False))

        adapter = BASE_DIR / "canonical_to_pptx.py"
        r1 = subprocess.run(
            ["python3", str(adapter), "--input", str(canonical_path), "--output", str(pptx_json_path)],
            capture_output=True, text=True, timeout=30
        )
        if r1.returncode != 0:
            return JSONResponse(status_code=500, content={"error": "Adapter failed", "stderr": r1.stderr[-2000:]})

        pptx_script = BASE_DIR / "generate-pptx.js"
        slides_dir = BASE_DIR / "assets" / "slides"
        r2 = subprocess.run(
            ["node", str(pptx_script), "--input", str(pptx_json_path), "--output", str(out_path), "--assets-dir", str(slides_dir)],
            capture_output=True, text=True, timeout=120
        )
        if r2.returncode != 0:
            return JSONResponse(status_code=500, content={"error": "PPTX generation failed", "stderr": r2.stderr[-2000:]})

        if not out_path.is_file():
            raise HTTPException(status_code=500, detail="PPTX not produced")

        pptx_bytes = out_path.read_bytes()

    devis_no = data.get("meta", {}).get("devis_no", job_id)
    filename = f"presentation_{devis_no}.pptx"
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
