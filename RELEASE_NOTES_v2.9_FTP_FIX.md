# v2.9 PS3 FTP encoding hotfix

- `PS3FTP.connect()` now configures the standard `ftplib.FTP` connection with `latin-1` before connecting. Some PS3 homebrew FTP implementations return non-UTF-8 bytes in control replies or directory listings (for example byte `0xB0`), which previously caused `Browse failed: utf-8 codec can’t decode byte...`.
- Latin-1 is byte-preserving for 0x00–0xFF; the existing ASCII-only remote path/name validation remains unchanged, so unusual folder names are skipped rather than used in FTP paths.
- Applies to both the background FTP directory browser and save downloads, because both reuse the same connection function.
- No changes to remote files, archive data, icon, dashboard, ISO conversion, homebrew, GitHub or Windows build assets.
- Does not fix errors from permissions, authentication, FTP server responses, or other unsupported encodings. This is not a live-PS3 tested change.
