import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import re
from pathlib import Path
from scipy import stats
import numpy as np
from textwrap import dedent


# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG & STYLING
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Immobilier France",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Source+Sans+3:wght@300;400;500;600&display=swap');

    /* IMPORTANT: Streamlit utilise aussi Material Icons (ou équivalent).
       Si ta CSS casse les spans, tu vois le texte "keyboard_arrow_right". */

    .stApp {
        background: linear-gradient(180deg, #0a0a0f 0%, #121218 50%, #0a0a0f 100%);
    }

    .main .block-container {
        padding: 2rem 3rem;
        max-width: 1400px;
    }

    h1, h2, h3 {
        font-family: 'Playfair Display', Georgia, serif !important;
        color: #f5f0e8 !important;
        letter-spacing: -0.02em;
    }

    h1 {
        font-size: 3.5rem !important;
        font-weight: 700 !important;
        background: linear-gradient(135deg, #f5f0e8 0%, #c9a227 50%, #f5f0e8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 0.5rem !important;
        text-align: center;
    }

    h2 {
        font-size: 2rem !important;
        font-weight: 600 !important;
        border-bottom: 1px solid rgba(201, 162, 39, 0.3);
        padding-bottom: 0.5rem;
        margin-top: 2rem !important;
    }

    /* ✅ MODIF 1: Ne PAS cibler span globalement (ça casse les icônes Streamlit) */
    p, div, li {
        font-family: 'Source Sans 3', -apple-system, sans-serif !important;
        color: #b8b5ad !important;
    }

    /* ✅ MODIF 2: cibler explicitement le texte Streamlit, sans toucher aux icônes */
    .stMarkdown, .stMarkdown p, .stMarkdown div, .stMarkdown li, .stCaption, .stText {
        font-family: 'Source Sans 3', -apple-system, sans-serif !important;
        color: #b8b5ad !important;
    }

    .title-section {
        text-align: center;
        padding: 3rem 2rem 1rem 2rem;
    }

    .title-subtitle {
        font-family: 'Source Sans 3', sans-serif !important;
        font-size: 1.25rem;
        font-weight: 300;
        color: #8a8780 !important;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        margin-bottom: 1rem;
    }

    .presentation-section {
        background: rgba(20, 20, 28, 0.6);
        border: 1px solid rgba(201, 162, 39, 0.15);
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin: 2rem 0 3rem 0;
    }

    .presentation-section h3 {
        color: #c9a227 !important;
        margin-bottom: 1rem;
        font-size: 1.3rem !important;
    }

    .presentation-section p {
        font-size: 1.05rem;
        line-height: 1.8;
        color: #9a9790 !important;
    }

    .map-container {
        background: rgba(20, 20, 28, 0.8);
        border: 1px solid rgba(201, 162, 39, 0.2);
        border-radius: 20px;
        padding: 1rem;
        margin: 1rem 0;
        position: relative;
    }

    .map-overlay {
        position: absolute;
        top: 10px;
        right: 10px;
        background: rgba(201, 162, 39, 0.9);
        color: #0a0a0f;
        padding: 5px 12px;
        border-radius: 8px;
        font-size: 0.75rem;
        font-weight: 600;
        z-index: 1000;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
        background: transparent;
        border-bottom: 1px solid rgba(201, 162, 39, 0.2);
    }

    .stTabs [data-baseweb="tab"] {
        font-family: 'Source Sans 3', sans-serif !important;
        font-size: 1rem;
        font-weight: 500;
        color: #6a6860;
        background: transparent;
        border: none;
        padding: 1rem 0.5rem;
    }

    .stTabs [aria-selected="true"] {
        color: #c9a227 !important;
        border-bottom: 2px solid #c9a227;
    }

    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(201, 162, 39, 0.3), transparent);
        margin: 3rem 0;
    }

    .info-box {
        background: rgba(201, 162, 39, 0.08);
        border-left: 3px solid #c9a227;
        padding: 1rem 1.5rem;
        border-radius: 0 12px 12px 0;
        margin: 1rem 0;
    }

    .stat-card {
        background: linear-gradient(145deg, rgba(30, 30, 40, 0.9), rgba(20, 20, 28, 0.9));
        border: 1px solid rgba(201, 162, 39, 0.2);
        border-radius: 16px;
        padding: 1.5rem;
        text-align: center;
    }

    .stat-value {
        font-family: 'Playfair Display', serif !important;
        font-size: 2rem;
        font-weight: 700;
        color: #c9a227 !important;
    }

    .stat-label {
        font-size: 0.85rem;
        color: #6a6860 !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    iframe {
        border-radius: 16px !important;
        border: none !important;
    }

    /* ✅ MODIF 3: Forcer la bonne font pour les icônes (expander, etc.) */
    [data-testid="stExpanderToggleIcon"],
    [data-testid="stExpanderToggleIcon"] span,
    span.material-icons,
    i.material-icons,
    [class*="material-icons"] {
        font-family: "Material Icons" !important;
        font-weight: normal !important;
        font-style: normal !important;
        letter-spacing: normal !important;
        text-transform: none !important;
        display: inline-block !important;
        white-space: nowrap !important;
        word-wrap: normal !important;
        direction: ltr !important;
        -webkit-font-smoothing: antialiased !important;
    }

