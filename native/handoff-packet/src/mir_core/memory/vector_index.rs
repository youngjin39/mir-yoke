//! Vector validation and sqlite-vec helpers; table names are caller-owned SQL identifiers.
use rusqlite::{Connection, params};
use std::fmt;

#[derive(Debug)]
pub enum Error {
    Validation(String),
    Sql(rusqlite::Error),
}
impl Error {
    pub fn python_class(&self) -> &'static str {
        match self {
            Self::Validation(_) => "ValueError",
            Self::Sql(_) => "OperationalError",
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Validation(s) => f.write_str(s),
            Self::Sql(e) => e.fmt(f),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Sql(e) => Some(e),
            Self::Validation(_) => None,
        }
    }
}
impl From<rusqlite::Error> for Error {
    fn from(e: rusqlite::Error) -> Self {
        Self::Sql(e)
    }
}
fn float_repr(x: f64) -> String {
    if x.is_nan() {
        "nan".into()
    } else {
        format!("{x:?}")
    }
}
pub fn validate_embedding(vector: &[f64], expected_dim: usize) -> Result<(), Error> {
    if vector.len() != expected_dim {
        return Err(Error::Validation(format!(
            "embedding length {} != expected dim {expected_dim}",
            vector.len()
        )));
    }
    for (i, &x) in vector.iter().enumerate() {
        if !x.is_finite() {
            return Err(Error::Validation(format!(
                "embedding[{i}] is not finite: {}",
                float_repr(x)
            )));
        }
        if x.abs() > 10.0 {
            return Err(Error::Validation(format!(
                "embedding[{i}]={} exceeds defensive bound \u{b1}10.0",
                float_repr(x)
            )));
        }
    }
    Ok(())
}
pub fn pack_vector(vector: &[f64]) -> Vec<u8> {
    vector
        .iter()
        .flat_map(|&x| (x as f32).to_le_bytes())
        .collect()
}
pub fn ensure_vec_table(conn: &Connection, dim: usize, table: &str) -> Result<(), Error> {
    conn.execute(
        &format!("CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0(embedding float[{dim}])"),
        [],
    )?;
    Ok(())
}
pub fn upsert_vector(
    conn: &Connection,
    rowid: i64,
    vector: &[f64],
    expected_dim: usize,
    table: &str,
) -> Result<(), Error> {
    validate_embedding(vector, expected_dim)?;
    conn.execute(
        &format!("INSERT OR REPLACE INTO {table}(rowid, embedding) VALUES (?, ?)"),
        params![rowid, pack_vector(vector)],
    )?;
    Ok(())
}
pub fn knn(
    conn: &Connection,
    query: &[f64],
    k: i64,
    table: &str,
) -> Result<Vec<(i64, f64)>, Error> {
    let mut stmt = conn.prepare(&format!(
        "SELECT rowid, distance FROM {table} \
         WHERE embedding MATCH ? ORDER BY distance LIMIT ?"
    ))?;
    Ok(stmt
        .query_map(params![pack_vector(query), k], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })?
        .collect::<Result<_, _>>()?)
}
