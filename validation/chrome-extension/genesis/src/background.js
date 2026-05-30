// Architecture note: keepalive alarm prevents SW termination mid-update
// Avoids: Pitfall 2 - MV3 service worker terminated after 30s inactivity

import { getBlocklist } from "./storage.js";
import { applyBlocklist } from "./ruleManager.js";

chrome.runtime.onInstalled.addListener(async () => {
  chrome.alarms.create("keepalive", { periodInMinutes: 0.4 });
  const domains = await getBlocklist();
  await applyBlocklist(domains);
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "keepalive") return;
});

chrome.storage.onChanged.addListener(async (changes, area) => {
  if (area === "local" && changes.blocklist) {
    await applyBlocklist(changes.blocklist.newValue ?? []);
  }
});
