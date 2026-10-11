#!/bin/bash
# Cross-compile dependencies for iPhoneOS. Never link Homebrew's macOS GLib.
set -euo pipefail
repo="$(pwd)"
sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
prefix="$repo/.ios-deps"
mkdir -p "$prefix" .ios-build
curl --fail --location --retry 3 https://download.gnome.org/sources/glib/2.82/glib-2.82.5.tar.xz -o .ios-build/glib.tar.xz
echo '05c2031f9bdf6b5aba7a06ca84f0b4aced28b19bf1b50c6ab25cc675277cbc3f  .ios-build/glib.tar.xz' | shasum -a 256 -c -
tar -xf .ios-build/glib.tar.xz -C .ios-build
cat > .ios-build/cross.ini <<EOF
[binaries]
c = ['xcrun', '--sdk', 'iphoneos', 'clang']
cpp = ['xcrun', '--sdk', 'iphoneos', 'clang++']
ar = ['xcrun', '--sdk', 'iphoneos', 'ar']
strip = ['xcrun', '--sdk', 'iphoneos', 'strip']
pkg-config = 'pkg-config'
[host_machine]
system = 'darwin'
cpu_family = 'aarch64'
cpu = 'aarch64'
endian = 'little'
[properties]
needs_exe_wrapper = true
pkg_config_libdir = ['$prefix/lib/pkgconfig']
[built-in options]
c_args = ['-target', 'arm64-apple-ios17.0', '-isysroot', '$sdk']
cpp_args = ['-target', 'arm64-apple-ios17.0', '-isysroot', '$sdk']
c_link_args = ['-target', 'arm64-apple-ios17.0', '-isysroot', '$sdk']
cpp_link_args = ['-target', 'arm64-apple-ios17.0', '-isysroot', '$sdk']
b_staticpic = true
EOF
# Static dependencies simplify signing: the only shipped binary is our framework.
meson setup .ios-build/glib-build .ios-build/glib-2.82.5 \
  --cross-file .ios-build/cross.ini --prefix "$prefix" --default-library static \
  -Dtests=false -Dinstalled_tests=false -Dintrospection=disabled \
  -Ddocumentation=false -Dman-pages=disabled -Dnls=disabled \
  -Dlibmount=disabled -Dselinux=disabled -Ddtrace=false -Dsystemtap=false
ninja -C .ios-build/glib-build install
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig"
export PKG_CONFIG_PATH="$PKG_CONFIG_LIBDIR"
mkdir -p .qemu/build-ios
cd .qemu/build-ios
../configure --python="$(command -v python3)" --cpu=aarch64 \
  --cc="xcrun --sdk iphoneos clang" --cxx="xcrun --sdk iphoneos clang++" \
  --extra-cflags="-target arm64-apple-ios17.0 -isysroot $sdk" \
  --extra-ldflags="-target arm64-apple-ios17.0 -isysroot $sdk" \
  --target-list=aarch64-softmmu --without-default-features --enable-tcg \
  --enable-tcg-interpreter --enable-fdt --disable-pixman --disable-tools \
  --disable-docs --disable-guest-agent --disable-hvf --disable-cocoa \
  --disable-vnc --disable-sdl --disable-gtk --disable-curses --disable-slirp \
  --with-coroutine=ucontext
ninja libPodium7QEMU.dylib
cd "$repo"
mkdir -p build-ios/Podium7QEMU.framework
cp .qemu/build-ios/libPodium7QEMU.dylib build-ios/Podium7QEMU.framework/Podium7QEMU
install_name_tool -id '@rpath/Podium7QEMU.framework/Podium7QEMU' build-ios/Podium7QEMU.framework/Podium7QEMU
python3 - <<'PY'
import pathlib, plistlib
plist = {'CFBundleExecutable': 'Podium7QEMU', 'CFBundleIdentifier': 'com.catyuragame.podium7.qemu',
         'CFBundleName': 'Podium7QEMU', 'CFBundlePackageType': 'FMWK',
         'CFBundleVersion': '1', 'CFBundleShortVersionString': '0.0.2', 'MinimumOSVersion': '17.0'}
pathlib.Path('build-ios/Podium7QEMU.framework/Info.plist').write_bytes(plistlib.dumps(plist))
PY
xcrun vtool -show-build build-ios/Podium7QEMU.framework/Podium7QEMU
otool -L build-ios/Podium7QEMU.framework/Podium7QEMU
# A macOS dependency in an iOS dylib is a hard error, never silently packaged.
if otool -L build-ios/Podium7QEMU.framework/Podium7QEMU | grep -E '/opt/homebrew|/usr/local|\.ios-deps'; then
  echo 'Non-system dependency leaked into iOS framework' >&2; exit 1
fi
