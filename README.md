# Skill cắt thô và đóng gói video (miễn phí, chạy trên máy)

Bộ này có 3 skill giúp Claude Code hoặc Codex (ChatGPT) **tự cắt thô rồi đóng gói video tiếng Việt** cho bạn. Bạn chỉ cần đưa file video và nói "cắt thô giúp mình", sau đó "đóng gói video này".

| Skill | Dùng cho video nào | Skill làm gì |
|---|---|---|
| `cat-tho-talking-head` | Nói trước camera: intro, vlog, clip quay bằng điện thoại / DJI / webcam, vài phút | Bỏ đoạn im lặng, từ đệm (à, ừ, ờm), chỗ nói lắp, câu nói hỏng rồi nói lại (giữ lần nói cuối) |
| `cat-tho-huong-dan` | Quay màn hình có lời giảng: hướng dẫn dùng app, Claude Code, ChatGPT… | Như trên, thêm: **tua nhanh và tắt tiếng** đoạn chờ mà màn hình đang chạy, cắt đoạn chờ đứng yên, đánh dấu chỗ nghi bạn nói lặp để bạn duyệt |
| `dong-goi-video` | Bản đã cắt thô (thường là talking head) | Thêm **phụ đề** (chữ hoa, từ khoá vàng), **thẻ motion graphic** minh hoạ đúng lúc bạn nói, zoom che chỗ cắt, **hiệu ứng âm thanh**, đoạn kết, rồi xuất bản cuối -14 LUFS |

Kết quả của 2 skill cắt thô:

- Một file `<tên video>_roughcut.mp4`: cắt đúng từng khung hình, âm lượng đã chuẩn hoá -14 LUFS (mức YouTube).
- Một file `<tên video>_roughcut.cutlist.txt`: ghi lại mỗi đoạn đã bỏ, kèm lý do bỏ.

**Miễn phí, không cần API key của dịch vụ AI chuyển giọng nói thành văn bản** (như Vbee, OpenAI Whisper API…). Giọng nói được nhận dạng ngay trên máy bằng model Zipformer tiếng Việt (~70 MB, tải một lần). Skill đóng gói dùng thêm whisper.cpp chạy trên máy (~1.6 GB, tải một lần) để canh phụ đề và hiệu ứng khớp từng chữ.

---

## Cài đặt: dán 1 prompt

### Trước khi cài

