WI-PRESENCE — version QR serveur + diagnostic

Cette version corrige le probleme principal du QR expire sur certains PC : le QR
est maintenant signe et date par Google Apps Script, pas par l'horloge du PC.
Le widget synchronise aussi son planning sur l'heure serveur Google.

Planning de production
- Lundi, mardi et jeudi
- 07:30–08:30 GMT
- Mode test disponible dans Parametres

1. Mettre a jour Google Apps Script

- Ouvrir le projet Apps Script lie au fichier Google Sheets.
- Remplacer tout le contenu de script.js par le script.js fourni ici.
- Enregistrer.
- Deploy > Manage deployments > Edit (ou New deployment).
- Type : Web app.
- Execute as : Me.
- Who has access : Anyone.
- Deployer la nouvelle version et conserver l'URL /exec.

Important : l'application Windows ne peut pas corriger un ancien deploiement
Apps Script. Il faut deployer cette nouvelle version avant le premier test.

2. Installer sur le PC du staff

- Extraire le ZIP dans un dossier local.
- Lancer Installer-WI-PRESENCE.exe.
- L'assistant installe Python et les dependances, puis cree les raccourcis
  Bureau et Menu Demarrer.
- Ne pas envoyer le fichier EXE seul par Gmail. Gmail bloque souvent les EXE.
  Envoyer le ZIP via Google Drive, puis extraire le ZIP avant de lancer l'EXE.

3. Utiliser le diagnostic

- Ouvrir l'icone WI-PRESENCE puis Parametres.
- Cliquer sur Lancer le diagnostic.
- Le rapport affiche : connexion Google, heure serveur, heure du PC, ecart
  d'horloge, source du QR, planning, lignes de presence et dernieres erreurs.

Lecture rapide des erreurs
- Service Google impossible : verifier Internet et l'URL /exec.
- Page HTML Google : le nouveau script n'est pas encore redeploye en Web app.
- QR en attente : attendre la connexion, puis relancer le diagnostic.
- Email echoue : verifier l'adresse et executer authorizeReports() une fois
  dans Apps Script pour autoriser MailApp.

Fichiers inclus
- Installer-WI-PRESENCE.exe : assistant graphique autonome.
- script.js : backend Apps Script complet.
- presence.py : application Windows complete.
- wi-presence-icon.ico : icone Windows.
