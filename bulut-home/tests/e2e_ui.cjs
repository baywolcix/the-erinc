// e2e_ui.py tarafından başlatılır. Sahte sağlayıcılı sunucuya karşı arayüzü gezer.
const { chromium } = require("playwright");
const URL = process.env.BULUT_URL, TOKEN = process.env.SETUP_TOKEN, SHOTS = process.env.SHOTS;
const assert = (c, m) => { if (!c) throw new Error("ASSERT: " + m); };
(async () => {
  const errors = [];
  const b = await chromium.launch();
  for (const [name, vp] of [["mobile", { width: 390, height: 844 }], ["desktop", { width: 1280, height: 800 }]]) {
    const ctx = await b.newContext({ viewport: vp });
    const page = await ctx.newPage();
    page.on("console", (m) => { if (m.type() === "error") errors.push(`${name}: ${m.text()}`); });
    page.on("pageerror", (e) => errors.push(`${name}: ${e}`));
    await page.goto(URL);
    await page.fill("[name=username]", "umut");
    await page.fill("[name=password]", "cok-gizli-parola");
    if (name === "mobile") await page.fill("[name=setup_token]", TOKEN);
    await page.click("#auth-form button");
    await page.waitForSelector("#app:not(.hidden)");
    if (name === "mobile") {
      await page.click("a[data-view=chat]");
      await page.fill("#input", "BULUT, bugün ne yaptık?");
      await page.click("#send");
      await page.waitForSelector(".msg.assistant:not(.thinking)");
      const txt = await page.innerText(".msg.assistant");
      assert(txt.includes("Yan Daire") && !txt.includes("[["), txt);
      assert(txt.includes("görev eklendi") && txt.includes("hafızaya kaydedildi"), "araç bilgisi: " + txt);
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}-chat.png` });
    }
    for (const view of ["tasks", "projects", "activity", "memory", "reports", "system", "approvals"]) {
      await page.click(`a[data-view=${view}]`);
      await page.waitForTimeout(300);
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}-${view}.png` });
    }
    if (name === "desktop") {
      await page.click("a[data-view=tasks]");
      await page.fill("#task-form [name=title]", "Kapak görseli tasarla");
      await page.click("#task-form button");
      await page.waitForSelector("text=Kapak görseli tasarla");
      assert(await page.locator(".item", { hasText: "PROGRESS.md" }).count() === 1, "sohbetten görev");
      await page.click("a[data-view=memory]");
      await page.waitForSelector("#memory-list >> text=Yan Daire demo");
      // proje silme → onay
      page.on("dialog", (d) => d.accept());
      await page.click("a[data-view=projects]");
      await page.locator(".card", { hasText: "İş ve Gelir" }).locator("text=Sil…").click();
      await page.click("a[data-view=approvals]");
      await page.waitForSelector("text=projesini sil");
      await page.click("#approval-list >> text=Reddet");
      await page.waitForSelector("#approval-list >> text=rejected");
      // günlük brifing
      await page.click("a[data-view=reports]");
      await page.click("#brief-generate");
      await page.waitForSelector("#brief-body >> text=Sabah brifingi");
      assert((await page.innerText("#brief-meta")).includes("model özeti"), "brifing meta");
      // sohbet geçmişi kalıcı
      await page.click("a[data-view=chat]");
      await page.click("#conv-toggle");
      await page.waitForSelector("#conv-list >> text=BULUT, bugün ne yaptık?");
      await page.click("#conv-list >> text=BULUT, bugün ne yaptık?");
      await page.waitForSelector(".msg.user");
      // telefon genişliğinde yatay taşma yok
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    assert(!overflow, `${name} yatay taşma`);
    await ctx.close();
  }
  await b.close();
  if (errors.length) { console.log("KONSOL HATALARI:\n" + errors.join("\n")); process.exit(1); }
  console.log("E2E OK");
})().catch((e) => { console.error(e); process.exit(1); });
