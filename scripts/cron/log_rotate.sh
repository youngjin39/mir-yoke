#!/bin/bash
# your-harness daemon log rotator
# Rotates /tmp/mir-*.log files: appends .YYYY-MM-DD, gzips, retains 7 days.
set -euo pipefail

LOG_DIR="${MIR_LOG_DIR:-/tmp}"
RETAIN_DAYS="${MIR_LOG_RETAIN_DAYS:-7}"
DATE_TAG="$(date -u +%Y-%m-%d)"

# Rotate matching logs
for log in "$LOG_DIR"/mir-*.log; do
    [ -f "$log" ] || continue
    # Skip empty files
    [ -s "$log" ] || continue

    archive="${log}.${DATE_TAG}"

    # If archive already exists for today, append
    if [ -f "$archive" ]; then
        cat "$log" >> "$archive"
    else
        cp "$log" "$archive"
    fi

    # Truncate live log (don't delete -- daemon may have file handle)
    : > "$log"

    # Compress the archive (if not already compressed)
    if [ -f "$archive" ] && [ ! -f "${archive}.gz" ]; then
        gzip "$archive" 2>/dev/null || true
    fi
done

# Retain only last N days
find "$LOG_DIR" -name 'mir-*.log.*.gz' -mtime "+${RETAIN_DAYS}" -delete 2>/dev/null || true

echo "[log_rotate] $(date -u +%FT%TZ): rotated logs in $LOG_DIR, retained ${RETAIN_DAYS} days"
