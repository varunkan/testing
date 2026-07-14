import Foundation

struct GoalSettings: Codable, Equatable {
    var dailyBudget: Double
    var monthlyTargetPct: Double
    var takeProfitPct: Double
    var stopLossPct: Double
    var maxHoldDays: Int
    var maxNewBuysPerDay: Int
    var minConfidenceToBuy: Double
    var universe: [String]

    static let `default` = GoalSettings(
        dailyBudget: 100,
        monthlyTargetPct: 0.30,
        takeProfitPct: 0.03,
        stopLossPct: 0.02,
        maxHoldDays: 5,
        maxNewBuysPerDay: 3,
        minConfidenceToBuy: 0.60,
        universe: ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "SPY", "QQQ"]
    )

    var targetProfitDollars: Double {
        monthlyTargetPct * dailyBudget * 21
    }

    var universeText: String {
        get { universe.joined(separator: ", ") }
        set {
            universe = newValue
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
                .filter { !$0.isEmpty }
        }
    }

    func asPortalConfig() -> PortalConfigPayload {
        PortalConfigPayload(
            daily_budget: dailyBudget,
            monthly_target_pct: monthlyTargetPct,
            take_profit_pct: takeProfitPct,
            stop_loss_pct: stopLossPct,
            max_hold_days: maxHoldDays,
            max_new_buys_per_day: maxNewBuysPerDay,
            min_confidence_to_buy: minConfidenceToBuy,
            planned_trading_days_per_month: 21,
            universe: universe,
            rss_urls: []
        )
    }

    func save(to defaults: UserDefaults) {
        if let data = try? JSONEncoder().encode(self) {
            defaults.set(data, forKey: "goalSettings")
        }
    }

    static func load(from defaults: UserDefaults) -> GoalSettings? {
        guard let data = defaults.data(forKey: "goalSettings") else { return nil }
        return try? JSONDecoder().decode(GoalSettings.self, from: data)
    }
}

struct PortalConfigPayload: Codable {
    var daily_budget: Double
    var monthly_target_pct: Double
    var take_profit_pct: Double
    var stop_loss_pct: Double
    var max_hold_days: Int
    var max_new_buys_per_day: Int
    var min_confidence_to_buy: Double
    var planned_trading_days_per_month: Int
    var universe: [String]
    var rss_urls: [String]
}

struct DailyRunRequest: Codable {
    var day: String?
    var config: PortalConfigPayload
}

struct Recommendation: Codable, Identifiable, Hashable {
    var id: String { "\(ticker)-\(action)-\(reason)-\(quantity)" }
    var ticker: String
    var action: String
    var confidence: Double
    var score: Double
    var quantity: Double
    var limit_price: Double?
    var expected_edge: Double
    var estimated_fees: Double
    var rationale: String
    var reason: String

    var isBuy: Bool { action.lowercased() == "buy" }
    var actionLabel: String { action.uppercased() }
}

struct DailyReport: Codable {
    var day: String
    var budget_added: Double
    var recommendations: [Recommendation]
    var trades_executed: [TradeRecord]
    var portfolio_after: PortfolioAfter
    var monthly_progress: MonthlyProgress

    var monthlyProgress: MonthlyProgress { monthly_progress }
}

struct TradeRecord: Codable, Identifiable {
    var id: String { "\(ts ?? "")-\(ticker)-\(side)-\(qty)" }
    var day: String?
    var ts: String?
    var ticker: String
    var side: String
    var qty: Double
    var px: Double
    var fees: Double
    var pnl: Double?
}

struct PortfolioAfter: Codable {
    var as_of: String?
    var cash: Double
    var equity: Double
    var positions: [PositionDTO]
}

struct PositionDTO: Codable, Identifiable {
    var id: String { ticker }
    var ticker: String
    var quantity: Double
    var avg_price: Double
    var opened_day: String?
}

struct MonthlyProgress: Codable {
    var year_month: String
    var daily_budget: Double
    var planned_trading_days: Int
    var target_pct: Double
    var target_profit: Double
    var realized_pnl: Double
    var progress_pct: Double
    var days_run: Int

    var progressClamped: Double {
        min(max(progress_pct, 0), 1.5)
    }
}

enum MonthKey {
    static func current() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f.string(from: Date())
    }
}
