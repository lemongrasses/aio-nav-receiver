//
//  AIOProtocol.swift
//  MyApp
//
//  Decoders for the two AIO NAV UDP packets, ported from web_monitor
//  (aio_system_dashboard/nav/decoder.py and status_packet.py).
//
//  Frame (both packets, little-endian):
//      55 AA | msg_id | payload_len u16 | payload | checksum u8
//  checksum = 8-bit sum of the bytes from msg_id to the end of the payload.
//

import Foundation

nonisolated enum AIO {
    static let sync: (UInt8, UInt8) = (0x55, 0xAA)
    static let navMessageID: UInt8 = 0x04
    static let defaultStatusMessageID: UInt8 = 0x05
    static let headerSize = 5
    static let navPayloadSize = 150
    static let navPacketSize = headerSize + navPayloadSize + 1      // 156
    static let statusPayloadSize = 36
    static let statusPacketSize = headerSize + statusPayloadSize + 1 // 42
    static let statusProtocolVersion: UInt8 = 1

    /// True when `bytes` starts with the 55 AA sync and carries `id` in byte 2.
    static func isFrame(_ bytes: [UInt8], id: UInt8) -> Bool {
        bytes.count >= 3 && bytes[0] == sync.0 && bytes[1] == sync.1 && bytes[2] == id
    }

    /// Checks the payload length field and the checksum byte that follows the payload.
    static func frameIsValid(_ bytes: [UInt8], payloadSize: Int) -> Bool {
        let reader = ByteReader(bytes)
        guard Int(reader.u16(3)) == payloadSize else { return false }
        let end = headerSize + payloadSize
        let sum = bytes[2..<end].reduce(UInt8(0)) { $0 &+ $1 }
        return bytes[end] == sum
    }

    static func reverseBits(_ x: UInt8) -> UInt8 {
        var r: UInt8 = 0
        for i in 0..<8 where x >> i & 1 == 1 {
            r |= 1 << (7 - i)
        }
        return r
    }

    /// Names of the bits that are set, in bit order.
    static func names(of bits: UInt32, in table: [String]) -> [String] {
        table.indices.filter { bits >> UInt32($0) & 1 == 1 }.map { table[$0] }
    }
}

/// Little-endian reads at absolute offsets.
nonisolated struct ByteReader {
    let bytes: [UInt8]

    init(_ bytes: [UInt8]) {
        self.bytes = bytes
    }

    func u8(_ o: Int) -> UInt8 { bytes[o] }
    func u16(_ o: Int) -> UInt16 { UInt16(bytes[o]) | UInt16(bytes[o + 1]) << 8 }
    func u32(_ o: Int) -> UInt32 { (0..<4).reduce(UInt32(0)) { $0 | UInt32(bytes[o + $1]) << (8 * $1) } }
    func u64(_ o: Int) -> UInt64 { (0..<8).reduce(UInt64(0)) { $0 | UInt64(bytes[o + $1]) << (8 * $1) } }
    func f32(_ o: Int) -> Float { Float(bitPattern: u32(o)) }
    func f64(_ o: Int) -> Double { Double(bitPattern: u64(o)) }
}

// MARK: - 0x04 navigation solution

/// Navigation flag bits after undoing the wire bit reversal.
nonisolated enum NavFlag: Int, CaseIterable, Sendable {
    case zupt, zihr, nhc, gnss, vupt, alignment, headingValid, fineAlignment

    var name: String {
        ["ZUPT", "ZIHR", "NHC", "GNSS", "VUPT", "ALIGN", "HEADING", "FINE"][rawValue]
    }
}

