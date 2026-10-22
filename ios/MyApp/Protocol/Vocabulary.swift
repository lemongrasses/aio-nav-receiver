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
    ]

    static func t(_ key: String, _ lang: UILanguage, _ args: [String: String] = [:]) -> String {
        var text = lang.pick(messages[key] ?? (key, key))
        for (name, value) in args {
            text = text.replacingOccurrences(of: "{\(name)}", with: value)
        }
        return text
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
