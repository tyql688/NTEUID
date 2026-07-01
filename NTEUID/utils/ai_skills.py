from __future__ import annotations

import shutil
from pathlib import Path

from gsuid_core.logger import logger
from gsuid_core.data_store import AI_CORE_PATH, get_res_path


def sync_ai_skills() -> None:
    source_root = Path(__file__).resolve().parents[2] / "skills"
    if not source_root.exists():
        return

    target_root = get_res_path(AI_CORE_PATH / "skills")
    marker_root = target_root / ".plugin-managed" / "NTEUID"
    marker_root.mkdir(parents=True, exist_ok=True)

    for source in sorted(item for item in source_root.iterdir() if (item / "SKILL.md").is_file()):
        target = target_root / source.name
        marker = marker_root / f"{source.name}.txt"
        old_marker = marker_root / f"{source.name}.json"

        if target.exists() and not marker.exists() and not old_marker.exists():
            logger.warning(f"[NTE AI] 跳过非 NTEUID 管理的 skill: {source.name}")
            continue
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        elif target.is_symlink():
            target.unlink()

        shutil.copytree(source, target)
        marker.write_text(source.as_posix() + "\n", encoding="utf-8")
        old_marker.unlink(missing_ok=True)
        logger.info(f"[NTE AI] skill 已同步: {source.name}")
