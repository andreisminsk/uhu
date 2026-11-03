# Changing Ollama Keep-Alive Timeout Permanently on macOS

By default, Ollama unloads models from memory after 4 to 5 minutes of inactivity. To change this duration permanently on macOS, you must configure a launch agent so the setting persists across system reboots.

## Step 1: Create the Launch Agent File
Open your Terminal and run the following command to create a new configuration file:

```bash
mkdir -p ~/Library/LaunchAgents && nano ~/Library/LaunchAgents/environment.ollama.plist
```

## Step 2: Paste the Configuration
Paste the text block below into the editor. You can replace `30m` with your preferred duration (e.g., `2h` for 2 hours, or `-1` to keep the model loaded indefinitely):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>environment.ollama</string>
    <key>ProgramArguments</key>
    <array>
        <string>launchctl</string>
        <string>setenv</string>
        <string>OLLAMA_KEEP_ALIVE</string>
        <string>30m</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

## Step 3: Save and Exit
1. Press **Ctrl + O** and then press **Enter** to save the file.
2. Press **Ctrl + X** to exit the nano editor.

## Step 4: Apply the Setting Immediately
Load the new rule into your current session and apply the environment variable by running:

```bash
launchctl load ~/Library/LaunchAgents/environment.ollama.plist
launchctl setenv OLLAMA_KEEP_ALIVE "30m"
```

## Step 5: Restart the Ollama Application
1. Click the **Ollama icon** in your macOS menu bar (top right).
2. Choose **Quit Ollama**.
3. Reopen **Ollama** from your Applications folder.

---
*Verify the change by running a query and executing `ollama ps` in your terminal. The **UNTIL** column should reflect your new timeout duration.*
