import requests
import bs4
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
from typing import Callable, Any
import csv


def get_page(url_request):
    """
    Récupère le contenu HTML d'une page web et le parse avec BeautifulSoup.

    Paramètre
    ---------
    url_request : str
        URL de la page à récupérer.

    Retour
    ------
    page : bs4.BeautifulSoup
        Objet BeautifulSoup représentant le DOM HTML de la page,
        prêt à être analysé (find, find_all, etc.).
    """
    request_text = requests.get(
        url_request,
        headers={"User-Agent": "Python for data science 'appart project'"}
    ).content

    page = bs4.BeautifulSoup(request_text, "lxml")
    return page



def scrap_pages(max_pages: int, url: str) -> list[str]:
    """
    Parcourt plusieurs pages de résultats d'annonces et extrait les URLs des annonces.

    Paramètres
    ----------
    max_pages : int
        Nombre maximum de pages à parcourir (limite de sécurité pour éviter
        des boucles trop longues ou infinies). Aussi parceque le nombre limité de page à parcour est 30 sur 
        le site EtreProprio.

    url : str
        URL de départ de la première page de résultats.

    Retour
    ------
    hrefs : list[str]
        Liste des URLs d'annonces collectées sur l'ensemble des pages parcourues.
    """
    hrefs = []
    pages_done = 0

    for _ in range(max_pages):
        main_page = get_page(url)

        ep_search_list_wrapper = main_page.find("div", {"class": "ep-search-list-wrapper"})
        if ep_search_list_wrapper is None:
            print(f"[scrap_pages] Stop: wrapper introuvable (pages_done={pages_done}, hrefs={len(hrefs)})")
            break  # structure inattendue

        links_before = len(hrefs)
        for a in ep_search_list_wrapper.find_all("a", href=True):
            hrefs.append(a["href"])
        links_added = len(hrefs) - links_before

        # print de contrôle
        pages_done += 1
        if pages_done % 5 == 0:
            print(f"[scrap_pages] {pages_done} pages parcourues, +{links_added} liens sur la dernière page, total={len(hrefs)}")

        class_next_page = main_page.find("div", {"class": "ep-nav-next"})
        if not class_next_page:
            # print de contrôle
            print(f"[scrap_pages] Stop: pas de page suivante (pages_done={pages_done}, total={len(hrefs)})")
            break  # pas de page suivante

        a_next_page = class_next_page.find("a", href=True)
        if not a_next_page:
            print(f"[scrap_pages] Stop: lien next introuvable (pages_done={pages_done}, total={len(hrefs)})")
            break

        url = a_next_page["href"]

    print(f"[scrap_pages] Terminé: pages={pages_done}, hrefs={len(hrefs)}")
    return hrefs



def scrape_url(nbr_pages_max : int, dep: str, bien_code: str, prix_min: str, prix_max: str) -> list[str]:
    """
    Paramètres
    ----------
    max_pages: 
        nbr max de page à parcourir pour les paramètres séléctionnés

    dep : str
        Code du département (ex: "01", "75", "92").

    bien_code : str
        Code du type de bien utilisé par le site
        (ex: "tl" = terrain, "th" = maison, "tf" = appartement, "tc" = commerce).

    prix_min : str
        Borne basse du prix utilisée dans l'URL de recherche.

    prix_max : str
        Borne haute du prix utilisée dans l'URL de recherche.

    Retour
    ------
    hrefs : list[str]
        Liste des URLs des annonces correspondant aux critères fournis.
    """
    date_order = ['.odd.g1', '.oda.g1']
    

    url1 = f"https://www.etreproprio.com/annonces/{bien_code}.p{prix_min}{prix_max}.ld{dep}{date_order[0]}#list"
    main_page = get_page(url1)

    # nombre d'annonces
    nbr_annonces = 0
    ep_count = main_page.find("h1", {"class": "ep-count title-underline"})
    if ep_count is not None:
        txt = ep_count.get_text(" ", strip=True)
        match = re.search(r"(\d+)\s+annonces", txt)
        nbr_annonces = int(match.group(1)) if match else 0

    print(f"[scrape_url] START dep={dep} bien={bien_code} prix={prix_min}{prix_max} annonces={nbr_annonces}")

    hrefs = scrap_pages(nbr_pages_max, url1)

    if nbr_annonces > 600:
        nbr_annonce_rest = nbr_annonces - 600
        nbr_page_rest = math.ceil((nbr_annonce_rest) / 20)
        print(
            f"[scrape_url] dep={dep} bien={bien_code} prix={prix_min}{prix_max} "
            f"-> annonces>600, pages extra={nbr_page_rest} ({nbr_annonce_rest} annonces)"
        )
        url2 = f"https://www.etreproprio.com/annonces/{bien_code}.p{prix_min}{prix_max}.ld{dep}{date_order[1]}#list"
        hrefs.extend(scrap_pages(nbr_page_rest, url2))

    print(f"[scrape_url] DONE  dep={dep} bien={bien_code} prix={prix_min}{prix_max} -> hrefs={len(hrefs)}")
    return hrefs

    


