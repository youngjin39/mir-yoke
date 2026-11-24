//! Finite float spelling with CPython exponent thresholds and `.0`.

#[derive(Debug)]
pub struct FloatError;
pub fn python_float(value: f64) -> Result<String, FloatError> {
    let encoded = serde_json::to_string(&value).map_err(|_| FloatError)?;
    let sign = if encoded.starts_with('-') { "-" } else { "" };
    let magnitude = encoded.trim_start_matches('-');
    let (mantissa, exponent) = magnitude.split_once(['e', 'E']).unwrap_or((magnitude, "0"));
    let decimal = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let all: String = mantissa.chars().filter(|c| *c != '.').collect();
    let Some(first) = all.find(|c| c != '0') else {
        return Ok(format!("{sign}0.0"));
    };
    let exponent = exponent.parse::<i32>().map_err(|_| FloatError)? + decimal - first as i32 - 1;
    let digits = all[first..].trim_end_matches('0');
    let decimal = (exponent + 1).max(0) as usize;
    let body = if !(-4..16).contains(&exponent) {
        let fraction = if digits.len() > 1 {
            format!(".{}", &digits[1..])
        } else {
            String::new()
        };
        format!("{}{fraction}e{exponent:+03}", &digits[..1])
    } else if exponent < 0 {
        format!("0.{}{}", "0".repeat((-exponent - 1) as usize), digits)
    } else if decimal >= digits.len() {
        format!("{digits}{}.0", "0".repeat(decimal - digits.len()))
    } else {
        format!("{}.{}", &digits[..decimal], &digits[decimal..])
    };
    Ok(format!("{sign}{body}"))
}
