# Chi Status

Chi Status 是 `tsai97216` 公開 GitHub 儲存庫的 Actions 與專案業務狀態儀表板。

- **正式網址：** https://status.chi.qzz.io/
- **更新頻率：** GitHub Actions 每 10 分鐘執行一次，程式碼更新也會觸發更新。
- **架構：** GitHub Actions 收集狀態並產生 `status.json`，GitHub Pages 發佈靜態儀表板。
- **維運成本：** 不需要常駐伺服器；網站端只讀取靜態 JSON。

## 監控範圍

收集器只列入 `tsai97216` 底下非 fork、非封存的公開 Repo，並以最近一次 GitHub Actions 執行紀錄為基礎。沒有 Workflow 執行紀錄的 Repo 不會被當成成功；若既有 Repo 的 API 暫時失敗，會保留上次卡片並標記為未知／資料過期。

「Actions 控制台」位於 https://status.chi.qzz.io/actions/，可透過 Cloudflare Worker 觸發允許清單中的工作流程。使用前需輸入 `STATUS_TRIGGER_SECRET`；GitHub Token 保存在 Worker Secret，不會放進公開網頁。一般狀態資料仍每 10 分鐘自動更新，頁面也會定時重新讀取最新資料。

部分專案另有專屬業務判讀：

- **VPS-01：** 檢查 Alist、BiliTool、Twitch Drops Miner 三個公開端點；至少兩個端點回傳 HTTP 200 即判定正常運作。
- **Chi Source / Chi Source Personal：** 讀取來源 Repo README 的 App 更新摘要，並檢查來源網站的基本頁面內容。
- **H、Chi 的工具箱、周邊收藏網：** 結合最近部署結果與公開網站檢查。
- **自動領取、限免遊戲通知、自動簽到：** 優先讀取專案產生的業務紀錄，不以 Actions 綠勾直接推定業務成功。

### 健康狀態的限制

網站探測會檢查 HTTP 狀態、回應內容是否為空、HTML 標題及部分常見錯誤／挑戰頁。這是基本探測，不是完整端對端測試，無法單憑它確認登入、資料庫、內部 API 或所有頁面功能正常。

VPS-01 的狀態依三個公開端點的 HTTP 回應判定：至少兩個回傳 HTTP 200 即為正常。此規則衡量的是端點回應，不會額外驗證頁面內的所有功能。

## 專案結構

```text
.
├── .github/workflows/update-status.yml  # 定時收集、測試、部署與失敗通知
├── scripts/
│   ├── update_status.py                 # 收集 GitHub 與業務狀態
│   └── notify_discord.py                # 異常／恢復通知及去重
├── tests/
│   └── test_notify_discord.py           # 狀態分類與 Discord 通知測試
├── docs/
│   └── discord-alerts.md                # Discord Webhook 設定與限制
├── index.html                           # 靜態儀表板
├── status.json                          # 自動產生的最新狀態資料
├── alert-state.json                     # 自動維護的告警去重狀態
└── CNAME                                # GitHub Pages 自訂網域
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

若要在本機測試 Discord 通知，請先設定環境變數 `DISCORD_WEBHOOK_URL`。不要把 Webhook URL 寫進程式碼或提交到 Git。

## 工作流程與告警

工作流程位於 [update-status.yml](.github/workflows/update-status.yml)。它會先執行單元測試，再收集資料、嘗試發送 Discord 異常通知、提交狀態 JSON，最後部署 GitHub Pages。工作流程失敗時會另外嘗試通知 Discord。

Discord 設定、去重規則與已知限制請見 [docs/discord-alerts.md](docs/discord-alerts.md)。

## 自訂網域

根目錄的 `CNAME` 指向 `status.chi.qzz.io`。若更改網域，請同步更新 GitHub Pages 設定、此檔案、`index.html` 的 canonical URL，以及 Discord 通知中的儀表板連結。
