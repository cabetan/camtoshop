// Español e inglés para el sitio y el portal. El idioma se recuerda en este navegador.
const TEXTOS = {
  es: {
    entrar: "Entrar", crear_cuenta: "Crear mi cuenta", crear_cuenta_titulo: "Crea tu cuenta", entrar_titulo: "Entra a tu cuenta",
    ya_tengo: "Ya tengo cuenta", no_tengo: "Crear una cuenta",
    hero: "Una foto. Un Reel. Tu marca.",
    hero_texto: "Manda la foto de tu producto por WhatsApp y di cuánto vale. Camtoshop te hace el Reel con tus colores, tu logo y tu música. Tú solo tocas Publicar.",
    hero_nota: "Sin agencia, sin diseñador y sin saber editar.",
    globo_uno: "Florero de cerámica verde, 200 mil",
    globo_dos: "¡Recibido! En unos 4 minutos te mando el Reel para que lo apruebes.",
    sonido_on: "Activar sonido", sonido_off: "Quitar sonido", video_alt: "Reel hecho por Camtoshop para un florero de cerámica",
    como_titulo: "Si sabes usar WhatsApp, ya sabes usar Camtoshop.",
    paso1: "Manda una foto", paso1_t: "Di qué es y cuánto vale, escrito o en una nota de voz.",
    paso2: "Recibe tu Reel", paso2_t: "En unos 4 minutos llega a tu chat. Si quieres cambiar algo, pídelo con tus palabras.",
    paso3: "Toca Publicar", paso3_t: "Sale en tu Instagram. Nada se publica hasta que apruebes esa versión.",
    estilos_titulo: "El mismo producto, con tu estilo.",
    estilo_impacto: "Impacto", estilo_impacto_t: "Letra grande sobre tu foto y música animada.",
    estilo_color: "Color", estilo_color_t: "El color de tu marca detrás del producto, con música cálida.",
    estilo_limpio: "Limpio", estilo_limpio_t: "Fondo claro, letra elegante y piano suave.",
    estilos_nota: "Elige tu logo, colores, letra y música una sola vez. Todos tus Reels salen así, y puedes probar otro estilo cuando quieras.",
    ti_titulo: "Hecho para quien vende, no para quien edita.",
    ti_1: "No necesitas tiempo", ti_1_t: "Una foto entre cliente y cliente es suficiente.",
    ti_2: "No necesitas experiencia", ti_2_t: "Camtoshop escribe el texto, arma el video y elige los hashtags.",
    ti_3: "Tú decides", ti_3_t: "Ves el Reel antes que nadie. Si no te gusta, no sale.",
    con_que: "Funciona con los modelos de Meta", con_que_t: "Muse Spark ve tu producto y escribe el Reel. SAM 3.1 recorta tu producto real. Muse Image crea escenas, siempre marcadas como IA. Muse Voice Transcribe entiende tus notas de voz.",
    cierre: "Tu próxima publicación está a una foto.",
    pie: "Camtoshop, hecho por btodigital en Colombia.",

    cartel: "Tu celular es el estudio.",
    cartel_t: "Manda una foto por WhatsApp y recibe un Reel con tus colores, tu logo y tu música. Nada se publica hasta que tú lo apruebes.",
    negocio: "Nombre de tu negocio", correo: "Correo", clave: "Contraseña", idioma_wa: "Idioma en WhatsApp",
    nav_reels: "Mis Reels", nav_marca: "Mi marca", nav_conexiones: "Mis cuentas", salir: "Salir",
    reels: "Mis Reels", reel_wa: "Hacer un Reel por WhatsApp", nuevo: "Haz un Reel aquí",
    nuevo_fotos: "Fotos de un solo producto", nuevo_texto: "¿Qué es y cuánto vale?", nuevo_ph: "Vela de soya, lavanda, 85 mil",
    nuevo_boton: "Hacer mi Reel", nuevo_nota: "Tarda unos 4 minutos. Usa los ajustes de tu marca y nada se publica sin tu aprobación.",
    vacio: "Tu primer Reel empieza con una foto",
    vacio_t: "Sube una foto aquí arriba o mándala a Camtoshop por WhatsApp. El Reel aparece aquí en unos 4 minutos.",
    pendiente: "Termina de configurar", paso_instagram: "Conectar Instagram", paso_celular: "Agregar tu celular", paso_marca: "Configurar tu marca",
    todos: "Todos mis Reels", publicar_ig: "Publicar en Instagram", publicando: "Publicando…",
    aplicar: "Hacer esta versión", haciendo: "Haciendo el Reel…", aplicar_nota: "Tarda cerca de un minuto. Nada se publica sin tu aprobación.",
    estado_error: "No se pudo terminar este Reel", estado_haciendo: "Haciendo el Reel…", estado_publicado: "Publicado", estado_listo: "Listo para aprobar",
    ver_ig: "Verlo en Instagram",
    marca: "Mi marca", logo: "Logo", subir_logo: "Subir logo", quitar: "Quitar", logo_nota: "Lo mejor es un PNG con fondo transparente. Sale arriba en cada Reel.",
    mi_musica: "Tu propia música", subir_pista: "Subir una canción",
    musica_nota: "Sube solo música que tengas derecho a usar. También puedes agregar una canción desde Instagram después de publicar.",
    estilo: "Estilo", colores: "Colores", color_1: "Color principal", color_2: "Color secundario", letra: "Letra", musica: "Música",
    letra_barlow: "Cartel", letra_playfair: "Elegante", letra_poppins: "Amigable", letra_caveat: "Hecha a mano",
    estilo_impacto_c: "Letra grande sobre tu foto", estilo_color_c: "Tu color detrás del producto", estilo_limpio_c: "Claro y tranquilo",
    pista_energia: "Animada", pista_energia_t: "Para lanzamientos y ofertas", pista_calida: "Cálida", pista_calida_t: "Relajada, con teclado",
    pista_elegante: "Elegante", pista_elegante_t: "Piano suave", pista_propia: "Mi canción", pista_propia_t: "La que subiste",
    pista_ninguna: "Sin música", pista_ninguna_t: "Agrégala luego en Instagram",
    guardando: "Guardando…", guardado: "Guardado. Tus próximos Reels saldrán así.", pista_guardada: "Canción guardada. Tus próximos Reels la usarán.",
    previa_frase: "NUEVO ESTA SEMANA", previa_musica: "Música: {pista}", reproducir: "Escuchar {pista}",
    conexiones: "Mis cuentas", instagram_nota: "Conecta la cuenta profesional de Instagram vinculada a tu página de Facebook.",
    instagram_ok: "Conectada a @{cuenta}, por la página {pagina}.", conectar_ig: "Conectar Instagram", desconectar: "Desconectar",
    celulares: "Celulares con WhatsApp",
    celulares_nota: "Vincula un celular para hacer y aprobar Reels por WhatsApp. Por ahora la línea solo responde a números autorizados. Siempre puedes hacer Reels en este portal.",
    codigo_nota: "Manda este código a Camtoshop desde el celular que vas a usar. Sirve por 30 minutos.", abrir_wa: "Abrir WhatsApp", agregar_cel: "Agregar un celular",
    error_general: "No funcionó. Inténtalo de nuevo.", error_meta: "No terminó la conexión con Facebook. Conecta Instagram de nuevo.",
  },
  en: {
    entrar: "Sign in", crear_cuenta: "Create my account", crear_cuenta_titulo: "Create your account", entrar_titulo: "Sign in",
    ya_tengo: "I already have an account", no_tengo: "Create an account",
    hero: "One photo. One Reel. Your brand.",
    hero_texto: "Send a product photo on WhatsApp and say what it costs. Camtoshop makes the Reel in your colors, with your logo and music. You just tap Publish.",
    hero_nota: "No agency, no designer, no editing skills.",
    globo_uno: "Green ceramic vase, 200 thousand",
    globo_dos: "Got it! In about 4 minutes I'll send you the Reel to approve.",
    sonido_on: "Turn sound on", sonido_off: "Turn sound off", video_alt: "A Reel made by Camtoshop for a ceramic vase",
    como_titulo: "If you can use WhatsApp, you can use Camtoshop.",
    paso1: "Send a photo", paso1_t: "Say what it is and what it costs, by text or voice note.",
    paso2: "Get your Reel", paso2_t: "In about four minutes it's in your chat. Ask for changes in your own words.",
    paso3: "Tap Publish", paso3_t: "It goes to your Instagram. Nothing is posted until you approve that version.",
    estilos_titulo: "Same product. Your look.",
    estilo_impacto: "Bold", estilo_impacto_t: "Big type over your photo, with upbeat music.",
    estilo_color: "Color", estilo_color_t: "Your brand color behind the product, with warm music.",
    estilo_limpio: "Clean", estilo_limpio_t: "Light background, elegant type and soft piano.",
    estilos_nota: "Set your logo, colors, lettering and music once. Every Reel follows them, and you can try another look any time.",
    ti_titulo: "Made for people who sell, not people who edit.",
    ti_1: "You don't need time", ti_1_t: "One photo between customers is enough.",
    ti_2: "You don't need experience", ti_2_t: "Camtoshop writes the copy, builds the video and picks the hashtags.",
    ti_3: "You decide", ti_3_t: "You see the Reel first. If you don't like it, it doesn't go out.",
    con_que: "Powered by Meta's models", con_que_t: "Muse Spark sees your product and writes the Reel. SAM 3.1 cuts out your real product. Muse Image creates scenes, always labeled as AI. Muse Voice Transcribe understands your voice notes.",
    cierre: "Your next post is one photo away.",
    pie: "Camtoshop, made by btodigital in Colombia.",

    cartel: "Your phone is the studio.",
    cartel_t: "Send a photo on WhatsApp and get a Reel in your colors, with your logo and music. Nothing goes live until you approve it.",
    negocio: "Business name", correo: "Email", clave: "Password", idioma_wa: "WhatsApp language",
    nav_reels: "My Reels", nav_marca: "My brand", nav_conexiones: "My accounts", salir: "Sign out",
    reels: "My Reels", reel_wa: "Make a Reel on WhatsApp", nuevo: "Make a Reel here",
    nuevo_fotos: "Photos of one product", nuevo_texto: "What is it and what does it cost?", nuevo_ph: "Soy candle, lavender scent, $25",
    nuevo_boton: "Make my Reel", nuevo_nota: "Takes about four minutes. It uses your brand settings, and nothing is published until you approve it.",
    vacio: "Your first Reel starts with one photo",
    vacio_t: "Upload a product photo above, or send it to Camtoshop on WhatsApp. The Reel appears here in about four minutes.",
    pendiente: "Finish setting up", paso_instagram: "Connect Instagram", paso_celular: "Add your phone", paso_marca: "Set up your brand",
    todos: "All my Reels", publicar_ig: "Publish to Instagram", publicando: "Publishing…",
    aplicar: "Make this version", haciendo: "Making the Reel…", aplicar_nota: "Takes about a minute. Nothing is published until you approve it.",
    estado_error: "Couldn't finish this Reel", estado_haciendo: "Making the Reel…", estado_publicado: "Published", estado_listo: "Ready for your approval",
    ver_ig: "See it on Instagram",
    marca: "My brand", logo: "Logo", subir_logo: "Upload logo", quitar: "Remove", logo_nota: "A PNG with a transparent background works best. It goes at the top of every Reel.",
    mi_musica: "Your own music", subir_pista: "Upload a track",
    musica_nota: "Only upload music you have the rights to use. You can also add a song from Instagram after publishing.",
    estilo: "Look", colores: "Colors", color_1: "Main color", color_2: "Second color", letra: "Lettering", musica: "Music",
    letra_barlow: "Poster", letra_playfair: "Elegant", letra_poppins: "Friendly", letra_caveat: "Handmade",
    estilo_impacto_c: "Big type over your photo", estilo_color_c: "Your color behind the product", estilo_limpio_c: "Light and quiet",
    pista_energia: "Upbeat", pista_energia_t: "For launches and sales", pista_calida: "Warm", pista_calida_t: "Relaxed keys",
    pista_elegante: "Elegant", pista_elegante_t: "Soft piano", pista_propia: "My track", pista_propia_t: "The one you uploaded",
    pista_ninguna: "No music", pista_ninguna_t: "Add a song in Instagram later",
    guardando: "Saving…", guardado: "Saved. Your next Reels will look like this.", pista_guardada: "Track saved. Your next Reels will use it.",
    previa_frase: "NEW THIS WEEK", previa_musica: "Music: {pista}", reproducir: "Play {pista}",
    conexiones: "My accounts", instagram_nota: "Connect the Instagram professional account linked to your Facebook Page.",
    instagram_ok: "Connected to @{cuenta}, through the Page {pagina}.", conectar_ig: "Connect Instagram", desconectar: "Disconnect",
    celulares: "WhatsApp phones",
    celulares_nota: "Link a phone to make and approve Reels on WhatsApp. For now the line only answers approved numbers. You can always make Reels in this portal.",
    codigo_nota: "Send this code to Camtoshop from the phone you'll use. It works for 30 minutes.", abrir_wa: "Open WhatsApp", agregar_cel: "Add a phone",
    error_general: "That didn't work. Try again.", error_meta: "The connection with Facebook didn't finish. Connect Instagram again.",
  },
};

