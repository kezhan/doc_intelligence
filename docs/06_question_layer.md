# 6. La couche Question — une fonction publique, N briques activables

> *« Le code n'est jamais le problème — c'est la clarté de l'organisation. »*

Tu poses une question. Le système rend un JSON détaillé qui contient tout ce qu'il
faut pour la suite du pipeline (retrieval, génération). C'est tout. Sur le papier,
c'est trois lignes :

```python
from src.question_parsing import understand_question

plan = understand_question(
    "Quelle est la prime sur ce contrat ?",
    document_type="pdf",
)
# → [ { "retrieval": {...}, "generation": {...}, "_meta": {...} } ]
```

Une fonction publique. Une question en entrée. **Une liste de dicts en sortie**
(toujours une liste — on verra pourquoi). À l'intérieur, beaucoup de petites
fonctions qui font chacune leur travail. À l'extérieur, un seul appel.

C'est l'objet de ce chapitre.

---

## 6.1 Pourquoi pas la cascade en dur

Première tentation, déjà à moitié croisée : appeler chaque helper en séquence
dans un seul gros pipeline.

```python
def understand_question(question):
    corrected = correct_spelling(question)
    return {
        "retrieval": {
            "main_query":      corrected,
            "rewrites":        rewrite_query(corrected),
            "anchor_keywords": extract_anchor_keywords(corrected),
            "page_hint":       extract_hints(corrected).page_hint,
            "section_hint":    extract_hints(corrected).section_hint,
            "layout_hint":     extract_hints(corrected).layout_hint,
        },
        "generation": {
            "original_question":  corrected,
            "format_constraint":  extract_format_constraint(corrected),
            "disambiguation":     extract_disambiguation(corrected)[0],
            "must_distinguish":   extract_disambiguation(corrected)[1],
        },
    }
```

Ça marche. Tant qu'on est sur des PDF. Mais :

- **`page_hint` est absurde dès qu'on s'attaque à un Word.** Un fichier `.docx` n'a
  pas de pagination intrinsèque — la page change avec la fenêtre, la police,
  les marges. Si la question dit *« page 3 »*, ça ne désigne rien de stable, et
  le pousser dans le JSON envoie un faux signal au retriever.
- **`section_hint` est absurde sur un Excel.** Pas de TOC, pas de section. Un
  Excel a des feuilles et des colonnes — axes orthogonaux à un Word.
- **Le JSON se remplit de `null`.** Dix briques, dont trois ont quelque chose à
  dire pour la question courante : sept champs vides. Bruit visuel, et pour le
  consommateur en aval, ambiguïté entre *« la brique a tourné et n'a rien
  trouvé »* et *« la brique n'a même pas tourné »*.
- **Ajouter une brique** demande de modifier la fonction principale. Le 11ᵉ
  helper, le 12ᵉ, le 20ᵉ — chacun pollue la même fonction. Au bout d'un moment
  on a un pipeline de 60 lignes qu'on n'ose plus toucher.

Le vrai problème : **la cascade est statique, le contexte est dynamique**. Le
contexte (= « quel type de document on interroge », « quelles infos peuvent
même exister dans ce document ») doit piloter ce qui tourne. Une cascade en
dur n'a pas de poignée pour ça.

---

## 6.2 La forme cible

```python
def understand_question(
    question: str,
    *,
    document_type: str = "pdf",                # "pdf" | "word" | "excel" | "email" | "pptx"
    enable: dict[str, bool] | None = None,     # override fin par brique
    domain_hint: str = "",
    conversation_history: list | None = None,
) -> list[dict]:
    ...
```

Trois propriétés que cette signature doit garantir :

1. **Toujours une liste.** Une question simple = liste à 1 élément. Une question
   composée (« la prime ET les exclusions ») = liste à 2 éléments indépendants.
   Le consommateur en aval n'a jamais à se demander s'il faut traiter un dict
   ou une liste de dicts.
2. **Le JSON ne contient que des champs populés.** Si la brique `page_hint`
   n'est pas active (parce qu'on est sur un Word) ou n'a rien trouvé (parce
   que la question ne mentionne pas de page), le champ **n'apparaît pas**. Pas
   de `null`.
3. **`document_type` pilote le défaut, `enable` permet l'override fin.** La
   majorité des appels ne passent que `document_type` ; les power-users
   peuvent activer/désactiver brique par brique.

---

## 6.3 Le pattern : registre + presets

Deux ingrédients.

### 6.3.1 Le registre

Chaque capacité devient une `Brick` dans un registre central. La `Brick`
déclare :

