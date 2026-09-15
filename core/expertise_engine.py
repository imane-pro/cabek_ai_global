"""Moteur d'expertise CABEK.
Compatible avec les poids YOLO actuellement utilisés par l'application.
"""
import cv2
import numpy as np
from bareme_c2 import calculer_cout_dommage, TARIF_REPARATION_DH, TARIF_MOP_DH

POIDS_CATEGORIE = {
    "d_brise":           0.9,
    "d_piece_manquante": 0.9,
    "d_casse":           0.8,
    "d_lampe_casse":     0.6,
    "d_bosse":           0.5,
    "d_fissure":         0.5,
    "d_crevaison":       0.7,
    "d_rayure":          0.3,
}

CLASSES_SANS_SURFACE = ["d_crevaison"]

SOLUTIONS = {
    "d_rayure":          "Polissage / peinture partielle",
    "d_bosse":           "Débosselage / redressage",
    "d_fissure":         "Réparation / mastic",
    "d_brise":           "Remplacement vitrage",
    "d_casse":           "Échange pièce",
    "d_lampe_casse":     "Réparation ou remplacement optique",
    "d_piece_manquante": "Échange pièce",
    "d_crevaison":       "Réparation / remplacement pneu",
}

# ══════════════════════════════════════════════════════════════════
# RÈGLES MÉTIER — PRIORITÉ AU REMPLACEMENT
# ══════════════════════════════════════════════════════════════════
# Une pièce qui présente un dommage imposant son remplacement est
# chiffrée une seule fois : les autres dommages de cette pièce sont
# considérés comme inclus dans le remplacement.

DOMMAGES_REMPLACEMENT_DIRECT = {
    "d_piece_manquante",
    "d_casse",
    "d_crevaison",
}

DOMMAGES_REMPLACEMENT_SI_GRAVE = {
    "d_fissure",
    "d_bosse",
    "d_brise",
    "d_lampe_casse",
}

# Classes du modèle dommages : d_bosse_slight, d_bosse_medium,
# d_bosse_severe, d_fissure_slight, etc.
SUFFIXE_GRAVITE_CLASSE = {
    "slight": "low",
    "leger": "low",
    "light": "low",
    "medium": "mid",
    "moderate": "mid",
    "modere": "mid",
    "mid": "mid",
    "severe": "high",
    "grave": "high",
    "high": "high",
}

GRAVITE_ORDRE = {"low": 0, "mid": 1, "high": 2}


def normaliser_classe_dommage(nom_classe: str):
    """Normalise une classe IA et récupère sa gravité explicite éventuelle."""
    nom = str(nom_classe).strip().lower()
    if not nom.startswith("d_"):
        return nom, None

    base, suffixe = nom.rsplit("_", 1)
    if suffixe in SUFFIXE_GRAVITE_CLASSE:
        return base, SUFFIXE_GRAVITE_CLASSE[suffixe]
    return nom, None


def gravite_max(niveau_a: str, niveau_b: str) -> str:
    """Retourne le niveau de gravité le plus élevé."""
    if GRAVITE_ORDRE.get(niveau_b, 0) > GRAVITE_ORDRE.get(niveau_a, 0):
        return niveau_b
    return niveau_a


def necessite_remplacement(item: dict) -> bool:
    """Détermine si le dommage impose le remplacement complet de la pièce."""

    type_dommage = item.get("type_brut", "")

    # La zone critique est une règle métier spécifique à la BOSSE.
    # Une bosse qui touche cette zone est automatiquement grave et impose
    # le remplacement. Les autres types de dommages ne sont pas concernés.
    if type_dommage == "d_bosse" and item.get("zone_critique_detectee") is True:
        return True

    niveau = item.get("niveau", "low")

    if type_dommage in DOMMAGES_REMPLACEMENT_DIRECT:
        return True

    return (
        type_dommage in DOMMAGES_REMPLACEMENT_SI_GRAVE
        and niveau == "high"
    )


