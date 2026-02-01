import SwiftUI
import AppKit

class SkyOverlayWindow: NSWindow {
    static var shared: SkyOverlayWindow?

    static func show() {
        print("[SkyOverlay] show() called")
        if shared == nil {
            print("[SkyOverlay] Creating new window")
            shared = SkyOverlayWindow()
        }
        shared?.alphaValue = 0
        shared?.orderFrontRegardless()

        // Fade in slowly
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 2.0
            shared?.animator().alphaValue = 1.0
        }
        print("[SkyOverlay] show() completed, starting fade in")
    }

    static func hide() {
        print("[SkyOverlay] hide() called")
        // Print stack trace to see who called hide()
        Thread.callStackSymbols.prefix(10).forEach { print($0) }
        // Immediately disappear
        shared?.alphaValue = 0
        shared?.orderOut(nil)
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

                // Twinkling stars
                TwinklingStarsView()
            }
        }
        .onAppear {
            withAnimation(.linear(duration: 12).repeatForever(autoreverses: false)) {
                phase = 1
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
                size: CGFloat.random(in: 0.5...1.2),
                maxOpacity: Double.random(in: 0.3...0.6),
                twinkleDuration: Double.random(in: 3...8),
                fadeInOut: true,
                delay: Double.random(in: 0...5)
            ))
        }

        // Layer 2: Medium stars
        for _ in 0..<50 {
            stars.append(StarData(
                x: CGFloat.random(in: 0...size.width),
                y: CGFloat.random(in: 0...size.height * 0.75),
                size: CGFloat.random(in: 1.2...2.5),
                maxOpacity: Double.random(in: 0.5...0.85),
                twinkleDuration: Double.random(in: 2...5),
                fadeInOut: Bool.random(),
                delay: Double.random(in: 0...4)
            ))
        }

        // Layer 3: Bright prominent stars (fewer)
        for _ in 0..<20 {
            stars.append(StarData(
                x: CGFloat.random(in: 0...size.width),
                y: CGFloat.random(in: 0...size.height * 0.6),
                size: CGFloat.random(in: 2.5...4.0),
                maxOpacity: Double.random(in: 0.7...1.0),
                twinkleDuration: Double.random(in: 1.5...4),
                fadeInOut: false,
                delay: Double.random(in: 0...2)
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
    let fadeInOut: Bool  // true = can disappear completely, false = just dims
    let delay: Double
}

struct TwinklingStar: View {
    let star: StarData

    @State private var opacity: Double = 0
    @State private var isVisible: Bool = true

    var body: some View {
        Circle()
            .fill(Color.white)
            .frame(width: star.size, height: star.size)
            .blur(radius: star.size > 2.5 ? 0.5 : 0)  // Slight glow for bright stars
            .opacity(opacity)
            .position(x: star.x, y: star.y)
            .onAppear {
                startTwinkling()
            }
    }

    private func startTwinkling() {
        DispatchQueue.main.asyncAfter(deadline: .now() + star.delay) {
            if star.fadeInOut {
                // Stars that appear and disappear
                fadeInOutCycle()
            } else {
                // Stars that just twinkle (dim and brighten)
                withAnimation(.easeInOut(duration: star.twinkleDuration).repeatForever(autoreverses: true)) {
                    opacity = star.maxOpacity
                }
            }
        }
    }

    private func fadeInOutCycle() {
        // Fade in
        withAnimation(.easeIn(duration: star.twinkleDuration * 0.4)) {
            opacity = star.maxOpacity
        }

        // Schedule fade out
        DispatchQueue.main.asyncAfter(deadline: .now() + star.twinkleDuration * Double.random(in: 0.5...1.5)) {
            withAnimation(.easeOut(duration: star.twinkleDuration * 0.6)) {
                opacity = 0
            }

            // Schedule next appearance
            DispatchQueue.main.asyncAfter(deadline: .now() + Double.random(in: 1...6)) {
                fadeInOutCycle()
            }
        }
    }
}
