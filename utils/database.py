import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "bot.db")

async def get_db():
    return await aiosqlite.connect(DB_PATH)

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                count       INTEGER DEFAULT 0,
                week_count  INTEGER DEFAULT 0,
                last_reset  TEXT
            );

            CREATE TABLE IF NOT EXISTS squads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                owner_id    INTEGER NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS squad_members (
                squad_id    INTEGER,
                user_id     INTEGER,
                role        TEXT DEFAULT 'member',  -- owner / co-owner / member
                joined_at   TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (squad_id, user_id),
                FOREIGN KEY (squad_id) REFERENCES squads(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS squad_stats (
                squad_id        INTEGER PRIMARY KEY,
                total_messages  INTEGER DEFAULT 0,
                FOREIGN KEY (squad_id) REFERENCES squads(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reports (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id     INTEGER,
                reporter_name   TEXT,
                report_type     TEXT,
                reported_user   TEXT,
                reason          TEXT,
                evidence        TEXT,
                extra_info      TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS warnings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                mod_id      INTEGER,
                reason      TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS config (
                key     TEXT PRIMARY KEY,
                value   TEXT
            );
        """)
        await db.commit()

# ── Messages ──────────────────────────────────────────────────────────────────

async def increment_message(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO messages (user_id, username, count, week_count)
            VALUES (?, ?, 1, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                count = count + 1,
                week_count = week_count + 1,
                username = excluded.username
        """, (user_id, username))
        await db.commit()

async def get_leaderboard(limit=10, weekly=True):
    col = "week_count" if weekly else "count"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT user_id, username, {col} as msgs FROM messages ORDER BY {col} DESC LIMIT ?",
            (limit,)
        ) as cur:
            return await cur.fetchall()

async def get_user_rank(user_id: int, weekly=True):
    col = "week_count" if weekly else "count"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT user_id, username, {col} as msgs, "
            f"(SELECT COUNT(*)+1 FROM messages m2 WHERE m2.{col} > m1.{col}) as rank "
            f"FROM messages m1 WHERE user_id = ?",
            (user_id,)
        ) as cur:
            return await cur.fetchone()

async def reset_weekly():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE messages SET week_count = 0")
        await db.commit()

# ── Squads ─────────────────────────────────────────────────────────────────────

async def create_squad(name: str, owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute("INSERT INTO squads (name, owner_id) VALUES (?, ?)", (name, owner_id))
            squad_id = cur.lastrowid
            await db.execute("INSERT INTO squad_members (squad_id, user_id, role) VALUES (?, ?, 'owner')", (squad_id, owner_id))
            await db.execute("INSERT INTO squad_stats (squad_id) VALUES (?)", (squad_id,))
            await db.commit()
            return squad_id
        except aiosqlite.IntegrityError:
            return None

async def get_squad_by_name(name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM squads WHERE LOWER(name) = LOWER(?)", (name,)) as cur:
            return await cur.fetchone()

async def get_user_squad(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.*, sm.role FROM squads s
            JOIN squad_members sm ON s.id = sm.squad_id
            WHERE sm.user_id = ?
        """, (user_id,)) as cur:
            return await cur.fetchone()

async def get_squad_members(squad_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM squad_members WHERE squad_id = ? ORDER BY role", (squad_id,)
        ) as cur:
            return await cur.fetchall()

async def update_squad_member_role(squad_id: int, user_id: int, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE squad_members SET role = ? WHERE squad_id = ? AND user_id = ?",
            (role, squad_id, user_id)
        )
        await db.commit()

async def add_squad_member(squad_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO squad_members (squad_id, user_id) VALUES (?, ?)", (squad_id, user_id)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def remove_squad_member(squad_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM squad_members WHERE squad_id = ? AND user_id = ?", (squad_id, user_id)
        )
        await db.commit()

async def delete_squad(squad_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM squads WHERE id = ?", (squad_id,))
        await db.commit()

async def rename_squad(squad_id: int, new_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("UPDATE squads SET name = ? WHERE id = ?", (new_name, squad_id))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def get_squad_leaderboard(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.name, ss.total_messages,
                   COUNT(sm.user_id) as member_count
            FROM squads s
            JOIN squad_stats ss ON s.id = ss.squad_id
            JOIN squad_members sm ON s.id = sm.squad_id
            GROUP BY s.id ORDER BY ss.total_messages DESC LIMIT ?
        """, (limit,)) as cur:
            return await cur.fetchall()

# ── Reports ────────────────────────────────────────────────────────────────────

async def save_report(reporter_id, reporter_name, report_type, reported_user, reason, evidence, extra_info):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO reports (reporter_id, reporter_name, report_type, reported_user, reason, evidence, extra_info)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (reporter_id, reporter_name, report_type, reported_user, reason, evidence, extra_info))
        await db.commit()
        return cur.lastrowid

# ── Warnings ───────────────────────────────────────────────────────────────────

async def add_warning(user_id: int, mod_id: int, reason: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warnings (user_id, mod_id, reason) VALUES (?, ?, ?)",
            (user_id, mod_id, reason)
        )
        await db.commit()

async def get_warnings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM warnings WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ) as cur:
            return await cur.fetchall()