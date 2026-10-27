"""Encryption at rest for customer documents and run screenshots.

Every file the application writes that can contain personal data (bills, identity
extracts, passbooks, roof photos, screenshots of portal pages) goes through write()
and comes back through read(). On disk it is Fernet ciphertext (AES-128-CBC with an
HMAC-SHA256 tag), so copying the data folder or a backup does not expose anything.

shortcut: the key lives in data/vault.key beside the data. That protects copies and
backups, not a fully compromised machine. Production moves it to the Windows DPAPI /
OS keychain or sets SOLARA_VAULT_KEY from a secrets manager.
"""
import os
from cryptography.fernet import Fernet
from .config import DATA

KEY_FILE = DATA / "vault.key"
MAGIC = b"SOLARA-VAULT-1\n"


def _key():
    env = os.environ.get("SOLARA_VAULT_KEY")
    if env:
        return env.encode()
    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(Fernet.generate_key())
    return KEY_FILE.read_bytes().strip()


_f = Fernet(_key())


def write(path, data: bytes):
    path.write_bytes(MAGIC + _f.encrypt(data))
    return len(data)


def read(path) -> bytes:
    blob = path.read_bytes()
    # files written before encryption was switched on are returned as they are
    return _f.decrypt(blob[len(MAGIC):]) if blob.startswith(MAGIC) else blob


def is_sealed(path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(len(MAGIC)) == MAGIC
