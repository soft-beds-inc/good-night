import SwiftUI
import AppKit
import Combine

class SkyState: ObservableObject {
    static let shared = SkyState()
    @Published var isTextVisible = false
}

class SkyOverlayWindow: NSWindow {
    static var shared: SkyOverlayWindow?

    static func show() {
        if shared == nil {
            shared = SkyOverlayWindow()
        }
        shared?.alphaValue = 0
        shared?.orderFrontRegardless()
        SkyState.shared.isTextVisible = false

        // Fade in slowly (2 sec)
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 2.0
            shared?.animator().alphaValue = 1.0
        }

        // Show text when gradient is 50% faded in (at 1 sec)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            SkyState.shared.isTextVisible = true
        }
    }

    static func hide() {
        // Start fading out sky (2 sec)
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 2.0
            shared?.animator().alphaValue = 0
        }, completionHandler: {
            shared?.orderOut(nil)
        })

        // Fade out text when gradient is 50% faded out (at 1 sec)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            SkyState.shared.isTextVisible = false
        }
    }

    static func toggle() {
        if shared?.isVisible == true && (shared?.alphaValue ?? 0) > 0.5 {
            hide()
        } else {
            show()
        }
    }

    init() {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let screenRect = screen.frame

        // Only cover top 1/3 of screen
        let height = screenRect.height / 3
        let windowRect = NSRect(
            x: screenRect.origin.x,
            y: screenRect.origin.y + screenRect.height - height,
            width: screenRect.width,
            height: height
        )

        super.init(
            contentRect: windowRect,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )

        self.level = .screenSaver
        self.backgroundColor = .clear
        self.isOpaque = false
        self.hasShadow = false
        self.ignoresMouseEvents = true
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        let hostingView = NSHostingView(rootView: SkyAuraView())
        hostingView.frame = NSRect(x: 0, y: 0, width: windowRect.width, height: windowRect.height)
        self.contentView = hostingView
    }
}

struct SkyAuraView: View {
    @State private var phase: CGFloat = 0

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Main gradient - max 70% opacity, fades to transparent at bottom
                LinearGradient(
                    stops: [
                        .init(color: Color(red: 0.02, green: 0.02, blue: 0.08).opacity(0.7), location: 0),
                        .init(color: Color(red: 0.05, green: 0.05, blue: 0.15).opacity(0.6), location: 0.2),
                        .init(color: Color(red: 0.08, green: 0.06, blue: 0.18).opacity(0.4), location: 0.5),
                        .init(color: Color(red: 0.08, green: 0.06, blue: 0.15).opacity(0.15), location: 0.8),
                        .init(color: Color.clear, location: 1.0),
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )

                // Aurora waves
                AuroraWave(phase: phase, color: Color.purple.opacity(0.15))
                AuroraWave(phase: phase + 0.3, color: Color.blue.opacity(0.12))
                AuroraWave(phase: phase + 0.6, color: Color.cyan.opacity(0.08))

                // Twinkling stars with rays
                TwinklingStarsView()

                // "it is dreaming" text - positioned higher
                DreamingTextView()
                    .position(x: geometry.size.width / 2, y: geometry.size.height * 0.30)
            }
        }
        .onAppear {
            withAnimation(.linear(duration: 12).repeatForever(autoreverses: false)) {
                phase = 1
            }
        }
    }
}

struct DreamingTextView: View {
    @ObservedObject var skyState = SkyState.shared
    @State private var visibleWords: Int = 0

    private let words = ["it ", "is ", "dreaming", ".", ".", "."]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(0..<words.count, id: \.self) { index in
                Text(words[index])
                    .opacity(visibleWords > index ? 0.9 : 0)
                    .animation(.easeInOut(duration: 1.0), value: visibleWords)
            }
        }
        .font(.custom("Roboto-Italic", size: 32))
        .foregroundColor(Color(red: 1.0, green: 0.85, blue: 0.2))
        .transformEffect(CGAffineTransform(a: 1, b: 0, c: -0.04, d: 1, tx: 0, ty: 0))
        .shadow(color: .black, radius: 0, x: -3, y: 0)
        .shadow(color: .black, radius: 0, x: 3, y: 0)
        .shadow(color: .black, radius: 0, x: 0, y: -3)
        .shadow(color: .black, radius: 0, x: 0, y: 3)
        .shadow(color: .black, radius: 0, x: -2, y: -2)
        .shadow(color: .black, radius: 0, x: 2, y: -2)
        .shadow(color: .black, radius: 0, x: -2, y: 2)
        .shadow(color: .black, radius: 0, x: 2, y: 2)
        .shadow(color: .black, radius: 2, x: 0, y: 0)
        .onChange(of: skyState.isTextVisible) { visible in
            if visible {
                // Show words one by one
                visibleWords = 0
                for i in 1...words.count {
                    DispatchQueue.main.asyncAfter(deadline: .now() + Double(i) * 1.5) {
                        visibleWords = i
                    }
                }
            } else {
                // Hide all at once
                visibleWords = 0
            }
        }
    }
}

struct AuroraWave: View {
    let phase: CGFloat
    let color: Color

