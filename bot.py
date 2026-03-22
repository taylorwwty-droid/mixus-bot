import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import asyncio
import os
import random
import datetime
import re
import io

# Load .env file if present (for external hosting like Wispbyte)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ===== CONFIGURATION =====
REPLIT_DOMAIN = os.environ.get("REPLIT_DEV_DOMAIN", "")
BANNER_URL = f"https://{REPLIT_DOMAIN}/api/public/banner.png" if REPLIT_DOMAIN else ""
EMBED_COLOR = 0x5DADE2

BULLET = "<:28474orangedot:1485287850747363551>"
ARROW  = "<:9153arroworange:1485287829339902012>"
STAR   = "<:20525orangestar2:1485287869903016197>"
GIFT   = "<:8469orangegift:1485287889842606110>"

# Number emojis for polls / WYR
NUM_EMOJIS = [
    "<:194205brown1:1485289005376475318>",
    "<:274503brown2:1485289045994242148>",
    "<:872961brown3:1485289163652595712>",
    "<:358225brown4:1485289097307099226>",
    "<:256087brown5:1485289026645655562>",
    "<:944763brown6:1485289193671364749>",
    "<:624343brown7:1485289120027639998>",
    "<:777059brown8:1485289142912028742>",
    "<:333876brown9:1485289068861325476>",
]

CURRENCY = "Mixus Stars"

PERMS_LIST = [
    "kick", "ban", "warn", "mute", "manage_punishments",
    "manage_tickets", "manage_applications", "manage_giveaways",
    "manage_economy", "manage_store", "manage_reaction_roles", "manage_bot"
]

DB_PATH = "amg_bot.db"

# ===== DATABASE =====
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            log_channel INTEGER,
            welcome_channel INTEGER,
            ticket_category INTEGER,
            ticket_log_channel INTEGER,
            app_log_channel INTEGER,
            middleman_log_channel INTEGER,
            mute_role INTEGER
        );
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            perm_node TEXT,
            role_id INTEGER,
            UNIQUE(guild_id, perm_node, role_id)
        );
        CREATE TABLE IF NOT EXISTS punishments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            mod_id INTEGER,
            type TEXT,
            reason TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            inviter_id INTEGER,
            invite_code TEXT
        );
        CREATE TABLE IF NOT EXISTS invite_cache (
            guild_id INTEGER,
            code TEXT,
            uses INTEGER,
            inviter_id INTEGER,
            PRIMARY KEY (guild_id, code)
        );
        CREATE TABLE IF NOT EXISTS economy (
            guild_id INTEGER,
            user_id INTEGER,
            balance INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS economy_cooldowns (
            guild_id INTEGER,
            user_id INTEGER,
            last_earned TEXT,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT,
            price INTEGER,
            item_type TEXT,
            role_id INTEGER,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER,
            prize TEXT,
            winners INTEGER DEFAULT 1,
            host_id INTEGER,
            end_time TEXT,
            ended INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS reaction_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            message_id INTEGER,
            emoji TEXT,
            role_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            user_id INTEGER,
            ticket_type TEXT DEFAULT 'ticket',
            status TEXT DEFAULT 'open',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS automod_settings (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            spam_enabled INTEGER DEFAULT 1,
            bulk_pings_enabled INTEGER DEFAULT 1,
            invite_links_enabled INTEGER DEFAULT 1,
            external_links_enabled INTEGER DEFAULT 0,
            nsfw_links_enabled INTEGER DEFAULT 1,
            spam_threshold INTEGER DEFAULT 5,
            ping_threshold INTEGER DEFAULT 5,
            exempt_roles TEXT DEFAULT '',
            exempt_channels TEXT DEFAULT '',
            automod_log_channel INTEGER
        );
        CREATE TABLE IF NOT EXISTS counting (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            current_count INTEGER DEFAULT 0,
            last_user_id INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS message_counters (
            guild_id INTEGER,
            channel_id INTEGER,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, channel_id)
        );
    """)
    # Migrations
    for migration in [
        "ALTER TABLE guild_settings ADD COLUMN staff_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN economy_log_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN qotd_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN qotd_ping_role INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN counting_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN general_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN fancy_welcome_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN welcome_ping_role INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN welcome_rules_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN welcome_general_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN welcome_trading_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN welcome_qotd_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN welcome_gws_channel INTEGER",
        "ALTER TABLE guild_settings ADD COLUMN welcome_roles_channel INTEGER",
    ]:
        try:
            c.execute(migration)
        except Exception:
            pass
    conn.commit()
    conn.close()

# ===== HELPERS =====
def get_conn():
    return sqlite3.connect(DB_PATH)

def make_embed(title: str, description: str = None, color: int = EMBED_COLOR) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    if BANNER_URL:
        embed.set_image(url=BANNER_URL)
    embed.set_footer(text="AMG | Adopt Me Giveaways")
    embed.timestamp = datetime.datetime.utcnow()
    return embed

async def has_perm(interaction: discord.Interaction, perm_node: str) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT role_id FROM permissions WHERE guild_id=? AND perm_node=?",
              (interaction.guild.id, perm_node))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return False
    user_role_ids = {r.id for r in interaction.user.roles}
    return any(role_id in user_role_ids for (role_id,) in rows)

async def log_action(guild: discord.Guild, title: str, description: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT log_channel FROM guild_settings WHERE guild_id=?", (guild.id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        ch = guild.get_channel(row[0])
        if ch:
            try:
                await ch.send(embed=make_embed(title, description))
            except Exception:
                pass

async def log_economy(guild: discord.Guild, description: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT economy_log_channel FROM guild_settings WHERE guild_id=?", (guild.id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        ch = guild.get_channel(row[0])
        if ch:
            try:
                await ch.send(embed=make_embed(f"{STAR} Economy Log", description))
            except Exception:
                pass

async def cache_invites(guild: discord.Guild):
    try:
        invites = await guild.invites()
        conn = get_conn()
        c = conn.cursor()
        for inv in invites:
            inviter_id = inv.inviter.id if inv.inviter else None
            c.execute("INSERT OR REPLACE INTO invite_cache (guild_id, code, uses, inviter_id) VALUES (?,?,?,?)",
                      (guild.id, inv.code, inv.uses or 0, inviter_id))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ===== AUTOMOD HELPERS =====
# Track spam per user: {guild_id: {user_id: [timestamps]}}
_spam_tracker: dict[int, dict[int, list]] = {}

NSFW_DOMAINS = [
    "pornhub", "xvideos", "xnxx", "redtube", "youporn", "tube8",
    "xhamster", "spankbang", "eporner", "drtuber", "nuvid", "onlyfans"
]

INVITE_PATTERN = re.compile(
    r"(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)[a-zA-Z0-9\-]+",
    re.IGNORECASE
)

URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE
)

async def run_automod(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT enabled, spam_enabled, bulk_pings_enabled, invite_links_enabled, "
              "external_links_enabled, nsfw_links_enabled, spam_threshold, ping_threshold, "
              "exempt_roles, exempt_channels, automod_log_channel "
              "FROM automod_settings WHERE guild_id=?", (message.guild.id,))
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return

    (enabled, spam_en, pings_en, invite_en, links_en, nsfw_en,
     spam_thresh, ping_thresh, exempt_roles_str, exempt_channels_str, log_ch_id) = row

    # Check exemptions
    exempt_role_ids = set(int(x) for x in exempt_roles_str.split(",") if x.strip().isdigit())
    exempt_ch_ids = set(int(x) for x in exempt_channels_str.split(",") if x.strip().isdigit())
    if message.channel.id in exempt_ch_ids:
        return
    user_role_ids = {r.id for r in message.author.roles}
    if user_role_ids & exempt_role_ids:
        return
    if message.author.guild_permissions.administrator:
        return

    action_taken = None
    reason = None

    content = message.content

    # Spam detection
    if spam_en:
        now = datetime.datetime.utcnow().timestamp()
        guild_tracker = _spam_tracker.setdefault(message.guild.id, {})
        user_times = guild_tracker.setdefault(message.author.id, [])
        user_times.append(now)
        # Keep only last 5 seconds
        user_times[:] = [t for t in user_times if now - t <= 5]
        if len(user_times) >= spam_thresh:
            action_taken = "delete"
            reason = f"Spam detected ({len(user_times)} messages in 5 seconds)"
            user_times.clear()

    # Bulk pings
    if pings_en and not action_taken:
        ping_count = len(message.mentions) + len(message.role_mentions)
        if ping_count >= ping_thresh:
            action_taken = "delete"
            reason = f"Bulk pings detected ({ping_count} mentions)"

    # Invite links
    if invite_en and not action_taken:
        if INVITE_PATTERN.search(content):
            action_taken = "delete"
            reason = "Discord invite link"

    # NSFW links
    if nsfw_en and not action_taken:
        urls = URL_PATTERN.findall(content)
        for url in urls:
            for domain in NSFW_DOMAINS:
                if domain in url.lower():
                    action_taken = "delete"
                    reason = f"NSFW link detected"
                    break
            if action_taken:
                break

    # External links (optional)
    if links_en and not action_taken:
        if URL_PATTERN.search(content):
            action_taken = "delete"
            reason = "External link"

    if action_taken == "delete":
        try:
            await message.delete()
        except Exception:
            pass
        try:
            warn_msg = await message.channel.send(
                embed=make_embed(
                    "⚠️ AutoMod",
                    f"{BULLET} {message.author.mention}, your message was removed.\n{ARROW} **Reason:** {reason}"
                )
            )
            await asyncio.sleep(5)
            await warn_msg.delete()
        except Exception:
            pass
        if log_ch_id:
            log_ch = message.guild.get_channel(log_ch_id)
            if log_ch:
                try:
                    await log_ch.send(embed=make_embed(
                        "🛡️ AutoMod Action",
                        f"{BULLET} **User:** {message.author.mention} (`{message.author.id}`)\n"
                        f"{BULLET} **Channel:** {message.channel.mention}\n"
                        f"{ARROW} **Reason:** {reason}\n"
                        f"{BULLET} **Content:** ```{content[:500]}```"
                    ))
                except Exception:
                    pass

# ===== SPAWN ITEMS =====
SPAWN_ITEMS = ["🥚 Egg", "🐾 Pet"]
CLAIM_TICKET_URL = "https://discord.com/channels/1125428468981698570/1483199129361317948"

class ItemClaimView(discord.ui.View):
    def __init__(self, item: str, spawned_by_guild: int):
        super().__init__(timeout=120)
        self.item = item
        self.spawned_by_guild = spawned_by_guild
        self.claimed = False

    @discord.ui.button(label="🎉 Claim!", style=discord.ButtonStyle.success, custom_id="amg_item_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed:
            await interaction.response.send_message(
                embed=make_embed("❌ Already Claimed", f"{BULLET} Someone already claimed this item!"),
                ephemeral=True)
            return
        self.claimed = True
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"
        await interaction.message.edit(view=self)
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} You claimed the {self.item}!",
            f"{BULLET} **Winner:** {interaction.user.mention}\n"
            f"{ARROW} Head to the ticket channel to claim your reward!\n"
            f"{BULLET} **Claim here:** [Open a Ticket]({CLAIM_TICKET_URL})"
        ))
        await interaction.channel.send(embed=make_embed(
            f"{GIFT} Item Claimed!",
            f"{STAR} {interaction.user.mention} claimed the **{self.item}**!\n\n"
            f"{BULLET} To collect your reward, create a ticket here:\n"
            f"{ARROW} [Click to open ticket channel]({CLAIM_TICKET_URL})"
        ))


# ===== BOT SETUP =====
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

_views_registered = False
_giveaway_task_started = False

# ===== EVENTS =====
@bot.event
async def on_ready():
    global _views_registered, _giveaway_task_started
    init_db()
    print(f"Adopt Me Giveaways Bot online as {bot.user} (ID: {bot.user.id})")
    if not _views_registered:
        bot.add_view(TicketOpenView())
        bot.add_view(TicketCloseView())
        bot.add_view(ApplicationCloseView())
        bot.add_view(MiddlemanCloseView())
        bot.add_view(MiddlemanOpenView())
        _views_registered = True
    if not _giveaway_task_started:
        check_giveaways.start()
        _giveaway_task_started = True
    await tree.sync()
    for guild in bot.guilds:
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild.id,))
        conn.commit()
        conn.close()
        await cache_invites(guild)
    print("Slash commands synced and invite cache loaded.")

@bot.event
async def on_guild_join(guild: discord.Guild):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild.id,))
    conn.commit()
    conn.close()
    await cache_invites(guild)

@bot.event
async def on_invite_create(invite: discord.Invite):
    conn = get_conn()
    c = conn.cursor()
    inviter_id = invite.inviter.id if invite.inviter else None
    c.execute("INSERT OR REPLACE INTO invite_cache (guild_id, code, uses, inviter_id) VALUES (?,?,?,?)",
              (invite.guild.id, invite.code, invite.uses or 0, inviter_id))
    conn.commit()
    conn.close()

@bot.event
async def on_invite_delete(invite: discord.Invite):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM invite_cache WHERE guild_id=? AND code=?", (invite.guild.id, invite.code))
    conn.commit()
    conn.close()

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    inviter = None
    inviter_count = 0
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT welcome_channel, fancy_welcome_channel, welcome_ping_role,
                        welcome_rules_channel, welcome_general_channel, welcome_trading_channel,
                        welcome_qotd_channel, welcome_gws_channel, welcome_roles_channel
                 FROM guild_settings WHERE guild_id=?""", (guild.id,))
    settings_row = c.fetchone()
    conn.close()

    # ---- Invite tracking ----
    try:
        current_invites = await guild.invites()
        conn2 = get_conn()
        c2 = conn2.cursor()
        for inv in current_invites:
            c2.execute("SELECT uses FROM invite_cache WHERE guild_id=? AND code=?", (guild.id, inv.code))
            row = c2.fetchone()
            old_uses = row[0] if row else 0
            if inv.uses > old_uses:
                inviter = inv.inviter
                c2.execute("UPDATE invite_cache SET uses=? WHERE guild_id=? AND code=?",
                           (inv.uses, guild.id, inv.code))
                if inviter:
                    c2.execute("INSERT INTO invites (guild_id, user_id, inviter_id, invite_code) VALUES (?,?,?,?)",
                               (guild.id, member.id, inviter.id, inv.code))
                break
        if inviter:
            c2.execute("SELECT COUNT(*) FROM invites WHERE guild_id=? AND inviter_id=?",
                       (guild.id, inviter.id))
            inviter_count = c2.fetchone()[0]
        conn2.commit()
        conn2.close()
    except Exception:
        pass

    # ---- Invite-based welcome (channel 1 — simple) ----
    if settings_row and settings_row[0]:
        inv_ch = guild.get_channel(settings_row[0])
        if inv_ch:
            inv_text = (
                f"{ARROW} **Invited by:** {inviter.mention} `({inviter_count} total invites)`"
                if inviter else f"{ARROW} **Invited by:** Unknown"
            )
            embed = make_embed(
                f"{STAR} Welcome to {guild.name}!",
                f"{BULLET} **Member:** {member.mention}\n"
                f"{inv_text}\n"
                f"{BULLET} **Account Created:** <t:{int(member.created_at.timestamp())}:R>\n"
                f"{BULLET} **Member Count:** `{guild.member_count}`"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            try:
                await inv_ch.send(content=member.mention, embed=embed)
            except Exception:
                pass

    # ---- Fancy welcome message (channel 2 — styled like image) ----
    if settings_row and settings_row[1]:
        fw_ch = guild.get_channel(settings_row[1])
        if fw_ch:
            ping_role = guild.get_role(settings_row[2]) if settings_row[2] else None

            def ch_link(col_idx):
                ch_id = settings_row[col_idx]
                return f"<#{ch_id}>" if ch_id else "—"

            rules_ch    = ch_link(3)
            general_ch  = ch_link(4)
            trading_ch  = ch_link(5)
            qotd_ch     = ch_link(6)
            gws_ch      = ch_link(7)
            roles_ch    = ch_link(8)

            embed = discord.Embed(
                description=(
                    f"**{member.mention} welcome to the… best adopt me giveaway and event server ever!**\n\n"
                    f"{BULLET} **Check these channels:**\n"
                    f"{ARROW} {rules_ch} — rules\n"
                    f"{ARROW} {general_ch} — general\n"
                    f"{ARROW} {trading_ch} — trading\n"
                    f"{ARROW} {qotd_ch} — qotd\n\n"
                    f"{BULLET} **Check Our Current Giveaways:**\n"
                    f"{ARROW} {gws_ch}\n\n"
                    f"{BULLET} **MAKE SURE TO GET YOUR ROLES:**\n"
                    f"{ARROW} {roles_ch}\n\n"
                    f"*never put on tomorrow, what can be done today!*"
                ),
                color=EMBED_COLOR
            )
            embed.set_author(name=f"Welcome to {guild.name} 🎉",
                             icon_url=guild.icon.url if guild.icon else None)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="AMG | Adopt Me Giveaways")
            embed.timestamp = datetime.datetime.utcnow()
            try:
                content = ping_role.mention if ping_role else member.mention
                await fw_ch.send(content=content, embed=embed)
            except Exception:
                pass

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    await bot.process_commands(message)

    # Run automod
    await run_automod(message)

    guild_id = message.guild.id
    user_id = message.author.id
    now = datetime.datetime.utcnow()

    # ---- Counting channel ----
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT channel_id, current_count, last_user_id FROM counting WHERE guild_id=?", (guild_id,))
    count_row = c.fetchone()
    conn.close()

    if count_row and count_row[0] == message.channel.id:
        count_channel_id, current_count, last_user_id = count_row
        text = message.content.strip()
        expected = current_count + 1
        valid_number = False
        try:
            num = int(text)
            if num == expected:
                valid_number = True
        except ValueError:
            pass

        if valid_number:
            if last_user_id == user_id:
                # Same user counted twice
                conn = get_conn()
                c = conn.cursor()
                c.execute("UPDATE counting SET current_count=0, last_user_id=0 WHERE guild_id=?", (guild_id,))
                conn.commit()
                conn.close()
                try:
                    await message.add_reaction("❌")
                    await message.channel.send(embed=make_embed(
                        "❌ Counting Reset!",
                        f"{BULLET} {message.author.mention} counted twice in a row!\n"
                        f"{ARROW} Count has been reset to **0**. Start again from **1**!"
                    ))
                except Exception:
                    pass
            else:
                conn = get_conn()
                c = conn.cursor()
                c.execute("UPDATE counting SET current_count=?, last_user_id=? WHERE guild_id=?",
                          (expected, user_id, guild_id))
                conn.commit()
                conn.close()
                try:
                    await message.add_reaction("✅")
                except Exception:
                    pass
        else:
            # Wrong number or non-number in counting channel
            conn = get_conn()
            c = conn.cursor()
            c.execute("UPDATE counting SET current_count=0, last_user_id=0 WHERE guild_id=?", (guild_id,))
            conn.commit()
            conn.close()
            try:
                await message.add_reaction("❌")
                await message.channel.send(embed=make_embed(
                    "❌ Wrong Number! Count Reset!",
                    f"{BULLET} {message.author.mention} ruined the count!\n"
                    f"{ARROW} The correct number was **{expected}**.\n"
                    f"{BULLET} Count has been reset to **0**. Start again from **1**!"
                ))
            except Exception:
                pass
        return

    # ---- General channel message spawn (every 200 messages) ----
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT general_channel FROM guild_settings WHERE guild_id=?", (guild_id,))
    gen_row = c.fetchone()
    conn.close()

    if gen_row and gen_row[0] and gen_row[0] == message.channel.id:
        conn = get_conn()
        c = conn.cursor()
        c.execute("""INSERT INTO message_counters (guild_id, channel_id, count) VALUES (?,?,1)
                     ON CONFLICT(guild_id, channel_id) DO UPDATE SET count=count+1""",
                  (guild_id, message.channel.id))
        c.execute("SELECT count FROM message_counters WHERE guild_id=? AND channel_id=?",
                  (guild_id, message.channel.id))
        counter_row = c.fetchone()
        current_msg_count = counter_row[0] if counter_row else 0
        if current_msg_count > 0 and current_msg_count % 200 == 0:
            c.execute("UPDATE message_counters SET count=0 WHERE guild_id=? AND channel_id=?",
                      (guild_id, message.channel.id))
            conn.commit()
            conn.close()
            spawned_item = random.choice(SPAWN_ITEMS)
            view = ItemClaimView(item=spawned_item, spawned_by_guild=guild_id)
            try:
                await message.channel.send(embed=make_embed(
                    f"{GIFT} An Item Has Spawned!",
                    f"{STAR} **{spawned_item}** has appeared in the chat!\n\n"
                    f"{BULLET} Be the **first** to click **Claim** to win it!\n"
                    f"{ARROW} After claiming, create a ticket to collect your reward.\n\n"
                    f"{BULLET} **Expires in 2 minutes!**"
                ), view=view)
            except Exception:
                pass
        else:
            conn.commit()
            conn.close()

    # ---- Economy: earn AMG Stars per message ----
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT last_earned FROM economy_cooldowns WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = c.fetchone()
    can_earn = True
    if row and row[0]:
        last = datetime.datetime.fromisoformat(row[0])
        if (now - last).total_seconds() < 60:
            can_earn = False
    if can_earn:
        earned = random.randint(1, 10)
        c.execute("""INSERT INTO economy (guild_id, user_id, balance) VALUES (?,?,?)
                     ON CONFLICT(guild_id, user_id) DO UPDATE SET balance=balance+?""",
                  (guild_id, user_id, earned, earned))
        c.execute("""INSERT INTO economy_cooldowns (guild_id, user_id, last_earned) VALUES (?,?,?)
                     ON CONFLICT(guild_id, user_id) DO UPDATE SET last_earned=?""",
                  (guild_id, user_id, now.isoformat(), now.isoformat()))
        conn.commit()
        conn.close()
        await log_economy(message.guild,
            f"{BULLET} **User:** {message.author.mention}\n"
            f"{ARROW} Earned `{earned}` {CURRENCY} {STAR}\n"
            f"{BULLET} **Channel:** {message.channel.mention}"
        )
    else:
        conn.commit()
        conn.close()

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
              (payload.guild_id, payload.message_id, str(payload.emoji)))
    row = c.fetchone()
    conn.close()
    if row:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            role = guild.get_role(row[0])
            member = guild.get_member(payload.user_id)
            if role and member:
                try:
                    await member.add_roles(role)
                except Exception:
                    pass

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
              (payload.guild_id, payload.message_id, str(payload.emoji)))
    row = c.fetchone()
    conn.close()
    if row:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            role = guild.get_role(row[0])
            member = guild.get_member(payload.user_id)
            if role and member:
                try:
                    await member.remove_roles(role)
                except Exception:
                    pass

