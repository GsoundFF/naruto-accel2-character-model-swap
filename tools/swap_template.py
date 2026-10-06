# -*- coding: utf-8 -*-
"""swap_template.py — surgical appearance transplant for ONE variant.

Fill in CONFIG from the output of `analyze_pairs.py`, then run once per variant
(battle / MODEL / 1P). Writes `_extract/replacement_surgical/<NAME>.CCS.gz`.

Key ideas (see SKILL.md for the full rationale):
  * only appearance blocks are replaced (body mesh / body texture / CLUTs /
    rigid eye-mouth pieces); skeleton, animations, name table and Stream stay
    the TARGET's, so the character keeps its own moves;
  * vertex bone ids are lookups slots -> only `lookupList` is rewritten;
  * the result must gzip to <= the target's stored size or it cannot be patched.
"""
import os
import struct
import ccs_common as C

# --------------------------------------------------------------------------
# CONFIG — fill these in from `python analyze_pairs.py <TARGET> <SOURCE>`
# --------------------------------------------------------------------------
TARGET = '/PL/2KRWBOD1.CCS'          # keeps its moves / skeleton
SOURCE = '/PL/2SZWBOD1.CCS'          # supplies the appearance
OUT_NAME = 'PL_2KRWBOD1.CCS.gz'      # written into _extract/replacement_surgical/

TGT_PREFIX = 'krw00t0'               # clump-name fragment that identifies the target skeleton
SRC_PREFIX = 'szw00t0'

# body Model block on each side, with its name index and per-mesh material index
TGT_BODY = 'MDL_2krw00t0 body'
SRC_BODY = 'MDL_2szw00t0 body'
TGT_BODY_IDX = 4503
TGT_MAT = 4504
SRC_MAT = 4672

# body texture block on each side + the CLUT index it points at
TGT_TEX = 'TEX_2krwbody'
SRC_TEX = 'TEX_2szwbody'
TGT_TEX_IDX = 4505
TGT_TEX_CLUT = 4520
SRC_TEX_CLUT = 4752

# CLUT blocks to refill: {target block name: source CLUT index}
TGT_CLUTS = {'CLT_2krwbody': 4752, 'CLT_2krwbodyc1': 4753, 'CLT_2krwbodyc2': 4754}

# optional: rigid face pieces transplanted as geometry only (1P models).
# The target's name index / parent / material are kept, otherwise the engine
# crashes when entering battle.
FACE_PIECES = []                     # e.g. ['eye1', 'eye2', 'mou1']
TGT_FACE_PREFIX = 'MDL_1krw00t0'
SRC_FACE_PREFIX = 'MDL_1szw00t0'

# bones the target skeleton does not have -> bind here (usually pelvis)
FALLBACK_TO = 28                     # target 'body' position
EXTRA_BONE_FIX = {'tail': 3, 'tail1': 3, 'tail2': 3}   # source bone name -> target position

# 'name' for skeletons with unique bone names, 'occ' when left/right share names
MAP_MODE = 'name'
# --------------------------------------------------------------------------


def main():
    tgt_data, _tgt_lba, tgt_size = C.load_inner(TARGET)
    src_data, _src_lba, _src_size = C.load_inner(SOURCE)
    tb, ti, t_head, t_tail, _ = C.parse_blocks(tgt_data)
    sb, si, _s_head, _s_tail, _ = C.parse_blocks(src_data)
    tnames = {n: i for i, (n, _p) in enumerate(ti.Names)}
    snames = {n: i for i, (n, _p) in enumerate(si.Names)}
    print('target %s blocks=%d stored=%d | source %s blocks=%d' % (
        TARGET, len(tb), tgt_size, SOURCE, len(sb)))

    pmap_fn = C.occ_pmap if MAP_MODE == 'occ' else C.name_pmap
    pmap = pmap_fn(sb, snames, SRC_PREFIX, tb, tnames, TGT_PREFIX, FALLBACK_TO)
    for bone, pos in EXTRA_BONE_FIX.items():
        for nm, i in (C.clump_bones(sb, snames, SRC_PREFIX) or []):
            if nm == bone:
                pmap[i] = pos

    src_body = C.block_data(src_data, sb, SRC_BODY)
    src_lookup = [x for b in sb if b[1] == SRC_BODY for x in (b[5].lookupList or [])]
    new_lookup = [pmap[e] for e in src_lookup]
    print('new lookup:', new_lookup)
    new_body = C.retarget_body(src_body, TGT_BODY_IDX, SRC_MAT, TGT_MAT, new_lookup)

    src_tex = bytearray(C.block_data(src_data, sb, SRC_TEX))
    struct.pack_into('<I', src_tex, 0, TGT_TEX_IDX)
    struct.pack_into('<I', src_tex, 4, TGT_TEX_CLUT)

    replacements = {TGT_BODY: new_body, TGT_TEX: bytes(src_tex)}
    for tgt_clut, src_clut_idx in TGT_CLUTS.items():
        payload = None
        for b in sb:
            o = b[5]
            if o and o.type == 'Clut' and o.index == src_clut_idx:
                payload = bytearray(src_data[b[2]:b[2] + b[4]])
                break
        assert payload is not None, 'source CLUT %d not found' % src_clut_idx
        struct.pack_into('<I', payload, 0, tgt_clut_idx_of(tb, tgt_clut))
        replacements[tgt_clut] = bytes(payload)

    for piece in FACE_PIECES:
        tgt_name = '%s %s' % (TGT_FACE_PREFIX, piece)
        src_name = '%s %s' % (SRC_FACE_PREFIX, piece)
        orig = C.block_data(tgt_data, tb, tgt_name)
        raw = bytearray(C.block_data(src_data, sb, src_name))
        struct.pack_into('<I', raw, 0, C.u32(orig, 0))    # target name index
        struct.pack_into('<I', raw, 28, C.u32(orig, 28))  # target parent ("_0" block)
        struct.pack_into('<I', raw, 32, C.u32(orig, 32))  # target material
        replacements[tgt_name] = bytes(raw)

    out = C.rebuild(tgt_data, t_head, t_tail, tb, replacements, C.rec_override(tb, replacements))
    print('rebuilt: %d -> %d bytes' % (len(tgt_data), len(out)))

    # verify by re-parsing
    nb, _ni, _nh, _nt, _nd = C.parse_blocks(out)
    assert [b[1] for b in nb] == [b[1] for b in tb], 'block order changed!'
    body = [b for b in nb if b[1] == TGT_BODY][0][5]
    assert list(body.lookupList) == new_lookup, 'lookup mismatch'
    assert all(m.materialIndex == TGT_MAT for m in body.meshes), 'material mismatch'
    print('verify OK: blocks=%d meshes=%d' % (len(nb), body.meshCount))

    gz, ok = C.fit_check(out, tgt_size, os.path.basename(OUT_NAME))
    if not ok:
        raise SystemExit('TOO BIG for in-place patch: free space or pick another source')
    dest = os.path.join(C.ROOM, '_extract', 'replacement_surgical')
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, OUT_NAME), 'wb') as fh:
        fh.write(gz)
    print('written', os.path.join(dest, OUT_NAME))


def tgt_clut_idx_of(blocks, name):
    for b in blocks:
        o = b[5]
        if o and o.type == 'Clut' and b[1] == name:
            return o.index
    raise KeyError(name)


if __name__ == '__main__':
    main()
