import { getBlocklist, setBlocklist } from "./storage.js";

async function render() {
  const domains = await getBlocklist();
  const list = document.getElementById("list");
  list.innerHTML = "";
  domains.forEach((domain, i) => {
    const li = document.createElement("li");
    li.textContent = domain;
    const btn = document.createElement("button");
    btn.textContent = "Remove";
    btn.onclick = () => removeDomain(i);
    li.appendChild(btn);
    list.appendChild(li);
  });
}

async function removeDomain(index) {
  const domains = await getBlocklist();
  domains.splice(index, 1);
  await setBlocklist(domains);
  render();
}

document.getElementById("add").onclick = async () => {
  const input = document.getElementById("site").value.trim();
  if (!input) return;
  const domains = await getBlocklist();
  domains.push(input);
  await setBlocklist(domains);
  document.getElementById("site").value = "";
  render();
};

render();
