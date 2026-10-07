import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const EDGE_PATH = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 9222;
const FRONTEND_URL = "http://localhost:5173";

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.id = 1;
    this.pending = new Map();
  }

  async connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.onopen = () => resolve();
      this.ws.onerror = (err) => reject(err);
      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.method === "Runtime.consoleAPICalled" && this.onConsole) {
          this.onConsole(msg.params);
        }
        if (msg.method === "Runtime.exceptionThrown" && this.onException) {
          this.onException(msg.params);
        }
        if (msg.id && this.pending.has(msg.id)) {
          const { resolve, reject } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          if (msg.error) {
            reject(new Error(msg.error.message));
          } else {
            resolve(msg.result);
          }
        }
      };
    });
  }

  async send(method, params = {}) {
    const id = this.id++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const res = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    return res?.result?.value;
  }

  close() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitForHttp(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return true;
    } catch {}
    await sleep(200);
  }
  throw new Error(`Timeout waiting for ${url}`);
}

async function runE2E() {
  console.log("=== STARTING END-TO-END BROWSER VERIFICATION ===");

  // 1. Clean existing test sessions in backend
  console.log("[PRE-TEST] Cleaning any existing sessions in backend...");
  try {
    const listRes = await fetch("http://127.0.0.1:8000/api/sessions");
    if (listRes.ok) {
      const list = await listRes.json();
      console.log(`Found ${list.length} prior sessions in backend. Deleting...`);
      for (const s of list) {
        await fetch(`http://127.0.0.1:8000/api/sessions/${s.session_id}`, { method: "DELETE" });
      }
    }
  } catch (err) {
    console.warn("Backend pre-clean warning:", err.message);
  }

  const tempUserDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "edge_e2e_"));
  console.log("Using temp user data dir:", tempUserDataDir);

  const edgeProcess = spawn(
    EDGE_PATH,
    [
      "--headless=new",
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${tempUserDataDir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-gpu",
      "--window-size=1280,900",
    ],
    { stdio: "ignore" }
  );

  try {
    await waitForHttp(`http://127.0.0.1:${PORT}/json/version`, 15000);
    console.log("Connected to Edge DevTools Protocol on port", PORT);

    const versionData = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    let target = versionData.find((t) => t.type === "page");
    if (!target) {
      const newTab = await (await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(FRONTEND_URL)}`)).json();
      target = newTab;
    }

    const cdp = new CDPClient(target.webSocketDebuggerUrl);
    await cdp.connect();
    console.log("WebSocket connected to target page");

    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");

    cdp.onConsole = (params) => {
      const text = params.args?.map((a) => {
        if (a.value !== undefined) return typeof a.value === "object" ? JSON.stringify(a.value) : String(a.value);
        if (a.preview) {
          const props = a.preview.properties?.map((p) => `${p.name}: ${p.value}`).join(", ");
          return `{ ${props} }`;
        }
        return a.description || "";
      }).join(" ");
      console.log(`[BROWSER CONSOLE ${params.type}]`, text);
    };

    cdp.onException = (params) => {
      console.error("[BROWSER EXCEPTION]", params.exceptionDetails?.text, params.exceptionDetails?.exception?.description);
    };

    // Navigate to frontend
    console.log("\n[STEP 1] Navigating to", FRONTEND_URL);
    await cdp.send("Page.navigate", { url: FRONTEND_URL });
    await sleep(2000);

    // Helper: wait for element
    async function waitForSelector(selector, timeoutMs = 10000) {
      const start = Date.now();
      while (Date.now() - start < timeoutMs) {
        const found = await cdp.evaluate(`Boolean(document.querySelector(${JSON.stringify(selector)}))`);
        if (found) return true;
        await sleep(250);
      }
      return false;
    }

    // Step 2: Log in via the real UI
    console.log("[STEP 2] Performing UI sign-in as sarah.compliance...");
    const hasLogin = await waitForSelector("#login-user-id", 5000);
    if (hasLogin) {
      await cdp.evaluate(`
        (() => {
          const uInput = document.querySelector('#login-user-id');
          const pInput = document.querySelector('#login-password');
          const remember = document.querySelector('.login-remember-me input');
          const btn = document.querySelector('.login-submit-btn');

          const nativeInputSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          nativeInputSetter.call(uInput, 'sarah.compliance');
          uInput.dispatchEvent(new Event('input', { bubbles: true }));

          nativeInputSetter.call(pInput, 'Compliance@2026');
          pInput.dispatchEvent(new Event('input', { bubbles: true }));

          if (remember && !remember.checked) {
            remember.click();
          }

          if (btn) btn.click();
        })()
      `);
    }

    const appLoaded = await waitForSelector(".stSidebar", 12000);
    console.log("Main application and sidebar loaded:", appLoaded);
    if (!appLoaded) {
      const bodySnippet = await cdp.evaluate(`document.body.innerHTML.slice(0, 500)`);
      throw new Error(`Application failed to load sidebar. Body snippet: ${bodySnippet}`);
    }

    // Clear any local storage sessions just in case
    await cdp.evaluate(`
      localStorage.setItem('ns_cg_chat_sessions_v1', JSON.stringify({}));
      localStorage.removeItem('ns_cg_active_session_id_v1');
    `);

    // Helper to submit a chat query and wait for stream completion
    async function submitChatQuery(queryText) {
      console.log(`Submitting chat query: "${queryText}"`);
      await cdp.evaluate(`
        (() => {
          const ta = document.querySelector('.cg-chatgpt-query-input');
          if (ta) {
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            nativeSetter.call(ta, ${JSON.stringify(queryText)});
            ta.dispatchEvent(new Event('input', { bubbles: true }));
          }
        })()
      `);
      await sleep(300);

      await cdp.evaluate(`
        (() => {
          const btn = document.querySelector('.cg-chatgpt-send-btn');
          if (btn) btn.click();
        })()
      `);

      // 1. Wait for stream to start
      for (let i = 0; i < 20; i++) {
        await sleep(100);
        const started = await cdp.evaluate(`
          Boolean(document.querySelector('.cg-chatgpt-send-btn--streaming') || document.querySelector('.cg-thinking'))
        `);
        if (started) break;
      }

      // 2. Wait for streaming and thinking indicator to finish
      const startPoll = Date.now();
      while (Date.now() - startPoll < 30000) {
        await sleep(300);
        const isBusy = await cdp.evaluate(`
          Boolean(document.querySelector('.cg-chatgpt-send-btn--streaming') || document.querySelector('.cg-thinking'))
        `);
        if (!isBusy) break;
      }
      await sleep(1200);
    }

    // 3. Verify Recent Chats is initially empty
    console.log("\n[STEP 3] Verifying initial Recent Chats state...");
    const initialSessionsCount = await cdp.evaluate(`document.querySelectorAll('.cg-session-item').length`);
    const emptyText = await cdp.evaluate(`document.querySelector('.cg-empty-sessions')?.textContent?.trim() || ""`);
    console.log(`Initial session count in sidebar: ${initialSessionsCount}, Empty label: "${emptyText}"`);
    if (initialSessionsCount !== 0) {
      throw new Error(`Expected 0 sessions initially, got ${initialSessionsCount}`);
    }
    if (emptyText !== "No conversations yet") {
      throw new Error(`Expected "No conversations yet", got "${emptyText}"`);
    }
    console.log("PASS: Recent Chats is initially clean with 'No conversations yet'!");

    // 4. Test repeatedly clicking "New Chat" without sending messages
    console.log("\n[STEP 4] Rapidly clicking 'New Chat' 5 times without sending any message...");
    for (let i = 1; i <= 5; i++) {
      await cdp.evaluate(`
        const btn = document.querySelector('.cg-new-chat-btn');
        if (btn) btn.click();
      `);
      await sleep(150);
    }
    await sleep(500);

    const postNewChatCount = await cdp.evaluate(`document.querySelectorAll('.cg-session-item').length`);
    console.log(`Session count after 5 rapid New Chat clicks: ${postNewChatCount}`);
    if (postNewChatCount !== 0) {
      throw new Error(`CRITICAL FAILURE: Clicking New Chat created empty session(s)! Found: ${postNewChatCount}`);
    }
    console.log("PASS: Repeatedly clicking New Chat did NOT create any empty conversations in Recent Chats!");

    // 5. Send first query (Chat 1)
    console.log("\n[STEP 5] Submitting first query for Chat 1...");
    await submitChatQuery("What are the borrowing limits for mutual funds under SEBI?");

    const chat1Count = await cdp.evaluate(`document.querySelectorAll('.cg-session-item').length`);
    const chat1Title = await cdp.evaluate(`document.querySelector('.cg-session-title')?.textContent?.trim() || ""`);
    console.log(`Sidebar session count after 1st query: ${chat1Count}, title: "${chat1Title}"`);
    if (chat1Count !== 1) {
      throw new Error(`Expected 1 session in sidebar, found ${chat1Count}`);
    }
    if (!chat1Title || chat1Title === "New Conversation") {
      throw new Error(`Expected meaningful title for Chat 1, got "${chat1Title}"`);
    }
    console.log("PASS: Conversation created and added to Recent Chats upon submitting first query!");

    // 6. Click "New Chat" and verify a blank session opens WITHOUT adding to Recent Chats
    console.log("\n[STEP 6] Clicking 'New Chat' to open a blank session...");
    const clickDetails = await cdp.evaluate(`
      (() => {
        const btn = document.querySelector('.cg-new-chat-btn');
        if (!btn) return { error: "No .cg-new-chat-btn button found" };
        const rect = btn.getBoundingClientRect();
        const activeBefore = localStorage.getItem('ns_cg_active_session_id_v1');
        btn.click();
        const activeAfter = localStorage.getItem('ns_cg_active_session_id_v1');
        return {
          found: true,
          visible: rect.width > 0 && rect.height > 0,
          activeBefore,
          activeAfter,
          chatSessionsKeys: Object.keys(JSON.parse(localStorage.getItem('ns_cg_chat_sessions_v1') || '{}'))
        };
      })()
    `);
    console.log("Step 6 clickDetails:", JSON.stringify(clickDetails, null, 2));
    await sleep(1000);

    const chatAfterNew = await cdp.evaluate(`document.querySelectorAll('.cg-session-item').length`);
    console.log(`Sidebar session count after clicking New Chat: ${chatAfterNew}`);
    if (chatAfterNew !== 1) {
      throw new Error(`Expected exactly 1 session in sidebar (no empty placeholder), found ${chatAfterNew}`);
    }

    const isTextareaEmpty = await cdp.evaluate(`
      (document.querySelector('.cg-chatgpt-query-input')?.value || "") === ""
    `);
    const isStarterOrEmpty = await cdp.evaluate(`
      Boolean(document.querySelector('.cg-chat-empty') || document.querySelector('.cg-chat-starters'))
    `);
    if (!isTextareaEmpty || !isStarterOrEmpty) {
      const dbg = await cdp.evaluate(`({
        scroll: document.querySelector('.cg-chat-scroll')?.innerHTML?.slice(0, 600),
        msgGroups: document.querySelectorAll('.cg-msg-group').length,
        streaming: Boolean(document.querySelector('.cg-chatgpt-send-btn--streaming')),
        thinking: Boolean(document.querySelector('.cg-thinking'))
      })`);
      console.log("DEBUG ON FAILURE:", JSON.stringify(dbg, null, 2));
      throw new Error("Expected blank session with cleared textarea and starter prompts/empty screen");
    }
    console.log("PASS: Blank session initialized cleanly without creating an empty chat in Recent Chats!");

    // 7. Send second query (Chat 2)
    console.log("\n[STEP 7] Submitting query in blank session for Chat 2...");
    await submitChatQuery("Explain categorization rules for equity schemes");

    const chat2Count = await cdp.evaluate(`document.querySelectorAll('.cg-session-item').length`);
    console.log(`Sidebar session count after 2nd query: ${chat2Count}`);
    if (chat2Count !== 2) {
      throw new Error(`Expected 2 sessions in sidebar, found ${chat2Count}`);
    }
    console.log("PASS: Second conversation created and added to Recent Chats!");

    // 8. Create Chat 3 and Chat 4
    console.log("\n[STEP 8] Creating Chat 3 and Chat 4...");
    // Chat 3:
    await cdp.evaluate(`document.querySelector('.cg-new-chat-btn').click();`);
    await sleep(500);
    await submitChatQuery("What are ESG disclosure requirements under BRSR?");

    // Chat 4:
    await cdp.evaluate(`document.querySelector('.cg-new-chat-btn').click();`);
    await sleep(500);
    await submitChatQuery("What are the timelines for updating SID and KIM?");

    const allTitles = await cdp.evaluate(`
      Array.from(document.querySelectorAll('.cg-session-title')).map(el => el.textContent.trim())
    `);
    console.log("All 4 chat titles in sidebar (newest first):", allTitles);
    if (allTitles.length !== 4) {
      throw new Error(`Expected 4 sessions, found ${allTitles.length}`);
    }
    console.log("PASS: 4 distinct conversations created and listed newest-first!");

    // 9. Test Deletion and Immediate Reflow:
    // Delete the 2nd chat in the list (index 1)
    console.log("\n[STEP 9] Deleting chat at index 1 from list [Chat 4, Chat 3, Chat 2, Chat 1]...");
    const targetToDeleteTitle = allTitles[1];
    console.log(`Deleting item at index 1: "${targetToDeleteTitle}"`);

    await cdp.evaluate(`
      const items = document.querySelectorAll('.cg-session-item');
      if (items.length > 1) {
        const deleteBtn = items[1].querySelector('.cg-session-delete');
        if (deleteBtn) deleteBtn.click();
      }
    `);
    await sleep(1500);

    const postDeleteTitles = await cdp.evaluate(`
      Array.from(document.querySelectorAll('.cg-session-title')).map(el => el.textContent.trim())
    `);
    console.log("Titles after deletion (reflowed list):", postDeleteTitles);
    if (postDeleteTitles.length !== 3) {
      throw new Error(`Expected 3 sessions after deletion, found ${postDeleteTitles.length}`);
    }
    if (postDeleteTitles.includes(targetToDeleteTitle)) {
      throw new Error(`Deleted chat "${targetToDeleteTitle}" is still present in sidebar!`);
    }
    // Verify order reflowed seamlessly: [Chat 4, Chat 2, Chat 1]
    const expectedRemaining = [allTitles[0], allTitles[2], allTitles[3]];
    console.log("Expected remaining titles:", expectedRemaining);
    if (JSON.stringify(postDeleteTitles) !== JSON.stringify(expectedRemaining)) {
      throw new Error(`Reflow order mismatch! Expected: ${JSON.stringify(expectedRemaining)}, Got: ${JSON.stringify(postDeleteTitles)}`);
    }
    console.log("PASS: Deletion reflowed immediately without gaps, stale entries, or placeholders!");

    // 10. Test Refresh while on a blank session
    console.log("\n[STEP 10] Testing refresh while on a blank session...");
    await cdp.evaluate(`document.querySelector('.cg-new-chat-btn').click();`);
    await sleep(600);
    console.log("Now on blank session. Reloading browser...");
    await cdp.send("Page.reload");
    await sleep(2500);
    await waitForSelector(".stSidebar", 10000);

    const postRefreshCount = await cdp.evaluate(`document.querySelectorAll('.cg-session-item').length`);
    const postRefreshTitles = await cdp.evaluate(`
      Array.from(document.querySelectorAll('.cg-session-title')).map(el => el.textContent.trim())
    `);
    console.log(`Session count after refresh: ${postRefreshCount}, titles:`, postRefreshTitles);
    if (postRefreshCount !== 3) {
      throw new Error(`Expected 3 sessions after refresh, found ${postRefreshCount}`);
    }
    if (postRefreshTitles.some((t) => t === "New Conversation")) {
      throw new Error("Found unwanted 'New Conversation' placeholder after browser refresh!");
    }
    console.log("PASS: Refresh while blank session is open preserves clean list without empty entries!");

    // 11. Test switching between existing chats
    console.log("\n[STEP 11] Testing switching between existing chats...");
    await cdp.evaluate(`
      const items = document.querySelectorAll('.cg-session-item');
      if (items.length > 0) items[0].click();
    `);
    await sleep(1000);

    const activeItemDot = await cdp.evaluate(`Boolean(document.querySelector('.cg-session-item.active'))`);
    const hasMessages = await cdp.evaluate(`document.querySelectorAll('.cg-msg-group').length > 0`);
    console.log(`Active session highlighted: ${activeItemDot}, conversation messages loaded: ${hasMessages}`);
    if (!activeItemDot || !hasMessages) {
      throw new Error("Expected active session to be highlighted and messages displayed");
    }
    console.log("PASS: Switching between chats works smoothly and restores history!");

    // 12. Verify backend sessions synchronization
    console.log("\n[STEP 12] Verifying backend persistence via /api/sessions...");
    const backendRes = await fetch("http://127.0.0.1:8000/api/sessions");
    const backendSessions = await backendRes.json();
    console.log(`Backend returned ${backendSessions.length} session(s):`, backendSessions.map((s) => s.title || s.preview));
    if (backendSessions.length !== 3) {
      throw new Error(`Expected exactly 3 sessions in backend persistence, got ${backendSessions.length}`);
    }
    for (const bs of backendSessions) {
      if (!bs.preview || bs.title === "New Conversation") {
        throw new Error(`Invalid backend session found: ${JSON.stringify(bs)}`);
      }
    }
    console.log("PASS: Backend persistence is 100% synchronized with frontend!");

    console.log("\n========================================================");
    console.log("✅ ALL END-TO-END VERIFICATION CHECKS PASSED SUCCESSFULLY!");
    console.log("========================================================");
  } finally {
    try {
      edgeProcess.kill();
    } catch {}
    try {
      fs.rmSync(tempUserDataDir, { recursive: true, force: true });
    } catch {}
  }
}

runE2E().catch((err) => {
  console.error("\nE2E VERIFICATION FAILED:", err);
  process.exit(1);
});
