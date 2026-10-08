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