# Chi Status Trigger Worker

This Worker securely calls GitHub's `workflow_dispatch` API for `tsai97216/status`. The GitHub token stays in a Cloudflare Worker secret and is never sent to the browser.

## 1. Create the Worker

In Cloudflare Dashboard, open **Workers & Pages → Create → Worker**, create a Worker named `chi-status-trigger`, then open its editor and replace the starter code with `worker/index.js` from this repository. Deploy it. Cloudflare will assign a `workers.dev` URL.

Alternatively, deploy this folder with Wrangler:

```sh
npx wrangler deploy --config worker/wrangler.toml
```

## 2. Add Worker secrets

Open the Worker **Settings → Variables and Secrets** and add these as **Secret**, not plain-text variables:

- `GITHUB_TOKEN`: a fine-grained personal access token restricted to the `tsai97216/status` repository, with **Actions: Read and write** permission. Do not put this token in the dashboard or repository.
- `TRIGGER_SECRET`: a separate, long random key used only to authorize manual trigger requests. Generate one locally, for example with a password manager or `openssl rand -hex 32`. Do not reuse your GitHub token.

Save the secrets and redeploy if the dashboard asks you to.

## 3. Connect the dashboard

Copy the Worker URL from Cloudflare. In `index.html`, set `TRIGGER_API_URL` to that exact URL. Commit the change and wait for GitHub Pages to deploy.

On the dashboard, click **觸發更新** and enter the `TRIGGER_SECRET`. The dashboard stores only this trigger key in that browser's local storage; it is not in the public source. To remove it, clear the site's local storage. Anyone who knows this separate trigger key can invoke the refresh endpoint, so keep it private and rotate it if exposed.

## Security notes

- Only requests with the dashboard's exact origin are accepted by the Worker.
- The Worker requires the separate `X-Trigger-Key` secret and only dispatches the `main` branch.
- Browser-origin checks are not authentication by themselves. Keep `TRIGGER_SECRET` private.
- The Worker never returns the GitHub token or raw GitHub API error body to the browser.
