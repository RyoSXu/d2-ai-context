from __future__ import annotations

from typing import Any

from .bungie_client import BungieClient, BungieApiError
from .config import PROFILE_DIR, Settings
from .oauth import get_valid_token
from .utils import now_iso, write_json


# Values confirmed from Bungie.Net API Destiny.DestinyComponentType documentation.
DESTINY_COMPONENTS: dict[str, int] = {
    "Profiles": 100,
    "ProfileInventories": 102,
    "ProfileCurrencies": 103,
    "ProfileProgression": 104,
    "Characters": 200,
    "CharacterInventories": 201,
    "CharacterEquipment": 205,
    "CharacterLoadouts": 206,
    "CharacterProgressions": 202,
    "ItemInstances": 300,
    "ItemObjectives": 301,
    "ItemPerks": 302,
    "ItemStats": 304,
    "ItemSockets": 305,
    "ItemReusablePlugs": 310,
    "Collectibles": 800,
    "Records": 900,
    "Craftables": 1300,
}


def get_authenticated_client(settings: Settings) -> BungieClient:
    token = get_valid_token(settings)
    return BungieClient(settings, access_token=token["access_token"])


def get_membership(client: BungieClient) -> dict[str, Any]:
    memberships = client.get_response("/User/GetMembershipsForCurrentUser/", auth=True)
    destiny_memberships = memberships.get("destinyMemberships", [])
    if not destiny_memberships:
        raise RuntimeError("没有识别到 Destiny 2 membership，请确认账号已绑定 Destiny 2。")

    cross_save_type = memberships.get("primaryMembershipId")
    if cross_save_type:
        for membership in destiny_memberships:
            if str(membership.get("membershipId")) == str(cross_save_type):
                return membership
    for membership in destiny_memberships:
        if membership.get("crossSaveOverride"):
            return membership
    return destiny_memberships[0]


def load_profile(settings: Settings) -> dict[str, Any]:
    client = get_authenticated_client(settings)
    membership = get_membership(client)
    membership_type = membership.get("membershipType")
    destiny_membership_id = membership.get("membershipId")
    if not membership_type or not destiny_membership_id:
        raise RuntimeError(f"membershipType 识别失败：{membership}")

    components = ",".join(str(value) for value in DESTINY_COMPONENTS.values())
    path = f"/Destiny2/{membership_type}/Profile/{destiny_membership_id}/"
    try:
        profile = client.get_response(path, auth=True, params={"components": components})
    except BungieApiError as exc:
        raise RuntimeError(
            "GetProfile 失败。某些 component 可能缺少权限或账号隐私设置不允许读取："
            f"{', '.join(DESTINY_COMPONENTS.keys())}。原始错误：{exc}"
        ) from exc

    output = {
        "fetched_at": now_iso(),
        "membership": membership,
        "requested_components": DESTINY_COMPONENTS,
        "profile": profile,
    }
    write_json(PROFILE_DIR / "raw_profile.json", output)
    return output

