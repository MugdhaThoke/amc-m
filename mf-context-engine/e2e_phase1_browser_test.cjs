// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// End-to-End Browser-based Test for Phase 1 Feedback System
// ===========================================================================

const { chromium } = require('playwright');
const path = require('path');

async function runBrowserE2E() {
  console.log('--- Starting Phase 1 End-to-End Browser Test ---');
  let browser;

  try {
    // 1. Launch Microsoft Edge on Windows
    console.log('[1/6] Launching Edge browser via Playwright...');
    browser = await chromium.launch({
      channel: 'msedge',
      headless: true,
    });
    const context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
    });
    const page = await context.newPage();

    // 2. Navigate to mf-context-engine frontend
    console.log('[2/6] Navigating to http://localhost:5173...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });
    console.log('Page loaded. Title:', await page.title());

    // 3. Authenticate as compliance_officer
    console.log('[3/6] Performing authentication on LoginScreen...');
    const userInput = page.locator('input[type="text"], input[name="userId"], input[placeholder*="User ID"], #userId').first();
    const passInput = page.locator('input[type="password"]').first();
    const submitBtn = page.locator('button[type="submit"]').first();

    await userInput.waitFor({ state: 'visible', timeout: 10000 });
    await userInput.fill('compliance_officer');
    await passInput.fill('Compliance@2026');
    await submitBtn.click();

    // Wait for login transition
    console.log('Waiting for login transition and workspace mount...');
    await page.waitForTimeout(3000);

    // Verify session token is present in localStorage or auth state
    const authStorage = await page.evaluate(() => {
      return {
        userToken: localStorage.getItem('ns_cg_auth_token_v1') || localStorage.getItem('auth_token') || sessionStorage.getItem('token'),
        currentUser: localStorage.getItem('ns_cg_active_user_v1'),
      };
    });
    console.log('Auth state detected:', authStorage.currentUser ? 'User logged in' : 'Checking page content');

    // 4. Test Phase 1 GET /api/feedback/status with category_breakdown via browser fetch
    console.log('[4/6] Testing GET /api/feedback/status with category_breakdown from browser context...');
    const statusResult = await page.evaluate(async () => {
      // First submit a test feedback with categories F08 and F04 to guarantee existing issue
      const uniqueQuery = 'E2E Browser Test Query: What is the TER for Bluechip?';
      const stored = sessionStorage.getItem('ns_cg_auth_session_v1') || localStorage.getItem('ns_cg_auth_session_v1');
      let token = null;
      if (stored) {
        try {
          token = JSON.parse(stored).token;
        } catch {}
      }
      const headers = {
        'Content-Type': 'application/json',
        'X-User-Role': 'Reviewer',
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      // Submit feedback
      const submitRes = await fetch('/api/feedback', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          response_id: `resp_browser_${Date.now()}`,
          interaction_id: `int_browser_${Date.now()}`,
          session_id: `sess_browser_${Date.now()}`,
          turn_number: 1,
          query_text: uniqueQuery,
          selected_categories: ['F08', 'F04'],
          feedback_text: 'Browser E2E test comment',
        }),
      });
      const submitData = await submitRes.json();

      // Probe status endpoint
      const statusRes = await fetch(`/api/feedback/status?query=${encodeURIComponent(uniqueQuery)}`, {
        headers,
      });
      const statusData = await statusRes.json();

      return { submitData, statusData };
    });

    console.log('Status Probe Result:');
    console.log('- has_existing_issue:', statusResult.statusData.has_existing_issue);
    console.log('- issue_id:', statusResult.statusData.issue_id);
    console.log('- match_type:', statusResult.statusData.match_type);
    console.log('- category_breakdown:', JSON.stringify(statusResult.statusData.category_breakdown, null, 2));

    if (!statusResult.statusData.has_existing_issue) {
      throw new Error('Expected has_existing_issue to be true');
    }
    if (!Array.isArray(statusResult.statusData.category_breakdown) || statusResult.statusData.category_breakdown.length === 0) {
      throw new Error('Expected category_breakdown to contain items');
    }

    // 5. Test Phase 1 GET /api/feedback/mine strictly session-scoped
    console.log('[5/6] Testing GET /api/feedback/mine strictly session-scoped from browser context...');
    const mineResult = await page.evaluate(async () => {
      const stored = sessionStorage.getItem('ns_cg_auth_session_v1') || localStorage.getItem('ns_cg_auth_session_v1');
      let token = null;
      if (stored) {
        try {
          token = JSON.parse(stored).token;
        } catch {}
      }
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch('/api/feedback/mine', { headers });
      const data = await res.json();
      return { status: res.status, data };
    });

    console.log('My Feedback Endpoint Result:');
    console.log('- HTTP Status:', mineResult.status);
    console.log('- Total issues for current user:', mineResult.data.total);
    if (mineResult.data.items && mineResult.data.items.length > 0) {
      const first = mineResult.data.items[0];
      console.log('- Sample Item:');
      console.log('  * issue_id:', first.issue_id);
      console.log('  * canonical_query_text:', first.canonical_query_text);
      console.log('  * user_reported_categories:', first.user_reported_categories);
      console.log('  * also_reported_by_count:', first.also_reported_by_count);
    }

    if (mineResult.status !== 200) {
      throw new Error(`Expected HTTP 200 on /api/feedback/mine, got ${mineResult.status}`);
    }

    // 6. Test IDOR protection from browser: verify /api/feedback/mine without token fails with 401
    console.log('[6/6] Testing security: Unauthenticated GET /api/feedback/mine returns 401...');
    const unauthResult = await page.evaluate(async () => {
      const res = await fetch('/api/feedback/mine');
      return { status: res.status };
    });
    console.log('- Unauthenticated status code:', unauthResult.status);
    if (unauthResult.status !== 401) {
      throw new Error(`Expected HTTP 401 on unauthenticated /api/feedback/mine, got ${unauthResult.status}`);
    }

    // Take verification screenshot
    const screenshotPath = path.join(__dirname, 'e2e_verification.png');
    await page.screenshot({ path: screenshotPath });
    console.log('Verification screenshot saved to:', screenshotPath);

    console.log('\n============================================================');
    console.log('SUCCESS: All Phase 1 browser-based end-to-end tests passed!');
    console.log('============================================================');
  } catch (err) {
    console.error('Browser E2E Test Failed:', err);
    process.exitCode = 1;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

runBrowserE2E();
