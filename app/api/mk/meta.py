"""
/api/meta, /api/stats, /api/emojis, /api/ap/show
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.services.note_converter import masto_status_to_mk_note
from app.services.user_converter import masto_to_misskey_user_detailed
from app.api.mk.helpers import _body, _token, _mastodon_client

router = APIRouter()


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
        "antennaLimit":              0,
        "antennaNotesLimit":         upstream_policies.get("antennaNotesLimit", 200),
        "wordMuteLimit":             upstream_policies.get("wordMuteLimit", 200),
        "webhookLimit":              upstream_policies.get("webhookLimit", 3),
        "clipLimit":                 0,
        "noteEachClipsLimit":        0,
        "userListLimit":             upstream_policies.get("userListLimit", 10),
        "userEachUserListsLimit":    upstream_policies.get("userEachUserListsLimit", 50),
        "rateLimitFactor":           upstream_policies.get("rateLimitFactor", 1),
        "avatarDecorationLimit":     upstream_policies.get("avatarDecorationLimit", 1),
        "canImportAntennas":         upstream_policies.get("canImportAntennas", False),
        "canImportBlocking":         upstream_policies.get("canImportBlocking", False),
        "canImportFollowing":        upstream_policies.get("canImportFollowing", False),
        "canImportMuting":           upstream_policies.get("canImportMuting", False),
        "canImportUserLists":        upstream_policies.get("canImportUserLists", False),
        "chatAvailability":          "unavailable",
        "uploadableFileTypes":       [
            "image/jpeg", "image/png", "image/gif", "image/webp",
            "image/avif", "image/svg+xml",
            "video/mp4", "video/mpeg", "video/webm", "video/quicktime",
            "audio/mpeg", "audio/ogg", "audio/wav", "audio/flac", "audio/aac",
        ],
        "noteDraftLimit":            0,
        "scheduledNoteLimit":        0,
        "watermarkAvailable":        upstream_policies.get("watermarkAvailable", False),
        "fileSizeLimit":             upstream_policies.get("fileSizeLimit", 50),
    }

    upstream_features: dict = upstream.get("features") or {}

    _ltl_setting = settings.ENABLE_LOCAL_TIMELINE.lower()
    if _ltl_setting == "true":
        _ltl_available = True
    elif _ltl_setting == "false":
        _ltl_available = False
    else:
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
        "miauth":                 True,
    }

    upstream_client_opts: dict = upstream.get("clientOptions") or {}
    client_options = {
        "entrancePageStyle":        upstream_client_opts.get("entrancePageStyle", "default"),
        "showTimelineForVisitor":   upstream_client_opts.get("showTimelineForVisitor", False),
        "showActivitiesForVisitor": upstream_client_opts.get("showActivitiesForVisitor", False),
    }

    return {
        "maintainerName":               upstream.get("maintainerName"),
        "maintainerEmail":              upstream.get("maintainerEmail"),
        "version":                      upstream.get("version") or settings.INSTANCE_VERSION,
        "providesTarball":              upstream.get("providesTarball", False),
        "name":                         upstream.get("name") or settings.INSTANCE_TITLE,
        "shortName":                    upstream.get("shortName"),
        "uri":                          upstream.get("uri") or host,
        "description":                  upstream.get("description") or settings.INSTANCE_DESCRIPTION,
        "langs":                        upstream.get("langs") or [],
        "tosUrl":                       upstream.get("tosUrl") or "",
        "repositoryUrl":                upstream.get("repositoryUrl"),
        "feedbackUrl":                  upstream.get("feedbackUrl"),
        "impressumUrl":                 upstream.get("impressumUrl") or "",
        "privacyPolicyUrl":             upstream.get("privacyPolicyUrl") or "",
        "inquiryUrl":                   upstream.get("inquiryUrl"),
        "disableRegistration":          upstream.get("disableRegistration", True),
        "emailRequiredForSignup":       upstream.get("emailRequiredForSignup", False),
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
        "googleAnalyticsMeasurementId": upstream.get("googleAnalyticsMeasurementId"),
        "swPublickey":                  upstream.get("swPublickey"),
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
        "maxNoteTextLength":            upstream.get("maxNoteTextLength", 3000),
        "defaultLightTheme":            upstream.get("defaultLightTheme"),
        "defaultDarkTheme":             upstream.get("defaultDarkTheme"),
        "clientOptions":                client_options,
        "ads":                          upstream.get("ads") or [],
        "notesPerOneAd":                upstream.get("notesPerOneAd", 0),
        "enableEmail":                  upstream.get("enableEmail", False),
        "enableServiceWorker":          upstream.get("enableServiceWorker", False),
        "translatorAvailable":          upstream.get("translatorAvailable", False),
        "serverRules":                  upstream.get("serverRules") or [],
        "policies":                     policies,
        "sentryForFrontend":            upstream.get("sentryForFrontend"),
        "mediaProxy":                   upstream.get("mediaProxy") or f"{host}/proxy",
        "enableUrlPreview":             upstream.get("enableUrlPreview", True),
        "noteSearchableScope":          upstream.get("noteSearchableScope", "local"),
        "federation":                   upstream.get("federation", "all"),
        "cacheRemoteFiles":             upstream.get("cacheRemoteFiles", False),
        "cacheRemoteSensitiveFiles":    upstream.get("cacheRemoteSensitiveFiles", True),
        "requireSetup":                 upstream.get("requireSetup", False),
        "proxyAccountName":             upstream.get("proxyAccountName"),
        "features":                     features,
    }


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


@router.post("/ap/show")
async def api_ap_show(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    uri = body.get("uri", "")
    if not uri:
        raise HTTPException(status_code=400, detail="uri is required")
    mk = await _mastodon_client(token, db)
    result = await mk.search(uri, resolve="true", limit=1)
    statuses = result.get("statuses") or []
    accounts = result.get("accounts") or []
    if statuses:
        return {"type": "Note", "object": masto_status_to_mk_note(statuses[0])}
    if accounts:
        return {"type": "User", "object": masto_to_misskey_user_detailed(accounts[0])}
    raise HTTPException(status_code=404, detail="Not found")
