import SwiftUI

/// In-app call screen. This is what the user sees when the app is open, or after tapping the
/// notification body. It is the closest thing to `IncomingCallActivity` that iOS allows an app
/// to draw itself.
@MainActor
struct IncomingCallView: View {
    @EnvironmentObject private var state: CallState

    var body: some View {
        ZStack {
            Color(red: 0.06, green: 0.08, blue: 0.09)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                Text("INCOMING CALL")
                    .font(.caption)
                    .tracking(2)
                    .foregroundStyle(.secondary)
                    .padding(.top, 72)

                Image(systemName: "person.crop.circle.fill")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 120, height: 120)
                    .foregroundStyle(.white.opacity(0.85))
                    .padding(.top, 40)

                Text(state.callerName)
                    .font(.system(size: 30, weight: .bold))
                    .foregroundStyle(.white)
                    .padding(.top, 24)

                Text(CallIDs.defaultCallerSubtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(.top, 8)

                Spacer()

                HStack {
                    callButton(
                        systemName: "phone.down.fill",
                        label: "Decline",
                        tint: .red
                    ) { decline() }

                    callButton(
                        systemName: "phone.fill",
                        label: "Answer",
                        tint: .green
                    ) { answer() }
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 56)
            }
        }
    }

    private func callButton(
        systemName: String,
        label: String,
        tint: Color,
        action: @escaping () -> Void
    ) -> some View {
        VStack(spacing: 12) {
            Button(action: action) {
                Image(systemName: systemName)
                    .font(.system(size: 28))
                    .foregroundStyle(.white)
                    .frame(width: 72, height: 72)
                    .background(tint)
                    .clipShape(Circle())
            }
            .accessibilityLabel(label)

            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func answer() {
        Task {
            await CallNotificationManager.shared.cancelAll()
            CallKitManager.shared.endCurrentCall(reason: .answeredElsewhere)
            state.phase = .answered
        }
    }

    private func decline() {
        Task {
            await CallNotificationManager.shared.cancelAll()
            CallKitManager.shared.endCurrentCall(reason: .declinedElsewhere)
            state.phase = .declined
        }
    }
}
