use std::{path::Path, sync::Arc, sync::atomic::Ordering, time::Duration};

use doorman_gateway::{
    Config,
    state::{GatewayRuntime, MemoryAutosaveConfig},
    storage::{runtime::SharedStorage, security_settings, snapshot},
};
use serde_json::json;
use uuid::Uuid;

// Environment-sensitive cases run in child processes so parallel tests cannot
// change the encryption key or autosave defaults beneath another test.
fn child(test: &str, directory: &Path) -> std::process::Command {
    let mut command = std::process::Command::new(std::env::current_exe().unwrap());
    command
        .args(["--exact", test, "--nocapture"])
        .env("DOORMAN_AUTOSAVE_CHILD", "1")
        .env("MEM_ENCRYPTION_KEY", "autosave-lifecycle-test-key")
        .env_remove("PYTHONINTMAXSTRDIGITS")
        .env_remove("MEM_DUMP_PATH")
        .current_dir(directory);
    command
}

fn run(command: &mut std::process::Command) {
    let output = command.output().unwrap();
    assert!(
        output.status.success(),
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn integer_digit_limit_environment_matches_python_startup() {
    if std::env::var_os("DOORMAN_AUTOSAVE_CHILD").is_some() {
        if std::env::var("DOORMAN_EXPECT_VALID").unwrap() == "false" {
            match Config::from_env() {
                Err(doorman_gateway::config::ConfigError::InvalidConfiguration(message)) => {
                    assert!(message.starts_with("PYTHONINTMAXSTRDIGITS"));
                }
                _ => panic!("invalid digit-limit configuration must prevent startup"),
            }
        } else {
            let expected: u64 = std::env::var("DOORMAN_EXPECT_FREQUENCY")
                .unwrap()
                .parse()
                .unwrap();
            assert_eq!(MemoryAutosaveConfig::default().frequency_seconds, expected);
        }
        return;
    }
    let valid = [
        ("", 4300),
        ("0", 0),
        ("640", 640),
        ("4300", 4300),
        ("5000", 5000),
        ("0640", 640),
        ("+640", 640),
        ("-0", 0),
        (" 640", 640),
        (" +640", 640),
        ("\u{b}640", 640),
        ("2147483647", 2147483647),
    ];
    for (value, limit) in valid {
        for (digits, separated) in [(1000, false), (4300, false), (4301, false), (1000, true)] {
            let frequency = format!("{}120", "٠".repeat(digits - 3));
            let frequency = if separated {
                frequency
                    .chars()
                    .map(|character| character.to_string())
                    .collect::<Vec<_>>()
                    .join("_")
            } else {
                frequency
            };
            let expected = if limit == 0 || digits <= limit {
                120
            } else {
                900
            };
            run(child(
                "integer_digit_limit_environment_matches_python_startup",
                &std::env::temp_dir(),
            )
            .env("PYTHONINTMAXSTRDIGITS", value)
            .env("MEM_AUTO_SAVE_FREQ", frequency)
            .env("DOORMAN_EXPECT_VALID", "true")
            .env("DOORMAN_EXPECT_FREQUENCY", expected.to_string()));
        }
    }
    for value in [
        "1",
        "639",
        "-1",
        "invalid",
        "٠",
        "1_000",
        "640 ",
        "640\n",
        " +640 ",
        "2147483648",
    ] {
        run(child(
            "integer_digit_limit_environment_matches_python_startup",
            &std::env::temp_dir(),
        )
        .env("PYTHONINTMAXSTRDIGITS", value)
        .env("DOORMAN_EXPECT_VALID", "false"));
    }
}

#[test]
fn autosave_environment_defaults_match_python() {
    if std::env::var_os("DOORMAN_AUTOSAVE_CHILD").is_some() {
        let expected_enabled = std::env::var("DOORMAN_EXPECT_ENABLED").unwrap() == "true";
        let expected_frequency: u64 = std::env::var("DOORMAN_EXPECT_FREQUENCY")
            .unwrap()
            .parse()
            .unwrap();
        let defaults = MemoryAutosaveConfig::default();
        assert_eq!(defaults.enabled, expected_enabled);
        assert_eq!(defaults.frequency_seconds, expected_frequency);
        let settings = security_settings::merge(&Config::for_test("unused".to_owned()), None);
        assert_eq!(settings["enable_auto_save"], expected_enabled);
        assert_eq!(settings["auto_save_frequency_seconds"], expected_frequency);
        assert_eq!(
            MemoryAutosaveConfig::from_settings(Some(&settings)).frequency_seconds,
            expected_frequency
        );
        // A positive interval recovered from a file/snapshot also survives an
        // environment default with a different cadence.
        assert_eq!(
            MemoryAutosaveConfig::from_settings(Some(&json!({
                "auto_save_frequency_seconds": 30
            })))
            .frequency_seconds,
            30
        );
        return;
    }
    // Oracle: pinned utils/security_settings_util.py::_env_bool/_env_int.
    for (enabled, frequency, expected_enabled, expected_frequency) in [
        (" true ", " 30 ", true, 30),
        ("\tOn\n", " +1 ", true, 1),
        ("YES", "59", true, 59),
        ("off", " 120 ", false, 120),
        ("invalid", "0", false, 900),
        ("false", "-1", false, 900),
        ("", "invalid", false, 900),
        ("true", "١٢٠", true, 120),
        ("true", "１２０", true, 120),
        ("true", "𝟙𝟚𝟘", true, 120),
        ("true", "1_٢0", true, 120),
        ("true", "\u{a0}+١_٢٠\u{3000}", true, 120),
        ("\u{1c}true\u{1f}", "\u{1c}30\u{1f}", true, 30),
        ("true", "١__٢٠", true, 900),
        ("true", "²⁶⁰", true, 900),
        ("true", "-١٢٠", true, 900),
        ("true", "\u{200b}120\u{200b}", true, 900),
    ] {
        run(child(
            "autosave_environment_defaults_match_python",
            &std::env::temp_dir(),
        )
        .env("MEM_AUTO_SAVE_ENABLED", enabled)
        .env("MEM_AUTO_SAVE_FREQ", frequency)
        .env("DOORMAN_EXPECT_ENABLED", expected_enabled.to_string())
        .env("DOORMAN_EXPECT_FREQUENCY", expected_frequency.to_string()));
    }
}

async fn settle_worker() {
    for _ in 0..20 {
        tokio::task::yield_now().await;
    }
}

fn dumps(directory: &Path) -> Vec<(std::path::PathBuf, Vec<u8>)> {
    let Ok(entries) = std::fs::read_dir(directory) else {
        return Vec::new();
    };
    let mut files: Vec<_> = entries
        .map(Result::unwrap)
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|extension| extension == "bin"))
        .map(|path| {
            let bytes = std::fs::read(&path).unwrap();
            assert!(bytes.starts_with(b"DMP1"));
            (path, bytes)
        })
        .collect();
    files.sort();
    files
}

