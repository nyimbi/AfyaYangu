import Foundation

// DTOs mirroring src/afya/service.py contracts.
struct HealthDTO: Codable {
	let status: String
	let version: String
	let tier4: Bool
}

struct FeatureDTO: Codable, Identifiable {
	let id: String
	let name: String
	let tier: Int
	let channels: [String]
}

struct TriageRequestDTO: Codable {
	let symptoms: [String]
	let temperature_c: Double
	let ebola_contact: Bool
}

struct TriageResultDTO: Codable {
	let risk_level: String
	let recommendation: String
	let treated_as_malaria_first: Bool
	let escalate_719: Bool
}

enum ApiError: Error {
	case transport(Int)
}