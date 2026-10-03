// vanalyze: batch image analysis with Apple Vision (macOS 13+; aesthetics needs macOS 15+).
// Reads image paths from stdin (one per line) and writes one JSON object per line to stdout:
// OCR lines (text, confidence, bbox), barcode/QR payloads, scene labels, face count and the
// largest face area, and the aesthetics score. Languages come from VANALYZE_LANGS (comma list).
import Foundation
import Vision

struct Line: Codable { let t: String; let c: Float; let x: Float; let y: Float; let w: Float; let h: Float }
struct Result: Codable {
    let path: String
    var lines: [Line] = []
    var codes: [String] = []
    var labels: [String: Float] = [:]
    var faces: Int = 0
    var maxFace: Float = 0
    var aesthetic: Float? = nil
    var utility: Bool? = nil
    var err: String? = nil
}

let langs = (ProcessInfo.processInfo.environment["VANALYZE_LANGS"] ?? "en-US")
    .split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
var paths: [String] = []
while let l = readLine(strippingNewline: true) { if !l.isEmpty { paths.append(l) } }
let out = FileHandle.standardOutput
let lock = NSLock()
let enc = JSONEncoder()

func analyze(_ path: String) -> Result {
    var r = Result(path: path)
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
    let text = VNRecognizeTextRequest()
    text.recognitionLevel = .accurate
    text.usesLanguageCorrection = true
    text.recognitionLanguages = langs
    let codes = VNDetectBarcodesRequest()
    let classify = VNClassifyImageRequest()
    let faces = VNDetectFaceRectanglesRequest()
    var reqs: [VNRequest] = [text, codes, classify, faces]
    var aes: VNRequest? = nil
    if #available(macOS 15.0, *) { let a = VNCalculateImageAestheticsScoresRequest(); reqs.append(a); aes = a }
    do { try handler.perform(reqs) } catch { r.err = "\(error)"; return r }
    for o in text.results ?? [] {
        guard let cand = o.topCandidates(1).first, cand.confidence >= 0.3 else { continue }
        let b = o.boundingBox
        r.lines.append(Line(t: cand.string, c: cand.confidence, x: Float(b.minX), y: Float(b.minY),
                            w: Float(b.width), h: Float(b.height)))
    }
    r.codes = (codes.results ?? []).compactMap { $0.payloadStringValue }
    for o in (classify.results ?? []).prefix(40) where o.confidence >= 0.15 { r.labels[o.identifier] = o.confidence }
    let f = faces.results ?? []
    r.faces = f.count
    r.maxFace = f.map { Float($0.boundingBox.width * $0.boundingBox.height) }.max() ?? 0
    if #available(macOS 15.0, *), let a = aes as? VNCalculateImageAestheticsScoresRequest, let s = a.results?.first {
        r.aesthetic = s.overallScore
        r.utility = s.isUtility
    }
    return r
}

DispatchQueue.concurrentPerform(iterations: paths.count) { i in
    let res = analyze(paths[i])
    if let d = try? enc.encode(res) {
        lock.lock(); out.write(d); out.write("\n".data(using: .utf8)!); lock.unlock()
    }
}
