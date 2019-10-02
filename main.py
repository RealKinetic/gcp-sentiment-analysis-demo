import datetime
import logging
import os
from urllib.parse import urlparse

from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from google.cloud import firestore
from google.cloud import language
from google.cloud.language import enums
from google.cloud.language import types

import tweepy


ENV = os.getenv('ENV', 'DEV')
CONSUMER_KEY = os.getenv('CONSUMER_KEY')
CONSUMER_SECRET = os.getenv('CONSUMER_SECRET')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('ACCESS_TOKEN_SECRET')

SENTIMENT_HAPPIEST = 'happiest'
SENTIMENT_HAPPIER = 'happier'
SENTIMENT_HAPPY = 'happy'
SENTIMENT_NEUTRAL = 'neutral'
SENTIMENT_UNHAPPY = 'unhappy'
SENTIMENT_UNHAPPIER = 'unhappier'
SENTIMENT_UNHAPPIEST = 'unhappiest'

log = logging.getLogger()
auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
twitter_api = tweepy.API(auth)
language_client = language.LanguageServiceClient()
app = Flask(__name__)


db = firestore.Client()


def calibrated_score(score, magnitude):
    calibrated = abs(score) + (0.08 * magnitude)
    if score < 0:
        calibrated = calibrated * -1
    return calibrated

def translate_sentiment(score, magnitude):
    score = calibrated_score(score, magnitude)

    # Sentiment is on a scale from -1.0 (very bad) to 1.0 (very good).
    # -0.25 to 0.25 is approximately neutral.
    if -0.25 <= score <= 0.25:
        return SENTIMENT_NEUTRAL

    if -0.45 < score < -0.25:
        return SENTIMENT_UNHAPPY

    if -0.75 < score <= -0.45:
        return SENTIMENT_UNHAPPIER

    if score <= -0.75:
        return SENTIMENT_UNHAPPIEST

    if 0.45 > score > 0.25:
        return SENTIMENT_HAPPY

    if 0.75 > score >= 0.45:
        return SENTIMENT_HAPPIER

    return SENTIMENT_HAPPIEST


@app.route('/')
def index():
    try:
        return render_template('index.html', tweets=_get_tweets())
    except Exception as e:
        log.error(e)
        return str(e), 500


@app.route('/analyze', methods=['POST'])
def analyze_tweet():
    try:
        _analyze_tweet()
    except Exception as e:
        log.error(e)
    return redirect('/')


def _get_tweets():
    # Then query for documents
    tweets_ref = db.collection(u'tweets')
    tweet_docs = tweets_ref.get()

    tweets = []
    for tweet in tweet_docs:
        tweet_ = tweet.to_dict()
        tweet_["sentiment"] = translate_sentiment(
            tweet_["score"], tweet_["magnitude"])

        tweets.append(tweet_)

    return tweets


def _analyze_tweet():
    # Pull tweet id from url.
    tweet_url = request.form.get('tweet')
    tweet_id = _get_tweet_id(tweet_url)

    # Fetch the tweet content.
    tweet = twitter_api.get_status(tweet_id, tweet_mode='extended')

    # Analyze the tweet content's sentiment.
    sentiment = _get_sentiment(tweet)

    tweet_doc = {
        u'tweet_id': tweet_id,
        u'text': tweet.full_text,
        u'date': firestore.SERVER_TIMESTAMP,
        u'url': tweet_url,
        u'magnitude': sentiment.magnitude,
        u'score': sentiment.score
    }

    doc_ref = db.collection(u'tweets').add(tweet_doc)

    return tweet_doc


def _get_tweet_id(tweet_url):
    # Tweet urls are of the form:
    # https://twitter.com/<username>/status/<id>
    url = urlparse(tweet_url)
    if url.hostname != 'twitter.com':
        raise Exception('Invalid hostname')

    if not url.path:
        raise Exception('Invalid path')

    parts = url.path.split('/')
    if len(parts) != 4:
        raise Exception('Invalid path')

    return int(parts[3])


def _get_sentiment(tweet):
    document = types.Document(
        content=tweet.full_text,
        type=enums.Document.Type.PLAIN_TEXT
    )
    return language_client.analyze_sentiment(
        document=document).document_sentiment




if __name__ == '__main__':
    # This is used when running locally only.
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 8080), debug=True)
