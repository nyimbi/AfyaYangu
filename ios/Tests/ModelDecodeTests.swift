import XCTest

@testable import AfyaYangu

final class ModelDecodeTests: XCTestCase {
	func testHealthDecode() throws {
		let d = try JSONDecoder().decode(HealthDTO.self, from: Data(#"{"status":"ok","version":"2.0.0","tier4":false}"#.utf8))
		XCTAssertEqual(d.status, "ok")
		XCTAssertFalse(d.tier4)
	}

	func testFeatureDecode() throws {
		let list = try JSONDecoder().decode([FeatureDTO].self, from: Data(
			#"[{"id":"TRI-001","name":"Broad Febrile-Illness Triage","tier":1,"channels":["native","whatsapp","ussd","sms"]}]"#.utf8))
		XCTAssertEqual(list.first?.channels.count, 4)
	}

	func testTriageDecode() throws {
		let d = try JSONDecoder().decode(TriageResultDTO.self, from: Data(
			#"{"risk_level":"malaria_suspect","recommendation":"Test malaria first","treated_as_malaria_first":true,"escalate_719":false}"#.utf8))
		XCTAssertTrue(d.treated_as_malaria_first)
		XCTAssertFalse(d.escalate_719)
	}

	func testTriageRequestEncoding() throws {
		let body = try JSONEncoder().encode(TriageRequestDTO(symptoms: ["fever"], temperature_c: 38.6, ebola_contact: false))
		let echoed = try JSONDecoder().decode(TriageRequestDTO.self, from: body)
		XCTAssertEqual(echoed.temperature_c, 38.6)
	}

	func testEmergencyCardRoundtrip() async throws {
		let defaults = UserDefaults(suiteName: "test.card")!
		defaults.removePersistentDomain(forName: "test.card")
		let client = BackendClient(baseURL: "http://localhost:8000", defaults: defaults)
		let card = "AFYA|Wanjiku|O+|penicillin|+254711222333"
		await client.saveEmergencyCard(card)
		let stored = await client.emergencyCard()
		XCTAssertEqual(stored, card)
	}
}