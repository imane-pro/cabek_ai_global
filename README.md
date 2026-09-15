# CABEK.AI — Application globale

L'application est maintenant une seule application Streamlit avec une navigation globale dans la barre latérale.

## Lancement

```powershell
pip install -r requirements.txt
python -m streamlit run app.py
```

## Navigation

- Accueil
- Collecte des données
- Expertise IA

Les anciennes interfaces séparées ne sont plus nécessaires pour lancer le système. Les pages dans `pages/` sont des pages de la même application Streamlit.

## Structure

```text
CABEK_AI_GLOBAL/
├── app.py
├── pages/
│   ├── 1_Accueil.py
│   ├── 2_Collecte.py
│   └── 3_Expertise_IA.py
├── core/
│   ├── dossier_manager.py
│   ├── expertise_engine.py
│   └── ui.py
├── bareme_c2.py
├── models/
│   ├── best_pieces.pt
│   ├── best.pt
│   └── best_zone_critique.pt
└── data/dossiers/
```

Le modèle `best_zone_critique.pt` est utilisé par le moteur pour intersecter le masque de zone critique avec le masque d'une `d_bosse`. Si l'intersection dépasse le seuil configuré, la bosse est forcée à `high` et le remplacement est déclenché par les règles métier existantes.
