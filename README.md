# PTCG 视频搬运流水线

把 YouTube 上的宝可梦集换式卡牌（PTCG）视频，做成**中英双语硬字幕**并上传 B 站。

---

## 一、为什么按这个时间窗口选片

**国内简中版比国际版滞后约 17 个月。**

| 国际版扩展包 | 国际发布 | 国内对应 |
|---|---|---|
| Black Bolt / White Flare（黑白） | 2025-06 | **当前版本** |
| Mega Evolution 基础包 | 2025-09 | 下个月起 |

→ 搬运窗口取 **2025-06 ~ 2025-10**。国内每进一个新版本，窗口整体后移。

### 内容源

- **Control Players Unite**（`@ControlPlayersUnite`）——控制卡组专精，一周约 2 条。
  2025-06~10 这个窗口内有 38 条，其中控制类占大多数。
- ~~Alloutblitzle~~ **已排除**：210 条视频里 165 条是 3 年前的 PTCGO 时代内容，版本对不上。

---

## 二、一次性准备

```bash
cd ptcg
source .venv/bin/activate

# 依赖已装好：ffmpeg-full / yt-dlp / mlx-whisper / bilibili-api-python
# 如需重装：
brew install ffmpeg-full yt-dlp
uv pip install --python .venv/bin/python mlx-whisper bilibili-api-python curl_cffi aiohttp
```

### B 站登录（只需一次）

```bash
python bin/login.py
```

会生成 `config/bili_qrcode.png`，用 B 站 App 扫码并在手机上确认。

> **必须用 TV 端扫码流程。** 网页端流程拿回来的 cookie 是空的（社区库解析 URL 参数失效），
> TV 端直接返回 `cookie_info` 结构，才有真实值。

Cookie 存在 `config/bili_cookies.json`，包含 `SESSDATA` / `bili_jct` / `DedeUserID` 等 8 项。

---

## 三、日常使用

```bash
# 一条视频跑到底（下载→转录→翻译→清洗→双语字幕→字幕审核→压制→生成投稿信息）
python bin/run.py <videoId 或 YouTube 链接>

# 链接随便哪种形式都行：
python bin/run.py "https://www.youtube.com/watch?v=5SEUZlKhp0Y"
python bin/run.py "https://youtu.be/5SEUZlKhp0Y"
python bin/run.py "https://www.youtube.com/live/5SEUZlKhp0Y?t=10"

# 跑到翻译为止，先看看字幕质量
python bin/run.py <videoId> --to 30

# 翻译不满意，重翻（覆盖已有 zh.srt）
python bin/run.py <videoId> --from 30 --to 30 --force

# 批量
python bin/run.py --list config/batch1.json

# 上传到 B 站
python bin/70_upload.py <videoId>

# 先看上传参数不实际提交
python bin/70_upload.py <videoId> --dry-run
```

产物都在 `data/jobs/<videoId>/`：

| 文件 | 说明 |
|---|---|
| `source.mp4` | 原始视频 |
| `source.whisper.srt` | Whisper 英文转录（工作用） |
| `source.ytasr.srt` | YouTube 自动字幕（对照参考） |
| `zh.srt` | 中文译文 |
| `bilingual.ass` | 双语 ASS 字幕 |
| `final.mp4` | 成片（硬字幕） |
| `bili.json` | 投稿标题/简介/标签/封面文字 |
| `upload_result.json` | 上传结果（aid/bvid） |

---

## 四、各阶段说明

| 脚本 | 做什么 | 关键点 |
|---|---|---|
| `10_download.py` | 下 1080p + 英文自动字幕 + 元数据 | 走 yt-dlp，抓 `--write-auto-subs` |
| `20_transcribe.py` | mlx-whisper large-v3 本地转录 | 带 PTCG 术语 initial-prompt |
| `30_translate.py` | DeepSeek 分批翻译 | 25 条一批，逐批注入相关术语 |
| `35_cleanup.py` | 中文后处理 | 修 token 崩坏、统一类型名 |
| `40_bilingual.py` | 合成双语 ASS | 中文在上英文在下 |
| `50_render.py` | 硬字幕压制 | H.264 CRF 20 |
| `60_meta.py` | 生成投稿信息 + 抽封面帧 | 模型起标题/写简介 |
| `70_upload.py` | 上传 B 站 | 强制转载 + 标题前缀 |
| `login.py` | B 站扫码登录 | TV 端流程 |

