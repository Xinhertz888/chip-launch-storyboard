#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
芯品发布会 · 配音质检工具（纯本地，无需 API Key）

用户每期自己录制配音（分段 mp3），本工具做两件事：
  1) 质检：文件是否齐全、格式是否规范、时长是否与配音稿匹配
  2) 输出 manifest.json：每段精确时长，供分镜"先配音定出准确时长"排时间轴

用法（在 voice/ 目录下）：
  python check.py --segs ./new_episode_segs --script peiyin.txt --out ./out

  new_episode_segs/ 下放 seg1.mp3、seg2.mp3 …（有几段放几个）
  peiyin.txt 每行一段（与分镜脚本配音稿逐字一致，空行/#开头跳过）

依赖：系统装有 ffmpeg（含 ffprobe）。无需 pip 包。
"""

import argparse
import json
import os
import subprocess
import sys


def probe(path):
    """返回 dict(duration, sample_rate, channels)，失败返回 None。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=sample_rate,channels",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        info = json.loads(out.stdout)
        fmt = info.get("format", {})
        stream = (info.get("streams") or [{}])[0]
        return {
            "duration": round(float(fmt.get("duration", 0)), 2),
            "sample_rate": stream.get("sample_rate"),
            "channels": stream.get("channels"),
        }
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="芯品发布会 · 配音质检工具")
    ap.add_argument("--segs", required=True, help="分段配音目录（seg1.mp3、seg2.mp3 …）")
    ap.add_argument("--script", required=True, help="配音稿 txt（每行一段）")
    ap.add_argument("--out", required=True, help="输出目录（manifest.json 写到这里）")
    args = ap.parse_args()

    for cmd in ("ffprobe",):
        if subprocess.run(["which", cmd], capture_output=True).returncode != 0:
            sys.exit(f"找不到 {cmd}，请先安装 ffmpeg。")

    if not os.path.isdir(args.segs):
        sys.exit(f"找不到分段目录：{args.segs}")
    with open(args.script, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        sys.exit("配音稿是空的。")

    print(f"配音稿 {len(lines)} 段，开始质检…")
    manifest, warns = [], []
    for i, text in enumerate(lines, 1):
        seg = os.path.join(args.segs, f"seg{i}.mp3")
        if not os.path.exists(seg):
            # 兼容 wav
            alt = os.path.join(args.segs, f"seg{i}.wav")
            seg = alt if os.path.exists(alt) else seg
        if not os.path.exists(seg):
            warns.append(f"第 {i} 段缺文件：{args.segs}/seg{i}.mp3（或 .wav）")
            manifest.append({"seg": i, "text": text, "file": None,
                             "chars": len(text), "duration_sec": None})
            continue
        info = probe(seg)
        if not info or not info["duration"]:
            warns.append(f"第 {i} 段无法读取音频信息：{seg}")
            manifest.append({"seg": i, "text": text, "file": os.path.basename(seg),
                             "chars": len(text), "duration_sec": None})
            continue
        dur, expected = info["duration"], len(text) / 4.5  # 4~5 字/秒
        if dur < 2:
            warns.append(f"第 {i} 段仅 {dur}s，过短，检查是否录全")
        if expected > 0 and abs(dur - expected) / expected > 0.4:
            warns.append(
                f"第 {i} 段 {dur}s，与按 4.5 字/秒估算的 {expected:.1f}s 偏差超 40%，"
                "检查语速或文字稿是否一致")
        manifest.append({"seg": i, "text": text, "file": os.path.basename(seg),
                         "chars": len(text), "duration_sec": dur,
                         "sample_rate": info["sample_rate"],
                         "channels": info["channels"]})

    os.makedirs(args.out, exist_ok=True)
    mp = os.path.join(args.out, "manifest.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    total = sum(m["duration_sec"] or 0 for m in manifest)
    print(f"\n质检完成：{mp}")
    print(f"共 {len(lines)} 段，总时长 {total:.1f}s（{total/60:.1f} 分钟）")
    if warns:
        print("\n⚠ 发现问题：")
        for w in warns:
            print("  -", w)
    else:
        print("全部通过 ✅")


if __name__ == "__main__":
    main()
