#!/bin/bash
export PATH=$PATH:/sbin:/usr/sbin

if ! wg show wg0 >/dev/null 2>&1; then
    echo "$(date): VPN down, reconnecting..." >> /var/log/vpn-watchdog.log
    wg-quick up wg0 >> /var/log/vpn-watchdog.log 2>&1
fi

if ! systemctl is-active anime_monitor >/dev/null 2>&1; then
    echo "$(date): Bot down, restarting..." >> /var/log/vpn-watchdog.log
    systemctl restart anime_monitor
fi
