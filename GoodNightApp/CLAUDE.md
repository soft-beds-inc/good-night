# Project Preferences

## Xcode Project Structure
- The Xcode project (GoodNightApp.xcodeproj) is located in the GoodNightApp/ subdirectory, NOT in the project root
- Always run xcodebuild commands from the GoodNightApp/ directory or use the -project flag with the full path
- Before executing xcodebuild commands, verify you are in the correct directory or explicitly cd into GoodNightApp/
- Example correct usage: `cd GoodNightApp && xcodebuild [options]` or `xcodebuild -project GoodNightApp/GoodNightApp.xcodeproj [options]`