- Máy **Mac** (đã chạy thử trên Mac Apple Silicon). Nếu chưa có [Homebrew](https://brew.sh), hãy cài trước.
- Ổ đĩa trống khoảng **3 GB** (thư viện + 2 model).
- Nên có Xcode Command Line Tools (`xcode-select --install`) để dùng hiệu ứng chữ nằm sau lưng người nói. Thiếu thì các phần khác vẫn chạy.
- Có **Claude Code** hoặc **Codex** (trợ lý lập trình của ChatGPT, bản CLI hoặc app desktop có quyền chạy lệnh trên máy).
  > ChatGPT bản chat trên web / điện thoại **không chạy được**, vì việc cắt video cần chạy ffmpeg và model ngay trên máy bạn.

### Prompt cài đặt

Mở Claude Code hoặc Codex, dán **nguyên văn** đoạn sau:

```text
Cài giúp mình bộ skill cắt thô video từ repo GitHub hocai-247/skill-edit-video.

1. Nếu chưa có thư mục ~/skill-edit-video thì chạy:
   git clone https://github.com/hocai-247/skill-edit-video.git ~/skill-edit-video
   Nếu có rồi thì chạy: git -C ~/skill-edit-video pull
2. Đọc file ~/skill-edit-video/install.sh trước, rồi chạy: bash ~/skill-edit-video/install.sh
   Nếu lỗi thì đọc thông báo, cài phần còn thiếu (Homebrew, uv, ffmpeg) rồi chạy lại cho tới khi thấy "XONG".
3. Báo lại cho mình bằng tiếng Việt: skill đã được gắn vào đâu (~/.claude/skills và/hoặc ~/.codex/skills),
   model đã tải xong chưa, và nhắc mình mở phiên mới để dùng.
```

Script cài đặt sẽ:

1. kiểm tra và cài `uv`, `ffmpeg-full` nếu máy chưa có;
2. cài thư viện Python;
3. tải model nhận dạng giọng nói (~70 MB) và kiểm tra checksum;
4. cài whisper.cpp và tải model `ggml-large-v3-turbo` (~1.6 GB, có kiểm checksum) cho skill đóng gói;
5. build tool tách người khỏi nền (Apple Vision) cho hiệu ứng chữ sau lưng;
6. gắn 3 skill vào `~/.claude/skills` (Claude Code) và `~/.codex/skills` (Codex, nếu máy có Codex). Nếu trước đó đã có skill trùng tên, bản cũ được cất vào `~/.skill-edit-video-backup/`;
7. chạy thử.

Chạy lại script bao nhiêu lần cũng không sao.

---

## Cách dùng

Mở một **phiên mới** của Claude Code hoặc Codex rồi nói tự nhiên, ví dụ:

- `cắt thô giúp mình video ~/Movies/intro.mov`
- `cắt thô video hướng dẫn này: ~/Desktop/huong-dan-claude.mov`
- `cắt thô intro, nhịp thong thả, xuất ra Desktop`
- `đóng gói video ~/Desktop/intro_roughcut.mp4: thêm phụ đề, motion graphic và sound effect`

Trợ lý sẽ:

1. **Nghe và phân tích** video. Clip 8 phút mất khoảng 20–60 giây; lần chạy lại cùng file gần như tức thì.
2. **Tự đọc lại các quyết định cắt** như một người biên tập, rồi báo bạn những chỗ nó chưa chắc. Ví dụ: "câu ở phút 2:10 có vẻ bạn nói lại, bỏ câu đầu nhé?"
3. **Xuất video** sau khi bạn đồng ý, kiểm tra hình và tiếng khớp nhau, rồi đưa bạn đường dẫn file.

Khi **đóng gói**, trợ lý canh thời điểm từng chữ bạn nói, chọn chỗ trống trong khung hình (không đè lên mặt), vẽ từng thẻ motion graphic bằng code, render bản xem trước để bạn góp ý, rồi mới xuất bản cuối. Bước này lâu hơn cắt thô (vài chục phút cho clip 1 phút). Trên Claude Code các thẻ được vẽ song song, trên Codex thì vẽ lần lượt nên chậm hơn.

### Mẹo để cắt chuẩn hơn

- **Tên riêng, từ tiếng Anh** hay bị nghe nhầm ("skill" thành "seo", "Claude" thành "cloud"). Hãy nói trước với trợ lý các tên có trong video, ví dụ: `trong video có nhắc Codex, Astra, Notion`. Khi tên được nhận đúng, trợ lý mới biết hai lần nói của cùng một câu là một.
- **Nhịp cắt**: mặc định là *nhanh* (cắt sát, rút ngắn khoảng ngắt). Muốn tự nhiên hơn thì nói "nhịp thong thả".
- **Video hướng dẫn**: skill coi bong bóng webcam nằm ở **góc dưới bên trái**. Nếu webcam của bạn ở chỗ khác, hãy nói cho trợ lý biết.
- Muốn **tự nghe lại từng câu** và bật/tắt bằng chuột thì mở giao diện web: `~/skill-edit-video/engine/run.sh` (trình duyệt sẽ mở http://127.0.0.1:8765). Các video trợ lý đã phân tích sẵn có trong danh sách gần đây.

### Giới hạn

- Mỗi lần cắt một video, có một người nói.
- Từ đệm dính liền vào câu, không có khoảng ngắt trước sau, thì không cắt được.
- Câu bạn cố ý lặp lại để nhấn mạnh có thể bị coi là nói lại. Trợ lý sẽ hỏi trước khi bỏ những câu dài.
- 2 skill cắt thô chỉ **cắt thô**. Phụ đề, hiệu ứng là việc của `dong-goi-video`.

---

## Cập nhật / gỡ cài

- **Cập nhật**: nói với trợ lý `cập nhật skill cắt thô`, hoặc tự chạy `git -C ~/skill-edit-video pull && bash ~/skill-edit-video/install.sh`.
- **Gỡ cài**: xoá các symlink `cat-tho-talking-head`, `cat-tho-huong-dan`, `dong-goi-video` trong `~/.claude/skills/` và `~/.codex/skills/`, rồi xoá thư mục `~/skill-edit-video`.

## Bên trong repo

```
skills/cat-tho-talking-head/SKILL.md   hướng dẫn cho trợ lý: cắt talking head
skills/cat-tho-huong-dan/SKILL.md      hướng dẫn cho trợ lý: cắt video hướng dẫn
skills/dong-goi-video/                 hướng dẫn + script đóng gói: phụ đề, thẻ motion graphic, SFX, render
engine/                                bộ máy cắt (Python + ffmpeg), có giao diện web
engine/scripts/roughcut_cli.py         lệnh analyze / realias / export mà skill gọi
engine/README.md                       mô tả kỹ thuật từng luật cắt (tiếng Anh)
install.sh                             script cài đặt
```

Video, bản cắt, cache và model đều nằm trong `engine/jobs`, `engine/cache`, `engine/models` trên máy bạn và không bao giờ được đẩy lên GitHub.
