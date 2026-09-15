use std::sync::Arc;

use axum::body::{Body, to_bytes};
use doorman_gateway::{AppState, Config, build_router, storage::runtime::SharedStorage};
use http::{Request, StatusCode, header};
use serde_json::{Value, json};
use tower::ServiceExt;

#[tokio::test]
async fn login_rate_limit_ignores_spoofed_forwarding_from_untrusted_peers() {
    let config = Config::for_test("removed-internal-backend".to_owned());
    let storage = SharedStorage::connect(&config.shared_storage)
        .await
        .unwrap();
    storage
        .insert_one(
            "settings",
            json!({
                "type": "security_settings",
                "trust_x_forwarded_for": true,
                "xff_trusted_proxies": ["10.0.0.0/8"]
            }),
        )
        .await
        .unwrap();
    let mut state = AppState::new(config).unwrap();
    state.storage = Some(Arc::new(storage));
    let app = build_router(state);
    for attempt in 1..=6 {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/platform/authorization")
                    .extension(axum::extract::ConnectInfo(
                        "198.51.100.91:43210"
                            .parse::<std::net::SocketAddr>()
                            .unwrap(),
                    ))
                    .header(header::CONTENT_TYPE, "application/json")
                    .header("x-forwarded-for", format!("203.0.113.{attempt}"))
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            if attempt <= 5 {
                StatusCode::BAD_REQUEST
            } else {
                StatusCode::TOO_MANY_REQUESTS
            }
        );
    }
    // Requests from a configured proxy use the forwarded address instead.
    for client in ["203.0.113.10", "203.0.113.11"] {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/platform/authorization")
                    .extension(axum::extract::ConnectInfo(
                        "10.0.0.2:43210".parse::<std::net::SocketAddr>().unwrap(),
                    ))
                    .header(header::CONTENT_TYPE, "application/json")
                    .header("x-forwarded-for", client)
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }
}

#[tokio::test]
async fn login_ip_window_matches_python_error_contract() {
    let mut config = Config::for_test("removed-internal-backend".to_owned());
    config.shared_storage.trust_x_forwarded_for = true;
    let storage = SharedStorage::connect(&config.shared_storage)
        .await
        .unwrap();
    let mut state = AppState::new(config).unwrap();
    state.storage = Some(Arc::new(storage));
    let app = build_router(state);

    for attempt in 1..=6 {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/platform/authorization")
                    .header(header::CONTENT_TYPE, "application/json")
                    .header("x-forwarded-for", "198.51.100.91")
                    .body(Body::from(json!({}).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        if attempt <= 5 {
            assert_eq!(response.status(), StatusCode::BAD_REQUEST);
            continue;
        }
        assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(response.headers()["x-ratelimit-limit"], "5");
        assert_eq!(response.headers()["x-ratelimit-remaining"], "0");
        assert!(response.headers().contains_key("retry-after"));
        assert!(response.headers().contains_key("x-ratelimit-reset"));
        let body = to_bytes(response.into_body(), 4096).await.unwrap();
        let body: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(body["detail"]["error_code"], "IP_RATE_LIMIT");
        assert!(body["detail"]["retry_after"].as_u64().is_some());
    }
}
