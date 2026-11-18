#!/usr/bin/env bash
# macOS launchd에 매일 07:00 (KST) skill-scan을 등록한다.
# 사용법: ./skill-scan/install_schedule.sh [uninstall]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.skillradar.skillscan"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
RUNNER="$REPO_ROOT/skill-scan/run_daily.sh"

if [ "${1:-}" = "uninstall" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $PLIST"
  exit 0
fi

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${RUNNER}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>7</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>${REPO_ROOT}/skill-scan/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>${REPO_ROOT}/skill-scan/logs/launchd.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>TZ</key><string>Asia/Seoul</string>
  </dict>
</dict>
</plist>
PLIST_EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "installed: $PLIST (daily 07:00 KST)"
echo "logs: $REPO_ROOT/skill-scan/logs/"
echo "제거: $0 uninstall"
