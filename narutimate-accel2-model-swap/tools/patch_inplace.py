# -*- coding: utf-8 -*-
"""patch_inplace.py — write replacement .gz files back into their ORIGINAL
extents inside a copy of the disc image.

NEVER rebuild the CVM: the container is encrypted, and a rebuilt (unencrypted)
volume makes the game blackscreen. Only the ZONE payload bytes are touched.

Usage:
    python patch_inplace.py --orig "<original.iso>" --out "<mod.iso>" \
        --cvm-lba 210454 --cvm-start 3 \
        --span 61588 731530 _extract/replacement_surgical/PL_2KRWBOD1.CCS.gz \
        --span 45303  86983 _extract/replacement_surgical/PL_1KRWBOD1.CCS.gz

Each --span is: <inner LBA> <stored size> <replacement .gz path>
The replacement must compress to <= <stored size>; it is padded with zeros so
the file keeps its original size and the filesystem stays untouched.
"""
import argparse
import gzip
import os
import sys


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--orig', required=True, help='original disc image (baseline)')
    ap.add_argument('--out', required=True, help='output MOD image (created)')
    ap.add_argument('--cvm-lba', type=int, default=210454)
    ap.add_argument('--cvm-start', type=int, default=3)
    ap.add_argument('--span', nargs=3, action='append', metavar=('LBA', 'SIZE', 'GZ'),
                    required=True, help='repeatable: inner LBA, stored size, replacement gz')
    return ap.parse_args()


def main():
    a = parse_args()
    sector = 2048
    prep = []
    for lba_s, size_s, gz_path in a.span:
        lba, size = int(lba_s), int(size_s)
        gz = open(gz_path, 'rb').read()
        if len(gz) > size:
            sys.exit('replacement %s is %d bytes > stored size %d -> cannot patch in place'
                     % (gz_path, len(gz), size))
        off = (a.cvm_lba + a.cvm_start + lba) * sector
        prep.append((off, size, gz, gz_path))
        print('span %-40s offset=%-12d size=%-8d gz=%d' % (gz_path, off, size, len(gz)))

    print('copying baseline image...')
    with open(a.orig, 'rb') as src, open(a.out, 'wb') as dst:
        while True:
            chunk = src.read(16 << 20)
            if not chunk:
                break
            dst.write(chunk)

    with open(a.out, 'r+b') as f:
        for off, size, gz, label in prep:
            f.seek(off)
            f.write(gz + b'\x00' * (size - len(gz)))
            f.flush()
            f.seek(off)
            back = f.read(size)
            assert back[:len(gz)] == gz, 'write-back mismatch ' + label
            assert back[len(gz):] == b'\x00' * (size - len(gz)), 'padding mismatch ' + label
            # also prove the ORIGINAL had this file here (mapping sanity)
            with open(a.orig, 'rb') as o:
                o.seek(off)
                orig_head = o.read(4)
            if orig_head[:2] == b'\x1f\x8b':
                print('  %-40s original signature ok (gzip)' % os.path.basename(label))
            else:
                print('  %-40s WARNING: original bytes are not gzip here!' % os.path.basename(label))
    print('patched ->', a.out, os.path.getsize(a.out))


if __name__ == '__main__':
    main()
