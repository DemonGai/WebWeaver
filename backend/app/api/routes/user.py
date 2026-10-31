"""个人中心接口：头像浮层、个人信息、登录设备、安全概览、我的操作日志。

这里处理的是「当前登录成员自己」（``users`` 表），不是浏览器账号池（``accounts`` 表，
见 ``routes/accounts.py``）。两者中文都叫「账号」，所以接口前缀特意用 ``/user`` 区分；
能查能改别人的接口在 ``routes/rbac.py`` 里。

全部只读自己或只改自己，因此只需要登录态，不挂权限点。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.api.deps import CurrentContext, CurrentUser, OptionalUser, SessionDep
from app.models.enums import AuditAction, AuditResult
from app.schemas.audit import AuditLogItem, AuditLogList
from app.schemas.user import (
    ProfilePayload,
    ProfileUpdate,
    ProfileUpdateResponse,
    SecurityPayload,
    SessionList,
    SessionRevokeResponse,
    UserMenuPayload,
)
from app.services import user as user_service

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/menu", response_model=UserMenuPayload, summary="头像菜单浮层数据")
async def get_user_menu(user: OptionalUser, session: SessionDep) -> UserMenuPayload:
    """未登录时返回占位内容，登录后换成真实的成员、角色与默认工作区。"""
    return await user_service.build_menu(session, user)


@router.get("/profile", response_model=ProfilePayload, summary="个人信息详情")
async def get_profile(user: CurrentUser, session: SessionDep) -> ProfilePayload:
    return await user_service.build_profile(session, user)


@router.patch("/profile", response_model=ProfileUpdateResponse, summary="修改显示名")
async def update_profile(
    payload: ProfileUpdate,
    user: CurrentUser,
    session: SessionDep,
    request: Request,
) -> ProfileUpdateResponse:
    """只能改显示名；邮箱涉及验证流程，不在这里改。"""
    profile = await user_service.update_display_name(
        session, user, payload.display_name, request=request
    )
    return ProfileUpdateResponse(
        ok=True,
        message=f"显示名已更新为「{profile.display_name}」",
        profile=profile,
    )


@router.get("/sessions", response_model=SessionList, summary="登录设备列表")
async def get_sessions(context: CurrentContext, session: SessionDep) -> SessionList:
    user, row = context
    return await user_service.list_sessions(session, user, current_id=row.id)


@router.delete(
    "/sessions/{session_id}",
    response_model=SessionRevokeResponse,
    summary="踢掉某个登录设备",
)
async def delete_session(
    session_id: UUID,
    context: CurrentContext,
    session: SessionDep,
    request: Request,
) -> SessionRevokeResponse:
    """吊销指定会话；踢的是自己当前这台，效果等同退出登录。"""
    user, row = context
    revoked = await user_service.revoke_session(
        session, user, session_id, current_id=row.id, request=request
    )
    signed_out = session_id == row.id
    return SessionRevokeResponse(
        ok=True,
        message="已退出当前设备" if signed_out else ("设备已下线" if revoked else "该设备已失效"),
        revoked=revoked,
        signed_out=signed_out,
    )


@router.get("/security", response_model=SecurityPayload, summary="安全概览")
async def get_security(user: CurrentUser, session: SessionDep) -> SecurityPayload:
    """返回改密时间、失败计数、锁定状态、在线设备数与最近认证事件。"""
    return await user_service.build_security(session, user)


@router.get("/audit-logs", response_model=AuditLogList, summary="我的操作日志")
async def get_my_audit_logs(
    user: CurrentUser,
    session: SessionDep,
    action: Annotated[AuditAction | None, Query(description="按动作筛选")] = None,
    result: Annotated[AuditResult | None, Query(description="按结果筛选")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="每页条数")] = 50,
    offset: Annotated[int, Query(ge=0, description="偏移量")] = 0,
) -> AuditLogList:
    """只看自己的记录；操作人由登录态决定，不接受前端传 operator。"""
    rows, total = await user_service.list_my_logs(
        session, user, action=action, result=result, limit=limit, offset=offset
    )
    return AuditLogList(
        items=[AuditLogItem.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
