// Architecture note: retry wrapper + ||domain/ anchor pattern
// Avoids: Pitfall 2 - SW termination drops rule updates
// Avoids: Pitfall 3 - substring urlFilter matches unintended domains

import { normalizeDomain } from "./domainUtils.js";

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 200;

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function applyBlocklist(domains) {
  const existing = await chrome.declarativeNetRequest.getDynamicRules();
  const removeRuleIds = existing.map(r => r.id);

  const addRules = domains.map((domain, i) => ({
    id: i + 1,
    priority: 1,
    action: { type: "block" },
    condition: {
      urlFilter: normalizeDomain(domain),
      resourceTypes: ["main_frame"]
    }
  }));

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds, addRules });
      return;
    } catch (err) {
      if (attempt === MAX_RETRIES) throw err;
      await sleep(RETRY_DELAY_MS);
    }
  }
}
