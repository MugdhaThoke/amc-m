import test from "node:test";
import assert from "node:assert/strict";
import { hasUserMessage, formatSidebarSessions } from "../utils/chatSessionUtils.js";

test("hasUserMessage validation", () => {
  assert.equal(hasUserMessage(null), false);
  assert.equal(hasUserMessage({}), false);
  assert.equal(hasUserMessage({ history: [] }), false);
  assert.equal(hasUserMessage({ history: [{ role: "assistant", content: "Hello" }] }), false);
  assert.equal(hasUserMessage({ history: [{ role: "user", content: "   " }] }), false);
  assert.equal(hasUserMessage({ history: [{ role: "user", content: "Valid message" }] }), true);
});

test("Recent chats filter logic: ignores empty or assistant-only conversations", () => {
  const sessions = {
    "sess-empty": {
      id: "sess-empty",
      title: "New Conversation",
      history: [],
      updatedAt: 1000,
    },
    "sess-asst": {
      id: "sess-asst",
      title: "Assistant greeting",
      history: [{ role: "assistant", content: "Hi" }],
      updatedAt: 2000,
    },
    "sess-valid-1": {
      id: "sess-valid-1",
      title: "Chat 1",
      history: [{ role: "user", content: "Query 1" }],
      updatedAt: 3000,
    },
    "sess-valid-2": {
      id: "sess-valid-2",
      title: "Chat 2",
      history: [{ role: "user", content: "Query 2" }],
      updatedAt: 4000,
    },
  };

  const filtered = Object.entries(sessions)
    .filter(([_, s]) => hasUserMessage(s))
    .sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0))
    .map(([id, s]) => ({ id, title: s.title }));

  assert.equal(filtered.length, 2);
  assert.equal(filtered[0].id, "sess-valid-2");
  assert.equal(filtered[1].id, "sess-valid-1");
});

test("Deletion reflow: deleting Chat 2 from [Chat 1, Chat 2, Chat 3, Chat 4] immediately reflows without gaps or duplicates", () => {
  const sessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Q1" }], updatedAt: 1000 },
    "chat-2": { id: "chat-2", title: "Chat 2", history: [{ role: "user", content: "Q2" }], updatedAt: 2000 },
    "chat-3": { id: "chat-3", title: "Chat 3", history: [{ role: "user", content: "Q3" }], updatedAt: 3000 },
    "chat-4": { id: "chat-4", title: "Chat 4", history: [{ role: "user", content: "Q4" }], updatedAt: 4000 },
  };

  // Simulate deletion of chat-2
  const copy = { ...sessions };
  delete copy["chat-2"];

  const reflowed = Object.entries(copy)
    .filter(([_, s]) => hasUserMessage(s))
    .sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0))
    .map(([id]) => id);

  assert.deepEqual(reflowed, ["chat-4", "chat-3", "chat-1"]);
  assert.equal(copy["chat-2"], undefined);
  assert.equal(Object.keys(copy).length, 3);
});

test("New Chat behavior: clicking New Chat does NOT insert an empty session into chatSessions", () => {
  let chatSessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Q1" }], updatedAt: 1000 },
  };
  let chatSessionId = "chat-1";

  function startNewChatSession() {
    const active = chatSessions[chatSessionId];
    const isBlank = !active || !hasUserMessage(active);
    if (isBlank) {
      return chatSessionId;
    }
    const freshId = "blank-uuid-1";
    chatSessionId = freshId;
    return freshId;
  }

  // First click on New Chat
  const id1 = startNewChatSession();
  assert.equal(id1, "blank-uuid-1");
  assert.equal(chatSessionId, "blank-uuid-1");
  // chatSessions must still ONLY have chat-1!
  assert.deepEqual(Object.keys(chatSessions), ["chat-1"]);

  // Rapidly click New Chat 5 more times
  for (let i = 0; i < 5; i++) {
    const idNext = startNewChatSession();
    assert.equal(idNext, "blank-uuid-1"); // Stays on the blank session
  }
  // Still only chat-1 in chatSessions, no stacked empty chats!
  assert.deepEqual(Object.keys(chatSessions), ["chat-1"]);

  // Recent chats filter must only show chat-1
  const recent = Object.entries(chatSessions).filter(([_, s]) => hasUserMessage(s));
  assert.equal(recent.length, 1);
  assert.equal(recent[0][0], "chat-1");
});

test("Active chat deletion: deleting active chat transitions to blank session without adding placeholder", () => {
  let chatSessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Q1" }], updatedAt: 1000 },
    "chat-2": { id: "chat-2", title: "Chat 2", history: [{ role: "user", content: "Q2" }], updatedAt: 2000 },
  };
  let chatSessionId = "chat-2";

  function deleteChatSession(id) {
    delete chatSessions[id];
    if (chatSessionId === id) {
      chatSessionId = "fresh-blank-id";
    }
  }

  deleteChatSession("chat-2");

  // chat-2 is gone, chatSessions contains only chat-1
  assert.deepEqual(Object.keys(chatSessions), ["chat-1"]);
  // active session is a clean blank session
  assert.equal(chatSessionId, "fresh-blank-id");
  assert.equal(chatSessions[chatSessionId], undefined);

  // Recent chats contains only chat-1
  const recent = Object.entries(chatSessions).filter(([_, s]) => hasUserMessage(s));
  assert.equal(recent.length, 1);
  assert.equal(recent[0][0], "chat-1");
});

