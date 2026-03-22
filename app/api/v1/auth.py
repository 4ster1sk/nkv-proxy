"""
認証フロー

エンドポイント:
  GET  /                           → /login or /dashboard にリダイレクト
  GET  /register                   - 新規登録ページ
  POST /register                   - 新規登録 → /login へリダイレクト（ログインさせない）
  GET  /login                      - ログインページ
  POST /login                      - ログイン処理
  GET  /login/2fa                  - 2FAコード入力
  POST /login/2fa                  - 2FAコード検証
  GET  /logout                     - ログアウト
  GET  /dashboard                  - ウェルカムページ（認証済みアプリ一覧 + Mastodon連携）
  POST /dashboard/mastodon-connect - Mastodon OAuth 開始
  GET  /auth/mastodon/callback     - Mastodon OAuth コールバック
  GET  /miauth/{sid}               - Miriaからの認証 → /login?next={sid} へリダイレクト
  GET  /oauth/authorize            - Mastodon OAuth 認可開始
  POST /api/v1/apps                - アプリ登録
  POST /oauth/token                - code → access_token
  POST /oauth/revoke               - トークン失効
  GET  /settings/2fa               - 2FA設定ページ
  POST /settings/2fa/enable        - 2FA有効化
  POST /settings/2fa/disable       - 2FA無効化
"""

import uuid
import httpx
from fastapi import APIRouter, Cookie, Depends, Form, Query, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.db import crud
from app.db.models import OAuthToken

router = APIRouter()

# ---------------------------------------------------------------------------
# セッションCookie名
# ---------------------------------------------------------------------------
SESSION_COOKIE = "proxy_session"   # access_token を直接 cookie に入れる


# ---------------------------------------------------------------------------
# スタイル
# ---------------------------------------------------------------------------
def _style() -> str:
    return """
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:#f0f2f5;min-height:100vh;display:flex;align-items:center;
         justify-content:center;padding:1rem}
    .card{background:#fff;border-radius:14px;box-shadow:0 4px 28px rgba(0,0,0,.11);
          width:100%;max-width:440px;overflow:hidden}
    .card.wide{max-width:660px}
    .header{background:linear-gradient(135deg,#6364e0,#9b59b6);color:#fff;padding:1.4rem 1.8rem}
    .header h1{font-size:1.15rem;font-weight:700}
    .header p{font-size:.85rem;opacity:.85;margin-top:.25rem}
    .body{padding:1.5rem 1.8rem}
    .form-group{margin-bottom:.9rem}
    label{display:block;font-size:.85rem;font-weight:500;color:#444;margin-bottom:.3rem}
    input[type=text],input[type=password],input[type=url]{
      width:100%;padding:.6rem .85rem;border:1.5px solid #d0d5dd;
      border-radius:8px;font-size:.93rem;outline:none;transition:border .2s}
    input:focus{border-color:#6364e0}
    .btn{width:100%;padding:.7rem;background:#6364e0;color:#fff;border:none;
         border-radius:8px;font-size:.95rem;font-weight:600;cursor:pointer;
         transition:background .2s;margin-top:.3rem}
    .btn:hover{background:#5051c5}
    .btn-secondary{background:#f0f2f5;color:#444;border:1.5px solid #d0d5dd}
    .btn-secondary:hover{background:#e4e6ea}
    .btn-danger{background:#e74c3c}
    .btn-danger:hover{background:#c0392b}
    .btn-sm{width:auto;padding:.4rem .9rem;font-size:.85rem}
    .error{background:#fff0f0;border:1px solid #ffcccc;color:#c0392b;
           border-radius:8px;padding:.6rem .85rem;margin-bottom:.9rem;font-size:.86rem}
    .success{background:#f0fff4;border:1px solid #b7ebc9;color:#27ae60;
             border-radius:8px;padding:.6rem .85rem;margin-bottom:.9rem;font-size:.86rem}
    .warn{background:#fffbf0;border:1px solid #f5d78e;color:#856404;
          border-radius:8px;padding:.8rem 1rem;margin-bottom:.9rem;font-size:.88rem}
    .note{font-size:.76rem;color:#aaa;margin-top:.8rem;text-align:center;line-height:1.5}
    a{color:#6364e0;text-decoration:none}
    a:hover{text-decoration:underline}
    .app-list{list-style:none;margin-top:.5rem}
    .app-item{display:flex;align-items:center;justify-content:space-between;
              padding:.6rem .8rem;background:#f8f9fa;border-radius:8px;margin-bottom:.5rem;
              font-size:.88rem}
    .app-name{font-weight:600;color:#333}
    .app-meta{font-size:.78rem;color:#888;margin-top:.15rem}
    .badge{display:inline-block;background:#e8f4fd;color:#1a6fac;
           border-radius:12px;padding:.15rem .5rem;font-size:.75rem;font-weight:600}
    .badge.green{background:#e8fdf0;color:#1a7a3c}
    .badge.red{background:#fdf0f0;color:#9a1a1a}
    .section-title{font-size:.8rem;font-weight:700;color:#888;text-transform:uppercase;
                   letter-spacing:.06em;margin:1.2rem 0 .5rem}
    hr{border:none;border-top:1px solid #eee;margin:1.2rem 0}
    """


