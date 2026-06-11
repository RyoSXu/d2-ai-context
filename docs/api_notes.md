# Bungie API Notes

This MVP uses read-only Bungie endpoints:

- `GET /Platform/Destiny2/Manifest/`
- `GET /Platform/User/GetMembershipsForCurrentUser/`
- `GET /Platform/Destiny2/{membershipType}/Profile/{destinyMembershipId}/`

`DestinyComponentType` values are taken from the official Bungie.Net API docs:

- Profiles: 100
- ProfileInventories: 102
- ProfileCurrencies: 103
- ProfileProgression: 104
- Characters: 200
- CharacterInventories: 201
- CharacterProgressions: 202
- CharacterEquipment: 205
- CharacterLoadouts: 206
- ItemInstances: 300
- ItemObjectives: 301
- ItemPerks: 302
- ItemStats: 304
- ItemSockets: 305
- ItemReusablePlugs: 310
- Collectibles: 800
- Records: 900
- Craftables: 1300

The tool never calls item transfer, equip, purchase, socket insertion, dismantle, or other account mutation endpoints.

