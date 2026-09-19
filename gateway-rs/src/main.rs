use std::{
    env,
    path::PathBuf,
    sync::{Arc, atomic::Ordering},
    time::Duration,
};

use doorman_gateway::{
    AppState, Config, build_router,
    hot_reload::HotReloadConfig,
    observability::analytics_aggregator::global_analytics,
    routes::platform::backfill_grpc_descriptors,
    state::{GatewayRuntime, MemoryAutosaveConfig},
    storage::{runtime::SharedStorage, security_settings, snapshot},
};
use tokio::net::TcpListener;
use tracing::{error, info, warn};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    doorman_gateway::observability::init();
    restore_metrics();

    let config = Config::from_env()?;
    let bind_addr = config.bind_addr();
    let state = AppState::from_config(config).await?;
    let storage = state.storage.clone();
    let runtime = state.runtime.clone();
    let mut autosave_task = None;
    let mut signal_dump_task = None;
    spawn_metrics_autosave(state.runtime.clone());

    if let Some(storage) = storage.as_ref().filter(|storage| !storage.is_memory()) {
        let backfill = backfill_grpc_descriptors(storage).await;
        if backfill.missing() > 0 {
            warn!(
                scanned = backfill.scanned,
                updated = backfill.updated,
                skipped = backfill.skipped,
                missing = backfill.missing(),
                "gRPC descriptor backfill completed with failures; readiness will remain degraded for affected APIs"
            );
        } else {
            info!(
                scanned = backfill.scanned,
                updated = backfill.updated,
                skipped = backfill.skipped,
                "gRPC descriptor backfill completed"
            );
        }
    }

    if let Some(storage) = storage.as_ref().filter(|storage| storage.is_memory()) {
        let dump_path = security_settings::startup_dump_path(&state.config);
        match snapshot::restore_latest(storage, dump_path.as_deref()).await {
            Ok((version, created_at)) => info!(version, created_at, "restored memory snapshot"),
            Err(snapshot::SnapshotError::Io(error_value))
                if error_value.kind() == std::io::ErrorKind::NotFound =>
            {
                info!("no existing memory snapshot found")
            }
            Err(snapshot::SnapshotError::MissingKey) => {
                warn!("MEM_ENCRYPTION_KEY is not configured; restore and autosave are disabled")
            }
            Err(error_value) => {
                error!(error = %error_value, "memory snapshot restore failed; refusing to start with empty state");
                return Err(error_value.into());
            }
        }
    }

    // Settings restored from a dump or MongoDB take precedence over the file.
    // Load before the listener and the first autosave so policy and persistence
    // use the same settings on the first request.
    if let Some(storage) = &storage {
        let settings = security_settings::load(storage, &state.config).await?;
        state
            .runtime
            .update_memory_autosave_config(MemoryAutosaveConfig::from_settings(Some(&settings)));
        if storage.is_memory() {
            autosave_task = Some(snapshot::spawn_autosave(storage.clone(), runtime.clone()));
            signal_dump_task = spawn_sigusr1_dump(storage.clone(), runtime.clone());
        }
    }

    // Memory snapshots are restored above, so the first purge sees the same
    // records that will serve traffic. External storage has no restore phase.
    if let Some(storage) = &storage {
        run_revocation_purge(storage, &state.runtime).await;
        spawn_revocation_purger(storage.clone(), state.runtime.clone());
    }

    spawn_sighup_reload(state.hot_reload.clone());
    let app = build_router(state);
    let listener = TcpListener::bind(&bind_addr).await?;

    info!(address = %bind_addr, "Doorman Rust gateway listening");
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
    .with_graceful_shutdown(shutdown_signal())
    .await?;

    // Axum has now drained active requests. Stop writers before the final dump
    // so an older autosave cannot replace the state committed during draining.
    for task in [autosave_task, signal_dump_task].into_iter().flatten() {
        task.abort();
        let _ = task.await;
    }
    if let Some(storage) = storage.filter(|storage| storage.is_memory()) {
        let dump_path = runtime.memory_autosave_config().borrow().dump_path.clone();
        match snapshot::dump(&storage, dump_path.as_deref()).await {
            Ok(path) => {
                runtime
                    .memory_snapshot_healthy
                    .store(true, Ordering::Relaxed);
                info!(path = %path.display(), "shutdown memory dump completed");
            }
            Err(snapshot::SnapshotError::MissingKey) => {}
            Err(error_value) => {
                runtime
                    .memory_snapshot_healthy
                    .store(false, Ordering::Relaxed);
                error!(error = %error_value, "shutdown memory dump failed");
            }
        }
    }
    persist_metrics();
    Ok(())
}

