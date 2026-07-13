import SwiftUI

struct RootView: View {
    @EnvironmentObject private var app: AppModel

    var body: some View {
        Group {
            if app.hasCompletedOnboarding {
                MainTabView()
            } else {
                OnboardingView()
            }
        }
        .animation(.easeInOut(duration: 0.35), value: app.hasCompletedOnboarding)
    }
}

struct MainTabView: View {
    @EnvironmentObject private var app: AppModel

    var body: some View {
        TabView {
            TodayView()
                .tabItem {
                    Label("Today", systemImage: "sun.horizon.fill")
                }
            ProgressScreen()
                .tabItem {
                    Label("Progress", systemImage: "chart.line.uptrend.xyaxis")
                }
            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "slider.horizontal.3")
                }
        }
        .tint(ForgeTheme.deepTeal)
        .task {
            if app.dailyReport == nil {
                await app.runMorningSession()
            }
        }
    }
}