def infer_type_from_href(href: str) -> str | None:
    """
    Paramètre
    ---------
    href : str
        URL de l'annonce immobilière.

    Retour
    ------
    type_bien : str | None
        Type de bien déduit à partir de l'URL parmi :
        - "terrain"
        - "maison"
        - "appartement"
        - "commerce"

        Retourne None si aucun type n'est identifié.
    """
    href_l = href.lower()

    if "terrain" in href_l:
        return "terrain"

    if "maison" in href_l:
        return "maison"

    if "appartement" in href_l:
        return "appartement"

    commerce_keywords = [
        "commerce", "commercial", "commerciaux",
        "restauration", "restaurant",
        "bureau", "bureau-local",
        "local", "cave", "boutique"
    ]
    if any(k in href_l for k in commerce_keywords):
        return "commerce"

    return None





def extract_fn(href: str) -> dict | None:
    """
    Paramètre
    ---------
    href : str
        URL de l'annonce immobilière à analyser.

    Retour
    ------
    data : dict | None
        Dictionnaire contenant les informations extraites de l'annonce avec
        les clés suivantes :

        - "prix"
        - "type_de_bien"
        - "url_annonce"
        - "surface_terrain"
        - "surface_interieure"
        - "surface_jardin"
        - "nombre_de_pieces"
        - "ville"
        - "code_postal"

        Retourne None si l'annonce est invalide ou si les informations
        nécessaires ne peuvent pas être extraites.
        Fait de l'extraction d'information et exclu les unités présentes (120m2 -> 120 ...)
    """

    type_bien = infer_type_from_href(href)
    if type_bien is None:
        return None

    page = get_page(href)
    if page is None:
        return None

    ep_price = page.find("div", {"class": "ep-price"})
    if ep_price is None:
        return None

    m_price = RE_PRICE.search(ep_price.get_text(" ", strip=True))
    if not m_price:
        return None

    ep_dtl = page.find("div", {"class": "ep-area"})
    ep_room = page.find("div", {"class": "ep-room"})
    ep_loc = page.find("div", {"class": "ep-loc"})

    if ep_dtl is None or ep_loc is None:
        return None

    price = m_price.group(1).replace(" ", "").replace("\u00A0", "")

    m_surface = RE_SURFACE.search(ep_dtl.get_text(" ", strip=True))
    surface = m_surface.group(1).replace(" ", "").replace("\u00A0", "") if m_surface else None

    ep_dtl_garden = ep_dtl.find("span", {"class": "dtl-main-surface-terrain"})
    if ep_dtl_garden:
        m_garden = RE_GARDEN.search(ep_dtl_garden.get_text(" ", strip=True))
        surface_garden = m_garden.group(0).replace(" ", "").replace("\u00A0", "") if m_garden else None
    else:
        surface_garden = None

    if ep_room:
        m_room = RE_ROOM.search(ep_room.get_text(" ", strip=True))
        room = m_room.group(0) if m_room else None
    else:
        room = None

    m_loc = RE_LOC.search(ep_loc.get_text(" ", strip=True))
    if not m_loc:
        return None

    ville = m_loc.group(1)
    code_postal = m_loc.group(2)

    if type_bien == "terrain":
        surface_terrain = surface
        surface_interieure = None
    else:
        surface_interieure = surface
        surface_terrain = None

    return {
        "prix": price,
        "type_de_bien": type_bien,
        "url_annonce": href,
        "surface_terrain": surface_terrain,
        "surface_interieure": surface_interieure,
        "surface_jardin": surface_garden,
        "nombre_de_pieces": room,
        "ville": ville,
        "code_postal": code_postal,
    }


