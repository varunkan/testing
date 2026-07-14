import SwiftUI

struct ProgressScreen: View {
    @EnvironmentObject private var app: AppModel
    @State private var animateBar = false

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphereBackground()

                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        Text("Monthly progress")
                            .font(.system(.title, design: .serif).weight(.semibold))
                            .foregroundStyle(ForgeTheme.ink)
                            .padding(.horizontal, 20)
                            .padding(.top, 12)

                        Text("Aspirational target — not a guarantee. Realized P&L after fees.")
                            .font(.subheadline)
                            .foregroundStyle(ForgeTheme.muted)
                            .padding(.horizontal, 20)

                        if let p = app.monthlyProgress {
                            progressCard(p)
                            statsGrid(p)
                            disclaimer
                        } else {
                            ProgressView()
                                .tint(ForgeTheme.deepTeal)
                                .frame(maxWidth: .infinity)
                                .padding(.top, 40)
                        }

                        if let report = app.dailyReport, !report.trades_executed.isEmpty {
                            Text("Recent fills")
                                .font(.headline)
                                .foregroundStyle(ForgeTheme.ink)
                                .padding(.horizontal, 20)
                                .padding(.top, 8)
                            ForEach(report.trades_executed) { trade in
                                tradeRow(trade)
                            }
                            .padding(.horizontal, 20)
                        }
                    }
                    .padding(.bottom, 32)
                }
                .refreshable {
                    await app.refreshMonthly()
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("Forge Desk")
                        .font(.system(.headline, design: .serif).weight(.bold))
                }
            }
            .task {
                await app.refreshMonthly()
                withAnimation(.easeOut(duration: 0.9)) {
                    animateBar = true
                }
            }
        }
    }

    private func progressCard(_ p: MonthlyProgress) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text("$\(p.realized_pnl, specifier: "%.2f")")
                    .font(.system(size: 36, weight: .bold, design: .rounded))
                    .foregroundStyle(ForgeTheme.ink)
                Text("of $\(p.target_profit, specifier: "%.0f")")
                    .font(.title3)
                    .foregroundStyle(ForgeTheme.muted)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(ForgeTheme.seaMist)
                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [ForgeTheme.deepTeal, ForgeTheme.amber],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width * CGFloat(min(animateBar ? p.progressClamped : 0, 1)))
                }
            }
            .frame(height: 12)

            Text("\(Int(p.progress_pct * 100))% of \(Int(p.target_pct * 100))% monthly target · \(p.days_run) days run")
                .font(.footnote)
                .foregroundStyle(ForgeTheme.muted)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .padding(.horizontal, 20)
    }

    private func statsGrid(_ p: MonthlyProgress) -> some View {
        HStack(spacing: 12) {
            statTile(title: "Daily budget", value: String(format: "$%.0f", p.daily_budget))
            statTile(title: "Month", value: p.year_month)
            statTile(title: "Plan days", value: "\(p.planned_trading_days)")
        }
        .padding(.horizontal, 20)
    }

    private func statTile(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(ForgeTheme.muted)
            Text(value)
                .font(.system(.headline, design: .rounded))
                .foregroundStyle(ForgeTheme.ink)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.white.opacity(0.65))
        )
    }

    private func tradeRow(_ trade: TradeRecord) -> some View {
        HStack {
            Text(trade.side.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(trade.side.lowercased() == "buy" ? ForgeTheme.buy : ForgeTheme.sell)
            Text(trade.ticker)
                .font(.body.weight(.semibold))
            Spacer()
            if let pnl = trade.pnl {
                Text(pnl >= 0 ? "+$\(pnl, specifier: "%.2f")" : "-$\(abs(pnl), specifier: "%.2f")")
                    .foregroundStyle(pnl >= 0 ? ForgeTheme.buy : ForgeTheme.sell)
            } else {
                Text("$\(trade.px * trade.qty, specifier: "%.2f")")
                    .foregroundStyle(ForgeTheme.muted)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color.white.opacity(0.65))
        )
    }

    private var disclaimer: some View {
        Text("Targets are aspirational. Markets can lose money. Forge Desk recommends tickets for manual placement — it does not auto-trade on Wealthsimple.")
            .font(.caption)
            .foregroundStyle(ForgeTheme.muted)
            .padding(.horizontal, 20)
    }
}
