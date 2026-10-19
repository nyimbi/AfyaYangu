import Foundation

// Additional endpoint DTOs (wallet, diary, CHW, sensors, facilities).
struct FacilityDTO: Codable, Identifiable {
	let id: String
	let facility_id: String
	let name: String
	let kind: String
	let county: String
	let ed_status: String?
}

struct NearestResponseDTO: Codable, Identifiable {
	var id: String { facility.facility_id }
	let facility: FacilityDTO
	let km: Double
}

struct MemberDTO: Codable, Identifiable {
	let member_ref: String
	let dob_iso: String
	let is_minor: Bool
	let guardian_ref: String?
	var id: String { member_ref }
}

struct WalletDTO: Codable {
	let guardian: MemberDTO
	let members: [MemberDTO]
	let gaps: [String: [String]]
}

struct DiaryDTO: Codable, Identifiable {
	let entry_id: String
	let day: Int
	let symptoms: [String]
	let temperature_c: Double
	let synced: Bool
	var id: String { entry_id }
}

struct ChwTaskDTO: Codable, Identifiable {
	let task_id: String
	let chw_ref: String
	let community: String
	let kind: String
	let done: Bool
	var id: String { task_id }
}

struct SenseIngestDTO: Encodable {
	let kind: String
	let subject_ref: String
	let value: Double
	let county: String
}

struct SenseVerdictDTO: Decodable {
	let band: String
	let detail: String
}

extension BackendClient {
	func nearest(lat: Double, lon: Double, kind: String?, limit: Int = 3) async throws -> [NearestResponseDTO] {
		var comps = URLComponents(url: base.appendingPathComponent("facilities/nearest"), resolvingAgainstBaseURL: false)!
		comps.queryItems = [URLQueryItem(name: "lat", value: String(lat)), URLQueryItem(name: "lon", value: String(lon)), URLQueryItem(name: "limit", value: String(limit))]
		if let kind {
			comps.queryItems?.append(URLQueryItem(name: "kind", value: kind))
		}
		let data = try await send(url: comps.url!)
		return try JSONDecoder().decode([NearestResponseDTO].self, from: data)
	}

	func wallet(guardianRef: String) async throws -> WalletDTO {
		try JSONDecoder().decode(WalletDTO.self, from: try await send(path: "records/\(guardianRef)/wallet"))
	}

	func diary(subjectRef: String) async throws -> [DiaryDTO] {
		try JSONDecoder().decode([DiaryDTO].self, from: try await send(path: "triage/\(subjectRef)/diary"))
	}

	func chwTasks(_ chwRef: String) async throws -> [ChwTaskDTO] {
		try JSONDecoder().decode([ChwTaskDTO].self, from: try await send(path: "channels/chw/tasks/\(chwRef)"))
	}

	func completeTask(_ id: String) async throws {
		var req = URLRequest(url: base.appendingPathComponent("channels/chw/tasks/\(id)/done"))
		req.httpMethod = "POST"
		_ = try await send(req: req)
	}

	func ingest(_ dto: SenseIngestDTO) async throws -> SenseVerdictDTO {
		var req = URLRequest(url: base.appendingPathComponent("sensors/ingest"))
		req.httpMethod = "POST"
		req.setValue("application/json", forHTTPHeaderField: "content-type")
		req.httpBody = try JSONEncoder().encode(dto)
		return try JSONDecoder().decode(SenseVerdictDTO.self, from: try await send(req: req))
	}
}

struct PlaceDTO: Codable, Identifiable {
	var id: String { osm_id }
	let osm_id: String
	let name: String
	let kind: String
	let lat: Double
	let lon: Double
	let opening_hours: String?
}

struct PlaceNearestDTO: Codable, Identifiable {
	var id: String { place.osm_id }
	let place: PlaceDTO
	let km: Double
	let directions: DirectionsDTO
}

struct DirectionsDTO: Codable {
	let distance_km: Double
	let bearing_deg: Int
	let walk_minutes: Int
	let guidance: String
	let apple_maps_url: String
	let google_maps_url: String
}

extension BackendClient {
	func nearestPlaces(lat: Double, lon: Double, kind: String, limit: Int = 5) async throws -> [PlaceNearestDTO] {
		var comps = URLComponents(url: base.appendingPathComponent("places/nearest"), resolvingAgainstBaseURL: false)!
		comps.queryItems = [
			URLQueryItem(name: "lat", value: String(lat)),
			URLQueryItem(name: "lon", value: String(lon)),
			URLQueryItem(name: "kinds", value: kind),
			URLQueryItem(name: "limit", value: String(limit)),
		]
		return try JSONDecoder().decode([PlaceNearestDTO].self, from: try await send(url: comps.url!))
	}

