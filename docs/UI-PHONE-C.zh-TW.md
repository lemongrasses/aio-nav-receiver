# 手機版 C 介面實作規格（Android／iPhone）

這份規格把已定案的 C 版設計，落到 Android（Compose）與 iPhone（SwiftUI）上。原則和桌面版一樣：**功能不改，只改呈現**。接收、判斷、設定的存檔與套用、通知、背景接收的行為都維持原樣。

參考資料：

| 資料 | 用途 |
|---|---|
| [UI-INVENTORY.zh-TW.md](UI-INVENTORY.zh-TW.md) | 現有功能清單，第二、三章是手機。驗收時逐項對照 |
| [UI-CRITIQUE.zh-TW.md](UI-CRITIQUE.zh-TW.md) | 為什麼要改 |
| 設計畫布 https://claude.ai/artifact/BBNqiQjVBRnFPoMfzrxtfH | C 版手機圖表、軌跡、設定、Android 通知的畫面（中英文各一份） |
| 桌面版實作（分支 `feature/desktop-ui-c`） | 畫面邏輯的參考實作：[presentation.py](../src/aio_receiver/ui/presentation.py)、[panels.py](../src/aio_receiver/ui/panels.py)、新字串在 [i18n.py](../src/aio_receiver/i18n.py) |

狀態分頁以第 4.1 節的「不捲動版」為準，**取代**畫布上的 C 手機狀態分頁。其他分頁以畫布為準，本文件補上畫布沒畫出的狀態與細節。

---

## 0. 先決定的事

這幾項設計與現有行為有出入。表中「建議」是我的建議，最後由你決定。

| # | 項目 | 現況 | 畫布 | 建議 |
|---|---|---|---|---|
| D1 | 清除圖表與統計 | 立即清除，沒有確認 | 按鈕寫「清除圖表與統計…」，說明寫「會先請你確認」 | **維持立即清除**（功能不改）。按鈕去掉「…」，說明改成「清掉圖表、軌跡與封包計數，立即生效。」。要加確認請另開一個改動 |
| D2 | 深色模式 | 跟隨系統（`isSystemInDarkTheme()`、iOS 系統色） | 只畫了淺色 | **只用淺色**，和桌面版一致。號誌色是對白底校正的，戶外也比較好讀。若要保留深色，需要另做一組 token |
| D3 | iPhone 軌跡 | Apple 地圖 | 方格紙自繪（與 Android 同） | **維持 Apple 地圖**（拿掉地圖算功能改變），只把線改成「可用＝綠實線、不可用＝灰虛線」，車輛標註改用號誌色 |
| D4 | Android 常駐通知 | 標題「可用 · 就緒」，綠或紅上色 | 通知裡畫小號誌、藍色指示標籤 | **這次只把顏色改成四類**（綠／黃／紅／灰），文字不變。客製版面（RemoteViews）留到之後 |
| D5 | 字體 | 系統字體 | Barlow、Noto Sans TC（網頁字） | **用系統字體**（Roboto／SF），數字用等寬數字：Android `fontFeatureSettings = "tnum"`，iOS `.monospacedDigit()`。不內嵌字型 |

---

## 1. 設計 token

### 1.1 顏色

顏色只用來表達意義，不做裝飾。桌面版的 [theme.py](../src/aio_receiver/ui/theme.py) 是同一套。

| 名稱 | 值 | 用途 |
|---|---|---|
| `Asphalt` | `#1D252C` | 文字、號誌桿、分頁列、頁首 |
| `Kerb` | `#E9ECEE` | 頁面底色 |
| `Panel` | `#FFFFFF` | 區塊底色 |
| `Text2` | `#3B454E` | 次要文字 |
| `Muted` | `#56616B` | 標籤、提示 |
| `Faint` | `#6B757E` | 尚未收到的值、未來的站點、過時的值（白底 4.5:1） |
| `Line` | `#D5DADF` | 分隔線、外框（**不可當文字色**） |
| `Go` | `#1E7B45` | 可用 |
| `Wait` | `#F2B705` | 預期中的等待；上面的字用 `Asphalt` |
| `Stop` | `#B3261E` | 出問題 |
| `Idle` | `#5F6A73` | 沒資料、AIO NAV 已停止 |
| `Info` | `#1B4F9C` | 藍色指示牌（現在要做什麼）、套用列 |
| `InfoInk` | `#E3ECF9` | 指示牌上的次要文字 |
| `LampOff` / `LampRingOff` / `LampTextOff` | `#2B353D` / `#46525C` / `#9AA4AC` | 未亮的燈 |
| `ChipExpected` | 底 `#FFF1BF`、字 `#6B4600`、框 `#E5C44D` | 對準流程的正常步驟 |
| `ChipProblem` | 底 `#FBE4E2`、字 `#B3261E`、框 `#E6A39E` | 真正的不可用原因 |
| `GoTint` / `GoInk` | `#DDEFE3` / `#145A32` | 本時刻出現的輔助更新 |
| `Amber` | `#8A5A00` | 值得注意的計數（遺失、順序錯亂） |
| `Focus` | `#1B5FD9` | 鍵盤焦點框 |

四類判斷的顏色：

| 類別 | 燈的位置 | 燈色 | 大字顏色 | 頂部色帶底色／字色 |
|---|---|---|---|---|
| `go` 可用 | 下 | `Go` | `Go` | `Go` ／白 |
| `wait` 等待 | 中 | `Wait` | `Asphalt` | `Wait` ／`Asphalt` |
| `stop` 有問題 | 上 | `Stop` | `Stop` | `Stop` ／白 |
| `idle` 沒資料 | 全暗 | — | `Idle` | `Idle` ／白 |

### 1.2 字級與尺寸

單位：Android 用 sp／dp，iPhone 用 pt。字級要能跟著系統字體大小放大，所以不要寫死高度；需要固定的只有燈與站點的大小。

