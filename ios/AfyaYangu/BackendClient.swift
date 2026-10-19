import Foundation
import CryptoKit

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
		// A refusal is not a result. The bound used to be `< 500`, so every 401/403/422/429 came back
		// as data and the catalogue's result panel printed a validation error in the same style as a
		// success — on a form whose whole purpose is to tell a person whether their report was taken.
		// Android has always thrown `HttpError` on any non-2xx; this is the two clients agreeing.
		guard (200..<300).contains(http.statusCode) else { throw ApiError.refused(http.statusCode, data) }
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
		// The stored token goes with the reclaim: the server honours a subject this service minted
		// without one, and *any* subject when the request carries its token.
		let held = defaults.string(forKey: "session.token")
		var data = try await issueAnonymous(subject: known, bearer: held)
		if known != nil, !Self.isSuccess(data) {
			// The subject could not be reclaimed — revoked by `DELETE MY DATA`, or the server was
			// wiped. Ask for a new identity rather than staying stuck on a name it cannot use.
			data = try await issueAnonymous(subject: nil, bearer: nil)
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

	private static func isSuccess(_ data: Data) -> Bool {
		(try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["token"] is String
	}

	private func issueAnonymous(subject: String?, bearer: String?) async throws -> Data {
		var req = URLRequest(url: base.appendingPathComponent("auth/anonymous"))
		req.httpMethod = "POST"
		req.setValue("application/json", forHTTPHeaderField: "content-type")
		if let bearer { req.setValue("Bearer \(bearer)", forHTTPHeaderField: "authorization") }
		req.httpBody = try JSONSerialization.data(withJSONObject: subject.map { ["subject_ref": $0] } ?? [:])
		let (data, _): (Data, URLResponse) = try await withCheckedThrowingContinuation { cont in
			session.dataTask(with: req) { data, resp, err in
				if let err { cont.resume(throwing: err) } else { cont.resume(returning: (data ?? Data(), resp ?? URLResponse())) }
			}.resume()
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

	/// §ACC-003's local-first store. The session credentials and the response cache stay in
	/// `UserDefaults` — a token and a last-good response are a cache, and calling them a database
	/// would be the same overstatement in the other direction. What moves here is the *queue*,
	/// because §16.1 principles 1 and 5 are promises about durability and a cache cannot keep them.
	private lazy var store = LocalStore()

	func queuedCount() -> Int { store.pendingCount() }

	/// Keep a write for later. The key is derived from the op's own content, so the same op always
	/// carries the same key and a replay after a restart is a repeat, not a second write (§15.5).
	/// It is also the row's primary key, which makes the deduplication a constraint rather than a
	/// convention.
	func enqueue(method: String, url: String, body: String, bodyBytes: Data? = nil,
		contentType: String = "application/json") {
		// A multipart op is keyed on its *bytes*, not on the base64 text: two encodings of the same
		// body would otherwise be two ops, and the key is what makes the replay a repeat.
		let key = bodyBytes.map { Self.opKey(method: method, url: url, body: $0) }
			?? Self.opKey(method: method, url: url, body: body)
		store.enqueue(
			QueuedOp(
				opId: key,
				dataset: URL(string: url)?.pathComponents.dropFirst().first ?? "unknown",
				clientTs: Int64(Date().timeIntervalSince1970 * 1000),
				method: method,
				url: url,
				body: body,
				contentType: contentType,
				key: key,
				attempt: 0,
				retryAtMs: nil
			)
		)
	}

	/// The op's idempotency key, derived from its own content and nothing else.
	///
	/// This was `String.hashValue`, which Swift seeds **randomly per process**: the same write got a
	/// different key after every launch, so a queue replayed across a restart was not recognised as a
	/// repeat and the write landed twice — the exact failure the key exists to prevent. A digest of
	/// the content is the same on every launch and on every device.
	static func opKey(method: String, url: String, body: String) -> String {
		opKey(method: method, url: url, body: Data(body.utf8))
	}

	/// The same key over bytes. A multipart body is binary, and `String(decoding:as:)` maps every
	/// byte that is not valid UTF-8 to the same replacement character — so two different photographs
	/// would digest identically and the second would replay as the first. The text overload stays the
	/// spelling for a JSON op, because it is the one the server's replay table was built against.
	static func opKey(method: String, url: String, body: Data) -> String {
		let material = "\(method) \(url) " + body.base64EncodedString()
		let digest = SHA256.hash(data: Data(material.utf8))
		return "OP-" + digest.prefix(12).map { String(format: "%02X", $0) }.joined()
	}

	/// Replay the queue. Stops at the first op still unreachable so ordering holds; an op the server
	/// *refuses* (4xx) is dropped rather than blocking the queue behind it forever.
	///
	/// It reads the status itself rather than going through `send(req:)`, which throws on a refusal:
	/// going through it would collapse every status into one error and lose the 429's `Retry-After`.
	@discardableResult
	func flushQueue() async -> Int {
		var sent = 0
		// One session for the whole replay: if it cannot be obtained there is nothing to send to.
		guard let (_, token) = try? await ensureSession() else { return 0 }
		for op in store.pending() {
			let now = Int64(Date().timeIntervalSince1970 * 1000)
			// Inside its backoff window: nothing after it is due either, so the replay stops here.
			if let due = op.retryAtMs, now < due { return sent }
			guard let url = URL(string: op.url) else { store.drop(op.opId); continue }
			var req = URLRequest(url: url)
			req.httpMethod = op.method
			req.setValue(op.contentType, forHTTPHeaderField: "content-type")
			req.setValue(op.key, forHTTPHeaderField: "idempotency-key")
			req.httpBody = op.bodyData
			req.setValue("Bearer \(token)", forHTTPHeaderField: "authorization")
			do {
				let (_, resp) = try await session.data(for: req)
				let http = resp as? HTTPURLResponse
				let code = http?.statusCode ?? 0
				if (200..<300).contains(code) {
					store.markSynced(op.opId, serverTs: now)
					sent += 1
				} else if code == 429 {
					// The one 4xx a retry fixes: the server is asking the device to wait, and the queue
					// is already the thing that waits. Dropping it deleted a write the person had made
					// because the app had been busy — §16.1's "never lost" read literally. The wait is
					// the server's own, so `Retry-After` wins over the local backoff.
					let attempt = op.attempt + 1
					let hinted = (http?.value(forHTTPHeaderField: "Retry-After")).flatMap { Int64($0) }
					let wait = hinted.map { $0 * 1000 } ?? backoffDelayMs(attempt)
					store.deferOp(op.opId, attempt: attempt, retryAtMs: now + wait)
					return sent // ordering holds: the queue stops at the first op that did not go
				} else if (400..<500).contains(code) {
					store.drop(op.opId) // refused: dropping it is honest, retrying it is not
				} else {
					// §16.2's "retry with exponential backoff". The delay is the server's own
					// function (`afya.sync.service:backoff_delay_s`), reproduced here because the
					// device is the side that has to wait: 2^attempt seconds, capped, so a failing
					// server is not hit once per resume forever.
					let attempt = op.attempt + 1
					store.deferOp(op.opId, attempt: attempt, retryAtMs: now + backoffDelayMs(attempt))
					return sent // ordering holds: the queue stops at the first op that did not go
				}
			} catch {
				let attempt = op.attempt + 1
				store.deferOp(op.opId, attempt: attempt, retryAtMs: now + backoffDelayMs(attempt))
				return sent
			}
		}
		return sent
	}

	private func backoffDelayMs(_ attempt: Int) -> Int64 {
		let seconds = min(Int64(1) << Int64(min(max(attempt, 0), 10)), 600)
		return seconds * 1000
	}
}