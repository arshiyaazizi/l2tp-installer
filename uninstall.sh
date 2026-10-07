#!/usr/bin/env bash
# حذف کامل L2TP + پنل (با بکاپ قبل از حذف)
set -uo pipefail
RED()  { printf '\033[1;31m%s\033[0m\n' "$*"; }
GRN()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
BLU()  { printf '\033[1;34m%s\033[0m\n' "$*"; }

[ "$(id -u)" = "0" ] || { RED "با root اجرا کن"; exit 1; }

BLU "──── بکاپ قبل از حذف ────"
BK="/root/l2tp-removed-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BK"
for p in /etc/ipsec.conf /etc/ipsec.secrets /etc/ipsec.d /etc/xl2tpd /etc/ppp/chap-secrets /root/l2tp-panel /etc/systemd/system/l2tp-panel.service; do
  [ -e "$p" ] && cp -a "$p" "$BK/" 2>/dev/null
done
GRN "  بکاپ: $BK"

BLU "──── توقف و غیرفعال‌سازی سرویس‌ها ────"
for s in l2tp-panel xl2tpd ipsec; do
  systemctl stop "$s" 2>/dev/null || true
  systemctl disable "$s" 2>/dev/null || true
  GRN "  $s متوقف شد"
done

BLU "──── حذف قوانین فایروال ────"
while iptables -D FORWARD -d 192.168.42.0/24 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; do :; done
while iptables -D FORWARD -s 192.168.42.0/24 -j ACCEPT 2>/dev/null; do :; done
while iptables -D FORWARD -j L2TP_QUOTA 2>/dev/null; do :; done
while iptables -t nat -D POSTROUTING -s 192.168.42.0/24 -j MASQUERADE 2>/dev/null; do :; done
while iptables -t nat -D POSTROUTING -s 192.168.42.0/24 -o eth0 -j MASQUERADE 2>/dev/null; do :; done
iptables -F L2TP_QUOTA 2>/dev/null || true
iptables -X L2TP_QUOTA 2>/dev/null || true
iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
GRN "  قوانین پاک شد"

BLU "──── حذف فایل‌ها ────"
rm -rf /root/l2tp-panel /etc/systemd/system/l2tp-panel.service
rm -f  /etc/ppp/chap-secrets /etc/ppp/options.xl2tpd
rm -rf /etc/xl2tpd
rm -f  /etc/ipsec.conf /etc/ipsec.secrets
rm -rf /etc/ipsec.d
rm -f  /etc/sysctl.d/99-l2tp.conf
systemctl daemon-reload
GRN "  فایل‌ها حذف شد (پکیج‌ها باقی میمونن)"

echo
GRN "════ حذف کامل شد ════"
echo "  برای نصب دوباره: bash install.sh"