# ===== GIVEAWAY TASK =====
@tasks.loop(seconds=30)
async def check_giveaways():
    now = datetime.datetime.utcnow()
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT id, guild_id, channel_id, message_id, prize, winners, host_id
                 FROM giveaways WHERE ended=0 AND end_time <= ?""", (now.isoformat(),))
    rows = c.fetchall()
    conn.close()
    for row in rows:
        await end_giveaway(*row)

async def end_giveaway(gw_id, guild_id, channel_id, message_id, prize, winners_count, host_id):
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    ch = guild.get_channel(channel_id)
    if not ch:
        return
    try:
        msg = await ch.fetch_message(message_id)
    except Exception:
        return
    entrants = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == str(GIFT):
            async for user in reaction.users():
                if not user.bot:
                    entrants.append(user)
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE giveaways SET ended=1 WHERE id=?", (gw_id,))
    conn.commit()
    conn.close()
    if not entrants:
        embed = make_embed(f"{GIFT} Giveaway Ended!", f"{BULLET} **Prize:** {prize}\n{BULLET} **Winners:** No valid entrants found.")
        await msg.edit(embed=embed)
        await ch.send(embed=embed)
        return
    actual = min(winners_count, len(entrants))
    winners = random.sample(entrants, actual)
    w_mentions = ", ".join(w.mention for w in winners)
    embed = make_embed(
        f"{GIFT} Giveaway Ended!",
        f"{BULLET} **Prize:** {prize}\n{STAR} **Winner(s):** {w_mentions}\n{ARROW} Congratulations!\n{BULLET} Create a support ticket in <#1483199129361317948> to claim your prize."
    )
    await msg.edit(embed=embed)
    await ch.send(content=w_mentions, embed=make_embed(
        f"{GIFT} Congratulations!",
        f"{STAR} You won **{prize}**!\n{ARROW} Head to <#1483199129361317948> in the server and create a support ticket to claim your prize."
    ))

def parse_duration(s: str) -> int:
    total = 0
    for val, unit in re.findall(r"(\d+)([smhd])", s.lower()):
        v = int(val)
        if unit == "s": total += v
        elif unit == "m": total += v * 60
        elif unit == "h": total += v * 3600
        elif unit == "d": total += v * 86400
    return total

# ===== PERSISTENT VIEWS =====

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger,
                       custom_id="amg_close_ticket", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id, ticket_type FROM tickets WHERE guild_id=? AND channel_id=? AND status='open'",
                  (interaction.guild.id, interaction.channel.id))
        row = c.fetchone()
        if not row:
            conn.close()
            await interaction.response.send_message(
                embed=make_embed("❌ Error", f"{BULLET} This is not an open ticket."), ephemeral=True)
            return
        user_id, ticket_type = row
        c.execute("UPDATE tickets SET status='closed' WHERE guild_id=? AND channel_id=?",
                  (interaction.guild.id, interaction.channel.id))
        c.execute("SELECT ticket_log_channel FROM guild_settings WHERE guild_id=?", (interaction.guild.id,))
        log_row = c.fetchone()
        conn.commit()
        conn.close()
        user = interaction.guild.get_member(user_id)
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Ticket Closed",
            f"{BULLET} **Closed by:** {interaction.user.mention}\n{BULLET} **Type:** {ticket_type.title()}"
        ))
        if log_row and log_row[0]:
            log_ch = interaction.guild.get_channel(log_row[0])
            if log_ch:
                try:
                    await log_ch.send(embed=make_embed(
                        f"{STAR} Ticket Closed — {ticket_type.title()}",
                        f"{BULLET} **Channel:** #{interaction.channel.name}\n"
                        f"{BULLET} **User:** {user.mention if user else user_id}\n"
                        f"{BULLET} **Closed by:** {interaction.user.mention}"
                    ))
                except Exception:
                    pass
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass


class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary,
                       custom_id="amg_open_ticket", emoji="📩")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status='open' AND ticket_type='ticket'",
                  (interaction.guild.id, interaction.user.id))
        existing = c.fetchone()
        if existing:
            ch = interaction.guild.get_channel(existing[0])
            conn.close()
            if ch:
                await interaction.response.send_message(
                    embed=make_embed("❌ Existing Ticket",
                                     f"{BULLET} You already have an open ticket: {ch.mention}"),
                    ephemeral=True)
                return
        c.execute("SELECT ticket_category, ticket_log_channel FROM guild_settings WHERE guild_id=?",
                  (interaction.guild.id,))
        row = c.fetchone()
        category_id = row[0] if row else None
        log_id = row[1] if row else None
        category = interaction.guild.get_channel(category_id) if category_id else None
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True)
        }
        ch = await interaction.guild.create_text_channel(
            f"ticket-{interaction.user.name}", category=category, overwrites=overwrites)
        c.execute("INSERT INTO tickets (guild_id, channel_id, user_id, ticket_type, created_at) VALUES (?,?,?,?,?)",
                  (interaction.guild.id, ch.id, interaction.user.id, "ticket",
                   datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        embed = make_embed(
            f"{STAR} Support Ticket",
            f"{BULLET} **User:** {interaction.user.mention}\n"
            f"{BULLET} **Opened:** <t:{int(datetime.datetime.utcnow().timestamp())}:R>\n\n"
            f"{ARROW} Please describe your issue and a staff member will assist you shortly.\n"
            f"{BULLET} Use the button below to close the ticket when resolved."
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await ch.send(content=interaction.user.mention, embed=embed, view=TicketCloseView())
        if log_id:
            log_ch = interaction.guild.get_channel(log_id)
            if log_ch:
                try:
                    await log_ch.send(embed=make_embed(
                        f"{STAR} Ticket Opened",
                        f"{BULLET} **User:** {interaction.user.mention}\n{BULLET} **Channel:** {ch.mention}"
                    ))
                except Exception:
                    pass
        await interaction.response.send_message(
            embed=make_embed(f"{STAR} Ticket Created", f"{BULLET} Your ticket: {ch.mention}"),
            ephemeral=True)


class ApplicationCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="amg_app_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await has_perm(interaction, "manage_applications"):
            await interaction.response.send_message(
                embed=make_embed("❌ No Permission",
                                 f"{BULLET} You don't have permission to manage applications."),
                ephemeral=True)
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id FROM tickets WHERE guild_id=? AND channel_id=? AND ticket_type='application' AND status='open'",
                  (interaction.guild.id, interaction.channel.id))
        row = c.fetchone()
        if not row:
            conn.close()
            await interaction.response.send_message(
                embed=make_embed("❌ Error", f"{BULLET} No open application found."), ephemeral=True)
            return
        c.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (interaction.channel.id,))
        conn.commit()
        conn.close()
        user = interaction.guild.get_member(row[0])
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Application Approved",
            f"{BULLET} **Approved by:** {interaction.user.mention}"))
        if user:
            try:
                await user.send(embed=make_embed(
                    f"{STAR} Application Approved — {interaction.guild.name}",
                    f"{ARROW} Congratulations! Your application has been approved!\n"
                    f"{BULLET} Please check the server for further instructions."
                ))
            except Exception:
                pass
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="amg_app_deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await has_perm(interaction, "manage_applications"):
            await interaction.response.send_message(
                embed=make_embed("❌ No Permission",
                                 f"{BULLET} You don't have permission to manage applications."),
                ephemeral=True)
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id FROM tickets WHERE guild_id=? AND channel_id=? AND ticket_type='application' AND status='open'",
                  (interaction.guild.id, interaction.channel.id))
        row = c.fetchone()
        if not row:
            conn.close()
            await interaction.response.send_message(
                embed=make_embed("❌ Error", f"{BULLET} No open application found."), ephemeral=True)
            return
        c.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (interaction.channel.id,))
        conn.commit()
        conn.close()
        user = interaction.guild.get_member(row[0])
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Application Denied",
            f"{BULLET} **Denied by:** {interaction.user.mention}"))
        if user:
            try:
                await user.send(embed=make_embed(
                    f"{STAR} Application Result — {interaction.guild.name}",
                    f"{ARROW} Unfortunately, your application has been denied at this time.\n"
                    f"{BULLET} You may apply again in the future. Keep improving!"
                ))
            except Exception:
                pass
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass


class MiddlemanCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Complete Trade", style=discord.ButtonStyle.success,
                       custom_id="amg_mm_complete")
    async def complete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await has_perm(interaction, "manage_tickets"):
            await interaction.response.send_message(
                embed=make_embed("❌ No Permission", f"{BULLET} Only staff can complete trades."),
                ephemeral=True)
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE tickets SET status='closed' WHERE guild_id=? AND channel_id=?",
                  (interaction.guild.id, interaction.channel.id))
        c.execute("SELECT middleman_log_channel FROM guild_settings WHERE guild_id=?",
                  (interaction.guild.id,))
        log_row = c.fetchone()
        conn.commit()
        conn.close()
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Trade Completed",
            f"{BULLET} **Completed by:** {interaction.user.mention}\n"
            f"{ARROW} This channel will be deleted shortly."
        ))
        if log_row and log_row[0]:
            log_ch = interaction.guild.get_channel(log_row[0])
            if log_ch:
                try:
                    await log_ch.send(embed=make_embed(
                        f"{STAR} Middleman Trade Completed",
                        f"{BULLET} **Channel:** #{interaction.channel.name}\n"
                        f"{BULLET} **Completed by:** {interaction.user.mention}"
                    ))
                except Exception:
                    pass
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

    @discord.ui.button(label="Cancel Trade", style=discord.ButtonStyle.danger,
                       custom_id="amg_mm_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await has_perm(interaction, "manage_tickets"):
            await interaction.response.send_message(
                embed=make_embed("❌ No Permission", f"{BULLET} Only staff can cancel trades."),
                ephemeral=True)
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE tickets SET status='closed' WHERE guild_id=? AND channel_id=?",
                  (interaction.guild.id, interaction.channel.id))
        conn.commit()
        conn.close()
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Trade Cancelled",
            f"{BULLET} **Cancelled by:** {interaction.user.mention}\n"
            f"{ARROW} This channel will be deleted shortly."
        ))
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass


# ===== MIDDLEMAN PANEL =====
class MiddlemanModal(discord.ui.Modal, title="Middleman Request"):
    trader_name = discord.ui.TextInput(
        label="Other Trader's Discord Username",
        placeholder="e.g. CoolTrader123",
        max_length=100
    )
    trade_details = discord.ui.TextInput(
        label="Trade Details",
        placeholder="e.g. Trading my Shadow Dragon for a Frost Dragon",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT ticket_category, middleman_log_channel FROM guild_settings WHERE guild_id=?",
                  (interaction.guild.id,))
        row = c.fetchone()
        cat_id = row[0] if row else None
        mm_log_id = row[1] if row else None
        category = interaction.guild.get_channel(cat_id) if cat_id else None
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True)
        }
        safe_name = interaction.user.name[:20]
        ch = await interaction.guild.create_text_channel(
            f"mm-{safe_name}", category=category, overwrites=overwrites)
        c.execute("INSERT INTO tickets (guild_id, channel_id, user_id, ticket_type, created_at) VALUES (?,?,?,?,?)",
                  (interaction.guild.id, ch.id, interaction.user.id, "middleman",
                   datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        embed = make_embed(
            f"{STAR} Middleman Request",
            f"{BULLET} **Requester:** {interaction.user.mention}\n"
            f"{BULLET} **Other Trader:** {self.trader_name.value}\n"
            f"{BULLET} **Trade Details:** {self.trade_details.value}\n\n"
            f"{ARROW} A staff middleman will assist you shortly.\n"
            f"{BULLET} **Do NOT proceed** with the trade until a middleman is present.\n"
            f"{BULLET} Staff will use the buttons below to complete or cancel the trade."
        )
        await ch.send(content=interaction.user.mention, embed=embed, view=MiddlemanCloseView())
        if mm_log_id:
            log_ch = interaction.guild.get_channel(mm_log_id)
            if log_ch:
                try:
                    await log_ch.send(embed=make_embed(
                        f"{STAR} New Middleman Request",
                        f"{BULLET} **Requester:** {interaction.user.mention}\n"
                        f"{BULLET} **Other Trader:** {self.trader_name.value}\n"
                        f"{BULLET} **Channel:** {ch.mention}\n"
                        f"{ARROW} **Details:** {self.trade_details.value}"
                    ))
                except Exception:
                    pass
        await interaction.response.send_message(
            embed=make_embed(f"{STAR} Middleman Created",
                             f"{BULLET} Your middleman channel has been created: {ch.mention}"),
            ephemeral=True)


class MiddlemanOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.primary,
                       custom_id="amg_open_middleman", emoji="🤝")
    async def open_middleman(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status='open' AND ticket_type='middleman'",
                  (interaction.guild.id, interaction.user.id))
        existing = c.fetchone()
        conn.close()
        if existing:
            ch = interaction.guild.get_channel(existing[0])
            if ch:
                await interaction.response.send_message(
                    embed=make_embed("❌ Existing Request",
                                     f"{BULLET} You already have an open middleman request: {ch.mention}"),
                    ephemeral=True)
                return
        await interaction.response.send_modal(MiddlemanModal())


# ===== APPLICATION OPEN VIEW =====
class ApplicationOpenView(discord.ui.View):
    def __init__(self, position: str, questions: list[str]):
        super().__init__(timeout=None)
        self.position = position
        self.questions = questions

    @discord.ui.button(label="Apply Now", style=discord.ButtonStyle.primary,
                       custom_id="amg_open_application", emoji="📋")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status='open' AND ticket_type='application'",
                  (interaction.guild.id, interaction.user.id))
        existing = c.fetchone()
        conn.close()
        if existing:
            ch = interaction.guild.get_channel(existing[0])
            if ch:
                await interaction.response.send_message(
                    embed=make_embed("❌ Existing Application",
                                     f"{BULLET} You already have an open application: {ch.mention}"),
                    ephemeral=True)
                return
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Application Started",
            f"{BULLET} Check your DMs to complete your **{self.position}** application."
        ), ephemeral=True)
        answers = []
        try:
            dm = await interaction.user.create_dm()
            await dm.send(embed=make_embed(
                f"{STAR} Application — {self.position}",
                f"{ARROW} Answer each question within **5 minutes**. Your answers will be reviewed by staff."
            ))
            for i, q in enumerate(self.questions, 1):
                await dm.send(embed=make_embed(
                    f"Question {i} of {len(self.questions)}",
                    f"{BULLET} {q}"
                ))
                try:
                    msg = await bot.wait_for(
                        "message", timeout=300,
                        check=lambda m: m.author.id == interaction.user.id and isinstance(m.channel, discord.DMChannel))
                    answers.append(msg.content)
                except asyncio.TimeoutError:
                    await dm.send(embed=make_embed("❌ Timed Out",
                                                   f"{BULLET} Application cancelled due to inactivity."))
                    return
        except discord.Forbidden:
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT ticket_category, app_log_channel FROM guild_settings WHERE guild_id=?",
                  (interaction.guild.id,))
        row = c.fetchone()
        cat_id = row[0] if row else None
        log_id = row[1] if row else None
        conn.close()
        category = interaction.guild.get_channel(cat_id) if cat_id else None
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True)
        }
        app_ch = await interaction.guild.create_text_channel(
            f"app-{interaction.user.name}", category=category, overwrites=overwrites)
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO tickets (guild_id, channel_id, user_id, ticket_type, created_at) VALUES (?,?,?,?,?)",
                  (interaction.guild.id, app_ch.id, interaction.user.id, "application",
                   datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        qa_lines = "\n".join(
            f"{BULLET} **Q{i+1}:** {q}\n{ARROW} **A:** {a}"
            for i, (q, a) in enumerate(zip(self.questions, answers))
        )
        embed = make_embed(
            f"{STAR} Application — {self.position}",
            f"{BULLET} **Applicant:** {interaction.user.mention}\n"
            f"{BULLET} **Position:** {self.position}\n"
            f"{BULLET} **Submitted:** <t:{int(datetime.datetime.utcnow().timestamp())}:R>\n\n"
            f"{qa_lines}"
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await app_ch.send(embed=embed, view=ApplicationCloseView())
        if log_id:
            log_ch = interaction.guild.get_channel(log_id)
            if log_ch:
                try:
                    await log_ch.send(embed=make_embed(
                        f"{STAR} New Application Received",
                        f"{BULLET} **Applicant:** {interaction.user.mention}\n"
                        f"{BULLET} **Position:** {self.position}\n"
                        f"{BULLET} **Channel:** {app_ch.mention}"
                    ))
                except Exception:
                    pass
        await dm.send(embed=make_embed(
            f"{STAR} Application Submitted!",
            f"{BULLET} Your application for **{self.position}** has been submitted.\n"
            f"{ARROW} You will be notified of the outcome. Good luck!"
        ))


# ===== /setup COMMANDS =====
setup_group = app_commands.Group(name="setup", description="Server configuration commands")

@setup_group.command(name="logchannel", description="Set the moderation log channel")
@app_commands.describe(channel="Channel to send moderation logs")
async def setup_log(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, log_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET log_channel=?",
              (interaction.guild.id, channel.id, channel.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Log Channel Set",
        f"{BULLET} Moderation logs will be sent to {channel.mention}"
    ))

@setup_group.command(name="welcomechannel", description="Set the welcome channel for new members")
@app_commands.describe(channel="Channel to send welcome messages")
async def setup_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, welcome_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET welcome_channel=?",
              (interaction.guild.id, channel.id, channel.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Welcome Channel Set",
        f"{BULLET} Welcome messages will now be sent to {channel.mention}"
    ))

@setup_group.command(name="muterole", description="Set the mute role used by /mute")
@app_commands.describe(role="Role to assign when muting a member")
async def setup_muterole(interaction: discord.Interaction, role: discord.Role):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, mute_role) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET mute_role=?",
              (interaction.guild.id, role.id, role.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Mute Role Set",
        f"{BULLET} Mute role set to {role.mention}"
    ))

@setup_group.command(name="staffchannel", description="Set the channel for promotion, demotion and staff removal announcements")
@app_commands.describe(channel="Channel to send staff announcements")
async def setup_staff_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, staff_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET staff_channel=?",
              (interaction.guild.id, channel.id, channel.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Staff Channel Set",
        f"{BULLET} Promotions, demotions and staff removals will be posted in {channel.mention}"
    ))

@setup_group.command(name="economylogchannel", description="Set the channel for economy earn logs")
@app_commands.describe(channel="Channel to send economy logs (AMG Stars earned)")
async def setup_economy_log(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, economy_log_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET economy_log_channel=?",
              (interaction.guild.id, channel.id, channel.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Economy Log Channel Set",
        f"{BULLET} {CURRENCY} earn logs will be sent to {channel.mention}"
    ))

@setup_group.command(name="qotdchannel", description="Set the channel and ping role for /qotd")
@app_commands.describe(channel="Channel to post questions of the day", ping_role="Role to ping with each QOTD")
async def setup_qotd(interaction: discord.Interaction, channel: discord.TextChannel,
                     ping_role: discord.Role = None):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, qotd_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET qotd_channel=?",
              (interaction.guild.id, channel.id, channel.id))
    if ping_role:
        c.execute("UPDATE guild_settings SET qotd_ping_role=? WHERE guild_id=?",
                  (ping_role.id, interaction.guild.id))
    conn.commit()
    conn.close()
    role_str = f" | Ping role: {ping_role.mention}" if ping_role else ""
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} QOTD Channel Set",
        f"{BULLET} Questions of the day will be posted in {channel.mention}{role_str}"
    ))

@setup_group.command(name="ticketcategory", description="Set the category for new ticket channels")
@app_commands.describe(category="Category to create ticket channels under",
                       log_channel="Channel to log ticket events")
async def setup_ticket_category(interaction: discord.Interaction,
                                 category: discord.CategoryChannel,
                                 log_channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (interaction.guild.id,))
    c.execute("UPDATE guild_settings SET ticket_category=? WHERE guild_id=?",
              (category.id, interaction.guild.id))
    if log_channel:
        c.execute("UPDATE guild_settings SET ticket_log_channel=? WHERE guild_id=?",
                  (log_channel.id, interaction.guild.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Ticket Category Set",
        f"{BULLET} Tickets will be created under **{category.name}**"
    ))

@setup_group.command(name="middlemanchannel", description="Set the log channel for middleman requests")
@app_commands.describe(channel="Channel to log middleman requests")
async def setup_middleman_log(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, middleman_log_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET middleman_log_channel=?",
              (interaction.guild.id, channel.id, channel.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Middleman Log Channel Set",
        f"{BULLET} Middleman logs will be sent to {channel.mention}"
    ))

@setup_group.command(name="countingchannel", description="Set the channel for the counting game")
@app_commands.describe(channel="Channel where members will count")
async def setup_counting(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, counting_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET counting_channel=?",
              (interaction.guild.id, channel.id, channel.id))
    c.execute("INSERT INTO counting (guild_id, channel_id, current_count, last_user_id) VALUES (?,?,0,0) ON CONFLICT(guild_id) DO UPDATE SET channel_id=?, current_count=0, last_user_id=0",
              (interaction.guild.id, channel.id, channel.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Counting Channel Set",
        f"{BULLET} Counting game is now active in {channel.mention}\n"
        f"{ARROW} Members start from **1** and count up. Wrong number = reset!"
    ))

@setup_group.command(name="generalchannel", description="Set the general chat channel where items will spawn every 200 messages")
@app_commands.describe(channel="General chat channel for item spawns")
async def setup_general(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id, general_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET general_channel=?",
              (interaction.guild.id, channel.id, channel.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} General Channel Set",
        f"{BULLET} A random item (egg or pet) will spawn every **200 messages** in {channel.mention}\n"
        f"{ARROW} First member to click Claim wins the item!"
    ))

@setup_group.command(name="welcomemessage", description="Set up the fancy welcome message for new members")
@app_commands.describe(
    channel="Channel to send the welcome message to",
    ping_role="Role to ping when a member joins (optional)",
    rules_channel="Your #rules channel",
    general_channel="Your #general channel",
    trading_channel="Your #trading channel",
    qotd_channel="Your #qotd channel",
    giveaways_channel="Your giveaways channel",
    roles_channel="Your #roles channel"
)
async def setup_welcomemsg(interaction: discord.Interaction,
                            channel: discord.TextChannel,
                            ping_role: discord.Role = None,
                            rules_channel: discord.TextChannel = None,
                            general_channel: discord.TextChannel = None,
                            trading_channel: discord.TextChannel = None,
                            qotd_channel: discord.TextChannel = None,
                            giveaways_channel: discord.TextChannel = None,
                            roles_channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (interaction.guild.id,))
    c.execute("""UPDATE guild_settings SET
                    fancy_welcome_channel=?,
                    welcome_ping_role=?,
                    welcome_rules_channel=?,
                    welcome_general_channel=?,
                    welcome_trading_channel=?,
                    welcome_qotd_channel=?,
                    welcome_gws_channel=?,
                    welcome_roles_channel=?
                 WHERE guild_id=?""",
              (channel.id,
               ping_role.id if ping_role else None,
               rules_channel.id if rules_channel else None,
               general_channel.id if general_channel else None,
               trading_channel.id if trading_channel else None,
               qotd_channel.id if qotd_channel else None,
               giveaways_channel.id if giveaways_channel else None,
               roles_channel.id if roles_channel else None,
               interaction.guild.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Fancy Welcome Message Configured",
        f"{BULLET} New members will receive a welcome message in {channel.mention}\n"
        + (f"{BULLET} **Ping role:** {ping_role.mention}\n" if ping_role else "")
        + f"{ARROW} Test it by having someone join the server!"
    ))

tree.add_command(setup_group)


# ===== /perms COMMANDS =====
perms_group = app_commands.Group(name="perms", description="Permission management commands")

@perms_group.command(name="set", description="Link a permission node to a role")
@app_commands.describe(permission="Permission node to grant", role="Role to receive this permission")
@app_commands.choices(permission=[app_commands.Choice(name=p, value=p) for p in PERMS_LIST])
async def perms_set(interaction: discord.Interaction, permission: str, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Only administrators can manage permissions."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO permissions (guild_id, perm_node, role_id) VALUES (?,?,?)",
              (interaction.guild.id, permission, role.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Permission Set",
        f"{BULLET} **Node:** `{permission}`\n{ARROW} **Role:** {role.mention}"
    ))

@perms_group.command(name="remove", description="Remove a permission node from a role")
@app_commands.describe(permission="Permission node to remove", role="Role to remove the permission from")
@app_commands.choices(permission=[app_commands.Choice(name=p, value=p) for p in PERMS_LIST])
async def perms_remove(interaction: discord.Interaction, permission: str, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Only administrators can manage permissions."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM permissions WHERE guild_id=? AND perm_node=? AND role_id=?",
              (interaction.guild.id, permission, role.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Permission Removed",
        f"{BULLET} **Node:** `{permission}`\n{ARROW} **Role:** {role.mention} no longer has this permission"
    ))

@perms_group.command(name="view", description="View all current permission configurations")
async def perms_view(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Only administrators can view permissions."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT perm_node, role_id FROM permissions WHERE guild_id=?", (interaction.guild.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Permission Configuration",
            f"{BULLET} No permissions configured yet.\n{ARROW} Use `/perms set` to link roles to permissions."
        ))
        return
    perm_dict: dict[str, list[str]] = {}
    for node, role_id in rows:
        role = interaction.guild.get_role(role_id)
        if role:
            perm_dict.setdefault(node, []).append(role.mention)
    lines = [f"{BULLET} **`{node}`** {ARROW} {', '.join(roles)}" for node, roles in perm_dict.items()]
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Permission Configuration",
        "\n".join(lines)
    ))

tree.add_command(perms_group)


# ===== MODERATION COMMANDS =====
@tree.command(name="purge", description="Delete a number of messages from this channel")
@app_commands.describe(amount="Number of messages to delete (1–100)")
async def purge_cmd(interaction: discord.Interaction, amount: int):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to purge messages."),
            ephemeral=True)
        return
    if amount < 1 or amount > 100:
        await interaction.response.send_message(
            embed=make_embed("❌ Invalid Amount", f"{BULLET} Amount must be between 1 and 100."),
            ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(embed=make_embed(
        f"{STAR} Messages Purged",
        f"{BULLET} Deleted **{len(deleted)}** messages from {interaction.channel.mention}\n"
        f"{BULLET} **Purged by:** {interaction.user.mention}"
    ), ephemeral=True)
    await log_action(interaction.guild, f"{STAR} Messages Purged",
                     f"{BULLET} **Amount:** {len(deleted)}\n"
                     f"{BULLET} **Channel:** {interaction.channel.mention}\n"
                     f"{BULLET} **By:** {interaction.user.mention}")


@tree.command(name="addrole", description="Add a role to a member")
@app_commands.describe(member="Member to add the role to", role="Role to add")
async def addrole_cmd(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to manage roles."),
            ephemeral=True)
        return
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I cannot assign a role higher than or equal to my own top role."),
            ephemeral=True)
        return
    try:
        await member.add_roles(role, reason=f"Added by {interaction.user}")
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Role Added",
            f"{BULLET} **Member:** {member.mention}\n"
            f"{ARROW} **Role Added:** {role.mention}\n"
            f"{BULLET} **By:** {interaction.user.mention}"
        ))
        await log_action(interaction.guild, f"{STAR} Role Added",
                         f"{BULLET} **Member:** {member}\n"
                         f"{ARROW} **Role:** {role.name}\n"
                         f"{BULLET} **By:** {interaction.user.mention}")
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to add that role."),
            ephemeral=True)


@tree.command(name="removerole", description="Remove a role from a member")
@app_commands.describe(member="Member to remove the role from", role="Role to remove")
async def removerole_cmd(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to manage roles."),
            ephemeral=True)
        return
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I cannot remove a role higher than or equal to my own top role."),
            ephemeral=True)
        return
    try:
        await member.remove_roles(role, reason=f"Removed by {interaction.user}")
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Role Removed",
            f"{BULLET} **Member:** {member.mention}\n"
            f"{ARROW} **Role Removed:** {role.mention}\n"
            f"{BULLET} **By:** {interaction.user.mention}"
        ))
        await log_action(interaction.guild, f"{STAR} Role Removed",
                         f"{BULLET} **Member:** {member}\n"
                         f"{ARROW} **Role:** {role.name}\n"
                         f"{BULLET} **By:** {interaction.user.mention}")
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to remove that role."),
            ephemeral=True)


@tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason for the kick")
async def kick_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await has_perm(interaction, "kick"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to kick members."),
            ephemeral=True)
        return
    if not interaction.user.guild_permissions.administrator and member.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} You cannot kick someone with an equal or higher role."),
            ephemeral=True)
        return
    try:
        await member.kick(reason=f"{interaction.user} | {reason}")
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO punishments (guild_id, user_id, mod_id, type, reason, timestamp) VALUES (?,?,?,?,?,?)",
                  (interaction.guild.id, member.id, interaction.user.id, "kick", reason,
                   datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Member Kicked",
            f"{BULLET} **Member:** {member.mention} (`{member.id}`)\n"
            f"{BULLET} **Moderator:** {interaction.user.mention}\n"
            f"{ARROW} **Reason:** {reason}"
        ))
        await log_action(interaction.guild, f"{STAR} Member Kicked",
                         f"{BULLET} **Member:** {member} (`{member.id}`)\n"
                         f"{BULLET} **Mod:** {interaction.user.mention}\n"
                         f"{ARROW} **Reason:** {reason}")
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to kick this member."),
            ephemeral=True)


@tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="Member to ban", reason="Reason for the ban",
                       delete_days="Days of messages to delete (0–7)")
async def ban_cmd(interaction: discord.Interaction, member: discord.Member,
                  reason: str = "No reason provided", delete_days: int = 0):
    if not await has_perm(interaction, "ban"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to ban members."),
            ephemeral=True)
        return
    if not interaction.user.guild_permissions.administrator and member.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} You cannot ban someone with an equal or higher role."),
            ephemeral=True)
        return
    try:
        await member.ban(reason=f"{interaction.user} | {reason}",
                         delete_message_days=max(0, min(delete_days, 7)))
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO punishments (guild_id, user_id, mod_id, type, reason, timestamp) VALUES (?,?,?,?,?,?)",
                  (interaction.guild.id, member.id, interaction.user.id, "ban", reason,
                   datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Member Banned",
            f"{BULLET} **Member:** {member.mention} (`{member.id}`)\n"
            f"{BULLET} **Moderator:** {interaction.user.mention}\n"
            f"{ARROW} **Reason:** {reason}"
        ))
        await log_action(interaction.guild, f"{STAR} Member Banned",
                         f"{BULLET} **Member:** {member} (`{member.id}`)\n"
                         f"{BULLET} **Mod:** {interaction.user.mention}\n"
                         f"{ARROW} **Reason:** {reason}")
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to ban this member."),
            ephemeral=True)


@tree.command(name="unban", description="Unban a user by their ID")
@app_commands.describe(user_id="The user ID to unban", reason="Reason for the unban")
async def unban_cmd(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    if not await has_perm(interaction, "ban"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to unban members."),
            ephemeral=True)
        return
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=f"{interaction.user} | {reason}")
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Member Unbanned",
            f"{BULLET} **User:** {user.mention} (`{user.id}`)\n"
            f"{BULLET} **Moderator:** {interaction.user.mention}\n"
            f"{ARROW} **Reason:** {reason}"
        ))
        await log_action(interaction.guild, f"{STAR} Member Unbanned",
                         f"{BULLET} **User:** {user} (`{user.id}`)\n"
                         f"{BULLET} **Mod:** {interaction.user.mention}\n"
                         f"{ARROW} **Reason:** {reason}")
    except discord.NotFound:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} User not found or not currently banned."), ephemeral=True)
    except ValueError:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Invalid user ID provided."), ephemeral=True)


@tree.command(name="warn", description="Issue a warning to a member")
@app_commands.describe(member="Member to warn", reason="Reason for the warning")
async def warn_cmd(interaction: discord.Interaction, member: discord.Member,
                   reason: str = "No reason provided"):
    if not await has_perm(interaction, "warn"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to warn members."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO punishments (guild_id, user_id, mod_id, type, reason, timestamp) VALUES (?,?,?,?,?,?)",
              (interaction.guild.id, member.id, interaction.user.id, "warn", reason,
               datetime.datetime.utcnow().isoformat()))
    warn_id = c.lastrowid
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Member Warned",
        f"{BULLET} **Member:** {member.mention} (`{member.id}`)\n"
        f"{BULLET} **Moderator:** {interaction.user.mention}\n"
        f"{BULLET} **Warning ID:** `#{warn_id}`\n"
        f"{ARROW} **Reason:** {reason}"
    ))
    try:
        await member.send(embed=make_embed(
            f"{STAR} You received a warning in {interaction.guild.name}",
            f"{BULLET} **Warning ID:** `#{warn_id}`\n{ARROW} **Reason:** {reason}"
        ))
    except Exception:
        pass
    await log_action(interaction.guild, f"{STAR} Member Warned",
                     f"{BULLET} **Member:** {member} (`{member.id}`)\n"
                     f"{BULLET} **Mod:** {interaction.user.mention}\n"
                     f"{BULLET} **ID:** `#{warn_id}`\n"
                     f"{ARROW} **Reason:** {reason}")


@tree.command(name="unwarn", description="Remove a specific warning from a member")
@app_commands.describe(member="Member to remove a warning from", warn_id="Warning ID to remove")
async def unwarn_cmd(interaction: discord.Interaction, member: discord.Member, warn_id: int):
    if not await has_perm(interaction, "warn"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to remove warnings."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM punishments WHERE id=? AND guild_id=? AND user_id=? AND type='warn'",
              (warn_id, interaction.guild.id, member.id))
    if not c.fetchone():
        conn.close()
        await interaction.response.send_message(
            embed=make_embed("❌ Error",
                             f"{BULLET} Warning `#{warn_id}` not found for {member.mention}."),
            ephemeral=True)
        return
    c.execute("DELETE FROM punishments WHERE id=?", (warn_id,))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Warning Removed",
        f"{BULLET} **Member:** {member.mention}\n"
        f"{BULLET} **Warning ID:** `#{warn_id}` removed\n"
        f"{BULLET} **Removed by:** {interaction.user.mention}"
    ))
    await log_action(interaction.guild, f"{STAR} Warning Removed",
                     f"{BULLET} **Member:** {member}\n"
                     f"{BULLET} **Warning ID:** `#{warn_id}`\n"
                     f"{BULLET} **Removed by:** {interaction.user.mention}")


@tree.command(name="mute", description="Mute a member using the configured mute role")
@app_commands.describe(member="Member to mute", reason="Reason for the mute")
async def mute_cmd(interaction: discord.Interaction, member: discord.Member,
                   reason: str = "No reason provided"):
    if not await has_perm(interaction, "mute"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to mute members."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT mute_role FROM guild_settings WHERE guild_id=?", (interaction.guild.id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        await interaction.response.send_message(
            embed=make_embed("❌ Not Configured", f"{BULLET} No mute role set. Use `/setup muterole` first."),
            ephemeral=True)
        return
    mute_role = interaction.guild.get_role(row[0])
    if not mute_role:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Mute role not found. Please reconfigure with `/setup muterole`."),
            ephemeral=True)
        return
    try:
        await member.add_roles(mute_role, reason=f"{interaction.user} | {reason}")
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO punishments (guild_id, user_id, mod_id, type, reason, timestamp) VALUES (?,?,?,?,?,?)",
                  (interaction.guild.id, member.id, interaction.user.id, "mute", reason,
                   datetime.datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Member Muted",
            f"{BULLET} **Member:** {member.mention} (`{member.id}`)\n"
            f"{BULLET} **Moderator:** {interaction.user.mention}\n"
            f"{ARROW} **Reason:** {reason}"
        ))
        try:
            await member.send(embed=make_embed(
                f"{STAR} You have been muted in {interaction.guild.name}",
                f"{ARROW} **Reason:** {reason}"
            ))
        except Exception:
            pass
        await log_action(interaction.guild, f"{STAR} Member Muted",
                         f"{BULLET} **Member:** {member} (`{member.id}`)\n"
                         f"{BULLET} **Mod:** {interaction.user.mention}\n"
                         f"{ARROW} **Reason:** {reason}")
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to mute this member."),
            ephemeral=True)


@tree.command(name="unmute", description="Unmute a member by removing their mute role")
@app_commands.describe(member="Member to unmute")
async def unmute_cmd(interaction: discord.Interaction, member: discord.Member):
    if not await has_perm(interaction, "mute"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to unmute members."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT mute_role FROM guild_settings WHERE guild_id=?", (interaction.guild.id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        await interaction.response.send_message(
            embed=make_embed("❌ Not Configured", f"{BULLET} No mute role configured."), ephemeral=True)
        return
    mute_role = interaction.guild.get_role(row[0])
    if mute_role and mute_role in member.roles:
        await member.remove_roles(mute_role, reason=f"Unmuted by {interaction.user}")
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Member Unmuted",
            f"{BULLET} **Member:** {member.mention}\n{BULLET} **Moderator:** {interaction.user.mention}"
        ))
        await log_action(interaction.guild, f"{STAR} Member Unmuted",
                         f"{BULLET} **Member:** {member}\n{BULLET} **Mod:** {interaction.user.mention}")
    else:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} {member.mention} is not currently muted."),
            ephemeral=True)


@tree.command(name="punishments", description="View all punishments for a member")
@app_commands.describe(member="Member to look up")
async def punishments_cmd(interaction: discord.Interaction, member: discord.Member):
    if not await has_perm(interaction, "manage_punishments"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to view punishments."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, type, reason, mod_id, timestamp FROM punishments WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 25",
              (interaction.guild.id, member.id))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Punishments — {member.display_name}",
            f"{BULLET} This member has a clean record with no punishments."
        ))
        return
    lines = []
    for pid, ptype, reason, mod_id, ts in rows:
        mod = interaction.guild.get_member(mod_id)
        mod_str = mod.mention if mod else f"`{mod_id}`"
        dt = datetime.datetime.fromisoformat(ts)
        lines.append(
            f"{BULLET} `#{pid}` **{ptype.upper()}** by {mod_str}\n"
            f"{ARROW} {reason} — <t:{int(dt.timestamp())}:R>"
        )
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Punishments — {member.display_name}",
        "\n".join(lines)
    ))


@tree.command(name="punishment", description="Remove a specific punishment record")
@app_commands.describe(action="Action to take", punishment_id="The punishment record ID")
@app_commands.choices(action=[app_commands.Choice(name="remove", value="remove")])
async def punishment_cmd(interaction: discord.Interaction, action: str, punishment_id: int):
    if not await has_perm(interaction, "manage_punishments"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to manage punishments."),
            ephemeral=True)
        return
    if action == "remove":
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id, type FROM punishments WHERE id=? AND guild_id=?",
                  (punishment_id, interaction.guild.id))
        row = c.fetchone()
        if not row:
            conn.close()
            await interaction.response.send_message(
                embed=make_embed("❌ Error",
                                 f"{BULLET} Punishment record `#{punishment_id}` not found."),
                ephemeral=True)
            return
        c.execute("DELETE FROM punishments WHERE id=?", (punishment_id,))
        conn.commit()
        conn.close()
        user = interaction.guild.get_member(row[0])
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Punishment Removed",
            f"{BULLET} **ID:** `#{punishment_id}`\n"
            f"{BULLET} **Type:** {row[1].upper()}\n"
            f"{BULLET} **User:** {user.mention if user else row[0]}\n"
            f"{BULLET} **Removed by:** {interaction.user.mention}"
        ))
        await log_action(interaction.guild, f"{STAR} Punishment Removed",
                         f"{BULLET} **ID:** `#{punishment_id}` ({row[1].upper()})\n"
                         f"{BULLET} **Removed by:** {interaction.user.mention}")


# ===== AUTOMOD COMMANDS =====
automod_group = app_commands.Group(name="automod", description="AutoMod configuration")

@automod_group.command(name="setup", description="Configure and enable auto-moderation")
@app_commands.describe(
    enabled="Enable or disable automod",
    spam="Block spam (5+ messages in 5 seconds)",
    bulk_pings="Block bulk mentions/pings",
    invite_links="Block Discord invite links",
    external_links="Block all external links",
    nsfw_links="Block NSFW/adult website links",
    spam_threshold="Messages in 5 seconds to trigger spam filter (default: 5)",
    ping_threshold="Number of pings to trigger bulk ping filter (default: 5)",
    log_channel="Channel to log automod actions"
)
async def automod_setup(interaction: discord.Interaction,
                        enabled: bool = True,
                        spam: bool = True,
                        bulk_pings: bool = True,
                        invite_links: bool = True,
                        external_links: bool = False,
                        nsfw_links: bool = True,
                        spam_threshold: int = 5,
                        ping_threshold: int = 5,
                        log_channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    log_id = log_channel.id if log_channel else None
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO automod_settings
                 (guild_id, enabled, spam_enabled, bulk_pings_enabled, invite_links_enabled,
                  external_links_enabled, nsfw_links_enabled, spam_threshold, ping_threshold, automod_log_channel)
                 VALUES (?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(guild_id) DO UPDATE SET
                   enabled=?, spam_enabled=?, bulk_pings_enabled=?, invite_links_enabled=?,
                   external_links_enabled=?, nsfw_links_enabled=?, spam_threshold=?,
                   ping_threshold=?, automod_log_channel=?""",
              (interaction.guild.id, int(enabled), int(spam), int(bulk_pings), int(invite_links),
               int(external_links), int(nsfw_links), spam_threshold, ping_threshold, log_id,
               int(enabled), int(spam), int(bulk_pings), int(invite_links),
               int(external_links), int(nsfw_links), spam_threshold, ping_threshold, log_id))
    conn.commit()
    conn.close()

    def status(v): return "✅ Enabled" if v else "❌ Disabled"

    log_str = log_channel.mention if log_channel else "Not set"
    await interaction.response.send_message(embed=make_embed(
        f"🛡️ AutoMod {'Enabled' if enabled else 'Disabled'}",
        f"{BULLET} **Status:** {'✅ Active' if enabled else '❌ Inactive'}\n\n"
        f"{ARROW} **Filters:**\n"
        f"{BULLET} Spam: {status(spam)} (threshold: {spam_threshold} msgs/5s)\n"
        f"{BULLET} Bulk Pings: {status(bulk_pings)} (threshold: {ping_threshold} pings)\n"
        f"{BULLET} Invite Links: {status(invite_links)}\n"
        f"{BULLET} External Links: {status(external_links)}\n"
        f"{BULLET} NSFW Links: {status(nsfw_links)}\n\n"
        f"{BULLET} **Log Channel:** {log_str}"
    ))

