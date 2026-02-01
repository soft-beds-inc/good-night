import SwiftUI
import UserNotifications

@main
struct GoodNightApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var dreamingManager = DreamingManager.shared

    var body: some Scene {
        Settings {
            EmptyView()
        }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    var statusItem: NSStatusItem?
    var popover: NSPopover?
    var sheepWindow: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Request notification permissions
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error = error {
                print("Notification permission error: \(error)")
            }
        }

        // Create status bar item
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)

        if let button = statusItem?.button {
            if let iconImage = NSImage(named: "MenuBarIcon") {
                iconImage.isTemplate = true
                iconImage.size = NSSize(width: 18, height: 18)
                button.image = iconImage
            } else {
                // Fallback: use moon emoji
                button.title = "🌙"
            }
            button.action = #selector(handleClick)
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }

        // Create popover
        popover = NSPopover()
        popover?.contentSize = NSSize(width: 400, height: 500)
        popover?.behavior = .transient
        popover?.contentViewController = NSHostingController(rootView: ContentView())

        // Hide dock icon
        NSApp.setActivationPolicy(.accessory)

        // Check first launch
        checkFirstLaunch()
    }

    func checkFirstLaunch() {
        let defaults = UserDefaults.standard
        if !defaults.bool(forKey: "hasLaunchedBefore") {
            defaults.set(true, forKey: "hasLaunchedBefore")
            // Show popover on first launch
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                self.showPopover()
            }
        }
    }

    @objc func handleClick() {
        guard let event = NSApp.currentEvent else { return }

        if event.type == .rightMouseUp {
            showContextMenu()
        } else {
            togglePopover()
        }
    }

    @objc func togglePopover() {
        // If dreaming, toggle the sky overlay instead
        if DreamingManager.shared.isDreaming {
            SkyOverlayWindow.toggle()
            return
        }

        // Otherwise show normal popover
        if let popover = popover {
            if popover.isShown {
                popover.performClose(nil)
            } else {
                showPopover()
            }
        }
    }

    func showContextMenu() {
        let menu = NSMenu()

        if DreamingManager.shared.isDreaming {
            let stopItem = NSMenuItem(title: "Stop Dreaming", action: #selector(stopDreaming), keyEquivalent: "")
            stopItem.target = self
            menu.addItem(stopItem)
        } else {
            let dreamItem = NSMenuItem(title: "Dream", action: #selector(startDreaming), keyEquivalent: "")
            dreamItem.target = self
            menu.addItem(dreamItem)
        }

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: "Quit", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem?.menu = menu
        statusItem?.button?.performClick(nil)
        statusItem?.menu = nil  // Remove menu so left-click works normally
    }

    @objc func startDreaming() {
        DreamingManager.shared.startDreaming()
    }

    @objc func stopDreaming() {
        DreamingManager.shared.stopDreaming()
        SkyOverlayWindow.hide()
    }

    @objc func quitApp() {
        NSApp.terminate(nil)
    }

    func showPopover() {
        if let button = statusItem?.button, let popover = popover {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    // Handle notification when app is in foreground
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }

    // Handle notification tap
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        showPopover()
        completionHandler()
    }
}
