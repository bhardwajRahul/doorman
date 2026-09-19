use std::{fs, io::Write, path::Path};

use serde_json::{Value, json};
use uuid::Uuid;

use crate::{config::Config, state::MemoryAutosaveConfig};

use super::runtime::{SharedStorage, StorageError};

pub fn merge(config: &Config, current: Option<&Value>) -> Value {
    let autosave = MemoryAutosaveConfig::default();
    let mut settings = json!({
        "type": "security_settings",
        "enable_auto_save": autosave.enabled,
        "auto_save_frequency_seconds": autosave.frequency_seconds,
        "dump_path": autosave.dump_path.unwrap_or_else(|| "generated/memory_dump.bin".to_owned()),
        "ip_whitelist": [], "ip_blacklist": [], "xff_trusted_proxies": [],
        "trust_x_forwarded_for": config.shared_storage.trust_x_forwarded_for,
        "allow_localhost_bypass": config.shared_storage.local_host_ip_bypass
    });
    if let Some(current) = current.and_then(Value::as_object) {
        let fields = settings.as_object_mut().unwrap();
        fields.extend(
            current
                .iter()
                .filter(|(key, value)| key.as_str() != "_id" && !value.is_null())
                .map(|(key, value)| (key.clone(), value.clone())),
        );
    }
    settings
}

/// Select the restart location before restoring the database. Do not persist
/// defaults here: an unreadable snapshot must leave the existing files intact.
pub fn startup_dump_path(config: &Config) -> Option<String> {
    let current = config.security_settings_file.as_deref().and_then(read_file);
    merge(config, current.as_ref())
        .get("dump_path")
        .and_then(Value::as_str)
        .map(str::to_owned)
}

/// Python loads the file only when memory mode has no stored settings document.
/// MongoDB (and settings already restored from a dump) always takes precedence.
pub async fn load(storage: &SharedStorage, config: &Config) -> Result<Value, StorageError> {
    if let Some(current) = storage
        .find_one("settings", &json!({"type": "security_settings"}))
        .await?
    {
        return Ok(merge(config, Some(&current)));
    }
    if storage.is_memory()
        && let Some(path) = config.security_settings_file.as_deref()
        && let Some(current) = read_file(path)
    {
        let settings = merge(config, Some(&current));
        storage.insert_one("settings", settings.clone()).await?;
        return Ok(settings);
    }
    let settings = merge(config, None);
    storage.insert_one("settings", settings.clone()).await?;
    persist(config, &settings);
    Ok(settings)
}

fn read_file(path: &Path) -> Option<Value> {
    let contents = match fs::read_to_string(path) {
        Ok(contents) => contents,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return None,
        Err(error) => {
            tracing::error!(%error, path = %path.display(), "failed to read security settings file");
            return None;
        }
    };
    if contents.trim().is_empty() {
        return None;
    }
    match serde_json::from_str::<Value>(&contents) {
        Ok(Value::Object(fields)) if !fields.is_empty() => Some(Value::Object(fields)),
        Ok(_) => None,
        Err(error) => {
            tracing::error!(%error, path = %path.display(), "invalid security settings file");
            None
        }
    }
}

/// Match Python's best-effort file mirror: the database remains authoritative.
/// Do not log the settings themselves, which may contain administrator-supplied data.
pub fn persist(config: &Config, settings: &Value) {
    let Some(path) = config.security_settings_file.as_deref() else {
        return;
    };
    if let Err(error) = write_file(path, settings) {
        tracing::error!(%error, path = %path.display(), "failed to write security settings file");
    }
}

