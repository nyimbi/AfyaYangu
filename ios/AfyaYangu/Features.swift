import SwiftUI
import PhotosUI

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
		.task {
			let mine = (try? await AppState.sharedClient.subjectRef()) ?? "U1"
			entries = (try? await AppState.sharedClient.diary(subjectRef: mine)) ?? []
		}
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

struct ActionsView: View {
	@State private var actions: [MobileActionDTO] = []
	@State private var loadError = false
	@State private var queued = 0

	private var groups: [String] {
		var order: [String] = []
		for a in actions where !order.contains(a.group) { order.append(a.group) }
		return order
	}

	var body: some View {
		List {
			if queued > 0 {
				Section {
					Label("\(queued) change(s) saved on this phone, waiting to send", systemImage: "tray.and.arrow.up")
						.font(.footnote).foregroundStyle(.secondary)
				}
			}
			if actions.isEmpty {
				Text(loadError ? "Could not load services. Check your connection and pull to refresh." : "Loading services…")
					.foregroundStyle(.secondary)
			}
			ForEach(groups, id: \.self) { group in
				Section(group) {
					ForEach(actions.filter { $0.group == group }) { action in
						NavigationLink(action.title) { ActionFormView(action: action) }
					}
				}
			}
		}
		.navigationTitle("All Services")
		.task { await load() }
		.refreshable { await load() }
	}

	private func load() async {
		do {
			actions = try await AppState.sharedClient.actions()
			loadError = false
		} catch {
			loadError = true
		}
		// §16.1: a network that just came back is the moment to send what was saved.
		_ = await AppState.sharedClient.flushQueue()
		queued = await AppState.sharedClient.queuedCount()
	}
}

// One generic form per catalogue action — built entirely from the fields the server sends.
struct ActionFormView: View {
	let action: MobileActionDTO
	@State private var values: [String: String] = [:]
	@State private var fileData: Data?
	@State private var pickerItem: PhotosPickerItem?
	@State private var result = ""
	@State private var failed = false
	@State private var busy = false

	private var hasFile: Bool { action.fields.contains { $0.type == "file" } }

	var body: some View {
		Form {
			Section {
				// A client-supplied field is the device's own subject, filled by the client. It is not
				// drawn: the catalogue marks it because the route binds it to the token, so a field
				// asking "who is this for?" would offer a control the server refuses by construction.
				ForEach(action.fields.filter { $0.client_supplied != true }) { field in
					fieldRow(field)
				}
			}
			Section {
				Button(busy ? "Working…" : action.method == "GET" ? "Run" : "Submit") { run() }
					.disabled(busy)
			}
			if !result.isEmpty {
				Section("Result") {
					Text(result).font(.system(.footnote, design: .monospaced)).foregroundStyle(failed ? .red : .primary)
				}
			}
		}
		.navigationTitle(action.title)
		.onChange(of: pickerItem) { _, item in
			guard let item else { return }
			Task { fileData = try? await item.loadTransferable(type: Data.self) }
		}
	}

	@ViewBuilder
	private func fieldRow(_ field: MobileFieldDTO) -> some View {
		switch field.type {
		case "bool":
			Toggle(field.label, isOn: Binding(
				get: { values[field.name] == "true" },
				set: { values[field.name] = $0 ? "true" : "false" }))
		case "select":
			Picker(field.label, selection: Binding(
				get: { values[field.name] ?? "" },
				set: { values[field.name] = $0 })) {
				Text("—").tag("")
				ForEach(field.options ?? [], id: \.self) { Text($0).tag($0) }
			}
		case "textarea":
			VStack(alignment: .leading) {
				Text(field.label).font(.caption).foregroundStyle(.secondary)
				TextField(field.placeholder ?? "", text: Binding(
					get: { values[field.name] ?? "" },
					set: { values[field.name] = $0 }), axis: .vertical).lineLimit(3...6)
			}
		case "file":
			PhotosPicker(selection: $pickerItem, matching: .images) {
				Label(fileData == nil ? field.label : "\(field.label) ✓", systemImage: "photo.on.rectangle")
			}
		default:
			TextField(field.placeholder.map { "\(field.label) (\($0))" } ?? field.label, text: Binding(
				get: { values[field.name] ?? "" },
				set: { values[field.name] = $0 }))
				.keyboardType(field.type == "int" ? .numberPad : field.type == "decimal" ? .decimalPad : .default)
		}
	}

	private func run() {
		let missing = action.fields.filter { $0.required && $0.client_supplied != true && $0.type != "file" && (values[$0.name] ?? "").isEmpty }
		guard missing.isEmpty else {
			failed = true
			result = "Please fill in: " + missing.map(\.label).joined(separator: ", ")
			return
		}
		busy = true
		result = ""
		failed = false
		Task {
			do {
				let data = try await AppState.sharedClient.submitOrQueue(action, values: values, file: fileData)
				result = Self.pretty(data)
			} catch {
				failed = true
				result = "Failed: \(error.localizedDescription)"
			}
			busy = false
		}
	}

	private static func pretty(_ data: Data) -> String {
		guard let obj = try? JSONSerialization.jsonObject(with: data),
			let out = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys])
		else { return String(data: data, encoding: .utf8) ?? "" }
		return String(decoding: out, as: UTF8.self)
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
			NavigationStack { ActionsView() }.tabItem { Label("All Services", systemImage: "square.grid.2x2") }.tag(7)
		}
	}
}