# Setting up the GitHub App and the Discord bot

You need two things before running GitPulse: a GitHub App (for webhooks and API access) and
a Discord application with a bot user. This takes about 10 minutes.

## Quick way: create the app from the manifest

From the repository folder:

```sh
python scripts/create_github_app.py
```

Your browser opens GitHub with the name, permissions, events and webhook URL already filled
in. Pick a name if `GitPulse` is taken, click **Create GitHub App**, and you're sent back to
the script, which saves `private-key.pem` and writes `GITHUB_APP_ID` and
`GITHUB_WEBHOOK_SECRET` to `.env`. Options:

| Option | Use |
| --- | --- |
| `--name "GitPulse Dev"` | Another name, for a second app used in development |
| `--webhook-url https://smee.io/xyz` | Another webhook URL, for local testing |
| `--private` | Only installable on your own account |
| `--org my-org` | Create it under an organization |

Then skip to [step 3](#3-app-id-and-private-key) to upload a logo (`docs/marketplace/logo.png`), and
[step 4](#4-install-the-app-on-your-repositories) to install it. The rest of this section
does the same thing by hand.

## 1. Webhook secret

Generate a random secret first, you'll paste it in the GitHub App and in `.env`:

```sh
python -c "import secrets; print(secrets.token_hex(32))"
```

## 2. Create the GitHub App

Go to **GitHub → Settings → Developer settings → GitHub Apps → New GitHub App**
(direct link: https://github.com/settings/apps/new).

### Basic information

| Field | Value |
| --- | --- |
| GitHub App name | `GitPulse`. Names are unique across GitHub, so if it's taken pick something like `GitPulse Discord` |
| Description | `Posts releases, pushes, issues and pull requests to Discord.` |
| Homepage URL | `https://gitpulse.saiyiidev.com` |

### Identifying and authorizing users

GitPulse never acts on behalf of a user, so leave the **Callback URL** empty and leave
**Request user authorization (OAuth) during installation** unchecked. Same for **Setup URL**
and **Device flow**.

### Webhook

| Field | Value |
| --- | --- |
| Active | checked |
| Webhook URL | `https://gitpulse.saiyiidev.com/webhook` |
| Webhook secret | the secret from step 1 |
| SSL verification | Enabled |

While developing, you can use a [smee.io](https://smee.io) URL here instead (see the README).

### Permissions

Under **Repository permissions**, set only these and leave everything else on *No access*:

| Permission | Access | Why |
| --- | --- | --- |
| Contents | Read-only | Needed for `push` and `release` events |
| Issues | Read and write | `issues` events, and `/issue create` |
| Pull requests | Read-only | `pull_request` events |
| Metadata | Read-only | Mandatory, selected automatically |

No organization or account permissions are needed.

### Subscribe to events

Once the permissions above are set, these checkboxes become available. Tick:

- [x] Issues
- [x] Pull request
- [x] Push
- [x] Release

(`Star` is not used yet.)

### Where can this GitHub App be installed?

- **Only on this account** if the bot is just for your own repositories.
- **Any account** if other people should be able to install it on theirs.

Click **Create GitHub App**.

## 3. App ID and private key

On the app's **General** page:

1. Copy the **App ID** (a number, not the Client ID) into `GITHUB_APP_ID`.
2. Scroll down to **Private keys** and click **Generate a private key**. A `.pem` file is
   downloaded.
3. Rename it to `private-key.pem` and put it next to `main.py` (or set
   `GITHUB_APP_PRIVATE_KEY_PATH`).

The key gives full access to the app. Don't commit it (`*.pem` is already in `.gitignore`),
don't paste it in Discord, and if it leaks, delete it from this page and generate a new one.

Under **Display information**, upload `docs/marketplace/logo.png` as the app's logo (and use the same
image as the Discord bot's avatar).

## 4. Install the app on your repositories

In the app settings, open **Install App** in the left sidebar, click **Install** next to
your account, then choose **All repositories** or **Only select repositories**.

You can change the selection later from **Settings → Applications → Installed GitHub Apps →
GitPulse → Configure**.

To check that GitHub can reach the bot, open the app's **Advanced** tab: every delivery is
listed under **Recent Deliveries** with the response code, and you can redeliver any of them.
The first one is a `ping`, GitPulse answers it with `200 pong`.

## 5. Create the Discord bot

1. Go to https://discord.com/developers/applications and click **New Application**. Name it
   GitPulse and upload an avatar if you want.
2. In the **Bot** tab, click **Reset Token**, copy it into `DISCORD_TOKEN`.
   No privileged intents are needed, leave all three off.
3. Leave **Public Bot** on if other servers should be able to add it, off otherwise.

### Invite link

In **OAuth2 → URL Generator**, select the scopes:

- `bot`
- `applications.commands`

and the bot permissions:

- View Channels
- Send Messages
- Embed Links

That gives a link like this one (replace `CLIENT_ID` with the Application ID from the
**General Information** tab):

```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=19456&scope=bot+applications.commands
```

Slash commands don't need an extra bot permission: the `applications.commands` scope is
enough, and members need the *Use Application Commands* permission, which everyone has by
default. `/about` prints the invite link for the running bot.

## 6. Fill in `.env`

```ini
DISCORD_TOKEN=...
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=./private-key.pem
GITHUB_WEBHOOK_SECRET=...
ADMIN_ROLE_NAME=Admin
SUPPORT_EMAIL=support@saiyiidev.com
```

Start the bot with `python main.py`. In the logs you should see:

```
gitpulse.bot: authenticated as GitHub App 'gitpulse-discord'
gitpulse.github.webhooks: webhook server listening on 0.0.0.0:8080
gitpulse.bot: synced 8 global commands (can take a while to show up)
gitpulse.bot: logged in as GitPulse#1234, in 1 servers
```

Global commands can take up to an hour to appear the first time. Set `DISCORD_GUILD_ID` to
your server's ID while testing, they'll show up instantly there.
