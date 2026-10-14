import SwiftUI
import PhotosUI

// SENS-004 photo + textual evidence submission.

struct MultipartBody {
	static func build(kind: String, subjectRef: String, county: String, note: String, consent: Bool, mime: String, data: Data, boundary: String) -> Data {
		var b = Data()
		func field(_ name: String, _ value: String) {
			b.append(string: "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n")
		}
		field("kind", kind)
		field("subject_ref", subjectRef)
		field("county", county)
		field("note", note)
		// §SEC-002's per-item consent. Sent as "true" only when the box is ticked; the server
		// refuses the photo without it, so a client that omitted this would show a control that
		// always fails.
		field("consent", consent ? "true" : "false")
		b.append(string: "--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"evidence.\(mime.contains("png") ? "png" : "jpg")\"\r\nContent-Type: \(mime)\r\n\r\n")
		b.append(data)
		b.append(string: "\r\n--\(boundary)--\r\n")
		return b
	}

	static func upload(client: BackendClient, kind: String, subjectRef: String, county: String, note: String, consent: Bool, mime: String, data: Data) async throws -> Data {
		let boundary = "afya-\(UUID().uuidString)"
		var req = URLRequest(url: client.base.appendingPathComponent("evidence"))
		req.httpMethod = "POST"
		req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "content-type")
		req.httpBody = build(kind: kind, subjectRef: subjectRef, county: county, note: note, consent: consent, mime: mime, data: data, boundary: boundary)
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
	// §SEC-002's per-item consent. Off by default and never remembered between submissions: a
	// consent that persisted would be the install-time grant the section explicitly does not ask for.
	@State private var sharePhoto = false
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
				Toggle("I agree to share this photo", isOn: $sharePhoto)
				Button("Send for review") {
					guard let data = imageData else { status = "Attach a photo first"; return }
					guard sharePhoto else { status = "Tick the box to agree to share this photo"; return }
					Task {
						do {
							let mine = (try? await AppState.sharedClient.subjectRef()) ?? "U1"
							let out = try await MultipartBody.upload(
								client: AppState.sharedClient, kind: kind, subjectRef: mine, county: "Nairobi",
								note: note, consent: sharePhoto, mime: "image/jpeg", data: data)
							let obj = (try? JSONSerialization.jsonObject(with: out)) as? [String: Any]
							status = obj?["deduped"] != nil
								? "Stored: \(obj?["submission_id"] ?? "") (deduped: \(obj?["deduped"] ?? false))"
								: "Stored ✓"
							sharePhoto = false
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