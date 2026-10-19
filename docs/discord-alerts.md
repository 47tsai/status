# Discord 通知設定

此儲存庫支援兩類 Discord 通知：

- **監控到專案異常**：每次狀態更新時檢查 status.json。只在某個專案第一次進入失敗狀態時通知；異常持續期間不重複發送通知，恢復正常後會發送恢復通知。狀態為未知、執行中或 API 暫時沒回傳資料，不會直接當作已恢復。
- **儀表板工作流程失敗**：狀態收集或 GitHub Pages 部署工作失敗時，另外發送一則通知。

## 監控判讀範圍

網站探測除 HTTP 狀態外，也會檢查回應內容是否為空、HTML 是否包含標題，以及標題是否明顯指向 404、502、Access Denied 或 Cloudflare 挑戰頁。這能攔截部分「HTTP 200 但實際顯示錯誤頁」的情況，仍不等於完整的登入、資料庫或應用流程測試。若端點受 Cloudflare Access 保護，會標示為未確認，而不是直接判定應用程式健康。

## 儀表板網址

正式網址：<https://status.chi.qzz.io/>。GitHub Pages 自訂網域由根目錄的 `CNAME` 檔案保存；若 DNS 與 Pages 網域設定已完成，等待 GitHub Pages 部署及 DNS/HTTPS 生效即可。

## 設定一次即可

1. 在 Discord 伺服器建立一個專用的 Webhook，複製 Webhook URL。
2. 開啟 GitHub 儲存庫的 **Settings → Secrets and variables → Actions**。
3. 在 **Repository secrets** 新增 Secret：
   - Name：DISCORD_WEBHOOK_URL
   - Secret：貼上完整的 Discord Webhook URL
4. 儲存後，下一次排程或程式碼更新執行時就會使用這個 Secret。

不要把 Webhook URL 放進程式碼、Issue、公開留言或提交紀錄。它相當於能向指定頻道發訊息的憑證。

## 行為與限制

- 同一專案持續失敗時只通知一次；狀態明確恢復後，未來再次失敗才會重新通知。
- 完成的 GitHub Actions 執行會使用實際 conclusion（例如 `success` 或 `failure`），不會把 API 的 `completed` 直接當成業務狀態，以免恢復判斷卡住。
- 儀表板也會把 `startup_failure` 列為需注意的工作流程異常。
- 單一儲存庫的 GitHub API 暫時失敗時，若有上次資料會保留卡片並標示「暫時無法更新」，不再讓專案悄悄消失，也不把舊狀態冒充即時結果。
- Discord 傳送失敗時不會更新去重狀態，後續排程可以重試；遇到限流、伺服器錯誤或短暫網路問題會先自動重試最多 3 次。
- Discord 暫時無法使用時，通知步驟不會阻止儀表板資料更新與部署；但通知本身可能延後到下一輪重試。
- 如果 Secret 尚未設定，通知步驟會略過，且不會假裝已成功傳送。
- 監控通知的頻率取決於此儲存庫的排程（每 10 分鐘）。短暫故障若在兩次檢查間恢復，可能不會被監控通知捕捉到。
- 此功能依賴 GitHub Actions 正常執行。若 GitHub Actions 本身不可用，就無法由同一工作流程保證通知送達。
