# PDF TOC Detection — Démarche méthodologique

> **Module** : `src/docpipeline/parsing/pdf/toc/`
> **Corpus de test** : `data/CG contrats MRH/`

---

## 1. Objectif

Étant donné un document PDF quelconque, extraire automatiquement sa table des matières sous forme d'un tableau structuré (`toc_df`), puis réinjecter ce TOC dans le PDF sous forme de signets navigables.

```
PDF input  →  [détection]  →  toc_df  →  [enrichissement]  →  PDF avec TOC intégré
```

Le `toc_df` contient au minimum :

| Colonne              | Description                                               |
|----------------------|-----------------------------------------------------------|
| `title`              | Titre du chapitre / section                               |
| `level`              | Niveau hiérarchique (1 = chapitre, 2 = section…)          |
| `page_num_displayed` | Numéro affiché textuellement dans le TOC                  |
| `page_num_real`      | Vrai index physique de la page dans le PDF                |
| `page_end`           | Dernière page du chapitre                                 |
| `has_link`           | Lien interne présent dans le PDF source                   |
| `validated`          | `True` si `page_num_real` est confirmé                    |

---

## 2. Pipeline en 4 étapes

### Étape 1 — Détection

Le détecteur analyse les pages du PDF et calcule un **score de confiance [0, 1]** en cumulant plusieurs signaux textuels :

- Mots-clés : *Sommaire*, *Table des matières*, *Contents*
- Lignes de points leaders (`......`)
- Ratio de chiffres en fin de ligne (> 30 % des lignes)
- Densité de liens internes (> 5 annotations par page)
- Position en début de document (bonus si page < 15)

**Sortie** : score de confiance + liste des pages candidates TOC.

---

### Étape 2 — Extraction (2 méthodes)

#### Méthode 1 — TOC natif

Applicable quand le PDF contient des **bookmarks binaires** (export Word/LibreOffice).

- Les bookmarks pointent toujours vers une destination physique → **liens garantis**
- `page_num_real` est disponible directement, sans calcul d'offset
- Seule vérification requise : contrôler l'ordre croissant des entrées

```
TOC natif détecté
      │
      ▼
extract_native_toc()   →   toc_df brut   →   validate_order()
```

#### Méthode 2 — Détection par pages

Applicable quand aucun TOC natif n'est présent.

1. Détecter les pages TOC par heuristiques (`detector.py`)
2. Extraire les entrées depuis ces pages — **avec ou sans liens** selon le PDF
3. **Confirmation et restructuration via LLM** : validation de la hiérarchie des niveaux, correction des titres mal parsés, détection des entrées fusionnées

```
Pas de TOC natif
      │
      ▼
detect_toc_pages()
      │
      ▼
extract_toc_from_pages()
      │
      ▼
[Liens présents ?]
   oui  │   non
        │    │
        │    ▼
        │  compute_page_offset()   (fuzzy matching)
        │    │
        └────┤
             ▼
      restructure_with_llm()
```

> **Rôle du LLM** : intervient en Méthode 2 uniquement, après l'analyse des liens.
> Son rôle est de confirmer la hiérarchie et restructurer les entrées mal parsées.
> Le pipeline fonctionne en mode dégradé sans lui.

---

### Étape 3 — Validation des pages

> Uniquement nécessaire pour la **Méthode 2 sans liens**.

Le numéro affiché dans le TOC textuel peut différer de la vraie page PDF à cause des pages liminaires (couverture, droits, préface…).

**Hypothèse forte** : le décalage est **uniforme** sur tout le document.
Si le Chapitre 1 est décalé de +1, tous les chapitres le sont.

#### Algorithme de calcul de l'offset global

