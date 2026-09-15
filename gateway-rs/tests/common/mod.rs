//! Shared behavioral assertions exercised against memory and external stores.

use doorman_gateway::storage::runtime::SharedStorage;
use serde_json::json;

pub async fn assert_configuration_import_merges_without_data_loss(storage: &SharedStorage) {
    storage.insert_one("apis", json!({"api_name":"keep","api_version":"v1","api_id":"stable-api-id","api_description":"original","api_servers":["http://original.example"]})).await.unwrap();
    storage
        .insert_one(
            "apis",
            json!({"api_name":"unrelated","api_version":"v1","api_id":"unrelated-api-id"}),
        )
        .await
        .unwrap();
    storage
        .insert_one("roles", json!({"role_name":"keep-role","manage_apis":true}))
        .await
        .unwrap();
    let original = storage
        .find_one("apis", &json!({"api_name":"keep"}))
        .await
        .unwrap()
        .unwrap();
    let counts = storage.import_configuration_atomically(&json!({
        "apis":[{"api_name":"keep","api_version":"v1","api_description":"updated"},{"api_name":"added","api_version":"v2"},{"api_name":"malformed"}],
        "endpoints":[{"api_name":"added","api_version":"v2","endpoint_method":"GET","endpoint_uri":"/test"}],
        "roles":[]
    }), json!({"snapshot_id":"merge-test","created_at":"2026-09-13T00:00:00Z"})).await.unwrap();
    assert_eq!(counts["apis"], 3); // Python reports attempted entries, including skipped ones.
    assert_eq!(counts["endpoints"], 1);
    let updated = storage
        .find_one("apis", &json!({"api_name":"keep"}))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(updated["api_id"], "stable-api-id");
    assert_eq!(updated["_id"], original["_id"]);
    assert_eq!(updated["api_description"], "updated");
    assert_eq!(updated["api_servers"], original["api_servers"]);
    assert!(
        storage
            .find_one("apis", &json!({"api_name":"unrelated"}))
            .await
            .unwrap()
            .is_some()
    );
    assert!(
        storage
            .find_one("roles", &json!({"role_name":"keep-role"}))
            .await
            .unwrap()
            .is_some()
    );
    assert!(
        storage
            .find_one("apis", &json!({"api_name":"malformed"}))
            .await
            .unwrap()
            .is_none()
    );
    let added = storage
        .find_one("apis", &json!({"api_name":"added"}))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(added["api_path"], "/added/v2");
    let endpoint = storage
        .find_one("endpoints", &json!({"api_name":"added"}))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(endpoint["api_id"], added["api_id"]);
    assert!(endpoint["endpoint_id"].as_str().is_some());
    let snapshot = storage
        .find_one("config_snapshots", &json!({"snapshot_id":"merge-test"}))
        .await
        .unwrap()
        .unwrap();
    assert!(
        snapshot["data"]["apis"]
            .as_array()
            .unwrap()
            .contains(&original)
    );

    assert!(storage.import_configuration_atomically(&json!({
        "apis":[{"api_name":"keep","api_version":"v1","api_description":"must-not-commit"}], "roles":[1]
    }), json!({"snapshot_id":"failed-merge"})).await.is_err());
    assert_eq!(
        storage
            .find_one("apis", &json!({"api_name":"keep"}))
            .await
            .unwrap()
            .unwrap(),
        updated
    );
    assert!(
        storage
            .find_one("config_snapshots", &json!({"snapshot_id":"failed-merge"}))
            .await
            .unwrap()
            .is_none()
    );
}

pub async fn assert_revocation_purge_preserves_active_and_revoke_all(storage: &SharedStorage) {
    for record in [
        json!({"type": "jti", "username": "purge-test", "jti": "expired", "expires_at": 99}),
        json!({"type": "jti", "username": "purge-test", "jti": "boundary", "expires_at": 100}),
        json!({"type": "jti", "username": "purge-test", "jti": "active", "expires_at": 101}),
        json!({"type": "all", "username": "purge-test", "expires_at": 1}),
        json!({"type": "jti", "username": "purge-test", "jti": "no-expiry"}),
    ] {
        storage.insert_one("revocations", record).await.unwrap();
    }
    assert_eq!(storage.purge_expired_revocations(100).await.unwrap(), 2);
    let remaining = storage
        .find_many("revocations", &json!({"username": "purge-test"}))
        .await
        .unwrap();
    assert_eq!(remaining.len(), 3);
    assert!(remaining.iter().any(|record| record["type"] == "all"));
    assert!(remaining.iter().any(|record| record["jti"] == "active"));
    assert!(remaining.iter().any(|record| record["jti"] == "no-expiry"));
    assert_eq!(storage.purge_expired_revocations(100).await.unwrap(), 0);
}
