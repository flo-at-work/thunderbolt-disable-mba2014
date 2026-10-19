#!/usr/bin/env python3
# Reproduces the "non-Darwin" (DTLK) sequence from the DSDT to disable Thunderbolt.
import os, subprocess, sys, time

DRY = "--dry" in sys.argv
ROOT = "00:1c.4"
CHAIN = ["0000:07:00.0", "0000:06:06.0", "0000:06:05.0", "0000:06:04.0",
         "0000:06:03.0", "0000:06:00.0", "0000:05:00.0"]

def sh(*a):
    return subprocess.check_output(a).decode().strip()

# Safeguard: only on a MacBook Air
prod = open("/sys/class/dmi/id/product_name").read().strip()
if not prod.startswith("MacBookAir"):
    sys.exit(f"Unexpected machine ({prod}), aborting.")

base = int(sh("setpci", "-s", "00:1f.0", "48.l"), 16) & 0xFF80
port = base + 0x100 + 8 * 47          # GPIO47 register

def rd():
    with open("/dev/port", "rb", buffering=0) as f:
        f.seek(port)
        return bytearray(f.read(4))

def wr(off, val):
    if DRY:
        return
    with open("/dev/port", "r+b", buffering=0) as f:
        f.seek(port + off)
        f.write(bytes([val]))

b = rd()
print("GPIO47 before :", hex(int.from_bytes(b, "little")))
if not (b[0] & 0x04):
    sys.exit("GD47 is already at 0 : nothing to do.")

# 1. remove the chain from the PCI bus (children first)
for d in CHAIN:
    p = f"/sys/bus/pci/devices/{d}/remove"
    if os.path.exists(p):
        print("remove", d)
        if not DRY:
            open(p, "w").write("1")

# 2. disable the root port link (Link Disable = bit 4)
v = int(sh("setpci", "-s", ROOT, "CAP_EXP+10.w"), 16)
print("LnkCtl", hex(v), "->", hex(v | 0x10))
if not DRY:
    subprocess.check_call(["setpci", "-s", ROOT, f"CAP_EXP+10.w={v | 0x10:04x}"])

# 3. same waiting than AML (2 s), then 4. GP47 = 0 then GD47 = 0
time.sleep(0.2 if DRY else 2.0)
wr(3, b[3] & 0x3F)    # GP47 = 0 (bit 31), bit 30 ignore
wr(0, b[0] & ~0x04)   # GD47 = 0 (bit 2)

print("GPIO47 after :", hex(int.from_bytes(rd(), "little")))
