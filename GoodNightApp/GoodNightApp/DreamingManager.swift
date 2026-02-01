import Foundation
import UserNotifications
import AVFoundation
import os.log

private let logger = Logger(subsystem: "com.goodnight.app", category: "dreaming")

class DreamingManager: ObservableObject {
    static let shared = DreamingManager()

    @Published var isDreaming = false
    @Published var resolutions: [Resolution] = []
    @Published var dreamError: String?
    @Published var isFirstRun = false
    @Published var daysToLookback: Int = 14

    private var audioPlayer: AVAudioPlayer?
    private var process: Process?

    private init() {
        checkFirstRun()
        loadResolutions()
    }

    func checkFirstRun() {
        // Check if good-night has run before by looking at state.json
        let stateFile = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".good-night/state.json")

        if !FileManager.default.fileExists(atPath: stateFile.path) {
            isFirstRun = true
            return
        }

        // Check if any connector has been processed (has last_processed timestamp)
        guard let data = try? Data(contentsOf: stateFile),
              let state = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let connectors = state["connectors"] as? [String: Any] else {
            isFirstRun = true
            return
        }

        // If no connectors configured, it's first run
        if connectors.isEmpty {
            isFirstRun = true
            return
        }

        // Check if any connector has a last_processed timestamp
        var hasProcessed = false
        for (_, connectorData) in connectors {
            if let connectorDict = connectorData as? [String: Any],
               connectorDict["last_processed"] != nil {
                hasProcessed = true
                break
            }
        }