</style>
""", unsafe_allow_html=True)



# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def load_html_map(filepath):
    """Load an HTML file and return its content."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()
    

def create_price_by_type_chart(df, selected_dept=None):
    """Create bar chart showing average price by property type."""
    df_valid = df.dropna(subset=['type_de_bien', 'prix']).copy()
    df_valid = df_valid[df_valid['prix'] > 0]
    
    # Filter by department if selected
    if selected_dept and selected_dept != "Tous les départements":
        df_valid = df_valid[df_valid['departement'] == selected_dept]
    
    # Aggregate by type
    type_data = df_valid.groupby('type_de_bien').agg(
        prix_moyen=('prix', 'mean'),
        nombre_annonces=('type_de_bien', 'count')
    ).reset_index()
    
    # Sort by price
    type_data = type_data.sort_values('prix_moyen', ascending=True)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=type_data['type_de_bien'],
        x=type_data['prix_moyen'],
        orientation='h',
        marker=dict(color='#c9a227'),
        text=[f"{x/1000:,.0f}k €" for x in type_data['prix_moyen']],
        textposition='outside',
        textfont=dict(color='#b8b5ad'),
        hovertemplate='<b>%{y}</b><br>Prix moyen: %{x:,.0f} €<br>Annonces: %{customdata}<extra></extra>',
        customdata=type_data['nombre_annonces']
    ))
    
    title = 'Prix moyen par type de bien'
    if selected_dept and selected_dept != "Tous les départements":
        title += f' ({selected_dept})'
    
    fig.update_layout(
        title=title,
        plot_bgcolor='rgba(20, 20, 28, 0.8)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#b8b5ad', family='Source Sans 3'),
        title_font=dict(size=18, color='#f5f0e8', family='Playfair Display'),
        xaxis=dict(
            title='Prix moyen (€)',
            gridcolor='rgba(201, 162, 39, 0.1)'
        ),
        yaxis=dict(
            title='',
            gridcolor='rgba(201, 162, 39, 0.1)'
        ),
        margin=dict(l=150)
    )
    
    return fig

