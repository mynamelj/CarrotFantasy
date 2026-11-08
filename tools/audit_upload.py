"""Audit the staged Git files and bundled ZIPs before publishing."""

import io
import re
import subprocess
import zipfile


BLOCKED = {
    ".apk", ".aab", ".apks", ".xapk", ".obb", ".dex", ".so", ".dll",
    ".jar", ".jks", ".keystore", ".p12", ".pem", ".key",
}


def check_name(name):
    from pathlib import PurePosixPath

    path = PurePosixPath(name.lower())
    if path.suffix in BLOCKED or any(part in {"private", "build", "dist", "decoded"} for part in path.parts):
        raise ValueError(f"Excluded upload path: {name}")


def main():
    staged = subprocess.check_output(["git", "ls-files", "--stage", "-z"])
    count = 0
    size = 0
    for row in staged.split(b"\0"):
        if not row:
            continue
        metadata, path = row.split(b"\t", 1)
        name = path.decode("utf-8")
        check_name(name)
        blob = metadata.split()[1].decode()
        raw = subprocess.check_output(["git", "cat-file", "blob", blob])
        if len(raw) > 2_000_000:
            raise ValueError(f"Unexpectedly large upload: {name}")
        if raw.startswith(b"PK\x03\x04"):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for item in archive.infolist():
                    check_name(item.filename)
        if re.search(rb"(?m)^-----BEGIN (?:RSA )?PRIVATE KEY-----\r?$", raw):
            raise ValueError(f"Private key detected: {name}")
        count += 1
        size += len(raw)
    if count == 0:
        raise ValueError("No staged files.")
    print(f"PASS {count} staged files, {size:,} bytes; archive contents inspected.")


if __name__ == "__main__":
    main()
