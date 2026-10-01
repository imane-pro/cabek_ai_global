"""
bareme_c2.py — Barème de chiffrage Cabek, catégorie véhicule C2
=================================================================
Contient les 3 tableaux réels (extraits des fichiers Excel fournis),
le registre de correspondance entre pièces, et les fonctions de calcul
du coût de réparation par dommage.

Logique retenue (validée) :
    Total = MO Réparation (heures × tarif) + MOP (heures × tarif) + MET (DH, valeur directe)
    - MOT (changement de pièce) : IGNORÉ
    - UN / NAC (peinture unie / nacrée) : IGNORÉS, seul MET (métallisée) est utilisé
"""

TARIF_REPARATION_DH = 110  # DH / heure — MO Réparation (tôlerie/dressage)
TARIF_MOP_DH = 70          # DH / heure — MOP (peinture & préparation)


# ══════════════════════════════════════════════════════════════
# 1. BARÈME MO RÉPARATION — catégorie C2 — heures selon gravité
#    (source : MO_reparation_C2.xlsx)
# ══════════════════════════════════════════════════════════════
BAREME_REPARATION_HEURES = {
    "PARE CHOC AV":    {"leger": 2.3, "moyen": 3.7, "fort": 6.5},
    "CALANDRE":        {"leger": 1.3, "moyen": 2.4, "fort": 4.5},
    "OPTIQUE G":       {"leger": 1.5, "moyen": 3.0, "fort": 4.0},
    "OPTIQUE D":       {"leger": 1.5, "moyen": 3.0, "fort": 4.0},
    "AILE AVG":        {"leger": 2.3, "moyen": 3.6, "fort": 5.7},
    "AILE AVD":        {"leger": 2.3, "moyen": 3.6, "fort": 5.7},
    "CAPOT MOTEUR":    {"leger": 3.3, "moyen": 5.5, "fort": 9.5},
    "JANTE ALUM":      {"leger": 2.1, "moyen": 3.3, "fort": 5.3},
    "JANTE ACIER":     {"leger": 1.5, "moyen": 2.4, "fort": 3.8},
    "PARE CHOC AR":    {"leger": 2.3, "moyen": 3.7, "fort": 6.2},
    "FEU ARG":         {"leger": 1.0, "moyen": 2.0, "fort": 2.0},
    "FEU ARD":         {"leger": 1.0, "moyen": 2.0, "fort": 2.0},
    "AILE ARG":        {"leger": 2.9, "moyen": 5.5, "fort": 11.0},
    "AILE ARD":        {"leger": 2.9, "moyen": 5.5, "fort": 11.0},
    "MALLE AR":        {"leger": 3.3, "moyen": 5.4, "fort": 8.7},
    "PORTE AVG/AVD":   {"leger": 2.8, "moyen": 4.8, "fort": 7.8},
    "PORTE ARG/ARD":   {"leger": 2.8, "moyen": 4.8, "fort": 7.8},
    "BAS CAISSE G/D":  {"leger": 5.1, "moyen": 7.0, "fort": 9.8},
    "RETROVISEUR G/D": {"leger": 1.5, "moyen": 2.8, "fort": 4.8},
}

# ══════════════════════════════════════════════════════════════
# 2. BARÈME MOP — catégorie C2 — heures peinture + préparation
#    (source : MOP_C2.xlsx — colonne MOP uniquement, MOT ignoré)
# ══════════════════════════════════════════════════════════════
BAREME_MOP_HEURES = {
    "PARE CHOC AV":              3.0,
    "CALANDRE":                  1.0,
    "AILE AVG":                  3.0,
    "AILE AVD":                  3.0,
    "CAPOT MOTEUR":              4.0,
    "JANTE AVG/AVD.ARG/ARD":     0.8,
    "PARE CHOC AR":              3.0,
    "AILE ARG":                  6.0,
    "AILE ARD":                  6.0,
    "MALLE AR":                  5.0,
    "PORTE AVG/AVD":             5.0,
    "PORTE ARG/ARD":             5.0,
    "BAS CAISSE G/D":            4.0,
    "RETROVISEUR G/D":           0.2,
}

