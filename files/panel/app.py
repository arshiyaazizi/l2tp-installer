#!/usr/bin/env python3
"""AZ L2TP VPN Panel — مدیریت یوزر، حجم و انقضا برای L2TP/IPsec"""
import os, re, sqlite3, subprocess, threading, time, secrets, datetime
from flask import Flask, request, redirect, session, render_template_string, url_for, flash

BASE = "/root/l2tp-panel"
DB = f"{BASE}/panel.db"
PASSFILE = f"{BASE}/.admin_pass"
KEYFILE = f"{BASE}/.secret_key"
CHAP = "/etc/ppp/chap-secrets"
BEGIN = "# BEGIN L2TP-PANEL"
END = "# END L2TP-PANEL"
CHAIN = "L2TP_QUOTA"
POOL = range(100, 200)          # IP ثابت پنل: 192.168.42.100-199
GB = 1024 ** 3

app = Flask(__name__)
if not os.path.exists(KEYFILE):
    open(KEYFILE, "w").write(secrets.token_hex(32))
app.secret_key = open(KEYFILE).read().strip()


def admin_password():
    if not os.path.exists(PASSFILE):
        p = "AZ-" + secrets.token_urlsafe(9)
        with open(PASSFILE, "w") as f:
            f.write(p)
        os.chmod(PASSFILE, 0o600)
    return open(PASSFILE).read().strip()


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            ip TEXT UNIQUE NOT NULL,
            total_gb REAL DEFAULT 0,
            used_bytes INTEGER DEFAULT 0,
            expiry TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')))""")


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def harvest():
    """خواندن شمارنده‌های iptables، جمع در دیتابیس و صفر کردن"""
    r = sh("iptables-save -c")
    if r.returncode != 0:
        return {}
    totals = {}
    pat = re.compile(r"\[(\d+):(\d+)\][^\n]*--comment\s+\"?l2tpu_([A-Za-z0-9._-]+)_(up|down)")
    for m in pat.finditer(r.stdout):
        totals[m.group(3)] = totals.get(m.group(3), 0) + int(m.group(2))
    sh(f"iptables -Z {CHAIN}")
    if totals:
        with db() as c:
            for u, b in totals.items():
                if b:
                    c.execute("UPDATE users SET used_bytes=used_bytes+? WHERE username=?", (b, u))
    return totals


def rebuild():
    """بازسازی زنجیره شمارش از روی دیتابیس (منبع حقیقت)"""
    harvest()
    with db() as c:
        users = c.execute("SELECT * FROM users ORDER BY id").fetchall()
    sh(f"iptables -F {CHAIN}")
    for u in users:
        if u["enabled"]:
            sh(f'iptables -A {CHAIN} -s {u["ip"]} -m comment --comment l2tpu_{u["username"]}_up -j RETURN')
            sh(f'iptables -A {CHAIN} -d {u["ip"]} -m comment --comment l2tpu_{u["username"]}_down -j RETURN')
        else:
            sh(f'iptables -A {CHAIN} -s {u["ip"]} -m comment --comment l2tpb_{u["username"]} -j DROP')
            sh(f'iptables -A {CHAIN} -d {u["ip"]} -m comment --comment l2tpb_{u["username"]}d -j DROP')


def sync_chap():
    """نوشتن بخش مدیریت‌شده chap-secrets از روی دیتابیس"""
    with db() as c:
        users = c.execute("SELECT * FROM users ORDER BY id").fetchall()
    out, skip = [], False
    for ln in open(CHAP):
        s = ln.strip()
        if s == BEGIN:
            skip = True
            continue
        if s == END:
            skip = False
            continue
        if not skip:
            out.append(ln)
    out.append(BEGIN + "\n")
    for u in users:
        line = f'"{u["username"]}" l2tpd "{u["password"]}" {u["ip"]}\n'
        out.append(line if u["enabled"] else "#" + line)
    out.append(END + "\n")
    tmp = CHAP + ".tmp"
    with open(tmp, "w") as f:
        f.writelines(out)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CHAP)