@automod_group.command(name="exempt", description="Exempt a role or channel from automod")
@app_commands.describe(role="Role to exempt from automod", channel="Channel to exempt from automod")
async def automod_exempt(interaction: discord.Interaction,
                         role: discord.Role = None,
                         channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} Administrator permission required."), ephemeral=True)
        return
    if not role and not channel:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Provide at least a role or channel to exempt."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO automod_settings (guild_id) VALUES (?)", (interaction.guild.id,))
    c.execute("SELECT exempt_roles, exempt_channels FROM automod_settings WHERE guild_id=?",
              (interaction.guild.id,))
    row = c.fetchone()
    exempt_roles = row[0] if row and row[0] else ""
    exempt_channels = row[1] if row and row[1] else ""
    added = []
    if role:
        role_ids = [x for x in exempt_roles.split(",") if x.strip()]
        if str(role.id) not in role_ids:
            role_ids.append(str(role.id))
        exempt_roles = ",".join(role_ids)
        added.append(f"Role: {role.mention}")
    if channel:
        ch_ids = [x for x in exempt_channels.split(",") if x.strip()]
        if str(channel.id) not in ch_ids:
            ch_ids.append(str(channel.id))
        exempt_channels = ",".join(ch_ids)
        added.append(f"Channel: {channel.mention}")
    c.execute("UPDATE automod_settings SET exempt_roles=?, exempt_channels=? WHERE guild_id=?",
              (exempt_roles, exempt_channels, interaction.guild.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"🛡️ AutoMod Exemption Added",
        f"{BULLET} **Exempted:** {', '.join(added)}"
    ))

