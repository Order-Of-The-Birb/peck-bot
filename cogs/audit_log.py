if __name__ == "__main__":
	raise Exception("Start the program from the main process")
import discord, logging
from asyncio import sleep as aSleep
from discord.ext import commands
from datetime import datetime, UTC
from calendar import monthrange
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
	from utils.bot import Bot
# ChannelIDs, RoleIDs, CategoryIDs
# owner_only, officer_only, members_only, debug_only
#from utils.bot import 
#import utils.generic as genericUtil
#import utils.time as timeUtil
#import utils.wt as wtUtil

# "utils.generic", "utils.time", "utils.wt"
__reload_deps__ = ()

class AuditColor(IntEnum):
	# Taken directly from Dyno's colors
	CREATE = 0x43B582
	DELETE = 0xFF470F
	MODIFY = 0x337FD5
class AuditLogDiffTypes(StrEnum):
	ACTIONS = "actions"
	AFK_CHANNEL = "afk_channel"
	AFK_TIMEOUT = "afk_timeout"
	ALLOW = "allow"
	APP_COMMAND_PERMISSIONS = "app_command_permissions"
	APPLIED_TAGS = "applied_tags"
	ARCHIVED = "archived"
	AUTO_ARCHIVE_DURATION = "auto_archive_duration"
	AVAILABLE = "available"
	AVAILABLE_TAGS = "available_tags"
	AVATAR = "avatar"
	BANNER = "banner"
	BITRATE = "bitrate"
	CHANNEL = "channel"
	CODE = "code"
	COLOR = "color"
	COLOUR = "colour"
	COVER_IMAGE = "cover_image"
	DEAF = "deaf"
	DEFAULT_AUTO_ARCHIVE_DURATION = "default_auto_archive_duration"
	DEFAULT_CHANNELS = "default_channels"
	DEFAULT_NOTIFICATIONS = "default_notifications"
	DEFAULT_REACTION_EMOJI = "default_reaction_emoji"
	DEFAULT_THREAD_SLOWMODE_DELAY = "default_thread_slowmode_delay"
	DENY = "deny"
	DESCRIPTION = "description"
	DISCOVERY_SPLASH = "discovery_splash"
	EMOJI = "emoji"
	ENABLE_EMOTICONS = "enable_emoticons"
	ENABLED = "enabled"
	ENTITY_TYPE = "entity_type"
	EVENT_TYPE = "event_type"
	EXEMPT_CHANNELS = "exempt_channels"
	EXEMPT_ROLES = "exempt_roles"
	EXPIRE_BEHAVIOR = "expire_behavior"
	EXPIRE_BEHAVIOUR = "expire_behaviour"
	EXPIRE_GRACE_PERIOD = "expire_grace_period"
	EXPLICIT_CONTENT_FILTER = "explicit_content_filter"
	FLAGS = "flags"
	FORMAT_TYPE = "format_type"
	GUILD = "guild"
	HOIST = "hoist"
	ICON = "icon"
	ID = "id"
	IN_ONBOARDING = "in_onboarding"
	INVITABLE = "invitable"
	INVITER = "inviter"
	LOCKED = "locked"
	MAX_AGE = "max_age"
	MAX_USES = "max_uses"
	MENTIONABLE = "mentionable"
	MFA_LEVEL = "mfa_level"
	MODE = "mode"
	MUTE = "mute"
	NAME = "name"
	NICK = "nick"
	NSFW = "nsfw"
	OPTIONS = "options"
	OVERWRITES = "overwrites"
	OWNER = "owner"
	PERMISSIONS = "permissions"
	POSITION = "position"
	PREFERRED_LOCALE = "preferred_locale"
	PREMIUM_PROGRESS_BAR_ENABLED = "premium_progress_bar_enabled"
	PRIVACY_LEVEL = "privacy_level"
	PROMPTS = "prompts"
	PRUNE_DELETE_DAYS = "prune_delete_days"
	PUBLIC_UPDATES_CHANNEL = "public_updates_channel"
	REQUIRED = "required"
	ROLES = "roles"
	RTC_REGION = "rtc_region"
	RULES_CHANNEL = "rules_channel"
	SECONDARY_COLOR = "secondary_color"
	SECONDARY_COLOUR = "secondary_colour"
	SINGLE_SELECT = "single_select"
	SLOWMODE_DELAY = "slowmode_delay"
	SPLASH = "splash"
	STATUS = "status"
	SYSTEM_CHANNEL = "system_channel"
	SYSTEM_CHANNEL_FLAGS = "system_channel_flags"
	TEMPORARY = "temporary"
	TERTIARY_COLOR = "tertiary_color"
	TERTIARY_COLOUR = "tertiary_colour"
	TIMED_OUT_UNTIL = "timed_out_until"
	TITLE = "title"
	TOPIC = "topic"
	TRIGGER = "trigger"
	TRIGGER_TYPE = "trigger_type"
	TYPE = "type"
	UNICODE_EMOJI = "unicode_emoji"
	USER = "user"
	USER_LIMIT = "user_limit"
	USES = "uses"
	VANITY_URL_CODE = "vanity_url_code"
	VERIFICATION_LEVEL = "verification_level"
	VIDEO_QUALITY_MODE = "video_quality_mode"
	VOLUME = "volume"
	WIDGET_CHANNEL = "widget_channel"
	WIDGET_ENABLED = "widget_enabled"