        isFirstRun = !hasProcessed
    }

    func startDreaming() {
        guard !isDreaming else { return }

        isDreaming = true
        dreamError = nil

        // Show sky overlay
        DispatchQueue.main.async {
            SkyOverlayWindow.show()
        }

        Task {
            await runDreamCycle()
        }
    }

    func stopDreaming() {
        process?.terminate()
        isDreaming = false
    }

    private func runDreamCycle() async {
        print("[Dream] runDreamCycle started")

        // Find good-night CLI
        let cliPath = findGoodNightCLI()

        guard let cliPath = cliPath else {
            print("[Dream] ERROR: Could not find good-night CLI")
            await MainActor.run {
                dreamError = "Could not find good-night CLI. Make sure it's installed."
                isDreaming = false
            }
            return
        }

        print("[Dream] Found CLI at: \(cliPath)")

        // Build command arguments
        var arguments = ["dream", "--quiet"]

        // Only pass --days on first run (when nothing has been processed yet)
        if isFirstRun {
            arguments.append(contentsOf: ["--days", "14"])
        }

        let commandString = "\(cliPath) \(arguments.joined(separator: " "))"
        print("[Dream] Running command: \(commandString)")

        // Run the CLI in background
        let result = await Task.detached {
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: cliPath)
            proc.arguments = arguments

            let pipe = Pipe()
            proc.standardOutput = pipe
            proc.standardError = pipe

            do {
                print("[Dream] Starting process...")
                try proc.run()
                print("[Dream] Process started with PID: \(proc.processIdentifier)")
                proc.waitUntilExit()
                print("[Dream] Process exited with status: \(proc.terminationStatus)")

                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8) ?? ""
                print("[Dream] Output length: \(output.count) chars")

                return (proc.terminationStatus, output)
            } catch {
                print("[Dream] ERROR starting process: \(error)")
                return (Int32(-1), error.localizedDescription)
            }
        }.value

        await MainActor.run {
            // Hide sky overlay
            SkyOverlayWindow.hide()

            if result.0 == 0 {
                isFirstRun = false
                loadResolutions()
                sendCompletionNotification()
            } else {
                dreamError = "Command: \(commandString)\n\nExit code: \(result.0)\n\nOutput:\n\(result.1)"
            }
            isDreaming = false
        }
    }

    private func findGoodNightCLI() -> String? {
        // Try common locations
        let paths = [
            "/usr/local/bin/good-night",
            "/opt/homebrew/bin/good-night",
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/good-night",
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/good-night",
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/good-night",
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin/good-night").path,
            // Also try via pip/python
        ]

        for path in paths {
            if FileManager.default.fileExists(atPath: path) {
                return path
            }
        }

        // Try to find via which
        let whichProcess = Process()
        whichProcess.executableURL = URL(fileURLWithPath: "/usr/bin/which")
        whichProcess.arguments = ["good-night"]

        let pipe = Pipe()
        whichProcess.standardOutput = pipe

        do {
            try whichProcess.run()
            whichProcess.waitUntilExit()

            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            if let path = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
               !path.isEmpty {
                return path
            }
        } catch {}

        // Try python module
        return findPythonModule()
    }

    private func findPythonModule() -> String? {
        // Try running as python module
        let pythonPaths = [
            "/usr/bin/python3",
            "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3"
        ]

        for python in pythonPaths {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: python)
            process.arguments = ["-c", "import good_night; print('found')"]

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = Pipe()

            do {
                try process.run()
                process.waitUntilExit()

                if process.terminationStatus == 0 {
                    // Return a wrapper script path
                    return createPythonWrapper(pythonPath: python)
                }
            } catch {}
        }

        return nil
    }

    private func createPythonWrapper(pythonPath: String) -> String {
        let wrapperPath = FileManager.default.temporaryDirectory.appendingPathComponent("good-night-wrapper.sh")
        let script = """
        #!/bin/bash
        \(pythonPath) -m good_night.cli.main "$@"
        """

        try? script.write(to: wrapperPath, atomically: true, encoding: .utf8)
        try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: wrapperPath.path)

        return wrapperPath.path
    }

    func loadResolutions() {
        let resolutionsDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".good-night/resolutions")

        guard let files = try? FileManager.default.contentsOfDirectory(
            at: resolutionsDir,
            includingPropertiesForKeys: [.creationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            return
        }

        // Sort by creation date, newest first
        let sortedFiles = files
            .filter { $0.pathExtension == "json" }
            .sorted { file1, file2 in
                let date1 = (try? file1.resourceValues(forKeys: [.creationDateKey]))?.creationDate ?? Date.distantPast
                let date2 = (try? file2.resourceValues(forKeys: [.creationDateKey]))?.creationDate ?? Date.distantPast
                return date1 > date2
            }

        var loadedResolutions: [Resolution] = []

        for file in sortedFiles.prefix(10) { // Load last 10 resolution files
            if let data = try? Data(contentsOf: file),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                loadedResolutions.append(contentsOf: parseResolutions(from: json, fileURL: file))
            }
        }

        resolutions = loadedResolutions
    }

    private func parseResolutions(from json: [String: Any], fileURL: URL) -> [Resolution] {
        var results: [Resolution] = []

        guard let resolutionsArray = json["resolutions"] as? [[String: Any]] else {
            return results
        }

        for connectorRes in resolutionsArray {
            guard let actions = connectorRes["actions"] as? [[String: Any]] else {
                continue
            }

            for action in actions {
                let resolution = Resolution(
                    id: UUID().uuidString,
                    name: action["name"] as? String ?? action["target"] as? String ?? "Unknown",
                    type: action["type"] as? String ?? "unknown",
                    description: action["description"] as? String ?? "",
                    content: action["content"] as? [String: Any] ?? [:],
                    directories: extractDirectories(from: action),
                    rationale: action["rationale"] as? String ?? "",
                    issueRefs: action["issue_refs"] as? [String] ?? [],
                    sourceFile: fileURL,
                    isLocalChange: action["local_change"] as? Bool ?? false,
                    operation: action["operation"] as? String ?? "create"
                )
                results.append(resolution)
            }
        }

        return results
    }

    private func extractDirectories(from action: [String: Any]) -> [String] {
        // Extract directories from references array (ConversationReference objects)
        var dirs: Set<String> = []

        // Primary source: references array with working_directory
        if let references = action["references"] as? [[String: Any]] {
            for ref in references {
                if let workingDir = ref["working_directory"] as? String, !workingDir.isEmpty {
                    dirs.insert(workingDir)
                }
            }
        }

        // Fallback: check content for working_directory
        if let content = action["content"] as? [String: Any],
           let workingDir = content["working_directory"] as? String, !workingDir.isEmpty {
            dirs.insert(workingDir)
        }

        // Also check local_change flag - if true, this is project-specific
        let isLocalChange = action["local_change"] as? Bool ?? false
        if isLocalChange && dirs.isEmpty {
            // If local_change but no directories, try to extract from target path
            if let target = action["target"] as? String, target.hasPrefix("/") {
                // Target might be something like /path/to/project/.claude/skills/...
                // Try to find the project root
                if let claudeRange = target.range(of: "/.claude/") {
                    let projectPath = String(target[..<claudeRange.lowerBound])
                    dirs.insert(projectPath)
                }
            }
        }

        return Array(dirs).sorted()
    }

    func applyResolution(_ resolution: Resolution, toDirectories directories: [String]) {
        // Placeholder for now
        print("Applying resolution '\(resolution.name)' to directories: \(directories)")

        // Remove from list
        resolutions.removeAll { $0.id == resolution.id }
    }

    func applyResolutionGlobally(_ resolution: Resolution) {
        // Placeholder for now
        print("Applying resolution '\(resolution.name)' globally")

        // Remove from list
        resolutions.removeAll { $0.id == resolution.id }
    }

    func dismissResolution(_ resolution: Resolution) {
        // Remove from UI list (doesn't delete the file)
        resolutions.removeAll { $0.id == resolution.id }
    }

    func testDream() {
        guard !isDreaming else { return }

        isDreaming = true
        dreamError = nil

        // Show sky overlay
        DispatchQueue.main.async {
            SkyOverlayWindow.show()
        }

        // Wait 10 seconds then complete
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) { [weak self] in
            SkyOverlayWindow.hide()
            self?.sendCompletionNotification()
            self?.isDreaming = false
        }
    }

    private func sendCompletionNotification() {
        logger.info("sendCompletionNotification called")

        let dreamSubjects = [
            "rabbits", "trees", "clouds", "mountains", "rivers",
            "stars", "butterflies", "rainbows", "meadows", "forests",
            "oceans", "sunsets", "flowers", "birds", "moonlight",
            "waterfalls", "gardens", "snowflakes", "fireflies", "auroras",
            "galaxies", "comets", "dolphins", "unicorns", "dragons",
            "crystals", "lavender", "hummingbirds", "cherry blossoms", "northern lights"
        ]

        let randomSubject = dreamSubjects.randomElement() ?? "stars"
        logger.info("Random subject: \(randomSubject)")

        // Check permission first
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            logger.info("Authorization status: \(settings.authorizationStatus.rawValue)")

            guard settings.authorizationStatus == .authorized else {
                logger.warning("Not authorized, requesting permission...")
                UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
                    logger.info("Permission granted: \(granted), error: \(String(describing: error))")
                    if granted {
                        self.postNotification(subject: randomSubject)
                    }
                }
                return
            }

            self.postNotification(subject: randomSubject)
        }
    }

    private func postNotification(subject: String) {
        logger.info("Posting notification with subject: \(subject)")

        let content = UNMutableNotificationContent()
        content.title = "Good Night"
        content.body = "I was dreaming about \(subject)"

        // Set up custom sound
        setupNotificationSound()
        content.sound = UNNotificationSound(named: UNNotificationSoundName("good-night-chirp.wav"))

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                logger.error("ERROR posting notification: \(error.localizedDescription)")
            } else {
                logger.info("Notification posted successfully")
            }
        }
    }

    private func setupNotificationSound() {
        let soundsDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Sounds")

        try? FileManager.default.createDirectory(at: soundsDir, withIntermediateDirectories: true)

        let destURL = soundsDir.appendingPathComponent("good-night-chirp.wav")

        // Always try to copy from bundle
        if let soundURL = Bundle.main.url(forResource: "mixkit-little-bird-calling-chirp-23", withExtension: "wav") {
            if !FileManager.default.fileExists(atPath: destURL.path) {
                try? FileManager.default.copyItem(at: soundURL, to: destURL)
            }
        }
    }
}

struct Resolution: Identifiable {
    let id: String
    let name: String
    let type: String
    let description: String
    let content: [String: Any]
    let directories: [String]
    let rationale: String
    let issueRefs: [String]
    let sourceFile: URL
    let isLocalChange: Bool
    let operation: String

    var displayType: String {
        switch type {
        case "skill": return "Skill"
        case "claude-md": return "CLAUDE.md"
        case "guideline": return "Guideline"
        default: return type.capitalized
        }
    }
}
