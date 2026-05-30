chrome.storage.onChanged.addListener((changes) => {
  if (changes.blocklist) {
    updateRules(changes.blocklist.newValue);
  }
});

async function updateRules(blocklist = []) {
  const existingRules = await chrome.declarativeNetRequest.getDynamicRules();
  const removeIds = existingRules.map(r => r.id);

  const addRules = blocklist.map((domain, i) => ({
    id: i + 1,
    priority: 1,
    action: { type: "block" },
    condition: { urlFilter: domain, resourceTypes: ["main_frame"] }
  }));

  await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: removeIds, addRules });
}
