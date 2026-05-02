import re
import asyncio
from pathlib import Path

from gsuid_core.logger import logger

from .RESOURCE_PATH import STATIC_RESOURCE_PATH

RESOURCE_URL = "https://cnb.cool/tyql688/NteMeta"
META_PATH: Path = STATIC_RESOURCE_PATH
META_PATH.mkdir(parents=True, exist_ok=True)


async def _exec_git(
    cmd: str,
    cwd: Path | None = None,
    timeout: float = 120.0,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        if proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        return -1, "", f"命令执行超时（>{timeout}s）"

    return (
        proc.returncode or 0,
        stdout_b.decode("utf-8", errors="replace"),
        stderr_b.decode("utf-8", errors="replace"),
    )


def _is_git_repo() -> bool:
    return (META_PATH / ".git").is_dir()


async def _detect_default_branch() -> str:
    # `git init` 流派下没有 origin/HEAD symref，本地分支名也不可信
    # （旧 buggy 安装可能落下 master 本地分支但远端是 main），所以走 ls-remote 现问。
    rc, ls_out, _ = await _exec_git(f"git ls-remote --symref {RESOURCE_URL} HEAD")
    if rc != 0:
        return "main"
    m = re.search(r"ref:\s+refs/heads/(\S+)", ls_out)
    return m.group(1) if m else "main"


async def update_resources(
    is_force: bool = False,
    silent: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {
        "success": False,
        "message": "",
        "files_changed": 0,
    }

    try:
        if _is_git_repo():
            if not silent:
                logger.info(f"[NTEUID] 执行资源更新: {'force' if is_force else 'normal'}")

            branch = await _detect_default_branch()

            _, old_head, _ = await _exec_git(
                "git rev-parse HEAD",
                cwd=META_PATH,
            )
            old_head = old_head.strip()

            if is_force:
                rc, stdout, stderr = await _exec_git(
                    f"git fetch origin {branch} && git reset --hard origin/{branch}",
                    cwd=META_PATH,
                )
            else:
                rc, stdout, stderr = await _exec_git(
                    f"git pull origin {branch}",
                    cwd=META_PATH,
                )

            if rc != 0:
                err = stderr.strip() or stdout.strip()
                result["message"] = f"更新失败: {err}"
                logger.error(f"[NTEUID] 资源更新失败: {err}")
                return result

            _, new_head, _ = await _exec_git(
                "git rev-parse HEAD",
                cwd=META_PATH,
            )
            new_head = new_head.strip()

            if old_head == new_head:
                result["success"] = True
                result["message"] = "已是最新"
                if not silent:
                    logger.info("[NTEUID] 资源已是最新")
                return result

            _, diff_out, _ = await _exec_git(
                f"git diff --stat {old_head} {new_head}",
                cwd=META_PATH,
            )
            num_match = re.search(r"(\d+) files? changed", diff_out)
            files_changed = int(num_match.group(1)) if num_match else 0
            result["success"] = True
            result["files_changed"] = files_changed
            result["message"] = f"更新成功，改动了{files_changed}个文件" if files_changed else "更新成功"
            logger.success(f"[NTEUID] 资源{result['message']}")
            return result

        logger.info(f"[NTEUID] 执行资源安装: {RESOURCE_URL}")

        default_branch = await _detect_default_branch()

        cmds = [
            "git init",
            f"git remote add origin {RESOURCE_URL}",
            f"git fetch origin {default_branch} --depth=1",
            f"git checkout -f -b {default_branch} FETCH_HEAD",
        ]

        for cmd in cmds:
            rc, stdout, stderr = await _exec_git(cmd, cwd=META_PATH)
            if rc != 0:
                err = stderr.strip() or stdout.strip()
                result["message"] = f"安装失败 ({cmd}): {err}"
                logger.error(f"[NTEUID] 资源安装失败 ({cmd}): {err}")
                return result

        result["success"] = True
        result["message"] = "首次安装成功"
        logger.success("[NTEUID] 资源包首次安装成功")

    except Exception as e:
        result["message"] = f"异常: {e}"
        logger.error(f"[NTEUID] 资源处理异常: {e}")

    return result


async def init_resources() -> None:
    is_repo = _is_git_repo()
    logger.info("[NTEUID] 资源包已存在, 开始自动更新..." if is_repo else "[NTEUID] 未检测到资源包，开始自动安装...")
    result = await update_resources(is_force=is_repo, silent=False)
    if result["success"]:
        # 覆盖首启时插件导入留下的空 dict
        from ..name_convert import load_char_meta

        load_char_meta()


async def start_resources() -> None:
    """启动资源管理：首次安装阻塞等待，后续更新走后台。"""
    if _is_git_repo():
        from ..background import create_background_task

        create_background_task(init_resources())
    else:
        await init_resources()