tree.add_command(automod_group)


# ===== TICKET COMMANDS =====
ticket_group = app_commands.Group(name="ticket", description="Ticket system management")

@ticket_group.command(name="setup", description="Post a ticket panel in a channel")
@app_commands.describe(channel="Channel to post the panel",
                       category="Category for new ticket channels",
                       log_channel="Channel to log ticket events")
async def ticket_setup(interaction: discord.Interaction, channel: discord.TextChannel,
                       category: discord.CategoryChannel = None,
                       log_channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_tickets"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to set up tickets."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (interaction.guild.id,))
    if category:
        c.execute("UPDATE guild_settings SET ticket_category=? WHERE guild_id=?",
                  (category.id, interaction.guild.id))
    if log_channel:
        c.execute("UPDATE guild_settings SET ticket_log_channel=? WHERE guild_id=?",
                  (log_channel.id, interaction.guild.id))
    conn.commit()
    conn.close()
    embed = make_embed(
        f"{STAR} AMG | Adopt Me Giveaways — Support",
        f"{BULLET} Need help? Click the button below to open a private support ticket.\n"
        f"{BULLET} A staff member will assist you as soon as possible.\n\n"
        f"{ARROW} **How it works:**\n"
        f"{BULLET} Click **Open Ticket**\n"
        f"{BULLET} Describe your issue in the private channel\n"
        f"{BULLET} Wait for a staff member to respond"
    )
    await channel.send(embed=embed, view=TicketOpenView())
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Ticket Panel Created",
        f"{BULLET} Ticket panel posted in {channel.mention}"
    ))

