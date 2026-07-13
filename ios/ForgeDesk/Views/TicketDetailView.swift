import SwiftUI

struct TicketDetailView: View {
    let recommendation: Recommendation
    @Environment(\.dismiss) private var dismiss
    @State private var approved = false
    @State private var appear = false

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphereBackground()

                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        HStack {
                            Text(recommendation.actionLabel)
                                .font(.system(.caption, design: .rounded).weight(.bold))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 7)
                                .background(recommendation.isBuy ? ForgeTheme.buy : ForgeTheme.sell)
                                .clipShape(Capsule())
                            Spacer()
                            Text("Confidence \(Int(recommendation.confidence * 100))%")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(ForgeTheme.deepTeal)
                        }

                        Text(recommendation.ticker)
                            .font(.system(size: 42, weight: .bold, design: .serif))
                            .foregroundStyle(ForgeTheme.ink)
                            .opacity(appear ? 1 : 0)
                            .offset(y: appear ? 0 : 8)

                        Text(recommendation.reason)
                            .font(.title3)
                            .foregroundStyle(ForgeTheme.ink.opacity(0.85))

                        VStack(alignment: .leading, spacing: 12) {
                            metric("Quantity", value: String(format: "%.4f shares", recommendation.quantity))
                            metric("Expected edge", value: String(format: "%.2f%%", recommendation.expected_edge * 100))
                            metric("Estimated fees", value: String(format: "$%.2f", recommendation.estimated_fees))
                            if let px = recommendation.limit_price {
                                metric("Limit price", value: String(format: "$%.2f", px))
                            } else {
                                metric("Order type", value: "Market / best effort")
                            }
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .fill(.ultraThinMaterial)
                        )

                        Text(recommendation.rationale)
                            .font(.body)
                            .foregroundStyle(ForgeTheme.muted)

                        Text("Wealthsimple does not offer a public trading API. Approve to mark this ticket for manual placement in your brokerage app.")
                            .font(.footnote)
                            .foregroundStyle(ForgeTheme.muted)
                            .padding(.top, 4)

                        if approved {
                            Label("Marked for manual placement", systemImage: "checkmark.circle.fill")
                                .font(.headline)
                                .foregroundStyle(ForgeTheme.buy)
                                .transition(.opacity.combined(with: .move(edge: .bottom)))
                        } else {
                            Button {
                                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                                    approved = true
                                }
                            } label: {
                                Text(recommendation.isBuy ? "Approve buy ticket" : "Approve sell ticket")
                                    .font(.headline)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 16)
                                    .background(ForgeTheme.amber)
                                    .foregroundStyle(ForgeTheme.ink)
                                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                            }
                        }
                    }
                    .padding(24)
                }
            }
            .navigationTitle("Trade ticket")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
            .onAppear {
                withAnimation(.easeOut(duration: 0.45)) { appear = true }
            }
        }
    }

    private func metric(_ title: String, value: String) -> some View {
        HStack {
            Text(title)
                .foregroundStyle(ForgeTheme.muted)
            Spacer()
            Text(value)
                .font(.body.weight(.semibold))
                .foregroundStyle(ForgeTheme.ink)
        }
    }
}
