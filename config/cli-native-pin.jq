select(.source_commit == $commit) | .targets[$target]
| select(.url | type == "string" and startswith("https://") and (contains("@") | not))
| select(.sha256 | type == "string" and test("^[0-9a-f]{64}$"))
| select(.size | type == "number" and . == floor and . > 0 and . <= 2147483647)
| [.url, .sha256, .size] | @tsv