@ticket_group.command(name="add", description="Add a member to the current ticket")
@app_commands.describe(member="Member to add to this ticket")
async def ticket_add(interaction: discord.Interaction, member: discord.Member):
    if not await has_perm(interaction, "manage_tickets"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to manage tickets."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM tickets WHERE guild_id=? AND channel_id=? AND status='open'",
              (interaction.guild.id, interaction.channel.id))
    row = c.fetchone()
    conn.close()
    if not row:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} This channel is not an open ticket."), ephemeral=True)
        return
    try:
        await interaction.channel.set_permissions(member,
            read_messages=True, send_messages=True)
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Member Added",
            f"{BULLET} {member.mention} has been added to this ticket."
        ))
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to edit channel permissions."),
            ephemeral=True)

@ticket_group.command(name="remove", description="Remove a member from the current ticket")
@app_commands.describe(member="Member to remove from this ticket")
async def ticket_remove(interaction: discord.Interaction, member: discord.Member):
    if not await has_perm(interaction, "manage_tickets"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to manage tickets."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM tickets WHERE guild_id=? AND channel_id=? AND status='open'",
              (interaction.guild.id, interaction.channel.id))
    row = c.fetchone()
    conn.close()
    if not row:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} This channel is not an open ticket."), ephemeral=True)
        return
    if row[0] == member.id:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} You cannot remove the ticket owner."), ephemeral=True)
        return
    try:
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Member Removed",
            f"{BULLET} {member.mention} has been removed from this ticket."
        ))
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to edit channel permissions."),
            ephemeral=True)

