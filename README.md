# 🔐 AZ L2TP VPN — نصب‌کننده

نصب کامل **L2TP/IPsec + پنل مدیریت کاربران** روی هر سرور اوبونتو (۲۲.۰۴ تا ۲۴.۰۴) با **یه دستور**.

شامل: `Libreswan (IPsec)` + `xl2tpd` + `pppd` + پنل وب فلاسک (مدیریت کاربر، سقف حجم، IP ثابت، انقضا) + فایروال و NAT.

---

## ⚡ نصب — یه خط کافیه!

```bash
curl -fsSL https://raw.githubusercontent.com/arshiyaazizi/l2tp-installer/main/install.sh | sudo bash
```

همه‌ی فایل‌ها **داخل خود اسکریپت جاسازی شدن** → نیازی به `git clone` نیست و فقط با همین یه خط روی هر سرور اوبونتو نصب میشه.

**با آرگومان:**
```bash
curl -fsSL https://raw.githubusercontent.com/arshiyaazizi/l2tp-installer/main/install.sh | sudo bash -s -- --password MY-PASS --psk MY-PSK
```

### روش کلون (اگه ترجیح میدی)
```bash
git clone https://github.com/arshiyaazizi/l2tp-installer.git
cd l2tp-installer
sudo bash install.sh
```

**رمزها رو خودکار رندوم میسازه و در پایان چاپ میکنه:**
```
🔑 رمز ورود پنل :  AZ-xxxxxxxx
🔐 PSK (L2TP)   :  aB3x...
🌐 پنل          :  http://IP:8085/
```

### گزینه‌ها
```bash
sudo bash install.sh --psk MY-PSK              # PSK دلخواه
sudo bash install.sh --password MY-PASSWORD     # رمز ورود پنل دلخواه
sudo bash install.sh --server vpn.example.com   # آدرس سرور (پیش‌فرض: تشخیص خودکار)
sudo bash install.sh --psk A --password B --server X
```

---

## 📱 اتصال کلاینت (آیفون / اندروید / ویندوز)

از پنل کاربر بساز و لینک یا اطلاعات رو وارد کن، یا دستی:

| فیلد | مقدار |
|---|---|
| نوع | L2TP/IPsec با PSK |
| آدرس سرور | آدرس سرور شما |
| PSK | همونی که نصب چاپ کرد |
| نام کاربری / رمز | از پنل ساخته‌شده |

---

## 🖥️ پنل مدیریت

- آدرس: `http://IP:8085/`
- فقط **رمز** دارد (نام کاربری نداره)
- قابلیت‌ها: افزودن/حذف کاربر، سقف حجم (GB)، تاریخ انقضا، IP ثابت (`192.168.42.100-199`)، گزارش مصرف، فعال/غیرفعال‌سازی
- همه‌چیز داخل `sqlite` ذخیره میشه: `/root/l2tp-panel/panel.db`
- کاربران در `/etc/ppp/chap-secrets` نوشته میشن (بازه `# BEGIN L2TP-PANEL` تا `# END L2TP-PANEL`)

---

## 🌐 پورت‌های موردنیاز (در فایروال سرور باز کن)

```
UDP 500    IKE
UDP 4500   NAT-T
UDP 1701   L2TP
TCP 8085   پنل مدیریت (بهتره فقط به IP خودت محدود بشه)
```

---

## 🗑ه حذف کامل

```bash
sudo bash uninstall.sh
```
همه‌ی سرویس‌ها، کانفیگ‌ها و پنل رو پاک میکنه (قبلش بکاپ میزنه).

---

## 📁 ساختار ریپو

```
install.sh              نصب‌کننده‌ی خودکار
uninstall.sh            حذف کامل
files/
  ipsec.conf            کانفیگ IPsec (آدرس سرور خودکار جایگزین میشه)
  ipsec.d/              گواهی‌های NSS
  xl2tpd.conf           کانفیگ xl2tpd (استخر 192.168.42.20-99)
  ppp-options.xl2tpd    گزینه‌های pppd
  ppp-chap-secrets      فایل کاربران (خالی — پنل پر میکنه)
  l2tp-secrets          secrets xl2tpd
  l2tp-panel.service    یونیت systemd پنل
  panel/app.py          پنل وب
```

## ⚠️ نکات
- اسکریپت قبل از تغییر، **بکاپ** از نسخه قبلی میزنه: `/root/l2tp-backup-<تاریخ>/`
- روی سروری که از قبل L2TP داره هم اجرا بشه، کانفیگ‌ها جایگزین و سرویس‌ها ری‌استارت میشن
- **PSK و رمز پنل رو جایی امن نگه دار** — کسی که PSK رو داشته باشه میتونه وصل بشه
