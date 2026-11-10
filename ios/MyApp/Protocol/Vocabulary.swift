//
//  Vocabulary.swift
//  MyApp
//
//  Readable words for the protocol codes and the verdict, in 繁體中文 and English: the same
//  wording as the desktop app's src/aio_receiver/i18n.py (VocabularyTests compares the two).
//  Protocol identifiers (READY, KEEP_STILL_REQUIRED) are never shown; standard acronyms
//  (GNSS, IMU, RTK, DSO, ZUPT …), units and packet ids (0x04) stay as they are in both.
//

import Darwin
import Foundation

/// The language the app shows; one at a time.
nonisolated enum UILanguage: String, CaseIterable, Sendable {
    case zhHant = "zh-Hant"
    case en

    /// zh-Hant when the iPhone's first preferred language is Chinese, otherwise English.
    static var system: UILanguage {
        (Locale.preferredLanguages.first ?? "").lowercased().hasPrefix("zh") ? .zhHant : .en
    }

    /// `setting` nil (or unknown) follows the system.
    static func resolve(_ setting: String?) -> UILanguage {
        setting.flatMap(UILanguage.init(rawValue:)) ?? system
    }

    var locale: Locale { Locale(identifier: rawValue) }

    /// Each language's name in itself.
    var nativeName: String {
        switch self {
        case .zhHant: "繁體中文"
        case .en: "English"
        }
    }

    func pick(_ pair: (String, String)) -> String {
        self == .zhHant ? pair.0 : pair.1
    }
}

