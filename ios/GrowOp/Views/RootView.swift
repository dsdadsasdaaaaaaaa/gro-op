import SwiftUI

enum AppTab: String, Hashable {
    case home, advisor, log, photos, tasks
}

struct RootView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        Group {
            if app.isConfigured {
                MainTabView()
            } else {
                OnboardingView()
            }
        }
        .animation(.default, value: app.isConfigured)
    }
}

struct MainTabView: View {
    @Environment(AppState.self) private var app
    // `-growop.initialTab photos` as a launch argument opens on that tab (handy for testing).
    @State private var selectedTab: AppTab = AppTab(rawValue: UserDefaults.standard.string(forKey: "growop.initialTab") ?? "") ?? .home

    var body: some View {
        TabView(selection: $selectedTab) {
            HomeView(selectedTab: $selectedTab)
                .tabItem { Label("Home", systemImage: "leaf.fill") }
                .tag(AppTab.home)

            AdvisorView()
                .tabItem { Label("Advisor", systemImage: "brain.head.profile") }
                .tag(AppTab.advisor)
                .badge(app.status?.unreadBrief == true ? "New" : nil)

            LogView()
                .tabItem { Label("Log", systemImage: "square.and.pencil") }
                .tag(AppTab.log)

            PhotosView()
                .tabItem { Label("Photos", systemImage: "camera.fill") }
                .tag(AppTab.photos)
                .badge(app.status?.openPhotoRequests ?? 0)

            TasksView()
                .tabItem { Label("Tasks", systemImage: "checklist") }
                .tag(AppTab.tasks)
                .badge(app.status?.openTasks ?? 0)
        }
        .task {
            app.startPolling()
            await app.refreshSettings()
        }
        // growop://advisor, growop://photos, growop://log, growop://tasks (used by push notifications)
        .onOpenURL { url in
            switch url.host?.lowercased() {
            case "advisor": selectedTab = .advisor
            case "photos": selectedTab = .photos
            case "log": selectedTab = .log
            case "tasks": selectedTab = .tasks
            default: selectedTab = .home
            }
        }
    }
}

struct OnboardingView: View {
    @Environment(AppState.self) private var app
    @State private var url: String = ServerConfig.defaultURL
    @State private var apiKey: String = ""
    @State private var isConnecting = false
    @State private var errorText: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    Image(systemName: "leaf.circle.fill")
                        .font(.system(size: 80))
                        .foregroundStyle(Color.accentColor)
                        .padding(.top, 40)

                    VStack(spacing: 8) {
                        Text("Connect to your grow brain")
                            .font(.title.bold())
                            .multilineTextAlignment(.center)
                        Text("Enter the address of the grow brain on your home network and the API key it was set up with. You only need to do this once.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.horizontal)

                    VStack(alignment: .leading, spacing: 14) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Server address").font(.subheadline.weight(.semibold))
                            TextField("http://homeassistant.local:8099", text: $url)
                                .textFieldStyle(.roundedBorder)
                                .keyboardType(.URL)
                                .textContentType(.URL)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                        }
                        VStack(alignment: .leading, spacing: 6) {
                            Text("API key").font(.subheadline.weight(.semibold))
                            TextField("Paste the key here", text: $apiKey)
                                .textFieldStyle(.roundedBorder)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                        }
                    }
                    .padding(.horizontal)

                    if let errorText {
                        Label(errorText, systemImage: "exclamationmark.triangle.fill")
                            .font(.subheadline)
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.leading)
                            .padding(.horizontal)
                    }

                    Button {
                        Task { await connect() }
                    } label: {
                        if isConnecting {
                            HStack(spacing: 10) { ProgressView().tint(.white); Text("Connecting…") }
                        } else {
                            Text("Connect")
                        }
                    }
                    .buttonStyle(BigButtonStyle())
                    .disabled(isConnecting || url.trimmingCharacters(in: .whitespaces).isEmpty || apiKey.trimmingCharacters(in: .whitespaces).isEmpty)
                    .padding(.horizontal)
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Color(.systemGroupedBackground))
        }
    }

    private func connect() async {
        isConnecting = true
        errorText = nil
        defer { isConnecting = false }
        do {
            try await app.connect(url: url, key: apiKey)
        } catch {
            errorText = error.localizedDescription
        }
    }
}