def create_price_distribution_by_city(df, selected_city=None, selected_arrondissement=None):
    """Create smooth distribution curve of price per m² for a selected city with percentage."""
    
    df_valid = df.dropna(subset=['ville', 'prix_m2']).copy()
    df_valid = df_valid[(df_valid['prix_m2'] > 0) & (df_valid['prix_m2'] < 30000)]
    
    # Filter based on selection
    if selected_city == "Toutes les villes" or not selected_city:
        df_city = df_valid
        title = 'Distribution du prix au m² - Toutes les villes'
    elif selected_city == "Paris":
        # Filter by Paris department
        df_city = df_valid[df_valid['departement'] == 'Paris']
        if selected_arrondissement and selected_arrondissement != "Tout Paris":
            # Filter by specific arrondissement
            df_city = df_city[df_city['ville'] == selected_arrondissement]
            title = f'Distribution du prix au m² - {selected_arrondissement}'
        else:
            title = 'Distribution du prix au m² - Paris (tous arrondissements)'
    else:
        # Regular city
        df_city = df_valid[df_valid['ville'] == selected_city]
        title = f'Distribution du prix au m² - {selected_city}'
    
    if len(df_city) < 10:
        fig = go.Figure()
        fig.add_annotation(
            text="Pas assez de données pour cette sélection",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color='#b8b5ad')
        )
    else:
        fig = go.Figure()
        
        # Create KDE curve
        data = df_city['prix_m2'].dropna()
        kde = stats.gaussian_kde(data)
        
        # Create x range
        x_min = data.min()
        x_max = data.max()
        x_range = np.linspace(x_min, x_max, 200)
        
        # Get density and convert to percentage
        # Multiply by bin width to approximate percentage
        density = kde(x_range)
        bin_width = (x_max - x_min) / 200
        percentage = density * bin_width * 100
        
        # Add filled curve
        fig.add_trace(go.Scatter(
            x=x_range,
            y=percentage,
            mode='lines',
            fill='tozeroy',
            fillcolor='rgba(201, 162, 39, 0.3)',
            line=dict(color='#c9a227', width=3),
            hovertemplate='Prix: %{x:,.0f} €/m²<br>%{y:.1f}%<extra></extra>'
        ))
    
    fig.update_layout(
        title=title,
        plot_bgcolor='rgba(20, 20, 28, 0.8)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#b8b5ad', family='Source Sans 3'),
        title_font=dict(size=18, color='#f5f0e8', family='Playfair Display'),
        showlegend=False,
        xaxis=dict(
            title='Prix au m² (€)',
            gridcolor='rgba(201, 162, 39, 0.1)'
        ),
        yaxis=dict(
            title='Pourcentage (%)',
            gridcolor='rgba(201, 162, 39, 0.1)'
        )
    )
    
    return fig

def get_city_options(df):
    """Get list of cities, with Paris handled separately via department."""
    df_valid = df.dropna(subset=['ville', 'prix_m2']).copy()
    
    # Get non-Paris cities (top 30)
    df_non_paris = df_valid[df_valid['departement'] != 'Paris']
    city_counts = df_non_paris['ville'].value_counts()
    top_cities = city_counts.head(30).index.tolist()
    
    # Add Paris as special option (will use department filter)
    return ["Toutes les villes", "Paris"] + sorted(top_cities)

def get_paris_arrondissements(df):
    """Get list of Paris arrondissements sorted logically."""
    df_paris = df[(df['departement'] == 'Paris') & (df['ville'].notna())].copy()
    
    arrondissements = df_paris['ville'].unique().tolist()
    
    # Sort by arrondissement number
    paris_pattern = re.compile(r'(\d+)', re.IGNORECASE)
    
    def sort_key(name):
        match = paris_pattern.search(name)
        if match:
            return int(match.group(1))
        return 999
    
    arrondissements_sorted = sorted(arrondissements, key=sort_key)
    
    return ["Tout Paris"] + arrondissements_sorted

def create_department_chart(df):
    """Create chart showing price per m² by department."""
    df_valid = df.dropna(subset=['departement', 'prix_m2']).copy()
    df_valid = df_valid[(df_valid['prix_m2'] > 0) & (df_valid['prix_m2'] < 20000)]
    
    # Aggregate by department
    dept_data = df_valid.groupby('departement').agg(
        prix_moyen_m2=('prix_m2', 'mean'),
        nombre_annonces=('departement', 'count')
    ).reset_index()
    
    # Sort by price and take top 15
    dept_data = dept_data.sort_values('prix_moyen_m2', ascending=True).tail(15)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=dept_data['departement'],
        x=dept_data['prix_moyen_m2'],
        orientation='h',
        marker=dict(
            color=dept_data['prix_moyen_m2'],
            colorscale=[[0, '#2ecc71'], [0.25, '#f1c40f'], [0.5, '#3498db'], [0.75, '#9b59b6'], [1, '#e74c3c']],
            colorbar=dict(
                title='Prix/m²',
                tickformat='€,.0f'
            )
        ),
        text=[f"{x:,.0f}€" for x in dept_data['prix_moyen_m2']],
        textposition='outside',
        textfont=dict(color='#b8b5ad'),
        hovertemplate='<b>%{y}</b><br>Prix moyen: %{x:,.0f}€/m²<br>Annonces: %{customdata}<extra></extra>',
        customdata=dept_data['nombre_annonces']
    ))
    
    fig.update_layout(
        title='Prix moyen au m² par département (Top 15)',
        plot_bgcolor='rgba(20, 20, 28, 0.8)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#b8b5ad', family='Source Sans 3'),
        title_font=dict(size=18, color='#f5f0e8', family='Playfair Display'),
        xaxis=dict(
            title='Prix moyen au m² (€)',
            gridcolor='rgba(201, 162, 39, 0.1)'
        ),
        yaxis=dict(
            title='',
            gridcolor='rgba(201, 162, 39, 0.1)'
        ),
        margin=dict(l=150)
    )
    
    return fig


