"""Implementation of ``git hash-object``.

Computes the SHA-1 of an object and optionally writes it to the database.
"""

import hashlib

from gitpy.repository import Repository

_VALID_TYPES = frozenset({"blob", "tree", "commit", "tag"})


def hash_object(
    repo: Repository,
    data: bytes,
    *,
    type_name: str = "blob",
    write: bool = False,
) -> str:
    """Compute (and optionally store) the SHA-1 of a Git object.

    Hashes the raw *data* bytes with the ``<type> <len>\\0`` header, exactly
    as ``git hash-object -t <type>`` does.  The data is never round-tripped
    through a Python object class, so the OID is always byte-for-byte
    identical to what real Git would produce.

    Args:
        repo: Repository whose object database is used when *write* is True.
        data: Raw object content (not including the Git header).
        type_name: Object type: "blob", "tree", "commit", or "tag".
        write: When True, persist the object to the object database.

    Returns:
        40-character hex SHA-1 of the object.

    Raises:
        ValueError: *type_name* is not a recognised Git object type.
    """
    if type_name not in _VALID_TYPES:
        raise ValueError(f"Unknown object type: {type_name!r}")

    header = f"{type_name} {len(data)}\0".encode()
    full = header + data
    sha = hashlib.sha1(full, usedforsecurity=False).hexdigest()

    if write:
        repo.objects.loose.write(sha, full)

    return sha
