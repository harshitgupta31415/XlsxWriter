from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class RotatingCores:
    """Allow two physical CPU cores at a time; rotate between paired runs."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("This core-rotation implementation is for Windows.")

        class ProcessorInfo(ctypes.Structure):
            _fields_ = [
                ("mask", ctypes.c_size_t),
                ("relationship", wintypes.DWORD),
                ("reserved", ctypes.c_ulonglong * 2),
            ]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        self.process = self.kernel.GetCurrentProcess()
        self.kernel.GetProcessAffinityMask.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel.SetProcessAffinityMask.argtypes = [
            wintypes.HANDLE,
            ctypes.c_size_t,
        ]
        allowed, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not self.kernel.GetProcessAffinityMask(
            self.process, ctypes.byref(allowed), ctypes.byref(system)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        self.original = allowed.value

        size = wintypes.DWORD()
        self.kernel.GetLogicalProcessorInformation(None, ctypes.byref(size))
        entries = (ProcessorInfo * (size.value // ctypes.sizeof(ProcessorInfo)))()
        if not self.kernel.GetLogicalProcessorInformation(entries, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        cores = [
            entry.mask & self.original
            for entry in entries
            if entry.relationship == 0 and entry.mask & self.original
        ]
        if len(cores) < 2:
            raise RuntimeError("At least two available physical cores are required.")
        self.pairs = [
            cores[i] | cores[(i + 1) % len(cores)] for i in range(0, len(cores), 2)
        ]
        self.index = 0

    def rotate(self) -> str:
        mask = self.pairs[self.index % len(self.pairs)]
        self.index += 1
        if not self.kernel.SetProcessAffinityMask(self.process, mask):
            raise ctypes.WinError(ctypes.get_last_error())
        return f"0x{mask:x}"

    def restore(self) -> None:
        if not self.kernel.SetProcessAffinityMask(self.process, self.original):
            raise ctypes.WinError(ctypes.get_last_error())