/// One 0x04 packet: 156 bytes, payload struct `<Qdd28fH3f`.
nonisolated struct NavSolution: Equatable, Sendable {
    /// GPS seconds of week (the wire value is microseconds).
    var time: Double
    var latitude: Double
    var longitude: Double
    var height: Float
    var velocityNorth: Float
    var velocityEast: Float
    var velocityUp: Float
    var roll: Float
    var pitch: Float
    /// Degrees as sent; may be −180…180. Use `heading360` for display.
    var heading: Float
    var positionNorthStd: Float
    var positionEastStd: Float
    var heightStd: Float
    var velocityNorthStd: Float
    var velocityEastStd: Float
    var velocityUpStd: Float
    var rollStd: Float
    var pitchStd: Float
    var headingStd: Float
    var gyroBias: [Float]
    var accelBias: [Float]
    var gyroScale: [Float]
    var accelScale: [Float]
    /// C-side flag bits (already un-reversed).
    var flags: UInt8
    var odometerScale: Float
    var mountPitch: Float
    var mountYaw: Float

    init?(bytes: [UInt8]) {
        guard bytes.count >= AIO.navPacketSize,
              AIO.isFrame(bytes, id: AIO.navMessageID),
              AIO.frameIsValid(bytes, payloadSize: AIO.navPayloadSize) else { return nil }
        let r = ByteReader(bytes)
        let f = (0..<28).map { r.f32(29 + 4 * $0) }
        time = Double(r.u64(5)) / 1e6
        latitude = r.f64(13)
        longitude = r.f64(21)
        height = f[0]
        velocityNorth = f[1]; velocityEast = f[2]; velocityUp = f[3]
        roll = f[4]; pitch = f[5]; heading = f[6]
        positionNorthStd = f[7]; positionEastStd = f[8]; heightStd = f[9]
        velocityNorthStd = f[10]; velocityEastStd = f[11]; velocityUpStd = f[12]
        rollStd = f[13]; pitchStd = f[14]; headingStd = f[15]
        gyroBias = Array(f[16..<19])
        accelBias = Array(f[19..<22])
        gyroScale = Array(f[22..<25])
        accelScale = Array(f[25..<28])
        flags = AIO.reverseBits(UInt8(truncatingIfNeeded: r.u16(141)))
        odometerScale = r.f32(143)
        mountPitch = r.f32(147)
        mountYaw = r.f32(151)
    }

    func has(_ flag: NavFlag) -> Bool { flags >> flag.rawValue & 1 == 1 }

    /// ALIGN, HEADING and FINE all set.
    var isAligned: Bool { has(.alignment) && has(.headingValid) && has(.fineAlignment) }

    var heading360: Double {
        let h = Double(heading).truncatingRemainder(dividingBy: 360)
        return h < 0 ? h + 360 : h
    }

    var groundSpeed: Double { hypot(Double(velocityNorth), Double(velocityEast)) }

    /// Every floating-point field is neither NaN nor ±Inf.
    var isFinite: Bool {
        let singles: [Float] = [height, velocityNorth, velocityEast, velocityUp, roll, pitch, heading,
                                positionNorthStd, positionEastStd, heightStd,
                                velocityNorthStd, velocityEastStd, velocityUpStd,
                                rollStd, pitchStd, headingStd, odometerScale, mountPitch, mountYaw]
            + gyroBias + accelBias + gyroScale + accelScale
        return time.isFinite && latitude.isFinite && longitude.isFinite && singles.allSatisfy(\.isFinite)
    }
}

// MARK: - 0x05 status packet

nonisolated enum DashboardState: UInt8, CaseIterable, Sendable {
    case booting, checking, navStarting, keepStill, moveStraight, refining, ready, degraded, fault, maintenance

    static let names = ["BOOTING", "CHECKING", "NAV_STARTING", "KEEP_STILL", "MOVE_STRAIGHT", "REFINING",
                        "READY", "DEGRADED", "FAULT", "MAINTENANCE"]

    var name: String { Self.names[Int(rawValue)] }

    static func name(of code: UInt8) -> String {
        DashboardState(rawValue: code)?.name ?? "STATE_\(code)"
    }
}

nonisolated enum RequestedAction: UInt8, CaseIterable, Sendable {
    case none, holdStill, driveStraight, keepDriving, safeStop, serviceRequired, maintenanceHold

    static let names = ["NONE", "HOLD_STILL", "DRIVE_STRAIGHT", "KEEP_DRIVING", "SAFE_STOP", "SERVICE_REQUIRED",
                        "MAINTENANCE_HOLD"]

    var name: String { Self.names[Int(rawValue)] }

    /// What the operator should do (readiness.ACTION_TEXT); nil for NONE.
    var operatorText: LocalizedStringResource? {
        switch self {
        case .none: nil
        case .holdStill: "Keep the vehicle completely still."
        case .driveStraight: "Drive straight at a steady speed in a safe, open area."
        case .keepDriving: "Keep driving normally with GNSS available."
        case .safeStop: "Stop using navigation and follow the vehicle's safety procedure."
        case .serviceRequired: "Maintenance is needed."
        case .maintenanceHold: "Stopped. Press Start to resume."
        }
    }
}