| 元素 | 字級 | 字重 |
|---|---|---|
| 判斷大字（可用／不可用） | 34 | Bold |
| 判斷原因 | 16 | SemiBold |
| 指示牌標題（沒有說明時） | 21 | Bold |
| 指示牌標題（有說明時） | 18 | Bold |
| 指示牌說明 | 13 | Regular |
| 區塊標題、可展開列標題 | 15 | SemiBold |
| 數值 | 14 到 16 | Medium，等寬數字 |
| 標籤、提示 | 12 到 13 | Regular |

觸控目標至少 48dp（Android）／44pt（iPhone）。

### 1.3 號誌元件

做成一個共用元件 `SignalMast(kind, orientation, size)`，四個地方用：

| 用在哪裡 | 方向 | 燈的直徑 |
|---|---|---|
| 狀態分頁頂部色帶 | 直立，深色圓角底座 | 20 |
| 圖表、軌跡分頁頁首 | 橫排，旁邊加一個字（等待／可用／有問題） | 14 |
| 設定分頁 | 不放 | — |
| Android 無法接收畫面 | 橫排 | 34 |

- 亮燈：燈色填滿，2 的白框。
- 未亮：`LampOff` 填滿，`LampRingOff` 框。
- 燈內圖示（直徑 ≥ 34 才畫）：上燈「!」、中燈時鐘、下燈勾號。
- **位置本身代表意思**，色盲也讀得出來，所以三燈的順序固定為上紅、中黃、下綠。
- 無障礙描述：「號誌：黃燈，等待」等，見第 5 節的 `mast_a11y_*`。

---

## 2. 共用的畫面邏輯（從桌面版移植）

桌面版把「畫面說什麼」寫成純函式：[presentation.py](../src/aio_receiver/ui/presentation.py)。請在兩支手機各移植一份，同樣寫成純函式並加單元測試，測試案例照抄 [test_presentation.py](../tests/test_presentation.py)。

建議檔案：

- Android：`ui/Presentation.kt`，測試 `src/test/.../ui/PresentationTest.kt`
- iPhone：`Views/Presentation.swift`，測試放進 `MyAppTests`

### 2.1 判斷類別與原因 `band(snapshot)` → `(kind, word, headline)`

輸入只用 snapshot 裡已有的值。**原因改用桌面版的 `band.*` 文字**，不再用目前的 `reason.*`。`reason.*` 仍留給通知與其他已經在用的地方。

| 條件（依序判斷，先符合先用） | kind | 原因字串 |
|---|---|---|
| verdict 可用 | go | `band.usable` |
| `NO_STATUS`，且 0x04、0x05 計數都是 0 | idle | `band.nothing` |
| `NO_STATUS`，且 0x05 計數是 0 | stop | `band.no_status` |
| `NO_STATUS`（其他） | stop | `band.status_lost`（{s}＝狀態逾時） |
| `NOT_READY`，狀態 `MAINTENANCE` | idle | `band.maintenance` |
| `NOT_READY`，狀態 `BOOTING`／`CHECKING`／`NAV_STARTING` | wait | `band.startup` |
| `NOT_READY`，狀態 `KEEP_STILL`／`MOVE_STRAIGHT`／`REFINING` | wait | `band.stage1`／`stage2`／`stage3` |
| `NOT_READY`，狀態 `READY` | stop | `band.ready_inhibit` |
| `NOT_READY`，狀態 `DEGRADED`／`FAULT` | stop | `band.degraded`／`band.fault` |
| `NOT_READY`（其他狀態碼） | stop | `band.state` |
| `READY_NOT_STABLE` | wait | `band.settling`（{s}＝就緒穩定時間） |
| `NAV_STALE`，從沒收到 0x04 | stop | `band.no_nav` |
| `NAV_STALE`（其他） | stop | `band.nav_lost`（{s}＝導航最大延遲） |
| `NAV_TIME_NOT_FORWARD` | stop | `band.nav_backwards` |
| `NAV_NOT_ALIGNED` | stop | `band.not_aligned` |
| `NAV_NOT_FINITE` | stop | `band.not_finite` |

### 2.2 指示牌 `guide(snapshot)` → `(kind, title, sub)`

kind 有三種：`plate`（藍牌）、`danger`（紅牌）、`quiet`（不放牌子，只有一行灰字）。

| 條件 | kind | 標題／說明 |
|---|---|---|
| 0x05 不是最新的，且從沒收到 0x05 | plate | `guide.no_status` ／`guide.no_status_sub` |
| 0x05 不是最新的，之前收到過 | plate | `guide.status_lost` ／`guide.status_lost_sub`（{age}＝距上一包的時間，{n}＝0x05 計數） |
| 要求動作 `NONE` | quiet | 動作文字「不需動作」 |
| 要求動作 `SAFE_STOP`／`SERVICE_REQUIRED` | danger | 動作文字 |
| 其他要求動作 | plate | 動作文字 |
| 什麼都還沒收到 | — | 不放指示牌。手機的設定說明在設定分頁，維持現況 |

「0x05 是最新的」的意思是：`status != null && statusAge <= statusTimeout`。

### 2.3 對準路線 `rail(snapshot)` → `(at, mode, fraction, note)`

照搬 `presentation.rail`。站點：

| 站 | 字串 | 涵蓋的狀態 |
|---|---|---|
| 0 啟動 | `station.start` | `BOOTING`、`CHECKING`、`NAV_STARTING` |
| 1 靜止 | `station.still` | `KEEP_STILL` |
| 2 直行 | `station.straight` | `MOVE_STRAIGHT` |
| 3 精對準 | `station.fine` | `REFINING` |
| 4 可用 | `station.usable` | `READY` |

各情況：

