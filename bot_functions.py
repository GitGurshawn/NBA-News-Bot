# Functions for use in 'discord_bot.py'
import re

# Sees if the bot is currently in a guild with the specified ID (when a bot is kicked/banned from a server while the bot is offline, the guild id doens't get removed properly)
def check_valid_guild(guild_id):
    for guild in client.guilds:
        if int(guild_id) == int(guild.id):
            return True
    return False

# Checks to see if a url is from the twitter domain
def filter_url(url):
    result = re.search("(.*\.)?twitter\.com", url)
    return result != None

# Checks if extended_tweet's expanded url is from the twitter domain
def check_extended_tweet(tweet_info):
    if (len(tweet_info['extended_tweet']['entities']['urls']) != 0) and (filter_url(tweet_info['extended_tweet']['entities']['urls'][0]['expanded_url']) == False):
        return False
    else:
        return True
