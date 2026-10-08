import Foundation

// Offline-first client per spec 16.1: cache last good response; 719 always callable.
actor BackendClient {
	private let base: URL
	private let session: URLSession = .shared
	private let defaults: UserDefaults

	init(baseURL: String, defaults: UserDefaults = .standard) {
		self.base = URL(string: baseURL)!
		self.defaults = defaults
	}

	func cached(_ key: String) -> Data? {
		defaults.data(forKey: "cache.\(key)")
	}

	private func send(path: String, body: Data? = nil) async throws -> Data {
		var req = URLRequest(url: base.appendingPathComponent(path))
		req.httpMethod = body == nil ? "GET" : "POST"
		if let body {
			req.httpBody = body
			req.setValue("application/json", forHTTPHeaderField: "content-type")
		}
		let (data, response): (Data, URLResponse) = try await withCheckedThrowingContinuation { cont in
			session.dataTask(with: req) { data, resp, err in
				if let err { cont.resume(throwing: err) } else { cont.resume(returning: (data ?? Data(), resp ?? URLResponse())) }
			}.resume()
		}
		guard let http = response as? HTTPURLResponse else { throw ApiError.transport(-1) }
		guard (200..<500).contains(http.statusCode) else { throw ApiError.transport(http.statusCode) }
		if (200..<300).contains(http.statusCode) { defaults.set(data, forKey: "cache.\(path)") }
		return data
	}

	func health() async throws -> HealthDTO {
		let data = try await send(path: "health")
		return try JSONDecoder().decode(HealthDTO.self, from: data)
	}

	func features() async throws -> [FeatureDTO] {
		let data = try await send(path: "features")
		return try JSONDecoder().decode([FeatureDTO].self, from: data)
	}

	func triagePreliminary(symptoms: [String], temperatureC: Double, ebolaContact: Bool) async throws -> TriageResultDTO {
		let body = try JSONEncoder().encode(TriageRequestDTO(symptoms: symptoms, temperature_c: temperatureC, ebola_contact: ebolaContact))
		let data = try await send(path: "triage/preliminary", body: body)
		return try JSONDecoder().decode(TriageResultDTO.self, from: data)
	}

	// EMG-003: offline emergency card persists without any network.
	func saveEmergencyCard(_ text: String) {
		defaults.set(text, forKey: "emergency.card")
	}

	func emergencyCard() -> String {
		defaults.string(forKey: "emergency.card") ?? "AFYA|set name|blood group|contact"
	}
}