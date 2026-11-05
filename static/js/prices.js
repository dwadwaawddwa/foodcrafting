document.getElementById("nav").innerHTML = nav("prices");
mountParamsPanel("params");
const $ = s => document.querySelector(s);
let selected = null;

// ---- Fish Sauce ----
async function calcSauce(){
  const params = getParams();
  $("#sauceOut").innerHTML = `<span class="spinner"></span> Calcul…`;
  const levels = [["T1_FISHSAUCE_LEVEL1","Basique (.1)"],["T1_FISHSAUCE_LEVEL2","Fancy (.2)"],["T1_FISHSAUCE_LEVEL3","Special (.3)"]];
  const results = await Promise.all(levels.map(([id])=>apiPost("/api/calc",{product_id:id,enchant:0,cities:params.cities,params})));
  const cards = results.map((d,i)=>{
    const r = d.route;
    const ing = d.ingredients.map(x=>`${x.name} ×${x.count}`).join(", ");
    return `<div class="food">
      <img class="itm" src="${d.img}">
      <div class="meta">
        <div class="nm">${levels[i][1]} — ${d.name}</div>
        <div class="small muted">${ing}</div>
        ${r?`<div class="small">Coût unité: <b>${fmt(r.buy_cost/r.amount)}</b> · meilleure ville d'achat: <b>${r.buy_city}</b></div>
        <div class="small">Prix vente marché (${r.sell_city}): ${fmt(r.sell_unit)}</div>`:
        `<div class="small neg">Pas de prix marché</div>`}
      </div></div>`;
  }).join("");
  $("#sauceOut").innerHTML = `<div class="grid-cards">${cards}</div>
    <div class="hint">Le « coût unité » est le prix de revient si tu crafts la sauce toi-même (poisson + algue). Compare-le au prix de vente marché.</div>`;
}
$("#sauceBtn").addEventListener("click", calcSauce);

// ---- Recherche item + autocomplete ----
let searchT=null;
$("#itemSearch").addEventListener("input", e=>{
  clearTimeout(searchT);
  searchT = setTimeout(async ()=>{
    const q=e.target.value.trim();
    if(q.length<2){ $("#sugg").style.display="none"; return; }
    const d = await apiGet("/api/items?q="+encodeURIComponent(q));
    $("#sugg").innerHTML = d.items.map(i=>`
      <div class="food" style="padding:6px;cursor:pointer" data-id="${i.item_id}" data-name="${i.name}">
        <img class="itm sm" src="${i.img}" loading="lazy">
        <div class="meta"><div class="nm" style="font-size:14px">${i.name}</div>
        <div class="small muted">${i.item_id}</div></div>
      </div>`).join("") || `<div class="small muted" style="padding:8px">Aucun item</div>`;
    $("#sugg").style.display="block";
  }, 250);
});
$("#sugg").addEventListener("click", e=>{
  const row=e.target.closest("[data-id]"); if(!row)return;
  selected = {id:row.dataset.id, name:row.dataset.name};
  $("#itemSearch").value = row.dataset.name;
  $("#selItem").innerHTML = `Sélectionné: <b>${selected.name}</b> (${selected.id})`;
  $("#sugg").style.display="none";
});
document.addEventListener("click", e=>{ if(!e.target.closest("#itemSearch,#sugg")) $("#sugg").style.display="none"; });

$("#addBtn").addEventListener("click", async ()=>{
  if(!selected){ toast("Choisis d'abord un item"); return; }
  const buy = parseFloat($("#mBuy").value)||null;
  const sell = parseFloat($("#mSell").value)||null;
  await apiPost("/api/manual", {item_id:selected.id, buy, sell});
  toast("Prix enregistré");
  $("#mBuy").value=""; $("#mSell").value=""; selected=null; $("#itemSearch").value=""; $("#selItem").innerHTML="";
  loadManual();
});

async function loadManual(){
  const d = await apiGet("/api/manual");
  if(!d.manual.length){ $("#manualList").innerHTML = `<div class="muted small">Aucun prix manuel enregistré.</div>`; return; }
  $("#manualList").innerHTML = `<table>
    <thead><tr><th>Item</th><th class="num">Achat</th><th class="num">Vente</th><th></th></tr></thead>
    <tbody>${d.manual.map(m=>`<tr>
      <td><img class="itm sm" src="${m.img}" loading="lazy"> ${m.name} <span class="small muted">${m.item_id}</span></td>
      <td class="num">${m.buy?fmt(m.buy):"—"}</td>
      <td class="num">${m.sell?fmt(m.sell):"—"}</td>
      <td class="num"><button class="ghost" data-del="${m.item_id}">✕</button></td>
    </tr>`).join("")}</tbody></table>`;
  $("#manualList").querySelectorAll("[data-del]").forEach(b=>b.addEventListener("click", async ()=>{
    await apiPost("/api/manual", {item_id:b.dataset.del, buy:null, sell:null});
    toast("Supprimé"); loadManual();
  }));
}
loadManual();
