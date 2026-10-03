// Optional browser check: npm install --no-save playwright, then use smoke_service.py.
const { chromium } = require("playwright");
const path = require("node:path");
const fs = require("node:fs");

(async () => {
  const browser = await chromium.launch({headless: true, ...(process.env.SESHAT_BROWSER_CHANNEL ? {channel: process.env.SESHAT_BROWSER_CHANNEL} : {})});
  try {
    const page = await browser.newPage({ viewport: {width: 1280, height: 1000} });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("http://127.0.0.1:8000/");
    await page.getByLabel("API key").fill(process.env.SESHAT_API_KEY);
    await page.getByRole("button", {name: "Connect", exact: true}).click();
    await page.getByText("No people enrolled yet.").waitFor();
    if (process.env.SESHAT_TEST_GESTURES) {
      await page.getByText(/Arm gestures are on/).waitFor();
    }
    await page.getByLabel("Person’s name").fill("Browser Fixture");
    await page.getByLabel("Reference photos").setInputFiles(path.resolve("seshat/tests/fixtures/astronaut.png"));
    await page.getByRole("button", {name: "Enroll photos", exact: true}).click();
    await page.getByText("Browser Fixture · 1 samples", {exact: true}).waitFor();
    await page.getByLabel("JPEG or PNG").setInputFiles(path.resolve("seshat/tests/fixtures/astronaut.png"));
    await page.getByRole("button", {name: "Recognize image", exact: true}).click();
    await page.waitForFunction(() => document.getElementById("result").textContent.includes('"person": "Browser Fixture"'));
    await page.getByText(`Browser Fixture · ${process.env.SESHAT_TEST_GESTURES ? "undetermined" : "disabled"}`, {exact: true}).waitFor();
    if (process.env.SESHAT_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.SESHAT_SCREENSHOT_DIR, {recursive: true});
      await page.screenshot({path: path.join(process.env.SESHAT_SCREENSHOT_DIR,"seshat-desktop.png"), fullPage: true});
      await page.setViewportSize({width: 390, height: 844});
      await page.screenshot({path: path.join(process.env.SESHAT_SCREENSHOT_DIR,"seshat-mobile.png"), fullPage: true});
    }
    page.on("dialog", dialog => dialog.accept());
    await page.getByRole("button", {name: "Delete person", exact: true}).click();
    await page.getByText("No people enrolled yet.").waitFor();
    if (errors.length) throw new Error(errors.join("\n"));
    console.log("Browser enrollment, recognition and deletion passed; no page errors");
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
