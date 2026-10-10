import SwiftUI

// Primary surfaces — human language only; registry IDs never appear in UI.

extension AppState {
	static let sharedState = AppState()
	static var sharedClient: BackendClient { sharedState.client }

	func assess(symptoms: [String], tempC: Double, contact: Bool) async -> TriageResultDTO? {
		try? await client.triagePreliminary(symptoms: symptoms, temperatureC: tempC, ebolaContact: contact)
	}
}

struct WrapChips: View {
	let act: (Double) async -> Void
	var temps: [Double] = [37.5, 38.3, 38.9]

	var body: some View {
		ScrollView(.horizontal, showsIndicators: false) {
			HStack {
				ForEach(temps, id: \.self) { t in
					Button("\(t, specifier: "%.1f") °C") { Task { await act(t) } }
						.buttonStyle(.bordered)
				}
			}
		}
	}
}

struct TriageInline: View {
	@State private var result: TriageResultDTO?
	@State private var contact = false

	var body: some View {
		VStack(alignment: .leading, spacing: 10) {
			Toggle("Contact with an Ebola patient or affected area?", isOn: $contact)
			WrapChips { temp in
				result = await AppState.sharedState.assess(symptoms: ["fever", "headache"], tempC: temp, contact: contact)
			}
			if let r = result {
				Text(r.recommendation).font(.footnote)
				if r.escalate_719 {
					Link("Call 719 now (free, 24/7)", destination: URL(string: "tel:719")!)
						.foregroundStyle(.red)
				}
			}
		}
	}
}

struct HomeScreen: View {
	@ObservedObject var state: AppState

	var body: some View {
		List {
			Section {
				Label(state.offline ? "Offline — showing your saved info" : "Connected", systemImage: state.offline ? "wifi.slash" : "wifi")
				if let h = state.health {
					Text(h.tier4 ? "Outbreak services active" : "Everyday care ready · outbreak standby").font(.footnote).foregroundStyle(.secondary)
				}
			}
			Section("Check how you feel") { TriageInline() }
			Section {
				ForEach(state.friendly) { fr in
					VStack(alignment: .leading, spacing: 3) {
						Text(fr.title).font(.subheadline)
						Text(fr.description).font(.caption).foregroundStyle(.secondary)
					}
				}
			}
		}
		.navigationTitle("Afya Yangu")
		.task { await state.refresh() }
		.refreshable { await state.refresh() }
	}
}

struct FinderView: View {
	@State private var results: [NearestResponseDTO] = []
	@State private var kind = "ed"

	private let kindOptions: [(String, String)] = [
		("ed", "A&E / emergency"), ("treatment_unit", "Treatment centre"), ("testing_site", "Testing site"),
		("pharmacy", "Pharmacy"), ("vaccination_point", "Vaccination"),
	]

	var body: some View {
		List {
			Section("Find care near me") {
				Picker("Type", selection: $kind) {
					ForEach(kindOptions, id: \.0) { Text($0.1).tag($0.0) }
				}
				Button("Search Nairobi CBD") {
					Task {
						results = (try? await AppState.sharedClient.nearest(lat: -1.2921, lon: 36.8219, kind: kind)) ?? []
					}
				}
			}
			Section("Results") {
				if results.isEmpty { Text("No results yet.").foregroundStyle(.secondary) }
				ForEach(results) { r in
					VStack(alignment: .leading) {
						Text(r.facility.name).font(.headline)
						Text("\(String(format: "%.1f", r.km)) km · \(r.facility.kind.humanName)\(r.facility.ed_status.map { " · \($0)" } ?? "")").font(.caption)
					}
				}
			}
		}
		.navigationTitle("Find Care")
	}
}

extension String {
	var humanName: String {
		switch self {
		case "ed": return "A&E"
		case "pharmacy": return "pharmacy"
		case "treatment_unit": return "treatment centre"
		default: return self
		}
	}
}

struct WalletView: View {
	@State private var wallet: WalletDTO?
	@State private var ref = "GUARD1"