def _proxy_base(request: Request) -> str:
    if settings.PROXY_BASE_URL:
        return settings.PROXY_BASE_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{proto}://{host}"


async def _get_session_user(
    request: Request,
    db: AsyncSession,
):
    """Cookie の access_token からユーザーを取得。未認証なら None。"""
    token_str = request.cookies.get(SESSION_COOKIE)
    if not token_str:
        return None, None
    result = await crud.get_token_with_user(db, token_str)
    if result is None:
        return None, None
    return result  # (token, user)


# ---------------------------------------------------------------------------
# GET /  — トップ
# ---------------------------------------------------------------------------

@router.get("/")
async def top(request: Request, db: AsyncSession = Depends(get_db)):
    result = await _get_session_user(request, db)
    if result[0]:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


# ---------------------------------------------------------------------------
# GET/POST /register  — 新規登録
# ---------------------------------------------------------------------------

@router.get("/register")
async def register_page(
    error: str = Query(default=""),
    success: str = Query(default=""),
):
    error_html = f'<div class="error">⚠️ {error}</div>' if error else ""
    success_html = f'<div class="success">✅ {success}</div>' if success else ""
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>新規登録 — {settings.APP_NAME}</title>
<style>{_style()}</style></head>
<body><div class="card">
  <div class="header"><h1>🚀 新規登録</h1><p>{settings.APP_NAME}</p></div>
  <div class="body">
    {error_html}{success_html}
    <form method="post" action="/register">
      <div class="form-group">
        <label>ユーザー名（3〜30文字、英数字・_）</label>
        <input type="text" name="username" required pattern="[a-zA-Z0-9_]{{3,30}}"
               placeholder="username">
      </div>
      <div class="form-group">
        <label>パスワード（8文字以上）</label>
        <input type="password" name="password" required minlength="8">
      </div>
      <div class="form-group">
        <label>パスワード（確認）</label>
        <input type="password" name="password_confirm" required minlength="8">
      </div>
      <button type="submit" class="btn">アカウントを作成する</button>
    </form>
    <p class="note">すでにアカウントをお持ちの方は <a href="/login">ログイン</a></p>
  </div>
