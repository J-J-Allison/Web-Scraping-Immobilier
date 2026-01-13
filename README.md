# 🏠 Projet de Web-Scraping et Data-Visualisation du Marché Immobilier Français

> **De la collecte automatisée à la visualisation interactive**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Selenium](https://img.shields.io/badge/Selenium-WebDriver-green.svg)](https://www.selenium.dev/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-red.svg)](https://streamlit.io/)
[![Folium](https://img.shields.io/badge/Folium-Maps-darkgreen.svg)](https://python-visualization.github.io/folium/)

## 📋 Présentation

Ce projet end-to-end de data engineering et data analysis porte sur le marché immobilier français. Il combine web-scraping multi-sources, traitement de données, analyse exploratoire et visualisation interactive via une application Streamlit. Plus de **617 000 annonces** ont été collectées et analysées.

**Institution :** Université Paris Sorbonne  
**Formation :** DU Sorbonne Data Analytics  
**Cours :** Programmation Python et Web Scraping

### 👥 Auteurs

- NADAT Sufyan
- ALLISON Jacques
- MANELLI Cédric

---

## 🎯 Objectifs

1. Constituer une base de données immobilières exploitable à partir d'annonces web
2. Harmoniser des données issues de sources hétérogènes
3. Nettoyer et filtrer les données pour obtenir des indicateurs cohérents
4. Restituer l'information de manière lisible (statistiques et cartes interactives)
5. Déployer une application Streamlit accessible à un public semi-technique

---

## 📊 Sources de Données

| Source | Méthode | Particularités |
|--------|---------|----------------|
| **EtreProprio** | Requests + BeautifulSoup | Scraping HTML statique, gestion de pagination |
| **SeLoger** | Selenium + undetected_chromedriver | Contenu dynamique, anti-bot, Shadow DOM |

### Variables collectées

| Variable | Description |
|----------|-------------|
| `type_bien` | Appartement, maison, terrain, commerce |
| `prix` | Prix de vente (€) |
| `surface_interieure` | Surface habitable (m²) |
| `surface_terrain` | Surface terrain pour terrains nus (m²) |
| `surface_exterieure` | Balcon, terrasse, jardin (m²) |
| `nb_pieces` | Nombre de pièces |
| `nb_chambres` | Nombre de chambres |
| `etage` | Étage du bien |
| `ville` | Nom de la ville |
| `code_postal` | Code postal |
| `departement` | Département |
| `classe_energetique` | DPE du bien |
| `prix_m2` | Prix au mètre carré (calculé) |

**Volume final :** 617 000+ annonces

---

## 🔬 Méthodologie

### Étape 1 : Collecte des Données

#### EtreProprio
- Analyse de la structure HTML et gestion de la pagination
- Stratégie de filtrage pour contourner la limite de 600 annonces par recherche
- Filtres : département, type de bien, plages de prix, ordre chronologique

#### SeLoger (Scraper avancé)
- **Selenium + undetected_chromedriver** pour éviter la détection
- **Gestion automatique des popups** (cookies, newsletters, Shadow DOM)
- **Simulation du comportement humain** :
  - Défilement avec courbe d'accélération naturelle
  - Pauses aléatoires (8-15 pages)
  - Variation de la taille de fenêtre
  - User-agents et résolutions d'écran variables
- **Exécution parallèle** : jusqu'à 10 navigateurs simultanés

### Étape 2 : Prétraitement et Nettoyage
- Conversion des variables en formats numériques
- Exclusion des annonces incomplètes ou aberrantes
- Harmonisation des noms de variables
- Création de la variable `prix_m2`

### Étape 3 : Géocodage
- API Nominatim (via geopy) pour obtenir les coordonnées géographiques
- Génération de fichiers GeoJSON (départements + arrondissements parisiens)

### Étape 4 : Visualisation
- Cartes interactives Folium
- Dashboard Streamlit avec graphiques Plotly

---

## 📈 Résultats et Dashboard Streamlit

### Structure de l'Application

```
┌─────────────────────────────────────────┐
│  1. Présentation du projet              │
├─────────────────────────────────────────┤
│  2. Statistiques                        │
│     ├── KPI principaux                  │
│     ├── Prix moyen par type de bien     │
│     ├── Distribution prix/m² par ville  │
│     └── Top 15 départements les + chers │
├─────────────────────────────────────────┤
│  3. Cartographie interactive            │
│     ├── Carte France (départements)     │
│     └── Carte Paris (arrondissements)   │
└─────────────────────────────────────────┘
```

### Indicateurs Clés (KPI)

| KPI | Description |
|-----|-------------|
| Nombre d'annonces | Volume total du dataset |
| Prix moyen | Moyenne des prix de vente |
| Prix moyen au m² | Indicateur de cherté |
| Surface intérieure moyenne | Taille moyenne des biens |

### Cartes Interactives

- **Carte France** : Bulles par département (taille = volume, couleur = prix/m²)
- **Carte Paris** : Zoom sur les 20 arrondissements
- Affichage au clic : prix moyen au m² et nombre d'annonces

---

## 🛠️ Technologies

```
# Scraping
requests            # Requêtes HTTP
beautifulsoup4      # Parsing HTML
selenium            # Automatisation navigateur
undetected-chromedriver  # Anti-détection

# Traitement
pandas              # Manipulation des données
numpy               # Calcul numérique
geopy               # Géocodage (Nominatim)

# Visualisation
matplotlib          # Graphiques statiques
plotly              # Graphiques interactifs
folium              # Cartes interactives

# Application
streamlit           # Dashboard web
```

---

## 📁 Structure du Projet

```
├── README.md
├── Rapport_Projet.pdf                 # Rapport complet
├── scraping/
│   ├── scraper_etreproprio.py         # Scraper EtreProprio
│   └── scraper_seloger.py             # Scraper SeLoger (Selenium)
├── data/
│   ├── raw/                           # Données brutes CSV
│   ├── cleaned/                       # Données nettoyées
│   └── geojson/                       # Fichiers géographiques
│       ├── departements.geojson
│       └── arrondissements_paris.geojson
├── notebooks/
│   ├── nettoyage.ipynb                # Prétraitement
│   ├── geocodage.ipynb                # Géocodage
│   └── analyse_exploratoire.ipynb     # Analyse
├── maps/
│   ├── carte_france.html              # Carte Folium France
│   └── carte_paris.html               # Carte Folium Paris
└── app/
    └── streamlit_app.py               # Application Streamlit
```

---

## 🚀 Démarrage Rapide

### Prérequis

```bash
pip install requests beautifulsoup4 selenium undetected-chromedriver
pip install pandas numpy geopy
pip install matplotlib plotly folium streamlit
```

### Exécution du Scraping

```bash
# Scraper EtreProprio
python scraping/scraper_etreproprio.py

# Scraper SeLoger (nécessite ChromeDriver)
python scraping/scraper_seloger.py
```

### Lancement de l'Application

```bash
# Cloner le dépôt
git clone https://github.com/VOTRE_NOM/immobilier-france-scraping.git
cd immobilier-france-scraping

# Lancer Streamlit
streamlit run app/streamlit_app.py
```

---

## ⚠️ Limites du Projet

| Limite | Description |
|--------|-------------|
| **Couverture** | Deux plateformes uniquement, certaines zones sous-représentées |
| **Fraîcheur** | Données figées à un instant donné, pas de dimension temporelle |
| **Qualité** | Surfaces déclaratives, pas d'info sur l'état général du bien |
| **Analyse** | Descriptive uniquement, pas de modélisation prédictive |

---

## 🔮 Évolutions Possibles

- Intégration de médianes et quantiles pour limiter l'effet des outliers
- Ajout d'une dimension temporelle (suivi des prix)
- Développement de modèles prédictifs (prix estimé)
- Intégration d'autres sources de données (notaires, INSEE)
- Segmentation fine (neuf/ancien, standing, classe énergétique)

---

## 📜 Licence

Ce projet a été réalisé dans un cadre académique dans le cadre du DU Sorbonne Data Analytics de l'Université Paris Sorbonne.

---
