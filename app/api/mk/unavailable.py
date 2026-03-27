"""
未対応機能（アンテナ・チャンネル・クリップ）のスタブ。
全エンドポイントが 400 UNAVAILABLE を返す。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _unavailable_error(feature: str) -> HTTPException:
    return HTTPException(status_code=400, detail={
        "error": {
            "message": f"{feature} is not available on this server.",
            "code": "UNAVAILABLE",
            "id": "a09c74c0-5b4e-4d60-9a6e-8b1e5a3c2d4f",
            "kind": "client",
        }
    })


@router.post("/antennas/list")
@router.post("/antennas/show")
@router.post("/antennas/create")
@router.post("/antennas/update")
@router.post("/antennas/delete")
@router.post("/antennas/notes")
async def api_antennas_unavailable(request: Request):
    raise _unavailable_error("Antenna")


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
