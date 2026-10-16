# Chi Status Actions Trigger Worker

This Worker provides a server-side allowlist for the projects shown on the Chi status dashboard. The GitHub token stays in a Cloudflare Worker secret and is never sent to the browser.

## 1. GitHub repository secrets

The tsai97216/status repository needs these four secrets in **Settings → Secrets and variables → Actions**:

- CLOUDFLARE_ACCOUNT_ID: your Cloudflare account ID.
- CLOUDFLARE_API_TOKEN: a Cloudflare API token allowed to edit/deploy Workers for this account.
- STATUS_WORKFLOW_TOKEN: a fine-grained GitHub personal access token with **Actions: Read and write** for only the repositories that need manual workflow dispatch: status, chi-source, chi-source-personal, free-game, sc-auto-claim, bahasign, apktwsign, h, and merch. Do not grant access to unrelated repositories.
- STATUS_TRIGGER_SECRET: a separate long random key used to authorize control-panel requests. Generate it with a password manager or locally using openssl rand -hex 32. Never reuse your GitHub token.

Do not paste any of these values into chat or commit them to the repository.

## 2. Deploy

The workflow .github/workflows/deploy-trigger-worker.yml deploys this Worker and configures its two Worker secrets automatically. It runs when files under worker/ change, or can be started manually from **Actions → Deploy Cloudflare trigger Worker → Run workflow**.

After a successful run, open the workflow run's **Summary** to see the workers.dev URL.

## 3. Connect the control panel

The URL is configured in actions.html and index.html. Open https://status.chi.qzz.io/actions.html, enter the STATUS_TRIGGER_SECRET, and use the controls to trigger a workflow from the status dashboard's project list. The key is stored in that browser's local storage; use **清除授權金鑰** to remove it.

## Project scope and safety

- The allowlist is limited to projects shown in status.json: status, chi-source, chi-source-personal, free-game, sc-auto-claim, bahasign, apktwsign, h, merch, nav, and the synthetic VPS-01 monitor.
- Only supported manual workflows are triggerable. NAV is shown as unavailable because its version workflow depends on real push commit metadata; VPS-01 is an external health check, not a GitHub Actions workflow.
- The Worker only dispatches the main branch and validates workflow inputs against the allowlist schema.
- Origin checks are not authentication by themselves. Keep STATUS_TRIGGER_SECRET private and rotate it if exposed.
- The GitHub token is stored as a Cloudflare Worker secret, not in public frontend code.
- A successful trigger response means GitHub accepted the request, not that the workflow completed successfully. Use each card's **執行紀錄** link to inspect the run.
