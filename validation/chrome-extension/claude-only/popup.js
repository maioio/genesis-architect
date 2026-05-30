async function load() {
  const { blocklist = [] } = await chrome.storage.sync.get("blocklist");
  const list = document.getElementById("list");
  list.innerHTML = "";
  blocklist.forEach((site, i) => {
    const li = document.createElement("li");
    li.textContent = site;
    const btn = document.createElement("button");
    btn.textContent = "Remove";
    btn.onclick = () => remove(i);
    li.appendChild(btn);
    list.appendChild(li);
  });
}

async function remove(index) {
  const { blocklist = [] } = await chrome.storage.sync.get("blocklist");
  blocklist.splice(index, 1);
  await chrome.storage.sync.set({ blocklist });
  load();
}

document.getElementById("add").onclick = async () => {
  const site = document.getElementById("site").value.trim();
  if (!site) return;
  const { blocklist = [] } = await chrome.storage.sync.get("blocklist");
  blocklist.push(site);
  await chrome.storage.sync.set({ blocklist });
  load();
};

load();
