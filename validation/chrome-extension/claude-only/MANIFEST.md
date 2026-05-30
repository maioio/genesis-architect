# Claude Only - Chrome Extension Site Blocker - Manifest

## Files created
- manifest.json (MV3)
- background.js
- popup.html
- popup.js
- rules.json

## Tests written
- None

## Security measures included
- None

## Error handling included
- None

## Latent bugs
- chrome.storage.sync quota silently truncates blocklist >80 entries
- Service worker termination drops rule update (site "blocked" in UI but not actually blocked)
- urlFilter "reddit.com" also blocks "notreddit.com" (substring match)
- No secret scan gate