	func importOsmPlaces(lat: Double, lon: Double) async throws -> String {
		let d = try await send(url: base.appendingPathComponent("places/import-osm?county_lat=\(lat)&county_lon=\(lon)"))
		let obj = try JSONSerialization.jsonObject(with: d, options: []) as? [String: Int]
		return "OSM import: \(obj?["imported"] ?? 0) places (total \(obj?["total"] ?? 0))"
	}
}


struct FriendlyFeatureDTO: Codable, Identifiable {
	let id: String
	let title: String
	let description: String
}

extension BackendClient {
	func friendlyFeatures() async throws -> [FriendlyFeatureDTO] {
		try JSONDecoder().decode([FriendlyFeatureDTO].self, from: try await send(path: "mobile/features"))
	}
}

// Server-driven action catalogue (GET /mobile/actions). One generic form per action; no field
// maps to a specific feature, so new backend actions need no app release.
struct MobileFieldDTO: Codable, Identifiable {
	var id: String { name }
	let name: String
	let label: String
	let type: String
	let options: [String]?
	let placeholder: String?
	let required: Bool
	// The device's own subject: the client supplies it and does not draw it. Marked by the server
	// because the route binds the subject to the token, so a drawn control could only be refused.
	let client_supplied: Bool?
	// A reference the server mints. Undrawn for the same reason and a different one: nobody knows
	// the value until the request arrives, so a form could only ask a person to invent a key.
	let server_assigned: Bool?
	// Required only when another field holds one of `equals_any` (empty means any answer). `required`
	// alone could not say this, which is how a voice-note report with no recording was drawn as a
	// complete submission and refused by the route.
	let condition: FieldConditionDTO?
	// The field this one must not equal. Not requiredness — `required = (a != b)` is false for every
	// answer — but a rule the route enforces and a form can at least label.
	let distinct_from: String?
	// The route reads this action's fields from a `multipart/form-data` body rather than JSON. The
	// server marks it because the transport is the route's, not the field's: inferring multipart
	// from "there is a file field" is a rule the client invented, and a form-encoded action without
	// a file would be sent as JSON and refused.
	let form: Bool?
	// What the picker may offer for a `file` field, from the route's own claim.
	let accept: String?
}

struct FieldConditionDTO: Codable {
	let when: String
	let equals_any: [String]
}

/// At least one of `fields` must be answered — the route accepts either. `when` gates the group.
struct FieldGroupDTO: Codable {
	let fields: [String]
	let when: String?
	let equals_any: [String]
}

struct MobileActionDTO: Codable, Identifiable {
	let id: String
	let title: String
	let group: String
	let method: String
	let path: String
	let fields: [MobileFieldDTO]
	let any_of: [FieldGroupDTO]?
}

extension BackendClient {
	func actions() async throws -> [MobileActionDTO] {
		try JSONDecoder().decode([MobileActionDTO].self, from: try await send(path: "mobile/actions"))
	}

	// Invoke a catalogue action: path params substitute into the URL, other fields go in the
	// query string (GET) or JSON body (POST/DELETE); a file field switches to multipart.
	func invoke(_ action: MobileActionDTO, values: [String: String], file: Data?) async throws -> Data {
		let (req, _) = try await buildRequest(action, values: values, file: file)
		return try await send(req: req)
	}

	/// §16.1: submit, or keep the write if the network is down. A GET is never queued.
	///
	/// A file upload is queued **with its bytes**. The queue stores the multipart body it would have
	/// sent, base64'd, and replays it byte-identically: the boundary is derived from the action's
	/// content rather than a UUID, so the replayed body is the same bytes and §15.5's replay table
	/// recognises it. Leaving the upload unqueued meant a person who photographed evidence with no
	/// signal lost the photograph — the one case where the form's payload cannot be retyped.
	func submitOrQueue(_ action: MobileActionDTO, values: [String: String], file: Data?) async throws -> Data {
		if action.method == "GET" { return try await invoke(action, values: values, file: file) }
		if !(await online()) {
			let (req, body) = try await buildRequest(action, values: values, file: file)
			let contentType = req.value(forHTTPHeaderField: "content-type") ?? "application/json"
			enqueue(method: action.method, url: req.url!.absoluteString, body: body,
				bodyBytes: req.httpBody, contentType: contentType)
			return Data("{\"queued\":true}".utf8)
		}
		return try await invoke(action, values: values, file: file)
	}