// Los errores llegan del servidor en inglés.
const ERRORES_ES = {
  "Another Reel is rendering. Try again in a few minutes.": "Se está haciendo otro Reel. Inténtalo en unos minutos.",
  "Camtoshop reached today's limit. Try again tomorrow.": "Camtoshop llegó al límite de hoy. Inténtalo mañana.",
  "Choose one of the available options": "Elige una de las opciones disponibles",
  "Connect Instagram again": "Conecta Instagram de nuevo",
  "Connect Instagram first": "Primero conecta Instagram",
  "Facebook didn't accept the connection. Please try again.": "Facebook no aceptó la conexión. Inténtalo de nuevo.",
  "Say what it is and what it costs": "Di qué es y cuánto vale",
  "Tell us your business name": "Escribe el nombre de tu negocio",
  "That email already has an account": "Ese correo ya tiene una cuenta",
  "That email doesn't look right": "Revisa el correo",
  "This Reel is still rendering": "Este Reel todavía se está haciendo",
  "Too many attempts. Try again later.": "Demasiados intentos. Inténtalo más tarde.",
  "Upload 1 to 8 photos of one product": "Sube de 1 a 8 fotos de un solo producto",
  "Use JPG, PNG or WEBP photos under 10 MB": "Usa fotos JPG, PNG o WEBP de menos de 10 MB",
  "Use at least 8 characters for your password": "Usa al menos 8 caracteres en tu contraseña",
  "We couldn't read your Facebook Pages. Please try again.": "No pudimos leer tus páginas de Facebook. Inténtalo de nuevo.",
  "We found no Instagram professional account linked to a Facebook Page you manage": "No encontramos una cuenta profesional de Instagram vinculada a una página de Facebook que administres",
  "Wrong email or password": "Correo o contraseña incorrectos",
  "You reached today's limit of Reels": "Llegaste al límite de Reels de hoy",
  "Upload your track first": "Primero sube tu canción",
  "Use a PNG or JPG logo": "Usa un logo PNG o JPG",
  "Use a logo under 5 MB": "Usa un logo de menos de 5 MB",
  "Use a track under 20 MB": "Usa una canción de menos de 20 MB",
  "Use an MP3 or M4A track": "Usa una canción MP3 o M4A",
  "Use colors like #FFD23F": "Usa colores como #FFD23F",
};

