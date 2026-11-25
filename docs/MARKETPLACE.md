# Listing GitPulse on GitHub Marketplace

GitPulse is listed as a free app. Free listings can be published from a personal account and
don't need publisher verification (only paid plans do).

## Before you start

The listing is reviewed by GitHub, so everything below must already work:

- [ ] The GitHub App exists and is **public** (*Where can this GitHub App be installed?* set
      to **Any account**). Draft listings can only be created for public apps.
- [ ] The bot is deployed and `https://gitpulse.saiyiidev.com` shows the landing page.
- [ ] `https://gitpulse.saiyiidev.com/privacy` and `/terms` load.
- [ ] `support@saiyiidev.com` receives email.
- [ ] You have at least one screenshot of GitPulse in Discord (see below).

## 1. Start the draft

**Settings → Developer settings → GitHub Apps → GitPulse**, scroll down to the Marketplace
section and click **List in Marketplace**. (Or go to https://github.com/marketplace/new and
click **Create draft listing**.)

The overview page shows which sections are left. Fill them in this order.

## 2. Listing description

**Listing name**

```
GitPulse
```

**Very short description of listing** (40 to 80 characters, no app name, no final period)

```
Post releases, pushes, issues and pull requests to Discord
```

**Primary category**: Chat. **Secondary category**: Project management (or Utilities).

**Supported languages**: Python.

**Customer support URL**

```
https://github.com/saiyii/gitpulse/issues
```

**Privacy policy URL**

```
https://gitpulse.saiyiidev.com/privacy
```

**Installation URL**: leave empty, it's only for OAuth apps.

Optional URLs:

| Field | Value |
| --- | --- |
| Company URL | `https://gitpulse.saiyiidev.com` |
| Documentation URL | `https://github.com/saiyii/gitpulse#readme` |
| Status URL | leave empty |

**Introductory description** (150 to 250 characters, starts with the app name)

```
GitPulse posts your repository activity to Discord: releases with their notes, pushes to the default branch, issues and pull requests. Slash commands let your team look up repos and open issues without leaving Discord.
```

**Detailed description** (1,000 characters max)

```markdown
### Releases your community actually sees
New releases are posted with their notes, cut cleanly when they're long, and direct download links for every asset.

### One channel per topic
Each Discord channel picks its own repositories and event types: releases in #announcements, pushes and pull requests in #dev.

### GitHub from Discord
`/repo` and `/release` show a repository's stats and latest release. `/issue create` opens an issue, limited to a role you choose.

### Minimal permissions
Read access to contents, metadata and pull requests, write access to issues only. Webhooks are verified with their signature, and the code is open source under MIT.
```

## 3. Images

| Field | File | Notes |
| --- | --- | --- |
| Logo | `docs/marketplace/logo.png` | 512×512, badge background `#0d1117` |
| Feature card | `docs/marketplace/feature-card.png` | 965×482, text color white |
| Product screenshots | your own | Up to 5, at least 1200 px wide, all the same ratio |

For the screenshots, take them in Discord once the bot runs: a release announcement, a push
summary, `/repo`, and `/subscribe`. Crop to the Discord window only (no browser bar or
taskbar) and keep the same ratio for all of them, for example 1600×1000 each with a bit of
padding. Add a short caption to each. Save copies in `docs/screenshots/` for the README.

## 4. Contact info

Use your own email addresses here, not a shared alias: GitHub uses them to reach you about
the listing, they aren't shown publicly. The public support contact is already covered by
the support URL and the app's support email.

## 5. Pricing

Add one plan:

| Field | Value |
| --- | --- |
| Pricing model | Free |
| Plan name | `Free` |
| Description | `Everything: all event types, all commands, unlimited repositories and channels.` |

## 6. Webhook

GitHub sends `marketplace_purchase` events (someone installs, changes plan or cancels) to the
webhook configured on the listing, not the app's. GitPulse already accepts and logs them on
the same endpoint.

Go to https://github.com/marketplace/manage, pick GitPulse, then **Webhook** in the sidebar:

| Field | Value |
| --- | --- |
| Payload URL | `https://gitpulse.saiyiidev.com/webhook` |
| Content type | `application/json` |
| Secret | the same value as `GITHUB_WEBHOOK_SECRET` in `.env` |
| Active | checked |

Using the same secret matters: GitPulse rejects anything not signed with it. After saving,
GitHub sends a `ping`, check that it got `200` in the delivery list. In the bot logs,
purchases look like:

```
gitpulse.bot: marketplace: purchased by organization octo-org, plan 'Free'
```

## 7. Submit

Back on the **Overview** page, accept the **GitHub Marketplace Developer Agreement** and click
**Submit for review**. Someone from GitHub's Marketplace team gets in touch, sometimes with
change requests. Once approved, the listing shows up at
`https://github.com/marketplace/<listing-name>`.

Things that commonly get a listing sent back: broken links, a privacy policy that doesn't
describe the actual data, screenshots with browser chrome, typos in the descriptions, or
using GitHub's logo outside their [logo guidelines](https://github.com/logos).
