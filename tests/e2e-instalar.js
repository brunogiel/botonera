/* E2E del cartel «instalá la botonera en tu inicio»: sale solo en el celu y desde el navegador (iPhone con los pasos de Compartir,
 * Android con el botón «Instalar» cuando el navegador ofrece instalar), no sale en compu, y cerrarlo lo apaga para siempre.
 * Uso: node tests/e2e-instalar.js
 */
const A = require('./arnes/arnes');
const R = A.nuevoReporte('e2e-instalar');
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';
const ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36';
const cierre = (page, n) => R.reg(n, 'Sin errores de página ni de consola', page.errores.length === 0 && page.consola.length === 0, page.errores.concat(page.consola).join(' | '));
async function abrir(page) { await page.goto(A.url()); await page.waitForSelector('#tabs', { timeout: 10000 }); await A.sleep(500); }

(async () => {
  let ok = false;
  try {
    await A.levantar();
    // iPhone: pasos de Compartir → Agregar a inicio
    let { ctx, page } = await A.ctxNuevo(A.escenario('simple'), { userAgent: IPHONE });
    try {
      await abrir(page);
      const t = await page.locator('#inst').innerText().catch(() => '');
      R.reg('iphone', 'En iPhone sale el cartel con «Compartir» y «Agregar a inicio», sin botón «Instalar»', /Instalá la botonera en tu inicio/.test(t) && /Compartir/.test(t) && /Agregar a inicio/.test(t) && !(await page.locator('[data-inst="instalar"]').count()), t.replace(/\n/g, ' '));
      const img = await page.locator('#inst img').getAttribute('src');
      R.reg('icono', 'El cartel muestra el ícono de la app', /\/icon\.svg/.test(img), img);
      R.reg('arriba-barra', 'El cartel queda por encima de la barra de abajo', await page.evaluate(() => { const i = document.getElementById('inst').getBoundingClientRect(), b = document.getElementById('tabs').getBoundingClientRect(); return i.bottom <= b.top + 1; }));
      await page.locator('[data-inst="cerrar"]').tap(); await A.sleep(300);
      R.reg('cerrar', 'Cerrar saca el cartel', (await page.locator('#inst').count()) === 0);
      await page.reload(); await page.waitForSelector('#tabs', { timeout: 10000 }); await A.sleep(500);
      R.reg('no-vuelve', 'Después de cerrarlo no vuelve a salir', (await page.locator('#inst').count()) === 0);
      cierre(page, 'errores-iphone');
    } finally { await ctx.close(); }

    // Android: el navegador ofrece instalar → botón «Instalar» que abre su aviso
    ({ ctx, page } = await A.ctxNuevo(A.escenario('simple'), { userAgent: ANDROID }));
    try {
      await abrir(page);
      const sin = await page.locator('#inst').innerText().catch(() => '');
      R.reg('android-pasos', 'En Android sin aviso del navegador, el cartel explica el menú ⋮', /menú ⋮/.test(sin) && !(await page.locator('[data-inst="instalar"]').count()), sin.replace(/\n/g, ' '));
      await page.evaluate(() => {
        const e = new Event('beforeinstallprompt', { cancelable: true });
        e.prompt = () => { window.__promptLlamado = true; return Promise.resolve(); };
        e.userChoice = Promise.resolve({ outcome: 'accepted' });
        window.dispatchEvent(e);
      });
      await A.sleep(200);
      R.reg('android-instalar', 'Con beforeinstallprompt aparece «Instalar»', (await page.locator('[data-inst="instalar"]').count()) === 1);
      await page.locator('[data-inst="instalar"]').tap(); await A.sleep(400);
      R.reg('android-prompt', 'Tocar «Instalar» abre el aviso del navegador y, si se acepta, apaga el cartel', (await page.evaluate(() => window.__promptLlamado === true)) && (await page.locator('#inst').count()) === 0);
      cierre(page, 'errores-android');
    } finally { await ctx.close(); }

    // Compu: no sale
    ({ ctx, page } = await A.ctxNuevo(A.escenario('simple'), { escritorio: true, ancho: 1280, alto: 800 }));
    try {
      await abrir(page);
      R.reg('compu', 'En compu no sale el cartel', (await page.locator('#inst').count()) === 0);
      cierre(page, 'errores-compu');
    } finally { await ctx.close(); }
  } finally { ok = R.fin(); await A.cerrar(); }
  process.exit(ok ? 0 : 1);
})();
