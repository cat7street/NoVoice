mod pipeline;

use pipeline::{check_environment, remove_vocals, ProcessOptions, ProgressEvent};
use serde::Serialize;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, State};

struct AppState {
    cancel: Mutex<Option<Arc<AtomicBool>>>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct BatchResult {
    ok: usize,
    fail: usize,
    last_output: Option<String>,
    errors: Vec<String>,
}

#[tauri::command]
fn env_check(python_path: Option<String>, model_repo: Option<String>) -> serde_json::Value {
    check_environment(python_path, model_repo)
}

#[tauri::command]
fn launch_uninstaller() -> Result<(), String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let dir = exe.parent().ok_or_else(|| "找不到程序目录".to_string())?;
    let uninst = dir.join("Uninstall.exe");
    if !uninst.exists() {
        return Err("当前目录没有卸载程序。可到开始菜单或「应用和功能」里卸载。".into());
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        std::process::Command::new("cmd")
            .args(["/C", "start", "", &uninst.display().to_string()])
            .current_dir(dir)
            .creation_flags(0x08000000)
            .spawn()
            .map_err(|e| format!("无法启动卸载程序: {e}"))?;
        return Ok(());
    }
    #[cfg(not(windows))]
    {
        std::process::Command::new(&uninst)
            .current_dir(dir)
            .spawn()
            .map_err(|e| format!("无法启动卸载程序: {e}"))?;
    }
    Ok(())
}

#[tauri::command]
fn cancel_job(state: State<'_, AppState>) -> bool {
    if let Ok(guard) = state.cancel.lock() {
        if let Some(flag) = guard.as_ref() {
            flag.store(true, Ordering::SeqCst);
            return true;
        }
    }
    false
}

#[tauri::command]
async fn process_videos(
    app: AppHandle,
    state: State<'_, AppState>,
    files: Vec<String>,
    options: ProcessOptions,
) -> Result<BatchResult, String> {
    let cancel = Arc::new(AtomicBool::new(false));
    {
        let mut guard = state.cancel.lock().map_err(|e| e.to_string())?;
        *guard = Some(cancel.clone());
    }

    let app_for_job = app.clone();
    let cancel_for_job = cancel.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let mut ok = 0usize;
        let mut fail = 0usize;
        let mut last_output = None;
        let mut errors = Vec::new();
        let total = files.len().max(1) as f64;

        for (i, file) in files.iter().enumerate() {
            if cancel_for_job.load(Ordering::SeqCst) {
                errors.push("已取消".into());
                break;
            }
            let input = PathBuf::from(file);
            let file_label = input
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or(file)
                .to_string();
            let _ = app_for_job.emit(
                "novoice-progress",
                ProgressEvent {
                    stage: "file".into(),
                    progress: i as f64 / total,
                    message: format!("[{}/{}] {}", i + 1, files.len(), file_label),
                    file: Some(file.clone()),
                },
            );

            let app2 = app_for_job.clone();
            let cancel2 = cancel_for_job.clone();
            let file_for_cb = file.clone();
            let base = i as f64 / total;
            let span = 1.0 / total;
            let processed = remove_vocals(
                &input,
                None,
                options.clone(),
                cancel2.clone(),
                Box::new(move |mut ev| {
                    ev.progress = base + span * ev.progress;
                    if ev.file.is_none() {
                        ev.file = Some(file_for_cb.clone());
                    }
                    let _ = app2.emit("novoice-progress", ev);
                    !cancel2.load(Ordering::SeqCst)
                }),
            );

            match processed {
                Ok(out) => {
                    ok += 1;
                    let out_s = out.display().to_string();
                    last_output = Some(out_s.clone());
                    let _ = app_for_job.emit(
                        "novoice-log",
                        serde_json::json!({
                            "level": "ok",
                            "message": format!("完成 -> {out_s}")
                        }),
                    );
                }
                Err(pipeline::PipelineError::Cancelled) => {
                    errors.push("已取消".into());
                    let _ = app_for_job.emit(
                        "novoice-log",
                        serde_json::json!({ "level": "err", "message": "已停止" }),
                    );
                    break;
                }
                Err(e) => {
                    fail += 1;
                    let msg = e.to_string();
                    errors.push(msg.clone());
                    let _ = app_for_job.emit(
                        "novoice-log",
                        serde_json::json!({
                            "level": "err",
                            "message": format!("失败: {msg}")
                        }),
                    );
                }
            }
        }

        BatchResult {
            ok,
            fail,
            last_output,
            errors,
        }
    })
    .await
    .map_err(|e| format!("处理线程异常: {e}"))?;

    if let Ok(mut guard) = state.cancel.lock() {
        *guard = None;
    }

    Ok(result)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .manage(AppState {
            cancel: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![env_check, process_videos, cancel_job, launch_uninstaller])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
