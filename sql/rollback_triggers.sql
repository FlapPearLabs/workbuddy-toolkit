-- ==============================================================================
-- WorkBuddy Multi-Account Universal Workspace Rollback
-- 移除共享触发器，恢复官方默认的严格多账号数据隔离
-- ==============================================================================

-- 1. 移除触发器
DROP TRIGGER IF EXISTS trg_sessions_force_shared_insert;
DROP TRIGGER IF EXISTS trg_sessions_force_shared_update;

-- 2. 如需将所有会话重新绑定到特定账号，可执行如下语句（将 <YOUR_UID> 替换为真实 UID）：
-- UPDATE sessions SET user_id = '<YOUR_UID>' WHERE user_id = '';
