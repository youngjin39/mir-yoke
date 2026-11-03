//! Pydantic's diagnostic text for the finite DispatchBrief contract.
use serde_json::Value;

pub(crate) struct ValidationIssue {
    pub location: Vec<String>,
    pub message: String,
    pub code: String,
    pub input: Value,
    pub input_repr: Option<String>,
    pub input_type: Option<String>,
}

pub(crate) fn render_errors(errors: &[ValidationIssue]) -> String {
    let plural = if errors.len() == 1 { "" } else { "s" };
    let mut output = format!(
        "{} validation error{plural} for DispatchBrief",
        errors.len()
    );
    for error in errors {
        output.push('\n');
        if !error.location.is_empty() {
            output.push_str(
                &error
                    .location
                    .iter()
                    .map(|part| {
                        if part.contains('.') {
                            format!("`{part}`")
                        } else {
                            part.clone()
                        }
                    })
                    .collect::<Vec<_>>()
                    .join("."),
            );
            output.push('\n');
        }
        let input_repr = error
            .input_repr
            .clone()
            .unwrap_or_else(|| python_value_repr(&error.input));
        output.push_str(&format!(
            "  {} [type={}, input_value={}, input_type={}]\n    For further information visit https://errors.pydantic.dev/2.13/v/{}",
            error.message,
            error.code,
            truncated_repr(&input_repr),
            error.input_type.as_deref().unwrap_or_else(|| python_type(&error.input)),
            error.code,
        ));
    }
    output
}

fn truncated_repr(value: &str) -> String {
    if value.len() <= 50 {
        return value.to_owned();
    }
    let mut prefix_end = 25;
    while !value.is_char_boundary(prefix_end) {
        prefix_end -= 1;
    }
    let mut suffix_start = value.len() - 24;
    while !value.is_char_boundary(suffix_start) {
        suffix_start += 1;
    }
    format!("{}...{}", &value[..prefix_end], &value[suffix_start..])
}

