"""Scan publishable/staged Git blobs. Report paths only, never matching secret values."""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [re.compile(rb"s" + rb"k-[A-Za-z0-9_-]{20,}"),
            re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}")]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def sensitive_path(name):
    filename = Path(name).name
    return ((filename == ".env" or filename.startswith(".env.")) and filename != ".env.example"
            or filename.endswith((".pem", ".key")))


def contains_secret(content):
    return any(pattern.search(content) for pattern in PATTERNS)


def scan(staged=False, history=False):
    failures = set()
    if staged:
        paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
    else:
        paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")
    for raw in filter(None, paths):
        name = raw.decode("utf-8")
        if staged:
            content = git("show", ":" + name)
        else:
            path = ROOT / name
            if not path.is_file():
                continue
            content = path.read_bytes()
        if sensitive_path(name) or contains_secret(content):
            failures.add(name)
    if history:
        for line in git("rev-list", "--objects", "--all").splitlines():
            parts = line.split(b" ", 1)
            if len(parts) != 2:
                continue
            object_id, raw_name = parts
            if git("cat-file", "-t", object_id.decode()).strip() != b"blob":
                continue
            name = raw_name.decode("utf-8", errors="replace")
            if sensitive_path(name) or contains_secret(git("cat-file", "blob", object_id.decode())):
                failures.add("history:" + name)
    for name in sorted(failures):
        print("BLOCKED sensitive file/content:", name)
    if not failures:
        print("Secret check passed (pattern-based; no secret values displayed).")
    return bool(failures)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    try:
        raise SystemExit(scan(args.staged, args.history))
    except subprocess.CalledProcessError:
        print("Secret check could not read Git state; blocked.")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
