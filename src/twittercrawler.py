from bs4 import BeautifulSoup
import requests
import re
import sys
import random
import os

base_url = "https://twitter.com/i/search/timeline"
if sys.platform == "linux" or sys.platform == "linux2":
    uafile = "useragentslinux.txt"
elif sys.platform == "darwin":
    uafile = "useragents.txt"
elif sys.platform == "win32":
    uafile = "useragentwindows.txt"

with open(uafile, "rt") as f:
    ualist = f.read().split("\n")


# tweet related class and functions
class Tweet:

    def __init__(self):
        self.links = []

    def __str__(self):
        return str(self.__dict__)


# functions for processing the html of the tweet
def clean_text(text):
    """Cleans raw text so that it can be written into a csv file without causing any errors."""
    temp = text
    temp.replace("\n", " ")
    temp.replace(",", " ")
    return temp


def has_class(element, class_):
    """Checks if an html element (a bs4 tag element) has a certain class."""
    return "class" in element.attrs and class_ in element.attrs["class"]


# actual sample parsers
def parse_html(crawler, html):
    """Sample parser. Takes the raw inner html from the twitter response and generates tweet objects to be passed to the handler"""
    soup = BeautifulSoup(html, "lxml")
    all_tweets = soup.find_all("li", attrs={"class": "stream-item"})

    for raw_tweet in all_tweets:
        tweet = html_to_tweet_object(raw_tweet)
        yield tweet


def html_to_tweet_object(element):
    """Parses the html of a single tweet from the response, and creates a tweet object."""
    tweet = Tweet()
    tweet_container = list(element.children)[1]
    attributes = tweet_container.attrs

    # add attributes to Tweet object
    tweet.tweet_id = attributes["data-tweet-id"]
    tweet.account_name = attributes["data-name"]
    tweet.user_id = attributes["data-user-id"]

    # find the contents of the tweet
    contents = None
    for c in tweet_container.findChildren():
        if has_class(c, "content"):
            contents = c
            break

    # parse the contents of the tweet for relevant information
    if contents is not None:
        for c in contents.findChildren():

            # parse the time of the tweet
            if has_class(c, "stream-item-header"):
                header = c
                for small in header.findChildren():
                    if has_class(small, "tweet-timestamp"):
                        tweet.timestamp = small.attrs["title"]
                        break

            # parse the text, links of the tweet
            if has_class(c, "js-tweet-text-container"):
                text = c
                for p in text.findChildren():
                    if has_class(p, "tweet-text"):
                        if hasattr(p, "contents") and not isinstance(p.contents[0], type(p)):
                            tweet.text = clean_text(p.contents[0])

                    if has_class(p, "twitter-timeline-link"):
                        if "data-expanded-url" in p.attrs:
                            url = p.attrs["data-expanded-url"]
                            if url not in tweet.links:
                                tweet.links.append(url)

            # parse the stats of the tweet
            if has_class(c, "stream-item-footer"):
                for span in c.findChildren():
                    if has_class(span, "ProfileTweet-action--reply"):
                        for grandchild in span.findChildren():
                            if "data-tweet-stat-count" in grandchild.attrs:
                                tweet.replies = grandchild.attrs["data-tweet-stat-count"]
                                break

                    if has_class(span, "ProfileTweet-action--retweet"):
                        for grandchild in span.findChildren():
                            if "data-tweet-stat-count" in grandchild.attrs:
                                tweet.retweets = grandchild.attrs["data-tweet-stat-count"]
                                break

                    if has_class(span, "ProfileTweet-action--favorite"):
                        for grandchild in span.findChildren():
                            if "data-tweet-stat-count" in grandchild.attrs:
                                tweet.favorites = grandchild.attrs["data-tweet-stat-count"]
                                break

    return tweet


def tweets_to_csv(crawler, tweet):
    """Outputs the profile of the tweets to a csv file."""

    # initialize the output_file
    if crawler.depth == 1:
        if os.path.exists(crawler.output_file):
            pass
        else:
            with open(crawler.output_file, "wt") as f:
                f.write(",".join(crawler.parameters))
                f.write("\n")

    parameters = crawler.parameters

    with open(crawler.output_file, "at") as f:
        for (i, parameter) in enumerate(parameters):
            if hasattr(tweet, parameter):
                f.write(str(getattr(tweet, parameter)))
            else:
                f.write("Null")
            if i < len(parameters) - 1:
                f.write(",")
            else:
                f.write("\n")


