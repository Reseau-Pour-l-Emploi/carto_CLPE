# Carte des Comités Locaux pour l'Emploi — France

Carte interactive des 362 Comités Locaux pour l'Emploi (CLPE), regroupements de communes sur le territoire français.

## 🚀 Hébergement sur GitHub Pages

### 1. Créer le dépôt

```bash
git init
git add .
git commit -m "Initial commit — Carte CLPE"
git branch -M main
git remote add origin https://github.com/<votre-utilisateur>/<votre-repo>.git
git push -u origin main
```

### 2. Activer GitHub Pages

1. Aller dans **Settings** → **Pages**
2. Source : **Deploy from a branch**
3. Branch : `main` / `/ (root)`
4. Cliquer **Save**

La carte sera disponible à l'adresse :
`https://<votre-utilisateur>.github.io/<votre-repo>/`

> ⚠️ GitHub Pages ne supporte pas les fichiers > 100 Mo. Les fichiers de données ici font entre 400 Ko et 11 Mo, ce qui est dans les limites.

---

## 📁 Structure des fichiers

```
.
├── index.html                      ← Carte Leaflet (HTML + JS)
├── data/
│   ├── reg.json                    ← Contours des régions (436 Ko)
│   ├── dep.json                    ← Contours des départements (1 Mo)
│   ├── clpe.json                   ← Contours des CLPE + couleurs (1,9 Mo)
│   ├── cle-delimitations.json      ← Contours des CLE TZCLD + couleurs (7,9 Mo)
│   └── com.json                    ← Contours des communes, simplifié (11 Mo)
└── README.md
```

## 🗺️ Fonctionnalités

- **362 CLPE** colorés en 6 tonalités de bleu avec algorithme de coloriage de graphe (aucun voisin de même couleur)
- **Survol** → infobulle avec le nom du comité
- **Clic** sur un CLPE → zoom automatique
- **3 listes déroulantes** : Région / Département / CLPE → zoom sur le territoire sélectionné
- **Labels** : noms des régions (zoom faible) et départements (zoom moyen)
- **Communes** visibles discrètement en fond, s'intensifient en zoomant
- Fond de carte sombre (CartoDB Dark)

## 📊 Sources des données

- Fichiers GeoJSON fournis par l'utilisateur (régions, départements, communes, CLPE)
- Géométries simplifiées pour des performances optimales en web