| 情況 | at | mode | 下方附註 |
|---|---|---|---|
| 0x05 不是最新的 | −1 | none | `rail.no_status`；什麼都沒收到時不顯示 |
| `READY`，就緒確認中 | 4 | progress | fraction＝已穩定秒數 ÷ 就緒穩定時間。最後一站由下往上填黃；附註顯示 `station.confirming` |
| `READY`，已穩定 | 4 | done | 最後一站變綠、畫勾 |
| `READY`，但 gate 沒有開始計時（`readySince` 是空的） | 4 | progress | `rail.ready_inhibit` |
| `DEGRADED` | 4 | lost | 最後一站紅底「!」，附註 `rail.degraded`（紅字） |
| `FAULT` | −1 | fault | `rail.fault`（紅字） |
| `MAINTENANCE` | −1 | stopped | `rail.stopped` |

確認中的倒數放在**路線下方的附註**，不要放在站名。放在站名會和「精對準」重疊，桌面版就是這樣改的。

### 2.4 不可用原因 `blocking(snapshot)` → `List<Chip(text, expected)>?`

- 0x05 不是最新的：回傳 `null`，顯示 `block.unknown`。
- `expected = 狀態在啟動或對準中，而且這個位元是 BOOT_IN_PROGRESS／KEEP_STILL_REQUIRED／MOVE_STRAIGHT_REQUIRED／FINE_ALIGNMENT_REQUIRED`。
- 第一屏的呈現規則見第 4.1 節的 ③。

### 2.5 成立條件 `conditions(snapshot)` → `List<(name, met)>`

18 項全部列出，**未成立的排前面**，各組內維持位元順序。另外算出成立幾項，顯示為 `status.met`。0x05 過時的話，後面加 `status.out_of_date`，整組變成 `Faint`。

### 2.6 串流文字 `navLink`／`statusLink`

| 情況 | 0x04 | 0x05 |
|---|---|---|
| 正常 | `link.nav`（Hz、ms） | `link.status`（Hz、幾秒前） |
| 中斷（超過門檻） | `link.lost`（紅） | `link.lost`（紅） |
| 從沒收到 | `link.none` | 已有 0x04 時用 `link.never`（紅），否則 `link.none` |

中斷門檻：0x04 用導航最大延遲，0x05 用狀態逾時。

時間格式照搬 `fmt_age`：未滿 60 秒用 `age.s`，未滿 1 小時用 `age.ms`，其他用 `age.hm`。

---

## 3. 需要補的資料（只在 store 層多帶出來，不改判斷）

| 資料 | 用在哪裡 | Android | iPhone |
|---|---|---|---|
| 判斷持續多久 `verdictFor`（秒） | 色帶的「已持續」 | `Monitor.changedAt` 已經有，換算後放進 `MonitorSnapshot` | 在 `MonitorStore` 的 tick 裡，判斷改變時記下時間 |
| 已穩定多久 `readyFor`（秒，可為空） | 路線最後一站的填色與倒數 | `Gate.readySince` 已經有 | `VehicleGate.readySince` 已經有，從 `MonitorEngine.snapshot` 帶出 |
| 時間軸區段的類別 `kind` | 圖表的「號誌歷程」 | `TimelineSegment` 加 `kind`，記錄時用第 2.1 節的函式算 | 同左 |
| 軌跡點是否可用 | 軌跡線的綠／灰 | `NavSample.usable` 已經有 | `NavSample` 加 `usable`（Android 已有，iPhone 補齊） |
| 0x05 接收頻率 | 0x05 串流格 | `statusRateHz` 已經有 | 目前沒有。做法同 0x04 的 `rateWindow`；不補的話 0x05 格只顯示「幾秒前」 |

這些都是顯示用的資料，不影響可用／不可用的判斷。現有的 gate 測試與共用測試向量（`fixtures/gate_vectors.json`）應該完全不受影響。

---

## 4. 各分頁

### 4.0 共同外框

- **分頁列**：`Asphalt` 底，84 高（含底部安全區）。
  - 選中的分頁：白字白圖示，粗體。未選中：`#AEB6BD`。
  - 圖示：狀態用三顆燈直排的號誌圖示（兩邊都自畫：Android 用 vector，iPhone 用 SwiftUI `Shape` 或 asset 裡的 SVG），圖表折線、軌跡定位點、設定齒輪。
  - Android 用 `NavigationBar(containerColor = Asphalt)`，並把 indicator 設為透明或深灰。iPhone 用 `UITabBarAppearance`，設定背景色與選中、未選中的顏色。
- **頁首**：狀態分頁沒有頁首，頂部色帶就是頁首（含 App 名稱）。其他三個分頁的頁首是 `Asphalt` 底：左邊白色標題 18 Bold，右邊橫排小號誌加一個字。
  - Android：`TopAppBar(colors = topAppBarColors(containerColor = Asphalt, titleContentColor = White))`，狀態分頁不放 topBar。
  - iPhone：在各頁的 `NavigationStack` 用 `.toolbarBackground(Asphalt, for: .navigationBar)`、`.toolbarBackground(.visible, …)`、`.toolbarColorScheme(.dark, …)`，標題改 inline，小號誌放 `ToolbarItem(placement: .topBarTrailing)`。狀態分頁 `.toolbar(.hidden, for: .navigationBar)`。
- **狀態列圖示顏色**：狀態分頁頂部是號誌色，所以 wait（黃）要用深色狀態列圖示，其他用淺色。
  - Android：`WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = (kind == wait)`。
  - iPhone：由 `.toolbarColorScheme` 或 `preferredColorScheme` 對應。

### 4.1 狀態分頁（不捲動版）

目標：在 390×844 的手機上，**收合時不用捲動**就看得到判斷、要做什麼、對準進度、兩個封包串流和三列細節的摘要。工程細節點開才看。

