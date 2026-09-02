use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;
use std::fs;
use std::io::{BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use thiserror::Error;
use which::which;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

pub const SAMPLE_RATE: u32 = 44100;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProcessOptions {
    pub model: String,
    pub tracks: String,
    pub bitrate: String,
    pub device: String,
    pub python_path: Option<String>,
    pub model_repo: Option<String>,
}

impl Default for ProcessOptions {
    fn default() -> Self {
        Self {
            model: "htdemucs".into(),
            tracks: "all".into(),
            bitrate: "320k".into(),
            device: "auto".into(),
            python_path: None,
            model_repo: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProgressEvent {
    pub stage: String,
    pub progress: f64,
    pub message: String,
    pub file: Option<String>,
}

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("{0}")]
    Message(String),
    #[error("已取消")]
    Cancelled,
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

pub type ProgressCb = Box<dyn FnMut(ProgressEvent) -> bool + Send>;

fn find_tool(name: &str) -> Result<PathBuf, PipelineError> {
    let root = project_root();
    let local = root.join("runtime").join("ffmpeg").join(format!("{name}.exe"));
    if local.exists() {
        return Ok(local);
    }
    let local2 = root.join("ffmpeg").join(format!("{name}.exe"));
    if local2.exists() {
        return Ok(local2);
    }
    which(name).map_err(|_| {
        PipelineError::Message(format!(
            "未找到 {name}。完整包应包含 runtime/ffmpeg；也可自行安装 FFmpeg 并加入 PATH。"
        ))
    })
}

fn run_checked(cmd: &mut Command) -> Result<(), PipelineError> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    let output = cmd.output()?;
    if output.status.success() {
        return Ok(());
    }
    let err = String::from_utf8_lossy(&output.stderr);
    let tail: String = err.chars().rev().take(2000).collect::<String>().chars().rev().collect();
    Err(PipelineError::Message(format!(
        "命令执行失败: {}\n{tail}",
        cmd.get_program().to_string_lossy()
    )))
}

fn probe(ffprobe: &Path, input: &Path) -> Result<Value, PipelineError> {
    let mut cmd = Command::new(ffprobe);
    cmd.args([
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
    ])
    .arg(input);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    let output = cmd.output()?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(PipelineError::Message(format!("ffprobe 失败:\n{err}")));
    }
    Ok(serde_json::from_slice(&output.stdout)?)
}

fn audio_codec_for(suffix: &str, bitrate: &str) -> (&'static str, String) {
    let s = suffix.to_ascii_lowercase();
    if s == ".webm" {
        ("libopus", if bitrate.is_empty() { "192k".into() } else { bitrate.into() })
    } else if s == ".avi" {
        ("libmp3lame", if bitrate.is_empty() { "320k".into() } else { bitrate.into() })
    } else {
        ("aac", if bitrate.is_empty() { "320k".into() } else { bitrate.into() })
    }
}

fn stream_i64(stream: &Value, key: &str, default: i64) -> i64 {
    stream
        .get(key)
        .and_then(|v| v.as_i64().or_else(|| v.as_f64().map(|x| x as i64)).or_else(|| {
            v.as_str().and_then(|s| s.parse::<i64>().ok())
        }))
        .unwrap_or(default)
}

fn stream_channels(stream: &Value) -> i64 {
    stream_i64(stream, "channels", 2).clamp(1, 16)
}

fn stream_sample_rate(stream: &Value) -> u32 {
    stream_i64(stream, "sample_rate", SAMPLE_RATE as i64).clamp(8000, 192000) as u32
}

fn channel_layout_of(stream: &Value, channels: i64) -> String {
    if let Some(layout) = stream
        .get("channel_layout")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty() && *s != "unknown")
    {
        return layout.to_string();
    }
    match channels {
        1 => "mono".into(),
        2 => "stereo".into(),
        3 => "2.1".into(),
        4 => "quad".into(),
        5 => "5.0".into(),
        6 => "5.1".into(),
        7 => "6.1".into(),
        8 => "7.1".into(),
        n => format!("{n}c"),
    }
}

