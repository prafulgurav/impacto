import UIKit
import UserNotifications

/// Handles the notification actions. This has to be a UNUserNotificationCenterDelegate set
/// before the app finishes launching, otherwise a tap on Answer that cold-starts the app is
/// dropped.
final class AppDelegate: NSObject, UIApplicationDelegate {

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        CallNotificationManager.shared.registerCategories()
        return true
    }
}

extension AppDelegate: UNUserNotificationCenterDelegate {

    /// Without this the notification is suppressed while the app is in the foreground — which
    /// is exactly when a demo is most likely to be watched.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        Task { @MainActor in
            if CallState.shared.phase != .answered && CallState.shared.phase != .declined {
                CallState.shared.phase = .ringing
                CallState.shared.callerName =
                    notification.request.content.userInfo[CallIDs.callerNameKey] as? String
                    ?? CallIDs.defaultCallerName
            }
        }
        return [.banner, .sound, .list]
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let callerName = response.notification.request.content
            .userInfo[CallIDs.callerNameKey] as? String ?? CallIDs.defaultCallerName

        // Whatever the user chose, the ringing stops first.
        await CallNotificationManager.shared.cancelAll()

        switch response.actionIdentifier {
        case CallIDs.answerAction:
            CallKitManager.shared.endCurrentCall(reason: .answeredElsewhere)
            await MainActor.run {
                CallState.shared.callerName = callerName
                CallState.shared.phase = .answered
            }

        case CallIDs.declineAction:
            CallKitManager.shared.endCurrentCall(reason: .declinedElsewhere)
            await MainActor.run {
                CallState.shared.callerName = callerName
                CallState.shared.phase = .declined
            }

        case UNNotificationDefaultActionIdentifier:
            // Tapped the body: show the in-app call screen and leave it ringing.
            await MainActor.run {
                CallState.shared.callerName = callerName
                CallState.shared.phase = .ringing
            }

        case UNNotificationDismissActionIdentifier:
            await MainActor.run { CallState.shared.phase = .missed }

        default:
            break
        }
    }
}
