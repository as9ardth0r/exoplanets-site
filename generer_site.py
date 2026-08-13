"""
Régénère automatiquement la barre de stats et les fiches "Dossiers
examinés" de index.html, à partir de :
  - resultats_candidats.csv  (RA/Dec/Tmag, nombre total d'étoiles scannées)
  - verdicts.csv             (le verdict humain sur chaque étoile vérifiée à l'œil)
  - un dossier d'images brutes (les PNG produits par exoplanet_bls_generic.py)

Ce que ce script automatise : les chiffres, la mise en page des fiches,
le recadrage des images. Ce qu'il n'automatise PAS, volontairement :
le verdict lui-même (binaire / variable / marginal / confirmé) et sa
justification -- ça reste un jugement humain, à écrire dans verdicts.csv
après avoir regardé le graphique produit par exoplanet_bls_generic.py.

Usage :
    python3 generer_site.py
    python3 generer_site.py --raw-dir dossier_avec_les_png_bruts

Structure attendue à côté de ce script :
    index.html
    verdicts.csv
    resultats_candidats.csv
    assets/crop/           (images déjà recadrées -- créé si absent)
    raw/                   (PNG bruts de exoplanet_bls_generic.py, optionnel)
"""

import argparse
import csv
import os
import re
import sys
from PIL import Image

CROP_DEFAUT = (0, 550, 1350, 1150)  # panneau "cycle complet"


def charger_resultats(path):
    """Renvoie un dict tic_id (str) -> ligne (dict) depuis resultats_candidats.csv."""
    table = {}
    if not os.path.exists(path):
        print(f"Attention : {path} introuvable, RA/Dec/Tmag ne seront pas remplis.")
        return table
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = re.search(r"\d+", row.get("nom", ""))
            if m:
                table[m.group()] = row
    return table


def charger_verdicts(path):
    if not os.path.exists(path):
        sys.exit(f"Erreur : {path} introuvable. Crée-le d'abord (voir l'entête du script).")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def recadrer_image(tic_id, raw_dir, crop_dir, crop_box):
    """Si un PNG brut existe pour cette étoile, le recadre et le sauvegarde
    dans assets/crop/. Ne fait rien si l'image recadrée existe déjà et
    qu'il n'y a pas de nouveau brut à traiter."""
    dest = os.path.join(crop_dir, f"tic-{tic_id}.png")
    if raw_dir:
        candidats = [
            os.path.join(raw_dir, f"resultat_TIC_{tic_id}.png"),
            os.path.join(raw_dir, f"resultat_TIC{tic_id}.png"),
        ]
        for src in candidats:
            if os.path.exists(src):
                im = Image.open(src)
                im.crop(crop_box).save(dest)
                print(f"  image recadrée : {src} -> {dest}")
                return
    if not os.path.exists(dest):
        print(f"  ⚠ pas d'image pour TIC {tic_id} (ni brute ni déjà recadrée dans assets/crop/)")


def carte_html(v, r):
    tic_id = v["tic_id"]
    ra = r.get("RA", "—")
    dec = r.get("Dec", "—")
    tmag = r.get("Tmag", "—")
    try:
        ra = f"{float(ra):.3f}"
        dec = f"{float(dec):.3f}"
        tmag = f"{float(tmag):.2f}"
    except (ValueError, TypeError):
        pass
    snr = v["snr"].strip() if v.get("snr", "").strip() else "—"
    note = v["note"].replace('""', '"')

    return f"""
        <div class="card">
          <div class="shot">
            <img src="assets/crop/tic-{tic_id}.png" alt="Courbe de lumière de TIC {tic_id}">
            <span class="stamp {v['stamp_class']}">{v['stamp_label']}</span>
          </div>
          <div class="body">
            <p class="tic">TIC {tic_id}</p>
            <p class="coords">RA {ra} · DEC {dec} · Tmag {tmag}</p>
            <p class="verdict-text">{note}</p>
            <div class="meta-row"><span>période <b>{v['periode']} j</b></span><span>snr <b>{snr}</b></span></div>
          </div>
        </div>
"""


def stats_html(n_scannees, n_bruts, n_confirmees, n_filtres=5, n_redetections=2):
    def fmt(n):
        return f"{(n // 100) * 100}+" if n >= 200 else str(n)

    return f"""
      <div class="stat"><span class="n">{n_redetections}</span><span class="l">redétections confirmées<br>(Kepler-69 b &amp; c)</span></div>
      <div class="stat"><span class="n">{fmt(n_scannees)}</span><span class="l">étoiles TESS passées<br>au crible</span></div>
      <div class="stat"><span class="n">{n_filtres}</span><span class="l">filtres anti-faux-positifs<br>nés d'un vrai cas</span></div>
      <div class="stat"><span class="n">{n_confirmees}</span><span class="l">exoplanète confirmée<br>pour l'instant</span></div>
"""


def remplacer_bloc(contenu, marqueur, nouveau_html):
    debut = f"<!-- {marqueur}:START -->"
    fin = f"<!-- {marqueur}:END -->"
    if debut not in contenu or fin not in contenu:
        sys.exit(f"Erreur : marqueurs {debut} / {fin} introuvables dans index.html")
    avant = contenu.split(debut)[0]
    apres = contenu.split(fin)[1]
    return f"{avant}{debut}{nouveau_html}    {fin}{apres}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", default=".")
    parser.add_argument("--raw-dir", default="raw",
                         help="Dossier contenant les PNG bruts de exoplanet_bls_generic.py")
    args = parser.parse_args()

    site = args.site_dir
    crop_dir = os.path.join(site, "assets", "crop")
    os.makedirs(crop_dir, exist_ok=True)

    resultats = charger_resultats(os.path.join(site, "resultats_candidats.csv"))
    verdicts = charger_verdicts(os.path.join(site, "verdicts.csv"))

    print(f"{len(verdicts)} dossier(s) dans verdicts.csv")
    cartes = []
    for v in verdicts:
        tic_id = v["tic_id"]
        r = resultats.get(tic_id, {})
        crop_box = CROP_DEFAUT
        if v.get("crop_box", "").strip():
            crop_box = tuple(int(x) for x in v["crop_box"].split(","))
        recadrer_image(tic_id, args.raw_dir if os.path.isdir(args.raw_dir) else None, crop_dir, crop_box)
        cartes.append(carte_html(v, r))

    n_scannees = len(resultats) if resultats else 2700
    n_bruts = sum(1 for r in resultats.values() if r.get("n_candidats", "0") not in ("0", ""))
    n_confirmees = sum(1 for v in verdicts if v["stamp_class"] == "confirm")

    with open(os.path.join(site, "index.html"), encoding="utf-8") as f:
        contenu = f.read()

    contenu = remplacer_bloc(contenu, "STATS", stats_html(n_scannees, n_bruts, n_confirmees))
    contenu = remplacer_bloc(contenu, "CARDS", "".join(cartes))

    with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as f:
        f.write(contenu)

    print(f"\nindex.html mis à jour : {n_scannees} étoiles scannées, "
          f"{len(verdicts)} dossier(s) affiché(s), {n_confirmees} confirmée(s)")


if __name__ == "__main__":
    main()
