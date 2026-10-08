import SwiftUI

@MainActor
final class AppState: ObservableObject {
	@Published var health: HealthDTO?
	@Published var offline: Bool = false
	@Published var features: [FeatureDTO] = []
	@Published var card: String = ""

	let client = BackendClient(baseURL: "http://localhost:8000")

	init() {
		card = UserDefaults.standard.string(forKey: "emergency.card") ?? ""
	}

	func refresh() async {
		do {
			health = try await client.health()
			features = try await client.features()
			offline = false
		} catch {
			// Spec 16.1: UI never blocks on the network — degrade to cache.
			if let cached = try? await client.features() { features = cached }
			offline = true
		}
	}

	func assess(symptoms: [String], tempC: Double, contact: Bool) async -> TriageResultDTO? {
		try? await client.triagePreliminary(symptoms: symptoms, temperatureC: tempC, ebolaContact: contact)
	}
}

struct ContentView: View {
	@EnvironmentObject var state: AppState

	var body: some View {
		List {
			Section("Connection") {
				Label(state.offline ? "Offline — cached state shown" : "Connected",
					systemImage: state.offline ? "wifi.slash" : "wifi")
				if let h = state.health {
					Text("backend \(h.version) · tier4 \(h.tier4 ? "active" : "dormant")")
				}
			}
			Section("TRI-001 febrile triage") {
				Text("fever chips + contact switch live in TriageView")
			}
			Section("Active features (\(state.features.count))") {
				ForEach(state.features) { f in
					Label("\(f.id) \(f.name)", systemImage: "checkmark.seal")
				}
			}
		}
		.navigationBarTitle("Afya Yangu")
		.task { await state.refresh() }
		.refreshable { await state.refresh() }
	}
}

struct TriageView: View {
	@EnvironmentObject var state: AppState
	@State private var contact = false
	@State private var result: TriageResultDTO?

	var body: some View {
		Form {
			Section("Symptoms") {
				Toggle("Contact with EVD patient / affected area", isOn: $contact)
				WrapChips { tempC in
					result = await state.assess(symptoms: ["fever", "headache"], tempC: tempC, contact: contact)
				}
			}
			if let r = result {
				Section("Result") {
					Text("\(r.risk_level): \(r.recommendation)")
					if r.escalate_719 { Text("Call 719 now").foregroundStyle(.red) }
				}
			}
		}
	}
}

struct WrapChips: View {
	let act: (Double) async -> Void
	var temps: [Double] = [37.5, 38.3, 38.9]

	var body: some View {
		ScrollView(.horizontal) {
			HStack {
				ForEach(temps, id: \.self) { t in
					Button("\(t, specifier: "%.1f") °C") { Task { await act(t) } }
						.buttonStyle(.bordered)
				}
			}
		}
	}
}