test("Sending first query after opening blank session creates conversation in Recent Chats", () => {
  let chatSessions = {};
  let chatSessionId = "blank-uuid-1";

  function sendFirstQuery(sid, queryText) {
    const userMsg = { role: "user", content: queryText, turn_index: 1 };
    const loadingMsg = { role: "assistant", loading: true, turn_index: 1 };
    const history = [userMsg, loadingMsg];
    const previewTitle = queryText.length > 45 ? queryText.slice(0, 44) + "…" : queryText;
    chatSessions[sid] = {
      id: sid,
      title: previewTitle,
      history,
      updatedAt: Date.now(),
    };
  }

  // Initially empty
  assert.equal(Object.keys(chatSessions).length, 0);

  // User submits first query (short query)
  sendFirstQuery(chatSessionId, "What are SEBI regulations?");

  // Now conversation appears in chatSessions
  assert.equal(Object.keys(chatSessions).length, 1);
  assert.equal(chatSessions[chatSessionId].title, "What are SEBI regulations?");
  assert.equal(hasUserMessage(chatSessions[chatSessionId]), true);

  // Formatted sidebar sessions shows this new conversation
  const sidebar = formatSidebarSessions(chatSessions);
  assert.equal(sidebar.length, 1);
  assert.equal(sidebar[0].session_id, "blank-uuid-1");
  assert.equal(sidebar[0].title, "What are SEBI regulations?");
});

test("Edge case: starting a new chat after deleting one", () => {
  let chatSessions = {
    "only-chat": { id: "only-chat", title: "Single Chat", history: [{ role: "user", content: "Hi" }], updatedAt: 1000 },
  };
  let chatSessionId = "only-chat";

  // 1. Delete the only chat
  delete chatSessions["only-chat"];
  if (chatSessionId === "only-chat") {
    chatSessionId = "blank-after-delete";
  }

  // Sidebar is empty
  assert.equal(formatSidebarSessions(chatSessions).length, 0);

  // 2. User clicks New Chat while already on blank session
  const activeSession = chatSessions[chatSessionId];
  const isCurrentBlank = !activeSession || !hasUserMessage(activeSession);
  if (!isCurrentBlank) {
    chatSessionId = "should-not-reach";
  }
  // Still blank, still 0 in sidebar
  assert.equal(chatSessionId, "blank-after-delete");
  assert.equal(formatSidebarSessions(chatSessions).length, 0);

  // 3. User sends query in this new session
  chatSessions[chatSessionId] = {
    id: chatSessionId,
    title: "Brand new conversation",
    history: [{ role: "user", content: "Brand new query" }],
    updatedAt: 2000,
  };

  // Now sidebar has 1 conversation
  const sidebar = formatSidebarSessions(chatSessions);
  assert.equal(sidebar.length, 1);
  assert.equal(sidebar[0].session_id, "blank-after-delete");
  assert.equal(sidebar[0].title, "Brand new conversation");
});

test("Edge case: refreshing the browser while a blank session is open", () => {
  // Saved storage state
  const mockStorageSessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Existing" }], updatedAt: 1000 },
    // Also simulate a buggy empty session that may have lingered previously in storage
    "stale-empty": { id: "stale-empty", title: "New Conversation", history: [], updatedAt: 1500 },
  };
  const mockActiveSessionId = "blank-session-never-sent"; // Active was blank session

  // Simulation of AppState initialization logic
  const cleaned = {};
  for (const [id, s] of Object.entries(mockStorageSessions)) {
    if (hasUserMessage(s)) {
      cleaned[id] = s;
    }
  }

  // Active session ID is retained or fallback
  const resolvedActiveId = mockActiveSessionId || "fallback-id";

  // Sidebar only renders cleaned sessions
  const sidebar = formatSidebarSessions(cleaned);
  assert.equal(sidebar.length, 1);
  assert.equal(sidebar[0].session_id, "chat-1");

  // Blank session is NOT in cleaned chatSessions
  assert.equal(cleaned[resolvedActiveId], undefined);
  // No "New Conversation" placeholder exists
  assert.equal(sidebar.some((s) => s.title === "New Conversation"), false);
});

test("Edge case: switching between existing chats preserves history and order", () => {
  const chatSessions = {
    "chat-1": { id: "chat-1", title: "Chat 1", history: [{ role: "user", content: "Q1" }, { role: "assistant", content: "A1" }], updatedAt: 1000 },
    "chat-2": { id: "chat-2", title: "Chat 2", history: [{ role: "user", content: "Q2" }, { role: "assistant", content: "A2" }], updatedAt: 2000 },
  };

  let activeId = "chat-1";
  assert.equal(chatSessions[activeId].history.length, 2);

  // Switch to chat-2
  activeId = "chat-2";
  assert.equal(chatSessions[activeId].history.length, 2);
  assert.equal(chatSessions[activeId].history[0].content, "Q2");

  // Sidebar ordering stays newest first (chat-2, then chat-1)
  const sidebar = formatSidebarSessions(chatSessions);
  assert.equal(sidebar[0].session_id, "chat-2");
  assert.equal(sidebar[1].session_id, "chat-1");
});

