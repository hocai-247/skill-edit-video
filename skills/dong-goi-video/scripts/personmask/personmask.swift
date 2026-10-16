// Person segmentation for every frame of a video using Apple Vision (built into macOS 12+, no model download).
// Writes 8-bit masks (255 = person) as raw frames to stdout; prints "size WxH" then "frames N" to stderr.
// Usage: personmask <video> [accurate|balanced|fast]
import Foundation
import AVFoundation
import Vision
import CoreVideo

let args = CommandLine.arguments
guard args.count >= 2 else { fputs("usage: personmask <video> [accurate|balanced|fast]\n", stderr); exit(2) }
let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
let quality = args.count > 2 ? args[2] : "accurate"

let sem = DispatchSemaphore(value: 0)
var track: AVAssetTrack?
Task { track = try? await asset.loadTracks(withMediaType: .video).first; sem.signal() }
sem.wait()
guard let vt = track else { fputs("no video track\n", stderr); exit(1) }

let reader = try! AVAssetReader(asset: asset)
let output = AVAssetReaderTrackOutput(track: vt, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
output.alwaysCopiesSampleData = false
reader.add(output)
reader.startReading()

let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = quality == "fast" ? .fast : (quality == "balanced" ? .balanced : .accurate)
request.outputPixelFormat = kCVPixelFormatType_OneComponent8

let out = FileHandle.standardOutput
var n = 0
var announced = false
var last = Data()
while let sample = output.copyNextSampleBuffer() {
    guard let pixels = CMSampleBufferGetImageBuffer(sample) else { continue }
    let handler = VNImageRequestHandler(cvPixelBuffer: pixels, options: [:])
    var frame = last
    if (try? handler.perform([request])) != nil, let mask = request.results?.first?.pixelBuffer {
        CVPixelBufferLockBaseAddress(mask, .readOnly)
        let w = CVPixelBufferGetWidth(mask), h = CVPixelBufferGetHeight(mask), bpr = CVPixelBufferGetBytesPerRow(mask)
        if !announced { fputs("size \(w)x\(h)\n", stderr); announced = true }
        let base = CVPixelBufferGetBaseAddress(mask)!.assumingMemoryBound(to: UInt8.self)
        frame = Data(capacity: w * h)
        for y in 0..<h { frame.append(base + y * bpr, count: w) }
        CVPixelBufferUnlockBaseAddress(mask, .readOnly)
        last = frame
    } else {
        fputs("warning: no mask for frame \(n), repeating previous\n", stderr)   // keeps the frame count exact
    }
    if !frame.isEmpty { out.write(frame) }
    n += 1
}
fputs("frames \(n)\n", stderr)
