# Good Night macOS App

A menu bar app for the Good Night CLI - an AI reflection system that analyzes conversations and produces artifacts through "dreaming" agents.

## Features

- **Menu Bar Icon**: Sits in your menu bar with a sheep icon
- **One-Click Dreaming**: Start a dream cycle with a single click
- **Sheep Animation**: Watch sheep jump over a fence while dreaming (counting sheep!)
- **Resolution Cards**: View generated resolutions as cards after dreaming
- **Apply Resolutions**: Apply resolutions to specific directories or globally
- **Notifications**: Get notified when dreaming completes with a cheerful chirp

## Building

### Prerequisites

- Xcode 15.0 or later
- macOS 13.0 or later
- The `good-night` CLI installed

### Build from Xcode

1. Open `GoodNightApp.xcodeproj` in Xcode
2. Select your development team (or use "Sign to Run Locally")
3. Build and run (⌘R)

### Build from Command Line

```bash
cd GoodNightApp
xcodebuild -project GoodNightApp.xcodeproj -scheme GoodNightApp -configuration Release build
```

The built app will be in:
```
~/Library/Developer/Xcode/DerivedData/GoodNightApp-*/Build/Products/Release/GoodNightApp.app
```

### Install

Copy the built app to your Applications folder:

```bash
cp -r ~/Library/Developer/Xcode/DerivedData/GoodNightApp-*/Build/Products/Release/GoodNightApp.app /Applications/
```

## Usage

1. **Launch**: Click the sheep icon in your menu bar
2. **First Run**: On first launch, you'll be asked how many days of conversation history to analyze
3. **Dream**: Click "Dream" to start analyzing your conversations
4. **Watch Sheep**: While dreaming, watch sheep jump over a fence
5. **Notification**: When complete, you'll hear a chirp and see a notification
6. **Review**: View resolution cards showing what changes are suggested
7. **Apply**: Apply resolutions to specific directories or globally

## Resolution Cards

Each card shows:
- **Name**: The target file/skill name
- **Type**: Skill, CLAUDE.md, or Guideline
- **Local/Global**: Whether the change is project-specific or user-wide
- **Operation**: Create, Update, or Append
- **Content**: Description of the change
- **Rationale**: Why this resolution was generated
- **Directories**: Which projects this relates to (for local changes)

### Applying Resolutions

- **Apply to Selected**: Select directories and apply the resolution only there
- **Apply Globally**: Apply the resolution to your user-wide configuration

## Files

- `GoodNightApp.swift` - Main app entry point
- `ContentView.swift` - UI components
- `DreamingManager.swift` - CLI integration and state management
- `SheepAnimationView.swift` - The sheep jumping animation

## Requirements

The app requires the `good-night` CLI to be installed. Install it with:

```bash
pip install good-night
```

Or for development:

```bash
cd /path/to/wandb-hackathon
pip install -e .
```
