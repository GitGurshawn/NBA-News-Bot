from tweepy import StreamListener, Stream, OAuthHandler
from discord.ext import commands, tasks
from bot_functions import check_valid_guild, filter_url, check_extended_tweet
from urllib3.exceptions import ProtocolError
import discord
import asyncio
import json
import psycopg2

# PostgreSQL database connection
con = psycopg2.connect(host="HOSTNAME", database="DATABASE", user="USER", password="PASSWORD")
cur = con.cursor()

# Tweepy auth
auth = OAuthHandler("CONSUMER_KEY", "CONSUMER_SECRET")
auth.set_access_token("KEY", "SECRET")

# Holds current valid tweet links
# Needs to be an array since quick consecutive tweets will not be read correctly, so a posting queue is needed
tweet_links = []

# Obtains custom prefix for each server the bot is in
def get_prefix(client, message):
    cur.execute("SELECT prefix FROM servers WHERE guild_id = " + str(message.guild.id))
    rows = cur.fetchall()
    return rows[0]

client = commands.Bot(command_prefix = get_prefix)
client.remove_command('help') # Deletes the help command included in the discord.py package

# Tweetpy tweet listener (async)
class StdOutListener(StreamListener):
    def on_data(self, data):
        try:
            tweet_info = json.loads(data)
            tweet_text = tweet_info["text"]
            tweet_link = "https://twitter.com/" + tweet_info["user"]["screen_name"] + "/status/" + str(tweet_info["id"])
            
            if tweet_info['user']['screen_name'] == "wojespn":
                # Filters out retweets, tweets with URLS (always promotions), and any replies
                if (not tweet_text.startswith("RT @")) and (tweet_info['is_quote_status'] == False) and (tweet_info['in_reply_to_status_id_str'] == None) and (len(tweet_info['entities']['urls']) == 0): # no need to check urls
                    tweet_links.append(tweet_link)
                elif (not tweet_text.startswith("RT @")) and (tweet_info['is_quote_status'] == False) and (tweet_info['in_reply_to_status_id_str'] == None) and (len(tweet_info['entities']['urls']) != 0): # must check urls
                    # some tweets have expanded urls even if they don't have a url link in their tweet (not sure why). to fix this problem, we have to filter out domains outside of twitter.com
                    # now it will filter out urls (ads, promotions, etc.), but won't filter out valid tweets that have an expanded url key in the 'tweet_info' dictionary.
                    if filter_url(tweet_info['entities']['urls'][0]['expanded_url']) == True:
                        # tweets with raw urls in them create an 'extended_tweet' key in the dictionary. we must check their entities as well (example tweet: https://twitter.com/wojespn/status/1339600503085228038)
                        if not ('extended_tweet' in tweet_info and check_extended_tweet(tweet_info) == False):
                            tweet_links.append(tweet_link)
        except KeyError as e:
            pass # deleted tweets cause KeyErrors

    def on_error(self, status):
        print(status)

# Bot's startups tasks        
@client.event
async def on_ready():
    twitterStream = Stream(auth,StdOutListener())
    try:
        twitterStream.filter(follow=["50323173"], is_async=True) # Follows @wojespn's tweets
    except ProtocolError:
        # Needed to avoid stream ending because of backlogged tweets (caused from large amount of retweets being filtered out)
        pass
    await client.change_presence(activity=discord.Game(name="!bball help")) # sets bot's status
    post_tweet.start()

# changeprefix command
@client.command()
async def changeprefix(ctx, prefix=None):
    if prefix != None:
        cur.execute("UPDATE servers SET prefix = %s WHERE guild_id = %s", (str(prefix) + " ", str(ctx.message.guild.id)))
        con.commit()
        await ctx.send("Changed prefix to " + str(prefix))
    else:
        await ctx.send("Must specify prefix, type `!bball help changeprefix` for more information")

