# Deploying on Pterodactyl behind Nginx

This is how GitPulse runs in production: a Pterodactyl server using a generic Python egg,
with Nginx on the host terminating HTTPS for `gitpulse.saiyiidev.com` and forwarding
`/webhook` to the port Pterodactyl gives the server.

```
GitHub ──HTTPS──▶ gitpulse.saiyiidev.com (Nginx :443) ──▶ 127.0.0.1:<port> (Pterodactyl container)
```

## 1. Allocation

GitPulse needs one port for its webhook server. In the panel admin area, add an allocation
to the node (**Nodes → your node → Allocation**). Two options:

- **IP `127.0.0.1`** (recommended): the port is only reachable from the host, so the only
  way in is through Nginx.
- The node's public IP: works too, but the raw port is then open to the internet. Requests
  are still signature-checked, but it's cleaner to keep it local. Note that Docker publishes
  ports before `ufw` rules apply, so `ufw deny` won't hide it.

Give the server that allocation as its primary one. Pterodactyl passes the port to the
container as `SERVER_PORT`, which GitPulse reads automatically, so `WEBHOOK_PORT` can stay
empty.

## 2. Create the server

Create a server with your Python egg (the generic one from
[pelican-eggs](https://github.com/pelican-eggs/generic) works). The variable names vary a
little between egg versions, but you want:

| Egg variable | Value |
| --- | --- |
| Docker image | Python 3.11 or newer |
| App py file / `PY_FILE` | `main.py` |
| Requirements file / `REQUIREMENTS_FILE` | `requirements.txt` |
| Git repo address / `GIT_ADDRESS` (if your egg has it) | `https://github.com/saiyii/gitpulse` |
| Auto update / `AUTO_UPDATE` | `1` if you want a `git pull` on every start |

If your egg doesn't do git, upload the repository files with the file manager or SFTP.

## 3. Secrets

With the file manager (or SFTP), create in the server root:

- `.env`, based on `.env.example`. Use `WEBHOOK_HOST=0.0.0.0` (inside the container) and
  leave `WEBHOOK_PORT` empty.
- `private-key.pem`, the GitHub App private key.

`gitpulse.db` is created on first start in the same folder, so subscriptions survive
restarts and egg reinstalls as long as you don't wipe the files.

## 4. Start it

Start the server. The console should show:

```
gitpulse.github.webhooks: webhook server listening on 0.0.0.0:25570
gitpulse.bot: logged in as GitPulse#1234, in 1 servers
```

From the host, check that the port answers:

```sh
curl http://127.0.0.1:25570/health
# OK
```

## 5. DNS

In Cloudflare (**saiyiidev.com → DNS → Records**), add:

| Type | Name | Content |
| --- | --- | --- |
| `CNAME` | `gitpulse` | `vps.saiyiidev.com` |

(an `A` record to the VPS IP works just as well). Whether the cloud is orange (proxied) or
grey (DNS only) depends on which TLS option you pick below.

## 6. HTTPS: pick one

### Option A: Cloudflare proxy + Origin certificate

Traffic goes GitHub → Cloudflare → your VPS. Cloudflare handles the public certificate, and
a free Cloudflare Origin certificate encrypts the hop to your server.

1. Set the `gitpulse` record to **Proxied** (orange cloud).
2. **SSL/TLS → Overview**: set the mode to **Full (strict)**.
3. **SSL/TLS → Origin Server → Create Certificate**. Keep the defaults (RSA, 15 years),
   hostnames `*.saiyiidev.com, saiyiidev.com`. Save the two blocks on the VPS:

   ```sh
   sudo mkdir -p /etc/ssl/cloudflare
   sudo nano /etc/ssl/cloudflare/saiyiidev.com.pem   # certificate
   sudo nano /etc/ssl/cloudflare/saiyiidev.com.key   # private key
   sudo chmod 600 /etc/ssl/cloudflare/saiyiidev.com.key
   ```

4. If **Bot Fight Mode** or a WAF rule is on, GitHub's requests can get challenged (you'll
   see `403` in Recent Deliveries). Add a WAF custom rule *Skip* for
   `http.host eq "gitpulse.saiyiidev.com" and http.request.uri.path eq "/webhook"`
   (Bot Fight Mode itself can't be skipped on the free plan, so turn it off if it blocks).

Use these lines in the Nginx config below:

```nginx
ssl_certificate     /etc/ssl/cloudflare/saiyiidev.com.pem;
ssl_certificate_key /etc/ssl/cloudflare/saiyiidev.com.key;
```

### Option B: DNS only + Let's Encrypt (Certbot)

GitHub talks to your VPS directly.

1. Set the `gitpulse` record to **DNS only** (grey cloud).
2. Start with a plain HTTP config, Certbot will add the HTTPS part itself.
   `/etc/nginx/sites-available/gitpulse.conf`:

   ```nginx
   server {
       listen 80;
       listen [::]:80;
       server_name gitpulse.saiyiidev.com;
       client_max_body_size 25m;

       location = /webhook {
           proxy_pass http://127.0.0.1:25570;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_read_timeout 15s;
       }

       location = /health {
           proxy_pass http://127.0.0.1:25570;
       }

       location / {
           return 404;
       }
   }
   ```

3. Enable it (see step 7 for the `ln -s` and reload commands), then:

   ```sh
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d gitpulse.saiyiidev.com --redirect
   ```

Certbot adds the `listen 443 ssl` lines with its certificate
(`/etc/letsencrypt/live/gitpulse.saiyiidev.com/...`), the HTTP to HTTPS redirect, and a
renewal timer. You can skip step 7's config in that case, only run its enable commands.

## 7. Nginx config

For option A, `/etc/nginx/sites-available/gitpulse.conf` (replace `25570` with your port):

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name gitpulse.saiyiidev.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name gitpulse.saiyiidev.com;

    ssl_certificate     /etc/ssl/cloudflare/saiyiidev.com.pem;
    ssl_certificate_key /etc/ssl/cloudflare/saiyiidev.com.key;

    # GitHub payloads can be up to 25 MB
    client_max_body_size 25m;

    location = /webhook {
        proxy_pass http://127.0.0.1:25570;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # GitHub waits 10 seconds at most, GitPulse answers right away
        proxy_read_timeout 15s;
    }

    location = /health {
        proxy_pass http://127.0.0.1:25570;
    }

    location / {
        return 404;
    }
}
```

If your allocation uses the public IP instead of `127.0.0.1`, put that IP in `proxy_pass`.

Enable it and reload:

```sh
sudo ln -s /etc/nginx/sites-available/gitpulse.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 8. Check

```sh
curl https://gitpulse.saiyiidev.com/health
# OK
```

Then in the GitHub App settings, **Advanced → Recent Deliveries**, redeliver the `ping`.
It should come back `200` with `pong`. Publish a release on a subscribed repo and it shows
up in Discord a second later.

## Updating

With `AUTO_UPDATE=1` and a git egg, restarting the server pulls the latest commit and
reinstalls requirements. Otherwise upload the new files and restart.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `401 invalid signature` in Recent Deliveries | `GITHUB_WEBHOOK_SECRET` doesn't match the app's webhook secret |
| `502 Bad Gateway` | Bot not running, or wrong port in `proxy_pass` |
| `403` with a Cloudflare page | Bot Fight Mode or WAF, see option A step 4 |
| `/subscribe` says the app isn't installed | Install it on that repo (GitHub App → Install App) |
| Commands don't show up | Global sync can take an hour, set `DISCORD_GUILD_ID` to test |
| Events are delivered but nothing is posted | The channel isn't subscribed to that event type, or the bot lacks Send Messages / Embed Links there. Check the logs |
