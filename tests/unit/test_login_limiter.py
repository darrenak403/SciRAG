from scientrag.auth import login_limiter


def test_blocks_after_the_maximum_number_of_failures():
    for _ in range(login_limiter.MAX_FAILURES - 1):
        login_limiter.record_failure("1.2.3.4", "a@example.com")
    assert not login_limiter.is_blocked("1.2.3.4", "a@example.com")

    login_limiter.record_failure("1.2.3.4", "a@example.com")
    assert login_limiter.is_blocked("1.2.3.4", "a@example.com")


def test_counts_each_ip_and_email_pair_separately():
    for _ in range(login_limiter.MAX_FAILURES):
        login_limiter.record_failure("1.2.3.4", "a@example.com")

    assert not login_limiter.is_blocked("5.6.7.8", "a@example.com")
    assert not login_limiter.is_blocked("1.2.3.4", "b@example.com")


def test_failures_older_than_the_window_are_forgotten(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(login_limiter.time, "monotonic", lambda: now)
    for _ in range(login_limiter.MAX_FAILURES):
        login_limiter.record_failure("1.2.3.4", "a@example.com")
    assert login_limiter.is_blocked("1.2.3.4", "a@example.com")

    now += login_limiter.WINDOW_SECONDS + 1
    assert not login_limiter.is_blocked("1.2.3.4", "a@example.com")


def test_clear_lifts_the_block():
    for _ in range(login_limiter.MAX_FAILURES):
        login_limiter.record_failure("1.2.3.4", "a@example.com")

    login_limiter.clear("1.2.3.4", "a@example.com")

    assert not login_limiter.is_blocked("1.2.3.4", "a@example.com")
