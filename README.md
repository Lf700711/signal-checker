# 部位進出場訊號檢查程式

你在 GitHub 上按一下「執行」，程式就會檢查行情，把「進場訊號、目前部位、出場價」用 Email 寄給你，並更新一個網頁。全部跑在 GitHub 上，不用自己的電腦、不用付費。**不會自動排程**，要你自己在美股開盤後（紐約時間 9:35 左右）手動按執行。

> 本程式只提供訊號與價位，**不是投資建議**，也不會幫你下單。高槓桿 ETF 風險很高，建議先用小部位或紙上模擬觀察一段時間。

---

## 一、它怎麼運作（先看懂再動手）

```
你在紐約 9:35 左右手動按 Run workflow
  GitHub Actions 啟動 ─→ 抓 Yahoo 行情 ─→ 套用你的規則
        │                                         │
        │                       ┌─────────────────┴───────────────┐
        ▼                       ▼                                 ▼
  更新 data/*.json         寄 Email 給你                 更新網頁 docs/index.html
  （部位記錄）          （進場訊號／部位／出場價）      （GitHub Pages 發布）

你在券商成交後 ─→ GitHub 的「Record position」表單填成交價 ─→ 程式開始追蹤這個部位
```

重點：

- **你下單，程式不下單。** 程式只告訴你「今天要不要進場、進場價多少、停損價多少」。
- **你要回報成交。** 你在券商真的成交後，到 GitHub 填一張表單（標的、方向、成交價），程式才會把它當成「有部位」，之後每天幫你算出場價。
- **出場自動記錄。** 程式每次執行時，用日K推算部位是否已被停損或停利出場，推算到就自動標成「無部位」並在 Email 通知你。實際成交價如果不同，用同一張表單的 `close` 修正即可。
- **請在券商設好停損單。** 程式只在你按下執行時檢查一次，無法盯盤；Email 會給你當天的出場價，請自己在券商更新停損單。

## 二、一次性設定（約 30～40 分鐘）

### 步驟 1：註冊 GitHub 並建立專案

1. 到 https://github.com 註冊帳號（免費）。
2. 登入後，右上角 `+` → **New repository**。
3. Repository name 填 `signal-checker`，選 **Public**（原因見下方「隱私」），按 **Create repository**。

### 步驟 2：把程式上傳到 GitHub

1. 解壓縮我給你的 `signal-checker.zip`。
2. 在你剛建立的專案頁面，按 **uploading an existing file**（或 `Add file` → `Upload files`）。
3. 把解壓縮後資料夾**裡面**的 `signal_checker`、`tests`、`data`、`docs` 這四個資料夾，以及 `requirements.txt`、`README.md`、`.gitignore` 拖進網頁，按 **Commit changes**。
4. 兩個排程檔要另外建立（因為名稱開頭是 `.` 的隱藏資料夾，拖曳上傳常常會漏掉）：
   1. 專案頁面按 `Add file` → **Create new file**。
   2. 檔名欄位輸入 `.github/workflows/check.yml`（輸入 `/` 會自動建立資料夾）。
   3. 用記事本打開 zip 裡 `copy-these-2-files` 資料夾的 `check.yml`，全選複製，貼到網頁的編輯區，按 **Commit changes**。
   4. 同樣方法再建一個 `.github/workflows/record.yml`，內容貼 `record.yml`。

### 步驟 3：準備 Gmail「應用程式密碼」

Email 通知用你的 Gmail 寄出，需要一組專用密碼，不是你的登入密碼。

1. 到 https://myaccount.google.com/security，開啟「**兩步驟驗證**」（已開啟就跳過）。
2. 到 https://myaccount.google.com/apppasswords，名稱填 `signal-checker`，按建立。
3. 會出現 **16 碼** 密碼，複製起來（空格可有可無）。這組密碼只會顯示一次。

### 步驟 4：把密碼存進 GitHub Secrets（不會公開）

專案頁面 → **Settings** → 左側 **Secrets and variables** → **Actions** → **New repository secret**，建立三個：

| Name | Secret（內容） |
|---|---|
| `GMAIL_USER` | 你的 Gmail 地址（寄件用） |
| `GMAIL_APP_PASSWORD` | 步驟 3 的 16 碼密碼 |
| `MAIL_TO` | 收件信箱（可以和寄件相同；多個收件人用逗號隔開） |

### 步驟 5：允許程式把記錄存回專案

