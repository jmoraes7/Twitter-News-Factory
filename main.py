import os, re
import sqlite3
import tweepy
from datetime import datetime
from flask import Flask, redirect, request, url_for, render_template
from werkzeug.exceptions import abort
import openai
import io
import warnings
from PIL import Image
from stability_sdk import client
import stability_sdk.interfaces.gooseai.generation.generation_pb2 as generation

app = Flask(__name__, static_url_path="/static")
app.config['SECRET_KEY'] = os.environ["FLASK_KEY"]


def get_db_connection():
  conn = sqlite3.connect('database.db')
  conn.row_factory = sqlite3.Row
  return conn


def get_post(tweet_id):
  conn = get_db_connection()
  post = conn.execute('SELECT * FROM posts WHERE tweet_id = ?',
                      (tweet_id, )).fetchone()
  conn.close()
  if post is None:
    abort(404)
  return post


@app.route('/')
def index():
  conn = get_db_connection()
  posts = conn.execute(
    'SELECT * FROM posts ORDER BY id DESC LIMIT 100').fetchall()
  conn.close()
  return render_template("index.html", posts=posts)


@app.route('/process_tweet', methods=["POST"])
def add():
  error = None
  form = request.form

  # Check if URL is valid
  id_regex = r"/status/(\d+)"
  match = re.search(id_regex, form["tweet_url"])
  if match == None:
    print("Not a valid Twitter URL")
    error = "Failing Regex. Not a valid Twitter URL"
    return render_template("error.html", error=error)
  if len(str(match.group(1))) != 19:
    print("Failing Regex. Not a Twitter URL containing a Tweet ID")
    error = "Failing Regex. Not a Twitter URL containing a Tweet ID"
    return render_template("error.html", error=error)
  tweet_id = str(match.group(1))

  # Get tweet info
  tweepy_client = tweepy.Client(os.environ["TWEEPY_KEY"])
  try:
    tweet = tweepy_client.get_tweet(tweet_id,
                                    tweet_fields=["created_at"],
                                    expansions="author_id")
  except tweepy.error.TweepyException as e:
    print("Tweepy API call failed. Not able to get tweet.")
    error = "Tweepy API call failed. Not able to get tweet. "
    error += str(e)
    return render_template("error.html", error=error)

  stripped_url_match = r"(.+/status/\d+)"
  match = re.search(stripped_url_match, form["tweet_url"])
  tweet_url = match.group(1)

  tweet_text = tweet.data.text
  tweet_date = tweet.data.created_at
  tweet_user_id = tweet.data.author_id
  tweet_user_name = tweet.includes["users"][0].username
  gen_date = datetime.now()

  # add tweet text to prompt and call GPT Davinci 003 API
  gpt_prompt = f"""Turn the following into an article in the style of the New York Times: {tweet_text}
  
  Your response should be structured exactly like this:
  Headline:
  Subheading:
  Summary:
  Article:
  Prompt for thumbnail image:
  """

  try:
    openai.api_key = os.environ["OPENAI_API_KEY"]

    response = openai.Completion.create(model="text-davinci-003",
                                        prompt=gpt_prompt,
                                        temperature=0.7,
                                        max_tokens=500,
                                        top_p=1,
                                        frequency_penalty=0,
                                        presence_penalty=0)

    response = response["choices"][0]["text"]
    # print(response)
  except Exception as e:
    print("Error calling OpenAI API")
    print(e)
    error = "Error calling OpenAI API: " + str(e)
    return render_template("error.html", error=error)

  # Parse the response into variables
  start_headline = response.index("Headline:") + len("Headline:")
  end_headline = response.index("Subheading:")
  start_subheading = response.index("Subheading:") + len("Subheading:")
  end_subheading = response.index("Summary:")
  start_summary = response.index("Summary:") + len("Summary:")
  end_summary = response.index("Article:")
  start_article = response.index("Article:") + len("Article:")
  end_article = response.lower().index("prompt for thumbnail image:")
  start_thumbnail = response.lower().index(
    "prompt for thumbnail image:") + len("prompt for thumbnail image:")
  end_thumbnail = len(response)

  headline = response[start_headline:end_headline].strip()
  subheading = response[start_subheading:end_subheading].strip()
  summary = response[start_summary:end_summary].strip()
  article = response[start_article:end_article].strip()
  thumbnail_prompt = response[start_thumbnail:end_thumbnail].strip()

  def to_snake_case(string):
    snake_case = re.sub(r'\W+', '_', string).lower()
    return snake_case[:40]

  thumbnail_file = to_snake_case(thumbnail_prompt)

  # print(headline, subheading, summary, article, thumbnail_prompt, thumbnail_file)

  # call Stable Diffusion API
  try:
    stability_api = client.StabilityInference(
      key=os.environ['STABILITY_KEY'],  # API Key reference.
      verbose=True,  # Print debug messages.
      engine="stable-diffusion-v1-5",  # Set the engine to use for generation. 
      # Available engines: stable-diffusion-v1 stable-diffusion-v1-5 stable-diffusion-512-v2-0 stable-diffusion-768-v2-0 stable-inpainting-v1-0 stable-inpainting-512-v2-0
    )

    answers = stability_api.generate(prompt=thumbnail_prompt,
                                     seed=992446758,
                                     steps=30,
                                     cfg_scale=8.0,
                                     width=512,
                                     height=320,
                                     samples=1,
                                     sampler=generation.SAMPLER_K_DPMPP_2M)

    for resp in answers:
      for artifact in resp.artifacts:
        if artifact.finish_reason == generation.FILTER:
          warnings.warn(
            "Your request activated the API's safety filters and could not be processed."
            "Please modify the prompt and try again.")
        if artifact.type == generation.ARTIFACT_IMAGE:
          image_path = "static/images/"
          img = Image.open(io.BytesIO(artifact.binary))
          img.save(
            f"{image_path}{str(thumbnail_file)}.png"
          )  # Save our generated images with their seed number as the filename.
  except Exception as e:
    print("Error calling Stable Diffusion API: ")
    print(e)
    error = "Error calling Stable Diffusion API: " + str(e)
    return render_template("error.html", error=error)

  # convert all to string
  tweet_id = str(tweet_id)
  tweet_url = str(tweet_url)
  tweet_date = str(tweet_date)
  tweet_user_id = str(tweet_user_id)
  tweet_user_name = str(tweet_user_name)
  gen_date = str(gen_date)
  headline = str(headline)
  subheading = str(subheading)
  summary = str(summary)
  article = str(article)
  thumbnail_file = str(thumbnail_file)
  thumbnail_prompt = str(thumbnail_prompt)

  # add to database
  try:
    conn = get_db_connection()
    conn.execute(
      'INSERT INTO posts (tweet_id, tweet_url, tweet_text, tweet_user_id, tweet_user_name, tweet_date, gen_date, headline, subheading, summary, article, thumbnail_file, thumbnail_prompt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      (tweet_id, tweet_url, tweet_text, tweet_user_id, tweet_user_name,
       tweet_date, gen_date, headline, subheading, summary, article,
       thumbnail_file, thumbnail_prompt))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))
  except Exception as e:
    print("Error adding to database")
    print(e)
    error = "Error adding to database: " + str(e)
    return render_template("error.html", error=error)


@app.route('/article/<tweet_id>')
def article(tweet_id):
  post = get_post(tweet_id)
  article = post['article'].split('\n')
  return render_template("article.html",
                         tweet_id=tweet_id,
                         post=post,
                         article=article)


@app.route('/error')
def error():
  error = ""
  return render_template("error.html", error=error)


@app.route('/manage_db')
def manage_db():
  return render_template("manage_db.html")


@app.route('/delete_article', methods=["POST"])
def delete_article():
  form = request.form
  if form["db_key"] == os.environ["DB_KEY"]:
    try:
      article = get_post(form["tweet_id"])
      conn = get_db_connection()
      conn.execute('DELETE FROM posts WHERE tweet_id = ?',
                   (form["tweet_id"], ))
      conn.commit()
      conn.close()
      return redirect(url_for('index'))
    except:
      return render_template(
        "error.html", error="Failed to find or delete item in database.")
  return render_template("error.html", error="Access denied")


app.run(host='0.0.0.0', port=81)
