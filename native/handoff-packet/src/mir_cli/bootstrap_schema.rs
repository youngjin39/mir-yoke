use super::Error; // shortcut: shipped schemas; extend the envelope with pinned keyword records.
use crate::python_json::{Value, parse};
fn refused(keyword: &str) -> Error {
    Error::new(
        "NotImplementedError",
        format!("bootstrap schema keyword is not connected: {keyword}"),
    )
}
fn repr(s: &str) -> String {
    crate::executor_execute::repr(s)
}
fn padding(i: usize, indent: usize) -> String {
    " ".repeat(if i == 0 { 0 } else { indent + 1 })
}
fn pp(v: &Value, indent: usize, allowance: usize) -> String {
    if v.repr().chars().count() + indent + allowance <= 72 {
        return v.repr();
    }
    match v {
        Value::Object(m) if !m.is_empty() => {
            let n = m.len();
            let entries = m
                .iter()
                .enumerate()
                .map(|(i, (k, v))| {
                    let key = k.repr();
                    format!(
                        "{}{}: {}",
                        padding(i, indent),
                        key,
                        pp(
                            v,
                            indent + 1 + key.chars().count() + 2,
                            if i + 1 == n { allowance + 1 } else { 1 }
                        )
                    )
                })
                .collect::<Vec<_>>();
            format!("{{{}}}", entries.join(",\n"))
        }
        Value::Array(a) if !a.is_empty() => format!(
            "[{}]",
            a.iter()
                .enumerate()
                .map(|(i, v)| format!(
                    "{}{}",
                    padding(i, indent),
                    pp(
                        v,
                        indent + 1,
                        if i + 1 == a.len() { allowance + 1 } else { 1 }
                    )
                ))
                .collect::<Vec<_>>()
                .join(",\n")
        ),
        _ => v.repr(),
    }
}
fn diagnostic(
    message: String,
    keyword: &str,
    data: (&Value, &Value),
    paths: (&str, &str),
) -> Error {
    let (schema, value) = data;
    let (sp, ip) = paths;
    Error::new(
        "ValidationError",
        format!(
            "{message}\n\nFailed validating {keyword} in schema{sp}:\n    {}\n\nOn instance{ip}:\n    {}",
            pp(schema, 0, 0).replace('\n', "\n    "),
            pp(value, 0, 0).replace('\n', "\n    ")
        ),
    )
}
fn matches_type(v: &Value, t: &str) -> bool {
    match t {
        "object" => v.is_object(),
        "array" => v.is_array(),
        "string" => v.as_str().is_some(),
        "boolean" => matches!(v, Value::Bool(_)),
        "null" => v.is_null(),
        _ => {
            matches!(v, Value::Number(n) if t == "number" || (t == "integer" && n.token.parse::<f64>().is_ok_and(|n| n.fract()==0.0)))
        }
    }
}
fn schema_check(s: &Value) -> Result<(), Error> {
    if matches!(s, Value::Bool(_)) {
        return Ok(());
    }
    let m = s.as_object().ok_or_else(|| refused("non-object schema"))?;
    for (k, v) in m.iter() {
        let k = k.as_str().ok_or_else(|| refused("surrogate keyword"))?;
        match k {
            "type"
                if !v.as_str().is_some_and(|t| {
                    "object array string null boolean number integer".split(' ').any(|x| x == t)
                }) =>
            {
                return Err(Error::new(
                    "SchemaError",
                    format!(
                        "{} is not valid under any of the given schemas\n\nFailed validating 'anyOf' in metaschema['allOf'][3]['properties']['type']:\n    {{'anyOf': [{{'$ref': '#/$defs/simpleTypes'}},\n               {{'type': 'array',\n                'items': {{'$ref': '#/$defs/simpleTypes'}},\n                'minItems': 1,\n                'uniqueItems': True}}]}}\n\nOn schema['type']:\n    {}",
                        v.repr(),
                        v.repr()
                    ),
                ));
            }
            "required" => {
                let a = v.as_array().ok_or_else(|| refused("required schema"))?;
                for (i, x) in a.iter().enumerate() {
                    if x.as_str().is_none() {
                        return Err(Error::new(
                            "SchemaError",
                            format!(
                                "{} is not of type 'string'\n\nFailed validating 'type' in metaschema['allOf'][3]['properties']['required']['items']:\n    {{'type': 'string'}}\n\nOn schema['required'][{i}]:\n    {}",
                                x.repr(),
                                x.repr()
                            ),
                        ));
                    }
                }
            }
            "properties" | "$defs" => {
                for (_, x) in v.as_object().ok_or_else(|| refused(k))?.iter() {
                    schema_check(x)?;
                }
            }
            "items" => schema_check(v)?,
            _ if "$schema $id $ref type const enum additionalProperties minItems uniqueItems minLength pattern".split(' ').any(|x| x == k) => {}
            _ => return Err(refused(k)),
        }
    }
    Ok(())
}
fn best(errors: Vec<Error>) -> Result<(), Error> {
    let key = |e: &Error| {
        let path = e
            .message
            .rsplit_once("\n\nOn instance")
            .map_or("", |(_, p)| p.split(":\n").next().unwrap_or(""));
        let parts = path
            .split('[')
            .skip(1)
            .map(|p| {
                p.strip_suffix(']')
                    .unwrap_or(p)
                    .parse::<usize>()
                    .map_or_else(|_| p.to_string(), |i| format!("{i:020}"))
            })
            .collect::<Vec<_>>();
        (std::cmp::Reverse(parts.len()), parts)
    };
    errors.into_iter().max_by_key(key).map_or(Ok(()), Err)
}
fn walk(v: &Value, s: &Value, root: &Value, sp: &str, ip: &str) -> Result<(), Error> {
    if s == &Value::Bool(true) {
        return Ok(());
    }
    if s == &Value::Bool(false) {
        return Err(diagnostic(
            format!("False schema does not allow {}", v.repr()),
            "None",
            (s, v),
            (sp, ip),
        ));
    }
    let fields = s.as_object().ok_or_else(|| refused("schema"))?;
    for (k, rule) in fields.iter() {
        let k = k.as_str().ok_or_else(|| refused("keyword"))?;
        let fail = |message| Err(diagnostic(message, &repr(k), (s, v), (sp, ip)));
        match k {
            "$ref" => {
                let reference = rule.as_str().ok_or_else(|| refused("$ref"))?;
                let mut target = root;
                for part in reference
                    .strip_prefix("#/")
                    .ok_or_else(|| refused("remote $ref"))?
                    .split('/')
                {
                    target = target
                        .get(&part.replace("~1", "/").replace("~0", "~"))
                        .ok_or_else(|| refused("unresolved $ref"))?;
                }
                walk(v, target, root, sp, ip)?;
            }
            "type" if !matches_type(v, rule.as_str().unwrap_or("")) => {
                return fail(format!("{} is not of type {}", v.repr(), rule.repr()));
            }
            "required" if v.is_object() => {
                for x in rule.as_array().ok_or_else(|| refused(k))? {
                    if v.get(x.as_str().ok_or_else(|| refused(k))?).is_none() {
                        return fail(format!("{} is a required property", x.repr()));
                    }
                }
            }
            "properties" if v.is_object() => {
                let mut errors = Vec::new();
                for (key, sub) in rule.as_object().ok_or_else(|| refused(k))?.iter() {
                    if let Some(x) = v.get(&key.py_str())
                        && let Err(e) = walk(
                            x,
                            sub,
                            root,
                            &format!("{sp}['properties'][{}]", key.repr()),
                            &format!("{ip}[{}]", key.repr()),
                        )
                    {
                        errors.push(e);
                    }
                }
                best(errors)?;
            }
            "additionalProperties" if rule == &Value::Bool(false) && v.is_object() => {
                let mut extras = v
                    .as_object()
                    .ok_or_else(|| refused(k))?
                    .keys()
                    .filter(|key| {
                        s.get("properties")
                            .and_then(|p| p.get(&key.py_str()))
                            .is_none()
                    })
                    .map(|x| x.py_str())
                    .collect::<Vec<_>>();
                extras.sort();
                if !extras.is_empty() {
                    return fail(format!(
                        "Additional properties are not allowed ({} {} unexpected)",
                        extras
                            .iter()
                            .map(|x| repr(x))
                            .collect::<Vec<_>>()
                            .join(", "),
                        if extras.len() == 1 { "was" } else { "were" }
                    ));
                }
            }
            "const"
                if v != rule
                    && !(matches!(v, Value::Number(_))
                        && v.to_serde().as_f64() == rule.to_serde().as_f64()) =>
            {
                return fail(format!("{} was expected", rule.repr()));
            }
            "enum" if !rule.as_array().ok_or_else(|| refused(k))?.contains(v) => {
                return fail(format!("{} is not one of {}", v.repr(), rule.repr()));
            }
            "minLength" if v.as_str().is_some() => {
                let n = rule.repr().parse::<usize>().map_err(|_| refused(k))?;
                if v.as_str().unwrap_or("").chars().count() < n {
                    return fail(if n == 1 {
                        format!("{} should be non-empty", v.repr())
                    } else {
                        format!("{} is too short", v.repr())
                    });
                }
            }
            "pattern" if v.as_str().is_some() => {
                let pattern = rule.as_str().ok_or_else(|| refused(k))?;
                if pattern != "^[0-9a-f]{64}$" {
                    return Err(refused("pattern outside frozen envelope"));
                }
                let text = v.as_str().unwrap_or("");
                let text = text.strip_suffix('\n').unwrap_or(text);
                if text.len() != 64
                    || !text
                        .bytes()
                        .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
                {
                    return fail(format!("{} does not match {}", v.repr(), rule.repr()));
                }
            }
            "minItems" if v.is_array() => {
                let n = rule.repr().parse::<usize>().map_err(|_| refused(k))?;
                if v.as_array().is_some_and(|a| a.len() < n) {
                    return fail(if n == 1 {
                        format!("{} should be non-empty", v.repr())
                    } else {
                        format!("{} is too short", v.repr())
                    });
                }
            }
            "uniqueItems" if rule == &Value::Bool(true) && v.is_array() => {
                let a = v.as_array().ok_or_else(|| refused(k))?;
                if a.iter().enumerate().any(|(i, x)| a[..i].contains(x)) {
                    return fail(format!("{} has non-unique elements", v.repr()));
                }
            }
            "items" if v.is_array() => {
                let mut errors = Vec::new();
                for (i, x) in v.as_array().ok_or_else(|| refused(k))?.iter().enumerate() {
                    if let Err(e) = walk(
                        x,
                        rule,
                        root,
                        &format!("{sp}['items']"),
                        &format!("{ip}[{i}]"),
                    ) {
                        errors.push(e);
                    }
                }
                best(errors)?;
            }
            _ => {} // schema_check admits only the frozen keyword set.
        }
    }
    Ok(())
}
pub(super) fn validate(instance: &str, schema: &str) -> Result<(), Error> {
    let parse = |text| parse(text).map_err(|e| Error::new(e.exception, e.to_string()));
    let (v, s) = (parse(instance)?, parse(schema)?);
    schema_check(&s)?;
    walk(&v, &s, &s, "", "")
}
