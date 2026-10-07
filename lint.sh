#!/bin/bash
# تست syntax هر سه اسکریپت + شبیه‌سازی جایگزینی IP در ipsec.conf (هیچی روی سرور اجرا نمیشه)
cd /root/l2tp-repo || exit 1
for f in install.sh uninstall.sh; do
  if bash -n "$f" 2>/tmp/e; then echo "SYNTAX OK   $f"; else echo "SYNTAX FAIL $f: $(cat /tmp/e)"; fi
done

echo "--- تست --help (باید بدون اجرا خارج بشه) ---"
bash install.sh --help >/dev/null 2>&1 && echo "  help OK" || echo "  help FAILED"

echo "--- شبیه‌سازی جایگزینی آدرس سرور ---"
TMP=$(mktemp -d)
cp files/ipsec.conf "$TMP/ipsec.conf"
sed -i "s/__SERVER_IP__/203.0.113.77/g" "$TMP/ipsec.conf"
if grep -q "__SERVER_IP__" "$TMP/ipsec.conf"; then echo "  FAILED: placeholder باقی مونده"; else echo "  placeholder جایگزین شد ✓"; fi
grep -n "leftid" "$TMP/ipsec.conf" | sed 's/^/  /'

echo "--- ساختار PSK (شبیه‌سازی) ---"
printf '%%any  %%any  : PSK "%s"\n' "TEST_PSK_123" | sed -E 's/(PSK ").*(")/\1<REDACTED>\2/' | sed 's/^/  /'

echo "--- فایل‌های لازم موجودن؟ ---"
for f in files/ipsec.conf files/ipsec.d/cert9.db files/ipsec.d/key4.db files/xl2tpd.conf \
         files/l2tp-secrets files/ppp-options.xl2tpd files/ppp-chap-secrets \
         files/l2tp-panel.service files/panel/app.py; do
  [ -f "$f" ] && echo "  OK   $f" || echo "  MISS $f"
done
rm -rf "$TMP"
