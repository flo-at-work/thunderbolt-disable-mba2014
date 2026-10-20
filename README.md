# Switch off the Thunderbolt controller on a 2014 MacBook Air under Linux, without `acpi_osi=!Darwin`

On a MacBook Air 11" (2014), the Thunderbolt 1 controller (Intel DSL3510 "Cactus Ridge") stays powered under Linux and costs about 1 W at idle. The usual workaround, `acpi_osi=!Darwin`, switches it off, but it also adds about 2 seconds to every resume from S3 and block other good Linux optimizations related to Apple hardware. The other workarounds like modprobe blacklisting or `pcie_ports=compat` kernel flag disable the use of the Thunderbolt but doesn't turn it off.

This repo contains a small script and a systemd unit that give you both: Thunderbolt off **and** the faster resume among with all Linux kernel optimizations for Apple.

> **Status: tested on one machine only** (MacBook Air 11" 2014, CachyOS, LTS kernel). The script writes to hardware registers. Read the [Warnings](#warnings) before using it.

## Results

Measured with PowerTOP on battery, 20 % brightness, WiFi on, nothing plugged in, 5 minutes of idle after login. Single measurements, so expect some noise (a few hundred mW).

| | `acpi_osi=!Darwin` | No flag, no script | No flag + `tb-off` |
|---|---|---|---|
| Idle discharge rate | 4.58 W | 5.54 W | ~4.6 W |
| Thunderbolt chain on the PCI bus | absent | present | absent |
| Kernel resume (`Waking up from S3` → `suspend exit`) | ~2.7 s (2.0 s of silence + ~0.7 s) | ~0.7 s | 0.83 s |

The suspend measurement has a resolution of ±1 point, so it only shows that no difference is visible, not that there is none.

## Why the flag costs 2 seconds, and why Thunderbolt is on without it

I dumped the ACPI tables in both modes: **the DSDT and all SSDTs are byte-identical** with and without `acpi_osi=!Darwin`. The firmware does not hand out different tables. The same AML code takes different branches depending on the `_OSI("Darwin")` answer (the `OSDW()` method).

What I found by disassembling the tables with `iasl`:

- The Thunderbolt power logic lives in `SSDT5`, not in the DSDT.
- In the non-Darwin path, the method `DTLK` (called from `_WAK` on S3 resume) does:
  1. `RP05.LDIS = 1` (disable the root-port link),
  2. `Sleep (0x07D0)` (**2000 ms**, this is the 2 s hole in the resume log),
  3. `GP47 = 0` and `GD47 = 0` (drive GPIO 47 low, which powers the controller off).
- In the Darwin path, nothing powers the controller off. Only macOS's own driver manages it.

So the idea is to replay that sequence from user space instead of letting the AML do it during resume.

## How it works

`tb-off.py` replicates the non-Darwin sequence:

1. Reads the GPIO base from the LPC bridge (`00:1f.0`, config offset `0x48`) and computes the GPIO 47 register address (`base + 0x100 + 8 × 47`).
2. Exits if `GD47` is already 0.
3. Removes the Thunderbolt chain from the PCI bus (children first).
4. Sets the *Link Disable* bit on the root port `00:1c.4`.
5. Waits 2 seconds, like the AML does.
6. Clears `GP47` (bit 31), then `GD47` (bit 2).

On my machine the GPIO 47 register reads `0x40000005` when the controller is powered and `0x00000001` after the sequence. That is the same value I get when booting with `acpi_osi=!Darwin`. My interpretation of the bits (`GD` = direction) is inferred from the AML and the observed values, not from a datasheet. Bit 30 is not named in the DSDT and I ignore it.

The firmware powers the controller back on at every S3 resume (the register returns to `0x40000005`), so the service is also triggered after each suspend target. The 2 s wait now happens after resume, in user space, and does not delay the lock screen.

## Requirements

- A MacBook Air from 2014 with the DSL3510 controller. The script refuses to run if `/sys/class/dmi/id/product_name` does not start with `MacBookAir`.
- Root, `python3`, and `setpci` (package `pciutils`).
- `/dev/port` readable and writable as root (it worked on my kernel; some kernels restrict it).
- **No `acpi_osi=!Darwin` on your kernel command line.** Check with `grep -o 'acpi_osi[^ ]*' /proc/cmdline` (it should print nothing).

## Install

First check that your PCI topology matches. The addresses are hard-coded in the script:

```bash
lspci -tv
```

You should see a Thunderbolt `DSL3510` controller behind root port `00:1c.4`, with the chain `05:00.0`, `06:00.0`, `06:03.0`, `06:04.0`, `06:05.0`, `06:06.0` and `07:00.0`. If yours differs, edit `ROOT` and `CHAIN` in the script.

Dry run first (it reads the registers and prints what it would do, without writing anything):

```bash
sudo python3 tb-off.py --dry
```

Then run it for real:

```bash
sudo python3 tb-off.py
```

Check that the GPIO 47 register is now `0x00000001` and that the chain is gone from `lspci -tv`. Then measure with `powertop` (on battery).

Install the service so it runs at boot and after every suspend:

```bash
sudo install -m 755 tb-off.py /usr/local/bin/tb-off.py
sudo cp tb-off.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tb-off.service
```

### Optional

Blacklist the `thunderbolt` module so that no driver can bind if the chain ever reappears:

```bash
echo "blacklist thunderbolt" | sudo tee /etc/modprobe.d/blacklist-thunderbolt.conf
```

If you use TLP, you do not need to add the Thunderbolt chain to `RUNTIME_PM_ENABLE`: the devices are removed from the bus.

### A pitfall in the unit file

Do not add `After=tlp.service` to the unit. On my system it created an ordering cycle (`tb-off` → `tlp` → `multi-user.target` → `tb-off`), and systemd silently dropped the job. `systemd-analyze verify` catches this.

## Verify

After a reboot, with nothing run by hand:

```bash
journalctl -u tb-off.service -b --no-pager
```

You should see `GPIO47 before : 0x40000005` followed by `GPIO47 after : 0x1`

After a suspend/resume, wait about 5 seconds and check again:

```bash
sudo python3 - <<'EOF'
import subprocess, struct
base = int(subprocess.check_output(['setpci','-s','00:1f.0','48.l']).decode(), 16) & 0xFF80
with open('/dev/port','rb',buffering=0) as f:
    f.seek(base + 0x100 + 8*47)
    print(hex(struct.unpack('<I', f.read(4))[0]))
EOF
```

It should print `0x1`. The journal should show a new run of the service just after the resume.

## Warnings

- **The script writes to hardware registers** (PCH GPIO, PCIe link control). The end state is the one the machine reaches on its own with `acpi_osi=!Darwin`, but I cannot promise it is safe on your unit. You are responsible for what you run.
- It was tested on one MacBook Air only. Other 2013 to 2015 models, or other firmware revisions, may use different GPIOs.
- **Thunderbolt will not work** while the service is active, and neither will any device that depends on the controller. A reboot with the service disabled restores everything (`sudo systemctl disable --now tb-off.service`). There is no hot "undo" sequence.
- Do not run `echo 1 > /sys/bus/pci/rescan` while the Thunderbolt power is off.
- If the machine freezes while the script runs, the likely culprit is the link-disable step with an active device on the chain. Reboot and open an issue.

## Not verified yet

I have not tested these with the service active, so please report what you see:

- A Mini DisplayPort monitor (it works with `acpi_osi=!Darwin`, which suggests the display path does not go through the Thunderbolt controller, but I have not confirmed it with this method).
- Idle power after many suspend/resume cycles.

## Credits and notes

Everything here comes from reading the DSDT/SSDT of my own machine (`acpidump` + `iasl -d`) and from measurements with PowerTOP. The method should apply to any Mac whose AML has the same structure, but I have no data beyond the one machine.