def appliquer_priorite_remplacement(instances: list) -> list:
    """
    Applique la règle métier au niveau de chaque pièce.

    Si une pièce contient au moins un dommage de remplacement :
      - le dommage déclencheur est marqué remplacement_requis ;
      - les autres dommages sont bloqués et leur coût est annulé ;
      - ils ne sont pas comptés comme lignes à chiffrer.
    """
    pieces_a_remplacer = {}

    for item in instances:
        piece = item.get("piece_ai_brut")
        if piece is not None and necessite_remplacement(item):
            pieces_a_remplacer.setdefault(piece, []).append(item)

    for item in instances:
        piece = item.get("piece_ai_brut")

        if piece is None or piece not in pieces_a_remplacer:
            item["remplacement_requis"] = False
            item["chiffrage_bloque"] = False
            continue

        if necessite_remplacement(item):
            item["remplacement_requis"] = True
            item["chiffrage_bloque"] = False
            item["cout"] = None

            if item.get("type_brut") == "d_bosse" and item.get("zone_critique_detectee") is True:
                avertissement = (
                    "Dommage situé sur une zone critique (arête / bord / zone "
                    "structurelle) détectée par le modèle IA — remplacement "
                    "complet de la pièce imposé, indépendamment de la surface "
                    "touchée ou de la gravité apparente. Le prix de la pièce et "
                    "la main-d'œuvre de remplacement ne sont pas couverts par le "
                    "barème C2 actuel. À chiffrer manuellement par un expert."
                )
            else:
                avertissement = (
                    "Ce dommage nécessite le remplacement complet de la pièce. "
                    "Le prix de la pièce et la main-d'œuvre de remplacement ne "
                    "sont pas couverts par le barème C2 actuel. À chiffrer "
                    "manuellement par un expert."
                )

            item["cout_detail"] = {
                "type": "remplacement",
                "remplacement_requis": True,
                "total": None,
                "declencheur_zone_critique": item.get("zone_critique_detectee", False),
                "avertissement": avertissement,
            }
            item["solution"] = "Remplacement complet de la pièce"
        else:
            item["remplacement_requis"] = False
            item["chiffrage_bloque"] = True
            item["cout"] = None
            item["cout_detail"] = {
                "type": "inclus_dans_remplacement",
                "remplacement_requis": True,
                "total": None,
                "avertissement": (
                    "Dommage non chiffré séparément : la pièce présente un "
                    "dommage nécessitant son remplacement complet. Ce dommage "
                    "est considéré comme inclus dans le remplacement de la pièce."
                ),
            }
            item["solution"] = "Non chiffré séparément — remplacement de la pièce requis"

    return instances

# ── Le calcul de coût réel (MO Réparation + MOP + MET, catégorie C2)
# vit maintenant dans bareme_c2.py — importé en haut du fichier.
# La liste de marques reste affichée à titre informatif (catégorie du
# véhicule), mais ne pilote plus le prix : seule la catégorie C2 est
# couverte par le barème actuel.
CATEGORIES_MARQUE = {
    "Éco":     ["Dacia", "Fiat", "Seat", "Skoda", "Lada"],
    "Standard": ["Renault", "Peugeot", "Citroën", "Ford", "Toyota", "Hyundai",
                 "Kia", "Volkswagen", "Nissan", "Opel", "Chevrolet", "Suzuki"],
    "Premium": ["Mercedes", "BMW", "Audi", "Lexus", "Volvo", "Land Rover", "Porsche"],
}


def get_categorie_marque(marque: str) -> str:
    for cat, marques in CATEGORIES_MARQUE.items():
        if marque in marques:
            return cat
    return "Standard"


# ══════════════════════════════════════════════════════════════════
# 4. CHARGEMENT DES MODÈLES (mis en cache)
# ══════════════════════════════════════════════════════════════════




def calculer_overlap(mask_d: np.ndarray, mask_p: np.ndarray) -> float:
    mask_d_bool = mask_d.astype(bool)
    mask_p_bool = mask_p.astype(bool)
    intersection = np.logical_and(mask_d_bool, mask_p_bool).sum()
    surface_dommage = mask_d_bool.sum()
    if surface_dommage == 0:
        return 0.0
    return float(intersection / surface_dommage)


def position_bucket(mask_d: np.ndarray, mask_p: np.ndarray) -> str:
    """
    Situe approximativement un dommage à l'intérieur de sa pièce (quadrant
    haut/bas × gauche/droite), pour pouvoir reconnaître "le même dommage vu
    sous un autre angle" entre plusieurs photos, sans reconstruction 3D.
    Retourne "inconnu" si la pièce ou le dommage n'a pas de pixels exploitables.
    """
    ys_p, xs_p = np.where(mask_p)
    if len(xs_p) == 0:
        return "inconnu"
    x_min, x_max = xs_p.min(), xs_p.max()
    y_min, y_max = ys_p.min(), ys_p.max()

    ys_d, xs_d = np.where(mask_d)
    if len(xs_d) == 0:
        return "inconnu"
    cx, cy = xs_d.mean(), ys_d.mean()

    fx = (cx - x_min) / max(x_max - x_min, 1)
    fy = (cy - y_min) / max(y_max - y_min, 1)

    horiz = "G" if fx < 0.5 else "D"
    vert = "H" if fy < 0.5 else "B"
    return f"{vert}{horiz}"


