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
fn proxy_applies(host: &str, authority: &str) -> bool {
    if env("HTTP_PROXY").is_empty() && env("ALL_PROXY").is_empty() {
        return false;
    }
    !env("NO_PROXY").split(',').any(|pattern| {
        let pattern = pattern.trim().to_ascii_lowercase();
        let domain = pattern.trim_start_matches('.');
        pattern == "*"
            || (!domain.is_empty()
                && ((!pattern.starts_with('.') && (host == domain || authority == domain))
                    || host.ends_with(&format!(".{domain}"))))
    })
}
fn line(reader: &mut impl BufRead) -> Result<Vec<u8>, HttpError> {
    let mut bytes = Vec::new();
    reader
        .read_until(b'\n', &mut bytes)
        .map_err(|e| io_error(e, "Read"))?;
    Ok(bytes)
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
        if proxy_applies(&host.to_ascii_lowercase(), &authority.to_ascii_lowercase()) {
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
            let status_line = String::from_utf8_lossy(&raw)
                .trim_end_matches(['\r', '\n'])
                .to_owned();
            let mut parts = status_line.splitn(3, ' ');
            let version = parts.next().unwrap_or("");
            let status = parts.next().and_then(|s| s.parse::<u16>().ok());
            if !matches!(version, "HTTP/1.1" | "HTTP/1.0") || status.is_none() {
                return Err(protocol(format!(
                    "illegal status line: bytearray(b'{status_line}')"
                )));
            }
            let status = status.unwrap_or(0);
            let reason = parts.next().unwrap_or("").to_owned();
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
            if headers
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

#[cfg(test)]
mod tests {
    use super::*;
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
