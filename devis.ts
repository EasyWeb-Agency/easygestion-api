/**
 * EasyGestion — Client API Devis
 * ================================
 * Appel à l'endpoint Railway pour générer un PDF de devis.
 *
 * Variables d'environnement requises (Vercel) :
 *   VITE_RAILWAY_URL    — URL de l'API Railway (ex. https://easygestion-devis.up.railway.app)
 *   VITE_DEVIS_API_KEY  — clé partagée avec le backend (header X-API-Key)
 */

const RAILWAY_URL = import.meta.env.VITE_RAILWAY_URL as string;
const API_KEY = import.meta.env.VITE_DEVIS_API_KEY as string;

/**
 * Structure canonique du devis (cf. generate_devis_v4.py).
 * Type minimal — étoffer selon besoin.
 */
export interface DevisCanonique {
  meta: {
    devis_no: string;
    date_creation: string;
    version: number;
    status?: string;
    template?: string;
  };
  client: {
    nom: string;
    representant?: string;
    adresse_l1?: string;
    adresse_l2?: string;
    email?: string;
    siret?: string;
  };
  emetteur: {
    nom: string;
    adresse_l1?: string;
    adresse_l2?: string;
    siret?: string;
    contact_nom?: string;
    contact_email?: string;
    contact_tel?: string;
  };
  projet: {
    nom: string;
    type: string;
    budget: number;
    duree_mois: number;
    tjm: number;
  };
  sections: Record<string, unknown>;
  budget_detail?: {
    modules?: Array<{ titre: string; items: Array<{ nom: string; heures: number }> }>;
    jalons?: Array<{ libelle: string; pourcentage: number; montant: number }>;
  };
}

/**
 * Génère un PDF de devis et renvoie un Blob téléchargeable.
 *
 * @param payload  Le devis au format canonique
 * @returns        Un Blob PDF (à utiliser avec URL.createObjectURL pour le download)
 * @throws         Error si la requête échoue
 */
export async function generateDevisPdf(payload: DevisCanonique): Promise<Blob> {
  if (!RAILWAY_URL) {
    throw new Error("VITE_RAILWAY_URL is not configured");
  }

  const response = await fetch(`${RAILWAY_URL}/devis`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      detail = err.detail || err.error || JSON.stringify(err);
    } catch {
      detail = await response.text();
    }
    throw new Error(`Devis generation failed: ${detail}`);
  }

  return await response.blob();
}

/**
 * Télécharge le PDF généré dans le navigateur.
 * À appeler depuis un onClick :
 *   const blob = await generateDevisPdf(devis);
 *   downloadPdfBlob(blob, `devis_${devis.meta.devis_no}.pdf`);
 */
export function downloadPdfBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Ouvre le PDF dans un nouvel onglet (preview avant download).
 */
export function previewPdfBlob(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  // Garder le blob URL valide quelques secondes pour que le navigateur ait le temps de l'ouvrir
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