@ticket_group.command(name="close", description="Close the current ticket")
@app_commands.describe(reason="Reason for closing the ticket")
async def ticket_close(interaction: discord.Interaction, reason: str = "No reason provided"):
    if not await has_perm(interaction, "manage_tickets"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to close tickets."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, ticket_type FROM tickets WHERE guild_id=? AND channel_id=? AND status='open'",
              (interaction.guild.id, interaction.channel.id))
    row = c.fetchone()
    if not row:
        conn.close()
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} This is not an open ticket."), ephemeral=True)
        return
    user_id, ticket_type = row
    c.execute("UPDATE tickets SET status='closed' WHERE guild_id=? AND channel_id=?",
              (interaction.guild.id, interaction.channel.id))
    c.execute("SELECT ticket_log_channel FROM guild_settings WHERE guild_id=?", (interaction.guild.id,))
    log_row = c.fetchone()
    conn.commit()
    conn.close()
    user = interaction.guild.get_member(user_id)
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Ticket Closed",
        f"{BULLET} **Closed by:** {interaction.user.mention}\n"
        f"{BULLET} **Type:** {ticket_type.title()}\n"
        f"{ARROW} **Reason:** {reason}"
    ))
    if log_row and log_row[0]:
        log_ch = interaction.guild.get_channel(log_row[0])
        if log_ch:
            try:
                await log_ch.send(embed=make_embed(
                    f"{STAR} Ticket Closed — {ticket_type.title()}",
                    f"{BULLET} **Channel:** #{interaction.channel.name}\n"
                    f"{BULLET} **User:** {user.mention if user else user_id}\n"
                    f"{BULLET} **Closed by:** {interaction.user.mention}\n"
                    f"{ARROW} **Reason:** {reason}"
                ))
            except Exception:
                pass
    await asyncio.sleep(5)
    try:
        await interaction.channel.delete()
    except Exception:
        pass

@ticket_group.command(name="closerequest", description="Request that a ticket be closed (DMs the ticket owner)")
@app_commands.describe(reason="Reason you are requesting the ticket be closed")
async def ticket_close_request(interaction: discord.Interaction, reason: str = "Issue appears to be resolved"):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, ticket_type FROM tickets WHERE guild_id=? AND channel_id=? AND status='open'",
              (interaction.guild.id, interaction.channel.id))
    row = c.fetchone()
    conn.close()
    if not row:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} This is not an open ticket."), ephemeral=True)
        return
    user_id, ticket_type = row
    user = interaction.guild.get_member(user_id)
    await interaction.response.send_message(embed=make_embed(
        f"🔔 Close Request Sent",
        f"{BULLET} **Requested by:** {interaction.user.mention}\n"
        f"{ARROW} **Reason:** {reason}\n\n"
        f"{BULLET} The ticket owner has been notified."
    ))
    if user:
        try:
            await user.send(embed=make_embed(
                f"🔔 Close Request — {interaction.guild.name}",
                f"{BULLET} **Staff Member:** {interaction.user.mention} has requested to close your ticket.\n"
                f"{ARROW} **Reason:** {reason}\n\n"
                f"{BULLET} If your issue is resolved, please close the ticket in {interaction.channel.mention}.\n"
                f"{BULLET} If you still need help, please let staff know."
            ))
        except Exception:
            pass

tree.add_command(ticket_group)


# ===== APPLICATION COMMANDS =====
app_group = app_commands.Group(name="application", description="Application system management")

@app_group.command(name="setup", description="Post an application panel in a channel")
@app_commands.describe(channel="Channel to post the application panel",
                       position="Position being applied for",
                       log_channel="Channel to log received applications")
async def app_setup(interaction: discord.Interaction, channel: discord.TextChannel,
                    position: str, log_channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_applications"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to set up applications."),
            ephemeral=True)
        return
    if log_channel:
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO guild_settings (guild_id, app_log_channel) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET app_log_channel=?",
                  (interaction.guild.id, log_channel.id, log_channel.id))
        conn.commit()
        conn.close()
    questions = [
        "What is your Roblox username?",
        "How old are you?",
        "How long have you been playing Adopt Me?",
        "Why do you want to join the Adopt Me Giveaways team?",
        "What makes you stand out from other applicants?",
        "Do you have any previous experience relevant to this position?",
        "How many hours per week can you dedicate to the server?"
    ]
    embed = make_embed(
        f"{STAR} Adopt Me Giveaways Staff Application — {position}",
        f"{BULLET} We are recruiting dedicated members for **{position}**!\n\n"
        f"{ARROW} **Requirements:**\n"
        f"{BULLET} Must be 13 or older\n"
        f"{BULLET} Active in the Adopt Me Giveaways community\n"
        f"{BULLET} Good communication and maturity\n\n"
        f"{ARROW} Click **Apply Now** to start your application via DMs."
    )
    await channel.send(embed=embed, view=ApplicationOpenView(position, questions))
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Application Panel Created",
        f"{BULLET} Application panel for **{position}** posted in {channel.mention}"
    ))

tree.add_command(app_group)


# ===== MIDDLEMAN COMMANDS =====
mm_group = app_commands.Group(name="middleman", description="Middleman system management")

@mm_group.command(name="setup", description="Post a middleman request panel in a channel")
@app_commands.describe(channel="Channel to post the panel",
                       category="Category for new middleman channels",
                       log_channel="Channel to log middleman requests")
async def middleman_setup(interaction: discord.Interaction, channel: discord.TextChannel,
                          category: discord.CategoryChannel = None,
                          log_channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_tickets"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to set up middleman."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (interaction.guild.id,))
    if category:
        c.execute("UPDATE guild_settings SET ticket_category=? WHERE guild_id=?",
                  (category.id, interaction.guild.id))
    if log_channel:
        c.execute("UPDATE guild_settings SET middleman_log_channel=? WHERE guild_id=?",
                  (log_channel.id, interaction.guild.id))
    conn.commit()
    conn.close()
    embed = make_embed(
        f"{STAR} Adopt Me Giveaways — Middleman",
        f"{BULLET} Need a trusted middleman for your trade? Click the button below!\n"
        f"{BULLET} A staff member will oversee your trade to keep both sides safe.\n\n"
        f"{ARROW} **How it works:**\n"
        f"{BULLET} Click **Request Middleman**\n"
        f"{BULLET} Fill in the trader's username and trade details\n"
        f"{BULLET} Wait in your private channel for a staff middleman\n"
        f"{BULLET} **Do NOT trade** until a middleman is present"
    )
    await channel.send(embed=embed, view=MiddlemanOpenView())
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Middleman Panel Created",
        f"{BULLET} Middleman panel posted in {channel.mention}"
    ), ephemeral=True)

tree.add_command(mm_group)


# ===== REACTION ROLES =====
rr_group = app_commands.Group(name="reactionrole", description="Reaction role management")

@rr_group.command(name="add", description="Add a reaction role to a message in this channel")
@app_commands.describe(message_id="ID of the target message", emoji="Emoji to react with",
                       role="Role to assign on reaction")
async def rr_add(interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
    if not await has_perm(interaction, "manage_reaction_roles"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage reaction roles."),
            ephemeral=True)
        return
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
    except Exception:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Message not found in this channel."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?,?,?,?)",
              (interaction.guild.id, msg.id, emoji, role.id))
    conn.commit()
    conn.close()
    try:
        await msg.add_reaction(emoji)
    except Exception:
        pass
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Reaction Role Added",
        f"{BULLET} **Message:** {msg.jump_url}\n"
        f"{BULLET} **Emoji:** {emoji}\n"
        f"{ARROW} **Role:** {role.mention}"
    ))

@rr_group.command(name="remove", description="Remove a reaction role from a message")
@app_commands.describe(message_id="ID of the target message", emoji="Emoji used", role="Role to remove")
async def rr_remove(interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
    if not await has_perm(interaction, "manage_reaction_roles"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage reaction roles."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=? AND role_id=?",
              (interaction.guild.id, int(message_id), emoji, role.id))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Reaction Role Removed",
        f"{BULLET} {emoji} {ARROW} {role.mention} has been removed."
    ))

@rr_group.command(name="list", description="List all reaction roles configured in this server")
async def rr_list(interaction: discord.Interaction):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id=?",
              (interaction.guild.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Reaction Roles", f"{BULLET} No reaction roles configured yet."))
        return
    lines = [f"{BULLET} `{mid}` {em} {ARROW} <@&{rid}>" for mid, em, rid in rows]
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Reaction Roles ({len(rows)})", "\n".join(lines)))

tree.add_command(rr_group)


# ===== GIVEAWAY COMMANDS =====
gw_group = app_commands.Group(name="giveaway", description="Giveaway management commands")

@gw_group.command(name="start", description="Start a giveaway")
@app_commands.describe(channel="Channel for the giveaway", duration="Duration e.g. 1h 30m 1d",
                       prize="Prize being given away", winners="Number of winners")
async def gw_start(interaction: discord.Interaction, channel: discord.TextChannel,
                   duration: str, prize: str, winners: int = 1):
    if not await has_perm(interaction, "manage_giveaways"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage giveaways."),
            ephemeral=True)
        return
    secs = parse_duration(duration)
    if secs <= 0:
        await interaction.response.send_message(
            embed=make_embed("❌ Invalid Duration",
                             f"{BULLET} Use formats like `1h`, `30m`, `2d`, `1h30m`."), ephemeral=True)
        return
    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=secs)
    embed = make_embed(
        f"{GIFT} GIVEAWAY",
        f"{STAR} **Prize:** {prize}\n"
        f"{BULLET} **Winners:** {winners}\n"
        f"{BULLET} **Hosted by:** {interaction.user.mention}\n"
        f"{BULLET} **Ends:** <t:{int(end_time.timestamp())}:R> (<t:{int(end_time.timestamp())}:f>)\n\n"
        f"{ARROW} React with {GIFT} to enter!"
    )
    msg = await channel.send(embed=embed)
    try:
        await msg.add_reaction(GIFT)
    except Exception:
        pass
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, host_id, end_time) VALUES (?,?,?,?,?,?,?)",
              (interaction.guild.id, channel.id, msg.id, prize, winners,
               interaction.user.id, end_time.isoformat()))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{GIFT} Giveaway Started",
        f"{BULLET} **Prize:** {prize}\n"
        f"{BULLET} **Channel:** {channel.mention}\n"
        f"{BULLET} **Ends:** <t:{int(end_time.timestamp())}:R>"
    ))

@gw_group.command(name="end", description="End a giveaway immediately")
@app_commands.describe(message_id="The giveaway message ID")
async def gw_end(interaction: discord.Interaction, message_id: str):
    if not await has_perm(interaction, "manage_giveaways"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage giveaways."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, guild_id, channel_id, message_id, prize, winners, host_id FROM giveaways WHERE guild_id=? AND message_id=? AND ended=0",
              (interaction.guild.id, int(message_id)))
    row = c.fetchone()
    conn.close()
    if not row:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} No active giveaway found with that message ID."),
            ephemeral=True)
        return
    await end_giveaway(*row)
    await interaction.response.send_message(embed=make_embed(
        f"{GIFT} Giveaway Ended", f"{BULLET} The giveaway has been ended and winners selected."))

@gw_group.command(name="reroll", description="Reroll winners for an ended giveaway")
@app_commands.describe(message_id="The giveaway message ID")
async def gw_reroll(interaction: discord.Interaction, message_id: str):
    if not await has_perm(interaction, "manage_giveaways"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage giveaways."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT channel_id, prize, winners, host_id FROM giveaways WHERE guild_id=? AND message_id=? AND ended=1",
              (interaction.guild.id, int(message_id)))
    row = c.fetchone()
    conn.close()
    if not row:
        await interaction.response.send_message(
            embed=make_embed("❌ Error",
                             f"{BULLET} No ended giveaway found with that message ID."), ephemeral=True)
        return
    channel_id, prize, winners_count, host_id = row
    ch = interaction.guild.get_channel(channel_id)
    if not ch:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Giveaway channel not found."), ephemeral=True)
        return
    try:
        msg = await ch.fetch_message(int(message_id))
    except Exception:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Could not fetch the giveaway message."),
            ephemeral=True)
        return
    entrants = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == str(GIFT):
            async for user in reaction.users():
                if not user.bot:
                    entrants.append(user)
    if not entrants:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} No valid entrants to reroll."), ephemeral=True)
        return
    actual = min(winners_count, len(entrants))
    winners = random.sample(entrants, actual)
    w_mentions = ", ".join(w.mention for w in winners)
    await ch.send(embed=make_embed(
        f"{GIFT} Giveaway Rerolled!",
        f"{STAR} **New Winner(s):** {w_mentions}\n"
        f"{BULLET} **Prize:** {prize}\n"
        f"{ARROW} Congratulations!"
    ))
    await interaction.response.send_message(embed=make_embed(
        f"{GIFT} Rerolled", f"{BULLET} New winner(s): {w_mentions}"))

tree.add_command(gw_group)


# ===== ECONOMY COMMANDS =====
@tree.command(name="balance", description="Check a member's AMG Stars balance")
@app_commands.describe(member="Member to check (leave empty for yourself)")
async def balance_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT balance FROM economy WHERE guild_id=? AND user_id=?",
              (interaction.guild.id, target.id))
    row = c.fetchone()
    conn.close()
    balance = row[0] if row else 0
    embed = make_embed(
        f"{STAR} Balance — {target.display_name}",
        f"{BULLET} **{CURRENCY}:** `{balance:,}` {STAR}"
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)


bal_admin = app_commands.Group(name="balanceadmin", description="Admin balance management")

