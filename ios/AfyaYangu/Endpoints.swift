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
}

struct MobileActionDTO: Codable, Identifiable {
	let id: String
	let title: String
	let group: String
	let method: String
	let path: String
	let fields: [MobileFieldDTO]
}

extension BackendClient {
	func actions() async throws -> [MobileActionDTO] {
		try JSONDecoder().decode([MobileActionDTO].self, from: try await send(path: "mobile/actions"))
	}

	// Invoke a catalogue action: path params substitute into the URL, other fields go in the
	// query string (GET) or JSON body (POST/DELETE); a file field switches to multipart.
	func invoke(_ action: MobileActionDTO, values: [String: String], file: Data?) async throws -> Data {
		// The subject is the device's, not a form field: a personal-data route binds the subject it
		// is given to the token, so anything else is refused by construction. The server marks the
		// field; a worker action's subject is unmarked and names someone else deliberately.
		let mine = try await subjectRef()
		var values = values
		if action.fields.contains(where: { $0.client_supplied == true }) { values["subject_ref"] = mine }
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
		if action.method != "GET", action.fields.contains(where: { $0.type == "file" }), let file {
			let boundary = "afya-\(UUID().uuidString)"
			req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "content-type")
			req.httpBody = Self.multipart(boundary: boundary, fields: body, file: file)
		} else if action.method != "GET", !body.isEmpty {
			req.setValue("application/json", forHTTPHeaderField: "content-type")
			req.httpBody = try JSONSerialization.data(withJSONObject: body)
		}
		return try await send(req: req)
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
		case "int": return Int(trimmed)
		case "decimal": return Double(trimmed)
		case "list": return trimmed.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
		default: return trimmed
		}
	}

	private static func queryText(_ value: Any) -> String {
		(value as? [String])?.joined(separator: ",") ?? "\(value)"
	}

	private static func multipart(boundary: String, fields: [String: Any], file: Data) -> Data {
		var out = Data()
		for (name, value) in fields {
			let text = (value as? [String])?.joined(separator: ",") ?? "\(value)"
			out.append(contentsOf: "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(text)\r\n".utf8)
		}
		out.append(contentsOf: "--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"upload.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
		out.append(file)
		out.append(contentsOf: "\r\n--\(boundary)--\r\n".utf8)
		return out
	}
}