class auditLogCog(commands.Cog):
	def __init__(self, bot:'Bot'):
		self.bot = bot
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(bot.logLevel)
		self.logger.debug(f"{self.__class__.__name__} initialized")
	# region Helpers
	@staticmethod
	def _format_account_age(created_at: datetime, now: datetime | None = None) -> str:
		"""Return a calendar-accurate age string in years, months, days."""
		current = (now or datetime.now(UTC)).astimezone(UTC).date()
		created = created_at.astimezone(UTC).date()

		if current < created:
			return "0 years, 0 months, 0 days"

		years = current.year - created.year
		months = current.month - created.month
		days = current.day - created.day

		if days < 0:
			months -= 1
			prev_month = 12 if current.month == 1 else current.month - 1
			prev_month_year = current.year - 1 if current.month == 1 else current.year
			days += monthrange(prev_month_year, prev_month)[1]

		if months < 0:
			years -= 1
			months += 12

		return f"{f"{years} year{"s" if years > 1 else ""}, " if years > 0 else ""}{f"{months} month{"s" if months > 1 else ""}, " if months > 0 else ""}{days} days"
	@staticmethod
	async def getAuditLogEntry(
		action: discord.AuditLogAction,
		/,
		*,
		guild: discord.Guild,
		target: discord.abc.Snowflake | None = None,
		targeting: discord.Role|discord.Member|discord.User|None = None,
		key: AuditLogDiffTypes | None = None,
		lookupAfter: bool = True,
		limit: int = 10
	) -> Optional[discord.AuditLogEntry]:
		await aSleep(0.2) # to let audit log populate
		_missing = object()
		async for entry in guild.audit_logs(limit=limit, action=action):
			if target is not None and (entry.target is None or entry.target.id != target.id):
				continue
			if targeting is not None and not (entry.extra and entry.extra.id == targeting.id):
				continue
			if key is None:
				return entry
			changes = entry.changes.after if lookupAfter else entry.changes.before
			if getattr(changes, str(key), _missing) is not _missing:
				return entry
		return None
	# endregion
	# region AutoMod
	# on_automod_rule_create(rule)
	# on_automod_rule_update(rule)
	# on_automod_rule_delete(rule)
	# on_automod_action(execution)
	# endregion
	# region Channels
	@commands.Cog.listener()
	async def on_guild_channel_delete(self, channel:discord.abc.GuildChannel):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.channel_delete, guild=channel.guild, target=channel)
		await self.bot.generateAuditLog(
			title="Channel deleted", color=AuditColor.DELETE, author=channel.guild, 
			items=[
				{"name": "Channel ID", "value": channel.id},
				{"name": "Channel Name", "value": channel.name},
				{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
			],
			footer_text=f"ID: {channel.id}"
		)
	@commands.Cog.listener()
	async def on_guild_channel_create(self, channel:discord.abc.GuildChannel):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.channel_create, guild=channel.guild, target=channel)
		await self.bot.generateAuditLog(
			title="Channel created", color=AuditColor.CREATE, author=channel.guild, 
			items=[
				{"name": "Channel", "value": channel.mention},
				{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
			],
			footer_text=f"ID: {channel.id}"
		)
	@commands.Cog.listener()
	async def on_guild_channel_update(self, before:discord.abc.GuildChannel, after:discord.abc.GuildChannel):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.channel_update, guild=after.guild, target=after)
		if before.name != after.name:
			await self.bot.generateAuditLog(
				title="Channel renamed", description=after.mention, color=AuditColor.CREATE, author=after.guild, 
				items=[
					{"name": "Before", "value": before.name},
					{"name": "After", "value": after.name},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				],
				footer_text=f"ID: {after.id}"
			)
		if before.position != after.position:
			await self.bot.generateAuditLog(
				title="Channel moved", description=after.mention, color=AuditColor.CREATE, author=after.guild, 
				items=[
					{"name": "Before", "value": before.position},
					{"name": "After", "value": after.position},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				],
				footer_text=f"ID: {after.id}"
			)
		for obj, afterPerms in after.overwrites.items():
			if (beforePerms := before.overwrites_for(obj)) == after.overwrites_for(obj): continue
			if beforePerms.is_empty() and not afterPerms.is_empty():
				pass
			else:
				pass
		for obj, beforePerms in [(i, j) for i, j in before.overwrites.items() if after.overwrites_for(i).is_empty()]:
			...
	# on_guild_channel_pins_update(channel, last_pin)
	# endregion
	# region Guilds
	# on_audit_log_entry_create(self, entry:discord.AuditLogEntry)
	# endregion
	# region Members
	@commands.Cog.listener()
	async def on_member_join(self, member:discord.Member):
		account_age = self._format_account_age(member.created_at)
		await self.bot.generateAuditLog(
			title="User Joined", author=member, color=AuditColor.CREATE, timestamp=member.joined_at,
			items=[
				{"name":"User", "value": member.mention},
				{"name":"Account age", "value": account_age}
			], author_avatar_thumbnail=True
		)
	@commands.Cog.listener()
	async def on_member_remove(self, member:discord.Member):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.kick, guild=member.guild, target=member)
		await self.bot.generateAuditLog(
			title=f"User {"Kicked" if auditLogEntry and auditLogEntry.user and auditLogEntry.user.id != member.id else "Left"}", author=member, color=AuditColor.DELETE, 
			items=[
				{"name": "User", "value": member.mention},
				{"name": "Moderator", "value": auditLogEntry.user.mention} if auditLogEntry and auditLogEntry.user else None
			], author_avatar_thumbnail=True
		)
	@commands.Cog.listener()
	async def on_member_update(self, before:discord.Member, after:discord.Member):
		if before.nick != after.nick:
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.member_update, guild=after.guild, target=after)
			await self.bot.generateAuditLog(
				description=f"**{after.mention} nickname changed**", author=before, color=AuditColor.MODIFY,
				items=[
					{"name": "Before", "value": before.nick},
					{"name": "After", "value": after.nick},
					{"name": "Moderator", "value": auditLogEntry.user.mention} if auditLogEntry and auditLogEntry.user and auditLogEntry.user.id != after.id else None
				]
			)
		if before.roles != after.roles:
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.member_update, guild=after.guild, target=after)
			new_roles = [i for i in after.roles if i not in before.roles]
			if new_roles:
				await self.bot.generateAuditLog(
					title=f"Role{"s" if len(new_roles) > 1 else ""} given", description=", ".join(i.name for i in new_roles), author=after, color=AuditColor.MODIFY, 
					items=[
						{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
					]
				)
			rm_roles = [i for i in before.roles if i not in after.roles]
			if rm_roles:
				await self.bot.generateAuditLog(
					title=f"Role{"s" if len(rm_roles) > 1 else ""} removed", description=", ".join(i.name for i in rm_roles), author=after, color=AuditColor.MODIFY, 
					items=[
						{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
					]
				)
		if not before.is_timed_out() and after.is_timed_out():
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.member_update, guild=after.guild, target=after, key=AuditLogDiffTypes.TIMED_OUT_UNTIL)
			await self.bot.generateAuditLog(
				description=f"**{before.mention} got timed out**", author=after, color=AuditColor.DELETE, 
				items=[
					{"name": "Until", "value": f"{after.timed_out_until.strftime("%Y-%m-%d %H:%M (%Z)")}"},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"},
					{"name": "Reason", "value": auditLogEntry.reason if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
		elif before.is_timed_out() and not after.is_timed_out():
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.member_update, guild=after.guild, target=after, key=AuditLogDiffTypes.TIMED_OUT_UNTIL
			)
			await self.bot.generateAuditLog(
				description=f"**{before.mention}'s timeout has been removed**", author=after, color=AuditColor.CREATE, 
				items=[{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry else "Unknown"}]
			)
	# on_user_update(before, after)
	@commands.Cog.listener()
	async def on_member_ban(self, guild:discord.Guild, user:discord.User|discord.Member):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.ban, guild=guild, target=user)
		await self.bot.generateAuditLog(
			title="User banned", author=guild, color=AuditColor.DELETE, author_avatar_thumbnail=True,
			items=[
				{"name": "User", "value": user.mention},
				{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"},
				{"name": "Reason", "value": auditLogEntry.reason if auditLogEntry else "Unknown"}
			]
		)
	@commands.Cog.listener()
	async def on_member_unban(self, guild:discord.Guild, user:discord.User):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.unban, guild=guild, target=user)
		await self.bot.generateAuditLog(
			title="User unbanned", author=guild, color=AuditColor.MODIFY, author_avatar_thumbnail=True, 
			items=[
				{"name": "User", "value": user.mention},
				{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
			]
		)
	# endregion
	# region Messages
	@commands.Cog.listener()
	async def on_message_edit(self, before:discord.Message, after:discord.Message):
		if after.author.id == self.bot.user.id: return
		if before.content != after.content:
			await self.bot.generateAuditLog(
				title="Message edited", description=f"In channel {after.channel.mention}", author=after.author, url=after.jump_url, color=AuditColor.MODIFY, 
				items=[
					{"name": "Before", "value": before.content},
					{"name": "After", "value":after.content}
				]
			)
		elif not before.pinned and after.pinned:
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.message_pin, guild=after.guild)
			await self.bot.generateAuditLog(
				title="Message pinned", url=after.jump_url, author=after.author, color=AuditColor.CREATE,
				items=[
					{"name": "Channel", "value": after.channel.mention},
					{"name": "Content", "value": after.content},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
		elif before.pinned and not after.pinned:
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.message_unpin, guild=after.guild)
			await self.bot.generateAuditLog(
				title="Message unpinned", url=after.jump_url, author=after.author, color=AuditColor.DELETE,
				items=[
					{"name": "Channel", "value": after.channel.mention},
					{"name": "Content", "value": after.content},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
	@commands.Cog.listener()
	async def on_message_delete(self, message:discord.Message):
		if message.author.id == self.bot.user.id or isinstance(message.channel, discord.DMChannel): return
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.message_delete, guild=message.guild)
		await self.bot.generateAuditLog(
			title="Message deleted", author=message.author, color=AuditColor.DELETE, 
			items=[
				{"name": "Sent by", "value": message.author.mention},
				{"name": "Channel", "value": message.channel.mention}, 
				{"name": "Content", "value": message.content},
				{"name": "Deleted by", "value": auditLogEntry.user.mention} if auditLogEntry and auditLogEntry.user and auditLogEntry.user.id != message.author.id else None
			]
		)
	# on_bulk_message_delete(messages)
	# endregion
	# region Roles
	@commands.Cog.listener()
	async def on_guild_role_create(self, role:discord.Role):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.role_create, guild=role.guild)
		await self.bot.generateAuditLog(
			title="Role created", color=AuditColor.CREATE, author=role.guild,
			items=[
				{"name": "Role", "value": role.mention},
				{"name": "Color", "value": f"#{role._colour:06X}"},
				{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
			]
		)
	@commands.Cog.listener()
	async def on_guild_role_delete(self, role:discord.Role):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.role_delete, guild=role.guild)
		await self.bot.generateAuditLog(
			title="Role deleted", footer_text=f"ID: {role.id}", color=AuditColor.DELETE, author=role.guild,
			items=[
				{"name": "Role ID", "value": role.id},
				{"name": "Role Name", "value": role.name},
				{"name": "Permissions bit array", "value": f"0x{role.permissions.value:014X}"},
				{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
			]
		)
	@commands.Cog.listener()
	async def on_guild_role_update(self, before:discord.Role, after:discord.Role):
		auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.role_update, guild=after.guild)
		if before.color != after.color:
			await self.bot.generateAuditLog(
				title="Role changed", color=AuditColor.MODIFY, author=before.guild,
				items=[
					{"name": "Before", "value": f"#{before._colour:06X}"},
					{"name": "After", "value": f"#{after._colour:06X}"},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
		if before.name != after.name:
			await self.bot.generateAuditLog(
				title="Role renamed", color=AuditColor.MODIFY, author=before.guild,
				items=[
					{"name": "Before", "value": before.name},
					{"name": "After", "value": after.name},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
	# endregion
	# region Scheduled event
	@commands.Cog.listener()
	async def on_scheduled_event_create(self, event:discord.ScheduledEvent):
		await self.bot.generateAuditLog(
			title="Scheduled event created", url=event.url, color=AuditColor.CREATE, author=event.creator,
			items=[
				{"name":"Title", "value":event.name},
				{"name":"Description", "value":event.description} if event.description else None,
				{"name":"Duration", "value": f"{event.start_time.strftime("%Y-%m-%dT%H:%M")} - {event.end_time.strftime("%Y-%m-%dT%H:%M") if event.end_time else "Undefined"}"},
				{"name":"Location", "value": event.location} if event.location else None,
				{"name":"Channel", "value": event.channel.mention} if event.channel else None,
				{"name": "Cover image", "value": event._cover_image} if event._cover_image else None 
			]
		)
	# on_scheduled_event_update(before, after)
	@commands.Cog.listener()
	async def on_scheduled_event_delete(self, event:discord.ScheduledEvent):
		await self.bot.generateAuditLog(
			title="Scheduled event deleted", url=event.url, color=AuditColor.DELETE, author=event.creator, 
			items=[
				{"name":"Title", "value":event.name},
				{"name":"Description", "value":event.description} if event.description else None,
				{"name":"Duration", "value": f"{event.start_time.strftime("%Y-%m-%dT%H:%M")} - {event.end_time.strftime("%Y-%m-%dT%H:%M") if event.end_time else "Undefined"}"},
				{"name":"Location", "value": event.location} if event.location else None,
				{"name":"Channel", "value": event.channel.mention} if event.channel else None,
				{"name": "Cover image", "value": event._cover_image} if event._cover_image else None 
			]
		)
	# endregion
	# region Threads
	# on_thread_create(thread)
	# on_thread_join(thread)
	# on_thread_update(before, after)
	# on_thread_remove(thread)
	# on_thread_delete(thread)
	# endregion
	# region Voice
	@commands.Cog.listener()
	async def on_voice_state_update(self, member:discord.Member, before:discord.VoiceState, after:discord.VoiceState):
		if before.channel is not None and after.channel is None:
			await self.bot.generateAuditLog(
				description=f"{member.mention} left voice channel {before.channel.mention}", color=AuditColor.DELETE, author=member
			)
		elif before.channel is None and after.channel is not None:
			await self.bot.generateAuditLog(
				description=f"{member.mention} left voice channel {after.channel.mention}", color=AuditColor.CREATE, author=member
			)
		elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
			await self.bot.generateAuditLog(
				description=f"{member.mention} switched voice channels {before.channel.mention} -> {after.channel.mention}", color=AuditColor.MODIFY, author=member
			)
		if not before.deaf and (after.deaf and not after.self_deaf):
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.member_update, guild=member.guild, target=member, key=AuditLogDiffTypes.DEAF)
			await self.bot.generateAuditLog(
				title="User server deafened", color=AuditColor.MODIFY, author=member,
				items=[
					{"name": "User", "value": member.mention},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
		elif (before.deaf and not before.self_deaf) and not after.deaf:
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.member_update, guild=member.guild, target=member, key=AuditLogDiffTypes.DEAF, lookupAfter=False)
			await self.bot.generateAuditLog(
				title="User server undeafened", color=AuditColor.MODIFY, author=member,
				items=[
					{"name": "User", "value": member.mention},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
		if not before.mute and (after.mute and not after.self_mute):
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.member_update, guild=member.guild, target=member, key=AuditLogDiffTypes.MUTE)
			await self.bot.generateAuditLog(
				title="User server muted", color=AuditColor.MODIFY, author=member,
				items=[
					{"name": "User", "value": member.mention},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
		elif (before.mute and not before.self_mute) and not after.mute:
			auditLogEntry = await self.getAuditLogEntry(discord.AuditLogAction.member_update, guild=member.guild, target=member, key=AuditLogDiffTypes.MUTE, lookupAfter=False)
			await self.bot.generateAuditLog(
				title="User server unmuted", color=AuditColor.MODIFY, author=member,
				items=[
					{"name": "User", "value": member.mention},
					{"name": "Moderator", "value": auditLogEntry.user.mention if auditLogEntry and auditLogEntry.user else "Unknown"}
				]
			)
	# endregion
async def setup(bot:'Bot'):
	await bot.add_cog(auditLogCog(bot))
