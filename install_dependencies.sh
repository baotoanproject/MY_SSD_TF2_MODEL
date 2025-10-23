#!/bin/bash

# Cập nhật hệ thống
sudo apt update

# Cài các gói cần thiết cho BLE và GLib
sudo apt install -y python3-dbus python3-gi libglib2.0-dev bluez

# Cài Network Manager để quản lý Wi-Fi
sudo apt install -y network-manager