def calculer_score_gravite(nom_dommage: str, ratio_surface: float, confiance: float,
                            alpha: float = 0.2, beta: float = 0.2, gamma: float = 0.6) -> float:
    poids = POIDS_CATEGORIE.get(nom_dommage, 0.5)
    if nom_dommage in CLASSES_SANS_SURFACE:
        beta_a = beta / (beta + gamma)
        gamma_a = gamma / (beta + gamma)
        return beta_a * confiance + gamma_a * poids
    return alpha * ratio_surface + beta * confiance + gamma * poids


def score_vers_gravite(score: float) -> str:
    if score < 0.35:
        return "low"
    elif score < 0.6:
        return "mid"
    return "high"


LABEL_GRAVITE = {"low": "Léger", "mid": "Modéré", "high": "Grave"}


def calculer_overlap_zone_critique(mask_d_np: np.ndarray, res_z) -> float:
    """
    Calcule le pourcentage du masque d'un dommage qui tombe à l'intérieur
    d'une (ou plusieurs) zone(s) critique(s) détectée(s) par le modèle 3
    (bord / arête / zone structurelle). Retourne 0.0 si aucune zone
    critique n'a été détectée sur l'image.

    NB : on prend le MAX sur toutes les zones critiques détectées (une
    seule suffit à faire basculer le dommage en zone critique), pas la
    somme, pour éviter de dépasser 100% en cas de zones qui se chevauchent.
    """
    if res_z is None or res_z.masks is None or len(res_z.boxes) == 0:
        return 0.0

    meilleur = 0.0
    for mask_z in res_z.masks.data:
        mask_z_np = mask_z.cpu().numpy().astype(bool)

        if mask_d_np.shape != mask_z_np.shape:
            mask_d_resized = cv2.resize(
                mask_d_np.astype(np.uint8),
                (mask_z_np.shape[1], mask_z_np.shape[0])
            ).astype(bool)
        else:
            mask_d_resized = mask_d_np

        overlap = calculer_overlap(mask_d_resized, mask_z_np)
        if overlap > meilleur:
            meilleur = overlap

    return meilleur


