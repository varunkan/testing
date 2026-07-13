import SwiftUI

/// First viewport: brand-first hero — Forge Desk, one headline, one sentence, one CTA.
struct OnboardingView: View {
    @EnvironmentObject private var app: AppModel
    @State private var appear = false

    var body: some View {
        ZStack {
            AtmosphereBackground()

            VStack(alignment: .leading, spacing: 0) {
                Spacer(minLength: 40)

                ZStack(alignment: .center) {
                    PulseRing()
                        .frame(width: 120, height: 120)
                    Image(systemName: "chart.xyaxis.line")
                        .font(.system(size: 36, weight: .light))
                        .foregroundStyle(ForgeTheme.deepTeal)
                        .scaleEffect(appear ? 1.0 : 0.92)
                        .animation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true), value: appear)
                }
                .frame(maxWidth: .infinity)
                .padding(.bottom, 28)
                .opacity(appear ? 1 : 0)
                .offset(y: appear ? 0 : 12)

                Text("Forge Desk")
                    .font(ForgeTheme.brandFont)
                    .foregroundStyle(ForgeTheme.ink)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .opacity(appear ? 1 : 0)

                Text("Morning recommendations. Fixed budget. Clear exits.")
                    .font(.system(.title3, design: .serif))
                    .foregroundStyle(ForgeTheme.ink.opacity(0.85))
                    .multilineTextAlignment(.center)
                    .padding(.top, 14)
                    .padding(.horizontal, 28)
                    .opacity(appear ? 1 : 0)
                    .offset(y: appear ? 0 : 8)

                Text("Set a daily budget. Each morning the agent ranks buys and sells with confidence and fee-aware sizing.")
                    .font(ForgeTheme.bodyFont)
                    .foregroundStyle(ForgeTheme.muted)
                    .multilineTextAlignment(.center)
                    .padding(.top, 12)
                    .padding(.horizontal, 36)
                    .opacity(appear ? 1 : 0)

                Spacer()

                VStack(spacing: 16) {
                    HStack {
                        Text("Daily budget")
                            .foregroundStyle(ForgeTheme.muted)
                        Spacer()
                        TextField("100", value: $app.goal.dailyBudget, format: .currency(code: "USD"))
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .font(.system(.title3, design: .rounded).weight(.semibold))
                            .foregroundStyle(ForgeTheme.ink)
                            .frame(width: 120)
                    }
                    .padding(.horizontal, 4)

                    HStack {
                        Text("Monthly target")
                            .foregroundStyle(ForgeTheme.muted)
                        Spacer()
                        Text("\(Int(app.goal.monthlyTargetPct * 100))%")
                            .font(.system(.title3, design: .rounded).weight(.semibold))
                            .foregroundStyle(ForgeTheme.ink)
                    }
                    .padding(.horizontal, 4)

                    Slider(
                        value: $app.goal.monthlyTargetPct,
                        in: 0.05...0.50,
                        step: 0.05
                    )
                    .tint(ForgeTheme.amber)

                    Text("Target ≈ $\(app.goal.targetProfitDollars, specifier: "%.0f") this month — aspirational, not guaranteed.")
                        .font(.footnote)
                        .foregroundStyle(ForgeTheme.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    Button {
                        withAnimation(.spring(response: 0.45, dampingFraction: 0.85)) {
                            app.saveGoal()
                        }
                    } label: {
                        Text("Open morning desk")
                            .font(.system(.headline, design: .rounded))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 16)
                            .background(ForgeTheme.deepTeal)
                            .foregroundStyle(.white)
                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    .padding(.top, 8)
                }
                .padding(24)
                .background(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(.ultraThinMaterial)
                )
                .padding(.horizontal, 20)
                .padding(.bottom, 28)
                .opacity(appear ? 1 : 0)
                .offset(y: appear ? 0 : 24)
            }
        }
        .onAppear {
            withAnimation(.easeOut(duration: 0.7)) {
                appear = true
            }
        }
    }
}
