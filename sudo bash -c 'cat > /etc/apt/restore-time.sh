#!/bin/bash
# Khôi phục lại thời gian từ file lưu

TIME_FILE="/etc/last_shutdown_time"

if [ -f "$TIME_FILE" ]; then
    # Lấy epoch time đầu tiên trong file
    SAVED_EPOCH=$(head -n 1 "$TIME_FILE")
    # Cộng thêm thời gian tương đối kể từ lần tắt (dự phòng)
    CURRENT_EPOCH=$(date +%s)
    if [ "$SAVED_EPOCH" -gt 0 ]; then
        # Nếu hệ thống đang có thời gian < 2024 (sai), thì mới set
        YEAR_NOW=$(date +%Y)
        if [ "$YEAR_NOW" -lt 2024 ]; then
            echo "[restore-time] Restoring saved time..."
            date -s "@$SAVED_EPOCH"
        else
            echo "[restore-time] System time looks OK ($YEAR_NOW), skip restore."
        fi
    fi
else
    echo "[restore-time] No saved time found."
fi
