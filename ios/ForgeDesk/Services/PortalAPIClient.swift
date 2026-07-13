import Foundation

enum PortalAPIError: LocalizedError {
    case badURL
    case http(Int, String)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .badURL:
            return "Invalid API URL. Check Settings."
        case .http(let code, let body):
            return "Server error \(code): \(body)"
        case .decoding(let err):
            return "Could not read response: \(err.localizedDescription)"
        }
    }
}

final class PortalAPIClient {
    static let defaultBaseURLString = "http://127.0.0.1:8000"

    var baseURL: URL

    init(baseURL: URL = URL(string: PortalAPIClient.defaultBaseURLString)!) {
        self.baseURL = baseURL
    }

    func runDaily(config: PortalConfigPayload) async throws -> DailyReport {
        let body = DailyRunRequest(day: nil, config: config)
        return try await post(path: "/portal/daily", body: body)
    }

    func fetchRecommendations(day: String) async throws -> [Recommendation] {
        try await get(path: "/portal/recommendations/\(day)")
    }

    func fetchMonthly(yearMonth: String, dailyBudget: Double) async throws -> MonthlyProgress {
        guard var components = URLComponents(string: baseURL.absoluteString + "/portal/monthly/\(yearMonth)") else {
            throw PortalAPIError.badURL
        }
        components.queryItems = [URLQueryItem(name: "daily_budget", value: String(dailyBudget))]
        guard let url = components.url else { throw PortalAPIError.badURL }
        return try await get(url: url)
    }

    func fetchTrades(yearMonth: String) async throws -> [TradeRecord] {
        try await get(path: "/portal/trades/\(yearMonth)")
    }

    // MARK: - Internals

    private func get<T: Decodable>(path: String) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
            throw PortalAPIError.badURL
        }
        return try await get(url: url)
    }

    private func get<T: Decodable>(url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw PortalAPIError.decoding(error)
        }
    }

    private func post<Body: Encodable, T: Decodable>(path: String, body: Body) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
            throw PortalAPIError.badURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw PortalAPIError.decoding(error)
        }
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw PortalAPIError.http(http.statusCode, body)
        }
    }
}
