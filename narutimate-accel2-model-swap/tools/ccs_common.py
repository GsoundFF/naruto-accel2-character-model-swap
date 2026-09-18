# -*- coding: utf-8 -*-
"""ccs_common.py — generic helpers for Narutimate Accel 2 CCS model swaps.

No game data and no hard-coded paths live here. Configure via environment:

    ROOM      game directory containing `_extract/data_inner.iso`
              and `_extract/inner_filelist.txt`
    CCS_LIB   directory that contains the `ccs_lib` package
              (from the open-source blender_ccs_importer project)

The inner file list is TAB separated:  <path>;1 \t <LBA> \t <gz length>
`gz length` is the file's STORED size on disc — it is also the hard capacity
limit for an in-place patch (a replacement must compress to <= this size).
"""
import os
import gzip
import struct
import sys
from collections import defaultdict

ROOM = os.environ.get('ROOM') or os.getcwd()
CCS_LIB = os.environ.get('CCS_LIB')
INNER_ISO = os.path.join(ROOM, '_extract', 'data_inner.iso')
FILELIST = os.path.join(ROOM, '_extract', 'inner_filelist.txt')
SECTOR = 2048

if CCS_LIB:
    sys.path.insert(0, os.path.abspath(CCS_LIB))

from ccs_lib.utils.PyBinaryReader.binary_reader import BinaryReader   # noqa: E402
from ccs_lib.ccs import ccsHeader, ccsIndex, CCSTypes, ccsDict, ccsFile  # noqa: E402
import ccs_lib.ccs as ccsmod                                          # noqa: E402
from ccs_lib.ccsModel import DeformableMesh                           # noqa: E402

TYPE_NAMES = {}
for _k in dir(CCSTypes):
    if not _k.startswith('_'):
        try:
            TYPE_NAMES[getattr(CCSTypes, _k).value] = _k
        except Exception:
            pass


def u32(buf, off):
    return struct.unpack_from('<I', buf, off)[0]


def f32(buf, off):
    return struct.unpack_from('<f', buf, off)[0]


def load_inner(path, decompress=True):
    """Read an inner-ISO file by its '/PL/...' path.

    Returns (data, inner_lba, stored_size). `data` is gunzipped when asked;
    the raw stored bytes are returned if the file is not gzip-compressed.
    """
    with open(FILELIST, encoding='utf-8') as fh:
        for line in fh:
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 3 and parts[0].split(';')[0] == path:
                lba, size = int(parts[1]), int(parts[2])
                with open(INNER_ISO, 'rb') as f:
                    f.seek(lba * SECTOR)
                    raw = f.read(size)
                if decompress:
                    try:
                        return gzip.decompress(raw), lba, size
                    except Exception:
                        return raw, lba, size
                return raw, lba, size
    raise KeyError(path)


def parse_blocks(data):
    """Walk the CCS container.

    Returns (blocks, index, head_len, tail, data). Each block is
    [type, name, start, rec, consumed, obj]. `tail` is everything after the
    Stream block (the Stream chunk itself is 8 bytes of header + rec bytes).
    """
    br = BinaryReader(data, encoding='cp932')
    h = br.read_struct(ccsHeader)
    it = br.read_struct(ccsIndex)
    CCSTypes(br.read_uint16())
    br.seek(2, 1)
    setup_size = br.read_uint32() * 4
    br.seek(setup_size, 1)
    head_len = br.pos()
    blocks = []
    while True:
        tnum = br.read_uint16()
        br.seek(2, 1)                      # 0xCCCC
        rec = br.read_uint32() * 4
        start = br.pos()
        if tnum == CCSTypes.Stream.value:
            br.seek(rec, 1)
            return blocks, it, head_len, data[br.pos():], data
        cls = getattr(ccsmod, ccsDict.get(tnum), None) if ccsDict.get(tnum) else None
        if cls:
            obj = br.read_struct(cls, None, it, h.Version)
            blocks.append([tnum, getattr(obj, 'name', ''), start, rec, br.pos() - start, obj])
        else:
            br.seek(rec, 1)
            blocks.append([tnum, '', start, rec, rec, None])


def block_data(data, blocks, name):
    for b in blocks:
        if b[1] == name:
            return data[b[2]:b[2] + b[4]]
    raise KeyError(name)