# Petit helper affichage
def df_card(df: pd.DataFrame, title: str, filename: str, notes: str = ""):
    st.markdown(f"**{title}** (`{filename}`)")
    if df.empty:
        st.warning(f"Fichier introuvable ou illisible : {filename}")
        return
    st.dataframe(df.head(3), use_container_width=True)
    st.caption(f"📊 {len(df):,} lignes × {len(df.columns)} colonnes")
    if notes:
        st.caption(notes)

@st.cache_data
def load_data():
    """Load and cache the CSV data."""
    df_clean = pd.read_csv('clean_data.csv', sep=',', low_memory=False)
    df_etrePro1 = pd.read_csv('etrePro1.csv', sep=';', low_memory=False)
    df_etrePro2 = pd.read_csv('etrePro2.csv', sep=';', low_memory=False)
    df_paris = pd.read_csv('paris.csv', sep=',', low_memory=False)

    # Convert numeric columns
    numeric_cols = ['surface_terrain', 'surface_interieure', 'surface_exterieure', 
                    'nombre_de_pieces', 'prix', 'prix_m2']
    for col in numeric_cols:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    return df_clean, df_etrePro1, df_etrePro2, df_paris


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # ─────────────────────────────────────────────────────────────────────────
    # TITLE SECTION
    # ─────────────────────────────────────────────────────────────────────────
    
    st.markdown("""
    <div class="title-section">
        <p class="title-subtitle">Analyse du marché immobilier</p>
        <h1>Immobilier France</h1>
    </div>
    """, unsafe_allow_html=True)
    
    
    # ─────────────────────────────────────────────────────────────────────────
    # DATA LOADING
    # ─────────────────────────────────────────────────────────────────────────
    
    df_clean, df_etrePro1, df_etrePro2, df_paris  = load_data()
    

        # Bloc intro stylé comme le reste (mêmes couleurs/typo via CSS existante)
    st.markdown(
        """
        <div class="presentation-section">
            <h3>Présentation</h3>
            <p>Présentation du projet, des données et du traitement appliqué.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Expander 1 : À propos (label sans markdown pour éviter l'affichage littéral des **)
    with st.expander("ℹ️ À propos du projet et des données", expanded=False):
        st.markdown(dedent("""
        ### Source des données

        Les jeux de données étudiés proviennent de deux sites majeurs d'annonces immobilières en France :  
        **SeLoger** et **EtreProprio**. SeLoger : principal portails immobiliers en France acheta ou location bien (~846 000 annonces).
        EtreProprio : biens à vendre directement via agences immobilières (~746 000)

        ### Structure des données récoltées

        - **SeLoger** (`paris.csv`) : ~22 000 annonces sur **Paris** et alentours (30 km).
        - **EtreProprio** (`etrePro1.csv` + `etrePro2.csv`) : ~600 000 annonces **à l’échelle nationale**, collectées par 2 collaborateurs.
        - **Variables clés (attendues)** : type de bien, surfaces (intérieure/terrain/extérieure), nombre de pièces,
          prix, **prix/m²**, ville, code postal, département / code département, url.

        > Données finales **~600k annonces** après consolidation et nettoyage.  
        Types de biens : principalement des appartements et maison mais présente
        aussi studios, lofts, terrains et commerces (~10%).

        ### Méthodes de web scraping

        Deux codes scrapers distincts **EtreProprio** et **SeLoger** adaptés aux contraintes techniques spécifiques.  
        - EtreProprio : analyse HTML, pagination, extraction URLs, stratégie de filtres combinés (département, type de bien, plages de prix, ordre chronologique), limitation 600 annonces par requête  
        - SeLoger : utilisation de Selenium (navigateur réel), exécution JavaScript, contenu dynamique, protections anti-bot, gestion automatique des pop-ups, simulation comportement humain  
        Collecte parallèle (multithreading) avec performance contrôlée.  
        Données extraites : type de bien, prix, surface, prix au m², localisation, caractéristiques logement, lien annonce.

        ### Traitement appliqué

        Le traitement vise à construire **un jeu unique propre** (`clean_data.csv`) à partir des CSV bruts en appliquant notamment :

        - **Harmonisation multi-sources** (noms de colonnes, formats, typages)
        - Conversion des variables en formats numériques cohérents (prix, surfaces, pièces)
        - Exclusion des annonces **incomplètes** et des valeurs **aberrantes** (outliers)
        - Normalisation des localisations (ville, code postal, département)
        - Création / recalcul de **prix au m²** (selon surface pertinente)

        ### Gestion des valeurs manquantes

        Les valeurs manquantes sont traitées au cas par cas :
        - suppression si information critique absente (ex: prix ou localisation)
        - imputations simples possibles si c’est justifiable (ex: surface extérieure non renseignée)

        ### Variables dérivées

        Le traitement inclut la création de variables utiles à l’analyse :
        - **prix_m2**
        - normalisation des champs géographiques (département, arrondissement Paris si présent)
        - indicateurs clés (volume, moyenne prix/m², etc.)

        Le dataset final **`clean_data.csv`** est celui utilisé dans l'application Streamlit.
        """))

    # ----------------------------
    # Expander 2 : Comparaison brutes vs clean
    # ----------------------------
    with st.expander("🔍 Comparaison : Données originales vs. transformées", expanded=False):
        st.markdown("### Données brutes (sources scraping)")
        colA, colB, colC = st.columns(3)

        with colA:
            df_card(
                df_paris,
                "📁 Données ORIGINALES SeLoger",
                "paris.csv",
                notes="Contenu dynamique (Selenium) | Paris + alentours | Champs variables selon annonce"
            )
        with colB:
            df_card(
                df_etrePro1,
                "📁 Données ORIGINALES EtreProprio (lot 1)",
                "EtrePro1.csv",
                notes="HTML statique (Requests/BS4) | Pagination + filtres (prix/type/dep)"
            )
        with colC:
            df_card(
                df_etrePro2,
                "📁 Données ORIGINALES EtreProprio (lot 2)",
                "etrePro2.csv",
                notes="Même logique que lot 1 | Complément de collecte / filtres"
            )

        st.markdown("---")
        st.markdown("### Données nettoyées et consolidées")

        col1, col2 = st.columns([2, 1])

        with col1:
            df_card(
                df_clean,
                "🟢 Données TRANSFORMÉES (final)",
                "clean_data.csv",
                notes="✅ Typages homogènes | ✅ Outliers filtrés | ✅ Colonnes harmonisées | ✅ prix/m² calculé"
            )

        with col2:
            if not df_clean.empty:
                price_col = next((c for c in ["prix"] if c in df_clean.columns), None)
                m2_col = next((c for c in ["prix_m2"] if c in df_clean.columns), None)
                surf_col = next((c for c in ["surface_interieure"] if c in df_clean.columns), None)

                st.markdown("**🧾 Contrôles rapides**")

                if price_col:
                    st.caption(f"Prix min/max : {df_clean[price_col].min():,.0f} / {df_clean[price_col].max():,.0f}")
                if m2_col:
                    st.caption(f"Prix/m² min/max : {df_clean[m2_col].min():,.0f} / {df_clean[m2_col].max():,.0f}")
                if surf_col:
                    st.caption(f"Surface min/max : {df_clean[surf_col].min():,.0f} / {df_clean[surf_col].max():,.0f}")
            else:
                st.info("Ajoute `clean_data.csv` pour activer les contrôles qualité.")

    st.markdown("---")









    # ─────────────────────────────────────────────────────────────────────────
    # STATISTICS SECTION
    # ─────────────────────────────────────────────────────────────────────────
    
    st.markdown("## 📊 Statistiques")
    
    if df_clean is not None:
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-value">{len(df_clean):,}</div>
                <div class="stat-label">Annonces</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            avg_price = df_clean['prix'].mean()
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-value">{avg_price/1000:,.0f}k€</div>
                <div class="stat-label">Prix moyen</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            avg_price_m2 = df_clean['prix_m2'].mean()
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-value">{avg_price_m2:,.0f}€</div>
                <div class="stat-label">Prix moyen/m²</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            avg_surface = df_clean['surface_interieure'].mean()
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-value">{avg_surface:,.0f}m²</div>
                <div class="stat-label">Surface moyenne</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Charts
        chart_tab1, chart_tab2, chart_tab3 = st.tabs([
            "💰 Prix moyen par Type de bien", 
            "🏙️ Distribution par Ville (ou Arrondissement de Paris)", 
            "🗺️ Prix par Département"
        ])
        
        with chart_tab1:
            # Department selector
            dept_list = ["Tous les départements"] + sorted(df_clean['departement'].dropna().unique().tolist())
            selected_dept = st.selectbox(
                "Filtrer par département :",
                dept_list,
                key="dept_selector"
            )
            fig_price_type = create_price_by_type_chart(df_clean, selected_dept)
            st.plotly_chart(fig_price_type, use_container_width=True)
        
        with chart_tab2:
            # City selector
            city_options = get_city_options(df_clean)
            selected_city = st.selectbox(
                "Sélectionner une ville :",
                city_options,
                key="city_selector"
            )
            
            # If Paris is selected, show arrondissement dropdown
            selected_arrondissement = None
            if selected_city == "Paris":
                paris_options = get_paris_arrondissements(df_clean)
                selected_arrondissement = st.selectbox(
                    "Sélectionner un arrondissement :",
                    paris_options,
                    key="arrondissement_selector"
                )
            
            fig_distribution = create_price_distribution_by_city(df_clean, selected_city, selected_arrondissement)
            st.plotly_chart(fig_distribution, use_container_width=True)
        
        with chart_tab3:
            fig_dept = create_department_chart(df_clean)
            st.plotly_chart(fig_dept, use_container_width=True)
    
    else:
        st.warning(f"⚠️ Fichier de données introuvable : Les statistiques ne peuvent pas être affichées.")
    
    st.markdown("---")
    
    # ─────────────────────────────────────────────────────────────────────────
    # MAPS SECTION
    # ─────────────────────────────────────────────────────────────────────────
    
    st.markdown("## 🗺️ Cartographie des prix")
    
    st.markdown("""
    <div class="info-box">
        <p style="margin: 0; color: #c9a227 !important;">
            <strong>Légende :</strong> La couleur représente le prix moyen au m², 
            la taille des cercles indique le nombre d'annonces.<br>
            <strong>💡 Astuce :</strong> Utilisez Ctrl + molette pour zoomer, ou cliquez en dehors de la carte pour la quitter.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Map file paths
    france_map_path = "carte_prix_moyen_dynamique.html"
    paris_map_path = "carte_prix_paris_par_arrondissement.html"
    
    map_tab1, map_tab2 = st.tabs(["🇫🇷 France par département", "🗼 Paris par arrondissement"])
    
    # ─── TAB 1: CARTE FRANCE ───
    with map_tab1:
        st.markdown("### Prix immobiliers par département")
        
        if os.path.exists(france_map_path):
            html_content = load_html_map(france_map_path)
            # Wrap map in a container that allows scrolling past it
            st.markdown('<div class="map-container">', unsafe_allow_html=True)
            components.html(html_content, height=600, scrolling=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error(f"⚠️ Fichier carte introuvable : `{france_map_path}`")
    
    # ─── TAB 2: CARTE PARIS ───
    with map_tab2:
        st.markdown("### Prix immobiliers par arrondissement parisien")
        
        if os.path.exists(paris_map_path):
            html_content = load_html_map(paris_map_path)
            st.markdown('<div class="map-container">', unsafe_allow_html=True)
            components.html(html_content, height=600, scrolling=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error(f"⚠️ Fichier carte introuvable : `{paris_map_path}`")
    
    # ─────────────────────────────────────────────────────────────────────────
    # FOOTER
    # ─────────────────────────────────────────────────────────────────────────
    
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; padding: 2rem 0; color: #4a4a4a;">
        <p style="font-size: 0.85rem; margin: 0;">
            Données immobilières • Visualisation interactive
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()