---

## 四·五、投稿文案规则

标题和简介有两部分是**程序强制写入**的，不交给模型，保证每期一致：

**标题前缀**

```
【搬运】【自用】【黑雷白焰】控制向新卡Top10盘点
└─ 固定前缀 ──┘└─ 模型生成 ────────┘
```

由 `60_meta.py` 生成时加上，`70_upload.py` 上传前再校验一次，重复会自动去掉。

**每条视频的额外信息（可选）**

在 `data/jobs/<视频ID>/extra.json` 里可以单独设置：

```json
{
  "title_tag": "超前环境",
  "note": "📌 版本说明：本视频来自国际版 2026 年 4 月，比国内当前版本超前约 10 个月……"
}
```

- `title_tag` 插在【搬运】【自用】之后，例如 `【搬运】【自用】【超前环境】【烈腿蝗控制】…`
- `note` 追加到简介开头，用来解释版本差异、卡池限制等

**简介尾部**

```
<模型写的卡组思路与看点>

⚠️ 本视频字幕由 AI 机器翻译，可能存在错译或术语不准，
欢迎在评论区指正，会持续修正。
素材来源：YouTube 频道 Control Players Unite
原视频：https://www.youtube.com/watch?v=xxxx
```

机翻声明是**必须**的 —— 实际译文确实有错（卡名被 ASR 听错、术语偶有偏差），
提前说明比被观众挑出来好。模型只负责写前半段内容介绍。

## 五、配置文件

| 文件 | 用途 |
|---|---|
| `config/settings.json` | 模型、字体、压制参数 |
| `config/glossary.json` | **4366 条**卡名官方简中译名（PokeAPI 数据 + 手工补充） |
| `config/aliases.json` | ASR 听错的卡名 → 正确英文名 |
| `config/cleanup.json` | 翻译后清洗规则 |
| `config/batch1.json` | 批量清单 |

### 维护 `aliases.json`（重要）

Whisper 会把卡名听错，例如：

```
Budew      → 被听成 "Bidou"
Krookodile → 被听成 "Crocodile"
Elgyem     → 被听成 "Elgium"
```

这些必须写进 `aliases.json`，翻译前会先把英文原文改写成正确卡名再送进模型。
**每做一条新视频，把发现的错音补进来，这张表会越用越准。**

### 维护 `cleanup.json`

模型偶尔会输出乱码词，例如把「你」写成「酸奶」。
在 `replace` 里加一条即可。替换按**长词优先**执行，所以 `酸奶回合一次` 会先于 `酸奶` 匹配。

---

## 六、踩过的坑（都解决了，别再来一遍）

### 1. HuggingFace 模型下载卡死

`mlx-whisper` 首次运行要下 large-v3（约 3GB）。走默认 Xet 传输通道会卡在 0 字节不动。

```bash
export HF_HUB_DISABLE_XET=1
```

或用镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 2. Homebrew 的 ffmpeg 没有 libass

普通 `ffmpeg` 编译时没带 `--enable-libass`，`subtitles` / `ass` 滤镜不可用，压制直接报 `No such filter`。

→ 必须装 **`ffmpeg-full`**。

### 3. ffmpeg 字幕滤镜的路径转义

```bash
# 错
-vf "subtitles=bilingual.ass:fontsdir=."
# 对
-vf "subtitles=filename=bilingual.ass"
```

### 4. `biliup` 装不上

PyPI 的 `biliup 1.3.5` 是空包，没有模块也没有 CLI；`biliup-rs` 只有 Linux wheel。
→ 改用 `bilibili-api-python`。

### 5. B 站网页端扫码 cookie 为空

`QrCodeLoginChannel.WEB` 解析 URL 参数取 cookie，实测全空。
→ 改用 `QrCodeLoginChannel.TV`，并在手机上确认一次。

### 6. `original` 参数类型坑

```python
# 错：0 是 falsy，但被当成 True，导致 copyright=1（自制）
original=0
# 对
original=False   # copyright=2（转载）
```