外層仍保留可捲動的容器（`verticalScroll`／`ScrollView`）：小手機或展開細節時可以捲。

```
┌───────────────────────────────────┐  ← 號誌色底，延伸到狀態列下方
│ ┌─┐ AIO NAV 接收監看      已持續 0.8 秒│
│ │●│ 不可用                          │  ① 判斷色帶
│ │○│ 對準第 1 階段：保持靜止           │
│ │○│                                 │
│ └─┘                                 │
├───────────────────────────────────┤  ← 白底
│ ┌───────────────────────────────┐ │
│ │ 👤 讓車輛完全靜止                │ │  ② 指示牌（藍；SAFE_STOP 紅；NONE 只有一行灰字）
│ └───────────────────────────────┘ │
│  ●━━①━━②━━③━━□                     │  ③ 對準路線＋附註或不可用原因
│ 啟動 靜止 直行 精對準 可用            │
│ 對準流程中，還有 3 步                 │
├────────────────┬──────────────────┤
│● 0x04          │● 0x05             │  ④ 封包串流（中斷的格子紅框紅字）
│  97 Hz  0 ms   │  2.0 Hz  0.3 秒前  │
├────────────────┴──────────────────┤
│ 導航 0x04      未對準 σ 0.05/0.05/0.10 m ˅│  ⑤ 三列可展開的摘要
│ 狀態 0x05            保持靜止 未成立 11 / 18 ˅│
│ 統計                沒有異常 累計可用 0:00:26 ˅│
├───────────────────────────────────┤
│   接收中，UDP 連接埠 9000　這支手機 10.42.0.37 │  ⑥ 接收資訊
└───────────────────────────────────┘
│ 狀態    圖表    軌跡    設定          │  分頁列
```

**① 判斷色帶**（約 104 高）：底色與字色見第 1.1 節。

- 左：直立小號誌（深色圓角底座 `Asphalt`、padding 6、燈 20、間距 5）。
- 右上一行：App 名稱 13，靠右放 `band.since`（數字 18）。
- 下面：判斷大字 34 Bold，再下面是原因 16 SemiBold，最多兩行。
- 可用變成不可用的瞬間，亮著的燈閃三次（每次 160 ms 暗、160 ms 亮）。開啟「減少動態效果」時不閃：Android 讀 `Settings.Global.ANIMATOR_DURATION_SCALE == 0`，iPhone 讀 `accessibilityReduceMotion`。這是畫面效果，不改變通知或其他行為。

**② 指示牌**（白底區、padding 12／16）：

- plate：`Info` 底、圓角 8，3 的白色內框加 2 的 `Info` 外框（道路指示牌的樣子）。左邊人形圖示 24，標題白字，`sub` 用 13 `InfoInk`。
- danger：同 plate，底改 `Stop`。
- quiet：不放牌子，一行 15 `Muted` 字「不需動作」。
- 什麼都還沒收到：整個 ② 不放。

**③ 對準路線**：

- 圖形：
  - 路是 10 高的圓角條，`Line` 色；已走過的部分用 `Asphalt`。
  - 站點直徑 30（最後一站是圓角方塊），框線 2.5，數字 14。
  - 站名 12：目前站 `Asphalt` 加粗，已過 `Asphalt`，未到 `Faint`。第一站靠左，最後一站靠右，中間置中。
  - 站點狀態的顏色照第 2.3 節，和桌面版一樣。
- 路線下方，**依序只放一種**：
  1. 有任何 `expected = false` 的原因：顯示原因標籤（`ChipProblem`），可換行。
  2. 原因全部都是 `expected`：一行琥珀色字（`#6B4600`）`rail_steps_left`，例如「對準流程中，還有 3 步」。完整清單在展開的「狀態 0x05」裡。
  3. 沒有原因，但有 rail 附註或確認中倒數：顯示附註（第 2.3 節）。
  4. 都沒有：不顯示。
- 什麼都還沒收到時，整條路線也不放，維持乾淨的「還沒收到任何封包」。

**④ 封包串流**：兩格並排，間隔 1（露出 `Line`），白底、padding 8／12。

- 每格：圓點 10（`Go`，中斷或沒收到為 `Stop`；從沒有資料為 `Faint`），標籤「0x04」或「0x05」12 `Muted`，下面是串流文字 14（第 2.6 節）。
- 中斷時整格 2 的 `Stop` 內框，文字紅色。

**⑤ 三列可展開的摘要**：

- 每列至少 48 高，白底，上方 1 的分隔線。左邊標題 15，右邊摘要 13 `Muted`（一行，超出用省略號），最右是 ˅／˄。
- 同一時間只開一列，點已開的列就收起。不用記住上次開哪一列。
- Android 用 `Modifier.clickable` 加 `semantics { stateDescription = 展開 或 收合 }`；iPhone 用 `DisclosureGroup`，或自製 Button 加 `.accessibilityValue`。
- 三列的摘要與展開內容如下。**展開內容必須包含現有畫面的每一個欄位**（對照 UI-INVENTORY 第二、三章）。

