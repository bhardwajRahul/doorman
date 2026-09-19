#![cfg(unix)]

use std::{
    fs,
    net::TcpListener,
    path::PathBuf,
    process::{Child, Command, Stdio},
    time::Duration,
};

use reqwest::{Client, StatusCode};
use serde_json::{Value, json};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use uuid::Uuid;

const PASSWORD: &str = "process-lifecycle-synthetic-password";
const KEY: &str = "process-lifecycle-synthetic-encryption-key";

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        let directory = std::env::temp_dir().join(format!("doorman-process-{}", Uuid::new_v4()));
        fs::create_dir(&directory).unwrap();
        Self(directory)
    }

    fn settings(&self, enabled: bool) {
        fs::write(
            self.0.join("security.json"),
            serde_json::to_vec(&json!({
                "dump_path": self.0.join("saved/state.bin"),
                "enable_auto_save": enabled,
                "auto_save_frequency_seconds": 120
            }))
            .unwrap(),
        )
        .unwrap();
    }

    fn spawn(&self, key: &str) -> Gateway {
        let reservation = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = reservation.local_addr().unwrap();
        drop(reservation);
        let log = self.0.join(format!("process-{}.log", Uuid::new_v4()));
        let output = fs::File::create(&log).unwrap();
        let child = Command::new(env!("CARGO_BIN_EXE_doorman-gateway"))
            .env_clear()
            .env("ENV", "development")
            .env("HOST", "127.0.0.1")
            .env("PORT", address.port().to_string())
            .env("THREADS", "1")
            .env("MEM_OR_EXTERNAL", "MEM")
            .env("DOORMAN_ADMIN_PASSWORD", PASSWORD)
            .env(
                "JWT_SECRET_KEY",
                "process-lifecycle-synthetic-jwt-secret-key",
            )
            .env("MEM_ENCRYPTION_KEY", key)
            .env("MEM_DUMP_PATH", self.0.join("environment/state.bin"))
            .env("SECURITY_SETTINGS_FILE", self.0.join("security.json"))
            .env("LOGS_DIR", self.0.join("logs"))
            .env("RUST_LOG", "info")
            .current_dir(&self.0)
            .stdout(Stdio::from(output.try_clone().unwrap()))
            .stderr(Stdio::from(output))
            .spawn()
            .unwrap();
        Gateway {
            child,
            log,
            base: format!("http://{address}"),
            client: Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .unwrap(),
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

struct Gateway {
    child: Child,
    log: PathBuf,
    base: String,
    client: Client,
}

impl Gateway {
    fn logs(&self) -> String {
        fs::read_to_string(&self.log).unwrap()
    }

    async fn ready(&mut self) {
        tokio::time::timeout(Duration::from_secs(20), async {
            loop {
                assert!(
                    self.child.try_wait().unwrap().is_none(),
                    "startup failed: {}",
                    self.logs()
                );
                if let Ok(response) = self
                    .client
                    .get(format!("{}/platform/monitor/liveness", self.base))
                    .send()
                    .await
                    && response.status().is_success()
                {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(20)).await;
            }
        })
        .await
        .expect("gateway did not start");
    }

    async fn login(&self) -> String {
        let response = self
            .client
            .post(format!("{}/platform/authorization", self.base))
            .json(&json!({"email": "admin@doorman.dev", "password": PASSWORD}))
            .send()
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "{}", self.logs());
        response
            .headers()
            .get_all("set-cookie")
            .iter()
            .map(|value| {
                value
                    .to_str()
                    .unwrap()
                    .split(';')
                    .next()
                    .unwrap()
                    .to_owned()
            })
            .collect::<Vec<_>>()
            .join("; ")
    }

    async fn create(&self, cookie: &str, name: &str) {
        let response = self
            .client
            .post(format!("{}/platform/api", self.base))
            .header("cookie", cookie)
            .json(&api(name))
            .send()
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::CREATED,
            "{}",
            response.text().await.unwrap()
        );
    }

    async fn assert_api(&self, cookie: &str, name: &str) {
        let response = self
            .client
            .get(format!("{}/platform/api/{name}/v1", self.base))
            .header("cookie", cookie)
            .send()
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "{}",
            response.text().await.unwrap()
        );
    }

    fn signal(&self, signal: &str) {
        assert!(
            Command::new("/bin/kill")
                .args([signal, &self.child.id().to_string()])
                .status()
                .unwrap()
                .success()
        );
    }

    async fn logged(&self, messages: &[&str]) {
        tokio::time::timeout(Duration::from_secs(10), async {
            while !messages.iter().any(|message| self.logs().contains(message)) {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap_or_else(|_| panic!("missing log {messages:?}: {}", self.logs()));
    }

    async fn exit(&mut self, success: bool) {
        let status = tokio::time::timeout(Duration::from_secs(15), async {
            loop {
                if let Some(status) = self.child.try_wait().unwrap() {
                    break status;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("gateway did not exit");
        assert_eq!(status.success(), success, "{}", self.logs());
    }
}

impl Drop for Gateway {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn api(name: &str) -> Value {
    json!({"api_name": name, "api_version": "v1", "api_type": "REST", "api_public": true, "api_auth_required": false})
}

#[tokio::test]
async fn sigusr1_uses_updated_settings_and_crash_restart_recovers() {
    let fixture = Fixture::new();
    let mut gateway = fixture.spawn(KEY);
    gateway.ready().await;
    let cookie = gateway.login().await;
    let response = gateway
        .client
        .put(format!("{}/platform/security/settings", gateway.base))
        .header("cookie", &cookie)
        .json(&json!({"dump_path": fixture.0.join("saved/state.bin"), "enable_auto_save": false}))
        .send()
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    gateway.create(&cookie, "signal-persisted").await;
    gateway.signal("-USR1");
    gateway.logged(&["SIGUSR1 memory dump completed"]).await;
    assert!(
        fixture.0.join("saved").is_dir(),
        "signal ignored saved path"
    );
    assert!(
        !fixture.0.join("environment").exists(),
        "signal wrote environment path"
    );
    gateway.child.kill().unwrap();
    gateway.child.wait().unwrap();
    let mut restarted = fixture.spawn(KEY);
    restarted.ready().await;
    assert!(restarted.logs().contains("restored memory snapshot"));
    let cookie = restarted.login().await;
    restarted.assert_api(&cookie, "signal-persisted").await;
    restarted.signal("-INT");
    restarted.exit(true).await;
    assert!(restarted.logs().contains("shutdown memory dump completed"));
    assert!(fixture.0.join("logs/enhanced_metrics.json").is_file());
}

#[tokio::test]
async fn sigterm_drains_active_request_before_final_snapshot_and_restart() {
    let fixture = Fixture::new();
    fixture.settings(true);
    let mut gateway = fixture.spawn(KEY);
    gateway.ready().await;
    gateway.logged(&["memory autosave completed"]).await;
    let cookie = gateway.login().await;
    let payload = api("drained-request").to_string();
    let address = gateway.base.strip_prefix("http://").unwrap();
    let mut stream = tokio::net::TcpStream::connect(address).await.unwrap();
    stream.write_all(format!(
        "POST /platform/api HTTP/1.1\r\nHost: {address}\r\nCookie: {cookie}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nExpect: 100-continue\r\nConnection: close\r\n\r\n", payload.len()
    ).as_bytes()).await.unwrap();
    // Hyper sends this only after the request reaches body extraction. Hold
    // the body until shutdown starts so the mutation happens during draining.
    let mut interim = vec![0; "HTTP/1.1 100 Continue\r\n\r\n".len()];
    tokio::time::timeout(Duration::from_secs(10), stream.read_exact(&mut interim))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        String::from_utf8(interim).unwrap().to_ascii_lowercase(),
        "http/1.1 100 continue\r\n\r\n"
    );
    gateway.signal("-TERM");
    gateway
        .logged(&["shutdown requested", "shutdown memory dump completed"])
        .await;
    stream.write_all(payload.as_bytes()).await.unwrap();
    let mut response = Vec::new();
    tokio::time::timeout(Duration::from_secs(10), stream.read_to_end(&mut response))
        .await
        .unwrap()
        .unwrap();
    assert!(
        String::from_utf8(response)
            .unwrap()
            .starts_with("HTTP/1.1 201")
    );
    gateway.exit(true).await;
    assert!(
        !fixture.0.join("environment").exists(),
        "shutdown ignored saved path"
    );
    let mut restarted = fixture.spawn(KEY);
    restarted.ready().await;
    restarted.logged(&["memory autosave completed"]).await;
    let logs = restarted.logs();
    assert!(
        logs.find("restored memory snapshot").unwrap()
            < logs.find("memory autosave completed").unwrap()
    );
    let cookie = restarted.login().await;
    restarted.assert_api(&cookie, "drained-request").await;
    restarted.signal("-TERM");
    restarted.exit(true).await;
}

#[tokio::test]
async fn unreadable_saved_snapshot_prevents_startup_without_overwriting_it() {
    let fixture = Fixture::new();
    fixture.settings(true);
    let mut gateway = fixture.spawn(KEY);
    gateway.ready().await;
    gateway.logged(&["memory autosave completed"]).await;
    let cookie = gateway.login().await;
    gateway.create(&cookie, "encrypted-state").await;
    gateway.signal("-TERM");
    gateway.exit(true).await;
    let files = || {
        let mut files = fs::read_dir(fixture.0.join("saved"))
            .unwrap()
            .map(|entry| {
                let path = entry.unwrap().path();
                let bytes = fs::read(&path).unwrap();
                (path, bytes)
            })
            .collect::<Vec<_>>();
        files.sort();
        files
    };
    let original = files();
    let mut wrong_key = fixture.spawn("different-synthetic-encryption-key");
    wrong_key.exit(false).await;
    assert!(
        wrong_key
            .logs()
            .contains("refusing to start with empty state")
    );
    assert_eq!(files(), original);
    for (path, _) in &original {
        fs::write(path, b"DMP1corrupt").unwrap();
    }
    let corrupt = files();
    let mut invalid = fixture.spawn(KEY);
    invalid.exit(false).await;
    assert!(
        invalid
            .logs()
            .contains("refusing to start with empty state")
    );
    assert_eq!(files(), corrupt);
}