</div></body></html>"""
    return HTMLResponse(content=html)


@router.post("/register")
async def register_submit(
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    from urllib.parse import quote

    def _err(msg: str):
        return RedirectResponse(url=f"/register?error={quote(msg)}", status_code=302)

    if len(username) < 3 or not username.replace("_", "").isalnum():
        return _err("ユーザー名は3〜30文字の英数字・アンダースコアで入力してください")
    if len(password) < 8:
        return _err("パスワードは8文字以上にしてください")
    if password != password_confirm:
        return _err("パスワードが一致しません")
    if await crud.get_user_by_username(db, username):
        return _err(f"ユーザー名 @{username} はすでに使われています")

    await crud.create_user(db, username=username, password=password)
    await db.commit()

    from urllib.parse import quote
    return RedirectResponse(
        url=f"/login?success={quote('登録完了！ログインしてください')}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# GET/POST /login  — ログイン
# ---------------------------------------------------------------------------

@router.get("/login")
async def login_page(
    request: Request,
    next: str = Query(default=""),       # miAuth session_id
    error: str = Query(default=""),
    success: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    # すでにログイン済みなら処理
    result = await _get_session_user(request, db)
    if result[0]:
        if next:
            return RedirectResponse(url=f"/login/post-auth?next={next}", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)

    error_html = f'<div class="error">⚠️ {error}</div>' if error else ""
    success_html = f'<div class="success">✅ {success}</div>' if success else ""
    next_input = f'<input type="hidden" name="next" value="{next}">' if next else ""

    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ログイン — {settings.APP_NAME}</title>
<style>{_style()}</style></head>
<body><div class="card">
  <div class="header"><h1>🔐 ログイン</h1><p>{settings.APP_NAME}</p></div>
  <div class="body">
    {error_html}{success_html}
    <form method="post" action="/login">
      {next_input}
      <div class="form-group">
        <label>ユーザー名</label>
        <input type="text" name="username" required autocomplete="username" placeholder="username">
      </div>
      <div class="form-group">
        <label>パスワード</label>
        <input type="password" name="password" required autocomplete="current-password" placeholder="••••••••">
      </div>
      <button type="submit" class="btn">ログイン</button>
    </form>
    <p class="note">アカウントをお持ちでない方は <a href="/register">新規登録</a></p>
  </div>
</div></body></html>"""
    return HTMLResponse(content=html)


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    from urllib.parse import quote

    user = await crud.authenticate_user(db, username=username, password=password)
    if user is None:
        existing = await crud.get_user_by_username(db, username)
        hint = "（アカウントが未登録の場合は新規登録してください）" if not existing else ""
        err = quote(f"ユーザー名またはパスワードが違います{hint}")
        next_param = f"&next={next}" if next else ""
        return RedirectResponse(url=f"/login?error={err}{next_param}", status_code=302)

    # 2FA チェック
    if user.totp_enabled:
        # 一時セッションとして pending をセッションIDで管理
        tmp_id = str(uuid.uuid4())
        # 簡易: pending情報をcookieに入れる（本番はDBで管理推奨）
        next_param = f"&next={next}" if next else ""
        resp = RedirectResponse(url=f"/login/2fa?next={next}", status_code=302)
        resp.set_cookie("pending_user_id", user.id, max_age=300, httponly=True)
        return resp

    # トークン発行
    token = await crud.create_oauth_token(
        db, session_id=None, app_id=None, user_id=user.id
    )
    await db.commit()

    if next:
        # miAuth フローの継続処理へ
        resp = RedirectResponse(url=f"/login/post-auth?next={next}", status_code=302)
    else:
        resp = RedirectResponse(url="/dashboard", status_code=302)

    resp.set_cookie(SESSION_COOKIE, token.access_token, httponly=True, max_age=86400 * 30)
    return resp


# ---------------------------------------------------------------------------
# GET/POST /login/2fa  — 2FA
# ---------------------------------------------------------------------------

@router.get("/login/2fa")
async def login_2fa_page(
    next: str = Query(default=""),
    error: str = Query(default=""),
):
    error_html = f'<div class="error">⚠️ {error}</div>' if error else ""
    next_input = f'<input type="hidden" name="next" value="{next}">' if next else ""
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>2段階認証 — {settings.APP_NAME}</title>
<style>{_style()}</style></head>
<body><div class="card">
  <div class="header"><h1>🔑 2段階認証</h1><p>認証アプリのコードを入力してください</p></div>
  <div class="body">
    {error_html}
    <form method="post" action="/login/2fa">
      {next_input}
      <div class="form-group">
        <label>6桁のコード</label>
        <input type="text" name="code" required maxlength="6" pattern="[0-9]{{6}}"
               inputmode="numeric" autocomplete="one-time-code"
               style="font-size:1.4rem;letter-spacing:.3em;text-align:center">
      </div>
      <button type="submit" class="btn">確認</button>
    </form>
  </div>