function idiomaGuardado() {
  try { return localStorage.getItem("camtoshop_idioma"); } catch { return null; }
}

let idioma = idiomaGuardado() || ((navigator.language || "en").toLowerCase().startsWith("es") ? "es" : "en");

function t(clave, datos = {}) {
  let texto = (TEXTOS[idioma] || TEXTOS.en)[clave] ?? clave;
  Object.entries(datos).forEach(([k, v]) => { texto = texto.replace(`{${k}}`, v); });
  return texto;
}

function traducirError(mensaje) {
  return idioma === "es" ? ERRORES_ES[mensaje] || mensaje : mensaje;
}

function aplicarIdioma() {
  document.documentElement.lang = idioma;
  document.querySelectorAll("[data-t]").forEach(n => { n.textContent = t(n.dataset.t); });
  document.querySelectorAll("[data-t-ph]").forEach(n => { n.placeholder = t(n.dataset.tPh); });
  document.querySelectorAll("[data-t-alt]").forEach(n => { n.setAttribute("aria-label", t(n.dataset.tAlt)); });
  document.querySelectorAll("[data-idioma]").forEach(b => { b.setAttribute("aria-pressed", b.dataset.idioma === idioma); });
}

function cambiarIdioma(nuevo) {
  idioma = nuevo;
  try { localStorage.setItem("camtoshop_idioma", nuevo); } catch { /* sin almacenamiento solo dura esta visita */ }
  aplicarIdioma();
  document.dispatchEvent(new Event("idioma"));
}

document.addEventListener("click", ev => {
  const boton = ev.target.closest("[data-idioma]");
  if (boton) cambiarIdioma(boton.dataset.idioma);
});
document.addEventListener("DOMContentLoaded", aplicarIdioma);
