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
git clone https://github.com/libffi/libffi.git .ios-build/libffi
# 3.5.0 includes upstream Mach-O CFI fixes needed by Xcode 16.4 (PR #857).
git -C .ios-build/libffi checkout --detach d2c78d2ebbd9e65401095c6a2f281fe5132f028b
(
  cd .ios-build/libffi
  ./autogen.sh
  CC="xcrun --sdk iphoneos clang" CFLAGS="-target arm64-apple-ios17.0 -isysroot $sdk -fPIC" \
    LDFLAGS="-target arm64-apple-ios17.0 -isysroot $sdk" \
    ./configure --host=aarch64-apple-darwin --prefix="$prefix" --disable-shared --enable-static --disable-docs
  make -j3
  make install
)
git clone https://github.com/utmapp/libucontext.git .ios-build/libucontext
git -C .ios-build/libucontext checkout --detach 9b1d8f01a6e99166f9808c79966abe10786de8b6
meson setup .ios-build/ucontext-build .ios-build/libucontext \
  --cross-file .ios-build/cross.ini --prefix "$prefix" --default-library static -Dfreestanding=true
ninja -C .ios-build/ucontext-build install
# Static dependencies simplify signing: the only shipped binary is our framework.
meson setup .ios-build/glib-build .ios-build/glib-2.82.5 \
  --cross-file .ios-build/cross.ini --prefix "$prefix" --default-library static \
  -Dtests=false -Dinstalled_tests=false -Dintrospection=disabled \
  -Ddocumentation=false -Dman-pages=disabled -Dnls=disabled \
  -Dlibmount=disabled -Dselinux=disabled -Ddtrace=false -Dsystemtap=false
ninja -C .ios-build/glib-build install
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig"
export PKG_CONFIG_PATH="$PKG_CONFIG_LIBDIR"
python3 Tools/patch_qemu_ios.py .qemu
for mode in tci jit; do
name=Podium7QEMU
directory=build-ios
flags=(--enable-tcg-interpreter)
define=''
if [[ "$mode" == jit ]]; then
  name=Podium7QEMUJIT
  directory=build-ios-jit
  flags=(--disable-tcg-interpreter)
  define='-DPODIUM7_IOS_JIT=1'
fi
mkdir -p ".qemu/$directory"
cd ".qemu/$directory"
../configure --python="$(command -v python3)" --cpu=aarch64 --cross-prefix= --host-cc=clang \
  --cc="xcrun --sdk iphoneos clang" --cxx="xcrun --sdk iphoneos clang++" \
  --extra-cflags="-target arm64-apple-ios17.0 -isysroot $sdk -DPODIUM7_IOS=1 $define -I$prefix/include -Werror=unguarded-availability-new" \
  --extra-ldflags="-target arm64-apple-ios17.0 -isysroot $sdk -L$prefix/lib -lucontext" \
  --target-list=aarch64-softmmu --without-default-features --enable-tcg \
  "${flags[@]}" --enable-fdt --disable-pixman --disable-tools \
  --disable-docs --disable-guest-agent --disable-hvf --disable-cocoa \
  --disable-vnc --disable-sdl --disable-gtk --disable-curses --disable-slirp \
  --with-coroutine=ucontext
ninja libPodium7QEMU.dylib
cd "$repo"
framework="build-ios/$name.framework"
mkdir -p "$framework/Licenses"
cp ".qemu/$directory/libPodium7QEMU.dylib" "$framework/$name"
cp .qemu/COPYING "$framework/Licenses/QEMU-GPL.txt"
cp .ios-build/glib-2.82.5/COPYING "$framework/Licenses/GLib.txt"
install_name_tool -id "@rpath/$name.framework/$name" "$framework/$name"
python3 - "$name" <<'PY'
import pathlib, plistlib, sys
name = sys.argv[1]
plist = {'CFBundleExecutable': name, 'CFBundleIdentifier': 'com.catyuragame.podium7.' + name.lower(),
         'CFBundleName': name, 'CFBundlePackageType': 'FMWK',
         'CFBundleVersion': '1', 'CFBundleShortVersionString': '0.0.2', 'MinimumOSVersion': '17.0'}
pathlib.Path('build-ios', name + '.framework', 'Info.plist').write_bytes(plistlib.dumps(plist))
PY
xcrun vtool -show-build "$framework/$name"
otool -L "$framework/$name"
# A macOS dependency in an iOS dylib is a hard error, never silently packaged.
if otool -L "$framework/$name" | grep -E '/opt/homebrew|/usr/local|\.ios-deps'; then
  echo 'Non-system dependency leaked into iOS framework' >&2; exit 1
fi
done
