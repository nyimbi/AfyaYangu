import Foundation

// Offline-first client per spec 16.1: cache last good response; 719 always callable.
actor BackendClient {
	let base: URL
	private let session: URLSession = .shared
	private let defaults: UserDefaults

	init(baseURL: String, defaults: UserDefaults = .standard) {
		self.base = URL(string: baseURL)!
		self.defaults = defaults
	}

	func cached(_ key: String) -> Data? {
		defaults.data(forKey: "cache.\(key)")
	}

	// Shared transport used by endpoint extensions.
	func send(path: String) async throws -> Data {
		try await send(req: URLRequest(url: base.appendingPathComponent(path)))
	}

	func send(url: URL) async throws -> Data {
		try await send(req: URLRequest(url: url))
	}

	func send(req: URLRequest) async throws -> Data {
		let (data, response): (Data, URLResponse) = try await withCheckedThrowingContinuation { cont in
			session.dataTask(with: req) { data, resp, err in
				if let err { cont.resume(throwing: err) } else { cont.resume(returning: (data ?? Data(), resp ?? URLResponse())) }
			}.resume()
		}
		let http = try __http(response)
		guard (200..<500).contains(http.statusCode) else { throw ApiError.transport(http.statusCode) }
		if (200..<300).contains(http.statusCode), let path = req.url?.path {
			defaults.set(data, forKey: "cache.\(path)")
		}
		return data
	}

	private func __http(_ response: URLResponse) throws -> HTTPURLResponse {
		guard let http = response as? HTTPURLResponse else { throw ApiError.transport(-1) }
		return http
	}

	func health() async throws -> HealthDTO {
		try JSONDecoder().decode(HealthDTO.self, from: try await send(path: "health"))
	}

	func features() async throws -> [FeatureDTO] {
		let data = try await send(path: "features")
		return try JSONDecoder().decode([FeatureDTO].self, from: data)
	}

	func triagePreliminary(symptoms: [String], temperatureC: Double, ebolaContact: Bool) async throws -> TriageResultDTO {
		var req = URLRequest(url: base.appendingPathComponent("triage/preliminary"))
		req.httpMethod = "POST"
		req.setValue("application/json", forHTTPHeaderField: "content-type")
		req.httpBody = try JSONEncoder().encode(TriageRequestDTO(symptoms: symptoms, temperature_c: temperatureC, ebola_contact: ebolaContact))
		return try JSONDecoder().decode(TriageResultDTO.self, from: try await send(req: req))
	}

	// EMG-003: offline emergency card persists without any network.
	func saveEmergencyCard(_ text: String) {
		defaults.set(text, forKey: "emergency.card")
	}

	func emergencyCard() -> String {
		defaults.string(forKey: "emergency.card") ?? "AFYA|set name|blood group|contact"
	}
}