def rebuild(src_data, head_len, tail, blocks, replacements, rec_overrides=None):
    """Rebuild a CCS byte stream.

    Unchanged blocks are copied verbatim; `replacements` maps block NAME ->
    new bytes; `rec_overrides` maps block NAME -> new `rec` value in bytes.
    The Stream chunk keeps 8 bytes of header + its own rec bytes.
    """
    rec_overrides = rec_overrides or {}
    bw = BinaryReader(encoding='cp932')
    bw.write_bytes(src_data[:head_len])
    for tnum, name, start, rec, consumed, _obj in blocks:
        payload = replacements.get(name, src_data[start:start + consumed])
        new_rec = rec_overrides.get(name, rec)
        bw.write_uint16(tnum)
        bw.write_uint16(0xCCCC)
        bw.write_uint32(new_rec // 4)
        bw.write_bytes(payload)
    last_end = blocks[-1][2] + blocks[-1][4]
    stream_head = src_data[last_end:last_end + 8]
    stream_rec = struct.unpack_from('<I', stream_head, 4)[0] * 4
    assert struct.unpack_from('<H', stream_head, 0)[0] == CCSTypes.Stream.value
    bw.write_bytes(stream_head)
    bw.write_bytes(src_data[last_end + 8:last_end + 8 + stream_rec])
    bw.write_bytes(tail)
    return bytes(bw.buffer())


def norm_bone(name):
    """'OBJ_2szw00t0 head' -> 'head'  (drops the leading object prefix)."""
    parts = name.split(' ')
    return ' '.join(parts[1:]) if len(parts) > 1 else name


def clump_bones(blocks, names, prefix):
    """[(bone_name, skeleton_position), ...] for the clump whose name carries
    `prefix`. The enumerate index of boneIndices IS the skeleton position."""
    for b in blocks:
        o = b[5]
        if o and o.type == 'Clump' and 'trall' in b[1] and prefix in b[1]:
            return [(norm_bone(names.get(bi, '?')), i) for i, bi in enumerate(o.boneIndices)]
    return None


def name_pmap(src_blocks, src_names, src_prefix, tgt_blocks, tgt_names, tgt_prefix, fallback):
    """source skeleton position -> target skeleton position, by bone NAME.

    Use for skeletons whose bone names are unique. See `occ_pmap` when left and
    right bones share identical names (very common in the 1P high models).
    """
    target = {}
    for b in tgt_blocks:
        o = b[5]
        if o and o.type == 'Clump' and 'trall' in b[1] and tgt_prefix in b[1]:
            for i, bi in enumerate(o.boneIndices):
                target.setdefault(norm_bone(tgt_names.get(bi, '?')), i)
    src = clump_bones(src_blocks, src_names, src_prefix) or []
    return {i: target.get(nm, fallback) for nm, i in src}


def occ_pmap(src_blocks, src_names, src_prefix, tgt_blocks, tgt_names, tgt_prefix, fallback):
    """Occurrence-aware map: the Nth source bone called X -> the Nth target bone
    called X. REQUIRED when left/right bones share a name (e.g. both called
    'clavicle'), otherwise both sides collapse onto the first match.
    """
    target = defaultdict(list)
    for b in tgt_blocks:
        o = b[5]
        if o and o.type == 'Clump' and 'trall' in b[1] and tgt_prefix in b[1]:
            for i, bi in enumerate(o.boneIndices):
                target[norm_bone(tgt_names.get(bi, '?'))].append(i)
    seen = defaultdict(int)
    out = {}
    for nm, i in (clump_bones(src_blocks, src_names, src_prefix) or []):
        lst = target.get(nm)
        k = seen[nm]
        seen[nm] += 1
        out[i] = lst[k] if lst and k < len(lst) else (lst[-1] if lst else fallback)
    return out


def retarget_body(src_body, name_idx, mat_from, mat_to, lookup):
    """Rewrite a deformable-body Model block into the target's name space.

    - u32 name index  -> name_idx
    - lookupList      -> `lookup` (one byte per entry)
    - per-mesh materialIndex: asserted == mat_from, rewritten to mat_to
    Vertex data (and therefore the bone SLOTS stored in it) is never touched:
    slots are indices into lookupList, not skeleton positions.
    """
    out = bytearray(src_body)
    struct.pack_into('<I', out, 0, name_idx)
    ll = src_body[16]
    head = 28 + ((ll + 3) & ~3)
    for i, v in enumerate(lookup):
        out[28 + i] = v
    off = head
    mesh_count = struct.unpack_from('<H', out, 10)[0]
    vscale = f32(src_body, 4)
    for i in range(mesh_count):
        assert u32(out, off) == mat_from, 'mesh %d material %d != %d' % (i, u32(out, off), mat_from)
        struct.pack_into('<I', out, off, mat_to)
        vc = u32(out, off + 4)
        dc = u32(out, off + 8)
        off += 12
        if dc == 0:
            off += 4 + vc * 6
            off = (off + 3) & ~3
            off += vc * 4 + vc * 4
        else:
            off += dc * 8 + dc * 4 + vc * 4
    return bytes(out)


def empty_model_header(data, blocks, new_idx):
    """Build a valid EMPTY Model block (28 bytes) by copying a REAL empty model
    found in the same file (rec == consumed == 28) and only changing its index.

    Do NOT synthesise an all-zero header: real ones carry
    outline = (-0.0, 1.0) and other fields the engine expects.
    """
    for b in blocks:
        if b[3] == 28 and b[4] == 28:
            out = bytearray(data[b[2]:b[2] + 28])
            struct.pack_into('<I', out, 0, new_idx)
            return bytes(out)
    raise RuntimeError('no real empty-model template found in this file')


def rec_override(src_blocks, replacements):
    """new rec value = new payload length + (original rec - consumed).

    Convention observed in the game files: Model body +1140, empty/hair +120,
    Texture +200, Clut +0 — but always take the delta from the block itself.
    """
    delta = {b[1]: b[3] - b[4] for b in src_blocks}
    return {nm: len(payload) + delta[nm] for nm, payload in replacements.items() if nm in delta}


def fit_check(payload, limit, label=''):
    gz = gzip.compress(payload, 9)
    ok = len(gz) <= limit
    print('  %-28s gz=%-8d limit=%-8d %s' % (label, len(gz), limit, 'FIT' if ok else 'TOO BIG'))
    return gz, ok
