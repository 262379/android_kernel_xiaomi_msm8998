#!/usr/bin/env python3
"""
KernelSU-Next manual hook patcher for non-GKI kernels (msm8998 / chiron, Linux 4.4).

依据: https://kernelsu-next.github.io/webpage/zh_CN/pages/how-to-integrate-for-non-gki.html
      "手动修改内核源码" 一节的 5 个补丁点,并针对本仓库(LineageOS lineage-22.2,
      CONFIG_COMPAT=y)额外补上 compat_do_execve / compat_do_execveat 两个 hook。

用法:
    python3 ksu_manual_patch.py <kernel_dir> <defconfig_path>

脚本使用正则按函数签名定位插入点,幂等 —— 重复运行不会重复插入。
"""

import re
import sys
import pathlib

MARKER = "KSU_MANUAL_HOOK_PATCH_APPLIED"


def already_patched(text: str) -> bool:
    return MARKER in text


def patch_exec_c(path: pathlib.Path) -> bool:
    text = path.read_text()
    if already_patched(text):
        print(f"[skip] {path} already patched")
        return False

    # 1) extern 声明 + do_execve hook
    pattern_do_execve = re.compile(
        r"(int do_execve\(struct filename \*filename,\n"
        r"\tconst char __user \*const __user \*__argv,\n"
        r"\tconst char __user \*const __user \*__envp\)\n"
        r"\{\n"
        r"\tstruct user_arg_ptr argv = \{ \.ptr\.native = __argv \};\n"
        r"\tstruct user_arg_ptr envp = \{ \.ptr\.native = __envp \};\n)"
        r"(\treturn do_execveat_common\(AT_FDCWD, filename, argv, envp, 0\);\n\})"
    )
    externs = (
        f"/* {MARKER} */\n"
        "#ifdef CONFIG_KSU\n"
        "__attribute__((hot))\n"
        "extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr,\n"
        "\t\t\t\tvoid *argv, void *envp, int *flags);\n"
        "#endif\n\n"
    )

    def _do_execve_repl(m):
        body, ret = m.group(1), m.group(2)
        return (
            body
            + "#ifdef CONFIG_KSU\n"
            "\tksu_handle_execveat((int *)AT_FDCWD, &filename, &argv, &envp, 0);\n"
            "#endif\n"
            + ret
        )

    new_text, n1 = pattern_do_execve.subn(_do_execve_repl, text)
    if n1 != 1:
        print(f"[fail] {path}: do_execve pattern matched {n1} times, expected 1")
        return False

    # 插入 extern 声明在 do_execve 定义之前
    new_text = new_text.replace(
        "int do_execve(struct filename *filename,",
        externs + "int do_execve(struct filename *filename,",
        1,
    )

    # 2) compat_do_execve hook (CONFIG_COMPAT=y 时需要)
    pattern_compat_execve = re.compile(
        r"(static int compat_do_execve\(struct filename \*filename,\n"
        r"\tconst compat_uptr_t __user \*__argv,\n"
        r"\tconst compat_uptr_t __user \*__envp\)\n"
        r"\{\n"
        r"\tstruct user_arg_ptr argv = \{\n"
        r"\t\t\.is_compat = true,\n"
        r"\t\t\.ptr\.compat = __argv,\n"
        r"\t\};\n"
        r"\tstruct user_arg_ptr envp = \{\n"
        r"\t\t\.is_compat = true,\n"
        r"\t\t\.ptr\.compat = __envp,\n"
        r"\t\};\n)"
        r"(\treturn do_execveat_common\(AT_FDCWD, filename, argv, envp, 0\);\n\})"
    )

    def _compat_execve_repl(m):
        return (
            m.group(1)
            + "#ifdef CONFIG_KSU // 32-bit ksud and 32-on-64 support\n"
            "\tksu_handle_execveat((int *)AT_FDCWD, &filename, &argv, &envp, 0);\n"
            "#endif\n"
            + m.group(2)
        )

    new_text, n2 = pattern_compat_execve.subn(_compat_execve_repl, new_text)
    if n2 != 1:
        print(f"[fail] {path}: compat_do_execve pattern matched {n2} times, expected 1")
        return False

    # 3) compat_do_execveat hook
    pattern_compat_execveat = re.compile(
        r"(static int compat_do_execveat\(int fd, struct filename \*filename,\n"
        r"\t\t\t      const compat_uptr_t __user \*__argv,\n"
        r"\t\t\t      const compat_uptr_t __user \*__envp,\n"
        r"\t\t\t      int flags\)\n"
        r"\{\n"
        r"\tstruct user_arg_ptr argv = \{\n"
        r"\t\t\.is_compat = true,\n"
        r"\t\t\.ptr\.compat = __argv,\n"
        r"\t\};\n"
        r"\tstruct user_arg_ptr envp = \{\n"
        r"\t\t\.is_compat = true,\n"
        r"\t\t\.ptr\.compat = __envp,\n"
        r"\t\};\n)"
        r"(\treturn do_execveat_common\(fd, filename, argv, envp, flags\);\n\})"
    )

    def _compat_execveat_repl(m):
        return (
            m.group(1)
            + "#ifdef CONFIG_KSU\n"
            "\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);\n"
            "#endif\n"
            + m.group(2)
        )

    new_text, n3 = pattern_compat_execveat.subn(_compat_execveat_repl, new_text)
    if n3 != 1:
        print(f"[fail] {path}: compat_do_execveat pattern matched {n3} times, expected 1")
        return False

    path.write_text(new_text)
    print(f"[ok] {path}: patched do_execve + compat_do_execve + compat_do_execveat")
    return True


