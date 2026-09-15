use std::collections::HashMap;

use serde_json::{Map, Value, json};

use super::runtime::StorageError;

pub const COLLECTIONS: [&str; 5] = ["apis", "endpoints", "roles", "groups", "routings"];

/// Match the pinned Python config importer: upsert supplied fields by natural
/// identity, ignore records missing identity, and preserve unrelated records.
pub fn merge_import(
    current: &mut HashMap<String, Vec<Value>>,
    payload: &Value,
) -> Result<Value, StorageError> {
    let mut counts = Map::new();
    for collection in COLLECTIONS {
        let values = match payload.get(collection) {
            None | Some(Value::Null) => &[][..],
            Some(Value::Array(values)) => values.as_slice(),
            _ => {
                return Err(StorageError::InvalidDocument(format!(
                    "{collection} must be an array"
                )));
            }
        };
        counts.insert(collection.to_owned(), json!(values.len()));
        let keys: &[&str] = match collection {
            "apis" => &["api_name", "api_version"],
            "endpoints" => &["api_name", "api_version", "endpoint_method", "endpoint_uri"],
            "roles" => &["role_name"],
            "groups" => &["group_name"],
            "routings" => &["client_key"],
            _ => unreachable!(),
        };
        for value in values {
            let mut updates = value.as_object().cloned().ok_or_else(|| {
                StorageError::InvalidDocument("configuration record must be an object".to_owned())
            })?;
            if keys.iter().any(|key| {
                updates
                    .get(*key)
                    .and_then(Value::as_str)
                    .is_none_or(str::is_empty)
            }) {
                continue;
            }
            updates.remove("_id");
            if collection == "endpoints" {
                if let Some(api) = current.get("apis").into_iter().flatten().find(|api| {
                    api.get("api_name") == updates.get("api_name")
                        && api.get("api_version") == updates.get("api_version")
                }) {
                    updates.insert(
                        "api_id".to_owned(),
                        api.get("api_id").cloned().unwrap_or(Value::Null),
                    );
                }
                updates
                    .entry("endpoint_id")
                    .or_insert_with(|| json!(uuid::Uuid::new_v4().to_string()));
            }
            let documents = current.entry(collection.to_owned()).or_default();
            if let Some(existing) = documents.iter_mut().find(|existing| {
                keys.iter()
                    .all(|key| existing.get(*key) == updates.get(*key))
            }) {
                if collection == "apis"
                    && updates
                        .get("api_id")
                        .and_then(Value::as_str)
                        .is_none_or(str::is_empty)
                {
                    updates.insert(
                        "api_id".to_owned(),
                        existing.get("api_id").cloned().unwrap_or(Value::Null),
                    );
                }
                existing
                    .as_object_mut()
                    .ok_or_else(|| {
                        StorageError::InvalidDocument(
                            "stored configuration must be an object".to_owned(),
                        )
                    })?
                    .extend(updates);
            } else {
                if collection == "apis" {
                    updates
                        .entry("api_id")
                        .or_insert_with(|| json!(uuid::Uuid::new_v4().to_string()));
                    let path = format!(
                        "/{}/{}",
                        updates["api_name"].as_str().unwrap(),
                        updates["api_version"].as_str().unwrap()
                    );
                    updates.entry("api_path").or_insert(json!(path));
                }
                updates.insert("_id".to_owned(), json!(uuid::Uuid::new_v4().to_string()));
                documents.push(Value::Object(updates));
            }
        }
    }
    Ok(Value::Object(counts))
}