| 列 | 收合時的摘要 | 展開內容（兩欄表格：標籤 12 `Muted`，值 14） |
|---|---|---|
| 導航 0x04 | `nav_summary_aligned` 或 `nav_summary_not_aligned`（ALIGN、HEADING、FINE 三個旗標都亮才算已對準），後面接「σ 北/東/下 m」；沒有 0x04 時用 `no_nav` | 資料延遲、接收頻率、位置 σ 北/東/下、航向 σ、緯度、經度、高度、航向、水平速率（含 km/h）、滾轉/俯仰；「對準」三個燈（圓點＋名稱，亮為 `Go`）；「本時刻的輔助更新」標籤（出現為 `GoTint` 底、`GoInk` 字，沒出現為白底、`Faint` 字）。過時的值全部 `Faint` |
| 狀態 0x05 | 正常：`status_summary`（例：「保持靜止　未成立 11 / 18」）；過時：`status_summary_stale`（紅字，例：「已過時　最後一包：就緒」）；沒有 0x05：`no_status` | 狀態、要求動作、GNSS 品質、工作階段、序號、儀表板運作時間、導航頻率、0x04 延遲、狀態延遲；「不可用原因」標籤全部列出（expected 用 `ChipExpected`，其他用 `ChipProblem`；沒有就顯示綠字「無」）；「成立條件（未成立在前）」18 項分兩欄，右上標 `status.met`。過時的值全部 `Faint`，絕不顯示綠色 |
| 統計 | 有異常計數時列出非零的項目，例如「遺失 0x05 2、無效 1」（遺失、順序錯亂用 `Amber`，其他用 `Stop`）；全部為零時顯示 `stats_ok`「沒有異常」。後面接「累計可用 0:00:26」 | 0x04 封包、0x05 封包、遺失 0x05、順序錯亂、兩個發送者、無效、其他來源、累計可用、最後發送者 |

**⑥ 接收資訊**：12 `Muted`，置中。

- 文字為 `listening_on`（或 `not_listening`），接著「這支手機 IP（介面）」。
- 最後發送者移到「統計」的展開內容裡，資訊沒有少。
- **Android**：沒在接收時，下面放「開始接收」按鈕（外框按鈕，48 高），和現在一樣。iPhone 沒有這個按鈕，也和現在一樣。

**Android 無法接收（綁定失敗）**：照畫布 `C-Android`。

- 在 ② 的位置放一個 `role=alert` 的方框（2 的 `Stop` 外框）：標題「無法接收」16 Bold 紅字，內文 `Words.bindError(...)`。
- 方框下面放藍色指示牌，文字為 `bind_plate`「到「設定」更換 0x04 連接埠」。
- 這時判斷仍照第 2.1 節（通常是 idle「還沒收到任何封包」）。

**第一屏高度預算**（收合狀態）：

| 區塊 | 高度 |
|---|---|
| ① 色帶 | 104 |
| ② 指示牌 | 70（有說明時 110） |
| ③ 路線＋一行 | 80 |
| ④ 串流 | 52 |
| ⑤ 三列 | 3 × 48 = 144 |
| ⑥ 接收資訊 | 36 |
| 間距 | 約 40 |
| **合計** | **約 526 到 566** |

可用高度：

- iPhone 390×844：扣狀態列與分頁列，約 714 可用，最長的情境（0x05 中斷，有說明）也放得下。
- Android 360×640dp：約 536 可用，最後一兩列可能要稍微捲一下。判斷、指示、路線、串流一定在第一屏。

### 4.2 圖表分頁

照畫布 `C-PhoneCharts`。

- **頁首**：`Asphalt` 底，標題「圖表」，右邊小號誌。頁首下半放時間範圍分段按鈕（1 分鐘／5 分鐘／10 分鐘）：選中的白底深字，未選中透明底、`#C9D0D6` 字、`#46525C` 框，按鈕至少 40 高。
  - 預設值與記憶方式**維持現況**：Android 預設 5、不記住，iPhone 會記住。
- **號誌歷程**（取代目前的「判斷」色帶）：
  - 三列，每列一盞燈（有問題／等待／可用）。該燈亮著的時段畫成色塊（`Stop`／`Wait`／`Go`），其他時段是 `#F1F3F5` 底，所以不用分辨顏色也看得出來。
  - 第四列「狀態」保留現有的各狀態色帶與圖例。
  - 下方時間刻度：左邊 `chart_minutes_ago`「5 分鐘前」，右邊 `chart_now`「現在」。
  - 說明文字 12.5 `Muted`：`chart_signal_hint`。
  - 需要第 3 節的 `TimelineSegment.kind`。idle 的時段三列都不上色。
- **圖表卡片**：分「導航品質」「運動」兩組，各組有灰色小標。每張卡白底：
  - 標題 14 加單位，右上放目前值 20 Bold（等寬數字），圖表下面是 Y 軸最小、最大值。
  - 多條線用**線型**區分，不只靠顏色：位置 σ 北實線 `Info`、東虛線 `#C25E00`、下點線 `#6A3DAD`，並附圖例。
  - 0x04 資料延遲：面積 `#FCE3CF`，上限線 `Stop` 虛線，標 `chart_limit`「上限 500 ms」（值取導航最大延遲）。
  - 航向畫成點。接收頻率是階梯線。
- 圖表**不可點選、沒有互動**，每 0.5 秒重繪，和現在一樣。沒資料時顯示「這段時間沒有資料。」。

### 4.3 軌跡分頁

- **Android**（自繪，照畫布 `C-PhoneTrack`）：
  - 方格紙 `Line` 色，北朝上。
  - 可用段：`Go` 實線，寬 7。不可用段：`#7B858E` 虛線，寬 4，線段 9、空隙 8（`PathEffect.dashPathEffect`）。
  - 車輛：深色圓（半徑 18）內嵌號誌色圓（半徑 13），加上航向箭頭。
  - 右上：比例尺與 N 指北。
  - 左上：圖例框（白底 94% 不透明，`Line` 框）。右上：「跟隨車輛」按鈕（44 高、2 的 `Asphalt` 框；開啟時 `Asphalt` 底白字）。
  - 底部：`Asphalt` 底的位置資訊列。第一行「緯度, 經度　航向　km/h」（等寬數字 17），第二行提示 12.5 `#C9D0D6`。提示只在不跟隨時顯示，和現在一樣。
  - 拖曳、雙指縮放、跟隨的行為都不變。