nonisolated enum StatusBits {
    static let health = ["DASHBOARD_OK", "CONFIG_OK", "IMU_STREAM_OK", "GNSS_STREAM_OK", "GNSS_QUALITY_OK",
                         "NAV_PROCESS_OK", "NAV_OUTPUT_OK", "ALIGNMENT_OK", "HEADING_OK", "FINE_ALIGNMENT_OK",
                         "DSO_OK", "EXTERNAL_ROUTE_OK", "RTK_CORRECTION_OK", "STORAGE_OK", "VEHICLE_ACK_OK",
                         "TIME_SYNC_OK", "NO_DUPLICATE_PROCESS", "WIFI_OK"]
    static let inhibit = ["BOOT_IN_PROGRESS", "CONFIG_INVALID", "IMU_MISSING_OR_STALE", "GNSS_MISSING_OR_STALE",
                          "GNSS_QUALITY_LOW", "NAV_NOT_RUNNING", "NAV_OUTPUT_STALE", "KEEP_STILL_REQUIRED",
                          "MOVE_STRAIGHT_REQUIRED", "FINE_ALIGNMENT_REQUIRED", "DSO_NOT_READY",
                          "EXTERNAL_ROUTE_DOWN", "RTK_CORRECTION_LOST", "STORAGE_NOT_WRITABLE", "MAINTENANCE_HOLD",
                          "STARTUP_TIMEOUT", "OWNERSHIP_CONFLICT", "INTERNAL_FAULT"]
    static let gnssQuality = ["Unknown", "None", "SPP", "RTK float", "RTK fix"]
}

/// One 0x05 packet: 42 bytes, payload struct `<BBBBIIQIIBBHHH`.
nonisolated struct StatusPacket: Equatable, Sendable {
    var protocolVersion: UInt8
    var state: UInt8
    var requestedAction: UInt8
    var gnssQuality: UInt8
    var sessionID: UInt32
    var sequence: UInt32
    var uptimeMs: UInt64
    var healthFlags: UInt32
    var inhibitFlags: UInt32
    /// 0x04 flags in C-side bit order (not reversed).
    var navFlags: UInt8
    var navRateDeciHz: UInt16
    /// Age of the last 0x04 at the dashboard; 65535 = none or older.
    var navAgeMs: UInt16

    init?(bytes: [UInt8], messageID: UInt8 = AIO.defaultStatusMessageID) {
        guard bytes.count >= AIO.statusPacketSize,
              AIO.isFrame(bytes, id: messageID),
              AIO.frameIsValid(bytes, payloadSize: AIO.statusPayloadSize) else { return nil }
        let r = ByteReader(bytes)
        protocolVersion = r.u8(5)
        guard protocolVersion == AIO.statusProtocolVersion else { return nil }
        state = r.u8(6)
        requestedAction = r.u8(7)
        gnssQuality = r.u8(8)
        sessionID = r.u32(9)
        sequence = r.u32(13)
        uptimeMs = r.u64(17)
        healthFlags = r.u32(25)
        inhibitFlags = r.u32(29)
        navFlags = r.u8(33)
        navRateDeciHz = r.u16(35)
        navAgeMs = r.u16(37)
    }

    var stateName: String { DashboardState.name(of: state) }
    var action: RequestedAction? { RequestedAction(rawValue: requestedAction) }
    var actionName: String { action?.name ?? "ACTION_\(requestedAction)" }
    var gnssQualityName: String {
        gnssQuality < StatusBits.gnssQuality.count ? StatusBits.gnssQuality[Int(gnssQuality)] : "\(gnssQuality)"
    }
    var healthNames: [String] { AIO.names(of: healthFlags, in: StatusBits.health) }
    var inhibitNames: [String] { AIO.names(of: inhibitFlags, in: StatusBits.inhibit) }
    var navRateHz: Double { Double(navRateDeciHz) / 10 }
}
