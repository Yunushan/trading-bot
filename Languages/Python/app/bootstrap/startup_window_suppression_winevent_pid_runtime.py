from __future__ import annotations


class TrackedPidRegistry:
    def __init__(self, api, root_pid: int):
        self.api = api
        self.root_pid = int(root_pid)
        self.lock = api.threading.Lock()
        self.pids: set[int] = {int(root_pid)}
        self.last_refresh_ts = 0.0

    def _enum_descendant_pids(self, root_pid: int) -> set[int]:
        pids: set[int] = {int(root_pid)}
        if not root_pid:
            return pids
        try:
            TH32CS_SNAPPROCESS = 0x00000002
            snapshot = self.api.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snapshot in (0, self.api.ctypes.c_void_p(-1).value):
                return pids

            class PROCESSENTRY32(self.api.ctypes.Structure):
                _fields_ = [
                    ("dwSize", self.api.wintypes.DWORD),
                    ("cntUsage", self.api.wintypes.DWORD),
                    ("th32ProcessID", self.api.wintypes.DWORD),
                    ("th32DefaultHeapID", self.api.ctypes.c_void_p),
                    ("th32ModuleID", self.api.wintypes.DWORD),
                    ("cntThreads", self.api.wintypes.DWORD),
                    ("th32ParentProcessID", self.api.wintypes.DWORD),
                    ("pcPriClassBase", self.api.wintypes.LONG),
                    ("dwFlags", self.api.wintypes.DWORD),
                    ("szExeFile", self.api.wintypes.WCHAR * 260),
                ]

            parent_to_children: dict[int, list[int]] = {}
            entry = PROCESSENTRY32()
            entry.dwSize = self.api.ctypes.sizeof(entry)
            try:
                if self.api.kernel32.Process32FirstW(snapshot, self.api.ctypes.byref(entry)):
                    while True:
                        child_pid = int(entry.th32ProcessID)
                        parent_pid = int(entry.th32ParentProcessID)
                        parent_to_children.setdefault(parent_pid, []).append(child_pid)
                        if not self.api.kernel32.Process32NextW(snapshot, self.api.ctypes.byref(entry)):
                            break
            finally:
                try:
                    self.api.kernel32.CloseHandle(snapshot)
                except Exception:
                    pass

            queue = [int(root_pid)]
            while queue:
                current = queue.pop()
                for child in parent_to_children.get(current, []):
                    if child not in pids:
                        pids.add(child)
                        queue.append(child)
        except Exception:
            return pids
        return pids

    def refresh(self, *, force: bool = False) -> set[int]:
        now = self.api.time.monotonic()
        with self.lock:
            if not force and (now - float(self.last_refresh_ts)) < 0.2:
                return set(self.pids)
        refreshed = self._enum_descendant_pids(self.root_pid)
        with self.lock:
            self.pids.clear()
            self.pids.update(refreshed)
            self.last_refresh_ts = now
            return set(self.pids)

    def contains(self, pid_val: int) -> bool:
        if not pid_val:
            return False
        with self.lock:
            if pid_val in self.pids:
                return True
        return pid_val in self.refresh(force=False)
