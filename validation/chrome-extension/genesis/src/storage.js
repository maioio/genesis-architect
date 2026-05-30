// Architecture note: blocklist -> local (10MB), prefs -> sync (small prefs only)
// Avoids: Pitfall 1 - chrome.storage.sync quota silently truncates lists > ~80 entries

export async function getBlocklist() {
  const result = await chrome.storage.local.get("blocklist");
  return result.blocklist ?? [];
}

export async function setBlocklist(domains) {
  if (!Array.isArray(domains)) throw new TypeError("blocklist must be an array");
  await chrome.storage.local.set({ blocklist: domains });
}

export async function getPrefs() {
  const result = await chrome.storage.sync.get("prefs");
  return result.prefs ?? { theme: "light" };
}

export async function setPrefs(prefs) {
  await chrome.storage.sync.set({ prefs });
}
