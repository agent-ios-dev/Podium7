"""Fetch selected Apple IPSW ZIP members with checked HTTP byte ranges.

No full firmware download, credentials, hardware exploit or invented memory map.
"""
import argparse
import hashlib
import io
import json
import pathlib
import plistlib
import urllib.request
import zipfile

URL = "https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-76865/68174A8B-44B2-4689-B8D4-C8F42F4FFBEE/iPodtouch_7_15.8.8_19H422_Restore.ipsw"
SIZE = 5013514038


class RemoteZIP(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.cache = {}
        self.block = 1024 * 1024

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        if position < 0:
            raise ValueError("negative seek")
        self.position = position
        return position

    def read(self, size=-1):
        size = min(size if size >= 0 else self.size - self.position, self.size - self.position)
        if size < 0:
            return b""
        if size > 128 * 1024 * 1024:
            raise ValueError("member exceeds 128 MiB extraction budget")
        parts = []
        while size:
            index, offset = divmod(self.position, self.block)
            if index not in self.cache:
                start, end = index * self.block, min((index + 1) * self.block, self.size) - 1
                request = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{self.size}":
                        raise ValueError("Apple CDN did not honor exact byte range; refusing full ZIP download")
                    data = response.read(end - start + 2)
                    if len(data) != end - start + 1:
                        raise ValueError("truncated/oversized range")
                    self.cache[index] = data
            data = self.cache[index]
            count = min(size, len(data) - offset)
            parts.append(data[offset:offset + count])
            self.position += count
            size -= count
        return b"".join(parts)


def stage(output, url=URL, size=SIZE):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(RemoteZIP(url, size)) as archive:
        manifest_data = archive.read("BuildManifest.plist")  # zipfile verifies member CRC.
        manifest = plistlib.loads(manifest_data)
        if manifest.get("SupportedProductTypes") != ["iPod9,1"]:
            raise ValueError("IPSW is not exclusively iPod9,1")
        identities = [x for x in manifest["BuildIdentities"] if x.get("Info", {}).get("DeviceClass") == "n112ap"]
        if not identities:
            raise ValueError("n112ap build identity is missing")
        identity = next((x for x in identities if "Erase" in x["Info"].get("Variant", "")), identities[0])
        report = {"url": url, "version": manifest["ProductVersion"], "build": manifest["ProductBuildVersion"],
                  "device": "iPod9,1", "identity": identity["Info"], "components": {}}
        (output / "BuildManifest.plist").write_bytes(manifest_data)
        for component in ["KernelCache", "DeviceTree"]:
            source = identity["Manifest"][component]["Info"]["Path"]
            info = archive.getinfo(source)
            if info.file_size > 128 * 1024 * 1024:
                raise ValueError("oversized component")
            data = archive.read(info)
            filename = component + ".im4p"
            (output / filename).write_bytes(data)
            report["components"][component] = {"source": source, "file": filename, "bytes": len(data),
                                                   "sha256": hashlib.sha256(data).hexdigest(), "zip_crc32": f"{info.CRC:08x}"}
            print(component, source, len(data), flush=True)
        (output / "firmware.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path(".firmware"))
    args = parser.parse_args()
    stage(args.output)