**Settings** → 左側 **Actions** → **General** → 最下面 **Workflow permissions** → 選 **Read and write permissions** → **Save**。

### 步驟 6：開啟網頁（GitHub Pages）

**Settings** → 左側 **Pages** → Source 選 **Deploy from a branch** → Branch 選 `main`、資料夾選 `/docs` → **Save**。
幾分鐘後網址會是：`https://你的GitHub帳號.github.io/signal-checker/`（第一次檢查完成後才會有內容）。

### 步驟 7：測試 Email

1. 專案上方 **Actions** → 左側 **Run signal check** → 右邊 **Run workflow**。
2. 勾選 **test_email**，按綠色 **Run workflow**。
3. 約 1 分鐘後，綠色勾勾代表成功，信箱會收到「[測試] 訊號檢查程式 Email 設定成功」。若沒收到先看垃圾郵件匣。
4. 失敗（紅色叉叉）：點進去看錯誤訊息。最常見是密碼貼錯，或 Secrets 名稱打錯（要完全一樣，大小寫也是）。

設定完成。之後每個交易日開盤後，重複下方「三、每天怎麼用」的步驟 1 即可。

> 提醒：在美股休市日、盤前或盤後執行，會顯示「今天沒有盤中資料」，不會寄信。

## 三、每天怎麼用

1. 紐約時間 9:35 之後（台灣冬令約晚上 10:35，夏令約 21:35），到 GitHub 專案 **Actions** → **Run signal check** → **Run workflow**（什麼都不用勾）→ 綠色 **Run workflow**。約 1 分鐘後收到 Email。手機瀏覽器也可以操作。同一天可重複執行，每次都用當下行情重新計算並寄信。
2. 看「**進場訊號**」區塊：
   - 有訊號：照 Email 的進場價與停損價，在券商自己決定要不要下單。
   - **成交後**回報：Actions → **Record position** → Run workflow：
     - action 選 `open`，symbol、side 選對，price 填實際成交價，按 Run。
     - 做多（買進程式）side 選 `long`，放空（賣出程式）選 `short`。
3. 看「**部位狀態 = 有**」區塊：每個部位當天的出場價、距離保本／移動出場還差多少。請把券商的停損單改成這個價位。
4. 看「**已自動出場**」區塊（如果有）：程式推算出的出場結果，請對照券商實際成交；不同就用 `close` 修正。

### Record position 的三種動作

| action | 用途 | 需要填 |
|---|---|---|
| `open` | 登記新部位 | 標的、方向、成交價（成交日不填就是今天） |
| `close` | 登記出場；或程式已自動標記出場但實際成交價不同時，修正最近一筆 | 標的、方向、成交價 |
| `delete` | 登記錯了，直接刪除目前部位 | 標的、方向 |

> 買進程式（做多）只有 BITX、ETHU；賣出程式（放空）有全部 10 檔。BITX 和 ETHU 的做多與放空是**各自獨立**的兩個部位。

## 四、我替你定下的規則解讀（請核對）

這些是把你的文字規則寫成程式時的具體解讀，**請逐條確認**；要改的話告訴我，或自己改 `signal_checker/config.py` 與 `engine.py`。

**進場（無部位時才檢查）**

- 做多：前日 `開盤 > 收盤`、今日 `開盤 ≤ 前日最高`、今日開盤到檢查當下的最高價 `> 前日最高` → 進場價 = 前日最高價。
- 放空：前日 `收盤 > 開盤`、今日 `開盤 ≥ 前日最低`、今日開盤到檢查當下的最低價 `< 前日最低` → 進場價 = 前日最低價。
- 「突破」「跌破」是嚴格大於／小於（剛好等於不算）。
- 有部位就不檢查進場。你沒回報成交，該標的就仍視為「無部位」，隔天繼續檢查。

**出場（做多）**

- 出場價最初 = 成本價 × (1 − 停損%)。
- 進場後最高價達到成本價 × (1 + 保本門檻)，出場價拉到成本價。
- 進場後最高價達到成本價 × (1 + 移動門檻)，出場價 = 進場後最高價 × (1 − 回撤%)；若低於成本價就用成本價。
- 出場價只會往有利方向移動，不會退回去。

**出場（放空）** 完全對稱：用進場後「最低價」，出場價 = 最低價 × (1 + 回彈%)；若高於成本價就用成本價。

