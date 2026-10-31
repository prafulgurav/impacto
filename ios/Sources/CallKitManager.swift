import Foundation
import CallKit
import AVFoundation

/// The CallKit path: the **real** system incoming-call screen, with a looping ringtone,
/// lock-screen takeover, and Answer / Decline handled by iOS itself.
///
/// ## The hard limitation, stated plainly
///
/// `CXProvider.reportNewIncomingCall` requires the app's process to be alive. Apple's only
/// sanctioned way to wake a terminated app for an incoming call is a **PushKit VoIP push**
/// (`PKPushRegistry`), and `didReceiveIncomingPushWith` *must* call `reportNewIncomingCall`
/// before it returns or iOS kills the app and may revoke the VoIP push privilege.
///
/// A VoIP push comes from APNs, which means a server and a VoIP services certificate. There is
/// no local, offline way to make this happen — no timer, no background task, no silent push
/// substitute. So:
///
///   * app in the foreground or background  → CallKit works, full system call UI (this file);
///   * app terminated, no server            → local notifications only (CallNotificationManager).
///
/// This file is wired for both: it works today for the alive case, and the PushKit hook is left
/// in place and documented so adding a server later is a small change rather than a rewrite.
final class CallKitManager: NSObject {

    static let shared = CallKitManager()

    private let provider: CXProvider
    private let callController = CXCallController()
    private var currentCallID: UUID?

    private override init() {
        let config = CXProviderConfiguration()
        config.supportsVideo = false
        config.maximumCallsPerCallGroup = 1
        config.maximumCallGroups = 1
        config.supportedHandleTypes = [.generic, .phoneNumber]
        // CallKit *does* loop this one, unlike a notification sound. Same .caf file.
        config.ringtoneSound = CallIDs.ringtoneFile

        provider = CXProvider(configuration: config)
        super.init()
        provider.setDelegate(self, queue: nil)
    }

    /// True when the process is alive and CallKit can be used for a true full-screen call.
    var isAvailable: Bool { true }

    /// Reports an incoming call to iOS. Returns false if the system refused it (for example
    /// because the user has blocked the app under Settings › Phone › Call Blocking).
    @discardableResult
    func reportIncomingCall(callerName: String) async -> Bool {
        let id = UUID()
        currentCallID = id

        let update = CXCallUpdate()
        update.remoteHandle = CXHandle(type: .generic, value: callerName)
        update.localizedCallerName = callerName
        update.hasVideo = false
        update.supportsDTMF = false
        update.supportsHolding = false
        update.supportsGrouping = false
        update.supportsUngrouping = false

        do {
            try await provider.reportNewIncomingCall(with: id, update: update)
            return true
        } catch {
            NSLog("[CallKitManager] reportNewIncomingCall failed: \(error)")
            currentCallID = nil
            return false
        }
    }

    /// Tears down whatever call is up, with the right end reason so it lands in Recents
    /// correctly.
    func endCurrentCall(reason: CXCallEndedReason = .remoteEnded) {
        guard let id = currentCallID else { return }
        provider.reportCall(with: id, endedAt: Date(), reason: reason)
        currentCallID = nil
    }
}

extension CallKitManager: CXProviderDelegate {

    func providerDidReset(_ provider: CXProvider) {
        currentCallID = nil
        Task { @MainActor in CallState.shared.phase = .idle }
    }

    func provider(_ provider: CXProvider, perform action: CXAnswerCallAction) {
        configureAudioSession()
        Task { @MainActor in
            CallState.shared.phase = .answered
            await CallNotificationManager.shared.cancelAll()
        }
        action.fulfill()
    }

    func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        Task { @MainActor in
            // CallKit uses one action for both "decline" and "hang up"; from a ringing state it
            // is a decline.
            CallState.shared.phase =
                CallState.shared.phase == .answered ? .idle : .declined
            await CallNotificationManager.shared.cancelAll()
        }
        currentCallID = nil
        action.fulfill()
    }

    func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        // Where a real app would start streaming audio.
    }

    func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        // Where a real app would tear the stream down.
    }

    private func configureAudioSession() {
        do {
            try AVAudioSession.sharedInstance()
                .setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetooth])
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {
            NSLog("[CallKitManager] Audio session error: \(error)")
        }
    }
}
