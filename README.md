# STYCH TYNY sur GitHub + Railway (depuis iPhone)

## 1. GitHub
1. github.com → **New repository** → nom `stych-tyny` → **Private** (obligatoire) → Create.
2. Dans l'app Fichiers, touche `stych_tyny_railway.zip` pour le décompresser.
3. Sur le repo : **Add file → Upload files**, sélectionne **tous** les fichiers du dossier décompressé → **Commit changes**.
4. ⚠️ Ne mets JAMAIS ton token ni `railway_variables.txt` sur GitHub.

## 2. Railway
1. railway.com → **New Project → Deploy from GitHub repo** → choisis `stych-tyny`.
2. Ouvre le service → **Variables → Raw Editor** → colle le contenu de `railway_variables.txt` → Update.
3. **Volume (indispensable)** : sur le projet, **+ New → Volume**, attache-le au service, **Mount path : `/data`**.
   Sans volume, la base est effacée à chaque déploiement : le bot refuse alors de démarrer et te le dit dans les logs.
4. **Deployments → Logs** : tu dois voir « STYCH TYNY démarré ». Puis dans Telegram : `/start`, `/admin`.
5. Garde **un seul** réplica (par défaut).

## 3. Configuration dans Telegram
`/admin` → 💰 Paiement : saisis tes 4 adresses crypto. Ajouter un eBook : `/admin` → ➕ Ajouter (titre, prix, catégorie, description, avantages, photo, PDF ≤ 20 Mo) → prévisualisation → Publier.

## 4. Données, sauvegardes, restauration
- Tout vit sur le volume `/data` (base, PDF, couvertures, sauvegardes) : redéployer ou mettre à jour le code ne les touche pas.
- Une sauvegarde est faite à chaque démarrage, puis chaque nuit à 03:30 UTC, et **le fichier t'est envoyé en message privé** sur Telegram (copie hors serveur). `/backup` en force une.
- **Restaurer** : envoie le fichier `.db.gz` au bot avec la légende `/restore`, puis Railway → Restart.

## 5. Mise à jour
Modifie / remplace les fichiers sur GitHub : Railway redéploie seul, les données restent.

## 6. Utilisation
`/admin` `/stats` `/orders` `/products` `/broadcast texte` `/promo CODE 10%` (ou `5€`, + nb max) `/test` (commande de test sans paiement) `/backup`.
Valider un paiement : vérifie le TXID sur un explorateur blockchain et la réception des fonds, puis ✅ ou ❌. Un 2ᵉ faux TXID refusé = bannissement (débannir : Admin → Clients bannis).

## Sécurité
Variables uniquement dans Railway. Admin vérifié côté serveur (`ADMIN_ID`), tentatives refusées journalisées. PDF envoyés seulement après vérification de l'achat en base. TXID uniques, validation atomique (pas de double livraison). Si le token fuite : @BotFather → `/revoke`, puis mets le nouveau dans Railway → Variables.
