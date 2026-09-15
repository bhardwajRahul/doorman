use std::net::IpAddr;

fn is_valid_ip_or_cidr(s: &str) -> bool {
    if s.contains('/') {
        let parts: Vec<&str> = s.split('/').collect();
        if parts.len() != 2 {
            return false;
        }
        if let Ok(ip) = parts[0].parse::<IpAddr>() {
            if let Ok(prefix) = parts[1].parse::<u8>() {
                return match ip {
                    IpAddr::V4(_) => prefix <= 32,
                    IpAddr::V6(_) => prefix <= 128,
                };
            }
        }
        false
    } else {
        s.parse::<IpAddr>().is_ok()
    }
}
