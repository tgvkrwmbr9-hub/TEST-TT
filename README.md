# STYCH TYNY — boutique d'eBooks Telegram

Bot Python (Aiogram 3) + SQLite persistant. Paiement crypto (SOL, BTC, ETH, USDC-ETH) avec QR code et TXID validé à la main, virement/PayPal via le chat admin, roue 24 h, codes promo, statistiques, bannissement automatique (2 faux TXID).

## Où sont tes données
Tout est dans `/opt/stych_tyny/data/` : `stych.db` (base), `storage/` (PDF et couvertures), `backups/`, `logs/`.
Une mise à jour remplace le code mais **jamais** ce dossier ni `.env`.

## Installation depuis iPhone (≈ 20 min)

**1. Créer le bot.** Dans Telegram, ouvre @BotFather → `/newbot` → note le **token**. Ne le partage jamais.
**2. Trouver ton ID.** Écris à @userinfobot : il te donne ton **ID numérique** (= `ADMIN_ID`).
**3. Louer un VPS** Ubuntu 24.04 (n'importe quel hébergeur). Note l'IP et le mot de passe root.
**4. Installer l'app Termius** (App Store). Crée un hôte avec l'IP, l'utilisateur `root`, connecte-toi.
**5. Envoyer le projet.** Dans Termius, onglet SFTP : envoie `stych_tyny.zip` dans `/root`. Puis :
```
apt-get update && apt-get install -y unzip
cd /root && unzip stych_tyny.zip && cd stych_tyny
ls -a
```
Le fichier `.env` est déjà rempli (token, ID, @Stychfr) : vérifie qu'il apparaît dans `ls -a`. Ne partage jamais ce zip.
**6. Installer et lancer 24h/24 :**
```
sudo bash deploy/install.sh
sudo systemctl status stych-tyny
```
Le bot tourne, redémarre seul en cas de panne (5 s) et au redémarrage du VPS. Sauvegarde automatique chaque jour à 03:30.
**7. Configurer dans Telegram :** ouvre ton bot → `/admin` → 💰 Paiement : saisis tes 4 adresses crypto (vérifie-les à deux fois). Rien n'est inventé : sans adresse, le moyen de paiement reste indisponible.

## Utilisation
- **Ajouter un eBook :** `/admin` → ➕ Ajouter : titre, prix, catégorie, description, avantages, photo, PDF. Tu vois la prévisualisation, puis **Publier**. PDF : 20 Mo max (limite Telegram).
- **Modifier :** `/admin` → 📚 Produits → ✏️ Modifier → champ → nouvelle valeur (ou nouvelle photo / nouveau PDF).
- **Valider un paiement :** tu reçois « NOUVELLE COMMANDE À VÉRIFIER ». **Vérifie le TXID sur un explorateur blockchain (et la réception des fonds)** puis ✅ ou ❌. Un 2ᵉ ❌ sur un faux TXID bannit le client (débannage : `/admin` → Clients bannis).
- **Virement / PayPal :** le client ouvre ton chat avec un message prérempli ; tu valides toi-même après avoir vu l'argent arriver.
- **Commandes :** `/admin` `/stats` `/orders` `/products` `/broadcast texte` `/promo CODE 10%` (ou `5€`, + nb max d'utilisations) `/test` (commande de test sans paiement). `/stop` côté client désactive les messages promo.

## Sauvegardes et restauration
Automatique : `data/backups/` (base + PDF), 14 jours conservés. Manuel : `sudo -u stych /opt/stych_tyny/venv/bin/python /opt/stych_tyny/backup.py`.
**Restaurer :**
```
sudo systemctl stop stych-tyny
sudo -u stych /opt/stych_tyny/venv/bin/python /opt/stych_tyny/restore.py          # liste
sudo -u stych /opt/stych_tyny/venv/bin/python /opt/stych_tyny/restore.py stych-AAAAMMJJ-HHMMSS.db.gz
sudo systemctl start stych-tyny
```
Conseil : copie régulièrement `data/backups/` hors du VPS (Termius SFTP), car une sauvegarde sur la même machine ne protège pas d'une panne du serveur.

## Mise à jour sans perte
Envoie le nouveau zip, décompresse-le dans un dossier, puis `sudo bash deploy/update.sh` : sauvegarde, remplace le code, redémarre.

## Sécurité
Token et ID uniquement dans `.env` (droits 600). Accès admin vérifié côté serveur par `ADMIN_ID`, tentatives refusées journalisées. PDF hors de tout dossier public, envoyés seulement après vérification en base de l'achat. TXID uniques (réutilisation impossible). Validation atomique : pas de double validation ni double livraison. Anti-spam : 10 actions / 5 s. Si ton token fuite : @BotFather → `/revoke`. Pense à sécuriser le VPS (mises à jour, clé SSH).

## Limites à connaître
- Le cours crypto vient de l'API publique CoinGecko ; en cas d'échec, le bot affiche la somme en euros.
- Un TXID seul ne prouve rien : c'est à toi de le vérifier.
- Les conversations en cours (saisie d'un TXID) sont en mémoire : un redémarrage les interrompt, mais aucune donnée enregistrée n'est perdue.
- Pas de remboursement automatique ni de factures PDF pour l'instant.
- Logs : `data/logs/bot.log` ou `sudo journalctl -u stych-tyny -f`.
