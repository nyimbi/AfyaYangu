import SwiftUI
import PhotosUI

// SENS-004 photo + textual evidence submission.

struct MultipartBody {
	static func build(kind: String, subjectRef: String, county: String, note: String, mime: String, data: Data, boundary: String) -> Data {
		var b = Data()
		func field(_ name: String, _ value: String) {
			b.append(string: "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n")
		}
		field("kind", kind)
		field("subject_ref", subjectRef)
		field("county", county)
		field("note", note)
		b.append(string: "--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"evidence.\(mime.contains("png") ? "png" : "jpg")\"\r\nContent-Type: \(mime)\r\n\r\n")
		b.append(data)
		b.append(string: "\r\n--\(boundary)--\r\n")
		return b
	}

	static func upload(client: BackendClient, kind: String, subjectRef: String, county: String, note: String, mime: String, data: Data) async throws -> Data {
		let boundary = "afya-\(UUID().uuidString)"
		var req = URLRequest(url: client.base.appendingPathComponent("evidence"))
		req.httpMethod = "POST"
		req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "content-type")
		req.httpBody = build(kind: kind, subjectRef: subjectRef, county: county, note: note, mime: mime, data: data, boundary: boundary)
		return try await client.send(req: req)
	}
}

extension Data {
	mutating func append(string: String) { append(contentsOf: string.utf8) }
}

struct EvidenceUploadView: View {
	@State private var imageData: Data?
	@State private var note = ""
	@State private var kind = "rash"
	@State private var status = ""
	@State private var pickerItem: PhotosPickerItem?

	var body: some View {
		Form {
			Section("Show a nurse your concern") {
				TextField("What did you observe?", text: $note)
				Picker("Type", selection: $kind) {
					Text("Rash").tag("rash")
					Text("Red eyes").tag("red_eye")
					Text("Pallor").tag("pallor")
					Text("Scene photo").tag("scene_photo")
				}
				PhotosPicker(selection: $pickerItem, matching: .images) {
					Label(imageData == nil ? "Attach photo" : "Photo attached ✓", systemImage: "photo.on.rectangle")
				}
				.onChange(of: pickerItem) { _, item in
					guard let item else { return }
					Task {
						if let data = try? await item.loadTransferable(type: Data.self) { imageData = data }
					}
				}
				Button("Send for review") {
					guard let data = imageData else { status = "Attach a photo first"; return }
					Task {
						do {
							let out = try await MultipartBody.upload(
								client: AppState.sharedClient, kind: kind, subjectRef: "U1", county: "Nairobi",
								note: note, mime: "image/jpeg", data: data)
							let obj = (try? JSONSerialization.jsonObject(with: out)) as? [String: Any]
							status = obj?["deduped"] != nil
								? "Stored: \(obj?["submission_id"] ?? "") (deduped: \(obj?["deduped"] ?? false))"
								: "Stored ✓"
						} catch {
							status = "Rejected: \(error.localizedDescription)"
						}
					}
				}
				if !status.isEmpty { Text(status).font(.footnote) }
			}
		}
		.navigationTitle("Evidence")
	}
}