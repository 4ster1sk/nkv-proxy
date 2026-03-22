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
# ヘルパー関数
# ---------------------------------------------------------------------------

def _head(title: str = "") -> str:
    """共通 <head> タグ（外部 CSS/JS を参照）"""
    prefix = f"{title} — " if title else ""
    return (
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{prefix}{settings.APP_NAME}</title>"
        '<link rel="stylesheet" href="/static/css/main.css">'
    )


def _proxy_base(request: Request) -> str:
    """このプロキシ自身の公開URLを返す。"""
    if settings.PROXY_BASE_URL:
        return settings.PROXY_BASE_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{proto}://{host}"


async def _get_session_user(request: Request, db: AsyncSession):
    """Cookie の access_token からユーザーを取得。未認証なら (None, None)。"""
    token_str = request.cookies.get(SESSION_COOKIE)
    if not token_str:
        return None, None
    result = await crud.get_token_with_user(db, token_str)
    if result is None:
        return None, None
    return result  # (token, user)


def _page(title: str, body_html: str, body_class: str = "") -> str:
    """完全なHTMLページを返す。"""
    cls = f' class="{body_class}"' if body_class else ""
    return (
        "<!DOCTYPE html>"
        "<html lang='ja'>"
        f"<head>{_head(title)}</head>"
        f"<body{cls}>"
        + body_html
        + '<script src="/static/js/main.js"></script>'
        "</body></html>"
    )


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
# GET /register  — 新規登録ページ
# ---------------------------------------------------------------------------