def analyser(modele_pieces, modele_dommages, image_np: np.ndarray,
             conf_pieces: float, conf_dommages: float, iou_min: float,
             marque: str, nom_image: str = "",
             modele_zone_critique=None, conf_zone_critique: float = 0.25,
             seuil_zone_critique: float = 0.05):
    """
    modele_zone_critique : modèle YOLO 1-classe "zone_critique" (bords /
        arêtes / zones structurelles) — optionnel. Si None, la détection
        de zone critique est simplement désactivée (aucun impact sur le
        reste de la logique).
    seuil_zone_critique   : fraction minimale du masque du dommage qui doit
        chevaucher une zone critique pour que le dommage soit considéré
        "sur zone critique" (les zones critiques sont souvent des bandes
        fines le long des arêtes, donc un seuil bas est recommandé).
    """
    res_p = modele_pieces.predict(image_np, conf=conf_pieces, agnostic_nms=True, verbose=False)[0]
    res_d = modele_dommages.predict(image_np, conf=conf_dommages, agnostic_nms=True, verbose=False)[0]

    res_z = None
    if modele_zone_critique is not None:
        res_z = modele_zone_critique.predict(
            image_np, conf=conf_zone_critique, agnostic_nms=True, verbose=False
        )[0]

    instances = []

    if res_d.masks is not None and len(res_d.boxes) > 0:
        for i, mask_d in enumerate(res_d.masks.data):
            nom_d_ia = modele_dommages.names[int(res_d.boxes.cls[i])]
            nom_d, gravite_classe = normaliser_classe_dommage(nom_d_ia)
            conf_d = float(res_d.boxes.conf[i])
            mask_d_np = mask_d.cpu().numpy().astype(bool)
            surface_d = mask_d_np.sum()

            meilleure_piece, meilleur_overlap = None, 0.0

            if res_p.masks is not None and len(res_p.boxes) > 0:
                for j, mask_p in enumerate(res_p.masks.data):
                    nom_p = modele_pieces.names[int(res_p.boxes.cls[j])]
                    conf_p = float(res_p.boxes.conf[j])
                    mask_p_np = mask_p.cpu().numpy().astype(bool)

                    if mask_d_np.shape != mask_p_np.shape:
                        mask_d_resized = cv2.resize(
                            mask_d_np.astype(np.uint8),
                            (mask_p_np.shape[1], mask_p_np.shape[0])
                        ).astype(bool)
                    else:
                        mask_d_resized = mask_d_np

                    overlap = calculer_overlap(mask_d_resized, mask_p_np)
                    if overlap > meilleur_overlap:
                        meilleur_overlap = overlap
                        meilleure_piece = {"nom": nom_p, "conf": conf_p, "mask": mask_p_np,
                                            "mask_d_aligne": mask_d_resized}

            piece_ai_brut = None  # nom de classe BRUT (ex: "p_Aile arriere droite"), pour le barème
            bucket = "inconnu"    # position approx. du dommage sur la pièce (pour dédup multi-images)
            if meilleure_piece and meilleur_overlap >= iou_min:
                surface_p = meilleure_piece["mask"].sum()
                if surface_p >= surface_d:
                    ratio_surface = surface_d / (surface_p + 1e-6)
                    piece_ai_brut = meilleure_piece["nom"]
                    piece_nom = meilleure_piece["nom"].replace("p_", "").replace("_", " ")
                    bucket = position_bucket(meilleure_piece["mask_d_aligne"], meilleure_piece["mask"])
                else:
                    h, w = image_np.shape[:2]
                    ratio_surface = surface_d / (h * w + 1e-6)
                    piece_nom = "zone non identifiée"
            else:
                h, w = image_np.shape[:2]
                ratio_surface = surface_d / (h * w + 1e-6)
                piece_nom = "zone non identifiée"

            score = calculer_score_gravite(nom_d, ratio_surface, conf_d)
            niveau_calcule = score_vers_gravite(score)

            # Si la classe IA indique explicitement une gravité, elle est
            # utilisée comme gravité métier de la classe. Sinon on conserve
            # le calcul surface + confiance + poids.
            niveau = gravite_classe if gravite_classe is not None else niveau_calcule

            # ── Zone critique : règle métier uniquement pour la BOSSE ──
            zone_overlap = calculer_overlap_zone_critique(mask_d_np, res_z)
            zone_critique_detectee = (
                nom_d == "d_bosse" and zone_overlap >= seuil_zone_critique
            )

            if zone_critique_detectee:
                niveau = "high"

            # ── Coût réel : MO Réparation + MOP + MET (catégorie C2) ──
            if piece_ai_brut is not None:
                detail_cout = calculer_cout_dommage(piece_ai_brut, nom_d, niveau)
            else:
                detail_cout = {
                    "avertissement": "Pièce non identifiée avec certitude — chiffrage impossible automatiquement.",
                    "total": None,
                }

            instances.append({
                "type": nom_d.replace("d_", "").replace("_", " "),
                "type_brut": nom_d,
                "classe_ia": nom_d_ia,
                "gravite_classe_ia": gravite_classe,
                "piece_ai_brut": piece_ai_brut,              # ex: "p_Aile arriere droite" ou None
                "position_bucket": bucket,                   # ex: "HD", "BG"... ou "inconnu"
                "source_image": nom_image,                   # nom du fichier photo d'origine
                "confiance": conf_d,
                "piece": piece_nom,
                "surface_pct": ratio_surface * 100,
                "score": score,
                "niveau": niveau,
                "solution": SOLUTIONS.get(nom_d, "À vérifier par un expert"),
                "cout": detail_cout.get("total"),          # None si non chiffrable
                "cout_detail": detail_cout,                 # détail complet (heures, avertissements...)
                "n_vues": 1,                                  # nb de photos où ce dommage a été vu (rempli après dédup)
                "images_sources": [nom_image],
                "remplacement_requis": False,
                "chiffrage_bloque": False,
                "zone_critique_detectee": zone_critique_detectee,   # bool — modèle 3
                "zone_critique_overlap_pct": zone_overlap * 100,    # % du dommage sur la zone critique
            })

    n_zones_critiques = (
        len(res_z.boxes) if (res_z is not None and res_z.boxes is not None) else 0
    )

    return {
        "instances": instances,
        "n_pieces": len(res_p.boxes) if res_p.boxes is not None else 0,
        "n_dommages": len(res_d.boxes) if res_d.boxes is not None else 0,
        "n_zones_critiques": n_zones_critiques,
        "img_pieces": res_p.plot()[:, :, ::-1],
        "img_dommages": res_d.plot()[:, :, ::-1],
        "img_zones_critiques": (
            res_z.plot()[:, :, ::-1] if res_z is not None else None
        ),
    }




