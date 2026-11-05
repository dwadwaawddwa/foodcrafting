// Helpers partages + panneau de parametres (persiste en localStorage)
const API = "";
const CITIES_DEFAULT = ["Thetford","Fort Sterling","Lymhurst","Bridgewatch","Martlock","Caerleon","Brecilien"];

const store = {
  get(k, d){ try{ return JSON.parse(localStorage.getItem(k)) ?? d; }catch(e){ return d; } },
  set(k, v){ localStorage.setItem(k, JSON.stringify(v)); },
};

function defaultParams(){
  return {
    buy_mode:"instant", sell_mode:"instant", return_rate:0.152,
    sell_tax:0.04, setup_fee:0.015, station_fee:0, craft_intermediates:true,
    avg_discount:0.05, spec_level:0, extra_fce:0, focus_price:0,
    server:"west", cities:[...CITIES_DEFAULT],
  };
}
function getParams(){ return Object.assign(defaultParams(), store.get("params", {})); }
function saveParams(p){ store.set("params", p); }

function fmt(n){
  if(n===null||n===undefined) return "—";
  const s = Math.round(n).toLocaleString("fr-FR");
  return s;
}
function money(n, cls=true){
  if(n===null||n===undefined) return '<span class="muted">—</span>';
  const c = cls ? (n>=0?"pos":"neg") : "";
  return `<span class="${c}">${fmt(n)}</span>`;
}
function tierBadge(t,e){ return `<span class="tier">T${t}${e?`<span class="ench">.${e}</span>`:""}</span>`; }

async function apiGet(path){ const r = await fetch(API+path); return r.json(); }
async function apiPost(path, body){
  const r = await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  return r.json();
}

