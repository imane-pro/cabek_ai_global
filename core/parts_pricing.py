"""
core/parts_pricing.py — Client de l'API AutoEstimate
======================================================
Récupère les statistiques de prix de pièces détachées (median/average/
minimum/maximum/observation_count) pour un véhicule + une pièce + un
type ("original", "adaptable", "occasion").

⚠️ À COMPLÉTER AVANT UTILISATION :
- BASE_URL : l'URL réelle du service AutoEstimate en production
  (ex. "https://autoestimate.cabek.internal/api/v1").
- Le token doit être stocké dans .streamlit/secrets.toml :

      AUTOESTIMATE_TOKEN = "cae_xxxxxxxxxxxxxxxx"

  jamais en dur dans ce fichier, jamais commité dans Git.
"""
from __future__ import annotations

import requests
import streamlit as st

BASE_URL = "http://192.168.2.184:8080/api/v1"

TYPES_PIECE_API = ("original", "adaptable", "occasion")


class AutoEstimateError(Exception):
    """Erreur générique de communication avec l'API AutoEstimate."""


class AutoEstimateAuthError(AutoEstimateError):
    """Token manquant, invalide ou révoqué (HTTP 401)."""


class AutoEstimateValidationError(AutoEstimateError):
    """Paramètres invalides envoyés à l'API (HTTP 422)."""


class AutoEstimateRateLimitError(AutoEstimateError):
    """Trop de requêtes envoyées (HTTP 429)."""


def _headers() -> dict:
    token = st.secrets.get("AUTOESTIMATE_TOKEN")
    if not token:
        raise AutoEstimateAuthError(
            "AUTOESTIMATE_TOKEN absent de .streamlit/secrets.toml — "
            "impossible d'appeler l'API AutoEstimate."
        )
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _get(path: str, params: dict | None = None) -> dict:
    try:
        r = requests.get(f"{BASE_URL}{path}", params=params or {}, headers=_headers(), timeout=10)
    except requests.RequestException as e:
        raise AutoEstimateError(f"AutoEstimate injoignable ({path}) : {e}") from e

    if r.status_code == 401:
        raise AutoEstimateAuthError("Token AutoEstimate invalide ou révoqué.")
    if r.status_code == 422:
        raise AutoEstimateValidationError(f"Paramètres invalides pour {path} : {r.text}")
    if r.status_code == 429:
        raise AutoEstimateRateLimitError("Limite de requêtes AutoEstimate atteinte (120/min) — réessaie plus tard.")
    if r.status_code >= 500:
        raise AutoEstimateError(f"Erreur serveur AutoEstimate ({r.status_code}) sur {path}.")
    r.raise_for_status()

    return r.json()


# ══════════════════════════════════════════════════════════════
# RÉFÉRENTIELS (marques / modèles / pièces) — cache 1h : bougent peu
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def get_marques() -> list[dict]:
    """Liste de {id, libelle} pour toutes les marques connues d'AutoEstimate."""
    return _get("/marques")["data"]


@st.cache_data(ttl=3600, show_spinner=False)
def get_models(marque_id: int) -> list[dict]:
    """Liste de {id, marque_id, libelle} pour tous les modèles d'une marque."""
    return _get("/models", {"marque_id": marque_id})["data"]


@st.cache_data(ttl=3600, show_spinner=False)
def get_parts(model_id: int | None = None) -> list[dict]:
    """
    Liste de {id, libelle} — toutes les pièces canoniques si model_id
    est omis, ou uniquement celles ayant des observations pour ce modèle.
    """
    params = {"model_id": model_id} if model_id else {}
    return _get("/parts", params)["data"]


# ══════════════════════════════════════════════════════════════
# ESTIMATION DE PRIX — cache 30 min : les prix pièces évoluent
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def get_estimation(
    marque_id: int,
    model_id: int,
    part_id: int,
    type_piece: str,
    year: int | None = None,
    source_id: int | None = None,
) -> dict | None:
    """
    Retourne le dict 'estimation' (median/average/minimum/maximum/
    observation_count) pour la combinaison donnée, ou None si l'API
    répond `data: null` (aucune observation ne correspond — jamais
    interprété comme un prix de 0).
    """
    params = {"marque_id": marque_id, "model_id": model_id, "part_id": part_id, "type": type_piece}
    if year:
        params["year"] = year
    if source_id:
        params["source_id"] = source_id

    payload = _get("/estimation", params)["data"]
    return payload["estimation"] if payload else None


def get_estimations_tous_types(
    marque_id: int, model_id: int, part_id: int, year: int | None = None
) -> dict[str, dict | None]:
    """
    Interroge les 3 types de pièce (original / adaptable / occasion) en
    une fois, pour laisser l'expert choisir la fourchette la plus
    pertinente plutôt que d'imposer un type par défaut caché.
    """
    resultats = {}
    for type_piece in TYPES_PIECE_API:
        try:
            resultats[type_piece] = get_estimation(marque_id, model_id, part_id, type_piece, year)
        except AutoEstimateError:
            resultats[type_piece] = None
    return resultats