</div></body></html>"""
    return HTMLResponse(content=html)


@router.post("/login/2fa")
async def login_2fa_submit(
    request: Request,
    code: str = Form(...),
    next: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    from urllib.parse import quote
    user_id = request.cookies.get("pending_user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    user = await crud.get_user_by_id(db, user_id)
    if not user or not user.totp_secret:
        return RedirectResponse(url="/login", status_code=302)

    if not crud.verify_totp(user.totp_secret, code.strip()):
        return RedirectResponse(
            url=f"/login/2fa?next={next}&error={quote('コードが違います')}",
            status_code=302,
        )

    token = await crud.create_oauth_token(
        db, session_id=None, app_id=None, user_id=user.id
    )
    await db.commit()

    if next:
        resp = RedirectResponse(url=f"/login/post-auth?next={next}", status_code=302)
    else:
        resp = RedirectResponse(url="/dashboard", status_code=302)

    resp.set_cookie(SESSION_COOKIE, token.access_token, httponly=True, max_age=86400 * 30)
    resp.delete_cookie("pending_user_id")
    return resp


# ---------------------------------------------------------------------------
# GET /login/post-auth  — ログイン後のmiAuth継続判定
# ---------------------------------------------------------------------------

@router.get("/login/post-auth")
async def login_post_auth(
    request: Request,
    next: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    ログイン済みの状態で miAuth セッションを継続する。
    Mastodon 未連携なら /dashboard でエラーを表示して案内する。
    連携済みなら miAuth 認可を完了してクライアントへ返す。
    """
    from urllib.parse import quote

    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url=f"/login?next={next}", status_code=302)

    _, user = result

    # Mastodon 未連携の場合
    if not user.mastodon_token:
        msg = quote(
            f"@{user.username} さんはまだMastodonと連携していません。"
            "ダッシュボードでMastodon連携を完了してから、"
            "アプリで再度ログイン操作を行ってください。"
        )
        return RedirectResponse(url=f"/dashboard?warn={msg}", status_code=302)

    if not next:
        return RedirectResponse(url="/dashboard", status_code=302)

    # miAuth セッションを取得・認可
    session = await crud.get_miauth_session(db, next)
    if session is None:
        return RedirectResponse(url="/dashboard", status_code=302)

    await crud.authorize_miauth_session(db, session_id=next, user_id=user.id)
    token = await crud.create_oauth_token(
        db, session_id=next, app_id=session.app_id,
        user_id=user.id, scopes=session.scopes,
    )
    await db.commit()

    redirect_uri = session.redirect_uri
    if redirect_uri and redirect_uri not in ("urn:ietf:wg:oauth:2.0:oob", ""):
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(url=f"{redirect_uri}{sep}code={next}", status_code=302)

    return HTMLResponse(content=_done_html(user.username, next, session.app_name))


# ---------------------------------------------------------------------------
# GET /logout
# ---------------------------------------------------------------------------

@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ---------------------------------------------------------------------------
# GET /dashboard  — ウェルカムページ
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def dashboard(
    request: Request,
    warn: str = Query(default=""),
    success: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url="/login", status_code=302)

    current_token, user = result

    # 認証済みアプリ一覧（このユーザーの有効トークン）
    tokens_result = await db.execute(
        select(OAuthToken)
        .where(OAuthToken.user_id == user.id, OAuthToken.revoked == False)  # noqa
        .order_by(OAuthToken.created_at.desc())
        .limit(20)
    )
    tokens = tokens_result.scalars().all()

    app_items = ""
    for t in tokens:
        if t.access_token == current_token.access_token:
            continue  # ダッシュボードセッション自体は除外
        scopes_badge = f'<span class="badge">{t.scopes[:30]}</span>'
        created = t.created_at.strftime("%Y/%m/%d %H:%M") if t.created_at else ""
        last_used = t.last_used_at.strftime("%Y/%m/%d %H:%M") if t.last_used_at else "未使用"
        app_items += f"""
        <li class="app-item">
          <div>
            <div class="app-name">アプリ #{t.id}</div>
            <div class="app-meta">登録: {created} / 最終利用: {last_used}</div>
            <div style="margin-top:.2rem">{scopes_badge}</div>
          </div>
          <form method="post" action="/dashboard/revoke/{t.id}" style="margin:0">
            <button type="submit" class="btn btn-danger btn-sm">取消</button>
          </form>
        </li>"""

    if not app_items:
        app_items = '<li style="color:#aaa;font-size:.88rem;padding:.5rem">認証済みアプリはありません</li>'

    # Mastodon 連携状態
    if user.mastodon_token:
        instance_host = (user.mastodon_instance or settings.MASTODON_INSTANCE_URL).replace("https://", "").rstrip("/")
        mastodon_section = f"""
        <p class="section-title">Mastodon連携</p>
        <div style="display:flex;align-items:center;gap:.8rem;padding:.6rem .8rem;
                    background:#f0fff4;border-radius:8px;margin-bottom:.5rem">
          <span class="badge green">✓ 連携済み</span>
          <span style="font-size:.88rem;color:#333">{instance_host}</span>
          <form method="post" action="/dashboard/mastodon-disconnect" style="margin:0;margin-left:auto">
            <button type="submit" class="btn btn-secondary btn-sm">解除</button>
          </form>
        </div>"""
    else:
        mastodon_section = f"""
        <p class="section-title">Mastodon連携</p>
        <div class="warn">
          ⚠️ Mastodonとまだ連携していません。
          アプリからのAPI利用にはMastodon連携が必要です。
        </div>
        <form method="post" action="/dashboard/mastodon-connect">
          <div class="form-group">
            <label>MastodonインスタンスURL</label>
            <input type="url" name="instance_url"
                   value="{settings.MASTODON_INSTANCE_URL}"
                   placeholder="https://mastodon.social" required>
          </div>
          <button type="submit" class="btn">Mastodonと連携する</button>
        </form>"""

    warn_html = f'<div class="warn">⚠️ {warn}</div>' if warn else ""
    success_html = f'<div class="success">✅ {success}</div>' if success else ""

    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ダッシュボード — {settings.APP_NAME}</title>
