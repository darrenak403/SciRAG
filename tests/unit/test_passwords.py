from scientrag.auth.passwords import DUMMY_HASH, hash_password, verify_password


def test_hash_is_argon2id_and_salted():
    first = hash_password("correct horse battery")
    second = hash_password("correct horse battery")

    assert first.startswith("$argon2id$")
    assert first != second


def test_verify_accepts_only_the_right_password():
    password_hash = hash_password("correct horse battery")

    assert verify_password(password_hash, "correct horse battery")
    assert not verify_password(password_hash, "correct horse batterx")
    assert not verify_password(password_hash, "")


def test_verify_returns_false_for_a_value_that_is_not_a_hash():
    assert not verify_password("not a hash", "anything")


def test_nothing_verifies_against_the_dummy_hash_by_accident():
    assert not verify_password(DUMMY_HASH, "")
    assert not verify_password(DUMMY_HASH, "password")
