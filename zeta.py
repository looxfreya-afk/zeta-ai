#!/usr/bin/env python3
"""Zeta AI - AI tools untuk Termux (tanpa library tambahan, cuma Python).

Dibuat oleh Jevon.
"""

import atexit
import base64
import codecs
import getpass
import glob
import hashlib
import hmac
import html
import http.server
import json
import re
import secrets
import select
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import termios
    import tty
except ImportError:  # bukan terminal Unix
    termios = tty = None

try:
    import readline  # riwayat ketikan, tombol panah, Tab
except ImportError:
    readline = None

VERSION = "1.7"
DEFAULT_AUTO = 0  # 0 = kirim langsung saat Enter (tanpa jeda)
DIR = os.environ.get("ZETA_HOME") or os.path.expanduser("~/.zeta_ai")
CFG_FILE = os.path.join(DIR, "config.json")
CHAT_DIR = os.path.join(DIR, "chats")
HIST_FILE = os.path.join(DIR, "history")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_MODEL = "openrouter/auto"
# API key TIDAK ditulis di kode (aman diunggah ke GitHub / dideploy).
# Isi lewat: environment OPENROUTER_API_KEY, perintah /key, atau dashboard admin.
DEFAULT_KEY = ""
DEFAULT_SYSTEM = (
    "Kamu adalah Zeta AI, asisten AI yang berjalan di Termux, dibuat oleh Jevon. "
    "Jawab singkat, jelas, dan pakai bahasa yang sama dengan pengguna. "
    "Kalau memberi perintah shell, pastikan cocok untuk Termux (Android)."
)
IMG_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
MAX_FILE = 30000  # batas karakter isi file teks yang dikirim
MAX_IMG = 5 * 1024 * 1024  # batas ukuran gambar (byte)
MAX_HIST_CHARS = 60000  # riwayat lebih panjang dari ini dipangkas saat dikirim
RETRY_CODES = (408, 425, 429, 500, 502, 503, 504)
PERSONAS = {
    "umum": DEFAULT_SYSTEM,
    "coder": DEFAULT_SYSTEM + " Fokus membantu coding: beri kode lengkap yang bisa langsung dijalankan, "
             "lalu jelaskan singkat bagian pentingnya.",
    "guru": DEFAULT_SYSTEM + " Berperan sebagai guru sabar: jelaskan langkah demi langkah dengan contoh sederhana, "
            "dan cek apakah penjelasannya sudah jelas.",
    "santai": DEFAULT_SYSTEM + " Ngobrol santai seperti teman: bahasa gaul yang sopan, singkat, boleh bercanda.",
    "penerjemah": DEFAULT_SYSTEM + " Tugas utama: menerjemahkan. Kalau teks berbahasa Indonesia, terjemahkan ke Inggris; "
                  "selain itu terjemahkan ke Indonesia. Beri terjemahannya saja, tanpa penjelasan tambahan.",
}

# ---------- warna & tema ----------
def c(code, text):
    return f"\033[{code}m{text}\033[0m"

def c256(n, text):
    return f"\033[38;5;{n}m{text}\033[0m"

BOLD, DIM, CYAN, GREEN, YELLOW, RED = "1", "2", "36", "32", "33", "31"

THEMES = {
    "laut":   {"grad": [51, 45, 39, 33, 27, 21], "accent": 45, "edge": 39},
    "api":    {"grad": [226, 220, 214, 208, 202, 196], "accent": 208, "edge": 202},
    "hutan":  {"grad": [154, 118, 82, 46, 40, 34], "accent": 82, "edge": 40},
    "ungu":   {"grad": [219, 213, 177, 141, 135, 99], "accent": 177, "edge": 141},
    "sakura": {"grad": [225, 219, 213, 207, 201, 165], "accent": 213, "edge": 207},
    "mono":   {"grad": [255, 252, 249, 246, 243, 240], "accent": 250, "edge": 244},
}
T = dict(THEMES["laut"])


def set_theme(name):
    T.clear()
    T.update(THEMES[name])


def acc(text):
    return c256(T["accent"], text)


def tw():
    return shutil.get_terminal_size((40, 20)).columns


LOGO = [
    "███████╗███████╗████████╗ █████╗ ",
    "╚══███╔╝██╔════╝╚══██╔══╝██╔══██╗",
    "  ███╔╝ █████╗     ██║   ███████║",
    " ███╔╝  ██╔══╝     ██║   ██╔══██║",
    "███████╗███████╗   ██║   ██║  ██║",
    "╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝",
]


def panel(rows, width, delay=0.0):
    """Kotak info rounded. rows = [(label, nilai)]."""
    inner = width - 4
    edge = T["edge"]

    def out(s):
        print("  " + s)
        if delay:
            sys.stdout.flush()
            time.sleep(delay)

    out(c256(edge, "╭" + "─" * (width - 2) + "╮"))
    for label, val in rows:
        if len(label) + len(val) > inner:
            val = val[: max(inner - len(label) - 1, 1)] + "…"
        pad = " " * (inner - len(label) - len(val))
        out(c256(edge, "│ ") + c(DIM, label) + val + pad + c256(edge, " │"))
    out(c256(edge, "╰" + "─" * (width - 2) + "╯"))


def banner(model, web=False, mem=0, theme="laut", anim=False, persona="umum"):
    anim = anim and sys.stdout.isatty()
    os.system("clear")
    print()
    for line, col in zip(LOGO, T["grad"]):
        print("  " + c256(col, line))
        if anim:
            sys.stdout.flush()
            time.sleep(0.07)
    print("  " + c(BOLD, "Z E T A   A I") + c(DIM, f"   v{VERSION}"))
    print()
    width = max(min(33, tw() - 4), 24)
    panel([
        ("pembuat  ", "Jevon"),
        ("model    ", model),
        ("web      ", "nyala" if web else "mati"),
        ("memori   ", f"{mem} catatan"),
        ("tema     ", theme),
        ("persona  ", persona),
        ("bantuan  ", "/help · @file · !cmd"),
    ], width, 0.04 if anim else 0.0)
    print()


# ---------- config ----------
def load_cfg():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


CFG_LOCK = threading.Lock()


def save_cfg(cfg):
    """Simpan config secara atomik (aman dipakai bersama server admin)."""
    with CFG_LOCK:
        os.makedirs(DIR, exist_ok=True)
        tmp = CFG_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(dict(cfg), f)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, CFG_FILE)


def get_key(cfg, force=False):
    key = os.environ.get("OPENROUTER_API_KEY") or cfg.get("api_key") or DEFAULT_KEY
    if key and not force:
        return key
    print(c(YELLOW, "Masukkan API key OpenRouter (tidak akan terlihat saat diketik)."))
    print(c(DIM, "Dapatkan di openrouter.ai/keys"))
    key = getpass.getpass("API key: ").strip()
    if not key:
        print(c(RED, "API key kosong. Keluar."))
        sys.exit(1)
    cfg["api_key"] = key
    save_cfg(cfg)
    return key


def full_system(system, mem):
    """Gabungkan instruksi dasar dengan catatan permanen (/memory)."""
    if not mem:
        return system
    notes = "\n".join(f"- {m}" for m in mem)
    return system + "\n\nCatatan permanen dari pengguna (ingat dan patuhi):\n" + notes


# ---------- animasi loading ----------
class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label):
        self.label = label
        self.evt = threading.Event()
        self.thread = None
        self.t0 = 0.0

    def start(self):
        self.t0 = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        i = 0
        while not self.evt.is_set():
            el = time.time() - self.t0
            sys.stdout.write(
                "\r\033[K" + acc(self.FRAMES[i % len(self.FRAMES)])
                + " " + c(DIM, f"{self.label} {el:.0f}s")
            )
            sys.stdout.flush()
            i += 1
            self.evt.wait(0.1)

    def stop(self):
        if self.thread is None:
            return
        self.evt.set()
        self.thread.join()
        self.thread = None
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


# ---------- tampilan markdown (streaming huruf demi huruf) ----------
def inline_md(t):
    """Markdown inline untuk teks utuh (dipakai di sel tabel)."""
    t = re.sub(r"\*\*(.+?)\*\*", lambda m: "\033[1m" + m.group(1) + "\033[22m", t)
    t = re.sub(r"(?<![*\w])\*([^*\s][^*]*?)\*(?![*\w])",
               lambda m: "\033[3m" + m.group(1) + "\033[23m", t)
    t = re.sub(r"`([^`]+)`", lambda m: "\033[33m" + m.group(1) + "\033[39m", t)
    return t


def plain_md(t):
    return re.sub(r"\*\*|`", "", t)