def free_ip():
    with db() as c:
        used = {r["ip"] for r in c.execute("SELECT ip FROM users")}
    for i in POOL:
        ip = f"192.168.42.{i}"
        if ip not in used:
            return ip
    return None


def online_ips():
    r = sh("ip -o -4 addr show")
    return set(re.findall(r"peer\s+(\d+\.\d+\.\d+\.\d+)", r.stdout))


def disable_user(uid):
    with db() as c:
        c.execute("UPDATE users SET enabled=0 WHERE id=?", (uid,))
    rebuild()
    sync_chap()


def ensure_fw():
    sh(f"iptables -N {CHAIN} 2>/dev/null")
    sh(f"iptables -C FORWARD -j {CHAIN} 2>/dev/null || iptables -I FORWARD 1 -j {CHAIN}")
    sh("iptables -C FORWARD -s 192.168.42.0/24 -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -s 192.168.42.0/24 -j ACCEPT")
    sh("iptables -C FORWARD -d 192.168.42.0/24 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || "
       "iptables -I FORWARD 1 -d 192.168.42.0/24 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")
    sh("iptables -t nat -C POSTROUTING -s 192.168.42.0/24 -j MASQUERADE 2>/dev/null || "
       "iptables -t nat -A POSTROUTING -s 192.168.42.0/24 -j MASQUERADE")


def tick_loop():
    while True:
        try:
            harvest()
            today = datetime.date.today().isoformat()
            with db() as c:
                rows = c.execute("SELECT * FROM users WHERE enabled=1").fetchall()
            for u in rows:
                if u["total_gb"] > 0 and u["used_bytes"] >= u["total_gb"] * GB:
                    disable_user(u["id"])
                    flash_safe(f"کاربر {u['username']} به دلیل اتمام حجم غیرفعال شد")
                elif u["expiry"] and today > u["expiry"]:
                    disable_user(u["id"])
                    flash_safe(f"کاربر {u['username']} منقضی شده و غیرفعال شد")
        except Exception as e:
            print("tick error:", e)
        time.sleep(60)


def flash_safe(msg):
    print("[panel]", msg)


