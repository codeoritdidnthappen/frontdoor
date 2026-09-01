import XCTest
@testable import FrontdoorCapture

/// The probe's resume discipline (#150).
///
/// A checked continuation may be resumed exactly once; resuming twice is a crash. Three things race
/// to do it — the photo delegate, the 15-second timeout, and cancellation when the operator taps
/// Done — so the winner is settled by a lock rather than by luck.
///
/// This is the part that can be tested without a camera. The timeout firing at all is the fix:
/// the previous shape raced the capture inside a task group, and a task group does not return until
/// every child finishes, so cancelling a child suspended on a continuation left it stranded and the
/// timeout could never propagate.
final class CapabilityProbeResumeGuardTests: XCTestCase {

    func testOnlyTheFirstClaimantWins() {
        let guardObject = CapabilityProbe.ResumeGuard()
        XCTAssertTrue(guardObject.claim(), "the first claimant must be allowed to resume")
        XCTAssertFalse(guardObject.claim(), "a second resume would crash the process")
        XCTAssertFalse(guardObject.claim())
    }

    func testExactlyOneClaimSucceedsUnderConcurrency() {
        // The delegate arrives on an AVFoundation queue, the timeout on a Task, cancellation on the
        // main actor. Whichever ordering the system picks, exactly one must win.
        for _ in 0..<200 {
            let guardObject = CapabilityProbe.ResumeGuard()
            let winners = Atomic()
            DispatchQueue.concurrentPerform(iterations: 16) { _ in
                if guardObject.claim() { winners.increment() }
            }
            XCTAssertEqual(winners.value, 1, "exactly one claimant must resume the continuation")
        }
    }
}

/// Minimal counter; XCTest has no built-in atomic and the point of the test is the race.
private final class Atomic: @unchecked Sendable {
    private let lock = NSLock()
    private var count = 0
    var value: Int { lock.lock(); defer { lock.unlock() }; return count }
    func increment() { lock.lock(); count += 1; lock.unlock() }
}
