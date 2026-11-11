"""Docker 镜像交互：内核「有没有」只由本地镜像决定。

口径只有一条 —— ``<仓库>:<tag>`` 出现在本地 ``docker image ls`` 里，就算这个
内核可用；没出现就是没获取。所以「获取内核」等价于 ``docker pull``，
不再有解压发行包、写 ``meta.json``、校验目录完整性那一整套东西。

两条实现上的注意：

- **不要用 ``asyncio.create_subprocess_exec``**：Windows 上 uvicorn 默认跑
  ``SelectorEventLoop``，创建子进程会直接抛 ``NotImplementedError``。
  统一用 ``asyncio.to_thread`` 包同步的 ``subprocess``。
- **``docker pull`` 在非 TTY 下没有进度条**，输出是逐层快照（每层状态变了才打印
  一行，形如 ``<layer>: Download complete``）。所以进度只能按
  「已完成层数 / 已知层数」估算，总层数在下载初期还不完整。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings

# Windows 上不给 CREATE_NO_WINDOW，每次调用都会闪一个黑框
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
SHORT_ID = 12

# 进度回调：(0~1 的比例, 一句人话)
ProgressHook = Callable[[float, str], None]


class DockerError(RuntimeError):
    """docker 命令不可用或执行失败。"""


@dataclass(frozen=True)
class ImageInfo:
    """一个本地镜像 tag 的完整信息。"""

    ref: str  # demon1315132284/browser_engine:cloakbrowser
    repository: str
    tag: str
    image_id: str  # sha256:...
    size_bytes: int
    created_at: str  # ISO8601，Docker 给的是 UTC
    digest: str | None = None  # RepoDigests 里的 sha256，本地构建的可能没有
    arch: str | None = None
    os_name: str | None = None
    # 镜像自带的 OCI 标签。滚动 tag（如 `cloakbrowser`）名字里没有版本号，
    # 版本得从 org.opencontainers.image.version 读，Dockerfile 里写了这个 label
    labels: dict[str, str] | None = None

    @property
    def short_id(self) -> str:
        return self.image_id.removeprefix("sha256:")[:SHORT_ID]

    @property
    def version(self) -> str | None:
        """镜像声明的版本号，没有就返回 None。"""
        return (self.labels or {}).get("org.opencontainers.image.version") or None


def docker_bin() -> str:
    return settings.kernel_docker_bin or "docker"


def run(
    args: list[str], *, timeout: float = 60, check: bool = False
) -> subprocess.CompletedProcess[str]:
    """同步执行一条 docker 命令。"""
    binary = shutil.which(docker_bin())
    if binary is None:
        raise DockerError(
            f"找不到 docker 命令（{docker_bin()}）。内核管理需要宿主机装 Docker，"
            "并把 docker 命令放进 PATH"
        )
    try:
        return subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=check,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise DockerError(f"docker {' '.join(args)} 超时（{timeout:.0f} 秒）") from exc
    except OSError as exc:
        raise DockerError(f"docker 启动失败：{exc}") from exc


def available() -> tuple[bool, str | None]:
    """探测 docker 是否可用；不可用时返回一句能直接显示给人看的原因。"""
    try:
        proc = run(["version", "--format", "{{.Server.Version}}"], timeout=15)
    except DockerError as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, None
    message = (proc.stderr or proc.stdout or "").strip().splitlines()
    hint = message[-1] if message else f"退出码 {proc.returncode}"
    if "Cannot connect" in hint or "pipe" in hint or "connection" in hint.lower():
        hint = f"Docker 守护进程没在运行（{hint}）"
    return False, hint


def list_images(repository: str) -> list[ImageInfo]:
    """列出某个仓库下的全部本地 tag，按 tag 名排序。

    先 ``image ls`` 拿 ref 清单，再一次性 ``image inspect`` 补精确大小与创建时间：
    ``image ls`` 给的 ``Size`` 是 ``2.13GB`` 这种四舍五入过的字符串，拿来算总量不准。
    """
    if not repository:
        return []
    proc = run(
        [
            "image",
            "ls",
            "--format",
            "{{.Repository}}:{{.Tag}}",
            "--filter",
            f"reference={repository}",
            "--filter",
            "dangling=false",
        ],
        timeout=30,
    )
    if proc.returncode != 0:
        raise DockerError((proc.stderr or proc.stdout or "列出镜像失败").strip())

    refs = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    refs = [ref for ref in refs if not ref.endswith(":<none>")]
    if not refs:
        return []
    return inspect_many(refs)


def inspect_many(refs: list[str]) -> list[ImageInfo]:
    """批量 inspect，返回顺序与入参一致；任何一个不存在都会整体失败。"""
    if not refs:
        return []
    proc = run(["image", "inspect", *refs], timeout=60)
    if proc.returncode != 0:
        raise DockerError((proc.stderr or proc.stdout or "inspect 失败").strip())
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DockerError(f"docker image inspect 返回的不是 JSON：{exc}") from exc

    items: list[ImageInfo] = []
    for ref, raw in zip(refs, payload, strict=False):
        repository, _, tag = ref.rpartition(":")
        digests = raw.get("RepoDigests") or []
        items.append(
            ImageInfo(
                ref=ref,
                repository=repository,
                tag=tag,
                image_id=str(raw.get("Id") or ""),
                size_bytes=int(raw.get("Size") or 0),
                created_at=str(raw.get("Created") or ""),
                digest=(digests[0].split("@", 1)[-1] if digests else None),
                arch=raw.get("Architecture"),
                os_name=raw.get("Os"),
                labels=(raw.get("Config") or {}).get("Labels") or None,
            )
        )
    return items


def inspect(ref: str) -> ImageInfo | None:
    """单个镜像；不存在返回 None（``docker image inspect`` 此时退出码非 0）。"""
    if not ref:
        return None
    proc = run(["image", "inspect", ref], timeout=30)
    if proc.returncode != 0:
        return None
    try:
        raw = json.loads(proc.stdout)[0]
    except (json.JSONDecodeError, IndexError, KeyError):
        return None
    repository, _, tag = ref.rpartition(":")
    digests = raw.get("RepoDigests") or []
    return ImageInfo(
        ref=ref,
        repository=repository,
        tag=tag,
        image_id=str(raw.get("Id") or ""),
        size_bytes=int(raw.get("Size") or 0),
        created_at=str(raw.get("Created") or ""),
        digest=(digests[0].split("@", 1)[-1] if digests else None),
        arch=raw.get("Architecture"),
        os_name=raw.get("Os"),
        labels=(raw.get("Config") or {}).get("Labels") or None,
    )


def exists(ref: str) -> bool:
    return inspect(ref) is not None


def remove(ref: str) -> tuple[bool, str]:
    """删本地镜像。失败（比如还有容器在用）返回原因，不抛。"""
    try:
        proc = run(["image", "rm", ref], timeout=120)
    except DockerError as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, f"已删除 {ref}"
    lines = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, (lines[-1] if lines else f"退出码 {proc.returncode}")


def _parse_layer_line(line: str) -> tuple[str, str] | None:
    """把 ``<layer>: <状态>`` 拆开；不是层状态行就返回 None。"""
    layer, sep, status = line.partition(": ")
    if not sep or not layer or " " in layer:
        return None
    if not (status.startswith("Pull") or status.startswith("Download") or status.startswith("Wait")):
        return None
    if layer.lower().startswith(("digest", "status", "latest", "main")):
        return None
    return layer, status


async def pull(ref: str, on_progress: ProgressHook | None = None) -> str:
    """拉取镜像，返回 docker 的结论行。

    进度按层估算：``Pull complete`` 的层数除以出现过的层数。层是陆续开始的，
    所以分母会变大，进度偶尔回退一格 —— 比一路 0% 然后突然 100% 诚实。
    """
    timeout = max(60.0, float(settings.kernel_image_pull_timeout))

    def work() -> str:
        binary = shutil.which(docker_bin())
        if binary is None:
            raise DockerError(
                f"找不到 docker 命令（{docker_bin()}）。内核管理需要宿主机装 Docker，"
                "并把 docker 命令放进 PATH"
            )
        try:
            proc = subprocess.Popen(
                [binary, "pull", ref],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=_CREATE_NO_WINDOW,
            )
        except OSError as exc:
            raise DockerError(f"docker pull 启动失败：{exc}") from exc

        layers: dict[str, str] = {}
        conclusion = ""
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip("\r\n").strip()
                if not line:
                    continue
                parsed = _parse_layer_line(line)
                if parsed:
                    layer, status = parsed
                    layers[layer] = status
                    total = len(layers)
                    done = sum(1 for value in layers.values() if value == "Pull complete")
                    if total and on_progress:
                        # 留 5% 给收尾的 manifest 写入，别让进度条先到 100 再卡住
                        on_progress(
                            0.05 + 0.9 * (done / total),
                            f"拉取中 {done}/{total} 层",
                        )
                elif line.startswith(("Digest:", "Status:")):
                    conclusion = line
                    if on_progress:
                        on_progress(0.98, line)
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            raise DockerError(f"拉取 {ref} 超过 {timeout:.0f} 秒，已中止") from exc
        finally:
            if proc.poll() is None:
                proc.kill()

        if proc.returncode != 0:
            raise DockerError(f"拉取 {ref} 失败（退出码 {proc.returncode}）")
        return conclusion or "拉取完成"

    return await asyncio.to_thread(work)
