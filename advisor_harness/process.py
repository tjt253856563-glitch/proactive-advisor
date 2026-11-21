"""Bounded subprocesses and a fail-closed Linux test sandbox."""

import ctypes
import errno
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .evidence import contains_secret, redact
from .policy import Blocked

OUTPUT_LIMIT = 32 * 1024
_WINDOWS_ROOT = Path(os.environ.get("SystemRoot", r"C:\Windows"))


def terminate(process):
    if os.name == "nt":
        try:
            subprocess.run(
                [str(_WINDOWS_ROOT / "System32" / "taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def capture(argv, *, cwd, env, deadline, guard, stdin=None, pass_fds=(), scrub=True, on_start=None):
    guard()
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt" else {"start_new_session": True, "pass_fds": pass_fds}
    )
    started = time.monotonic()
    with tempfile.TemporaryFile() as input_file:
        if stdin is not None:
            input_file.write(stdin)
            input_file.seek(0)
        with subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=input_file if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options,
        ) as process:
            if on_start is not None:
                try:
                    on_start()
                except BaseException:
                    terminate(process)
                    raise
            buffers = {"stdout": bytearray(), "stderr": bytearray()}
            truncated = set()

            def read(name, stream):
                while chunk := stream.read1(8192):
                    room = OUTPUT_LIMIT - len(buffers[name])
                    if len(chunk) > room:
                        truncated.add(name)
                    buffers[name].extend(chunk[:room])

            readers = [
                threading.Thread(target=read, args=(name, getattr(process, name)), daemon=True)
                for name in buffers
            ]
            for reader in readers:
                reader.start()
            timed_out = False
            try:
                while process.poll() is None or any(reader.is_alive() for reader in readers):
                    guard()
                    if time.monotonic() >= deadline:
                        timed_out = True
                        terminate(process)
                        break
                    time.sleep(0.025)
            except BaseException:
                terminate(process)
                raise
            finally:
                if os.name != "nt" and process.poll() is not None:
                    terminate(process)
                for reader in readers:
                    reader.join(timeout=1)
            transform = redact if scrub else str
            return {
                "exit_code": process.returncode, "timed_out": timed_out,
                "duration_seconds": round(time.monotonic() - started, 4),
                "truncated": sorted(truncated),
                **{name: transform(data.decode("utf-8", errors="replace")) for name, data in buffers.items()},
            }


@contextmanager
def seccomp_filter():
    try:
        lib = ctypes.CDLL("libseccomp.so.2")
    except OSError as exc:
        raise Blocked("Linux isolated mode needs libseccomp.so.2") from exc
    lib.seccomp_init.argtypes = (ctypes.c_uint32,)
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = (ctypes.c_char_p,)
    lib.seccomp_rule_add.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint)
    lib.seccomp_export_bpf.argtypes = (ctypes.c_void_p, ctypes.c_int)
    lib.seccomp_release.argtypes = (ctypes.c_void_p,)
    context = lib.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not context:
        raise Blocked("Cannot initialize the Linux syscall filter")
    try:
        for name in (
            b"socket", b"socketpair", b"socketcall", b"io_uring_setup", b"ptrace",
            b"process_vm_readv", b"process_vm_writev", b"pidfd_getfd", b"open_by_handle_at",
            b"fork", b"vfork", b"clone", b"clone3",
        ):
            number = lib.seccomp_syscall_resolve_name(name)
            if number >= 0 and lib.seccomp_rule_add(context, 0x00050000 | errno.EPERM, number, 0) != 0:
                raise Blocked("Cannot install required Linux syscall filter rule")
        with tempfile.TemporaryFile() as stream:
            if lib.seccomp_export_bpf(context, stream.fileno()) != 0:
                raise Blocked("Cannot compile the Linux syscall filter")
            stream.seek(0)
            yield stream.fileno()
    finally:
        lib.seccomp_release(context)


def command_environment():
    env = {
        "PATH": os.defpath, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    if os.name == "nt":
        env["SystemRoot"] = str(_WINDOWS_ROOT)
    return env


def run_test(policy, check, *, trusted, deadline, guard, on_start=None):
    argv = check["argv"][:]
    if check.get("execution", "isolated") == "trusted":
        if not trusted:
            raise Blocked("Trusted command needs the operator's --allow-trusted-tests flag")
        if argv[0] == "{python}":
            argv[0] = sys.executable
        elif not Path(argv[0]).is_absolute():
            raise Blocked("Trusted program must be an absolute executable path")
        if os.name == "nt" and Path(argv[0]).suffix.lower() != ".exe":
            raise Blocked("Trusted Windows program must be an executable, excluding shell scripts")
        return capture(argv, cwd=policy.root, env=command_environment(), deadline=deadline, guard=guard, on_start=on_start)

    required = ["/usr/bin/bwrap", "/usr/bin/prlimit"]
    if sys.platform != "linux" or not all(Path(path).is_file() for path in required):
        raise Blocked("Isolated tests need Linux/WSL with bubblewrap, prlimit and libseccomp")
    if argv[0] == "{python}":
        argv[0] = "/usr/bin/python3"
    if not argv[0].startswith("/usr/bin/") or Path(argv[0]).parent != Path("/usr/bin"):
        raise Blocked("Isolated executable must be under /usr/bin")
    with tempfile.TemporaryDirectory(prefix="advisor-test-") as temp, seccomp_filter() as fd:
        fixture = Path(temp) / "work"
        fixture.mkdir()
        for name in policy.files:
            guard()
            data = policy.read(name)
            if data is not None:
                try:
                    sensitive = contains_secret(data)
                except UnicodeDecodeError as exc:
                    raise Blocked("Isolated project inputs must be UTF-8 text") from exc
                if sensitive:
                    raise Blocked("Credential-like content cannot be copied into a test run")
                target = fixture / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        launcher = [
            required[0], "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--die-with-parent",
            "--cap-drop", "ALL", "--clearenv", "--setenv", "PATH", "/usr/bin",
            "--setenv", "PYTHONUTF8", "1", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--setenv", "TMPDIR", "/tmp", "--ro-bind", "/usr", "/usr",
        ]
        for path in ("/lib", "/lib64", "/bin"):
            if Path(path).exists():
                launcher.extend(("--ro-bind", path, path))
        launcher.extend([
            "--proc", "/proc", "--dev", "/dev", "--size", str(32 * 1024 * 1024), "--tmpfs", "/tmp",
            "--ro-bind", str(fixture), "/work", "--chdir", "/work", "--seccomp", str(fd),
            "--", required[1], "--nofile=64:64", "--fsize=4194304:4194304",
            "--as=1073741824:1073741824", "--core=0:0", "--", *argv,
        ])
        outcome = capture(
            launcher, cwd=fixture, env=command_environment(), deadline=deadline, guard=guard,
            pass_fds=(fd,), on_start=on_start,
        )
        if outcome["stderr"].startswith(("bwrap:", "prlimit:")):
            raise Blocked("Sandbox launch failed: " + outcome["stderr"][:500])
        return outcome
