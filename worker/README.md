# Chi Actions Trigger Worker

This Worker exposes a small, server-side allowlist of approved GitHub Actions workflows. The GitHub token stays in a Cloudflare Worker secret and is never sent to the browser.

## 1. GitHub repository secrets

The tsai97216/status repository needs these four secrets in **Settings → Secrets and variables → Actions**:

- CLOUDFLARE_ACCOUNT_ID: your Cloudflare account ID.
- CLOUDFLARE_API_TOKEN: a Cloudflare API token allowed to edit/deploy Workers for this account.
- STATUS_WORKFLOW_TOKEN: a fine-grained GitHub personal access token with **Actions: Read and write** on every repository listed in worker/index.js. The allowlist spans multiple tsai97216 repositories. Do not restrict this token to tsai97216/status only, or dispatches to other repositories will fail. Grant only the repository access and permissions needed.
- STATUS_TRIGGER_SECRET: a separate long random key used to authorize control-panel requests. Generate it with a password manager or locally using openssl rand -hex 32. Never reuse your GitHub token.

Do not paste any of these values into chat or commit them to the repository.

## 2. Deploy

The workflow .github/workflows/deploy-trigger-worker.yml deploys this Worker and configures its two Worker secrets automatically. It runs when files under worker/ change, or can be started manually from **Actions → Deploy Cloudflare trigger Worker → Run workflow**.

After a successful run, open the workflow run's **Summary** to see the workers.dev URL.

## 3. Connect the control panel

Set API_URL in actions.html to the exact Worker URL from the workflow summary. Also set TRIGGER_API_URL in index.html to that same URL, then commit and wait for GitHub Pages to deploy.

Open https://status.chi.qzz.io/actions.html, enter the STATUS_TRIGGER_SECRET, and use the controls to trigger an approved workflow. The key is stored in that browser's local storage; use **清除授權金鑰** to remove it.

## Security notes

- The Worker accepts browser requests only from https://status.chi.qzz.io.
- Every workflow is checked against a server-side allowlist; clients cannot supply arbitrary repositories or workflow filenames.
- The Worker only dispatches the main branch and validates workflow inputs against the allowlist schema.
- Origin checks are not authentication by themselves. Keep STATUS_TRIGGER_SECRET private and rotate it if exposed.
- The GitHub token is stored as a Cloudflare Worker secret, not in public frontend code.
- A successful trigger response means GitHub accepted the request, not that the workflow completed successfully. Use each card's **執行紀錄** link to inspect the run.
