# PS3 Stats

PS3 Stats is a read-only homebrew app for the XMB. It refreshes the CELL and RSX temperatures and free internal storage every second. Press **Circle** to exit. A missing or invalid measurement appears as **Unavailable**.

The first hardware test target is **CFW 4.93**. The app reads the temperatures directly and does not require webMAN MOD. It does not read fan speed, alter fan settings, or open a network connection.

## Build

With a PS3DEV toolchain and PSL1GHT installed, set `PS3DEV` and `PSL1GHT` to the toolchain and SDK directories. Run `make -C ps3-stats` from the repository root. The PSL1GHT build generates `PS3_Stats.pkg` and `PS3_Stats.gnpdrm.pkg`.

## Install and check

Download `PS3_Stats.pkg` from the repository’s Releases (the finalized CFW package), or use your local build’s `PS3_Stats.gnpdrm.pkg`. Copy it to a USB drive and install it through **Game → Package Manager → Install Package Files** on your CFW console. Start **PS3 Stats** from the Game column. Check that both temperature readings appear, compare free space with **Settings → System Settings → System Information**, and confirm that Circle returns you to the XMB. Free space is reported in GiB and may be rounded differently by the XMB.

The build can be verified on a workstation. Installation and temperature readings need confirmation on a physical CFW 4.93 console.
