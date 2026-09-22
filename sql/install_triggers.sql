-- ==============================================================================
-- WorkBuddy Multi-Account Universal Workspace Patch
-- 让所有已保存或新登录的 WorkBuddy 账号共享同一套工作区、历史对话与会话上下文
-- ==============================================================================

-- 1. 将现存所有历史会话的 user_id 置空，触发官方的跨账号全局放行逻辑：
-- (WHERE user_id = :currentUserId OR user_id IS NULL OR user_id = '')
UPDATE sessions SET user_id = '' WHERE user_id IS NOT NULL AND user_id != '';

-- 2. 创建自动注入触发器：新会话插入时自动将 user_id 置空
CREATE TRIGGER IF NOT EXISTS trg_sessions_force_shared_insert
AFTER INSERT ON sessions
WHEN NEW.user_id != '' AND NEW.user_id IS NOT NULL
BEGIN
    UPDATE sessions SET user_id = '' WHERE id = NEW.id;
END;

-- 3. 创建防篡改更新触发器：当会话 user_id 被更新为特定账号时，自动重置为空
CREATE TRIGGER IF NOT EXISTS trg_sessions_force_shared_update
AFTER UPDATE OF user_id ON sessions
WHEN NEW.user_id != '' AND NEW.user_id IS NOT NULL
BEGIN
    UPDATE sessions SET user_id = '' WHERE id = NEW.id;
END;
