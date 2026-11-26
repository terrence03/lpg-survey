# 家用液化石油氣供氣定型化契約宣導問卷（輕量版）

原 Streamlit 版問卷網站的輕量化重寫。流程、題目、跳題規則、必填規則與寫入 Google Sheets 的欄位格式都和原版相同。

- **前端**：`public/` 內的純 HTML／CSS／JS，沒有建置步驟。題目與跳題規則全部在 `public/questions.json`。
- **後端**：`server/` 內的 FastAPI，負責提供靜態檔，以及兩支 API：
  - `POST /api/checkin`：寫一筆打卡紀錄 `[timestamp, sid]`
  - `POST /api/survey`：檢查必填後寫一筆問卷紀錄（欄位順序同原版 `SURVEY_HEADERS`）
  - 寫入 Sheets 失敗時，退回寫本機 `output/*.csv`，並把該列內容記錄到 log
- 直接相依套件只有 3 個（fastapi、uvicorn、google-auth）。

## 和原版的差異

| 項目 | 原版 | 輕量版 |
|---|---|---|
| 問卷版面 | 一頁捲到底 | 分 5 步（影片 → 小測驗 → 基本資料 → 瓦斯與契約 → 資訊管道），頂部進度條，底部固定按鈕 |
| 重新整理 | 答案消失、跳回首頁 | 答案暫存在手機瀏覽器，重新整理後回到原步驟 |
| 手機返回鍵 | 離開問卷 | 回到上一步 |
| 「填問卷」的打卡紀錄 | 未寫入（程式被註解） | 會寫入一筆 |
| 網路中斷 | 顯示錯誤 | 先暫存在手機，恢復連線後自動補送 |
| YouTube 影片 | 直接載入播放器 | 先顯示縮圖，點了才載入 |
| 完成圖 | PNG 1.1 MB | WebP 約 110 KB |

驗證規則**刻意維持原版**，包括以下幾點：
- 5.1 只有選「完全不瞭解」時才必填。
- 7 題同時勾「網路社群」和「戶外廣告」時，只檢查 7.1。
- 「其他」的文字框不必填。
- 性別「其他」的說明文字，原版就沒有寫進試算表欄位，這裡也一樣。

## 本機執行

```bash
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8080
# 開 http://localhost:8080
```

沒有設定試算表時，資料會寫到 `output/checkin.csv` 和 `output/survey.csv`。

也可以用 Docker：把原本的 `.streamlit/secrets.toml` 放到專案根目錄的 `.streamlit/` 下，然後執行 `docker compose up --build`，網址是 http://localhost:8538 。

### 設定方式（擇一）

1. **沿用原版 secrets.toml**：格式與原版相同，含 `[gcp_service_account]` 與 `[spreadsheet] check_in / response`。用 `SECRETS_FILE` 指定路徑，預設為 `.streamlit/secrets.toml`。
2. **環境變數**：`SPREADSHEET_CHECKIN`、`SPREADSHEET_RESPONSE`，以及選填的 `GCP_SERVICE_ACCOUNT_JSON`（整份金鑰 JSON 字串）。沒給金鑰時，會使用執行環境的預設身分，例如 Cloud Run 綁定的服務帳戶。

## 部署到 Google Cloud Run

建議使用台灣機房（`asia-east1`），並直接讓 Cloud Run 以原本那個服務帳戶的身分執行。這樣就不需要上傳金鑰檔。

### 一次性準備

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 選擇原本服務帳戶所在的專案，或新建一個專案。
2. 建立帳單帳戶並連結專案（需要信用卡）。這個流量在免費額度內，但建議到「帳單 → 預算與快訊」設一個例如 NT$100 的預算警示。
3. 安裝 [gcloud CLI](https://cloud.google.com/sdk/docs/install)，然後執行：

```bash
gcloud auth login
gcloud config set project <專案ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com sheets.googleapis.com
```

4. 確認兩張試算表都已經分享給服務帳戶的 email，並給予「編輯者」權限。原版已經設定過的話就不用再改。

### 部署 / 更新

在專案根目錄執行：

```bash
gcloud run deploy lpg-survey \
  --source . \
  --region asia-east1 \
  --allow-unauthenticated \
  --service-account <服務帳戶email> \
  --set-env-vars SPREADSHEET_CHECKIN=<打卡試算表ID>,SPREADSHEET_RESPONSE=<問卷試算表ID> \
  --memory 256Mi --cpu 1 \
  --min-instances 0 --max-instances 3
```

完成後會顯示一個 `https://lpg-survey-xxxx.asia-east1.run.app` 網址，可以拿這個網址做 QR Code。之後每次更新，都是重新執行同一行指令。

如果出現 `iam.serviceAccounts.actAs` 權限錯誤，請給部署者帳號加上該服務帳戶的「服務帳戶使用者」角色。

### 費用與冷啟動

- 免費額度每月 200 萬次請求、18 萬 vCPU 秒，宣導活動的量遠低於這個數字。
- 對外流量在亞洲區不在免費額度內。每位民眾大約 0.3 MB（主要是圖片），1,000 人約 0.3 GB，費用以美分計。
- 閒置時會自動關機，下一位民眾開啟時要多等約 1–2 秒。首頁開啟時就會先喚醒後端，等民眾送出問卷時通常已經就緒。
- 如果活動當天想完全避免等待，可以改成 `--min-instances 1`，但這會產生少量費用，活動結束後要改回 `0`。
- Cloud Run 的磁碟是暫時的。萬一寫入 Sheets 失敗，CSV 檔會在機器重啟後消失，但每一列內容都會寫進 Cloud Logging，可以到 Cloud Run → 記錄 搜尋 `Sheets append failed` 找回。

## 修改題目

編輯 `public/questions.json` 即可：

- 文字、選項：直接改 `question`、`options`。
- 跳題：`show` 可以是 `{"q": "題目", "eq": "1"}`（等於）、`{"q": ..., "in": ["3","4"]}`（屬於其中之一）或 `{"q": ..., "has": "7"}`（複選有勾），`parent` 決定子題顯示在哪一題的卡片內。
- 分步：`steps` 陣列。

注意：必填規則寫在 `public/app.js` 的 `RULES` 和 `server/survey.py` 的 `is_complete()`，兩邊要一起改。新增欄位時，也要更新 `server/survey.py` 的 `SURVEY_HEADERS` 和試算表的標題列。

如果手上有改過的舊版 `questions.toml`，可以用 `python scripts/toml_to_json.py questions.toml` 把題目文字同步進來。
