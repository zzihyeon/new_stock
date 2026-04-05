#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR" "$LAUNCH_DIR"

write_plist() {
  local label="$1"
  local script_path="$2"
  local schedule_xml="$3"
  local out="$LAUNCH_DIR/${label}.plist"

  cat > "$out" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>${label}</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>${PROJECT_DIR}/${script_path}</string>
    </array>
    <key>WorkingDirectory</key><string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
${schedule_xml}
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>${LOG_DIR}/${label}.out.log</string>
    <key>StandardErrorPath</key><string>${LOG_DIR}/${label}.err.log</string>
  </dict>
</plist>
EOF

  launchctl unload "$out" >/dev/null 2>&1 || true
  launchctl load "$out"
  echo "Installed: $out"
}

WEEKDAY_0800='    <array>
      <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    </array>'

WEEKDAY_0900='    <array>
      <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    </array>'

WEEKDAY_1300='    <array>
      <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
    </array>'

WEEKDAY_1500='    <array>
      <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    </array>'

WEEKDAY_1900='    <array>
      <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
    </array>'

for old_label in ingest1600 watchlist2000 intraday30m screener alert1400 alert2000; do
  old_plist="$LAUNCH_DIR/com.jihyeonyu.stock.${old_label}.plist"
  if [ -f "$old_plist" ]; then
    launchctl unload "$old_plist" >/dev/null 2>&1 || true
    rm -f "$old_plist"
    echo "Removed old: $old_plist"
  fi
done

write_plist "com.jihyeonyu.stock.realtime" "scripts/run_realtime_sync.sh" "$WEEKDAY_0800"
write_plist "com.jihyeonyu.stock.alert0900" "scripts/run_alert_0900.sh" "$WEEKDAY_0900"
write_plist "com.jihyeonyu.stock.alert1300" "scripts/run_alert_1300.sh" "$WEEKDAY_1300"
write_plist "com.jihyeonyu.stock.alert1500" "scripts/run_alert_1500.sh" "$WEEKDAY_1500"
write_plist "com.jihyeonyu.stock.alert1900" "scripts/run_alert_1900.sh" "$WEEKDAY_1900"

echo ""
echo "Registered jobs:"
launchctl list | grep "com.jihyeonyu.stock." || true