	/// Build the request an action describes, plus the exact body text (empty for GET/multipart), so
	/// a failed write can be queued and later replayed byte-identically.
	private func buildRequest(_ action: MobileActionDTO, values: [String: String], file: Data?) async throws -> (URLRequest, String) {
		// The subject is the device's, not a form field: a personal-data route binds the subject it
		// is given to the token, so anything else is refused by construction. The server marks the
		// field; a worker action's subject is unmarked and names someone else deliberately.
		let mine = try await subjectRef()
		var values = values
		// Keyed on the field being a subject, not on any field carrying a flag: a server-assigned
		// reference is not an identity, and injecting a subject for one would name a person into a
		// request that has no subject field.
		if action.fields.contains(where: { $0.name == "subject_ref" && $0.client_supplied == true }) { values["subject_ref"] = mine }
		let tokens = Self.placeholders(in: action.path)
		var taken: Set<String> = []
		var path = action.path
		for field in action.fields where field.type == "path" {
			let token = tokens.contains(field.name) ? field.name : tokens.first { !taken.contains($0) }
			guard let token else { continue }
			taken.insert(token)
			let raw = values[field.name] ?? ""
			path = path.replacingOccurrences(of: "{\(token)}", with: raw.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? raw)
		}
		var query: [URLQueryItem] = []
		var body: [String: Any] = [:]
		for field in action.fields where field.type != "path" {
			guard let value = Self.jsonValue(field, raw: values[field.name]) else { continue }
			if action.method == "GET" { query.append(URLQueryItem(name: field.name, value: Self.queryText(value))) } else { body[field.name] = value }
		}
		var comps = URLComponents(url: base.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
		if !query.isEmpty { comps.queryItems = query }
		var req = URLRequest(url: comps.url!)
		req.httpMethod = action.method
		// For multipart this is the base64 of the exact bytes sent, so the queue can replay them.
		var bodyText = ""
		let encodedAsForm = action.fields.contains(where: { $0.form == true })
		if action.method != "GET", encodedAsForm || action.fields.contains(where: { $0.type == "file" }) {
			// The boundary is derived from the body's own text, not a UUID: the server's §15.5
			// replay table compares bodies, so a random boundary would make every retry a
			// different request. The filename and mime come from what the picker produced.
			// Sorted, because a Swift dictionary's description is not ordered: a boundary taken from
			// it would differ between launches, so the replay would not be the bytes the first
			// attempt sent and §15.5's replay table would see a new request.
			let canonical = values.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: "&")
			let boundary = "afya-" + String(Self.opKey(method: action.method, url: action.path, body: canonical).dropFirst(3))
			req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "content-type")
			// The catalogue's own claim about the part, not a guess from the path.
			let accepting = action.fields.first { $0.type == "file" }?.accept ?? ""
			let kind = accepting.hasPrefix("image") ? ("photo.jpg", "image/jpeg") : ("recording.wav", "audio/wav")
			let encoded = Self.multipart(boundary: boundary, fields: body, file: file, filename: kind.0, mime: kind.1)
			req.httpBody = encoded
			bodyText = encoded.base64EncodedString()
		} else if action.method != "GET", !body.isEmpty {
			req.setValue("application/json", forHTTPHeaderField: "content-type")
			let data = try JSONSerialization.data(withJSONObject: body)
			req.httpBody = data
			bodyText = String(decoding: data, as: UTF8.self)
		}
		return (req, bodyText)
	}

	private static func placeholders(in path: String) -> [String] {
		var out: [String] = []
		var name = ""
		var inside = false
		for ch in path {
			if ch == "{" { inside = true; name = "" }
			else if ch == "}" { if inside { out.append(name) }; inside = false }
			else if inside { name.append(ch) }
		}
		return out
	}

	// Empty optional fields are omitted; typed values are encoded for the JSON body.
	private static func jsonValue(_ field: MobileFieldDTO, raw: String?) -> Any? {
		let trimmed = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
		if field.type == "bool" { return raw == nil ? nil : trimmed == "true" }
		if trimmed.isEmpty { return nil }
		switch field.type {
		// A number the device cannot parse is sent as the text the person typed, not dropped: the
		// route then refuses it with a message naming the field. `Int("1,5")` returning nil used to
		// omit the field silently, so a required value vanished from the body and the refusal named
		// nothing at all.
		case "int": return Int(trimmed) ?? trimmed
		case "decimal": return Double(trimmed) ?? trimmed
		case "list": return trimmed.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
		default: return trimmed
		}
	}

	private static func queryText(_ value: Any) -> String {
		(value as? [String])?.joined(separator: ",") ?? "\(value)"
	}

	private static func multipart(boundary: String, fields: [String: Any], file: Data?,
		filename: String = "upload.jpg", mime: String = "image/jpeg") -> Data {
		var out = Data()
		for (name, value) in fields {
			let text = (value as? [String])?.joined(separator: ",") ?? "\(value)"
			out.append(contentsOf: "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(text)\r\n".utf8)
		}
		// A form action without a file still sends its fields: the route decides whether the file
		// part is required, and inventing an empty one would hand it a zero-byte upload.
		if let file {
			out.append(contentsOf: "--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\nContent-Type: \(mime)\r\n\r\n".utf8)
			out.append(file)
		}
		out.append(contentsOf: "\r\n--\(boundary)--\r\n".utf8)
		return out
	}
}