def patch_open_c(path: pathlib.Path) -> bool:
    text = path.read_text()
    if already_patched(text):
        print(f"[skip] {path} already patched")
        return False

    pattern = re.compile(
        r"(SYSCALL_DEFINE3\(faccessat, int, dfd, const char __user \*, filename, int, mode\)\n"
        r"\{\n"
        r"\tconst struct cred \*old_cred;\n"
        r"\tstruct cred \*override_cred;\n"
        r"\tstruct path path;\n"
        r"\tstruct inode \*inode;\n"
        r"\tstruct vfsmount \*mnt;\n"
        r"\tint res;\n"
        r"\tunsigned int lookup_flags = LOOKUP_FOLLOW;\n\n)"
        r"(\tif \(mode & ~S_IRWXO\))"
    )

    externs = (
        f"/* {MARKER} */\n"
        "#ifdef CONFIG_KSU\n"
        "__attribute__((hot))\n"
        "extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,\n"
        "\t\t\t\tint *mode, int *flags);\n"
        "#endif\n\n"
    )

    def _repl(m):
        return (
            m.group(1)
            + "#ifdef CONFIG_KSU\n"
            "\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);\n"
            "#endif\n\n"
            + m.group(2)
        )

    new_text, n = pattern.subn(_repl, text)
    if n != 1:
        print(f"[fail] {path}: faccessat pattern matched {n} times, expected 1")
        return False

    new_text = new_text.replace(
        "SYSCALL_DEFINE3(faccessat, int, dfd,",
        externs + "SYSCALL_DEFINE3(faccessat, int, dfd,",
        1,
    )

    path.write_text(new_text)
    print(f"[ok] {path}: patched faccessat")
    return True


def patch_read_write_c(path: pathlib.Path) -> bool:
    text = path.read_text()
    if already_patched(text):
        print(f"[skip] {path} already patched")
        return False

    pattern = re.compile(
        r"(SYSCALL_DEFINE3\(read, unsigned int, fd, char __user \*, buf, size_t, count\)\n"
        r"\{\n"
        r"\tstruct fd f = fdget_pos\(fd\);\n"
        r"\tssize_t ret = -EBADF;\n\n)"
        r"(\tif \(f\.file\) \{)"
    )

    externs = (
        f"/* {MARKER} */\n"
        "#ifdef CONFIG_KSU\n"
        "extern bool ksu_vfs_read_hook __read_mostly;\n"
        "extern __attribute__((cold)) int ksu_handle_sys_read(unsigned int fd,\n"
        "\t\t\t\tchar __user **buf_ptr, size_t *count_ptr);\n"
        "#endif\n\n"
    )

    def _repl(m):
        return (
            m.group(1)
            + "#ifdef CONFIG_KSU\n"
            "\tif (unlikely(ksu_vfs_read_hook))\n"
            "\t\tksu_handle_sys_read(fd, &buf, &count);\n"
            "#endif\n"
            + m.group(2)
        )

    new_text, n = pattern.subn(_repl, text)
    if n != 1:
        print(f"[fail] {path}: sys_read pattern matched {n} times, expected 1")
        return False

    new_text = new_text.replace(
        "SYSCALL_DEFINE3(read, unsigned int, fd,",
        externs + "SYSCALL_DEFINE3(read, unsigned int, fd,",
        1,
    )

    path.write_text(new_text)
    print(f"[ok] {path}: patched sys_read")
    return True


