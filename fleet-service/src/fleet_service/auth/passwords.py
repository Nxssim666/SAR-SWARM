"""
Password hashing with Argon2id (ADR 0009).

Hashing takes tens of milliseconds by design, so it runs in a worker thread, and
callers must not hold a database transaction open while awaiting it (ADR 0019).
"""

import asyncio

import argon2
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256


class Passwords:
    """Hash and verify passwords; verifying an unknown user costs the same as a known one."""

    def __init__(self, hasher: argon2.PasswordHasher | None = None) -> None:
        self._hasher = hasher or argon2.PasswordHasher()  # RFC 9106 low-memory profile
        self._dummy_hash: str | None = None

    async def hash(self, password: str) -> str:
        """Return the Argon2id hash of ``password``."""
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        """Return True if ``password`` matches ``password_hash``."""
        return await asyncio.to_thread(self._verify_sync, password_hash, password)

    async def verify_unknown_user(self, password: str) -> None:
        """Spend the time of a real verification, so response timing does not reveal accounts."""
        if self._dummy_hash is None:
            self._dummy_hash = await self.hash("not-a-real-password-for-timing")
        await self.verify(self._dummy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        """Return True if ``password_hash`` used different parameters than the current ones."""
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True

    def _verify_sync(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


def fast_passwords_for_tests() -> Passwords:
    """Deliberately weak parameters, for tests only."""
    return Passwords(argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
