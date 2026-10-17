# LEAKSOURCE INVESTIGATOR 3.1 — enquête publique, responsable et vérifiable

**Objectif :** rechercher si `@d0nut2x` ou d'autres commentateurs ont indiqué *comment ils voient des épisodes d'anime avant la sortie*, et conserver les preuves pertinentes. L'enquête ne cherche pas à obtenir des fichiers vidéo non autorisés, des identités privées, des mots de passe ou des accès à des groupes fermés.

## Installation sur Windows

1. Décompresser le ZIP **en entier** dans un dossier, par exemple `Bureau\LEAKSOURCE_V3`.
2. Double-cliquer sur **`INSTALLER.bat`** (Python 3.10 ou supérieur requis). Installer Python depuis [python.org](https://www.python.org/downloads/) si nécessaire. L'installateur de LEAKSOURCE ne nécessite pas de droits administrateur ; Python/pip peuvent demander une configuration de PATH.
3. Double-cliquer sur **`DEMARRER.bat`**.
4. Choisir `all_free` puis **« DÉMARRER L'ENQUÊTE GRATUITE »**. Il ne faut aucune clé ni aucun abonnement. Le bouton **Arrêter** stoppe proprement les appels suivants.
5. Consulter l'onglet **Indices et preuves**. Double-cliquer pour ouvrir une source. Une citation affichée par un moteur de recherche ne prouve ni que l'original existe encore ni qu'elle correspond à la publication complète.
6. Pour une preuve visuelle, sélectionner une ligne puis **« Capture auto dans 8 s »** et afficher la page originale. **Attention : cette fonction prend une capture de tout l'écran**, après accord explicite, et l'enregistre seulement sur le PC. Prévoir de masquer tes données privées. Tu peux aussi ajouter une capture existante.
7. Cliquer sur **« Générer rapport HTML + CSV + JSON »** : les fichiers seront écrits dans `sorties/`. Ouvrir `sorties/rapport.html`.

## Ce qui marche à 0 € (sans clé)

| Source | Mode | Type de couverture | Limitation explicite |
| --- | --- | --- | --- |
| Bing RSS | Automatique | Pages publiques indexées, dont certaines discussions X/Reddit | Les moteurs ne répertorient pas tous les messages, et le flux peut être filtré ou indisponible |
| Google News RSS | Automatique | Articles d'actualité et sites indexés par Google News | Ce n'est pas une recherche de tous les commentaires |
| Bluesky AppView | API publique, sans connexion | Posts publics correspondant à des termes ciblés | Indexation, disponibilité, quotas et pagination limitent la couverture |
| Hacker News/Algolia | API publique, sans connexion | Commentaires publics indexés | Peu de discussions d'anime ; non pertinent pour la plupart des cas |
| Archives fournies en JSON/CSV/JSONL | Lecture locale | Messages et liens que tu as légitimement obtenus | Dépend de la qualité et de l'étendue de l'archive |

Il n'y a **pas de scraping automatique des pages X/Reddit**, pas de cookies récupérés, pas de CAPTCHA contourné, ni de proxies/IP tournantes. Les sites peuvent bloquer ou limiter les sources gratuites. **Une recherche vide n'est pas une preuve d'absence.**

La liste de requêtes est construite dans `sources.py` : mentions de `d0nut2x`, Bleach/TYBW, `YonkouProd`, `screener`, `source`, `leak`, ainsi que du français et du japonais. Le curseur « Requêtes par source » limite le travail effectué à chaque cycle. Un cache de 18 h évite de recommencer immédiatement les mêmes recherches ; la reprise est automatique.

## Reddit — analyse approfondie des commentaires (si autorisé)

Reddit exige une autorisation explicite avant d'accéder à son API. Si tu as reçu cette autorisation et un `Client ID / Client Secret`, copie `.env.example` en `.env` puis complète :

```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
```

Dans **Sources avancées**, utilise **« Explorer les threads Reddit autorisés »**. L'application :

- Cherche des *publications* pertinentes via Reddit, ainsi que des discussions Reddit déjà découvertes via les moteurs ;
- Ouvre ces publications via l'API Reddit **OAuth** et récupère les commentaires et réponses imbriquées avec PRAW (`replace_more`) ;
- Respecte les limites de threads, le plafond de commentaires analysés (un fil peut nécessiter plus de requêtes pour charger ses branches), le compteur de couverture, les codes d'erreur ;
- Ne stocke que les commentaires comportant des mots-clés associés à l'enquête ; les contenus Reddit stockés sont purgés automatiquement après 48 h lors de l'ouverture suivante de la base (précaution minimale ; vérifier les obligations supplémentaires de ton autorisation).

**Important :** Reddit recherche surtout les *posts*, pas tout l'historique de chaque commentaire. Même avec l'API, les discussions supprimées, privées ou indisponibles resteront hors de portée. Reddit peut refuser l'accès pour cet usage.

Demande d'accès : <https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data> et <https://support.reddithelp.com/hc/en-us/articles/16471395473812-Responsible-Builder-Policy>.

## X — API officielle (optionnelle, peut être facturée)

**Ne pas activer si budget 0 €.** L'option n'est jamais lancée automatiquement. Si tu disposes d'un Bearer Token X valide avec droits adaptés, inscris-le dans `.env` :

```
X_BEARER_TOKEN=...
```

Depuis l'onglet Sources avancées, choisir le maximum de pages API puis confirmer explicitement le risque de facturation. Le module interroge la recherche officielle de posts/réponses autour de `@d0nut2x` ; l'accès archive nécessite un niveau habilité. Les limites temporelles et historiques imposées par X restent applicables. **Le programme n'impose pas de plafond monétaire absolu** : le régler sur la console X si tu utilises cette option.

Politiques : <https://help.x.com/en/rules-and-policies/x-automation> et API : <https://docs.x.com/>.

## Brave — plus d'indexation, seulement en option

Brave Search API propose 5 $ de crédits mensuels pour le plan Search (environ 1 000 requêtes), mais exige actuellement une carte bancaire à l'inscription ; attention à toute dépense au-delà des crédits. Le programme ne peut pas plafonner la facturation de ton compte Brave, même s'il limite ses propres requêtes.

Lien : <https://brave.com/search/api/>

Si tu as une clé Brave, renseigne `BRAVE_SEARCH_API_KEY=...` dans `.env`, puis choisis **`all_plus`** (Brave + RSS + Bluesky + Hacker News) ou `brave` (Brave uniquement). Le mode `all_free` ne l'utilise pas.

**Correction Brave V3.1** : les résultats de recherche Brave ne sont pas conservés dans SQLite, CSV ou JSON, conformément aux conditions officielles datées du 1er septembre 2026. Ils restent seulement en mémoire vive pendant l'utilisation de l'application, dans l'onglet **4 · Résultats Brave (temporaires)**, et disparaissent à sa fermeture. Pour constituer une preuve, examine puis note les informations directement depuis la publication originale. Conditions : <https://api-dashboard.search.brave.com/documentation/resources/terms-of-service>.

**Migration** : l'ancienne V3 sauvegardait potentiellement les résultats Brave. Si tu copies la base de l'ancienne V3 dans le nouveau dossier, les anciens `search_snippet` seront supprimés à l'ouverture. Les exports générés avec l'ancienne version ne sont pas supprimés automatiquement ; efface-les s'ils contiennent des extraits Brave.

**Réglage conseillé à 0 €** : le plan Brave doit être **Prepaid**, avec **0 $ de crédit acheté** et **Auto-reload désactivé**. Vérifie également les limites d'utilisation dans ton tableau de bord Brave.

## Fichiers importants

```
DEMARRER.bat                   lancer la fenêtre
INSTALLER.bat                 installer les dépendances Python
LANCER_TESTS.bat              lancer les tests unitaires
app.py                        interface graphique locale
engine.py                     détection, preuves, SQLite, rapport
sources.py                    connecteurs externes conformes
.env.example                  modèle de clés (ne pas partager)
requirements.txt              bibliothèques Python
examples/exemple_messages.json jeu de démonstration fictif
sorties/enquete.sqlite3       sauvegarde locale, crée à l'exécution
sorties/rapport.html          rapport généré
sorties/preuves.csv           tableau Excel compatible
sorties/preuves.json          export machine
sorties/captures/             images originales ajoutées localement
```

## Bien interpréter le résultat

- `EXTRAIT INDEXÉ — NON VÉRIFIÉ` = moteur de recherche, **pas** preuve. Ne pas conclure que l'auteur a dit ces mots exacts sur le site actuel.
- `MESSAGE FOURNI` = données JSON/CSV ou texte ajouté par l'utilisateur, à authentifier.
- `API AUTORISÉE` = message obtenu par un connecteur officiel, sans garantie de véracité des propos.
- Score /100 = **pertinence des mots et indices**, **pas probabilité** que la source possède un épisode.
- Questions et réponses ne sont reliées automatiquement **que** quand les IDs parent/enfant le démontrent.
- Les captures de ton écran montrent ce que ton ordinateur affichait à cet instant. Elles ne prouvent pas que la personne dit vrai.
- Le rapport affiche les sources interrogées, les incidents d'accès, les résultats conservés et les zones manquantes.
- Ne pas harceler de leakeurs, contacter leur entourage, divulguer de données privées ou chercher à accéder à des services fermés sans invitation et autorisation.

## Test de démonstration (hors ligne)

Dans « Importer des messages JSON/CSV », sélectionne `examples/exemple_messages.json` pour vérifier la mécanique de question-réponse. **Ces deux messages sont entièrement fictifs**. Pour les supprimer, ferme le programme et supprime `sorties/enquete.sqlite3` et les éventuels fichiers `.sqlite3-wal`/`.sqlite3-shm` ; ne mélange pas les données de démo à une véritable enquête.

Pour vérifier le cœur du moteur sans Internet : `LANCER_TESTS.bat`.

## Ce que le programme NE peut pas faire

Il n'accède **pas** à tous les commentaires X/Reddit gratuitement ; n'invente **pas** des noms de sites secrets, ne rejoint **pas** des groupes Discord/Telegram privés, et ne récupère **pas** des épisodes. Une enquête exhaustive sur les archives complètes de X demande un accès aux données que cette version ne possède pas. Dans les groupes privés, aucun automatisme de lecture n'est proposé sans permission explicite et API prévue à cet effet.
