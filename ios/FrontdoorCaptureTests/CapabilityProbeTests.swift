import AVFoundation
import XCTest
@testable import FrontdoorCapture

/// The probe's resume discipline (#150).
///
/// A checked continuation may be resumed exactly once; twice is a crash. Three things race to do
/// it — the photo delegate, the 15-second timeout, and cancellation when the operator taps Done —
/// and cancellation can arrive *before* the continuation exists, which is how an earlier fix left
/// it permanently stranded.
final class CaptureBoxTests: XCTestCase {

    private enum ProbeTestError: Error { case stub, first, second }

    func testTheFirstOutcomeWinsAndLaterOnesAreAbsorbed() async {
        let box = CapabilityProbe.CaptureBox()
        let task = Task {
            try await withCheckedThrowingContinuation { c in
                box.attach(c)
                box.finish(.failure(ProbeTestError.first))
                box.finish(.failure(ProbeTestError.second))  // must not crash, must not win
            }
        }
        do { _ = try await task.value; XCTFail("expected the first failure") }
        catch { XCTAssertEqual(error as? ProbeTestError, .first) }
    }

    func testAnOutcomeArrivingBeforeAttachIsReplayed() async {
        // This is the case that hung the probe: cancellation ran before the continuation existed,
        // consumed the right to resume, and found nothing to resume.
        let box = CapabilityProbe.CaptureBox()
        box.finish(.failure(CancellationError()))
        let task = Task {
            try await withCheckedThrowingContinuation { c in box.attach(c) }
        }
        do { _ = try await task.value; XCTFail("expected the replayed cancellation") }
        catch { XCTAssertTrue(error is CancellationError) }
    }

    func testConcurrentFinishersProduceExactlyOneResume() async {
        // Delegate, timeout and cancellation arrive on different threads. Whichever ordering the
        // system picks, the continuation must be resumed once and only once.
        for _ in 0..<100 {
            let box = CapabilityProbe.CaptureBox()
            let task = Task {
                try await withCheckedThrowingContinuation { c in
                    box.attach(c)
                    DispatchQueue.concurrentPerform(iterations: 16) { _ in
                        box.finish(.failure(ProbeTestError.stub))
                    }
                }
            }
            do { _ = try await task.value; XCTFail("expected a failure") }
            catch { XCTAssertEqual(error as? ProbeTestError, .stub) }
        }
    }

    func testFinishingCancelsTheDeadline() {
        let box = CapabilityProbe.CaptureBox()
        let deadline = Task<Void, Never> { try? await Task.sleep(for: .seconds(60)) }
        box.deadline = deadline
        let task = Task { try await withCheckedThrowingContinuation { c in box.attach(c) } }
        box.finish(.failure(ProbeTestError.stub))
        XCTAssertTrue(deadline.isCancelled, "a finished capture must not leave its timeout running")
        task.cancel()
    }
}