class TwitterCrawler:

    def __init__(self, query="hoge", max_depth=None, parser=parse_html, handler=tweets_to_csv, init_min_pos=None, output_file="output",
                 parameters=["tweet_id", "account_name", "user_id", "timestamp", "text", "links", "repiles", "retweets", "favorites"]):
        self.query = query
        self.max_depth = max_depth
        self.parser = parser
        self.handler = handler
        self.last_min_pos = init_min_pos
        self.output_file = output_file
        self.parameters = parameters

        self.depth = None
        self.end_reason = None

    def crawl(self):
        """Actual crawl function. Written as a relatively general interface in case of future updates."""
        connection_cut = False
        seed = self.last_min_pos if self.last_min_pos is not None else "hoge"
        ua = random.choice(ualist)
        headers = {"User-Agent": ua}
        # sample: https://twitter.com/i/search/timeline?vertical=news&q=%40realDonaldTrump&src=typd&include_available_features=1&include_entities=1&lang=en&max_position=TWEET-822697129130852352-822730561210826753-BD1UO2FFu9QAAAAAAAAETAAAAAcAAAASQAAAAACAAAAAAAAAAAAAAAAAgCAAhAAAAAAABAACAgCAAAAQAAAAAAAAAAAAAAAAAIAAgAIgAAAAAAAAEBAgAAAQQAAEAAAAAACAAAAAAACIAAAAAAAAgAgEAAAAAAAAAIAAAAAAIAAAgAAAAAAAAAAAQAAAAAABAAAAAAAAAAAACAAAAEAAgAAAAAAAAAAA&reset_error_state=false
        response = requests.get(base_url,
                                params={"q": self.query,
                                        "max_position": seed,
                                        "vertical": "news",
                                        "src": "typd",
                                        "include_entities": "1",
                                        "include_available_features": "1",
                                        "lang": "en"
                                        }, headers=headers)

        self.depth = 0

        while True:
            self.depth += 1

            data = response.json()

            # data is a python dictionary
            # data should come with keys ['new_latent_count', 'items_html', 'min_position', 'focused_refresh_interval', 'has_more_items']
            min_pos = data["min_position"]

            if self.last_min_pos is not None:
                if not connection_cut and min_pos == self.last_min_pos:
                    print("Starting to loop! Exitting with status:")
                    self.dump()
                    sys.exit(1)

            self.last_min_pos = min_pos
            html = data["items_html"]

            # parse the html
            for item in self.parser(self, html):
                self.handler(self, item)

            # log for debugging
            with open("log" + self.query + ".txt", "at") as f:
                f.write(min_pos + "\n")

            if not self.check_if_finished():
                ua = random.choice(ualist)
                headers = {"User-Agent": ua}
                try:
                    r = requests.get(base_url, params={"q": self.query,
                                                          "vertical": "default",
                                                          "max_position": min_pos,
                                                          "src": "typd",
                                                          "include_entities": "1",
                                                          "include_available_features": "1",
                                                          "lang": "en"
                                                        }, headers=headers)
                except:
                    connection_cut = True
                    continue
                response = r
                connection_cut = False
                # crawl_twitter_recursively(response, parser=parser, status=status)
            else:
                if not data["has_more_items"]:
                    self.end_reason = "no more items"
                elif self.check_if_finished():
                    self.end_reason = "finish condition met"
                else:
                    self.end_reason = "terminated for some unintended reason"
                print("Crawl ended successfuly with following status:")
                self.dump()
                break

    def check_if_finished(self):
        if self.max_depth is not None and self.depth >= self.max_depth:
            return True
        else:
            return False

    def dump(self):
        print("""
            last min pos: {}
            Finish reason: {}
            """.format(self.last_min_pos, self.end_reason))

    def restart(self):
        try:
            with open("log" + self.query + ".txt", "rt") as f:
                seed = f.read().split("\n")[-1]
                self.last_min_pos = seed
                self.crawl()
        except FileNotFoundError:
            print("Error: Failed to find log file for restart.")
