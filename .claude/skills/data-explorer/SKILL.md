---
name: data-explorer
description: |
  Explore et profile un fichier de données CSV, TSV ou Excel : résumé des colonnes, valeurs manquantes, valeurs aberrantes, doublons, corrélations et rapport de qualité. À utiliser quand on demande « analyse ces données », « résume ce CSV », « profile ce fichier », « trouve les valeurs aberrantes » ou « vérifie la qualité des données ».
user-invocable: true
version: 2.2.0-fr
---
# Explorateur de données

## Rôle
Prendre un fichier CSV, TSV ou Excel, en dresser le profil, contrôler sa qualité et en tirer une première analyse.

## Règle absolue
Chaque chiffre du rapport sort d'un calcul exécuté sur le fichier (script pandas lancé avec Bash). Aucun chiffre estimé, arrondi de tête ou inventé. Si un calcul échoue, le dire au lieu de le remplacer par une estimation.

## Déroulé

### Étape 1 : chargement
- Détecter le format (CSV, TSV, XLSX) et, pour un CSV, le séparateur (`,` ou `;`) et le séparateur décimal (`.` ou `,`).
- Détecter l'encodage (voir [guide](references/data-explorer/guide.md)).
- Donner le nombre de lignes et de colonnes et le type déduit de chaque colonne.

### Étape 2 : profil
- Pour chaque colonne : type, nombre de valeurs distinctes, taux de valeurs manquantes, et pour les colonnes numériques minimum, maximum, moyenne, médiane.
- Colonnes catégorielles : les 5 valeurs les plus fréquentes avec leurs effectifs.
- Colonnes numériques : forme de la distribution (asymétrie, aplatissement).

### Étape 3 : contrôle qualité
- Valeurs manquantes : où elles se concentrent et si elles semblent liées à d'autres colonnes. Présenter ce lien comme une hypothèse, pas comme une conclusion.
- Valeurs aberrantes : méthode de l'écart interquartile, et score z pour les gros volumes.
- Lignes en double.
- Incohérences de type (nombres stockés en texte, dates dans des formats différents, etc.).

### Étape 4 : corrélations
- Corrélations de Pearson et de Spearman entre colonnes numériques.
- Signaler les corrélations fortes (|r| > 0,7).
- Lien entre une colonne catégorielle et une colonne numérique : test F de l'ANOVA.

### Étape 5 : constats et pistes
- Résumer les 3 constats principaux.
- Proposer 3 pistes d'analyse et laisser l'utilisateur choisir (AskUserQuestion).

## Livrables
- Rapport de profil en Markdown, en français.
- Bilan qualité sous forme de liste de contrôles (manquants, doublons, aberrations, types), chacun avec son chiffre mesuré. Pas de note globale sur 100 : elle n'aurait pas de définition stable.
- Pistes d'analyse.

## Outils
- Bash : scripts Python pandas pour le profil.
- Read : lecture directe d'un petit fichier.
- Pour les graphiques, utiliser la skill `dataviz` si elle est disponible.

## Quand ne pas utiliser cette skill
- Pour produire des graphiques : skill `dataviz`.
- Pour optimiser des requêtes SQL ou générer un rapport métier : skill `data-analyst`.
- Pour produire un fichier Word ou PowerPoint : skills `docx` ou `pptx`.