- **iPhone**（維持 Apple 地圖，見 D3）：
  - 軌跡改成兩種 `MapPolyline`：可用段 `Go`、寬 7；不可用段 `#7B858E`、寬 4，`StrokeStyle(dash: [9, 8])`。需要第 3 節的 `usable`。
  - 車輛標註的底色改用號誌色：wait 用 `Wait` 加深色箭頭，idle 用 `Idle`。
  - 圖例框與位置資訊列的樣式同 Android。「跟隨車輛」維持在工具列右上，指北針與比例尺維持 MapKit 內建。

### 4.4 設定分頁

照畫布 `C-PhoneSettings`。「草稿＋套用」的行為完全不變，只重新分組並調整樣式。

```
設定（Asphalt 頁首）
── 現場常用　改了不會影響判斷結果
   這支手機 wlan0                  10.42.0.37（可選取）
   Wi-Fi                          已連線，沒有網際網路（保持連線）
   接收                            ● 是（Go）／● 否（Stop）
   版本                            1.2.1 (10201)    ← 格式維持現況
   （連 Jetson 熱點的說明文字，維持現有內容）
   語言  立即生效，不需套用          [跟隨系統|繁體中文|English]
   保持螢幕開啟                      (開關)
   在背景持續接收（Android 才有）     (開關)
   （背景說明）（通知已關閉警告，橘字，只在權限關閉時）
── 進階：接收與判斷規則　要和裝置設定一致
   0x04 連接埠                      [ 9000 ]
   0x05 使用另一個連接埠              (開關) → 開啟才出現「0x05 連接埠」
   0x05 訊息 ID                     [−] 0x05 [+]
   只接受來源 IP                     [ 不限 ]
   （UDP 沒有驗證的說明）
   ┌ 紅框 ───────────────────────┐
   │ 判斷規則：實際使用時不可放寬     │
   │ 狀態逾時        [−] 3.0 s [+]  │
   │ 就緒穩定時間    [−] 2.0 s [+]  │
   │ 導航最大延遲    [−] 0.5 s [+]  │
   │ 預設為 3.0、2.0、0.5 秒，與桌面版相同。│
   └──────────────────────────────┘
── 把這頁的欄位改回預設；按「套用」才會生效。   [恢復預設值]
   清掉圖表、軌跡與封包計數，立即生效。        [清除圖表與統計]（紅框，見 D1）
┌ 套用列（Info 底，固定在分頁列上方，只在有未套用的變更時出現）┐
│ 1 項未套用：只接受來源 IP                      [ 套用 ] │
└──────────────────────────────────────────┘
```

- 每一行至少 50 高，行與行之間用 1 的 `#EEF0F2` 分隔。值靠右，數值用等寬數字。
- 輸入框：1.5 的 `#8A949C` 框，錯誤時紅框（現有行為）。步進器按鈕 44×44、1.5 的 `Asphalt` 框。開關開啟時用 `Asphalt` 色。
- 各欄位的範圍、步進與驗證**全部不變**。
- 套用列：
  - 內容為 `apply_pending`，加上變更欄位名稱的清單（用 `list_separator` 連接）。
  - 草稿有錯時不可按，內容改為紅底白字的 `check_ports`「請檢查埠號與來源 IP 位址。」（現有文字）。
  - 套用後套用列消失。
  - 語言照舊立即生效，不算未套用。
- iPhone：沒有「在背景持續接收」這一行（現況）。版本列在「現場常用」裡。可以繼續用 `Form`，但要改用白底 section、`Kerb` 頁面底色，並調整 `.listRowSeparatorTint`。

### 4.5 Android 常駐通知（D4，只改顏色）

- `setColor` 改成四類顏色。wait 用 `Wait`，但上色後的通知文字由系統決定；若對比不足，wait 改用 `#8A5A00`。
- 標題、內文、「停止」按鈕、靜音、點一下開 App，全部不變。
- 狀態列小圖示：可以再加 `ic_stat_wait`、`ic_stat_idle`，非必要。

---

## 5. 新增與變更的字串

### 5.1 怎麼放

- **Android**：放在 `values/strings.xml` 與 `values-zh-rTW/strings.xml`。和桌面版共用的字串，請加進 [StringsTest.kt](../android/app/src/test/java/com/lemongrass/aionav/StringsTest.kt) 的 `messages` 對照表，讓測試保證和 `i18n.py` 一字不差。桌面的 `{name}` 會在測試裡自動轉成 `%1$s`。
- **iPhone**：放在 `Localizable.xcstrings`，key 用英文原文，`zh-Hant` 填中文。和桌面版共用的字串，加進 `MyAppTests` 讀 `i18n.py` 比對的清單。
- **用詞**：中文要符合 [TERMINOLOGY.zh-TW.md](TERMINOLOGY.zh-TW.md) 的「不使用的詞」（例如寫「延遲」不寫「過舊」，寫「操作人員」不寫「操作員」）。三平台的測試都會檢查。
- **英文**：句子開頭大寫、其餘小寫，不出現中文字。

### 5.2 與桌面版共用（文字照抄 `i18n.py`，桌面分支已經有）

