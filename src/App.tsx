import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { open } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";
import "./App.css";

type EnvInfo = {
  ffmpeg?: string | null;
  ffprobe?: string | null;
  python?: string;
  demucs?: boolean;
  modelRepo?: string;
  nvidia?: boolean;
};

type ProgressEvent = {
  stage: string;
  progress: number;
  message: string;
  file?: string | null;
};

type LogItem = { level: "ok" | "err" | "dim"; message: string };

type BatchResult = {
  ok: number;
  fail: number;
  lastOutput?: string | null;
  errors: string[];
};

const VIDEO_EXTS = [
  ".mp4", ".mkv", ".mov", ".m4v", ".avi", ".webm", ".flv",
  ".ts", ".m2ts", ".wmv", ".mpg", ".mpeg", ".3gp",
];

const MODEL_OPTIONS = [
  { label: "标准", desc: "更快", value: "htdemucs" },
  { label: "高质量", desc: "更干净", value: "htdemucs_ft" },
];

const TRACK_OPTIONS = [
  { label: "全部音轨", desc: "逐条处理", value: "all" },
  { label: "仅第一条", desc: "其余保留", value: "first" },
];

function isVideoPath(path: string) {
  const lower = path.toLowerCase();
  return VIDEO_EXTS.some((ext) => lower.endsWith(ext));
}

function basename(path: string) {
  const parts = path.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || path;
}

function extOf(path: string) {
  const name = basename(path);
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i + 1).toUpperCase() : "FILE";
}

