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

// FeatureDTO is the ops registry shape (its `id` is a spec code) and is deliberately not fetched by
// this app; the friendly `/mobile/features` DTO in Endpoints.swift is what screens render.

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
	/// A 4xx/5xx the server answered with. The body is carried because it is the only place the
	/// reason lives — a validation error names the field the form got wrong.
	case refused(Int, Data)
}

extension ApiError: LocalizedError {
	/// What the person reads when a submission is refused.
	///
	/// The server's own message is the useful part — a validation error names the field the form got
	/// wrong — so it is lifted out of `detail` rather than replaced by a generic sentence. Without
	/// this the result panel would say "The operation couldn't be completed. (ApiError error 1.)".
	var errorDescription: String? {
		switch self {
		case .transport(let code):
			return "Could not reach the server (code \(code))."
		case .refused(let code, let data):
			if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
			   let detail = obj["detail"] {
				let text = detail is String ? (detail as? String ?? "") : String(decoding: try! JSONSerialization.data(withJSONObject: detail), as: UTF8.self)
				return "The server refused this (\(code)): \(text)"
			}
			return "The server refused this (\(code)): \(String(decoding: data.prefix(300), as: UTF8.self))"
		}
	}
}