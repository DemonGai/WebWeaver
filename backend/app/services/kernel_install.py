"""内核获取 = ``docker pull``。

旧实现是在临时 venv 里 pip 装包、或用 aria2 下 zip 再解压，落盘到
``browser_engine/<slug>/<version>/``。那套东西现在全部由镜像替代：镜像仓库里
每个 tag 就是一个现成的运行时，拉下来即可 ``docker run``，不需要在宿主机上
凑二进制。

任务模型沿用内存态（``job()`` / ``jobs()``），因为 ``docker pull`` 本身没有
稳定的任务 id 可查，进度只能读它自己的输出。进程重启后任务丢失，页面会提示
「任务中断」—— 但该拉完的镜像已经落盘，重新进页面就是新状态。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from loguru import logger

from app.schemas.kernels import InstallJob
from app.services import browser_novnc, kernel_image, kernel_pool, kernel_scan
from app.services.kernel_image import DockerError

MAX_JOBS = 20

_jobs: dict[str, InstallJob] = {}
_lock = asyncio.Lock()
# 一次只拉一个：500MB 起的层，并发会把带宽和磁盘 IO 打满
_semaphore = asyncio.Semaphore(1)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def jobs() -> list[InstallJob]:
    return sorted(_jobs.values(), key=lambda item: item.started_at, reverse=True)


def job(job_id: str) -> InstallJob | None:
    return _jobs.get(job_id)


def _remember(item: InstallJob) -> None:
    _jobs[item.id] = item
    if len(_jobs) <= MAX_JOBS:
        return
    finished = [j for j in _jobs.values() if j.status != "running"]
    for stale in sorted(finished, key=lambda j: j.started_at)[: len(_jobs) - MAX_JOBS]:
        _jobs.pop(stale.id, None)


def resolve_ref(slug: str, tag: str | None, version: str | None) -> tuple[str, str]:
    """把用户输入归一成 ``(镜像全名, 用作展示的版本号)``。

    三种输入都接受：完整 tag（``cloakbrowser-146.0...``）、纯版本号
    （``146.0...``，自动补前缀）、都不给（拉滚动 tag）。
    """
    registry = kernel_scan.registry()
    cleaned_tag = (tag or "").strip()
    cleaned_version = (version or "").strip()

    if cleaned_tag:
        # 允许直接贴带仓库名的全名
        ref = cleaned_tag if "/" in cleaned_tag else f"{registry}:{cleaned_tag}"
        short = cleaned_tag.rsplit(":", 1)[-1]
        _, tag_version = kernel_scan.parse_tag(short, [slug])
        return ref, tag_version or short

    if cleaned_version:
        return f"{registry}:{slug}-{cleaned_version}", cleaned_version

    return f"{registry}:{slug}", "latest"


async def start(
    slug: str,
    tag: str | None = None,
    version: str | None = None,
) -> InstallJob:
    """建任务并丢到后台。返回的 job 立刻可用于轮询。"""
    ref, display_version = resolve_ref(slug, tag, version)

    ok, reason = await asyncio.to_thread(kernel_image.available)
    if not ok:
        raise DockerError(reason or "Docker 不可用")

    item = InstallJob(
        id=uuid.uuid4().hex,
        slug=slug,
        version=display_version,
        tag=ref.rsplit(":", 1)[-1],
        image_ref=ref,
        status="running",
        progress=0.0,
        message="已排队，等待开始",
        started_at=_now(),
    )

    async with _lock:
        _remember(item)

    asyncio.create_task(_run(item))
    return item


def _set(item: InstallJob, progress: float, message: str) -> None:
    item.progress = max(item.progress, min(progress, 0.99))
    item.message = message


async def _run(item: InstallJob) -> None:
    """在信号量后面等，然后拉。任何异常都折成 failed，不往外抛。"""
    async with _semaphore:
        item.message = "正在拉取镜像"
        try:
            conclusion = await kernel_image.pull(
                item.image_ref,
                lambda progress, message: _set(item, progress, message),
            )
        except DockerError as exc:
            item.status = "failed"
            item.error = str(exc)
            item.finished_at = _now()
            logger.warning("拉取镜像失败 {}：{}", item.image_ref, exc)
            return
        except Exception as exc:  # noqa: BLE001 - 后台任务不能把异常漏给事件循环
            item.status = "failed"
            item.error = f"{exc.__class__.__name__}: {exc}"
            item.finished_at = _now()
            logger.exception("拉取镜像异常 {}", item.image_ref)
            return

    # 拉完再 inspect 一次：滚动 tag 的真实版本号只有镜像自己知道
    try:
        info = await asyncio.to_thread(kernel_image.inspect, item.image_ref)
    except DockerError:
        info = None
    if info and info.version:
        item.version = info.version

    item.progress = 1.0
    item.status = "success"
    item.message = conclusion or "拉取完成"
    item.finished_at = _now()
    # 同一个 tag 可能被重新构建过，noVNC 能力判定不能继续用旧镜像的结论
    browser_novnc.forget(item.image_ref)
    # 台账跟随事实：种子里的旧版本号如果本地根本没有镜像，改记成刚拉的这个，
    # 否则之后新建的实例会一直卡在「本地没有这个版本的镜像」
    try:
        await kernel_pool.adopt_pulled(item.slug, item.version)
    except Exception:  # noqa: BLE001 - 校正失败不该把成功的拉取标成失败
        logger.exception("校正内核台账失败 {}", item.image_ref)
    logger.info("镜像就绪 {}（{}）", item.image_ref, item.message)


__all__ = [
    "MAX_JOBS",
    "DockerError",
    "job",
    "jobs",
    "resolve_ref",
    "start",
]