TPL = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AZ L2TP Panel</title><style>
:root{--bg:#0f172a;--card:#1e293b;--br:#334155;--tx:#e2e8f0;--mut:#94a3b8;--ac:#38bdf8;--ok:#4ade80;--bad:#f87171}
*{box-sizing:border-box}body{margin:0;font-family:Tahoma,Arial,sans-serif;background:var(--bg);color:var(--tx)}
.wrap{max-width:1100px;margin:20px auto;padding:0 14px}
h1{color:var(--ac);font-size:22px}.sub{color:var(--mut);font-size:13px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--br);border-radius:12px;padding:16px;margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:9px 8px;border-bottom:1px solid var(--br);text-align:right;vertical-align:middle}
th{color:var(--mut);font-weight:normal;font-size:12px}
tr:last-child td{border-bottom:none}
input,button{font-family:inherit;border-radius:8px;border:1px solid var(--br);background:#0b1220;color:var(--tx);padding:8px 10px;font-size:14px}
button{cursor:pointer;background:var(--ac);color:#052e16;border:none;font-weight:bold}
button:hover{filter:brightness(1.1)}button.sm{padding:5px 9px;font-size:12px}
button.warn{background:var(--bad);color:#fff}button.gh{background:var(--br);color:var(--tx)}
.badge{display:inline-block;padding:3px 9px;border-radius:20px;font-size:12px}
.on{background:#052e16;color:var(--ok)}.off{background:#450a0a;color:var(--bad)}
.mono{font-family:monospace;direction:ltr}
.formrow{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.formrow input{width:130px}.grow{flex:1}
.flash{background:#7f1d1d;border:1px solid var(--bad);color:#fecaca;padding:10px 14px;border-radius:10px;margin-bottom:14px}
.flash.ok{background:#052e16;border-color:var(--ok);color:#bbf7d0}
.hint{color:var(--mut);font-size:12px;margin-top:6px}
.ip{color:var(--mut);font-size:12px}
.usage{font-family:monospace}.dim{color:var(--mut)}
</style></head><body><div class="wrap">
<h1>🔐 پنل L2TP — AZ VPN</h1>
<div class="sub">ساخت یوزر • حجم • انقضا • مصرف لحظه‌ای</div>
{% with msgs = get_flashed_messages() %}
  {% for m in msgs %}<div class="flash ok">{{ m }}</div>{% endfor %}
{% endwith %}
<div class="card">
<form class="formrow" method="post" action="/add">
  <input name="username" placeholder="یوزرنیم" required pattern="[A-Za-z0-9._-]{3,32}">
  <input name="password" placeholder="پسورد (خالی=خودکار)">
  <input name="gb" type="number" step="0.1" min="0" placeholder="حجم GB (0=نامحدود)" value="20">
  <input name="days" type="number" min="0" placeholder="روز (0=بدون انقضا)" value="30">
  <button type="submit">➕ افزودن کاربر</button>
</form>
<div class="hint">IP ثابت به صورت خودکار از محدوده 192.168.42.100-199 اختصاص می‌یابد. حجم/روز = ۰ یعنی بدون محدودیت.</div>
</div>
<div class="card">
<table>
<tr><th>کاربر</th><th>پسورد</th><th>IP</th><th>مصرف</th><th>سقف</th><th>انقضا</th><th>وضعیت</th><th></th></tr>
{% for u in users %}
<tr>
 <td><b>{{ u.username }}</b> {% if u.ip in online %}<span class="badge on">● آنلاین</span>{% endif %}</td>
 <td class="mono">{{ u.password }}</td>
 <td class="mono ip">{{ u.ip }}</td>
 <td class="usage">{{ '%.2f'|format(u.used_gb) }} GB</td>
 <td>{% if u.total_gb > 0 %}{{ '%.1f'|format(u.total_gb) }} GB{% else %}<span class="dim">نامحدود</span>{% endif %}</td>
 <td>{% if u.expiry %}{{ u.expiry }}{% else %}<span class="dim">—</span>{% endif %}</td>
 <td>{% if u.enabled %}<span class="badge on">فعال</span>{% else %}<span class="badge off">غیرفعال</span>{% endif %}</td>
 <td style="white-space:nowrap">
  <form method="post" action="/user/{{ u.id }}/extend" style="display:inline-flex;gap:4px">
   <input name="gb" type="number" step="0.1" min="0" placeholder="+GB" style="width:76px;padding:5px">
   <input name="days" type="number" min="0" placeholder="+روز" style="width:66px;padding:5px">
   <button class="sm" type="submit">افزایش</button>
  </form>
  <form method="post" action="/user/{{ u.id }}/toggle" style="display:inline">
   <button class="sm gh" type="submit">{% if u.enabled %}⏸ توقف{% else %}▶ فعال{% endif %}</button></form>
  <form method="post" action="/user/{{ u.id }}/delete" style="display:inline"
        onsubmit="return confirm('کاربر {{ u.username }} حذف شود؟')">
   <button class="sm warn" type="submit">🗑</button></form>
 </td>
</tr>
{% else %}
<tr><td colspan="8" class="dim">هنوز کاربری ثبت نشده.</td></tr>
{% endfor %}
</table>
</div>
<div class="card hint">🔄 مصرف هر ۶۰ ثانیه بروز می‌شود • غیرفعال‌سازی خودکار در اتمام حجم یا انقضا •
<a href="/logout" style="color:var(--bad)">خروج</a></div>
</div></body></html>"""

LOGIN_TPL = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ورود پنل L2TP</title>
<style>body{margin:0;font-family:Tahoma,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:30px;width:320px;text-align:center}
h1{color:#38bdf8;font-size:20px;margin:0 0 18px}input{width:100%;padding:11px;margin-bottom:12px;border-radius:9px;border:1px solid #334155;background:#0b1220;color:#e2e8f0;font-family:inherit;box-sizing:border-box}
button{width:100%;padding:11px;border:none;border-radius:9px;background:#38bdf8;color:#052e16;font-weight:bold;cursor:pointer;font-family:inherit}
.err{color:#f87171;font-size:13px;margin-bottom:10px}</style></head><body>
<div class="card"><h1>🔐 ورود به پنل</h1>
{% if err %}<div class="err">پسورد اشتباه است</div>{% endif %}
<form method="post"><input type="password" name="password" placeholder="پسورد ادمین" autofocus>
<button type="submit">ورود</button></form></div></body></html>"""


def login_required(f):
    from functools import wraps
    @wraps(f)
    def w(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*a, **k)
    return w


@app.route("/login", methods=["GET", "POST"])
def login():
    err = False
    if request.method == "POST":
        if request.form.get("password", "") == admin_password():
            session["admin"] = True
            return redirect("/")
        time.sleep(1)
        err = True
    return render_template_string(LOGIN_TPL, err=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
@login_required
def index():
    harvest()
    on = online_ips()
    with db() as c:
        rows = c.execute("SELECT * FROM users ORDER BY id").fetchall()
    users = [dict(r, used_gb=r["used_bytes"] / GB) for r in rows]
    return render_template_string(TPL, users=users, online=on)


@app.post("/add")
@login_required
def add():
    uname = request.form.get("username", "").strip()
    pwd = request.form.get("password", "").strip() or secrets.token_urlsafe(10)[:14]
    try:
        gb = max(0.0, float(request.form.get("gb", 0) or 0))
        days = max(0, int(request.form.get("days", 0) or 0))
    except ValueError:
        flash("مقدار حجم/روز نامعتبر است")
        return redirect("/")
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", uname):
        flash("یوزرنیم فقط حروف انگلیسی، عدد، نقطه و _ - باشد (۳ تا ۳۲ کاراکتر)")
        return redirect("/")
    ip = free_ip()
    if not ip:
        flash("محدوده IP پنل پر است!")
        return redirect("/")
    expiry = (datetime.date.today() + datetime.timedelta(days=days)).isoformat() if days else None
    try:
        with db() as c:
            c.execute("INSERT INTO users(username,password,ip,total_gb,expiry) VALUES(?,?,?,?,?)",
                      (uname, pwd, ip, gb, expiry))
    except sqlite3.IntegrityError:
        flash("این یوزرنیم قبلا ثبت شده")
        return redirect("/")
    rebuild()
    sync_chap()
    flash(f"کاربر {uname} ساخته شد — IP: {ip}")
    return redirect("/")


@app.post("/user/<int:uid>/extend")
@login_required
def extend(uid):
    try:
        gb = max(0.0, float(request.form.get("gb", 0) or 0))
        days = max(0, int(request.form.get("days", 0) or 0))
    except ValueError:
        flash("مقدار نامعتبر")
        return redirect("/")
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            return redirect("/")
        base = datetime.date.today()
        if u["expiry"]:
            try:
                cur = datetime.date.fromisoformat(u["expiry"])
                base = max(base, cur)
            except ValueError:
                pass
        new_expiry = (base + datetime.timedelta(days=days)).isoformat() if days else u["expiry"]
        c.execute("UPDATE users SET total_gb=total_gb+?, expiry=?, enabled=1 WHERE id=?",
                  (gb, new_expiry, uid))
    rebuild()
    sync_chap()
    flash(f"کاربر {u['username']}: +{gb:g} گیگابایت و +{days} روز اعمال شد")
    return redirect("/")


@app.post("/user/<int:uid>/toggle")
@login_required
def toggle(uid):
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            return redirect("/")
        c.execute("UPDATE users SET enabled=? WHERE id=?", (0 if u["enabled"] else 1, uid))
    rebuild()
    sync_chap()
    flash(f"کاربر {u['username']} {'فعال' if not u['enabled'] else 'غیرفعال'} شد")
    return redirect("/")


@app.post("/user/<int:uid>/delete")
@login_required
def delete(uid):
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            return redirect("/")
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    rebuild()
    sync_chap()
    flash(f"کاربر {u['username']} حذف شد")
    return redirect("/")


if __name__ == "__main__":
    os.makedirs(BASE, exist_ok=True)
    init_db()
    ensure_fw()
    admin_password()
    threading.Thread(target=tick_loop, daemon=True).start()
    print(f"Panel on :8085  admin pass: {admin_password()}")
    app.run(host="0.0.0.0", port=8085, threaded=True)