export default function App() {
  const [files, setFiles] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [model, setModel] = useState("htdemucs");
  const [tracks, setTracks] = useState("all");
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("就绪");
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [env, setEnv] = useState<EnvInfo | null>(null);
  const [lastOutput, setLastOutput] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [playerPath, setPlayerPath] = useState<string | null>(null);
  const [autoPlay, setAutoPlay] = useState(true);
  const [showAbout, setShowAbout] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const pushLog = useCallback((level: LogItem["level"], message: string) => {
    setLogs((prev) => [...prev, { level, message }].slice(-300));
  }, []);

  const addFiles = useCallback(
    (incoming: string[]) => {
      setFiles((prev) => {
        const next = [...prev];
        for (const p of incoming) {
          if (!p) continue;
          if (!isVideoPath(p)) {
            pushLog("dim", `跳过（不是常见视频格式）: ${basename(p)}`);
            continue;
          }
          if (!next.includes(p)) next.push(p);
        }
        return next;
      });
    },
    [pushLog],
  );

  const playFile = useCallback((path: string | null | undefined) => {
    if (!path) return;
    setPlayerPath(path);
    setLastOutput(path);
  }, []);

  useEffect(() => {
    invoke<EnvInfo>("env_check", { pythonPath: null, modelRepo: null })
      .then(setEnv)
      .catch((e) => pushLog("err", String(e)));

    let cancelled = false;
    let unlistenDrop: (() => void) | undefined;
    (async () => {
      try {
        unlistenDrop = await getCurrentWindow().onDragDropEvent((event) => {
          if (cancelled) return;
          if (event.payload.type === "over") setDragOver(true);
          else if (event.payload.type === "leave") setDragOver(false);
          else if (event.payload.type === "drop") {
            setDragOver(false);
            addFiles(event.payload.paths || []);
          }
        });
      } catch (e) {
        pushLog("dim", `原生拖放不可用: ${String(e)}`);
      }
    })();
    return () => {
      cancelled = true;
      unlistenDrop?.();
    };
  }, [addFiles, pushLog]);

  useEffect(() => {
    let unlistenProgress: (() => void) | undefined;
    let unlistenLog: (() => void) | undefined;
    (async () => {
      unlistenProgress = await listen<ProgressEvent>("novoice-progress", (ev) => {
        setProgress(Math.max(0, Math.min(1, ev.payload.progress || 0)));
        setStatus(ev.payload.message);
      });
      unlistenLog = await listen<{ level: LogItem["level"]; message: string }>(
        "novoice-log",
        (ev) => pushLog(ev.payload.level, ev.payload.message),
      );
    })();
    return () => {
      unlistenProgress?.();
      unlistenLog?.();
    };
  }, [pushLog]);

  useEffect(() => {
    setSelected((prev) => new Set([...prev].filter((p) => files.includes(p))));
    if (!running) setStatus(files.length ? `已选 ${files.length} 个文件` : "就绪");
  }, [files, running]);

  useEffect(() => {
    const el = videoRef.current;
    if (!el || !playerPath) return;
    el.load();
    if (autoPlay) {
      const p = el.play();
      if (p && typeof p.catch === "function") p.catch(() => undefined);
    }
  }, [playerPath, autoPlay]);

  const playerSrc = useMemo(() => {
    if (!playerPath) return "";
    try {
      return convertFileSrc(playerPath);
    } catch {
      return "";
    }
  }, [playerPath]);

  async function onPick() {
    const picked = await open({
      multiple: true,
      filters: [{ name: "视频文件", extensions: VIDEO_EXTS.map((e) => e.slice(1)) }],
    });
    if (!picked) return;
    addFiles(Array.isArray(picked) ? picked : [picked]);
  }

  function toggleSelect(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  function removeSelected() {
    if (!selected.size) {
      setFiles((prev) => prev.slice(0, -1));
      return;
    }
    setFiles((prev) => prev.filter((p) => !selected.has(p)));
    setSelected(new Set());
  }

  async function onStart() {
    if (!files.length) {
      pushLog("dim", "请先添加视频文件。");
      return;
    }
    if (env && (!env.ffmpeg || !env.demucs)) {
      pushLog("err", "环境不完整：需要 FFmpeg 与可用的 Demucs Python 环境。");
      return;
    }
    setRunning(true);
    setProgress(0);
    setStatus("开始处理…");
    pushLog("dim", `开始处理 ${files.length} 个文件（模型 ${model}）`);
    try {
      const result = await invoke<BatchResult>("process_videos", {
        files,
        options: {
          model,
          tracks,
          bitrate: "320k",
          device: "auto",
          pythonPath: null,
          modelRepo: null,
        },
      });
      if (result.lastOutput) {
        setLastOutput(result.lastOutput);
        playFile(result.lastOutput);
        pushLog("ok", `已载入播放器: ${basename(result.lastOutput)}`);
      }
      setStatus("完成");
      setProgress(1);
      if (result.fail === 0) pushLog("ok", `全部处理完成（${result.ok} 个文件）`);
      else pushLog("err", `成功 ${result.ok} 个，失败 ${result.fail} 个`);
    } catch (e) {
      pushLog("err", String(e));
      setStatus("失败");
    } finally {
      setRunning(false);
    }
  }

  async function onCancel() {
    await invoke("cancel_job");
    setStatus("正在停止…");
    pushLog("dim", "已请求停止…");
  }

  async function onOpenOutput() {
    const target = lastOutput || (files[0] ? files[0].replace(/[^\\/]+$/, "") : null);
    if (!target) return;
    try {
      try {
        const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
        await revealItemInDir(target);
      } catch {
        await openPath(target);
      }
    } catch (e) {
      pushLog("err", String(e));
    }
  }

  const pct = Math.round(progress * 100);
  const envReady = !!(env?.ffmpeg && env?.demucs);

  return (
    <div className="shell">
      <div className="bg-orb orb-a" />
      <div className="bg-orb orb-b" />

      <header className="topbar">
        <div className="brand">
          <div className="mark">NV</div>
          <div>
            <div className="kicker">NoVoice</div>
            <h1>视频去人声</h1>
          </div>
        </div>
        <div className="top-meta">
          <button className="ghost" onClick={() => setShowAbout(true)}>说明</button>
          <span className={`pill ${envReady ? "good" : env ? "bad" : ""}`}>
            {env ? (envReady ? "环境正常" : "环境缺件") : "检查中"}
          </span>
        </div>
      </header>

      <div className="workspace">
        <section className={`panel files ${dragOver ? "over" : ""}`}>
          <div className="panel-head">
            <div>
              <strong>文件队列</strong>
              <span className="chip">{files.length}</span>
            </div>
            <div className="btn-row">
              <button onClick={onPick} disabled={running}>添加</button>
              <button onClick={removeSelected} disabled={running || !files.length}>移除</button>
              <button onClick={() => setFiles([])} disabled={running || !files.length}>清空</button>
            </div>
          </div>
          {files.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">＋</div>
              <div className="empty-title">拖拽视频到这里</div>
              <div className="muted">支持批量，也可点右上角添加</div>
            </div>
          ) : (
            <ul className="list">
              {files.map((f, idx) => (
                <li key={f} className={selected.has(f) ? "on" : ""} onClick={() => toggleSelect(f)} title={f}>
                  <div className="ext">{extOf(f)}</div>
                  <div className="meta">
                    <div className="name">{basename(f)}</div>
                    <div className="path">{f}</div>
                  </div>
                  <div className="idx">#{idx + 1}</div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel controls">
          <div className="panel-head">
            <strong>处理控制</strong>
          </div>

          <div className="field">
            <span className="label">分离质量</span>
            <div className="seg">
              {MODEL_OPTIONS.map((o) => (
                <button key={o.value} className={model === o.value ? "on" : ""} disabled={running} onClick={() => setModel(o.value)}>
                  <b>{o.label}</b>
                  <span>{o.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <span className="label">音轨策略</span>
            <div className="seg">
              {TRACK_OPTIONS.map((o) => (
                <button key={o.value} className={tracks === o.value ? "on" : ""} disabled={running} onClick={() => setTracks(o.value)}>
                  <b>{o.label}</b>
                  <span>{o.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="check">
            <input type="checkbox" checked={autoPlay} onChange={(e) => setAutoPlay(e.target.checked)} />
            完成后自动播放
          </label>

          <div className="status-box">
            <div>
              <div className="label">当前状态</div>
              <div className="status">{status}</div>
            </div>
            <div className="pct">{pct}%</div>
          </div>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${pct}%` }} /></div>

          <div className="actions">
            {!running ? (
              <button className="primary" onClick={onStart} disabled={!files.length}>开始处理</button>
            ) : (
              <button className="danger" onClick={onCancel}>停止</button>
            )}
            <button onClick={() => playFile(lastOutput)} disabled={!lastOutput}>播放结果</button>
            <button onClick={onOpenOutput} disabled={!lastOutput && !files.length}>打开输出</button>
          </div>
        </section>

        <section className="panel player">
          <div className="panel-head">
            <div>
              <strong>预览播放器</strong>
              <span className="muted">{playerPath ? basename(playerPath) : "未载入"}</span>
            </div>
            <div className="btn-row">
              <button onClick={() => playFile(lastOutput)} disabled={!lastOutput}>载入</button>
              <button onClick={() => setPlayerPath(null)} disabled={!playerPath}>关闭</button>
            </div>
          </div>
          {playerPath && playerSrc ? (
            <video key={playerPath} ref={videoRef} className="video" src={playerSrc} controls playsInline preload="metadata" />
          ) : (
            <div className="empty short">
              <div className="empty-title">等待处理结果</div>
              <div className="muted">完成后会自动出现在这里</div>
            </div>
          )}
        </section>

        <section className="panel logs">
          <div className="panel-head">
            <div>
              <strong>运行日志</strong>
              <span className="chip">{logs.length}</span>
            </div>
            <button onClick={() => setLogs([])} disabled={!logs.length}>清空</button>
          </div>
          <div className="log">
            {logs.length === 0 ? (
              <div className="muted pad">暂无日志</div>
            ) : (
              logs.map((l, i) => (
                <div key={`${i}-${l.message}`} className={`log-line ${l.level}`}>
                  <span className="dot" />
                  <span>{l.message}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      {showAbout && (
        <div className="modal-mask" onClick={() => setShowAbout(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>关于 NoVoice</h2>
              <button onClick={() => setShowAbout(false)}>关闭</button>
            </div>
            <div className="modal-body">
              <p>视频去人声工具：画面零重编码，仅处理音轨，支持拖放批量处理与内置播放。</p>
              <p><strong>作者：</strong>cat7street</p>
              <p>
                <strong>开源地址：</strong>
                <a href="https://github.com/cat7street/NoVoice" target="_blank" rel="noreferrer">
                  https://github.com/cat7street/NoVoice
                </a>
              </p>
              <p className="muted">技术栈：Tauri 2 + React + Rust；分离引擎复用 Demucs。</p>
            </div>
            <div className="modal-actions">
              <button
                className="primary"
                onClick={async () => {
                  try {
                    const { openUrl } = await import("@tauri-apps/plugin-opener");
                    await openUrl("https://github.com/cat7street/NoVoice");
                  } catch {
                    try {
                      await openPath("https://github.com/cat7street/NoVoice");
                    } catch (e2) {
                      pushLog("err", String(e2));
                    }
                  }
                }}
              >
                打开开源地址
              </button>
              <button onClick={() => setShowAbout(false)}>知道了</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
