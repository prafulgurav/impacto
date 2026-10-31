import SwiftUI

@main
struct LocalCallStyleApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var state = CallState.shared

    var body: some Scene {
        WindowGroup {
            ZStack {
                ContentView()
                // The in-app stand-in for Android's full-screen intent. It covers the app when
                // a call is ringing; it cannot cover the lock screen (only CallKit can).
                if state.phase == .ringing {
                    IncomingCallView()
                        .transition(.move(edge: .bottom))
                        .zIndex(1)
                }
            }
            .animation(.easeInOut(duration: 0.2), value: state.phase)
            .environmentObject(state)
        }
    }
}
