"""Git object storage implementation.

This module provides storage backends for Git objects:
- LooseObjectStore: Individual zlib-compressed files
- ObjectDatabase: High-level interface with type-safe access
- PackFile: Pack file reader
- PackIndex: Pack index for fast lookup
- PackWriter: Pack file writer
- Delta functions: Delta encoding/decoding

Storage format follows Git's conventions:
- Loose objects stored at .git/objects/<sha[0:2]>/<sha[2:40]>
- Pack files stored at .git/objects/pack/pack-<sha>.pack
- All data is zlib-compressed
- SHA-1 verification on read
"""

from .compression import compress, decompress, decompress_stream
from .database import ObjectDatabase
from .delta import (
    DeltaCopy,
    DeltaInsert,
    apply_delta,
    create_delta,
    parse_delta,
)
from .loose import LooseObjectStore
from .pack import (
    PACK_SIGNATURE,
    PACK_VERSION,
    PackFile,
    PackObject,
    PackObjectType,
    read_ofs_delta_offset,
    read_pack_object_header,
    write_ofs_delta_offset,
    write_pack_object_header,
)
from .pack_index import (
    IDX_SIGNATURE,
    IDX_VERSION,
    PackIndex,
    PackIndexEntry,
)
from .pack_writer import PackEntry, PackWriter

__all__ = [
    # Compression
    "compress",
    "decompress",
    "decompress_stream",
    # Loose objects
    "LooseObjectStore",
    # Object database
    "ObjectDatabase",
    # Delta
    "DeltaInsert",
    "DeltaCopy",
    "parse_delta",
    "apply_delta",
    "create_delta",
    # Pack file
    "PACK_SIGNATURE",
    "PACK_VERSION",
    "PackFile",
    "PackObject",
    "PackObjectType",
    "read_pack_object_header",
    "write_pack_object_header",
    "read_ofs_delta_offset",
    "write_ofs_delta_offset",
    # Pack index
    "IDX_SIGNATURE",
    "IDX_VERSION",
    "PackIndex",
    "PackIndexEntry",
    # Pack writer
    "PackEntry",
    "PackWriter",
]
