"""Identify mounted removable Windows volumes by serial number."""
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class RemovableDrive:
    serial: str
    label: str
    root: Path


def removable_drives():
    if os.name != 'nt':
        return []
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetLogicalDrives.restype = wintypes.DWORD
    kernel.GetDriveTypeW.argtypes = (wintypes.LPCWSTR,)
    kernel.GetDriveTypeW.restype = wintypes.UINT
    kernel.GetVolumeInformationW.argtypes = (
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
    )
    kernel.GetVolumeInformationW.restype = wintypes.BOOL
    mask = kernel.GetLogicalDrives()
    drives = []
    for index, letter in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
        if not mask & (1 << index):
            continue
        root = letter + ':\\'
        if kernel.GetDriveTypeW(root) != 2:  # DRIVE_REMOVABLE
            continue
        label = ctypes.create_unicode_buffer(261)
        serial = wintypes.DWORD()
        if kernel.GetVolumeInformationW(root, label, len(label), ctypes.byref(serial), None, None, None, 0):
            drives.append(RemovableDrive(f'{serial.value:08X}', label.value or 'Removable drive', Path(root)))
    return drives


def remembered_drive(preference, drives):
    serial = preference.get('serial')
    matches = [drive for drive in drives if drive.serial == serial]
    return matches[0] if len(matches) == 1 else None