#[tokio::test]
async fn autosave_cadence_updates_disable_and_failure_recovery() {
    if std::env::var_os("DOORMAN_AUTOSAVE_CHILD").is_none() {
        let directory = std::env::temp_dir().join(format!("doorman-autosave-{}", Uuid::new_v4()));
        std::fs::create_dir(&directory).unwrap();
        run(child(
            "autosave_cadence_updates_disable_and_failure_recovery",
            &directory,
        )
        .env("MEM_AUTO_SAVE_ENABLED", "true")
        .env("MEM_AUTO_SAVE_FREQ", "30"));
        std::fs::remove_dir_all(directory).unwrap();
        return;
    }
    let config = Config::for_test("unused".to_owned());
    let storage = Arc::new(
        SharedStorage::connect(&config.shared_storage)
            .await
            .unwrap(),
    );
    let runtime = Arc::new(GatewayRuntime::default());
    let directory = std::env::current_dir().unwrap();
    let first = directory.join("first");
    let second = directory.join("second");
    let mut settings = security_settings::merge(&config, None);
    settings["dump_path"] = json!(first.join("dump.bin"));
    runtime.update_memory_autosave_config(MemoryAutosaveConfig::from_settings(Some(&settings)));
    storage
        .insert_one("groups", json!({"group_name": "before"}))
        .await
        .unwrap();

    // Freeze only Tokio's clock. Dumps still use real encryption and files;
    // comparing bytes also detects overwrites within one wall-clock second.
    tokio::time::pause();
    let worker = snapshot::spawn_autosave(storage.clone(), runtime.clone());
    settle_worker().await;
    let initial = dumps(&first);
    assert_eq!(initial.len(), 1, "startup must dump immediately");
    assert!(runtime.memory_snapshot_healthy.load(Ordering::Relaxed));
    storage
        .insert_one("groups", json!({"group_name": "after"}))
        .await
        .unwrap();
    tokio::time::advance(Duration::from_secs(59)).await;
    settle_worker().await;
    assert_eq!(
        dumps(&first),
        initial,
        "positive intervals below 60 use a 60-second wait"
    );
    // Tokio rounds timer deadlines up to its next millisecond tick.
    tokio::time::advance(Duration::from_millis(1001)).await;
    settle_worker().await;
    let scheduled = dumps(&first);
    assert_ne!(scheduled, initial, "the scheduled dump must actually run");
    let restored = SharedStorage::connect(&config.shared_storage)
        .await
        .unwrap();
    snapshot::restore(&restored, scheduled.last().unwrap().0.to_str())
        .await
        .unwrap();
    assert!(
        restored
            .find_one("groups", &json!({"group_name": "after"}))
            .await
            .unwrap()
            .is_some()
    );

    settings["dump_path"] = json!(second.join("dump.bin"));
    settings["auto_save_frequency_seconds"] = json!(120);
    runtime.update_memory_autosave_config(MemoryAutosaveConfig::from_settings(Some(&settings)));
    settle_worker().await;
    let changed = dumps(&second);
    assert_eq!(
        changed.len(),
        1,
        "a path/cadence update must dump immediately"
    );
    tokio::time::advance(Duration::from_secs(119)).await;
    settle_worker().await;
    assert_eq!(dumps(&second), changed);
    assert_eq!(
        dumps(&first),
        scheduled,
        "the old path must stop receiving saves"
    );
    tokio::time::advance(Duration::from_millis(1001)).await;
    settle_worker().await;
    assert_ne!(dumps(&second), changed, "the new cadence must take effect");

    settings["enable_auto_save"] = json!(false);
    runtime.update_memory_autosave_config(MemoryAutosaveConfig::from_settings(Some(&settings)));
    settle_worker().await;
    let disabled = dumps(&second);
    tokio::time::advance(Duration::from_secs(3600)).await;
    settle_worker().await;
    assert_eq!(dumps(&second), disabled, "disabled autosave must stay idle");

    let blocked = directory.join("blocked");
    std::fs::write(&blocked, b"file blocks the directory").unwrap();
    settings["enable_auto_save"] = json!(true);
    settings["dump_path"] = json!(blocked.join("dump.bin"));
    runtime.update_memory_autosave_config(MemoryAutosaveConfig::from_settings(Some(&settings)));
    settle_worker().await;
    assert!(!runtime.memory_snapshot_healthy.load(Ordering::Relaxed));
    assert!(
        !worker.is_finished(),
        "a failed dump must not kill the worker"
    );
    assert_eq!(
        dumps(&second),
        disabled,
        "failure must preserve previous dumps"
    );
    std::fs::remove_file(&blocked).unwrap();
    tokio::time::advance(Duration::from_millis(120_001)).await;
    settle_worker().await;
    assert_eq!(
        dumps(&blocked).len(),
        1,
        "a later scheduled save must recover"
    );
    assert!(runtime.memory_snapshot_healthy.load(Ordering::Relaxed));
    assert!(!worker.is_finished());
    worker.abort();
    assert!(worker.await.unwrap_err().is_cancelled());
}
