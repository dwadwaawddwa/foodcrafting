document.getElementById("nav").innerHTML = nav("calc");
mountParamsPanel("params");

let META = null;
const $ = s => document.querySelector(s);
const CATLABEL = {meal:"Repas", sauce:"Sauce", refined:"Raffiné"};

async function init(){
  META = await apiGet("/api/meta");
  const sel = $("#product");
  const groups = {};
  META.products.forEach(p=>{ (groups[p.category] ||= []).push(p); });
  sel.innerHTML = Object.entries(groups).map(([cat,items])=>
    `<optgroup label="${CATLABEL[cat]||cat}">`+
    items.map(p=>`<option value="${p.product_id}">T${p.tier} — ${p.name}</option>`).join("")+
    `</optgroup>`
  ).join("");
  sel.addEventListener("change", fillEnchant);
  // recette par defaut : une salade poisson T4 si dispo
  const def = META.products.find(p=>p.product_id==="T4_MEAL_SALAD_FISH") || META.products.find(p=>p.category==="meal");
  if(def) sel.value = def.product_id;
  fillEnchant();
}

function fillEnchant(){
  const pid = $("#product").value;
  const p = META.products.find(x=>x.product_id===pid);
  const es = $("#enchant");
  es.innerHTML = p.enchants.map(e=>`<option value="${e}">${e===0?"Base (.0)":"."+e}</option>`).join("");
}

async function run(){
  const params = getParams();
  const body = {
    product_id: $("#product").value,
    enchant: parseInt($("#enchant").value),
    cities: params.cities,
    params,
  };
  $("#result").innerHTML = `<div class="card"><span class="spinner"></span> Récupération des prix sur ${params.cities.length} villes…</div>`;
  const d = await apiPost("/api/calc", body);
  render(d);
}

