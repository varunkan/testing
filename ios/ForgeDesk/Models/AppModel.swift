import Foundation
import SwiftUI

/// Shared app state: goal settings, today's report, monthly progress.
@MainActor
final class AppModel: ObservableObject {
    @Published var goal: GoalSettings
    @Published var dailyReport: DailyReport?
    @Published var monthlyProgress: MonthlyProgress?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var hasCompletedOnboarding: Bool
    @Published var useDemoMode: Bool

    private let defaults = UserDefaults.standard
    private let api: PortalAPIClient

    init(api: PortalAPIClient = PortalAPIClient()) {
        self.api = api
        let stored = GoalSettings.load(from: defaults) ?? GoalSettings.default
        self.goal = stored
        self.hasCompletedOnboarding = defaults.bool(forKey: "hasCompletedOnboarding")
        self.useDemoMode = defaults.object(forKey: "useDemoMode") as? Bool ?? true
        self.api.baseURL = URL(string: defaults.string(forKey: "apiBaseURL") ?? PortalAPIClient.defaultBaseURLString)!
    }

    var apiBaseURLString: String {
        get { api.baseURL.absoluteString }
        set {
            if let url = URL(string: newValue) {
                api.baseURL = url
                defaults.set(newValue, forKey: "apiBaseURL")
            }
        }
    }

    func saveGoal() {
        goal.save(to: defaults)
        defaults.set(true, forKey: "hasCompletedOnboarding")
        hasCompletedOnboarding = true
        defaults.set(useDemoMode, forKey: "useDemoMode")
    }

    func runMorningSession() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            if useDemoMode {
                dailyReport = DemoData.sampleDailyReport(budget: goal.dailyBudget)
                monthlyProgress = DemoData.sampleMonthlyProgress(
                    budget: goal.dailyBudget,
                    targetPct: goal.monthlyTargetPct
                )
            } else {
                let report = try await api.runDaily(config: goal.asPortalConfig())
                dailyReport = report
                monthlyProgress = report.monthlyProgress
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshMonthly() async {
        do {
            if useDemoMode {
                monthlyProgress = DemoData.sampleMonthlyProgress(
                    budget: goal.dailyBudget,
                    targetPct: goal.monthlyTargetPct
                )
            } else {
                let ym = MonthKey.current()
                monthlyProgress = try await api.fetchMonthly(
                    yearMonth: ym,
                    dailyBudget: goal.dailyBudget
                )
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
