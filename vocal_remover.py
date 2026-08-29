# -*- coding: utf-8 -*-
"""视频去人声工具 - 核心处理模块。

处理流程:
1. ffprobe 读取视频信息（视频流 / 音轨 / 字幕 / 章节 / 元数据）
2. ffmpeg 从视频中无损提取音轨，转成 44.1kHz 立体声 wav
3. Demucs AI 模型把音轨分离成「人声」和「无人声伴奏」两部分
4. ffmpeg 重新封装: 视频流直接流复制(-c:v copy, 零重编码, 逐位不变),
   字幕/章节/元数据原样保留, 仅音轨换成去人声后的版本

因此视频画面、字幕、章节、元数据完全不受影响。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

SAMPLE_RATE = 44100  # Demucs 模型的原生采样率

# 本地模型仓库: 存在则通过 --repo 使用, 避免首次运行联网下载
# (官方源 https://dl.fbaipublicfiles.com 在部分地区无法访问)
MODEL_REPO = Path(__file__).resolve().parent / "models"

__all__ = [
    "Options",
    "remove_vocals",
    "probe",
    "VocalRemoverError",
    "NoAudioTrackError",
    "CancelledError",
    "find_tools",
]


class VocalRemoverError(RuntimeError):
    """处理失败。"""


class NoAudioTrackError(VocalRemoverError):
    """视频里没有音轨。"""


class CancelledError(VocalRemoverError):
    """用户取消。"""


@dataclass
class Options:
    model: str = "htdemucs"   # 分离模型: htdemucs=标准(快) / htdemucs_ft=高质量(慢)
    bitrate: str = "320k"     # 输出音轨码率
    device: str = "auto"      # auto / cpu / cuda
    tracks: str = "all"       # all=处理全部音轨 / first=仅处理第一条, 其余原样保留


# 进度回调: (阶段, 0~1 进度或 None, 说明文字) -> 返回 False 表示请求取消
ProgressCB = Callable[[str, Optional[float], str], bool]

_TOOLS: Optional[tuple] = None


def find_tools() -> tuple:
    """定位 ffmpeg / ffprobe。"""
    global _TOOLS
    if _TOOLS is None:
        ff = shutil.which("ffmpeg")
        fp = shutil.which("ffprobe")
        if not ff or not fp:
            raise VocalRemoverError(
                "未找到 ffmpeg / ffprobe。请先安装 FFmpeg 并加入 PATH，\n"
                "例如: winget install Gyan.FFmpeg"
            )
        _TOOLS = (str(Path(ff)), str(Path(fp)))
    return _TOOLS


def _run(cmd) -> subprocess.CompletedProcess:
    p = subprocess.run([str(c) for c in cmd], capture_output=True)
    if p.returncode != 0:
        err = (p.stderr or b"").decode("utf-8", "replace").strip()[-2000:]
        raise VocalRemoverError(f"命令执行失败: {Path(cmd[0]).name} ...\n{err}")
    return p


def probe(path) -> dict:
    """用 ffprobe 读取媒体信息。"""
    _, ffprobe = find_tools()
    p = _run([
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    return json.loads(p.stdout.decode("utf-8", "replace"))


def _audio_codec_for(suffix: str, bitrate: str) -> tuple:
    """按输出容器选择音轨编码器（音轨内容变了必须重编码，视频流不受影响）。"""
    s = suffix.lower()
    if s == ".webm":
        return "libopus", bitrate or "192k"
    if s == ".avi":
        return "libmp3lame", bitrate or "320k"
    return "aac", bitrate or "320k"


_PCT = re.compile(r"(\d{1,3})%")

_NVIDIA: Optional[bool] = None


def _has_nvidia() -> bool:
    """是否有可用的 NVIDIA GPU（缓存结果）。"""
    global _NVIDIA
    if _NVIDIA is None:
        exe = shutil.which("nvidia-smi")
        if not exe:
            _NVIDIA = False
        else:
            try:
                _NVIDIA = subprocess.run([exe], capture_output=True,
                                         timeout=5).returncode == 0
            except Exception:
                _NVIDIA = False
    return _NVIDIA


def _run_demucs(wav: Path, out_dir: Path, opts: Options,
                cb: ProgressCB, label: str, base: float, span: float) -> Path:
    """调用 Demucs 分离人声，返回 no_vocals.wav 的路径。"""
    def build_args(segment: Optional[float], device: str):
        args = [
            sys.executable, "-m", "demucs.separate",
            "--two-stems", "vocals",
            "-n", opts.model,
            "-o", str(out_dir),
            "-d", device,
        ]
        local_yaml = MODEL_REPO / f"{opts.model}.yaml"
        if MODEL_REPO.is_dir() and local_yaml.exists():
            args += ["--repo", str(MODEL_REPO)]
        if segment:
            args += ["--segment", str(segment)]
        args.append(str(wav))
        return args

    if opts.device == "auto":
        device = "cuda" if _has_nvidia() else "cpu"
    else:
        device = opts.device
    segment = None
    last_err = ""
    for attempt in range(3):
        proc = subprocess.Popen(build_args(segment, device),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        tail = ""
        buf = b""
        cancelled = False
        while True:
            ch = proc.stderr.read(1)
            if not ch:
                break
            buf += ch
            if ch in (b"\r", b"\n"):
                line = buf.decode("utf-8", "replace").strip()
                buf = b""
                if not line:
                    continue
                tail = line
                m = _PCT.findall(line)
                if m:
                    pct = min(int(m[-1]), 100)
                    if not cb("separate", base + span * pct / 100.0,
                              f"{label} AI 分离人声 {pct}%"):
                        cancelled = True
                        proc.kill()
                        break
        proc.wait()
        if cancelled:
            raise CancelledError()
        no_voc = out_dir / opts.model / wav.stem / "no_vocals.wav"
        if proc.returncode == 0 and no_voc.exists():
            return no_voc
        last_err = (tail or "")[-800:]
        combined = last_err.lower()
        if "out of memory" in combined and device == "cuda" and attempt == 0:
            segment = 4  # 缩小分段降低显存占用后重试
            continue
        if device == "cuda" and attempt <= 1:
            device = "cpu"  # GPU 不可用时退回 CPU
            segment = None
            continue
        break
    raise VocalRemoverError(f"AI 人声分离失败:\n{last_err}")


def remove_vocals(input_path, output_path=None,
                  options: Optional[Options] = None,
                  progress: Optional[ProgressCB] = None) -> Path:
    """去掉视频里的人声，返回输出文件路径。

    input_path  : 输入视频
    output_path : 输出视频；缺省为「原名_无人声.扩展名」放在同目录
    progress    : 可选进度回调，返回 False 可取消
    """
    input_path = Path(input_path).absolute()
    opts = options or Options()
    cb: ProgressCB = progress or (lambda *a: True)

    if not input_path.exists():
        raise VocalRemoverError(f"文件不存在: {input_path}")
    if output_path is None:
        output_path = input_path.with_name(input_path.stem + "_无人声" + input_path.suffix)
    output_path = Path(output_path).absolute()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    info = probe(input_path)
    streams = info.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams:
        raise VocalRemoverError(f"文件里没有视频画面流: {input_path.name}")
    if not audio_streams:
        raise NoAudioTrackError(f"视频里没有音轨，无法去人声: {input_path.name}")

    todo = audio_streams if opts.tracks == "all" else audio_streams[:1]
    sel_idx = {s["index"] for s in todo}

    ffmpeg, _ = find_tools()
    total = max(len(todo), 1)
    with tempfile.TemporaryDirectory(prefix="novoice_") as td:
        tdp = Path(td)
        sep_wavs = []
        for k, s in enumerate(todo):
            base, span = k / total, 1.0 / total
            label = f"[音轨{k + 1}/{total}]"
            if not cb("extract", base, f"{label} 提取音频..."):
                raise CancelledError()
            wav = tdp / f"track{k}.wav"
            _run([
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(input_path),
                "-map", f"0:{s['index']}", "-vn",
                "-c:a", "pcm_f32le", "-ar", str(SAMPLE_RATE), "-ac", "2",
                str(wav),
            ])
            sep_wavs.append(_run_demucs(wav, tdp / f"sep{k}", opts, cb,
                                        label, base, span))

        if not cb("mux", 0.98, "合成视频（画面直接复制，零重编码）..."):
            raise CancelledError()

        args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(input_path)]
        for w in sep_wavs:
            args += ["-i", str(w)]

        # 视频: 全部直接复制（零重编码）
        args += ["-map", "0:v", "-c:v", "copy"]

        # 音轨: 按原来的顺序输出；被处理的换成分离结果，其余原样复制
        proc_k = 0
        for m, s in enumerate(audio_streams):
            if s["index"] in sel_idx:
                args += ["-map", f"{1 + proc_k}:a:0"]
                proc_k += 1
            else:
                args += ["-map", f"0:{s['index']}"]

        # 字幕 / 章节内嵌流 / 字体附件: 原样保留
        args += ["-map", "0:s?", "-map", "0:t?", "-c:s", "copy"]
        # MP4/MOV 封装器会自动保留 timed-metadata 数据流, 显式映射反而会重复一份;
        # MKV/WebM 需要显式映射才会保留(如 GoPro GPMF)
        if output_path.suffix.lower() not in (".mp4", ".m4v", ".mov", ".3gp"):
            args += ["-map", "0:d?"]

        acodec, abr = _audio_codec_for(output_path.suffix, opts.bitrate)
        for m, s in enumerate(audio_streams):
            if s["index"] in sel_idx:
                args += [f"-c:a:{m}", acodec, f"-b:a:{m}", abr]
            else:
                args += [f"-c:a:{m}", "copy"]
            lang = (s.get("tags") or {}).get("language")
            if lang:
                args += [f"-metadata:s:a:{m}", f"language={lang}"]

        args += ["-map_metadata", "0", "-map_chapters", "0"]
        if output_path.suffix.lower() == ".mp4":
            args += ["-movflags", "+faststart"]
        args.append(str(output_path))

        try:
            _run(args)
        except VocalRemoverError:
            # 个别容器的附件/数据流无法直接复制时，降级去掉这两类流重试
            minimal = [a for a in args if a not in ("0:t?", "0:d?")]
            if len(minimal) != len(args):
                _run(minimal)
            else:
                raise

    cb("done", 1.0, str(output_path))
    return output_path


def main(argv=None) -> int:
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        prog="vocal_remover",
        description="视频去人声工具: 去掉视频音轨中的人声，画面/字幕/章节/元数据保持原样。",
        epilog="示例: python vocal_remover.py 视频.mp4\n"
               "      python vocal_remover.py a.mp4 b.mkv -o 输出目录未指定时自动加 _无人声 后缀",
    )
    ap.add_argument("inputs", nargs="+", help="输入视频文件（可多个）")
    ap.add_argument("-o", "--output", help="输出文件路径（仅单个输入时可指定）")
    ap.add_argument("-m", "--model", default="htdemucs",
                    choices=["htdemucs", "htdemucs_ft"],
                    help="分离模型: htdemucs=标准(默认), htdemucs_ft=高质量(慢约4倍)")
    ap.add_argument("-t", "--tracks", default="all", choices=["all", "first"],
                    help="all=处理全部音轨(默认), first=仅处理第一条、其余原样保留")
    ap.add_argument("--bitrate", default="320k", help="输出音轨码率(默认 320k)")
    ap.add_argument("-d", "--device", default="auto",
                    choices=["auto", "cpu", "cuda"], help="计算设备(默认 auto)")
    args = ap.parse_args(argv)

    if args.output and len(args.inputs) > 1:
        ap.error("-o 只能在单个输入文件时使用")

    opts = Options(model=args.model, bitrate=args.bitrate,
                   device=args.device, tracks=args.tracks)

    def on_progress(stage, pct, msg) -> bool:
        if pct is not None:
            print(f"\r  {msg:<40}", end="", flush=True)
        else:
            print(f"  {msg}")
        return True

    failed = 0
    for i, f in enumerate(args.inputs, 1):
        print(f"[{i}/{len(args.inputs)}] {Path(f).name}")
        try:
            out = remove_vocals(f, args.output, opts, on_progress)
            print()
            print(f"  完成 -> {out}")
        except CancelledError:
            print("\n已取消")
            return 130
        except Exception as e:
            failed += 1
            print(f"\n  失败: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
