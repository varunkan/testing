import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var app: AppModel
    @State private var universeText: String = ""

    var body: some View {
        NavigationStack {
            ZStack {
                AtmosphereBackground()

                Form {
                    Section {
                        Toggle("Demo mode (offline sample data)", isOn: $app.useDemoMode)
                        TextField("API base URL", text: Binding(
                            get: { app.apiBaseURLString },
                            set: { app.apiBaseURLString = $0 }
                        ))
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .disabled(app.useDemoMode)
                    } header: {
                        Text("Connection")
                    } footer: {
                        Text("Start the backend with: uvicorn wealthsimple_agent.api.main:app --port 8000. For a physical iPhone, use your Mac’s LAN IP instead of 127.0.0.1.")
                    }

                    Section("Goal") {
                        HStack {
                            Text("Daily budget")
                            Spacer()
                            TextField("100", value: $app.goal.dailyBudget, format: .currency(code: "USD"))
                                .keyboardType(.decimalPad)
                                .multilineTextAlignment(.trailing)
                                .frame(width: 120)
                        }
                        HStack {
                            Text("Monthly target")
                            Spacer()
                            Text("\(Int(app.goal.monthlyTargetPct * 100))%")
                        }
                        Slider(value: $app.goal.monthlyTargetPct, in: 0.05...0.50, step: 0.05)
                            .tint(ForgeTheme.amber)
                    }

                    Section("Risk") {
                        HStack {
                            Text("Take profit")
                            Spacer()
                            Text("\(Int(app.goal.takeProfitPct * 100))%")
                        }
                        Slider(value: $app.goal.takeProfitPct, in: 0.01...0.15, step: 0.01)
                            .tint(ForgeTheme.buy)
                        HStack {
                            Text("Stop loss")
                            Spacer()
                            Text("\(Int(app.goal.stopLossPct * 100))%")
                        }
                        Slider(value: $app.goal.stopLossPct, in: 0.01...0.15, step: 0.01)
                            .tint(ForgeTheme.sell)
                        Stepper("Max hold days: \(app.goal.maxHoldDays)", value: $app.goal.maxHoldDays, in: 1...20)
                        Stepper("Max new buys/day: \(app.goal.maxNewBuysPerDay)", value: $app.goal.maxNewBuysPerDay, in: 1...8)
                    }

                    Section("Universe") {
                        TextField("AAPL, MSFT, …", text: $universeText)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .onAppear { universeText = app.goal.universeText }
                            .onChange(of: universeText) { _, newValue in
                                app.goal.universeText = newValue
                            }
                    }

                    Section {
                        Button("Save settings") {
                            app.saveGoal()
                        }
                        .foregroundStyle(ForgeTheme.deepTeal)
                    }

                    Section {
                        Text("Forge Desk is educational software. Not financial advice. Live Wealthsimple automation requires an official broker API.")
                            .font(.caption)
                            .foregroundStyle(ForgeTheme.muted)
                    }
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