def collect_urls(
    lst_dep: list[str],
    nbr_pages_max : int,
    list_prix_min: list[str],
    list_prix_max: list[str],
    bien_code: str,
    max_workers: int = 10,
) -> list[str]:
    """
    Paramètres
    ----------
    lst_dep : list[str]
        Liste des codes départements à parcourir.

    list_prix_min : list[str]
        Liste des bornes basses de prix utilisées pour la recherche.

    list_prix_max : list[str]
        Liste des bornes hautes de prix utilisées pour la recherche.

    bien_code : str
        Code du type de bien utilisé par le site
        (ex: "tl", "th", "tf", "tc").

    max_workers : int, optionnel
        Nombre maximal de threads utilisés pour la collecte parallèle.

    Retour
    ------
    href_list : list[str]
        Liste dédupliquée des URLs d'annonces collectées.
    """

    price_pairs = list(zip(list_prix_min, list_prix_max))
    href_list: list[str] = []

    total_tasks = len(lst_dep) * len(price_pairs)
    done_tasks = 0

    # print controle
    print(f"[collect_urls] START bien={bien_code} tasks={total_tasks} workers={max_workers} pages max {nbr_pages_max}")

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}

        for dep in lst_dep:
            for prix_min, prix_max in price_pairs:
                fut = ex.submit(
                    scrape_url,
                    nbr_pages_max=nbr_pages_max,
                    dep=dep,
                    bien_code=bien_code,
                    prix_min=prix_min,
                    prix_max=prix_max,
                )
                futures[fut] = (dep, prix_min, prix_max)

        for fut in as_completed(futures):
            dep, prix_min, prix_max = futures[fut]
            done_tasks += 1
            try:
                hrefs = fut.result()
                href_list.extend(hrefs)
            except Exception as e:
                print(f"[collect_urls] ERROR dep={dep} prix={prix_min}{prix_max} -> {e}")

            if done_tasks % 50 == 0 or done_tasks == total_tasks:
                print(f"[collect_urls] Progress {done_tasks}/{total_tasks} | urls_collectées={len(href_list)}")

    before = len(href_list)
    href_list = list(dict.fromkeys(href_list))
    after = len(href_list)
    print(f"[collect_urls] DONE  bien={bien_code} urls_brutes={before} urls_uniques={after}")
    return href_list




def collect_fn(
    href_list: list[str],
    extract_fn: Callable[[str], dict | None],
    info_bien_dic: dict[str, list],
    max_workers: int = 15,
    verbose: bool = False,
) -> tuple[list[dict], dict[str, list]]:
    """
    Parallélise l'extraction d'infos sur chaque URL d'annonce.

    - href_list : liste d'URLs
    - extract_fn : fonction du style extract_fn(href, var) -> dict | None
    - var : ex "terrain"
    - info_bien_dic : dict de listes à remplir
    - max_workers : nombre de threads
    - verbose : print chaque row si True

    Retourne : (results, info_bien_dic)
    """
    results: list[dict] = []

    total = len(href_list)
    done = 0
    ok = 0
    skipped = 0
    print(f"[parse_ads_parallel] START urls={total} workers={max_workers}")

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(extract_fn, href): href for href in href_list}

        for fut in as_completed(futures):
            done += 1
            href = futures[fut]
            try:
                row = fut.result()
                if row is None:
                    skipped += 1
                else:
                    ok += 1
                    if verbose:
                        print(row)
                    results.append(row)
            except Exception as e:
                print(f"[parse_ads_parallel] ERROR href={href} -> {e}")

            if done % 200 == 0 or done == total:
                print(f"[parse_ads_parallel] Progress {done}/{total} | ok={ok} skipped={skipped}")

    for row in results:
        for k in info_bien_dic:
            info_bien_dic[k].append(row.get(k))

    print(f"[parse_ads_parallel] DONE  rows={len(results)} colonnes={len(info_bien_dic)}")
    return info_bien_dic