	var body: some View {
		Form {
			Section("Whose family?") {
				TextField("Guardian name or ref", text: $ref)
				Button("Open family wallet") {
					Task { wallet = try? await AppState.sharedClient.wallet(guardianRef: ref) }
				}
			}
			if let w = wallet {
				Section("In the wallet") {
					ForEach(w.members) { m in
						VStack(alignment: .leading, spacing: 3) {
							Text(m.member_ref).font(.headline)
							Text("Born \(m.dob_iso)\(m.is_minor ? " · child" : "")").font(.caption).foregroundStyle(.secondary)
						}
					}
				}
				Section("Vaccinations to catch up on") {
					ForEach(w.gaps.keys.sorted(), id: \.self) { k in
						Text(k + ": " + (w.gaps[k] ?? []).joined(separator: ", ")).font(.footnote)
					}
				}
			}
		}
		.navigationTitle("Family")
	}
}

struct DiaryView: View {
	@State private var entries: [DiaryDTO] = []

	var body: some View {
		List {
			Section("My 21-day diary") {
				if entries.isEmpty {
					Text("Nothing logged yet.").foregroundStyle(.secondary)
					Text("If you were exposed to illness, log how you feel each day for 21 days.").font(.caption).foregroundStyle(.secondary)
				}
				ForEach(entries) { e in
					HStack {
						Text("Day \(e.day)").bold()
						Text(e.symptoms.joined(separator: ", ")).font(.caption)
						Spacer()
						Image(systemName: e.synced ? "checkmark.circle.fill" : "icloud.slash").foregroundStyle(e.synced ? .green : .orange)
					}
				}
			}
		}
		.navigationTitle("My Health")
		.task { entries = (try? await AppState.sharedClient.diary(subjectRef: "U1")) ?? [] }
	}
}

struct ChwView: View {
	@State private var tasks: [ChwTaskDTO] = []

	var body: some View {
		List {
			Section("Open work") {
				if tasks.isEmpty {
					Text("All caught up.").foregroundStyle(.secondary)
				}
				ForEach(tasks) { t in
					HStack {
						VStack(alignment: .leading, spacing: 3) {
							Text(t.kind.humanTask).font(.headline)
							Text(t.community).font(.caption).foregroundStyle(.secondary)
						}
						Spacer()
						Button("Done") {
							Task {
								try? await AppState.sharedClient.completeTask(t.task_id)
								tasks = (try? await AppState.sharedClient.chwTasks("CHW1")) ?? []
							}
						}
						.buttonStyle(.bordered)
					}
				}
			}
		}
		.navigationTitle("Community")
		.task { tasks = (try? await AppState.sharedClient.chwTasks("CHW1")) ?? [] }
	}
}

extension String {
	var humanTask: String {
		switch self {
		case "followup": return "Follow-up visit"
		case "referral": return "Refer someone to care"
		case "sensitisation": return "Community sensitisation"
		default: return self
		}
	}
}

struct FeatureTabView: View {
	@ObservedObject var state: AppState = AppState.sharedState
	@State private var tab: Int = Int(UserDefaults.standard.integer(forKey: "startTab"))

	var body: some View {
		TabView(selection: $tab) {
			NavigationStack { HomeScreen(state: state) }.tabItem { Label("Home", systemImage: "house") }.tag(0)
			NavigationStack { FinderView() }.tabItem { Label("Find Care", systemImage: "cross.case") }.tag(1)
			NavigationStack { WalletView() }.tabItem { Label("Family", systemImage: "person.3") }.tag(2)
			NavigationStack { DiaryView() }.tabItem { Label("My Health", systemImage: "book.closed") }.tag(3)
			NavigationStack { ChwView() }.tabItem { Label("Community", systemImage: "figure.walk") }.tag(4)
			NavigationStack { EvidenceUploadView() }.tabItem { Label("Photos", systemImage: "camera") }.tag(5)
			NavigationStack { PlacesView() }.tabItem { Label("Maps", systemImage: "map") }.tag(6)
		}
	}
}