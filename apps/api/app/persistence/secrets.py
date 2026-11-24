import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class CredentialError(Exception):
    pass


class CredentialVault:
    def __init__(self, key_path: Path, *, existing_credentials: bool):
        self.path = Path(key_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            if existing_credentials:
                raise CredentialError('Chave local ausente. Restaure a chave original antes de iniciar a API.')
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, 'wb') as output:
                    output.write(Fernet.generate_key())
        if self.path.stat().st_mode & 0o077:
            raise CredentialError('A chave local deve ter permissão 600.')
        try:
            self.fernet = Fernet(self.path.read_bytes())
        except (ValueError, OSError):
            raise CredentialError('Chave local inválida ou inacessível.') from None

    def encrypt(self, email: str, token: str) -> bytes:
        return self.fernet.encrypt(json.dumps({'email': email, 'token': token}).encode())

    def decrypt(self, encrypted: bytes) -> dict:
        try:
            return json.loads(self.fernet.decrypt(encrypted))
        except (InvalidToken, ValueError, UnicodeError):
            raise CredentialError('Não foi possível abrir as credenciais. Restaure a chave original.') from None