@router.get("/register")
async def register_page(
    error: str = Query(default=""),
    success: str = Query(default=""),
):
    from urllib.parse import unquote
    error_html = f'<div class="alert alert-error">⚠️ {unquote(error)}</div>' if error else ""
    success_html = f'<div class="alert alert-success">✅ {unquote(success)}</div>' if success else ""
    body = f"""
<div class="card">
  <div class="header"><h1>🚀 新規登録</h1><p>{settings.APP_NAME}</p></div>
  <div class="body">
    {error_html}{success_html}
    <form method="post" action="/register">
      <div class="form-group">
        <label>ユーザー名（3〜30文字、英数字・_）</label>
        <input type="text" name="username" required pattern="[a-zA-Z0-9_]{{3,30}}" placeholder="username">
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
</div>"""
    return HTMLResponse(content=_page("新規登録", body))


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
    next: str = Query(default=""),
    error: str = Query(default=""),
    success: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    from urllib.parse import unquote
    result = await _get_session_user(request, db)
    if result[0]:
        if next:
            return RedirectResponse(url=f"/login/post-auth?next={next}", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)

    error_html = f'<div class="alert alert-error">⚠️ {unquote(error)}</div>' if error else ""
    success_html = f'<div class="alert alert-success">✅ {unquote(success)}</div>' if success else ""
    next_input = f'<input type="hidden" name="next" value="{next}">' if next else ""

    body = f"""
<div class="card">
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
</div>"""
    return HTMLResponse(content=_page("ログイン", body))


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
    error_html = f'<div class="alert alert-error">⚠️ {error}</div>' if error else ""
    next_input = f'<input type="hidden" name="next" value="{next}">' if next else ""
    body = f"""
<div class="card">
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
</div>"""
    return HTMLResponse(content=_page("2段階認証", body))


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

    # Web UI テスト用 API キー（なければ作成）
    api_key_obj = await crud.get_or_create_api_key(db, user.id)
    await db.commit()
    web_api_key = api_key_obj.key

    # 認証済みアプリ一覧
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
            continue
        created = t.created_at.strftime("%Y/%m/%d %H:%M") if t.created_at else ""
        last_used = t.last_used_at.strftime("%Y/%m/%d %H:%M") if t.last_used_at else "未使用"

        # 権限リスト（折りたたみ表示用）
        scopes_list = [s.strip() for s in t.scopes.replace(",", " ").split() if s.strip()]
        has_admin = any("admin" in s for s in scopes_list)
        admin_count = sum(1 for s in scopes_list if "admin" in s)
        perm_items = "".join(
            f'<li>✓ {_PERM_LABELS.get(s, s)}</li>'
            for s in scopes_list if "admin" not in s
        )
        if admin_count:
            perm_items += f'<li style="color:#856404">⚠️ 管理者権限 ({admin_count}項目)</li>'

        # admin 制限トグル
        if has_admin:
            if t.admin_restricted:
                admin_btn = f"""
              <form method="post" action="/dashboard/admin-restrict/{t.id}/disable" style="margin:0">
                <button type="submit" class="btn btn-secondary btn-sm" title="admin APIは現在無効">🔒 admin: 無効</button>
              </form>"""
            else:
                admin_btn = f"""
              <form method="post" action="/dashboard/admin-restrict/{t.id}/enable" style="margin:0">
                <button type="submit" class="btn btn-sm" style="background:#e8a020;color:#fff" title="admin APIは現在有効">🔓 admin: 有効</button>
              </form>"""
        else:
            admin_btn = ""

        app_items += f"""
        <li class="app-item" style="flex-direction:column;align-items:stretch;gap:.4rem">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:.4rem">
            <div>
              <div class="app-name">アプリ #{t.id}</div>
              <div class="app-meta">登録: {created} / 最終利用: {last_used}</div>
            </div>
            <div style="display:flex;gap:.4rem;align-items:center;flex-shrink:0">
              {admin_btn}
              <form method="post" action="/dashboard/revoke/{t.id}" style="margin:0">
                <button type="submit" class="btn btn-danger btn-sm">取消</button>
              </form>
            </div>
          </div>
          <details>
            <summary style="font-size:.78rem;color:var(--primary);cursor:pointer;user-select:none">
              権限を見る ▽
            </summary>
            <ul style="list-style:none;padding:.4rem .6rem;font-size:.8rem;color:var(--text-2)">
              {perm_items}
            </ul>
          </details>
        </li>"""

    if not app_items:
        app_items = '<li style="color:var(--text-3);font-size:.88rem;padding:.5rem">認証済みアプリはありません</li>'

    # Mastodon 連携状態
    if user.mastodon_token:
        instance_host = (user.mastodon_instance or settings.MASTODON_INSTANCE_URL).replace("https://", "").rstrip("/")
        mastodon_section = f"""
        <p class="section-title">Mastodon連携</p>
        <div class="mastodon-connected">
          <span class="badge badge-green">✓ 連携済み</span>
          <span style="font-size:.88rem">{instance_host}</span>
          <form method="post" action="/dashboard/mastodon-disconnect" style="margin:0;margin-left:auto">
            <button type="submit" class="btn btn-secondary btn-sm">解除</button>
          </form>
        </div>"""
    else:
        mastodon_section = f"""
        <p class="section-title">Mastodon連携</p>
        <div class="alert alert-warn">
          ⚠️ Mastodonとまだ連携していません。アプリからのAPI利用にはMastodon連携が必要です。
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

    warn_html = f'<div class="alert alert-warn">⚠️ {warn}</div>' if warn else ""
    success_html = f'<div class="alert alert-success">✅ {success}</div>' if success else ""

    # ---- HTML 組み立て（変数を先に展開してから埋め込む）----
    _username = user.username
    _appname = settings.APP_NAME
    body = (
        '<div class="card wide">'
        '<div class="header">'
        f'<h1>👋 @{_username} さん、ようこそ！</h1>'
        f'<p>{_appname} ダッシュボード</p>'
        '</div>'
        '<div class="body">'
        + warn_html + success_html
        + mastodon_section
        + '<hr>'
        '<p class="section-title">認証済みアプリ</p>'
        f'<ul class="app-list">{app_items}</ul>'
        '<hr>'
        '<p class="section-title">🔑 共通 API キー</p>'
        '<div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.8rem">'
        f'<code id="webApiKey" data-key="{web_api_key}" style="background:var(--surface-2);'
        'border:1px solid var(--border);border-radius:6px;padding:.3rem .7rem;'
        'font-size:.82rem;flex:1;word-break:break-all;letter-spacing:.05em">••••••••••••••••</code>'
        '<button type="button" class="btn btn-secondary btn-sm" id="toggleKeyBtn" '
        'onclick="toggleApiKey()" title="表示/非表示">👁</button>'
        '<form method="post" action="/dashboard/regenerate-api-key" style="margin:0">'
        '<button type="submit" class="btn btn-secondary btn-sm">再生成</button>'
        '</form></div>'
        '<script>'
        'let _keyVisible = false;'
        'function toggleApiKey() {'
        '  const el = document.getElementById("webApiKey");'
        '  const btn = document.getElementById("toggleKeyBtn");'
        '  _keyVisible = !_keyVisible;'
        '  el.textContent = _keyVisible ? el.dataset.key : "••••••••••••••••";'
        '  btn.textContent = _keyVisible ? "🙈" : "👁";'
        '}'
        '</script>'
        '<hr>'
        '<div style="display:flex;gap:.6rem;flex-wrap:wrap;margin-bottom:.6rem">'
        '<a href="/settings/2fa"><button class="btn btn-secondary btn-sm">2段階認証設定</button></a>'
        '<a href="/logout"><button class="btn btn-secondary btn-sm">ログアウト</button></a>'
        '</div>'
        '<hr>'
        '<p class="section-title">🧪 Misskey API テスト</p>'
        '<div class="form-group">'
        '<label>エンドポイント（例: i / notes/timeline）</label>'
        '<input type="text" id="mkEp" value="i" placeholder="i">'
        '</div>'
        '<div class="form-group">'
        '<label>リクエストボディ (JSON)</label>'
        '<textarea id="mkBody" rows="3" style="width:100%;padding:.6rem .85rem;border:1.5px solid var(--border);'
        'border-radius:8px;font-family:monospace;font-size:.84rem;resize:vertical;'
        'background:var(--surface);color:var(--text)">{"limit":5}</textarea>'
        '</div>'
        '<label style="display:flex;align-items:center;gap:.5rem;margin-bottom:.6rem;font-size:.85rem;cursor:pointer">'
        '<input type="checkbox" id="mkUseToken" checked> 認証トークンを使用（共通 API キー）'
        '</label>'
        '<button type="button" class="btn" onclick="runMk()" style="max-width:160px;margin-bottom:.8rem">送信</button>'
        '<pre id="mkResult" style="display:none;background:var(--surface-2);border:1px solid var(--border);'
        'border-radius:8px;padding:.8rem;font-size:.78rem;max-height:280px;overflow:auto;white-space:pre-wrap"></pre>'
        '<hr>'
        '<p class="section-title">🧪 Mastodon API テスト</p>'
        '<div style="display:flex;gap:.6rem;margin-bottom:.6rem">'
        '<select id="mastoMethod" style="padding:.55rem .7rem;border:1.5px solid var(--border);'
        'border-radius:8px;background:var(--surface);color:var(--text);font-size:.9rem">'
        '<option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>'
        '</select>'
        '<input type="text" id="mastoPath" value="timelines/home" placeholder="timelines/home" style="flex:1">'
        '</div>'
        '<div class="form-group">'
        '<label>リクエストボディ (POST/PUT のみ)</label>'
        '<textarea id="mastoBody" rows="2" style="width:100%;padding:.6rem .85rem;border:1.5px solid var(--border);'
        'border-radius:8px;font-family:monospace;font-size:.84rem;resize:vertical;'
        'background:var(--surface);color:var(--text)" placeholder="{}"></textarea>'
        '</div>'
        '<label style="display:flex;align-items:center;gap:.5rem;margin-bottom:.6rem;font-size:.85rem;cursor:pointer">'
        '<input type="checkbox" id="mastoUseToken" checked> 認証トークンを使用（mastodon_token）'
        '</label>'
        '<button type="button" class="btn" onclick="runMasto()" style="max-width:160px;margin-bottom:.8rem">送信</button>'
        '<pre id="mastoResult" style="display:none;background:var(--surface-2);border:1px solid var(--border);'
        'border-radius:8px;padding:.8rem;font-size:.78rem;max-height:280px;overflow:auto;white-space:pre-wrap"></pre>'
        """<script>
    const API_KEY = document.getElementById("webApiKey").dataset.key;
    async function runMk() {
      const pre = document.getElementById("mkResult");
      pre.style.display = "block"; pre.textContent = "送信中...";
      try {
        let b = {};
        try { b = JSON.parse(document.getElementById("mkBody").value || "{}"); } catch(e) {}
        if (document.getElementById("mkUseToken").checked) b.i = API_KEY;
        const r = await fetch("/api/" + document.getElementById("mkEp").value.trim(),
          {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
        const d = await r.json().catch(()=>r.text());
        pre.textContent = JSON.stringify(d, null, 2);
      } catch(e) { pre.textContent = "エラー: " + e.message; }
    }
    async function runMasto() {
      const pre = document.getElementById("mastoResult");
      pre.style.display = "block"; pre.textContent = "送信中...";
      try {
        const method = document.getElementById("mastoMethod").value;
        const path = document.getElementById("mastoPath").value.trim();
        const useToken = document.getElementById("mastoUseToken").checked;
        const bodyText = document.getElementById("mastoBody").value.trim();
        const r = await fetch("/dashboard/mastodon-api-test", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            method: method,
            path: path,
            use_token: useToken,
            body: (["POST","PUT"].includes(method) && bodyText) ? JSON.parse(bodyText) : null
          })
        });
        const d = await r.json().catch(()=>r.text());
        pre.textContent = JSON.stringify(d, null, 2);
      } catch(e) { pre.textContent = "エラー: " + e.message; }
    }
    </script>"""
        + '</div></div>'
    )
    return HTMLResponse(content=_page("ダッシュボード", body, body_class="dashboard"))


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
# POST /dashboard/mastodon-api-test  — Mastodon API テスト（バックエンド経由）
# ---------------------------------------------------------------------------

@router.post("/dashboard/mastodon-api-test")
async def dashboard_mastodon_api_test(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    ダッシュボードの Mastodon API テストフォームからの呼び出し。
    ユーザーの mastodon_token を使って上流 Mastodon API を叩く。
    """
    result = await _get_session_user(request, db)
    if not result[0]:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    _, user = result

    body = await request.json()
    method = body.get("method", "GET").upper()
    path = body.get("path", "").strip("/")
    use_token = body.get("use_token", True)
    req_body = body.get("body")

    instance = user.mastodon_instance or settings.MASTODON_INSTANCE_URL
    url = f"{instance}/api/v1/{path}"

    headers: dict = {"Content-Type": "application/json"}
    if use_token and user.mastodon_token:
        headers["Authorization"] = f"Bearer {user.mastodon_token}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            elif method == "PUT":
                resp = await client.put(url, headers=headers, json=req_body)
            else:  # POST
                resp = await client.post(url, headers=headers, json=req_body)
        try:
            return resp.json()
        except Exception:
            return {"status": resp.status_code, "text": resp.text}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# POST /dashboard/admin-restrict  — Admin制限トグル
