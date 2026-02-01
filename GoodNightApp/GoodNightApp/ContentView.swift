import SwiftUI

struct ContentView: View {
    @ObservedObject var dreamingManager = DreamingManager.shared

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HeaderView()

            Divider()

            // Content
            if dreamingManager.isDreaming {
                DreamingView()
            } else if dreamingManager.isFirstRun {
                FirstRunView()
            } else if dreamingManager.noNewConversations {
                NoNewConversationsView()
            } else if !dreamingManager.resolutions.isEmpty {
                ResolutionsView()
            } else {
                EmptyStateView()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(NSColor.windowBackgroundColor))
    }
}

struct HeaderView: View {
    @ObservedObject var dreamingManager = DreamingManager.shared

    var body: some View {
        HStack {
            Image(nsImage: NSImage(named: "MenuBarIcon") ?? NSImage())
                .resizable()
                .frame(width: 24, height: 24)

            Text("Good Night")
                .font(.headline)

            Spacer()

            if dreamingManager.isDreaming {
                Button("Stop") {
                    dreamingManager.stopDreaming()
                }
                .buttonStyle(.bordered)
            } else {
                Button("Test") {
                    dreamingManager.testDream()
                }
                .buttonStyle(.bordered)

                Button("Dream") {
                    dreamingManager.startDreaming()
                }
                .buttonStyle(.borderedProminent)
                .disabled(dreamingManager.isFirstRun && dreamingManager.daysToLookback == 0)
            }
        }
        .padding()
    }
}

struct FirstRunView: View {
    @ObservedObject var dreamingManager = DreamingManager.shared

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "moon.stars.fill")
                .font(.system(size: 48))
                .foregroundColor(.purple)

            Text("Welcome to Good Night")
                .font(.title2)
                .fontWeight(.semibold)

            Text("This appears to be your first dream.\nHow many days of conversation history should I analyze?")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)

            HStack {
                Text("Days to look back:")
                Stepper(value: $dreamingManager.daysToLookback, in: 1...365) {
                    Text("\(dreamingManager.daysToLookback)")
                        .frame(width: 40)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color(NSColor.controlBackgroundColor))
                        .cornerRadius(6)
                }
            }

            Text("More days = more comprehensive analysis\nbut slower and more expensive")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button("Start First Dream") {
                dreamingManager.startDreaming()
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .padding(30)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct DreamingView: View {
    var body: some View {
        VStack(spacing: 20) {
            Text("Dreaming")
                .font(.title)
                .fontWeight(.medium)

            Text("Analyzing conversations and generating insights...")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EmptyStateView: View {
    @ObservedObject var dreamingManager = DreamingManager.shared

    var body: some View {
        VStack(spacing: 20) {
            if let error = dreamingManager.dreamError {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.orange)

                Text("Dream Error")
                    .font(.title2)
                    .fontWeight(.semibold)

                ScrollView {
                    Text(error)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundColor(.secondary)
                        .textSelection(.enabled)
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(NSColor.controlBackgroundColor))
                        .cornerRadius(8)
                }
                .frame(maxHeight: 200)
            } else {
                Image(systemName: "moon.zzz.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.gray)

                Text("No Dreams Yet")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Click 'Dream' to analyze your\nconversations and generate insights")
                    .multilineTextAlignment(.center)
                    .foregroundColor(.secondary)
            }
        }
        .padding(30)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct NoNewConversationsView: View {
    @ObservedObject var dreamingManager = DreamingManager.shared

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 48))
                .foregroundColor(.green)

            Text("All Caught Up")
                .font(.title2)
                .fontWeight(.semibold)

            Text("No new conversations since last dream.\nCome back after more coding sessions!")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)

            Button("Dream Again") {
                dreamingManager.noNewConversations = false
                dreamingManager.startDreaming()
            }
            .buttonStyle(.bordered)
        }
        .padding(30)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct ResolutionsView: View {
    @ObservedObject var dreamingManager = DreamingManager.shared

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(dreamingManager.resolutions) { resolution in
                    ResolutionCard(resolution: resolution)
                }
            }
            .padding()
        }
    }
}

struct ResolutionCard: View {
    let resolution: Resolution
    @ObservedObject var dreamingManager = DreamingManager.shared
    @State private var selectedDirectories: Set<String> = []
    @State private var isExpanded = false
    @State private var showingPreview = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Clickable content area (expands/collapses on tap)
            VStack(alignment: .leading, spacing: 12) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(resolution.name)
                            .font(.headline)
                            .lineLimit(1)