class MD:
    """Render markdown sambil streaming. Teks tampil per huruf; awal baris
    ditahan sebentar hanya kalau perlu untuk mengenali judul/daftar/kode/tabel."""

    def __init__(self):
        self.code = False
        self.table = []
        self.hold = ""      # awal baris yang belum bisa dikenali
        self.mode = None    # para head bullet num quote code row fence
        self.full = ""      # isi baris yang dikumpulkan utuh (row, fence)
        self.bold = self.ital = self.incode = False
        self.carry = ""

    # -- util --
    def w(self, s):
        sys.stdout.write(s)

    def gutter(self):
        return c256(T["accent"], "│") + " "

    def begin_line(self):
        if self.table:
            self.render_table()
        self.w(self.gutter())

    # -- masukan --
    def feed(self, text):
        for ch in text:
            if ch == "\r":
                continue
            if ch == "\n":
                self.end_line()
            elif self.mode is None:
                self.hold += ch
                self.decide()
            elif self.mode == "code":
                self.w(ch)
            elif self.mode in ("row", "fence"):
                self.full += ch
            else:
                self.inline_char(ch)
        sys.stdout.flush()

    def flush(self):
        if self.hold or self.mode is not None:
            self.end_line()
        if self.table:
            self.render_table()
        sys.stdout.flush()

    # -- inline: **tebal**, *miring*, `kode` --
    def inline_char(self, ch):
        if self.carry:
            self.carry = ""
            if ch == "*":
                self.bold = not self.bold
                self.w("\033[1m" if self.bold else "\033[22m")
                return
            if self.ital:
                self.ital = False
                self.w("\033[23m")
            elif ch.isspace():
                self.w("*")
            else:
                self.ital = True
                self.w("\033[3m")
        if self.incode:
            if ch == "`":
                self.incode = False
                self.w("\033[39m")
            else:
                self.w(ch)
        elif ch == "`":
            self.incode = True
            self.w("\033[33m")
        elif ch == "*":
            self.carry = "*"
        else:
            self.w(ch)

    def feed_inline(self, text):
        for ch in text:
            self.inline_char(ch)

    def finish_inline(self):
        if self.carry == "*":
            self.w("\033[23m" if self.ital else "*")  # * penutup miring di akhir baris
        self.w("\033[0m\n")

    # -- mengenali jenis baris --
    def para(self, text):
        self.begin_line()
        self.mode = "para"
        self.hold = ""
        self.feed_inline(text)

    def start(self, mode, prefix, rest):
        self.begin_line()
        self.w(prefix)
        self.mode = mode
        self.hold = ""
        self.feed_inline(rest)

    def decide(self):
        h = self.hold
        s = h.lstrip()
        if self.code:
            if s == "" or ("```".startswith(s) and len(s) < 3):
                return
            if s.startswith("```"):
                self.mode, self.full, self.hold = "fence", h, ""
            else:
                self.begin_line()
                self.w("\033[32m" + h)
                self.mode, self.hold = "code", ""
            return
        if not s:
            return
        indent = h[: len(h) - len(s)]
        c0 = s[0]
        if c0 == "|":
            self.mode, self.full, self.hold = "row", h, ""
        elif c0 == "`":
            if len(s) < 3 and "```".startswith(s):
                return
            if s.startswith("```"):
                self.mode, self.full, self.hold = "fence", h, ""
            else:
                self.para(h)
        elif c0 == "#":
            n = len(s) - len(s.lstrip("#"))
            rest = s[n:]
            if n > 6:
                self.para(h)
            elif rest == "":
                return
            elif rest[0] == " ":
                style = "\033[1;96m▌ " if n == 1 else "\033[1;36m"
                self.start("head", indent + style, rest[1:])
            else:
                self.para(h)
        elif c0 in "-*_":
            if len(s) == 1:
                return
            if s[1] == " " and c0 in "-*":
                self.start("bullet", indent + acc("•") + " ", s[2:])
            elif set(s) == {c0}:
                return  # garis pemisah (---) atau awal **tebal**
            else:
                self.para(h)
        elif c0.isdigit():
            n = len(s) - len(s.lstrip("0123456789"))
            rest = s[n:]
            if rest == "":
                return
            if rest[0] in ".)":
                if len(rest) == 1:
                    return
                if rest[1] == " ":
                    self.start("num", indent + c(CYAN, s[: n + 1]) + " ", rest[2:])
                else:
                    self.para(h)
            else:
                self.para(h)
        elif c0 == ">":
            if len(s) == 1:
                return
            rest = s[2:] if s[1] == " " else s[1:]
            self.start("quote", indent + c(DIM, "│ "), rest)
        else:
            self.para(h)

    # -- akhir baris --
    def end_line(self):
        m = self.mode
        if m is None:
            h = self.hold
            s = h.strip()
            if self.code:
                if s.startswith("```"):
                    self.code = False
                    self.begin_line()
                    self.w(c(DIM, "┄┄┄") + "\n")
                else:
                    self.begin_line()
                    self.w(c(GREEN, h) + "\n")
            elif s == "":
                self.begin_line()
                self.w("\n")
            elif re.fullmatch(r"([-*_])\1{2,}", s):
                self.begin_line()
                self.w(c(DIM, "─" * min(tw() - 6, 36)) + "\n")
            else:
                self.para(h)
                self.finish_inline()
        elif m == "row":
            s = self.full.strip()
            if len(s) > 1 and s.endswith("|"):
                self.table.append(s)
            else:
                self.para(self.full)
                self.finish_inline()
        elif m == "fence":
            s = self.full.strip()
            self.begin_line()
            if self.code:
                self.w(c(DIM, "┄┄┄") + "\n")
            else:
                self.w(c(DIM, "┄┄┄ " + s[3:].strip()) + "\n")
            self.code = not self.code
        elif m == "code":
            self.w("\033[0m\n")
        else:
            if m == "head":
                self.w("\033[0m")
            self.finish_inline()
        self.mode = None
        self.hold = ""
        self.full = ""
        self.bold = self.ital = self.incode = False
        self.carry = ""

    def render_table(self):
        rows = []
        for r in self.table:
            cells = [x.strip() for x in r.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", x) or x == "" for x in cells) and any(cells):
                continue
            rows.append(cells)
        self.table = []
        if not rows:
            return
        n = max(len(r) for r in rows)
        for r in rows:
            r += [""] * (n - len(r))
        widths = [max(len(plain_md(r[i])) for r in rows) for i in range(n)]
        fits = sum(widths) + 3 * (n - 1) <= tw() - 4
        for ri, r in enumerate(rows):
            if fits:
                cells = [inline_md(r[i]) + " " * (widths[i] - len(plain_md(r[i]))) for i in range(n)]
            else:
                cells = [inline_md(x) for x in r]
            if ri == 0:
                cells = [c(BOLD, x) for x in cells]
            self.w(self.gutter() + c(DIM, " │ ").join(cells) + "\n")
            if ri == 0 and fits:
                self.w(self.gutter() + c(DIM, "─┼─".join("─" * wd for wd in widths)) + "\n")


# ---------- API (streaming) ----------
def msg_len(m):
    body = m["content"]
    if isinstance(body, list):
        return sum(len(p.get("text", "")) for p in body if p.get("type") == "text")
    return len(body)


def trim_history(messages):
    """Buang pesan paling lama kalau riwayat kepanjangan. Return (pesan, jumlah_dibuang)."""
    total = sum(msg_len(m) for m in messages)
    start = 0
    while total > MAX_HIST_CHARS and start < len(messages) - 1:
        total -= msg_len(messages[start])
        start += 1
    while 0 < start < len(messages) - 1 and messages[start]["role"] != "user":
        start += 1
    return messages[start:], start


def stream_reply(key, model, system, messages, web=False, state=None):
    state = state if state is not None else {}
    sendm, cut = trim_history(messages)
    payload = {
        "model": model,
        "max_tokens": 2048,
        "messages": [{"role": "system", "content": system}] + sendm,
        "stream": True,
        "usage": {"include": True},
    }
    if cut:
        print(c(DIM, f"(riwayat lama dipangkas: {cut} pesan; /compact untuk meringkas)"))
    if web:
        payload["plugins"] = [{"id": "web", "max_results": 5}]
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "X-Title": "Zeta AI",
        },
    )
    out = state.setdefault("out", [])
    state["started"] = False
    sources = []
    md = MD()
    first = True
    actual = None
    usage = {}
    spin = Spinner("mikir + cari web" if web else "mikir")
    t0 = time.time()
    spin.start()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue  # abaikan komentar keep-alive OpenRouter
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if "error" in ev:
                    err = ev["error"]
                    raise RuntimeError(err.get("message", "error") if isinstance(err, dict) else str(err))
                if ev.get("model"):
                    actual = ev["model"]
                if isinstance(ev.get("usage"), dict):
                    usage = ev["usage"]
                for ch in ev.get("choices", []):
                    delta = ch.get("delta") or {}
                    for a in delta.get("annotations") or []:
                        uc = a.get("url_citation") or {}
                        if uc.get("url") and uc["url"] not in [s[0] for s in sources]:
                            sources.append((uc["url"], uc.get("title") or ""))
                    t = delta.get("content")
                    if t:
                        if first:
                            spin.stop()
                            sys.stdout.write(acc("╭─ ") + c(BOLD, "zeta") + "\n")
                            first = False
                            state["started"] = True
                        out.append(t)
                        md.feed(t)
    finally:
        spin.stop()
        md.flush()  # tampilkan sisa teks walau koneksi putus di tengah
    if first:
        print(c(DIM, "(jawaban kosong, coba ganti model dengan /model)"))
    else:
        if sources:
            print(md.gutter() + c(DIM, "Sumber:"))
            for i, (u, ttl) in enumerate(sources[:5], 1):
                print(md.gutter() + c(DIM, f"{i}. {ttl[:40]} {u}" if ttl else f"{i}. {u}"))
        parts = [f"{time.time() - t0:.1f}s"]
        if actual:
            parts.append(actual)
        if usage.get("total_tokens"):
            parts.append(f"{usage['total_tokens']} token")
        try:
            if usage.get("cost"):
                parts.append(f"${float(usage['cost']):.4f}")
        except (TypeError, ValueError):
            pass
        print(acc("╰─ ") + c(DIM, " · ".join(parts)))
    return "".join(out)


