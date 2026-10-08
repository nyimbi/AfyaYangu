import SwiftUI

// Tier-1/2 feature surfaces: FND-001 finder, REC-001 wallet, TRI-002 diary, CHAN-005 CHW console.

extension AppState {
	static let sharedState = AppState()
	static var sharedClient: BackendClient { sharedState.client }

	func assess(symptoms: [String], tempC: Double, contact: Bool) async -> TriageResultDTO? {
		try? await client.triagePreliminary(symptoms: symptoms, temperatureC: tempC, ebolaContact: contact)
	}
}

struct FinderView: View {
	@State private var results: [NearestResponseDTO] = []

	var body: some View {
		List {
			Section("FND-001 Facility Finder") {
				Button("Find treatment units near Nairobi") {
					Task {
						let primary = (try? await AppState.sharedClient.nearest(lat: -1.29, lon: 36.82, kind: "treatment_unit")) ?? []
						let fallback = primary.isEmpty ? ((try? await AppState.sharedClient.nearest(lat: -1.29, lon: 36.82, kind: "ed")) ?? []) : []
						results = primary + fallback
					}
				}
				ForEach(results) { r in
					VStack(alignment: .leading) {
						Text("\(r.facility.name) · \(r.facility.county)")
						Text("\(r.km, specifier: "%.1f") km · \(r.facility.kind)").font(.caption).foregroundStyle(.secondary)
					}
				}
			}
		}
		.navigationTitle("Finder")
	}
}

struct WalletView: View {
	@State private var wallet: WalletDTO?
	@State private var ref = "GUARD1"

	var body: some View {
		Form {
			TextField("Guardian ref", text: $ref)
			Button("Load REC-001 Family Health Wallet") {
				Task { self.wallet = try? await AppState.sharedClient.wallet(guardianRef: ref) }
			}
			if let w = wallet {
				Section("Members") {
					ForEach(w.members) { m in
						VStack(alignment: .leading) {
							Text(m.member_ref).font(.headline)
							Text("DOB \(m.dob_iso) \(m.is_minor ? "· minor" : "")").font(.caption2)
						}
					}
				}
				Section("Immunisation gaps") {
					ForEach(w.gaps.keys.sorted(), id: \.self) { k in
						Text(k + ": " + (w.gaps[k] ?? []).joined(separator: ", "))
					}
				}
			}
		}
		.navigationTitle("Wallet")
	}
}

struct DiaryView: View {
	@State private var entries: [DiaryDTO] = []

	var body: some View {
		List {
			Section("TRI-002 Symptom Diary (21-day observation)") {
				if entries.isEmpty { Text("No synced entries yet.").foregroundStyle(.secondary) }
				ForEach(entries) { e in
					HStack {
						Text("Day \(e.day)").bold()
						Text(e.symptoms.joined(separator: ", ")).font(.caption)
						Spacer()
						Image(systemName: e.synced ? "checkmark.circle.fill" : "icloud.slash")
					}
				}
			}
		}
		.navigationTitle("Diary")
		.task {
			entries = (try? await AppState.sharedClient.diary(subjectRef: "U1")) ?? []
		}
	}
}

struct ChwView: View {
	@State private var tasks: [ChwTaskDTO] = []

	var body: some View {
		List {
			Section("CHAN-005 CHW open tasks") {
				if tasks.isEmpty { Text("Nothing open for CHW1.").foregroundStyle(.secondary) }
				ForEach(tasks) { t in
					HStack {
						Text("\(t.task_id) · \(t.kind)").bold()
						Text(t.community).font(.caption)
						Spacer()
						Button("Done") {
							Task {
								try? await AppState.sharedClient.completeTask(t.task_id)
								tasks = (try? await AppState.sharedClient.chwTasks("CHW1")) ?? []
							}
						}
					}
				}
			}
		}
		.navigationTitle("CHW")
		.task {
			tasks = (try? await AppState.sharedClient.chwTasks("CHW1")) ?? []
		}
	}
}

struct HomeScreen: View {
	@ObservedObject var state: AppState

	var body: some View {
		List {
			Section("Connection") {
				Label(state.offline ? "Offline — cached state shown" : "Connected", systemImage: state.offline ? "wifi.slash" : "wifi")
				if let h = state.health { Text("backend \(h.version) · tier4 \(h.tier4 ? "active" : "dormant")") }
			}
			Section("TRI-001 Triage") { TriageInline() }
			Section("Active features (\(state.features.count))") {
				ForEach(state.features) { f in
					Label("\(f.id) \(f.name)", systemImage: "checkmark.seal")
				}
			}
		}
		.navigationTitle("Afya Yangu")
		.task { await state.refresh() }
		.refreshable { await state.refresh() }
	}
}

struct TriageInline: View {
	@ObservedObject var state: AppState = AppState.sharedState
	@State private var result: TriageResultDTO?

	var body: some View {
		WrapChips { temp in
			result = await state.assess(symptoms: ["fever", "headache"], tempC: temp, contact: false)
		}
		if let r = result {
			Text("\(r.risk_level): \(r.recommendation)").font(.footnote)
			if r.escalate_719 { Text("Call 719 now").foregroundStyle(.red) }
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

struct FeatureTabView: View {
	@ObservedObject var state: AppState = AppState.sharedState

	var body: some View {
		TabView {
			NavigationStack { HomeScreen(state: state) }.tabItem { Label("Status", systemImage: "wifi") }
			NavigationStack { FinderView() }.tabItem { Label("Finder", systemImage: "mappin.and.ellipse") }
			NavigationStack { WalletView() }.tabItem { Label("Wallet", systemImage: "person.3") }
			NavigationStack { DiaryView() }.tabItem { Label("Diary", systemImage: "book") }
			NavigationStack { ChwView() }.tabItem { Label("CHW", systemImage: "figure.walk") }
		}
	}
}