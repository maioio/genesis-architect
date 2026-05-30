// Tests from PITFALLS.md Pitfall 2 - Implementation block
// Key test: retry logic applies rule on 3rd attempt after 2 failures

let updateCallCount = 0;
let updateShouldFailUntil = 0;

global.chrome = {
  declarativeNetRequest: {
    getDynamicRules: async () => [],
    updateDynamicRules: async () => {
      updateCallCount++;
      if (updateCallCount <= updateShouldFailUntil) {
        throw new Error("SW not ready");
      }
    }
  }
};

const { applyBlocklist } = await import("../src/ruleManager.js");

describe("ruleManager - retry on SW termination", () => {
  beforeEach(() => {
    updateCallCount = 0;
    updateShouldFailUntil = 0;
  });

  test("succeeds on first attempt when Chrome is ready", async () => {
    await applyBlocklist(["reddit.com"]);
    expect(updateCallCount).toBe(1);
  });

  test("retries and succeeds on 2nd attempt", async () => {
    updateShouldFailUntil = 1;
    await applyBlocklist(["reddit.com"]);
    expect(updateCallCount).toBe(2);
  });

  // Critical: SW termination causes 2 failures - must succeed on 3rd
  test("retries and succeeds on 3rd attempt after 2 SW termination failures", async () => {
    updateShouldFailUntil = 2;
    await applyBlocklist(["reddit.com"]);
    expect(updateCallCount).toBe(3);
  });

  test("throws after 3 failures (does not retry forever)", async () => {
    updateShouldFailUntil = 3;
    await expect(applyBlocklist(["reddit.com"])).rejects.toThrow("SW not ready");
    expect(updateCallCount).toBe(3);
  });
});

describe("ruleManager - urlFilter format", () => {
  let capturedRules = [];
  beforeEach(() => {
    capturedRules = [];
    chrome.declarativeNetRequest.updateDynamicRules = async ({ addRules }) => {
      capturedRules = addRules;
    };
    updateCallCount = 0;
  });

  test("urlFilter uses || prefix and / suffix for domain anchoring", async () => {
    await applyBlocklist(["reddit.com"]);
    expect(capturedRules[0].condition.urlFilter).toBe("||reddit.com/");
  });
});