| 桌面 key | 中文 | English |
|---|---|---|
| `band.usable` 等全部 `band.*`（約 20 條，見第 2.1 節） | 見 i18n.py | 見 i18n.py |
| `band.since` | 已持續 {age} | For {age} |
| `band.total` | 累計可用 | Usable total |
| `mast.stop`／`mast.wait`／`mast.go` | 有問題／等待／可用 | Problem／Wait／Usable |
| `guide.no_status` | 開啟儀表板的 0x05 | Turn on 0x05 in the dashboard |
| `guide.no_status_sub` | 有 0x04，但從來沒有收到 0x05。請確認儀表板設定檔中的 status_udp.enabled: true，且 destination 指向這台電腦。 | 見 i18n.py |
| `guide.status_lost` | 檢查儀表板與網路 | Check the dashboard and the network |
| `guide.status_lost_sub` | 0x05 已中斷 {age}。之前已經收到 {n} 包，所以設定沒有問題。… | 見 i18n.py |
| `station.start`、`station.still`、`station.straight`、`station.fine`、`station.usable` | 啟動、靜止、直行、精對準、可用 | Start、Still、Straight、Fine、Usable |
| `station.confirming` | 確認中 {x:.1f} / {y:g} 秒 | Confirming {x:.1f} / {y:g} s |
| `rail.no_status`、`rail.ready_inhibit`、`rail.degraded`、`rail.fault`、`rail.stopped`、`rail.unknown` | 見 i18n.py | 見 i18n.py |
| `block.title`、`block.unknown`、`block.expected` | 不可用原因、沒有最新的 0x05，無法得知、對準流程的正常步驟，依序完成後會消失。 | 見 i18n.py |
| `link.none`、`link.never`、`link.lost`、`link.nav`、`link.status` | 見 i18n.py | 見 i18n.py |
| `age.s`、`age.ms`、`age.hm` | {s:.1f} 秒 等 | {s:.1f} s 等 |
| `status.health` | 成立條件（未成立在前） | Conditions met (unmet first) |
| `status.met` | 成立 {n} / {total} | {n} / {total} met |
| `status.out_of_date` | （已過時） | (out of date) |
| `track.usable`、`track.blocked` | 可用、不可用 | Usable、Blocked |

注意：

- Python 的 `{x:.1f}`、`{y:g}` 這類格式，Android 用 `%1$.1f`、iOS 用 `%.1f` 改寫，數字要先格式化好再傳入。比對測試若無法直接比格式字串，就比格式化後的結果。
- 現有的 `reason.*` 保留不動，通知還在用。

### 5.3 手機專用（新增）

| 建議 key（Android） | 中文 | English | 備註 |
|---|---|---|---|
| `mast_a11y_go`、`mast_a11y_wait`、`mast_a11y_stop`、`mast_a11y_idle` | 號誌：綠燈，可用／號誌：黃燈，等待／號誌：紅燈，有問題／號誌：未亮，沒有資料 | Signal: green, usable／Signal: yellow, wait／Signal: red, problem／Signal: off, no data | 無障礙描述 |
| `rail_steps_left` | 對準流程中，還有 %d 步 | Alignment in progress, %d steps to go | 用 plurals：Android `<plurals>`，iOS 在 xcstrings 設 plural variation。英文 one：「1 step to go」 |
| `nav_summary_aligned` | 已對準　σ %s m | Aligned, σ %s m | |
| `nav_summary_not_aligned` | 未對準　σ %s m | Not aligned, σ %s m | |
| `status_summary` | %1$s　未成立 %2$d / %3$d | %1$s, %2$d / %3$d unmet | %1$s＝狀態名稱 |
| `status_summary_stale` | 已過時　最後一包：%s | Out of date, last: %s | 紅字 |
| `stats_ok` | 沒有異常 | No problems | |
| `streams_label` | 封包 | Packets | 只給無障礙標籤用，畫面不顯示 |
| `bind_plate` | 到「設定」更換 0x04 連接埠 | Change the 0x04 port in Settings | Android |
| `chart_signal_title` | 號誌歷程 | Signal history | |
| `chart_signal_hint` | 每一列是一盞燈，亮著的時段畫成色塊，不用分辨顏色也看得出來。 | Each row is one lamp; the times it was lit are filled in, so colour is not needed to read it. | |
| `chart_minutes_ago` | %d 分鐘前 | %d min ago | |
| `chart_now` | 現在 | Now | |
| `chart_limit` | 上限 %s ms | Limit %s ms | |
| `set_sec_everyday` | 現場常用 | Everyday | 可與桌面 `set.sec_everyday` 共用 |
| `set_everyday_sub` | 改了不會影響判斷結果 | Changing these never changes the verdict | |
| `set_sec_advanced` | 進階：接收與判斷規則 | Advanced: receiving and rules | 與桌面共用 |
| `set_advanced_sub` | 要和裝置設定一致 | Must match the device's settings | 與桌面共用 |
| `set_rules_title` | 判斷規則：實際使用時不可放寬 | Rules: do not loosen them for real use | |
| `language_hint` | 立即生效，不需套用 | Applies at once, no Apply needed | |
| `restore_hint` | 把這頁的欄位改回預設；按「套用」才會生效。 | Puts this page's fields back to the defaults. They take effect when you tap Apply. | |
| `clear_hint` | 清掉圖表、軌跡與封包計數，立即生效。 | Clears the charts, the track and the packet counts, at once. | 見 D1 |
| `apply_pending` | %1$d 項未套用：%2$s | %1$d changes not applied: %2$s | 用 plurals；英文 one：「1 change not applied: %2$s」 |
| `expanded`、`collapsed` | 已展開、已收合 | Expanded、Collapsed | 無障礙狀態 |

現有的字串（卡片標題、欄位名稱、`listening_on`、`not_listening`、`start_monitoring`、`check_ports`、`no_nav`、`no_status`……）沿用，不改字。

---

## 6. 檔案對照

### Android（`android/app/src/main/java/com/lemongrass/aionav/`）

