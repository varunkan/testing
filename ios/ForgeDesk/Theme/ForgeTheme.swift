import SwiftUI

enum ForgeTheme {
    // Atmospheric light palette — forest teal + warm amber (not purple / cream / terracotta)
    static let ink = Color(red: 0.10, green: 0.16, blue: 0.18)
    static let muted = Color(red: 0.32, green: 0.40, blue: 0.42)
    static let creamFog = Color(red: 0.93, green: 0.96, blue: 0.95)
    static let seaMist = Color(red: 0.78, green: 0.90, blue: 0.88)
    static let deepTeal = Color(red: 0.07, green: 0.38, blue: 0.36)
    static let amber = Color(red: 0.86, green: 0.52, blue: 0.12)
    static let buy = Color(red: 0.12, green: 0.55, blue: 0.40)
    static let sell = Color(red: 0.72, green: 0.28, blue: 0.22)
    static let risk = Color(red: 0.55, green: 0.20, blue: 0.18)

    static var backgroundGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(red: 0.90, green: 0.95, blue: 0.94),
                Color(red: 0.96, green: 0.94, blue: 0.88),
                Color(red: 0.86, green: 0.92, blue: 0.91),
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    static var brandFont: Font {
        .system(.largeTitle, design: .serif).weight(.bold)
    }

    static var headlineFont: Font {
        .system(.title2, design: .serif).weight(.semibold)
    }

    static var bodyFont: Font {
        .system(.body, design: .default)
    }
}

struct AtmosphereBackground: View {
    var body: some View {
        ZStack {
            ForgeTheme.backgroundGradient
            // Soft diagonal band for depth (not flat single color)
            GeometryReader { geo in
                Path { path in
                    path.move(to: CGPoint(x: 0, y: geo.size.height * 0.18))
                    path.addLine(to: CGPoint(x: geo.size.width, y: geo.size.height * 0.05))
                    path.addLine(to: CGPoint(x: geo.size.width, y: geo.size.height * 0.42))
                    path.addLine(to: CGPoint(x: 0, y: geo.size.height * 0.55))
                    path.closeSubpath()
                }
                .fill(
                    LinearGradient(
                        colors: [
                            ForgeTheme.seaMist.opacity(0.55),
                            Color.clear,
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
            }
        }
        .ignoresSafeArea()
    }
}

struct PulseRing: View {
    @State private var pulse = false

    var body: some View {
        Circle()
            .stroke(ForgeTheme.deepTeal.opacity(0.25), lineWidth: 1)
            .scaleEffect(pulse ? 1.35 : 0.85)
            .opacity(pulse ? 0 : 0.7)
            .onAppear {
                withAnimation(.easeOut(duration: 2.2).repeatForever(autoreverses: false)) {
                    pulse = true
                }
            }
    }
}
