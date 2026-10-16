# Chi Auth

Chi Auth is the planned shared identity service for the Chi web ecosystem. Its relying-party ID is `chi.qzz.io`, so passkeys registered at the central origin can be used by eligible Chi subdomains when those apps integrate with the identity service.

## Current scope

This first foundation implements the Passkey identity core only. It is not yet the complete single-sign-on integration for every Chi project. Each application must later be registered as a client and use a secure authorization-code flow with PKCE; do not share a broad-domain session cookie or copy an authentication token into localStorage.

- Passkey registration is bootstrap-only and should be enabled with a high-entropy `CHI_AUTH_SETUP_SECRET`.
- After the first credential exists, public registration is closed.
- Passkey verification must happen server-side.
- Session cookies are host-only and are not shared with sibling subdomains.
- Existing project authentication, including Chi Status `TRIGGER_SECRET`, remains unchanged until integration is tested.

## Before deployment

1. Create a Cloudflare D1 database named `chi-auth` and replace the placeholder `database_id` in `wrangler.toml`.
2. Set the Worker secret `CHI_AUTH_SETUP_SECRET` using a password-manager-generated random value. Never commit or paste it into source code.
3. Apply the migration with Wrangler.
4. Confirm the Cloudflare zone for `qzz.io` and explicitly configure the route `chi.qzz.io/auth/*`. Do not route the whole root domain to this Worker.
5. Run the tests and a deployment dry run.
6. Before production use, add and verify rate limiting and operational recovery procedures.

The service must not be considered production-ready until D1 is configured, deployment is verified, and the remaining hardening checklist is complete.