1. Sélectionner un échantillon d'entrées : niveau 1, titre > 15 caractères, exclure les titres génériques (*Introduction*, *Conclusion*)
2. Pour chaque entrée, chercher son texte dans une fenêtre `[page_displayed − k, page_displayed + k]` via **fuzzy matching** (seuil ≥ 0.85, après normalisation)
3. Agréger les offsets trouvés :
   - Si ≥ 80 % convergent → **offset global validé**, application à toutes les lignes
   - Sinon → mode dégradé, offset = 0, `validated = False`

```python
page_num_real = page_num_displayed + offset
```

---

### Étape 4 — Enrichissement et injection

- **`page_end`** : calculé par l'hypothèse forte `page_end[i] = page_num_real[i+1] − 1`
  (prochaine entrée de même niveau ou de niveau supérieur)
- Validation de l'ordre croissant des pages
- Réinjection du TOC dans le PDF via `bookmarks.py` (`doc.set_toc()`)

---

## 3. Procédure d'évaluation des algorithmes

### 3.1 Corpus de référence

- Sélectionner **20 à 50 PDFs** couvrant les 4 cas : TOC natif / liens / textuel / sans TOC
- Produire manuellement un `toc_df` de référence (**ground truth**) par PDF : titre exact, niveau, vraie page physique
- Stocker en JSON pour automatiser les comparaisons

### 3.2 Métriques

| Métrique          | Formule                          | Ce qu'elle mesure                        |
|-------------------|----------------------------------|------------------------------------------|
| Précision         | Entrées correctes / Extraites    | Pas de fausses entrées                   |
| Rappel (Recall)   | Entrées correctes / Attendues    | Pas d'entrées manquées                   |
| **F1-score**      | 2 × (P × R) / (P + R)           | Équilibre — **métrique principale**      |
| Précision page    | Pages exactes / Total            | Qualité du calcul d'offset               |
| Taux de détection | PDFs avec TOC trouvé / Total     | Robustesse du détecteur                  |

> **Critère d'acceptation** : une entrée est correcte si le titre matche à ≥ 85 % (fuzzy)
> ET si `|page_num_real − page_réf| ≤ 1`.

### 3.3 Protocole

1. **Test unitaire par algorithme** : évaluer chaque méthode séparément (natif, liens, dotted, multiline) sur son sous-corpus dédié
2. **Test intégration** : pipeline complet sur les 50 PDFs, comparaison avec les ground truths
3. **Analyse des échecs** : classifier par type (mauvaise méthode choisie / offset incorrect / titre mal parsé / LLM mal restructuré)
4. **Itération** : ajuster seuils de scoring, patterns et prompts LLM — objectif **F1 ≥ 0.90**

### 3.4 Livrables

- `evaluate_toc_quality.py` — compare `toc_df` automatique vs référence, produit un rapport CSV par PDF
- Notebook `benchmark` — métriques par méthode, histogrammes des offsets, courbes F1
- Rapport synthèse — F1 global, distribution des méthodes utilisées, impact du LLM, limites connues

---

## 4. Structure du module

```
src/docpipeline/parsing/pdf/toc/
├── main.py                   # Orchestrateur — pipeline complet
├── schema.py                 # Contrat du toc_df (colonnes, types, validation)
│
├── native.py                 # Méthode 1 : extraction bookmarks natifs
├── detector.py               # Détection heuristique des pages TOC
├── links.py                  # Extraction via liens internes
├── textual.py                # Extraction textuelle (dotted, multiline)
│
├── validate_order.py         # Vérification ordre croissant des pages
├── enrich_page_end.py        # Calcul de page_end
│
├── gpt.py                    # Confirmation / restructuration LLM (Méthode 2)
├── bookmarks.py              # Injection du TOC dans le PDF
│
├── models.py                 # Modèles de données
├── patterns.py               # Patterns regex de détection
├── scoring.py                # Scoring des heuristiques
├── reader.py                 # Wrapper lecture PDF
└── exceptions.py             # Exceptions métier
```

---

*Document validé — vision initiale du pipeline, antérieure à toute modification du code.*
