import Foundation
import UserNotifications

/// The local-notification path: the closest iOS equivalent of Android's full-screen
/// CallStyle notification.
///
/// ## What this can and cannot do
///
/// It **can**: post a call-looking alert with Answer / Decline buttons, break through Focus
/// (with the Time Sensitive capability), fire on a schedule with the app terminated, and keep
/// making noise for ~45 seconds.
///
/// It **cannot**: take over the screen. iOS has no `setFullScreenIntent` equivalent. A local
/// notification is a banner or a lock-screen entry; the user must tap it. The only way to get
/// the real full-screen incoming-call UI on a locked device from a terminated app is a **PushKit
/// VoIP push**, which requires a server — see the top-level README.
///
/// ## Why notifications are chained
///
/// `UNNotificationSound` plays **once**. There is no `isLooping`. To ring continuously, this
/// schedules a series of notifications `ringPulseSeconds` apart and cancels the remainder the
/// moment the user answers or declines.
final class CallNotificationManager {

    static let shared = CallNotificationManager()
    private let center = UNUserNotificationCenter.current()

    private init() {}

    // MARK: - Setup

    /// Registers the Answer / Decline category. Call once, early, from the app delegate.
    func registerCategories() {
        let answer = UNNotificationAction(
            identifier: CallIDs.answerAction,
            title: "Answer",
            options: [.foreground] // bring the app up so we can show the in-call UI
        )
        let decline = UNNotificationAction(
            identifier: CallIDs.declineAction,
            title: "Decline",
            options: [.destructive] // handled in the background, no app launch needed
        )
        let category = UNNotificationCategory(
            identifier: CallIDs.category,
            actions: [answer, decline],
            intentIdentifiers: [],
            options: [.customDismissAction]
        )
        center.setNotificationCategories([category])
    }

    func requestAuthorization() async -> Bool {
        do {
            // .timeSensitive is requested here but only takes effect if the target carries the
            // Time Sensitive Notifications capability.
            return try await center.requestAuthorization(
                options: [.alert, .sound, .badge, .timeSensitive]
            )
        } catch {
            return false
        }
    }

    func authorizationStatus() async -> UNAuthorizationStatus {
        await center.notificationSettings().authorizationStatus
    }

    // MARK: - Ringing

    /// Use case 1 (instant) and use case 2 (scheduled) are the same code path with a different
    /// delay — `delay == 0` posts almost immediately.
    func scheduleCall(callerName: String, after delay: TimeInterval) async {
        await cancelAll()

        let pulses = max(1, Int(CallIDs.ringTimeoutSeconds / CallIDs.ringPulseSeconds))

        for index in 0..<pulses {
            // UNTimeIntervalNotificationTrigger rejects an interval below 1 second, so the
            // first notification is nudged forward rather than fired at 0.
            let interval = max(1, delay + Double(index) * CallIDs.ringPulseSeconds)

            let content = UNMutableNotificationContent()
            content.title = callerName
            content.body = index == 0
                ? "Incoming call · \(CallIDs.defaultCallerSubtitle)"
                : "Still ringing · \(callerName)"
            content.categoryIdentifier = CallIDs.category
            content.userInfo = [CallIDs.callerNameKey: callerName]
            content.sound = ringtoneSound()
            content.interruptionLevel = .timeSensitive
            content.relevanceScore = 1.0
            // Groups every pulse into one thread so the lock screen shows a single call, not a
            // stack of nine alerts.
            content.threadIdentifier = CallIDs.requestPrefix

            let request = UNNotificationRequest(
                identifier: "\(CallIDs.requestPrefix)-\(index)",
                content: content,
                trigger: UNTimeIntervalNotificationTrigger(timeInterval: interval, repeats: false)
            )

            do {
                try await center.add(request)
            } catch {
                NSLog("[CallNotificationManager] Could not schedule pulse \(index): \(error)")
            }
        }
    }

    /// Falls back to the default sound rather than silence if the .caf is missing, and says so
    /// in the log — a silent "working" call is far harder to debug.
    private func ringtoneSound() -> UNNotificationSound {
        let name = (CallIDs.ringtoneFile as NSString).deletingPathExtension
        let ext = (CallIDs.ringtoneFile as NSString).pathExtension
        guard Bundle.main.url(forResource: name, withExtension: ext) != nil else {
            NSLog("[CallNotificationManager] \(CallIDs.ringtoneFile) is not in the bundle; "
                  + "using the default notification sound. See Resources/ringtone-README.txt.")
            // Not .defaultCritical — that one needs the Critical Alerts entitlement and is
            // rejected without it.
            return .default
        }
        return UNNotificationSound(named: UNNotificationSoundName(CallIDs.ringtoneFile))
    }

    /// Stops the ringing: removes both the pulses that have not fired yet and the ones already
    /// sitting in Notification Center.
    func cancelAll() async {
        let ids = (0..<64).map { "\(CallIDs.requestPrefix)-\($0)" }
        center.removePendingNotificationRequests(withIdentifiers: ids)
        center.removeDeliveredNotifications(withIdentifiers: ids)
    }
}