# ══════════════════════════════════════════════════════════════
# 3. BARÈME INGRÉDIENTS & PEINTURE — catégorie C2, Métallisée (MET) — DH
#    (source : Ingredients_MET_C2.xlsx — colonne MET uniquement, UN/NAC ignorés)
#    ⚠️ Table plus grossière : pas de distinction gauche/droite ni avant/arrière
#    pour certaines pièces (ex: "AILE AV" couvre AVG et AVD).
# ══════════════════════════════════════════════════════════════
BAREME_MET_DH = {
    "AILE AV":       270,
    "AILE AR":       300,
    "PC AV":         290,
    "PC AR":         290,
    "CAPOT":         322,
    "MALLE":         322,
    "PORTE":         310,
    "BAS DE CAISSE": 234,
}



# ══════════════════════════════════════════════════════════════
# 4. REGISTRE DES PIÈCES — fait le lien entre UNE pièce "canonique"
#    et sa clé dans CHACUN des 3 tableaux (les granularités diffèrent
#    d'un tableau à l'autre, ex: MET ne distingue pas gauche/droite).
#    `None` = donnée absente de ce tableau pour cette pièce.
# ══════════════════════════════════════════════════════════════

# ⚠️ Le modèle IA a UNE seule classe "p_Roue" pour les jantes, alors que
# le barème distingue JANTE ALUM / JANTE ACIER (heures différentes).
# Impossible de deviner le matériau depuis la détection seule → on doit
# choisir un défaut. "roue_acier" est retenu ici (le plus courant/le plus
# conservateur en coût) — change vers "roue_alu" ci-dessous si tu préfères.
ROUE_DEFAUT = "roue_acier"  # ou "roue_alu"

PIECES_C2 = {
    "pare_choc_avant":     {"nom": "Pare-choc avant",        "reparation": "PARE CHOC AV",   "mop": "PARE CHOC AV",           "met": "PC AV"},
    "pare_choc_arriere":   {"nom": "Pare-choc arrière",      "reparation": "PARE CHOC AR",   "mop": "PARE CHOC AR",           "met": "PC AR"},
    "calandre":            {"nom": "Calandre",               "reparation": "CALANDRE",       "mop": "CALANDRE",               "met": None},
    "phare_avant_gauche":  {"nom": "Phare avant gauche",     "reparation": "OPTIQUE G",      "mop": None,                      "met": None},
    "phare_avant_droit":   {"nom": "Phare avant droit",      "reparation": "OPTIQUE D",      "mop": None,                      "met": None},
    "feu_arriere_gauche":  {"nom": "Feu arrière gauche",     "reparation": "FEU ARG",        "mop": None,                      "met": None},
    "feu_arriere_droit":   {"nom": "Feu arrière droit",      "reparation": "FEU ARD",        "mop": None,                      "met": None},
    "aile_avant_gauche":   {"nom": "Aile avant gauche",      "reparation": "AILE AVG",       "mop": "AILE AVG",                "met": "AILE AV"},
    "aile_avant_droite":   {"nom": "Aile avant droite",      "reparation": "AILE AVD",       "mop": "AILE AVD",                "met": "AILE AV"},
    "aile_arriere_gauche": {"nom": "Aile arrière gauche",    "reparation": "AILE ARG",       "mop": "AILE ARG",                "met": "AILE AR"},
    "aile_arriere_droite": {"nom": "Aile arrière droite",    "reparation": "AILE ARD",       "mop": "AILE ARD",                "met": "AILE AR"},
    "capot":               {"nom": "Capot moteur",           "reparation": "CAPOT MOTEUR",   "mop": "CAPOT MOTEUR",           "met": "CAPOT"},
    "malle_arriere":       {"nom": "Coffre / Malle arrière", "reparation": "MALLE AR",       "mop": "MALLE AR",               "met": "MALLE"},
    "porte_avant":         {"nom": "Porte avant",            "reparation": "PORTE AVG/AVD",  "mop": "PORTE AVG/AVD",          "met": "PORTE"},
    "porte_arriere":       {"nom": "Porte arrière",          "reparation": "PORTE ARG/ARD",  "mop": "PORTE ARG/ARD",          "met": "PORTE"},
    "bas_de_caisse":       {"nom": "Bas de caisse",          "reparation": "BAS CAISSE G/D", "mop": "BAS CAISSE G/D",         "met": "BAS DE CAISSE"},
    "retroviseur":         {"nom": "Rétroviseur",            "reparation": "RETROVISEUR G/D","mop": "RETROVISEUR G/D",        "met": None},
    "roue_alu":            {"nom": "Roue (jante alu)",       "reparation": "JANTE ALUM",     "mop": "JANTE AVG/AVD.ARG/ARD",  "met": None},
    "roue_acier":          {"nom": "Roue (jante acier)",     "reparation": "JANTE ACIER",    "mop": "JANTE AVG/AVD.ARG/ARD",  "met": None},
}