### 7. 标题必须带前缀

上传前强制加 `【搬运】【自用】`：

```python
TITLE_PREFIX = "【搬运】【自用】"
```

`ensure_title_prefix()` 会去掉重复前缀再加一次，不会叠两层。

### 8. 已发布稿件的编辑接口也受限

`/x/vu/web/edit` 需要完整稿件参数，实测返回 `-400 请求错误`。
→ **改简介/标题去创作中心手动改**，脚本只负责首次上传。

### 9. B 站删除接口要图形验证码

`member.bilibili.com/x/web/archive/delete` 返回 `340022 验证码错误`，脚本删不了。
→ 删除旧稿件只能去创作中心手动操作。

---

## 七、质量检查清单

每条视频发之前过一遍：

- [ ] 中文里没有成段英文（卡名允许括号保留英文）
- [ ] 卡名是官方简中译名（对照 `glossary.json`）
- [ ] 没有「酸奶」这类 token 崩坏词
- [ ] 双语字幕位置不挡画面主体
- [ ] 标题带 `【搬运】【自用】`
- [ ] 版权选「转载」，原链接填对
- [ ] 简介里注明来源频道

---

## 八、待办

- [ ] 封面加中文字（现在只抽帧，`cover_text` 生成了但没用）
- [ ] `glossary.json` 补全到黑白版全卡池的卡牌道具名（现在道具名只有几十条）
- [ ] 支持定时/队列，一次提交多条
- [ ] 大文件上传时调低分片并发（57 分片的 567MB 视频有 6 个分片 SSL 报错，靠重试补上）

## 翻译模型：云端 / 本地切换

流水线默认用 Alma 的云端 provider 翻译，也可以改成本地 Ollama。

```bash
python bin/use_local.py            # 看当前用哪个后端，本地模式会顺带列 Ollama 里的模型
python bin/use_local.py local      # 切本地（config/settings.json 里 provider.mode = "local"）
python bin/use_local.py cloud      # 切回云端
```

本地模式的几个细节：

- 走 Ollama 的 `/api/chat`，不是 OpenAI 兼容接口。
- **必须传 `think: false`**：qwen3.5 默认开思考，会把上下文耗在思考上并破坏 JSON 输出契约。
- 不发 `format: json`：当前这版 Ollama 的 MLX runner 会直接返回 `501 structured output is unavailable`，
  所以 JSON 只能靠提示词约束，`parse_json()` 里有容错（能从句中被截断的结果里抢救完整的行）。
- `num_ctx` 默认 32768，批量 25 条字幕加题库够用。

`config/settings.json` 结构：

```json
"provider": {
  "mode": "cloud",
  "model": "workbuddy/deepseek-v4.1-flash",
  "local": { "base": "http://localhost:11434", "model": "qwen3.5:9b", "num_ctx": 32768 }
}
```

## 为什么先审字幕再压制

压制（50_render）是整条流程里最贵的一步：一期 80 分钟的视频要几分钟 CPU、
产出 2GB 左右，改一条错字就得重来一遍。所以流程改成：

    30 翻译 → 35 清洗 → 40 双语字幕 → **45 审核** → 50 压制 → 60 投稿信息

`45_review.py` 做两件事：

1. **能自动修的当场修掉**：没翻的英文卡名替换成官方简中名；和官方名只差一两个
   字的错译（保母曼波→保姆曼波 这类）改正。
2. **修不了的直接拦住**：纯英文整句、中文里夹着一长串英文、卡名仍是英文、
   还有没纠正的近似名 —— 只要有一项，就以非 0 退出，`50_render.py` 拒绝执行。

`50_render.py` 自己也有两道保险：

- 没有 `review.json`、或 `zh.clean.srt` 比 `review.json` 新，直接拒绝；
- 字幕和编码参数都没变过、`final.mp4` 已经存在，就跳过重压（`--force` 可强制）。

审核结果写在 `data/jobs/<id>/review.json`，想跳过自动修正用
`python bin/45_review.py <id> --no-fix`。

**千万别再「先压了再说」**：一次重压是十几分钟机器时间，一次审核是几秒钟。
