from app.security import hash_password, verify_password


def test_a_password_verifies_against_its_own_hash():
    stored = hash_password("correct-horse-battery")

    assert verify_password("correct-horse-battery", stored) is True


def test_a_wrong_password_does_not_verify():
    stored = hash_password("correct-horse-battery")

    assert verify_password("wrong-horse-battery", stored) is False


def test_the_same_password_hashes_differently_each_time():
    # Each hash contains its own random salt, so identical passwords cannot be spotted.
    assert hash_password("same-password-123") != hash_password("same-password-123")


def test_a_corrupt_stored_hash_fails_safely_instead_of_crashing():
    assert verify_password("anything", "this-is-not-a-valid-hash") is False