def list_models(key, keyword=""):
    req = urllib.request.Request(MODELS_URL, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    ids = sorted(m["id"] for m in data.get("data", []))
    if keyword:
        ids = [i for i in ids if keyword.lower() in i.lower()]
    return ids


def explain_http_error(e):
    try:
        msg = json.loads(e.read().decode()).get("error", {}).get("message", "")
    except Exception:
        msg = ""
    hints = {
        401: "API key salah/dicabut. Ganti dengan /key",
        402: "Kredit OpenRouter habis. Isi di openrouter.ai/credits",
        403: "Akses ditolak untuk key/model ini.",
        404: "Model tidak ditemukan. Cari dengan /models <kata>",
        429: "Kena rate limit. Tunggu sebentar.",
    }
    return f"HTTP {e.code}: {hints.get(e.code, msg or e.reason)}"


def respond(key, model, system, messages, web):
    """Minta jawaban untuk riwayat saat ini. True kalau berhasil."""
    for attempt in range(1, 4):
        state = {"out": [], "started": False}
        problem, retry, stopped = "", False, False
        try:
            reply = stream_reply(key, model, system, messages, web, state)
        except urllib.error.HTTPError as e:
            problem, retry = explain_http_error(e), e.code in RETRY_CODES
        except urllib.error.URLError:
            problem, retry = "Tidak ada koneksi internet.", True
        except KeyboardInterrupt:
            problem, stopped = "(dihentikan)", True
        except Exception as e:
            problem = f"Error: {e}"
        else:
            print()
            messages.append({"role": "assistant", "content": reply})
            return True

        partial = "".join(state["out"])
        if partial:  # sebagian jawaban sudah tampil: simpan, jangan dibuang
            print(c(DIM if stopped else RED, problem))
            print(c(DIM, "(jawaban sebagian disimpan, /retry untuk ulang)") + "\n")
            messages.append({"role": "assistant", "content": partial})
            return True
        if retry and attempt < 3:
            wait = 2 * attempt
            print(c(DIM, f"{problem}  Coba lagi {attempt}/2 dalam {wait} detik..."))
            try:
                time.sleep(wait)
            except KeyboardInterrupt:
                print(c(DIM, "(dibatalkan)") + "\n")
                return False
            continue
        print(c(DIM if stopped else RED, problem) + "\n")
        return False
    return False


def fetch_url(url):
    """Ambil halaman web dan ubah jadi teks polos."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Zeta AI)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read(1500000)
        ctype = resp.headers.get("Content-Type", "")
    low = ctype.lower()
    if low.startswith(("image/", "audio/", "video/")) or "pdf" in low or "zip" in low:
        raise ValueError("bukan halaman teks")
    m = re.search(r"charset=([\w-]+)", ctype)
    try:
        text = raw.decode(m.group(1) if m else "utf-8", "ignore")
    except LookupError:
        text = raw.decode("utf-8", "ignore")
    if "html" in low or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"(?s)<!--.*?-->", " ", text)
        text = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = text.strip()
    if not text:
        raise ValueError("halaman kosong")
    return text[:MAX_FILE] + ("\n(dipotong)" if len(text) > MAX_FILE else "")


def compact_history(key, model, messages):
    """Ringkas riwayat obrolan jadi satu catatan singkat (tanpa streaming)."""
    ask = trim_history(messages)[0] + [{
        "role": "user",
        "content": "Ringkas seluruh obrolan di atas jadi poin-poin singkat (fakta, keputusan, "
                   "konteks penting) dalam bahasa yang sama, supaya bisa dilanjutkan tanpa riwayat penuh.",
    }]
    payload = {"model": model, "max_tokens": 1024,
               "messages": [{"role": "system", "content": DEFAULT_SYSTEM}] + ask}
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}", "X-Title": "Zeta AI"},
    )
    spin = Spinner("meringkas")
    spin.start()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    finally:
        spin.stop()
    summary = (data["choices"][0]["message"].get("content") or "").strip()
    if not summary:
        raise RuntimeError("ringkasan kosong")
    return [
        {"role": "user", "content": "[Ringkasan obrolan sebelumnya]\n" + summary},
        {"role": "assistant", "content": "Oke, saya paham konteksnya. Lanjut."},
    ]


# ---------- file, gambar, shell ----------
def build_message(text, pending):
    """Proses @file di pesan. Return (isi_untuk_API, isi_untuk_riwayat, catatan)."""
    extra = ""
    images = []
    notes = []
    for tok in text.split():
        if len(tok) < 2 or not tok.startswith("@"):
            continue
        if tok[1:].lower().startswith(("http://", "https://")):
            url = tok[1:].rstrip(",;:!?)")
            try:
                page = fetch_url(url)
                extra += f"\n\n[Halaman web: {url}]\n```\n{page}\n```"
                notes.append(c(GREEN, f"  + web: {url[:50]}"))
            except Exception as e:
                notes.append(c(RED, f"  gagal buka {url[:50]}: {e}"))
            continue
        path = os.path.expanduser(tok[1:].rstrip(",;:!?"))
        if not os.path.isfile(path):
            notes.append(c(RED, f"  file tidak ditemukan: {tok[1:]}"))
            continue
        name = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in IMG_TYPES:
                if os.path.getsize(path) > MAX_IMG:
                    notes.append(c(RED, f"  gambar terlalu besar (maks 5MB): {name}"))
                    continue
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                images.append((name, f"data:{IMG_TYPES[ext]};base64,{b64}"))
                notes.append(c(GREEN, f"  + gambar: {name}"))
            else:
                with open(path, "rb") as f:
                    raw = f.read(MAX_FILE + 1)
                if b"\0" in raw[:2048]:
                    notes.append(c(RED, f"  bukan file teks: {name}"))
                    continue
                body = raw[:MAX_FILE].decode("utf-8", "ignore")
                cut = len(raw) > MAX_FILE
                extra += f"\n\n[File: {name}]\n```\n{body}\n```"
                if cut:
                    extra += "\n(isi file dipotong karena terlalu panjang)"
                notes.append(c(GREEN, f"  + file: {name}" + (" (dipotong)" if cut else "")))
        except OSError as e:
            notes.append(c(RED, f"  gagal baca {name}: {e}"))

    prefix = "\n\n".join(pending) + "\n\n" if pending else ""
    full = prefix + text + extra
    if not images:
        return full, full, notes
    parts = [{"type": "text", "text": full}]
    for _name, url in images:
        parts.append({"type": "image_url", "image_url": {"url": url}})
    hist = full + "\n[gambar terlampir: " + ", ".join(n for n, _ in images) + "]"
    return parts, hist, notes


def run_shell(cmd, pending):
    if not cmd:
        print(c(DIM, "Pakai: !perintah   (contoh: !ls  atau  !cd ~/storage)"))
        return
    if cmd == "cd" or cmd.startswith("cd "):
        target = os.path.expanduser(cmd[2:].strip() or "~")
        try:
            os.chdir(target)
            print(c(GREEN, os.getcwd()))
        except OSError as e:
            print(c(RED, str(e)))
        return
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           errors="ignore", timeout=60)
        out = (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        out = "(timeout 60 detik)"
    print(out or c(DIM, "(tidak ada output)"))
    pending.append(f"[Hasil perintah `{cmd}` di {os.getcwd()}]\n```\n{out[:4000]}\n```")
    print(c(DIM, "  (hasil ikut dikirim ke AI di pesan berikutnya)"))


# ---------- sesi obrolan ----------
def new_sid():
    return time.strftime("%Y%m%d-%H%M%S")


def sess_path(sid, ext="json"):
    return os.path.join(CHAT_DIR, f"chat-{sid}.{ext}")


def save_session(sid, messages, model):
    """Simpan otomatis supaya obrolan bisa dilanjutkan lewat /load."""
    if not messages:
        return
    first = next((m["content"] for m in messages if m["role"] == "user"), "")
    title = " ".join(str(first).split())[:50]
    try:
        os.makedirs(CHAT_DIR, exist_ok=True)
        with open(sess_path(sid), "w") as f:
            json.dump({"id": sid, "title": title, "model": model,
                       "updated": time.time(), "messages": messages}, f, ensure_ascii=False)
    except OSError:
        pass


def list_sessions(limit=10):
    try:
        names = sorted((n for n in os.listdir(CHAT_DIR)
                        if n.startswith("chat-") and n.endswith(".json")), reverse=True)
    except OSError:
        return []
    out = []
    for n in names[:limit]:
        try:
            with open(os.path.join(CHAT_DIR, n)) as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out


def show_sessions():
    sess = list_sessions()
    if not sess:
        print(c(DIM, "Belum ada obrolan tersimpan."))
        return
    for i, d in enumerate(sess, 1):
        when = time.strftime("%d/%m %H:%M", time.localtime(d.get("updated", 0)))
        print(f"  {acc(str(i) + '.')} {c(DIM, when)}  {d.get('title', '')}")
    print(c(DIM, "  buka dengan: /load <nomor>"))


def export_chat(messages, sid):
    os.makedirs(CHAT_DIR, exist_ok=True)
    path = sess_path(sid, "md")
    with open(path, "w") as f:
        for m in messages:
            who = "Kamu" if m["role"] == "user" else "Zeta"
            f.write(f"## {who}\n\n{m['content']}\n\n")
    return path


# ---------- server admin (web, hanya bisa dibuka dari perangkat ini) ----------
# Dashboard untuk mengatur Zeta lewat browser: http://127.0.0.1:8787
# Aman secara bawaan: hanya localhost, wajib password (PBKDF2), sesi acak,
# proteksi CSRF + cek Host, batas percobaan login, dan tanpa fitur eksekusi perintah.
ADMIN_PORT = 8787
ADMIN_LOG = os.path.join(DIR, "admin.log")
ADMIN = {"server": None, "ctx": None}
SID_RE = re.compile(r"\d{8}-\d{6}")
ADMIN_MSG = {
    "saved": "Pengaturan tersimpan.",
    "key": "API key diperbarui.",
    "mem_add": "Catatan ditambahkan.",
    "mem_del": "Catatan dihapus.",
    "sess_del": "Obrolan dihapus.",
    "pw": "Password diganti, silakan login lagi.",
    "bad": "Input tidak valid.",
    "pwbad": "Password lama salah atau password baru tidak valid (min 8 karakter, harus sama).",
    "wrong": "Password salah.",
    "locked": "Terlalu banyak percobaan gagal. Tunggu 5 menit.",
    "pwenv": "Password dikelola lewat environment variable server, tidak bisa diganti dari sini.",
    "busy": "Chat sedang memproses permintaan lain, coba lagi sebentar.",
}
ADMIN_ERR = ("bad", "pwbad", "wrong", "locked", "pwenv", "busy")
ADMIN_CSS = (
    ":root{color-scheme:dark}*{box-sizing:border-box}"
    "body{margin:0;background:#0b0f1a;color:#e6edf7;font:15px/1.5 system-ui,sans-serif}"
    "main{max-width:720px;margin:0 auto;padding:16px}"
    "h1{font-size:22px;margin:8px 0 16px}"
    "h2{font-size:13px;margin:0 0 10px;color:#7dd3fc;text-transform:uppercase;letter-spacing:.08em}"
    ".card{background:#121829;border:1px solid #1f2a44;border-radius:14px;padding:14px;margin-bottom:14px}"
    "label{display:block;font-size:13px;color:#9fb0cc;margin:10px 0 4px}"
    "input,select,textarea{width:100%;background:#0b1222;color:#e6edf7;border:1px solid #2a3858;"
    "border-radius:10px;padding:10px;font:inherit}"
    "input[type=checkbox]{width:auto;margin-right:8px}"
    "button{background:#2dd4ff;color:#04111a;border:0;border-radius:10px;padding:10px 14px;"
    "font:inherit;font-weight:600;margin-top:12px}"
    "button.danger{background:#ff6b6b;color:#1a0505}button.ghost{background:#1f2a44;color:#e6edf7}"
    "button.sm{padding:6px 10px;margin:0}"
    ".row{display:flex;gap:10px;align-items:center;justify-content:space-between;"
    "padding:8px 0;border-top:1px solid #1b2540}.row:first-of-type{border-top:0}"
    ".muted{color:#8394b3;font-size:13px}a{color:#7dd3fc}"
    ".flash{background:#0f2a1f;border:1px solid #1f6b4a;border-radius:10px;padding:10px;margin-bottom:14px}"
    ".flash.err{background:#2a1212;border-color:#7a2a2a}"
    "pre{white-space:pre-wrap;word-break:break-word;margin:0;font:13px/1.45 ui-monospace,monospace}"
    ".top{display:flex;justify-content:space-between;align-items:center}"
)
hx = html.escape


class AdminCtx:
    def __init__(self, cfg, public_host="", env_pw=False):
        self.cfg = cfg
        self.lock = threading.RLock()  # ubah cfg lalu save_cfg (yang punya kunci sendiri)
        self.port = 0
        self.sessions = {}  # token -> {"csrf": ..., "exp": ...}
        self.fails = {}     # ip -> waktu login gagal
        self.public_host = public_host.strip().lower()
        self.secure = bool(self.public_host)  # mode publik: cookie Secure + HSTS
        self.env_pw = env_pw  # password dikelola lewat environment
        self.chats = {}     # token sesi -> riwayat chat web
        self.chat_lock = threading.Lock()


def admin_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return {"salt": salt.hex(), "hash": digest.hex()}


def admin_check(cfg, password):
    rec = cfg.get("admin") or {}
    try:
        salt = bytes.fromhex(rec["salt"])
        want = bytes.fromhex(rec["hash"])
    except (KeyError, ValueError, TypeError):
        return False
    got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return hmac.compare_digest(got, want)


def admin_log(event):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(event).split())[:200] + "\n"
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(ADMIN_LOG, "a") as f:
            f.write(line)
        os.chmod(ADMIN_LOG, 0o600)
    except OSError:
        pass


def admin_log_tail(n=20):
    try:
        with open(ADMIN_LOG) as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


def admin_page(title, body):
    return ("<!doctype html><html lang=id><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>" + hx(title) + "</title><style>" + ADMIN_CSS + "</style></head>"
            "<body><main>" + body + "</main></body></html>")


def flash_html(code):
    msg = ADMIN_MSG.get(code)
    if not msg:
        return ""
    cls = "flash err" if code in ADMIN_ERR else "flash"
    return f'<div class="{cls}">{hx(msg)}</div>'


def csrf_form(action, csrf, inner):
    return (f'<form method="post" action="{action}">'
            f'<input type="hidden" name="csrf" value="{hx(csrf)}">{inner}</form>')


def admin_login_page(code=""):
    body = ("<h1>Zeta Admin</h1>" + flash_html(code)
            + '<div class="card"><form method="post" action="/login">'
            '<label>Password admin</label>'
            '<input type="password" name="password" autocomplete="current-password" autofocus required>'
            '<button type="submit">Masuk</button></form></div>'
            '<p class="muted">Halaman ini hanya bisa dibuka dari perangkat ini (localhost).</p>')
    return admin_page("Zeta Admin", body)


def admin_dashboard(ctx, csrf, code=""):
    cfg = ctx.cfg
    with ctx.lock:
        model = str(cfg.get("model", DEFAULT_MODEL))
        persona = str(cfg.get("persona", "umum"))
        theme = str(cfg.get("theme", "laut"))
        web = bool(cfg.get("web", False))
        auto = cfg.get("auto", DEFAULT_AUTO)
        system = str(cfg.get("system", DEFAULT_SYSTEM))
        mem = [str(m) for m in cfg.get("memory", [])]
        env_key = os.environ.get("OPENROUTER_API_KEY")
        keyval = env_key or cfg.get("api_key") or ""
        keysrc = "environment" if env_key else "tersimpan di config" if keyval else "belum diatur"
    sess = list_sessions(30)

    def opts(names, cur):
        return "".join(
            f'<option value="{hx(n)}"{" selected" if n == cur else ""}>{hx(n)}</option>' for n in names)

    def row(label, value):
        return f'<div class="row"><span class="muted">{hx(label)}</span><b>{hx(str(value))}</b></div>'

    status = ('<div class="card"><h2>Status</h2>'
              + row("Versi", VERSION) + row("Repo update", cfg.get("update_repo") or "belum diatur")
              + row("Model", model) + row("Persona", persona)
              + row("Cari web", "nyala" if web else "mati") + row("Tema", theme)
              + row("Catatan memori", len(mem)) + row("Obrolan tersimpan", len(sess))
              + row("API key", (("••••" + keyval[-4:]) if keyval else "—") + f" ({keysrc})") + '</div>')

    settings = ('<div class="card"><h2>Pengaturan</h2>' + csrf_form("/settings", csrf, (
        f'<label>Model</label><input name="model" value="{hx(model)}" maxlength="100" required>'
        f'<label>Persona</label><select name="persona">{opts(list(PERSONAS) + ["kustom"], persona)}</select>'
        f'<label>Instruksi sistem (dipakai kalau persona = kustom)</label>'
        f'<textarea name="system" rows="5" maxlength="4000">{hx(system)}</textarea>'
        f'<label>Tema terminal</label><select name="theme">{opts(list(THEMES), theme)}</select>'
        f'<label>Auto-kirim (detik, 0 = mati)</label>'
        f'<input name="auto" type="number" min="0" max="30" step="0.5" value="{hx(str(auto))}">'
        f'<label><input type="checkbox" name="web"{" checked" if web else ""}>Izinkan AI cari web</label>'
        '<button type="submit">Simpan</button>')) + '</div>')

    keyform = ('<div class="card"><h2>API key OpenRouter</h2>' + csrf_form("/key", csrf, (
        '<label>Key baru (tidak pernah ditampilkan penuh)</label>'
        '<input type="password" name="api_key" autocomplete="off" placeholder="sk-or-v1-...">'
        '<button type="submit">Ganti key</button>')) + '</div>')

    mem_rows = ""
    for i, m in enumerate(mem, 1):
        mem_rows += ('<div class="row"><span>' + hx(m) + '</span>'
                     + csrf_form("/memory/del", csrf,
                                 f'<input type="hidden" name="n" value="{i}">'
                                 '<button class="danger sm" type="submit">Hapus</button>')
                     + '</div>')
    memory = ('<div class="card"><h2>Catatan permanen</h2>'
              + (mem_rows or '<p class="muted">Belum ada catatan.</p>')
              + csrf_form("/memory/add", csrf,
                          '<label>Catatan baru</label><input name="text" maxlength="500" required>'
                          '<button type="submit">Tambah</button>') + '</div>')

    sess_rows = ""
    for d in sess:
        sid = str(d.get("id", ""))
        if not SID_RE.fullmatch(sid):
            continue
        when = time.strftime("%d/%m %H:%M", time.localtime(d.get("updated", 0)))
        title = str(d.get("title", "")) or "(tanpa judul)"
        sess_rows += ('<div class="row"><div><a href="/session?id=' + sid + '">' + hx(title) + '</a>'
                      f'<div class="muted">{hx(when)} · {len(d.get("messages", []))} pesan</div></div>'
                      + csrf_form("/session/del", csrf,
                                  f'<input type="hidden" name="id" value="{sid}">'
                                  '<button class="danger sm" type="submit">Hapus</button>')
                      + '</div>')
    sessions = ('<div class="card"><h2>Obrolan tersimpan</h2>'
                + (sess_rows or '<p class="muted">Belum ada obrolan.</p>') + '</div>')

    pwform = ('<div class="card"><h2>Ganti password admin</h2>' + csrf_form("/password", csrf, (
        '<label>Password lama</label><input type="password" name="old" autocomplete="current-password" required>'
        '<label>Password baru (min 8 karakter)</label>'
        '<input type="password" name="new" autocomplete="new-password" minlength="8" required>'
        '<label>Ulangi password baru</label>'
        '<input type="password" name="again" autocomplete="new-password" minlength="8" required>'
        '<button type="submit">Ganti password</button>')) + '</div>')

    if ctx.env_pw:
        pwform = ('<div class="card"><h2>Password admin</h2><p class="muted">'
                  'Dikelola lewat environment variable ZETA_ADMIN_PASSWORD.</p></div>')
    log = ('<div class="card"><h2>Aktivitas admin</h2><pre>'
           + hx("\n".join(admin_log_tail(20)) or "(kosong)") + '</pre></div>')

    head = ('<div class="top"><h1>Zeta Admin</h1>'
            + csrf_form("/logout", csrf, '<button class="ghost sm" type="submit">Keluar</button>') + '</div>')
    return admin_page("Zeta Admin", head + flash_html(code) + '<p><a href="/chat">Chat web →</a></p>' + status + settings + keyform
                      + memory + sessions + pwform + log)


def admin_session_page(sid):
    if not SID_RE.fullmatch(sid):
        return None
    try:
        with open(sess_path(sid)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    body = '<p><a href="/">← kembali</a></p><h1>' + hx(str(d.get("title", "")) or "Obrolan") + "</h1>"
    for m in d.get("messages", []):
        who = "Kamu" if m.get("role") == "user" else "Zeta"
        text = m.get("content", "")
        text = text if isinstance(text, str) else str(text)
        body += f'<div class="card"><h2>{who}</h2><pre>{hx(text[:6000])}</pre></div>'
    return admin_page("Obrolan", body)


def web_ask(cfg, messages):
    """Satu kali tanya ke OpenRouter tanpa streaming (dipakai chat web)."""
    key = os.environ.get("OPENROUTER_API_KEY") or cfg.get("api_key")
    if not key:
        raise RuntimeError("API key belum diatur")
    sendm = trim_history(messages)[0]
    system = full_system(cfg.get("system", DEFAULT_SYSTEM), cfg.get("memory", []))
    payload = {"model": cfg.get("model", DEFAULT_MODEL), "max_tokens": 2048,
               "messages": [{"role": "system", "content": system}] + sendm}
    if cfg.get("web"):
        payload["plugins"] = [{"id": "web", "max_results": 5}]
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}", "X-Title": "Zeta AI"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    text = (data["choices"][0]["message"].get("content") or "").strip()
    if not text:
        raise RuntimeError("jawaban kosong")
    return text


def admin_chat_page(history, csrf, code=""):
    body = ('<div class="top"><h1>Chat web</h1><a href="/">← kembali</a></div>' + flash_html(code))
    if not history:
        body += '<p class="muted">Mulai percakapan di bawah. Riwayat ini hanya berlaku untuk sesi login ini.</p>'
    for m in history:
        who = {"user": "Kamu", "assistant": "Zeta", "error": "Error"}.get(m["role"], "?")
        body += f'<div class="card"><h2>{who}</h2><pre>{hx(str(m["content"])[:8000])}</pre></div>'
    body += csrf_form("/chat", csrf,
                      '<label>Pesan</label><textarea name="text" rows="4" maxlength="8000" required autofocus>'
                      '</textarea><button type="submit">Kirim</button>')
    body += csrf_form("/chat/clear", csrf, '<button class="ghost sm" type="submit">Hapus riwayat chat</button>')
    return admin_page("Chat web", body)


class AdminHandler(http.server.BaseHTTPRequestHandler):
    ctx = None  # diisi lewat subclass di admin_start
    server_version = "ZetaAdmin"
    sys_version = ""

    def log_message(self, *args):
        pass

    # -- util --
    def _send(self, code, body="", headers=None, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                         "frame-ancestors 'none'; base-uri 'none'")
        if self.ctx.secure:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        for k, v in headers or []:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _to(self, where):
        self._send(303, "", [("Location", where)])

    def _hosts(self):
        port = self.ctx.port
        hosts = [f"127.0.0.1:{port}", f"localhost:{port}"]
        if self.ctx.public_host:
            hosts += [self.ctx.public_host, f"{self.ctx.public_host}:{port}"]
        return hosts

    def _host_ok(self):
        # cegah DNS rebinding: Host harus alamat kita sendiri
        return (self.headers.get("Host") or "").lower() in self._hosts()

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return origin.lower() in {s + h for h in self._hosts() for s in ("http://", "https://")}

    def _client_ip(self):
        if self.ctx.secure:  # di belakang proxy: pakai alamat yang dicatat proxy terdekat
            xff = self.headers.get("X-Forwarded-For") or ""
            if xff.strip():
                return xff.split(",")[-1].strip()[:64]
        return self.client_address[0]

    def _cookie(self, value, max_age):
        flags = "HttpOnly; SameSite=Strict; Path=/; " + ("Secure; " if self.ctx.secure else "")
        return f"zeta_admin={value}; {flags}Max-Age={max_age}"

    def _session(self):
        token = ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "zeta_admin":
                token = v
        s = self.ctx.sessions.get(token)
        now = time.time()
        if s and s["exp"] > now:
            s["exp"] = now + 3600
            return token, s
        if s:
            self.ctx.sessions.pop(token, None)
            self.ctx.chats.pop(token, None)
        return None

    # -- GET --
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/healthz":  # untuk health check platform hosting
            return self._send(200, "ok", ctype="text/plain; charset=utf-8")
        if not self._host_ok():
            return self._send(403, "Host tidak diizinkan")
        q = urllib.parse.parse_qs(url.query)
        if url.path == "/login":
            return self._send(200, admin_login_page(q.get("m", [""])[0]))
        sess = self._session()
        if not sess:
            return self._to("/login")
        token, s = sess
        csrf = s["csrf"]
        if url.path == "/":
            return self._send(200, admin_dashboard(self.ctx, csrf, q.get("m", [""])[0]))
        if url.path == "/chat":
            return self._send(200, admin_chat_page(self.ctx.chats.get(token, []), csrf, q.get("m", [""])[0]))
        if url.path == "/session":
            page = admin_session_page(q.get("id", [""])[0])
            if page is None:
                return self._send(404, admin_page("Tidak ditemukan", '<p>Obrolan tidak ditemukan.</p>'
                                                  '<p><a href="/">← kembali</a></p>'))
            return self._send(200, page)
        return self._send(404, admin_page("Tidak ditemukan", '<p>Halaman tidak ada.</p>'))

    # -- POST --
    def do_POST(self):
        if not self._host_ok() or not self._origin_ok():
            return self._send(403, "Permintaan ditolak")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send(400, "Permintaan salah")
        if n < 0 or n > 65536:
            return self._send(413, "Terlalu besar")
        body = self.rfile.read(n).decode("utf-8", "ignore")
        form = {k: v[0] for k, v in urllib.parse.parse_qs(body, keep_blank_values=True).items()}
        path = urllib.parse.urlsplit(self.path).path
        if path == "/login":
            return self._login(form)
        sess = self._session()
        if not sess:
            return self._to("/login")
        token, s = sess
        if not hmac.compare_digest(form.get("csrf", ""), s["csrf"]):
            return self._send(403, "Token CSRF salah")
        if path == "/logout":
            self.ctx.sessions.pop(token, None)
            self.ctx.chats.pop(token, None)
            admin_log("logout")
            return self._send(303, "", [("Location", "/login"), ("Set-Cookie", self._cookie("", 0))])
        if path == "/chat":
            return self._chat(form, token)
        if path == "/chat/clear":
            self.ctx.chats.pop(token, None)
            return self._to("/chat")
        handler = {
            "/settings": self._settings, "/key": self._key,
            "/memory/add": self._mem_add, "/memory/del": self._mem_del,
            "/session/del": self._sess_del, "/password": self._password,
        }.get(path)
        if handler is None:
            return self._send(404, "Tidak ada")
        handler(form)

    def _login(self, form):
        ctx = self.ctx
        now = time.time()
        for t in [t for t, v in ctx.sessions.items() if v["exp"] <= now]:
            ctx.sessions.pop(t, None)
            ctx.chats.pop(t, None)
        if len(ctx.fails) > 2000:
            ctx.fails = {k: v for k, v in ctx.fails.items() if v and now - v[-1] < 300}
        ip = self._client_ip()
        recent = [t for t in ctx.fails.get(ip, []) if now - t < 300]
        ctx.fails[ip] = recent
        if len(recent) >= 5:
            admin_log(f"login diblokir sementara ({ip})")
            return self._send(429, admin_login_page("locked"))
        if admin_check(ctx.cfg, form.get("password", "")):
            ctx.fails.pop(ip, None)
            token = secrets.token_urlsafe(32)
            ctx.sessions[token] = {"csrf": secrets.token_urlsafe(24), "exp": now + 3600}
            admin_log(f"login berhasil ({ip})")
            return self._send(303, "", [("Location", "/"), ("Set-Cookie", self._cookie(token, 3600))])
        recent.append(now)
        admin_log(f"login gagal ({ip})")
        return self._send(401, admin_login_page("wrong"))

    def _chat(self, f, token):
        ctx = self.ctx
        text = f.get("text", "").strip()
        if not 1 <= len(text) <= 8000:
            return self._to("/chat?m=bad")
        if not ctx.chat_lock.acquire(blocking=False):
            return self._to("/chat?m=busy")
        try:
            hist = ctx.chats.setdefault(token, [])
            sendable = [m for m in hist if m["role"] in ("user", "assistant")]
            sendable.append({"role": "user", "content": text})
            try:
                reply = web_ask(ctx.cfg, sendable)
                tail = {"role": "assistant", "content": reply}
                admin_log("chat web")
            except urllib.error.HTTPError as e:
                tail = {"role": "error", "content": explain_http_error(e)}
            except Exception as e:
                tail = {"role": "error", "content": f"Gagal: {str(e)[:200]}"}
            hist += [{"role": "user", "content": text}, tail]
            del hist[:-40]
        finally:
            ctx.chat_lock.release()
        self._to("/chat")

    def _settings(self, f):
        ctx, cfg = self.ctx, self.ctx.cfg
        model = f.get("model", "").strip()
        persona = f.get("persona", "")
        theme = f.get("theme", "")
        system = f.get("system", "").strip()
        try:
            auto = float(f.get("auto", "0").replace(",", "."))
        except ValueError:
            auto = -1
        ok = (re.fullmatch(r"[A-Za-z0-9_.:/\-]{1,100}", model)
              and (persona in PERSONAS or persona == "kustom")
              and theme in THEMES and 0 <= auto <= 30 and len(system) <= 4000
              and (persona != "kustom" or system))
        if not ok:
            return self._to("/?m=bad")
        with ctx.lock:
            cfg["model"] = model
            cfg["persona"] = persona
            cfg["system"] = PERSONAS[persona] if persona in PERSONAS else system
            cfg["theme"] = theme
            cfg["web"] = f.get("web") == "on"
            cfg["auto"] = 0 if auto == 0 else max(0.5, auto)
            save_cfg(cfg)
        admin_log("pengaturan diubah")
        self._to("/?m=saved")

    def _key(self, f):
        newkey = f.get("api_key", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", newkey):
            return self._to("/?m=bad")
        with self.ctx.lock:
            self.ctx.cfg["api_key"] = newkey
            save_cfg(self.ctx.cfg)
        admin_log("API key diganti")
        self._to("/?m=key")

    def _mem_add(self, f):
        text = " ".join(f.get("text", "").split())
        if not 1 <= len(text) <= 500:
            return self._to("/?m=bad")
        with self.ctx.lock:
            self.ctx.cfg.setdefault("memory", []).append(text)
            save_cfg(self.ctx.cfg)
        admin_log("catatan ditambah")
        self._to("/?m=mem_add")

    def _mem_del(self, f):
        try:
            n = int(f.get("n", ""))
        except ValueError:
            return self._to("/?m=bad")
        with self.ctx.lock:
            mem = self.ctx.cfg.setdefault("memory", [])
            if not 1 <= n <= len(mem):
                return self._to("/?m=bad")
            mem.pop(n - 1)
            save_cfg(self.ctx.cfg)
        admin_log("catatan dihapus")
        self._to("/?m=mem_del")

    def _sess_del(self, f):
        sid = f.get("id", "")
        if not SID_RE.fullmatch(sid):
            return self._to("/?m=bad")
        for ext in ("json", "md"):
            try:
                os.remove(sess_path(sid, ext))
            except OSError:
                pass
        admin_log(f"obrolan {sid} dihapus")
        self._to("/?m=sess_del")

    def _password(self, f):
        ctx = self.ctx
        if ctx.env_pw:
            return self._to("/?m=pwenv")
        old, new, again = f.get("old", ""), f.get("new", ""), f.get("again", "")
        if not admin_check(ctx.cfg, old):
            ctx.fails.setdefault(self._client_ip(), []).append(time.time())  # tebakan juga dibatasi
            admin_log("ganti password gagal (password lama salah)")
            return self._to("/?m=pwbad")
        if new != again or not 8 <= len(new) <= 200:
            return self._to("/?m=pwbad")
        with ctx.lock:
            ctx.cfg["admin"] = admin_hash(new)
            save_cfg(ctx.cfg)
        ctx.sessions.clear()
        ctx.chats.clear()
        admin_log("password admin diganti")
        self._send(303, "", [("Location", "/login?m=pw"), ("Set-Cookie", self._cookie("", 0))])


def admin_start(cfg, port, host="127.0.0.1", public_host="", env_pw=False, retry=True):
    """Jalankan server admin. Return port yang dipakai."""
    ctx = AdminCtx(cfg, public_host, env_pw)
    handler = type("BoundAdminHandler", (AdminHandler,), {"ctx": ctx})
    ports = range(port, port + 10) if retry else [port]
    last = None
    for p in ports:
        try:
            srv = http.server.ThreadingHTTPServer((host, p), handler)
            break
        except OSError as e:
            last = e
    else:
        raise last
    srv.daemon_threads = True
    ctx.port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ADMIN["server"], ADMIN["ctx"] = srv, ctx
    admin_log(f"server admin dimulai di {host}:{ctx.port}" + (f" (publik: {public_host})" if public_host else ""))
    return ctx.port


def admin_stop():
    srv = ADMIN["server"]
    if srv:
        srv.shutdown()
        srv.server_close()
        ADMIN["server"] = ADMIN["ctx"] = None
        admin_log("server admin dihentikan")
        return True
    return False


def admin_set_password(cfg):
    if cfg.get("admin") and not admin_check(cfg, getpass.getpass("Password admin lama: ")):
        print(c(RED, "Password lama salah."))
        return False
    for _ in range(3):
        p1 = getpass.getpass("Password admin baru (min 8 karakter): ")
        if len(p1) < 8:
            print(c(RED, "Terlalu pendek."))
            continue
        if p1 != getpass.getpass("Ulangi password: "):
            print(c(RED, "Tidak sama."))
            continue
        cfg["admin"] = admin_hash(p1)
        save_cfg(cfg)
        admin_log("password admin diatur lewat terminal")
        print(c(GREEN, "Password admin tersimpan."))
        return True
    print(c(RED, "Gagal 3 kali, dibatalkan."))
    return False


def admin_url_hint(port):
    print(c(GREEN, f"Server admin aktif: http://127.0.0.1:{port}"))
    print(c(DIM, "  Buka di browser HP ini, login dengan password admin."))
    print(c(DIM, "  Hanya bisa diakses dari perangkat ini. /admin stop untuk mematikan."))


def admin_command(cfg, sub, rest):
    try:
        if sub in ("", "start"):
            if ADMIN["server"]:
                return admin_url_hint(ADMIN["ctx"].port)
            if not cfg.get("admin") and not admin_set_password(cfg):
                return
            admin_url_hint(admin_start(cfg, int(cfg.get("admin_port", ADMIN_PORT))))
        elif sub == "stop":
            print(c(GREEN, "Server admin dimatikan.") if admin_stop() else c(DIM, "Server admin tidak aktif."))
        elif sub == "password":
            admin_set_password(cfg)
        elif sub == "port":
            if not rest.isdigit() or not 1024 <= int(rest) <= 65535:
                print(c(RED, "Pakai: /admin port <1024-65535>"))
                return
            cfg["admin_port"] = int(rest)
            save_cfg(cfg)
            print(c(GREEN, f"Port admin: {rest}") + c(DIM, "  (berlaku saat server dimulai ulang)"))
        elif sub == "log":
            lines = admin_log_tail(15)
            print("\n".join(lines) if lines else c(DIM, "Log masih kosong."))
        elif sub == "status":
            if ADMIN["server"]:
                print(c(GREEN, f"Aktif di http://127.0.0.1:{ADMIN['ctx'].port}"))
            else:
                print(c(DIM, "Tidak aktif. Mulai dengan /admin"))
        else:
            print(c(RED, "Pakai: /admin [start|stop|password|port <n>|log|status]"))
    except (EOFError, KeyboardInterrupt):
        print(c(DIM, "(dibatalkan)"))
    except OSError as e:
        print(c(RED, f"Server admin gagal jalan: {e}"))


def admin_only():
    """python zeta.py --admin : server admin saja, tanpa chat terminal.

    Lokal (bawaan): 127.0.0.1. Untuk hosting online atur environment:
      ZETA_HOST=0.0.0.0  ZETA_PUBLIC_HOST=domain-kamu  ZETA_ADMIN_PASSWORD=(min 12 karakter)
      PORT=...           ZETA_HOME=/data (folder data permanen)  OPENROUTER_API_KEY=...
    Mode publik gagal-tertutup: tanpa domain dan password kuat, server menolak start."""
    cfg = load_cfg()
    host = os.environ.get("ZETA_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port_env = os.environ.get("PORT") or os.environ.get("ZETA_PORT")
    try:
        port = int(port_env) if port_env else int(cfg.get("admin_port", ADMIN_PORT))
    except ValueError:
        sys.exit("PORT tidak valid.")
    public = re.sub(r"^https?://", "", os.environ.get("ZETA_PUBLIC_HOST", "").strip().lower()).rstrip("/")
    env_pw = os.environ.get("ZETA_ADMIN_PASSWORD", "")
    if host not in ("127.0.0.1", "localhost", "::1"):
        problems = []
        if not public:
            problems.append("ZETA_PUBLIC_HOST wajib diisi (domain publik, contoh: zeta.onrender.com)")
        if len(env_pw) < 12:
            problems.append("ZETA_ADMIN_PASSWORD wajib diisi, minimal 12 karakter")
        if problems:
            for p in problems:
                print("Ditolak (mode publik): " + p, file=sys.stderr)
            sys.exit(2)
    if env_pw:
        cfg["admin"] = admin_hash(env_pw)  # password dari environment, tidak ditulis polos ke disk
    elif not cfg.get("admin"):
        if sys.stdin.isatty():
            if not admin_set_password(cfg):
                sys.exit(1)
        else:
            print("Password admin belum diatur. Jalankan: python zeta.py --set-password "
                  "(atau isi ZETA_ADMIN_PASSWORD).", file=sys.stderr)
            sys.exit(2)
    try:
        port = admin_start(cfg, port, host, public, bool(env_pw), retry=not port_env)
    except (EOFError, KeyboardInterrupt):
        sys.exit(1)
    except OSError as e:
        sys.exit(f"Gagal membuka port: {e}")
    if public:
        print(f"Server admin aktif di {host}:{port} (akses lewat https://{public})", flush=True)
    else:
        admin_url_hint(port)
        print(c(DIM, "  Tekan Ctrl+C untuk berhenti."), flush=True)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_a: stop.set())
    stop.wait()
    admin_stop()
    print("Server admin berhenti.", flush=True)


# ---------- update otomatis dari GitHub ----------
UPDATE = {"latest": None, "shown": False}


def ver_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4]) or (0,)


def update_base(cfg):
    repo = str(cfg.get("update_repo", "")).strip()
    branch = str(cfg.get("update_branch", "main")).strip() or "main"
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", repo):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_./\-]+", branch):
        return None
    return f"https://raw.githubusercontent.com/{repo}/{branch}/"


def http_get(url, limit=3000000, timeout=15):
    headers = {"User-Agent": "Mozilla/5.0 (Zeta AI updater)"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://raw.githubusercontent.com/"):
        headers["Authorization"] = f"token {token}"  # untuk repo privat
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read(limit + 1)[:limit]


def remote_info(cfg):
    """Return (versi_di_repo, isi_zeta_py)."""
    base = update_base(cfg)
    if not base:
        raise ValueError("repo update belum diatur")
    data = http_get(base + "zeta.py")
    m = re.search(rb'^VERSION\s*=\s*"([^"]+)"', data, re.M)
    if not m:
        raise ValueError("file di repo bukan zeta.py yang valid")
    return m.group(1).decode(), data


def verify_update(cfg, data):
    """Periksa sintaks dan (kalau ada) checksum zeta.py.sha256 di repo. Lempar error kalau gagal."""
    try:
        src = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("file bukan teks UTF-8")
    compile(src, "zeta.py", "exec")  # SyntaxError -> update ditolak
    if "def main(" not in src:
        raise ValueError("bukan zeta.py yang valid")
    try:
        want = http_get(update_base(cfg) + "zeta.py.sha256", 1000).decode().split()[0].lower()
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        return "tanpa checksum (zeta.py.sha256 tidak ada di repo)"
    if hashlib.sha256(data).hexdigest() != want:
        raise ValueError("checksum tidak cocok, update dibatalkan")
    return "checksum cocok"


def apply_update(data, path=None):
    path = path or os.path.abspath(__file__)
    shutil.copy2(path, path + ".bak")  # cadangan untuk /update rollback
    tmp = path + ".new"
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        os.chmod(tmp, os.stat(path).st_mode)
    except OSError:
        pass
    os.replace(tmp, path)
    return path


def update_check_bg(cfg):
    """Cek versi baru di latar belakang saat Zeta dibuka (tidak menghambat)."""
    def work():
        try:
            ver, _ = remote_info(cfg)
            if ver_tuple(ver) > ver_tuple(VERSION):
                UPDATE["latest"] = ver
        except Exception:
            pass
    if update_base(cfg) and cfg.get("auto_update_check", True):
        threading.Thread(target=work, daemon=True).start()


def update_command(cfg, arg):
    sub, _, rest = arg.partition(" ")
    sub, rest = sub.lower(), rest.strip()
    try:
        if sub == "repo":
            parts = rest.split()
            if not parts:
                print(f"Repo: {cfg.get('update_repo') or '(belum diatur)'}  cabang: {cfg.get('update_branch', 'main')}")
                return
            test = {"update_repo": parts[0], "update_branch": parts[1] if len(parts) > 1 else "main"}
            if not update_base(test):
                print(c(RED, "Format: /update repo username/nama-repo [cabang]"))
                return
            cfg.update(test)
            save_cfg(cfg)
            print(c(GREEN, f"Repo update: {test['update_repo']} ({test['update_branch']})"))
            return
        if sub == "auto":
            if rest.lower() in ("on", "off"):
                cfg["auto_update_check"] = rest.lower() == "on"
                save_cfg(cfg)
            print("Cek update otomatis saat dibuka: " + ("nyala" if cfg.get("auto_update_check", True) else "mati"))
            return
        if sub == "rollback":
            path = os.path.abspath(__file__)
            if not os.path.exists(path + ".bak"):
                print(c(DIM, "Belum ada cadangan versi lama."))
                return
            shutil.copy2(path + ".bak", path)
            print(c(GREEN, "Versi lama dipulihkan.") + c(DIM, " Jalankan ulang Zeta."))
            return
        if not update_base(cfg):
            print(c(YELLOW, "Repo update belum diatur. Pakai: /update repo username/nama-repo"))
            return
        print(c(DIM, "Mengecek versi terbaru..."))
        ver, data = remote_info(cfg)
        if ver_tuple(ver) <= ver_tuple(VERSION):
            print(c(GREEN, f"Sudah versi terbaru (v{VERSION})."))
            return
        print(f"Versi baru tersedia: v{ver} (sekarang v{VERSION})")
        if sub == "check":
            print(c(DIM, "Jalankan /update untuk memperbarui."))
            return
        print(c(DIM, verify_update(cfg, data)))
        if input("Perbarui sekarang? (y/N) ").strip().lower() != "y":
            print(c(DIM, "Dibatalkan."))
            return
        path = apply_update(data)
        print(c(GREEN, f"Terupdate ke v{ver}.") + c(DIM, f" Cadangan: {path}.bak"))
        if input("Mulai ulang Zeta sekarang? (Y/n) ").strip().lower() != "n":
            atexit._run_exitfuncs()  # simpan riwayat ketikan dulu
            os.execv(sys.executable, [sys.executable, path] + sys.argv[1:])
        print(c(DIM, "Jalankan ulang Zeta untuk memakai versi baru."))
    except (EOFError, KeyboardInterrupt):
        print(c(DIM, "(dibatalkan)"))
    except urllib.error.HTTPError as e:
        print(c(RED, f"Gagal mengambil dari GitHub: HTTP {e.code} (cek nama repo/cabang; repo privat butuh GITHUB_TOKEN)"))
    except urllib.error.URLError:
        print(c(RED, "Tidak ada koneksi internet."))
    except Exception as e:
        print(c(RED, f"Update gagal: {e}"))


# ---------- uji mandiri & baris perintah ----------
def selftest():
    """python zeta.py --selftest : pemeriksaan offline cepat (dipakai CI)."""
    import contextlib
    import http.client
    import io
    import tempfile
    global ADMIN_LOG
    fails, total = [], [0]

    def check(name, cond):
        total[0] += 1
        if not cond:
            fails.append(name)

    sample = "# Judul\n- poin **tebal**\n| a | b |\n|---|---|\n| 1 | 2 |\n```py\nx = 1\n```\nakhir *miring*"

    def render(chunks):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            md = MD()
            for part in chunks:
                md.feed(part)
            md.flush()
        return buf.getvalue()

    check("markdown streaming konsisten", render([sample]) == render(list(sample)))
    cfg = {"admin": admin_hash("kata-sandi-uji")}
    check("hash password", admin_check(cfg, "kata-sandi-uji") and not admin_check(cfg, "salah"))
    check("urutan versi", ver_tuple("1.10") > ver_tuple("1.9") and ver_tuple(VERSION) >= ver_tuple("1.0"))
    big = [{"role": "user", "content": "a" * MAX_HIST_CHARS}, {"role": "assistant", "content": "b"},
           {"role": "user", "content": "c"}]
    trimmed, cut = trim_history(big)
    check("pangkas riwayat", cut == 2 and trimmed[-1]["content"] == "c")
    check("repo update divalidasi", update_base({"update_repo": "a/b"}) and not update_base({"update_repo": "x;y"}))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "a.txt")
        with open(path, "w") as f:
            f.write("isi uji")
        content, _, _ = build_message(f"baca @{path}", [])
        check("baca file", "isi uji" in content)
        ADMIN_LOG = os.path.join(d, "admin.log")
        try:
            port = admin_start(cfg, 0)
            def get(p, host=None):
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", p, headers={"Host": host or f"127.0.0.1:{port}"})
                r = conn.getresponse()
                r.read()
                conn.close()
                return r.status
            check("healthz", get("/healthz", "apa-saja") == 200)
            check("login terbuka", get("/login") == 200)
            check("host asing ditolak", get("/login", "evil.example") == 403)
            check("dashboard butuh login", get("/") == 303)
        finally:
            admin_stop()
    if fails:
        print("selftest GAGAL: " + ", ".join(fails))
        return 1
    print(f"selftest OK ({total[0]} pemeriksaan)")
    return 0


CLI_HELP = """Zeta AI v{v}
  python zeta.py                     mulai chat di terminal
  python zeta.py --admin             server admin saja (lihat README untuk mode online)
  python zeta.py --set-password      atur password admin
  python zeta.py --set-repo U/R [C]  atur repo GitHub untuk /update (cabang C, bawaan main)
  python zeta.py --version | --selftest | --help
"""


def cli(argv):
    if "--help" in argv or "-h" in argv:
        print(CLI_HELP.format(v=VERSION))
    elif "--version" in argv:
        print(f"Zeta AI v{VERSION}")
    elif "--selftest" in argv:
        sys.exit(selftest())
    elif "--set-password" in argv:
        try:
            sys.exit(0 if admin_set_password(load_cfg()) else 1)
        except (EOFError, KeyboardInterrupt):
            sys.exit(1)
    elif "--set-repo" in argv:
        args = argv[argv.index("--set-repo") + 1:][:2]
        cfg = load_cfg()
        test = {"update_repo": args[0] if args else "", "update_branch": args[1] if len(args) > 1 else "main"}
        if not update_base(test):
            sys.exit("Format: --set-repo username/nama-repo [cabang]")
        cfg.update(test)
        save_cfg(cfg)
        print(f"Repo update: {test['update_repo']} ({test['update_branch']})")
    elif "--admin" in argv:
        admin_only()
    else:
        main()


# ---------- input: riwayat, panah, Tab ----------
COMMANDS = [
    "/help", "/status", "/clear", "/new", "/sessions", "/load", "/export", "/save",
    "/retry", "/copy", "/compact", "/model", "/models", "/web", "/memory", "/theme",
    "/persona", "/auto", "/system", "/admin", "/update", "/key", "/exit",
]


def completer(text, state):
    try:
        buf = readline.get_line_buffer().lstrip()
        if text.startswith("@"):
            matches = []
            for m in sorted(glob.glob(os.path.expanduser(text[1:]) + "*")):
                matches.append("@" + m + ("/" if os.path.isdir(m) else ""))
        elif buf.startswith("/theme "):
            matches = [t for t in THEMES if t.startswith(text)]
        elif buf.startswith("/persona "):
            matches = [p for p in PERSONAS if p.startswith(text)]
        elif buf.startswith("/update "):
            matches = [a for a in ("repo", "check", "auto", "rollback") if a.startswith(text)]
        elif buf.startswith("/admin "):
            matches = [a for a in ("start", "stop", "password", "port", "log", "status")
                       if a.startswith(text)]
        elif buf.startswith("/web ") or buf.startswith("/auto "):
            matches = [o for o in ("on", "off") if o.startswith(text)]
        elif buf.startswith("/") and " " not in buf:
            matches = [x for x in COMMANDS if x.startswith(text)]
        else:
            matches = []
        return matches[state] if state < len(matches) else None
    except Exception:
        return None


def setup_readline():
    if readline is None:
        return
    os.makedirs(DIR, exist_ok=True)
    try:
        readline.read_history_file(HIST_FILE)
    except OSError:
        pass
    readline.set_history_length(500)

    def save_hist():
        try:
            readline.write_history_file(HIST_FILE)
        except OSError:
            pass

    atexit.register(save_hist)
    readline.set_completer_delims(" \t\n")
    readline.set_completer(completer)
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")


def rl_prompt(p):
    """Bungkus kode warna supaya readline tidak salah hitung lebar prompt."""
    if readline is None:
        return p
    return re.sub(r"(\033\[[0-9;]*m)", "\001\\1\002", p)


# ---------- commands ----------
HELP = """
  /help            tampilkan bantuan
  /status          lihat pengaturan saat ini
  /new             mulai obrolan baru (yang lama tetap tersimpan)
  /sessions        daftar obrolan lama   |   /load <n>  buka & lanjutkan
  /export          simpan obrolan jadi file .md yang enak dibaca
  /retry           jawab ulang pertanyaan terakhir
  /copy            salin jawaban terakhir  |  /copy code = salin blok kode terakhir
                   (perlu termux-api; tanpa itu disimpan ke file)
  /compact         ringkas riwayat panjang supaya hemat dan tetap nyambung
  /persona <nama>  ganti gaya: umum, coder, guru, santai, penerjemah
  /model <nama>    ganti model
  /models <kata>   cari daftar model (misal: /models claude)
  /web on|off      AI cari info terbaru di internet
  /theme <nama>    ganti tema warna (tanpa nama = lihat pilihan)
  /memory <teks>   simpan catatan permanen (tanpa teks = lihat daftar)
  /memory del <n>  hapus catatan nomor n  |  /memory clear = hapus semua
  /auto <opsi>     auto-jawab saat berhenti ngetik: on | off | <detik>
  /system <teks>   ubah kepribadian/instruksi Zeta
  /admin           server admin (web, khusus perangkat ini, wajib password)
                   /admin stop | password | port <n> | log | status
  /update          cek & pasang versi baru dari GitHub
                   /update repo user/repo | check | auto on/off | rollback
  /key             ganti API key
  /exit            keluar

  @namafile        sertakan file teks atau gambar di pesan
                   contoh: jelaskan @script.py   |   apa ini? @foto.jpg
  @https://...     baca isi halaman web, contoh: rangkum @https://contoh.com
  \\ di akhir baris, atau \"\"\" ... \"\"\"   tulis pesan beberapa baris
  !perintah        jalankan perintah shell, hasilnya ikut dibahas AI
                   contoh: !ls   |   !cd ~/storage/downloads

  Tombol: panah atas/bawah = riwayat ketikan, Tab = lengkapi /perintah
  dan nama file setelah @. Ctrl+D untuk keluar. (Panah tidak aktif
  saat /auto nyala.)
"""


def read_line(prompt, delay):
    """Baca input. Terkirim saat Enter, atau otomatis kalau berhenti mengetik
    selama `delay` detik (delay=0 -> mode biasa, harus Enter)."""
    if not delay or not sys.stdin.isatty() or termios is None:
        return input(rl_prompt(prompt))

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    dec = codecs.getincrementaldecoder("utf-8")("ignore")
    buf = ""
    esc = 0  # 0 normal, 1 setelah ESC, 2 di dalam urutan [ ... (tombol panah dll)
    done = False

    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        tty.setcbreak(fd)
        while not done:
            r, _, _ = select.select([fd], [], [], delay if buf.strip() else None)
            if not r:
                break  # berhenti mengetik -> kirim
            data = os.read(fd, 1024)
            if not data:
                raise EOFError
            for ch in dec.decode(data):
                if esc == 1:
                    esc = 2 if ch in "[O" else 0
                    continue
                if esc == 2:
                    if ch.isalpha() or ch == "~":
                        esc = 0
                    continue
                if ch == "\x1b":
                    esc = 1
                elif ch in ("\r", "\n"):
                    if buf.strip():
                        done = True
                        break
                elif ch == "\x04":
                    if not buf:
                        raise EOFError
                elif ch in ("\x7f", "\x08"):
                    if buf:
                        buf = buf[:-1]
                        sys.stdout.write("\b \b")
                elif ch >= " ":
                    buf += ch
                    sys.stdout.write(ch)
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return buf


def read_multiline(first):
    """Pesan beberapa baris: akhiri baris dengan \\, atau buka dan tutup dengan \"\"\"."""
    def more():
        return input(rl_prompt(c(DIM, "  … ")))

    if first == '"""':
        lines = []
        while True:
            ln = more()
            if ln.strip() == '"""':
                break
            lines.append(ln)
        return "\n".join(lines).strip()
    while first.endswith("\\"):
        first = first[:-1].rstrip() + "\n" + more()
    return first.strip()


def handle_memory(arg, cfg):
    mem = cfg.setdefault("memory", [])
    low = arg.lower()
    if not arg:
        if not mem:
            print(c(DIM, "Belum ada catatan. Tambah dengan: /memory <teks>"))
        for i, m in enumerate(mem, 1):
            print(f"  {acc(str(i) + '.')} {m}")
        return
    if low == "clear":
        mem.clear()
        save_cfg(cfg)
        print(c(GREEN, "Semua catatan dihapus."))
    elif low.startswith("del "):
        try:
            n = int(low[4:].strip())
            removed = mem.pop(n - 1)
            save_cfg(cfg)
            print(c(GREEN, f"Dihapus: {removed}"))
        except (ValueError, IndexError):
            print(c(RED, "Pakai: /memory del <nomor>"))
    else:
        mem.append(arg)
        save_cfg(cfg)
        print(c(GREEN, f"Tersimpan di catatan #{len(mem)}."))


def swatch(name):
    return "".join(c256(g, "██") for g in THEMES[name]["grad"])


def copy_last(messages, what=""):
    last = next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), None)
    if not last:
        print(c(DIM, "Belum ada jawaban untuk disalin."))
        return
    if what == "code":
        blocks = re.findall(r"```[^\n]*\n(.*?)```", last, re.S)
        if not blocks:
            print(c(DIM, "Tidak ada blok kode di jawaban terakhir."))
            return
        last = blocks[-1].rstrip("\n")
    tool = shutil.which("termux-clipboard-set")
    if not tool:
        path = os.path.join(DIR, "salinan.txt")
        try:
            os.makedirs(DIR, exist_ok=True)
            with open(path, "w") as f:
                f.write(last)
        except OSError as e:
            print(c(RED, f"Gagal menyimpan: {e}"))
            return
        print(c(YELLOW, "termux-api belum terpasang, teks disimpan di: " + path))
        print(c(DIM, "Untuk menyalin langsung: pkg install termux-api (+ aplikasi Termux:API)"))
        return
    try:
        subprocess.run([tool], input=last, text=True, timeout=10)
        print(c(GREEN, "Jawaban tersalin."))
    except Exception as e:
        print(c(RED, f"Gagal menyalin: {e}"))