**計算細節**

- 「高點／低點」與「獲利幅度」都用日K的**盤中最高／最低價**，不是收盤價。
- 進場日當天的高（低）點計入進場後極端價，但**進場日當天不判斷出場**（無法知道高低點發生在你進場前還是後）。
- 之後每天，用「前一天為止」的極端價算出場價，再看今天的日K有沒有觸及；同一天內「先創高再回落」的先後順序無法得知，所以當天新高要到隔天才會提高出場價。
- 日K跳空越過出場價時，出場價以開盤價計，損益會比預期差。
- 不含手續費、滑價、股息。
- SPXU 放空的保本門檻與移動門檻都是 10%，依你的確認照原樣執行（獲利一達 10%，兩個階段同時成立，出場價用移動出場價）。

## 五、需要知道的限制

1. **進場判斷用的是「開盤到你按下執行當下」的高低點。** 你晚幾分鐘按，盤中高低點可能已經不同，進場價仍是前日高／低點，但訊號可能多出或消失。Yahoo 免費行情也可能延遲幾分鐘，Email 會標示行情資料時間，落後超過 15 分鐘會提醒。忘記執行的日子，出場推算會在下次執行時用日K補上，但錯過的進場訊號就沒了。
2. **資料來源 yfinance 是非官方的。** 偶爾會失敗；失敗時 Email 會列出哪幾檔資料錯誤，不會悄悄略過。全部失敗時不會存檔，稍後再手動執行一次即可。
3. **反向分割。** 這些槓桿 ETF 偶爾會做合股／分割。分割後 Yahoo 的歷史價格會調整，但你當初登記的進場價不會，遇到時請用 `delete` 後依新價 `open` 重新登記。
4. **隱私。** GitHub Pages 免費版需要 Public 專案，所以 `data/positions.json`（你的部位與成交價）和網頁**任何人知道網址都看得到**。裡面沒有帳號、股數、金額，但仍是你的交易資訊。若介意：把專案設為 Private，網頁就無法免費發布，但 Email 通知照常運作（部位狀態看 Email 與 `data/positions.json` 即可）。

## 六、常見問題

- **Email 沒收到**：先看垃圾郵件匣；到 Actions 看最近一次執行是否紅色叉叉；確認 3 個 Secrets 名稱與內容。
- **按了執行卻沒收到信**：到 Actions 點進最近一次 `Run signal check`，看 Log 最後一行。若顯示「今天沒有盤中資料」，代表現在不是美股正常盤時段（休市、盤前或盤後）。
- **想改停損、移動門檻**：改 `signal_checker/config.py` 裡對應標的那一行即可，格式 `R(停損%, 保本觸發%, 移動出場觸發%, 回撤或回彈%)`。在 GitHub 網頁上點該檔案，按右上角鉛筆圖示編輯，再 Commit。
- **想加新標的**：在 `config.py` 的 `LONG_RULES` 或 `SHORT_RULES` 加一行，並到 `.github/workflows/record.yml` 的 `symbol` 選項清單補上。
- **想新增通知方式（Telegram）或換資料來源（Alpaca）**：告訴我，改動集中在 `notify.py` 與 `market.py`。

## 七、檔案說明

| 路徑 | 用途 |
|---|---|
| `signal_checker/config.py` | 所有標的與規則參數（最常需要改的檔案） |
| `signal_checker/engine.py` | 進場判斷與出場價計算（純計算） |
| `signal_checker/check.py` | 每日檢查主程式 |
| `signal_checker/record.py` | 回報成交 |
| `signal_checker/market.py` | 抓行情（yfinance） |
| `signal_checker/notify.py` | 組合並寄出 Email |
| `signal_checker/render.py` | 產生網頁 |
| `data/positions.json` | 目前部位與已出場紀錄 |
| `data/state.json` | 最近一次檢查結果（程式自動維護） |
| `docs/index.html` | 網頁（程式自動產生） |
| `.github/workflows/check.yml` | 手動執行檢查（按 Run workflow） |
| `.github/workflows/record.yml` | 回報成交的表單 |
| `tests/` | 自動測試（共 38 項，驗證規則計算） |

## 八、（選用）在自己電腦上測試

```bash
pip install -r requirements.txt
python -m unittest discover -s tests          # 跑測試
python -m signal_checker.check --force --dry-run   # 只印結果，不寄信、不存檔（開盤時段才有資料）
```