@bal_admin.command(name="add", description="Add AMG Stars to a member's balance")
@app_commands.describe(member="Member to add stars to", amount="Amount to add")
async def bal_add(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not await has_perm(interaction, "manage_economy"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage the economy."),
            ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Amount must be a positive number."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO economy (guild_id, user_id, balance) VALUES (?,?,?)
                 ON CONFLICT(guild_id, user_id) DO UPDATE SET balance=balance+?""",
              (interaction.guild.id, member.id, amount, amount))
    c.execute("SELECT balance FROM economy WHERE guild_id=? AND user_id=?",
              (interaction.guild.id, member.id))
    new_bal = c.fetchone()[0]
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} {CURRENCY} Added",
        f"{BULLET} **Member:** {member.mention}\n"
        f"{BULLET} **Added:** `+{amount:,}` {STAR}\n"
        f"{ARROW} **New Balance:** `{new_bal:,}` {STAR}"
    ))
    await log_action(interaction.guild, f"{STAR} Economy Admin — Stars Added",
                     f"{BULLET} **Member:** {member.mention}\n"
                     f"{BULLET} **Added:** `+{amount:,}` {CURRENCY}\n"
                     f"{ARROW} **New Balance:** `{new_bal:,}`\n"
                     f"{BULLET} **By:** {interaction.user.mention}")

@bal_admin.command(name="remove", description="Remove AMG Stars from a member's balance")
@app_commands.describe(member="Member to remove stars from", amount="Amount to remove")
async def bal_remove(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not await has_perm(interaction, "manage_economy"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage the economy."),
            ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Amount must be a positive number."), ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT balance FROM economy WHERE guild_id=? AND user_id=?",
              (interaction.guild.id, member.id))
    row = c.fetchone()
    current = row[0] if row else 0
    new_bal = max(0, current - amount)
    c.execute("""INSERT INTO economy (guild_id, user_id, balance) VALUES (?,?,?)
                 ON CONFLICT(guild_id, user_id) DO UPDATE SET balance=?""",
              (interaction.guild.id, member.id, new_bal, new_bal))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} {CURRENCY} Removed",
        f"{BULLET} **Member:** {member.mention}\n"
        f"{BULLET} **Removed:** `-{amount:,}` {STAR}\n"
        f"{ARROW} **New Balance:** `{new_bal:,}` {STAR}"
    ))
    await log_action(interaction.guild, f"{STAR} Economy Admin — Stars Removed",
                     f"{BULLET} **Member:** {member.mention}\n"
                     f"{BULLET} **Removed:** `-{amount:,}` {CURRENCY}\n"
                     f"{ARROW} **New Balance:** `{new_bal:,}`\n"
                     f"{BULLET} **By:** {interaction.user.mention}")

tree.add_command(bal_admin)


# ===== STORE COMMANDS =====
store_group = app_commands.Group(name="store", description="Server store commands")

@store_group.command(name="view", description="Browse the server store")
async def store_view(interaction: discord.Interaction):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, price, item_type, role_id, description FROM store WHERE guild_id=?",
              (interaction.guild.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Server Store",
            f"{BULLET} The store is currently empty!\n{ARROW} Check back later for items."
        ))
        return
    lines = []
    for sid, name, price, itype, role_id, desc in rows:
        role_str = f" {ARROW} <@&{role_id}>" if itype == "role" and role_id else ""
        desc_str = f"\n{ARROW} _{desc}_" if desc else ""
        lines.append(f"{BULLET} **[#{sid}] {name}** — `{price:,}` {STAR} {CURRENCY}{role_str}{desc_str}")
    lines.append(f"\n{ARROW} Use `/buy <item_id>` to purchase.")
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Server Store ({len(rows)} items)", "\n".join(lines)))

@store_group.command(name="add", description="Add an item to the store")
@app_commands.describe(name="Item name", price="Price in AMG Stars", item_type="Type of item",
                       role="Role to grant (for role items)", description="Item description")
@app_commands.choices(item_type=[
    app_commands.Choice(name="role", value="role"),
    app_commands.Choice(name="item", value="item")
])
async def store_add(interaction: discord.Interaction, name: str, price: int, item_type: str,
                    role: discord.Role = None, description: str = ""):
    if not await has_perm(interaction, "manage_store"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage the store."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO store (guild_id, name, price, item_type, role_id, description) VALUES (?,?,?,?,?,?)",
              (interaction.guild.id, name, price, item_type, role.id if role else None, description))
    item_id = c.lastrowid
    conn.commit()
    conn.close()
    role_str = f"\n{BULLET} **Role:** {role.mention}" if role else ""
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Store Item Added",
        f"{BULLET} **ID:** `#{item_id}`\n"
        f"{BULLET} **Name:** {name}\n"
        f"{BULLET} **Price:** `{price:,}` {CURRENCY}{role_str}"
    ))

@store_group.command(name="remove", description="Remove an item from the store")
@app_commands.describe(item_id="The store item ID to remove")
async def store_remove(interaction: discord.Interaction, item_id: int):
    if not await has_perm(interaction, "manage_store"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission",
                             f"{BULLET} You don't have permission to manage the store."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name FROM store WHERE id=? AND guild_id=?", (item_id, interaction.guild.id))
    row = c.fetchone()
    if not row:
        conn.close()
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Item `#{item_id}` not found in the store."),
            ephemeral=True)
        return
    c.execute("DELETE FROM store WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Store Item Removed",
        f"{BULLET} **{row[0]}** (`#{item_id}`) has been removed from the store."
    ))

tree.add_command(store_group)


@tree.command(name="buy", description="Purchase an item from the server store")
@app_commands.describe(item_id="The ID of the item you want to buy")
async def buy_cmd(interaction: discord.Interaction, item_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name, price, item_type, role_id, description FROM store WHERE id=? AND guild_id=?",
              (item_id, interaction.guild.id))
    item = c.fetchone()
    if not item:
        conn.close()
        await interaction.response.send_message(
            embed=make_embed("❌ Error",
                             f"{BULLET} Item `#{item_id}` not found. Use `/store view` to browse."),
            ephemeral=True)
        return
    name, price, item_type, role_id, desc = item
    c.execute("SELECT balance FROM economy WHERE guild_id=? AND user_id=?",
              (interaction.guild.id, interaction.user.id))
    bal_row = c.fetchone()
    balance = bal_row[0] if bal_row else 0
    if balance < price:
        conn.close()
        await interaction.response.send_message(embed=make_embed(
            f"❌ Insufficient {CURRENCY}",
            f"{BULLET} **Required:** `{price:,}` {STAR}\n"
            f"{BULLET} **Your Balance:** `{balance:,}` {STAR}\n"
            f"{ARROW} You need `{price - balance:,}` more {CURRENCY}."
        ), ephemeral=True)
        return
    new_bal = balance - price
    c.execute("UPDATE economy SET balance=? WHERE guild_id=? AND user_id=?",
              (new_bal, interaction.guild.id, interaction.user.id))
    conn.commit()
    conn.close()
    if item_type == "role" and role_id:
        role = interaction.guild.get_role(role_id)
        if role:
            try:
                await interaction.user.add_roles(role, reason="Store purchase")
            except Exception:
                pass
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Purchase Successful!",
        f"{BULLET} **Item:** {name}\n"
        f"{BULLET} **Cost:** `{price:,}` {STAR}\n"
        f"{ARROW} **Remaining Balance:** `{new_bal:,}` {STAR}"
    ))


@tree.command(name="leaderboard", description="View the server's top AMG Stars holders")
async def leaderboard_cmd(interaction: discord.Interaction):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, balance FROM economy WHERE guild_id=? ORDER BY balance DESC LIMIT 10",
              (interaction.guild.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message(embed=make_embed(
            f"{STAR} Economy Leaderboard",
            f"{BULLET} No economy data yet. Start chatting to earn {CURRENCY}!"
        ))
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, bal) in enumerate(rows):
        member = interaction.guild.get_member(uid)
        name = member.display_name if member else f"User {uid}"
        prefix = medals[i] if i < 3 else f"`#{i+1}`"
        lines.append(f"{prefix} **{name}** — `{bal:,}` {STAR}")
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} {CURRENCY} Leaderboard — {interaction.guild.name}",
        "\n".join(lines)
    ))


@tree.command(name="invites", description="Check how many invites a member has")
@app_commands.describe(member="Member to check (leave empty for yourself)")
async def invites_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM invites WHERE guild_id=? AND inviter_id=?",
              (interaction.guild.id, target.id))
    count = c.fetchone()[0]
    conn.close()
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Invites — {target.display_name}",
        f"{BULLET} **Total Members Invited:** `{count}`"
    ))


@tree.command(name="say", description="Send a plain or embed message to a channel")
@app_commands.describe(
    channel="Channel to send the message to",
    message="Plain text content (used alone for plain messages, or as extra text above an embed)",
    title="Embed title — providing this switches to embed mode",
    description="Embed body text",
    color="Embed color as a hex code e.g. 5DADE2 (leave blank for default blue)"
)
async def say_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str = None,
    title: str = None,
    description: str = None,
    color: str = None
):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to use /say."),
            ephemeral=True)
        return
    if not message and not title and not description:
        await interaction.response.send_message(
            embed=make_embed("❌ Nothing to send",
                             f"{BULLET} Provide at least a **message** (plain text) or a **title**/**description** (embed)."),
            ephemeral=True)
        return
    embed_mode = title or description
    embed = None
    if embed_mode:
        resolved_color = EMBED_COLOR
        if color:
            try:
                resolved_color = int(color.lstrip("#"), 16)
            except ValueError:
                await interaction.response.send_message(
                    embed=make_embed("❌ Invalid Color",
                                     f"{BULLET} Color must be a valid hex code e.g. `FF5733` or `#FF5733`."),
                    ephemeral=True)
                return
        embed = discord.Embed(
            title=title or discord.utils.MISSING,
            description=description or discord.utils.MISSING,
            color=resolved_color
        )
        if BANNER_URL:
            embed.set_image(url=BANNER_URL)
        embed.set_footer(text="AMG | Adopt Me Giveaways")
        embed.timestamp = datetime.datetime.utcnow()
    try:
        await channel.send(content=message or None, embed=embed)
        await interaction.response.send_message(
            embed=make_embed(f"{STAR} Message Sent",
                             f"{BULLET} Your message was sent to {channel.mention}."),
            ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to send messages in {channel.mention}."),
            ephemeral=True)


@tree.command(name="botinfo", description="View information about the Adopt Me Giveaways bot")
async def botinfo_cmd(interaction: discord.Interaction):
    embed = make_embed(
        f"{STAR} Adopt Me Giveaways Bot",
        f"{BULLET} **Name:** {bot.user.mention}\n"
        f"{BULLET} **Servers:** `{len(bot.guilds)}`\n\n"
        f"{ARROW} **Features:**\n"
        f"{BULLET} Moderation — kick, ban, warn, mute, purge, add/remove role\n"
        f"{BULLET} AutoMod — spam, bulk pings, invite/NSFW links\n"
        f"{BULLET} Permissions system\n"
        f"{BULLET} Invite tracker & welcome messages\n"
        f"{BULLET} Support ticket system\n"
        f"{BULLET} Staff application system\n"
        f"{BULLET} Middleman trade tickets\n"
        f"{BULLET} Reaction roles\n"
        f"{BULLET} Giveaways with auto-end\n"
        f"{BULLET} {CURRENCY} economy & configurable store\n"
        f"{BULLET} Polls, QOTD & Would You Rather"
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# ===== STAFF ANNOUNCEMENT COMMANDS =====
async def get_staff_channel(guild: discord.Guild):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT staff_channel FROM guild_settings WHERE guild_id=?", (guild.id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return guild.get_channel(row[0])
    return None


@tree.command(name="promote", description="Post a promotion announcement to the staff channel")
@app_commands.describe(
    member="The member being promoted",
    new_role="The role they are being promoted to",
    supervisor="Their direct supervisor",
    other_supervisors="Other supervisors (mention them, e.g. @User1 @User2)",
    permissions="Permissions granted with this promotion"
)
async def promote_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    new_role: discord.Role,
    supervisor: discord.Member,
    other_supervisors: str = "None",
    permissions: str = "Standard staff permissions"
):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to post promotions."),
            ephemeral=True)
        return
    staff_ch = await get_staff_channel(interaction.guild)
    if not staff_ch:
        await interaction.response.send_message(
            embed=make_embed("❌ Not Configured",
                             f"{BULLET} No staff channel set. Use `/setup staffchannel` first."),
            ephemeral=True)
        return
    embed = make_embed(
        f"{STAR} Staff Promotion",
        f"{BULLET} **Member:** {member.mention}\n"
        f"{BULLET} **New Role:** {new_role.mention}\n"
        f"{BULLET} **Promoted by:** {interaction.user.mention}\n"
        f"{BULLET} **Supervisor:** {supervisor.mention}\n"
        f"{BULLET} **Other Supervisors:** {other_supervisors}\n"
        f"{ARROW} **Permissions:** {permissions}\n\n"
        f"{STAR} Congratulations on your promotion, {member.mention}!"
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await staff_ch.send(content=member.mention, embed=embed)
    await interaction.response.send_message(
        embed=make_embed(f"{STAR} Promotion Posted",
                         f"{BULLET} Promotion for {member.mention} has been posted in {staff_ch.mention}"))
    await log_action(interaction.guild, f"{STAR} Staff Promotion",
                     f"{BULLET} **Member:** {member}\n"
                     f"{BULLET} **New Role:** {new_role.name}\n"
                     f"{BULLET} **By:** {interaction.user}")


@tree.command(name="demote", description="Post a demotion announcement to the staff channel")
@app_commands.describe(
    member="The member being demoted",
    new_role="The role they are being demoted to",
    new_supervisor="Their new supervisor",
    other_supervisors="Other supervisors (mention them, e.g. @User1 @User2)",
    new_permissions="Permissions they now hold after demotion"
)
async def demote_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    new_role: discord.Role,
    new_supervisor: discord.Member,
    other_supervisors: str = "None",
    new_permissions: str = "Standard staff permissions"
):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to post demotions."),
            ephemeral=True)
        return
    staff_ch = await get_staff_channel(interaction.guild)
    if not staff_ch:
        await interaction.response.send_message(
            embed=make_embed("❌ Not Configured",
                             f"{BULLET} No staff channel set. Use `/setup staffchannel` first."),
            ephemeral=True)
        return
    embed = make_embed(
        f"{STAR} Staff Demotion",
        f"{BULLET} **Member:** {member.mention}\n"
        f"{BULLET} **New Role:** {new_role.mention}\n"
        f"{BULLET} **Demoted by:** {interaction.user.mention}\n"
        f"{BULLET} **New Supervisor:** {new_supervisor.mention}\n"
        f"{BULLET} **Other Supervisors:** {other_supervisors}\n"
        f"{ARROW} **New Permissions:** {new_permissions}"
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await staff_ch.send(content=member.mention, embed=embed)
    await interaction.response.send_message(
        embed=make_embed(f"{STAR} Demotion Posted",
                         f"{BULLET} Demotion for {member.mention} has been posted in {staff_ch.mention}"))
    await log_action(interaction.guild, f"{STAR} Staff Demotion",
                     f"{BULLET} **Member:** {member}\n"
                     f"{BULLET} **New Role:** {new_role.name}\n"
                     f"{BULLET} **By:** {interaction.user}")


@tree.command(name="removestaff", description="Post a staff removal announcement to the staff channel")
@app_commands.describe(
    member="The staff member being removed",
    reason="Reason for the removal"
)
async def removestaff_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to post staff removals."),
            ephemeral=True)
        return
    staff_ch = await get_staff_channel(interaction.guild)
    if not staff_ch:
        await interaction.response.send_message(
            embed=make_embed("❌ Not Configured",
                             f"{BULLET} No staff channel set. Use `/setup staffchannel` first."),
            ephemeral=True)
        return
    embed = make_embed(
        f"{STAR} Staff Removal",
        f"{BULLET} **Member:** {member.mention}\n"
        f"{BULLET} **Removed by:** {interaction.user.mention}\n"
        f"{ARROW} **Reason:** {reason}"
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await staff_ch.send(embed=embed)
    await interaction.response.send_message(
        embed=make_embed(f"{STAR} Removal Posted",
                         f"{BULLET} Staff removal for {member.mention} has been posted in {staff_ch.mention}"))
    await log_action(interaction.guild, f"{STAR} Staff Removed",
                     f"{BULLET} **Member:** {member}\n"
                     f"{BULLET} **By:** {interaction.user}\n"
                     f"{ARROW} **Reason:** {reason}")


# ===== QOTD COMMAND =====
@tree.command(name="qotd", description="Post a Question of the Day to the configured QOTD channel")
@app_commands.describe(question="The question to post as today's QOTD")
async def qotd_cmd(interaction: discord.Interaction, question: str):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to post QOTD."),
            ephemeral=True)
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT qotd_channel, qotd_ping_role FROM guild_settings WHERE guild_id=?",
              (interaction.guild.id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        await interaction.response.send_message(
            embed=make_embed("❌ Not Configured",
                             f"{BULLET} No QOTD channel set. Use `/setup qotdchannel` first."),
            ephemeral=True)
        return
    qotd_ch_id, ping_role_id = row
    qotd_ch = interaction.guild.get_channel(qotd_ch_id)
    if not qotd_ch:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} QOTD channel not found. Please reconfigure."),
            ephemeral=True)
        return

    ping_role = interaction.guild.get_role(ping_role_id) if ping_role_id else None
    ping_content = ping_role.mention if ping_role else ""

    # Find the best answer channel (channel named "qotd" or "general" or first text channel)
    answer_ch = None
    for ch in interaction.guild.text_channels:
        if "qotd" in ch.name.lower() or "answer" in ch.name.lower():
            answer_ch = ch
            break
    if not answer_ch:
        for ch in interaction.guild.text_channels:
            if "general" in ch.name.lower():
                answer_ch = ch
                break
    if not answer_ch and interaction.guild.text_channels:
        answer_ch = interaction.guild.text_channels[0]

    answer_str = f"\n{ARROW} Answer in {answer_ch.mention}!" if answer_ch else ""

    embed = make_embed(
        f"❓ Question of the Day",
        f"{STAR} **{question}**\n\n"
        f"{BULLET} **Posted by:** {interaction.user.mention}{answer_str}"
    )
    await qotd_ch.send(content=ping_content if ping_content else None, embed=embed)
    await interaction.response.send_message(
        embed=make_embed(f"{STAR} QOTD Posted",
                         f"{BULLET} Your question has been posted in {qotd_ch.mention}!"),
        ephemeral=True)


# ===== WOULD YOU RATHER COMMAND =====
@tree.command(name="wyr", description="Post a Would You Rather question with two options")
@app_commands.describe(
    question="The Would You Rather question",
    answer1="First option (reaction 1)",
    answer2="Second option (reaction 2)",
    channel="Channel to post in (defaults to current channel)"
)
async def wyr_cmd(interaction: discord.Interaction, question: str,
                  answer1: str, answer2: str,
                  channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to post WYR."),
            ephemeral=True)
        return
    target_ch = channel or interaction.channel
    embed = make_embed(
        f"🤔 Would You Rather?",
        f"{STAR} **{question}**\n\n"
        f"{NUM_EMOJIS[0]} **Option 1:** {answer1}\n\n"
        f"{NUM_EMOJIS[1]} **Option 2:** {answer2}\n\n"
        f"{BULLET} React with your choice!"
    )
    msg = await target_ch.send(embed=embed)
    try:
        await msg.add_reaction(NUM_EMOJIS[0])
    except Exception:
        pass
    try:
        await msg.add_reaction(NUM_EMOJIS[1])
    except Exception:
        pass
    await interaction.response.send_message(
        embed=make_embed(f"{STAR} WYR Posted", f"{BULLET} Posted in {target_ch.mention}!"),
        ephemeral=True)


# ===== ADD EMOJIS COMMAND =====
@tree.command(name="addemojis", description="Upload multiple emojis to this server at once")
@app_commands.describe(
    name1="Name for emoji 1 (then send your images as attachments in the next message)",
    name2="Name for emoji 2",
    name3="Name for emoji 3",
    name4="Name for emoji 4",
    name5="Name for emoji 5"
)
async def addemojis_cmd(
    interaction: discord.Interaction,
    name1: str,
    name2: str = None,
    name3: str = None,
    name4: str = None,
    name5: str = None
):
    if not interaction.user.guild_permissions.manage_emojis:
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You need the Manage Emojis permission."),
            ephemeral=True)
        return
    await interaction.response.send_message(embed=make_embed(
        f"{STAR} Upload Emojis",
        f"{BULLET} Please send your emoji images as **file attachments** in your next message.\n"
        f"{ARROW} Send up to **5 images** now. They will be uploaded as:\n"
        f"{BULLET} Image 1 → `:{name1}:`\n"
        + (f"{BULLET} Image 2 → `:{name2}:`\n" if name2 else "")
        + (f"{BULLET} Image 3 → `:{name3}:`\n" if name3 else "")
        + (f"{BULLET} Image 4 → `:{name4}:`\n" if name4 else "")
        + (f"{BULLET} Image 5 → `:{name5}:`\n" if name5 else "")
        + f"\n{BULLET} You have **60 seconds** to send your attachments."
    ))
    names = [n for n in [name1, name2, name3, name4, name5] if n]
    try:
        msg = await bot.wait_for(
            "message",
            timeout=60,
            check=lambda m: (
                m.author.id == interaction.user.id and
                m.channel.id == interaction.channel.id and
                len(m.attachments) > 0
            )
        )
    except asyncio.TimeoutError:
        await interaction.channel.send(embed=make_embed("❌ Timed Out",
            f"{BULLET} No attachments received. Please try `/addemojis` again."))
        return
    added = []
    failed = []
    for i, attachment in enumerate(msg.attachments[:len(names)]):
        name = names[i]
        try:
            image_bytes = await attachment.read()
            emoji = await interaction.guild.create_custom_emoji(name=name, image=image_bytes)
            added.append(f"{str(emoji)} `:{name}:`")
        except discord.Forbidden:
            failed.append(f"`:{name}:` — No permission")
        except discord.HTTPException as e:
            failed.append(f"`:{name}:` — {e.text}")
        except Exception as e:
            failed.append(f"`:{name}:` — {str(e)}")
    result_lines = []
    if added:
        result_lines.append(f"{ARROW} **Added ({len(added)}):**\n" + "\n".join(f"{BULLET} {a}" for a in added))
    if failed:
        result_lines.append(f"\n{ARROW} **Failed ({len(failed)}):**\n" + "\n".join(f"{BULLET} {f}" for f in failed))
    await interaction.channel.send(embed=make_embed(
        f"{STAR} Emoji Upload Results",
        "\n".join(result_lines) if result_lines else f"{BULLET} No emojis processed."
    ))


# ===== POLL COMMAND =====
poll_group = app_commands.Group(name="poll", description="Poll commands")

@poll_group.command(name="create", description="Create a poll with up to 9 answer options")
@app_commands.describe(
    question="The poll question",
    answer1="Option 1 (required)",
    answer2="Option 2 (required)",
    answer3="Option 3",
    answer4="Option 4",
    answer5="Option 5",
    answer6="Option 6",
    answer7="Option 7",
    answer8="Option 8",
    answer9="Option 9",
    channel="Channel to post the poll (defaults to current channel)"
)
async def poll_create(
    interaction: discord.Interaction,
    question: str,
    answer1: str,
    answer2: str,
    answer3: str = None,
    answer4: str = None,
    answer5: str = None,
    answer6: str = None,
    answer7: str = None,
    answer8: str = None,
    answer9: str = None,
    channel: discord.TextChannel = None
):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to create polls."),
            ephemeral=True)
        return
    answers = [a for a in [answer1, answer2, answer3, answer4, answer5,
                             answer6, answer7, answer8, answer9] if a]
    target_ch = channel or interaction.channel
    options_text = "\n".join(
        f"{NUM_EMOJIS[i]} **{answers[i]}**"
        for i in range(len(answers))
    )
    embed = make_embed(
        f"📊 Poll",
        f"{STAR} **{question}**\n\n"
        f"{options_text}\n\n"
        f"{BULLET} React with your choice!\n"
        f"{BULLET} **Posted by:** {interaction.user.mention}"
    )
    msg = await target_ch.send(embed=embed)
    for i in range(len(answers)):
        try:
            await msg.add_reaction(NUM_EMOJIS[i])
        except Exception:
            pass
    await interaction.response.send_message(
        embed=make_embed(f"{STAR} Poll Created",
                         f"{BULLET} Poll posted in {target_ch.mention} with {len(answers)} options!"),
        ephemeral=True)

tree.add_command(poll_group)


# ===== SEND COMMANDS =====
send_group = app_commands.Group(name="send", description="Send pre-built server messages")

@send_group.command(name="rules", description="Send the AMG server rules to a channel")
@app_commands.describe(channel="Channel to send the rules to (defaults to current channel)")
async def send_rules(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to send rules."),
            ephemeral=True)
        return
    target_ch = channel or interaction.channel
    embed = discord.Embed(
        title="🎮 AMG | Adopt Me Giveaways — Server Rules",
        color=EMBED_COLOR,
        description=(
            f"{BULLET} **1. Respect All Members**\n"
            f"{ARROW} Treat all members with respect at all times. Harassment, bullying, "
            f"discrimination, or aggressive behaviour towards others is not allowed.\n\n"
            f"{BULLET} **2. No Scamming or Value Scamming**\n"
            f"{ARROW} Scamming or attempting to scam other members will result in severe punishment.\n\n"
            f"{BULLET} **3. Cross Trading Policy**\n"
            f"{ARROW} Cross trading is not allowed unless conducted through an approved staff middleman.\n\n"
            f"{BULLET} **4. No Advertising or Links**\n"
            f"{ARROW} Advertising other Discord servers, services, social media, or sending links is "
            f"strictly prohibited unless approved by staff.\n\n"
            f"{BULLET} **5. No Spam — unless server event**\n"
            f"{ARROW} Spamming messages, emojis, reactions, or mentions is not allowed.\n\n"
            f"{BULLET} **6. Use Channels Correctly**\n"
            f"{ARROW} Please keep conversations in the appropriate channels.\n\n"
            f"{BULLET} **7. Giveaway Integrity**\n"
            f"{ARROW} Exploiting giveaways, using alternate accounts, or manipulating giveaway "
            f"systems is not allowed.\n\n"
            f"{BULLET} **8. Respect Staff**\n"
            f"{ARROW} Disrespecting staff members or ignoring moderation instructions is not allowed.\n\n"
            f"{BULLET} **9. Follow Discord Terms of Service**\n"
            f"{ARROW} All members must follow Discord's Terms of Service.\n\n"
            f"{BULLET} **10. Staff Authority**\n"
            f"{ARROW} Staff decisions are final and must be respected."
        )
    )
    if BANNER_URL:
        embed.set_image(url=BANNER_URL)
    embed.set_footer(text="AMG | Adopt Me Giveaways")
    embed.timestamp = datetime.datetime.utcnow()
    try:
        await target_ch.send(embed=embed)
        await interaction.response.send_message(
            embed=make_embed(f"{STAR} Rules Sent", f"{BULLET} Rules posted in {target_ch.mention}"),
            ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} I don't have permission to send messages in {target_ch.mention}."),
            ephemeral=True)

@send_group.command(name="welcome", description="Send a test welcome message as if a member just joined")
@app_commands.describe(member="Member to use for the test welcome (defaults to you)")
async def send_welcome_test(interaction: discord.Interaction, member: discord.Member = None):
    if not await has_perm(interaction, "manage_bot"):
        await interaction.response.send_message(
            embed=make_embed("❌ No Permission", f"{BULLET} You don't have permission to do this."),
            ephemeral=True)
        return
    target = member or interaction.user
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT fancy_welcome_channel, welcome_ping_role,
                        welcome_rules_channel, welcome_general_channel, welcome_trading_channel,
                        welcome_qotd_channel, welcome_gws_channel, welcome_roles_channel
                 FROM guild_settings WHERE guild_id=?""", (interaction.guild.id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        await interaction.response.send_message(
            embed=make_embed("❌ Not Configured",
                             f"{BULLET} No fancy welcome channel set. Use `/setup welcomemessage` first."),
            ephemeral=True)
        return
    fw_ch = interaction.guild.get_channel(row[0])
    if not fw_ch:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Welcome channel not found."), ephemeral=True)
        return
    ping_role = interaction.guild.get_role(row[1]) if row[1] else None

    def ch_link(idx):
        cid = row[idx]
        return f"<#{cid}>" if cid else "—"

    embed = discord.Embed(
        description=(
            f"**{target.mention} welcome to the… best adopt me giveaway and event server ever!**\n\n"
            f"{BULLET} **Check these channels:**\n"
            f"{ARROW} {ch_link(2)} — rules\n"
            f"{ARROW} {ch_link(3)} — general\n"
            f"{ARROW} {ch_link(4)} — trading\n"
            f"{ARROW} {ch_link(5)} — qotd\n\n"
            f"{BULLET} **Check Our Current Giveaways:**\n"
            f"{ARROW} {ch_link(6)}\n\n"
            f"{BULLET} **MAKE SURE TO GET YOUR ROLES:**\n"
            f"{ARROW} {ch_link(7)}\n\n"
            f"*never put on tomorrow, what can be done today!*"
        ),
        color=EMBED_COLOR
    )
    embed.set_author(name=f"Welcome to {interaction.guild.name} 🎉",
                     icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.set_footer(text="AMG | Adopt Me Giveaways")
    embed.timestamp = datetime.datetime.utcnow()
    content = ping_role.mention if ping_role else target.mention
    try:
        await fw_ch.send(content=content, embed=embed)
        await interaction.response.send_message(
            embed=make_embed(f"{STAR} Test Welcome Sent", f"{BULLET} Preview posted in {fw_ch.mention}"),
            ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=make_embed("❌ Error", f"{BULLET} Cannot send to {fw_ch.mention}."), ephemeral=True)

tree.add_command(send_group)


# ===== RUN =====
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN is not set!")

bot.run(TOKEN)
