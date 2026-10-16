#!/usr/bin/env bash
# Cài 3 skill (cat-tho-talking-head, cat-tho-huong-dan, dong-goi-video) cho Claude Code và Codex.
# Chạy lại nhiều lần cũng được: bước nào xong rồi thì bỏ qua.
#   bash ~/skill-edit-video/install.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="$HERE/engine"
SKILLS=(cat-tho-talking-head cat-tho-huong-dan dong-goi-video)
EXPECTED="$HOME/skill-edit-video"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nLỖI: %s\n' "$*" >&2; exit 1; }

if [ "$HERE" != "$EXPECTED" ]; then
  die "Repo phải nằm ở $EXPECTED (skill gọi engine theo đường dẫn này). Hiện đang ở $HERE."
fi

say "1/7 Kiểm tra công cụ"
command -v git >/dev/null || die "Chưa có git."
if ! command -v uv >/dev/null; then
  if command -v brew >/dev/null; then brew install uv
  else die "Chưa có uv. Cài: curl -LsSf https://astral.sh/uv/install.sh | sh  rồi mở terminal mới."; fi
fi
if [ ! -x /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg ] && [ ! -x /usr/local/opt/ffmpeg-full/bin/ffmpeg ] \
   && ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null; then brew install ffmpeg-full
  else die "Chưa có ffmpeg. macOS: brew install ffmpeg-full · Ubuntu: sudo apt install ffmpeg"; fi
fi

say "2/7 Cài thư viện Python (uv sync)"
(cd "$ENGINE" && uv sync --quiet)

say "3/7 Tải model nghe tiếng Việt Zipformer (~70 MB, chỉ lần đầu, có kiểm SHA-256)"
(cd "$ENGINE" && .venv/bin/python -c "from roughcut import stt; stt.ensure_model(print); print('model OK')")

say "4/7 whisper.cpp + model ggml-large-v3-turbo (~1.6 GB, chỉ lần đầu) cho dong-goi-video"
if ! command -v whisper-cli >/dev/null; then
  if command -v brew >/dev/null; then brew install whisper-cpp
  else die "Chưa có whisper-cli. Cài whisper.cpp rồi chạy lại."; fi
fi
WMODEL="$ENGINE/models/whisper/ggml-large-v3-turbo.bin"
WSHA="1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"
WURL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
if [ -f "$HOME/Developer/whisper-models/ggml-large-v3-turbo.bin" ] && [ ! -f "$WMODEL" ]; then
  echo "  dùng model có sẵn ở ~/Developer/whisper-models"
elif [ ! -f "$WMODEL" ]; then
  mkdir -p "$(dirname "$WMODEL")"
  curl -fL --retry 3 -C - -o "$WMODEL.part" "$WURL"
  got="$(shasum -a 256 "$WMODEL.part" | cut -d' ' -f1)"
  [ "$got" = "$WSHA" ] || { rm -f "$WMODEL.part"; die "Model whisper sai checksum ($got). Chạy lại để tải lại."; }
  mv "$WMODEL.part" "$WMODEL"; echo "  model whisper OK"
else
  echo "  model whisper (đã có)"
fi

say "5/7 Build tool tách người (Apple Vision) cho chữ nằm sau lưng"
PM="$HERE/skills/dong-goi-video/scripts/personmask"
if [ -x "$PM/personmask" ]; then echo "  personmask (đã có)"
elif command -v swiftc >/dev/null; then swiftc -O "$PM/personmask.swift" -o "$PM/personmask" && echo "  personmask OK"
else echo "  BỎ QUA: chưa có swiftc (xcode-select --install). Chỉ cần cho hiệu ứng chữ sau lưng."; fi

say "6/7 Gắn skill vào Claude Code và Codex"
targets=()
[ -d "$HOME/.claude" ] && targets+=("$HOME/.claude/skills")
[ -d "$HOME/.codex" ] && targets+=("$HOME/.codex/skills")
[ ${#targets[@]} -eq 0 ] && targets+=("$HOME/.claude/skills")
stamp="$(date +%Y%m%d-%H%M%S)"
for t in "${targets[@]}"; do
  mkdir -p "$t"
  for s in "${SKILLS[@]}"; do
    link="$t/$s"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$HERE/skills/$s" ]; then
      echo "  $link (đã có)"; continue
    fi
    if [ -e "$link" ] || [ -L "$link" ]; then
      # backup OUTSIDE the skills folder: a copy left inside would load as a duplicate skill
      bk="$HOME/.skill-edit-video-backup/$stamp/$(basename "$t")-$(basename "$(dirname "$t")")"
      mkdir -p "$bk"; mv "$link" "$bk/"; echo "  bản cũ cất ở $bk/$s"
    fi
    ln -s "$HERE/skills/$s" "$link"; echo "  $link -> $HERE/skills/$s"
  done
done

say "7/7 Chạy thử"
(cd "$ENGINE" && .venv/bin/python -c "from roughcut import ff, stt; assert stt.model_ready(); print('ffmpeg:', ff.FFMPEG)")
(cd "$ENGINE" && .venv/bin/python scripts/roughcut_cli.py --help >/dev/null && echo "CLI OK")
(cd "$ENGINE" && .venv/bin/python -c "import scipy, PIL, fontTools; print('thư viện đóng gói OK')")
ffmpeg_bin="$(cd "$ENGINE" && .venv/bin/python -c "from roughcut import ff; print(ff.FFMPEG)")"
filters="$("$ffmpeg_bin" -hide_banner -filters 2>/dev/null || true)"   # no `| grep -q`: SIGPIPE + pipefail = false alarm
grep -q " subtitles " <<<"$filters" && echo "ffmpeg có libass OK" \
  || echo "CẢNH BÁO: ffmpeg thiếu filter subtitles (libass) — cần brew install ffmpeg-full cho phụ đề"

say "XONG. Mở phiên Claude Code / Codex MỚI rồi gõ: cắt thô giúp mình video <đường dẫn>"
