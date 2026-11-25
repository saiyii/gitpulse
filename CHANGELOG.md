# Changelog

## 1.0.0 - 2026-11-25

First public release.

### Added

- Release, push, issue and pull request announcements, posted per channel with
  `/subscribe owner/name [events]`.
- `/repo`, `/release`, `/subscriptions`, `/unsubscribe`, `/help` and `/about`.
- `/issue create` to open an issue from Discord, limited to a configurable role.
- GitHub App authentication with cached installation tokens, and a fallback for public
  repositories where the app isn't installed.
- Webhook signature checks and duplicate delivery filtering.
- Landing page, privacy policy and terms served by the bot itself.
- `scripts/create_github_app.py` to create the GitHub App from a manifest.
- Pterodactyl start script that pulls the latest code on every start.

### Fixed

- HTML tags from issue and release bodies (`<sub>`, `<details>`...) no longer show up
  as raw text in Discord.
