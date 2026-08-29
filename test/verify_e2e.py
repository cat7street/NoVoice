# -*- coding: utf-8 -*-
"""端到端验证: 真实运行 vocal_remover CLI, 校验「其他东西不受影响」的承诺。

检查项:
1. 视频流逐位一致(不重编码)
2. 时长一致
3. 字幕/双音轨/数据流/语言标签/章节/标题 全部保留
4. 人声频段(250~3400Hz)能量显著下降 —— 人声确实被去掉
5. 音乐频段(低音 40~180Hz / 高频 5.5k~6.5kHz)能量基本不变 —— 伴奏确实保留
6. tracks=first 时第二条音轨逐位一致
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
SRC = ROOT / "test" / "test_src.mp4"


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, **kw)


def video_hash(path):
    p = run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:v", "-c", "copy",
             "-f", "hash", "-hash", "md5", "-"])
    return p.stdout.decode().strip()


def audio_hash(path, idx):
    p = run(["ffmpeg", "-v", "error", "-i", path, "-map", f"0:a:{idx}",
             "-c", "copy", "-f", "hash", "-hash", "md5", "-"])
    return p.stdout.decode().strip()


def band_volume(path, audio_map, lo, hi):
    p = run(["ffmpeg", "-i", path, "-map", audio_map,
             "-af", f"highpass=f={lo},lowpass=f={hi},volumedetect",
             "-f", "null", "-"])
    m = re.search(rb"mean_volume:\s*(-?[\d.]+) dB", p.stderr)
    return float(m.group(1)) if m else None


def ffprobe_json(path, args):
    p = run(["ffprobe", "-v", "error", "-print_format", "json"] + args + [path])
    import json
    return json.loads(p.stdout.decode("utf-8", "replace"))


def check(name, ok, detail=""):
    print(f"  [{'通过' if ok else '失败'}] {name}" + (f"  ({detail})" if detail else ""))
    return ok


def main():
    all_ok = True
    out_all = ROOT / "test" / "test_src_无人声.mp4"
    out_first = ROOT / "test" / "test_first_无人声.mp4"
    for f in (out_all, out_first):
        f.unlink(missing_ok=True)

    print("== 运行 CLI(全部音轨, htdemucs) ==")
    p = run([PY, ROOT / "vocal_remover.py", SRC], cwd=ROOT)
    print(p.stdout.decode("utf-8", "replace")[-300:])
    assert p.returncode == 0, "CLI 运行失败"
    all_ok &= check("输出文件生成", out_all.exists())

    print("== 运行 CLI(仅第一条音轨) ==")
    p = run([PY, ROOT / "vocal_remover.py", SRC, "-t", "first",
             "-o", out_first], cwd=ROOT)
    assert p.returncode == 0, "CLI(tracks=first) 运行失败"

    print("== 结构校验 ==")
    info_in = ffprobe_json(SRC, ["-show_streams", "-show_format", "-show_chapters"])
    info_out = ffprobe_json(out_all, ["-show_streams", "-show_format", "-show_chapters"])

    all_ok &= check("视频流逐位一致", video_hash(SRC) == video_hash(out_all),
                    video_hash(out_all).replace("MD5=", ""))
    d_in = float(info_in["format"]["duration"])
    d_out = float(info_out["format"]["duration"])
    all_ok &= check("时长一致", abs(d_in - d_out) < 0.2, f"{d_in:.2f}s -> {d_out:.2f}s")

    def types(info):
        return [s["codec_type"] for s in info["streams"]]
    t_in, t_out = types(info_in), types(info_out)
    all_ok &= check("流类型一一对应", t_in == t_out, f"{t_in} == {t_out}")

    langs = [(s.get("tags") or {}).get("language") for s in info_out["streams"]]
    all_ok &= check("音轨语言标签保留", langs[1:3] == ["chi", "eng"], str(langs))

    chap_in = [(c["start_time"], c["end_time"], (c.get("tags") or {}).get("title"))
               for c in info_in["chapters"]]
    chap_out = [(c["start_time"], c["end_time"], (c.get("tags") or {}).get("title"))
                for c in info_out["chapters"]]
    all_ok &= check("章节完整保留", chap_in == chap_out,
                    "; ".join(t for _, _, t in chap_out))

    title_out = (info_out["format"].get("tags") or {}).get("title")
    all_ok &= check("标题元数据保留", title_out == "去人声测试视频", str(title_out))

    h_in = audio_hash(SRC, 1)
    h_out = audio_hash(out_first, 1)
    all_ok &= check("tracks=first 时第二音轨逐位一致", h_in == h_out)

    print("== 音频效果校验(全部音轨模式, 第一音轨) ==")
    # 基准: 纯音乐在 250~3400Hz 的底噪(-33dB 左右), 人声约 -24dB 且主导该频段
    music_ref = ROOT / "test" / "music.wav"
    speech_in = band_volume(SRC, "0:a:0", 250, 3400)
    speech_out = band_volume(out_all, "0:a:0", 250, 3400)
    music_floor = band_volume(music_ref, "0:a:0", 250, 3400)
    drop = speech_in - speech_out
    all_ok &= check("人声频段衰减 >5dB", drop > 5,
                    f"{speech_in} -> {speech_out} dB (降 {drop:.1f}dB)")
    all_ok &= check("人声去除到音乐底噪水平(±1.5dB)",
                    abs(speech_out - music_floor) < 1.5,
                    f"输出 {speech_out} vs 纯音乐 {music_floor} dB")

    bass_in = band_volume(SRC, "0:a:0", 40, 180)
    bass_out = band_volume(out_all, "0:a:0", 40, 180)
    all_ok &= check("低音伴奏保留(变化<3dB)", abs(bass_in - bass_out) < 3,
                    f"{bass_in} -> {bass_out} dB")

    spark_in = band_volume(SRC, "0:a:0", 5500, 6500)
    spark_out = band_volume(out_all, "0:a:0", 5500, 6500)
    all_ok &= check("高频音乐保留(变化<3dB)", abs(spark_in - spark_out) < 3,
                    f"{spark_in} -> {spark_out} dB")

    print()
    print("全部通过 ✔" if all_ok else "存在失败项 ✘")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
