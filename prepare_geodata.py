#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_geodata.py
==================
Script de préparation des données géographiques pour la carte CLPE.

Produit trois fichiers à placer à la racine du dépôt :
  topo_communes.json    — TopoJSON des communes (WGS-84, simplifié)
  departements.geojson  — GeoJSON des départements
  regions.geojson       — GeoJSON des régions

Les DOM (971–976) sont repositionnés près de la métropole.

─── PRÉREQUIS ───────────────────────────────────────────────────────────
  pip install requests geopandas topojson numpy shapely

─── USAGE ───────────────────────────────────────────────────────────────
  python prepare_geodata.py

Source des données : geo.api.gouv.fr (Etalab / DINUM)
Les contours de communes intègrent déjà les communes déléguées / associées
telles que fusionnées dans les « communes nouvelles » (données INSEE courantes).

Pour forcer l'usage d'ADMIN-EXPRESS-COG-CARTO-PE via le WFS IGN
(notamment pour récupérer les géométries des communes associées en tant
qu'entités séparées), activez le flag USE_IGN_WFS = True ci-dessous.
"""

import json
import os
import sys
import requests
import geopandas as gpd
from shapely.affinity import translate, scale as affine_scale
from shapely.ops import unary_union
import topojson as tp

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

# Tolérance de simplification (degrés décimaux)
SIMPLIFY_COMMUNES = 0.003   # ~250 m
SIMPLIFY_DEPREG   = 0.002   # ~175 m

# Activer le WFS IGN pour ADMIN-EXPRESS-COG-CARTO-PE
# (plus précis mais requiert davantage de requêtes)
USE_IGN_WFS = False

# Décalages pour repositionner les DOM proches de la métropole
# Métropole : lon ∈ [-5, 9], lat ∈ [41, 51]
# Format : code_dep → {dx: Δlon, dy: Δlat, sc: facteur_échelle}
DOM_DEP_TRANSFORMS = {
    "971": dict(dx= 57.8, dy= 30.2, sc=1.0),   # Guadeloupe  → ~ -3.7°, 47.2°
    "972": dict(dx= 59.3, dy= 32.2, sc=1.0),   # Martinique  → ~ -1.8°, 47.0°
    "973": dict(dx= 53.2, dy= 14.2, sc=0.22),  # Guyane (réduit × 0.22)
    "974": dict(dx=-44.2, dy= 67.2, sc=1.0),   # La Réunion  → ~11.3°, 46.5°
    "976": dict(dx=-34.3, dy= 59.3, sc=1.0),   # Mayotte     → ~10.9°, 46.5°
}

# Correspondance code_région DOM → code_dep (pour appliquer le même décalage)
DOM_REG_TRANSFORMS = {
    "01": "971",   # Guadeloupe
    "02": "972",   # Martinique
    "03": "973",   # Guyane
    "04": "974",   # La Réunion
    "06": "976",   # Mayotte
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)


def apply_dom_transform(geom, t, cx, cy):
    """Mise à l'échelle (depuis centroïde) puis translation."""
    if t["sc"] != 1.0:
        geom = affine_scale(geom, xfact=t["sc"], yfact=t["sc"], origin=(cx, cy))
    return translate(geom, xoff=t["dx"], yoff=t["dy"])


def reproject_gdf_by_dep(gdf, code_col, transform_map):
    """
    Déplace les géométries du GDF dont `code_col` est dans `transform_map`.
    L'origine de la mise à l'échelle est le centroïde moyen du groupe.
    """
    gdf = gdf.copy()
    for code, t in transform_map.items():
        mask = gdf[code_col] == code
        if not mask.any():
            continue
        cx = float(gdf.loc[mask, "geometry"].centroid.x.mean())
        cy = float(gdf.loc[mask, "geometry"].centroid.y.mean())
        gdf.loc[mask, "geometry"] = gdf.loc[mask, "geometry"].apply(
            lambda g: apply_dom_transform(g, t, cx, cy)
        )
    return gdf


# ─── CHARGEMENT VIA GEO.API.GOUV.FR ──────────────────────────────────────────

GEOAPI = "https://geo.api.gouv.fr"


def geoapi_get(endpoint, timeout=300):
    url = f"{GEOAPI}{endpoint}"
    log(f"  GET {url}")
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def load_communes_geoapi():
    log("  Chargement des communes via geo.api.gouv.fr…")
    data = geoapi_get(
        "/communes"
        "?format=geojson"
        "&geometry=contour"
        "&fields=nom,code,codeDepartement"
    )
    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    gdf = gdf.rename(columns={
        "code":             "INSEE_COM",
        "nom":              "NOM",
        "codeDepartement":  "DEP",
    })
    # Assure 5 caractères (certaines API renvoient le code sans zéro initial)
    gdf["INSEE_COM"] = gdf["INSEE_COM"].astype(str).str.zfill(5)
    gdf["DEP"]       = gdf["DEP"].astype(str).str.zfill(2)
    return gdf[["INSEE_COM", "NOM", "DEP", "geometry"]]


def load_departements_geoapi():
    log("  Chargement des départements…")
    data = geoapi_get("/departements?format=geojson&geometry=contour&fields=nom,code")
    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    gdf = gdf.rename(columns={"code": "CODE", "nom": "NOM"})
    gdf["CODE"] = gdf["CODE"].astype(str).str.zfill(2)
    return gdf[["CODE", "NOM", "geometry"]]


def load_regions_geoapi():
    log("  Chargement des régions…")
    data = geoapi_get("/regions?format=geojson&geometry=contour&fields=nom,code")
    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    gdf = gdf.rename(columns={"code": "CODE", "nom": "NOM"})
    gdf["CODE"] = gdf["CODE"].astype(str).str.zfill(2)
    return gdf[["CODE", "NOM", "geometry"]]


# ─── CHARGEMENT VIA WFS IGN (optionnel) ───────────────────────────────────────

IGN_WFS = "https://data.geopf.fr/wfs/ows"


def fetch_wfs_paginated(typename, page=1000):
    """Récupère toutes les entités d'une couche WFS IGN en paginant."""
    features, start = [], 0
    log(f"  WFS {typename}", end="")
    while True:
        r = requests.get(IGN_WFS, params={
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": typename, "OUTPUTFORMAT": "application/json",
            "COUNT": page, "STARTINDEX": start,
        }, timeout=120)
        r.raise_for_status()
        batch = r.json().get("features", [])
        features.extend(batch)
        print(f" {len(features)}", end="", flush=True)
        if len(batch) < page:
            break
        start += page
    print()
    return {"type": "FeatureCollection", "features": features}


def load_communes_ign():
    """
    Charge communes principales + communes associées/déléguées depuis WFS IGN.
    Fusionne les géométries des communes déléguées sur leur commune principale.
    """
    log("  Chargement communes principales (WFS IGN)…")
    fc_com = fetch_wfs_paginated("ADMINEXPRESS-COG-CARTO-PE.LATEST:commune")
    gdf_com = gpd.GeoDataFrame.from_features(fc_com["features"], crs="EPSG:4326")
    gdf_com.columns = [c.lower() for c in gdf_com.columns]

    # Colonnes WFS ADMIN-EXPRESS (minuscules)
    insee_col = next((c for c in gdf_com.columns if "insee_com" in c and "d" not in c[-2:]), "insee_com")
    dep_col   = next((c for c in gdf_com.columns if "insee_dep" in c), "insee_dep")
    nom_col   = next((c for c in gdf_com.columns if c in ("nom", "nom_m")), "nom")

    gdf_com = gdf_com.rename(columns={
        insee_col: "INSEE_COM",
        dep_col:   "DEP",
        nom_col:   "NOM",
    })
    gdf_com["INSEE_COM"] = gdf_com["INSEE_COM"].astype(str).str.zfill(5)

    log("  Chargement communes associées/déléguées (WFS IGN)…")
    fc_cad = fetch_wfs_paginated("ADMINEXPRESS-COG-CARTO-PE.LATEST:commune_associee_ou_deleguee")
    if fc_cad["features"]:
        gdf_cad = gpd.GeoDataFrame.from_features(fc_cad["features"], crs="EPSG:4326")
        gdf_cad.columns = [c.lower() for c in gdf_cad.columns]
        # insee_com_d = code de la commune de destination (commune principale)
        dest_col = next((c for c in gdf_cad.columns if "com_d" in c or "comd" in c), None)
        if dest_col:
            gdf_cad = gdf_cad[[dest_col, "geometry"]].copy()
            gdf_cad[dest_col] = gdf_cad[dest_col].astype(str).str.zfill(5)
            extra = (
                gdf_cad.groupby(dest_col)["geometry"]
                .apply(lambda gs: unary_union(list(gs)))
                .reset_index()
                .rename(columns={dest_col: "INSEE_COM", "geometry": "extra"})
            )
            gdf_com = gdf_com.merge(extra, on="INSEE_COM", how="left")
            has_extra = gdf_com["extra"].notna()
            gdf_com.loc[has_extra, "geometry"] = gdf_com.loc[has_extra].apply(
                lambda r: unary_union([r.geometry, r["extra"]]), axis=1
            )
            gdf_com = gdf_com.drop(columns=["extra"])

    return gdf_com[["INSEE_COM", "NOM", "DEP", "geometry"]]


# ─── EXPORT ───────────────────────────────────────────────────────────────────

def export_topojson(gdf, path, obj_name="communes"):
    log(f"  Export TopoJSON → {path}")
    topo = tp.Topology({obj_name: gdf}, prequantize=1_000_000, topology=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(topo.to_json())
    log(f"    Taille : {os.path.getsize(path)/1e6:.1f} Mo")


def export_geojson(gdf, path):
    log(f"  Export GeoJSON → {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(gdf.to_json(ensure_ascii=False))
    log(f"    Taille : {os.path.getsize(path)/1e6:.1f} Mo")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    log("=" * 62)
    log("  Préparation des données géographiques — Carte CLPE")
    log("=" * 62)

    # ── [1/3] Communes ──────────────────────────────────────────
    log("\n[1/3] Communes")
    if USE_IGN_WFS:
        gdf_com = load_communes_ign()
    else:
        gdf_com = load_communes_geoapi()
    log(f"  {len(gdf_com)} communes chargées")

    gdf_com = reproject_gdf_by_dep(gdf_com, "DEP", DOM_DEP_TRANSFORMS)
    gdf_com["geometry"] = gdf_com.geometry.simplify(SIMPLIFY_COMMUNES, preserve_topology=True)
    gdf_com = gdf_com[["INSEE_COM", "NOM", "geometry"]]
    export_topojson(gdf_com, "topo_communes.json", obj_name="communes")

    # ── [2/3] Départements ──────────────────────────────────────
    log("\n[2/3] Départements")
    gdf_dep = load_departements_geoapi()
    gdf_dep = reproject_gdf_by_dep(gdf_dep, "CODE", DOM_DEP_TRANSFORMS)
    gdf_dep["geometry"] = gdf_dep.geometry.simplify(SIMPLIFY_DEPREG, preserve_topology=True)
    export_geojson(gdf_dep, "departements.geojson")

    # ── [3/3] Régions ────────────────────────────────────────────
    log("\n[3/3] Régions")
    gdf_reg = load_regions_geoapi()
    # Convertit la map région→dep en map région→transform
    dom_reg_t = {
        reg: DOM_DEP_TRANSFORMS[dep]
        for reg, dep in DOM_REG_TRANSFORMS.items()
        if dep in DOM_DEP_TRANSFORMS
    }
    gdf_reg = reproject_gdf_by_dep(gdf_reg, "CODE", dom_reg_t)
    gdf_reg["geometry"] = gdf_reg.geometry.simplify(SIMPLIFY_DEPREG, preserve_topology=True)
    export_geojson(gdf_reg, "regions.geojson")

    log("\n✓  Terminé. Fichiers à déposer à la racine du dépôt :")
    log("     topo_communes.json")
    log("     departements.geojson")
    log("     regions.geojson")
    log("     communes_clpe.csv  (votre fichier)")
    log("     index.html         (l'application)")


if __name__ == "__main__":
    main()
