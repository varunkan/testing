import Foundation

/// Offline sample data so the iOS UI is usable without a running backend.
enum DemoData {
    static func sampleDailyReport(budget: Double) -> DailyReport {
        let day: String = {
            let f = DateFormatter()
            f.calendar = Calendar(identifier: .gregorian)
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = .current
            f.dateFormat = "yyyy-MM-dd"
            return f.string(from: Date())
        }()
        let buys = [
            Recommendation(
                ticker: "NVDA",
                action: "buy",
                confidence: 0.82,
                score: 0.61,
                quantity: (budget * 0.55) / 920,
                limit_price: nil,
                expected_edge: 0.012,
                estimated_fees: 0.45,
                rationale: "Momentum + news sentiment aligned; score=0.61",
                reason: "top-ranked buy within daily budget"
            ),
            Recommendation(
                ticker: "AAPL",
                action: "buy",
                confidence: 0.74,
                score: 0.42,
                quantity: (budget * 0.44) / 210,
                limit_price: nil,
                expected_edge: 0.008,
                estimated_fees: 0.32,
                rationale: "Steady uptrend over lookback; score=0.42",
                reason: "top-ranked buy within daily budget"
            ),
        ]
        let sells = [
            Recommendation(
                ticker: "MSFT",
                action: "sell",
                confidence: 1.0,
                score: 0.0,
                quantity: 0.31,
                limit_price: nil,
                expected_edge: 0.034,
                estimated_fees: 0.28,
                rationale: "Position hit +3.4% take-profit",
                reason: "take-profit exit (+3.40%)"
            ),
        ]
        let progress = sampleMonthlyProgress(budget: budget, targetPct: 0.30)
        return DailyReport(
            day: day,
            budget_added: budget,
            recommendations: sells + buys,
            trades_executed: [
                TradeRecord(day: day, ts: nil, ticker: "MSFT", side: "sell", qty: 0.31, px: 428.2, fees: 0.28, pnl: 4.12),
            ],
            portfolio_after: PortfolioAfter(
                as_of: nil,
                cash: 12.4,
                equity: budget * 8.2,
                positions: [
                    PositionDTO(ticker: "NVDA", quantity: 0.42, avg_price: 905, opened_day: day),
                    PositionDTO(ticker: "AAPL", quantity: 1.1, avg_price: 208, opened_day: day),
                ]
            ),
            monthly_progress: progress
        )
    }

    static func sampleMonthlyProgress(budget: Double, targetPct: Double) -> MonthlyProgress {
        let target = targetPct * budget * 21
        let realized = target * 0.41
        return MonthlyProgress(
            year_month: MonthKey.current(),
            daily_budget: budget,
            planned_trading_days: 21,
            target_pct: targetPct,
            target_profit: target,
            realized_pnl: realized,
            progress_pct: realized / target,
            days_run: 12
        )
    }
}
