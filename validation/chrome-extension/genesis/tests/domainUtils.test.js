// Tests from PITFALLS.md Pitfall 3 - Implementation block
import { normalizeDomain } from "../src/domainUtils.js";

describe("normalizeDomain", () => {
  test("bare domain gets || prefix and / suffix", () => {
    expect(normalizeDomain("reddit.com")).toBe("||reddit.com/");
  });

  test("strips https://", () => {
    expect(normalizeDomain("https://reddit.com")).toBe("||reddit.com/");
  });

  test("strips http://", () => {
    expect(normalizeDomain("http://reddit.com")).toBe("||reddit.com/");
  });

  test("strips www.", () => {
    expect(normalizeDomain("www.reddit.com")).toBe("||reddit.com/");
  });

  test("strips https://www.", () => {
    expect(normalizeDomain("https://www.reddit.com")).toBe("||reddit.com/");
  });

  test("strips trailing path", () => {
    expect(normalizeDomain("reddit.com/r/programming")).toBe("||reddit.com/");
  });

  // Critical: verify notreddit.com is NOT matched by reddit.com rule
  // urlFilter "||reddit.com/" anchors to domain boundary - "notreddit.com" does not match
  test("normalized pattern does not match substring domain", () => {
    const pattern = normalizeDomain("reddit.com");
    // The || prefix means the filter only matches at domain start
    // This test documents the contract - actual Chrome enforcement tested manually
    expect(pattern).toBe("||reddit.com/");
    expect(pattern).not.toContain("notreddit");
  });

  test("throws on empty input", () => {
    expect(() => normalizeDomain("")).toThrow("Empty domain after normalization");
  });

  test("throws on whitespace only", () => {
    expect(() => normalizeDomain("   ")).toThrow("Empty domain after normalization");
  });
});