fn write_file(path: &Path, settings: &Value) -> Result<(), std::io::Error> {
    let mut settings = settings.clone();
    if let Some(fields) = settings.as_object_mut() {
        fields.remove("_id");
    }
    let bytes = serde_json::to_vec(&settings)?;
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        fs::create_dir_all(parent)?;
    }
    let temporary = path.with_extension(format!("{}.tmp", Uuid::new_v4()));
    let result = (|| {
        let mut options = fs::OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options.open(&temporary)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        fs::rename(&temporary, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    struct Fixture {
        directory: PathBuf,
        config: Config,
    }

    impl Fixture {
        fn new() -> Self {
            let directory =
                std::env::temp_dir().join(format!("doorman-settings-{}", Uuid::new_v4()));
            fs::create_dir(&directory).unwrap();
            let mut config = Config::for_test("unused".to_owned());
            config.security_settings_file = Some(directory.join("security.json"));
            Self { directory, config }
        }

        fn path(&self) -> &Path {
            self.config.security_settings_file.as_deref().unwrap()
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.directory);
        }
    }

    #[tokio::test]
    async fn load_settings_from_file_in_memory_mode_matches_python() {
        let fixture = Fixture::new();
        let expected = json!({"type": "security_settings", "trust_x_forwarded_for": true,
            "xff_trusted_proxies": ["10.0.0.1/32"], "enable_auto_save": true,
            "auto_save_frequency_seconds": 120, "dump_path": fixture.directory.join("dump.bin"),
            "ip_whitelist": ["203.0.113.1"], "allow_localhost_bypass": true});
        fs::write(fixture.path(), expected.to_string()).unwrap();
        let storage = SharedStorage::connect(&fixture.config.shared_storage)
            .await
            .unwrap();
        let loaded = load(&storage, &fixture.config).await.unwrap();
        for (key, value) in expected.as_object().unwrap() {
            assert_eq!(&loaded[key], value, "{key}");
        }
        let stored = storage
            .find_one("settings", &json!({"type": "security_settings"}))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(merge(&fixture.config, Some(&stored)), loaded);
        assert_eq!(
            MemoryAutosaveConfig::from_settings(Some(&loaded)).frequency_seconds,
            120
        );
    }

    #[test]
    fn merge_and_file_serialization_drop_mongo_id_and_null_overrides() {
        let fixture = Fixture::new();
        let defaults = merge(&fixture.config, None);
        let settings = merge(
            &fixture.config,
            Some(&json!({"_id": {"$oid": "507f1f77bcf86cd799439011"},
            "type": "security_settings", "enable_auto_save": null, "ip_whitelist": ["203.0.113.1"]})),
        );
        assert!(settings.get("_id").is_none());
        assert_eq!(settings["enable_auto_save"], defaults["enable_auto_save"]);
        write_file(fixture.path(), &settings).unwrap();
        let stored: Value = serde_json::from_slice(&fs::read(fixture.path()).unwrap()).unwrap();
        assert_eq!(stored, settings);
        assert_eq!(stored["type"], "security_settings");
    }

    #[tokio::test]
    async fn stored_settings_take_precedence_over_the_file() {
        let fixture = Fixture::new();
        fs::write(
            fixture.path(),
            r#"{"enable_auto_save":true,"ip_blacklist":["203.0.113.8"]}"#,
        )
        .unwrap();
        let bytes = fs::read(fixture.path()).unwrap();
        let storage = SharedStorage::connect(&fixture.config.shared_storage)
            .await
            .unwrap();
        storage
            .insert_one(
                "settings",
                json!({"type": "security_settings", "enable_auto_save": false,
            "ip_blacklist": ["203.0.113.9"]}),
            )
            .await
            .unwrap();
        let loaded = load(&storage, &fixture.config).await.unwrap();
        assert_eq!(loaded["enable_auto_save"], false);
        assert_eq!(loaded["ip_blacklist"], json!(["203.0.113.9"]));
        assert_eq!(fs::read(fixture.path()).unwrap(), bytes);
    }

    #[tokio::test]
    async fn invalid_or_empty_file_falls_back_to_defaults_matching_python() {
        for contents in ["", "not json", "[]", "{}", "null"] {
            let fixture = Fixture::new();
            fs::write(fixture.path(), contents).unwrap();
            let storage = SharedStorage::connect(&fixture.config.shared_storage)
                .await
                .unwrap();
            let loaded = load(&storage, &fixture.config).await.unwrap();
            assert_eq!(loaded, merge(&fixture.config, None));
            assert_eq!(read_file(fixture.path()).unwrap(), loaded);
        }
    }

    #[tokio::test]
    async fn file_write_failure_keeps_authoritative_settings_and_existing_path() {
        let mut fixture = Fixture::new();
        fixture.config.security_settings_file = Some(fixture.directory.clone());
        let storage = SharedStorage::connect(&fixture.config.shared_storage)
            .await
            .unwrap();
        let loaded = load(&storage, &fixture.config).await.unwrap();
        assert!(fixture.directory.is_dir());
        assert_eq!(
            merge(
                &fixture.config,
                storage
                    .find_one("settings", &json!({}))
                    .await
                    .unwrap()
                    .as_ref()
            ),
            loaded
        );
    }
}
