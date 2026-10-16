# Skill cắt thô video (miễn phí, chạy trên máy)

Bộ này có 2 skill giúp Claude Code hoặc Codex (ChatGPT) **tự cắt thô video tiếng Việt** cho bạn. Bạn chỉ cần đưa file video và nói "cắt thô giúp mình".

| Skill | Dùng cho video nào | Skill làm gì |
|---|---|---|
| `cat-tho-talking-head` | Nói trước camera: intro, vlog, clip quay bằng điện thoại / DJI / webcam, vài phút | Bỏ đoạn im lặng, từ đệm (à, ừ, ờm), chỗ nói lắp, câu nói hỏng rồi nói lại (giữ lần nói cuối) |
| `cat-tho-huong-dan` | Quay màn hình có lời giảng: hướng dẫn dùng app, Claude Code, ChatGPT… | Như trên, thêm: **tua nhanh và tắt tiếng** đoạn chờ mà màn hình đang chạy, cắt đoạn chờ đứng yên, đánh dấu chỗ nghi bạn nói lặp để bạn duyệt |

Kết quả bạn nhận được:

- Một file `<tên video>_roughcut.mp4`: cắt đúng từng khung hình, âm lượng đã chuẩn hoá -14 LUFS (mức YouTube).
- Một file `<tên video>_roughcut.cutlist.txt`: ghi lại mỗi đoạn đã bỏ, kèm lý do bỏ.

**Miễn phí, không cần API key của dịch vụ AI chuyển giọng nói thành văn bản** (như Vbee, OpenAI Whisper API…). Giọng nói được nhận dạng ngay trên máy bằng model Zipformer tiếng Việt (~70 MB, tải một lần).

---

## Cài đặt: dán 1 prompt

### Trước khi cài

- Máy **Mac** (đã chạy thử trên Mac Apple Silicon). Nếu chưa có [Homebrew](https://brew.sh), hãy cài trước.
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
4. gắn 2 skill vào `~/.claude/skills` (Claude Code) và `~/.codex/skills` (Codex, nếu máy có Codex). Nếu trước đó đã có skill trùng tên, bản cũ được cất vào `~/.skill-edit-video-backup/`;
5. chạy thử.

Chạy lại script bao nhiêu lần cũng không sao.

---

## Cách dùng

Mở một **phiên mới** của Claude Code hoặc Codex rồi nói tự nhiên, ví dụ:

- `cắt thô giúp mình video ~/Movies/intro.mov`
- `cắt thô video hướng dẫn này: ~/Desktop/huong-dan-claude.mov`
- `cắt thô intro, nhịp thong thả, xuất ra Desktop`

Trợ lý sẽ:

1. **Nghe và phân tích** video. Clip 8 phút mất khoảng 20–60 giây; lần chạy lại cùng file gần như tức thì.
2. **Tự đọc lại các quyết định cắt** như một người biên tập, rồi báo bạn những chỗ nó chưa chắc. Ví dụ: "câu ở phút 2:10 có vẻ bạn nói lại, bỏ câu đầu nhé?"
3. **Xuất video** sau khi bạn đồng ý, kiểm tra hình và tiếng khớp nhau, rồi đưa bạn đường dẫn file.

### Mẹo để cắt chuẩn hơn

- **Tên riêng, từ tiếng Anh** hay bị nghe nhầm ("skill" thành "seo", "Claude" thành "cloud"). Hãy nói trước với trợ lý các tên có trong video, ví dụ: `trong video có nhắc Codex, Astra, Notion`. Khi tên được nhận đúng, trợ lý mới biết hai lần nói của cùng một câu là một.
- **Nhịp cắt**: mặc định là *nhanh* (cắt sát, rút ngắn khoảng ngắt). Muốn tự nhiên hơn thì nói "nhịp thong thả".
- **Video hướng dẫn**: skill coi bong bóng webcam nằm ở **góc dưới bên trái**. Nếu webcam của bạn ở chỗ khác, hãy nói cho trợ lý biết.
- Muốn **tự nghe lại từng câu** và bật/tắt bằng chuột thì mở giao diện web: `~/skill-edit-video/engine/run.sh` (trình duyệt sẽ mở http://127.0.0.1:8765). Các video trợ lý đã phân tích sẵn có trong danh sách gần đây.

### Giới hạn

- Mỗi lần cắt một video, có một người nói.
- Từ đệm dính liền vào câu, không có khoảng ngắt trước sau, thì không cắt được.
- Câu bạn cố ý lặp lại để nhấn mạnh có thể bị coi là nói lại. Trợ lý sẽ hỏi trước khi bỏ những câu dài.
- Đây là bản **cắt thô**. Phụ đề, hiệu ứng, nhạc là bước sau.

---

## Cập nhật / gỡ cài

- **Cập nhật**: nói với trợ lý `cập nhật skill cắt thô`, hoặc tự chạy `git -C ~/skill-edit-video pull && bash ~/skill-edit-video/install.sh`.
- **Gỡ cài**: xoá 4 symlink `~/.claude/skills/cat-tho-talking-head`, `~/.claude/skills/cat-tho-huong-dan`, `~/.codex/skills/cat-tho-talking-head`, `~/.codex/skills/cat-tho-huong-dan`, rồi xoá thư mục `~/skill-edit-video`.

## Bên trong repo

```
skills/cat-tho-talking-head/SKILL.md   hướng dẫn cho trợ lý: cắt talking head
skills/cat-tho-huong-dan/SKILL.md      hướng dẫn cho trợ lý: cắt video hướng dẫn
engine/                                bộ máy cắt (Python + ffmpeg), có giao diện web
engine/scripts/roughcut_cli.py         lệnh analyze / realias / export mà skill gọi
engine/README.md                       mô tả kỹ thuật từng luật cắt (tiếng Anh)
install.sh                             script cài đặt
```

Video, bản cắt, cache và model đều nằm trong `engine/jobs`, `engine/cache`, `engine/models` trên máy bạn và không bao giờ được đẩy lên GitHub.
