//! Shared argparse option-name resolution for the public supply families.
pub(super) fn resolve<'a>(token: &str, names: &'a [&str]) -> Result<Option<&'a str>, String> {
    let name = token.split_once('=').map_or(token, |(name, _)| name);
    let name = if name == "-h" { "--help" } else { name };
    if let Some(exact) = names.iter().find(|n| **n == name) {
        return Ok(Some(exact));
    }
    let matches: Vec<_> = names
        .iter()
        .copied()
        .filter(|n| name.starts_with("--") && n.starts_with(name))
        .collect();
    match matches.as_slice() {
        [] => Ok(None),
        [name] => Ok(Some(name)),
        _ => Err(format!(
            "ambiguous option: {token} could match {}",
            matches.join(", ")
        )),
    }
}