# setchannel command
@client.command()
async def setchannel(ctx, channel_id=None):
    found_id = False
    
    if channel_id != None:
        for channel in ctx.guild.text_channels:
            if str(channel_id) == str(channel.id):
                found_id = True
                cur.execute("UPDATE servers SET text_channel = %s WHERE guild_id = %s", (str(channel_id) + " ", str(ctx.message.guild.id)))
                con.commit()
                await ctx.send("Successfully changed channel to `" + channel.name + "`")
        if found_id == False:
            await ctx.send("The specified channel ID could not be found in the server. Make sure you are using the correct channel ID")
    else:
        await ctx.send("Must specify channel ID, type `!bball help setchannel` for more information")

# Overridden help command
@client.command()
async def help(ctx, command=None):
    if command == None:
        embedVar = discord.Embed(title="Help for NBA News Bot", description='Support Adrian Wojnarowski by following him on  twitter [here](https://twitter.com/wojespn)', color=0x00ff00)
        embedVar.add_field(name="Commands", value='`changeprefix`, `setchannel`', inline=False)
        embedVar.add_field(name="Command Help", value='Type `!bball help <command name>` for descriptions of each command', inline=False)
        await ctx.send(embed=embedVar)
    else:
        if command == "changeprefix":
            embedVar = discord.Embed(title="Command Help for: `changeprefix`", description='\u200b', color=0x00ff00)
            embedVar.add_field(name="Description", value="Changes the prefix for the bot's commands. Type `!bball changeprefix <prefix>` to set it to the specified prefix."
                                                          "There is no need to add a space after the your custom prefix since it will be automatically be added.", inline=False)
            await ctx.send(embed=embedVar)
            
        elif command == "setchannel":
            embedVar = discord.Embed(title="Command Help for: `setchannel`", description='\u200b', color=0x00ff00)
            embedVar.add_field(name="Description", value="Changes the text channel that the bot posts the tweet links to. You will need to obtain the desired text channel's"
                                                          "channel ID to make the switch. Type `!bball setchannel <channel id>` to set the channel to the specified channel ID.", inline=False)
            await ctx.send(embed=embedVar)
        else:
            await ctx.send("Command not found, see list of commands using `!bball help`")
                       

# Checks every 10 seconds to see if a valid tweet needs to be posted to each server's assigned text-channel
@tasks.loop(seconds=10)
async def post_tweet():
    await client.wait_until_ready()
    if len(tweet_links) != 0:
        for x in tweet_links.copy():
            cur.execute("SELECT text_channel FROM servers")
            rows = cur.fetchall()

            for row in rows:
                channel = client.get_channel(int(row[0]))

                try:
                    await channel.send(x)
                except AttributeError:
                    # Invalid channel ID (deleted channel)
                    cur.execute("SELECT guild_id FROM servers WHERE text_channel = %s", (row[0],))
                    result = cur.fetchall()
                    gid = int(result[0][0])
                    if check_valid_guild(gid):
                        curr_guild = client.get_guild(gid)
                        cur.execute("UPDATE servers SET text_channel = %s WHERE guild_id = %s", (str(curr_guild.text_channels[0].id), gid))
                        con.commit()
                        channel = client.get_channel(int(curr_guild.text_channels[0].id))
                        await channel.send(x)
                    else:
                        # bot no longer connected to server, so it gets removed from db
                        cur.execute("DELETE FROM servers WHERE guild_id = %s", (gid,))
                        con.commit()
                    
            tweet_links.pop(0)

# Adds server id to database when bot enters server
@client.event
async def on_guild_join(guild):
    cur.execute("INSERT INTO servers (guild_id, text_channel, prefix) VALUES (%s, %s, %s)", (guild.id, str(guild.text_channels[0].id), "!bball "))
    con.commit()
    await guild.text_channels[0].send("Welcome to the NBA News Bot. You will now recieve NBA news tweets from Adrian Wojnarowski on this text channel. Type '!bball"
                                       "help setchannel' to learn how to set the bot to a different text channel.")

# Removes server id from database if bot leaves sever
@client.event
async def on_guild_remove(guild):
    cur.execute("DELETE FROM servers WHERE guild_id = %s", (guild.id,))
    con.commit()

client.run("DISCORD_TOKEN") # discord token

