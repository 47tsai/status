# Chi Status

Chi Status 是集中檢視 `47tsai` 公開 GitHub 儲存庫的工作流程執行結果、服務可用性與專案業務狀態的監控儀表板。

- **正式網址：** https://status.chi.qzz.io/
- **Actions 控制台：** https://status.chi.qzz.io/action/
- **更新頻率：** cron-job.org 每 10 分鐘觸發 GitHub Actions（`workflow_dispatch`）；監控程式碼更新也會透過 `push` 事件觸發更新。
- **架構：** GitHub Actions 收集狀態並產生 `status.json`，再由 GitHub Pages 發佈靜態儀表板。每輪成功收集都會更新資料時間戳與探測結果，因此目前每輪也會重新部署儀表板；不能單純因為沒有專案狀態翻轉就跳過部署，否則頁面會顯示過期的更新時間或探測數據。

網站包含狀態總覽與 `/action/` Actions 控制台；`/actions/` 僅處理 Chi Auth OAuth 回呼，不是另一個控制台。使用控制台前，須透過 Chi Auth 完成 Passkey 登入，才能查看及觸發核准清單中的工作流程。

## 監控範圍

收集器只監控 `scripts/update_status.py` 中 `MONITORED_REPOS` 明確列出的儲存庫，不會自動發現或新增其他儲存庫。新增監控時，需手動把儲存庫名稱加入清單；每個儲存庫以最近一次 GitHub Actions 執行紀錄為基礎。沒有工作流程執行紀錄的儲存庫不會被當成成功；若儲存庫的 API 暫時失敗，會保留上次卡片並標記為未知或資料過期。

部分專案另有專屬業務判讀：

- **VPS-01：** 檢查 Alist、BiliTool、Twitch Drops Miner 三個公開端點；至少兩個端點回傳 HTTP 200 即判定正常。
- **Vaultwarden：** 每 10 分鐘檢查 `https://vault.chi.qzz.io/alive` 存活端點。
- **Chi Auth：** 每 10 分鐘檢查 `https://auth.chi.qzz.io/` 首頁的 HTTP 狀態與基本回應；這不等於完整驗證 Passkey／SSO 流程。
- **Chi SMS：** 每 10 分鐘檢查 Cloudflare Worker `https://sms-forwarder.tsai97216.workers.dev/` 的健康端點 HTTP 狀態與回應；這不等於完整驗證 iOS 捷徑、API 金鑰或 Discord 轉發流程。
- **Chi Source / Chi Source Personal：** 讀取來源儲存庫 README 的應用程式更新摘要，並檢查來源網站的基本頁面內容。
- **H、Chi 的工具箱、周邊收藏網：** 結合最近部署結果與公開網站檢查。
- **自動領取、限免遊戲通知、自動簽到：** 優先讀取專案產生的業務紀錄，不以 Actions 工作流程成功直接推定業務成功。

### 健康狀態的限制

網站探測會檢查 HTTP 狀態、回應內容是否為空、HTML 標題及部分常見錯誤／挑戰頁。這是基本探測，不是完整端對端測試，無法單憑它確認登入、資料庫、內部 API 或所有頁面功能正常。

## 專案結構

```text
.
├── .github/workflows/
├── action/index.html              # Actions 控制台
├── actions/index.html             # Chi Auth OAuth 回呼入口
├── index.html                     # 狀態總覽
├── release.json                   # 發布清單（本站版本與 chi-system 釘版）
├── status.json                    # 自動產生的最新狀態資料
├── scripts/                       # 狀態收集與 Discord 通知
├── tests/                         # 單元測試（含版本識別測試）
└── worker/                        # 工作流程觸發 API
```

`version.json` 不在 repo 內，由部署工作流程依 `release.json` 與本次部署的 commit 產生，見下節。

## 版本識別

- **發布清單：** `release.json`（在 repo 內）是本站的發布身分：`site`、`version`（SemVer，不帶 `v` 前綴）、`chiSystemVersion`。本站版本與 chi-system 版本完全分開；此前沒有版本號慣例，自 chi-system 遷移完成起算，目前版本為 `1.0.0`。
- **遞增規則：** MAJOR 為破壞性變更（`status.json` 格式、`version.json` 欄位、監控卡片契約或控制台 API 改變）；MINOR 為新功能（新增監控服務、控制台新能力）；PATCH 為修復或純樣式調整。改版號時只改 `release.json` 的 `version`。
- **部署產物：** `version.json` 由部署工作流程產生（`version`、`commit`、`commitShort`、`chiSystemVersion`、`deployedAt`），隨 Pages 一起發佈，不進 repo。頁尾以 `fetch('/version.json', {cache: 'no-store'})` 執行期讀取、顯示「版本號 · 短版 commit SHA」；讀取失敗時不顯示虛構版本、不影響主要功能。
  - 註：產生 `version.json` 的部署步驟尚未加入工作流程——Muse 的 GitHub App 缺少 Workflows 權限，API 拒絕更新 `.github/workflows/update-status.yml`（403 Resource not accessible by integration）。在此之前 `version.json` 尚不存在，頁尾不顯示版本。解法：齊在 GitHub App 安裝設定中授權 Workflows 權限，或手動把該步驟加進工作流程（內容見本次提交的說明），之後部署即自動產生。
- **純資料更新：** bot 每 10 分鐘的 `status.json` 更新不改 `release.json`、不升版；`version` 保持不變，只有部署產物的 `commit` 與 `deployedAt` 隨部署更新。
- **正式發布 Tag：** 按規範每次正式發布應建立 `vMAJOR.MINOR.PATCH` Tag，Tag 名、`version.json` 的 `version` 與發布紀錄三者一致；首個 `v1.0.0` Tag 尚未建立，待齊確認後再走完整發布流程。

## 本機執行測試

需要 Python 3.12，不需安裝第三方套件：

```bash
python -m unittest discover -s tests -v
```

重新收集狀態（會呼叫 GitHub API，並以目前目錄的 `status.json` 作為舊資料參考）：

```bash
python scripts/update_status.py
```

不要把 Discord Webhook URL 寫進程式碼或提交至 GitHub 儲存庫。工作流程會先執行單元測試，再收集資料、嘗試發送 Discord 異常通知、提交狀態 JSON，最後部署 GitHub Pages。工作流程失敗時會另外嘗試通知 Discord。

## 自訂網域

根目錄的 `CNAME` 指向 `status.chi.qzz.io`。若更改網域，請同步更新 GitHub Pages 設定、此檔案與 Discord 通知中的儀表板連結。