                        HStack(spacing: 8) {
                            Label(resolution.displayType, systemImage: typeIcon)
                                .font(.caption)
                                .foregroundColor(.secondary)

                            if resolution.isLocalChange {
                                Text("Local")
                                    .font(.caption2)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.orange.opacity(0.2))
                                    .foregroundColor(.orange)
                                    .cornerRadius(4)
                            } else {
                                Text("Global")
                                    .font(.caption2)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.blue.opacity(0.2))
                                    .foregroundColor(.blue)
                                    .cornerRadius(4)
                            }

                            Text(resolution.operation.capitalized)
                                .font(.caption2)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.gray.opacity(0.2))
                                .foregroundColor(.secondary)
                                .cornerRadius(4)
                        }
                    }

                    Spacer()

                    Button(action: { showingPreview = true }) {
                        Image(systemName: "doc.text")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .foregroundColor(.secondary)
                        .font(.caption)
                        .padding(.leading, 4)

                    Button(action: { dreamingManager.dismissResolution(resolution) }) {
                        Image(systemName: "xmark")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .padding(.leading, 8)
                }

                // Content preview
                Text(resolution.description.isEmpty ? "No description" : resolution.description)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .lineLimit(isExpanded ? nil : 2)

                if isExpanded {
                    // Rationale
                    if !resolution.rationale.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Rationale")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundColor(.secondary)

                            Text(resolution.rationale)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.top, 4)
                    }

                    // Directories selection
                    if !resolution.directories.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Apply to directories:")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundColor(.secondary)

                            ForEach(resolution.directories, id: \.self) { dir in
                                DirectoryButton(
                                    directory: dir,
                                    isSelected: selectedDirectories.contains(dir),
                                    onToggle: {
                                        if selectedDirectories.contains(dir) {
                                            selectedDirectories.remove(dir)
                                        } else {
                                            selectedDirectories.insert(dir)
                                        }
                                    }
                                )
                            }
                        }
                        .padding(.top, 4)
                    }
                }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            }

            Divider()

            // Action buttons (not part of tap area)
            HStack {
                if !resolution.directories.isEmpty && !selectedDirectories.isEmpty {
                    Button("Apply to Selected") {
                        dreamingManager.applyResolution(resolution, toDirectories: Array(selectedDirectories))
                    }
                    .buttonStyle(.bordered)
                }

                Spacer()

                Button("Apply Globally") {
                    dreamingManager.applyResolutionGlobally(resolution)
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 2, x: 0, y: 1)
        .sheet(isPresented: $showingPreview) {
            MarkdownPreviewSheet(resolution: resolution)
        }
    }

    private var typeIcon: String {
        switch resolution.type {
        case "skill": return "wand.and.stars"
        case "claude-md": return "doc.text"
        case "guideline": return "list.bullet.rectangle"
        default: return "square.and.pencil"
        }
    }
}

struct DirectoryButton: View {
    let directory: String
    let isSelected: Bool
    let onToggle: () -> Void

    var body: some View {
        Button(action: onToggle) {
            HStack {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(isSelected ? .accentColor : .secondary)

                Text(shortenPath(directory))
                    .font(.caption)
                    .lineLimit(1)
                    .truncationMode(.middle)

                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }

    private func shortenPath(_ path: String) -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        if path.hasPrefix(home) {
            return "~" + path.dropFirst(home.count)
        }
        return path
    }
}

struct MarkdownPreviewSheet: View {
    let resolution: Resolution
    @Environment(\.dismiss) var dismiss

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(resolution.name)
                        .font(.headline)
                    Text(resolution.displayType)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button("Done") {
                    dismiss()
                }
                .buttonStyle(.bordered)
            }
            .padding()

            Divider()

            // Rendered markdown content
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(parseMarkdownLines(resolution.markdownContent), id: \.id) { line in
                        line.view
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
            }
        }
        .frame(width: 500, height: 400)
    }

    private func parseMarkdownLines(_ markdown: String) -> [MarkdownLine] {
        let lines = markdown.components(separatedBy: "\n")
        var result: [MarkdownLine] = []

        for (index, line) in lines.enumerated() {
            if line.hasPrefix("# ") {
                let text = String(line.dropFirst(2))
                result.append(MarkdownLine(id: index, view: AnyView(
                    Text(text)
                        .font(.title)
                        .fontWeight(.bold)
                        .padding(.bottom, 4)
                )))
            } else if line.hasPrefix("## ") {
                let text = String(line.dropFirst(3))
                result.append(MarkdownLine(id: index, view: AnyView(
                    Text(text)
                        .font(.title2)
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                        .padding(.bottom, 2)
                )))
            } else if line.hasPrefix("### ") {
                let text = String(line.dropFirst(4))
                result.append(MarkdownLine(id: index, view: AnyView(
                    Text(text)
                        .font(.title3)
                        .fontWeight(.medium)
                        .padding(.top, 4)
                )))
            } else if line.hasPrefix("- ") {
                let text = String(line.dropFirst(2))
                result.append(MarkdownLine(id: index, view: AnyView(
                    HStack(alignment: .top, spacing: 8) {
                        Text("•")
                            .foregroundColor(.secondary)
                        Text(renderInlineMarkdown(text))
                            .textSelection(.enabled)
                    }
                    .padding(.leading, 8)
                )))
            } else if line.trimmingCharacters(in: .whitespaces).isEmpty {
                result.append(MarkdownLine(id: index, view: AnyView(
                    Spacer().frame(height: 8)
                )))
            } else {
                result.append(MarkdownLine(id: index, view: AnyView(
                    Text(renderInlineMarkdown(line))
                        .textSelection(.enabled)
                )))
            }
        }

        return result
    }

    private func renderInlineMarkdown(_ text: String) -> AttributedString {
        // Try to parse as attributed string with markdown
        if let attributed = try? AttributedString(markdown: text, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            return attributed
        }
        return AttributedString(text)
    }
}

struct MarkdownLine: Identifiable {
    let id: Int
    let view: AnyView
}

#Preview {
    ContentView()
        .frame(width: 400, height: 500)
}
