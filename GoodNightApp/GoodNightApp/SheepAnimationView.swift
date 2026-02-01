import SwiftUI

struct SheepAnimationView: View {
    @State private var sheepStates: [SheepState] = []
    let timer = Timer.publish(every: 1.5, on: .main, in: .common).autoconnect()

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Semi-transparent overlay
                Color.black.opacity(0.3)

                // Fence for sheep to jump over
                FenceView()
                    .position(x: geometry.size.width / 2, y: geometry.size.height * 0.65)

                // Animated sheep
                ForEach(sheepStates) { sheep in
                    JumpingSheepView(state: sheep, containerSize: geometry.size)
                }
            }
        }
        .onReceive(timer) { _ in
            addNewSheep()
        }
        .onAppear {
            addNewSheep()
        }
    }

    private func addNewSheep() {
        let newSheep = SheepState(id: UUID())
        sheepStates.append(newSheep)

        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
            sheepStates.removeAll { $0.id == newSheep.id }
        }
    }
}

struct SheepState: Identifiable {
    let id: UUID
    let startTime = Date()
}

struct JumpingSheepView: View {
    let state: SheepState
    let containerSize: CGSize

    @State private var progress: CGFloat = 0
    @State private var rotation: Double = 0

    var body: some View {
        SheepShape()
            .fill(Color.white)
            .frame(width: 60, height: 45)
            .shadow(color: .black.opacity(0.3), radius: 3, x: 2, y: 2)
            .rotationEffect(.degrees(rotation))
            .position(position)
            .onAppear {
                withAnimation(.easeInOut(duration: 2.5)) {
                    progress = 1
                }
                // Add slight wobble
                withAnimation(.easeInOut(duration: 0.3).repeatForever(autoreverses: true)) {
                    rotation = 5
                }
            }
    }

    private var position: CGPoint {
        // Parabolic jump trajectory from left to right
        let startX: CGFloat = -50
        let endX: CGFloat = containerSize.width + 50
        let currentX = startX + (endX - startX) * progress

        let midY = containerSize.height * 0.65 // Fence height
        let jumpHeight: CGFloat = 150

        // Parabola: y = -4h(x-0.5)^2 + h where x is 0 to 1
        let normalizedX = progress
        let jumpOffset = -4 * jumpHeight * pow(normalizedX - 0.5, 2) + jumpHeight
        let currentY = midY - jumpOffset

        return CGPoint(x: currentX, y: currentY)
    }
}

struct SheepShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()

        let bodyWidth = rect.width * 0.8
        let bodyHeight = rect.height * 0.6

        // Fluffy body (cloud-like shape)
        let bodyCenter = CGPoint(x: rect.midX, y: rect.midY)

        // Main body ellipse
        path.addEllipse(in: CGRect(
            x: bodyCenter.x - bodyWidth/2,
            y: bodyCenter.y - bodyHeight/2,
            width: bodyWidth,
            height: bodyHeight
        ))

        // Fluffy bumps on top
        let bumpSize: CGFloat = bodyHeight * 0.35
        path.addEllipse(in: CGRect(
            x: bodyCenter.x - bodyWidth * 0.35,
            y: bodyCenter.y - bodyHeight * 0.6,
            width: bumpSize,
            height: bumpSize
        ))
        path.addEllipse(in: CGRect(
            x: bodyCenter.x - bumpSize/2,
            y: bodyCenter.y - bodyHeight * 0.7,
            width: bumpSize,
            height: bumpSize
        ))
        path.addEllipse(in: CGRect(
            x: bodyCenter.x + bodyWidth * 0.15,
            y: bodyCenter.y - bodyHeight * 0.55,
            width: bumpSize,
            height: bumpSize
        ))

        // Head (smaller circle on the right)
        let headSize = bodyHeight * 0.7
        path.addEllipse(in: CGRect(
            x: bodyCenter.x + bodyWidth * 0.3,
            y: bodyCenter.y - headSize * 0.3,
            width: headSize,
            height: headSize
        ))

        // Front legs
        let legWidth: CGFloat = 6
        let legHeight: CGFloat = bodyHeight * 0.5

        // Front leg (bent forward for jumping)
        path.addRoundedRect(
            in: CGRect(
                x: bodyCenter.x + bodyWidth * 0.1,
                y: bodyCenter.y + bodyHeight * 0.2,
                width: legWidth,
                height: legHeight
            ),
            cornerSize: CGSize(width: 2, height: 2)
        )

        // Back leg (extended back)
        path.addRoundedRect(
            in: CGRect(
                x: bodyCenter.x - bodyWidth * 0.3,
                y: bodyCenter.y + bodyHeight * 0.15,
                width: legWidth,
                height: legHeight * 1.1
            ),
            cornerSize: CGSize(width: 2, height: 2)
        )

        return path
    }
}

struct FenceView: View {
    var body: some View {
        HStack(spacing: 20) {
            ForEach(0..<5, id: \.self) { _ in
                FencePost()
            }
        }
    }
}

struct FencePost: View {
    var body: some View {
        ZStack {
            // Vertical post
            RoundedRectangle(cornerRadius: 2)
                .fill(Color.brown.opacity(0.8))
                .frame(width: 8, height: 60)

            // Horizontal rails
            VStack(spacing: 15) {
                RoundedRectangle(cornerRadius: 1)
                    .fill(Color.brown.opacity(0.7))
                    .frame(width: 40, height: 4)

                RoundedRectangle(cornerRadius: 1)
                    .fill(Color.brown.opacity(0.7))
                    .frame(width: 40, height: 4)
            }
        }
    }
}

#Preview {
    SheepAnimationView()
        .frame(width: 400, height: 500)
        .background(Color.gray)
}