#[cfg(unix)]
fn spawn_sighup_reload(config: Arc<HotReloadConfig>) {
    tokio::spawn(async move {
        let mut signal = match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::hangup())
        {
            Ok(signal) => signal,
            Err(error_value) => {
                warn!(error = %error_value, "failed to register SIGHUP configuration reload handler");
                return;
            }
        };
        while signal.recv().await.is_some() {
            match config.reload() {
                Ok(()) => info!("configuration reloaded from SIGHUP"),
                Err(error_value) => {
                    error!(error = %error_value, "SIGHUP configuration reload failed; retaining prior configuration")
                }
            }
        }
    });
}

#[cfg(not(unix))]
fn spawn_sighup_reload(_config: Arc<HotReloadConfig>) {}

async fn run_revocation_purge(storage: &SharedStorage, runtime: &GatewayRuntime) {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    match storage.purge_expired_revocations(now).await {
        Ok(removed) => {
            runtime
                .revocation_purge_healthy
                .store(true, Ordering::Relaxed);
            if removed > 0 {
                info!(removed, "purged expired token revocations");
            }
        }
        Err(error_value) => {
            runtime
                .revocation_purge_healthy
                .store(false, Ordering::Relaxed);
            error!(error = %error_value, "expired token revocation purge failed");
        }
    }
}

fn spawn_revocation_purger(storage: Arc<SharedStorage>, runtime: Arc<GatewayRuntime>) {
    let seconds = env::var("REVOCATION_PURGE_INTERVAL_SECONDS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(300)
        .max(1);
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(seconds));
        interval.tick().await;
        loop {
            interval.tick().await;
            run_revocation_purge(&storage, &runtime).await;
        }
    });
}

#[cfg(unix)]
fn spawn_sigusr1_dump(
    storage: Arc<SharedStorage>,
    runtime: Arc<GatewayRuntime>,
) -> Option<tokio::task::JoinHandle<()>> {
    // Register before opening the listener, so the first accepted request can
    // safely be followed by an on-demand signal.
    let mut signal =
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::user_defined1()) {
            Ok(signal) => signal,
            Err(error_value) => {
                warn!(error = %error_value, "failed to register SIGUSR1 memory dump handler");
                return None;
            }
        };
    Some(tokio::spawn(async move {
        while signal.recv().await.is_some() {
            let dump_path = runtime.memory_autosave_config().borrow().dump_path.clone();
            match snapshot::dump(&storage, dump_path.as_deref()).await {
                Ok(path) => {
                    runtime
                        .memory_snapshot_healthy
                        .store(true, Ordering::Relaxed);
                    info!(path = %path.display(), "SIGUSR1 memory dump completed");
                }
                Err(error_value) => {
                    runtime
                        .memory_snapshot_healthy
                        .store(false, Ordering::Relaxed);
                    error!(error = %error_value, "SIGUSR1 memory dump failed");
                }
            }
        }
    }))
}

#[cfg(not(unix))]
fn spawn_sigusr1_dump(
    _storage: Arc<SharedStorage>,
    _runtime: Arc<GatewayRuntime>,
) -> Option<tokio::task::JoinHandle<()>> {
    None
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        () = ctrl_c => {},
        () = terminate => {},
    }

    info!("shutdown requested; draining active requests");
}

fn metrics_paths() -> [PathBuf; 2] {
    let directory = env::var_os("LOGS_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("platform-logs"));
    [
        directory.join("enhanced_metrics.json"),
        directory.join("metrics.json"),
    ]
}

fn restore_metrics() {
    for path in metrics_paths() {
        if !path.exists() {
            continue;
        }
        match global_analytics().load_from_file(&path) {
            Ok(()) => {
                info!(path = %path.display(), "restored gateway metrics");
                return;
            }
            Err(error_value) => {
                warn!(path = %path.display(), error = %error_value, "gateway metrics restore skipped");
            }
        }
    }
}

fn persist_metrics() -> bool {
    let mut persisted = true;
    for path in metrics_paths() {
        if let Err(error_value) = global_analytics().save_to_file(&path) {
            persisted = false;
            warn!(path = %path.display(), error = %error_value, "gateway metrics persistence failed");
        }
    }
    persisted
}

fn spawn_metrics_autosave(runtime: Arc<GatewayRuntime>) {
    let seconds = env::var("METRICS_SAVE_INTERVAL")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(60)
        .max(1);
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(seconds));
        interval.tick().await;
        loop {
            interval.tick().await;
            runtime
                .metrics_persistence_healthy
                .store(persist_metrics(), Ordering::Relaxed);
        }
    });
}
