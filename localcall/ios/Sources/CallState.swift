import Foundation
import Combine

enum CallPhase: Equatable {
    case idle
    case scheduled(at: Date)
    case ringing
    case answered
    case declined
    case missed
}

/// Observable state for the UI. Process-scoped; nothing here needs to be persisted.
@MainActor
final class CallState: ObservableObject {
    static let shared = CallState()

    @Published var phase: CallPhase = .idle
    @Published var callerName: String = CallIDs.defaultCallerName
    @Published var lastMessage: String = ""

    private init() {}

    var statusText: String {
        switch phase {
        case .idle:
            return "Idle."
        case .scheduled(let date):
            let f = DateFormatter()
            f.timeStyle = .medium
            return "Scheduled to ring at \(f.string(from: date))."
        case .ringing:
            return "Ringing…"
        case .answered:
            return "Call answered."
        case .declined:
            return "Call declined."
        case .missed:
            return "Missed call."
        }
    }
}
