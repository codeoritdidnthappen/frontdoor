import Foundation
import Network

/// Drains the pending-upload queue, automatically when a connection appears and on demand
/// (TICK-029, #33, AC2 and AC6).
@MainActor
final class UploadCoordinator: ObservableObject {

    /// Files still on the phone. What the operator reads before leaving a field session.
    @Published private(set) var pendingCount: Int = 0
    @Published private(set) var isDraining = false
    /// Files that will never upload without a person looking at them.
    ///
    /// A list rather than one slot: an operator with several blocked captures needs to see all of
    /// them, not whichever failed last. Cleared at the start of every drain so a problem that has
    /// since been fixed stops being reported.
    @Published private(set) var blockingErrors: [String] = []
    @Published private(set) var lastDrainSummary: String?

    private let directory: URL
    private let client: UploadClient?
    private let monitor = NWPathMonitor()
    private var started = false

    init(directory: URL, client: UploadClient?) {
        self.directory = directory
        self.client = client
        refreshCount()
    }

    /// Convenience wiring for the app: reads configuration and returns nil-client if unconfigured.
    convenience init(directory: URL, settings: UploadSettings = .fromBundle()) {
        self.init(directory: directory, client: settings.client())
    }

    var isConfigured: Bool { client != nil }

    /// Re-derive the count from the disk. Off the main actor: the scan decodes every sidecar in
    /// the directory, which is a day of captures during a field session.
    func refreshCount() {
        let dir = directory
        Task {
            let count = await Task.detached { UploadQueue.pendingCount(in: dir) }.value
            self.pendingCount = count
        }
    }

    /// Watch for connectivity and drain when it returns.
    ///
    /// The monitor is the whole of AC2's "uploads when connectivity returns": there is no timer and
    /// no retry schedule, because the queue lives on disk and a drain is cheap to repeat. A field
    /// session that walks past a coffee shop drains without anyone deciding to.
    func start() {
        guard !started, client != nil else { return }
        started = true
        monitor.pathUpdateHandler = { [weak self] path in
            guard path.status == .satisfied else { return }
            Task { @MainActor in await self?.drain() }
        }
        monitor.start(queue: DispatchQueue(label: "frontdoor.upload.path"))
    }

    /// Upload everything queued. Safe to call again while one is running; the second call returns.
    func drain() async {
        guard let client, !isDraining else { return }
        isDraining = true
        defer { isDraining = false }

        blockingErrors = []
        var stored = 0
        var failed = 0

        // Scanned once, off the main actor. Re-listing the directory per item made a 300-file
        // backlog 300 scans and 300 sidecar decodes, all blocking the UI the operator is watching.
        let dir = directory
        let work = await Task.detached { UploadQueue.pending(in: dir) }.value
        var remaining = work.count
        pendingCount = remaining

        for item in work {
            switch await client.send(item) {
            case .stored:
                // Only here, and only now: the server confirmed the stored bytes hash to what the
                // sidecar recorded, which is the whole of AC5's precondition for deleting.
                UploadQueue.discardLocal(item)
                stored += 1
            case .rejected(let why):
                // Kept on the phone deliberately. A refusal the server will repeat means the file
                // and its recorded hash disagree, and deleting it would destroy the only evidence.
                blockingErrors.append("\(item.captureId) (\(item.kind.rawValue)): \(why)")
                failed += 1
            case .retry:
                failed += 1
            }
            // Counted down rather than rescanned, so the number moves without touching the disk.
            remaining -= 1
            pendingCount = remaining + failed
        }

        lastDrainSummary = stored == 0 && failed == 0
            ? "Nothing to upload."
            : "Uploaded \(stored), \(failed) still waiting."
        // One authoritative rescan at the end, when it costs nothing that anyone is waiting on.
        refreshCount()
    }
}

/// Where the app sends captures, and the secret that lets it.
///
/// Both come from Info.plist via build settings rather than source, so the upload key is not
/// committed — the same arrangement as `DEVELOPMENT_TEAM`. The key authorises ingest and nothing
/// else: it is not an R2 credential and cannot read the bucket, which is the point of routing
/// uploads through the server at all.
struct UploadSettings {
    var serverURL: URL?
    var uploadKey: String?

    static func fromBundle(_ bundle: Bundle = .main) -> UploadSettings {
        func string(_ key: String) -> String? {
            let value = (bundle.object(forInfoDictionaryKey: key) as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return (value?.isEmpty ?? true) ? nil : value
        }
        return UploadSettings(
            serverURL: string("FrontdoorServerURL").flatMap(URL.init(string:)),
            uploadKey: string("FrontdoorUploadKey"))
    }

    /// A client, or nil when the build has no server or no key.
    ///
    /// nil disables upload and says so in the UI. Silently doing nothing would let an operator
    /// finish a day believing the queue was draining.
    func client() -> UploadClient? {
        guard let serverURL, let uploadKey else { return nil }
        return UploadClient(baseURL: serverURL, uploadKey: uploadKey)
    }
}
