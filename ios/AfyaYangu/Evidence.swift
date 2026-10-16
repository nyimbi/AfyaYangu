import SwiftUI
import PhotosUI
import CryptoKit

// SENS-004 photo + textual evidence submission.

/// §16.4's resumable upload. A phone camera produces 4–8 MB files, and the single-shot route means a
/// dropped connection at 90% costs the whole upload again on a metered connection — which is the cost
/// the section's own argument is about. Chunks are addressed by their *offset in the whole*, not by an
/// index, so a client that restarts and re-slices the file still lands its bytes in the right place.
///
/// `nextOffset` is read back from every answer rather than computed here: the server is the authority
/// on what it holds, and a retry after an unacknowledged chunk comes back with the position it already
/// had. That is what makes the loop safe to re-enter.
struct ResumableUpload {
	static let chunkBytes = 512 * 1024

	static func sha256Hex(_ data: Data) -> String {
		SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
	}

	/// base64url, unpadded — the alphabet the JSON body carries, since `+` and `/` would need escaping.
	static func b64url(_ data: Data) -> String {
		data.base64EncodedString()
			.replacingOccurrences(of: "+", with: "-")
			.replacingOccurrences(of: "/", with: "_")
			.replacingOccurrences(of: "=", with: "")
	}

	private static func json(_ client: BackendClient, _ path: String, _ body: [String: Any]) async throws -> [String: Any] {
		var req = URLRequest(url: client.base.appendingPathComponent(path))
		req.httpMethod = "POST"
		req.setValue("application/json", forHTTPHeaderField: "content-type")
		req.httpBody = try JSONSerialization.data(withJSONObject: body)
		let out = try await client.send(req: req)
		return (try? JSONSerialization.jsonObject(with: out)) as? [String: Any] ?? [:]
	}

	static func upload(client: BackendClient, kind: String, subjectRef: String, county: String,
	                   note: String, consent: Bool, mime: String, data: Data) async throws -> [String: Any] {
		// The whole file's hash is the client's claim about the picture it holds. A server-side hash of
		// the reassembled chunks would be checking its own reassembly rather than the photo chosen.
		var opened = try await json(client, "evidence/upload", [
			"kind": kind, "subject_ref": subjectRef, "county": county, "note": note,
			"consent": consent, "declared_bytes": data.count,
			"image_sha256": sha256Hex(data), "mime": mime, "chunk_bytes": chunkBytes,
		])
		guard let sessionId = opened["session_id"] as? String else { throw ApiError.transport(500) }
		var offset = opened["next_offset"] as? Int ?? 0
		while offset < data.count {
			let end = min(offset + chunkBytes, data.count)
			let chunk = data.subdata(in: offset..<end)
			opened = try await json(client, "evidence/upload/\(sessionId)/chunk", [
				"offset": offset, "chunk_sha256": sha256Hex(chunk), "data": b64url(chunk),
			])
			let next = opened["next_offset"] as? Int ?? offset
			// A server that answers with the same offset twice would spin here forever; the loop's
			// progress is the server's claim, so it is asserted rather than assumed.
			guard next > offset else { throw ApiError.transport(500) }
			offset = next
		}
		return try await json(client, "evidence/upload/\(sessionId)/finish", [:])
	}
}

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
							// A photo past the chunk size goes up resumably; a small one takes the
							// single-shot route, where a retry costs one request rather than a session.
							let obj: [String: Any]
							if data.count > ResumableUpload.chunkBytes {
								obj = try await ResumableUpload.upload(
									client: AppState.sharedClient, kind: kind, subjectRef: mine, county: "Nairobi",
									note: note, consent: sharePhoto, mime: "image/jpeg", data: data)
							} else {
								let out = try await MultipartBody.upload(
									client: AppState.sharedClient, kind: kind, subjectRef: mine, county: "Nairobi",
									note: note, consent: sharePhoto, mime: "image/jpeg", data: data)
								obj = (try? JSONSerialization.jsonObject(with: out)) as? [String: Any] ?? [:]
							}
							status = obj["deduped"] != nil
								? "Stored: \(obj["submission_id"] ?? "") (deduped: \(obj["deduped"] ?? false))"
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