import SwiftUI

@main
struct GrowOpApp: App {
    @State private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                .tint(.accentColor)
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                appState.startPolling()
            case .inactive, .background:
                appState.stopPolling()
            @unknown default:
                break
            }
        }
    }
}
