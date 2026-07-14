from pathlib import Path


def patch(path, old, new):
    p = Path(path)
    if not p.exists():
        print("Skip", path)
        return

    text = p.read_text()

    if old in text:
        text = text.replace(old, new)
        p.write_text(text)
        print("Patched", path)
    else:
        print("Already patched:", path)


patch(
    "drivers/kernelsu/runtime/ksud_integration.c",
    "copy_to_iter(KERNEL_SU_RC + ksu_rc_pos,",
    "copy_to_iter((void *)(KERNEL_SU_RC + ksu_rc_pos),"
)

patch(
    "drivers/kernelsu/compat/kernel_compat.c",
    "kvfree(p);",
    "kvfree((void *)p);"
)

patch(
    "drivers/kernelsu/selinux/rules.c",
    "#include <uapi/linux/sched/types.h>",
    "#include <linux/sched.h>"
)

# adb_root.c
p = Path("drivers/kernelsu/feature/adb_root.c")
if p.exists():
    text = p.read_text()

    if "#ifndef ALIGN_DOWN" not in text:
        compat = """

#ifndef ALIGN_DOWN
#define ALIGN_DOWN(x, a) ((typeof(x))((x) & ~((typeof(x))(a) - 1)))
#endif

#ifndef ALIGN
#define ALIGN(x, a) __ALIGN_KERNEL((x), (a))
#endif

#ifndef PAGE_ALIGN
#define PAGE_ALIGN(addr) ALIGN(addr, PAGE_SIZE)
#endif

"""

        lines = text.splitlines(True)

        insert = 0
        for i, line in enumerate(lines):
            if line.startswith("#include"):
                insert = i + 1

        lines.insert(insert, compat)
        text = "".join(lines)

    text = text.replace(
        "ALIGN_DOWN(stackp - sizeof(kLdPreload), 8)",
        "((stackp - sizeof(kLdPreload)) & ~7UL)"
    )

    text = text.replace(
        "ALIGN_DOWN(stackp - sizeof(kLdLibraryPath), 8)",
        "((stackp - sizeof(kLdLibraryPath)) & ~7UL)"
    )

    p.write_text(text)
    print("Patched adb_root.c")

# sucompat
p = Path("drivers/kernelsu/core/sucompat.c")
if p.exists():
    text = p.read_text()

    text = text.replace(
        "struct proc_ops",
        "struct file_operations"
    )

    text = text.replace(".proc_open =", ".open =")
    text = text.replace(".proc_read =", ".read =")
    text = text.replace(".proc_write =", ".write =")
    text = text.replace(".proc_lseek =", ".llseek =")
    text = text.replace(".proc_release =", ".release =")

    p.write_text(text)
    print("Patched sucompat.c")

# kvfree_sensitive
p = Path("drivers/kernelsu/compat/kernel_compat.h")
if p.exists():
    text = p.read_text()

    if "kvfree_sensitive" not in text:
        text += """

#ifndef kvfree_sensitive
#define kvfree_sensitive kvfree
#endif
"""
        p.write_text(text)
        print("Patched kernel_compat.h")

print("KernelSU Linux 4.4 compatibility patches applied.")

# ----------------------------------------------------------
# Disable selinux_hide for Linux 4.4
# ----------------------------------------------------------

# 不编译 selinux_hide.o
p = Path("drivers/kernelsu/feature/Makefile")
if p.exists():
    text = p.read_text()

    text = text.replace(
        "obj-y += selinux_hide.o",
        "# obj-y += selinux_hide.o"
    )

    p.write_text(text)
    print("Disabled selinux_hide.o")

# hook_manager.h 提供空实现，避免链接错误
p = Path("drivers/kernelsu/hook/hook_manager.h")
if p.exists():
    text = p.read_text()

    text = text.replace(
        "void ksu_selinux_hide_init(void);",
        """static inline void ksu_selinux_hide_init(void)
{
}
"""
    )

    text = text.replace(
        "void ksu_selinux_hide_exit(void);",
        """static inline void ksu_selinux_hide_exit(void)
{
}
"""
    )

    p.write_text(text)
    print("Patched hook_manager.h")
