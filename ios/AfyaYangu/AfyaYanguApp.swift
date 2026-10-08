import SwiftUI

@main
struct AfyaYanguApp: App {
	@StateObject private var store = AppState()

	var body: some Scene {
		WindowGroup {
			FeatureTabView().environmentObject(store)
		}
	}
}