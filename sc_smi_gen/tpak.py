"""CC0-1.0. Strings-only reader for TPAK v7 archives.

Re-implemented from the public format description
(sc-server-under-the-hood, docs/08-reverse-engineering/tpak-format.md).
It lists entry names and extracts only the string tables the generator
needs; it is deliberately not a general asset extractor.
"""
import struct
import zlib

MAGIC, VERSION, CHECK = 0x4B415054, 7, 0xFFFFFFE3
WANTED = ('strings\\english\\string.txt', 'strings\\russian\\string.txt')


class PakError(ValueError):
    pass


def _inflate(data, key, expected=None):
    if len(data) < 4:
        raise PakError('table too short')
    first = struct.unpack_from('<I', data)[0] ^ (key & 0xFFFFFFFF)
    raw = struct.pack('<I', first) + data[4:]
    try:
        out = zlib.decompress(raw, -15)
    except zlib.error as error:
        raise PakError('cannot inflate table') from error
    if expected is not None and len(out) != expected:
        raise PakError('table size mismatch')
    return out


def _align4(n):
    return (n + 3) & ~3


class Pak:
    def __init__(self, data):
        self.data = data
        if len(data) < 28:
            raise PakError('not a TPAK file')
        magic, version, _reserved, n, check, u1, c1 = struct.unpack_from('<7I', data)
        if magic != MAGIC or version != VERSION or check != CHECK:
            raise PakError('not a TPAK v7 file')
        pos = 28
        register = _inflate(data[pos:pos + c1], n, u1)
        pos = _align4(pos + c1) + 4 * n          # skip the sorted permutation
        (c2,) = struct.unpack_from('<I', data, pos); pos += 4
        files = _inflate(data[pos:pos + c2], c2 + n, 16 * n)
        pos = _align4(pos + c2)
        c3, m = struct.unpack_from('<2I', data, pos); pos += 8
        chunks = _inflate(data[pos:pos + c3], m + c3 + n, 16 * m) if m else b''
        self.base = _align4(pos + c3)
        self.chunks = [struct.unpack_from('<4I', chunks, 16 * i) for i in range(m)]
        names, offsets, p = [], {}, 0
        for idx in range(n):
            (length,) = struct.unpack_from('<I', register, p)
            stored = register[p + 4:p + 4 + length]
            k = (length % 5 + idx) & 0xFF
            plain = bytes(b ^ ((2 * (j + length) + k) & 0xFF) for j, b in enumerate(stored))
            offsets[p + 4] = plain.decode('utf-8', 'replace')
            names.append(offsets[p + 4])
            p += 4 + length + 1
        self.entries = {}
        for i in range(n):
            size, name_offset, count, first = struct.unpack_from('<4I', files, 16 * i)
            name = offsets.get(name_offset)
            if name is None:
                raise PakError('bad name offset')
            self.entries[name.lower()] = (size, count, first)

    def names(self):
        return sorted(self.entries)

    def read(self, name):
        size, count, first = self.entries[name.lower()]
        out = bytearray(size)
        for file_offset, csize_plain, data_offset, csize in self.chunks[first:first + count]:
            start = self.base + data_offset
            blob = self.data[start:start + csize]
            piece = blob if csize == csize_plain else zlib.decompress(blob, -15)
            if len(piece) != csize_plain or file_offset + csize_plain > size:
                raise PakError('chunk size mismatch')
            out[file_offset:file_offset + csize_plain] = piece
        return bytes(out)


def extract_strings(pak_path, target):
    """Write strings/english/string.txt and strings/russian/string.txt under target."""
    pak = Pak(pak_path.read_bytes())
    written = []
    for name in WANTED:
        if name not in pak.entries:
            raise PakError('missing entry ' + name.replace('\\', '/'))
        folder = name.split('\\')[1]
        path = target / folder / 'string.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pak.read(name))
        written.append(path)
    return written
