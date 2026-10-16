# Chi Auth

Chi Auth is the shared identity service planned for the Chi web ecosystem. Its WebAuthn relying-party ID is `chi.qzz.io`, allowing eligible Chi subdomains to use the same registered passkey once they integrate through the central sign-in flow.

## Current scope

This PR implements the Passkey identity core, not the finished single sign-on (SSO) rollout. Each application still needs to be registered as a client and integrated with a secure authorization-code flow using PKCE.

- The first Passkey is enrolled with a high-entropy `CHI_AUTH_SETUP_SECRET`.
- Once initialized, public registration is closed. After signing in, the owner can add a backup Passkey.
- Registration ceremonies are short-lived and bound to the authorizing setup or session context.
- Passkey assertions and attestation are verified server-side using SimpleWebAuthn.
- Session tokens are random, stored as hashes, and issued in a host-only `Secure; HttpOnly; SameSite=Lax` cookie.
- Authentication endpoints have a database-backed per-IP rate limit; IP addresses are hashed before being stored in the rate-limit table.
- Existing project authentication, including Chi Status `TRIGGER_SECRET`, remains unchanged until each integration is tested.

## Before deployment

1. Create a Cloudflare D1 database named `chi-auth` and replace the placeholder `database_id` in `wrangler.toml`.
2. Set the Worker secret `CHI_AUTH_SETUP_SECRET` using a password-manager-generated random value. Never commit or paste it into source code.
3. Apply all D1 migrations with Wrangler, including `0002_security_hardening.sql`.
4. Confirm the Cloudflare zone for `qzz.io` and explicitly configure only the route `chi.qzz.io/auth/*`. Do not route the whole root site to this Worker.
5. Run the tests and a deployment dry run.
6. Verify Passkey creation and login on a real browser/device, test rate-limit behavior, and document a recovery procedure before production use.

## SSO follow-up

The next phase must add a strict client registry, exact redirect-URI allowlists, authorization-code + PKCE exchange, CSRF/state validation, one-time codes, and app-by-app permissions. Each application should validate its own callback and maintain its own session. Do not share a broad-domain session cookie or put bearer tokens in localStorage.

The service is not production-ready until D1 is configured, deployment and device tests pass, recovery is verified, and the SSO client flow has been reviewed.
