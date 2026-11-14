//! Direct HTTP/1.1 transport; TLS, encoded responses and applying proxies fail explicitly.
use crate::mir_core::memory::backends::omlx_http::{
    HttpError, HttpRequest, HttpResponse, Transport,
};
use std::{
    io::{self, BufRead, BufReader, Read, Write},
    net::{TcpStream, ToSocketAddrs},
    time::Duration,
};

pub struct HttpTransport;
fn unsupported(s: impl Into<String>) -> HttpError {
    HttpError::new("UnsupportedProtocol", s)
}

fn protocol(s: impl Into<String>) -> HttpError {
    HttpError::new("RemoteProtocolError", s)
}
fn io_error(e: io::Error, phase: &str) -> HttpError {
    if matches!(
        e.kind(),
        io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
    ) {
        HttpError::new(&format!("{phase}Timeout"), "timed out")
    } else {
        let message = if e.kind() == io::ErrorKind::ConnectionRefused {
            format!(
                "[Errno {}] Connection refused",
                e.raw_os_error().unwrap_or(0)
            )
        } else {
            e.to_string()
        };
        HttpError::new(&format!("{phase}Error"), message)
    }
}
fn env(name: &str) -> String {
    std::env::var(name.to_ascii_lowercase())
        .or_else(|_| std::env::var(name))
        .unwrap_or_default()
}
fn proxy_applies(host: &str) -> Result<bool, HttpError> {
    if env("HTTP_PROXY").is_empty() && env("ALL_PROXY").is_empty() {
        return Ok(false);
    }
    Ok(!no_proxy_bypasses(host, &env("NO_PROXY"))?)
}
fn no_proxy_bypasses(host: &str, patterns: &str) -> Result<bool, HttpError> {
    let idna = |value: &str| {
        !value.is_ascii()
            || value
                .split(['.', '/', ':', '@'])
                .any(|label| label.to_ascii_lowercase().starts_with("xn--"))
    };
    if idna(host)
        || !patterns.is_ascii()
        || patterns
            .split(',')
            .any(|p| idna(crate::python_json::python_strip(p)))
    {
        return Err(unsupported("IDNA proxy matching is not supported"));
    }
    // httpx._utils.get_environment_proxies: '*' overrides every other mount.
    let strip = crate::python_json::python_strip;
    if patterns.split(',').any(|p| strip(p) == "*") {
        return Ok(true);
    }
    let mut bypass = false;
    for pattern in patterns.split(',') {
        let pattern = strip(pattern).to_ascii_lowercase();
        if pattern.is_empty() {
            continue;
        }
        let domain = pattern.trim_start_matches('.');
        if pattern.starts_with("..")
            || domain.split('.').any(|label| {
                label.is_empty()
                    || !label
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b == b'-')
            })
        {
            return Err(unsupported(format!(
                "NO_PROXY pattern {pattern:?} is not supported"
            )));
        }
        // httpx treats bare localhost and IPv4 as exact mounts, other bare
        // domains as *domain, and leading-dot domains as *.domain.
        let exact = pattern == "localhost" || pattern.parse::<std::net::Ipv4Addr>().is_ok();
        bypass |= if exact {
            host == pattern
        } else {
            (!pattern.starts_with('.') && host == domain)
                || host
                    .strip_suffix(&format!(".{domain}"))
                    .is_some_and(|prefix| !prefix.is_empty())
        };
    }
    Ok(bypass)
}
fn line(reader: &mut impl BufRead) -> Result<Vec<u8>, HttpError> {
    let mut bytes = Vec::new();
    reader
        .read_until(b'\n', &mut bytes)
        .map_err(|e| io_error(e, "Read"))?;
    Ok(bytes)
}
fn bytearray(bytes: &[u8]) -> String {
    let quote = if bytes.contains(&b'\'') && !bytes.contains(&b'"') {
        '"'
    } else {
        '\''
    };
    let mut out = format!("bytearray(b{quote}");
    for &b in bytes {
        match b {
            b'\\' => out.push_str("\\\\"),
            b'\r' => out.push_str("\\r"),
            b'\n' => out.push_str("\\n"),
            b'\t' => out.push_str("\\t"),
            b if b == quote as u8 => {
                out.push('\\');
                out.push(quote);
            }
            32..=126 => out.push(char::from(b)),
            b => out.push_str(&format!("\\x{b:02x}")),
        }
    }
    format!("{out}{quote})")
}
impl Transport for HttpTransport {
    fn send(&mut self, request: HttpRequest) -> Result<HttpResponse, HttpError> {
        let url = request.url.split('#').next().unwrap_or("");
        if url.starts_with("https://") {
            return Err(unsupported("HTTPS embedding transport is not supported"));
        }
        let rest = url
            .strip_prefix("http://")
            .ok_or_else(|| unsupported("Only http:// embedding URLs are supported"))?;
        let end = rest.find(['/', '?']).unwrap_or(rest.len());
        let authority = &rest[..end];
        if authority.contains('@') {
            return Err(unsupported("URL credentials are not supported"));
        }
        let (host, port) = if authority.starts_with('[') {
            let end = authority
                .find(']')
                .ok_or_else(|| unsupported("Invalid IPv6 URL"))?;
            (
                &authority[1..end],
                authority[end + 1..].strip_prefix(':').unwrap_or("80"),
            )
        } else {
            authority.rsplit_once(':').unwrap_or((authority, "80"))
        };
        if proxy_applies(&host.to_ascii_lowercase())? {
            return Err(unsupported(
                "Environment proxy embedding transport is not supported",
            ));
        }
        let target = if rest[end..].starts_with('/') {
            rest[end..].to_owned()
        } else {
            format!("/{}", &rest[end..])
        };
        if !target.is_ascii() || target.bytes().any(|b| b <= b' ' || b == 127) {
            return Err(unsupported(
                "Non-ASCII or control characters in embedding URL are not supported",
            ));
        }
        let port: u16 = port.parse().map_err(|_| unsupported("Invalid URL port"))?;
        let timeout =
            |phase: &str| Duration::from_secs(request.timeout[phase].as_u64().unwrap_or(0));
        let addresses = (host, port)
            .to_socket_addrs()
            .map_err(|e| io_error(e, "Connect"))?;
        let mut connection = Err(HttpError::new("ConnectError", "No addresses found"));
        for address in addresses {
            connection = TcpStream::connect_timeout(&address, timeout("connect"))
                .map_err(|e| io_error(e, "Connect"));
            if connection.is_ok() {
                break;
            }
        }
        let mut stream = connection?;
        stream
            .set_read_timeout(Some(timeout("read")))
            .map_err(|e| io_error(e, "Read"))?;
        stream
            .set_write_timeout(Some(timeout("write")))
            .map_err(|e| io_error(e, "Write"))?;
        // httpx 0.28 preserves model/input insertion order, emits UTF-8 and no spaces.
        let body = format!(
            "{{\"model\":{},\"input\":{}}}",
            request.body["model"], request.body["input"]
        );
        let mut head = format!(
            "{} {target} HTTP/1.1\r\nHost: {authority}\r\nAccept: */*\r\nAccept-Encoding: identity\r\nConnection: keep-alive\r\nUser-Agent: mir-native\r\nContent-Length: {}\r\n",
            request.method,
            body.len()
        );
        for (name, value) in request.headers {
            if !value.is_ascii() || value.contains(['\r', '\n']) {
                return Err(HttpError::new(
                    "LocalProtocolError",
                    "Invalid embedding header value",
                ));
            }
            head.push_str(&format!("{name}: {value}\r\n"));
        }
        stream
            .write_all(format!("{head}\r\n{body}").as_bytes())
            .map_err(|e| io_error(e, "Write"))?;
        let mut reader = BufReader::new(stream);
        loop {
            let raw = line(&mut reader)?;
            if raw.is_empty() {
                return Err(protocol("Server disconnected without sending a response."));
            }
            let status_line = raw.strip_suffix(b"\n").unwrap_or(&raw);
            let status_line = status_line.strip_suffix(b"\r").unwrap_or(status_line);
            if status_line.is_empty() {
                return Err(protocol("no response line received"));
            }
            let parts: Vec<_> = status_line.splitn(3, |b| *b == b' ').collect();
            let version = parts[0];
            let valid = version.len() == 8
                && version.starts_with(b"HTTP/")
                && version[5].is_ascii_digit()
                && version[6] == b'.'
                && version[7].is_ascii_digit()
                && parts
                    .get(1)
                    .is_some_and(|s| s.len() == 3 && s.iter().all(u8::is_ascii_digit))
                && parts
                    .get(2)
                    .is_none_or(|s| !s.iter().any(|b| matches!(b, 0 | 10..=13)));
            if !valid {
                return Err(protocol(format!(
                    "illegal status line: {}",
                    bytearray(status_line)
                )));
            }
            let status = parts[1]
                .iter()
                .fold(0u16, |n, b| n * 10 + u16::from(b - b'0'));
            let reason = parts
                .get(2)
                .map(|s| String::from_utf8_lossy(s).into_owned())
                .unwrap_or_default();
            let mut headers = std::collections::BTreeMap::new();
            loop {
                let raw = line(&mut reader)?;
                if raw == b"\r\n" || raw == b"\n" {
                    break;
                }
                let header = String::from_utf8_lossy(&raw);
                let (name, value) = header
                    .split_once(':')
                    .ok_or_else(|| protocol("illegal header line"))?;
                headers.insert(name.to_ascii_lowercase(), value.trim().to_owned());
            }
            if status < 100 {
                return Err(protocol(format!(
                    "InformationalResponse status_code should be in range [100, 200), not {status}"
                )));
            }
            if status == 101 {
                return Err(protocol(
                    "Received server _SWITCH_UPGRADE event without a pending proposal",
                ));
            }
            if status < 200 {
                continue;
            }
            if let Some(encoding) = headers.get("content-encoding")
                && !encoding.eq_ignore_ascii_case("identity")
            {
                return Err(unsupported(format!(
                    "Content-Encoding {encoding} is not supported"
                )));
            }
            let mut body = Vec::new();
            if no_response_body(&request.method, status) {
                // h11/httpx framing: these responses have no message body,
                // even when Content-Length or Transfer-Encoding is present.
            } else if headers
                .get("transfer-encoding")
                .is_some_and(|s| s.eq_ignore_ascii_case("chunked"))
            {
                loop {
                    let raw = line(&mut reader)?;
                    let text = String::from_utf8_lossy(&raw);
                    let size =
                        usize::from_str_radix(text.split(';').next().unwrap_or("").trim(), 16)
                            .map_err(|_| protocol("illegal chunk header"))?;
                    if size == 0 {
                        loop {
                            let trailer = line(&mut reader)?;
                            if trailer.is_empty() {
                                return Err(protocol("incomplete chunked read"));
                            }
                            if matches!(trailer.as_slice(), b"\r\n" | b"\n") {
                                break;
                            }
                        }
                        break;
                    }
                    let start = body.len();
                    reader
                        .by_ref()
                        .take(size as u64)
                        .read_to_end(&mut body)
                        .map_err(|e| io_error(e, "Read"))?;
                    if body.len() - start != size || line(&mut reader)? != b"\r\n" {
                        return Err(protocol("incomplete chunked read"));
                    }
                }
            } else if let Some(size) = headers.get("content-length") {
                let size: u64 = size.parse().map_err(|_| protocol("bad Content-Length"))?;
                reader
                    .take(size)
                    .read_to_end(&mut body)
                    .map_err(|e| io_error(e, "Read"))?;
                if body.len() as u64 != size {
                    return Err(protocol(format!(
                        "peer closed connection without sending complete message body (received {} bytes, expected {size})",
                        body.len()
                    )));
                }
            } else {
                reader
                    .read_to_end(&mut body)
                    .map_err(|e| io_error(e, "Read"))?;
            }
            return Ok(HttpResponse {
                status,
                reason,
                body,
            });
        }
    }
}

