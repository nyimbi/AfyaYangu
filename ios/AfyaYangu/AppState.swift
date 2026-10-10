import Foundation
import SwiftUI

@MainActor
final class AppState: ObservableObject {
	@Published var health: HealthDTO?
	@Published var offline = false
	@Published var features: [FeatureDTO] = []
	@Published var friendly: [FriendlyFeatureDTO] = []
	@Published var card: String = ""

	let client = BackendClient(baseURL: UserDefaults.standard.string(forKey: "base_url") ?? "http://localhost:8000")

	init() {
		card = UserDefaults.standard.string(forKey: "emergency.card") ?? ""
	}

	func refresh() async {
		do {
			health = try await client.health()
			features = try await client.features()
			friendly = (try? await client.friendlyFeatures()) ?? []
			offline = false
		} catch {
			// Spec 16.1: UI never blocks on the network — degrade to cache.
			if let cached = try? await client.features() { features = cached }
			offline = true
		}
	}

	func saveCard(_ text: String) async {
		card = text
		await client.saveEmergencyCard(text)
	}

	func loadCard() async {
		card = await client.emergencyCard()
	}
}