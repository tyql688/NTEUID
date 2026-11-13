from __future__ import annotations

import hashlib
import unicodedata
from typing import Self, Literal
from pathlib import Path, PureWindowsPath
from collections.abc import Iterable

from pydantic import Field, BaseModel, model_validator

RECEIPT = ".nte-manifest.json"


class Digest(BaseModel):
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def matches(self, path: Path) -> bool:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != self.size:
            return False
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest() == self.sha256


class Manifest(BaseModel):
    format: Literal[1]
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    archive: Digest
    files: dict[str, Digest]

    @model_validator(mode="after")
    def check_paths(self) -> Self:
        paths: dict[str, str] = {}
        for name in self.files:
            parts = name.split("/")
            for depth, part in enumerate(parts, 1):
                prefix = "/".join(parts[:depth])
                key = unicodedata.normalize("NFC", prefix).casefold()
                if (
                    not part
                    or (part.startswith(".") and name != ".gitignore")
                    or part.endswith((" ", "."))
                    or PureWindowsPath(part).is_reserved()
                    or any(c in '<>:"\\|?*' or ord(c) < 32 for c in part)
                    or paths.setdefault(key, prefix) != prefix
                    or (depth < len(parts) and prefix in self.files)
                ):
                    raise ValueError(f"无效的资源路径 {name!r}")
        if "char_meta.json" not in self.files:
            raise ValueError("清单缺少角色索引")
        return self


def write_verified(target: Path, chunks: Iterable[bytes], expected: Digest) -> None:
    size, sha = 0, hashlib.sha256()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output:
        for chunk in chunks:
            size += len(chunk)
            if size > expected.size:
                break
            output.write(chunk)
            sha.update(chunk)
    if size != expected.size or sha.hexdigest() != expected.sha256:
        raise ValueError(f"资源校验失败 {target.name}")
