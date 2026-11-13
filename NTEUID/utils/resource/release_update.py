from __future__ import annotations

import os
import shutil
import hashlib
from typing import TypedDict
from pathlib import Path
from zipfile import ZipFile
from urllib.parse import quote

import httpx
from filelock import FileLock
from pydantic import Field, BaseModel

from .release_files import RECEIPT, Digest, Manifest, write_verified

RESOURCE_URL = "https://cnb.cool/tyql688/NteMeta"


class ResourceUpdateResult(TypedDict):
    success: bool
    message: str
    files_changed: int
    changed: bool


class _Asset(BaseModel):
    name: str
    hash_algo: str = ""
    hash_value: str = ""


class _Release(BaseModel):
    tag_name: str = Field(pattern=r"^res-[0-9a-f]{40}$")
    assets: list[_Asset] = Field(default_factory=list)


def _manifest(client: httpx.Client, local: bytes, force: bool) -> tuple[Manifest, bytes]:
    headers = {"Accept": "application/json"}
    if force:
        headers["Cache-Control"] = "no-cache"
    latest = client.get(f"{RESOURCE_URL}/-/releases/latest", headers=headers).raise_for_status()
    release = _Release.model_validate_json(latest.content)
    checksum = next((a.hash_value for a in release.assets if a.name == "manifest.json" and a.hash_algo == "sha256"), "")
    raw = local
    if not raw or hashlib.sha256(raw).hexdigest() != checksum:
        url = f"{RESOURCE_URL}/-/releases/download/{release.tag_name}/manifest.json"
        raw = client.get(url).raise_for_status().content
    manifest = Manifest.model_validate_json(raw)
    if release.tag_name != f"res-{manifest.commit}" or (checksum and hashlib.sha256(raw).hexdigest() != checksum):
        raise ValueError("Release 与资源清单不符")
    return manifest, raw


def _download(client: httpx.Client, url: str, target: Path, digest: Digest) -> None:
    with client.stream("GET", url) as response:
        response.raise_for_status()
        write_verified(target, response.iter_bytes(1024 * 1024), digest)


def _discard(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path)


def _prepare(
    client: httpx.Client, root: Path, staged: Path, manifest: Manifest, needed: list[str], archive: Path | None
) -> None:
    if archive is not None:
        with ZipFile(archive) as bundle:
            for name in needed:
                with bundle.open(name) as source:
                    write_verified(staged / name, iter(lambda: source.read(1024 * 1024), b""), manifest.files[name])
    else:
        for name in needed:
            url = f"{RESOURCE_URL}/-/git/raw/{manifest.commit}/{quote(name)}"
            _download(client, url, staged / name, manifest.files[name])
    for name in manifest.files.keys() - set(needed):
        target = staged / name
        with (root / name).open("rb") as source:
            write_verified(target, iter(lambda: source.read(1024 * 1024), b""), manifest.files[name])


def sync_release(root: Path, *, force: bool = False, local_zip: Path | None = None) -> ResourceUpdateResult:
    work = root.with_name(".nte-resource-update")
    if root.is_symlink() or work.is_symlink() or (work / "update.lock").is_symlink():
        raise ValueError("资源更新目录包含外部链接")
    work.mkdir(exist_ok=True)
    previous, staged, download = work / "previous", work / "next", work / "resources.zip"
    with FileLock(work / "update.lock", timeout=0), httpx.Client(follow_redirects=True, timeout=60) as client:
        if previous.is_dir() and not previous.is_symlink() and not (root / RECEIPT).is_file():
            _discard(root)
            previous.rename(root)
        for path in (previous, staged, download, work / "owner"):
            _discard(path)
        root.mkdir(exist_ok=True)

        receipt = root / RECEIPT
        local = receipt.read_bytes() if not receipt.is_symlink() and receipt.is_file() else b""
        manifest, raw = _manifest(client, local, force)

        existing: set[str] = set()
        directories: set[str] = set()
        for parent, dirs, files in os.walk(root):
            base = Path(parent)
            for name in dirs.copy():
                path = base / name
                if path.is_symlink() or name == ".git":
                    dirs.remove(name)
                    files.append(name)
                else:
                    directories.add(path.relative_to(root).as_posix())
            existing.update((base / name).relative_to(root).as_posix() for name in files)
        extras = existing - manifest.files.keys() - {RECEIPT}
        expected_dirs = {p.as_posix() for name in manifest.files for p in Path(name).parents}
        stale_dirs = directories - expected_dirs
        clean_install = not local and not (existing & manifest.files.keys())
        needed = [
            name for name, digest in manifest.files.items() if name not in existing or not digest.matches(root / name)
        ]
        if not needed and not extras and not stale_dirs:
            if raw != local:
                staged.write_bytes(raw)
                staged.replace(receipt)
            return {"success": True, "message": "已是最新", "files_changed": 0, "changed": False}

        # 下载和校验完成后切换整棵目录。中断在两次重命名之间时，下次从 previous 恢复。
        staged.mkdir()
        try:
            archive = local_zip
            if archive is not None and not manifest.archive.matches(archive):
                raise ValueError("本地 ZIP 与 Release 清单不符")
            if clean_install and archive is None:
                url = f"{RESOURCE_URL}/-/releases/download/res-{manifest.commit}/resources.zip"
                _download(client, url, download, manifest.archive)
                archive = download
            _prepare(client, root, staged, manifest, needed, archive)
            (staged / RECEIPT).write_bytes(raw)
            root.rename(previous)
            try:
                staged.rename(root)
            finally:
                if not root.exists():
                    previous.rename(root)
            _discard(previous)
        finally:
            _discard(staged)
            download.unlink(missing_ok=True)
        count = len(needed) + len(extras)
        return {
            "success": True,
            "message": "资源安装完成" if clean_install else "资源已同步",
            "files_changed": count,
            "changed": True,
        }