fn no_response_body(method: &str, status: u16) -> bool {
    method == "HEAD" || matches!(status, 204 | 304)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_body_framing_rules() {
        assert!(no_response_body("HEAD", 200));
        assert!(no_response_body("POST", 204));
        assert!(no_response_body("POST", 304));
        assert!(!no_response_body("POST", 200));
        assert!(!no_response_body("POST", 205));
    }
    #[test]
    fn frozen_no_proxy_matching() {
        let records: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/fixtures/y-e6-proxy.json")).unwrap();
        for r in records.as_array().unwrap() {
            let host = r["host"].as_str().unwrap();
            if r["native_open"].as_bool() == Some(true) {
                let error = no_proxy_bypasses(host, r["pattern"].as_str().unwrap())
                    .expect_err(&format!("IDNA must be explicitly refused: {r}"));
                assert_eq!(error.class, "UnsupportedProtocol");
                assert_eq!(error.message, r["native_message"].as_str().unwrap());
                continue;
            }
            assert_eq!(
                no_proxy_bypasses(host, r["pattern"].as_str().unwrap()).unwrap(),
                !r["applies"].as_bool().unwrap(),
                "{r}"
            );
        }
    }
    #[test]
    fn unsupported_no_proxy_patterns_fail_closed() {
        for pattern in [
            "http://localhost",
            "localhost:80",
            "::1",
            "*.example.com",
            "127.0.0.0/8",
            "é.test",
            "..example.com",
        ] {
            assert_eq!(
                no_proxy_bypasses("localhost", &format!("localhost,{pattern}"))
                    .unwrap_err()
                    .class,
                "UnsupportedProtocol"
            );
            let star = no_proxy_bypasses("localhost", &format!("{pattern},*"));
            if pattern.is_ascii() {
                assert!(star.unwrap());
            } else {
                assert_eq!(star.unwrap_err().class, "UnsupportedProtocol");
            }
        }
    }
    #[test]
    fn real_socket_write_failures() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let mut stream = TcpStream::connect(listener.local_addr().unwrap()).unwrap();
        let (_peer, _) = listener.accept().unwrap();
        stream.set_nonblocking(true).unwrap();
        let error = stream.write_all(&vec![0; 16 * 1024 * 1024]).unwrap_err();
        assert_eq!(io_error(error, "Write").class, "WriteTimeout");
        stream.shutdown(std::net::Shutdown::Write).unwrap();
        let error = stream.write_all(b"closed").unwrap_err();
        assert_eq!(io_error(error, "Write").class, "WriteError");
    }
}