def calculer_agregats(instances: list) -> dict:
    """
    Calcule les totaux après application des règles métier.

    Un dommage secondaire d'une pièce déjà condamnée au remplacement
    n'est pas compté comme une ligne à chiffrer manuellement.
    """
    score_global = (
        float(np.mean([it.get("score", 0.0) for it in instances]))
        if instances else 0.0
    )

    cout_total = sum(
        float(it.get("cout") or 0.0)
        for it in instances
        if it.get("cout") is not None
    )

    n_a_verifier = 0
    for it in instances:
        if it.get("chiffrage_bloque") is True:
            continue
        if it.get("remplacement_requis") is True:
            n_a_verifier += 1
            continue
        if it.get("cout") is None:
            n_a_verifier += 1

    total_mo_reparation = sum(
        (it.get("cout_detail") or {}).get("cout_reparation", 0) or 0
        for it in instances
        if it.get("cout") is not None
    )
    total_mo_peinture = sum(
        (it.get("cout_detail") or {}).get("cout_mop", 0) or 0
        for it in instances
        if it.get("cout") is not None
    )
    total_produit_peinture = sum(
        (it.get("cout_detail") or {}).get("cout_met", 0) or 0
        for it in instances
        if it.get("cout") is not None
    )
    total_fourniture = 0  # remplacement/fourniture hors barème actuel

    return {
        "score_global": score_global,
        "cout_total": cout_total,
        "n_a_verifier": n_a_verifier,
        "total_mo_reparation": total_mo_reparation,
        "total_mo_peinture": total_mo_peinture,
        "total_produit_peinture": total_produit_peinture,
        "total_fourniture": total_fourniture,
    }


# ==========================================================

def dedupliquer_instances(toutes_instances: list) -> list:
    """
    Déduplique les dommages détectés.

    RÈGLE :
    - Même pièce + même type de dommage = un seul dommage retenu.
    - Seule la détection avec le score de confiance LE PLUS ÉLEVÉ est conservée 
      (pour éviter de doubler le coût de réparation).
    - Les pièces non identifiées ne sont pas fusionnées.
    """
    groupes = {}

    for inst in toutes_instances:
        # --------------------------------------------------
        # 1. Pièce non identifiée (zone non identifiée)
        # --------------------------------------------------
        if inst.get("piece_ai_brut") is None:
            # On conserve chaque détection séparément
            cle = ("__unique__", id(inst))

        # --------------------------------------------------
        # 2. Pièce identifiée
        # --------------------------------------------------
        else:
            # Même pièce + même type de dommage
            cle = (
                inst["piece_ai_brut"],
                inst["type_brut"],
            )

        groupes.setdefault(cle, []).append(inst)

    resultat = []

    # ------------------------------------------------------
    # Selection de la détection avec la meilleure confiance
    # ------------------------------------------------------
    for membres in groupes.values():
        # Garder la détection avec la confiance maximale
        representant = max(
            membres,
            key=lambda x: x["confiance"]
        ).copy()

        # Conserver les informations sur l'historique des détections
        representant["n_vues"] = len(membres)
        representant["images_sources"] = sorted(
            {m["source_image"] for m in membres}
        )
        representant["confiance_max"] = representant["confiance"]
        representant["n_detections_fusionnees"] = len(membres) - 1

        # La zone critique ne s'applique qu'aux bosses. Si une bosse est
        # critique sur au moins une vue, elle reste grave après fusion.
        if representant.get("type_brut") == "d_bosse" and any(
            m.get("zone_critique_detectee") for m in membres
        ):
            representant["zone_critique_detectee"] = True
            representant["zone_critique_overlap_pct"] = max(
                m.get("zone_critique_overlap_pct", 0.0) for m in membres
            )
            representant["niveau"] = "high"

        resultat.append(representant)

    return resultat

