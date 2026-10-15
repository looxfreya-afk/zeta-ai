#!/data/data/com.termux/files/usr/bin/sh
# Zeta AI - installer 1 perintah untuk Termux
# Pakai:  sh install.sh            (dari folder ini)
#   atau: curl -fsSL https://raw.githubusercontent.com/USER/REPO/main/install.sh | sh
set -eu
REPO="${ZETA_REPO:-}"        # contoh: jevon/zeta-ai
BRANCH="${ZETA_BRANCH:-main}"
DEST="$HOME/.zeta_ai"
BIN="${PREFIX:-/usr}/bin"

say() { printf '\033[1;36m==>\033[0m %s\n' "$1"; }

say "Memasang Python..."
if command -v pkg >/dev/null 2>&1; then
  pkg install -y python >/dev/null 2>&1 || pkg install -y python
fi
command -v python3 >/dev/null 2>&1 || { echo "python3 tidak ditemukan"; exit 1; }

mkdir -p "$DEST"
if [ -f "$(dirname "$0")/zeta.py" ]; then
  say "Menyalin zeta.py dari folder ini..."
  cp "$(dirname "$0")/zeta.py" "$DEST/zeta.py"
elif [ -n "$REPO" ]; then
  say "Mengunduh zeta.py dari GitHub ($REPO)..."
  curl -fsSL "https://raw.githubusercontent.com/$REPO/$BRANCH/zeta.py" -o "$DEST/zeta.py"
else
  echo "Set ZETA_REPO=user/repo atau jalankan dari folder yang berisi zeta.py"; exit 1
fi
python3 -m py_compile "$DEST/zeta.py"

say "Membuat perintah 'zeta'..."
cat > "$BIN/zeta" <<SH
#!/bin/sh
exec python3 "$DEST/zeta.py" "\$@"
SH
chmod +x "$BIN/zeta"
[ -n "$REPO" ] && python3 "$DEST/zeta.py" --set-repo "$REPO" "$BRANCH" || true

# Opsional: layanan latar belakang (admin web) + jalan otomatis
if [ -d "$(dirname "$0")/termux" ] && command -v pkg >/dev/null 2>&1; then
  say "Menyiapkan mode latar belakang (opsional)..."
  pkg install -y termux-services termux-api >/dev/null 2>&1 || true
  SVC="${PREFIX:-/usr}/var/service/zeta-admin"
  mkdir -p "$SVC"
  cp "$(dirname "$0")/termux/run" "$SVC/run" && chmod +x "$SVC/run"
  mkdir -p "$HOME/.termux/boot"
  cp "$(dirname "$0")/termux/boot-zeta" "$HOME/.termux/boot/zeta" && chmod +x "$HOME/.termux/boot/zeta"
fi

say "Selesai! Ketik:  zeta"
echo "  Admin web  : zeta --admin"
echo "  Latar belakang: sv-enable zeta-admin   (restart Termux dulu)"
echo "  Update     : /update di dalam zeta"
