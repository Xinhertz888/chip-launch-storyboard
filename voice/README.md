# 统一配音 · voice/

「芯品发布会」所有视频的配音都从这里统一：同一个声音、同一套流程。

## 方案

| 方案 | 说明 | 什么时候用 |
|---|---|---|
| **A. SiliconFlow API（推荐）** | 调用开源声音克隆模型（CosyVoice2 / IndexTTS-2 / Fish Speech），无需本地 GPU | 日常配音，`dub.py` 直接跑 |
| **B. 本地自部署** | [index-tts/index-tts](https://github.com/index-tts/index-tts)（B站出品，24k+ stars，中文强＋精确时长控制） | 有 GPU 机器时 |

本目录默认走方案 A。两个方案用的都是开源模型，声音标准一致。

## 三步上手（方案 A）

### 1. 拿 API Key

1. 注册 https://cloud.siliconflow.cn （新用户有免费额度）
2. **完成实名认证**（上传自定义音色必需）
3. 到 https://cloud.siliconflow.cn/account/ak 获取 API Key
4. 复制 `voice/.env.example` 为 `voice/.env`，填入 `SILICONFLOW_API_KEY`

```bash
pip install -r voice/requirements.txt
cp voice/.env.example voice/.env   # 然后填 key
```

### 2. 上传你的声音，生成专属音色（只需一次）

`voice/reference/` 已有 6 段基准配音（2026-10-18 入库，ADC34DSO75 第一期分镜配音稿）：

| 文件 | 时长 | 内容 |
|---|---|---|
| sample1.mp3 | 5.7s | 固定开场白：芯品发布会，一分钟带你看懂最新芯片…… |
| sample2.mp3 | 9.5s | 芯片参数介绍段 |
| sample3.mp3 | 10.7s | 痛点段（AI 数据中心电压毛刺） |
| sample4.mp3 | 9.8s | 方案段（事件检测＋存储做进片子里） |
| sample5.mp3 | 4.4s | 应用场景段 |
| sample6.mp3 | 4.4s | 收束＋关注 |

每段配有同名 `.txt`（文字稿取自分镜脚本配音稿原文，已请用户校对）。
**克隆推荐用 sample3**（10.7 秒，语气最完整）。

```bash
cd voice
python dub.py upload-voice --audio reference/sample3.mp3 \
    --text "$(cat reference/sample3.txt)" --name xinpin-voice
```

把输出的 URI（形如 `speech:xxx`）写进 `.env` 的 `XINPIN_VOICE_URI`。
从此所有配音都是这个声音。

### 3. 配音稿 → 音频

配音稿 txt 每行一段（空行/`#`开头跳过），例如：

```
芯品发布会，一分钟带你看懂最新芯片。
这颗芯片是……
```

```bash
python dub.py dub --script peiyin.txt --out out/lps27dewo
```

得到 `out/lps27dewo/line_01.mp3…` ＋ `manifest.json`（每段文字、字符数、时长）。
时长直接拿去排分镜时间轴——正好对应 skill 里"先配音定出准确时长"的流程。

常用参数：`--speed 1.1` 加速；`--model IndexTTS-2` 换模型（模型广场确认 ID）；`--voice` 临时换音色。

## 费用参考

按输入文本 UTF-8 字节计费。CosyVoice2-0.5B 约 $7.15/M 字节：
一期 60 秒配音约 300 字 ≈ 900 字节 ≈ **0.006 美元**，基本等于免费。

## 和分镜流程的衔接

1. 按 skill 写出分镜脚本，定稿配音稿（中文口播，4~5 字/秒）
2. 把配音稿存成 txt，跑 `dub.py dub`
3. 用 `manifest.json` 的时长排时间轴、做画面（Opus 5.5 实现路线）
4. 字幕直接取配音稿文本，逐字对齐

## 方案 B：本地自部署（有 GPU 的机器）

```bash
git clone https://github.com/index-tts/index-tts && cd index-tts
# 按仓库 README 安装（需 Python 3.10+、PyTorch、8GB+ 显存）
uv run webui.py          # 浏览器打开 http://127.0.0.1:7860，可视化克隆
# 或命令行：
PYTHONPATH="$PYTHONPATH:." uv run indextts/infer_v2.py
```

Python 调用示例（以 `voice/reference/sample1.mp3` 为音色参考）：

```python
from indextts.infer_v2 import IndexTTS2
tts = IndexTTS2(cfg_path="checkpoints/config.yaml", model_dir="checkpoints")
tts.infer(spk_audio_prompt="voice/reference/sample1.mp3",
          text="芯品发布会，一分钟带你看懂最新芯片。",
          output_path="out.wav")
```

> 云电脑（2 核 / 7.7G 内存 / 无 GPU）跑不动这类模型，
> 日常直接用方案 A；方案 B 留给有显卡的机器。