    var body: some View {
        GeometryReader { geometry in
            Path { path in
                let width = geometry.size.width
                let height = geometry.size.height
                let midHeight = height * 0.5

                path.move(to: CGPoint(x: 0, y: 0))
                path.addLine(to: CGPoint(x: 0, y: midHeight))

                for x in stride(from: 0, to: width, by: 3) {
                    let relativeX = x / width
                    let sine = sin((relativeX + phase) * .pi * 2.5)
                    let y = midHeight + sine * 30
                    path.addLine(to: CGPoint(x: x, y: y))
                }

                path.addLine(to: CGPoint(x: width, y: 0))
                path.closeSubpath()
            }
            .fill(color)
            .blur(radius: 25)
        }
    }
}

struct TwinklingStarsView: View {
    @State private var starData: [StarData] = []

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                ForEach(starData) { star in
                    TwinklingStar(star: star)
                }
            }
            .onAppear {
                generateStars(in: geometry.size)
            }
        }
    }

    private func generateStars(in size: CGSize) {
        var stars: [StarData] = []

        // Layer 1: Many tiny distant stars (most numerous)
        for _ in 0..<120 {
            stars.append(StarData(
                x: CGFloat.random(in: 0...size.width),
                y: CGFloat.random(in: 0...size.height * 0.8),
                size: CGFloat.random(in: 0.8...1.5),
                maxOpacity: Double.random(in: 0.3...0.6),
                twinkleDuration: Double.random(in: 3...8),
                fadeInOut: true,
                delay: Double.random(in: 0...5),
                isYellow: Double.random(in: 0...1) < 0.15  // 15% chance of yellow
            ))
        }

        // Layer 2: Medium stars
        for _ in 0..<50 {
            stars.append(StarData(
                x: CGFloat.random(in: 0...size.width),
                y: CGFloat.random(in: 0...size.height * 0.75),
                size: CGFloat.random(in: 1.5...3.0),
                maxOpacity: Double.random(in: 0.5...0.85),
                twinkleDuration: Double.random(in: 2...5),
                fadeInOut: Bool.random(),
                delay: Double.random(in: 0...4),
                isYellow: Double.random(in: 0...1) < 0.2  // 20% chance of yellow
            ))
        }

        // Layer 3: Bright prominent stars (fewer)
        for _ in 0..<25 {
            stars.append(StarData(
                x: CGFloat.random(in: 0...size.width),
                y: CGFloat.random(in: 0...size.height * 0.6),
                size: CGFloat.random(in: 3.0...5.0),
                maxOpacity: Double.random(in: 0.7...1.0),
                twinkleDuration: Double.random(in: 1.5...4),
                fadeInOut: false,
                delay: Double.random(in: 0...2),
                isYellow: Double.random(in: 0...1) < 0.25  // 25% chance of yellow
            ))
        }

        starData = stars
    }
}

struct StarData: Identifiable {
    let id = UUID()
    let x: CGFloat
    let y: CGFloat
    let size: CGFloat
    let maxOpacity: Double
    let twinkleDuration: Double
    let fadeInOut: Bool
    let delay: Double
    let isYellow: Bool
}

struct TwinklingStar: View {
    let star: StarData

    @State private var opacity: Double = 0

    var starColor: Color {
        if star.isYellow {
            return Color(red: 1.0, green: 0.95, blue: 0.7)  // Soft warm yellow
        } else {
            return Color.white
        }
    }

    var body: some View {
        ZStack {
            // Main star body with rays
            StarShape(points: 8, innerRatio: 0.4)
                .fill(starColor)
                .frame(width: star.size * 2, height: star.size * 2)

            // Glow effect for larger stars
            if star.size > 2 {
                Circle()
                    .fill(starColor.opacity(0.3))
                    .frame(width: star.size * 1.5, height: star.size * 1.5)
                    .blur(radius: star.size * 0.5)
            }
        }
        .opacity(opacity)
        .position(x: star.x, y: star.y)
        .onAppear {
            startTwinkling()
        }
    }

    private func startTwinkling() {
        DispatchQueue.main.asyncAfter(deadline: .now() + star.delay) {
            if star.fadeInOut {
                fadeInOutCycle()
            } else {
                withAnimation(.easeInOut(duration: star.twinkleDuration).repeatForever(autoreverses: true)) {
                    opacity = star.maxOpacity
                }
            }
        }
    }

    private func fadeInOutCycle() {
        withAnimation(.easeIn(duration: star.twinkleDuration * 0.4)) {
            opacity = star.maxOpacity
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + star.twinkleDuration * Double.random(in: 0.5...1.5)) {
            withAnimation(.easeOut(duration: star.twinkleDuration * 0.6)) {
                opacity = 0
            }

            DispatchQueue.main.asyncAfter(deadline: .now() + Double.random(in: 1...6)) {
                fadeInOutCycle()
            }
        }
    }
}

// 4-pointed star shape with rays
struct StarShape: Shape {
    let points: Int
    let innerRatio: CGFloat

    func path(in rect: CGRect) -> Path {
        let center = CGPoint(x: rect.width / 2, y: rect.height / 2)
        let outerRadius = min(rect.width, rect.height) / 2
        let innerRadius = outerRadius * innerRatio

        var path = Path()
        let angleStep = .pi / CGFloat(points)

        for i in 0..<(points * 2) {
            let radius = i.isMultiple(of: 2) ? outerRadius : innerRadius
            let angle = CGFloat(i) * angleStep - .pi / 2

            let point = CGPoint(
                x: center.x + radius * cos(angle),
                y: center.y + radius * sin(angle)
            )

            if i == 0 {
                path.move(to: point)
            } else {
                path.addLine(to: point)
            }
        }

        path.closeSubpath()
        return path
    }
}
