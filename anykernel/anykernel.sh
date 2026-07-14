### AnyKernel3 Ramdisk Mod Script
## osm0sis @ xda-developers

### AnyKernel setup
# global properties
properties() { '
kernel.string=chiron KernelSU-Next (manual hook) by CI
kernel.compiler=Clang
do.devicecheck=1
do.modules=0
do.systemless=1
do.cleanup=1
do.cleanuponabort=0
device.name1=chiron
device.name2=
device.name3=
device.name4=
device.name5=
supported.versions=
supported.patchlevels=
supported.vendorpatchlevels=
'; } # end properties


### AnyKernel install
## boot files attributes
boot_attributes() {
set_perm_recursive 0 0 755 644 $RAMDISK/*;
set_perm_recursive 0 0 750 750 $RAMDISK/init* $RAMDISK/sbin;
} # end attributes

# boot shell variables
# chiron 是单 slot(A-only)老设备,没有 A/B 分区、没有 vendor_boot/init_boot,
# 只有单一 boot 分区,直接用 "boot" 别名让 ak3-core.sh 自动定位分区。
BLOCK=boot;
IS_SLOT_DEVICE=0;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=auto;

# import functions/variables and setup patching - see for reference (DO NOT REMOVE)
. tools/ak3-core.sh;

# boot install
dump_boot;

# 手动 hook 方式的 KernelSU-Next 不需要额外的 ramdisk 改动,
# 新内核里已经包含了 syscall hook,直接重新打包 boot.img 即可。

write_boot;
## end boot install
