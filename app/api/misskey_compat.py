"""
Misskey-compatible API endpoints ( POST /api/... ).

Misskey のネイティブクライアントや連合サーバーが叩くエンドポイントを
このプロキシ上でも応答できるようにする。

認証トークンはリクエストボディの "i" フィールド、または
Authorization: Bearer ヘッダーのどちらでも受け付ける。
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import crud
from app.db.database import get_db
from app.services.instance_cache import supports_local_timeline
from app.services.mastodon_client import MastodonClient
from app.services.misskey_client import MisskeyClient
from app.services.note_converter import (
    _build_reaction_key,
    masto_status_to_mk_note,
    masto_statuses_to_mk_notes,
    mk_renote_stub,
)
from app.services.user_converter import (
    masto_to_misskey_user_detailed,
    masto_to_misskey_user_lite,
)

router = APIRouter(prefix="/api", tags=["misskey-compat"])


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


async def _check_admin_allowed(token: str, db: AsyncSession) -> None:
    """
    access_token が admin_restricted=True の場合 403 を返す。
    /api/admin/* エンドポイントの冒頭で呼ぶ。
    """
    result = await crud.get_token_with_user(db, token)
    if result is None:
        raise HTTPException(status_code=401, detail="Credential required")
    token_obj, _ = result
    if token_obj.admin_restricted:
        raise HTTPException(
            status_code=403,
            detail="Admin API access is temporarily disabled for this token. "
                   "Re-enable it from the dashboard."
        )


def _mk_follow_relationship(
    account: dict,
    viewer_id: str,
    is_following: bool,
) -> dict:
    """
    Mastodon account → Misskey フォロー/フォロワー関係オブジェクト。

    Mastodon は createdAt や followerId を返さないため:
    - id        : UUIDv5(viewer_id + account_id) で決定論的に生成
    - createdAt : account.created_at を近似値として使用
    - followerId/followeeId : is_following の向きで決定
    """
    import uuid as _uuid
    account_id = account.get("id", "")
    # 決定論的な UUID を生成（同じペアなら常に同じIDになる）
    seed = f"{viewer_id}:{account_id}"
    rel_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, seed))
    created_at = account.get("created_at", "")

    if is_following:
        # 自分(viewer) が account をフォロー
        follower_id = viewer_id
        followee_id = account_id
        followee = masto_to_misskey_user_detailed(account)
        follower = None
    else:
        # account が自分(viewer) をフォロー
        follower_id = account_id
        followee_id = viewer_id
        followee = None
        follower = masto_to_misskey_user_detailed(account)

    return {
        "id": rel_id,
        "createdAt": created_at,
        "followeeId": followee_id,
        "followerId": follower_id,
        "followee": followee,
        "follower": follower,
    }


async def _body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _token(body: dict, request: Request) -> str | None:
    if body.get("i"):
        return body["i"]
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def _mastodon_client(token: str, db: AsyncSession) -> "MastodonClient":
    """
    access_token または api_key → User → MastodonClient を返す。
    Mastodon未連携の場合は 403。
    """
    # まず OAuthToken で検索
    result = await crud.get_token_with_user(db, token)
    if result is None:
        # 次に ApiKey で検索
        api_key_obj = await crud.get_api_key_by_key(db, token)
        if api_key_obj is None:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        from sqlalchemy import select as _sel

        from app.db.models import User as _User
        user_result = await db.execute(_sel(_User).where(_User.id == api_key_obj.user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
    else:
        _, user = result

    if not user.mastodon_token:
        raise HTTPException(
            status_code=403,
            detail="Mastodon連携が未設定です。ダッシュボードで連携してください。"
        )
    return MastodonClient(user.mastodon_token, user.mastodon_instance)


def _mk_client(token: str) -> MisskeyClient:
    """旧来のMisskeyClientが必要なエンドポイント用（将来的に削除予定）"""
    return MisskeyClient(token)


async def _forward(endpoint: str, body: dict) -> dict | list:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.MASTODON_INSTANCE_URL}/api/{endpoint}",
            json=body,
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    if resp.status_code == 204:
        return {}
    return resp.json()


# ---------------------------------------------------------------------------
# /api/meta  — 完全互換実装
# ---------------------------------------------------------------------------

@router.post("/meta")
async def api_meta(request: Request):
    """
    Misskey 互換の /api/meta。
    実際の /api/meta レスポンス構造（61フィールド）に完全準拠。
    上流 Misskey から取得して一部をプロキシ情報で上書きする。
    上流障害時は最低限のフォールバック値で応答する。
    """
    body = await _body(request)

    upstream: dict = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.MASTODON_INSTANCE_URL}/api/meta",
                json={"detail": body.get("detail", True)},
            )
            if resp.status_code == 200:
                upstream = resp.json()
    except Exception:
        pass

    host = settings.MASTODON_INSTANCE_URL.rstrip("/")

    # policies: 上流の値をベースに antennaLimit だけ 0 に上書き（仕様通り）
    upstream_policies: dict = upstream.get("policies") or {}
    policies = {
        "gtlAvailable":              upstream_policies.get("gtlAvailable", False),
        "ltlAvailable":              upstream_policies.get("ltlAvailable", False),
        "canPublicNote":             upstream_policies.get("canPublicNote", True),
        "mentionLimit":              upstream_policies.get("mentionLimit", 20),
        "canInvite":                 upstream_policies.get("canInvite", False),
        "inviteLimit":               upstream_policies.get("inviteLimit", 0),
        "inviteLimitCycle":          upstream_policies.get("inviteLimitCycle", 10080),
        "inviteExpirationTime":      upstream_policies.get("inviteExpirationTime", 0),
        "canManageCustomEmojis":     upstream_policies.get("canManageCustomEmojis", False),
        "canManageAvatarDecorations":upstream_policies.get("canManageAvatarDecorations", False),
        "canSearchNotes":            upstream_policies.get("canSearchNotes", False),
        "canSearchUsers":            upstream_policies.get("canSearchUsers", True),
        "canUseTranslator":          upstream_policies.get("canUseTranslator", False),
        "canHideAds":                upstream_policies.get("canHideAds", False),
        "driveCapacityMb":           upstream_policies.get("driveCapacityMb", 500),
        "maxFileSizeMb":             upstream_policies.get("maxFileSizeMb", 30),
        "alwaysMarkNsfw":            upstream_policies.get("alwaysMarkNsfw", False),
        "canUpdateBioMedia":         upstream_policies.get("canUpdateBioMedia", True),
        "pinLimit":                  upstream_policies.get("pinLimit", 5),
        # ── アンテナ制限（ロール制限 = 0）──────────────────────
        "antennaLimit":              0,
        "antennaNotesLimit":         upstream_policies.get("antennaNotesLimit", 200),
        # ────────────────────────────────────────────────────────
        "wordMuteLimit":             upstream_policies.get("wordMuteLimit", 200),
        "webhookLimit":              upstream_policies.get("webhookLimit", 3),
        # ── クリップ機能なし ──────────────────────────────────────
        "clipLimit":                 0,
        "noteEachClipsLimit":        0,
        # ────────────────────────────────────────────────────────
        "userListLimit":             upstream_policies.get("userListLimit", 10),
        "userEachUserListsLimit":    upstream_policies.get("userEachUserListsLimit", 50),
        "rateLimitFactor":           upstream_policies.get("rateLimitFactor", 1),
        "avatarDecorationLimit":     upstream_policies.get("avatarDecorationLimit", 1),
        "canImportAntennas":         upstream_policies.get("canImportAntennas", False),
        "canImportBlocking":         upstream_policies.get("canImportBlocking", False),
        "canImportFollowing":        upstream_policies.get("canImportFollowing", False),
        "canImportMuting":           upstream_policies.get("canImportMuting", False),
        "canImportUserLists":        upstream_policies.get("canImportUserLists", False),
        # ── チャット・ノートドラフト・スケジュール投稿なし ────────
        "chatAvailability":          "unavailable",
        "uploadableFileTypes":       [
            "image/jpeg", "image/png", "image/gif", "image/webp",
            "image/avif", "image/svg+xml",
            "video/mp4", "video/mpeg", "video/webm", "video/quicktime",
            "audio/mpeg", "audio/ogg", "audio/wav", "audio/flac", "audio/aac",
        ],
        "noteDraftLimit":            0,
        "scheduledNoteLimit":        0,
        # ────────────────────────────────────────────────────────
        "watermarkAvailable":        upstream_policies.get("watermarkAvailable", False),
        "fileSizeLimit":             upstream_policies.get("fileSizeLimit", 50),
    }

    # features: Misskey の features 構造に準拠
    # 上流が Mastodon 互換サーバーの場合 /api/meta が存在しないため
    # globalTimeline はプロキシとして常に True にする
    upstream_features: dict = upstream.get("features") or {}

    # ENABLE_LOCAL_TIMELINE 設定に基づいて LTL の表示可否を決定
    _ltl_setting = settings.ENABLE_LOCAL_TIMELINE.lower()
    if _ltl_setting == "true":
        _ltl_available = True
    elif _ltl_setting == "false":
        _ltl_available = False
    else:
        # auto: キャッシュを使って確認（同期コンテキストなのでデフォルト False、実際の判定は LTL 呼び出し時）
        _ltl_available = upstream_features.get("localTimeline", False)

    features = {
        "localTimeline":          _ltl_available,
        "globalTimeline":         upstream_features.get("globalTimeline", True),
        "registration":           upstream_features.get("registration", False),
        "emailRequiredForSignup": upstream_features.get("emailRequiredForSignup", False),
        "hcaptcha":               upstream_features.get("hcaptcha", False),
        "recaptcha":              upstream_features.get("recaptcha", False),
        "turnstile":              upstream_features.get("turnstile", False),
        "objectStorage":          upstream_features.get("objectStorage", False),
        "serviceWorker":          upstream_features.get("serviceWorker", False),
        "miauth":                 True,   # このプロキシは常に miAuth 対応
    }

    # clientOptions
    upstream_client_opts: dict = upstream.get("clientOptions") or {}
    client_options = {
        "entrancePageStyle":        upstream_client_opts.get("entrancePageStyle", "default"),
        "showTimelineForVisitor":   upstream_client_opts.get("showTimelineForVisitor", False),
        "showActivitiesForVisitor": upstream_client_opts.get("showActivitiesForVisitor", False),
    }

    return {
        # ── 管理者情報 ──────────────────────────────────────────────
        "maintainerName":               upstream.get("maintainerName"),
        "maintainerEmail":              upstream.get("maintainerEmail"),
        # ── バージョン・識別 ─────────────────────────────────────────
        "version":                      upstream.get("version") or settings.INSTANCE_VERSION,
        "providesTarball":              upstream.get("providesTarball", False),
        "name":                         upstream.get("name") or settings.INSTANCE_TITLE,
        "shortName":                    upstream.get("shortName"),
        "uri":                          upstream.get("uri") or host,
        "description":                  upstream.get("description") or settings.INSTANCE_DESCRIPTION,
        "langs":                        upstream.get("langs") or [],
        # ── 各種 URL ────────────────────────────────────────────────
        "tosUrl":                       upstream.get("tosUrl") or "",
        "repositoryUrl":                upstream.get("repositoryUrl"),
        "feedbackUrl":                  upstream.get("feedbackUrl"),
        "impressumUrl":                 upstream.get("impressumUrl") or "",
        "privacyPolicyUrl":             upstream.get("privacyPolicyUrl") or "",
        "inquiryUrl":                   upstream.get("inquiryUrl"),
        # ── 登録・サインアップ制御 ────────────────────────────────────
        "disableRegistration":          upstream.get("disableRegistration", True),
        "emailRequiredForSignup":       upstream.get("emailRequiredForSignup", False),
        # ── Captcha 設定 ────────────────────────────────────────────
        "enableHcaptcha":               upstream.get("enableHcaptcha", False),
        "hcaptchaSiteKey":              upstream.get("hcaptchaSiteKey"),
        "enableMcaptcha":               upstream.get("enableMcaptcha", False),
        "mcaptchaSiteKey":              upstream.get("mcaptchaSiteKey"),
        "mcaptchaInstanceUrl":          upstream.get("mcaptchaInstanceUrl"),
        "enableRecaptcha":              upstream.get("enableRecaptcha", False),
        "recaptchaSiteKey":             upstream.get("recaptchaSiteKey"),
        "enableTurnstile":              upstream.get("enableTurnstile", False),
        "turnstileSiteKey":             upstream.get("turnstileSiteKey"),
        "enableTestcaptcha":            upstream.get("enableTestcaptcha", False),
        # ── アナリティクス ───────────────────────────────────────────
        "googleAnalyticsMeasurementId": upstream.get("googleAnalyticsMeasurementId"),
        # ── PWA / ServiceWorker ───────────────────────────────────
        "swPublickey":                  upstream.get("swPublickey"),
        # ── 外観 ────────────────────────────────────────────────────
        "themeColor":                   upstream.get("themeColor"),
        "disableSignup":                upstream.get("disableSignup", True),
        "serverChartsAuthRequired":     upstream.get("serverChartsAuthRequired", False),
        "mascotImageUrl":               upstream.get("mascotImageUrl"),
        "bannerUrl":                    upstream.get("bannerUrl") or "",
        "infoImageUrl":                 upstream.get("infoImageUrl"),
        "serverErrorImageUrl":          upstream.get("serverErrorImageUrl"),
        "notFoundImageUrl":             upstream.get("notFoundImageUrl"),
        "iconUrl":                      upstream.get("iconUrl"),
        "backgroundImageUrl":           upstream.get("backgroundImageUrl"),
        "logoImageUrl":                 upstream.get("logoImageUrl"),
        # ── ノート設定 ────────────────────────────────────────────
        "maxNoteTextLength":            upstream.get("maxNoteTextLength", 3000),
        # ── テーマ ────────────────────────────────────────────────
        "defaultLightTheme":            upstream.get("defaultLightTheme"),
        "defaultDarkTheme":             upstream.get("defaultDarkTheme"),
        # ── クライアント設定 ──────────────────────────────────────
        "clientOptions":                client_options,
        # ── 広告 ────────────────────────────────────────────────
        "ads":                          upstream.get("ads") or [],
        "notesPerOneAd":                upstream.get("notesPerOneAd", 0),
        # ── メール・ServiceWorker ────────────────────────────────
        "enableEmail":                  upstream.get("enableEmail", False),
        "enableServiceWorker":          upstream.get("enableServiceWorker", False),
        # ── 翻訳 ────────────────────────────────────────────────
        "translatorAvailable":          upstream.get("translatorAvailable", False),
        # ── サーバールール ────────────────────────────────────────
        "serverRules":                  upstream.get("serverRules") or [],
        # ── ポリシー（antennaLimit=0 で上書き済み）────────────────
        "policies":                     policies,
        # ── Sentry ───────────────────────────────────────────────
        "sentryForFrontend":            upstream.get("sentryForFrontend"),
        # ── メディアプロキシ ──────────────────────────────────────
        "mediaProxy":                   upstream.get("mediaProxy") or f"{host}/proxy",
        # ── URL プレビュー ────────────────────────────────────────
        "enableUrlPreview":             upstream.get("enableUrlPreview", True),
        # ── 検索・連合 ────────────────────────────────────────────
        "noteSearchableScope":          upstream.get("noteSearchableScope", "local"),
        "federation":                   upstream.get("federation", "all"),
        # ── キャッシュ ────────────────────────────────────────────
        "cacheRemoteFiles":             upstream.get("cacheRemoteFiles", False),
        "cacheRemoteSensitiveFiles":    upstream.get("cacheRemoteSensitiveFiles", True),
        # ── セットアップ ──────────────────────────────────────────
        "requireSetup":                 upstream.get("requireSetup", False),
        # ── プロキシアカウント ────────────────────────────────────
        "proxyAccountName":             upstream.get("proxyAccountName"),
        # ── 機能フラグ ────────────────────────────────────────────
        "features":                     features,
    }


# ---------------------------------------------------------------------------
# /api/stats
# ---------------------------------------------------------------------------

@router.post("/stats")
async def api_stats(request: Request):
    body = await _body(request)
    try:
        return await _forward("stats", body)
    except Exception:
        return {
            "notesCount": 0,
            "originalNotesCount": 0,
            "usersCount": 0,
            "originalUsersCount": 0,
            "instances": 0,
            "driveUsageLocal": 0,
            "driveUsageRemote": 0,
        }



# ---------------------------------------------------------------------------
# /api/i
# ---------------------------------------------------------------------------

@router.post("/i")
async def api_i(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Misskey の /api/i 互換エンドポイント。
    Mastodon の GET /api/v1/accounts/verify_credentials に変換して返す。
    """
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")

    # DBからユーザー取得（twoFactorEnabled等の補完用）
    result = await crud.get_token_with_user(db, token)
    db_user = result[1] if result else None

    mk_client = await _mastodon_client(token, db)
    masto_user = await mk_client.verify_credentials()
    return masto_to_misskey_user_detailed(masto_user, db_user=db_user, is_me=True)


@router.post("/i/update")
async def api_i_update(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk_client = await _mastodon_client(token, db)
    payload = {k: v for k, v in body.items() if k != "i"}
    masto_user = await mk_client.update_credentials(**payload)
    result = await crud.get_token_with_user(db, token)
    db_user = result[1] if result else None
    return masto_to_misskey_user_detailed(masto_user, db_user=db_user, is_me=True)


@router.post("/i/notifications")
async def api_i_notifications(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk_client = await _mastodon_client(token, db)
    return await mk_client.get_notifications(
        limit=body.get("limit", 20),
        since_id=body.get("sinceId"),
        max_id=body.get("untilId"),
    )


# ---------------------------------------------------------------------------
# /api/notifications
# ---------------------------------------------------------------------------

@router.post("/notifications/mark-all-as-read")
async def api_notifications_mark_all_read(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).clear_notifications()


# ---------------------------------------------------------------------------
# /api/notes
# ---------------------------------------------------------------------------

@router.post("/notes/timeline")
async def api_notes_timeline(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    _tl_params: dict = {"limit": body.get("limit", 20)}
    if body.get("untilId"):
        _tl_params["max_id"] = body["untilId"]
    if body.get("sinceId"):
        _tl_params["min_id"] = body["sinceId"]
    statuses = await mk.home_timeline(**_tl_params)
    return masto_statuses_to_mk_notes(statuses)


@router.post("/notes/local-timeline")
async def api_notes_local_timeline(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)

    # ENABLE_LOCAL_TIMELINE の値に応じて LTL の可否を判定
    ltl_setting = settings.ENABLE_LOCAL_TIMELINE.lower()

    if ltl_setting == "false":
        # 強制無効
        raise HTTPException(status_code=400, detail={
            "error": {
                "message": "Local timeline has been disabled.",
                "code": "LTL_DISABLED",
                "id": "45a6eb02-7695-4393-b023-dd3be9aaaefd",
                "kind": "client",
            }
        })
    elif ltl_setting == "auto":
        # 上流インスタンスの機能を確認（キャッシュ TTL 3時間）
        if token:
            result = await crud.get_token_with_user(db, token)
            if not result:
                result = await crud.get_api_key_by_key(db, token)
                if result:
                    from sqlalchemy import select as _sel

                    from app.db.models import User as _User
                    user_result = await db.execute(_sel(_User).where(_User.id == result.user_id))
                    user = user_result.scalar_one_or_none()
                else:
                    user = None
            else:
                _, user = result
            instance = (user.mastodon_instance if user else None) or settings.MASTODON_INSTANCE_URL
        else:
            instance = settings.MASTODON_INSTANCE_URL

        ltl_ok = await supports_local_timeline(instance)
        if not ltl_ok:
            raise HTTPException(status_code=400, detail={
                "error": {
                    "message": "Local timeline is not available on this instance.",
                    "code": "LTL_DISABLED",
                    "id": "45a6eb02-7695-4393-b023-dd3be9aaaefd",
                    "kind": "client",
                }
            })
    # else: ltl_setting == "true" → 強制有効、チェックスキップ

    if not token:
        return []
    mk = await _mastodon_client(token, db)
    _tl_params: dict = {"local": True, "limit": body.get("limit", 20)}
    if body.get("untilId"):
        _tl_params["max_id"] = body["untilId"]
    if body.get("sinceId"):
        _tl_params["min_id"] = body["sinceId"]
    statuses = await mk.public_timeline(**_tl_params)
    return masto_statuses_to_mk_notes(statuses)

@router.post("/notes/global-timeline")
async def api_notes_global_timeline(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    mk = await _mastodon_client(token or "", db) if token else None
    if mk is None:
        return []
    _tl_params3: dict = {"limit": body.get("limit", 20)}
    if body.get("untilId"):
        _tl_params3["max_id"] = body["untilId"]
    if body.get("sinceId"):
        _tl_params3["min_id"] = body["sinceId"]
    statuses = await mk.public_timeline(**_tl_params3)
    return masto_statuses_to_mk_notes(statuses)


@router.post("/notes/create")
async def api_notes_create(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    # visibility: Misskey → Mastodon
    vis = {"public": "public", "home": "unlisted", "followers": "private", "specified": "direct"}.get(
        body.get("visibility", "public"), "public"
    )
    status = await mk.create_status(
        status=body.get("text", ""),
        spoiler_text=body.get("cw"),
        visibility=vis,
        in_reply_to_id=body.get("replyId"),
        media_ids=body.get("fileIds"),
        poll=body.get("poll"),
    )
    return {"createdNote": masto_status_to_mk_note(status)}


@router.post("/notes/delete")
async def api_notes_delete(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    await mk.delete_status(body["noteId"])
    return {}


@router.post("/notes/show")
async def api_notes_show(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    status = await mk.get_status(body["noteId"])
    return masto_status_to_mk_note(status)


@router.post("/notes/renotes")
async def api_notes_renotes(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    note_id = body["noteId"]

    # --- プラン B（採用）: reblogged_by のアカウントから Renote スタブを生成 ---
    # Mastodon の reblogged_by はアカウント一覧のみ返すため、
    # note_converter.mk_renote_stub で Misskey 互換 Renote オブジェクトに変換する。
    accounts = await mk.get_reblogged_by(note_id)
    return [mk_renote_stub(a, note_id) for a in accounts]

    # --- プラン A（コメントアウト）: context の descendants から本物の Renote を返す ---
    # get_context は replies も含むため reblog のみをフィルタする必要がある。
    # descendants 内で reblog.id == note_id のものが renote に相当する。
    #
    # context = await mk.get_context(note_id)
    # renotes = [
    #     masto_status_to_mk_note(s)
    #     for s in context.get("descendants", [])
    #     if s.get("reblog") and s["reblog"].get("id") == note_id
    # ]
    # return renotes


@router.post("/notes/replies")
async def api_notes_replies(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    context = await mk.get_context(body["noteId"])
    return masto_statuses_to_mk_notes(context.get("descendants", []))


@router.post("/notes/search")
async def api_notes_search(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    query = body.get("query", "")
    limit = body.get("limit", 20)
    result = await mk.search(query, type="statuses", limit=limit)
    statuses = result.get("statuses", []) if isinstance(result, dict) else []
    return masto_statuses_to_mk_notes(statuses)


# ---------------------------------------------------------------------------
# /api/notes/reactions
# ---------------------------------------------------------------------------

@router.post("/notes/reactions/create")
async def api_reactions_create(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    reaction = body.get("reaction", "❤")
    # Fedibird API は ":shortcode:" 形式をそのまま受け取る（コロンを剥がさない）
    try:
        status = await mk.add_emoji_reaction(body["noteId"], reaction)
    except Exception:
        status = await mk.favourite(body["noteId"])
    return masto_status_to_mk_note(status)


@router.post("/notes/reactions/delete")
async def api_reactions_delete(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    reaction = body.get("reaction", "❤")
    try:
        status = await mk.remove_emoji_reaction(body["noteId"], reaction)
    except Exception:
        status = await mk.unfavourite(body["noteId"])
    return masto_status_to_mk_note(status)


@router.post("/notes/reactions")
async def api_reactions_list(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    note_id = body.get("noteId", "")
    reaction = body.get("reaction")  # Misskey は特定リアクションを絞り込み指定できる

    def _parse_reacted_by(entries: list, fallback_reaction: str) -> list:
        """
        reacted_by レスポンスを Misskey reactions リスト形式に変換。

        Nekonoverse の reacted_by は
          [{"actor": {account}, "emoji": ":honi:"}, ...]
        という形式で返す。account 配列形式の場合も許容する。
        """
        result = []
        for entry in entries:
            # {"actor": {...}, "emoji": ":honi:"} 形式
            if "actor" in entry:
                account = entry["actor"]
                reaction = entry.get("emoji") or fallback_reaction
            else:
                # 通常の account オブジェクト形式（フォールバック）
                account = entry
                reaction = fallback_reaction

            account = masto_to_misskey_user_lite(account)
            result.append(
                {
                    "id": account.get("id", ""),
                    # nullを返してきた場合、現在時刻を使う
                    "createdAt": account.get(
                        "created_at",
                        datetime.now(timezone.utc)
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z"),
                    ),
                    "type": reaction,
                    "user": account,
                }
            )
        return result

    if reaction:
        # 特定リアクションのユーザー一覧:
        # GET /api/v1/statuses/{id}/reacted_by?emoji=:shortcode:
        try:
            entries = await mk.get_reacted_by(note_id, reaction)
            return _parse_reacted_by(
                entries if isinstance(entries, list) else [], reaction
            )
        except Exception:
            # reacted_by 未対応サーバーは favourited_by にフォールバック
            accounts = await mk._get(f"statuses/{note_id}/favourited_by")
            return [
                {
                    "id": a.get("id"),
                    # nullを返してきた場合、現在時刻を使う
                    "createdAt": a.get(
                        "created_at",
                        datetime.now(timezone.utc)
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z"),
                    ),
                    "reaction": reaction,
                    "user": masto_to_misskey_user_lite(a),
                }
                for a in (accounts if isinstance(accounts, list) else [])
            ]

    # reaction 未指定: ステータスの emoji_reactions から全リアクション一覧を構築
    status = await mk.get_status(note_id)
    fedibird_reactions = status.get("emoji_reactions") or []
    if fedibird_reactions:
        result = []
        for er in fedibird_reactions:
            rkey, _ = _build_reaction_key(er)
            if not rkey:
                continue
            # account_ids があれば各ユーザーを展開（ID のみで詳細なし）
            if er.get("account_ids"):
                for aid in er["account_ids"]:
                    result.append({"id": aid, "createdAt": "", "reaction": rkey, "user": {"id": aid}})
            else:
                # reacted_by エンドポイントでユーザー情報を取得
                try:
                    entries = await mk.get_reacted_by(note_id, rkey)
                    result.extend(_parse_reacted_by(
                        entries if isinstance(entries, list) else [], rkey
                    ))
                except Exception:
                    # 取得できない場合はカウント分だけダミーエントリ
                    for _ in range(er.get("count", 0)):
                        result.append({"id": "", "createdAt": "", "reaction": rkey, "user": {}})
        return result

    # フォールバック: favourited_by（Fedibird 拡張非対応サーバー）
    accounts = await mk._get(f"statuses/{note_id}/favourited_by")
    return [
        {"id": a.get("id"), "reaction": "❤", "user": masto_to_misskey_user_lite(a)}
        for a in (accounts if isinstance(accounts, list) else [])
    ]

@router.post("/notes/favorites/create")
async def api_favorites_create(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    status = await mk.bookmark(body["noteId"])
    return masto_status_to_mk_note(status)


@router.post("/notes/favorites/delete")
async def api_favorites_delete(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    status = await mk.unbookmark(body["noteId"])
    return masto_status_to_mk_note(status)


# ---------------------------------------------------------------------------
# /api/users
# ---------------------------------------------------------------------------

@router.post("/users/show")
async def api_users_show(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    if "userId" in body:
        account = await mk.get_account(body["userId"])
    else:
        username = body.get("username", "")
        host = body.get("host")
        query = f"{username}@{host}" if host else username
        results = await mk.search_accounts(query, limit=1)
        account = results[0] if results else {}
    return masto_to_misskey_user_detailed(account)


@router.post("/users/search")
async def api_users_search(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    accounts = await mk.search_accounts(body.get("query", ""), limit=body.get("limit", 20))
    return [masto_to_misskey_user_detailed(a) for a in accounts]


@router.post("/users/followers")
async def api_users_followers(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    # 自分自身の account ID を取得（followeeId に使用）
    me = await mk.verify_credentials()
    viewer_id = me.get("id", "")
    accounts = await mk.get_followers(body["userId"], limit=body.get("limit", 40))
    return [
        _mk_follow_relationship(a, viewer_id, is_following=False)
        for a in (accounts if isinstance(accounts, list) else [])
    ]


@router.post("/users/following")
async def api_users_following(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    # 自分自身の account ID を取得（followerId に使用）
    me = await mk.verify_credentials()
    viewer_id = me.get("id", "")
    accounts = await mk.get_following(body["userId"], limit=body.get("limit", 40))
    return [
        _mk_follow_relationship(a, viewer_id, is_following=True)
        for a in (accounts if isinstance(accounts, list) else [])
    ]


@router.post("/users/notes")
async def api_users_notes(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    statuses = await mk.get_account_statuses(body["userId"], limit=body.get("limit", 20))
    return masto_statuses_to_mk_notes(statuses)


# ---------------------------------------------------------------------------
# /api/following
# ---------------------------------------------------------------------------

@router.post("/following/create")
async def api_following_create(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).follow(body["userId"])


@router.post("/following/delete")
async def api_following_delete(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).unfollow(body["userId"])


# ---------------------------------------------------------------------------
# /api/blocking
# ---------------------------------------------------------------------------

@router.post("/blocking/create")
async def api_blocking_create(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).block(body["userId"])


@router.post("/blocking/delete")
async def api_blocking_delete(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).unblock(body["userId"])


@router.post("/blocking/list")
async def api_blocking_list(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).get_blocks(limit=body.get("limit", 40))


# ---------------------------------------------------------------------------
# /api/muting
# ---------------------------------------------------------------------------

@router.post("/muting/create")
async def api_muting_create(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).mute(body["userId"])


@router.post("/muting/delete")
async def api_muting_delete(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).unmute(body["userId"])


@router.post("/muting/list")
async def api_muting_list(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).get_mutes(limit=body.get("limit", 40))


# ---------------------------------------------------------------------------
# /api/miauth/{session}/check
# ---------------------------------------------------------------------------

@router.post("/miauth/{session_id}/check")
async def api_miauth_check(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    このプロキシ自身が miAuth 発行元のため、
    上流ではなく DB から session を取得してトークンを返す。
    Misskey 互換レスポンス: {"ok": true, "token": "...", "user": {...}}
    """
    session = await crud.get_miauth_session(db, session_id)

    if session is None or not session.authorized:
        return {"ok": False}

    # セッションに紐付いたOAuthTokenを取得
    from sqlalchemy import select as sa_select

    from app.db.models import OAuthToken
    result = await db.execute(
        sa_select(OAuthToken).where(
            OAuthToken.session_id == session_id,
            OAuthToken.revoked == False,  # noqa
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        return {"ok": False}

    # ユーザー情報を取得
    user = await crud.get_user_by_id(db, session.user_id)
    if user is None:
        return {"ok": False}

    # Misskey互換のuserオブジェクトを構築
    return {
        "ok": True,
        "token": token.access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.display_name or user.username,
            "host": None,
            "avatarUrl": user.avatar_url,
            "isBot": user.is_bot,
            "isLocked": user.is_locked,
            "description": user.bio or "",
            "createdAt": user.created_at.isoformat() if user.created_at else "",
            "followersCount": 0,
            "followingCount": 0,
            "notesCount": 0,
            "emojis": [],
            "fields": [],
        },
    }


# ---------------------------------------------------------------------------
# /api/emojis
# ---------------------------------------------------------------------------

@router.post("/emojis")
async def api_emojis(request: Request, db: AsyncSession = Depends(get_db)):
    """
    カスタム絵文字一覧を返す。
    Mastodon の GET /api/v1/custom_emojis を呼んで Misskey 互換形式に変換する。
    認証不要（ゲストでも取得可能）。
    """
    body = await _body(request)
    token = _token(body, request)

    emojis_raw: list = []
    if token:
        try:
            mk = await _mastodon_client(token, db)
            emojis_raw = await mk.get_custom_emojis()
        except HTTPException:
            pass

    if not emojis_raw:
        # 認証なし / 取得失敗時は上流にゲストで問い合わせ
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.MASTODON_INSTANCE_URL}/api/v1/custom_emojis"
                )
            if resp.status_code == 200:
                emojis_raw = resp.json()
        except Exception:
            emojis_raw = []

    emojis = [
        {
            "name": e.get("shortcode", ""),
            "url": e.get("url", ""),
            "category": e.get("category") or "",
            "aliases": [],
            "host": None,
            "isSensitive": False,
            "roleIdsThatCanBeUsedThisEmojiAsReaction": [],
            "localOnly": False,
        }
        for e in emojis_raw
    ]
    return {"emojis": emojis}



# ---------------------------------------------------------------------------
# /api/admin/*  — 管理者 API（admin_restricted フラグで一時無効化可能）
# ---------------------------------------------------------------------------

@router.post("/admin/show-users")
async def api_admin_show_users(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    accounts = await mk._get("admin/accounts", params={
        "limit": body.get("limit", 20),
        "origin": body.get("origin", "local"),
    })
    return accounts if isinstance(accounts, list) else []


@router.post("/admin/show-user")
async def api_admin_show_user(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    return await mk._get(f"admin/accounts/{body['userId']}")


@router.post("/admin/suspend-user")
async def api_admin_suspend_user(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    await mk._post(f"admin/accounts/{body['userId']}/action",
                   json={"type": "suspend"})
    return {}


@router.post("/admin/unsuspend-user")
async def api_admin_unsuspend_user(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    await mk._post(f"admin/accounts/{body['userId']}/unsuspend")
    return {}


@router.post("/admin/get-index-stats")
async def api_admin_index_stats(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    # Mastodon に同等エンドポイントなし → ダミーレスポンス
    return []


@router.post("/admin/get-table-stats")
async def api_admin_table_stats(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    return {}


@router.post("/admin/server-info")
async def api_admin_server_info(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    return {"machine": "proxy", "cpu": {}, "mem": {}, "fs": {}, "net": {}}


@router.post("/admin/abuse-user-reports")
async def api_admin_abuse_reports(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    try:
        reports = await mk._get("admin/reports", params={"limit": body.get("limit", 20)})
        return reports if isinstance(reports, list) else []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# /api/users/lists  & /api/notes/user-list-timeline
# ---------------------------------------------------------------------------

def _masto_list_to_mk(masto: dict) -> dict:
    """Mastodon list オブジェクト → Misskey UserList"""
    return {
        "id": masto.get("id", ""),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "name": masto.get("title", ""),
        "userIds": [],
        "isPublic": False,
    }


@router.post("/users/lists/list")
async def api_users_lists_list(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    lists = await mk.get_lists()
    return [_masto_list_to_mk(lst) for lst in lists]


@router.post("/users/lists/show")
async def api_users_lists_show(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    lst = await mk.get_list(body["listId"])
    return _masto_list_to_mk(lst)


@router.post("/users/lists/create")
async def api_users_lists_create(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    lst = await mk.create_list(body.get("name", ""))
    return _masto_list_to_mk(lst)


@router.post("/users/lists/update")
async def api_users_lists_update(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    lst = await mk.update_list(body["listId"], body.get("name", ""))
    return _masto_list_to_mk(lst)


@router.post("/users/lists/delete")
async def api_users_lists_delete(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    await mk.delete_list(body["listId"])
    return {}


@router.post("/users/lists/push")
async def api_users_lists_push(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    await mk.add_list_accounts(body["listId"], [body["userId"]])
    return {}


@router.post("/users/lists/pull")
async def api_users_lists_pull(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    await mk.remove_list_accounts(body["listId"], [body["userId"]])
    return {}


@router.post("/users/lists/get-memberships")
async def api_users_lists_get_memberships(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    accounts = await mk.get_list_accounts(body["listId"], limit=body.get("limit", 30))
    return [masto_to_misskey_user_detailed(a) for a in accounts]


@router.post("/notes/user-list-timeline")
async def api_notes_user_list_timeline(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    statuses = await mk.list_timeline(
        body["listId"],
        limit=body.get("limit", 20),
        max_id=body.get("untilId"),
        since_id=body.get("sinceId"),
    )
    return masto_statuses_to_mk_notes(statuses)


# ---------------------------------------------------------------------------
# 未対応機能（アンテナ・チャンネル・クリップ）
# ---------------------------------------------------------------------------

def _unavailable_error(feature: str) -> HTTPException:
    return HTTPException(status_code=400, detail={
        "error": {
            "message": f"{feature} is not available on this server.",
            "code": "UNAVAILABLE",
            "id": "a09c74c0-5b4e-4d60-9a6e-8b1e5a3c2d4f",
            "kind": "client",
        }
    })


# アンテナ
@router.post("/antennas/list")
@router.post("/antennas/show")
@router.post("/antennas/create")
@router.post("/antennas/update")
@router.post("/antennas/delete")
@router.post("/antennas/notes")
async def api_antennas_unavailable(request: Request):
    raise _unavailable_error("Antenna")


# チャンネル
@router.post("/channels/timeline")
@router.post("/channels/show")
@router.post("/channels/create")
@router.post("/channels/update")
@router.post("/channels/follow")
@router.post("/channels/unfollow")
@router.post("/channels/featured")
@router.post("/channels/my-favorites")
@router.post("/channels/search")
async def api_channels_unavailable(request: Request):
    raise _unavailable_error("Channel")


# クリップ
@router.post("/clips/list")
@router.post("/clips/show")
@router.post("/clips/create")
@router.post("/clips/update")
@router.post("/clips/delete")
@router.post("/clips/add-note")
@router.post("/clips/remove-note")
@router.post("/clips/notes")
@router.post("/clips/my-favorites")
async def api_clips_unavailable(request: Request):
    raise _unavailable_error("Clip")
