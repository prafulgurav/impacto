import SwiftUI
import UIKit
import UserNotifications

@MainActor
struct ContentView: View {
    @EnvironmentObject private var state: CallState

    @State private var notificationsAuthorized = false
    @State private var ringtoneBundled = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Status") {
                    Text(state.statusText)
                        .font(.callout)
                }

                Section("Trigger") {
                    Button("Ring now") { ringNow() }
                    Button("Ring in 10 seconds") { ringLater(after: 10) }
                    Button("Cancel scheduled ring", role: .destructive) { cancelRing() }
                }

                Section("Permissions") {
                    LabeledContent("Notifications") {
                        Text(notificationsAuthorized ? "Granted" : "Not granted")
                            .foregroundStyle(notificationsAuthorized ? .green : .red)
                    }
                    if !notificationsAuthorized {
                        Button("Request permission") {
                            Task {
                                _ = await CallNotificationManager.shared.requestAuthorization()
                                await refresh()
                            }
                        }
                    }
                    Button("Open iOS Settings") { openSettings() }
                }

                Section("Ringtone") {
                    LabeledContent("ringtone.caf") {
                        Text(ringtoneBundled ? "Bundled" : "Missing")
                            .foregroundStyle(ringtoneBundled ? .green : .orange)
                    }
                    if !ringtoneBundled {
                        Text("Add Resources/ringtone.caf — MP3 is not a valid iOS notification "
                             + "sound. Run scripts/make-ringtone.sh to convert one.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    Text("""
                    A local notification cannot take over the lock screen on iOS — there is no \
                    equivalent of Android's full-screen intent. CallKit gives the real \
                    incoming-call screen, but only while this app is running. Waking a \
                    terminated app for a call needs a PushKit VoIP push from a server.
                    """)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                } header: {
                    Text("Platform limits")
                }
            }
            .navigationTitle("Local Call Style")
        }
        .task { await refresh() }
    }

    // MARK: - Actions

    private func ringNow() {
        Task {
            // Prefer CallKit when the app is alive: it is the only path that gives the genuine
            // full-screen call UI with a looping ringtone.
            let reported = await CallKitManager.shared.reportIncomingCall(
                callerName: state.callerName
            )
            if !reported {
                await CallNotificationManager.shared.scheduleCall(
                    callerName: state.callerName, after: 0
                )
            }
            state.phase = .ringing
        }
    }

    private func ringLater(after seconds: TimeInterval) {
        // The app may well be terminated in 10 seconds' time, so the scheduled path is always
        // local notifications. CallKit cannot be scheduled.
        Task {
            await CallNotificationManager.shared.scheduleCall(
                callerName: state.callerName, after: seconds
            )
            state.phase = .scheduled(at: Date().addingTimeInterval(seconds))
        }
    }

    private func cancelRing() {
        Task {
            await CallNotificationManager.shared.cancelAll()
            CallKitManager.shared.endCurrentCall(reason: .remoteEnded)
            state.phase = .idle
        }
    }

    private func refresh() async {
        let status = await CallNotificationManager.shared.authorizationStatus()
        notificationsAuthorized = (status == .authorized || status == .provisional)

        let name = (CallIDs.ringtoneFile as NSString).deletingPathExtension
        let ext = (CallIDs.ringtoneFile as NSString).pathExtension
        ringtoneBundled = Bundle.main.url(forResource: name, withExtension: ext) != nil
    }

    private func openSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }
}