fn extract_front_pan(channels: i64) -> String {
    match channels {
        1 => "pan=stereo|c0=c0|c1=c0".into(),
        _ => "pan=stereo|c0=c0|c1=c1".into(),
    }
}

fn extract_center_pan() -> &'static str {
    "pan=stereo|c0=c2|c1=c2"
}

fn has_center_channel(channels: i64) -> bool {
    channels >= 5
}

fn pan_layout_name(layout: &str, channels: i64) -> String {
    if layout.chars().any(|c| !c.is_ascii_alphanumeric() && c != '.' && c != '_') {
        format!("{channels}c")
    } else {
        layout.to_string()
    }
}

fn vocals_map_front(channels: i64, layout: &str) -> String {
    let layout = pan_layout_name(layout, channels);
    match channels {
        1 => format!("pan={layout}|c0=0.5*c0+0.5*c1"),
        2 => format!("pan={layout}|c0=c0|c1=c1"),
        n => {
            let mut assigns = vec!["c0=c0".to_string(), "c1=c1".to_string()];
            for i in 2..n {
                assigns.push(format!("c{i}=0*c0"));
            }
            format!("pan={layout}|{}", assigns.join("|"))
        }
    }
}

fn vocals_map_center(channels: i64, layout: &str) -> String {
    let layout = pan_layout_name(layout, channels);
    let mut assigns = Vec::new();
    for i in 0..channels {
        if i == 2 {
            assigns.push("c2=0.5*c0+0.5*c1".to_string());
        } else {
            assigns.push(format!("c{i}=0*c0"));
        }
    }
    format!("pan={layout}|{}", assigns.join("|"))
}

fn keep_layout_name(layout: &str) -> bool {
    !layout.ends_with('c')
        && layout
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '_')
}

fn subtract_mapped_vocals(
    ffmpeg: &Path,
    original: &Path,
    original_is_wav: bool,
    stream_index: i64,
    vocals: &Path,
    out_wav: &Path,
    channels: i64,
    sample_rate: u32,
    layout: &str,
    map_v: &str,
) -> Result<(), PipelineError> {
    let orig_label = if original_is_wav {
        "0:a:0".to_string()
    } else {
        format!("0:{stream_index}")
    };
    let graphs = [
        format!(
            "[1:a]aresample={sample_rate}:resampler=soxr:precision=28,{map_v}[v];[{orig_label}][v]amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights=1 -1[a]"
        ),
        format!(
            "[1:a]aresample={sample_rate},{map_v}[v];[{orig_label}][v]amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights=1 -1[a]"
        ),
    ];
    let mut last_err = None;
    let keep_layout = keep_layout_name(layout);
    for graph in &graphs {
        let mut cmd = Command::new(ffmpeg);
        cmd.args(["-y", "-hide_banner", "-loglevel", "error", "-i"])
            .arg(original)
            .arg("-i")
            .arg(vocals)
            .args([
                "-filter_complex",
                graph,
                "-map",
                "[a]",
                "-c:a",
                "pcm_f32le",
                "-ar",
                &sample_rate.to_string(),
                "-ac",
                &channels.to_string(),
            ]);
        if keep_layout {
            cmd.args(["-channel_layout", layout]);
        }
        match run_checked(cmd.arg(out_wav)) {
            Ok(()) => return Ok(()),
            Err(e) => last_err = Some(e),
        }
    }
    Err(last_err.unwrap_or_else(|| PipelineError::Message("原轨减人声失败".into())))
}

fn encode_bitrate(channels: i64, requested: &str) -> String {
    if requested != "320k" && !requested.is_empty() {
        return requested.to_string();
    }
    match channels {
        n if n >= 8 => "768k".into(),
        n if n >= 6 => "640k".into(),
        n if n >= 3 => "384k".into(),
        _ => {
            if requested.is_empty() {
                "320k".into()
            } else {
                requested.to_string()
            }
        }
    }
}

