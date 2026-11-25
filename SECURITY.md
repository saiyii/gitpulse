# Security

If you find a security issue in GitPulse, please don't open a public issue. Email
**support@saiyiidev.com** with the details and I'll get back to you as soon as I can.

## How GitPulse handles credentials

- Every webhook is checked against its `X-Hub-Signature-256` HMAC before the payload is even
  parsed. Requests with a missing or wrong signature get a `401`.
- The GitHub App private key only lives on the server running the bot. It is used to sign
  JWTs that expire after 9 minutes, which are exchanged for installation tokens that expire
  after an hour. Tokens are kept in memory, never written to disk or logged.
- The app asks for the smallest set of permissions it needs: read access to contents,
  metadata and pull requests, and write access to issues (for `/issue create`).
- Secrets are read from environment variables. `.env` and `*.pem` are git-ignored.