- son **nom** (clé d'activation)
- sa **cible** : `retrieval` ou `generation` (où son output atterrit dans le JSON)
- son **extracteur** (`run`) : prend la question + un contexte, retourne soit
  `None` (rien trouvé / pas applicable), soit un `dict` de champs à merger
- les **types de document compatibles** (vide = tous)
- si elle a besoin d'un **LLM** (info utile pour le costing)

```python
@dataclass(frozen=True)
class Brick:
    name: str
    target: str                                       # "retrieval" | "generation"
    run: Callable[[str, dict], dict | None]
    compatible_doc_types: tuple[str, ...] = ()
    requires_llm: bool = False
    description: str = ""
```

Le registre lui-même est un dict :

```python
BRICKS: dict[str, Brick] = {
    "rewrite":         Brick("rewrite",         "retrieval",  _run_rewrite, requires_llm=True),
    "anchor_keywords": Brick("anchor_keywords", "retrieval",  _run_anchors),
    "page_hint":       Brick("page_hint",       "retrieval",  _run_page_hint,
                             compatible_doc_types=("pdf", "pptx")),
    "section_hint":    Brick("section_hint",    "retrieval",  _run_section_hint,
                             compatible_doc_types=("pdf", "word", "pptx")),
    "layout_hint":     Brick("layout_hint",     "retrieval",  _run_layout_hint),
    "format":          Brick("format",          "generation", _run_format),
    "disambiguation":  Brick("disambiguation",  "generation", _run_disambig),
    # ...
}
```

**Ajouter la 11ᵉ brique = une ligne.** Pas de modification du pipeline.

### 6.3.2 Les presets

Chaque type de document a une liste de briques actives par défaut.

```python
PRESETS: dict[str, list[str]] = {
    "pdf":   ["rewrite", "anchor_keywords", "page_hint", "section_hint", "layout_hint",
              "format", "disambiguation"],
    "word":  ["rewrite", "anchor_keywords",              "section_hint", "layout_hint",
              "format", "disambiguation"],   # ← pas de page_hint
    "excel": ["rewrite", "anchor_keywords", "sheet_hint", "column_hint",
              "format", "disambiguation"],
    # ...
}
```

C'est ici que se code la **connaissance métier** : « en Word, parler de page n'a
pas de sens », « en Excel, on parle de feuilles et de colonnes ». L'utilisateur
ne le sait pas forcément. Le système, lui, le sait.

### 6.3.3 L'orchestration

Le pipeline devient minuscule : pour chaque sous-question, pour chaque brique
active, lance, range le résultat dans `retrieval` ou `generation`.

```python
def _run_extraction(q, doc_type, active_bricks, ctx, intent):
    output = {
        "retrieval":  {"main_query": q},
        "generation": {"original_question": q},
        "_meta":      {"intent": intent, "document_type": doc_type, "bricks_active": []},
    }
    for name in active_bricks:
        brick = BRICKS[name]
        if brick.compatible_doc_types and doc_type not in brick.compatible_doc_types:
            continue
        result = brick.run(q, ctx)
        if not result:                   # None ou dict vide → on skip
            continue
        output[brick.target].update(result)
        output["_meta"]["bricks_active"].append(name)
    return output
```

Le pipeline ne sait pas **ce que** font les briques. Il sait juste les appeler
dans l'ordre déclaré et merger leurs résultats. Toute la connaissance métier
vit dans le registre (ce que fait chaque brique) et dans les presets
(lesquelles tourner par défaut).

---

## 6.4 Le cas Word

L'utilisateur dit *« la prime, page 3 du contrat »*. Le document est un `.docx`.

Avec la cascade naïve, `page_hint=3` part dans le JSON, le retriever de la couche
suivante essaie de filtrer sur `page=3`, et… il n'y a pas de page stable dans
un `.docx`. Soit il échoue silencieusement, soit il filtre faussement. Dans les
deux cas tu te retrouves à débugger un truc qui n'aurait jamais dû partir.

Avec le registre + preset Word :

- `PRESETS["word"]` ne contient pas `page_hint`.
- La brique `page_hint` ne tourne **pas**.
- Le champ `page_hint` n'apparaît **pas** dans le JSON.
- Le retriever en aval ne reçoit **aucun** signal trompeur.

Variante plus subtile : on peut vouloir préserver l'info que l'utilisateur a
**mentionné** une page, même si elle n'est pas stable. Une brique
`page_hint_approximate` peut être ajoutée au preset Word, qui produit
`{"page_hint": 3, "page_hint_approximate": true}`. Le retriever en aval choisit
alors d'utiliser ça comme post-filtre faible, pas comme filtre fort. C'est une
décision **produit**, pas d'architecture — et le pattern la rend triviale à
implémenter.

---

## 6.5 L'override par appel

Le preset est un défaut, pas une règle. À l'appel, on peut désactiver ou activer
brique par brique :

```python
# Désactiver une brique du preset (parce qu'on sait que la question est triviale)
plan = understand_question(q, document_type="pdf", enable={"rewrite": False})

# Activer une brique custom non comprise dans le preset
plan = understand_question(q, document_type="pdf", enable={"my_jurisdiction_brick": True})
```

Convention :

| `enable` | Effet |
|---|---|
| `None` | preset complet pour `document_type` |
| `{"X": False}` | preset moins X |
| `{"Y": True}` | preset plus Y (Y doit exister dans `BRICKS`) |
| `{"X": False, "Y": True}` | les deux à la fois |

---

## 6.6 Multi-questions : toujours une liste

> *« Quelles sont la prime et les exclusions ? »*

Deux questions agglutinées. Une seule passe de retrieval, une seule passe de
génération, ne donneront pas un bon résultat — la prime et les exclusions
vivent dans des sections différentes, exigent des extractions différentes.

La fonction décompose en interne (brique `decompose`, déjà LLM-driven), produit
deux sous-questions, et retourne deux entrées dans la liste. Chaque entrée est
un JSON complet, autonome, prêt à être traité indépendamment par la suite du
pipeline.

```python
plan = understand_question(
    "Quelles sont la prime et les exclusions ?",
    document_type="pdf",
)
# plan = [
#   { "retrieval": {"main_query": "Quelle est la prime ?",        ...}, "generation": {...} },
#   { "retrieval": {"main_query": "Quelles sont les exclusions ?", ...}, "generation": {...} },
# ]
```

Pour les questions simples, la liste a un seul élément. Pour les questions
composées, plusieurs. **Le consommateur boucle, point.** Plus de `if isinstance(...)`.

---

## 6.7 L'agentique : le LLM dans les briques, pas autour

Tentation : faire choisir les briques par un LLM. *« Ô grand modèle, vu cette
question, quelles briques dois-je activer ? »*

Mauvaise idée pour ce niveau-là. Trois raisons :

1. **Latence.** Un appel LLM de gating = +500 ms à 1 s sur chaque question, juste
   pour décider quoi tourner. Les briques elles-mêmes coûtent souvent moins que ça.
2. **Non-déterminisme.** Le même utilisateur, la même question, deux appels :
   possiblement deux ensembles de briques actives différents. Cauchemar pour
   reproduire un bug.
3. **Marginal return.** Les presets statiques par doc_type capturent ~95 % de
   la décision correcte. L'agentique optimiserait les 5 % restants au prix de
   la prévisibilité.

Le LLM reste utile, **à l'intérieur** des briques qui en ont vraiment besoin
(`rewrite`, `decompose`, `spell`), pas comme orchestrateur global. Si un cas
d'usage exige du gating intelligent, on peut ajouter une brique `auto_select`
opt-in qui le fait — mais elle reste désactivée par défaut.

Règle du pouce : **le LLM est un outil, pas un chef d'orchestre.**

---

## 6.8 Recette : ajouter une brique en quatre étapes

Tu veux extraire la juridiction (« pour le droit français… »).

1. **Écris l'extracteur** dans un fichier dédié :

   ```python
   # src/question/jurisdiction.py
   def extract_jurisdiction(q: str) -> str | None:
       ...
   ```

2. **Déclare la brique** dans le registre :

   ```python
   # src/question/bricks.py
   def _run_jurisdiction(q: str, _ctx: dict) -> dict | None:
       v = extract_jurisdiction(q)
       return {"jurisdiction": v} if v else None

   BRICKS["jurisdiction"] = Brick(
       "jurisdiction", "retrieval", _run_jurisdiction,
       compatible_doc_types=("pdf", "word"),     # pas pertinent pour excel/email
   )
   ```

3. **Ajoute-la aux presets** où elle a du sens :

   ```python
   # src/question/presets.py
   PRESETS["pdf"].append("jurisdiction")
   PRESETS["word"].append("jurisdiction")
   ```

4. **Teste** : un cas où la brique fire, un cas où elle ne fire pas, un cas sur
   un type de document non supporté.

Aucune autre partie du pipeline n'est touchée. Le test du pipeline complet ne
change pas (à part l'ajout d'un check « si la brique est listée, son output
apparaît »).

---

## 6.9 Récap

- Une seule fonction publique : `understand_question(question, *, document_type, enable=None, ...)`.
- Une liste de dicts en sortie, **toujours** (même pour une question simple).
- Le JSON ne contient **que** des champs réellement populés. Pas de `null`.
- Les briques sont des entrées d'un **registre**, activables par **preset**
  (défaut piloté par `document_type`) ou par **override** (`enable={...}`).
- Le contexte du document pilote le défaut. La connaissance métier (« la
  notion de page n'existe pas en Word ») vit dans les presets, pas dans le
  pipeline.
- L'agentique reste **à l'intérieur** des briques qui en ont besoin, jamais
  autour comme gating.

Le bénéfice n'est pas dans une brique en particulier — c'est dans le fait
qu'**ajouter, retirer, ou conditionner une brique ne touche pas le pipeline**.
Un pipeline qu'on touche peu est un pipeline qu'on casse peu.