# ---------------------------------------------------------------------------

@router.post("/dashboard/admin-restrict/{token_id}/enable")
async def dashboard_admin_restrict_enable(
    token_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url="/login", status_code=302)
    _, user = result
    token = await db.get(OAuthToken, token_id)
    if token and token.user_id == user.id:
        await crud.set_admin_restricted(db, token_id, True)
        await db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


@router.post("/dashboard/admin-restrict/{token_id}/disable")
async def dashboard_admin_restrict_disable(
    token_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url="/login", status_code=302)
    _, user = result
    token = await db.get(OAuthToken, token_id)
    if token and token.user_id == user.id:
        await crud.set_admin_restricted(db, token_id, False)
        await db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


# ---------------------------------------------------------------------------
# POST /dashboard/regenerate-api-key
# ---------------------------------------------------------------------------

@router.post("/dashboard/regenerate-api-key")
async def dashboard_regenerate_api_key(
    request: Request, db: AsyncSession = Depends(get_db)
):
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url="/login", status_code=302)
    _, user = result
    await crud.regenerate_api_key(db, user.id)
    await db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


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
    - ログイン済み: 権限確認画面を表示（許可する / 拒否する）
    - 未ログイン:   /login?next={session_id} へリダイレクト
    """
    # セッション登録（なければ作成）
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
    elif name and not session.app_name:
        from sqlalchemy import update as _upd
        from app.db.models import MiAuthSession as _MS
        await db.execute(
            _upd(_MS).where(_MS.session_id == session_id)
            .values(app_name=name, permission=permission)
        )
        await db.commit()

    result = await _get_session_user(request, db)
    if not result[0]:
        # 未ログイン → ログインページへ
        return RedirectResponse(url=f"/login?next={session_id}", status_code=302)

    # ログイン済み → 確認画面を表示
    _, user = result
    effective_name = name or (session.app_name if session else settings.APP_NAME)
    effective_perm = permission or (session.permission if session else "")
    return HTMLResponse(content=_miauth_confirm_page(
        session_id=session_id,
        app_name=effective_name,
        permission=effective_perm,
        username=user.username,
    ))


@router.post("/miauth/{session_id}/approve")
async def miauth_approve(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """ユーザーが「許可する」を押したとき。"""
    result = await _get_session_user(request, db)
    if not result[0]:
        return RedirectResponse(url=f"/login?next={session_id}", status_code=302)
    _, user = result

    session = await crud.get_miauth_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=400, detail="Session not found or expired.")

    await crud.authorize_miauth_session(db, session_id=session_id, user_id=user.id)
    await crud.create_oauth_token(
        db, session_id=session_id, app_id=session.app_id,
        user_id=user.id, scopes=session.scopes,
    )
    await db.commit()

    redirect_uri = session.redirect_uri
    if redirect_uri and redirect_uri not in ("urn:ietf:wg:oauth:2.0:oob", ""):
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(url=f"{redirect_uri}{sep}code={session_id}", status_code=302)
    return HTMLResponse(content=_done_html(user.username, session_id, session.app_name))


@router.post("/miauth/{session_id}/deny")
async def miauth_deny(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """ユーザーが「拒否する」を押したとき。"""
    session = await crud.get_miauth_session(db, session_id)
    if session:
        from sqlalchemy import delete as _del
        from app.db.models import MiAuthSession as _MS
        await db.execute(_del(_MS).where(_MS.session_id == session_id))
        await db.commit()

    redirect_uri = session.redirect_uri if session else None
    if redirect_uri and redirect_uri not in ("urn:ietf:wg:oauth:2.0:oob", ""):
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(
            url=f"{redirect_uri}{sep}error=access_denied&error_description=User+denied+access",
            status_code=302,
        )
    body = """
