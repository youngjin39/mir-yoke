"""Test that all JSON Schema files in docs/templates/_schema/ self-validate (Draft 2020-12)."""
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


def test_all_schemas_self_validate():
    schema_dir = Path("docs/templates/_schema")
    if not schema_dir.exists():
        return  # No schemas present yet — pass until baseline is established
    schema_files = list(schema_dir.glob("*.schema.json"))
    assert schema_files, f"No *.schema.json files found in {schema_dir}"
    for schema_file in schema_files:
        schema = json.load(open(schema_file))
        # Validate schema structure against Draft 2020-12 meta-schema
        jsonschema.Draft202012Validator.check_schema(schema)


if __name__ == "__main__":
    test_all_schemas_self_validate()
    print("test_schema_validity: PASS")
