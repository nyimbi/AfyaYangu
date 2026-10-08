import SwiftUI
import CoreLocation
import UIKit

// FND + OSM: GPS-driven nearest pharmacy/clinic/hospital/school + turn-by-turn handoff to Apple/Google Maps.

@MainActor
final class Locator: NSObject, ObservableObject, CLLocationManagerDelegate {
	@Published var coordinate: CLLocationCoordinate2D?
	@Published var denied = false

	private let manager = CLLocationManager()

	override init() {
		super.init()
		manager.delegate = self
		manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
	}

	func start() {
		switch manager.authorizationStatus {
		case .notDetermined:
			manager.requestWhenInUseAuthorization()
		case .denied, .restricted:
			denied = true
		default:
			manager.requestLocation()
		}
	}

	func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
		switch manager.authorizationStatus {
		case .denied, .restricted:
			denied = true
		case .authorizedWhenInUse, .authorizedAlways:
			denied = false
			manager.requestLocation()
		default:
			break
		}
	}

	func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
		coordinate = locations.first?.coordinate
	}

	func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
		// Spec 16.1: never block the UI — manual coordinates remain available.
		denied = true
	}
}

struct PlacesView: View {
	@StateObject private var locator = Locator()
	@State private var kind = "pharmacy"
	@State private var results: [PlaceNearestDTO] = []
	@State private var status = "OpenStreetMap-backed: pharmacies, hospitals, clinics, schools, water points."
	@State private var manualLat = ""
	@State private var manualLon = ""

	private let kinds = ["pharmacy", "hospital", "clinic", "school", "water_point"]

	var body: some View {
		Form {
			Section("Your location") {
				if let c = locator.coordinate {
					Text(String(format: "GPS: %.4f, %.4f", c.latitude, c.longitude)).font(.footnote)
					Text("Import OSM places around you")
					Button("Import OpenStreetMap places here") {
						Task {
							try? await AppState.sharedClient.importOsmPlaces(lat: c.latitude, lon: c.longitude)
							status = "OSM imported ✓"
						}
					}
				}
				if locator.coordinate == nil {
					TextField("Manual latitude", text: $manualLat)
						.keyboardType(.numbersAndPunctuation)
					TextField("Manual longitude", text: $manualLon)
						.keyboardType(.numbersAndPunctuation)
				}
				Picker("Place type", selection: $kind) {
					ForEach(kinds, id: \.self) { Text($0.capitalized) }
				}
				.pickerStyle(.segmented)
				Button("Find nearest \(kind)") { Task { await fetch() } }
				if locator.coordinate == nil && manualLat.isEmpty { Text(locator.denied ? "Location denied — enter manual coordinates or allow access." : "Waiting for GPS fix…").font(.caption) }
			}
			Section(status.isEmpty ? "" : status) {
				if status.isEmpty { EmptyView() }
				Text(status).font(.caption).foregroundStyle(.secondary)
			}
			Section("Nearest \(kind)") {
				if results.isEmpty { Text("No results yet.").foregroundStyle(.secondary) }
				ForEach(results) { r in
					VStack(alignment: .leading, spacing: 4) {
						Text(r.place.name).font(.headline)
						Text("\(r.place.kind) · \(String(format: "%.1f", r.km)) km · ~\(r.directions.walk_minutes) min walk · bearing \(r.directions.bearing_deg)°").font(.caption)
						Text(r.directions.guidance).font(.caption).foregroundStyle(.secondary)
						HStack {
							Button("Navigate (Apple Maps)") {
								UIApplication.shared.open(URL(string: r.directions.apple_maps_url)!)
							}
							Button("Google Maps") {
								UIApplication.shared.open((URL(string: r.directions.google_maps_url))!)
							}
						}.buttonStyle(.bordered).font(.caption)
					}
				}
			}
		}
		.navigationTitle("Maps")
		.task { locator.start() }
	}

	private func fetch() async {
		guard let lat = locatorLat(), let lon = locatorLon() else {
			status = "No location yet (GPS off/denied): enter manual coordinates."
			return
		}
		do {
			results = try await AppState.sharedClient.nearestPlaces(lat: lat, lon: lon, kind: kind)
			if results.isEmpty { status = "None found — import OSM places for this area first." }
		} catch {
			results = []
			status = "Offline: \(error.localizedDescription)"
		}
	}

	private func locatorLat() -> Double? {
		if let c = locator.coordinate { return c.latitude }
		return Double(manualLat)
	}

	private func locatorLon() -> Double? {
		if let c = locator.coordinate { return c.longitude }
		return Double(manualLon)
	}
}