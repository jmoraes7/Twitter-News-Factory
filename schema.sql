DROP TABLE IF EXISTS posts;

CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tweet_id TEXT NOT NULL,
    tweet_url TEXT NOT NULL,
    tweet_text TEXT NOT NULL,
    tweet_user_id TEXT NOT NULL,
    tweet_user_name TEXT NOT NULL,
    tweet_date TEXT NOT NULL,
    gen_date TEXT NOT NULL,
    headline TEXT NOT NULL,
    subheading TEXT NOT NULL,
    summary TEXT NOT NULL,
    article TEXT NOT NULL,
    thumbnail_file TEXT NOT NULL,
    thumbnail_prompt TEXT NOT NULL
);