//
//  UDPReceiver.swift
//  MyApp
//
//  Listens on one or two UDP ports on its own thread, so 100 Hz 0x04 traffic is never
//  dropped because the UI is busy. Every datagram goes to `handler` with the sender's IPv4
//  address and the arrival time on the monotonic clock.
//

import Darwin
import Foundation
import Synchronization

nonisolated final class UDPReceiver: Sendable {
    typealias Handler = @Sendable (_ bytes: [UInt8], _ sender: String, _ arrival: Double) -> Void

    /// A port that could not be opened; `code` is the errno. Vocabulary.bindError words it.
    struct BindError: Error, Equatable {
        let port: UInt16
        let code: Int32
    }

    private let sockets: [Int32]
    private let running = Atomic<Bool>(true)
    private let handler: Handler

    /// Binds every port (0.0.0.0) and starts receiving. Throws when a port cannot be bound.
    init(ports: [UInt16], handler: @escaping Handler) throws {
        var opened: [Int32] = []
        for port in Set(ports).sorted() {
            do {
                opened.append(try Self.bind(port: port))
            } catch {
                opened.forEach { close($0) }
                throw error
            }
        }
        sockets = opened
        self.handler = handler
        let thread = Thread { [self] in receiveLoop() }
        thread.name = "UDPReceiver"
        thread.qualityOfService = .userInteractive
        thread.start()
    }

    /// Stops the thread; the sockets close within 200 ms.
    func stop() {
        running.store(false, ordering: .relaxed)
    }

    private func receiveLoop() {
        var polls = sockets.map { pollfd(fd: $0, events: Int16(POLLIN), revents: 0) }
        var buffer = [UInt8](repeating: 0, count: 2048)
        while running.load(ordering: .relaxed) {
            guard poll(&polls, nfds_t(polls.count), 200) > 0 else { continue }
            for i in polls.indices where polls[i].revents & Int16(POLLIN) != 0 {
                var from = sockaddr_in()
                var length = socklen_t(MemoryLayout<sockaddr_in>.size)
                let count = withUnsafeMutablePointer(to: &from) {
                    $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                        recvfrom(polls[i].fd, &buffer, buffer.count, 0, $0, &length)
                    }
                }
                let arrival = ProcessInfo.processInfo.systemUptime
                guard count > 0 else { continue }
                handler(Array(buffer[0..<count]), Self.address(from.sin_addr), arrival)
            }
        }
        sockets.forEach { close($0) }
    }

    private static func bind(port: UInt16) throws -> Int32 {
        let fd = socket(AF_INET, SOCK_DGRAM, Int32(IPPROTO_UDP))
        guard fd >= 0 else { throw BindError(port: port, code: errno) }
        var on: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &on, socklen_t(MemoryLayout<Int32>.size))
        var bufferSize: Int32 = 1 << 20
        setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &bufferSize, socklen_t(MemoryLayout<Int32>.size))

        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = port.bigEndian
        address.sin_addr = in_addr(s_addr: INADDR_ANY)
        let result = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard result == 0 else {
            let code = errno
            close(fd)
            throw BindError(port: port, code: code)
        }
        return fd
    }

    static func address(_ addr: in_addr) -> String {
        var addr = addr
        var text = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
        guard inet_ntop(AF_INET, &addr, &text, socklen_t(INET_ADDRSTRLEN)) != nil else { return "?" }
        return String(decoding: text.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)
    }

    /// IPv4 addresses of this device's network interfaces (Wi-Fi first), for the
    /// `output_udp` destination on the AIO NAV side.
    static func localAddresses() -> [(interface: String, address: String)] {
        var list: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&list) == 0, let first = list else { return [] }
        defer { freeifaddrs(list) }
        var found: [(String, String)] = []
        for entry in sequence(first: first, next: { $0.pointee.ifa_next }) {
            let ifa = entry.pointee
            guard let sa = ifa.ifa_addr, sa.pointee.sa_family == UInt8(AF_INET),
                  ifa.ifa_flags & UInt32(IFF_UP) != 0, ifa.ifa_flags & UInt32(IFF_LOOPBACK) == 0 else { continue }
            let ip = sa.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { address($0.pointee.sin_addr) }
            found.append((String(cString: ifa.ifa_name), ip))
        }
        return found.sorted { ($0.0 == "en0" ? 0 : 1, $0.0) < ($1.0 == "en0" ? 0 : 1, $1.0) }
    }
}
