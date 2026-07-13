import SwiftUI

struct TodayView: View {
    @EnvironmentObject private var app: AppModel
    @State private var selected: Recommendation?

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphereBackground()

                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        header
                        if let err = app.errorMessage {
                            Text(err)
                                .font(.footnote)
                                .foregroundStyle(ForgeTheme.sell)
                                .padding(.horizontal, 20)
                        }
                        if app.isLoading && app.dailyReport == nil {
                            ProgressView("Researching morning ideas…")
                                .tint(ForgeTheme.deepTeal)
                                .frame(maxWidth: .infinity)
                                .padding(.top, 40)
                        } else if let report = app.dailyReport {
                            budgetChip(report)
                            recommendationsList(report.recommendations)
                        } else {
                            emptyState
                        }
                    }
                    .padding(.bottom, 32)
                }
                .refreshable {
                    await app.runMorningSession()
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("Forge Desk")
                        .font(.system(.headline, design: .serif).weight(.bold))
                        .foregroundStyle(ForgeTheme.ink)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await app.runMorningSession() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .foregroundStyle(ForgeTheme.deepTeal)
                    }
                    .disabled(app.isLoading)
                }
            }
            .sheet(item: $selected) { rec in
                TicketDetailView(recommendation: rec)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(greeting)
                .font(.system(.title, design: .serif).weight(.semibold))
                .foregroundStyle(ForgeTheme.ink)
            Text("Ranked buys and sells for today’s $\(app.goal.dailyBudget, specifier: "%.0f") budget.")
                .font(.subheadline)
                .foregroundStyle(ForgeTheme.muted)
        }
        .padding(.horizontal, 20)
        .padding(.top, 12)
    }

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        if hour < 12 { return "Good morning" }
        if hour < 18 { return "Afternoon desk" }
        return "Evening desk"
    }

    private func budgetChip(_ report: DailyReport) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Budget deployed")
                    .font(.caption)
                    .foregroundStyle(ForgeTheme.muted)
                Text("$\(report.budget_added, specifier: "%.0f")")
                    .font(.system(.title2, design: .rounded).weight(.bold))
                    .foregroundStyle(ForgeTheme.ink)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(report.day)
                    .font(.caption)
                    .foregroundStyle(ForgeTheme.muted)
                Text("\(report.recommendations.count) tickets")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(ForgeTheme.deepTeal)
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .padding(.horizontal, 20)
    }

    private func recommendationsList(_ items: [Recommendation]) -> some View {
        LazyVStack(spacing: 12) {
            ForEach(Array(items.enumerated()), id: \.element.id) { index, rec in
                Button {
                    selected = rec
                } label: {
                    RecommendationRow(recommendation: rec)
                }
                .buttonStyle(.plain)
                .opacity(1)
                .offset(y: 0)
                .animation(.spring(response: 0.5, dampingFraction: 0.85).delay(Double(index) * 0.05), value: items.count)
            }
        }
        .padding(.horizontal, 20)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Text("No morning tickets yet")
                .font(ForgeTheme.headlineFont)
                .foregroundStyle(ForgeTheme.ink)
            Text("Pull to refresh or tap the reload button.")
                .foregroundStyle(ForgeTheme.muted)
            Button("Run morning session") {
                Task { await app.runMorningSession() }
            }
            .buttonStyle(.borderedProminent)
            .tint(ForgeTheme.deepTeal)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 48)
    }
}

struct RecommendationRow: View {
    let recommendation: Recommendation

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Text(recommendation.actionLabel)
                .font(.system(.caption, design: .rounded).weight(.bold))
                .foregroundStyle(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(recommendation.isBuy ? ForgeTheme.buy : ForgeTheme.sell)
                .clipShape(Capsule())

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(recommendation.ticker)
                        .font(.system(.title3, design: .rounded).weight(.bold))
                        .foregroundStyle(ForgeTheme.ink)
                    Spacer()
                    Text("\(Int(recommendation.confidence * 100))%")
                        .font(.system(.subheadline, design: .rounded).weight(.semibold))
                        .foregroundStyle(ForgeTheme.deepTeal)
                }
                Text(recommendation.reason)
                    .font(.footnote)
                    .foregroundStyle(ForgeTheme.muted)
                    .lineLimit(2)
                HStack {
                    Text("Qty \(recommendation.quantity, specifier: "%.3f")")
                    Text("·")
                    Text("Edge \(recommendation.expected_edge * 100, specifier: "%.1f")%")
                    Text("·")
                    Text("Fees $\(recommendation.estimated_fees, specifier: "%.2f")")
                }
                .font(.caption2)
                .foregroundStyle(ForgeTheme.muted)
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white.opacity(0.72))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(ForgeTheme.seaMist.opacity(0.8), lineWidth: 1)
        )
    }
}
