"""Permission catalogue, rate limiter, tokens, password hashing."""

from datetime import timedelta

import pytest

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.auth.permissions import MINIMUM_ROLE, Permission, has_permission, permissions_for
from fleet_service.auth.ratelimit import FailureLimiter
from fleet_service.auth.sessions import TOKEN_PREFIX, hash_token, new_token
from fleet_service.domain.enums import ROLE_RANK, Role

from support import FakeClock


def test_every_permission_has_a_minimum_role() -> None:
    assert set(MINIMUM_ROLE) == set(Permission)


@pytest.mark.parametrize("permission", list(Permission))
def test_higher_roles_never_have_fewer_permissions(permission: Permission) -> None:
    granted = [
        has_permission(role, permission) for role in sorted(Role, key=lambda role: ROLE_RANK[role])
    ]

    assert granted == sorted(granted)  # False... then True...


def test_role_permission_sets() -> None:
    assert permissions_for(Role.OBSERVER) == [Permission.FLEET_VIEW]
    assert set(permissions_for(Role.OPERATOR)) == {
        Permission.FLEET_VIEW,
        Permission.MISSIONS_PLAN,
        Permission.ALERTS_ACK,
        Permission.AIRCRAFT_HOLD,
        Permission.AIRCRAFT_COMMAND,
    }
    assert Permission.CONTROL_OVERRIDE in permissions_for(Role.SUPERVISOR)
    assert Permission.USERS_MANAGE not in permissions_for(Role.SUPERVISOR)
    assert permissions_for(Role.ADMIN) == list(Permission)


def test_limiter_blocks_after_max_failures_and_recovers_after_the_window() -> None:
    clock = FakeClock()
    limiter = FailureLimiter(clock, max_failures=3, window=timedelta(minutes=5))

    for _ in range(3):
        assert limiter.retry_after_s("user:x") is None
        limiter.record_failure("user:x")
        clock.advance(seconds=10)

    assert limiter.retry_after_s("user:x") == 270  # the first failure expires 300 s after it
    clock.advance(seconds=271)
    assert limiter.retry_after_s("user:x") is None


def test_limiter_keys_are_independent_and_reset_clears() -> None:
    limiter = FailureLimiter(FakeClock(), max_failures=1, window=timedelta(minutes=5))

    limiter.record_failure("user:a")

    assert limiter.retry_after_s("user:a") is not None
    assert limiter.retry_after_s("user:b") is None
    limiter.reset("user:a")
    assert limiter.retry_after_s("user:a") is None


def test_tokens_are_prefixed_unique_and_stored_hashed() -> None:
    tokens = {new_token() for _ in range(100)}

    assert len(tokens) == 100
    token = tokens.pop()
    assert token.startswith(TOKEN_PREFIX)
    assert len(token) >= len(TOKEN_PREFIX) + 43  # 32 random bytes, base64url
    assert hash_token(token) != token
    assert len(hash_token(token)) == 64


async def test_passwords_verify_and_reject() -> None:
    passwords = fast_passwords_for_tests()
    stored = await passwords.hash("correct-horse-battery")

    assert stored.startswith("$argon2id$")
    assert await passwords.verify(stored, "correct-horse-battery")
    assert not await passwords.verify(stored, "wrong-horse-battery")
    assert not await passwords.verify("not-a-hash", "anything")
    await passwords.verify_unknown_user("anything")  # must not raise


def test_rehash_is_needed_when_parameters_change() -> None:
    import argon2

    old = argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("x" * 12)

    assert not fast_passwords_for_tests().needs_rehash(old)
    assert argon2.PasswordHasher().check_needs_rehash(old)