| 檔案 | 改什麼 |
|---|---|
| `ui/Components.kt` | 換成第 1 節的 token。`AioTheme` 固定淺色（D2）。新增 `SignalMast`、`StationRail`、`StreamCell`、`ExpandRow`、`SignChip`、`InstructionPlate` |
| `ui/Presentation.kt`（新） | 第 2 節的純函式 |
| `ui/StatusScreen.kt` | 改成第 4.1 節的版面。現有的 `NavigationCard`、`StatusPacketCard`、`StatisticsCard` 拆成展開內容 |
| `ui/ChartsScreen.kt`、`ui/TimeChart.kt` | 頁首、號誌歷程、卡片樣式、線型 |
| `ui/TrackScreen.kt` | 顏色、虛線、圖例、按鈕、位置資訊列 |
| `ui/SettingsScreen.kt` | 分組、套用列、紅框規則區 |
| `MainActivity.kt` | 分頁列顏色與圖示、各分頁頁首、狀態分頁不放 topBar、狀態列圖示顏色 |
| `monitor/MonitorStore.kt` | `MonitorSnapshot` 加 `verdictFor`、`readyFor`；`TimelineSegment` 加 `kind` |
| `monitor/MonitorService.kt` | 通知顏色（D4） |
| `res/values*/strings.xml`、`res/values/colors.xml` | 字串與顏色 |
| `src/test/.../StringsTest.kt` | 加入共用字串的對照 |
| `src/test/.../ui/PresentationTest.kt`（新） | 移植 `test_presentation.py` |

### iPhone（`ios/MyApp/`）

| 檔案 | 改什麼 |
|---|---|
| `Views/Components.swift` | token（`Color` extension）、`SignalMast`、`StationRail`、`StreamCell`、`ExpandRow`、`InstructionPlate` |
| `Views/Presentation.swift`（新） | 第 2 節的純函式 |
| `Views/StatusView.swift` | 第 4.1 節的版面，隱藏導覽列 |
| `Views/ChartsView.swift` | 頁首、號誌歷程、卡片 |
| `Views/TrackMapView.swift` | 兩種線、標註顏色、圖例、位置資訊列 |
| `Views/SettingsView.swift` | 分組、套用列、規則區 |
| `ContentView.swift` | TabView 外觀、各分頁工具列顏色 |
| `Monitor/MonitorEngine.swift`、`Monitor/MonitorStore.swift` | `readyFor`、`verdictFor`、`TimelineSegment.kind`、`NavSample.usable`，（可選）0x05 頻率 |
| `Localizable.xcstrings` | 字串 |
| `MyAppTests/MyAppTests.swift` | 共用字串比對、presentation 測試 |

---

## 7. 驗收

### 7.1 每個情境都要看過

兩種語言各一次。Android 用 360×640dp 與 412×915dp，iPhone 用 iPhone SE 與 iPhone 15。

| 情境 | 怎麼產生 | 要看到 |
|---|---|---|
| 什麼都沒收到 | 不送任何封包 | 號誌全暗、灰色「不可用」「還沒收到任何封包」，沒有指示牌與路線 |
| 有 0x04、從沒有 0x05 | `tools/fake_sender.py` 只送 0x04 | 紅燈、「開啟儀表板的 0x05」、0x05 格「從未收到」 |
| 對準第 1 階段 | 送 `KEEP_STILL`、`HOLD_STILL`，加上三個 expected 位元 | 黃燈、藍牌「讓車輛完全靜止」、路線在 1、琥珀字「還有 3 步」 |
| 就緒確認中 | 剛進 `READY` 的 2 秒內 | 黃燈、「不需動作」灰字、最後一站往上填黃、附註倒數 |
| 可用 | `READY` 超過 2 秒 | 綠燈、最後一站綠勾、三列摘要都正常 |
| 0x05 中斷 | 可用時停送 0x05 | 紅燈、亮燈閃三次、「檢查儀表板與網路」加說明、0x05 格紅框「中斷 x 秒」、狀態列「已過時」紅字、值變 `Faint` |
| 降級並要求停止 | 送 `DEGRADED`、`SAFE_STOP`，加 `RTK_CORRECTION_LOST` | 紅燈、**紅色**指示牌、路線最後一站紅「!」、紅色原因標籤直接顯示在第一屏 |
| AIO NAV 已停止 | 送 `MAINTENANCE` | 號誌全暗、灰色字 |
| 無法接收（Android） | 先用別的程式占住 9000 | 紅框「無法接收」，下面藍牌「到「設定」更換 0x04 連接埠」 |
| 未在接收（Android） | 關掉背景接收後切回 App 前停止 | 「未在接收。」＋「開始接收」按鈕 |
| 系統字體放大到 130% | 系統設定 | 文字不被截斷、換行正常；可以捲動 |
| TalkBack／VoiceOver | 系統設定 | 號誌讀出「號誌：黃燈，等待」；三列讀出「已展開／已收合」 |

### 7.2 功能沒有少

逐項打勾 [UI-INVENTORY.zh-TW.md](UI-INVENTORY.zh-TW.md) 第二、三章。特別注意這幾項：

- [ ] 狀態分頁的每個欄位都還在（第 4.1 節 ⑤ 的展開內容），包括最後發送者、狀態延遲、儀表板運作時間
- [ ] Android「開始接收」按鈕只在沒接收時出現
- [ ] 圖表時間範圍 1／5／10 分鐘，記不記住維持各平台現況
- [ ] 軌跡的拖曳、縮放、跟隨車輛與提示文字維持
- [ ] 設定的草稿＋套用、語言立即生效、恢復預設值只改草稿、清除的行為（D1）
- [ ] 通知的內容、「停止」按鈕、背景接收不變
- [ ] 過時的值顯示 `Faint`，絕不顯示綠色

### 7.3 測試

- Android：`./gradlew testDebugUnitTest`，包含 StringsTest 的共用字串對照與 PresentationTest。
- iPhone：`MyAppTests` 全綠。
- 桌面版：改了 `i18n.py` 才需要跑 `pytest`。這份規格不需要改它，桌面分支已經有這些字串。
- CI 的 `android.yml` 會讀 `src/aio_receiver/i18n.py`，所以手機分支要**建在 `feature/desktop-ui-c` 之上**，或等它合併進 main 之後再開，否則共用字串的對照會找不到新的 key。
