// Architecture note: || prefix + / suffix anchors to domain boundary
// Avoids: Pitfall 3 - urlFilter substring matching blocks unintended domains

export function normalizeDomain(input) {
  let domain = input.trim().toLowerCase();
  domain = domain.replace(/^https?:\/\//, "");
  domain = domain.replace(/^www\./, "");
  domain = domain.replace(/\/.*$/, "");
  if (!domain) throw new Error("Empty domain after normalization");
  return `||${domain}/`;
}