def dict_to_csv(data: dict[str, list], filename: str):
    """
    Paramètres
    ----------
    data : dict[str, list]
        Dictionnaire où chaque clé correspond à une colonne du fichier CSV
        et chaque valeur à une liste de données.

    filename : str
        Nom ou chemin du fichier CSV à créer.

    Retour
    ------
    None
    """
    keys = data.keys()
    rows = zip(*data.values())

    n_rows = len(next(iter(data.values()))) if data else 0
    print(f"[dict_to_csv] START filename={filename} rows={n_rows} cols={len(data)}")

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(keys)
        writer.writerows(rows)

    print(f"[dict_to_csv] DONE  filename={filename}")


###############################################################################
#####################  CODE HERE ##############################################
###############################################################################



RE_PRICE   = re.compile(r"(\d[\d\s\u00A0]*)")
RE_SURFACE = re.compile(r"(\d[\d\s\u00A0]*)")
RE_GARDEN  = re.compile(r"\d[\d\u00A0]*")
RE_ROOM    = re.compile(r"\d+")
RE_LOC     = re.compile(r"—\s*(.*?)\s+(\d{5})\s*—")


# paramètre standards
'''
lst_dep = [f"{i:02d}" for i in range(1, 96)]
lst_dep.remove("20")
nbr_pages_max = 30
list_bien = ["th", "tf", "tl", "tc"]
'''


list_prix_min = ["50000", "75000", "100000", "120000", "140000", "160000",
                 "180000", "200000", "240000", "260000", "280000", "300000",
                 "325000", "350000", "375000", "400000", "450000", "500000",
                 "600000", "700000", "800000", "900000", "1000000"]
list_prix_max = ["-75000", "-100000", "-120000", "-140000", "-160000", "-180000",
                 "-200000", "-240000", "-260000", "-280000", "-300000", "-325000",
                 "-350000", "-375000", "-400000", "-450000", "-500000", "-600000",
                 "-700000", "-800000", "-900000", "-1000000", ""]


#paramètres simulation:
lst_dep = ['66']
nbr_pages_max = 1
list_bien = ["tf"]


print(f"[MAIN] START biens={list_bien} deps={len(lst_dep)} tranches_prix={len(list_prix_min)}")

for bien in list_bien:
    print(f"\n[MAIN] ===== Traitement bien_code={bien} =====")

    MAX_WORKERS = 10
    href_list = collect_urls(
        lst_dep=lst_dep,
        nbr_pages_max = nbr_pages_max,
        list_prix_min=list_prix_min,
        list_prix_max=list_prix_max,
        bien_code=bien,
        max_workers=MAX_WORKERS,
    )
    print(f"[MAIN] Total hrefs uniques pour {bien}: {len(href_list)}")

    MAX_WORKERS = 15
    info_bien_dic = {
        "prix": [],
        "type_de_bien": [],
        "url_annonce": [],
        "surface_terrain": [],
        "surface_interieure": [],
        "surface_jardin": [],
        "nombre_de_pieces": [],
        "ville": [],
        "code_postal": [],
    }

    info_bien_dic = collect_fn(
        href_list=href_list,
        extract_fn=extract_fn,
        info_bien_dic=info_bien_dic,
        max_workers=MAX_WORKERS,
        verbose=False
    )

    dict_to_csv(info_bien_dic, f"annonces__test_{bien}.csv")
    print(f"[MAIN] CSV écrit: annonces_test_{bien}.csv | lignes={len(info_bien_dic['prix'])}")

print("[MAIN] DONE")
