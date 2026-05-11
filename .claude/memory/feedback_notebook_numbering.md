---
name: Notebook numbering convention
description: Always prefix notebooks in notebooks/ with a 2-digit chapter number (e.g. 06_understanding_question.ipynb)
type: feedback
originSessionId: ab537f14-b206-4abe-b2c3-e4e16a6f564e
---
Préfixer chaque nouveau notebook dans `notebooks/` par un numéro à 2 chiffres correspondant à son chapitre, suivi d'un underscore et d'un nom descriptif.

Exemples : `04_parsing_pdf_page.ipynb`, `05_test_conversion_pdf_word.ipynb`, `06_understanding_question.ipynb`.

**Why:** L'utilisateur structure ses notebooks comme un livre/cours par chapitres. Demande explicite : "tu vas à chaque fois numéroter les notebooks".

**How to apply:** À chaque création de notebook dans ce projet (et lors d'un éventuel rename de l'existant), utiliser ce format `NN_<nom>.ipynb`. Demander le numéro si pas évident depuis le contexte.
