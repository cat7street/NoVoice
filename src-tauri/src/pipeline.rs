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
    which(name).map_err(|_| {
        PipelineError::Message(format!(
            "未找到 {name}。请先安装 FFmpeg 并加入 PATH，例如: winget install Gyan.FFmpeg"
        ))
    })
}

fn run_checked(cmd: &mut Command) -> Result<(), PipelineError> {
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
    let output = Command::new(ffprobe)
        .args([
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
        ])
        .arg(input)
        .output()?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(PipelineError::Message(format!("ffprobe 失败:
{err}")));
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

fn has_nvidia() -> bool {
    which("nvidia-smi")
        .ok()
        .and_then(|p| Command::new(p).output().ok())
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn project_root() -> PathBuf {
    // src-tauri 的可执行文件在 target/.../；发布后也尽量回退到当前目录。
    if let Ok(exe) = std::env::current_exe() {
        let mut p = exe;
        for _ in 0..5 {
            if let Some(parent) = p.parent() {
                p = parent.to_path_buf();
                if p.join("models").is_dir() || p.join(".venv").is_dir() || p.join("package.json").is_file() {
                    return p;
                }
            }
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn default_python() -> PathBuf {
    let root = project_root();
    let candidates = [
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
    let pct_re = Regex::new(r"(d{1,3})%").unwrap();

    for attempt in 0..3 {
        ensure_not_cancelled(cancel)?;
        let mut args = vec![
            "-m".into(),
            "demucs.separate".into(),
            "--two-stems".into(),
            "vocals".into(),
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

        let mut child = Command::new(python)
            .args(&args)
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()?;
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
        let no_voc = out_dir
            .join(&opts.model)
            .join(wav.file_stem().unwrap_or_default())
            .join("no_vocals.wav");
        if status.success() && no_voc.exists() {
            return Ok(no_voc);
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
            let wav = td.join(format!("track{k}.wav"));
            run_checked(
                Command::new(&ffmpeg)
                    .args([
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                    ])
                    .arg(&input_path)
                    .args([
                        "-map",
                        &format!("0:{idx}"),
                        "-vn",
                        "-c:a",
                        "pcm_f32le",
                        "-ar",
                        &SAMPLE_RATE.to_string(),
                        "-ac",
                        "2",
                    ])
                    .arg(&wav),
            )?;
            let sep_dir = td.join(format!("sep{k}"));
            fs::create_dir_all(&sep_dir)?;
            sep_wavs.push(run_demucs(
                &python,
                &wav,
                &sep_dir,
                &opts,
                &model_repo,
                &label,
                base,
                span,
                &cancel,
                &mut progress,
            )?);
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

        let (acodec, abr) = audio_codec_for(&suffix, &opts.bitrate);
        for (m, stream) in audio_streams.iter().enumerate() {
            let idx = stream.get("index").and_then(|v| v.as_i64()).unwrap_or(-1);
            if sel_idx.contains(&idx) {
                args.push(format!("-c:a:{m}"));
                args.push(acodec.into());
                args.push(format!("-b:a:{m}"));
                args.push(abr.clone());
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
