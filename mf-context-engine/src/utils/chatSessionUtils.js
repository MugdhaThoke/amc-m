/**
 * Utilities for chat sessions management.
 */

/**
 * Check if a session has at least one actual, meaningful user message.
 * @param {object} session
 * @returns {boolean}
 */
export function hasUserMessage(session) {
  if (!session || !Array.isArray(session.history)) return false;
  return session.history.some(
    (m) => m && m.role === "user" && typeof m.content === "string" && m.content.trim().length > 0
  );
}

/**
 * Filter and sort chat sessions for sidebar display.
 * Only returns sessions that have at least one user message,
 * sorted newest-first by updatedAt or createdAt.
 * @param {Record<string, object>} chatSessions
 * @param {number} [limit=50]
 * @returns {Array<{session_id: string, title: string, words: string[], turn_count: number}>}
 */
export function formatSidebarSessions(chatSessions, limit = 50) {
  if (!chatSessions || typeof chatSessions !== "object") return [];

  return Object.entries(chatSessions)
    .filter(([_, s]) => hasUserMessage(s))
    .sort((a, b) => {
      const timeA = b[1]?.updatedAt || b[1]?.createdAt || 0;
      const timeB = a[1]?.updatedAt || a[1]?.createdAt || 0;
      return timeA - timeB;
    })
    .slice(0, limit)
    .map(([id, s]) => {
      const firstUserMsg = (s.history || []).find(
        (m) => m && m.role === "user" && typeof m.content === "string" && m.content.trim().length > 0
      );
      const userContent = firstUserMsg?.content?.trim() || "";
      const fallbackTitle = userContent
        ? (userContent.length > 45 ? userContent.slice(0, 44) + "…" : userContent)
        : "Conversation";
      const title = (s.title && s.title !== "New Conversation") ? s.title : fallbackTitle;
      const words = title.split(/\s+/).filter(Boolean);
      return {
        session_id: id,
        title,
        words,
        turn_count: (s.history || []).filter((m) => m.role === "user").length,
      };
    });
}
