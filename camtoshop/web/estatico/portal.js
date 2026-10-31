const $ = id => document.getElementById(id);
const LINEA = "15550321707";
const ESTILOS = [{ id: "impacto" }, { id: "color" }, { id: "limpio" }];
const FUENTES = [
  { id: "barlow", css: '900 30px "Barlow Condensed"' },
  { id: "playfair", css: '800 24px "Playfair Display"' },
  { id: "poppins", css: '800 22px Poppins' },
  { id: "caveat", css: '700 30px Caveat' },
];
const PISTAS = [{ id: "energia" }, { id: "calida" }, { id: "elegante" }, { id: "propia" }, { id: "ninguna" }];
const ESCALA_PREVIA = { barlow: [46, 1], playfair: [30, 1.08], poppins: [28, 1.1], caveat: [40, .95] };
const CLARO = "#F7F6F2", OSCURO = "#141414";

let propuestaActual = null, descartados = [];
let yo = null, reels = [], reelAbierto = null, elegidoReel = null, sondeo = null, audio = null, registrando = true;

// --- Comunes ----------------------------------------------------------------------

function avisar(texto) {
  document.querySelectorAll("[data-aviso]").forEach(a => { a.textContent = traducirError(texto || ""); a.hidden = !texto; });
}

async function pedir(ruta, metodo = "GET", datos) {
  const formulario = datos instanceof FormData;
  const r = await fetch(ruta, { method: metodo, headers: datos && !formulario ? { "Content-Type": "application/json" } : {},
                                body: formulario ? datos : datos ? JSON.stringify(datos) : undefined });
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(typeof cuerpo.detail === "string" ? cuerpo.detail : t("error_general")), { estado: r.status });
  return cuerpo;
}

async function hacer(accion) {
  avisar("");
  try { const e = await accion(); if (e && e.nombre) pintar(e); return e; } catch (e) { avisar(e.message); }
}

function crear(etiqueta, propiedades = {}, ...hijos) {
  const n = Object.assign(document.createElement(etiqueta), propiedades);
  n.append(...hijos);
  return n;
}

// --- Colores: la misma regla de contraste del render ---------------------------------

function luz(hex) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => c <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
  return .2126 * r + .7152 * g + .0722 * b;
}
function contraste(a, b) { const [x, y] = [luz(a), luz(b)].sort((m, n) => n - m); return (x + .05) / (y + .05); }
function legible(fondo) { return contraste(fondo, "#FFFFFF") >= contraste(fondo, OSCURO) ? "#FFFFFF" : OSCURO; }
function acento(fondo, ...colores) { return colores.find(c => contraste(c, fondo) >= 2.5) || legible(fondo); }
function tema(m) {
  if (m.estilo === "color") return { fondo: m.primario, texto: legible(m.primario), acento: acento(m.primario, m.secundario) };
  if (m.estilo === "limpio") return { fondo: CLARO, texto: OSCURO, acento: acento(CLARO, m.primario, m.secundario) };
  const sobreFoto = [m.primario, m.secundario].find(c => contraste(c, OSCURO) >= 4.5) || "#FFFFFF";
  return { fondo: "", texto: "#FFFFFF", acento: sobreFoto };
}

// --- Navegación --------------------------------------------------------------------