def patch_stat_c(path: pathlib.Path) -> bool:
    text = path.read_text()
    if already_patched(text):
        print(f"[skip] {path} already patched")
        return False

    pattern = re.compile(
        r"(SYSCALL_DEFINE4\(newfstatat, int, dfd, const char __user \*, filename,\n"
        r"\t\tstruct stat __user \*, statbuf, int, flag\)\n"
        r"\{\n"
        r"\tstruct kstat stat;\n"
        r"\tint error;\n\n)"
        r"(\terror = vfs_fstatat\(dfd, filename, &stat, flag\);)"
    )

    externs = (
        f"/* {MARKER} */\n"
        "#ifdef CONFIG_KSU\n"
        "__attribute__((hot))\n"
        "extern int ksu_handle_stat(int *dfd, const char __user **filename_user,\n"
        "\t\t\t\tint *flags);\n"
        "#endif\n\n"
    )

    def _repl(m):
        return (
            m.group(1)
            + "#ifdef CONFIG_KSU\n"
            "\tksu_handle_stat(&dfd, &filename, &flag);\n"
            "#endif\n"
            + m.group(2)
        )

    new_text, n = pattern.subn(_repl, text)
    if n != 1:
        print(f"[fail] {path}: newfstatat pattern matched {n} times, expected 1")
        return False

    new_text = new_text.replace(
        "SYSCALL_DEFINE4(newfstatat, int, dfd,",
        externs + "SYSCALL_DEFINE4(newfstatat, int, dfd,",
        1,
    )

    path.write_text(new_text)
    print(f"[ok] {path}: patched newfstatat")
    return True


def patch_reboot_c(path: pathlib.Path) -> bool:
    text = path.read_text()
    if already_patched(text):
        print(f"[skip] {path} already patched")
        return False

    pattern = re.compile(
        r"(SYSCALL_DEFINE4\(reboot, int, magic1, int, magic2, unsigned int, cmd,\n"
        r"\t\tvoid __user \*, arg\)\n"
        r"\{\n"
        r"\tstruct pid_namespace \*pid_ns = task_active_pid_ns\(current\);\n"
        r"\tchar buffer\[256\];\n"
        r"\tint ret = 0;\n\n)"
        r"(\t/\* We only trust the superuser with rebooting the system\. \*/)"
    )

    externs = (
        f"/* {MARKER} */\n"
        "#ifdef CONFIG_KSU\n"
        "extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd,\n"
        "\t\t\t\tvoid __user **arg);\n"
        "#endif\n\n"
    )

    def _repl(m):
        return (
            m.group(1)
            + "#ifdef CONFIG_KSU\n"
            "\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);\n"
            "#endif\n"
            + m.group(2)
        )

    new_text, n = pattern.subn(_repl, text)
    if n != 1:
        print(f"[fail] {path}: reboot pattern matched {n} times, expected 1")
        return False

    new_text = new_text.replace(
        "SYSCALL_DEFINE4(reboot, int, magic1,",
        externs + "SYSCALL_DEFINE4(reboot, int, magic1,",
        1,
    )

    path.write_text(new_text)
    print(f"[ok] {path}: patched sys_reboot")
    return True


def patch_defconfig(path: pathlib.Path) -> bool:
    text = path.read_text()
    if "CONFIG_KSU=y" in text:
        print(f"[skip] {path} already has CONFIG_KSU")
        return False

    block = (
        "\n# KernelSU Next (manual hooks, non-GKI / non-kprobe)\n"
        "CONFIG_KSU=y\n"
        "CONFIG_KSU_MANUAL_HOOK=y\n"
        "# CONFIG_KSU_KPROBE_HOOKS is not set\n"
    )
    if not text.endswith("\n"):
        text += "\n"
    text += block
    path.write_text(text)
    print(f"[ok] {path}: appended CONFIG_KSU=y / CONFIG_KSU_MANUAL_HOOK=y")
    return True


def main():
    if len(sys.argv) != 3:
        print("usage: ksu_manual_patch.py <kernel_dir> <defconfig_path>")
        sys.exit(1)

    kernel_dir = pathlib.Path(sys.argv[1])
    defconfig = pathlib.Path(sys.argv[2])

    targets = [
        (patch_exec_c, kernel_dir / "fs" / "exec.c"),
        (patch_open_c, kernel_dir / "fs" / "open.c"),
        (patch_read_write_c, kernel_dir / "fs" / "read_write.c"),
        (patch_stat_c, kernel_dir / "fs" / "stat.c"),
        (patch_reboot_c, kernel_dir / "kernel" / "reboot.c"),
    ]

    failed = False
    for fn, p in targets:
        if not p.exists():
            print(f"[fail] {p} does not exist")
            failed = True
            continue
        try:
            fn(p)
        except Exception as e:
            print(f"[fail] {p}: {e}")
            failed = True

    if not defconfig.exists():
        print(f"[fail] defconfig {defconfig} does not exist")
        failed = True
    else:
        patch_defconfig(defconfig)

    if failed:
        print("\nSome patches failed — the kernel source may differ from the "
              "expected context. Check the printed [fail] lines and adjust "
              "the regex patterns in this script to match your tree.")
        sys.exit(1)

    print("\nAll manual hooks applied successfully.")


if __name__ == "__main__":
    main()
