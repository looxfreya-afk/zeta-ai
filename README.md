# Zeta AI — dibuat oleh Jevon

Chat AI di terminal (Termux/Linux), tanpa dependensi pip. Fitur: markdown, baca file/gambar, cari web, perintah shell, memori, tema, sesi tersimpan, **admin web**, **auto-update**, **deploy online**.

## Install di Termux (1 perintah)
```sh
pkg install -y curl
ZETA_REPO=USER/REPO sh -c "$(curl -fsSL https://raw.githubusercontent.com/USER/REPO/main/install.sh)"
```
atau dari folder ini: `sh install.sh`. Lalu ketik `zeta`. Saat pertama kali, masukkan API key OpenRouter (atau `/key`).

## Perintah
`zeta` · `zeta --admin` (dashboard di http://127.0.0.1:8787) · `zeta --set-password` · `zeta --set-repo USER/REPO` · `zeta --version` · `zeta --selftest`

## Auto-update
Upload folder ini ke GitHub, lalu di zeta: `/update repo USER/REPO`, `/update check`, `/update` (pasang), `/update auto on`, `/update rollback`. Update dicek sintaksnya dan checksum (`zeta.py.sha256`, dibuat otomatis oleh GitHub Actions).

## Latar belakang & auto-start (Termux)
`sv-enable zeta-admin` (butuh termux-services; restart Termux). Untuk jalan saat HP menyala: pasang Termux:Boot, file ada di `~/.termux/boot/zeta`.

## Deploy online (admin web via HTTPS)
Env wajib: `ZETA_HOST=0.0.0.0`, `ZETA_PUBLIC_HOST=domain-kamu`, `ZETA_ADMIN_PASSWORD` (≥12 karakter), `OPENROUTER_API_KEY`, `ZETA_HOME=/data` (disk permanen). Health check: `/healthz`. Tanpa domain/password server menolak start.
- **Render**: New → Blueprint, pilih repo (`render.yaml`).
- **Railway**: deploy dari repo (`railway.json` + `Dockerfile`), tambah volume di `/data`.
- **Docker/VPS**: `docker build -t zeta . && docker run -p 8787:8787 -v zeta:/data --env-file .env zeta`; atau systemd + Caddy di folder `deploy/`.

## Keamanan
Jangan commit API key. Key lama yang pernah dibagikan sebaiknya dicabut di OpenRouter.