# ══════════════════════════════════════════════════════════════
# 5. MAPPING : classe du modèle IA "pièces"  →  clé canonique ci-dessus
#    ✅ Noms EXACTS confirmés par Cabek — correspondance validée.
# ══════════════════════════════════════════════════════════════
AI_PIECE_VERS_CANONICAL = {
    "p_Pare-chocs avant":     "pare_choc_avant",
    "p_Pare-chocs arriere":   "pare_choc_arriere",
    "p_Calandre":             "calandre",
    "p_Phare avant gauche":   "phare_avant_gauche",
    "p_Phare avant droit":    "phare_avant_droit",
    "p_Feu arriere gauche":   "feu_arriere_gauche",
    "p_Feu arriere droit":    "feu_arriere_droit",
    "p_Aile avant gauche":    "aile_avant_gauche",
    "p_Aile avant droite":    "aile_avant_droite",
    "p_Aile arriere gauche":  "aile_arriere_gauche",
    "p_Aile arriere droite":  "aile_arriere_droite",
    "p_Capot":                "capot",
    "p_Coffre":                "malle_arriere",
    "p_Porte avant":        "porte_avant",
    "p_Porte avant gauche": "porte_avant",
    "p_Porte avant droite": "porte_avant",

    "p_Porte arriere":        "porte_arriere",
    "p_Porte arriere gauche": "porte_arriere",
    "p_Porte arriere droite": "porte_arriere",
    "p_bas de caisse":        "bas_de_caisse",
    "p_Retroviseur droit":    "retroviseur",
    "p_Retroviseur gauche":   "retroviseur",   # même ligne barème (G/D fusionné), au cas où cette classe existe aussi
    "p_Roue":                 ROUE_DEFAUT,     # ambiguïté alu/acier — cf. note ci-dessus

    # Le modèle IA peut distinguer gauche/droite pour les portes,
    # tandis que le barème C2 utilise une seule ligne avant et une seule ligne arrière.
    "p_Porte avant gauche":    "porte_avant",
    "p_Porte avant droite":    "porte_avant",
    "p_Porte arriere gauche":  "porte_arriere",
    "p_Porte arriere droite":  "porte_arriere",
    "p_Porte arrière gauche":  "porte_arriere",
    "p_Porte arrière droite":  "porte_arriere",
}

# ══════════════════════════════════════════════════════════════
# 6. MAPPING : gravité IA (low/mid/high) → colonne du barème réparation
# ══════════════════════════════════════════════════════════════
GRAVITE_VERS_BAREME = {"low": "leger", "mid": "moyen", "high": "fort"}
LABEL_GRAVITE_BAREME = {"leger": "Léger", "moyen": "Moyen", "fort": "Fort"}

# ══════════════════════════════════════════════════════════════
# 7. Types de dommage qui NE relèvent PAS d'une réparation classique
#    (nécessitent un remplacement de pièce / MOT+fourniture, non couverts
#    par ce barème puisque MOT est volontairement ignoré) → à chiffrer
#    manuellement plutôt que de donner un montant potentiellement faux.
# ══════════════════════════════════════════════════════════════
DOMMAGES_HORS_BAREME_REPARATION = {"d_piece_manquante", "d_casse", "d_crevaison", "d_brise"}


