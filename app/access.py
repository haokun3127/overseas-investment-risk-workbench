from fastapi import HTTPException, Request


def company_of(request):
    return getattr(request.state, "company_id", None)


def is_admin(request):
    return company_of(request) is None and getattr(request.state, "username", "") == "admin"


def require_admin(request):
    if not is_admin(request):
        raise HTTPException(403, "仅管理员可执行此操作。")


def admin_only(request: Request):
    require_admin(request)


def session_company(request):
    """Company users use their own company; admins use this session's selected company."""
    cid = company_of(request)
    return cid if cid is not None else getattr(request.state, "active_company", None)
