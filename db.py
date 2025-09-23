import os
import psycopg2

conn = psycopg2.connect(
    host="localhost", database="flask_db", user="postgres", password="Lalo"
)

cur = conn.cursor()

# Table Books

# cur.execute("DROP TABLE IF EXISTS books;")

# cur.execute(
#     "CREATE TABLE books (id serial PRIMARY KEY,"
#     "title varchar (150) NOT NULL,"
#     "author_id int NOT NULL,"
#     "Description text NOT NULL,"
#     "category_id int NOT NULL,"
#     "price numeric (10, 2) NOT NULL,"
#     "cover varchar (255) NOT NULL,"
#     "file varchar (255) NOT NULL,"
#     "date_added date DEFAULT CURRENT_TIMESTAMP);"
# )

# cur.execute(
#     """
#     INSERT INTO books (title, author_id, description, category_id, price, cover, file)
#     VALUES (%s, %s, %s, %s, %s, %s, %s)
#     RETURNING id;
# """,
#     (
#         "Crime and Punishment",
#         1,
#         "A classic psychological novel about Raskolnikov, a poor student in St. Petersburg, whose crime leads to guilt, paranoia, and a search for redemption.",
#         1,
#         15.99,
#         "crime_and_punishment.jpg",
#         "crime_and_punishment.pdf",
#     ),
# )

# Table Authors

# cur.execute("DROP TABLE IF EXISTS authors;")

# cur.execute(
#     """
#     CREATE TABLE authors (id serial PRIMARY KEY,
#     name varchar(255) NOT NULL
#     );
# """
# )

# cur.execute(
#     """
#     INSERT INTO authors (name)
#     VALUES (%s)
#     RETURNING id;
# """,
#     ("Fyodor Dostoevsky",),
# )

# Table Categories

# cur.execute("DROP TABLE IF EXISTS categories;")

# cur.execute(
#     """
#     CREATE TABLE categories (id serial PRIMARY KEY,
#     name varchar(255) NOT NULL
#     );
# """
# )

# cur.execute(
#     """
#     INSERT INTO categories (name)
#     VALUES (%s)
#     RETURNING id;
# """,
#     ("Novel",),
# )

# cur.execute(
#     """
#     ALTER TABLE categories
#     ADD CONSTRAINT unique_category_name UNIQUE (name);
# """
# )

# cur.execute(
#     """
#     ALTER TABLE authors
#     ADD CONSTRAINT unique_author_name UNIQUE (name);
# """
# )

# cur.execute(
#     """
#     CREATE TABLE contact_messages (
#     id           BIGSERIAL PRIMARY KEY,
#     name         TEXT NOT NULL,
#     email        TEXT NOT NULL,
#     subject      TEXT NOT NULL,
#     message      TEXT NOT NULL,
#     want_copy    BOOLEAN DEFAULT FALSE,
#     ip           INET,
#     user_agent   TEXT,
#     created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
# );
#  """
# )


# cur.execute(
#     """
#     CREATE TABLE IF NOT EXISTS wishlists (
#     user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#     book_id    BIGINT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
#     created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
#     PRIMARY KEY (user_id, book_id)
# );
#  """
# )


conn.commit()
cur.close()
conn.close()
