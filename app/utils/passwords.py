"""
ONE place that knows which hasher belongs to which table.

The platform has TWO password schemes and cannot safely unify them:
  users            -> werkzeug scrypt   (managers, master)
  dealership_team  -> bcrypt            (reps)

Hashes are one-way, so converting would require force-resetting every existing
rep -- including Ryan, who is already disengaged. That is a worse outcome than
the split. Instead: nobody chooses a hasher again. Everything goes through here.

Stage 6 proved the footgun is real: pick the wrong scheme and the account
silently cannot log in, with no error anywhere.
"""
from werkzeug.security import generate_password_hash, check_password_hash
import bcrypt

USER = 'user'   # users table          -> scrypt
REP  = 'rep'    # dealership_team table -> bcrypt


def hash_password(kind, plaintext):
    """Hash a password with the scheme that table requires."""
    if kind == USER:
        return generate_password_hash(plaintext)
    if kind == REP:
        return bcrypt.hashpw(plaintext.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    raise ValueError(f"unknown account kind: {kind!r} (expected 'user' or 'rep')")


def verify_password(kind, stored_hash, plaintext):
    """Check a password. Returns True/False. Never raises on a bad hash."""
    if not stored_hash:
        return False
    try:
        if kind == USER:
            return check_password_hash(stored_hash, plaintext)
        if kind == REP:
            return bcrypt.checkpw(plaintext.encode('utf-8'), stored_hash.encode('utf-8'))
    except Exception:
        return False
    raise ValueError(f"unknown account kind: {kind!r}")


def scheme_of(stored_hash):
    """Identify a hash's scheme -- useful for audits and a future migration."""
    if not stored_hash:
        return None
    if stored_hash.startswith('$2b$') or stored_hash.startswith('$2a$'):
        return 'bcrypt'
    if stored_hash.startswith('scrypt:') or stored_hash.startswith('pbkdf2:'):
        return 'werkzeug'
    return 'unknown'
