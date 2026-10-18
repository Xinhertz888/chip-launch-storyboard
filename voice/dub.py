#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
芯品发布会 · 统一配音工具

后端：SiliconFlow TTS API（调用开源声音克隆模型，无需本地 GPU）
  - 默认 FunAudioLLM/CosyVoice2-0.5B（中文自然，文档完备）
  - 可换 IndexTTS-2（B站出品，中文强＋精确时长控制，适合"先配音定出准确时长"）
  - 可换 Fish Speech 系（综合质量口碑最好）
  - 有 GPU 机器想本地跑：见 voice/README.md（index-tts/index-tts）

两种用法（在 voice/ 目录下执行）：

  1) 上传参考音频，生成专属音色 URI（只需做一次）：
     python dub.py upload-voice --audio reference/sample1.mp3 \
         --text "$(cat reference/sample1.txt)" --name xinpin-voice
     把输出的 URI 写进 .env 的 XINPIN_VOICE_URI。

  2) 配音稿合成（txt 每行一段，空行/#开头跳过）：
     python dub.py dub --script peiyin.txt --out out/lps27dewo
     得到 out/lps27dewo/line_01.mp3 … ＋ manifest.json（含每段时长，供分镜时间轴用）

依赖：pip install -r requirements.txt
"""

import argparse
import json
import os
import subprocess
import sys

API_BASE = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "FunAudioLLM/CosyVoice2-0.5B"


def load_dotenv(path):
    """极简 .env 解析（无第三方依赖）。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_key(args):
    key = args.api_key or os.environ.get("SILICONFLOW_API_KEY")
    if not key:
        sys.exit(
            "缺少 API Key。请：\n"
            "  1) 去 https://cloud.siliconflow.cn/account/ak 注册并获取 Key\n"
            "     （注意：上传自定义音色需要先完成实名认证）\n"
            "  2) 复制 voice/.env.example 为 voice/.env 并填入 SILICONFLOW_API_KEY"
        )
    return key


def api_headers(key):
    return {"Authorization": f"Bearer {key}"}


def cmd_upload_voice(args):
    import requests

    key = get_key(args)
    if not os.path.exists(args.audio):
        sys.exit(f"找不到参考音频：{args.audio}")
    if not args.text or not args.text.strip():
        sys.exit("必须提供参考音频的完整文字内容（--text），且逐字一致。")

    model = args.model or os.environ.get("XINPIN_MODEL", DEFAULT_MODEL)
    print(f"上传参考音频 {args.audio}（模型 {model}）…")
    with open(args.audio, "rb") as fh:
        r = requests.post(
            f"{API_BASE}/uploads/audio/voice",
            headers=api_headers(key),
            files={"file": fh},
            data={"model": model, "customName": args.name, "text": args.text.strip()},
            timeout=120,
        )
    if r.status_code == 401:
        sys.exit("API Key 无效（401）。请检查 .env 中的 SILICONFLOW_API_KEY。")
    if r.status_code != 200:
        sys.exit(f"上传失败（{r.status_code}）：{r.text[:500]}")
    uri = r.json().get("uri")
    if not uri:
        sys.exit(f"接口未返回音色 URI：{r.text[:500]}")
    print("\n上传成功！专属音色 URI：")
    print(uri)
    print("\n把它写进 voice/.env：")
    print(f"XINPIN_VOICE_URI={uri}")


def synth_one(key, model, voice, text, speed, out_path):
    import requests

    r = requests.post(
        f"{API_BASE}/audio/speech",
        headers={**api_headers(key), "Content-Type": "application/json"},
        data=json.dumps(
            {
                "model": model,
                "input": text,
                "voice": voice,
                "response_format": "mp3",
                "speed": speed,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        timeout=180,
    )
    if r.status_code == 401:
        sys.exit("API Key 无效（401）。请检查 .env 中的 SILICONFLOW_API_KEY。")
    if r.status_code == 402:
        sys.exit("账户余额不足（402）。请去 SiliconFlow 后台充值或领免费额度。")
    if r.status_code != 200:
        raise RuntimeError(f"合成失败（{r.status_code}）：{r.text[:300]}")
    with open(out_path, "wb") as f:
        f.write(r.content)


def probe_duration(path):
    """用 ffprobe 读时长；没有 ffprobe 就返回 None。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        return round(float(out.stdout.strip()), 2)
    except Exception:
        return None


def cmd_dub(args):
    key = get_key(args)
    voice = args.voice or os.environ.get("XINPIN_VOICE_URI")
    if not voice:
        sys.exit(
            "缺少音色 URI。请先跑 upload-voice 得到 URI，再：\n"
            "  1) 写进 voice/.env 的 XINPIN_VOICE_URI，或\n"
            "  2) 用 --voice speech:xxx 传入"
        )
    model = args.model or os.environ.get("XINPIN_MODEL", DEFAULT_MODEL)
    if not os.path.exists(args.script):
        sys.exit(f"找不到配音稿：{args.script}")

    with open(args.script, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        sys.exit("配音稿是空的（每行一段，空行和 # 开头会被跳过）。")

    os.makedirs(args.out, exist_ok=True)
    print(f"共 {len(lines)} 段，模型 {model}，开始合成…")
    manifest = []
    for i, text in enumerate(lines, 1):
        out_path = os.path.join(args.out, f"line_{i:02d}.mp3")
        print(f"  [{i}/{len(lines)}] {text[:24]}…")
        synth_one(key, model, voice, text, args.speed, out_path)
        manifest.append({
            "line": i,
            "text": text,
            "file": os.path.basename(out_path),
            "chars": len(text),
            "duration_sec": probe_duration(out_path),
        })

    manifest_path = os.path.join(args.out, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    total = sum(m["duration_sec"] or 0 for m in manifest)
    print(f"\n完成：{args.out}/（{len(lines)} 段）")
    if total:
        print(f"总时长约 {total:.1f} 秒（{total/60:.1f} 分钟），供分镜时间轴使用")
    else:
        print("未装 ffprobe，无法统计时长；manifest.json 里 duration_sec 为 null")
    print(f"明细见 {manifest_path}")


def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    ap = argparse.ArgumentParser(description="芯品发布会 · 统一配音工具")
    ap.add_argument("--api-key", default=None, help="SiliconFlow API Key（默认读 .env）")
    ap.add_argument("--model", default=None,
                    help=f"TTS 模型（默认 {DEFAULT_MODEL}）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_up = sub.add_parser("upload-voice", help="上传参考音频，生成专属音色 URI")
    p_up.add_argument("--audio", required=True, help="参考音频路径（8~10 秒，清晰无噪）")
    p_up.add_argument("--text", required=True, help="参考音频的完整文字内容（逐字一致）")
    p_up.add_argument("--name", default="xinpin-voice", help="音色名称")
    p_up.set_defaults(func=cmd_upload_voice)

    p_dub = sub.add_parser("dub", help="配音稿合成")
    p_dub.add_argument("--script", required=True, help="配音稿 txt（每行一段）")
    p_dub.add_argument("--out", required=True, help="输出目录")
    p_dub.add_argument("--voice", default=None, help="音色 URI（默认读 .env）")
    p_dub.add_argument("--speed", type=float, default=1.0, help="语速（0.25~4.0，默认 1.0）")
    p_dub.set_defaults(func=cmd_dub)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