fn has_nvidia() -> bool {
    which("nvidia-smi")
        .ok()
        .and_then(|p| Command::new(p).output().ok())
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn project_root() -> PathBuf {
    // 优先：exe 同目录（完整包）；其次向上找开发目录。
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            if dir.join("runtime").is_dir()
                || dir.join("models").is_dir()
                || dir.join(".venv").is_dir()
                || dir.join("package.json").is_file()
            {
                return dir.to_path_buf();
            }
            let mut p = dir.to_path_buf();
            for _ in 0..6 {
                if let Some(parent) = p.parent() {
                    p = parent.to_path_buf();
                    if p.join("runtime").is_dir()
                        || p.join("models").is_dir()
                        || p.join(".venv").is_dir()
                        || p.join("package.json").is_file()
                    {
                        return p;
                    }
                }
            }
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn default_python() -> PathBuf {
    let root = project_root();
    let candidates = [
        root.join("runtime").join("python").join("python.exe"),
        root.join("runtime").join("python").join("pythonw.exe"),
        root.join("runtime").join("python").join("Scripts").join("python.exe"),
        root.join("runtime").join("python").join("Scripts").join("pythonw.exe"),
        root.join(".venv").join("Scripts").join("python.exe"),
        root.join(".venv").join("Scripts").join("pythonw.exe"),
        root.join("venv").join("Scripts").join("python.exe"),
    ];
    for c in candidates {
        if c.exists() {
            return c;
        }
    }
    which("python").unwrap_or_else(|_| PathBuf::from("python"))
}

fn default_model_repo() -> PathBuf {
    project_root().join("models")
}

fn ensure_not_cancelled(flag: &AtomicBool) -> Result<(), PipelineError> {
    if flag.load(Ordering::SeqCst) {
        Err(PipelineError::Cancelled)
    } else {
        Ok(())
    }
}

fn run_demucs(
    python: &Path,
    wav: &Path,
    out_dir: &Path,
    opts: &ProcessOptions,
    model_repo: &Path,
    label: &str,
    base: f64,
    span: f64,
    cancel: &AtomicBool,
    progress: &mut ProgressCb,
) -> Result<PathBuf, PipelineError> {
    let mut device = if opts.device == "auto" {
        if has_nvidia() { "cuda".into() } else { "cpu".into() }
    } else {
        opts.device.clone()
    };
    let mut segment: Option<f64> = None;
    let mut last_err = String::new();
    let pct_re = Regex::new(r"(\d{1,3})%").unwrap();

    for attempt in 0..3 {
        ensure_not_cancelled(cancel)?;
        let mut args = vec![
            "-m".into(),
            "demucs.separate".into(),
            "--two-stems".into(),
            "vocals".into(),
            "--other-method".into(),
            "none".into(),
            "--clip-mode".into(),
            "none".into(),
            "--float32".into(),
            "-n".into(),
            opts.model.clone(),
            "-o".into(),
            out_dir.display().to_string(),
            "-d".into(),
            device.clone(),
        ];
        let local_yaml = model_repo.join(format!("{}.yaml", opts.model));
        if model_repo.is_dir() && local_yaml.exists() {
            args.push("--repo".into());
            args.push(model_repo.display().to_string());
        }
        if let Some(seg) = segment {
            args.push("--segment".into());
            args.push(seg.to_string());
        }
        args.push(wav.display().to_string());

        let mut cmd = Command::new(python);
        cmd.args(&args)
            .stdout(Stdio::null())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = cmd.spawn()?;
        let mut cancelled = false;
        let mut tail = String::new();
        if let Some(stderr) = child.stderr.take() {
            let mut reader = BufReader::new(stderr);
            let mut buf = Vec::new();
            loop {
                buf.clear();
                let mut byte = [0u8; 1];
                match reader.read(&mut byte) {
                    Ok(0) => break,
                    Ok(_) => {
                        if byte[0] == b'\n' || byte[0] == b'\r' {
                            let line = String::from_utf8_lossy(&buf).trim().to_string();
                            if line.is_empty() {
                                continue;
                            }
                            tail = line.clone();
                            if let Some(caps) = pct_re.captures_iter(&line).last() {
                                if let Ok(p) = caps[1].parse::<i32>() {
                                    let pct = p.clamp(0, 100) as f64;
                                    let overall = base + span * pct / 100.0;
                                    if !progress(ProgressEvent {
                                        stage: "separate".into(),
                                        progress: overall,
                                        message: format!("{label} AI 分离人声 {p}%"),
                                        file: Some(wav.display().to_string()),
                                    }) || cancel.load(Ordering::SeqCst)
                                    {
                                        cancelled = true;
                                        let _ = child.kill();
                                        break;
                                    }
                                }
                            }
                        } else {
                            buf.push(byte[0]);
                        }
                    }
                    Err(_) => break,
                }
            }
        }
        let status = child.wait()?;
        if cancelled || cancel.load(Ordering::SeqCst) {
            return Err(PipelineError::Cancelled);
        }
        let vocals = out_dir
            .join(&opts.model)
            .join(wav.file_stem().unwrap_or_default())
            .join("vocals.wav");
        if status.success() && vocals.exists() {
            return Ok(vocals);
        }
        last_err = tail.chars().rev().take(800).collect::<String>().chars().rev().collect();
        let combined = last_err.to_ascii_lowercase();
        if combined.contains("out of memory") && device == "cuda" && attempt == 0 {
            segment = Some(4.0);
            continue;
        }
        if device == "cuda" && attempt <= 1 {
            device = "cpu".into();
            segment = None;
            continue;
        }
        break;
    }
    Err(PipelineError::Message(format!("AI 人声分离失败:\n{last_err}")))
}

pub fn remove_vocals(
    input_path: &Path,
    output_path: Option<PathBuf>,
    opts: ProcessOptions,
    cancel: Arc<AtomicBool>,
    mut progress: ProgressCb,
) -> Result<PathBuf, PipelineError> {
    ensure_not_cancelled(&cancel)?;
    let ffmpeg = find_tool("ffmpeg")?;
    let ffprobe = find_tool("ffprobe")?;
    let python = opts
        .python_path
        .as_ref()
        .map(PathBuf::from)
        .filter(|p| p.exists())
        .unwrap_or_else(default_python);
    let model_repo = opts
        .model_repo
        .as_ref()
        .map(PathBuf::from)
        .filter(|p| p.exists())
        .unwrap_or_else(default_model_repo);

    let input_path = fs::canonicalize(input_path).unwrap_or_else(|_| input_path.to_path_buf());
    if !input_path.exists() {
        return Err(PipelineError::Message(format!(
            "文件不存在: {}",
            input_path.display()
        )));
    }
    let output_path = match output_path {
        Some(p) => p,
        None => {
            let stem = input_path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("output");
            let ext = input_path
                .extension()
                .and_then(|s| s.to_str())
                .map(|s| format!(".{s}"))
                .unwrap_or_default();
            input_path.with_file_name(format!("{stem}_无人声{ext}"))
        }
    };
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }

    let info = probe(&ffprobe, &input_path)?;
    let streams = info
        .get("streams")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let video_streams: Vec<_> = streams
        .iter()
        .filter(|s| s.get("codec_type").and_then(|v| v.as_str()) == Some("video"))
        .cloned()
        .collect();
    let audio_streams: Vec<_> = streams
        .iter()
        .filter(|s| s.get("codec_type").and_then(|v| v.as_str()) == Some("audio"))
        .cloned()
        .collect();
    if video_streams.is_empty() {
        return Err(PipelineError::Message(format!(
            "文件里没有视频画面流: {}",
            input_path.file_name().and_then(|s| s.to_str()).unwrap_or("?")
        )));
    }
    if audio_streams.is_empty() {
        return Err(PipelineError::Message(format!(
            "视频里没有音轨，无法去人声: {}",
            input_path.file_name().and_then(|s| s.to_str()).unwrap_or("?")
        )));
    }

    let todo: Vec<_> = if opts.tracks == "first" {
        audio_streams.iter().take(1).cloned().collect()
    } else {
        audio_streams.clone()
    };
    let sel_idx: HashSet<i64> = todo
        .iter()
        .filter_map(|s| s.get("index").and_then(|v| v.as_i64()))
        .collect();

    let td = std::env::temp_dir().join(format!("novoice_{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(&td)?;
    let cleanup_td = td.clone();
    let result = (|| {
        let mut sep_wavs = Vec::new();
        let total = todo.len().max(1) as f64;
        for (k, stream) in todo.iter().enumerate() {
            ensure_not_cancelled(&cancel)?;
            let base = k as f64 / total;
            let span = 1.0 / total;
            let label = format!("[音轨{}/{}]", k + 1, todo.len());
            if !progress(ProgressEvent {
                stage: "extract".into(),
                progress: base,
                message: format!("{label} 提取音频..."),
                file: Some(input_path.display().to_string()),
            }) {
                return Err(PipelineError::Cancelled);
            }
            let idx = stream
                .get("index")
                .and_then(|v| v.as_i64())
                .ok_or_else(|| PipelineError::Message("音轨缺少 index".into()))?;
            let channels = stream_channels(stream);
            let sample_rate = stream_sample_rate(stream);
            let layout = channel_layout_of(stream, channels);
            let wav = td.join(format!("track{k}_front.wav"));
            run_checked(
                Command::new(&ffmpeg)
                    .args(["-y", "-hide_banner", "-loglevel", "error", "-i"])
                    .arg(&input_path)
                    .args([
                        "-map",
                        &format!("0:{idx}"),
                        "-vn",
                        "-af",
                        &extract_front_pan(channels),
                        "-c:a",
                        "pcm_f32le",
                        "-ar",
                        &SAMPLE_RATE.to_string(),
                    ])
                    .arg(&wav),
            )?;
            let sep_dir = td.join(format!("sep{k}"));
            fs::create_dir_all(&sep_dir)?;
            let front_span = if has_center_channel(channels) {
                span * 0.45
            } else {
                span * 0.9
            };
            let front_vocals = run_demucs(
                &python,
                &wav,
                &sep_dir,
                &opts,
                &model_repo,
                &label,
                base,
                front_span,
                &cancel,
                &mut progress,
            )?;
            if !progress(ProgressEvent {
                stage: "restore".into(),
                progress: base + front_span,
                message: format!("{label} 原轨减人声，保留其他声道..."),
                file: Some(input_path.display().to_string()),
            }) {
                return Err(PipelineError::Cancelled);
            }
            let restored = td.join(format!("restored{k}.wav"));
            subtract_mapped_vocals(
                &ffmpeg,
                &input_path,
                false,
                idx,
                &front_vocals,
                &restored,
                channels,
                sample_rate,
                &layout,
                &vocals_map_front(channels, &layout),
            )?;
            if has_center_channel(channels) {
                let center_wav = td.join(format!("track{k}_center.wav"));
                run_checked(
                    Command::new(&ffmpeg)
                        .args(["-y", "-hide_banner", "-loglevel", "error", "-i"])
                        .arg(&input_path)
                        .args([
                            "-map",
                            &format!("0:{idx}"),
                            "-vn",
                            "-af",
                            extract_center_pan(),
                            "-c:a",
                            "pcm_f32le",
                            "-ar",
                            &SAMPLE_RATE.to_string(),
                        ])
                        .arg(&center_wav),
                )?;
                let center_dir = td.join(format!("sep{k}_c"));
                fs::create_dir_all(&center_dir)?;
                let center_vocals = run_demucs(
                    &python,
                    &center_wav,
                    &center_dir,
                    &opts,
                    &model_repo,
                    &format!("{label} 中置"),
                    base + front_span,
                    span * 0.45,
                    &cancel,
                    &mut progress,
                )?;
                let restored2 = td.join(format!("restored{k}_c.wav"));
                subtract_mapped_vocals(
                    &ffmpeg,
                    &restored,
                    true,
                    0,
                    &center_vocals,
                    &restored2,
                    channels,
                    sample_rate,
                    &layout,
                    &vocals_map_center(channels, &layout),
                )?;
                sep_wavs.push(restored2);
            } else {
                sep_wavs.push(restored);
            }
        }

        if !progress(ProgressEvent {
            stage: "mux".into(),
            progress: 0.98,
            message: "合成视频（画面直接复制，零重编码）...".into(),
            file: Some(input_path.display().to_string()),
        }) {
            return Err(PipelineError::Cancelled);
        }

        let mut args: Vec<String> = vec![
            "-y".into(),
            "-hide_banner".into(),
            "-loglevel".into(),
            "error".into(),
            "-i".into(),
            input_path.display().to_string(),
        ];
        for w in &sep_wavs {
            args.push("-i".into());
            args.push(w.display().to_string());
        }
        args.extend(["-map".into(), "0:v".into(), "-c:v".into(), "copy".into()]);

        let mut proc_k = 0usize;
        for stream in &audio_streams {
            let idx = stream.get("index").and_then(|v| v.as_i64()).unwrap_or(-1);
            if sel_idx.contains(&idx) {
                args.push("-map".into());
                args.push(format!("{}:a:0", 1 + proc_k));
                proc_k += 1;
            } else {
                args.push("-map".into());
                args.push(format!("0:{idx}"));
            }
        }
        args.extend([
            "-map".into(),
            "0:s?".into(),
            "-map".into(),
            "0:t?".into(),
            "-c:s".into(),
            "copy".into(),
        ]);
        let suffix = output_path
            .extension()
            .and_then(|s| s.to_str())
            .map(|s| format!(".{s}"))
            .unwrap_or_default()
            .to_ascii_lowercase();
        if !matches!(suffix.as_str(), ".mp4" | ".m4v" | ".mov" | ".3gp") {
            args.extend(["-map".into(), "0:d?".into()]);
        }

        let (acodec, _) = audio_codec_for(&suffix, &opts.bitrate);
        for (m, stream) in audio_streams.iter().enumerate() {
            let idx = stream.get("index").and_then(|v| v.as_i64()).unwrap_or(-1);
            if sel_idx.contains(&idx) {
                let ch = stream_channels(stream);
                let abr = encode_bitrate(ch, &opts.bitrate);
                let layout = channel_layout_of(stream, ch);
                args.push(format!("-c:a:{m}"));
                args.push(acodec.into());
                args.push(format!("-b:a:{m}"));
                args.push(abr);
                args.push(format!("-ac:a:{m}"));
                args.push(ch.to_string());
                args.push(format!("-ar:a:{m}"));
                args.push(stream_sample_rate(stream).to_string());
                if !layout.ends_with('c') {
                    args.push(format!("-channel_layout:a:{m}"));
                    args.push(layout);
                }
            } else {
                args.push(format!("-c:a:{m}"));
                args.push("copy".into());
            }
            if let Some(lang) = stream
                .get("tags")
                .and_then(|t| t.get("language"))
                .and_then(|v| v.as_str())
            {
                args.push(format!("-metadata:s:a:{m}"));
                args.push(format!("language={lang}"));
            }
        }
        args.extend(["-map_metadata".into(), "0".into(), "-map_chapters".into(), "0".into()]);
        if suffix == ".mp4" {
            args.extend(["-movflags".into(), "+faststart".into()]);
        }
        args.push(output_path.display().to_string());

        let first = Command::new(&ffmpeg).args(&args).output()?;
        if !first.status.success() {
            let filtered: Vec<String> = args
                .into_iter()
                .filter(|a| a != "0:t?" && a != "0:d?")
                .collect();
            run_checked(Command::new(&ffmpeg).args(&filtered))?;
        }

        let _ = progress(ProgressEvent {
            stage: "done".into(),
            progress: 1.0,
            message: output_path.display().to_string(),
            file: Some(output_path.display().to_string()),
        });
        Ok(output_path)
    })();

    let _ = fs::remove_dir_all(cleanup_td);
    result
}

pub fn check_environment(python_path: Option<String>, model_repo: Option<String>) -> Value {
    let ffmpeg = find_tool("ffmpeg").ok().map(|p| p.display().to_string());
    let ffprobe = find_tool("ffprobe").ok().map(|p| p.display().to_string());
    let python = python_path
        .map(PathBuf::from)
        .filter(|p| p.exists())
        .unwrap_or_else(default_python);
    let repo = model_repo
        .map(PathBuf::from)
        .filter(|p| p.exists())
        .unwrap_or_else(default_model_repo);
    let demucs_ok = Command::new(&python)
        .args(["-c", "import demucs"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);
    serde_json::json!({
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "python": python.display().to_string(),
        "demucs": demucs_ok,
        "modelRepo": repo.display().to_string(),
        "nvidia": has_nvidia(),
    })
}
