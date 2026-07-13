# Forge Desk (iOS)

SwiftUI app for the daily **buy/sell recommendation portal**.

Brand: **Forge Desk** — morning recommendations, fixed daily budget, fee-aware tickets, monthly progress toward an aspirational target.

## Screens

1. **Onboarding** — set daily budget + monthly target %
2. **Today** — morning recommendation feed (buys + exits)
3. **Trade ticket** — detail + approve for *manual* brokerage placement
4. **Progress** — monthly realized P&L vs aspirational 30% target
5. **Settings** — demo mode, API URL, risk controls, universe

## Requirements

- macOS with **Xcode 15+** (iOS 17 deployment target)
- Optional: [XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`)
- Optional: Python backend from this repo for live data

## Open in Xcode

### Option A — XcodeGen (recommended)

```bash
cd ios
brew install xcodegen   # once
./bootstrap_xcode.sh
open ForgeDesk.xcodeproj
```

### Option B — New Xcode project

1. Xcode → File → New → Project → **App** (SwiftUI, Swift, iOS 17+)
2. Product Name: `ForgeDesk`
3. Delete the default `ContentView.swift`
4. Drag all files under `ios/ForgeDesk/` into the project (copy if needed)
5. Set Info.plist / enable **App Transport Security → Allow Local Networking** for `http://127.0.0.1:8000`

## Run (demo mode — no backend)

1. Build & run on Simulator
2. Demo mode is **on by default** (Settings) — uses offline sample recommendations
3. Explore Today → ticket detail → Progress

## Run against the Python portal API

```bash
# from repo root
pip3 install -r requirements.txt
uvicorn wealthsimple_agent.api.main:app --host 0.0.0.0 --port 8000
```

In the iOS app **Settings**:
- Turn **Demo mode** off
- API base URL:
  - Simulator: `http://127.0.0.1:8000`
  - Physical device: `http://<your-mac-lan-ip>:8000`

Then pull-to-refresh on **Today** to call `POST /portal/daily`.

## Important

- Tickets are for **manual placement** (tap Approve). The app does **not** auto-trade on Wealthsimple.
- Monthly profit targets are **aspirational**, not guaranteed.
- Not financial advice.
