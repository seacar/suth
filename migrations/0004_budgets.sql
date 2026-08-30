-- Phase 3: per-project/per-caller spend caps — plan §6/§9. A caller with no
-- row here is uncapped; enforcement only applies once a budget is declared.
CREATE TABLE IF NOT EXISTS budgets (
    project_id    TEXT NOT NULL REFERENCES projects(id),
    caller        TEXT NOT NULL DEFAULT '',
    period        TEXT NOT NULL DEFAULT 'all-time',
    token_cap     INTEGER NOT NULL,
    spend_to_date INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, caller, period)
);
