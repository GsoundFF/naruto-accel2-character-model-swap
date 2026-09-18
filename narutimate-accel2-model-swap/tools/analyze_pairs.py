# -*- coding: utf-8 -*-
"""analyze_pairs.py — dump the structure of a target/source CCS pair so you can
fill in the CONFIG of `swap_template.py`.

Usage:
    set ROOM=<game dir>
    set CCS_LIB=<dir containing ccs_lib>
    python analyze_pairs.py /PL/2KRWBOD1.CCS /PL/2SZWBOD1.CCS

Prints, for each file: block counts, the trall clump with every bone and its
skeleton position, each body-like Model block (name index / mesh count /
lookupListCount / lookupList), and every Texture/Clut with its index.
"""
import sys
import ccs_common as C


def dump(path):
    data, lba, size = C.load_inner(path)
    blocks, index, head_len, tail, _ = C.parse_blocks(data)
    names = {i: n for i, (n, _p) in enumerate(index.Names)}
    print('=' * 100)
    print('%s   innerLBA=%d  stored=%d  decompressed=%d  blocks=%d' % (
        path, lba, size, len(data), len(blocks)))

    for b in blocks:
        o = b[5]
        if o and o.type == 'Clump' and 'trall' in b[1]:
            bones = C.clump_bones(blocks, names, '')
            print('  clump %-24s bones=%d' % (b[1], o.boneCount))
            print('    ' + ' | '.join('%2d:%s' % (i, nm) for nm, i in bones))

    for b in blocks:
        o = b[5]
        if o and o.type == 'Model' and o.meshCount and 'body' in b[1]:
            print('  MODEL %-28s idx=%-6d meshes=%-3d llcount=%-3d mat0=%d' % (
                b[1], o.index, o.meshCount, o.lookupListCount,
                o.meshes[0].materialIndex if o.meshCount else -1))
            print('     lookup=%s' % (list(o.lookupList or [])))
        elif o and o.type == 'Model' and b[4] >= 28:
            print('  MODEL %-28s idx=%-6d meshes=%-3d consumed=%d' % (
                b[1], getattr(o, 'index', -1), getattr(o, 'meshCount', -1), b[4]))

    for b in blocks:
        o = b[5]
        if not o:
            continue
        if o.type == 'Texture':
            print('  TEX   %-28s idx=%-6d clut=%-6s type=%-3s dataSize=%s' % (
                b[1], o.index, getattr(o, 'clutIndex', None),
                getattr(o, 'textureType', None), getattr(o, 'textureDataSize', None)))
        elif o.type == 'Clut':
            print('  CLT   %-28s idx=%-6d colors=%s' % (
                b[1], o.index, getattr(o, 'colorCount', None)))

    small = [b[1] for b in blocks
             if b[5] and b[5].type == 'Model' and 'body' not in b[1]
             and 'shadow' not in b[1] and b[5].meshCount > 0]
    print('  meshed small models (eyes/mouth/weapon):', small)
    empties = [b[1] for b in blocks if b[3] == 28 and b[4] == 28]
    print('  real empty-model templates available:', len(empties))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    for p in sys.argv[1:]:
        dump(p)
