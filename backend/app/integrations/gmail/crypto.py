from collections.abc import Sequence

from cryptography.fernet import Fernet, InvalidToken


class TokenCipher:
    """Encrypt refresh tokens with the first key and decrypt with any active key."""

    def __init__(self, keys: Sequence[str]) -> None:
        if not keys:
            raise ValueError("At least one token encryption key is required")
        self._fernets = [Fernet(key.encode()) for key in keys]

    def encrypt(self, plaintext: str) -> str:
        return "v1:" + self._fernets[0].encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            version, payload = ciphertext.split(":", 1)
        except ValueError as exc:
            raise InvalidToken("Unsupported token version") from exc
        if version != "v1":
            raise InvalidToken("Unsupported token version")
        for fernet in self._fernets:
            try:
                return fernet.decrypt(payload.encode()).decode()
            except InvalidToken:
                continue
        raise InvalidToken("Token cannot be decrypted")