def main():
    cfg = load_cfg()
    key = get_key(cfg)
    model = cfg.get("model", DEFAULT_MODEL)
    system = cfg.get("system", DEFAULT_SYSTEM)
    auto = cfg.get("auto", DEFAULT_AUTO)
    web = cfg.get("web", False)
    theme = cfg.get("theme", "laut")
    if theme not in THEMES:
        theme = "laut"
    set_theme(theme)
    persona = cfg.get("persona", "umum")
    messages = []
    pending = []  # hasil perintah shell yang menunggu dikirim ke AI
    sid = new_sid()

    def sync():
        """Ambil perubahan dari server admin (cfg adalah sumber kebenaran)."""
        nonlocal model, web, auto, system, persona, theme, key
        model = cfg.get("model", model)
        web = cfg.get("web", web)
        auto = cfg.get("auto", auto)
        system = cfg.get("system", system)
        persona = cfg.get("persona", persona)
        new_theme = cfg.get("theme", theme)
        if new_theme in THEMES and new_theme != theme:
            theme = new_theme
            set_theme(theme)
        key = get_key(cfg)

    setup_readline()
    update_check_bg(cfg)
    banner(model, web, len(cfg.get("memory", [])), theme, anim=True, persona=persona)
    if list_sessions(1):
        print(c(DIM, "  /sessions untuk melanjutkan obrolan lama") + "\n")

    while True:
        sync()
        if UPDATE["latest"] and not UPDATE["shown"]:
            UPDATE["shown"] = True
            print(acc("↑ ") + f"Versi baru tersedia: v{UPDATE['latest']} (sekarang v{VERSION}). Ketik /update")
        prompt = acc("kamu") + c(DIM, " ❯ ")
        try:
            text = read_line(prompt, auto).strip()
        except EOFError:
            print("\n" + c(DIM, "Sampai jumpa."))
            break
        except KeyboardInterrupt:
            print("\n" + c(DIM, "(Ctrl+D atau /exit untuk keluar)"))
            continue
        if text and text[0] not in "!/":
            try:
                text = read_multiline(text)
            except (EOFError, KeyboardInterrupt):
                print(c(DIM, "(dibatalkan)"))
                continue
        if not text:
            continue
        sync()  # perubahan dari server admin saat menunggu ketikan langsung berlaku

        if text.startswith("!"):
            try:
                run_shell(text[1:].strip(), pending)
            except KeyboardInterrupt:
                print(c(DIM, "(dibatalkan)"))
            continue

        if text.startswith("/"):
            cmd, _, arg = text.partition(" ")
            arg = arg.strip()
            mem_n = len(cfg.get("memory", []))
            if cmd in ("/exit", "/quit", "/q"):
                print(c(DIM, "Sampai jumpa."))
                break
            elif cmd == "/help":
                print(c(CYAN, HELP))
            elif cmd == "/status":
                panel([
                    ("model    ", model),
                    ("web      ", "nyala" if web else "mati"),
                    ("tema     ", theme),
                    ("persona  ", persona),
                    ("auto     ", f"{auto} detik" if auto else "mati"),
                    ("memori   ", f"{mem_n} catatan"),
                    ("admin    ", f"nyala :{ADMIN['ctx'].port}" if ADMIN["server"] else "mati"),
                    ("pesan    ", f"{len(messages)} dalam riwayat"),
                    ("folder   ", os.getcwd()),
                ], max(min(40, tw() - 4), 24))
            elif cmd in ("/clear", "/new"):
                messages = []
                pending.clear()
                sid = new_sid()
                banner(model, web, mem_n, theme, persona=persona)
            elif cmd == "/sessions":
                show_sessions()
            elif cmd == "/load":
                sess = list_sessions()
                if not arg.isdigit():
                    show_sessions()
                elif not 1 <= int(arg) <= len(sess):
                    print(c(RED, "Nomor tidak ada. Lihat daftar dengan /sessions"))
                else:
                    d = sess[int(arg) - 1]
                    messages = d.get("messages", [])
                    sid = d.get("id", new_sid())
                    pending.clear()
                    print(c(GREEN, f"Dibuka: {d.get('title', '')}") + c(DIM, f"  ({len(messages)} pesan)"))
                    last = next((m["content"] for m in reversed(messages)
                                 if m["role"] == "assistant"), None)
                    if last:
                        print(c(DIM, "Jawaban terakhir:"))
                        print(c(DIM, last[:300] + ("…" if len(last) > 300 else "")))
            elif cmd in ("/export", "/save"):
                if messages:
                    print(c(GREEN, "Tersimpan: " + export_chat(messages, sid)))
                else:
                    print(c(DIM, "Belum ada obrolan."))
            elif cmd == "/retry":
                if messages and messages[-1]["role"] == "assistant":
                    old = messages.pop()
                    if respond(key, model, full_system(system, cfg.get("memory", [])), messages, web):
                        save_session(sid, messages, model)
                    else:
                        messages.append(old)
                else:
                    print(c(DIM, "Belum ada jawaban untuk diulang."))
            elif cmd == "/copy":
                copy_last(messages, arg.lower())
            elif cmd == "/compact":
                if len(messages) < 2:
                    print(c(DIM, "Riwayat masih pendek, belum perlu diringkas."))
                else:
                    try:
                        before = sum(msg_len(m) for m in messages)
                        messages = compact_history(key, model, messages)
                        save_session(sid, messages, model)
                        print(c(GREEN, "Riwayat diringkas.")
                              + c(DIM, f"  ({before} → {sum(msg_len(m) for m in messages)} karakter)"))
                    except urllib.error.HTTPError as e:
                        print(c(RED, explain_http_error(e)))
                    except Exception as e:
                        print(c(RED, f"Gagal meringkas: {e}"))
            elif cmd == "/persona":
                name = arg.lower()
                if name in PERSONAS:
                    persona = name
                    system = PERSONAS[name]
                    cfg["persona"], cfg["system"] = persona, system
                    save_cfg(cfg)
                    print(c(GREEN, f"Persona: {persona}"))
                else:
                    for p in PERSONAS:
                        print("  " + acc("•") + " " + p + (c(DIM, "  ← sekarang") if p == persona else ""))
                    print(c(DIM, "  pilih dengan: /persona <nama>"))
            elif cmd == "/model":
                if arg:
                    model = arg
                    cfg["model"] = model
                    save_cfg(cfg)
                    print(c(GREEN, f"Model: {model}"))
                else:
                    print(f"Model sekarang: {model}")
            elif cmd == "/web":
                if arg.lower() in ("on", "nyala"):
                    web = True
                elif arg.lower() in ("off", "mati"):
                    web = False
                elif arg:
                    print(c(RED, "Pakai: /web on | off"))
                    continue
                cfg["web"] = web
                save_cfg(cfg)
                print(c(GREEN, "Cari web: " + ("nyala" if web else "mati")))
            elif cmd == "/theme":
                name = arg.lower()
                if name in THEMES:
                    theme = name
                    set_theme(theme)
                    cfg["theme"] = theme
                    save_cfg(cfg)
                    print(swatch(theme) + " " + c(GREEN, f"Tema: {theme}"))
                else:
                    for t in THEMES:
                        print("  " + swatch(t) + " " + t + (c(DIM, "  ← sekarang") if t == theme else ""))
                    print(c(DIM, "  pilih dengan: /theme <nama>"))
            elif cmd == "/memory":
                handle_memory(arg, cfg)
            elif cmd == "/auto":
                if arg.lower() in ("off", "mati", "0"):
                    auto = 0
                elif arg.lower() in ("on", "nyala"):
                    auto = 1.5
                elif arg:
                    try:
                        auto = max(0.5, float(arg.replace(",", ".")))
                    except ValueError:
                        print(c(RED, "Pakai: /auto on | off | <detik>"))
                        continue
                cfg["auto"] = auto
                save_cfg(cfg)
                if auto:
                    print(c(GREEN, f"Auto-jawab nyala: terkirim {auto} detik setelah berhenti ngetik."))
                else:
                    print(c(GREEN, "Auto-jawab mati: tekan Enter untuk kirim."))
            elif cmd == "/models":
                try:
                    ids = list_models(key, arg)
                except Exception as e:
                    print(c(RED, f"Gagal ambil daftar model: {e}"))
                else:
                    if not ids:
                        print(c(DIM, "Tidak ada model yang cocok."))
                    for i in ids[:40]:
                        print("  " + i)
                    if len(ids) > 40:
                        print(c(DIM, f"  ...dan {len(ids) - 40} lagi, persempit dengan kata kunci."))
            elif cmd == "/system":
                if arg:
                    system = arg
                    persona = "kustom"
                    cfg["system"], cfg["persona"] = system, persona
                    save_cfg(cfg)
                    print(c(GREEN, "Instruksi diperbarui."))
                else:
                    print(system)
            elif cmd == "/update":
                update_command(cfg, arg)
            elif cmd == "/admin":
                sub, _, rest = arg.partition(" ")
                admin_command(cfg, sub.lower(), rest.strip())
            elif cmd == "/key":
                key = get_key(cfg, force=True)
                print(c(GREEN, "API key diperbarui."))
            else:
                print(c(RED, "Perintah tidak dikenal. Ketik /help"))
            continue

        content, hist, notes = build_message(text, pending)
        for n in notes:
            print(n)
        messages.append({"role": "user", "content": content})
        if respond(key, model, full_system(system, cfg.get("memory", [])), messages, web):
            messages[-2]["content"] = hist  # gambar tidak disimpan di riwayat
            pending.clear()
            save_session(sid, messages, model)
        else:
            messages.pop()


if __name__ == "__main__":
    if shutil.which("clear") is None:
        os.system = lambda *_a, **_k: 0
    cli(sys.argv[1:])