function ir(vista) {
  ["reels", "detalle", "marca", "conexiones"].forEach(v => { $("v-" + v).hidden = v !== vista; });
  document.querySelectorAll(".pestanas button").forEach(b => {
    const activa = b.dataset.vista === (vista === "detalle" ? "reels" : vista);
    if (activa) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  if (vista !== "detalle") $("video").pause();
  if (audio) { audio.pause(); audio = null; document.querySelectorAll(".oir").forEach(b => { b.textContent = "▶"; }); }
  history.replaceState(null, "", vista === "reels" || vista === "detalle" ? "/portal" : "#" + vista);
  window.scrollTo(0, 0);
}

// --- Estado general ----------------------------------------------------------------

function pintar(e) {
  yo = e;
  $("acceso").hidden = true; $("app").hidden = false;
  $("nombre-negocio").textContent = e.nombre;
  aplicarIdioma();
  $("hacer-reel").href = `https://wa.me/${LINEA}`;
  pintarPasos(e); pintarConexiones(e); pintarLogo(e); pintarCuadro();
  if (sondeo && e.celulares.length > sondeo.antes) { clearInterval(sondeo.id); sondeo = null; $("codigo").hidden = true; }
}

function pintarPasos(e) {
  const pasos = [
    [t("paso_instagram"), !!e.instagram, "conexiones"],
    [t("paso_celular"), e.celulares.length > 0, "conexiones"],
    [t("paso_marca"), e.marca.logo || e.marca.estilo !== "impacto" || e.marca.primario !== "#FFD23F", "marca"],
  ];
  const caja = $("pasos"); caja.textContent = "";
  caja.hidden = pasos.every(p => p[1]);
  caja.append(crear("strong", { textContent: t("pendiente") }));
  pasos.forEach(([texto, hecho, vista]) => {
    const b = crear("button", { textContent: texto, disabled: hecho, onclick: () => ir(vista) });
    if (hecho) b.dataset.hecho = "1";
    caja.append(b);
  });
}

function pintarConexiones(e) {
  $("meta-nota").textContent = e.instagram ? t("instagram_ok", { cuenta: e.instagram, pagina: e.pagina }) : t("instagram_nota");
  $("meta-conectar").hidden = !!e.instagram || e.demo;
  $("meta-quitar").hidden = !e.instagram || e.demo;
  const elegir = $("meta-elegir"); elegir.textContent = "";
  e.por_elegir.forEach(c => elegir.append(crear("button", {
    className: "secundario", textContent: `@${c.instagram}, ${c.pagina}`,
    onclick: () => hacer(() => pedir("/api/portal/cuenta", "POST", { pagina_id: c.id })),
  })));
  const lista = $("celulares"); lista.textContent = "";
  e.celulares.forEach(n => lista.append(crear("div", { className: "celular" }, crear("span", { textContent: "+" + n }),
    crear("button", { className: "enlace", textContent: t("quitar"), onclick: () => hacer(async () => {
      await pedir("/api/portal/celulares/" + n, "DELETE"); return pedir("/api/portal/yo");
    }) }))));
  $("shop-nota").textContent = e.shopify ? `Connected to ${e.shopify}.`
    : "Optional. New products become drafts in your store, and the daily agent can suggest what to promote.";
  $("shop-form").hidden = !!e.shopify || e.demo;
  $("shop-quitar").hidden = !e.shopify || e.demo;
}

// --- Reels ----------------------------------------------------------------------------

function fecha(segundos) {
  return new Date(segundos * 1000).toLocaleDateString(idioma, { month: "short", day: "numeric" });
}

function estadoDe(r) {
  if (r.fase === "error") return [t("estado_error"), ""];
  if (r.fase !== "listo") return [t("estado_haciendo"), ""];
  if (r.publicaciones.length) return [t("estado_publicado"), "vivo"];
  return [t("estado_listo"), ""];
}

async function cargarReels() {
  reels = await pedir("/api/portal/reels");
  const caja = $("reels"); caja.textContent = "";
  $("sin-reels").hidden = reels.length > 0;
  reels.forEach(r => {
    const [texto, clase] = estadoDe(r);
    const marco = crear("span", { className: "marco" });
    if (r.tiene_video && r.fase === "listo") {
      const v = crear("video", { src: `/portal/reels/${r.id}/video#t=1.5`, muted: true, preload: "metadata", playsInline: true, loop: true });
      marco.append(v);
    } else marco.append(crear("span", { className: "pensando", textContent: texto }));
    const tarjeta = crear("button", { className: "tarjeta", onclick: () => abrir(r.id) }, marco,
      crear("b", { textContent: r.nombre }), crear("small", { className: clase, textContent: `${texto}, ${fecha(r.creado)}` }));
    const video = marco.querySelector("video");
    if (video) {
      tarjeta.onmouseenter = () => video.play().catch(() => {});
      tarjeta.onmouseleave = () => video.pause();
    }
    caja.append(tarjeta);
  });
  pintarCuadro();
  const pendiente = reels.some(r => r.fase !== "listo" && r.fase !== "error");
  clearTimeout(cargarReels.espera);
  if (pendiente) cargarReels.espera = setTimeout(() => cargarReels().catch(() => {}), 6000);
  if (reelAbierto) { const r = reels.find(x => x.id === reelAbierto); if (r) pintarDetalle(r); }
}

async function cargarPropuesta() {
  const p = await pedir(`/api/portal/propuesta?idioma=${idioma}&excluir=${encodeURIComponent(descartados.join(","))}`);
  propuestaActual = p.producto || null;
  $("propuesta").hidden = !propuestaActual;
  if (propuestaActual) $("propuesta-texto").textContent = p.texto.replaceAll("*", "");
}

function grupo(titulo, opciones, clase, valor, alCambiar, armar) {
  const caja = crear("div", { className: "opciones " + clase });
  const nombre = titulo + Math.random().toString(36).slice(2);
  opciones.forEach(o => {
    const entrada = crear("input", { type: "radio", name: nombre, value: o.id, checked: o.id === valor, onchange: () => alCambiar(o.id) });
    caja.append(crear("label", { className: "opcion" }, entrada, armar(o)));
  });
  return crear("fieldset", {}, crear("legend", { textContent: titulo }), caja);
}

function tarjetaEstilo(m) {
  return o => {
    const aspecto = tema({ ...m, estilo: o.id });
    const muestra = crear("span", { className: "muestra" });
    muestra.style.background = aspecto.fondo || `url(${productoPrevio()}) center / cover, #555`;
    return crear("span", {}, muestra, crear("b", { textContent: t("estilo_" + o.id) }), crear("em", { textContent: t(`estilo_${o.id}_c`) }));
  };
}

function tarjetaFuente(o) {
  const tipo = crear("span", { className: "tipo", textContent: "$45.000" });
  tipo.style.font = o.css;
  return crear("span", {}, tipo, crear("em", { textContent: t("letra_" + o.id) }));
}

function tarjetaPista(o) {
  const nombre = t("pista_" + o.id);
  const texto = crear("span", {}, crear("b", { textContent: nombre }), crear("em", { textContent: t(`pista_${o.id}_t`) }));
  if (o.id === "ninguna") return crear("span", {}, texto);
  const oir = crear("button", { type: "button", className: "oir", textContent: "▶", ariaLabel: t("reproducir", { pista: nombre }) });
  oir.onclick = ev => {
    ev.preventDefault();
    const sonaba = oir.textContent === "■";
    if (audio) audio.pause();
    document.querySelectorAll(".oir").forEach(b => { b.textContent = "▶"; });
    if (sonaba) return;
    audio = new Audio(`/portal/musica/${o.id}`); audio.play().catch(() => avisar("Upload your track first"));
    audio.onended = () => { oir.textContent = "▶"; };
    oir.textContent = "■";
  };
  return crear("span", { className: "pista" }, texto, oir);
}

function colores(m, alCambiar) {
  const entrada = (titulo, campo) => crear("label", { className: "color" },
    crear("input", { type: "color", value: m[campo], oninput: ev => alCambiar(campo, ev.target.value) }), titulo);
  const caja = crear("div", { className: "opciones dos" }, entrada(t("color_1"), "primario"), entrada(t("color_2"), "secundario"));
  return crear("fieldset", {}, crear("legend", { textContent: t("colores") }), caja);
}

function pistasDisponibles() {
  return PISTAS.filter(p => p.id !== "propia" || yo.marca.musica_propia);
}

function controles(caja, m, cambiar) {
  caja.textContent = "";
  caja.append(
    grupo(t("estilo"), ESTILOS, "tres", m.estilo, v => cambiar("estilo", v, true), tarjetaEstilo(m)),
    colores(m, (c, v) => cambiar(c, v)),
    grupo(t("letra"), FUENTES, "dos", m.fuente, v => cambiar("fuente", v), tarjetaFuente),
    grupo(t("musica"), pistasDisponibles(), "dos", m.musica, v => cambiar("musica", v), tarjetaPista),
  );
}

function abrir(id) {
  reelAbierto = id;
  const r = reels.find(x => x.id === id);
  elegidoReel = { ...yo.marca, ...r.marca };
  $("video").src = r.tiene_video ? `/portal/reels/${id}/video?${Date.now()}` : "";
  controles($("d-controles"), elegidoReel, (c, v) => { elegidoReel[c] = v; });
  pintarDetalle(r);
  ir("detalle");
}

function pintarDetalle(r) {
  $("d-nombre").textContent = r.nombre;
  const [texto] = estadoDe(r);
  $("d-estado").textContent = r.fase === "error" ? `${texto}. ${r.error}` : texto;
  const pub = $("d-publicado"); pub.textContent = "";
  r.publicaciones.filter(p => p.url).forEach(p => pub.append(crear("a", { href: p.url, target: "_blank", rel: "noopener", textContent: t("ver_ig") })));
  const ocupado = r.fase !== "listo" && r.fase !== "error";
  $("d-aplicar").disabled = ocupado;
  $("d-publicar").hidden = ocupado || r.fase === "error" || !yo.instagram || r.publicaciones.length > 0;
  $("d-aplicar").textContent = t(ocupado ? "haciendo" : "aplicar");
}

// --- Estudio de marca --------------------------------------------------------------------

function productoPrevio() {
  const r = reels.find(x => x.tiene_video);
  return r ? `/portal/reels/${r.id}/producto` : "/estatico/demo/producto.png";
}

function pintarCuadro() {
  if (!yo) return;
  const m = yo.marca, aspecto = tema(m), [tamano, interlinea] = ESCALA_PREVIA[m.fuente];
  const css = FUENTES.find(f => f.id === m.fuente).css.split(" ");
  const cuadro = $("cuadro"); cuadro.textContent = "";
  cuadro.style.background = aspecto.fondo || "#333";
  if (!aspecto.fondo) {
    const f = crear("div", { className: "fondo" }); f.style.backgroundImage = `url(${productoPrevio()})`;
    cuadro.append(f);
  }
  const frase = crear("div", { className: "frase" }, crear("b", { textContent: t("previa_frase") }), crear("b", { textContent: "$45.000" }));
  frase.style.cssText = `font-family:${css.slice(2).join(" ")};font-weight:${css[0]};font-size:${tamano / 3.04}cqw;line-height:${interlinea};color:${aspecto.texto}`;
  frase.lastChild.style.color = aspecto.acento;
  cuadro.append(frase, crear("img", { className: "producto", src: productoPrevio(), alt: "" }));
  if (m.logo) cuadro.append(crear("img", { className: "marca-logo", src: "/portal/marca/logo?" + (pintarCuadro.vez || 0), alt: "" }));
  $("cuadro-pie").textContent = t("previa_musica", { pista: t("pista_" + m.musica) });
}

function pintarLogo(e) {
  $("logo-vista").hidden = !e.marca.logo;
  if (e.marca.logo) $("logo-vista").src = "/portal/marca/logo?" + (pintarCuadro.vez || 0);
  $("logo-quitar").hidden = !e.marca.logo;
}

function refrescarEstudio() {
  controles($("m-controles"), yo.marca, cambiarMarca);
  pintarCuadro();
}

function cambiarMarca(campo, valor, redibujar) {
  yo.marca[campo] = valor;
  if (redibujar) refrescarEstudio(); else pintarCuadro();
  clearTimeout(cambiarMarca.espera);
  $("guardado").textContent = t("guardando");
  cambiarMarca.espera = setTimeout(async () => {
    const { estilo, fuente, primario, secundario, musica } = yo.marca;
    try {
      pintarPasos(await pedir("/api/portal/marca", "POST", { estilo, fuente, primario, secundario, musica }));
      $("guardado").textContent = t("guardado");
    } catch (e) { $("guardado").textContent = ""; avisar(e.message); }
  }, 500);
}

async function subir(ruta, archivo) {
  const datos = new FormData(); datos.append("archivo", archivo);
  return pedir(ruta, "POST", datos);
}

// --- Eventos ------------------------------------------------------------------------------

function modo(registro) {
  registrando = registro;
  $("titulo-acceso").textContent = t(registro ? "crear_cuenta_titulo" : "entrar_titulo");
  $("enviar").textContent = t(registro ? "crear_cuenta" : "entrar");
  $("cambiar-modo").textContent = t(registro ? "ya_tengo" : "no_tengo");
  $("solo-registro").hidden = $("solo-registro2").hidden = !registro;
}

document.querySelectorAll(".pestanas button").forEach(b => { b.onclick = () => { reelAbierto = null; ir(b.dataset.vista); }; });
$("volver").onclick = () => { reelAbierto = null; ir("reels"); };
$("cambiar-modo").onclick = () => modo(!registrando);
$("formulario").onsubmit = async ev => {
  ev.preventDefault();
  const base = { correo: $("correo").value, clave: $("clave").value };
  const e = await hacer(() => registrando
    ? pedir("/api/portal/registro", "POST", { ...base, nombre: $("nombre").value, idioma: $("idioma-wa").value })
    : pedir("/api/portal/entrar", "POST", base));
  if (e && e.nombre) iniciar();
};
document.querySelectorAll(".salir").forEach(b => {
  b.onclick = async () => { await fetch("/api/portal/salir", { method: "POST" }); location.href = "/"; };
});
$("meta-quitar").onclick = () => hacer(() => pedir("/api/portal/conexiones/instagram", "DELETE"));
$("shop-quitar").onclick = () => hacer(() => pedir("/api/portal/conexiones/shopify", "DELETE"));
$("shop-form").onsubmit = ev => {
  ev.preventDefault();
  hacer(async () => {
    const e = await pedir("/api/portal/shopify", "POST", { tienda: $("tienda").value, token: $("token").value });
    $("token").value = ""; return e;
  });
};
$("cel-nuevo").onclick = () => hacer(async () => {
  const r = await pedir("/api/portal/codigo", "POST");
  $("codigo-texto").textContent = r.codigo; $("codigo-enlace").href = r.enlace; $("codigo").hidden = false;
  const e = await pedir("/api/portal/yo");
  if (sondeo) clearInterval(sondeo.id);
  sondeo = { antes: e.celulares.length, id: setInterval(() => pedir("/api/portal/yo").then(pintar).catch(() => {}), 4000) };
  return e;
});
$("logo-archivo").onchange = ev => hacer(async () => {
  const e = await subir("/api/portal/marca/logo", ev.target.files[0]);
  ev.target.value = ""; pintarCuadro.vez = Date.now();
  pintar(e);
  if (e.color_sugerido) cambiarMarca("primario", e.color_sugerido, true); else refrescarEstudio();
});
$("logo-quitar").onclick = () => hacer(() => pedir("/api/portal/marca/logo", "DELETE"));
$("pista-archivo").onchange = ev => hacer(async () => {
  const e = await subir("/api/portal/marca/musica", ev.target.files[0]);
  ev.target.value = ""; pintar(e); refrescarEstudio();
  $("guardado").textContent = t("pista_guardada");
});
$("d-publicar").onclick = () => hacer(async () => {
  $("d-publicar").disabled = true; $("d-publicar").textContent = t("publicando");
  try { await pedir(`/api/portal/reels/${reelAbierto}/publicar`, "POST"); await cargarReels(); }
  finally { $("d-publicar").disabled = false; $("d-publicar").textContent = t("publicar_ig"); }
});
$("propuesta-hacer").onclick = () => hacer(async () => {
  await pedir("/api/portal/propuesta", "POST", { producto: propuestaActual });
  $("propuesta").hidden = true;
  await cargarReels();
});
$("propuesta-otra").onclick = () => hacer(async () => {
  descartados.push(propuestaActual);
  await cargarPropuesta();
});
$("nuevo").onsubmit = ev => {
  ev.preventDefault();
  hacer(async () => {
    const datos = new FormData();
    [...$("nuevo-fotos").files].forEach(f => datos.append("fotos", f));
    datos.append("texto", $("nuevo-texto").value);
    await pedir("/api/portal/reels", "POST", datos);
    ev.target.reset();
    await cargarReels();
  });
};
$("d-aplicar").onclick = () => hacer(async () => {
  const { estilo, fuente, primario, secundario, musica } = elegidoReel;
  await pedir(`/api/portal/reels/${reelAbierto}/estilo`, "POST", { estilo, fuente, primario, secundario, musica });
  await cargarReels();
});

document.addEventListener("idioma", () => {
  if (!yo) { modo(registrando); return; }
  pintar(yo); refrescarEstudio(); cargarReels().catch(() => {}); cargarPropuesta().catch(() => {});
  if (reelAbierto) controles($("d-controles"), elegidoReel, (c, v) => { elegidoReel[c] = v; });
});

async function iniciar() {
  await cargarReels().catch(() => {});
  refrescarEstudio();
  cargarPropuesta().catch(() => {});
  const vista = location.hash.slice(1);
  ir(["marca", "conexiones"].includes(vista) ? vista : "reels");
}

(async () => {
  const consulta = new URLSearchParams(location.search);
  const error = consulta.get("error");
  if (error) {
    avisar(error === "meta" ? t("error_meta") : error);
    history.replaceState(null, "", "/portal#conexiones");
  }
  try { pintar(await pedir("/api/portal/yo")); await iniciar(); }
  catch {
    $("acceso").hidden = false;
    $("idioma-wa").value = idioma;
    aplicarIdioma();
    modo(!consulta.has("entrar"));
  }
})();