function render(d){
  if(d.error){ $("#result").innerHTML = `<div class="card neg">Erreur: ${d.error}</div>`; return; }
  const r = d.route;
  const shop = d.shopping;
  const ingRows = shop.rows.map(i=>`
    <tr>
      <td><img class="itm sm" src="${i.img}" loading="lazy"> ${i.name}
        ${i.crafted?'<span class="badge">crafté</span>':''}</td>
      <td class="num">${i.count}</td>
      <td>${i.city?`<b style="color:var(--gold2)">${i.city}</b>`:'<span class="neg">non coté</span>'}</td>
      <td class="num">${i.unit===null?'<span class="neg">?</span>':fmt(i.unit)}</td>
      <td class="num">${i.line===null?'<span class="neg">?</span>':fmt(i.line)}</td>
    </tr>`).join("");

  const ingTotal = shop.total;
  const missing = shop.missing;

  const header = `
    <div style="display:flex;gap:16px;align-items:center">
      <img class="itm" style="width:72px;height:72px" src="${d.img}">
      <div>
        <h2 style="margin:0;border:none">${tierBadge(d.tier,d.enchant)} ${d.name}</h2>
        <div class="muted small">${d.name_en} · IP ${d.item_power} · ${d.nutrition} nutrition · focus ${fmt(d.focus)}${r&&r.eff_focus!==r.base_focus?` → <b class="pos">${fmt(r.eff_focus)}</b> (spé)`:''}</div>
      </div>
      ${r?`<div style="margin-left:auto;text-align:right">
        <div class="l muted small">PROFIT / CRAFT</div>
        <div class="big ${r.profit>=0?'pos':'neg'}">${fmt(r.profit)}</div>
        <div class="small muted">ROI ${r.roi}%</div>
      </div>`:''}
    </div>`;

  const routeBlock = r ? `
    <div class="route">
      <div class="step">
        <div class="l muted small">ACHETER LES INGRÉDIENTS À</div>
        <div style="font-size:20px;color:var(--gold2);font-weight:700">${r.buy_city}</div>
        <div class="small">Coût matériaux: <b>${fmt(r.buy_cost)}</b></div>
        <div class="small muted">+ frais station ${fmt(r.station_fee)}</div>
      </div>
      <div class="arrow">➜</div>
      <div class="step">
        <div class="l muted small">CRAFTER PUIS VENDRE À</div>
        <div style="font-size:20px;color:var(--gold2);font-weight:700">${r.sell_city}</div>
        <div class="small">Prix unité: <b>${fmt(r.sell_unit)}</b> × ${r.amount}</div>
        <div class="small muted">Revenu net (taxes déduites): ${fmt(r.sell_net)}</div>
      </div>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="v ${r.profit>=0?'pos':'neg'}">${fmt(r.profit_per_item)}</div><div class="l">Profit / unité</div></div>
      <div class="kpi"><div class="v">${r.profit_per_focus??'—'}</div><div class="l">Profit / focus (effectif)</div></div>
      <div class="kpi"><div class="v">${fmt(r.eff_focus)}</div><div class="l">Focus / craft (spé)</div></div>
      ${r.focus_cost>0?`<div class="kpi"><div class="v">${fmt(r.focus_cost)}</div><div class="l">Coût du focus</div></div>`:''}
      <div class="kpi"><div class="v">${fmt(r.total_cost)}</div><div class="l">Coût total</div></div>
      <div class="kpi"><div class="v">${fmt(r.sell_net)}</div><div class="l">Revenu net</div></div>
    </div>` : `
    <div class="card" style="background:var(--bg2);margin:14px 0">
      <b class="stale">⚠ Produit non coté sur le marché (aucun prix de vente).</b>
      <div class="small muted">Coût de craft estimé des ingrédients : <b>${missing?'incomplet':fmt(ingTotal)+' (avant return rate)'}</b>.
      Ajoute un prix de vente manuel dans l'onglet « Prix manuels » pour obtenir le profit.</div>
    </div>`;

  const cityTables = r ? `
  <div class="layout" style="padding:0;margin-top:18px;grid-template-columns:1fr 1fr">
    <div class="card">
      <h3>Coût d'achat par ville</h3>
      <table><thead><tr><th>Ville</th><th class="num">Coût matériaux</th></tr></thead>
      <tbody>${r.buy_table.map(x=>`<tr><td>${x.city===r.buy_city?'⭐ ':''}${x.city}</td><td class="num">${fmt(x.cost)}</td></tr>`).join("")}</tbody></table>
    </div>
    <div class="card">
      <h3>Revenu net de vente par ville</h3>
      <table><thead><tr><th>Ville</th><th class="num">Unité</th><th class="num">Revenu net</th></tr></thead>
      <tbody>${r.sell_table.map(x=>`<tr><td>${x.city===r.sell_city?'⭐ ':''}${x.city}</td><td class="num">${fmt(x.unit)}</td><td class="num">${fmt(x.net)}</td></tr>`).join("")}</tbody></table>
    </div>
  </div>` : '';

  $("#result").innerHTML = `
  <div class="card">
    ${header}
    ${routeBlock}
    <h3>🛒 Liste d'achat — chaque ingrédient dans sa ville la moins chère</h3>
    <table>
      <thead><tr><th>Ingrédient</th><th class="num">Qté</th><th>Acheter à</th><th class="num">Unité</th><th class="num">Total</th></tr></thead>
      <tbody>${ingRows}</tbody>
    </table>
    <div class="kpis" style="margin-top:12px">
      <div class="kpi"><div class="v">${fmt(shop.total_after_return)}</div><div class="l">Coût achat éclaté (après retour)</div></div>
      ${r?`<div class="kpi"><div class="v">${fmt(r.buy_cost)}</div><div class="l">Coût si tout à ${r.buy_city}</div></div>`:''}
      ${shop.saving_vs_single!==undefined?`<div class="kpi"><div class="v ${shop.saving_vs_single>=0?'pos':''}">${fmt(shop.saving_vs_single)}</div><div class="l">Économie vs mono-ville</div></div>`:''}
    </div>
    <div class="hint">L'achat éclaté suppose que tu passes dans chaque ville (ou via le marché). Le profit affiché en haut utilise l'achat mono-ville (plus réaliste si tu crafts au même endroit).</div>
  </div>
  ${cityTables}`;
}

$("#calcBtn").addEventListener("click", run);
init();