<div class="card">
  <div class="header"><h1>🚫 アクセスを拒否しました</h1><p></p></div>
  <div class="body">
    <p>アクセスを拒否しました。このページを閉じてください。</p>
    <a href="/dashboard"><button class="btn btn-secondary" style="margin-top:1rem">ダッシュボードへ</button></a>
  </div>
</div>"""
    return HTMLResponse(content=_page("拒否", body))


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

    error_html = f'<div class="alert alert-error">⚠️ {error}</div>' if error else ""
    success_html = f'<div class="alert alert-success">✅ {success}</div>' if success else ""
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

    body = f"""
<div class="card">
  <div class="header"><h1>🔑 2段階認証設定</h1><p>@{user.username}</p></div>
  <div class="body">{body_html}
    <p class="note" style="margin-top:1rem"><a href="/dashboard">← ダッシュボードに戻る</a></p>
  </div>
</div>"""
    return HTMLResponse(content=_page("2段階認証設定", body))


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

_PERM_LABELS = {'read:account': 'アカウント情報の読み取り', 'write:account': 'アカウント情報の変更', 'read:blocks': 'ブロックリストの読み取り', 'write:blocks': 'ブロック操作', 'read:drive': 'ドライブの読み取り', 'write:drive': 'ドライブへのアップロード', 'read:favorites': 'お気に入りの読み取り', 'write:favorites': 'お気に入りの追加・削除', 'read:following': 'フォロー情報の読み取り', 'write:following': 'フォロー・フォロー解除', 'read:messaging': 'メッセージの読み取り', 'write:messaging': 'メッセージの送信', 'read:mutes': 'ミュートリストの読み取り', 'write:mutes': 'ミュート操作', 'write:notes': 'ノートの投稿・削除', 'read:notifications': '通知の読み取り', 'write:notifications': '通知の操作', 'read:reactions': 'リアクションの読み取り', 'write:reactions': 'リアクションの追加・削除', 'write:votes': 'アンケートへの投票', 'read:channels': 'チャンネルの読み取り', 'write:channels': 'チャンネルの作成・管理', 'read:gallery': 'ギャラリーの読み取り', 'write:gallery': 'ギャラリーの投稿', 'read:federation': '連合情報の読み取り', 'write:report-abuse': '違反報告の送信'}


def _miauth_confirm_page(
    session_id: str, app_name: str, permission: str, username: str
) -> str:
    """miAuth権限確認画面。"""
    perms = [p.strip() for p in permission.split(",") if p.strip()]
    admin_perms = [p for p in perms if "admin" in p]
    normal_perms = [p for p in perms if "admin" not in p]

    perm_items = "\n".join(
        f'<li style="padding:.2rem 0">✓ {_PERM_LABELS.get(p, p)}</li>'
        for p in normal_perms
    )
    if admin_perms:
        perm_items += f'\n<li style="padding:.2rem 0;color:#856404">⚠️ 管理者権限 ({len(admin_perms)}項目)</li>'

    admin_warn = """
    <div class="alert alert-warn">
      ⚠️ このアプリは<strong>管理者権限</strong>を要求しています。信頼できるアプリにのみ許可してください。
    </div>""" if admin_perms else ""

    body = f"""
