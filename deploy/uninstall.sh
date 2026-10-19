#!/bin/bash
# Stops RSC's background jobs and removes the Desktop icon. Your data (~/RSC) is NOT touched.
# To remove the AI models too:  ollama rm llama3.2:3b qwen2.5vl:3b   (or delete the Ollama app)
for label in app checkmail weeklyreport dailysheet ollama claude-myles; do
  plist="$HOME/Library/LaunchAgents/com.reclaimedspacecrafters.$label.plist"
  [ -f "$plist" ] && { launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null; rm -f "$plist"; echo "Stopped $label"; }
done
rm -f "$HOME/Desktop/RSC.command"
echo "Done. Your jobs and settings are still in ${RSC_HOME:-$HOME/RSC}. Delete that folder yourself if you really want them gone."
