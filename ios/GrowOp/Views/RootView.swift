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
        // growop://setup?mode=direct&url=http://…:8099&key=… (from the dashboard's "Set up a phone" QR code)
        .onOpenURL { url in
            guard url.host?.lowercased() == "setup",
                  let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems,
                  let server = items.first(where: { $0.name == "url" })?.value, !server.isEmpty,
                  let key = items.first(where: { $0.name == "key" })?.value, !key.isEmpty else { return }
            let cfg = ServerConfig(mode: .direct, baseURL: server, apiKey: key, haURL: "", haToken: "", haAddonSlug: nil, haIngressPath: nil)
            Task { _ = try? await app.connect(cfg) }
        }
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
                .badge(app.needsYouPhotoCount)

            TasksView()
                .tabItem { Label("Tasks", systemImage: "checklist") }
                .tag(AppTab.tasks)
                .badge(app.needsYouTaskCount)
        }
        .task {
            app.startPolling()
            await app.refreshSettings()
            await app.loadPlants()
        }
        // One-time "Which plant is yours?" once the backend reports plants and none is chosen yet.
        .sheet(isPresented: Binding(get: { app.showPlantChoice }, set: { if !$0 { app.dismissPlantChoice() } })) {
            PlantChoiceSheet()
        }
        // growop://advisor, growop://photos, growop://log, growop://tasks (used by push notifications)
        .onOpenURL { url in
            // growop://photos?plant=2 opens on that plant, so a reminder about Dad's plant shows Dad's request
            if let p = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "plant" })?.value,
               let id = Int(p) {
                app.selectPlant(id)
            }
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
    // Prefilled from any previously saved config, or from `-growop.prefill.*` launch arguments
    // (used to push exact addresses onto the phone without typing).
    @State private var mode: ConnectionMode = ServerConfig.load().mode
    @State private var url: String = UserDefaults.standard.string(forKey: "growop.prefill.url")
        ?? (ServerConfig.load().baseURL.isEmpty ? ServerConfig.defaultURL : ServerConfig.load().baseURL)
    @State private var haURL: String = UserDefaults.standard.string(forKey: "growop.prefill.haURL") ?? ServerConfig.load().haURL
    @State private var haToken: String = ServerConfig.load().haToken
    @State private var apiKey: String = UserDefaults.standard.string(forKey: "growop.prefill.apiKey") ?? ServerConfig.load().apiKey
    @State private var isConnecting = false
    @State private var errorText: String?

    private var candidate: ServerConfig {
        ServerConfig(mode: mode, baseURL: url, apiKey: apiKey, haURL: haURL, haToken: haToken)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    Image(systemName: "leaf.circle.fill")
                        .font(.system(size: 80))
                        .foregroundStyle(Color.brand)
                        .padding(.top, 40)

                    VStack(spacing: 8) {
                        Text("Connect to GrowOp at home")
                            .font(.title.bold())
                            .multilineTextAlignment(.center)
                        Text(mode == .direct
                             ? "Enter the address of the grow brain on your home network and the API key it was set up with. You only need to do this once."
                             : "Connect through Home Assistant so the app works even when you're away from home.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.horizontal)

                    Picker("Connection", selection: $mode) {
                        ForEach(ConnectionMode.allCases, id: \.self) { m in
                            Text(m.title).tag(m)
                        }
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal)
                    .onChange(of: mode) { _, _ in errorText = nil }

                    VStack(alignment: .leading, spacing: 14) {
                        if mode == .direct {
                            field("Server address") {
                                TextField("http://homeassistant.local:8099", text: $url)
                                    .keyboardType(.URL)
                                    .textContentType(.URL)
                            }
                        } else {
                            field("Home Assistant URL") {
                                TextField("https://….ui.nabu.casa", text: $haURL)
                                    .keyboardType(.URL)
                                    .textContentType(.URL)
                            }
                            field("Home Assistant access token", hint: "Home Assistant → your profile (bottom left) → Security → Create token") {
                                SecureField("Paste the token here", text: $haToken)
                            }
                        }
                        field("Grow Brain API key") {
                            TextField("Paste the key here", text: $apiKey)
                        }
                    }
                    .padding(.horizontal)

                    if let errorText {
                        Label(errorText, systemImage: "exclamationmark.triangle.fill")
                            .font(.subheadline)
                            .foregroundStyle(Color.alertRed)
                            .multilineTextAlignment(.leading)
                            .frame(maxWidth: .infinity, alignment: .leading)
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
                    .disabled(isConnecting || !candidate.isConfigured)
                    .padding(.horizontal)
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Color.bg.ignoresSafeArea())
        }
    }

    @ViewBuilder
    private func field<Content: View>(_ title: String, hint: String? = nil, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.subheadline.weight(.semibold))
            content()
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
            if let hint {
                Text(hint).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func connect() async {
        isConnecting = true
        errorText = nil
        defer { isConnecting = false }
        do {
            try await app.connect(candidate)
        } catch {
            errorText = error.localizedDescription
        }
    }
}
