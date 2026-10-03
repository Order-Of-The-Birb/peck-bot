"""Resource limits shared by commands on the bot's single asyncio event loop."""

from asyncio import Semaphore


# Keep this gate outside utils.wt and utils.generic: cog reloads replace those
# modules, but an in-flight browser and its queued callers must keep one gate.
# Do not add this module to the cog dependency reload prefixes.
browser_slot = Semaphore(1)