function toast(msg){
  let t = document.querySelector(".toast");
  if(!t){ t=document.createElement("div"); t.className="toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove("show"),2200);
}

// Panneau de parametres reutilisable — retourne un objet {read()} et se dessine dans elId
function mountParamsPanel(elId, onChange){
  const p = getParams();
  const el = document.getElementById(elId);
  const seg = (name,opts)=>`<div class="seg" data-seg="${name}">`+
    opts.map(([v,l])=>`<button data-v="${v}" class="${p[name]===v?'on':''}">${l}</button>`).join("")+`</div>`;
  el.innerHTML = `
    <label class="f">Achat des ingrédients</label>
    ${seg("buy_mode",[["instant","Instant."],["order","Ordre achat"],["avg14","Moy. 14j"]])}
    <div id="avgWrap" style="margin-top:6px;${p.buy_mode==='avg14'?'':'display:none'}">
      <label class="f" style="margin-top:4px">Décote sous la moyenne 14j (%)</label>
      <input type="number" id="avgDisc" value="${Math.round(p.avg_discount*100)}" min="0" max="50" step="1">
      <div class="hint">Achat estimé = prix moyen 14 jours de la ville − x %.</div>
    </div>
    <label class="f">Vente du produit</label>
    ${seg("sell_mode",[["instant","Instantané (buy order)"],["order","Ordre de vente"]])}
    <label class="f">Taux de retour ressources (cuisine)</label>
    <div class="row">
      <select id="rrSel">
        <option value="0">0 % (aucun)</option>
        <option value="0.152">15,2 % — Ville royale (sans focus)</option>
        <option value="0.435">43,5 % — Ville royale + focus</option>
        <option value="0.248">24,8 % — Caerleon (sans focus)</option>
        <option value="0.479">47,9 % — Caerleon + focus</option>
        <option value="0.528">52,8 % — Caerleon + focus + gold day</option>
      </select>
    </div>
    <div class="hint">Seule Caerleon bonus la food (+15 %). La spé ne change pas le RRR (elle réduit le focus).</div>
    <label class="f">Taxe de vente</label>
    ${seg("sell_tax_prem",[["prem","Premium 4%"],["nonprem","Non-prem 8%"]])}
    <label class="f">Frais station (silver / craft)</label>
    <input type="number" id="stationFee" value="${p.station_fee}" min="0" step="10">
    <label class="f"><input type="checkbox" id="craftInter" ${p.craft_intermediates?"checked":""} style="width:auto"> Crafter les intermédiaires (sauce, pain…)</label>
    <label class="f">Spécialisation du plat (0–100)</label>
    <div class="row">
      <input type="number" id="specLevel" value="${p.spec_level}" min="0" max="100" step="1">
      <input type="number" id="extraFce" value="${p.extra_fce}" min="0" step="500" title="FCE bonus (mutuel autres plats spé)" placeholder="FCE bonus">
    </div>
    <div class="hint" id="fceHint"></div>
    <label class="f">Valeur du focus (silver/point, optionnel)</label>
    <input type="number" id="focusPrice" value="${p.focus_price}" min="0" step="1">
    <label class="f">Serveur</label>
    <select id="serverSel">
      <option value="west">Amérique (west)</option>
      <option value="europe">Europe</option>
      <option value="east">Asie (east)</option>
    </select>
    <label class="f">Villes analysées</label>
    <div class="chips" id="cityChips"></div>
  `;
  el.querySelector("#rrSel").value = String(p.return_rate);
  el.querySelector("#serverSel").value = p.server;
  el.querySelectorAll('[data-seg="sell_tax_prem"] button').forEach(b=>{
    b.classList.toggle("on", (b.dataset.v==="prem")===(p.sell_tax<=0.05));
  });
  const chips = el.querySelector("#cityChips");
  chips.innerHTML = CITIES_DEFAULT.map(c=>`<span class="chip ${p.cities.includes(c)?'on':''}" data-city="${c}">${c}</span>`).join("");

  function persist(){
    const np = getParams();
    np.buy_mode = el.querySelector('[data-seg="buy_mode"] .on').dataset.v;
    np.sell_mode = el.querySelector('[data-seg="sell_mode"] .on').dataset.v;
    np.return_rate = parseFloat(el.querySelector("#rrSel").value);
    np.sell_tax = el.querySelector('[data-seg="sell_tax_prem"] .on').dataset.v==="prem"?0.04:0.08;
    np.station_fee = parseFloat(el.querySelector("#stationFee").value)||0;
    np.craft_intermediates = el.querySelector("#craftInter").checked;
    np.avg_discount = (parseFloat(el.querySelector("#avgDisc").value)||0)/100;
    np.spec_level = Math.max(0,Math.min(100,parseInt(el.querySelector("#specLevel").value)||0));
    np.extra_fce = parseFloat(el.querySelector("#extraFce").value)||0;
    np.focus_price = parseFloat(el.querySelector("#focusPrice").value)||0;
    const fce = np.spec_level*250 + np.extra_fce;
    const mult = Math.pow(0.5, fce/10000);
    el.querySelector("#fceHint").innerHTML = `FCE ${fce.toLocaleString("fr-FR")} → focus × <b>${mult.toFixed(3)}</b> (÷${(1/mult).toFixed(2)}). 250 FCE/niveau + ~30/niveau par autre plat spé.`;
    np.server = el.querySelector("#serverSel").value;
    np.cities = [...chips.querySelectorAll(".chip.on")].map(c=>c.dataset.city);
    if(np.cities.length===0){ np.cities=[...CITIES_DEFAULT]; chips.querySelectorAll(".chip").forEach(c=>c.classList.add("on")); }
    el.querySelector("#avgWrap").style.display = np.buy_mode==="avg14" ? "" : "none";
    saveParams(np);
    if(onChange) onChange(np);
  }
  el.querySelectorAll(".seg").forEach(s=>s.addEventListener("click",e=>{
    const b=e.target.closest("button"); if(!b)return;
    s.querySelectorAll("button").forEach(x=>x.classList.remove("on")); b.classList.add("on"); persist();
  }));
  chips.addEventListener("click",e=>{ const c=e.target.closest(".chip"); if(!c)return; c.classList.toggle("on"); persist(); });
  ["#rrSel","#stationFee","#craftInter","#serverSel","#avgDisc","#specLevel","#extraFce","#focusPrice"]
    .forEach(sel=>el.querySelector(sel).addEventListener("change",persist));
  persist();  // initialise l'indice FCE
  return { read:getParams };
}

// Barre de navigation
function nav(active){
  return `<header class="top">
    <div class="brand">🍲 Albion Food Craft<small>PROFIT & ROUTES</small></div>
    <nav class="tabs">
      <a href="/index.html" class="${active==='calc'?'active':''}">Calculateur</a>
      <a href="/rankings.html" class="${active==='rank'?'active':''}">Classement rentabilité</a>
      <a href="/prices.html" class="${active==='prices'?'active':''}">Prix manuels & Fish Sauce</a>
    </nav>
  </header>`;
}