def calculer_cout_dommage(piece_ai: str, type_dommage: str, niveau_gravite: str) -> dict:
    """
    piece_ai       : nom de la classe détectée par le modèle "pièces" (ex: "p_aile_arriere_droite")
    type_dommage   : nom de la classe détectée par le modèle "dommages" (ex: "d_bosse")
    niveau_gravite : "low", "mid" ou "high" (sortie de score_vers_gravite())

    Retourne le détail du calcul (heures, coûts, total) ou un dict avec
    "erreur"/"avertissement" si une donnée manque ou si le type de dommage
    n'est pas couvert par ce barème.
    """
    # ── Cas des dommages nécessitant un remplacement (hors barème actuel) ──
    if type_dommage in DOMMAGES_HORS_BAREME_REPARATION:
        return {
            "piece_ai": piece_ai,
            "type_dommage": type_dommage,
            "avertissement": (
                f"'{type_dommage}' nécessite un remplacement de pièce (MOT + fourniture), "
                f"non couvert par ce barème (MOT volontairement ignoré). "
                f"À chiffrer manuellement par un expert."
            ),
            "total": None,
        }

    canon = AI_PIECE_VERS_CANONICAL.get(piece_ai, "__inconnue__")
    if canon == "__inconnue__":
        return {
            "piece_ai": piece_ai,
            "erreur": f"Pièce '{piece_ai}' non reconnue. Ajoute-la dans AI_PIECE_VERS_CANONICAL.",
            "total": None,
        }
    if canon is None or canon not in PIECES_C2:
        return {
            "piece_ai": piece_ai,
            "avertissement": f"'{piece_ai}' n'a pas encore de ligne dans le barème C2 actuel. À chiffrer manuellement.",
            "total": None,
        }

    fiche = PIECES_C2[canon]
    niveau_bareme = GRAVITE_VERS_BAREME.get(niveau_gravite, "moyen")

    cle_rep = fiche["reparation"]
    cle_mop = fiche["mop"]
    cle_met = fiche["met"]

    heures_rep = BAREME_REPARATION_HEURES.get(cle_rep, {}).get(niveau_bareme) if cle_rep else None
    heures_mop = BAREME_MOP_HEURES.get(cle_mop) if cle_mop else None
    prix_met   = BAREME_MET_DH.get(cle_met) if cle_met else None

    manquants = []
    if heures_rep is None:
        manquants.append("heures MO Réparation")
    if heures_mop is None:
        manquants.append("heures MOP")
    if prix_met is None:
        manquants.append("prix MET")

    cout_reparation = heures_rep * TARIF_REPARATION_DH if heures_rep is not None else 0
    cout_mop        = heures_mop * TARIF_MOP_DH if heures_mop is not None else 0
    cout_met        = prix_met if prix_met is not None else 0

    resultat = {
        "piece_ai": piece_ai,
        "piece_nom": fiche["nom"],
        "type_dommage": type_dommage,
        "gravite": LABEL_GRAVITE_BAREME[niveau_bareme],
        "heures_reparation": heures_rep,
        "cout_reparation": round(cout_reparation, 2),
        "heures_mop": heures_mop,
        "cout_mop": round(cout_mop, 2),
        "cout_met": cout_met,
        "total": round(cout_reparation + cout_mop + cout_met, 2),
    }

    if manquants:
        resultat["avertissement"] = (
            "Donnée(s) manquante(s) dans le barème pour '" + fiche["nom"] + "' : "
            + ", ".join(manquants) + " — coût partiel, à compléter manuellement."
        )

    return resultat


def calculer_cout_total(dommages: list) -> dict:
    """
    dommages : liste de dicts {"piece_ai": ..., "type_dommage": ..., "niveau_gravite": ...}
    Retourne le détail par dommage + le total général (uniquement sur les lignes chiffrables).
    """
    details = []
    total_general = 0.0
    a_verifier = []

    for d in dommages:
        r = calculer_cout_dommage(d["piece_ai"], d["type_dommage"], d["niveau_gravite"])
        details.append(r)
        if r.get("total") is not None:
            total_general += r["total"]
        if r.get("avertissement") or r.get("erreur"):
            a_verifier.append(r)

    return {
        "details": details,
        "total_general": round(total_general, 2),
        "a_verifier": a_verifier,
    }