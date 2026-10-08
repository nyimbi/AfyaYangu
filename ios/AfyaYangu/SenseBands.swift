import Foundation

/// Client-side band engines — same contracts as src/afya/sensors/service.py and android SenseBands.kt.
enum SenseBands {
	static func respiration(_ rate: Double) -> String { (rate < 12 || rate > 25) ? "alert" : "normal" }
	static func cough(_ perHour: Double) -> String { perHour >= 30 ? "alert" : (perHour >= 15 ? "watch" : "normal") }
	static func ppg(_ hr: Double) -> String { (hr < 45 || hr > 120) ? "alert" : (hr < 55 || hr > 100 ? "watch" : "normal") }
	static func fall(_ peakG: Double) -> String { peakG > 4.0 ? "alert" : "normal" }
}