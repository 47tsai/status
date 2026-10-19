# Chi Status

Chi Status 是 `tsai97216` 公開 GitHub 儲存庫的 Actions 與專案業務狀態儀表板。

- **正式網址：** https://status.chi.qzz.io/
- **Actions 控制台：** https://status.chi.qzz.io/action/
- **更新頻率：** 由 cron-job.org 每 10 分鐘觸發 GitHub Actions（`workflow_dispatch`）；監控相關程式碼更新也會透過 `push` 事件觸發更新。
- **架構：** GitHub Actions 收集狀態並產生 `status.json`，再由 GitHub Pages 發佈靜態儀表板。每輪成功收集都會更新資料時間戳與探測結果，因此目前每輪也會重新部署儀表板；不能單純因為沒有專案狀態翻轉就跳過部署，否則頁面會顯示過期的更新時間或探測數據。

主站與 `/action/` 是唯一兩個介面；`/actions/` 僅處理 Chi Auth OAuth 回呼，不是另一個控制台。Actions 控制台需透過 Chi Auth Passkey 登入，才可查看及觸發允許清單中的工作流程。

## 監控範圍

收集器只列入 `tsai97216` 底下非 fork、非封存的公開 Repo，並以最近一次 GitHub Actions 執行紀錄為基礎。沒有 Workflow 執行紀錄的 Repo 不會被當成成功；若既有 Repo 的 API 暫時失敗，會保留上次卡片並標記為未知／資料過期。

部分專案另有專屬業務判讀：

- **VPS-01：** 檢查 Alist、BiliTool、Twitch Drops Miner 三個公開端點；至少兩個端點回傳 HTTP 200 即判定正常。
- **Vaultwarden：** 每 10 分鐘檢查 `https://vault.chi.qzz.io/alive` 存活端點。
- **Chi Auth：** 每 10 分鐘檢查 `https://auth.chi.qzz.io/` 首頁的 HTTP 狀態與基本回應；這不等於完整驗證 Passkey／SSO 流程。
- **Chi Source / Chi Source Personal：** 讀取來源 Repo README 的 App 更新摘要，並檢查來源網站的基本頁面內容。
- **H、Chi 的工具箱、周邊收藏網：** 結合最近部署結果與公開網站檢查。
- **自動領取、限免遊戲通知、自動簽到：** 優先讀取專案產生的業務紀錄，不以 Actions 綠勾直接推定業務成功。

### 健康狀態的限制

網站探測會檢查 HTTP 狀態、回應內容是否為空、HTML 標題及部分常見錯誤／挑戰頁。這是基本探測，不是完整端對端測試，無法單憑它確認登入、資料庫、內部 API 或所有頁面功能正常。

## 專案結構

```text
.
├── .github/workflows/
├── action/index.html              # Actions 控制台
├── actions/index.html             # Chi Auth OAuth 回呼入口
├── index.html                     # 狀態總覽
├── status.json                    # 自動產生的最新狀態資料
├── scripts/                       # 狀態收集與 Discord 通知
└── worker/                        # 工作流程觸發 API
```

## 本機執行測試

需要 Python 3.12，不需安裝第三方套件：

```bash
python -m unittest discover -s tests -v
```

重新收集狀態（會呼叫 GitHub API，並以目前目錄的 `status.json` 作為舊資料參考）：

```bash
python scripts/update_status.py
```

不要把 Discord Webhook URL 寫進程式碼或提交到 Git。工作流程會先執行單元測試，再收集資料、嘗試發送 Discord 異常通知、提交狀態 JSON，最後部署 GitHub Pages。工作流程失敗時會另外嘗試通知 Discord。

## 自訂網域

根目錄的 `CNAME` 指向 `status.chi.qzz.io`。若更改網域，請同步更新 GitHub Pages 設定、此檔案與 Discord 通知中的儀表板連結。
