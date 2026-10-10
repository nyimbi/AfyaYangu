import Foundation

// Offline-first client per spec 16.1: cache last good response; 719 always callable.
actor BackendClient {
	let base: URL
	private let session: URLSession = .shared
	private let defaults: UserDefaults
	private var sessionSubject: String?
	private var sessionToken: String?

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
		// Personal-data routes bind the subject they name to the token that named it (§17), so every
		// request carries the device's session. The subject is the device's, never a form field.
		var signed = req
		if signed.value(forHTTPHeaderField: "authorization") == nil {
			let (_, token) = try await ensureSession()
			signed.setValue("Bearer \(token)", forHTTPHeaderField: "authorization")
		}
		let (data, response): (Data, URLResponse) = try await withCheckedThrowingContinuation { cont in
			session.dataTask(with: signed) { data, resp, err in
				if let err { cont.resume(throwing: err) } else { cont.resume(returning: (data ?? Data(), resp ?? URLResponse())) }
			}.resume()
		}
		let http = try __http(response)
		guard (200..<500).contains(http.statusCode) else { throw ApiError.transport(http.statusCode) }
		if (200..<300).contains(http.statusCode), let path = signed.url?.path {
			defaults.set(data, forKey: "cache.\(path)")
		}
		return data
	}

	/// The device's anonymous subject, obtained once and reused across launches.
	func subjectRef() async throws -> String {
		try await ensureSession().0
	}

	/// Returns (subject, token), issuing one if the device has none or the token expired.
	private func ensureSession() async throws -> (String, String) {
		if let s = sessionSubject, let t = sessionToken { return (s, t) }
		let known = defaults.string(forKey: "session.subject")
		var body: [String: Any] = known.map { ["subject_ref": $0] } ?? [:]
		var req = URLRequest(url: base.appendingPathComponent("auth/anonymous"))
		req.httpMethod = "POST"
		req.setValue("application/json", forHTTPHeaderField: "content-type")
		req.httpBody = try JSONSerialization.data(withJSONObject: body)
		let (data, _): (Data, URLResponse) = try await withCheckedThrowingContinuation { cont in
			session.dataTask(with: req) { data, resp, err in
				if let err { cont.resume(throwing: err) } else { cont.resume(returning: (data ?? Data(), resp ?? URLResponse())) }
			}.resume()
		}
		guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any],
		      let s = obj["subject_ref"] as? String, let t = obj["token"] as? String else {
			throw ApiError.transport(-1)
		}
		sessionSubject = s
		sessionToken = t
		defaults.set(s, forKey: "session.subject")
		defaults.set(t, forKey: "session.token")
		return (s, t)
	}

	private func __http(_ response: URLResponse) throws -> HTTPURLResponse {
		guard let http = response as? HTTPURLResponse else { throw ApiError.transport(-1) }
		return http
	}

	func health() async throws -> HealthDTO {
		try JSONDecoder().decode(HealthDTO.self, from: try await send(path: "health"))
	}

	// No `features()`: the registry endpoint's id is a spec code (CHAN-000), and this app shows the
	// friendly `/mobile/features` instead (`friendlyFeatures()` in Endpoints.swift).

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

	// --- §16.1 offline queue: a write made with no network is kept, not lost -------------------

	/// Whether the backend is reachable now. A bare probe, no session, so it cannot recurse.
	func online() async -> Bool {
		var req = URLRequest(url: base.appendingPathComponent("health"))
		req.timeoutInterval = 2
		do {
			let (_, resp) = try await session.data(for: req)
			return ((resp as? HTTPURLResponse)?.statusCode ?? 0) < 500
		} catch {
			return false
		}
	}

	private var queuedOps: [[String: String]] {
		get { (defaults.array(forKey: "queue") as? [[String: String]]) ?? [] }
		set { defaults.set(newValue, forKey: "queue") }
	}

	func queuedCount() -> Int { queuedOps.count }

	/// Keep a write for later. The key is derived from the op's own content, so the same op always
	/// carries the same key and a replay after a restart is a repeat, not a second write (§15.5).
	func enqueue(method: String, url: String, body: String) {
		let key = "q-" + String(UInt(bitPattern: "\(method) \(url) \(body)".hashValue), radix: 16)
		queuedOps.append(["method": method, "url": url, "body": body, "key": key])
	}

	/// Replay the queue. Stops at the first op still unreachable so ordering holds; an op the server
	/// *refuses* (4xx) is dropped rather than blocking the queue behind it forever.
	///
	/// It reads the status itself rather than going through `send(req:)`, which only throws at 5xx:
	/// a 4xx there returns its body as though it were a success, so a refused op would be counted
	/// as sent and silently discarded rather than reported.
	@discardableResult
	func flushQueue() async -> Int {
		var remaining: [[String: String]] = []
		var sent = 0
		var stopped = false
		// One session for the whole replay: if it cannot be obtained there is nothing to send to.
		guard let (_, token) = try? await ensureSession() else { return 0 }
		for op in queuedOps {
			if stopped { remaining.append(op); continue }
			guard let url = URL(string: op["url"] ?? "") else { continue }
			var req = URLRequest(url: url)
			req.httpMethod = op["method"]
			req.setValue("application/json", forHTTPHeaderField: "content-type")
			req.setValue(op["key"], forHTTPHeaderField: "idempotency-key")
			req.httpBody = (op["body"] ?? "").data(using: .utf8)
			req.setValue("Bearer \(token)", forHTTPHeaderField: "authorization")
			do {
				let (_, resp) = try await session.data(for: req)
				let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
				if (200..<300).contains(code) {
					sent += 1
				} else if (400..<500).contains(code) {
					continue // refused: dropping it is honest, retrying it is not
				} else {
					remaining.append(op)
					stopped = true
				}
			} catch {
				remaining.append(op)
				stopped = true
			}
		}
		queuedOps = remaining
		return sent
	}
}