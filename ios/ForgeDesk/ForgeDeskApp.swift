//
//  ForgeDeskApp.swift
//  ForgeDesk
//
//  Morning buy/sell recommendation portal for the Wealthsimple trading agent.
//

import SwiftUI

@main
struct ForgeDeskApp: App {
    @StateObject private var appModel = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appModel)
                .preferredColorScheme(.light)
        }
    }
}
