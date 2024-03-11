from datetime import date
from flask import Flask, render_template, redirect, url_for, abort, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import NewPost, RegisterForm, LoginForm, CommentForm
import os
import smtplib


today = date.today().strftime("%B %d, %Y")
year = date.today().strftime("%Y")
EMAIL = os.environ.get('EMAIL')
PASSWORD = os.environ.get('PSS')


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY')
Bootstrap5(app)
ckeditor = CKEditor()
ckeditor.init_app(app)


# Configure Gravatar
gravatar = Gravatar(
    app,
    size=100,
    rating='g',
    default='retro',
    force_default=False,
    force_lower=False,
    use_ssl=False,
    base_url=None
)


# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)

def admin_only(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated and current_user.id == 1:
            return route(*args, **kwargs)
        else:
            return abort(403)
    return wrapper


def user_only(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated:
            return route(*args, **kwargs)
        else:
            return abort(403)
    return wrapper


# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URI', 'sqlite:///themarcoblog.db')
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False)
    password: Mapped[str] = mapped_column(String(250), nullable=False)
    # Adding parent relationship
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    # Adding child relationship with User
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="posts")
    # Adding parent relationship with Comment
    comments = relationship("Comment", back_populates="parent_post")


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Adding child relationship with User
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")
    # Adding child relationship with BLogPost
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")



with app.app_context():
    db.create_all()


@app.route("/register", methods=["POST", "GET"])
def register():
    register_form = RegisterForm()
    if register_form.validate_on_submit():
        email = register_form.email.data
        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        if user:
            flash("You've already registered with that email, please log in instead!")
            return redirect(url_for('login'))
        else:
            new_user = User(
                name=register_form.name.data,
                email=email,
                password=generate_password_hash(register_form.password.data, 'pbkdf2:sha256', 8)
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
        return redirect(url_for('get_all_posts'))
    return render_template('register.html', form=register_form)


@app.route("/login", methods=["POST", "GET"])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        email = login_form.email.data
        password = login_form.password.data
        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        if not user:
            flash("A user with that email does not exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash("Password incorrect, please try again.")
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('get_all_posts'))
    return render_template('login.html', form=login_form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    posts = db.session.execute(db.select(BlogPost)).scalars().all()
    return render_template("index.html", all_posts=posts, year=year)


# TODO: Add a route so that you can click on individual posts.
@app.route('/post/<int:post_id>', methods=["POST", "GET"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("Please login or register  to comment on the blog posts!")
            return redirect(url_for('login'))
        else:
            new_comment = Comment(
                text=comment_form.comment.data,
                comment_author=current_user,
                parent_post=requested_post
            )
            db.session.add(new_comment)
            db.session.commit()
            # Cleaning text from last comment
            comment_form.comment.data = ""
    return render_template("post.html", post=requested_post, current_user=current_user, comment_form=comment_form, year=year)


@app.route("/new-post", methods=["POST", "GET"])
@admin_only
def make_post():
    form = NewPost()
    if form.validate_on_submit():
        new_post = BlogPost(
                title=form.title.data,
                subtitle=form.subtitle.data,
                date=today,
                body=form.body.data,
                author=current_user,
                img_url=form.img_url.data
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('get_all_posts'))
    return render_template("make-post.html", current_user=current_user, form=form, year=year)


@app.route("/edit-post/<int:post_id>", methods=["POST", "GET"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = NewPost(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        body=post.body,
        author=current_user.name
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.body = edit_form.body.data
        post.author = current_user
        db.session.commit()
        return redirect(url_for('show_post', post_id=post.id))
    return render_template("make-post.html", form=edit_form, current_user=current_user, is_edit=True, year=year)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/delete-comment/<int:comment_id>/<int:post_id>")
@user_only
def delete_comment(comment_id, post_id):
    comment = db.get_or_404(Comment, comment_id)
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for('show_post', post_id=post_id))

# Below is the code from previous lessons. No changes needed.
@app.route("/about")
def about():
    return render_template("about.html", year=year)


@app.route("/contact", methods=["POST", "GET"])
def contact():
    if request.method == "POST":
        with smtplib.SMTP_SSL("smtp-relay.gmail.com") as connection:
            connection.starttls()
            connection.login(user=EMAIL, password=PASSWORD)
            connection.sendmail(
                from_addr=EMAIL,
                to_addrs=EMAIL,
                msg=f"Subject:New Message from themarcoblog.com\n\n"
                    f"Name: {request.form['name']}\n"
                    f"Email: {request.form['email']}\n"
                    f"Phone: {request.form['phone']}\n"
                    f"Message: {request.form['message']}")
        return render_template("contact.html", year=year, msg_sent=True)
    return render_template("contact.html", year=year)


if __name__ == "__main__":
    app.run(debug=True, port=5003)
