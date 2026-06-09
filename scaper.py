import requests
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# ─── CONFIG ───────────────────────────────────────────────
API_KEY = os.environ.get('GOOGLE_PLACES_KEY', 'AIzaSyBvPWSTlm_9xW7T9ybHaPNIOP2l0Nh7HyQ')

CATEGORIES = [
    'restaurant',
    'hair_salon',
    'car_repair',
    'physiotherapist',
    'gym',
    'photographer',
    'florist',
    'bakery',
    'clothing_store',
    'spa'
]

VILLES = [
    'Brussels,Belgium',
    'Liège,Belgium',
    'Namur,Belgium',
    'Ghent,Belgium',
    'Antwerp,Belgium'
]

# ─── SCRAPE GOOGLE MAPS ───────────────────────────────────
def get_prospects(categorie, ville):
    url = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
    params = {
        'query': f'{categorie} in {ville}',
        'key': API_KEY
    }
    
    try:
        res = requests.get(url, params=params, timeout=10).json()
    except Exception as e:
        print(f'  Erreur requête : {e}')
        return []

    prospects = []

    for place in res.get('results', []):
        place_id = place.get('place_id')
        if not place_id:
            continue

        # Détails du lieu
        detail_url = 'https://maps.googleapis.com/maps/api/place/details/json'
        detail_params = {
            'place_id': place_id,
            'fields': 'name,website,formatted_phone_number,rating,user_ratings_total,formatted_address',
            'key': API_KEY
        }

        try:
            detail = requests.get(detail_url, params=detail_params, timeout=10).json().get('result', {})
        except Exception:
            continue

        # Garder seulement ceux SANS site web → prospects chauds
        if not detail.get('website'):
            prospects.append({
                'nom':      detail.get('name', ''),
                'tel':      detail.get('formatted_phone_number', ''),
                'adresse':  detail.get('formatted_address', ''),
                'note':     str(detail.get('rating', '')),
                'avis':     str(detail.get('user_ratings_total', 0)),
                'ville':    ville.split(',')[0],
                'categorie': categorie,
                'statut':   'À valider'
            })

        time.sleep(0.15)  # Respecter les limites API

    return prospects


# ─── UPLOAD GOOGLE SHEETS ─────────────────────────────────
def upload_to_sheets(prospects):
    creds_raw = os.environ.get('GSPREAD_CREDS', '{}')
    
    try:
        creds_dict = json.loads(creds_raw)
    except json.JSONDecodeError:
        print('⚠ GSPREAD_CREDS invalide — export CSV local uniquement')
        return False

    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open('Prospects QNA').sheet1
    except Exception as e:
        print(f'⚠ Erreur connexion Sheets : {e}')
        return False

    # Récupérer les noms déjà présents pour éviter les doublons
    try:
        existants = [row[0] for row in sheet.get_all_values()[1:]]
    except Exception:
        existants = []

    added = 0
    for p in prospects:
        if p['nom'] and p['nom'] not in existants:
            sheet.append_row([
                p['nom'],
                p['tel'],
                p['adresse'],
                p['note'],
                p['avis'],
                p['ville'],
                p['categorie'],
                p['statut']
            ])
            existants.append(p['nom'])
            added += 1
            time.sleep(0.1)

    print(f'✓ {added} nouveaux prospects ajoutés dans Google Sheets')
    return True


# ─── EXPORT CSV LOCAL (fallback) ──────────────────────────
def export_csv(prospects):
    import csv
    filename = 'prospects.csv'
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['nom','tel','adresse','note','avis','ville','categorie','statut'])
        writer.writeheader()
        writer.writerows(prospects)
    print(f'✓ {len(prospects)} prospects exportés dans {filename}')


# ─── MAIN ─────────────────────────────────────────────────
if __name__ == '__main__':
    tous_prospects = []

    for ville in VILLES:
        for cat in CATEGORIES:
            print(f'  Scraping {cat} à {ville}...')
            nouveaux = get_prospects(cat, ville)
            tous_prospects.extend(nouveaux)
            print(f'  → {len(nouveaux)} prospects sans site trouvés')

    print(f'\n🎯 Total : {len(tous_prospects)} prospects sans site')

    # Trier par nombre d'avis (plus actifs en premier)
    tous_prospects.sort(key=lambda x: int(x['avis']) if x['avis'].isdigit() else 0, reverse=True)

    # Upload Sheets ou CSV local
    if not upload_to_sheets(tous_prospects):
        export_csv(tous_prospects)
