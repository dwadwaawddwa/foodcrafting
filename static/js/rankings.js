document.getElementById("nav").innerHTML = nav("rank");
mountParamsPanel("params");
const $ = s => document.querySelector(s);
let META=null, SORT="profit", VIEW="cards";
const sel = { category:"meal", tiers:new Set(), enchants:new Set(), families:new Set() };

function chip(v,l,on){ return `<span class="chip ${on?'on':''}" data-v="${v}">${l}</span>`; }

async function init(){
  META = await apiGet("/api/meta");
  $("#catChips").innerHTML = [["meal","Repas"],["sauce","Sauce"],["refined","Raffiné"],["all","Tout"]]
    .map(([v,l])=>chip(v,l,v==="meal")).join("");
  $("#tierChips").innerHTML = META.tiers.map(t=>chip(t,"T"+t,false)).join("");
  $("#enchChips").innerHTML = [0,1,2,3].map(e=>chip(e,e===0?".0":"."+e,false)).join("");
  updateFamilies();

  $("#catChips").addEventListener("click",e=>{
    const c=e.target.closest(".chip"); if(!c)return;
    $("#catChips").querySelectorAll(".chip").forEach(x=>x.classList.remove("on"));
    c.classList.add("on"); sel.category=c.dataset.v; updateFamilies();
  });
  multi("#tierChips", sel.tiers, parseInt);
  multi("#enchChips", sel.enchants, parseInt);
  $("#famChips").addEventListener("click",e=>{
    const c=e.target.closest(".chip"); if(!c)return;
    c.classList.toggle("on");
    c.classList.contains("on")?sel.families.add(c.dataset.v):sel.families.delete(c.dataset.v);
  });
  $("#sortSeg").addEventListener("click",e=>{
    const b=e.target.closest("button"); if(!b)return;
    $("#sortSeg").querySelectorAll("button").forEach(x=>x.classList.remove("on"));
    b.classList.add("on"); SORT=b.dataset.v;
  });
  $("#goBtn").addEventListener("click", run);
}

function multi(id,set,conv){
  $(id).addEventListener("click",e=>{
    const c=e.target.closest(".chip"); if(!c)return;
    c.classList.toggle("on");
    const v=conv(c.dataset.v);
    c.classList.contains("on")?set.add(v):set.delete(v);
  });
}

function updateFamilies(){
  const cat=sel.category;
  const fams=[...new Set(META.products.filter(p=>cat==="all"||p.category===cat).map(p=>p.family))].sort();
  sel.families.clear();
  $("#famChips").innerHTML = fams.map(f=>chip(f,f.replace(/_/g," "),false)).join("");
}

async function run(){
  const params=getParams();
  const body={
    category:sel.category,
    tiers:[...sel.tiers], enchants: sel.enchants.size?[...sel.enchants]:null,
    families:[...sel.families], sort:SORT, cities:params.cities, params,
  };
  $("#out").innerHTML=`<div class="card"><span class="spinner"></span> Calcul sur ${params.cities.length} villes… (peut prendre quelques secondes)</div>`;
  const d=await apiPost("/api/rankings", body);
  render(d);
}

function render(d){
  if(!d.rows || !d.rows.length){ $("#out").innerHTML=`<div class="card">Aucun résultat (pas de prix marché). Élargis les filtres ou ajoute des prix manuels.</div>`; return; }
  const toolbar=`<div class="card" style="display:flex;align-items:center;gap:12px">
      <b>${d.count}</b> recettes classées par <b>${labelSort(SORT)}</b>
      <div class="seg" style="margin-left:auto;max-width:220px">
        <button id="vCards" class="${VIEW==='cards'?'on':''}">Cartes</button>
        <button id="vTable" class="${VIEW==='table'?'on':''}">Tableau</button>
      </div></div>`;
  const content = VIEW==="cards"?cards(d.rows):table(d.rows);
  $("#out").innerHTML = toolbar + `<div style="margin-top:14px">${content}</div>`;
  $("#vCards").onclick=()=>{VIEW="cards";render(d);};
  $("#vTable").onclick=()=>{VIEW="table";render(d);};
}
function labelSort(s){return {profit:"profit/craft",roi:"ROI %",profit_per_focus:"profit/focus",profit_per_nutrition:"profit/nutrition"}[s];}

function metric(r){
  if(SORT==="roi") return r.roi+" %";
  if(SORT==="profit_per_focus") return (r.profit_per_focus??"—")+" /focus";
  if(SORT==="profit_per_nutrition") return (r.profit_per_nutrition??"—")+" /nut";
  return fmt(r.profit);
}

function cards(rows){
  return `<div class="grid-cards">`+rows.map(r=>`
    <div class="food">
      <img class="itm" src="${r.img}" loading="lazy">
      <div class="meta">
        <div class="nm">${r.name}</div>
        <div class="small muted">${tierBadge(r.tier,r.enchant)} · ${r.nutrition} nut · ${fmt(r.focus)} focus</div>
        <div class="small">Acheter <b>${r.buy_city}</b> ➜ vendre <b>${r.sell_city}</b></div>
        <div style="margin-top:4px"><span class="big ${r.profit>=0?'pos':'neg'}" style="font-size:19px">${fmt(r.profit)}</span>
          <span class="small muted">/craft · ROI ${r.roi}%</span></div>
      </div>
    </div>`).join("")+`</div>`;
}

function table(rows){
  return `<div class="card" style="overflow-x:auto"><table>
    <thead><tr><th>Plat</th><th>Tier</th><th>Acheter</th><th>Vendre</th>
      <th class="num">Coût</th><th class="num">Revenu net</th><th class="num">Profit</th>
      <th class="num">ROI</th><th class="num">/focus</th><th class="num">/nut</th></tr></thead>
    <tbody>${rows.map(r=>`<tr>
      <td><img class="itm sm" src="${r.img}" loading="lazy"> ${r.name}</td>
      <td>${tierBadge(r.tier,r.enchant)}</td>
      <td>${r.buy_city}</td><td>${r.sell_city}</td>
      <td class="num">${fmt(r.total_cost)}</td>
      <td class="num">${fmt(r.sell_net)}</td>
      <td class="num">${money(r.profit)}</td>
      <td class="num">${r.roi}%</td>
      <td class="num">${r.profit_per_focus??"—"}</td>
      <td class="num">${r.profit_per_nutrition??"—"}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

init();