<div class="card">
  <div class="header">
    <h1>🔐 アクセス許可の確認</h1>
    <p>@{username} としてログイン中</p>
  </div>
  <div class="body">
    {admin_warn}
    <p style="font-size:.9rem;margin-bottom:.8rem">
      <strong>{app_name}</strong> が以下の権限を要求しています：
    </p>
    <ul style="list-style:none;background:var(--surface-2);border:1px solid var(--border);
               border-radius:8px;padding:.6rem .9rem;margin-bottom:1.2rem;
               max-height:200px;overflow-y:auto;font-size:.88rem">
      {perm_items}
    </ul>
    <div style="display:flex;gap:.6rem">
      <form method="post" action="/miauth/{session_id}/approve" style="flex:1;margin:0">
        <button type="submit" class="btn">✓ 許可する</button>
      </form>
      <form method="post" action="/miauth/{session_id}/deny" style="flex:1;margin:0">
        <button type="submit" class="btn btn-secondary">✗ 拒否する</button>
      </form>
    </div>
  </div>
</div>"""
    return _page("アクセス許可の確認", body)


def _done_html(username: str, session_id: str, app_name: str) -> str:
    body = f"""
<div class="card">
  <div class="header"><h1>✅ 認証完了</h1><p>{app_name}</p></div>
  <div class="body">
    <p>ようこそ、<strong>@{username}</strong> さん！</p>
    <p style="margin:.8rem 0;font-size:.9rem;color:var(--text-2);">
      {app_name} へのアクセスを許可しました。<br>以下のコードをアプリに入力してください。
    </p>
    <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:8px;
                padding:1rem;margin:.8rem 0;font-family:monospace;word-break:break-all;
                font-size:.9rem;user-select:all">{session_id}</div>
    <p class="note">このページは閉じて構いません。</p>
  </div>
</div>"""
    return _page("認証完了", body)
