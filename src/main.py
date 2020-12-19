#!/usr/bin/env python3
"""Bot to create games on discord."""
import logging.handlers
import time
import traceback
import shlex

import discord
from bosspiles_integration import generate_matches_from_bosspile
from bga_game_list import bga_game_message_list, is_game_valid
from bga_table_status import get_tables_by_players
from bga_create_game import setup_bga_game
from creds_iface import setup_bga_account
from bga_add_friend import add_friends
from keys import TOKEN
from tfm_create_game import init_tfm_game
from menu_root import trigger_interactive_response
from utils import send_help, force_double_quotes

LOG_FILENAME = "errs"
SUBCOMMANDS = ["!setup", "!play", "!status", "!help", "!options", "!list", "!friend", "!tfm"]
logger = logging.getLogger(__name__)
logging.getLogger("discord").setLevel(logging.WARN)
# Add the log message handler to the logger
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=10000000, backupCount=0)
formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

intents = discord.Intents(messages=True, guilds=True, members=True)
client = discord.Client(intents=intents)
# Keep track of context in global variable {"<author id>": {"context": context, "timestamp": int timestamp}}
contexts = {}


@client.event
async def on_ready():
    """Let the user who started the bot know that the connection succeeded."""
    logger.info(f"{client.user.name} has connected to Discord, and is active on {len(client.guilds)} servers!")
    listening_to_help = discord.Activity(type=discord.ActivityType.listening, name="!help")
    await client.change_presence(activity=listening_to_help)


@client.event
async def on_message(message):
    """Listen to messages so that this bot can do something."""
    # Don't respond to this bot's own messages!
    if message.author == client.user:
        return
    if message.content.startswith("!bga"):  # Transition to new syntax
        message.content = message.content.replace("bga ", "").replace("make", "play").replace("tables", "status")
        message.content = message.content.replace("bga", "help")  # If it's just !bga, do !help instead
    if any([message.content.startswith(i) for i in SUBCOMMANDS]):
        log_received_message(message)
        if message.content.startswith("!tfm"):
            await try_catch(message, init_tfm_game, [message])
        else:
            # Preserve command syntax and when there are missing args, go interactive
            try:
                message.content = force_double_quotes(message.content)
                args = shlex.split(message.content)
                await try_catch(message, trigger_bga_action, [message, args])
            except ValueError as e:
                await message.channel.send("Problem parsing command: " + str(e))
    # Use a contexts variable to keep track of next step for user.
    # this can be anything the user sends to the bot and needs to be parsed according to the context.
    elif str(message.channel.type) == "private" and message.channel.me == client.user:
        log_received_message(message)
        safe_to_check_timestamp = str(message.author) in contexts and "timestamp" in contexts[str(message.author)]
        if safe_to_check_timestamp and contexts[str(message.author)]["timestamp"] > time.time() - 30:
            interactive_args = [message, contexts, message.content.split(" ")[0][1:], []]
            await try_catch(message, trigger_interactive_response, interactive_args)
        else:
            await message.channel.send("Operation timed out...")
            await try_catch(message, trigger_interactive_response, [message, contexts, "timeout", []])
    # Integration with Bosspiles bot
    elif message.author.id == 713362507770626149 and ":vs:" in message.content:
        logger.debug("Bosspile integration has been triggered.")
        await try_catch(message, generate_matches_from_bosspile, [message])


def log_received_message(message):
    """Log incoming messages, but strip passwords if possible.

    Passwords are expected in the !setup longform command
    as well as !setup when the context is `bga password`
    """
    is_context_bga_password = (
        str(message.author) in contexts
        and "context" in contexts[str(message.author)]
        and contexts[str(message.author)] == "bga password"
    )
    if not is_context_bga_password:
        msg = message.content
        if "setup" not in message.content:
            msg = " ".join(msg.split(" ")[:-1])  # Don't log passwords, which should be last arg
        logger.debug(
            f"Received message from {message.author.name} (ID:{message.author.id}) on server {message.guild.name}: `{msg}`",
        )


async def try_catch(message, function, args_list):
    try:
        await function(*args_list)
    except discord.errors.Forbidden as e:
        if e.text == "403 Forbidden (error code: 50013): Missing Permissions":
            await message.channel.send(
                "The operation failed because admins didn't give the bot the permissions it needs on this server. Try kicking and readding the bot.",
            )
        elif e.text == "403 Forbidden (error code: 50007): Cannot send messages to this user":
            await message.channel.send(
                "Cannot send messages to this user. This may be because this user has DMs disabled for non-friends or that admins didn't give this bot the permissions it needs.",
            )
        else:
            await message.channel.send("Operation failed due to problem with permissions: " + e.text)
    except Exception as e:
        logger.error("Encountered error:" + str(e) + "\n" + str(traceback.format_exc()))
        await message.channel.send("Tell <@!234561564697559041> to fix his bga bot.")


async def trigger_bga_action(message, args):
    author = str(message.author)
    command = args[0][1:]
    args.remove(args[0])
    noninteractive_commands = ["list", "help", "options"]
    if command in noninteractive_commands:
        contexts[author] = {}
    if command == "setup" and len(args) == 2:
        bga_user, bga_passwd = args[1], args[2]
        await setup_bga_account(message, bga_user, bga_passwd)
    elif command == "play" and len(args) >= 2:
        options = {}
        game = args[0]
        players = args[1:]
        for arg in args:
            if ":" in arg:
                key, value = arg.split(":")[:2]
                options[key] = value
                # Options with : are not players
                players.remove(arg)
        discord_id = message.author.id
        await setup_bga_game(message, discord_id, game, players, options)
    elif command == "status" and len(args) >= 2:
        game = ""  # if game isn't specified, then bot will search for all games
        for arg in args:
            if await is_game_valid(arg):
                game = arg
                args.remove(game)
        players = args  # remaining args will all of the players
        await get_tables_by_players(players, message, game_target=game)
    elif command == "friend" and len(args) >= 2:
        await add_friends(args[1:], message)
    elif command == "list":
        game_sublists = await bga_game_message_list()
        for sublist in game_sublists:  # All messages are 1000 chars <=
            await message.channel.send(sublist)
    elif command == "help":
        await send_help(message, "bga_help")
    elif command == "options":
        await send_help(message, "bga_options")
    else:
        await trigger_interactive_response(message, contexts, command, args)


client.run(TOKEN)
