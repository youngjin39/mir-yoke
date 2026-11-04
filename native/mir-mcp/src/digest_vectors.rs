// Reused padding vectors from the lifecycle crate.
#[test]
fn sha256_matches_reference_at_padding_boundaries() {
    // Expected values come from Python hashlib over bytes (i * 7) % 251.
    for (len, expected) in [
        (
            0,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        (
            1,
            "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
        ),
        (
            55,
            "8af594de0e003fdee5c8bb088216c824349b4137070f559574f4a4bddd27b714",
        ),
        (
            56,
            "db81bc2bfd43620591df192139062da77d4c376f1888ea3d2190bd07c8d901f9",
        ),
        (
            57,
            "4d95ad65f5ec430c9a97ae9243b87d4d6fa0c474288c93cecfbfe9257e711780",
        ),
        (
            63,
            "bd535b38bf0d0d1a09d370b7e34b2696cea3767801a45d5611a4aaa6954e8527",
        ),
        (
            64,
            "292be91abe8c0909fe3d26575af5755eee74d23816dc68c3ba41765136967654",
        ),
        (
            65,
            "ba65aedf7884642499a59ae124894611d986cf429e69f569488048af3a99e25a",
        ),
        (
            119,
            "d367ab298e74477421127b0b448667c37c006c636f5738f081c39388756e5fad",
        ),
        (
            120,
            "be7beb9c82089eb08da8fe6eb30c13b9d56869014e228a8c3eb0fdfe832efab2",
        ),
        (
            127,
            "770cba7b80c7615a327db5812ccd3f80895d801b587448fcd0b2c1a10f5c88a3",
        ),
        (
            128,
            "cb5311e1d7aa8e11d6af7081f3ffc3e4efa008c7483a1a791fe170bf37546ba7",
        ),
        (
            1000,
            "59425e4412e296fc74736673ce067027f384203f59c0d2c3e6be7b13347b3ffc",
        ),
    ] {
        let data: Vec<u8> = (0..len).map(|i| ((i * 7) % 251) as u8).collect();
        assert_eq!(crate::digest::sha256(&data), expected, "length {len}");
    }
}
