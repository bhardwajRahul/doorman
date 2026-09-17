use std::{
    collections::{BTreeMap, HashMap},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64},
    },
    time::Instant,
};

use reqwest::{Client, redirect::Policy};
use serde_json::Value;
use thiserror::Error;
use tokio::sync::watch;

use crate::{
    config::Config,
    gateway::circuit_breaker::CircuitEntry,
    hot_reload::HotReloadConfig,
    storage::{
        models::PolicyDocuments,
        runtime::{SharedStorage, StorageError},
    },
    validation::json::ValidatorRegistry,
};

#[derive(Debug, Error)]
pub enum StateError {
    #[error("failed to construct gateway HTTP client: {0}")]
    Http(#[from] reqwest::Error),
    #[error("required shared storage is unavailable: {0}")]
    Storage(#[from] StorageError),
}

#[derive(Clone)]
pub struct AppState {
    pub config: Config,
    pub proxy_client: Client,
    pub policy_documents: Option<Arc<Mutex<PolicyDocuments>>>,
    pub storage: Option<Arc<SharedStorage>>,
    pub runtime: Arc<GatewayRuntime>,
    pub hot_reload: Arc<HotReloadConfig>,
    pub validators: Arc<ValidatorRegistry>,
}

pub struct GatewayRuntime {
    pub started_at: Instant,
    pub active_requests: AtomicU64,
    pub request_total: AtomicU64,
    pub request_duration_micros: AtomicU64,
    pub request_duration_buckets: [AtomicU64; 11],
    pub total_bytes_in: AtomicU64,
    pub total_bytes_out: AtomicU64,
    pub responses_by_status: Mutex<BTreeMap<u16, u64>>,
    pub circuits: Mutex<HashMap<String, CircuitEntry>>,
    pub retries_total: AtomicU64,
    pub upstream_timeouts_total: AtomicU64,
    pub memory_snapshot_healthy: AtomicBool,
    pub metrics_persistence_healthy: AtomicBool,
    pub revocation_purge_healthy: AtomicBool,
    pub activity_log_healthy: AtomicBool,
    pub security_audit_log_healthy: AtomicBool,
    memory_autosave_updates: watch::Sender<MemoryAutosaveConfig>,
}

#[derive(Clone, Debug)]
pub struct MemoryAutosaveConfig {
    pub enabled: bool,
    pub frequency_seconds: u64,
    pub dump_path: Option<String>,
}

impl MemoryAutosaveConfig {
    pub fn from_settings(settings: Option<&Value>) -> Self {
        let mut config = Self::default();
        let Some(settings) = settings else {
            return config;
        };
        if let Some(enabled) = settings.get("enable_auto_save").and_then(Value::as_bool) {
            config.enabled = enabled;
        }
        if let Some(frequency_seconds) = settings
            .get("auto_save_frequency_seconds")
            .and_then(Value::as_u64)
            .filter(|value| *value > 0)
        {
            config.frequency_seconds = frequency_seconds;
        }
        if let Some(path) = settings
            .get("dump_path")
            .and_then(Value::as_str)
            .filter(|path| !path.trim().is_empty())
        {
            config.dump_path = Some(path.to_owned());
        }
        config
    }
}

impl Default for MemoryAutosaveConfig {
    fn default() -> Self {
        let enabled = std::env::var("MEM_AUTO_SAVE_ENABLED")
            .ok()
            .is_some_and(|value| {
                matches!(
                    crate::python_scalar::strip(&value)
                        .to_ascii_lowercase()
                        .as_str(),
                    "1" | "true" | "yes" | "on"
                )
            });
        let frequency_seconds = std::env::var("MEM_AUTO_SAVE_FREQ")
            .ok()
            .and_then(|value| {
                crate::python_scalar::parse_integer(crate::python_scalar::strip(&value))
            })
            .and_then(|value| u64::try_from(value).ok())
            // Python preserves positive environment intervals; the worker
            // applies the 60-second scheduling minimum independently.
            .filter(|value| *value > 0)
            .unwrap_or(900);
        let dump_path = std::env::var("MEM_DUMP_PATH")
            .ok()
            .filter(|path| !path.trim().is_empty());
        Self {
            enabled,
            frequency_seconds,
            dump_path,
        }
    }
}

impl Default for GatewayRuntime {
    fn default() -> Self {
        let (memory_autosave_updates, _) = watch::channel(MemoryAutosaveConfig::default());
        Self {
            started_at: Instant::now(),
            active_requests: AtomicU64::new(0),
            request_total: AtomicU64::new(0),
            request_duration_micros: AtomicU64::new(0),
            request_duration_buckets: std::array::from_fn(|_| AtomicU64::new(0)),
            total_bytes_in: AtomicU64::new(0),
            total_bytes_out: AtomicU64::new(0),
            responses_by_status: Mutex::new(BTreeMap::new()),
            circuits: Mutex::new(HashMap::new()),
            retries_total: AtomicU64::new(0),
            upstream_timeouts_total: AtomicU64::new(0),
            memory_snapshot_healthy: AtomicBool::new(true),
            metrics_persistence_healthy: AtomicBool::new(true),
            revocation_purge_healthy: AtomicBool::new(true),
            activity_log_healthy: AtomicBool::new(true),
            security_audit_log_healthy: AtomicBool::new(true),
            memory_autosave_updates,
        }
    }
}

impl GatewayRuntime {
    pub fn memory_autosave_config(&self) -> watch::Receiver<MemoryAutosaveConfig> {
        self.memory_autosave_updates.subscribe()
    }

    pub fn update_memory_autosave_config(&self, config: MemoryAutosaveConfig) {
        self.memory_autosave_updates.send_replace(config);
    }
}

impl AppState {
    pub fn new(config: Config) -> Result<Self, reqwest::Error> {
        let proxy_client = Client::builder()
            .user_agent("doorman-gateway/2.0.0 (compatible; httpx/0.27)")
            .connect_timeout(config.connect_timeout)
            .redirect(Policy::none())
            .pool_max_idle_per_host(32)
            .tcp_keepalive(std::time::Duration::from_secs(60))
            .build()?;
        Ok(Self {
            config,
            proxy_client,
            policy_documents: None,
            storage: None,
            runtime: Arc::new(GatewayRuntime::default()),
            hot_reload: Arc::new(HotReloadConfig::from_env()),
            validators: Arc::new(ValidatorRegistry::default()),
        })
    }

    pub async fn from_config(config: Config) -> Result<Self, StateError> {
        let mut state = Self::new(config)?;
        let storage = SharedStorage::connect(&state.config.shared_storage).await?;
        storage.initialize_core().await?;
        state.storage = Some(Arc::new(storage));
        Ok(state)
    }

    pub fn with_policy_documents(mut self, documents: PolicyDocuments) -> Self {
        self.policy_documents = Some(Arc::new(Mutex::new(documents)));
        self
    }

    pub fn with_validator(
        mut self,
        name: impl Into<String>,
        validator: impl Fn(&serde_json::Value, &serde_json::Value) -> Result<(), String>
        + Send
        + Sync
        + 'static,
    ) -> Self {
        Arc::make_mut(&mut self.validators).register(name, validator);
        self
    }
}
