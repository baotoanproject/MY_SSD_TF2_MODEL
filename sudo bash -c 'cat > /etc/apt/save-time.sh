#!/bin/bash
# Ghi lại thời gian hệ thống trước khi tắt

TIME_FILE="/etc/last_shutdown_time"

# Ghi giờ hiện tại (theo epoch + ISO để đọc dễ)
date +%s > "$TIME_FILE"
date -Is >> "$TIME_FILE"

echo "[save-time] Saved system time to $TIME_FILE"
