import SwiftUI

@main
struct AfyaYanguApp: App {
	@StateObject private var store = AppState()

	var body: some Scene {
		WindowGroup {
			ContentView().environmentObject(store)
		}
	}
}