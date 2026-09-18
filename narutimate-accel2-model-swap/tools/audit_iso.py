# -*- coding: utf-8 -*-
"""audit_iso.py — prove a MOD image differs from the original ONLY where intended.

Compares two images sector by sector and prints every changed range, flagging any
offset that is not in the expected list.

Usage:
    python audit_iso.py --orig "<original.iso>" --mod "<mod.iso>" \
        --expect 523796480 --expect 557148160 --expect 596221952

Expected offsets are the outer offsets computed as (CVM_LBA + 3 + innerLBA) * 2048.
"""
import argparse
import os


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--orig', required=True)
    ap.add_argument('--mod', required=True)
    ap.add_argument('--sector', type=int, default=2048)
    ap.add_argument('--expect', type=int, action='append', default=[])
    return ap.parse_args()


def main():
    a = parse_args()
    chunk = 4 << 20
    f = open(a.orig, 'rb')
    g = open(a.mod, 'rb')
    off = 0
    cur = None
    ranges = []
    while True:
        x = f.read(chunk)
        y = g.read(chunk)
        if not x:
            break
        if len(x) != len(y):
            print('!! size mismatch near offset', off)
            break
        for i in range(0, len(x) - len(x) % a.sector, a.sector):
            if x[i:i + a.sector] != y[i:i + a.sector]:
                if cur is None:
                    cur = off + i
            elif cur is not None:
                ranges.append((cur, off + i - cur))
                cur = None
        off += len(x)
    if cur is not None:
        ranges.append((cur, off - cur))
    f.close()
    g.close()

    print('mod size: %d  (orig %d)' % (os.path.getsize(a.mod), os.path.getsize(a.orig)))
    print('changed spans: %d' % len(ranges))
    ok = True
    for st, ln in ranges:
        tag = 'expected' if st in a.expect else '!! UNEXPECTED'
        if st not in a.expect:
            ok = False
        print('  offset=%-12d len=%-9d (%6.1f KB)  %s' % (st, ln, ln / 1024.0, tag))
    for e in a.expect:
        if not any(st == e for st, _ in ranges):
            print('  !! expected span %d was NOT changed' % e)
            ok = False
    print('RESULT:', 'OK (only intended spans differ)' if ok else 'CHECK ABOVE')


if __name__ == '__main__':
    main()