pub(crate) fn python_value_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Number(number) => {
            if let Some(float) = number.as_f64().filter(|_| number.is_f64()) {
                let repr = number.to_string();
                if let Some((mantissa, exponent)) = repr.split_once('e') {
                    let (sign, digits) = match exponent.strip_prefix('-') {
                        Some(digits) => ('-', digits),
                        None => ('+', exponent.strip_prefix('+').unwrap_or(exponent)),
                    };
                    format!("{mantissa}e{sign}{digits:0>2}")
                } else if float != 0.0 && float.abs() < 0.0001 {
                    let (sign, unsigned) = match repr.strip_prefix('-') {
                        Some(unsigned) => ("-", unsigned),
                        None => ("", repr.as_str()),
                    };
                    let fraction = unsigned.strip_prefix("0.").unwrap_or(unsigned);
                    let significant = fraction.trim_start_matches('0');
                    let exponent = fraction.len() - significant.len() + 1;
                    let (first, rest) = significant.split_at(1);
                    let point = if rest.is_empty() { "" } else { "." };
                    format!("{sign}{first}{point}{rest}e-{exponent:02}")
                } else {
                    repr
                }
            } else {
                number.to_string()
            }
        }
        Value::String(text) => crate::executor_execute::repr(text),
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(python_value_repr)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(fields) => format!(
            "{{{}}}",
            fields
                .iter()
                .map(|(key, value)| format!(
                    "{}: {}",
                    crate::executor_execute::repr(key),
                    python_value_repr(value),
                ))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

pub(crate) fn python_type(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(number) if number.is_f64() => "float",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn issue(location: &[&str], message: &str, code: &str, input: Value) -> ValidationIssue {
        ValidationIssue {
            location: location.iter().map(|part| (*part).to_owned()).collect(),
            message: message.into(),
            code: code.into(),
            input,
            input_repr: None,
            input_type: None,
        }
    }

    #[test]
    fn nested_error_matches_pydantic() {
        assert_eq!(
            render_errors(&[issue(
                &["source_refs", "task_spec"],
                "Input should be a valid string",
                "string_type",
                Value::Null,
            )]),
            "1 validation error for DispatchBrief\nsource_refs.task_spec\n  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]\n    For further information visit https://errors.pydantic.dev/2.13/v/string_type"
        );
    }

    #[test]
    fn root_error_keeps_supplied_dictionary_order() {
        let mut error = issue(
            &[],
            "Value error, DispatchBrief.version must be 1",
            "value_error",
            json!({"a": 2, "z": 1}),
        );
        error.input_repr = Some("{'z': 1, 'a': 2}".into());
        assert_eq!(
            render_errors(&[error]),
            "1 validation error for DispatchBrief\n  Value error, DispatchBrief.version must be 1 [type=value_error, input_value={'z': 1, 'a': 2}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error"
        );
    }

    #[test]
    fn extended_json_number_can_supply_its_python_type_and_repr() {
        let mut error = issue(
            &["task_id"],
            "Input should be a valid string",
            "string_type",
            json!({}),
        );
        error.input_repr = Some("inf".into());
        error.input_type = Some("float".into());
        assert!(render_errors(&[error]).contains("input_value=inf, input_type=float]"));
    }

    #[test]
    fn truncation_uses_utf8_bytes_and_keeps_valid_boundaries() {
        for (input, expected) in [
            ("A".repeat(48), format!("'{}'", "A".repeat(48))),
            (
                "A".repeat(49),
                format!("'{}...{}'", "A".repeat(24), "A".repeat(23)),
            ),
            (
                "\u{d55c}".repeat(17),
                format!("'{}...{}'", "\u{d55c}".repeat(8), "\u{d55c}".repeat(7)),
            ),
            (
                "\u{1f600}".repeat(13),
                format!("'{}...{}'", "\u{1f600}".repeat(6), "\u{1f600}".repeat(5)),
            ),
        ] {
            let rendered =
                render_errors(&[issue(&["task_id"], "message", "string_type", json!(input))]);
            assert!(
                rendered.contains(&format!("input_value={expected},")),
                "{rendered}"
            );
        }
    }

    #[test]
    fn multiple_errors_have_plural_header_and_no_trailing_newline() {
        let rendered = render_errors(&[
            issue(
                &["owned_scope", "0"],
                "Input should be a valid string",
                "string_type",
                json!(false),
            ),
            issue(&["task_id"], "Field required", "missing", json!({})),
        ]);
        assert!(rendered.starts_with("2 validation errors for DispatchBrief\nowned_scope.0\n"));
        assert!(rendered.contains("input_value=False, input_type=bool]"));
        assert!(rendered.contains("/string_type\ntask_id\n"));
        assert!(rendered.ends_with("/missing"));
    }

    #[test]
    fn location_components_containing_dots_are_quoted() {
        let rendered = render_errors(&[issue(
            &["source_refs", "a.b"],
            "Extra inputs are not permitted",
            "extra_forbidden",
            json!(1),
        )]);
        assert!(rendered.contains("\nsource_refs.`a.b`\n"));
    }

    #[test]
    fn python_container_and_float_representations() {
        assert_eq!(
            python_value_repr(&json!([null, true, false, {"x": [1, "a'b"]}])),
            "[None, True, False, {'x': [1, \"a'b\"]}]"
        );
        for (value, expected) in [
            (1.0, "1.0"),
            (-0.0, "-0.0"),
            (1e-5, "1e-05"),
            (0.000099, "9.9e-05"),
            (-1e-5, "-1e-05"),
            (1e16, "1e+16"),
            (1e100, "1e+100"),
            (f64::from_bits(0x431e083bf94e335d), "2113325745016023.2"),
            (f64::from_bits(0xc2b2694180ab0910), "-20243279817481.062"),
        ] {
            assert_eq!(python_value_repr(&json!(value)), expected);
        }
        for (value, expected) in [
            (json!(null), "NoneType"),
            (json!(true), "bool"),
            (json!(1), "int"),
            (json!(1.0), "float"),
            (json!("x"), "str"),
            (json!([]), "list"),
            (json!({}), "dict"),
        ] {
            assert_eq!(python_type(&value), expected);
        }
    }
}
