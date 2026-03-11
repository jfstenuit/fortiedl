# Installation Guide

This guide covers installation on a Linux server for production use.  
No programming knowledge is required.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Git | any | To clone the repository |
| Docker CE | 24 + | Includes Docker Compose v2 |

Docker must be configured to start on boot (see [Step 6](#6-auto-start-on-server-reboot)).

---

## 1. Clone the repository

```bash
git clone <repository-url> /opt/blocklist-manager
cd /opt/blocklist-manager
```

---

## 2. Create and edit the configuration file

```bash
cp .env.example .env
```

Open `.env` with a text editor and fill in **all** values:

```bash
nano .env          # or: vi .env
```

| Variable | Description |
|---|---|
| `OIDC_DISCOVERY_URL` | Well-known URL of your identity provider (see below) |
| `OIDC_CLIENT_ID` | Application (client) ID from the IdP registration |
| `OIDC_CLIENT_SECRET` | Client secret from the IdP registration |
| `OIDC_REQUIRED_GROUP` | Display name of the group whose members may log in |
| `SESSION_SECRET` | Random secret — generate one: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `LIST_BASIC_AUTH_USER` | Username the Fortigate uses to fetch the EDL |
| `LIST_BASIC_AUTH_PASSWORD` | Strong password for the above |
| `DB_PASSWORD` | Strong password for the internal database user |
| `DB_USER` | Database username (e.g. `blocklist`) |
| `DB_NAME` | Database name (e.g. `blocklist`) |

**Azure AD / Entra ID** discovery URL:
```
https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration
```

**Authentik** discovery URL:
```
https://<authentik-host>/application/o/<app-slug>/.well-known/openid-configuration
```

---

## 3. Install the TLS certificate

nginx expects two PEM files in `nginx/certs/`:

| File | Contents |
|---|---|
| `nginx/certs/cert.pem` | Your server certificate (and any intermediate chain) |
| `nginx/certs/privkey.pem` | The corresponding private key |

```bash
mkdir -p nginx/certs
```

**Option A — Certificate from an internal PKI or commercial CA**

Copy the files directly:
```bash
cp /path/to/your/certificate.pem  nginx/certs/cert.pem
cp /path/to/your/private-key.pem  nginx/certs/privkey.pem
chmod 640 nginx/certs/privkey.pem
```

If your certificate and intermediate chain are separate files, concatenate them:
```bash
cat server.crt intermediate.crt > nginx/certs/cert.pem
```

**Option B — Let's Encrypt (certbot)**

After obtaining the certificate with certbot, link the files:
```bash
ln -sf /etc/letsencrypt/live/<your-domain>/fullchain.pem nginx/certs/cert.pem
ln -sf /etc/letsencrypt/live/<your-domain>/privkey.pem   nginx/certs/privkey.pem
```

Add a certbot renewal hook to reload nginx after each renewal:
```bash
echo "sudo docker compose -f /opt/blocklist-manager/docker-compose.yml exec proxy nginx -s reload" \
  | sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-blocklist-nginx.sh
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-blocklist-nginx.sh
```

---

## 4. Start the application

```bash
sudo docker compose up -d
```

All three containers (database, application, reverse proxy) will start and restart
automatically if they crash.

Check that everything is running:
```bash
sudo docker compose ps
```

All three services should show `running (healthy)` or `Up`.

Follow the logs to confirm the application started cleanly:
```bash
sudo docker compose logs -f app
```

Press `Ctrl-C` to stop following.

---

## 5. Verify the installation

Open `https://<your-hostname>` in a browser.  
You should be redirected to your identity provider's login page.

The Fortigate EDL endpoint is at:
```
https://<your-hostname>/api/list?id=<list-name>
```

Test it with curl:
```bash
curl -u <LIST_BASIC_AUTH_USER>:<LIST_BASIC_AUTH_PASSWORD> \
     https://<your-hostname>/api/list?id=default
```

An empty list returns an empty body with HTTP 200.

---

## 6. Auto-start on server reboot

The containers are configured with `restart: unless-stopped`, meaning Docker will
restart them automatically after a crash or reboot — provided the Docker daemon
itself starts on boot.

Enable the Docker daemon to start on boot (run once):
```bash
sudo systemctl enable docker
```

Verify:
```bash
sudo systemctl is-enabled docker
# expected output: enabled
```

To confirm the full setup survives a reboot:
```bash
sudo reboot
# after the server comes back:
sudo docker compose -f /opt/blocklist-manager/docker-compose.yml ps
```

---

## Updating to a new version

```bash
cd /opt/blocklist-manager
git pull
sudo docker compose up -d --build
```

The database volume is preserved across rebuilds.  
Database migrations run automatically on application startup.

---

## Stopping the application

```bash
sudo docker compose down          # stop containers, keep data
sudo docker compose down -v       # stop containers AND delete the database
```
