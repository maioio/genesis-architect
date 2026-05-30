// Tests from PITFALLS.md Pitfall 1 - Implementation block
// Key test: 100 domains must ALL be retrievable (sync storage would silently truncate at ~80)

const mockLocal = {};
const mockSync = {};

global.chrome = {
  storage: {
    local: {
      get: async (key) => ({ [key]: mockLocal[key] }),
      set: async (obj) => Object.assign(mockLocal, obj),
    },
    sync: {
      get: async (key) => ({ [key]: mockSync[key] }),
      set: async (obj) => Object.assign(mockSync, obj),
    }
  }
};

// Must import after mock is set up
const { getBlocklist, setBlocklist, getPrefs, setPrefs } = await import("../src/storage.js");

describe("storage - blocklist uses local, not sync", () => {
  beforeEach(() => {
    delete mockLocal.blocklist;
    delete mockSync.blocklist;
  });

  test("getBlocklist returns empty array by default", async () => {
    expect(await getBlocklist()).toEqual([]);
  });

  test("setBlocklist writes to local storage", async () => {
    await setBlocklist(["reddit.com"]);
    expect(mockLocal.blocklist).toEqual(["reddit.com"]);
    expect(mockSync.blocklist).toBeUndefined();
  });

  // Critical test: sync quota overflow scenario
  test("100 domains are all retrievable (sync would silently truncate)", async () => {
    const domains = Array.from({ length: 100 }, (_, i) => `site${i}.com`);
    await setBlocklist(domains);
    const retrieved = await getBlocklist();
    expect(retrieved).toHaveLength(100);
    expect(retrieved[99]).toBe("site99.com");
  });

  test("setBlocklist throws on non-array input", async () => {
    await expect(setBlocklist("reddit.com")).rejects.toThrow("blocklist must be an array");
  });
});

describe("storage - prefs use sync", () => {
  test("getPrefs returns default theme", async () => {
    const prefs = await getPrefs();
    expect(prefs.theme).toBe("light");
  });

  test("setPrefs writes to sync storage", async () => {
    await setPrefs({ theme: "dark" });
    expect(mockSync.prefs).toEqual({ theme: "dark" });
    expect(mockLocal.prefs).toBeUndefined();
  });
});