<style>
{_style()}
body{{align-items:flex-start;padding:2rem 1rem}}
.card.wide{{margin:0 auto}}
</style></head>
<body><div class="card wide">
  <div class="header">
    <h1>👋 @{user.username} さん、ようこそ！</h1>
    <p>{settings.APP_NAME} ダッシュボード</p>
  </div>
  <div class="body">
    {warn_html}{success_html}

    {mastodon_section}

    <hr>
    <p class="section-title">認証済みアプリ</p>
    <ul class="app-list">{app_items}</ul>

    <hr>
    <div style="display:flex;gap:.6rem;flex-wrap:wrap">
      <a href="/settings/2fa">
        <button class="btn btn-secondary btn-sm">2段階認証設定</button>
      </a>
      <a href="/logout">
        <button class="btn btn-secondary btn-sm">ログアウト</button>
      </a>
    </div>
  </div>
</div></body></html>"""
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# POST /dashboard/mastodon-connect  — Mastodon OAuth 開始
# ---------------------------------------------------------------------------

@router.post("/dashboard/mastodon-connect")
async def dashboard_mastodon_connect(
    request: Request,
    instance_url: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url="/login", status_code=302)
    _, user = result

    # URL正規化
    instance_url = instance_url.rstrip("/")
    if not instance_url.startswith("http"):
        instance_url = "https://" + instance_url

    base = _proxy_base(request)
    return await _start_mastodon_oauth(
        db=db, user=user, miauth_session_id=None,
        base=base, instance_url=instance_url,
    )


# ---------------------------------------------------------------------------
# POST /dashboard/mastodon-disconnect  — Mastodon 連携解除
# ---------------------------------------------------------------------------

@router.post("/dashboard/mastodon-disconnect")
async def dashboard_mastodon_disconnect(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url="/login", status_code=302)
    _, user = result

    from sqlalchemy import update
    from app.db.models import User
    await db.execute(
        update(User).where(User.id == user.id).values(
            mastodon_token=None, mastodon_instance=None, mastodon_account_id=None
        )
    )
    await db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


# ---------------------------------------------------------------------------
# POST /dashboard/revoke/{token_id}  — アプリトークン取消
# ---------------------------------------------------------------------------

@router.post("/dashboard/revoke/{token_id}")
async def dashboard_revoke_token(
    token_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url="/login", status_code=302)
    _, user = result

    # 自分のトークンのみ取消可能
    token = await db.get(OAuthToken, token_id)
    if token and token.user_id == user.id:
        token.revoked = True
        await db.commit()

    from urllib.parse import quote
    return RedirectResponse(
        url=f"/dashboard?success={quote('アプリの認証を取消しました')}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# GET /miauth/{session_id}  — Miriaからの認証エントリポイント
# ---------------------------------------------------------------------------

@router.get("/miauth/{session_id}")
async def miauth_entry(
    session_id: str,
    request: Request,
    name: str = Query(default=""),
    permission: str = Query(default=""),
    callback: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Miria等のクライアントが叩く認証エントリポイント。
    セッションをDBに登録してログインページへリダイレクト。
    """
    session = await crud.get_miauth_session(db, session_id)
    if session is None:
        await crud.create_miauth_session(
            db,
            session_id=session_id,
            redirect_uri=callback,
            scopes=permission.replace(",", " ") or "read write follow push",
            app_name=name or settings.APP_NAME,
            permission=permission,
        )
        await db.commit()

    return RedirectResponse(
        url=f"/login?next={session_id}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Mastodon OAuth ヘルパー
# ---------------------------------------------------------------------------

async def _start_mastodon_oauth(
    *, db: AsyncSession, user, miauth_session_id: str | None,
    base: str, instance_url: str,
):
    callback_url = f"{base}/auth/mastodon/callback"

    mastodon_app = await crud.get_mastodon_app(db, instance_url)
    if mastodon_app is None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{instance_url}/api/v1/apps",
                json={
                    "client_name": settings.APP_NAME,
                    "redirect_uris": callback_url,
                    "scopes": "read write follow push",
                    "website": base,
                },
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Mastodon ({instance_url}) へのアプリ登録に失敗しました")
        app_data = resp.json()
        mastodon_app = await crud.get_or_create_mastodon_app(
            db,
            instance_url=instance_url,
            client_id=app_data["client_id"],
            client_secret=app_data["client_secret"],
        )

    state_obj = await crud.create_mastodon_oauth_state(
        db,
        user_id=user.id,
        miauth_session_id=miauth_session_id,
        mastodon_app_id=mastodon_app.id,
        mastodon_instance=instance_url,
    )
    await db.commit()

    auth_url = (
        f"{instance_url}/oauth/authorize"
        f"?client_id={mastodon_app.client_id}"
        f"&redirect_uri={callback_url}"
        f"&response_type=code"
        f"&scope=read+write+follow+push"
        f"&state={state_obj.state}"
    )
    return RedirectResponse(url=auth_url, status_code=302)


# ---------------------------------------------------------------------------
# GET /auth/mastodon/callback  — Mastodon OAuth コールバック
# ---------------------------------------------------------------------------

@router.get("/auth/mastodon/callback")
async def mastodon_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    state_obj = await crud.get_mastodon_oauth_state(db, state)
    if state_obj is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    base = _proxy_base(request)
    callback_url = f"{base}/auth/mastodon/callback"
    instance_url = state_obj.mastodon_instance

    # トークン取得
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{instance_url}/oauth/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": state_obj.mastodon_app.client_id,
                "client_secret": state_obj.mastodon_app.client_secret,
                "redirect_uri": callback_url,
                "scope": "read write follow push",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Mastodonトークンの取得に失敗しました")

    mastodon_token = resp.json()["access_token"]

    # アカウント情報取得
    async with httpx.AsyncClient(timeout=10) as client:
        acc_resp = await client.get(
            f"{instance_url}/api/v1/accounts/verify_credentials",
            headers={"Authorization": f"Bearer {mastodon_token}"},
        )
    mastodon_account_id = acc_resp.json().get("id", "") if acc_resp.status_code == 200 else ""

    await crud.set_mastodon_credentials(
        db, state_obj.user_id,
        token=mastodon_token,
        instance=instance_url,
        account_id=mastodon_account_id,
    )
    await crud.delete_mastodon_oauth_state(db, state_obj.id)
    await db.commit()

    instance_host = instance_url.replace("https://", "").rstrip("/")

    # miAuth セッションがある場合 → miAuth 完了後クライアントへ
    if state_obj.miauth_session_id:
        session = await crud.get_miauth_session(db, state_obj.miauth_session_id)
        if session:
            user = await crud.get_user_by_id(db, state_obj.user_id)
            await crud.authorize_miauth_session(
                db, session_id=session.session_id, user_id=state_obj.user_id
            )
            token = await crud.create_oauth_token(
                db, session_id=session.session_id,
                app_id=session.app_id, user_id=state_obj.user_id,
                scopes=session.scopes,
            )
            await db.commit()

            redirect_uri = session.redirect_uri
            if redirect_uri and redirect_uri not in ("urn:ietf:wg:oauth:2.0:oob", ""):
                sep = "&" if "?" in redirect_uri else "?"
                return RedirectResponse(url=f"{redirect_uri}{sep}code={session.session_id}", status_code=302)
            return HTMLResponse(content=_done_html(user.username, session.session_id, session.app_name))

    from urllib.parse import quote
    return RedirectResponse(
        url=f"/dashboard?success={quote(f'Mastodon ({instance_host}) との連携が完了しました')}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/apps
# ---------------------------------------------------------------------------

@router.post("/api/v1/apps")
async def register_app(request: Request, db: AsyncSession = Depends(get_db)):
    ct = request.headers.get("content-type", "")
    body = await request.json() if "application/json" in ct else dict(await request.form())

    app = await crud.create_app(
        db,
        name=body.get("client_name") or body.get("name") or settings.APP_NAME,
        website=body.get("website"),
        redirect_uris=body.get("redirect_uris") or settings.APP_CALLBACK_URL or "urn:ietf:wg:oauth:2.0:oob",
        scopes=body.get("scopes") or "read write follow push",
    )
    await db.commit()
    return {
        "id": app.id, "name": app.name, "website": app.website,
        "redirect_uri": app.redirect_uris,
        "client_id": app.client_id, "client_secret": app.client_secret,
        "vapid_key": None,
    }


# ---------------------------------------------------------------------------
# GET /oauth/authorize
# ---------------------------------------------------------------------------

@router.get("/oauth/authorize")
async def oauth_authorize(
    request: Request,
    client_id: str = Query(default=""),
    redirect_uri: str = Query(default=None),
    scope: str = Query(default="read write follow push"),
    response_type: str = Query(default="code"),
    db: AsyncSession = Depends(get_db),
):
    app = await crud.get_app_by_client_id(db, client_id) if client_id else None
    session_id = str(uuid.uuid4())
    callback_uri = redirect_uri or (app.redirect_uris if app else None) or settings.APP_CALLBACK_URL

    await crud.create_miauth_session(
        db,
        session_id=session_id,
        app_id=app.id if app else None,
        redirect_uri=callback_uri,
        scopes=scope,
        app_name=app.name if app else settings.APP_NAME,
        permission=scope.replace(" ", ","),
    )
    await db.commit()

    base = _proxy_base(request)
    return RedirectResponse(
        url=f"{base}/miauth/{session_id}"
            f"?name={app.name if app else settings.APP_NAME}"
            f"&permission={scope.replace(' ', ',')}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# POST /oauth/token
# ---------------------------------------------------------------------------

@router.post("/oauth/token")
async def oauth_token(request: Request, db: AsyncSession = Depends(get_db)):
    ct = request.headers.get("content-type", "")
    body = await request.json() if "application/json" in ct else dict(await request.form())

    if body.get("grant_type") == "client_credentials":
        return {"access_token": "guest", "token_type": "Bearer", "scope": "read", "created_at": 0}

    code = body.get("code", "")
    if not code:
        raise HTTPException(status_code=401, detail="Missing code")

    session = await crud.get_miauth_session(db, code)
    if session and session.authorized:
        result = await db.execute(
            select(OAuthToken).where(
                OAuthToken.session_id == code, OAuthToken.revoked == False  # noqa
            )
        )
        token = result.scalar_one_or_none()
        if token:
            return {"access_token": token.access_token, "token_type": "Bearer",
                    "scope": token.scopes, "created_at": 0}

    raise HTTPException(status_code=401, detail="Invalid or expired code")


# ---------------------------------------------------------------------------
# POST /oauth/revoke
# ---------------------------------------------------------------------------

@router.post("/oauth/revoke")
async def oauth_revoke(request: Request, db: AsyncSession = Depends(get_db)):
    ct = request.headers.get("content-type", "")
    body = await request.json() if "application/json" in ct else dict(await request.form())
    token = body.get("token", "")
    if token:
        await crud.revoke_token(db, token)
        await db.commit()
    return {}


# ---------------------------------------------------------------------------
# 2FA 設定
# ---------------------------------------------------------------------------

@router.get("/settings/2fa")
async def settings_2fa_page(
    request: Request,
    error: str = Query(default=""),
    success: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url="/login", status_code=302)
    _, user = result

    error_html = f'<div class="error">⚠️ {error}</div>' if error else ""
    success_html = f'<div class="success">✅ {success}</div>' if success else ""
    token_str = request.cookies.get(SESSION_COOKIE, "")

    if user.totp_enabled:
        body_html = f"""
        {error_html}{success_html}
        <p style="color:#27ae60;font-weight:600;margin-bottom:1rem">✅ 2段階認証は有効です</p>
        <form method="post" action="/settings/2fa/disable">
          <input type="hidden" name="token" value="{token_str}">
          <button type="submit" class="btn btn-danger">2段階認証を無効にする</button>
        </form>"""
    else:
        secret = crud.generate_totp_secret()
        qr = crud.generate_totp_qr_base64(secret, user.username)
        body_html = f"""
        {error_html}{success_html}
        <p style="margin-bottom:1rem;font-size:.9rem;color:#555">
          認証アプリ（Google Authenticator等）でQRコードをスキャンしてください。
        </p>
        <div style="text-align:center;margin-bottom:1rem">
          <img src="data:image/png;base64,{qr}" alt="QR" style="max-width:200px;border-radius:8px">
        </div>
        <form method="post" action="/settings/2fa/enable">
          <input type="hidden" name="token" value="{token_str}">
          <input type="hidden" name="secret" value="{secret}">
          <div class="form-group">
            <label>確認コード（6桁）</label>
            <input type="text" name="code" required maxlength="6" pattern="[0-9]{{6}}"
                   inputmode="numeric"
                   style="font-size:1.3rem;letter-spacing:.3em;text-align:center">
          </div>
          <button type="submit" class="btn">2段階認証を有効にする</button>
        </form>"""

    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>2段階認証設定</title>
<style>{_style()}</style></head>
<body><div class="card">
  <div class="header"><h1>🔑 2段階認証設定</h1><p>@{user.username}</p></div>
  <div class="body">{body_html}
    <p class="note" style="margin-top:1rem"><a href="/dashboard">← ダッシュボードに戻る</a></p>
  </div>
</div></body></html>"""
    return HTMLResponse(content=html)


@router.post("/settings/2fa/enable")
async def settings_2fa_enable(
    token: str = Form(...),
    secret: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    from urllib.parse import quote
    result = await crud.get_token_with_user(db, token)
    if result is None:
        raise HTTPException(status_code=401)
    _, user = result

    if not crud.verify_totp(secret, code.strip()):
        return RedirectResponse(url=f"/settings/2fa?error={quote('コードが違います')}", status_code=302)

    await crud.enable_totp(db, user.id, secret)
    await db.commit()
    return RedirectResponse(url=f"/settings/2fa?success={quote('2段階認証を有効にしました')}", status_code=302)


@router.post("/settings/2fa/disable")
async def settings_2fa_disable(
    token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    from urllib.parse import quote
    result = await crud.get_token_with_user(db, token)
    if result is None:
        raise HTTPException(status_code=401)
    _, user = result

    await crud.disable_totp(db, user.id)
    await db.commit()
    return RedirectResponse(url=f"/settings/2fa?success={quote('2段階認証を無効にしました')}", status_code=302)


# ---------------------------------------------------------------------------
# ヘルパー: 認証完了HTML
# ---------------------------------------------------------------------------

def _done_html(username: str, session_id: str, app_name: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>認証完了</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:420px;margin:4rem auto;
       padding:1.5rem;text-align:center}}
  h1{{color:#27ae60;font-size:1.4rem}}
  .code{{background:#f5f5f5;border:1px solid #ddd;border-radius:8px;
         padding:1rem;margin:1.5rem 0;font-family:monospace;
         word-break:break-all;user-select:all;font-size:.9rem}}
  p{{color:#666;font-size:.9rem;line-height:1.6}}
</style></head>
<body>
  <h1>✅ 認証完了</h1>
  <p>ようこそ、<strong>@{username}</strong> さん！</p>
  <p>{app_name} へのアクセスを許可しました。<br>以下のコードをアプリに入力してください。</p>
  <div class="code">{session_id}</div>
  <p style="color:#aaa;font-size:.8rem">このページは閉じて構いません。</p>
</body></html>"""
