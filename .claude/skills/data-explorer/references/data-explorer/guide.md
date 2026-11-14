# Guide de l'explorateur de données

## Encodage

Détecter l'encodage avant de charger le fichier, puis le préciser à pandas (`encoding=...`).

| Encodage | Indice | Traitement |
|----------|--------|------------|
| UTF-8 | BOM présent, ou lecture sans erreur | Valeur par défaut (`utf-8-sig` si BOM) |
| Windows-1252 (cp1252) | Fichier exporté d'Excel ou d'un logiciel Windows ; « é » mal lu en UTF-8 | `encoding="cp1252"` |
| Latin-1 (ISO-8859-1) | Ancien export, souvent de sites publics | `encoding="latin-1"` |

Contrôle : après chargement, vérifier qu'aucun libellé ne contient « Ã© » ou « � ». Si c'est le cas, l'encodage choisi est faux.

## Fichiers français

- Séparateur souvent `;` (`sep=";"`) et décimale souvent `,` (`decimal=","`).
- Dates souvent au format JJ/MM/AAAA (`dayfirst=True`).
- Codes INSEE, codes postaux et codes de département à lire en texte (`dtype=str`) pour garder les zéros initiaux et les codes corses 2A et 2B.

## Valeurs aberrantes

### Écart interquartile (méthode par défaut)
- Aberrante si inférieure à Q1 − 1,5 × IQR ou supérieure à Q3 + 1,5 × IQR.

### Score z (gros volumes)
- Aberrante si |z| > 3.

Une valeur aberrante n'est pas forcément une erreur : la signaler, ne pas la supprimer.

## Format du profil

Pour chaque colonne :
- type, nombre de valeurs distinctes, taux de valeurs manquantes ;
- numérique : minimum, maximum, moyenne, médiane, écart type ;
- catégorielle : 5 valeurs les plus fréquentes avec leurs effectifs.
