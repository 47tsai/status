# Chi Status Trigger Worker

This Worker securely calls GitHub's `workflow_dispatch` API for `tsai97216/status`. The GitHub token stays in a Cloudflare Worker secret and is never sent to the browser.

## 1. Configure GitHub repository secrets

The repository needs these four secrets in **Settings → Secrets and variables → Actions**:

- `CLOUDFLARE_ACCOUNT_ID`: your Cloudflare account ID.
- `CLOUDFLARE_API_TOKEN`: a Cloudflare API token allowed to edit/deploy Workers for this account.
- `STATUS_WORKFLOW_TOKEN`: a fine-grained GitHub personal access token restricted to the `tsai97216/status` repository, with **Actions: Read and write** permission.
- `STATUS_TRIGGER_SECRET`: a separate long random key used to authorize manual trigger requests. Generate it with a password manager or locally using `openssl rand -hex 32`. Keep a copy because you will enter this key in the dashboard when asked. Never reuse your GitHub token.

Do not paste any of these values into chat or commit them to the repository.

## 2. Deploy

The workflow `.github/workflows/deploy-trigger-worker.yml` deploys this Worker and configures its two Worker secrets automatically. It runs when files under `worker/` change, or can be started manually from **Actions → Deploy Cloudflare trigger Worker → Run workflow**.

After a successful run, open the workflow run's **Summary** to see the `workers.dev` URL.

## 3. Connect the dashboard

Set `TRIGGER_API_URL` in the dashboard's `index.html` to the exact Worker URL from the workflow summary, then commit the change and wait for GitHub Pages to deploy.

On the dashboard, click **觸發更新** and enter the value you saved as `STATUS_TRIGGER_SECRET`. The dashboard stores this key only in that browser's local storage. To remove it, clear the site's local storage. Anyone who knows this separate key can invoke the refresh endpoint, so keep it private and rotate it if exposed.

## Security notes

- The Worker accepts browser requests only from `https://status.chi.qzz.io`.
- The Worker requires the separate trigger key and only dispatches the `main` branch.
- Origin checks are not authentication by themselves. Keep `STATUS_TRIGGER_SECRET` private.
- The GitHub token is stored as a Cloudflare Worker secret, not in public frontend code.
