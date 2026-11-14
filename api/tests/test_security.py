from app.security import generate_api_key, hash_api_key


def test_generated_key_has_prefix_and_matching_hash() -> None:
    key, prefix, key_hash = generate_api_key()
    assert key.startswith("ta_")
    assert key.startswith(prefix)
    assert len(prefix) == 11
    assert key_hash == hash_api_key(key)
    assert len(key_hash) == 64


def test_keys_are_unique_and_hash_is_not_the_key() -> None:
    first, _, first_hash = generate_api_key()
    second, _, second_hash = generate_api_key()
    assert first != second
    assert first_hash != second_hash
    assert first not in first_hash