#[cfg(test)]
mod e10_http_tests {
    use super::*;
    #[test]
    fn frozen_loopback_protocol() {
        if std::env::var_os("E10_HTTP_WORKER").is_none() {
            assert!(
                std::process::Command::new(std::env::current_exe().unwrap())
                    .args([
                        "--exact",
                        "mir_cli::embedding_http::e10_http_tests::frozen_loopback_protocol",
                        "--nocapture"
                    ])
                    .env_clear()
                    .env("E10_HTTP_WORKER", "1")
                    .env("NO_PROXY", "*")
                    .status()
                    .unwrap()
                    .success()
            );
            return;
        }
        let records: Vec<serde_json::Value> =
            serde_json::from_str(include_str!("../../tests/fixtures/e10_http.json")).unwrap();
        let mut mismatches = Vec::new();
        for (i, r) in records.iter().enumerate() {
            let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let url = format!("http://{}/embeddings", listener.local_addr().unwrap());
            let wire: Vec<u8> = serde_json::from_value(r["wire"].clone()).unwrap();
            let server = std::thread::spawn(move || {
                let mut stream = listener.accept().unwrap().0;
                let mut bytes = Vec::new();
                let mut byte = [0];
                while !bytes.ends_with(b"\r\n\r\n") {
                    stream.read_exact(&mut byte).unwrap();
                    bytes.push(byte[0]);
                }
                stream
                    .read_exact(&mut vec![0; br#"{"model":"fake","input":["fake"]}"#.len()])
                    .unwrap();
                stream.write_all(&wire).unwrap();
            });
            let result = HttpTransport.send(HttpRequest {
                url,
                method: "POST".into(),
                headers: Default::default(),
                body: serde_json::json!({"model":"fake","input":["fake"]}),
                timeout: serde_json::json!({"connect":1,"read":1,"write":1}),
            });
            server.join().unwrap();
            let actual = match result {
                Ok(r) => {
                    serde_json::json!({"status":r.status,"reason":r.reason,"body":String::from_utf8_lossy(&r.body)})
                }
                Err(e) => serde_json::json!({"error":e.class,"message":e.message}),
            };
            let mut expected = r.clone();
            expected.as_object_mut().unwrap().remove("wire");
            if actual != expected {
                mismatches.push(format!("case {i}: actual {actual}; expected {expected}"));
            }
        }
        assert!(mismatches.is_empty(), "{}", mismatches.join("\n"));
    }
}
