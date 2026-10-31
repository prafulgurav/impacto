import Foundation

/// Shared identifiers. Kept in one place so a notification action and its handler can never
/// drift apart.
enum CallIDs {
    /// Notification category that carries the Answer / Decline buttons.
    static let category = "INCOMING_CALL"

    static let answerAction = "ANSWER_CALL"
    static let declineAction = "DECLINE_CALL"

    /// Prefix for the chained ring notifications, so they can all be cancelled at once.
    static let requestPrefix = "incoming-call"

    static let callerNameKey = "callerName"

    /// Bundled sound file. MUST be .caf / .aiff / .wav — see Resources/ringtone-README.txt.
    static let ringtoneFile = "ringtone.caf"

    /// Length of one ring "pulse". Each chained notification plays the sound once, so this
    /// should be close to the length of the audio file.
    static let ringPulseSeconds: TimeInterval = 5

    /// How long the call rings before it gives up.
    static let ringTimeoutSeconds: TimeInterval = 45

    static let defaultCallerName = "Alex Morgan"
    static let defaultCallerSubtitle = "Mobile · +91 98765 43210"
}