nonisolated enum Vocabulary {
    static let states: [String: (String, String)] = [
        "BOOTING": ("開機中", "Booting"), "CHECKING": ("檢查中", "Checking"),
        "NAV_STARTING": ("AIO NAV 啟動中", "Starting AIO NAV"), "KEEP_STILL": ("保持靜止", "Keep still"),
        "MOVE_STRAIGHT": ("直線行駛", "Drive straight"), "REFINING": ("精對準", "Refining"),
        "READY": ("就緒", "Ready"), "DEGRADED": ("降級", "Degraded"), "FAULT": ("故障", "Fault"),
        "MAINTENANCE": ("已停止", "Stopped"),
    ]
    static let actions: [String: (String, String)] = [
        "NONE": ("不需動作", "Nothing to do"),
        "HOLD_STILL": ("讓車輛完全靜止", "Keep the vehicle completely still"),
        "DRIVE_STRAIGHT": ("在安全、空曠的區域以穩定速度直線行駛", "Drive straight at a steady speed in a safe, open area"),
        "KEEP_DRIVING": ("在有 GNSS 的環境下繼續正常行駛", "Keep driving normally where GNSS is available"),
        "SAFE_STOP": ("停止使用導航，並依車輛安全程序處理",
                      "Stop using navigation and follow the vehicle's safety procedure"),
        "SERVICE_REQUIRED": ("需要維護", "Maintenance is needed"),
        "MAINTENANCE_HOLD": ("已停止，請在儀表板的總覽頁面按「恢復」或「啟動」",
                             "Stopped. Press Resume or Start on the dashboard's Overview page"),
    ]
    static let gnssQuality: [(String, String)] = [
        ("未知", "Unknown"), ("無定位", "No fix"), ("單點定位", "Single point"),
        ("RTK 浮動解", "RTK float"), ("RTK 固定解", "RTK fixed"),
    ]
    static let health: [(String, String)] = [
        ("儀表板正常", "Dashboard OK"), ("設定有效", "Configuration valid"),
        ("IMU 資料正常", "IMU data OK"), ("GNSS 資料正常", "GNSS data OK"),
        ("GNSS 品質足夠", "GNSS quality sufficient"), ("AIO NAV 執行中", "Navigation process running"),
        ("導航輸出正常", "Navigation output OK"), ("粗對準完成", "Coarse alignment done"),
        ("初始航向完成", "Heading valid"), ("精對準完成", "Fine alignment done"), ("DSO 正常", "DSO OK"),
        ("到車端的路由正常", "Route to the vehicle OK"), ("RTK 修正資料正常", "RTK corrections OK"),
        ("儲存空間可寫入", "Storage writable"), ("車端已確認接收", "Vehicle acknowledged"),
        ("時間同步正常", "Time synchronised"), ("AIO NAV 沒有重複執行", "No duplicate process"),
        ("Wi-Fi 正常", "Wi-Fi OK"),
    ]
    static let inhibit: [(String, String)] = [
        ("開機中", "Booting"), ("設定無效", "Configuration invalid"),
        ("IMU 資料缺少或延遲", "IMU data missing or stale"), ("GNSS 資料缺少或延遲", "GNSS data missing or stale"),
        ("GNSS 品質不足", "GNSS quality too low"), ("AIO NAV 未執行", "Navigation not running"),
        ("導航輸出延遲", "Navigation output stale"), ("需要保持靜止", "Must keep still"),
        ("需要直線行駛", "Must drive straight"), ("需要精對準", "Fine alignment needed"),
        ("DSO 尚未就緒", "DSO not ready"), ("沒有到車端的路由", "No route to the vehicle"),
        ("RTK 修正資料中斷", "RTK corrections lost"), ("儲存空間無法寫入", "Storage not writable"),
        ("操作人員已停止", "Stopped by an operator"), ("啟動逾時", "Startup timed out"), ("管理權衝突", "Ownership conflict"),
        ("內部錯誤", "Internal fault"),
    ]
    static let lamps: [String: (String, String)] = [
        "ALIGN": ("粗對準", "Coarse aligned"), "HEADING": ("初始航向", "Heading valid"),
        "FINE": ("精對準", "Fine aligned"),
    ]
    /// Desktop _T keys used here: verdict words and reasons, "none", system errors.
    static let messages: [String: (String, String)] = [
        "word.usable": ("可用", "Usable"),
        "word.blocked": ("不可用", "Blocked"),
        "reason.usable": ("可用", "Usable"),
        "reason.no_status": ("沒有最新的狀態封包 (0x05)", "No current status packet (0x05)"),
        "reason.not_ready": ("狀態不是就緒：{state}（{inhibit}）", "Status is not ready: {state} ({inhibit})"),
        "reason.ready_not_stable": ("就緒尚未穩定", "Ready, not yet stable"),
        "reason.nav_stale": ("導航資料太舊 (0x04)", "Navigation data too old (0x04)"),
        "reason.nav_time_not_forward": ("導航時間沒有往前", "Navigation time did not move forward"),
        "reason.nav_not_aligned": ("導航旗標未對準", "Navigation flags not aligned"),
        "reason.nav_not_finite": ("導航資料不是有限值", "Navigation data not finite"),
        "none": ("無", "None"),
        "band.no_status": ("沒有狀態封包 0x05", "No status packets (0x05)"),
        "fail.bind": ("無法監聽 {addr}：{error}", "Cannot listen on {addr}: {error}"),
        "os.in_use": ("這個連接埠已被其他程式使用", "the port is in use by another program"),
        "os.denied": ("沒有權限", "permission denied"),
        "os.no_address": ("這台電腦沒有這個位址", "this computer has no such address"),
        "os.other": ("系統錯誤 {code}：{text}", "system error {code}: {text}"),

        // Layout C (desktop branch feature/desktop-ui-c): the signal band, guidance, route and streams.
        "band.usable": ("導航輸出可以使用", "The navigation output may be used"),
        "band.nothing": ("還沒收到任何封包", "No packets received yet"),
        "band.status_lost": ("狀態封包 0x05 中斷超過 {s} 秒", "Status packets (0x05) stopped for over {s} s"),
        "band.startup": ("系統啟動中", "Starting up"),
        "band.stage1": ("對準第 1 階段：保持靜止", "Alignment stage 1: keep still"),
        "band.stage2": ("對準第 2 階段：直線行駛", "Alignment stage 2: drive straight"),
        "band.stage3": ("對準第 3 階段：精對準", "Alignment stage 3: fine alignment"),
        "band.ready_inhibit": ("已就緒，但仍有不可用原因", "Ready, but a blocking condition remains"),
        "band.degraded": ("就緒後失去必要條件", "A required condition was lost after ready"),
        "band.fault": ("AIO NAV 故障", "AIO NAV fault"),
        "band.maintenance": ("AIO NAV 已停止", "AIO NAV stopped"),
        "band.state": ("狀態 {state}", "State {state}"),
        "band.settling": ("就緒確認中（需穩定 {s} 秒）", "Confirming ready (must hold for {s} s)"),
        "band.no_nav": ("沒有導航封包 0x04", "No navigation packets (0x04)"),
        "band.nav_lost": ("導航封包 0x04 中斷超過 {s} 秒", "Navigation packets (0x04) stopped for over {s} s"),
        "band.nav_backwards": ("導航時間沒有往前", "Navigation time did not move forward"),
        "band.not_aligned": ("導航旗標顯示未對準", "Navigation flags say not aligned"),
        "band.not_finite": ("導航資料含無效數值", "Navigation data has invalid values"),
        "band.since": ("已持續 {age}", "For {age}"),
        "band.total": ("累計可用", "Usable total"),
        "mast.stop": ("有問題", "Problem"),
        "mast.wait": ("等待", "Wait"),
        "mast.go": ("可用", "Usable"),
        "guide.no_status": ("開啟儀表板的 0x05", "Turn on 0x05 in the dashboard"),
        "guide.no_status_sub": ("有 0x04，但從來沒有收到 0x05。請確認儀表板設定檔中的 status_udp.enabled: true，且 destination 指向這台電腦。",
                                "0x04 is arriving but 0x05 never has. Check that the dashboard has status_udp.enabled: true and that its destination is this computer."),
        "guide.status_lost": ("檢查儀表板與網路", "Check the dashboard and the network"),
        "guide.status_lost_sub": ("0x05 已中斷 {age}。之前已經收到 {n} 包，所以設定沒有問題。請確認儀表板還在執行，以及這台電腦和裝置之間的網路沒有中斷。",
                                  "0x05 stopped {age} ago. {n} packets arrived before that, so the settings are fine. Check that the dashboard is still running and that the network between this computer and the device is up."),
        "age.s": ("{s:.1f} 秒", "{s:.1f} s"),
        "age.ms": ("{m} 分 {s:02d} 秒", "{m} min {s:02d} s"),
        "age.hm": ("{h} 小時 {m} 分", "{h} h {m} min"),
        "station.start": ("啟動", "Start"),
        "station.still": ("靜止", "Still"),
        "station.straight": ("直行", "Straight"),
        "station.fine": ("精對準", "Fine"),
        "station.usable": ("可用", "Usable"),
        "station.confirming": ("確認中 {x:.1f} / {y:g} 秒", "Confirming {x:.1f} / {y:g} s"),
        "rail.no_status": ("沒有最新的狀態封包，無法判斷對準進度。", "No current status packet, so alignment progress is unknown."),
        "rail.ready_inhibit": ("就緒，但仍有不可用原因", "Ready, but a blocking condition remains"),
        "rail.degraded": ("曾經就緒，之後失去條件", "Was ready, then lost a condition"),
        "rail.fault": ("AIO NAV、其輸出或管理權有問題", "Problem with AIO NAV, its output or its ownership"),
        "rail.stopped": ("操作人員已停止，或尚未啟動", "Stopped by the operator, or not started"),
        "rail.unknown": ("未知狀態 {state}", "Unknown state {state}"),
        "link.none": ("沒有資料", "No data"),
        "link.never": ("從未收到", "Never received"),
        "link.lost": ("中斷 {age}", "Lost for {age}"),
        "link.nav": ("{rate:.0f} Hz   {ms:.0f} ms", "{rate:.0f} Hz   {ms:.0f} ms"),
        "link.status": ("{rate:.1f} Hz   {s:.1f} 秒前", "{rate:.1f} Hz   {s:.1f} s ago"),
        "block.title": ("不可用原因", "Blocking conditions"),
        "block.unknown": ("沒有最新的 0x05，無法得知", "Unknown: no current 0x05"),
        "block.expected": ("對準流程的正常步驟，依序完成後會消失。", "These are normal alignment steps. They clear one by one."),
        "status.state": ("狀態", "State"),
        "status.health": ("成立條件（未成立在前）", "Conditions met (unmet first)"),
        "status.met": ("成立 {n} / {total}", "{n} / {total} met"),
        "status.out_of_date": ("（已過時）", " (out of date)"),
        "track.usable": ("可用", "Usable"),
        "track.blocked": ("不可用", "Blocked"),
        "set.sec_everyday": ("現場常用", "Everyday"),
        "set.sec_advanced": ("進階：接收與判斷規則", "Advanced: receiving and rules"),
        "set.advanced_sub": ("要和裝置設定一致", "Must match the device's settings"),
    ]

    /// The message in `lang` with its `{name}` or `{name:spec}` fields filled, as Python's
    /// str.format does for the specs i18n.py uses: `.1f`, `.0f`, `g` (Doubles) and `02d` (Ints).
    static func t(_ key: String, _ lang: UILanguage, _ args: [String: Any] = [:]) -> String {
        let text = lang.pick(messages[key] ?? (key, key))
        guard !args.isEmpty, let field = try? Regex(#"\{([a-z_]+)(?::([^}]*))?\}"#) else { return text }
        return text.replacing(field) { match in
            let name = String(match.output[1].substring ?? "")
            let spec = match.output[2].substring.map(String.init) ?? ""
            guard let value = args[name] else { return String(match.output[0].substring ?? "") }
            return format(value, spec)
        }
    }

    static func format(_ value: Any, _ spec: String) -> String {
        switch (value, spec) {
        case let (d as Double, s) where s.hasSuffix("f"): String(format: "%\(s)", d)
        case let (d as Double, "g"): String(format: "%g", d)
        case let (i as Int, "02d"): String(format: "%02d", i)
        case let (d as Double, ""): String(format: "%g", d)
        default: "\(value)"
        }
    }

    /// Items joined the way each language lists them.
    static func joined(_ items: [String], _ lang: UILanguage) -> String {
        items.joined(separator: lang.pick(("、", ", ")))
    }

    static func stateName(_ code: UInt8, _ lang: UILanguage) -> String {
        let name = DashboardState.name(of: code)
        return states[name].map(lang.pick) ?? name
    }

    static func actionText(_ code: UInt8, _ lang: UILanguage) -> String {
        guard let action = RequestedAction(rawValue: code) else { return "#\(code)" }
        return lang.pick(actions[action.name]!)
    }

    static func gnssQualityName(_ code: UInt8, _ lang: UILanguage) -> String {
        Int(code) < gnssQuality.count ? lang.pick(gnssQuality[Int(code)]) : "#\(code)"
    }

    static func healthNames(_ bits: UInt32, _ lang: UILanguage) -> [String] {
        health.indices.filter { bits >> UInt32($0) & 1 == 1 }.map { lang.pick(health[$0]) }
    }

    static func inhibitNames(_ bits: UInt32, _ lang: UILanguage) -> [String] {
        inhibit.indices.filter { bits >> UInt32($0) & 1 == 1 }.map { lang.pick(inhibit[$0]) }
    }

    static func lampName(_ flag: NavFlag, _ lang: UILanguage) -> String {
        lamps[flag.name].map(lang.pick) ?? flag.name
    }

    static func word(usable: Bool, _ lang: UILanguage) -> String {
        t(usable ? "word.usable" : "word.blocked", lang)
    }

    /// The verdict's reason as one sentence, like the desktop's Verdict.text.
    static func reason(_ verdict: VehicleGate.Verdict, _ lang: UILanguage) -> String {
        switch verdict {
        case .usable: t("reason.usable", lang)
        case .noStatus: t("reason.no_status", lang)
        case let .notReady(state, bits):
            t("reason.not_ready", lang, ["state": stateName(state, lang),
                                         "inhibit": inhibitNames(bits, lang).isEmpty
                                             ? "—" : joined(inhibitNames(bits, lang), lang)])
        case .readyNotStable: t("reason.ready_not_stable", lang)
        case .navTooOld: t("reason.nav_stale", lang)
        case .navTimeBackwards: t("reason.nav_time_not_forward", lang)
        case .notAligned: t("reason.nav_not_aligned", lang)
        case .notFinite: t("reason.nav_not_finite", lang)
        }
    }

    /// A socket error in the app's language; the system's own text only for rare errors.
    static func bindError(port: UInt16, code: Int32, _ lang: UILanguage) -> String {
        let error: String
        switch code {
        case EADDRINUSE: error = t("os.in_use", lang)
        case EACCES, EPERM: error = t("os.denied", lang)
        case EADDRNOTAVAIL: error = t("os.no_address", lang)
        default: error = t("os.other", lang, ["code": "\(code)", "text": String(cString: strerror(code))])
        }
        return t("fail.bind", lang, ["addr": "0.0.0.0:\(port)", "error": error])
    }
}
