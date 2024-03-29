import datetime
import logging
import os
from urllib.parse import urlparse

from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from google.cloud import language
from google.cloud.language import enums
from google.cloud.language import types
import sqlalchemy
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import tweepy


ENV = os.getenv('ENV', 'DEV')
CONSUMER_KEY = os.getenv('CONSUMER_KEY')
CONSUMER_SECRET = os.getenv('CONSUMER_SECRET')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('ACCESS_TOKEN_SECRET')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME', 'sentiment')
DB_CONN_NAME = os.getenv('DB_CONN')

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

query = {'charset': 'utf8mb4'}
if ENV == 'PROD':
    # Cloud SQL Proxy uses a special Unix socket.
    query['unix_socket'] = '/cloudsql/{}'.format(DB_CONN_NAME)

## Connect to Cloud SQL.
db = sqlalchemy.create_engine(
    sqlalchemy.engine.url.URL(
        drivername='mysql+pymysql',
        username=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        query=query
    ),
)
Base = declarative_base()
Session = sessionmaker(bind=db)


class Tweet(Base):
    __tablename__ = 'tweets'
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.datetime.now, index=True)
    text = Column(String(300))
    url = Column(String(1024))
    magnitude = Column(Float)
    score = Column(Float)

    def calibrated_score(self):
        score = abs(self.score) + (0.08 * self.magnitude)
        if self.score < 0:
            score = score * -1
        return score

    def translate_sentiment(self):
        score = self.calibrated_score()

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

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'text': self.text,
            'url': self.url,
            'magnitude': self.magnitude,
            'score': self.score,
        }


# Create tables if they don't exist.
Base.metadata.create_all(db)


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
    session = Session()
    return session.query(Tweet).order_by(Tweet.date.desc()).limit(10)


def _analyze_tweet():
    # Pull tweet id from url.
    tweet_url = request.form.get('tweet')
    tweet_id = _get_tweet_id(tweet_url)

    # Fetch the tweet content.
    tweet = twitter_api.get_status(tweet_id, tweet_mode='extended')

    # Analyze the tweet content's sentiment.
    sentiment = _get_sentiment(tweet)

    # Write the result to Cloud SQL.
    result = Tweet(
        text=tweet.full_text,
        url=tweet_url,
        magnitude=sentiment.magnitude,
        score=sentiment.score
    )
    session = Session()
    session.add(result)
    session.commit()
    return result


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


def gcf_entrypoint(req):
    """Wrapper for Google Cloud Functions entrypoint."""

    if req.path == '/':
        try:
            return jsonify([tweet.to_dict() for tweet in _get_tweets()])
        except Exception as e:
            log.error(e)
            return str(e), 500

    if req.path == '/analyze':
        try:
            return jsonify(_analyze_tweet().to_dict())
        except Exception as e:
            log.error(e)
            return str(e), 500

    return 'Not Found', 404


if __name__ == '__main__':
    # This is used when running locally only.
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 8080), debug=True)
