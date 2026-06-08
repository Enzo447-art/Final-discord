# ⚡ Cord — Clone Discord en Flask

Interface Discord complète avec : messagerie temps réel, serveurs, amis, appels, profil, recherche.

## 🚀 Lancer en local

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Lancer
python app.py
```

Ouvrir → http://localhost:5000

---

## 🌐 Déployer sur Render (gratuit)

### Méthode simple (recommandée)

1. **Pusher sur GitHub**
```bash
git init
git add .
git commit -m "init cord"
git remote add origin https://github.com/TON_USER/cord.git
git push -u origin main
```

2. **Créer un service sur Render**
   - Aller sur https://render.com → **New → Web Service**
   - Connecter votre repo GitHub
   - Render détecte automatiquement `render.yaml`
   - Cliquer **Deploy**

3. **Variables d'environnement** (auto-générées via render.yaml)
   - `SECRET_KEY` → généré automatiquement
   - `DATABASE_URL` → PostgreSQL gratuit inclus

### Méthode manuelle

| Champ | Valeur |
|-------|--------|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn --worker-class eventlet -w 1 app:app --bind 0.0.0.0:$PORT` |

**Variables d'env à ajouter :**
- `SECRET_KEY` = une chaîne aléatoire longue
- `DATABASE_URL` = URL PostgreSQL de Render

---

## 🏗️ Structure

```
discord_clone/
├── app.py               # Application Flask principale
├── requirements.txt     # Dépendances Python
├── render.yaml          # Config déploiement Render
├── Procfile             # Config gunicorn
├── templates/
│   ├── landing.html     # Page d'accueil
│   ├── auth.html        # Login / Register
│   └── app.html         # Interface principale
└── static/
    └── uploads/         # Avatars et icônes serveurs
```

## ✨ Fonctionnalités

- 💬 **Messagerie temps réel** via Socket.IO
- 🏰 **Serveurs** — création, invitation, canaux texte/voix
- 👥 **Amis** — code ami, demandes, acceptation
- 📞 **Appels** — interface d'appel audio/vidéo (WebRTC ready)
- 🔍 **Recherche** de serveurs publics
- 🎨 **Profils** — photo, tag unique, code ami
- 📱 **Responsive** — adapté mobile

## 🗄️ Base de données

- **Local** : SQLite automatique (`instance/discord.db`)
- **Production** : PostgreSQL (Render)

La BDD est créée automatiquement au démarrage.
