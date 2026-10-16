#!/usr/bin/env bash
# Cài 2 skill cắt thô (cat-tho-talking-head, cat-tho-huong-dan) cho Claude Code và Codex.
# Chạy lại nhiều lần cũng được: bước nào xong rồi thì bỏ qua.
#   bash ~/skill-edit-video/install.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="$HERE/engine"
SKILLS=(cat-tho-talking-head cat-tho-huong-dan)
EXPECTED="$HOME/skill-edit-video"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nLỖI: %s\n' "$*" >&2; exit 1; }

if [ "$HERE" != "$EXPECTED" ]; then
  die "Repo phải nằm ở $EXPECTED (skill gọi engine theo đường dẫn này). Hiện đang ở $HERE."
fi

say "1/5 Kiểm tra công cụ"
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

say "2/5 Cài thư viện Python (uv sync)"
(cd "$ENGINE" && uv sync --quiet)

say "3/5 Tải model nghe tiếng Việt Zipformer (~70 MB, chỉ lần đầu, có kiểm SHA-256)"
(cd "$ENGINE" && .venv/bin/python -c "from roughcut import stt; stt.ensure_model(print); print('model OK')")

say "4/5 Gắn skill vào Claude Code và Codex"
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

say "5/5 Chạy thử"
(cd "$ENGINE" && .venv/bin/python -c "from roughcut import ff, stt; assert stt.model_ready(); print('ffmpeg:', ff.FFMPEG)")
(cd "$ENGINE" && .venv/bin/python scripts/roughcut_cli.py --help >/dev/null && echo "CLI OK")

say "XONG. Mở phiên Claude Code / Codex MỚI rồi gõ: cắt thô giúp mình video <đường dẫn>"
